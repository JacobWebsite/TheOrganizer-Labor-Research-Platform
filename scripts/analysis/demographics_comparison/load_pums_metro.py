"""One-time ETL: aggregate PUMS ACS microdata into metro x industry demographics table.

Reads acs_occ_demo_profiles.csv (34M rows), aggregates to ~5K-15K metro x 2-digit-NAICS
profiles, and loads into pums_metro_demographics table.

Usage:
    py scripts/analysis/demographics_comparison/load_pums_metro.py
"""
import sys
import os
import csv
import re
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

# Project root for finding the CSV
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
PUMS_CSV = os.path.join(PROJECT_ROOT, 'data', 'raw', 'ipums_acs', 'acs_occ_demo_profiles.csv')

# IPUMS race code mapping
# 1=White, 2=Black, 3=AIAN, 4=Asian, 5=Asian(Other), 6-9=Two+/Other
RACE_MAP = {
    '1': 'white',
    '2': 'black',
    '3': 'aian',
    '4': 'asian',
    '5': 'asian',  # Other Asian / Pacific Islander -> Asian
    '6': 'two_plus',
    '7': 'two_plus',
    '8': 'two_plus',
    '9': 'two_plus',
}

# Min respondents for inclusion
MIN_RESPONDENTS = 30


def strip_naics_letters(indnaics):
    """Strip trailing letters from IPUMS INDNAICS code and take first 2 digits.

    Examples: '722Z' -> '72', '2211P' -> '22', '311' -> '31'
    """
    if not indnaics:
        return None
    # Strip trailing non-digit characters
    cleaned = re.sub(r'[^0-9]', '', indnaics)
    if len(cleaned) < 2:
        return None
    return cleaned[:2]


def process_csv():
    """Read PUMS CSV in chunks and aggregate to metro x industry profiles."""
    print('Reading PUMS CSV: %s' % PUMS_CSV)
    if not os.path.exists(PUMS_CSV):
        print('ERROR: PUMS CSV not found at %s' % PUMS_CSV)
        sys.exit(1)

    # Accumulators: (met2013, naics_2digit) -> counts
    agg = defaultdict(lambda: {
        'n_respondents': 0,
        'total_weighted': 0.0,
        'race_white': 0.0,
        'race_black': 0.0,
        'race_asian': 0.0,
        'race_aian': 0.0,
        'race_two_plus': 0.0,
        'hispanic': 0.0,
        'not_hispanic': 0.0,
        'male': 0.0,
        'female': 0.0,
    })

    t0 = time.time()
    row_count = 0
    kept_count = 0

    with open(PUMS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            if row_count % 5000000 == 0:
                elapsed = time.time() - t0
                print('  ...processed %dM rows (%.0fs, %d kept)' % (
                    row_count // 1000000, elapsed, kept_count))

            # Filter: private wage workers only
            classwkr = row.get('classwkr', '').strip()
            if classwkr != '2':
                continue

            indnaics = row.get('indnaics', '').strip()
            if indnaics == '0' or not indnaics:
                continue

            met2013 = row.get('met2013', '').strip()
            if met2013 in ('00000', '0', ''):
                continue

            # Parse weight
            weight_str = row.get('weighted_count', '0').strip()
            try:
                weight = float(weight_str)
            except ValueError:
                continue
            if weight <= 0:
                continue

            # Map NAICS
            naics_2d = strip_naics_letters(indnaics)
            if not naics_2d:
                continue

            # Map demographics
            race_code = row.get('race', '').strip()
            hispan_code = row.get('hispan', '').strip()
            sex_code = row.get('sex', '').strip()

            race_cat = RACE_MAP.get(race_code, None)
            is_hispanic = hispan_code in ('1', '2', '3', '4')
            is_female = sex_code == '2'

            key = (met2013, naics_2d)
            rec = agg[key]
            rec['n_respondents'] += 1
            rec['total_weighted'] += weight

            # Race (only for non-Hispanic to match EEO-1 convention)
            if not is_hispanic and race_cat:
                race_key = 'race_' + race_cat
                rec[race_key] += weight

            # Hispanic
            if is_hispanic:
                rec['hispanic'] += weight
            else:
                rec['not_hispanic'] += weight

            # Sex
            if is_female:
                rec['female'] += weight
            else:
                rec['male'] += weight

            kept_count += 1

    elapsed = time.time() - t0
    print('Read %d rows in %.0fs (%d kept, %d metro-industry groups)' % (
        row_count, elapsed, kept_count, len(agg)))
    return agg


def compute_percentages(agg):
    """Convert weighted counts to percentages."""
    results = []
    for (met2013, naics_2d), rec in agg.items():
        if rec['n_respondents'] < MIN_RESPONDENTS:
            continue

        # Race percentages (non-Hispanic race total)
        race_total = (rec['race_white'] + rec['race_black'] + rec['race_asian'] +
                      rec['race_aian'] + rec['race_two_plus'])

        if race_total > 0:
            race_white = round(100.0 * rec['race_white'] / race_total, 2)
            race_black = round(100.0 * rec['race_black'] / race_total, 2)
            race_asian = round(100.0 * rec['race_asian'] / race_total, 2)
            race_aian = round(100.0 * rec['race_aian'] / race_total, 2)
            race_two_plus = round(100.0 * rec['race_two_plus'] / race_total, 2)
        else:
            race_white = race_black = race_asian = race_aian = race_two_plus = 0.0

        # NHOPI: IPUMS doesn't separate NHOPI from Asian/Two+
        # Set to 0 (consistent with plan)
        race_nhopi = 0.0

        # Hispanic percentage
        hisp_total = rec['hispanic'] + rec['not_hispanic']
        hispanic_pct = round(100.0 * rec['hispanic'] / hisp_total, 2) if hisp_total > 0 else 0.0

        # Sex percentage
        sex_total = rec['male'] + rec['female']
        sex_female = round(100.0 * rec['female'] / sex_total, 2) if sex_total > 0 else 0.0

        results.append({
            'met2013': met2013,
            'naics_2digit': naics_2d,
            'race_white': race_white,
            'race_black': race_black,
            'race_asian': race_asian,
            'race_aian': race_aian,
            'race_nhopi': race_nhopi,
            'race_two_plus': race_two_plus,
            'hispanic_pct': hispanic_pct,
            'sex_female': sex_female,
            'n_respondents': rec['n_respondents'],
            'total_weighted': round(rec['total_weighted'], 1),
        })

    print('Computed percentages for %d metro-industry groups (>=%d respondents)' % (
        len(results), MIN_RESPONDENTS))
    return results


def load_to_db(results):
    """Create table and insert results."""
    conn = get_connection()
    cur = conn.cursor()

    # Create table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pums_metro_demographics (
            met2013 VARCHAR(10),
            naics_2digit VARCHAR(4),
            race_white FLOAT,
            race_black FLOAT,
            race_asian FLOAT,
            race_aian FLOAT,
            race_nhopi FLOAT,
            race_two_plus FLOAT,
            hispanic_pct FLOAT,
            sex_female FLOAT,
            n_respondents INTEGER,
            total_weighted FLOAT,
            PRIMARY KEY (met2013, naics_2digit)
        )
    """)
    conn.commit()

    # Clear existing data
    cur.execute("DELETE FROM pums_metro_demographics")
    conn.commit()

    # Insert in batches
    insert_sql = """
        INSERT INTO pums_metro_demographics
        (met2013, naics_2digit, race_white, race_black, race_asian,
         race_aian, race_nhopi, race_two_plus, hispanic_pct, sex_female,
         n_respondents, total_weighted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    batch_size = 1000
    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]
        rows = [(
            r['met2013'], r['naics_2digit'],
            r['race_white'], r['race_black'], r['race_asian'],
            r['race_aian'], r['race_nhopi'], r['race_two_plus'],
            r['hispanic_pct'], r['sex_female'],
            r['n_respondents'], r['total_weighted'],
        ) for r in batch]
        cur.executemany(insert_sql, rows)
        conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM pums_metro_demographics")
    count = cur.fetchone()[0]
    print('Loaded %d rows into pums_metro_demographics' % count)

    # Spot check
    cur.execute("""
        SELECT met2013, naics_2digit, race_white, race_black, race_asian,
               hispanic_pct, sex_female, n_respondents
        FROM pums_metro_demographics
        ORDER BY n_respondents DESC LIMIT 5
    """)
    print('')
    print('Top 5 by respondent count:')
    for row in cur.fetchall():
        print('  met=%s naics=%s  W=%.1f B=%.1f A=%.1f  H=%.1f  F=%.1f  n=%d' % (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]))

    conn.close()


def main():
    t0 = time.time()
    print('PUMS Metro Demographics ETL')
    print('=' * 60)

    # Step 1: Read and aggregate CSV
    agg = process_csv()

    # Step 2: Compute percentages
    results = compute_percentages(agg)

    # Step 3: Load to database
    load_to_db(results)

    print('')
    print('Done in %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
