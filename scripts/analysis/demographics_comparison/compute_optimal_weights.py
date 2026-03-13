"""One-time script: find per-NAICS-group optimal ACS/LODES weights for M1b.

Loads selected_200.json and EEO-1 ground truth, then for each NAICS group
tries ACS weights from 0.30 to 0.90 and picks the one with lowest avg race MAE.

Usage:
    py scripts/analysis/demographics_comparison/compute_optimal_weights.py

Output: prints OPTIMAL_WEIGHTS_BY_GROUP dict to copy-paste into methodologies.py.
"""
import sys
import os
import json
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import (
    get_acs_race_nonhispanic_v2, get_lodes_race, zip_to_county,
)
from classifiers import classify_naics_group
from metrics import mae as compute_mae

SCRIPT_DIR = os.path.dirname(__file__)
SELECTED_FILE = os.path.join(SCRIPT_DIR, 'selected_200.json')
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def blend_race(acs_race, lodes_race, acs_w):
    """Blend ACS and LODES race dicts with given ACS weight."""
    lodes_w = 1.0 - acs_w
    active = []
    if acs_race is not None:
        active.append((acs_race, acs_w))
    if lodes_race is not None:
        active.append((lodes_race, lodes_w))
    if not active:
        return None
    total_w = sum(w for _, w in active)
    if total_w == 0:
        return None
    result = {}
    for cat in RACE_CATS:
        val = sum(d.get(cat, 0) * w for d, w in active) / total_w
        result[cat] = round(val, 2)
    return result


def main():
    # Load companies
    if not os.path.exists(SELECTED_FILE):
        print('ERROR: %s not found.' % SELECTED_FILE)
        sys.exit(1)
    with open(SELECTED_FILE, 'r', encoding='utf-8') as f:
        companies = json.load(f)

    # Load EEO-1
    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Pre-fetch ACS and LODES race for each company, group by NAICS group
    groups = defaultdict(list)  # group_name -> [(acs_race, lodes_race, truth_race), ...]

    for company in companies:
        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')

        # Get ground truth
        truth = None
        for row in eeo1_rows:
            if row.get('COMPANY') == company_code and _safe_int(row.get('YEAR')) == year:
                truth = parse_eeo1_row(row)
                break
        if not truth:
            for row in eeo1_rows:
                if row.get('COMPANY') == company_code:
                    truth = parse_eeo1_row(row)
                    break
        if not truth:
            continue

        # Resolve geography
        if not county_fips:
            county_fips = zip_to_county(cur, company.get('zipcode', ''))
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            continue

        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)

        group = classify_naics_group(naics)
        groups[group].append((acs_race, lodes_race, truth['race']))

    # Find optimal weights per group
    print('')
    print('OPTIMAL WEIGHTS BY NAICS GROUP')
    print('=' * 80)
    print('%-40s | %3s | %6s | %6s | %8s' % ('Group', 'N', 'ACS_w', 'LODES_w', 'Best MAE'))
    print('-' * 80)

    weight_candidates = [round(0.30 + i * 0.05, 2) for i in range(13)]  # 0.30 to 0.90

    optimal = {}
    for group in sorted(groups.keys()):
        entries = groups[group]
        n = len(entries)

        if n < 3:
            # Too few companies, use default
            optimal[group] = (0.60, 0.40)
            print('%-40s | %3d | %6.2f | %6.2f | %8s' % (
                group[:40], n, 0.60, 0.40, 'default'))
            continue

        best_w = 0.60
        best_mae = float('inf')

        for acs_w in weight_candidates:
            maes = []
            for acs_race, lodes_race, truth_race in entries:
                blended = blend_race(acs_race, lodes_race, acs_w)
                if blended and truth_race:
                    m = compute_mae(blended, truth_race)
                    if m is not None:
                        maes.append(m)
            if maes:
                avg_mae = sum(maes) / len(maes)
                if avg_mae < best_mae:
                    best_mae = avg_mae
                    best_w = acs_w

        lodes_w = round(1.0 - best_w, 2)
        optimal[group] = (best_w, lodes_w)
        print('%-40s | %3d | %6.2f | %6.2f | %8.2f' % (
            group[:40], n, best_w, lodes_w, best_mae))

    # Print dict literal for copy-paste
    print('')
    print('# Copy-paste this into methodologies.py OPTIMAL_WEIGHTS_BY_GROUP:')
    print('OPTIMAL_WEIGHTS_BY_GROUP = {')
    for group in sorted(optimal.keys()):
        acs_w, lodes_w = optimal[group]
        print("    '%s': (%.2f, %.2f)," % (group, acs_w, lodes_w))
    print('}')

    conn.close()


if __name__ == '__main__':
    main()
