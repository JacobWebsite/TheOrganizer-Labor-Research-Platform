"""One-time script: find per-NAICS-group optimal ACS/LODES weights for M1c and M5c.

Uses 5-fold cross-validation on 400 training companies (selected_400.json).
Produces two weight dicts:
  - OPTIMAL_WEIGHTS_V3_BY_GROUP: keyed by NAICS group (18 named + 'Other')
  - OPTIMAL_WEIGHTS_V3_BY_CATEGORY: keyed by M5 category (local_labor, occupation,
    manufacturing, default)

Key differences from compute_optimal_weights.py:
  1. Uses selected_400.json (not selected_200.json)
  2. 5-fold cross-validation (not single-set optimization)
  3. Weight search range [0.35, 0.75] (not [0.30, 0.90])
  4. Groups with < 15 companies get global cross-validated optimum
  5. Also computes per-M5-category weights

Usage:
    py scripts/analysis/demographics_comparison/compute_optimal_weights_v3.py

Output: prints two dict literals for copy-paste into methodologies_v3.py.
"""
import sys
import os
import json
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

# Weight search range: 0.35 to 0.75 in 0.05 steps
WEIGHT_CANDIDATES = [round(0.35 + i * 0.05, 2) for i in range(9)]  # 0.35..0.75

# M5 category definitions (from config.py INDUSTRY_WEIGHTS)
M5_CATEGORIES = {
    'local_labor': ['11', '23', '311', '312', '722'],
    'occupation': ['52', '54', '62'],
    'manufacturing': ['31', '32', '33'],
}

# Minimum group size for per-group optimization
MIN_GROUP_SIZE = 15


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


def classify_m5_category(naics):
    """Classify NAICS into M5 weight category."""
    for cat, prefixes in M5_CATEGORIES.items():
        for prefix in sorted(prefixes, key=len, reverse=True):
            if naics.startswith(prefix):
                return cat
    return 'default'


def five_fold_cv_optimal_weight(entries, weight_candidates):
    """Find optimal ACS weight via 5-fold cross-validation.

    entries: list of (acs_race, lodes_race, truth_race) tuples
    weight_candidates: list of float weights to try

    Returns (best_weight, best_cv_mae)
    """
    random.seed(42)
    indices = list(range(len(entries)))
    random.shuffle(indices)

    # Create 5 folds
    folds = [[] for _ in range(5)]
    for i, idx in enumerate(indices):
        folds[i % 5].append(idx)

    best_w = 0.60
    best_cv_mae = float('inf')

    for acs_w in weight_candidates:
        fold_maes = []
        for fold_idx in range(5):
            # Validation fold
            val_indices = folds[fold_idx]
            val_maes = []
            for idx in val_indices:
                acs_race, lodes_race, truth_race = entries[idx]
                blended = blend_race(acs_race, lodes_race, acs_w)
                if blended and truth_race:
                    m = compute_mae(blended, truth_race)
                    if m is not None:
                        val_maes.append(m)
            if val_maes:
                fold_maes.append(sum(val_maes) / len(val_maes))

        if fold_maes:
            avg_cv_mae = sum(fold_maes) / len(fold_maes)
            if avg_cv_mae < best_cv_mae:
                best_cv_mae = avg_cv_mae
                best_w = acs_w

    return best_w, best_cv_mae


def main():
    # Load companies
    if not os.path.exists(SELECTED_FILE):
        print('ERROR: %s not found.' % SELECTED_FILE)
        print('Run select_400.py first to generate the training set.')
        sys.exit(1)
    with open(SELECTED_FILE, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    print('Loaded %d companies from selected_400.json' % len(companies))

    # Load EEO-1
    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Pre-fetch ACS and LODES race for each company
    # Group by NAICS group and by M5 category
    naics_groups = defaultdict(list)   # group_name -> [(acs_race, lodes_race, truth_race)]
    m5_groups = defaultdict(list)      # m5_category -> [(acs_race, lodes_race, truth_race)]
    all_entries = []                   # flat list for global optimum

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

        entry = (acs_race, lodes_race, truth['race'])

        group = classify_naics_group(naics)
        naics_groups[group].append(entry)

        m5_cat = classify_m5_category(naics)
        m5_groups[m5_cat].append(entry)

        all_entries.append(entry)

    print('Successfully loaded %d companies (%d skipped)' % (len(all_entries), skipped))
    print('')

    # =========================================================================
    # STEP 1: Global cross-validated optimum (all companies)
    # =========================================================================
    print('Computing global cross-validated optimum...')
    global_best_w, global_best_mae = five_fold_cv_optimal_weight(
        all_entries, WEIGHT_CANDIDATES
    )
    print('  Global optimum: ACS_w=%.2f, LODES_w=%.2f, CV MAE=%.2f' % (
        global_best_w, round(1.0 - global_best_w, 2), global_best_mae))
    print('')

    # =========================================================================
    # STEP 2: Per-NAICS-group weights (5-fold CV)
    # =========================================================================
    print('OPTIMAL WEIGHTS BY NAICS GROUP (5-fold CV)')
    print('=' * 90)
    print('%-45s | %3s | %6s | %6s | %8s | %s' % (
        'Group', 'N', 'ACS_w', 'LODES_w', 'CV MAE', 'Note'))
    print('-' * 90)

    optimal_by_group = {}
    for group in sorted(naics_groups.keys()):
        entries = naics_groups[group]
        n = len(entries)

        if n < MIN_GROUP_SIZE:
            # Too few companies -- use global cross-validated optimum
            acs_w = global_best_w
            lodes_w = round(1.0 - acs_w, 2)
            optimal_by_group[group] = (acs_w, lodes_w)
            print('%-45s | %3d | %6.2f | %6.2f | %8s | global (N<%d)' % (
                group[:45], n, acs_w, lodes_w, '--', MIN_GROUP_SIZE))
            continue

        best_w, best_mae = five_fold_cv_optimal_weight(entries, WEIGHT_CANDIDATES)
        lodes_w = round(1.0 - best_w, 2)
        optimal_by_group[group] = (best_w, lodes_w)
        print('%-45s | %3d | %6.2f | %6.2f | %8.2f | CV' % (
            group[:45], n, best_w, lodes_w, best_mae))

    # =========================================================================
    # STEP 3: Per-M5-category weights (5-fold CV)
    # =========================================================================
    print('')
    print('OPTIMAL WEIGHTS BY M5 CATEGORY (5-fold CV)')
    print('=' * 90)
    print('%-20s | %3s | %6s | %6s | %8s | %s' % (
        'Category', 'N', 'ACS_w', 'LODES_w', 'CV MAE', 'Note'))
    print('-' * 90)

    optimal_by_category = {}
    for cat in ['local_labor', 'occupation', 'manufacturing', 'default']:
        entries = m5_groups.get(cat, [])
        n = len(entries)

        if n < MIN_GROUP_SIZE:
            acs_w = global_best_w
            lodes_w = round(1.0 - acs_w, 2)
            optimal_by_category[cat] = (acs_w, lodes_w)
            print('%-20s | %3d | %6.2f | %6.2f | %8s | global (N<%d)' % (
                cat, n, acs_w, lodes_w, '--', MIN_GROUP_SIZE))
            continue

        best_w, best_mae = five_fold_cv_optimal_weight(entries, WEIGHT_CANDIDATES)
        lodes_w = round(1.0 - best_w, 2)
        optimal_by_category[cat] = (best_w, lodes_w)
        print('%-20s | %3d | %6.2f | %6.2f | %8.2f | CV' % (
            cat, n, best_w, lodes_w, best_mae))

    # =========================================================================
    # STEP 4: Print dict literals for copy-paste into methodologies_v3.py
    # =========================================================================
    print('')
    print('')
    print('# ' + '=' * 78)
    print('# Copy-paste the following into methodologies_v3.py')
    print('# ' + '=' * 78)
    print('')
    print('# Per-NAICS-group weights (M1c): 5-fold CV on 400 training companies')
    print('# Groups with < %d companies use global optimum (ACS_w=%.2f)' % (
        MIN_GROUP_SIZE, global_best_w))
    print('OPTIMAL_WEIGHTS_V3_BY_GROUP = {')
    for group in sorted(optimal_by_group.keys()):
        acs_w, lodes_w = optimal_by_group[group]
        print("    '%s': (%.2f, %.2f)," % (group, acs_w, lodes_w))
    print('}')

    print('')
    print('# Per-M5-category weights (M5c): 5-fold CV on 400 training companies')
    print('OPTIMAL_WEIGHTS_V3_BY_CATEGORY = {')
    for cat in ['local_labor', 'occupation', 'manufacturing', 'default']:
        acs_w, lodes_w = optimal_by_category[cat]
        print("    '%s': (%.2f, %.2f)," % (cat, acs_w, lodes_w))
    print('}')

    print('')
    print('# Global cross-validated optimum: ACS_w=%.2f, CV MAE=%.2f' % (
        global_best_w, global_best_mae))

    conn.close()
    print('')
    print('Done.')


if __name__ == '__main__':
    main()
