"""
Load EPA ECHO Exporter into epa_echo_facilities.

24Q-21: Environmental compliance and enforcement. Currently empty in the
24-Question coverage scorecard. EPA's Enforcement and Compliance History
Online (ECHO) consolidates ~1.5M regulated facilities across CAA (air),
CWA (water), RCRA (hazardous waste), SDWA (drinking water), and other
programs into a weekly-refreshed bulk export.

Source: https://echo.epa.gov/files/echodownloads/echo_exporter.zip
Schema: 133 columns; we keep a focused 30-column projection.

Usage:
    py scripts/etl/load_epa_echo.py                            # use existing zip
    py scripts/etl/load_epa_echo.py --redownload               # re-fetch from EPA
    py scripts/etl/load_epa_echo.py --zip-path /path/to/zip    # use custom zip path

Run time: ~3-5 min (1.5M rows via COPY).
"""
import argparse
import csv
import io
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection

DEFAULT_ZIP = PROJECT_ROOT / "files" / "epa_echo" / "echo_exporter.zip"
DOWNLOAD_URL = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"

# Projection: 30 columns from the 133 available. Drops sub-program detail
# (CAA_/CWA_/RCRA_ counts) since the FAC_-prefixed totals roll them up.
KEEP_COLS = [
    "REGISTRY_ID",
    "FAC_NAME",
    "FAC_STREET",
    "FAC_CITY",
    "FAC_STATE",
    "FAC_ZIP",
    "FAC_COUNTY",
    "FAC_FIPS_CODE",
    "FAC_LAT",
    "FAC_LONG",
    "FAC_NAICS_CODES",
    "FAC_SIC_CODES",
    "FAC_ACTIVE_FLAG",
    "FAC_MAJOR_FLAG",
    "FAC_INSPECTION_COUNT",
    "FAC_DATE_LAST_INSPECTION",
    "FAC_DAYS_LAST_INSPECTION",
    "FAC_INFORMAL_COUNT",
    "FAC_DATE_LAST_INFORMAL_ACTION",
    "FAC_FORMAL_ACTION_COUNT",
    "FAC_DATE_LAST_FORMAL_ACTION",
    "FAC_TOTAL_PENALTIES",
    "FAC_PENALTY_COUNT",
    "FAC_LAST_PENALTY_AMT",
    "FAC_DATE_LAST_PENALTY",
    "FAC_QTRS_WITH_NC",
    "FAC_3YR_COMPLIANCE_HISTORY",
    "FAC_COMPLIANCE_STATUS",
    "FAC_SNC_FLAG",
    "FAC_INDIAN_CNTRY_FLAG",
]

DDL_TABLE = """
DROP TABLE IF EXISTS epa_echo_facilities CASCADE;
CREATE TABLE epa_echo_facilities (
    registry_id              TEXT PRIMARY KEY,
    fac_name                 TEXT,
    fac_street               TEXT,
    fac_city                 TEXT,
    fac_state                CHAR(2),
    fac_zip                  TEXT,
    fac_county               TEXT,
    fac_fips_code            TEXT,
    fac_lat                  DOUBLE PRECISION,
    fac_long                 DOUBLE PRECISION,
    fac_naics_codes          TEXT,
    fac_sic_codes            TEXT,
    fac_active_flag          CHAR(1),
    fac_major_flag           CHAR(1),
    fac_inspection_count     INTEGER,
    fac_date_last_inspection DATE,
    fac_days_last_inspection INTEGER,
    fac_informal_count       INTEGER,
    fac_date_last_informal_action DATE,
    fac_formal_action_count  INTEGER,
    fac_date_last_formal_action   DATE,
    fac_total_penalties      NUMERIC(14,2),
    fac_penalty_count        INTEGER,
    fac_last_penalty_amt     NUMERIC(14,2),
    fac_date_last_penalty    DATE,
    fac_qtrs_with_nc         INTEGER,
    fac_3yr_compliance_history TEXT,
    fac_compliance_status    TEXT,
    fac_snc_flag             CHAR(1),
    fac_indian_cntry_flag    CHAR(1),
    name_norm                TEXT,
    loaded_at                TIMESTAMPTZ DEFAULT NOW()
);
"""

# Indexes are created AFTER the bulk load to avoid per-row index updates.
# Without this split, the GIN trigram index alone roughly 5x's the load time.
DDL_INDEXES = """
CREATE INDEX idx_epa_echo_state_name      ON epa_echo_facilities (fac_state, name_norm);
CREATE INDEX idx_epa_echo_zip             ON epa_echo_facilities (fac_zip) WHERE fac_zip IS NOT NULL;
CREATE INDEX idx_epa_echo_active          ON epa_echo_facilities (fac_active_flag) WHERE fac_active_flag = 'Y';
CREATE INDEX idx_epa_echo_name_trgm       ON epa_echo_facilities USING gin (name_norm gin_trgm_ops);
"""


def _norm_int(v):
    if not v or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _norm_float(v):
    if not v or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _norm_date(v):
    """ECHO dates are MM/DD/YYYY."""
    if not v or v == "":
        return None
    try:
        return datetime.strptime(v.strip(), "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


def _norm_char1(v):
    if not v or v == "":
        return None
    return v.strip()[:1].upper()


def _norm_zip(v):
    if not v:
        return None
    return v.strip()[:10] or None


def _norm_state(v):
    if not v:
        return None
    s = v.strip().upper()[:2]
    return s if len(s) == 2 and s.isalpha() else None


def _norm_name_match(name):
    """Aggressive normalization for matching: upper, strip suffix, collapse spaces."""
    if not name:
        return None
    s = name.upper().strip()
    # Strip common suffixes (single-pass)
    for suffix in (" LLC", " L.L.C.", " INC", " INC.", " CORPORATION", " CORP",
                   " CO.", " COMPANY", " LP", " LTD", " PLLC", " PC"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip(" ,.")
            break
    # Collapse whitespace + drop punctuation
    import re
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _project_row(row, header_index):
    """Pluck KEEP_COLS values out of a wide CSV row, applying type coercion."""
    g = lambda col: row[header_index[col]] if col in header_index else ""
    return (
        g("REGISTRY_ID").strip(),
        g("FAC_NAME").strip() or None,
        g("FAC_STREET").strip() or None,
        g("FAC_CITY").strip() or None,
        _norm_state(g("FAC_STATE")),
        _norm_zip(g("FAC_ZIP")),
        g("FAC_COUNTY").strip() or None,
        g("FAC_FIPS_CODE").strip() or None,
        _norm_float(g("FAC_LAT")),
        _norm_float(g("FAC_LONG")),
        g("FAC_NAICS_CODES").strip() or None,
        g("FAC_SIC_CODES").strip() or None,
        _norm_char1(g("FAC_ACTIVE_FLAG")),
        _norm_char1(g("FAC_MAJOR_FLAG")),
        _norm_int(g("FAC_INSPECTION_COUNT")),
        _norm_date(g("FAC_DATE_LAST_INSPECTION")),
        _norm_int(g("FAC_DAYS_LAST_INSPECTION")),
        _norm_int(g("FAC_INFORMAL_COUNT")),
        _norm_date(g("FAC_DATE_LAST_INFORMAL_ACTION")),
        _norm_int(g("FAC_FORMAL_ACTION_COUNT")),
        _norm_date(g("FAC_DATE_LAST_FORMAL_ACTION")),
        _norm_float(g("FAC_TOTAL_PENALTIES")),
        _norm_int(g("FAC_PENALTY_COUNT")),
        _norm_float(g("FAC_LAST_PENALTY_AMT")),
        _norm_date(g("FAC_DATE_LAST_PENALTY")),
        _norm_int(g("FAC_QTRS_WITH_NC")),
        g("FAC_3YR_COMPLIANCE_HISTORY").strip() or None,
        g("FAC_COMPLIANCE_STATUS").strip() or None,
        _norm_char1(g("FAC_SNC_FLAG")),
        _norm_char1(g("FAC_INDIAN_CNTRY_FLAG")),
        _norm_name_match(g("FAC_NAME")),
    )


def download(zip_path: Path):
    """Download the ECHO Exporter ZIP via PowerShell (works around Windows
    cert revocation issues that bite curl)."""
    import subprocess
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {DOWNLOAD_URL} -> {zip_path}")
    cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        f"Invoke-WebRequest -Uri '{DOWNLOAD_URL}' -OutFile '{zip_path}' -UseBasicParsing",
    ]
    subprocess.run(cmd, check=True)
    print(f"  Downloaded {zip_path.stat().st_size / 1e6:.1f} MB")


def load(zip_path: Path):
    if not zip_path.exists():
        raise FileNotFoundError(f"{zip_path} not found; pass --redownload")

    conn = get_connection()
    cur = conn.cursor()

    print("Creating epa_echo_facilities table (indexes deferred)...")
    conn.autocommit = True
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cur.execute(DDL_TABLE)
    conn.autocommit = False

    print(f"Reading {zip_path}...")
    t0 = time.time()
    z = zipfile.ZipFile(zip_path)
    csv_name = next(n for n in z.namelist() if n.endswith(".csv"))

    with z.open(csv_name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.reader(text)
        header = next(reader)
        header_index = {h: i for i, h in enumerate(header)}
        missing = [c for c in KEEP_COLS if c not in header_index]
        if missing:
            print(f"WARNING: missing columns in CSV: {missing}")

        # Stream rows into COPY via a generator
        from psycopg2.extras import execute_values
        BATCH = 5000
        batch = []
        total = 0
        skipped = 0

        insert_sql = """
            INSERT INTO epa_echo_facilities (
                registry_id, fac_name, fac_street, fac_city, fac_state, fac_zip,
                fac_county, fac_fips_code, fac_lat, fac_long, fac_naics_codes,
                fac_sic_codes, fac_active_flag, fac_major_flag,
                fac_inspection_count, fac_date_last_inspection, fac_days_last_inspection,
                fac_informal_count, fac_date_last_informal_action,
                fac_formal_action_count, fac_date_last_formal_action,
                fac_total_penalties, fac_penalty_count, fac_last_penalty_amt,
                fac_date_last_penalty, fac_qtrs_with_nc, fac_3yr_compliance_history,
                fac_compliance_status, fac_snc_flag, fac_indian_cntry_flag, name_norm
            ) VALUES %s
            ON CONFLICT (registry_id) DO NOTHING
        """

        for row in reader:
            try:
                projected = _project_row(row, header_index)
            except (IndexError, ValueError):
                skipped += 1
                continue
            if not projected[0]:  # registry_id required
                skipped += 1
                continue
            batch.append(projected)
            if len(batch) >= BATCH:
                execute_values(cur, insert_sql, batch, page_size=BATCH)
                total += len(batch)
                batch = []
                if total % 100_000 == 0:
                    print(f"  Loaded {total:,} rows ({time.time() - t0:.0f}s elapsed)")

        if batch:
            execute_values(cur, insert_sql, batch, page_size=BATCH)
            total += len(batch)

    conn.commit()
    print(f"\n  Loaded {total:,} rows ({skipped:,} skipped) in {time.time() - t0:.0f}s")

    print("  Creating indexes...")
    t1 = time.time()
    conn.autocommit = True
    cur.execute(DDL_INDEXES)
    conn.autocommit = False
    print(f"    Indexes created in {time.time() - t1:.0f}s")

    # Refresh data_source_freshness
    cur.execute("""
        INSERT INTO data_source_freshness
            (source_name, display_name, last_updated, record_count,
             date_range_start, date_range_end, notes)
        VALUES (
            'epa_echo', 'EPA ECHO Environmental Enforcement', %s, %s,
            (SELECT MIN(fac_date_last_inspection) FROM epa_echo_facilities WHERE fac_date_last_inspection IS NOT NULL),
            (SELECT MAX(fac_date_last_inspection) FROM epa_echo_facilities WHERE fac_date_last_inspection IS NOT NULL),
            '24Q-21 environmental signal. EPA ECHO weekly bulk export of CAA/CWA/RCRA/SDWA enforcement.'
        )
        ON CONFLICT (source_name) DO UPDATE SET
            last_updated = EXCLUDED.last_updated,
            record_count = EXCLUDED.record_count,
            date_range_start = EXCLUDED.date_range_start,
            date_range_end = EXCLUDED.date_range_end,
            notes = EXCLUDED.notes
    """, (datetime.now(timezone.utc), total))
    conn.commit()
    print("  Updated data_source_freshness for epa_echo")

    # Print quick stats
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities")
    print("\nVerification:")
    print(f"  epa_echo_facilities rows:       {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_active_flag = 'Y'")
    print(f"  active facilities:               {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_inspection_count > 0")
    print(f"  with at least 1 inspection:      {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_formal_action_count > 0")
    print(f"  with formal enforcement action:  {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_total_penalties > 0")
    print(f"  with penalties assessed:         {cur.fetchone()[0]:,}")
    cur.execute("SELECT fac_state, COUNT(*) AS n FROM epa_echo_facilities GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    print("  Top states:")
    for s, n in cur.fetchall():
        print(f"    {s}: {n:,}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP), help="Path to echo_exporter.zip")
    parser.add_argument("--redownload", action="store_true", help="Re-fetch from EPA before loading")
    args = parser.parse_args()

    zip_path = Path(args.zip_path)
    if args.redownload or not zip_path.exists():
        download(zip_path)
    load(zip_path)


if __name__ == "__main__":
    main()
