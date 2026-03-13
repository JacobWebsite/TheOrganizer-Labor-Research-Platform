"""Select 1000 permanent holdout companies, stratified by naics_group x region.

These are FROZEN forever -- never used for training or tuning.
Drawn from 2019-2020 EEO-1 data (all files) with valid NAICS + ZIP.

Output: selected_permanent_holdout_1000.json

Usage:
    py scripts/analysis/demographics_comparison/select_permanent_holdout_100.py
"""
import sys
import os
import json
import random
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
sys.path.insert(0, os.path.dirname(__file__))

from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from classifiers import classify_naics_group, classify_region
from db_config import get_connection
from psycopg2.extras import RealDictCursor

SCRIPT_DIR = os.path.dirname(__file__)
TARGET = 1000
SEED = 99


def classify_size_bucket(total):
    if total < 100:
        return '1-99'
    elif total < 1000:
        return '100-999'
    elif total < 10000:
        return '1000-9999'
    else:
        return '10000+'


def main():
    print('SELECT PERMANENT HOLDOUT (1000 companies)')
    print('=' * 60)

    # Load all EEO-1 data, filter to 2019-2020
    print('Loading all EEO-1 files...')
    eeo1_rows = load_all_eeo1_data()

    valid_years = {'2019', '2020'}
    recent = [r for r in eeo1_rows if str(r.get('YEAR', '')).strip() in valid_years]
    print('Rows in 2019-2020: %d' % len(recent))

    # Deduplicate by company code (most recent year)
    by_code = defaultdict(list)
    for row in recent:
        code = (row.get('COMPANY') or '').strip()
        if code:
            by_code[code].append(row)

    # Parse and filter
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    candidates = []
    for code, rows in by_code.items():
        rows.sort(key=lambda r: int(float(r.get('YEAR', 0) or 0)), reverse=True)
        parsed = parse_eeo1_row(rows[0])
        if not parsed:
            continue
        naics = parsed.get('naics', '')
        if not naics or len(naics) < 4:
            continue
        if parsed['total'] < 50:
            continue
        zipcode = parsed.get('zipcode', '')
        county_fips = zip_to_county(cur, zipcode) if zipcode else None
        if not county_fips:
            continue
        state_fips = county_fips[:2]

        parsed['county_fips'] = county_fips
        parsed['state_fips'] = state_fips
        parsed['classifications'] = {
            'naics_group': classify_naics_group(naics),
            'region': classify_region(parsed['state']),
            'size': classify_size_bucket(parsed['total']),
        }
        candidates.append(parsed)

    conn.close()
    print('Valid candidates: %d' % len(candidates))

    # Stratify by naics_group x region
    cells = defaultdict(list)
    for c in candidates:
        key = (c['classifications']['naics_group'], c['classifications']['region'])
        cells[key].append(c)

    print('Strata: %d cells' % len(cells))

    # Proportional allocation
    total_pool = len(candidates)
    allocations = {}
    for key, companies in cells.items():
        allocations[key] = max(1, round(TARGET * len(companies) / total_pool))

    # Adjust to hit TARGET
    allocated = sum(allocations.values())
    sorted_keys = sorted(cells.keys(), key=lambda k: len(cells[k]), reverse=True)
    while allocated > TARGET:
        for key in reversed(sorted_keys):
            if allocated <= TARGET:
                break
            if allocations[key] > 1:
                allocations[key] -= 1
                allocated -= 1
    while allocated < TARGET:
        for key in sorted_keys:
            if allocated >= TARGET:
                break
            if allocations[key] < len(cells[key]):
                allocations[key] += 1
                allocated += 1

    # Sample
    random.seed(SEED)
    selected = []
    for key, count in allocations.items():
        cell_companies = cells[key]
        sampled = random.sample(cell_companies, min(count, len(cell_companies)))
        selected.extend(sampled)

    print('Selected: %d companies' % len(selected))

    # Print distribution
    print('')
    print('By NAICS Group:')
    group_counts = defaultdict(int)
    for c in selected:
        group_counts[c['classifications']['naics_group']] += 1
    for group, count in sorted(group_counts.items(), key=lambda x: -x[1]):
        print('  %-45s %d' % (group, count))

    print('')
    print('By Region:')
    region_counts = defaultdict(int)
    for c in selected:
        region_counts[c['classifications']['region']] += 1
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        print('  %-20s %d' % (region, count))

    # Build output
    output_companies = []
    for c in selected:
        output_companies.append({
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

    output = {
        'description': 'Permanent holdout (1000 companies, FROZEN, never train)',
        'seed': SEED,
        'n_companies': len(output_companies),
        'companies': output_companies,
    }

    output_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('')
    print('Output: %s' % output_path)
    print('Done.')


if __name__ == '__main__':
    main()
