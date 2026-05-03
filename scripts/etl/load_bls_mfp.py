#!/usr/bin/env python3
"""Load BLS Multifactor Productivity CSV data into PostgreSQL.

Source: bls_mfp_data.csv (1,350 rows, 36 series, years 1987-2024)
Target: bls_mfp table in olms_multiyear
"""

import argparse
import csv
import io
import sys

import psycopg2

DB_PARAMS = dict(
    dbname="olms_multiyear",
    user="postgres",
    password="Juniordog33!",
    host="localhost",
)

CSV_PATH = r"C:\Users\jakew\Downloads\bls_mfp_data.csv"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bls_mfp (
    series_id VARCHAR(20) NOT NULL,
    sector VARCHAR(50) NOT NULL,
    measure VARCHAR(30) NOT NULL,
    duration_type VARCHAR(20) NOT NULL,
    year INTEGER NOT NULL,
    value NUMERIC,
    PRIMARY KEY (series_id, year)
);
CREATE INDEX IF NOT EXISTS idx_mfp_year ON bls_mfp (year);
CREATE INDEX IF NOT EXISTS idx_mfp_measure ON bls_mfp (measure);
CREATE INDEX IF NOT EXISTS idx_mfp_sector ON bls_mfp (sector);
"""


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def step_schema():
    print("Creating table bls_mfp ...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    print("  Done.")


def step_load():
    print(f"Loading from {CSV_PATH} ...")

    # Read CSV into a StringIO buffer formatted for COPY
    buf = io.StringIO()
    row_count = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            buf.write("\t".join([
                row["series_id"],
                row["sector"],
                row["measure"],
                row["duration_type"],
                row["year"],
                row["value"],
            ]) + "\n")
            row_count += 1

    buf.seek(0)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE bls_mfp;")
            cur.copy_from(
                buf,
                "bls_mfp",
                sep="\t",
                columns=("series_id", "sector", "measure", "duration_type", "year", "value"),
            )
        conn.commit()

    print(f"  Loaded {row_count} rows.")


def step_verify():
    print("Verifying bls_mfp ...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bls_mfp;")
            count = cur.fetchone()[0]
            print(f"  Row count: {count}")

            cur.execute("SELECT MIN(year), MAX(year) FROM bls_mfp;")
            yr_min, yr_max = cur.fetchone()
            print(f"  Year range: {yr_min} - {yr_max}")

            cur.execute("SELECT COUNT(DISTINCT series_id) FROM bls_mfp;")
            n_series = cur.fetchone()[0]
            print(f"  Distinct series: {n_series}")

            cur.execute("SELECT COUNT(DISTINCT sector) FROM bls_mfp;")
            n_sectors = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT measure) FROM bls_mfp;")
            n_measures = cur.fetchone()[0]
            print(f"  Sectors: {n_sectors}, Measures: {n_measures}")

            print("\n  -- Capital_Intensity sample (Index, last 5 years) --")
            cur.execute("""
                SELECT series_id, sector, year, value
                FROM bls_mfp
                WHERE measure = 'Capital_Intensity'
                  AND duration_type = 'Index_2017eq100'
                ORDER BY sector, year DESC
                LIMIT 10;
            """)
            for row in cur.fetchall():
                print(f"    {row[0]}  {row[1]:<30s}  {row[2]}  {row[3]}")

            print("\n  -- Labor_Input sample (Pct_Change_YoY, last 5 years) --")
            cur.execute("""
                SELECT series_id, sector, year, value
                FROM bls_mfp
                WHERE measure = 'Labor_Input'
                  AND duration_type = 'Pct_Change_YoY'
                ORDER BY sector, year DESC
                LIMIT 10;
            """)
            for row in cur.fetchall():
                print(f"    {row[0]}  {row[1]:<30s}  {row[2]}  {row[3]}")

    print("\n  Verification complete.")


STEPS = {
    "schema": [step_schema],
    "load": [step_load],
    "verify": [step_verify],
    "all": [step_schema, step_load, step_verify],
}


def main():
    parser = argparse.ArgumentParser(description="Load BLS Multifactor Productivity data")
    parser.add_argument(
        "--step",
        choices=STEPS.keys(),
        default="all",
        help="Which step to run (default: all)",
    )
    args = parser.parse_args()

    for fn in STEPS[args.step]:
        fn()

    print("\nDone.")


if __name__ == "__main__":
    main()
