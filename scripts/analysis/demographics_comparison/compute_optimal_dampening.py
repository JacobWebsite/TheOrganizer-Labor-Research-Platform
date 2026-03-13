"""One-time script: find per-NAICS-group optimal dampening exponents for M3c.

M3c (Variable Dampening IPF) formula:
    raw_k = ACS_k^alpha * LODES_k^(1-alpha), then normalize so sum = 100.

- alpha = 0.5 is the geometric mean (current M3b behavior)
- alpha = 1.0 is pure ACS
- alpha = 0.0 is pure LODES

Uses 5-fold cross-validation on 400 training companies to find optimal alpha
per NAICS group.  Groups with < 15 companies fall back to the global optimum.

Usage:
    py scripts/analysis/demographics_comparison/compute_optimal_dampening.py

Output: prints OPTIMAL_DAMPENING_BY_GROUP dict to copy-paste into
        methodologies_v3.py.
"""
import sys
import os
import json
import math
import random
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
SELECTED_FILE = os.path.join(SCRIPT_DIR, 'selected_400.json')
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def dampened_ipf_alpha(acs_race, lodes_race, alpha):
    """Apply dampened IPF with variable alpha.

    raw_k = ACS_k^alpha * LODES_k^(1-alpha), then normalize to sum=100.
    """
    if acs_race is None or lodes_race is None:
        return None
    raw = {}
    for k in RACE_CATS:
        a = max(acs_race.get(k, 0), 0)
        l = max(lodes_race.get(k, 0), 0)
        if a == 0 and l == 0:
            raw[k] = 0
        elif a == 0:
            raw[k] = 0
        elif l == 0:
            raw[k] = 0
        else:
            raw[k] = (a ** alpha) * (l ** (1.0 - alpha))
    total = sum(raw.values())
    if total == 0:
        return None
    return {k: round(raw[k] * 100.0 / total, 2) for k in RACE_CATS}


def five_fold_cv_optimal_alpha(entries, alpha_candidates):
    """Find optimal alpha via 5-fold cross-validation.

    entries: list of (acs_race, lodes_race, truth_race) tuples
    alpha_candidates: list of float alpha values to try

    Returns (best_alpha, best_cv_mae)
    """
    random.seed(42)
    indices = list(range(len(entries)))
    random.shuffle(indices)

    folds = [[] for _ in range(5)]
    for i, idx in enumerate(indices):
        folds[i % 5].append(idx)

    best_alpha = 0.50
    best_cv_mae = float('inf')

    for alpha in alpha_candidates:
        fold_maes = []
        for fold_idx in range(5):
            val_indices = folds[fold_idx]
            val_maes = []
            for idx in val_indices:
                acs_race, lodes_race, truth_race = entries[idx]
                result = dampened_ipf_alpha(acs_race, lodes_race, alpha)
                if result and truth_race:
                    m = compute_mae(result, truth_race)
                    if m is not None:
                        val_maes.append(m)
            if val_maes:
                fold_maes.append(sum(val_maes) / len(val_maes))

        if fold_maes:
            avg_cv_mae = sum(fold_maes) / len(fold_maes)
            if avg_cv_mae < best_cv_mae:
                best_cv_mae = avg_cv_mae
                best_alpha = alpha

    return best_alpha, best_cv_mae


def main():
    # Load companies
    if not os.path.exists(SELECTED_FILE):
        print('ERROR: %s not found.' % SELECTED_FILE)
        sys.exit(1)
    with open(SELECTED_FILE, 'r', encoding='utf-8') as f:
        companies = json.load(f)

    print('Loaded %d companies from %s' % (len(companies), os.path.basename(SELECTED_FILE)))

    # Load EEO-1
    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Pre-fetch ACS and LODES race for each company, group by NAICS group
    groups = defaultdict(list)  # group_name -> [(acs_race, lodes_race, truth_race), ...]
    all_entries = []  # flat list for global optimum
    skipped = 0

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
            skipped += 1
            continue

        # Resolve geography
        if not county_fips:
            county_fips = zip_to_county(cur, company.get('zipcode', ''))
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)

        group = classify_naics_group(naics)
        entry = (acs_race, lodes_race, truth['race'])
        groups[group].append(entry)
        all_entries.append(entry)

    print('Loaded %d entries (%d skipped)' % (len(all_entries), skipped))
    print('')

    # Alpha candidates
    alpha_candidates = [round(0.30 + i * 0.05, 2) for i in range(9)]  # 0.30 to 0.70

    # Global optimum across all companies
    print('Computing global optimum alpha...')
    global_alpha, global_mae = five_fold_cv_optimal_alpha(all_entries, alpha_candidates)
    print('Global optimum: alpha=%.2f  CV MAE=%.2f' % (global_alpha, global_mae))
    print('')

    # Per-group optimum
    print('OPTIMAL DAMPENING BY NAICS GROUP')
    print('=' * 64)
    print('%-40s | %3s | %5s | %6s' % ('Group', 'N', 'Alpha', 'CV MAE'))
    print('-' * 64)

    optimal = {}
    for group in sorted(groups.keys()):
        entries = groups[group]
        n = len(entries)

        if n < 15:
            # Too few companies -- use global optimum
            optimal[group] = global_alpha
            print('%-40s | %3d | %5.2f | %6s' % (
                group[:40], n, global_alpha, 'global'))
            continue

        best_alpha, best_mae = five_fold_cv_optimal_alpha(entries, alpha_candidates)
        optimal[group] = best_alpha
        print('%-40s | %3d | %5.2f | %6.2f' % (
            group[:40], n, best_alpha, best_mae))

    # Add global fallback for groups not seen
    print('-' * 64)
    print('%-40s | %3s | %5.2f | %6.2f' % (
        'GLOBAL (fallback)', 'all', global_alpha, global_mae))
    print('')

    # Print dict literal for copy-paste
    print('# Copy-paste this into methodologies_v3.py:')
    print('OPTIMAL_DAMPENING_BY_GROUP = {')
    for group in sorted(optimal.keys()):
        print("    '%s': %.2f," % (group, optimal[group]))
    print("    '_global': %.2f," % global_alpha)
    print('}')

    conn.close()


if __name__ == '__main__':
    main()
