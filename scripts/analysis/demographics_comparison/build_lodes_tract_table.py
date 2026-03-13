"""One-time ETL: create cur_lodes_tract_metrics from raw LODES WAC CSV files.

Reads *_wac_S000_JT00_2022.csv.gz files from LODES_bulk_2022 directory,
aggregates block-level data (w_geocode 15-digit) to tract level (w_geocode[:11]),
and loads into PostgreSQL.

Usage:
    py scripts/analysis/demographics_comparison/build_lodes_tract_table.py
"""
import sys
import os
import csv
import gzip
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LODES_DIR = os.path.join(PROJECT_ROOT, 'New Data sources 2_27', 'LODES_bulk_2022')

# Columns we need from WAC S000 files
# w_geocode, C000 (total), CR01-CR05,CR07 (race), CT01-CT02 (hisp), CS01-CS02 (gender)
DEMO_COLS = ['C000', 'CR01', 'CR02', 'CR03', 'CR04', 'CR05', 'CR07',
             'CT01', 'CT02', 'CS01', 'CS02']


def aggregate_from_csv():
    """Read all state WAC S000 files, aggregate blocks to tracts."""
    import glob
    pattern = os.path.join(LODES_DIR, '*_wac_S000_JT00_2022.csv.gz')
    files = sorted(glob.glob(pattern))

    if not files:
        print('ERROR: No WAC S000 files found in %s' % LODES_DIR)
        sys.exit(1)

    print('Found %d state WAC files' % len(files))

    # Aggregate: tract_fips -> {col: sum}
    tract_data = defaultdict(lambda: {c: 0 for c in DEMO_COLS})
    total_blocks = 0

    for i, filepath in enumerate(files):
        state_code = os.path.basename(filepath)[:2]
        if (i + 1) % 10 == 0 or i == 0:
            print('  Reading %d/%d (%s)...' % (i + 1, len(files), state_code))

        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                geocode = row.get('w_geocode', '').strip()
                if len(geocode) < 11:
                    continue
                tract_fips = geocode[:11]
                for col in DEMO_COLS:
                    try:
                        tract_data[tract_fips][col] += int(row.get(col, 0))
                    except (ValueError, TypeError):
                        pass
                total_blocks += 1

    print('  Read %d blocks, aggregated to %d tracts' % (total_blocks, len(tract_data)))
    return tract_data


def load_to_db(tract_data):
    """Create table and bulk insert tract-level data."""
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # Drop if exists
    print('Dropping existing cur_lodes_tract_metrics (if any)...')
    cur.execute("DROP TABLE IF EXISTS cur_lodes_tract_metrics")

    # Create table
    print('Creating cur_lodes_tract_metrics...')
    cur.execute("""
        CREATE TABLE cur_lodes_tract_metrics (
            state_fips VARCHAR(2),
            county_fips VARCHAR(5),
            tract_fips VARCHAR(11),
            total_jobs INTEGER,
            jobs_white INTEGER,
            jobs_black INTEGER,
            jobs_native INTEGER,
            jobs_asian INTEGER,
            jobs_pacific INTEGER,
            jobs_two_plus_races INTEGER,
            jobs_not_hispanic INTEGER,
            jobs_hispanic INTEGER,
            jobs_male INTEGER,
            jobs_female INTEGER
        )
    """)

    # Bulk insert
    print('Inserting %d tract rows...' % len(tract_data))
    insert_sql = """
        INSERT INTO cur_lodes_tract_metrics
        (state_fips, county_fips, tract_fips, total_jobs,
         jobs_white, jobs_black, jobs_native, jobs_asian, jobs_pacific,
         jobs_two_plus_races, jobs_not_hispanic, jobs_hispanic,
         jobs_male, jobs_female)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    batch = []
    inserted = 0
    for tract_fips, cols in tract_data.items():
        total = cols['C000']
        if total <= 0:
            continue
        batch.append((
            tract_fips[:2],       # state_fips
            tract_fips[:5],       # county_fips
            tract_fips,           # tract_fips
            total,                # total_jobs
            cols['CR01'],         # jobs_white
            cols['CR02'],         # jobs_black
            cols['CR03'],         # jobs_native
            cols['CR04'],         # jobs_asian
            cols['CR05'],         # jobs_pacific
            cols['CR07'],         # jobs_two_plus_races
            cols['CT01'],         # jobs_not_hispanic
            cols['CT02'],         # jobs_hispanic
            cols['CS01'],         # jobs_male
            cols['CS02'],         # jobs_female
        ))
        if len(batch) >= 5000:
            cur.executemany(insert_sql, batch)
            inserted += len(batch)
            batch = []

    if batch:
        cur.executemany(insert_sql, batch)
        inserted += len(batch)

    print('  Inserted %d rows' % inserted)

    # Add indexes
    print('Adding indexes...')
    cur.execute("CREATE INDEX idx_lodes_tract_tract ON cur_lodes_tract_metrics (tract_fips)")
    cur.execute("CREATE INDEX idx_lodes_tract_county ON cur_lodes_tract_metrics (county_fips)")

    # Verify
    cur.execute("SELECT COUNT(*) FROM cur_lodes_tract_metrics")
    count = cur.fetchone()[0]
    print('  Final table: %d rows' % count)

    conn.close()


def main():
    t0 = time.time()
    tract_data = aggregate_from_csv()
    load_to_db(tract_data)
    print('Done in %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
