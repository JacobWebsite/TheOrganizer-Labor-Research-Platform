"""
Loader: NY Authorities Budget Office Procurement Reports (4 datasets unified).

Loads four nearly-identical schemas into one unified staging table:
  - State Authorities          (33-col superset, dataset_id 'ehig-g5x3')
  - Local Authorities          (20-col subset,   dataset_id '8w5p-k45m')
  - Local Development Corps    (20-col subset,   dataset_id 'd84c-dk28')
  - Industrial Dev Agencies    (20-col subset,   dataset_id 'p3p6-xqr5'  -- snake_case headers)

Total expected rows: ~372,010

Per the shared spec at C:/Users/jakew/AppData/Local/Temp/contracts_loader_shared_spec.md.

Idempotent: DROP TABLE + CREATE TABLE on every run.

Usage:
    py scripts/etl/contracts/load_ny_abo.py
    py scripts/etl/contracts/load_ny_abo.py --limit 1000
    py scripts/etl/contracts/load_ny_abo.py --csv-dir D:/some/dir
    py scripts/etl/contracts/load_ny_abo.py --no-freshness-update
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# Add project root to path so we can import db_config
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from db_config import get_connection  # noqa: E402

# Allow Python's csv module to handle very wide / unusual rows
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TABLE_NAME = "state_contracts_ny_abo"
SOURCE_NAME = "state_contracts_ny_abo"
DISPLAY_NAME = "NY ABO Procurement Reports (4 datasets)"

# (dataset_source, source_dataset_id, default_filename)
DATASETS = [
    (
        "state_authorities",
        "ehig-g5x3",
        "Procurement_Report_for_State_Authorities_20260422.csv",
    ),
    (
        "local_authorities",
        "8w5p-k45m",
        "Procurement_Report_for_Local_Authorities_20260422.csv",
    ),
    (
        "local_dev_corps",
        "d84c-dk28",
        "Procurement_Report_for_Local_Development_Corporations_20260422.csv",
    ),
    (
        "industrial_dev_agencies",
        "p3p6-xqr5",
        "Procurement_Report_for_Industrial_Development_Agencies_20260422.csv",
    ),
]

# Native columns from the State Authorities CSV (33-col superset).
# Order matches CSV header order. We map every column from every file
# into this unified column set. Columns absent from the 20-col files
# are stored as NULL.
NATIVE_COLUMNS = [
    "authority_name",
    "fiscal_year_end_date",
    "procurements",
    "vendor_name_raw",
    "vendor_address_1_raw",
    "vendor_address_2",
    "vendor_city_raw",
    "vendor_state_raw",
    "vendor_postal_code_raw",
    "vendor_province_region",
    "vendor_country",
    "procurement_description",
    "type_of_procurement",
    "award_process",
    "award_date_raw",
    "begin_date",          # state-only
    "renewal_date",        # state-only
    "end_date",
    "contract_amount_raw",
    "fair_market_value",
    "fmv_explanation",
    "amount_expended_for_fiscal_year",
    "amount_expended_to_date",            # state-only
    "current_or_outstanding_balance",     # state-only
    "number_of_bids_or_proposals_received",  # state-only
    "nys_or_foreign_business_enterprise",    # state-only
    "vendor_is_a_mwbe",                      # state-only
    "solicited_mwbe",                        # state-only
    "number_of_mwbe_proposals",              # state-only
    "exempt_from_publishing",                # state-only
    "reason_for_publishing_exemption",       # state-only
    "status",                                # state-only
    "transaction_number",                    # state-only
]

# CSV header label -> our native column name. Handles both Title Case
# (state/local/LDC files) and snake_case (IDA file).
HEADER_MAP = {
    # Title Case (3 of 4 files)
    "Authority Name": "authority_name",
    "Fiscal Year End Date": "fiscal_year_end_date",
    "Procurements": "procurements",
    "Vendor Name": "vendor_name_raw",
    "Vendor Address 1": "vendor_address_1_raw",
    "Vendor Address 2": "vendor_address_2",
    "Vendor City": "vendor_city_raw",
    "Vendor State": "vendor_state_raw",
    "Vendor Postal Code": "vendor_postal_code_raw",
    "Vendor Province/Region": "vendor_province_region",
    "Vendor Country": "vendor_country",
    "Procurement Description": "procurement_description",
    "Type of Procurement": "type_of_procurement",
    "Award Process": "award_process",
    "Award Date": "award_date_raw",
    "Begin Date": "begin_date",
    "Renewal Date": "renewal_date",
    "End Date": "end_date",
    "Contract Amount": "contract_amount_raw",
    "Fair Market Value": "fair_market_value",
    "FMV Explanation": "fmv_explanation",
    "Amount Expended for Fiscal Year": "amount_expended_for_fiscal_year",
    "Amount Expended to Date": "amount_expended_to_date",
    "Current or Outstanding Balance": "current_or_outstanding_balance",
    "Number of Bids or Proposals Received": "number_of_bids_or_proposals_received",
    "NYS or Foreign Business Enterprise": "nys_or_foreign_business_enterprise",
    "Vendor is a MWBE": "vendor_is_a_mwbe",
    "Solicited MWBE": "solicited_mwbe",
    "Number of MWBE Proposals": "number_of_mwbe_proposals",
    "Exempt From Publishing": "exempt_from_publishing",
    "Reason for Publishing Exemption": "reason_for_publishing_exemption",
    "Status": "status",
    "Transaction Number": "transaction_number",
    # snake_case (IDA file)
    "authority_name": "authority_name",
    "fiscal_year_end_date": "fiscal_year_end_date",
    "procurements": "procurements",
    "vendor_name": "vendor_name_raw",
    "vendor_address_1": "vendor_address_1_raw",
    "vendor_address_2": "vendor_address_2",
    "vendor_city": "vendor_city_raw",
    "vendor_state": "vendor_state_raw",
    "vendor_postal_code": "vendor_postal_code_raw",
    "vendor_province_region": "vendor_province_region",
    "vendor_country": "vendor_country",
    "procurement_description": "procurement_description",
    "type_of_procurement": "type_of_procurement",
    "award_process": "award_process",
    "award_date": "award_date_raw",
    "begin_date": "begin_date",
    "renewal_date": "renewal_date",
    "end_date": "end_date",
    "contract_amount": "contract_amount_raw",
    "fair_market_value": "fair_market_value",
    "fmv_explanation": "fmv_explanation",
    "amount_expended_for_fiscal_year": "amount_expended_for_fiscal_year",
    "amount_expended_to_date": "amount_expended_to_date",
    "current_or_outstanding_balance": "current_or_outstanding_balance",
    "number_of_bids_or_proposals_received": "number_of_bids_or_proposals_received",
    "nys_or_foreign_business_enterprise": "nys_or_foreign_business_enterprise",
    "vendor_is_a_mwbe": "vendor_is_a_mwbe",
    "solicited_mwbe": "solicited_mwbe",
    "number_of_mwbe_proposals": "number_of_mwbe_proposals",
    "exempt_from_publishing": "exempt_from_publishing",
    "reason_for_publishing_exemption": "reason_for_publishing_exemption",
    "status": "status",
    "transaction_number": "transaction_number",
}


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------


def normalize_vendor_name(name: str) -> str:
    """Match scripts/etl/_match_usaspending.py exactly. See shared spec."""
    if not name:
        return ""
    result = name.lower().strip()
    result = re.sub(
        r"\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\b\.?",
        "",
        result,
    )
    result = re.sub(r"\bd/?b/?a\b\.?", "", result)
    result = re.sub(r"[^\w\s]", " ", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


_AMOUNT_STRIP_RE = re.compile(r"[\$,\s]")


def parse_amount(raw: Optional[str]) -> Optional[float]:
    """Parse '$13,650.00' -> 13650.00. Empty/garbage -> None."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    # Strip $, commas, whitespace
    cleaned = _AMOUNT_STRIP_RE.sub("", s)
    if not cleaned or cleaned in {"-", "."}:
        return None
    # Parens style negatives, just in case
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(raw: Optional[str]) -> Optional[date]:
    """Parse known date formats appearing across the 4 ABO files.

    Recognized formats:
      - MM/DD/YYYY              (state/local/LDC)
      - YYYY-MM-DDTHH:MM:SS.sss (IDA)
      - YYYY Mon DD HH:MM:SS AM (Renewal Date in state authorities, ignored if not parseable)
    Returns None on anything we don't recognize.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    # MM/DD/YYYY or M/D/YYYY
    if "/" in s:
        try:
            return datetime.strptime(s, "%m/%d/%Y").date()
        except ValueError:
            pass
    # ISO-ish with T separator (IDA)
    if "T" in s:
        try:
            return datetime.fromisoformat(s.replace("Z", "")).date()
        except ValueError:
            pass
        try:
            # Strip the .000 or similar fractional seconds tail safely
            head = s.split(".")[0]
            return datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            pass
    # Plain YYYY-MM-DD
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        pass
    # Don't try to parse the weird "2017 Aug 16 12:00:00 AM" Renewal Date
    return None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def build_create_sql() -> str:
    native_cols_sql = ",\n        ".join(f"{c} TEXT" for c in NATIVE_COLUMNS)
    return f"""
    DROP TABLE IF EXISTS {TABLE_NAME} CASCADE;
    CREATE TABLE {TABLE_NAME} (
        id                       BIGSERIAL PRIMARY KEY,
        dataset_source           TEXT NOT NULL,
        source_dataset_id        TEXT NOT NULL,
        -- Canonical fields (per shared spec)
        vendor_name              TEXT NOT NULL,
        vendor_name_norm         TEXT NOT NULL,
        vendor_state             TEXT,
        vendor_city              TEXT,
        vendor_address_1         TEXT,
        vendor_postal_code       TEXT,
        contract_amount          NUMERIC,
        award_date               DATE,
        agency_name              TEXT,
        loaded_at                TIMESTAMP DEFAULT NOW(),
        -- Native source columns (raw, preserved for traceability)
        {native_cols_sql}
    );
    """


def build_indexes_sql() -> list[str]:
    return [
        f"CREATE INDEX idx_{TABLE_NAME}_vendor_norm_state ON {TABLE_NAME} (vendor_name_norm, vendor_state);",
        f"CREATE INDEX idx_{TABLE_NAME}_dataset ON {TABLE_NAME} (dataset_source);",
        f"CREATE INDEX idx_{TABLE_NAME}_award_date ON {TABLE_NAME} (award_date);",
    ]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


# Columns we COPY into (in order). We let id default and loaded_at default.
COPY_COLUMNS = (
    [
        "dataset_source",
        "source_dataset_id",
        "vendor_name",
        "vendor_name_norm",
        "vendor_state",
        "vendor_city",
        "vendor_address_1",
        "vendor_postal_code",
        "contract_amount",
        "award_date",
        "agency_name",
    ]
    + NATIVE_COLUMNS
)


def _csv_escape(val) -> str:
    """Render a value for COPY ... WITH CSV. None -> empty (treated as NULL)."""
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return repr(val)
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


def load_one_file(
    cur,
    csv_path: Path,
    dataset_source: str,
    source_dataset_id: str,
    limit: Optional[int],
) -> tuple[int, int]:
    """Stream a CSV through StringIO + COPY. Returns (rows_loaded, rows_skipped)."""
    print(f"  Reading: {csv_path.name}")
    if not csv_path.exists():
        print(f"  SKIP: file not found: {csv_path}")
        return (0, 0)

    rows_loaded = 0
    rows_skipped = 0
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        # Resolve header -> native column mapping for THIS file
        header_to_native = {}
        for h in reader.fieldnames or []:
            mapped = HEADER_MAP.get(h.strip())
            if mapped:
                header_to_native[h] = mapped
            else:
                # Unknown header -- ignore but warn once
                print(f"  WARN: unmapped header column '{h}' in {csv_path.name}")

        for raw_row in reader:
            if limit is not None and rows_loaded >= limit:
                break

            # Build native column dict (Title Case headers may be missing in 20-col files)
            native = {col: None for col in NATIVE_COLUMNS}
            for src_h, native_col in header_to_native.items():
                v = raw_row.get(src_h)
                if v is not None:
                    v = v.strip()
                    if v == "":
                        v = None
                native[native_col] = v

            vendor_name_raw = native.get("vendor_name_raw") or ""
            if not vendor_name_raw:
                # Vendor name is required (NOT NULL) -- skip
                rows_skipped += 1
                continue

            # Canonical fields
            vendor_name = vendor_name_raw
            vendor_name_norm = normalize_vendor_name(vendor_name)
            vendor_state = native.get("vendor_state_raw") or "NY"
            vendor_city = native.get("vendor_city_raw")
            vendor_address_1 = native.get("vendor_address_1_raw")
            vendor_postal_code = native.get("vendor_postal_code_raw")
            contract_amount = parse_amount(native.get("contract_amount_raw"))
            award_date = parse_date(native.get("award_date_raw"))
            agency_name = native.get("authority_name")

            row = [
                dataset_source,
                source_dataset_id,
                vendor_name,
                vendor_name_norm,
                vendor_state,
                vendor_city,
                vendor_address_1,
                vendor_postal_code,
                contract_amount,
                award_date,
                agency_name,
            ] + [native.get(col) for col in NATIVE_COLUMNS]

            writer.writerow([_csv_escape(v) for v in row])
            rows_loaded += 1

            # Flush in chunks to avoid huge in-memory buffers
            if rows_loaded % 50000 == 0:
                buffer.seek(0)
                cur.copy_expert(
                    f"COPY {TABLE_NAME} ({', '.join(COPY_COLUMNS)}) "
                    f"FROM STDIN WITH CSV NULL ''",
                    buffer,
                )
                buffer.seek(0)
                buffer.truncate(0)
                writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
                print(f"    {rows_loaded:>9,} rows so far")

    # Final flush
    if buffer.tell() > 0:
        buffer.seek(0)
        cur.copy_expert(
            f"COPY {TABLE_NAME} ({', '.join(COPY_COLUMNS)}) "
            f"FROM STDIN WITH CSV NULL ''",
            buffer,
        )

    print(f"    Done: {rows_loaded:,} loaded, {rows_skipped:,} skipped (no vendor name)")
    return rows_loaded, rows_skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load NY ABO 4-dataset procurement CSVs into unified staging table."
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("C:/Users/jakew/Downloads/"),
        help="Directory containing the 4 ABO procurement CSV files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Smoke-test mode: load at most N rows PER FILE (default = all).",
    )
    parser.add_argument(
        "--no-freshness-update",
        action="store_true",
        help="Skip data_source_freshness write (for dev runs).",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Allow the loader to succeed and write freshness even if one or more of "
            "the 4 expected input CSVs is missing or empty. Default: fail with exit code 2 "
            "to prevent silent partial loads (e.g. when a quarterly refresh misnames a file)."
        ),
    )
    args = parser.parse_args()

    csv_dir: Path = args.csv_dir
    if not csv_dir.is_dir():
        print(f"ERROR: --csv-dir not found: {csv_dir}", file=sys.stderr)
        return 2

    # Preflight: verify ALL 4 expected CSVs exist BEFORE we DROP+CREATE the
    # staging table or COPY anything. Without this check, a missing file
    # discovered mid-load would leave the staging table populated with rows
    # from datasets 1, 3, 4 only and the operator might miss the exit-code
    # signal before downstream MVs read the partial data.
    # (Open Problem: NY ABO Loader Atomicity, fixed 2026-05-04.)
    if not args.allow_partial:
        preflight_missing = [
            fname for _, _, fname in DATASETS
            if not (csv_dir / fname).exists()
        ]
        if preflight_missing:
            print("=" * 70)
            print(
                f"ERROR: preflight failed -- {len(preflight_missing)} of "
                f"{len(DATASETS)} expected NY ABO CSVs not found in {csv_dir}"
            )
            for fname in preflight_missing:
                print(f"  - {fname}")
            print()
            print(
                "  Refusing to drop+rebuild staging table with partial input. "
                "Download the missing files, or pass --allow-partial to override "
                "(not recommended for production)."
            )
            print("=" * 70)
            return 2

    print("=" * 70)
    print("NY ABO Procurement Loader")
    print(f"  csv_dir:           {csv_dir}")
    print(f"  table:             {TABLE_NAME}")
    print(f"  limit per file:    {args.limit if args.limit else 'NONE (full load)'}")
    print(f"  freshness update:  {'SKIP' if args.no_freshness_update else 'YES'}")
    print("=" * 70)

    t0 = time.time()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("\n[1/4] Drop + create table...")
            cur.execute(build_create_sql())
            conn.commit()

            print(f"\n[2/4] Loading {len(DATASETS)} dataset files via COPY...")
            total_loaded = 0
            total_skipped = 0
            missing_files: list[str] = []
            empty_files: list[str] = []
            # Files where rows were skipped 100% of the time -- distinct from
            # "truly empty" because the file IS present and HAS rows but the
            # parser rejected every one (signal of schema drift). Reported
            # separately so an operator can tell "ABO never published this
            # quarter" apart from "ABO changed their schema, our parser is
            # broken."
            all_rejected_files: list[tuple[str, int]] = []
            per_dataset_loaded: dict[str, int] = {}
            for ds_source, ds_id, fname in DATASETS:
                print(f"\n  Dataset: {ds_source} (id={ds_id})")
                csv_path = csv_dir / fname
                if not csv_path.exists():
                    missing_files.append(fname)
                    per_dataset_loaded[ds_source] = 0
                    print(f"  MISSING: {csv_path}")
                    continue
                loaded, skipped = load_one_file(
                    cur, csv_path, ds_source, ds_id, args.limit
                )
                conn.commit()
                total_loaded += loaded
                total_skipped += skipped
                per_dataset_loaded[ds_source] = loaded
                if loaded == 0:
                    if skipped > 0:
                        # File present, rows present, every row rejected --
                        # almost certainly schema drift. Different signal than
                        # an empty file.
                        all_rejected_files.append((fname, skipped))
                    else:
                        empty_files.append(fname)

            # Fail loudly if any expected dataset didn't contribute rows, unless
            # operator opts in via --allow-partial. This prevents a future
            # quarterly refresh that misnames one file from silently producing
            # partial NY ABO data with misleading freshness counts.
            if (missing_files or empty_files or all_rejected_files) and not args.allow_partial:
                print()
                print("=" * 70)
                print(
                    "ERROR: NY ABO loader expected all "
                    f"{len(DATASETS)} input CSVs to contribute rows."
                )
                if missing_files:
                    print(f"  Missing files ({len(missing_files)}):")
                    for f in missing_files:
                        print(f"    - {f}")
                if empty_files:
                    print(f"  Truly empty files / 0 rows in source ({len(empty_files)}):")
                    for f in empty_files:
                        print(f"    - {f}")
                if all_rejected_files:
                    print(
                        f"  Files where ALL rows were rejected -- LIKELY SCHEMA DRIFT "
                        f"({len(all_rejected_files)}):"
                    )
                    for f, sk in all_rejected_files:
                        print(f"    - {f} ({sk:,} rows rejected by parser)")
                print()
                print("  Per-dataset rows loaded so far:")
                for ds_source, n in per_dataset_loaded.items():
                    print(f"    {ds_source}: {n:,}")
                print()
                print("  Refusing to write data_source_freshness with partial data.")
                print("  Re-run with --allow-partial to override (not recommended for production).")
                print("=" * 70)
                return 2

            print("\n[3/4] Building indexes...")
            for sql in build_indexes_sql():
                cur.execute(sql)
            conn.commit()

            # Pull stats for summary + freshness
            print("\n[4/4] Computing summary stats...")
            cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            row_count = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(DISTINCT vendor_name_norm) FROM {TABLE_NAME}")
            distinct_vendors = cur.fetchone()[0]
            cur.execute(
                f"SELECT MIN(award_date), MAX(award_date) FROM {TABLE_NAME} "
                f"WHERE award_date IS NOT NULL"
            )
            date_min, date_max = cur.fetchone()
            cur.execute(
                f"SELECT COALESCE(SUM(contract_amount), 0) FROM {TABLE_NAME}"
            )
            total_value = cur.fetchone()[0]
            cur.execute(
                f"SELECT vendor_name FROM {TABLE_NAME} "
                f"WHERE vendor_name IS NOT NULL ORDER BY id LIMIT 1"
            )
            sample_row = cur.fetchone()
            sample_vendor = sample_row[0] if sample_row else "(none)"

            # Freshness registration
            if not args.no_freshness_update:
                # Build per-dataset counts string for traceability
                ds_counts = ", ".join(
                    f"{ds}={n:,}" for ds, n in per_dataset_loaded.items()
                )
                partial_note = ""
                if missing_files or empty_files:
                    partial_note = (
                        f" PARTIAL LOAD (--allow-partial): "
                        f"missing={len(missing_files)}, empty={len(empty_files)}."
                    )
                notes = (
                    f"4 datasets unified ({ds_counts}). "
                    f"Source dataset IDs: state_authorities=ehig-g5x3, "
                    f"local_authorities=8w5p-k45m, local_dev_corps=d84c-dk28, "
                    f"industrial_dev_agencies=p3p6-xqr5. "
                    f"Skipped {total_skipped:,} rows missing vendor name.{partial_note}"
                )
                cur.execute(
                    """
                    INSERT INTO data_source_freshness
                        (source_name, display_name, last_updated, record_count,
                         date_range_start, date_range_end, notes)
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s)
                    ON CONFLICT (source_name) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        last_updated = NOW(),
                        record_count = EXCLUDED.record_count,
                        date_range_start = EXCLUDED.date_range_start,
                        date_range_end = EXCLUDED.date_range_end,
                        notes = EXCLUDED.notes
                    """,
                    [SOURCE_NAME, DISPLAY_NAME, row_count, date_min, date_max, notes],
                )
                conn.commit()
                print("  data_source_freshness updated.")
            else:
                print("  Skipped data_source_freshness update (--no-freshness-update).")

    finally:
        conn.close()

    wall = time.time() - t0
    mins, secs = divmod(int(wall), 60)

    # Total $ format
    try:
        total_value_int = int(total_value)
    except (TypeError, ValueError):
        total_value_int = 0

    print()
    print("=" * 70)
    print("=== NY ABO PROCUREMENT LOAD COMPLETE ===")
    print(f"Table:             {TABLE_NAME}")
    print(f"Rows loaded:       {row_count:,}")
    print(f"Distinct vendors:  {distinct_vendors:,}")
    if date_min and date_max:
        print(f"Date range:        {date_min} to {date_max}")
    else:
        print("Date range:        (no parseable award dates)")
    print(f"Total $ value:     ${total_value_int:,}")
    print(f"Sample vendor:     {sample_vendor}")
    print(f"Skipped (no name): {total_skipped:,}")
    print(f"Wall time:         {mins}m {secs}s")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
