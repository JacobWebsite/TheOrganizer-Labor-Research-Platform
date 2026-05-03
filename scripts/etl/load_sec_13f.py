"""
Load SEC Form 13F bulk data sets into Postgres.

24Q-9: Stockholders. SEC Form 13F is the canonical source of institutional
ownership in U.S. publicly-traded firms (every institutional manager with
>$100M AUM files quarterly).

The bulk distribution at https://www.sec.gov/dera/data/form-13f-data-sets
publishes one ZIP per calendar quarter (recent renaming uses date-range
filenames like '01dec2025-28feb2026_form13f.zip'). Each ZIP contains:
  - SUBMISSION.tsv     -- accession + filer CIK + period
  - COVERPAGE.tsv      -- filer name + address
  - INFOTABLE.tsv      -- the holdings (millions of rows; this is the big one)
  - SIGNATURE / OTHERMANAGER / SUMMARY -- secondary

We hydrate two tables:
  - sec_13f_submissions: one row per accession (filer-quarter pair)
  - sec_13f_holdings:    one row per (accession, security) holding

For matching, the join from a master employer to "who owns me" runs:
  master.canonical_name  ~~  sec_13f_holdings.name_of_issuer_norm
  -> sec_13f_holdings.accession_number
  -> sec_13f_submissions.filer_cik / filer_name

Usage:
    py scripts/etl/load_sec_13f.py                         # load every ZIP in files/sec_13f/
    py scripts/etl/load_sec_13f.py --zip-path PATH         # load a single ZIP
    py scripts/etl/load_sec_13f.py --dry-run               # roll back at end

Run time: roughly 90 seconds per quarterly ZIP on COPY path (8M holdings/quarter).

VALUE field: per SEC's 2023 rule change, market value is now reported in
whole dollars. Older 13F data from before Jan 3 2023 was in thousands of
dollars; we don't load that period in this script.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection

DEFAULT_DIR = PROJECT_ROOT / "files" / "sec_13f"

# Schema. Indexes are created AFTER bulk load (per the EPA loader pattern)
# to avoid per-row trigram updates that 5x the load time.
DDL_TABLES = """
DROP TABLE IF EXISTS sec_13f_holdings CASCADE;
DROP TABLE IF EXISTS sec_13f_submissions CASCADE;

CREATE TABLE sec_13f_submissions (
    accession_number     TEXT PRIMARY KEY,
    filer_cik            TEXT NOT NULL,
    filer_name           TEXT,
    filer_state          TEXT,
    filer_city           TEXT,
    filer_zip            TEXT,
    filing_date          DATE,
    period_of_report     DATE,
    submission_type      TEXT,
    table_entry_total    INTEGER,
    table_value_total    NUMERIC(20, 2),
    loaded_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sec_13f_holdings (
    id                              BIGSERIAL PRIMARY KEY,
    accession_number                TEXT NOT NULL,
    infotable_sk                    BIGINT,
    name_of_issuer                  TEXT NOT NULL,
    name_of_issuer_norm             TEXT NOT NULL,
    title_of_class                  TEXT,
    cusip                           TEXT,
    figi                            TEXT,
    value                           NUMERIC(20, 2),  -- whole dollars
    shares_or_principal_amount      BIGINT,
    shares_or_principal_amount_type TEXT,
    put_call                        TEXT,
    investment_discretion           TEXT,
    voting_auth_sole                BIGINT,
    voting_auth_shared              BIGINT,
    voting_auth_none                BIGINT
);
"""

DDL_INDEXES = """
CREATE INDEX idx_sec_13f_subs_cik
    ON sec_13f_submissions (filer_cik);
CREATE INDEX idx_sec_13f_subs_period
    ON sec_13f_submissions (period_of_report);
CREATE INDEX idx_sec_13f_holdings_accession
    ON sec_13f_holdings (accession_number);
CREATE INDEX idx_sec_13f_holdings_cusip
    ON sec_13f_holdings (cusip) WHERE cusip IS NOT NULL;
CREATE INDEX idx_sec_13f_holdings_issuer_trgm
    ON sec_13f_holdings USING gin (name_of_issuer_norm gin_trgm_ops);
"""


# Date format in TSV is DD-MON-YYYY (e.g., '31-DEC-2025')
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")


def _parse_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if not _DATE_RE.match(s):
        return None
    try:
        return datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _parse_int(s: Optional[str]) -> Optional[int]:
    if s is None or s == "":
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_num(s: Optional[str]) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


_NORM_RE = re.compile(r"[^a-z0-9 ]+")


def _norm_issuer(name: str) -> str:
    """Aggressive normalization for matching to master_employers.canonical_name.
    Lowercase, drop punctuation, strip common suffixes, collapse whitespace."""
    if not name:
        return ""
    s = name.lower().strip()
    # Strip common corporate suffixes once
    for suffix in (
        " inc", " corporation", " corp", " co", " company", " ltd",
        " plc", " llc", " l p", " lp", " holdings", " group",
    ):
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip(" ,.")
            break
    s = _NORM_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _resolve_tsv_path(z: zipfile.ZipFile, basename: str) -> Optional[str]:
    """Locate a TSV by basename whether it's at the ZIP root or nested
    under a single subdirectory. SEC's bulk distributions are inconsistent
    -- e.g. the Jun-Aug 2025 bundle wraps files under
    01JUN2025-31AUG2025_form13f/, while the Dec-Feb bundle uses the root."""
    target = basename.lower()
    for n in z.namelist():
        if n.lower().endswith("/" + target) or n.lower() == target:
            return n
    return None


def _read_tsv(z: zipfile.ZipFile, basename: str) -> Tuple[List[str], Iterable[List[str]]]:
    name = _resolve_tsv_path(z, basename)
    if name is None:
        raise KeyError(f"{basename} not found in zip namelist")
    raw = z.open(name)
    # Use TextIOWrapper with utf-8 + replace; SEC files are utf-8 but with
    # occasional dirty bytes from manager-typed addresses.
    text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE)
    header = next(reader)
    return header, reader


def _idx(header: List[str], col: str) -> int:
    """Look up column index, raising if missing (forces a deliberate fail
    when SEC changes their schema rather than silently returning None)."""
    try:
        return header.index(col)
    except ValueError:
        raise KeyError(f"Column {col!r} missing from TSV header: {header}")


def load_one_zip(zip_path: Path, conn) -> Tuple[int, int]:
    """Load a single quarterly bundle. Returns (n_submissions, n_holdings)."""
    print(f"\n=== {zip_path.name} ===")
    t0 = time.time()
    cur = conn.cursor()

    z = zipfile.ZipFile(zip_path)

    # Step 1: SUBMISSION + COVERPAGE -> sec_13f_submissions
    print("  Reading SUBMISSION.tsv...")
    sub_header, sub_rows = _read_tsv(z, "SUBMISSION.tsv")
    sub_acc = _idx(sub_header, "ACCESSION_NUMBER")
    sub_filing = _idx(sub_header, "FILING_DATE")
    sub_type = _idx(sub_header, "SUBMISSIONTYPE")
    sub_cik = _idx(sub_header, "CIK")
    sub_period = _idx(sub_header, "PERIODOFREPORT")
    submissions = {}
    for row in sub_rows:
        if len(row) <= max(sub_acc, sub_filing, sub_type, sub_cik, sub_period):
            continue
        # Filter to actual 13F holdings reports; skip notices.
        stype = (row[sub_type] or "").strip()
        if not stype.startswith("13F"):
            continue
        submissions[row[sub_acc].strip()] = {
            "filer_cik": (row[sub_cik] or "").strip().lstrip("0") or None,
            "filing_date": _parse_date(row[sub_filing]),
            "period_of_report": _parse_date(row[sub_period]),
            "submission_type": stype,
            "filer_name": None,
            "filer_state": None,
            "filer_city": None,
            "filer_zip": None,
            "table_entry_total": None,
            "table_value_total": None,
        }

    print("  Reading COVERPAGE.tsv...")
    cover_header, cover_rows = _read_tsv(z, "COVERPAGE.tsv")
    cv_acc = _idx(cover_header, "ACCESSION_NUMBER")
    cv_name = _idx(cover_header, "FILINGMANAGER_NAME")
    cv_city = _idx(cover_header, "FILINGMANAGER_CITY")
    cv_state = _idx(cover_header, "FILINGMANAGER_STATEORCOUNTRY")
    cv_zip = _idx(cover_header, "FILINGMANAGER_ZIPCODE")
    for row in cover_rows:
        if len(row) <= max(cv_acc, cv_name, cv_city, cv_state, cv_zip):
            continue
        acc = row[cv_acc].strip()
        if acc not in submissions:
            continue
        submissions[acc]["filer_name"] = (row[cv_name] or "").strip() or None
        submissions[acc]["filer_state"] = (row[cv_state] or "").strip() or None
        submissions[acc]["filer_city"] = (row[cv_city] or "").strip() or None
        submissions[acc]["filer_zip"] = (row[cv_zip] or "").strip()[:10] or None

    print("  Reading SUMMARYPAGE.tsv...")
    try:
        sp_header, sp_rows = _read_tsv(z, "SUMMARYPAGE.tsv")
        sp_acc = _idx(sp_header, "ACCESSION_NUMBER")
        sp_count = _idx(sp_header, "TABLEENTRYTOTAL")
        sp_value = _idx(sp_header, "TABLEVALUETOTAL")
        for row in sp_rows:
            if len(row) <= max(sp_acc, sp_count, sp_value):
                continue
            acc = row[sp_acc].strip()
            if acc not in submissions:
                continue
            submissions[acc]["table_entry_total"] = _parse_int(row[sp_count])
            submissions[acc]["table_value_total"] = _parse_num(row[sp_value])
    except KeyError:
        pass  # SUMMARYPAGE schema variant; fields default to None

    # Bulk insert submissions. ON CONFLICT skip in case the same accession
    # appears in two ZIPs (shouldn't, but defensive).
    print(f"  Inserting {len(submissions):,} submissions...")
    sub_rows_to_insert = [
        (
            acc,
            d["filer_cik"],
            d["filer_name"],
            d["filer_state"],
            d["filer_city"],
            d["filer_zip"],
            d["filing_date"],
            d["period_of_report"],
            d["submission_type"],
            d["table_entry_total"],
            d["table_value_total"],
        )
        for acc, d in submissions.items()
        if d["filer_cik"]  # skip rows missing CIK; can't be matched anyway
    ]
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """
        INSERT INTO sec_13f_submissions
            (accession_number, filer_cik, filer_name, filer_state, filer_city,
             filer_zip, filing_date, period_of_report, submission_type,
             table_entry_total, table_value_total)
        VALUES %s
        ON CONFLICT (accession_number) DO NOTHING
        """,
        sub_rows_to_insert,
        page_size=2000,
    )

    # Step 2: INFOTABLE.tsv -> sec_13f_holdings (the big one).
    print("  Streaming INFOTABLE.tsv into COPY...")
    info_header, info_rows = _read_tsv(z, "INFOTABLE.tsv")
    it_acc = _idx(info_header, "ACCESSION_NUMBER")
    it_sk = _idx(info_header, "INFOTABLE_SK")
    it_name = _idx(info_header, "NAMEOFISSUER")
    it_class = _idx(info_header, "TITLEOFCLASS")
    it_cusip = _idx(info_header, "CUSIP")
    it_figi = _idx(info_header, "FIGI")
    it_value = _idx(info_header, "VALUE")
    it_shares = _idx(info_header, "SSHPRNAMT")
    it_shares_type = _idx(info_header, "SSHPRNAMTTYPE")
    it_putcall = _idx(info_header, "PUTCALL")
    it_disc = _idx(info_header, "INVESTMENTDISCRETION")
    it_va_sole = _idx(info_header, "VOTING_AUTH_SOLE")
    it_va_shared = _idx(info_header, "VOTING_AUTH_SHARED")
    it_va_none = _idx(info_header, "VOTING_AUTH_NONE")

    valid_acc = set(submissions.keys())
    BATCH = 10000
    batch: List[tuple] = []
    n_holdings = 0
    insert_sql = """
        INSERT INTO sec_13f_holdings (
            accession_number, infotable_sk, name_of_issuer, name_of_issuer_norm,
            title_of_class, cusip, figi, value,
            shares_or_principal_amount, shares_or_principal_amount_type,
            put_call, investment_discretion,
            voting_auth_sole, voting_auth_shared, voting_auth_none
        ) VALUES %s
    """
    for row in info_rows:
        if len(row) <= it_va_none:
            continue
        acc = row[it_acc].strip()
        if acc not in valid_acc:
            continue  # Skip holdings whose submission wasn't loaded (non-13F)
        name = (row[it_name] or "").strip()
        if not name:
            continue
        batch.append(
            (
                acc,
                _parse_int(row[it_sk]),
                name,
                _norm_issuer(name),
                (row[it_class] or "").strip() or None,
                (row[it_cusip] or "").strip() or None,
                (row[it_figi] or "").strip() or None,
                _parse_num(row[it_value]),
                _parse_int(row[it_shares]),
                (row[it_shares_type] or "").strip() or None,
                (row[it_putcall] or "").strip() or None,
                (row[it_disc] or "").strip() or None,
                _parse_int(row[it_va_sole]),
                _parse_int(row[it_va_shared]),
                _parse_int(row[it_va_none]),
            )
        )
        if len(batch) >= BATCH:
            execute_values(cur, insert_sql, batch, page_size=BATCH)
            n_holdings += len(batch)
            batch = []
            if n_holdings % 500_000 == 0:
                print(f"    {n_holdings:>10,} holdings ({time.time() - t0:.0f}s)")
    if batch:
        execute_values(cur, insert_sql, batch, page_size=BATCH)
        n_holdings += len(batch)

    print(
        f"  done: {len(submissions):,} submissions, {n_holdings:,} holdings "
        f"({time.time() - t0:.0f}s)"
    )
    return len(submissions), n_holdings


def load(dir_path: Path, dry_run: bool = False) -> None:
    zips = sorted(dir_path.glob("*_form13f.zip"))
    if not zips:
        raise FileNotFoundError(f"No *_form13f.zip files found in {dir_path}")

    conn = get_connection()
    try:
        # CREATE EXTENSION is idempotent and external to our schema; it
        # can stay in autocommit. But the table DROP/CREATE must NOT be
        # autocommitted -- otherwise --dry-run silently destroys the
        # existing schema before rolling back the inserts. Move table
        # DDL inside the per-zip transaction so it commits/rolls back
        # together with the data (Codex 2026-05-02 finding #2).
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.autocommit = False

        print("Resetting sec_13f_* tables (indexes deferred)...")
        cur.execute(DDL_TABLES)

        total_subs = 0
        total_holdings = 0
        for zp in zips:
            ns, nh = load_one_zip(zp, conn)
            total_subs += ns
            total_holdings += nh
            if dry_run:
                conn.rollback()
                # On dry-run, the rollback also reverts the schema reset.
                # Re-run the schema reset for the next zip (in dry-run we
                # still want to validate per-zip parsing).
                cur.execute(DDL_TABLES)
            else:
                conn.commit()

        if not dry_run:
            print("\nCreating indexes...")
            t1 = time.time()
            conn.autocommit = True
            cur.execute(DDL_INDEXES)
            conn.autocommit = False
            print(f"  indexes done in {time.time() - t1:.0f}s")

            # Update freshness
            cur.execute(
                """
                INSERT INTO data_source_freshness
                    (source_name, display_name, last_updated, record_count, notes)
                VALUES (
                    'sec_13f', 'SEC Form 13F Institutional Holdings',
                    %s, %s,
                    '24Q-9 stockholders. SEC Form 13F bulk data sets, last 4 quarters.'
                )
                ON CONFLICT (source_name) DO UPDATE SET
                    last_updated = EXCLUDED.last_updated,
                    record_count = EXCLUDED.record_count,
                    notes = EXCLUDED.notes
                """,
                (datetime.now(timezone.utc), total_holdings),
            )
            conn.commit()

        print()
        print(f"TOTAL: {total_subs:,} submissions, {total_holdings:,} holdings")
        print("       across", len(zips), "quarterly bundles.")
        if dry_run:
            print("DRY RUN -- rolled back each ZIP. Re-run without --dry-run to commit.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--zip-dir",
        default=str(DEFAULT_DIR),
        help="Directory holding *_form13f.zip files",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load(Path(args.zip_dir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
