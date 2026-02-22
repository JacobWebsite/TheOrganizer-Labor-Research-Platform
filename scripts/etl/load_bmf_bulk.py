#!/usr/bin/env python3
"""
Bulk loader for IRS EO Business Master File extracts.

Features:
- Downloads all BMF extract files linked from IRS EO BMF page
- Supports CSV and fixed-width formats
- Adds required columns to irs_bmf idempotently
- Uses COPY -> staging table -> ON CONFLICT upsert for speed
- Computes name_normalized and is_labor_org flags
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

import requests

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection

IRS_BMF_URL = (
    "https://www.irs.gov/charities-non-profits/"
    "exempt-organizations-business-master-file-extract-eo-bmf"
)
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "data" / "bmf_bulk"
BATCH_SIZE = 50000
REQUEST_TIMEOUT = 120


@dataclass
class LoadStats:
    parsed_total: int = 0
    valid_total: int = 0
    skipped_missing_key: int = 0
    loaded_total: int = 0
    files_processed: int = 0
    subsection_counts: Counter = None
    state_counts: Counter = None
    labor_org_count: int = 0

    def __post_init__(self) -> None:
        if self.subsection_counts is None:
            self.subsection_counts = Counter()
        if self.state_counts is None:
            self.state_counts = Counter()


def load_normalizer():
    """
    Load normalize_employer_aggressive using importlib.

    The task specification points to scripts/import/name_normalizer.py.
    This repo may have moved the normalizer, so we try the task path first,
    then the canonical shared module under src/python/matching.
    """
    candidate_paths = [
        PROJECT_ROOT / "scripts" / "import" / "name_normalizer.py",
        PROJECT_ROOT / "src" / "python" / "matching" / "name_normalization.py",
    ]

    for module_path in candidate_paths:
        if not module_path.exists():
            continue
        spec = importlib.util.spec_from_file_location("name_normalizer", str(module_path))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        # Python 3.14 dataclass import edge case: register before exec_module.
        sys.modules["name_normalizer"] = mod
        spec.loader.exec_module(mod)
        if hasattr(mod, "normalize_employer_aggressive"):
            return mod.normalize_employer_aggressive
        if hasattr(mod, "normalize_name_aggressive"):
            return mod.normalize_name_aggressive

    return lambda x: (x or "").strip().lower()


def discover_bmf_links(session: requests.Session) -> List[str]:
    resp = session.get(IRS_BMF_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    links: List[str] = []
    seen = set()

    for href in hrefs:
        absolute = urljoin(IRS_BMF_URL, href)
        lower = absolute.lower()
        if not (lower.endswith(".zip") or lower.endswith(".csv") or lower.endswith(".txt") or lower.endswith(".dat")):
            continue
        if "irs.gov" not in lower and "amazonaws.com" not in lower:
            continue
        if "bmf" not in lower and "eo" not in lower and "soi" not in lower:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)

    return links


def download_files(session: requests.Session, urls: List[str], download_dir: Path) -> List[Path]:
    download_dir.mkdir(parents=True, exist_ok=True)
    downloaded: List[Path] = []

    for idx, url in enumerate(urls, start=1):
        filename = url.split("/")[-1].split("?")[0].strip()
        if not filename:
            filename = f"bmf_file_{idx}.dat"
        target = download_dir / filename

        if target.exists() and target.stat().st_size > 0:
            print(f"[skip] {target.name} already exists")
            downloaded.append(target)
            continue

        print(f"[download] {idx}/{len(urls)} {url}")
        with session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            with open(target, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        downloaded.append(target)

    return downloaded


def list_input_files(download_dir: Path) -> List[Path]:
    patterns = ("*.zip", "*.csv", "*.txt", "*.dat")
    files: List[Path] = []
    for pattern in patterns:
        files.extend(download_dir.rglob(pattern))
    return sorted({p.resolve() for p in files if p.is_file()})


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def clean_ein(value: Optional[str]) -> Optional[str]:
    v = clean_text(value)
    if not v:
        return None
    digits = re.sub(r"\D", "", v)
    if not digits:
        return None
    if len(digits) <= 9:
        digits = digits.zfill(9)
    return digits[:9]


def clean_zip(value: Optional[str]) -> Optional[str]:
    v = clean_text(value)
    if not v:
        return None
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 5:
        return digits[:5]
    return v[:10]


def clean_state(value: Optional[str]) -> Optional[str]:
    v = clean_text(value)
    if not v:
        return None
    v = v.upper()
    return v[:2]


def clean_code(value: Optional[str], width: int = 2) -> Optional[str]:
    v = clean_text(value)
    if not v:
        return None
    digits = re.sub(r"\D", "", v)
    if digits:
        return digits.zfill(width)[-width:]
    return v[:width]


def parse_numeric(value: Optional[str]) -> Optional[float]:
    v = clean_text(value)
    if not v:
        return None
    v = v.replace("$", "").replace(",", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_ruling_date(value: Optional[str]) -> Optional[date]:
    v = clean_text(value)
    if not v:
        return None
    digits = re.sub(r"\D", "", v)
    if not digits:
        return None

    # Common BMF patterns
    formats = []
    if len(digits) == 8:
        formats = ["%Y%m%d", "%m%d%Y"]
    elif len(digits) == 6:
        formats = ["%Y%m%d", "%m%d%Y", "%Y%m", "%m%Y"]
    elif len(digits) == 4:
        # YYYY
        try:
            year = int(digits)
            if 1800 <= year <= 2100:
                return date(year, 1, 1)
        except ValueError:
            return None

    for fmt in formats:
        try:
            dt = datetime.strptime(digits, fmt)
            # Reject obvious bad dates
            if 1800 <= dt.year <= 2100:
                return dt.date()
        except ValueError:
            continue

    # Fallback: try parsing with separators
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(v, fmt)
            if 1800 <= dt.year <= 2100:
                return dt.date()
        except ValueError:
            continue
    return None


def map_csv_row(row: Dict[str, str]) -> Dict[str, object]:
    aliases = {k.strip().lower(): v for k, v in row.items() if k is not None}

    def first(*keys: str) -> Optional[str]:
        for key in keys:
            v = aliases.get(key)
            if v is not None and str(v).strip() != "":
                return str(v)
        return None

    return {
        "ein": clean_ein(first("ein", "ein1")),
        "org_name": clean_text(first("name", "org_name", "organization_name", "primary_name", "taxpayer_name")),
        "state": clean_state(first("state", "st")),
        "city": clean_text(first("city", "city_name")),
        "zip_code": clean_zip(first("zip", "zipcode", "zip_code", "zip5")),
        "ntee_code": clean_text(first("ntee_code", "ntee", "ntee_cd")),
        "subsection_code": clean_code(first("subsection_code", "subseccd", "subsection")),
        "ruling_date": parse_ruling_date(first("ruling_date", "ruling", "rul_dt", "ruling_yr")),
        "deductibility_code": clean_text(first("deductibility_code", "deductibility", "deduct_cd")),
        "foundation_code": clean_text(first("foundation_code", "foundation", "foundation_cd")),
        "income_amount": parse_numeric(first("income_amount", "income_amt", "income", "totrev", "total_revenue")),
        "asset_amount": parse_numeric(first("asset_amount", "asset_amt", "assets", "totassets", "total_assets")),
        "group_exemption_number": clean_text(first("group_exemption_number", "gen", "group_exemption_num")),
    }


def parse_delimited_text(text: str) -> Iterator[Dict[str, object]]:
    sample = text[:10000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    for row in reader:
        mapped = map_csv_row(row)
        yield mapped


def parse_csv_stream(raw_bytes: bytes) -> Iterator[Dict[str, object]]:
    text = raw_bytes.decode("utf-8", errors="replace")
    yield from parse_delimited_text(text)


def parse_fixed_width_line(line: str) -> Dict[str, object]:
    # IRS EO BMF extract fixed-width layout (common production variant).
    # Slices are resilient fallbacks if CSV is unavailable.
    s = line.rstrip("\r\n")
    if len(s) < 80:
        return {}

    def field(start: int, end: int) -> str:
        if start >= len(s):
            return ""
        return s[start:end]

    ein = clean_ein(field(0, 9))
    org_name = clean_text(field(9, 79))
    city = clean_text(field(154, 184))
    state = clean_state(field(184, 186))
    zip_code = clean_zip(field(186, 195))
    group_exemption_number = clean_text(field(190, 194))
    subsection_code = clean_code(field(194, 196))
    ruling_date = parse_ruling_date(field(199, 207))
    deductibility_code = clean_text(field(206, 207))
    foundation_code = clean_text(field(207, 209))
    asset_amount = parse_numeric(field(232, 245))
    income_amount = parse_numeric(field(245, 258))
    ntee_code = clean_text(field(275, 279))

    return {
        "ein": ein,
        "org_name": org_name,
        "state": state,
        "city": city,
        "zip_code": zip_code,
        "ntee_code": ntee_code,
        "subsection_code": subsection_code,
        "ruling_date": ruling_date,
        "deductibility_code": deductibility_code,
        "foundation_code": foundation_code,
        "income_amount": income_amount,
        "asset_amount": asset_amount,
        "group_exemption_number": group_exemption_number,
    }


def parse_fixed_width_stream(raw_bytes: bytes) -> Iterator[Dict[str, object]]:
    text = raw_bytes.decode("latin-1", errors="replace")
    for line in text.splitlines():
        mapped = parse_fixed_width_line(line)
        if mapped:
            yield mapped


def detect_format(filename: str, raw_bytes: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".txt") or lower.endswith(".dat"):
        head = raw_bytes[:8192].decode("utf-8", errors="replace")
        first_line = head.splitlines()[0].lower() if head.splitlines() else ""
        if "," in first_line and ("ein" in first_line or "name" in first_line):
            return "csv"
        if "\t" in first_line and ("ein" in first_line or "name" in first_line):
            return "csv"
        return "fixed"
    return "fixed"


def iter_records_from_path(path: Path) -> Iterator[Dict[str, object]]:
    lower = path.name.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                mlower = member.filename.lower()
                if not (mlower.endswith(".csv") or mlower.endswith(".txt") or mlower.endswith(".dat")):
                    continue
                with zf.open(member, "r") as fh:
                    raw = fh.read()
                fmt = detect_format(member.filename, raw)
                if fmt == "csv":
                    yield from parse_csv_stream(raw)
                else:
                    yield from parse_fixed_width_stream(raw)
        return

    raw = path.read_bytes()
    fmt = detect_format(path.name, raw)
    if fmt == "csv":
        yield from parse_csv_stream(raw)
    else:
        yield from parse_fixed_width_stream(raw)


def finalize_record(record: Dict[str, object], normalize_name) -> Optional[Tuple]:
    ein = clean_ein(record.get("ein"))
    org_name = clean_text(record.get("org_name"))
    if not ein or not org_name:
        return None

    state = clean_state(record.get("state"))
    city = clean_text(record.get("city"))
    zip_code = clean_zip(record.get("zip_code"))
    ntee_code = clean_text(record.get("ntee_code"))
    subsection_code = clean_code(record.get("subsection_code"))
    ruling_date = record.get("ruling_date")
    if ruling_date and not isinstance(ruling_date, date):
        ruling_date = parse_ruling_date(str(ruling_date))
    deductibility_code = clean_text(record.get("deductibility_code"))
    foundation_code = clean_text(record.get("foundation_code"))
    income_amount = parse_numeric(record.get("income_amount"))
    asset_amount = parse_numeric(record.get("asset_amount"))
    group_exemption_number = clean_text(record.get("group_exemption_number"))

    name_normalized = normalize_name(org_name) if org_name else None
    if name_normalized:
        name_normalized = str(name_normalized).strip().lower()
    is_labor_org = bool((ntee_code or "").upper().startswith("J") or subsection_code == "05")

    return (
        ein,
        org_name,
        state,
        city,
        zip_code,
        ntee_code,
        subsection_code,
        ruling_date.isoformat() if isinstance(ruling_date, date) else None,
        deductibility_code,
        foundation_code,
        income_amount,
        asset_amount,
        name_normalized,
        is_labor_org,
        group_exemption_number,
    )


def ensure_irs_bmf_columns(cur) -> None:
    cur.execute(
        """
        ALTER TABLE irs_bmf
        ADD COLUMN IF NOT EXISTS name_normalized TEXT,
        ADD COLUMN IF NOT EXISTS is_labor_org BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS group_exemption_number TEXT
        """
    )


def create_stage_table(cur) -> None:
    cur.execute("DROP TABLE IF EXISTS _irs_bmf_stage")
    cur.execute(
        """
        CREATE TEMP TABLE _irs_bmf_stage (
            ein TEXT,
            org_name TEXT,
            state TEXT,
            city TEXT,
            zip_code TEXT,
            ntee_code TEXT,
            subsection_code TEXT,
            ruling_date DATE,
            deductibility_code TEXT,
            foundation_code TEXT,
            income_amount NUMERIC,
            asset_amount NUMERIC,
            name_normalized TEXT,
            is_labor_org BOOLEAN,
            group_exemption_number TEXT
        ) ON COMMIT DROP
        """
    )


def copy_batch_to_stage(cur, batch: List[Tuple]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    for row in batch:
        serial_row = []
        for val in row:
            if val is None:
                serial_row.append(r"\N")
            else:
                serial_row.append(val)
        writer.writerow(serial_row)
    buffer.seek(0)

    cur.copy_expert(
        """
        COPY _irs_bmf_stage (
            ein, org_name, state, city, zip_code,
            ntee_code, subsection_code, ruling_date,
            deductibility_code, foundation_code,
            income_amount, asset_amount,
            name_normalized, is_labor_org, group_exemption_number
        )
        FROM STDIN
        WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N')
        """,
        buffer,
    )


def upsert_stage(cur) -> int:
    cur.execute(
        """
        WITH stage_dedup AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY s.ein
                    ORDER BY
                        -- prefer richer records first
                        (CASE WHEN s.org_name IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.state IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.city IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.zip_code IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.ntee_code IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.subsection_code IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.ruling_date IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.deductibility_code IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.foundation_code IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.income_amount IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.asset_amount IS NOT NULL THEN 1 ELSE 0 END +
                         CASE WHEN s.group_exemption_number IS NOT NULL THEN 1 ELSE 0 END) DESC,
                        LENGTH(COALESCE(s.org_name, '')) DESC
                ) AS rn
            FROM _irs_bmf_stage s
            WHERE s.ein IS NOT NULL
        )
        INSERT INTO irs_bmf (
            ein, org_name, state, city, zip_code,
            ntee_code, subsection_code, ruling_date,
            deductibility_code, foundation_code,
            income_amount, asset_amount,
            name_normalized, is_labor_org, group_exemption_number,
            updated_at
        )
        SELECT
            s.ein, s.org_name, s.state, s.city, s.zip_code,
            s.ntee_code, s.subsection_code, s.ruling_date,
            s.deductibility_code, s.foundation_code,
            s.income_amount, s.asset_amount,
            s.name_normalized, COALESCE(s.is_labor_org, FALSE), s.group_exemption_number,
            NOW()
        FROM stage_dedup s
        WHERE s.rn = 1
        ON CONFLICT (ein) DO UPDATE
        SET
            org_name = CASE
                WHEN LENGTH(COALESCE(EXCLUDED.org_name, '')) >= LENGTH(COALESCE(irs_bmf.org_name, ''))
                    THEN EXCLUDED.org_name ELSE irs_bmf.org_name END,
            state = COALESCE(EXCLUDED.state, irs_bmf.state),
            city = COALESCE(EXCLUDED.city, irs_bmf.city),
            zip_code = COALESCE(EXCLUDED.zip_code, irs_bmf.zip_code),
            ntee_code = COALESCE(EXCLUDED.ntee_code, irs_bmf.ntee_code),
            subsection_code = COALESCE(EXCLUDED.subsection_code, irs_bmf.subsection_code),
            ruling_date = COALESCE(EXCLUDED.ruling_date, irs_bmf.ruling_date),
            deductibility_code = COALESCE(EXCLUDED.deductibility_code, irs_bmf.deductibility_code),
            foundation_code = COALESCE(EXCLUDED.foundation_code, irs_bmf.foundation_code),
            income_amount = CASE
                WHEN EXCLUDED.income_amount IS NULL THEN irs_bmf.income_amount
                WHEN irs_bmf.income_amount IS NULL THEN EXCLUDED.income_amount
                WHEN ABS(EXCLUDED.income_amount) > ABS(irs_bmf.income_amount) THEN EXCLUDED.income_amount
                ELSE irs_bmf.income_amount
            END,
            asset_amount = CASE
                WHEN EXCLUDED.asset_amount IS NULL THEN irs_bmf.asset_amount
                WHEN irs_bmf.asset_amount IS NULL THEN EXCLUDED.asset_amount
                WHEN ABS(EXCLUDED.asset_amount) > ABS(irs_bmf.asset_amount) THEN EXCLUDED.asset_amount
                ELSE irs_bmf.asset_amount
            END,
            name_normalized = COALESCE(EXCLUDED.name_normalized, irs_bmf.name_normalized),
            is_labor_org = COALESCE(EXCLUDED.is_labor_org, FALSE) OR COALESCE(irs_bmf.is_labor_org, FALSE),
            group_exemption_number = COALESCE(EXCLUDED.group_exemption_number, irs_bmf.group_exemption_number),
            updated_at = NOW()
        """
    )
    rowcount = cur.rowcount
    cur.execute("TRUNCATE TABLE _irs_bmf_stage")
    return rowcount


def print_top_counter(counter: Counter, label: str, top_n: int = 10) -> None:
    print(label)
    for key, value in counter.most_common(top_n):
        display = key if key is not None and str(key).strip() else "[NULL]"
        print(f"  {display}: {value:,}")


def print_db_summary(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM irs_bmf")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM irs_bmf WHERE is_labor_org = TRUE")
    labor = cur.fetchone()[0]
    print(f"Total records loaded: {total:,}")
    print(f"Labor org count: {labor:,}")

    print("Top 10 subsection_code:")
    cur.execute(
        """
        SELECT COALESCE(subsection_code, '[NULL]') AS subsection_code, COUNT(*)
        FROM irs_bmf
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
        """
    )
    for code, cnt in cur.fetchall():
        print(f"  {code}: {cnt:,}")

    print("Top 10 states:")
    cur.execute(
        """
        SELECT COALESCE(state, '[NULL]') AS state, COUNT(*)
        FROM irs_bmf
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
        """
    )
    for st, cnt in cur.fetchall():
        print(f"  {st}: {cnt:,}")


def process_files(
    files: List[Path],
    normalize_name,
    cur=None,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> LoadStats:
    stats = LoadStats()
    batch: List[Tuple] = []

    for file_path in files:
        print(f"[parse] {file_path.name}")
        stats.files_processed += 1
        for raw_record in iter_records_from_path(file_path):
            stats.parsed_total += 1
            final = finalize_record(raw_record, normalize_name)
            if final is None:
                stats.skipped_missing_key += 1
                continue

            stats.valid_total += 1
            subsection = final[6]
            state = final[2]
            is_labor_org = final[13]
            stats.subsection_counts[subsection or "[NULL]"] += 1
            stats.state_counts[state or "[NULL]"] += 1
            if is_labor_org:
                stats.labor_org_count += 1

            if dry_run:
                if limit and stats.valid_total >= limit:
                    return stats
                continue

            batch.append(final)
            if limit and stats.valid_total >= limit:
                break
            if len(batch) >= BATCH_SIZE:
                copy_batch_to_stage(cur, batch)
                stats.loaded_total += upsert_stage(cur)
                batch = []

        if limit and stats.valid_total >= limit:
            break

    if not dry_run and batch:
        copy_batch_to_stage(cur, batch)
        stats.loaded_total += upsert_stage(cur)

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load IRS EO BMF bulk extracts into irs_bmf")
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="Directory to store downloaded BMF files (default: data/bmf_bulk/)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download and use files already present in --download-dir",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N valid records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and summarize without inserting into DB",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    normalize_name = load_normalizer()

    session = requests.Session()
    session.headers.update({"User-Agent": "labor-data-project-bmf-loader/1.0"})

    try:
        if not args.skip_download:
            print("[step] Discovering EO BMF links from IRS page")
            links = discover_bmf_links(session)
            if not links:
                print("ERROR: No download links found on IRS EO BMF page.")
                return 1
            print(f"[step] Found {len(links)} file links")
            download_files(session, links, args.download_dir)
        else:
            args.download_dir.mkdir(parents=True, exist_ok=True)
            print("[step] Skipping download")

        files = list_input_files(args.download_dir)
        if not files:
            print(f"ERROR: No input files found in {args.download_dir}")
            return 1
        print(f"[step] Processing {len(files)} files from {args.download_dir}")

        if args.dry_run:
            stats = process_files(files, normalize_name, cur=None, dry_run=True, limit=args.limit)
            print("[summary] Dry run complete")
            print(f"Files processed: {stats.files_processed}")
            print(f"Parsed records: {stats.parsed_total:,}")
            print(f"Valid records: {stats.valid_total:,}")
            print(f"Skipped missing EIN/org_name: {stats.skipped_missing_key:,}")
            print(f"Labor org count: {stats.labor_org_count:,}")
            print_top_counter(stats.subsection_counts, "Top 10 subsection_code:")
            print_top_counter(stats.state_counts, "Top 10 states:")
            return 0

        conn = get_connection()
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                ensure_irs_bmf_columns(cur)
                create_stage_table(cur)
                stats = process_files(files, normalize_name, cur=cur, dry_run=False, limit=args.limit)
                conn.commit()
                print("[summary] Load complete")
                print(f"Files processed: {stats.files_processed}")
                print(f"Parsed records: {stats.parsed_total:,}")
                print(f"Valid records: {stats.valid_total:,}")
                print(f"Skipped missing EIN/org_name: {stats.skipped_missing_key:,}")
                print(f"Upsert row operations: {stats.loaded_total:,}")
                print_db_summary(cur)
            return 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
