"""Select V10 sealed holdout (1,000 companies) and rebuild training set.

Creates a fresh holdout that has NEVER been touched by any optimization,
excluding companies already in the permanent holdout.

Stratified by naics_group x region (same approach as select_test_holdout_1000.py).

Outputs:
  - selected_v10_sealed_holdout_1000.json  (new sealed holdout)
  - expanded_training_v10.json             (training set minus BOTH holdouts)

Usage:
    py scripts/analysis/demographics_comparison/select_v10_holdout.py
"""
import sys
import os
import json
import random
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

SCRIPT_DIR = os.path.dirname(__file__)
TARGET = 1000
SEED = 2026031210  # today's date + "10" for V10


def main():
    print('V10 SEALED HOLDOUT SELECTION')
    print('Seed: %d' % SEED)
    print('=' * 60)

    # ---- Load full EEO-1 pool ----
    pool_path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
    with open(pool_path, 'r', encoding='utf-8') as f:
        pool = json.load(f)
    print('Full pool size: %d' % len(pool))

    # ---- Load permanent holdout ----
    perm_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
    with open(perm_path, 'r', encoding='utf-8') as f:
        perm_data = json.load(f)
    perm_companies = perm_data.get('companies', perm_data)
    perm_ids = set(c['company_code'] for c in perm_companies)
    print('Permanent holdout size: %d' % len(perm_ids))

    # ---- Exclude permanent holdout from pool ----
    eligible = [c for c in pool if c['company_code'] not in perm_ids]
    print('Eligible for V10 holdout (pool - perm): %d' % len(eligible))

    # ---- Stratified sampling by naics_group x region ----
    cells = defaultdict(list)
    for c in eligible:
        cls = c.get('classifications', {})
        key = (cls.get('naics_group', 'Other'), cls.get('region', 'Other'))
        cells[key].append(c)

    print('Strata (naics_group x region): %d cells' % len(cells))

    # Proportional allocation
    total_eligible = len(eligible)
    allocations = {}
    for key, companies in cells.items():
        allocations[key] = max(1, int(TARGET * len(companies) / total_eligible))

    # Adjust to hit exactly TARGET
    allocated = sum(allocations.values())
    if allocated < TARGET:
        sorted_keys = sorted(cells.keys(), key=lambda k: len(cells[k]), reverse=True)
        for key in sorted_keys:
            if allocated >= TARGET:
                break
            allocations[key] += 1
            allocated += 1
    elif allocated > TARGET:
        sorted_keys = sorted(cells.keys(), key=lambda k: len(cells[k]))
        for key in sorted_keys:
            if allocated <= TARGET:
                break
            if allocations[key] > 1:
                allocations[key] -= 1
                allocated -= 1

    # Sample
    random.seed(SEED)
    selected = []
    for key, count in allocations.items():
        cell_companies = cells[key]
        if count >= len(cell_companies):
            sampled = cell_companies
        else:
            sampled = random.sample(cell_companies, count)
        selected.extend(sampled)

    v10_ids = set(c['company_code'] for c in selected)

    # ---- OVERLAP CHECK ----
    overlap = v10_ids & perm_ids
    assert len(overlap) == 0, "CONTAMINATION WITH PERMANENT HOLDOUT: %d overlap" % len(overlap)
    print('')
    print('PASS: zero overlap with permanent holdout. V10 sealed holdout N=%d' % len(v10_ids))

    # ---- Distribution by NAICS Group ----
    print('')
    print('V10 Holdout by NAICS Group:')
    group_counts = defaultdict(int)
    for c in selected:
        group_counts[c['classifications']['naics_group']] += 1
    for group, count in sorted(group_counts.items(), key=lambda x: -x[1]):
        pool_count = sum(1 for c in eligible if c['classifications']['naics_group'] == group)
        print('  %-45s %3d / %5d (%.1f%%)' % (group, count, pool_count,
              100 * count / pool_count if pool_count else 0))

    print('')
    print('V10 Holdout by Region:')
    region_counts = defaultdict(int)
    for c in selected:
        region_counts[c['classifications']['region']] += 1
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        pool_count = sum(1 for c in eligible if c['classifications']['region'] == region)
        print('  %-20s %3d / %5d (%.1f%%)' % (region, count, pool_count,
              100 * count / pool_count if pool_count else 0))

    # ---- Save V10 sealed holdout ----
    holdout_output = {
        'description': 'V10 sealed holdout (1000 companies, NEVER used in optimization)',
        'seed': SEED,
        'n_companies': len(selected),
        'source': 'expanded_training_v6.json (excluding permanent holdout)',
        'companies': selected,
    }
    holdout_path = os.path.join(SCRIPT_DIR, 'selected_v10_sealed_holdout_1000.json')
    with open(holdout_path, 'w', encoding='utf-8') as f:
        json.dump(holdout_output, f, indent=2)
    print('')
    print('Saved V10 sealed holdout: %s' % holdout_path)

    # ---- Build training set excluding BOTH holdouts ----
    training = [c for c in pool if c['company_code'] not in perm_ids
                and c['company_code'] not in v10_ids]
    training_ids = set(c['company_code'] for c in training)

    assert len(training_ids & perm_ids) == 0, "PERM CONTAMINATION in training"
    assert len(training_ids & v10_ids) == 0, "V10 CONTAMINATION in training"

    print('')
    print('Training set N: %d' % len(training))
    print('PASS: both holdouts excluded from training')

    # Save training set
    training_path = os.path.join(SCRIPT_DIR, 'expanded_training_v10.json')
    with open(training_path, 'w', encoding='utf-8') as f:
        json.dump(training, f, indent=2)
    print('Saved training set: %s' % training_path)

    # ---- Summary ----
    print('')
    print('SUMMARY')
    print('  Full pool (excl perm holdout): %d' % len(pool))
    print('  Permanent holdout (separate):  %d' % len(perm_ids))
    print('  V10 sealed holdout:            %d' % len(v10_ids))
    print('  Training (V10):                %d' % len(training))
    print('  Check: V10(%d) + Train(%d) = %d (should be %d = pool)' % (
        len(v10_ids), len(training),
        len(v10_ids) + len(training), len(pool)))

    print('')
    print('Done.')


if __name__ == '__main__':
    main()
