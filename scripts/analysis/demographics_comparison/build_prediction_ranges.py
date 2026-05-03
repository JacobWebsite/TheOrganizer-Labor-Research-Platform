"""Build prediction range lookup table from V11 K-fold cross-validation results.

Reads v11_kfold_predictions.json (14,593 companies with honest OOS predictions)
and computes P15/P85 of signed errors (pred - truth) per {naics_group, diversity_tier}
cell. Falls back to {naics_group}, {diversity_tier}, or global when cell N < 30.

Output: prediction_ranges_v11.json
  - Keys: "naics_group|diversity_tier", "naics_group|*", "*|diversity_tier", "*|*"
  - Values: {category: {"p15": float, "p85": float}, "n": int}

Usage:
    py scripts/analysis/demographics_comparison/build_prediction_ranges.py
"""
import json
import os
import sys
import numpy as np
from collections import defaultdict

MIN_CELL_N = 30

RACE_CATS = ['White', 'Black', 'Asian']
HISP_CATS = ['Hispanic']
GENDER_CATS = ['Female']
ALL_CATS = RACE_CATS + HISP_CATS + GENDER_CATS

HERE = os.path.dirname(os.path.abspath(__file__))


def load_predictions():
    path = os.path.join(HERE, 'v11_kfold_predictions.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['predictions']


def compute_signed_errors(predictions):
    """Compute signed errors (pred - truth) for each company and category.

    Returns list of dicts with keys: naics_group, diversity_tier, and
    error_{cat} for each category.
    """
    records = []
    for p in predictions:
        naics_group = p.get('naics_group', 'Other')
        diversity_tier = p.get('diversity_tier', 'unknown')

        errors = {}
        has_any = False

        # Race errors
        pred_race = p.get('pred_race')
        truth_race = p.get('truth_race')
        if pred_race and truth_race:
            for cat in RACE_CATS:
                pred_val = pred_race.get(cat)
                truth_val = truth_race.get(cat)
                if pred_val is not None and truth_val is not None:
                    errors[cat] = pred_val - truth_val
                    has_any = True

        # Hispanic errors
        pred_hisp = p.get('pred_hispanic')
        truth_hisp = p.get('truth_hispanic')
        if pred_hisp and truth_hisp:
            for cat in HISP_CATS:
                pred_val = pred_hisp.get(cat)
                truth_val = truth_hisp.get(cat)
                if pred_val is not None and truth_val is not None:
                    errors[cat] = pred_val - truth_val
                    has_any = True

        # Gender errors
        pred_gender = p.get('pred_gender')
        truth_gender = p.get('truth_gender')
        if pred_gender and truth_gender:
            for cat in GENDER_CATS:
                pred_val = pred_gender.get(cat)
                truth_val = truth_gender.get(cat)
                if pred_val is not None and truth_val is not None:
                    errors[cat] = pred_val - truth_val
                    has_any = True

        if has_any:
            records.append({
                'naics_group': naics_group,
                'diversity_tier': diversity_tier,
                'errors': errors,
            })

    return records


def compute_percentiles(error_lists):
    """Compute P15/P85 for each category from accumulated error lists.

    Returns {cat: {"p15": float, "p85": float}} and n (min count across cats).
    """
    result = {}
    min_n = float('inf')
    for cat in ALL_CATS:
        vals = error_lists.get(cat, [])
        if len(vals) >= MIN_CELL_N:
            arr = np.array(vals)
            result[cat] = {
                'p15': round(float(np.percentile(arr, 15)), 2),
                'p85': round(float(np.percentile(arr, 85)), 2),
            }
            min_n = min(min_n, len(vals))
    if min_n == float('inf'):
        min_n = 0
    return result, int(min_n)


def build_lookup(records):
    """Build hierarchical lookup table.

    Keys:
      - "naics_group|diversity_tier" (most specific)
      - "naics_group|*" (naics-only fallback)
      - "*|diversity_tier" (tier-only fallback)
      - "*|*" (global fallback)
    """
    # Accumulate errors by cell
    cells = defaultdict(lambda: defaultdict(list))

    for rec in records:
        ng = rec['naics_group']
        dt = rec['diversity_tier']
        for cat, err in rec['errors'].items():
            cells[(ng, dt)][cat].append(err)
            cells[(ng, '*')][cat].append(err)
            cells[('*', dt)][cat].append(err)
            cells[('*', '*')][cat].append(err)

    lookup = {}
    for (ng, dt), error_lists in cells.items():
        percentiles, n = compute_percentiles(error_lists)
        if percentiles:
            key = '%s|%s' % (ng, dt)
            lookup[key] = {
                'ranges': percentiles,
                'n': n,
            }

    return lookup


def main():
    print('Loading V11 K-fold predictions...')
    predictions = load_predictions()
    print('  %d companies loaded' % len(predictions))

    print('Computing signed errors...')
    records = compute_signed_errors(predictions)
    print('  %d companies with at least one error computed' % len(records))

    print('Building lookup table...')
    lookup = build_lookup(records)
    print('  %d cells in lookup table' % len(lookup))

    # Show some stats
    specific_cells = [k for k in lookup if '*' not in k]
    naics_cells = [k for k in lookup if k.endswith('|*') and not k.startswith('*')]
    tier_cells = [k for k in lookup if k.startswith('*|') and not k.endswith('|*')]
    print('  %d specific cells (naics x tier)' % len(specific_cells))
    print('  %d naics-only fallback cells' % len(naics_cells))
    print('  %d tier-only fallback cells' % len(tier_cells))
    print('  1 global fallback cell')

    # Write output
    out_path = os.path.join(HERE, 'prediction_ranges_v11.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(lookup, f, indent=2)
    print('\nWrote %s' % out_path)

    # Also copy to api/data/ for the API to load
    api_data_dir = os.path.join(HERE, '..', '..', '..', 'api', 'data')
    os.makedirs(api_data_dir, exist_ok=True)
    api_path = os.path.join(api_data_dir, 'prediction_ranges_v11.json')
    with open(api_path, 'w', encoding='utf-8') as f:
        json.dump(lookup, f, indent=2)
    print('Wrote %s' % api_path)

    # Print sample
    global_key = '*|*'
    if global_key in lookup:
        print('\nGlobal fallback ranges:')
        for cat, vals in lookup[global_key]['ranges'].items():
            print('  %s: P15=%.2f, P85=%.2f' % (cat, vals['p15'], vals['p85']))
        print('  N=%d' % lookup[global_key]['n'])


if __name__ == '__main__':
    main()
