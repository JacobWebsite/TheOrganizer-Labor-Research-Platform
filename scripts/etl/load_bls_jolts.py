"""
Load BLS Job Openings and Labor Turnover Survey (JOLTS) data.

Source: Data_3_04/jt.* files
Tables: bls_jolts_industry, bls_jolts_dataelement, bls_jolts_sizeclass,
        bls_jolts_state, bls_jolts_ratelevel, bls_jolts_series (~2K),
        bls_jolts_data (~618K)
Curated MV: mv_jolts_industry_rates

Usage:
  py scripts/etl/load_bls_jolts.py
  py scripts/etl/load_bls_jolts.py --data-dir Data_3_04 --dry-run
  py scripts/etl/load_bls_jolts.py --step lookups
  py scripts/etl/load_bls_jolts.py --step series
  py scripts/etl/load_bls_jolts.py --step data
  py scripts/etl/load_bls_jolts.py --step views
  py scripts/etl/load_bls_jolts.py --step verify
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from scripts.etl.bls_tsv_helpers import load_data_file, load_lookup_table, ts


def parse_args():
    ap = argparse.ArgumentParser(description="Load BLS JOLTS data")
    ap.add_argument("--data-dir", default="Data_3_04")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--step", choices=["lookups", "series", "data", "views", "verify"],
                    default=None)
    return ap.parse_args()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
LOOKUP_TABLES = {
    "bls_jolts_industry": {
        "file": "jt.industry",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_jolts_industry (
                industry_code VARCHAR(6) PRIMARY KEY,
                industry_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_jolts_dataelement": {
        "file": "jt.dataelement",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_jolts_dataelement (
                dataelement_code VARCHAR(2) PRIMARY KEY,
                dataelement_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_jolts_sizeclass": {
        "file": "jt.sizeclass.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_jolts_sizeclass (
                sizeclass_code VARCHAR(2) PRIMARY KEY,
                sizeclass_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_jolts_state": {
        "file": "jt.state.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_jolts_state (
                state_code VARCHAR(2) PRIMARY KEY,
                state_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_jolts_ratelevel": {
        "file": "jt.ratelevel.txt",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_jolts_ratelevel (
                ratelevel_code VARCHAR(1) PRIMARY KEY,
                ratelevel_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
}


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------
SERIES_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bls_jolts_series (
    series_id VARCHAR(30) PRIMARY KEY,
    seasonal CHAR(1),
    industry_code VARCHAR(6),
    state_code VARCHAR(2),
    area_code VARCHAR(5),
    sizeclass_code VARCHAR(2),
    dataelement_code VARCHAR(2),
    ratelevel_code VARCHAR(1),
    footnote_codes TEXT,
    begin_year INTEGER,
    begin_period VARCHAR(3),
    end_year INTEGER,
    end_period VARCHAR(3)
);
"""

SERIES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jolts_series_ind ON bls_jolts_series (industry_code)",
    "CREATE INDEX IF NOT EXISTS idx_jolts_series_state ON bls_jolts_series (state_code)",
    "CREATE INDEX IF NOT EXISTS idx_jolts_series_de ON bls_jolts_series (dataelement_code)",
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
DATA_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bls_jolts_data (
    series_id VARCHAR(30) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(3) NOT NULL,
    value NUMERIC(12,1),
    footnote_codes TEXT,
    _loaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (series_id, year, period)
);
"""

DATA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jolts_data_year ON bls_jolts_data (year)",
]


# ---------------------------------------------------------------------------
# MV
# ---------------------------------------------------------------------------
MV_SQL = """
CREATE MATERIALIZED VIEW mv_jolts_industry_rates AS
SELECT d.year, d.period, s.industry_code, i.industry_text AS industry_name,
       s.dataelement_code, de.dataelement_text,
       s.state_code, st.state_text,
       d.value AS rate
FROM bls_jolts_data d
JOIN bls_jolts_series s ON d.series_id = s.series_id
LEFT JOIN bls_jolts_industry i ON s.industry_code = i.industry_code
LEFT JOIN bls_jolts_dataelement de ON s.dataelement_code = de.dataelement_code
LEFT JOIN bls_jolts_state st ON s.state_code = st.state_code
WHERE s.ratelevel_code = 'R'
  AND s.sizeclass_code = '00'
  AND s.state_code = '00';
"""


def step_lookups(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading JOLTS lookup tables ===")
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
    print(f"\n[{ts()}] === Loading bls_jolts_series ===")
    fpath = os.path.join(data_dir, "jt.series")
    if not os.path.exists(fpath):
        raise SystemExit(f"Missing: {fpath}")
    if dry_run:
        print(f"  DRY RUN: would load bls_jolts_series")
        return

    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        cur.execute(SERIES_CREATE_SQL)
        cur.execute("TRUNCATE bls_jolts_series")
        for idx in SERIES_INDEXES:
            cur.execute(idx)
    conn.commit()

    rows = []
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            line = line.rstrip("\r\n")
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 10:
                continue
            # series_id, seasonal, industry_code, state_code, area_code,
            # sizeclass_code, dataelement_code, ratelevel_code, footnote_codes,
            # begin_year, begin_period, end_year, end_period
            vals = parts[:13] if len(parts) >= 13 else parts + [""] * (13 - len(parts))
            rows.append(tuple(vals))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO bls_jolts_series
               (series_id, seasonal, industry_code, state_code, area_code,
                sizeclass_code, dataelement_code, ratelevel_code, footnote_codes,
                begin_year, begin_period, end_year, end_period)
               VALUES %s ON CONFLICT DO NOTHING""",
            rows,
            page_size=1000,
        )
    conn.commit()
    print(f"  [{ts()}] bls_jolts_series: {len(rows):,} rows")


def step_data(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading bls_jolts_data ===")
    # Load from all jt.data.*.* files
    data_files = sorted(
        f for f in os.listdir(data_dir)
        if f.startswith("jt.data.") and not f.startswith("jt (")
    )
    if not data_files:
        raise SystemExit(f"No jt.data.* files in {data_dir}")

    if dry_run:
        print(f"  DRY RUN: would load from {len(data_files)} files")
        return

    with conn.cursor() as cur:
        cur.execute(DATA_CREATE_SQL)
        for idx in DATA_INDEXES:
            cur.execute(idx)
    conn.commit()

    insert_sql = """
        INSERT INTO bls_jolts_data (series_id, year, period, value, footnote_codes)
        VALUES %s ON CONFLICT DO NOTHING
    """

    # Use AllItems (most complete) or Current as primary file
    primary = None
    for f in data_files:
        if "AllItems" in f or "Current" in f:
            primary = f
            break
    if not primary:
        primary = data_files[0]

    fpath = os.path.join(data_dir, primary)
    load_data_file(conn, fpath, "bls_jolts_data", insert_sql)


def step_views(conn):
    print(f"\n[{ts()}] === Creating mv_jolts_industry_rates ===")
    with conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_jolts_industry_rates CASCADE")
        cur.execute(MV_SQL)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_jolts_year ON mv_jolts_industry_rates (year)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_jolts_ind ON mv_jolts_industry_rates (industry_code)")
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mv_jolts_industry_rates")
        cnt = cur.fetchone()[0]
    print(f"  [{ts()}] mv_jolts_industry_rates: {cnt:,} rows")


def step_verify(conn):
    print(f"\n[{ts()}] === JOLTS Verification ===")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bls_jolts_series")
        print(f"  bls_jolts_series: {cur.fetchone()[0]:,} rows")

        cur.execute("SELECT COUNT(*) FROM bls_jolts_data")
        print(f"  bls_jolts_data: {cur.fetchone()[0]:,} rows")

        # Total nonfarm quit rate 2024
        cur.execute("""
            SELECT year, period, rate
            FROM mv_jolts_industry_rates
            WHERE industry_code = '000000'
              AND dataelement_code = 'QU'
              AND year = 2024
            ORDER BY period DESC
            LIMIT 3
        """)
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"  Total nonfarm quit rate {r[0]} {r[1]}: {r[2]}")
        else:
            print("  WARNING: No quit rate data found for 2024")

        cur.execute("SELECT COUNT(*) FROM mv_jolts_industry_rates")
        print(f"  mv_jolts_industry_rates: {cur.fetchone()[0]:,} rows")


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
