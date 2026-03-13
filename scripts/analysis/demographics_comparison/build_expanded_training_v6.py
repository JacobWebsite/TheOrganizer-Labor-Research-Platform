"""Build expanded EEO-1 training set for Gate V2.

Loads all EEO-1 data, deduplicates by company code (most recent year),
filters for quality (valid NAICS, state, total >= 50), excludes the 100
permanent holdout companies, adds geographic and classification data.

Target: ~3,000-3,500 companies.
Output: expanded_training_v6.json

Usage:
    py scripts/analysis/demographics_comparison/build_expanded_training_v6.py
"""
import sys
import os
import json
import csv
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)


def classify_size_bucket(total):
    """Classify workforce size into bucket."""
    if total < 100:
        return '1-99'
    elif total < 1000:
        return '100-999'
    elif total < 10000:
        return '1000-9999'
    else:
        return '10000+'


def load_holdout_codes():
    """Load the 1000 permanent holdout company codes to exclude."""
    holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
    if not os.path.exists(holdout_path):
        print('WARNING: Holdout file not found: %s' % holdout_path)
        return set()
    with open(holdout_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Handle both list and dict-with-companies formats
    if isinstance(data, dict):
        companies = data.get('companies', [])
    else:
        companies = data
    codes = set(c['company_code'] for c in companies)
    print('Loaded %d holdout company codes to exclude' % len(codes))
    return codes


def main():
    print('BUILD EXPANDED TRAINING V6')
    print('=' * 60)

    # ------------------------------------------------------------------
    # Step 1: Load ALL EEO-1 data (objectors + nonobjectors + supplements)
    # ------------------------------------------------------------------
    print('Loading all EEO-1 files...')
    eeo1_rows = load_all_eeo1_data()
    print('Total unique EEO-1 rows: %d' % len(eeo1_rows))

    # ------------------------------------------------------------------
    # Step 2: Filter to 2019-2020 only (100% NAICS + ZIP coverage),
    # then deduplicate by company code (keep most recent year)
    # ------------------------------------------------------------------
    valid_years = {'2019', '2020'}
    recent_rows = [r for r in eeo1_rows
                   if str(r.get('YEAR', '')).strip() in valid_years]
    print('Rows in 2019-2020: %d (of %d total)' % (len(recent_rows), len(eeo1_rows)))

    by_code = defaultdict(list)
    for row in recent_rows:
        code = (row.get('COMPANY') or '').strip()
        if code:
            by_code[code].append(row)

    print('Unique company codes (2019-2020): %d' % len(by_code))

    # For each company, keep the row with the most recent year
    deduped = {}
    for code, rows in by_code.items():
        rows.sort(key=lambda r: int(float(r.get('YEAR', 0) or 0)), reverse=True)
        parsed = parse_eeo1_row(rows[0])
        if parsed:
            deduped[code] = parsed

    print('Parsed (non-zero total): %d' % len(deduped))

    # ------------------------------------------------------------------
    # Step 3: Filter -- valid NAICS (>= 4 digits), valid state, total >= 50
    # ------------------------------------------------------------------
    filtered = {}
    skip_naics = 0
    skip_state = 0
    skip_size = 0
    for code, c in deduped.items():
        naics = c.get('naics', '')
        if not naics or len(naics) < 4:
            skip_naics += 1
            continue
        state = c.get('state', '')
        if not state:
            skip_state += 1
            continue
        if c['total'] < 50:
            skip_size += 1
            continue
        filtered[code] = c

    print('After filters:')
    print('  Skipped (NAICS < 4 digits): %d' % skip_naics)
    print('  Skipped (no state):         %d' % skip_state)
    print('  Skipped (total < 50):       %d' % skip_size)
    print('  Remaining:                  %d' % len(filtered))

    # ------------------------------------------------------------------
    # Step 4: Exclude 100 permanent holdout + 1000 test holdout companies
    # ------------------------------------------------------------------
    holdout_codes = load_holdout_codes()

    # Also load 1000 test holdout(s)
    test_holdout_files = [
        'selected_test_holdout_1000.json',
        'selected_test_holdout_v8_1000.json',
    ]
    test_codes = set()
    for thf in test_holdout_files:
        test_holdout_path = os.path.join(SCRIPT_DIR, thf)
        if os.path.exists(test_holdout_path):
            with open(test_holdout_path, 'r', encoding='utf-8') as f:
                tdata = json.load(f)
            test_companies = tdata.get('companies', tdata)
            codes_in_file = set(c['company_code'] for c in test_companies)
            test_codes |= codes_in_file
            print('Loaded %d test holdout codes from %s' % (len(codes_in_file), thf))

    all_excluded = holdout_codes | test_codes
    excluded = 0
    for code in list(filtered.keys()):
        if code in all_excluded:
            del filtered[code]
            excluded += 1
    print('Excluded holdout + test companies: %d' % excluded)
    print('After exclusion:    %d' % len(filtered))

    # ------------------------------------------------------------------
    # Step 5: Add geographic data (county_fips, state_fips)
    # ------------------------------------------------------------------
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    geo_found = 0
    geo_missing = 0
    for code, c in list(filtered.items()):
        county_fips = zip_to_county(cur, c['zipcode'])
        if county_fips:
            c['county_fips'] = county_fips
            c['state_fips'] = county_fips[:2] if len(county_fips) >= 2 else ''
            geo_found += 1
        else:
            # Remove companies without valid geography
            del filtered[code]
            geo_missing += 1

    print('Geography resolution:')
    print('  Found county_fips:  %d' % geo_found)
    print('  Missing (removed):  %d' % geo_missing)
    print('  Final pool size:    %d' % len(filtered))

    conn.close()

    # ------------------------------------------------------------------
    # Step 6: Add classifications (naics_group, region, size)
    # ------------------------------------------------------------------
    for code, c in filtered.items():
        c['classifications'] = {
            'naics_group': classify_naics_group(c['naics']),
            'region': classify_region(c['state']),
            'size': classify_size_bucket(c['total']),
        }

    # ------------------------------------------------------------------
    # Step 7: Build output
    # ------------------------------------------------------------------
    output = []
    for code, c in sorted(filtered.items()):
        output.append({
            'company_code': c['company_code'],
            'name': c['name'],
            'naics': c['naics'],
            'state': c['state'],
            'zipcode': c['zipcode'],
            'total': c['total'],
            'year': c['year'],
            'county_fips': c['county_fips'],
            'state_fips': c['state_fips'],
            'classifications': c['classifications'],
        })

    output_path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('')
    print('Output: %s' % output_path)
    print('Total companies: %d' % len(output))

    # ------------------------------------------------------------------
    # Step 9: Print summary stats
    # ------------------------------------------------------------------
    print('')
    print('SUMMARY STATS')
    print('=' * 60)
    print('Total companies: %d' % len(output))

    # Per industry group
    print('')
    print('By NAICS Group:')
    naics_counts = defaultdict(int)
    for c in output:
        naics_counts[c['classifications']['naics_group']] += 1
    for group, count in sorted(naics_counts.items(), key=lambda x: -x[1]):
        print('  %-45s %d' % (group, count))

    # Per region
    print('')
    print('By Region:')
    region_counts = defaultdict(int)
    for c in output:
        region_counts[c['classifications']['region']] += 1
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        print('  %-20s %d' % (region, count))

    # Per size bucket
    print('')
    print('By Size:')
    size_counts = defaultdict(int)
    for c in output:
        size_counts[c['classifications']['size']] += 1
    for size, count in sorted(size_counts.items()):
        print('  %-20s %d' % (size, count))

    print('')
    print('Done.')


if __name__ == '__main__':
    main()
