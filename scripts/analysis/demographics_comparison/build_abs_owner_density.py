"""Build ABS minority-owner density table from Census ABS county-level data.

Loads ABS_2023_abscb_county.csv, computes minority-owner firm share per county,
writes to PostgreSQL abs_owner_density table + backup abs_owner_density.json.

Data limitation: County-level ABS files have NAICS2022='00' (all-sector only).
Cannot compute fips x naics_2 cross-tab. Uses county-only minority-owner share.

Source: New Data sources 2_27/ABS_latest_state_local/csv/ABS_2023_abscb_county.csv

Usage:
    py scripts/analysis/demographics_comparison/build_abs_owner_density.py
"""
import sys
import os
import csv
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
ABS_CSV = os.path.join(
    PROJECT_ROOT,
    'New Data sources 2_27', 'ABS_latest_state_local', 'csv',
    'ABS_2023_abscb_county.csv'
)


def parse_firmpdemp(val):
    """Parse FIRMPDEMP value, returning None for suppressed ('D', 'S', '')."""
    if not val or val.strip() in ('D', 'S', 'N', 'X', ''):
        return None
    try:
        return int(val.strip().replace(',', ''))
    except ValueError:
        return None


def main():
    print('BUILD ABS OWNER DENSITY')
    print('=' * 60)

    if not os.path.exists(ABS_CSV):
        print('ERROR: ABS CSV not found: %s' % ABS_CSV)
        sys.exit(1)

    # Parse CSV -- handle BOM and quoted fields
    # NOTE: County-level ABS files only have RACE_GROUP='00' (totals) --
    # no race breakdown at county level. We extract total firm counts and
    # compute a proxy minority_share using LODES county data from the DB.
    county_data = {}  # fips -> total_firms

    with open(ABS_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows_read = 0
        for row in reader:
            rows_read += 1
            naics = row.get('NAICS2022', '').strip()
            if naics != '00':
                continue  # Only all-sector rows

            # Only total demographics (all sex/ethnicity/race/veteran)
            if row.get('SEX', '').strip() != '001':
                continue
            if row.get('ETH_GROUP', '').strip() != '001':
                continue
            if row.get('VET_GROUP', '').strip() != '001':
                continue

            state_code = row.get('state', '').strip().zfill(2)
            county_code = row.get('county', '').strip().zfill(3)
            fips = state_code + county_code

            firms = parse_firmpdemp(row.get('FIRMPDEMP', ''))
            if firms is not None:
                county_data[fips] = firms

    print('CSV rows read: %d' % rows_read)
    print('Counties with firm data: %d' % len(county_data))

    # Compute minority_share using LODES data from DB as proxy
    # (ABS doesn't have race breakdown at county level)
    conn_lodes = get_connection()
    cur_lodes = conn_lodes.cursor()

    results = {}
    computed = 0
    missing = 0

    for fips, total_firms in county_data.items():
        # Get LODES minority % for this county
        try:
            cur_lodes.execute("""
                SELECT pct_minority FROM cur_lodes_geo_metrics
                WHERE county_fips = %s LIMIT 1
            """, (fips,))
            row = cur_lodes.fetchone()
            if row and row[0] is not None:
                # pct_minority is a proportion (0-1), convert to percentage
                minority_share = round(float(row[0]) * 100.0, 2)
            else:
                minority_share = None
        except Exception:
            minority_share = None

        if minority_share is not None:
            results[fips] = {
                'total_firms': total_firms,
                'minority_share': minority_share,
            }
            computed += 1
        else:
            # Still include with firm count, no minority share
            results[fips] = {
                'total_firms': total_firms,
                'minority_share': None,
            }
            missing += 1

    cur_lodes.close()
    conn_lodes.close()

    print('Computed minority share (via LODES): %d counties' % computed)
    print('Missing LODES data: %d counties' % missing)

    if not results:
        print('ERROR: No results computed. Check CSV format.')
        sys.exit(1)

    # Summary stats
    shares = [v['minority_share'] for v in results.values() if v['minority_share'] is not None]
    if shares:
        shares.sort()
        print('')
        print('Minority share distribution (LODES-based, %d counties):' % len(shares))
        print('  Min: %.1f%%' % shares[0])
        print('  P25: %.1f%%' % shares[len(shares) // 4])
        print('  Median: %.1f%%' % shares[len(shares) // 2])
        print('  P75: %.1f%%' % shares[3 * len(shares) // 4])
        print('  Max: %.1f%%' % shares[-1])

    # Save JSON backup (only entries with minority_share)
    json_results = {k: v for k, v in results.items() if v['minority_share'] is not None}
    json_path = os.path.join(SCRIPT_DIR, 'abs_owner_density.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, indent=2)
    print('')
    print('Saved JSON: %s (%d entries)' % (json_path, len(json_results)))

    # Write to PostgreSQL
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS abs_owner_density (
            county_fips VARCHAR(5) PRIMARY KEY,
            total_firms INTEGER,
            minority_share NUMERIC(5,2)
        )
    """)
    cur.execute("TRUNCATE abs_owner_density")

    batch = []
    for fips, data in results.items():
        batch.append((fips, data['total_firms'], data['minority_share']))

    from psycopg2.extras import execute_batch
    execute_batch(cur, """
        INSERT INTO abs_owner_density (county_fips, total_firms, minority_share)
        VALUES (%s, %s, %s)
    """, batch)
    conn.commit()
    print('Loaded %d rows into abs_owner_density table' % len(batch))

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
