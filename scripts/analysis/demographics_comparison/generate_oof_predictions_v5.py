"""Generate out-of-fold (OOF) predictions for Expert A/B/D models.

5-fold GroupKFold by naics_group. For each fold:
- Expert A: re-optimize alpha per NAICS group on training fold, predict held-out
- Expert B: no learned params, predict directly
- Expert D (= M3b): no learned params, predict directly

Output: oof_predictions_v5.csv

Usage:
    py scripts/analysis/demographics_comparison/generate_oof_predictions_v5.py
"""
import sys
import os
import json
import csv
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county
from metrics import mae
from cached_loaders_v5 import CachedLoadersV5
from cached_loaders_v2 import cached_method_3b
from cached_loaders_v5 import cached_expert_a, cached_expert_b
from methodologies_v5 import (
    smoothed_variable_dampened_ipf, NATIONAL_EEO1_PRIOR,
    NAICS_GROUP_COUNTS, _prior_smooth, apply_floor,
    SMOOTHING_FLOOR,
)
from methodologies_v3 import OPTIMAL_DAMPENING_BY_GROUP
from methodologies import OPTIMAL_WEIGHTS_BY_GROUP
from classifiers import classify_naics_group

SCRIPT_DIR = os.path.dirname(__file__)
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def load_companies():
    """Load all_companies_v4.json."""
    json_path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def assign_folds(companies, n_folds=5):
    """Assign companies to folds via GroupKFold on naics_group."""
    # Group companies by naics_group
    group_to_companies = defaultdict(list)
    for i, c in enumerate(companies):
        group = c.get('classifications', {}).get('naics_group', 'Other')
        group_to_companies[group].append(i)

    # Assign groups to folds round-robin (sorted by size for balance)
    sorted_groups = sorted(group_to_companies.keys(),
                           key=lambda g: len(group_to_companies[g]), reverse=True)
    fold_sizes = [0] * n_folds
    group_fold = {}
    for group in sorted_groups:
        # Assign to smallest fold
        min_fold = min(range(n_folds), key=lambda f: fold_sizes[f])
        group_fold[group] = min_fold
        fold_sizes[min_fold] += len(group_to_companies[group])

    # Map company index to fold
    company_folds = [0] * len(companies)
    for group, indices in group_to_companies.items():
        fold = group_fold[group]
        for idx in indices:
            company_folds[idx] = fold

    return company_folds


def optimize_alpha_for_group(cl, train_companies, eeo1_rows, naics_group, cur):
    """Grid search alpha for Expert A on training fold companies in this NAICS group."""
    best_alpha = 0.50
    best_mae = float('inf')

    group_companies = [c for c in train_companies
                       if c.get('classifications', {}).get('naics_group', 'Other') == naics_group]

    if len(group_companies) < 5:
        return OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50)

    for alpha_try in [x / 100.0 for x in range(20, 85, 5)]:
        maes = []
        for company in group_companies:
            naics4 = company.get('naics', '')[:4]
            state_fips = company.get('state_fips', '')
            county_fips = company.get('county_fips', '')
            if not county_fips:
                continue

            # Get ground truth
            truth = None
            for row in eeo1_rows:
                if row.get('COMPANY') == company['company_code']:
                    truth = parse_eeo1_row(row)
                    break
            if not truth or not truth.get('race'):
                continue

            # Run Expert A with this alpha
            race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
            lodes_race = cl.get_lodes_race(county_fips)
            acs_smooth = _prior_smooth(race_data, NATIONAL_EEO1_PRIOR)
            lodes_smooth = _prior_smooth(lodes_race, NATIONAL_EEO1_PRIOR)
            race_result = smoothed_variable_dampened_ipf(
                acs_smooth, lodes_smooth, RACE_CATS, alpha_try)

            if race_result:
                m = mae(race_result, truth['race'])
                if m is not None:
                    maes.append(m)

        if maes:
            avg_mae = sum(maes) / len(maes)
            if avg_mae < best_mae:
                best_mae = avg_mae
                best_alpha = alpha_try

    return best_alpha


def main():
    t0 = time.time()
    print('GENERATE OOF PREDICTIONS V5')
    print('=' * 60)

    companies = load_companies()
    print('Companies: %d' % len(companies))

    # Assign folds
    folds = assign_folds(companies)
    fold_counts = defaultdict(int)
    for f in folds:
        fold_counts[f] += 1
    print('Fold sizes: %s' % dict(sorted(fold_counts.items())))

    # Load EEO-1
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV5(cur)

    # Count companies per NAICS group
    for c in companies:
        group = c.get('classifications', {}).get('naics_group', 'Other')
        NAICS_GROUP_COUNTS[group] = NAICS_GROUP_COUNTS.get(group, 0) + 1

    results = []
    skipped = 0

    for fold_id in range(5):
        print('')
        print('--- Fold %d ---' % fold_id)

        # Split
        train_companies = [c for i, c in enumerate(companies) if folds[i] != fold_id]
        test_companies = [c for i, c in enumerate(companies) if folds[i] == fold_id]
        test_indices = [i for i in range(len(companies)) if folds[i] == fold_id]
        print('  Train: %d, Test: %d' % (len(train_companies), len(test_companies)))

        # Optimize alpha per NAICS group on training fold
        naics_groups = set(c.get('classifications', {}).get('naics_group', 'Other')
                          for c in train_companies)
        fold_alphas = {}
        for group in naics_groups:
            fold_alphas[group] = optimize_alpha_for_group(
                cl, train_companies, eeo1_rows, group, cur)

        print('  Optimized alphas for %d groups' % len(fold_alphas))

        # Predict on test fold
        for company in test_companies:
            company_code = company['company_code']
            naics = company.get('naics', '')
            naics4 = naics[:4]
            zipcode = company.get('zipcode', '')
            county_fips = company.get('county_fips', '')
            state_fips = company.get('state_fips', '')

            if not county_fips:
                county_fips = zip_to_county(cur, zipcode)
            if not state_fips and county_fips:
                state_fips = county_fips[:2]
            if not county_fips:
                skipped += 1
                continue

            # Ground truth
            truth = None
            for row in eeo1_rows:
                if row.get('COMPANY') == company_code:
                    truth = parse_eeo1_row(row)
                    break
            if not truth:
                skipped += 1
                continue

            group = company.get('classifications', {}).get('naics_group', 'Other')

            # Expert A with fold-optimized alpha
            alpha_opt = fold_alphas.get(group, 0.50)
            n_segment = NAICS_GROUP_COUNTS.get(group, 5)
            alpha_final = (n_segment * alpha_opt + 5 * 0.50) / (n_segment + 5)

            race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
            lodes_race = cl.get_lodes_race(county_fips)
            acs_smooth = _prior_smooth(race_data, NATIONAL_EEO1_PRIOR)
            lodes_smooth = _prior_smooth(lodes_race, NATIONAL_EEO1_PRIOR)
            expert_a_race = smoothed_variable_dampened_ipf(
                acs_smooth, lodes_smooth, RACE_CATS, alpha_final)

            # Expert B
            try:
                expert_b_result = cached_expert_b(
                    cl, naics4, state_fips, county_fips, zipcode=zipcode)
                expert_b_race = expert_b_result.get('race')
            except Exception:
                expert_b_race = None

            # Expert D (= M3b)
            try:
                expert_d_result = cached_method_3b(cl, naics4, state_fips, county_fips)
                expert_d_race = expert_d_result.get('race')
            except Exception:
                expert_d_race = None

            actual_race = truth.get('race', {})

            result_row = {
                'company_code': company_code,
                'fold': fold_id,
                'naics_group': group,
                'alpha_used': round(alpha_final, 3),
            }

            # Expert A predictions
            for cat in RACE_CATS:
                result_row['expert_a_%s' % cat] = expert_a_race.get(cat, 0) if expert_a_race else None
            # Expert B predictions
            for cat in RACE_CATS:
                result_row['expert_b_%s' % cat] = expert_b_race.get(cat, 0) if expert_b_race else None
            # Expert D predictions
            for cat in RACE_CATS:
                result_row['expert_d_%s' % cat] = expert_d_race.get(cat, 0) if expert_d_race else None
            # Actuals
            for cat in RACE_CATS:
                result_row['actual_%s' % cat] = actual_race.get(cat, 0)

            results.append(result_row)

    elapsed = time.time() - t0
    print('')
    print('Generated %d OOF predictions in %.1fs (%d skipped)' % (
        len(results), elapsed, skipped))

    # Quick summary
    expert_maes = {'A': [], 'B': [], 'D': []}
    for row in results:
        for expert, prefix in [('A', 'expert_a_'), ('B', 'expert_b_'), ('D', 'expert_d_')]:
            pred = {}
            actual = {}
            for cat in RACE_CATS:
                p = row.get('%s%s' % (prefix, cat))
                a = row.get('actual_%s' % cat)
                if p is not None and a is not None:
                    pred[cat] = p
                    actual[cat] = a
            if pred and actual:
                m = mae(pred, actual)
                if m is not None:
                    expert_maes[expert].append(m)

    print('')
    print('Expert OOF Race MAE:')
    for expert in ['A', 'B', 'D']:
        maes = expert_maes[expert]
        if maes:
            print('  Expert %s: %.3f (n=%d)' % (expert, sum(maes) / len(maes), len(maes)))

    # Write CSV
    output_path = os.path.join(SCRIPT_DIR, 'oof_predictions_v5.csv')
    if results:
        cols = list(results[0].keys())
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(results)
        print('Output: %s (%d rows)' % (output_path, len(results)))

    cl.print_stats()
    conn.close()


if __name__ == '__main__':
    main()
