"""
Load BLS Survey of Occupational Injuries and Illnesses (SOII) data.

Source: Data_3_04/is.* files
Tables: bls_soii_industry, bls_soii_area, bls_soii_case_type, bls_soii_data_type,
        bls_soii_supersector, bls_soii_series (~891K), bls_soii_data (~5.7M)
Curated MV: mv_soii_industry_rates

Usage:
  py scripts/etl/load_bls_soii.py
  py scripts/etl/load_bls_soii.py --data-dir Data_3_04 --dry-run
  py scripts/etl/load_bls_soii.py --step lookups
  py scripts/etl/load_bls_soii.py --step series
  py scripts/etl/load_bls_soii.py --step data
  py scripts/etl/load_bls_soii.py --step views
  py scripts/etl/load_bls_soii.py --step verify
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from scripts.etl.bls_tsv_helpers import load_data_file, load_lookup_table, ts


def parse_args():
    ap = argparse.ArgumentParser(description="Load BLS SOII data")
    ap.add_argument("--data-dir", default="Data_3_04")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--step", choices=["lookups", "series", "data", "views", "verify"],
                    default=None, help="Run only one step (default: all)")
    return ap.parse_args()


# ---------------------------------------------------------------------------
# Lookup table DDL
# ---------------------------------------------------------------------------
LOOKUP_TABLES = {
    "bls_soii_industry": {
        "file": "is.industry.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_soii_industry (
                supersector_code VARCHAR(3),
                industry_code VARCHAR(6) PRIMARY KEY,
                industry_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_soii_area": {
        "file": "is.area",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_soii_area (
                area_code VARCHAR(3) PRIMARY KEY,
                area_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_soii_case_type": {
        "file": "is.case_type.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_soii_case_type (
                case_type_code VARCHAR(2) PRIMARY KEY,
                case_type_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_soii_data_type": {
        "file": "is.data_type.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_soii_data_type (
                data_type_code VARCHAR(2) PRIMARY KEY,
                data_type_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_soii_supersector": {
        "file": "is.supersector",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_soii_supersector (
                supersector_code VARCHAR(3) PRIMARY KEY,
                supersector_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
}


# ---------------------------------------------------------------------------
# Series table
# ---------------------------------------------------------------------------
SERIES_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bls_soii_series (
    series_id VARCHAR(20) PRIMARY KEY,
    seasonal CHAR(1),
    supersector_code VARCHAR(3),
    industry_code VARCHAR(6),
    data_type_code VARCHAR(2),
    case_type_code VARCHAR(2),
    area_code VARCHAR(3),
    series_title TEXT,
    footnote_codes TEXT,
    begin_year INTEGER,
    begin_period VARCHAR(3),
    end_year INTEGER,
    end_period VARCHAR(3)
);
"""

SERIES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_soii_series_ind ON bls_soii_series (industry_code)",
    "CREATE INDEX IF NOT EXISTS idx_soii_series_area ON bls_soii_series (area_code)",
    "CREATE INDEX IF NOT EXISTS idx_soii_series_dtype ON bls_soii_series (data_type_code)",
]


# ---------------------------------------------------------------------------
# Data table
# ---------------------------------------------------------------------------
DATA_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bls_soii_data (
    series_id VARCHAR(20) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(3) NOT NULL,
    value NUMERIC(12,4),
    footnote_codes TEXT,
    _loaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (series_id, year, period)
);
"""

DATA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_soii_data_year ON bls_soii_data (year)",
]


# ---------------------------------------------------------------------------
# MV
# ---------------------------------------------------------------------------
MV_SQL = """
CREATE MATERIALIZED VIEW mv_soii_industry_rates AS
SELECT d.year, s.industry_code, i.industry_text AS industry_name,
       s.case_type_code, ct.case_type_text,
       s.data_type_code, dt.data_type_text,
       d.value AS rate
FROM bls_soii_data d
JOIN bls_soii_series s ON d.series_id = s.series_id
LEFT JOIN bls_soii_industry i ON s.industry_code = i.industry_code
LEFT JOIN bls_soii_case_type ct ON s.case_type_code = ct.case_type_code
LEFT JOIN bls_soii_data_type dt ON s.data_type_code = dt.data_type_code
WHERE d.period = 'A01'
  AND s.area_code IN ('000', '100')
  AND s.data_type_code IN ('1', '3')
  AND s.case_type_code IN ('1', '2', '3');
"""


def step_lookups(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading SOII lookup tables ===")
    for table_name, info in LOOKUP_TABLES.items():
        fpath = os.path.join(data_dir, info["file"])
        if not os.path.exists(fpath):
            print(f"  WARNING: missing {fpath}")
            continue
        if dry_run:
            print(f"  DRY RUN: would load {table_name} from {info['file']}")
            continue
        load_lookup_table(conn, fpath, table_name, info["sql"])


def step_series(conn, data_dir, dry_run):
    """Load series using COPY for speed on ~891K rows."""
    print(f"\n[{ts()}] === Loading bls_soii_series ===")
    fpath = os.path.join(data_dir, "is.series")
    if not os.path.exists(fpath):
        raise SystemExit(f"Missing: {fpath}")
    if dry_run:
        print(f"  DRY RUN: would load bls_soii_series from is.series")
        return

    with conn.cursor() as cur:
        cur.execute(SERIES_CREATE_SQL)
        cur.execute("TRUNCATE bls_soii_series")
        for idx in SERIES_INDEXES:
            cur.execute(idx)
    conn.commit()

    # Parse and load via COPY
    rows = []
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # skip header
            line = line.rstrip("\r\n")
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 10:
                continue
            rows.append(parts)

    # Build CSV buffer for COPY
    buf = io.StringIO()
    for parts in rows:
        # series_id, seasonal, supersector_code, industry_code, data_type_code,
        # case_type_code, area_code, series_title, footnote_codes, begin_year,
        # begin_period, end_year, end_period
        vals = parts[:13] if len(parts) >= 13 else parts + [""] * (13 - len(parts))
        # Escape any tabs/newlines in series_title
        vals[7] = vals[7].replace("\t", " ").replace("\n", " ")
        buf.write("\t".join(vals) + "\n")

    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            """COPY bls_soii_series
               (series_id, seasonal, supersector_code, industry_code,
                data_type_code, case_type_code, area_code, series_title,
                footnote_codes, begin_year, begin_period, end_year, end_period)
               FROM STDIN WITH (FORMAT text, DELIMITER E'\\t')""",
            buf,
        )
    conn.commit()
    print(f"  [{ts()}] bls_soii_series: {len(rows):,} rows")


def step_data(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading bls_soii_data ===")
    fpath = os.path.join(data_dir, "is.data.1.AllData")
    if not os.path.exists(fpath):
        raise SystemExit(f"Missing: {fpath}")
    if dry_run:
        print(f"  DRY RUN: would load bls_soii_data from is.data.1.AllData")
        return

    with conn.cursor() as cur:
        cur.execute(DATA_CREATE_SQL)
        for idx in DATA_INDEXES:
            cur.execute(idx)
    conn.commit()

    insert_sql = """
        INSERT INTO bls_soii_data (series_id, year, period, value, footnote_codes)
        VALUES %s ON CONFLICT DO NOTHING
    """
    load_data_file(conn, fpath, "bls_soii_data", insert_sql)


def step_views(conn):
    print(f"\n[{ts()}] === Creating mv_soii_industry_rates ===")
    with conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_soii_industry_rates CASCADE")
        cur.execute(MV_SQL)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_soii_year ON mv_soii_industry_rates (year)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_soii_ind ON mv_soii_industry_rates (industry_code)")
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mv_soii_industry_rates")
        cnt = cur.fetchone()[0]
    print(f"  [{ts()}] mv_soii_industry_rates: {cnt:,} rows")


def step_verify(conn):
    print(f"\n[{ts()}] === SOII Verification ===")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bls_soii_series")
        print(f"  bls_soii_series: {cur.fetchone()[0]:,} rows")

        cur.execute("SELECT COUNT(*) FROM bls_soii_data")
        print(f"  bls_soii_data: {cur.fetchone()[0]:,} rows")

        # Check for orphan data rows
        cur.execute("""
            SELECT COUNT(*) FROM bls_soii_data d
            WHERE NOT EXISTS (SELECT 1 FROM bls_soii_series s WHERE s.series_id = d.series_id)
        """)
        orphans = cur.fetchone()[0]
        print(f"  Orphan data rows (no matching series): {orphans:,}")

        # Nursing homes (623110) injury rate
        cur.execute("""
            SELECT d.year, d.rate
            FROM mv_soii_industry_rates d
            WHERE d.industry_code = '623110'
              AND d.case_type_code = '1'
              AND d.data_type_code = '3'
            ORDER BY d.year DESC
            LIMIT 3
        """)
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"  Nursing homes (623110) total recordable rate {r[0]}: {r[1]}")
        else:
            print("  WARNING: No nursing home injury rates found")

        cur.execute("SELECT COUNT(*) FROM mv_soii_industry_rates")
        print(f"  mv_soii_industry_rates: {cur.fetchone()[0]:,} rows")


def main():
    args = parse_args()
    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    data_dir = os.path.join(project_root, args.data_dir)
    if not os.path.isdir(data_dir):
        data_dir = args.data_dir

    conn = get_connection()
    try:
        steps = [args.step] if args.step else ["lookups", "series", "data", "views", "verify"]
        for step in steps:
            if step in ("views", "verify") and args.dry_run:
                print(f"  DRY RUN: skipping {step}")
                continue
            if step == "lookups":
                step_lookups(conn, data_dir, args.dry_run)
            elif step == "series":
                step_series(conn, data_dir, args.dry_run)
            elif step == "data":
                step_data(conn, data_dir, args.dry_run)
            elif step == "views":
                step_views(conn)
            elif step == "verify":
                step_verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
