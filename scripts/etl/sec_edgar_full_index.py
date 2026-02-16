#!/usr/bin/env python3
"""
SEC EDGAR Full Index ETL

Loads SEC company metadata into sec_companies from SEC bulk submissions data.

Primary source:
    https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip

Usage:
    py scripts/etl/sec_edgar_full_index.py --limit 100
    py scripts/etl/sec_edgar_full_index.py
    py scripts/etl/sec_edgar_full_index.py --zip-path C:\\path\\to\\submissions.zip --limit 1000
"""
import argparse
import json
import os
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.request import Request, urlopen

from psycopg2.extras import RealDictCursor, execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection

SEC_SUBMISSIONS_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
DEFAULT_LOCAL_ZIP = Path.home() / "Downloads" / "submissions.zip"
DEFAULT_USER_AGENT = "labor-data-project/1.0 (research@local)"

US_STATES_AND_TERRITORIES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_ein(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    ein = "".join(ch for ch in str(value) if ch.isdigit())
    if len(ein) != 9 or ein == "000000000":
        return None
    return ein


def _clean_state(value: Optional[str]) -> Optional[str]:
    state = _clean_text(value)
    if not state:
        return None
    state = state.upper()
    if state in US_STATES_AND_TERRITORIES:
        return state
    return None


def _compact_address(address_obj: Optional[Dict]) -> Optional[str]:
    if not address_obj:
        return None
    parts = [
        _clean_text(address_obj.get("street1")),
        _clean_text(address_obj.get("street2")),
        _clean_text(address_obj.get("city")),
        _clean_text(address_obj.get("stateOrCountry")),
        _clean_text(address_obj.get("zipCode")),
    ]
    cleaned = [part for part in parts if part]
    return ", ".join(cleaned) if cleaned else None


def _get_last_filing_date(recent: Optional[Dict]) -> Optional[str]:
    if not recent:
        return None
    filing_dates = recent.get("filingDate")
    if not filing_dates or not isinstance(filing_dates, list):
        return None
    for date_str in filing_dates:
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                return dt.isoformat()
            except ValueError:
                continue
    return None


def _iter_company_json_filenames(zf: zipfile.ZipFile) -> Iterable[str]:
    # Keep only company-level submissions files (exclude paginated "-submissions-###.json" entries)
    for name in zf.namelist():
        if not name.endswith(".json"):
            continue
        if "-submissions-" in name:
            continue
        yield name


def _parse_company_json(raw: Dict, source_file: str) -> Optional[Dict]:
    cik_raw = _clean_text(raw.get("cik"))
    if not cik_raw:
        return None
    cik_digits = "".join(ch for ch in cik_raw if ch.isdigit())
    if not cik_digits:
        return None

    company_name = _clean_text(raw.get("name"))
    if not company_name:
        return None

    addresses = raw.get("addresses") or {}
    business = addresses.get("business") or {}
    mailing = addresses.get("mailing") or {}
    state = _clean_state(business.get("stateOrCountry")) or _clean_state(mailing.get("stateOrCountry"))

    filings = raw.get("filings") or {}
    recent = filings.get("recent") or {}

    return {
        "cik": cik_digits.lstrip("0") or "0",
        "company_name": company_name,
        "ein": _clean_ein(raw.get("ein")),
        "state": state,
        "sic_code": _clean_text(raw.get("sic")),
        "naics_code": None,
        "business_address": _compact_address(business),
        "mailing_address": _compact_address(mailing),
        "source_file": source_file,
        "last_filing_date": _get_last_filing_date(recent),
    }


def _download_submissions_zip(destination: Path, user_agent: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(SEC_SUBMISSIONS_URL, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=120) as response:
        data = response.read()
    destination.write_bytes(data)
    return destination


def extract_companies(zip_path: Optional[str], limit: Optional[int], download_if_missing: bool) -> List[Dict]:
    local_zip = Path(zip_path) if zip_path else DEFAULT_LOCAL_ZIP
    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)

    if not local_zip.exists():
        if not download_if_missing:
            raise FileNotFoundError(
                f"SEC submissions zip not found at {local_zip}. "
                "Use --download-if-missing or provide --zip-path."
            )
        print(f"Local submissions zip missing. Downloading from SEC to: {local_zip}")
        _download_submissions_zip(local_zip, user_agent=user_agent)

    print(f"Reading SEC submissions from: {local_zip}")
    start = time.time()
    companies: List[Dict] = []
    errors = 0

    with zipfile.ZipFile(local_zip) as zf:
        file_names = list(_iter_company_json_filenames(zf))
        total_files = len(file_names)
        print(f"Company JSON files detected: {total_files:,}")

        for idx, filename in enumerate(file_names, start=1):
            try:
                raw = json.loads(zf.read(filename))
                parsed = _parse_company_json(raw, source_file=filename)
                if parsed:
                    companies.append(parsed)
            except Exception:
                errors += 1

            if limit and len(companies) >= limit:
                break

            if idx % 50000 == 0:
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed else 0.0
                print(f"Processed {idx:,}/{total_files:,} files ({rate:.0f} files/sec)")

    elapsed = time.time() - start
    print(f"Extracted {len(companies):,} companies in {elapsed:.1f}s (errors: {errors:,})")
    return companies


def load_to_db(companies: List[Dict]) -> int:
    if not companies:
        print("No companies extracted. Nothing to load.")
        return 0

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = 0")
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'sec_companies'
                """
            )
            available_cols = {row["column_name"] for row in cur.fetchall()}

            candidate_cols = [
                "cik",
                "company_name",
                "ein",
                "state",
                "sic_code",
                "naics_code",
                "business_address",
                "mailing_address",
                "source_file",
                "last_filing_date",
            ]
            insert_cols = [col for col in candidate_cols if col in available_cols]
            if "cik" not in insert_cols or "company_name" not in insert_cols:
                raise RuntimeError(
                    "sec_companies is missing required columns 'cik' and/or 'company_name'. "
                    "Run scripts/etl/create_sec_companies_table.sql first."
                )

            values_sql = ", ".join([f"%({col})s" for col in insert_cols])
            insert_cols_sql = ", ".join(insert_cols)

            update_cols = [col for col in insert_cols if col != "cik"]
            update_assignments = [f"{col} = EXCLUDED.{col}" for col in update_cols]
            if "updated_at" in available_cols:
                update_assignments.append("updated_at = NOW()")
            update_sql = ",\n                    ".join(update_assignments) if update_assignments else "cik = EXCLUDED.cik"

            insert_sql = f"""
                INSERT INTO sec_companies ({insert_cols_sql})
                VALUES ({values_sql})
                ON CONFLICT (cik) DO UPDATE SET
                    {update_sql}
            """
            execute_batch(cur, insert_sql, companies, page_size=5000)
        conn.commit()
    finally:
        conn.close()

    print(f"Loaded/updated {len(companies):,} rows into sec_companies")
    return len(companies)


def print_stats() -> None:
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'sec_companies'
                """
            )
            columns = {row["column_name"] for row in cur.fetchall()}
            with_naics_expr = "COUNT(naics_code) AS with_naics" if "naics_code" in columns else "0::bigint AS with_naics"

            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(ein) AS with_ein,
                    COUNT(DISTINCT state) AS states_covered,
                    COUNT(sic_code) AS with_sic,
                    {with_naics_expr}
                FROM sec_companies
                """
            )
            stats = cur.fetchone()
    finally:
        conn.close()

    total = stats["total"] or 0
    with_ein = stats["with_ein"] or 0
    with_sic = stats["with_sic"] or 0
    with_naics = stats["with_naics"] or 0
    states_covered = stats["states_covered"] or 0

    print("\nsec_companies stats:")
    print(f"  Total companies: {total:,}")
    print(f"  With EIN: {with_ein:,} ({(with_ein / total * 100) if total else 0:.1f}%)")
    print(f"  States covered: {states_covered:,}")
    print(f"  With SIC code: {with_sic:,} ({(with_sic / total * 100) if total else 0:.1f}%)")
    print(f"  With NAICS code: {with_naics:,} ({(with_naics / total * 100) if total else 0:.1f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load SEC EDGAR company index into sec_companies")
    parser.add_argument("--limit", type=int, help="Limit number of companies (for testing)")
    parser.add_argument("--zip-path", help="Path to local submissions.zip")
    parser.add_argument(
        "--download-if-missing",
        action="store_true",
        help="Download submissions.zip from SEC if missing at --zip-path/default location",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SEC EDGAR Full Index ETL")
    print("=" * 60)
    print("Tip: run SQL first -> scripts/etl/create_sec_companies_table.sql")

    try:
        companies = extract_companies(
            zip_path=args.zip_path,
            limit=args.limit,
            download_if_missing=args.download_if_missing,
        )
    except Exception as exc:
        print(f"Extraction failed: {exc}")
        return 1

    if not companies:
        print("No companies extracted.")
        return 1

    load_to_db(companies)
    print_stats()
    print("\nETL complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
