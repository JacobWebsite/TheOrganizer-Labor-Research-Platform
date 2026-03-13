"""Find optimal minority threshold for M3f via 5-fold CV on selected_400.json.

M3f logic:
    If Finance/Insurance or Utilities -> M3 IPF (always)
    Else if county_minority_share > threshold -> dampened IPF (M3b)
    Else -> M3 IPF

Tests thresholds: [0.15, 0.20, 0.25, 0.30]
Picks threshold minimizing cross-validated race MAE.

Usage:
    py scripts/analysis/demographics_comparison/compute_m3f_threshold.py
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
    get_acs_race_nonhispanic_v2, get_lodes_race, get_lodes_pct_minority,
    zip_to_county,
)
from methodologies import _ipf_two_marginals, _dampened_ipf
from classifiers import classify_naics_group
from metrics import mae as compute_mae

SCRIPT_DIR = os.path.dirname(__file__)
SELECTED_FILE = os.path.join(SCRIPT_DIR, 'selected_400.json')
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def m3f_race_estimate(acs_race, lodes_race, naics_group, pct_minority, threshold):
    """Compute M3f race estimate for a given threshold."""
    if naics_group in ('Finance/Insurance (52)', 'Utilities (22)'):
        return _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    if pct_minority is not None and pct_minority > threshold:
        return _dampened_ipf(acs_race, lodes_race, RACE_CATS)
    return _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)


def five_fold_cv(entries, threshold):
    """5-fold CV for a given threshold. Returns average MAE."""
    random.seed(42)
    indices = list(range(len(entries)))
    random.shuffle(indices)

    folds = [[] for _ in range(5)]
    for i, idx in enumerate(indices):
        folds[i % 5].append(idx)

    fold_maes = []
    for fold_idx in range(5):
        val_maes = []
        for idx in folds[fold_idx]:
            acs_race, lodes_race, truth_race, naics_group, pct_min = entries[idx]
            result = m3f_race_estimate(acs_race, lodes_race, naics_group,
                                        pct_min, threshold)
            if result and truth_race:
                m = compute_mae(result, truth_race)
                if m is not None:
                    val_maes.append(m)
        if val_maes:
            fold_maes.append(sum(val_maes) / len(val_maes))

    return sum(fold_maes) / len(fold_maes) if fold_maes else float('inf')


def main():
    if not os.path.exists(SELECTED_FILE):
        print('ERROR: %s not found.' % SELECTED_FILE)
        sys.exit(1)

    with open(SELECTED_FILE, 'r', encoding='utf-8') as f:
        companies = json.load(f)

    print('Loaded %d companies from %s' % (len(companies), os.path.basename(SELECTED_FILE)))

    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Pre-fetch data
    entries = []
    skipped = 0

    for company in companies:
        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')

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

        if not county_fips:
            county_fips = zip_to_county(cur, company.get('zipcode', ''))
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)
        pct_min = get_lodes_pct_minority(cur, county_fips)
        naics_group = classify_naics_group(naics)

        entries.append((acs_race, lodes_race, truth['race'], naics_group, pct_min))

    print('Loaded %d entries (%d skipped)' % (len(entries), skipped))
    print('')

    # Test thresholds
    thresholds = [0.15, 0.20, 0.25, 0.30]

    print('M3F THRESHOLD OPTIMIZATION')
    print('=' * 50)
    print('%-12s | %8s' % ('Threshold', 'CV MAE'))
    print('-' * 50)

    best_threshold = 0.20
    best_mae = float('inf')

    for threshold in thresholds:
        cv_mae = five_fold_cv(entries, threshold)
        marker = ''
        if cv_mae < best_mae:
            best_mae = cv_mae
            best_threshold = threshold
            marker = ' <-- best'
        print('%-12.2f | %8.4f%s' % (threshold, cv_mae, marker))

    print('-' * 50)
    print('')
    print('OPTIMAL THRESHOLD: %.2f (CV MAE: %.4f)' % (best_threshold, best_mae))
    print('')

    # Count how many companies each threshold affects
    print('COMPANY ROUTING DISTRIBUTION:')
    finance_utils = sum(1 for e in entries if e[3] in ('Finance/Insurance (52)', 'Utilities (22)'))
    print('  Finance/Utilities (always M3 IPF): %d' % finance_utils)
    for threshold in thresholds:
        above = sum(1 for e in entries
                    if e[3] not in ('Finance/Insurance (52)', 'Utilities (22)')
                    and e[4] is not None and e[4] > threshold)
        below = len(entries) - finance_utils - above
        marker = ' <-- optimal' if threshold == best_threshold else ''
        print('  Threshold %.2f: %d dampened, %d IPF%s' % (
            threshold, above, below, marker))

    print('')
    print('# Update config.py with:')
    print('OPTIMAL_M3F_THRESHOLD = %.2f' % best_threshold)

    conn.close()


if __name__ == '__main__':
    main()
