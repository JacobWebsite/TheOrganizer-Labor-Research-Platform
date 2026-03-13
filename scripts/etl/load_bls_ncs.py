"""
Load BLS National Compensation Survey (NCS) / Employee Benefits data.

Source: Data_3_04/nb.* files
Tables: bls_ncs_industry, bls_ncs_estimate, bls_ncs_datatype, bls_ncs_subcell,
        bls_ncs_ownership, bls_ncs_provision, bls_ncs_series (~100K),
        bls_ncs_data (~768K)
Curated MV: mv_ncs_benefits_access

Usage:
  py scripts/etl/load_bls_ncs.py
  py scripts/etl/load_bls_ncs.py --data-dir Data_3_04 --dry-run
  py scripts/etl/load_bls_ncs.py --step lookups
  py scripts/etl/load_bls_ncs.py --step series
  py scripts/etl/load_bls_ncs.py --step data
  py scripts/etl/load_bls_ncs.py --step views
  py scripts/etl/load_bls_ncs.py --step verify
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
    ap = argparse.ArgumentParser(description="Load BLS NCS/Benefits data")
    ap.add_argument("--data-dir", default="Data_3_04")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--step", choices=["lookups", "series", "data", "views", "verify"],
                    default=None)
    return ap.parse_args()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
LOOKUP_TABLES = {
    "bls_ncs_industry": {
        "file": "nb.industry",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_industry (
                industry_code VARCHAR(6) PRIMARY KEY,
                industry_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_ncs_estimate": {
        "file": "nb.estimate",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_estimate (
                estimate_code VARCHAR(2) PRIMARY KEY,
                estimate_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_ncs_datatype": {
        "file": "nb.datatype",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_datatype (
                datatype_code VARCHAR(2) PRIMARY KEY,
                datatype_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_ncs_subcell": {
        "file": "nb.subcell",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_subcell (
                subcell_code VARCHAR(2) PRIMARY KEY,
                subcell_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_ncs_ownership": {
        "file": "nb.ownership",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_ownership (
                ownership_code VARCHAR(1) PRIMARY KEY,
                ownership_text TEXT,
                display_level INTEGER,
                selectable BOOLEAN,
                sort_sequence INTEGER
            )
        """,
    },
    "bls_ncs_provision": {
        "file": "nb.provision",
        "sql": """
            CREATE TABLE IF NOT EXISTS bls_ncs_provision (
                provision_code VARCHAR(3) PRIMARY KEY,
                provision_text TEXT,
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
CREATE TABLE IF NOT EXISTS bls_ncs_series (
    series_id VARCHAR(30) PRIMARY KEY,
    seasonal CHAR(1),
    ownership_code VARCHAR(1),
    estimate_code VARCHAR(2),
    industry_code VARCHAR(6),
    occupation_code VARCHAR(6),
    subcell_code VARCHAR(2),
    datatype_code VARCHAR(2),
    provision_code VARCHAR(3),
    survey_code VARCHAR(2),
    series_title TEXT,
    footnote_codes TEXT,
    begin_year INTEGER,
    begin_period VARCHAR(3),
    end_year INTEGER,
    end_period VARCHAR(3)
);
"""

SERIES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ncs_series_ind ON bls_ncs_series (industry_code)",
    "CREATE INDEX IF NOT EXISTS idx_ncs_series_own ON bls_ncs_series (ownership_code)",
    "CREATE INDEX IF NOT EXISTS idx_ncs_series_prov ON bls_ncs_series (provision_code)",
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
DATA_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bls_ncs_data (
    series_id VARCHAR(30) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(3) NOT NULL,
    value NUMERIC(12,4),
    footnote_codes TEXT,
    _loaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (series_id, year, period)
);
"""

DATA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ncs_data_year ON bls_ncs_data (year)",
]


# ---------------------------------------------------------------------------
# MV
# ---------------------------------------------------------------------------
MV_SQL = """
CREATE MATERIALIZED VIEW mv_ncs_benefits_access AS
SELECT d.year, s.ownership_code, own.ownership_text,
       s.industry_code, i.industry_text AS industry_name,
       s.estimate_code, est.estimate_text,
       s.datatype_code, dt.datatype_text,
       s.provision_code, prov.provision_text,
       s.subcell_code, sc.subcell_text,
       d.value AS rate
FROM bls_ncs_data d
JOIN bls_ncs_series s ON d.series_id = s.series_id
LEFT JOIN bls_ncs_industry i ON s.industry_code = i.industry_code
LEFT JOIN bls_ncs_ownership own ON s.ownership_code = own.ownership_code
LEFT JOIN bls_ncs_estimate est ON s.estimate_code = est.estimate_code
LEFT JOIN bls_ncs_datatype dt ON s.datatype_code = dt.datatype_code
LEFT JOIN bls_ncs_provision prov ON s.provision_code = prov.provision_code
LEFT JOIN bls_ncs_subcell sc ON s.subcell_code = sc.subcell_code
WHERE d.period = 'A01'
  AND s.occupation_code = '000000';
"""


def step_lookups(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading NCS lookup tables ===")
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
    print(f"\n[{ts()}] === Loading bls_ncs_series ===")
    fpath = os.path.join(data_dir, "nb.series")
    if not os.path.exists(fpath):
        raise SystemExit(f"Missing: {fpath}")
    if dry_run:
        print(f"  DRY RUN: would load bls_ncs_series")
        return

    from psycopg2.extras import execute_values

    with conn.cursor() as cur:
        cur.execute(SERIES_CREATE_SQL)
        cur.execute("TRUNCATE bls_ncs_series")
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
            if len(parts) < 12:
                continue
            # series_id, seasonal, ownership_code, estimate_code, industry_code,
            # occupation_code, subcell_code, datatype_code, provision_code,
            # survey_code, series_title, footnote_codes, begin_year, begin_period,
            # end_year, end_period
            vals = parts[:16] if len(parts) >= 16 else parts + [""] * (16 - len(parts))
            rows.append(tuple(vals))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO bls_ncs_series
               (series_id, seasonal, ownership_code, estimate_code, industry_code,
                occupation_code, subcell_code, datatype_code, provision_code,
                survey_code, series_title, footnote_codes,
                begin_year, begin_period, end_year, end_period)
               VALUES %s ON CONFLICT DO NOTHING""",
            rows,
            page_size=5000,
        )
    conn.commit()
    print(f"  [{ts()}] bls_ncs_series: {len(rows):,} rows")


def step_data(conn, data_dir, dry_run):
    print(f"\n[{ts()}] === Loading bls_ncs_data ===")
    fpath = os.path.join(data_dir, "nb.data.1.AllData")
    if not os.path.exists(fpath):
        raise SystemExit(f"Missing: {fpath}")
    if dry_run:
        print(f"  DRY RUN: would load bls_ncs_data")
        return

    with conn.cursor() as cur:
        cur.execute(DATA_CREATE_SQL)
        for idx in DATA_INDEXES:
            cur.execute(idx)
    conn.commit()

    insert_sql = """
        INSERT INTO bls_ncs_data (series_id, year, period, value, footnote_codes)
        VALUES %s ON CONFLICT DO NOTHING
    """
    load_data_file(conn, fpath, "bls_ncs_data", insert_sql)


def step_views(conn):
    print(f"\n[{ts()}] === Creating mv_ncs_benefits_access ===")
    with conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_ncs_benefits_access CASCADE")
        cur.execute(MV_SQL)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_ncs_year ON mv_ncs_benefits_access (year)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_ncs_ind ON mv_ncs_benefits_access (industry_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mv_ncs_own ON mv_ncs_benefits_access (ownership_code)")
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mv_ncs_benefits_access")
        cnt = cur.fetchone()[0]
    print(f"  [{ts()}] mv_ncs_benefits_access: {cnt:,} rows")


def step_verify(conn):
    print(f"\n[{ts()}] === NCS Verification ===")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bls_ncs_series")
        print(f"  bls_ncs_series: {cur.fetchone()[0]:,} rows")

        cur.execute("SELECT COUNT(*) FROM bls_ncs_data")
        print(f"  bls_ncs_data: {cur.fetchone()[0]:,} rows")

        # Private industry medical care access
        cur.execute("""
            SELECT year, rate
            FROM mv_ncs_benefits_access
            WHERE ownership_code = '2'
              AND industry_code = '000000'
              AND provision_code = '014'
              AND datatype_code = '01'
              AND subcell_code = '00'
            ORDER BY year DESC
            LIMIT 3
        """)
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"  Private industry medical access {r[0]}: {r[1]}%")
        else:
            # Try broader search
            cur.execute("""
                SELECT year, provision_text, rate
                FROM mv_ncs_benefits_access
                WHERE ownership_code = '2'
                  AND industry_code = '000000'
                  AND subcell_code = '00'
                  AND provision_text ILIKE '%%medical%%'
                ORDER BY year DESC
                LIMIT 5
            """)
            rows = cur.fetchall()
            if rows:
                for r in rows:
                    print(f"  Private industry {r[1]} {r[0]}: {r[2]}%")
            else:
                print("  WARNING: No private industry medical access data found")

        cur.execute("SELECT COUNT(*) FROM mv_ncs_benefits_access")
        print(f"  mv_ncs_benefits_access: {cur.fetchone()[0]:,} rows")


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
