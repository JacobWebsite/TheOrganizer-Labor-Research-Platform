"""
Curate LODES WAC demographic columns into cur_lodes_geo_metrics.

Streams WAC .gz files (one state at a time) and aggregates demographic
columns (race, ethnicity, sex, education) to the county level, then
UPDATEs existing cur_lodes_geo_metrics rows.

WAC demographic columns:
  CR01-CR05,CR07: Race (White, Black, American Indian, Asian, NHPI, Two+)
  CT01-CT02: Ethnicity (Not Hispanic, Hispanic)
  CS01-CS02: Sex (Male, Female)
  CD01-CD04: Education (Less than HS, HS, Some college, Bachelor's+)

Usage:
  py scripts/etl/lodes_curate_demographics.py
  py scripts/etl/lodes_curate_demographics.py --source-dir "path/to/wac/files"
  py scripts/etl/lodes_curate_demographics.py --status
"""

import argparse
import csv
import gzip
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

DEFAULT_SOURCE_DIR = Path('New Data sources 2_27/LODES_bulk_2022')

DEMO_COLS = {
    'C000': 'demo_total_jobs',
    'CR01': 'jobs_white',
    'CR02': 'jobs_black',
    'CR03': 'jobs_native',
    'CR04': 'jobs_asian',
    'CR05': 'jobs_pacific',
    'CR07': 'jobs_two_plus_races',
    'CT01': 'jobs_not_hispanic',
    'CT02': 'jobs_hispanic',
    'CS01': 'jobs_male',
    'CS02': 'jobs_female',
    'CD01': 'jobs_edu_less_than_hs',
    'CD02': 'jobs_edu_hs',
    'CD03': 'jobs_edu_some_college',
    'CD04': 'jobs_edu_bachelors_plus',
}


def add_demographic_columns(conn):
    """Add demographic columns to cur_lodes_geo_metrics if missing."""
    with conn.cursor() as cur:
        for pg_col in DEMO_COLS.values():
            cur.execute(f"""
                ALTER TABLE cur_lodes_geo_metrics
                ADD COLUMN IF NOT EXISTS {pg_col} INTEGER
            """)
        # Percentage columns
        for pct_col in ['pct_female', 'pct_hispanic', 'pct_minority', 'pct_bachelors_plus']:
            cur.execute(f"""
                ALTER TABLE cur_lodes_geo_metrics
                ADD COLUMN IF NOT EXISTS {pct_col} NUMERIC(6,4)
            """)
    conn.commit()
    print("  Demographic columns ensured.")


def process_wac_file(gz_path):
    """Stream a single WAC .gz file and aggregate demographics to county level.

    Returns: dict[county_fips] -> {col_name: int_sum, ...}
    """
    county_data = defaultdict(lambda: defaultdict(int))

    with gzip.open(gz_path, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            geocode = row.get('w_geocode', '')
            if len(geocode) < 5:
                continue
            county_fips = geocode[:5]

            for wac_col, pg_col in DEMO_COLS.items():
                val = row.get(wac_col, '0')
                try:
                    county_data[county_fips][pg_col] += int(val)
                except (ValueError, TypeError):
                    pass

    return county_data


def update_county_demographics(conn, county_data):
    """UPDATE cur_lodes_geo_metrics with aggregated demographic data."""
    updated = 0
    skipped = 0

    with conn.cursor() as cur:
        for county_fips, demo in county_data.items():
            # Build SET clause
            set_parts = []
            values = []
            for col, val in demo.items():
                set_parts.append(f"{col} = %s")
                values.append(val)

            if not set_parts:
                continue

            values.append(county_fips)
            cur.execute(f"""
                UPDATE cur_lodes_geo_metrics
                SET {', '.join(set_parts)}
                WHERE county_fips = %s
            """, values)

            if cur.rowcount > 0:
                updated += 1
            else:
                skipped += 1

    conn.commit()
    return updated, skipped


def compute_percentages(conn):
    """Compute percentage columns from raw counts using demo_total_jobs as denominator."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE cur_lodes_geo_metrics
            SET
                pct_female = CASE WHEN demo_total_jobs > 0
                    THEN ROUND(jobs_female::numeric / demo_total_jobs, 4)
                    ELSE NULL END,
                pct_hispanic = CASE WHEN demo_total_jobs > 0
                    THEN ROUND(jobs_hispanic::numeric / demo_total_jobs, 4)
                    ELSE NULL END,
                pct_minority = CASE WHEN demo_total_jobs > 0
                    THEN ROUND((COALESCE(jobs_black,0) + COALESCE(jobs_native,0)
                        + COALESCE(jobs_asian,0) + COALESCE(jobs_pacific,0)
                        + COALESCE(jobs_two_plus_races,0))::numeric / demo_total_jobs, 4)
                    ELSE NULL END,
                pct_bachelors_plus = CASE WHEN demo_total_jobs > 0
                    THEN ROUND(jobs_edu_bachelors_plus::numeric / demo_total_jobs, 4)
                    ELSE NULL END
            WHERE jobs_white IS NOT NULL
        """)
        pct_updated = cur.rowcount
    conn.commit()
    return pct_updated


def show_status(conn):
    """Show current demographic coverage."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cur_lodes_geo_metrics")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cur_lodes_geo_metrics WHERE jobs_white IS NOT NULL")
        with_demo = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cur_lodes_geo_metrics WHERE pct_female IS NOT NULL")
        with_pct = cur.fetchone()[0]

        print(f"cur_lodes_geo_metrics: {total:,} counties")
        print(f"  With demographics: {with_demo:,} ({with_demo/total*100:.1f}%)" if total else "  Empty")
        print(f"  With percentages:  {with_pct:,}" if total else "")

        if with_demo > 0:
            cur.execute("""
                SELECT
                    AVG(pct_female) AS avg_female,
                    AVG(pct_minority) AS avg_minority,
                    AVG(pct_hispanic) AS avg_hispanic,
                    AVG(pct_bachelors_plus) AS avg_bachelors
                FROM cur_lodes_geo_metrics
                WHERE pct_female IS NOT NULL
            """)
            row = cur.fetchone()
            print(f"  Avg % female:       {float(row[0])*100:.1f}%")
            print(f"  Avg % minority:     {float(row[1])*100:.1f}%")
            print(f"  Avg % hispanic:     {float(row[2])*100:.1f}%")
            print(f"  Avg % bachelors+:   {float(row[3])*100:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='Curate LODES WAC demographics into county metrics')
    parser.add_argument('--source-dir', type=str, default=None,
                        help='Directory containing WAC .gz files')
    parser.add_argument('--status', action='store_true',
                        help='Show current status and exit')
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    if args.status:
        show_status(conn)
        conn.close()
        return

    source_dir = Path(args.source_dir) if args.source_dir else DEFAULT_SOURCE_DIR
    wac_files = sorted(source_dir.glob('*_wac_S000_JT00_2022.csv.gz'))

    if not wac_files:
        print(f"No WAC .gz files found in {source_dir}")
        conn.close()
        return

    print(f"Found {len(wac_files)} WAC files in {source_dir}")

    # Step 1: Add columns
    add_demographic_columns(conn)

    # Step 2: Process each state file
    total_counties = 0
    total_updated = 0
    total_skipped = 0

    for gz_path in wac_files:
        state_abbr = gz_path.name[:2].upper()
        print(f"  Processing {state_abbr}...", end='', flush=True)

        county_data = process_wac_file(gz_path)
        updated, skipped = update_county_demographics(conn, county_data)

        total_counties += len(county_data)
        total_updated += updated
        total_skipped += skipped
        print(f" {len(county_data)} counties, {updated} updated, {skipped} unmatched")

    # Step 3: Compute percentages
    print("\nComputing percentages...")
    pct_updated = compute_percentages(conn)
    print(f"  {pct_updated:,} counties with percentages")

    print(f"\nDone. Counties processed: {total_counties:,}, updated: {total_updated:,}, unmatched: {total_skipped:,}")

    show_status(conn)
    conn.close()


if __name__ == '__main__':
    main()
