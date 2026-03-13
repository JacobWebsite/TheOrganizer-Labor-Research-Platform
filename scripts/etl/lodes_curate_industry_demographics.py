"""
Curate LODES WAC industry-weighted demographics into lodes_county_industry_demographics.

For each county x industry (CNS01-CNS20), computes industry-weighted demographic
breakdowns.  The WAC file provides demographics for ALL workers in a census block,
not per-industry.  To approximate industry-specific demographics we weight each
block's demographic counts by the fraction of the county's industry employment
located in that block:

    weight_block = CNS_industry_block / sum(CNS_industry across county blocks)
    weighted_demographic = sum(demographic_count * weight_block)

This produces estimates like "what share of Manufacturing workers in county X
are Black?" based on the geographic co-location of industry jobs and demographic
composition within census blocks.

Output table: lodes_county_industry_demographics
    (county_fips, cns_code) PRIMARY KEY
    total_industry_jobs  -- raw sum of CNS column across county
    jobs_white ... jobs_female  -- industry-weighted demographic counts (NUMERIC)

Usage:
    py scripts/etl/lodes_curate_industry_demographics.py
    py scripts/etl/lodes_curate_industry_demographics.py --source-dir "path/to/wac/files"
    py scripts/etl/lodes_curate_industry_demographics.py --status
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

# The 20 NAICS-based industry columns in WAC files
CNS_COLS = [f'CNS{i:02d}' for i in range(1, 21)]

# Demographic columns we want to weight by industry geography
DEMO_COLS = {
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
}

CREATE_TABLE_SQL = """
DROP TABLE IF EXISTS lodes_county_industry_demographics;

CREATE TABLE lodes_county_industry_demographics (
    county_fips VARCHAR(5),
    cns_code VARCHAR(5),
    total_industry_jobs INTEGER,
    jobs_white NUMERIC,
    jobs_black NUMERIC,
    jobs_native NUMERIC,
    jobs_asian NUMERIC,
    jobs_pacific NUMERIC,
    jobs_two_plus_races NUMERIC,
    jobs_not_hispanic NUMERIC,
    jobs_hispanic NUMERIC,
    jobs_male NUMERIC,
    jobs_female NUMERIC,
    PRIMARY KEY (county_fips, cns_code)
);
"""


def create_table(conn):
    """Drop and recreate the lodes_county_industry_demographics table."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    print("  Table lodes_county_industry_demographics created.")


def process_wac_file(gz_path):
    """Stream a single WAC .gz file and collect block-level data for weighting.

    Returns two structures:
      industry_totals: dict[(county_fips, cns_col)] -> int
          Total employment in that industry across all blocks in the county.
      block_records: list of dicts, each with:
          county_fips, {cns_col: int}, {demo_wac_col: int}

    We accumulate block records in memory (one state at a time) so we can
    compute weights in a second pass.
    """
    # Phase 1: read all blocks, accumulate county-level industry totals
    # and store per-block data for the weighting pass.
    #
    # Memory: ~500K blocks per large state, each storing ~32 ints.
    # At ~300 bytes per record that is ~150 MB for CA -- acceptable.

    # county_fips -> cns_col -> total jobs
    industry_totals = defaultdict(lambda: defaultdict(int))

    # list of (county_fips, {cns_col: val}, {demo_wac_col: val})
    block_records = []

    with gzip.open(gz_path, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            geocode = row.get('w_geocode', '')
            if len(geocode) < 5:
                continue
            county_fips = geocode[:5]

            # Read CNS values for this block
            cns_vals = {}
            for cns_col in CNS_COLS:
                raw = row.get(cns_col, '0')
                try:
                    val = int(raw)
                except (ValueError, TypeError):
                    val = 0
                if val > 0:
                    cns_vals[cns_col] = val
                    industry_totals[county_fips][cns_col] += val

            # Read demographic values for this block
            demo_vals = {}
            for wac_col in DEMO_COLS:
                raw = row.get(wac_col, '0')
                try:
                    demo_vals[wac_col] = int(raw)
                except (ValueError, TypeError):
                    demo_vals[wac_col] = 0

            # Only store if this block has at least one industry with jobs
            if cns_vals:
                block_records.append((county_fips, cns_vals, demo_vals))

    return industry_totals, block_records


def compute_weighted_demographics(industry_totals, block_records):
    """Compute industry-weighted demographics for each county x industry pair.

    For each county and each CNS industry:
      weight_block = cns_block / cns_county_total
      weighted_demo[col] += demo_block[col] * weight_block

    Returns: dict[(county_fips, cns_col)] -> {
        'total_industry_jobs': int,
        'jobs_white': float, ... 'jobs_female': float
    }
    """
    # Accumulator: (county_fips, cns_col) -> {pg_col: float}
    result = defaultdict(lambda: defaultdict(float))

    for county_fips, cns_vals, demo_vals in block_records:
        for cns_col, cns_block_val in cns_vals.items():
            county_total = industry_totals[county_fips][cns_col]
            if county_total <= 0:
                continue
            weight = cns_block_val / county_total

            key = (county_fips, cns_col)
            for wac_col, pg_col in DEMO_COLS.items():
                result[key][pg_col] += demo_vals[wac_col] * weight

    # Attach total industry jobs
    final = {}
    for (county_fips, cns_col), demos in result.items():
        record = dict(demos)
        record['total_industry_jobs'] = industry_totals[county_fips][cns_col]
        final[(county_fips, cns_col)] = record

    return final


def insert_results(conn, weighted_data):
    """Batch INSERT weighted demographic data into the table.

    Uses ON CONFLICT to merge results across states that share county FIPS
    (should not happen since FIPS are state-prefixed, but safe anyway).
    """
    if not weighted_data:
        return 0

    pg_demo_cols = list(DEMO_COLS.values())
    all_cols = ['county_fips', 'cns_code', 'total_industry_jobs'] + pg_demo_cols

    insert_sql = """
        INSERT INTO lodes_county_industry_demographics
            ({cols})
        VALUES ({placeholders})
        ON CONFLICT (county_fips, cns_code) DO UPDATE SET
            total_industry_jobs = EXCLUDED.total_industry_jobs,
            {updates}
    """.format(
        cols=', '.join(all_cols),
        placeholders=', '.join(['%s'] * len(all_cols)),
        updates=', '.join(f'{c} = EXCLUDED.{c}' for c in pg_demo_cols)
    )

    rows = []
    for (county_fips, cns_col), record in weighted_data.items():
        row = [
            county_fips,
            cns_col,
            record['total_industry_jobs'],
        ]
        for pg_col in pg_demo_cols:
            row.append(round(record.get(pg_col, 0.0), 4))
        rows.append(row)

    inserted = 0
    batch_size = 5000
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            for r in batch:
                cur.execute(insert_sql, r)
            inserted += len(batch)
    conn.commit()
    return inserted


def show_status(conn):
    """Show current table contents summary."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'lodes_county_industry_demographics'
            ) AS e
        """)
        if not cur.fetchone()[0]:
            print("Table lodes_county_industry_demographics does not exist.")
            return

        cur.execute("SELECT COUNT(*) FROM lodes_county_industry_demographics")
        total = cur.fetchone()[0]
        print(f"lodes_county_industry_demographics: {total:,} rows")

        if total == 0:
            return

        cur.execute("""
            SELECT COUNT(DISTINCT county_fips) FROM lodes_county_industry_demographics
        """)
        counties = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(DISTINCT cns_code) FROM lodes_county_industry_demographics
        """)
        industries = cur.fetchone()[0]

        print(f"  Distinct counties: {counties:,}")
        print(f"  Distinct CNS codes: {industries}")

        cur.execute("""
            SELECT cns_code,
                   COUNT(*) AS counties,
                   SUM(total_industry_jobs) AS total_jobs,
                   ROUND(AVG(CASE WHEN total_industry_jobs > 0
                       THEN jobs_black / total_industry_jobs * 100 END), 1) AS avg_pct_black,
                   ROUND(AVG(CASE WHEN total_industry_jobs > 0
                       THEN jobs_hispanic / total_industry_jobs * 100 END), 1) AS avg_pct_hispanic,
                   ROUND(AVG(CASE WHEN total_industry_jobs > 0
                       THEN jobs_female / total_industry_jobs * 100 END), 1) AS avg_pct_female
            FROM lodes_county_industry_demographics
            WHERE total_industry_jobs > 0
            GROUP BY cns_code
            ORDER BY cns_code
        """)
        print(f"\n  {'CNS':<7} {'Counties':>8} {'Total Jobs':>12} {'%Black':>7} {'%Hisp':>7} {'%Female':>8}")
        print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*7} {'-'*7} {'-'*8}")
        for row in cur.fetchall():
            cns, cnt, jobs, pct_b, pct_h, pct_f = row
            pct_b_s = f"{float(pct_b):.1f}" if pct_b is not None else "N/A"
            pct_h_s = f"{float(pct_h):.1f}" if pct_h is not None else "N/A"
            pct_f_s = f"{float(pct_f):.1f}" if pct_f is not None else "N/A"
            print(f"  {cns:<7} {cnt:>8,} {int(jobs):>12,} {pct_b_s:>7} {pct_h_s:>7} {pct_f_s:>8}")


def main():
    parser = argparse.ArgumentParser(
        description='Curate LODES WAC industry-weighted demographics by county'
    )
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

    # Step 1: Create table
    create_table(conn)

    # Step 2: Process each state file
    total_rows = 0
    total_counties = set()

    for gz_path in wac_files:
        state_abbr = gz_path.name[:2].upper()
        print(f"  Processing {state_abbr}...", end='', flush=True)

        # Phase 1: read blocks and accumulate industry totals
        industry_totals, block_records = process_wac_file(gz_path)

        # Phase 2: compute weighted demographics
        weighted_data = compute_weighted_demographics(industry_totals, block_records)

        # Phase 3: insert into database
        inserted = insert_results(conn, weighted_data)

        state_counties = set(k[0] for k in weighted_data.keys())
        total_counties.update(state_counties)
        total_rows += inserted

        print(f" {len(state_counties)} counties, {inserted} rows inserted, "
              f"{len(block_records):,} blocks processed")

    print(f"\nDone. Total rows: {total_rows:,}, counties: {len(total_counties):,}")

    # Show summary
    print("\n--- Summary ---")
    show_status(conn)
    conn.close()


if __name__ == '__main__':
    main()
