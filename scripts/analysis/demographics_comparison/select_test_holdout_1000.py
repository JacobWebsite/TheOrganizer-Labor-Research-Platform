"""Select 1,000 stratified test holdout companies from expanded training pool.

Stratified by naics_group x region. These companies are set aside for
testing only -- never used for training.

Excludes the 400 permanent holdout companies.

Output: selected_test_holdout_1000.json

Usage:
    py scripts/analysis/demographics_comparison/select_test_holdout_1000.py
"""
import sys
import os
import json
import random
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

SCRIPT_DIR = os.path.dirname(__file__)
TARGET = 1000
SEED = 42


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Select stratified test holdout')
    parser.add_argument('--seed', type=int, default=SEED,
                        help='Random seed (default: %d)' % SEED)
    parser.add_argument('--output', type=str, default=None,
                        help='Output filename (default: selected_test_holdout_1000.json)')
    cli_args = parser.parse_args()

    seed = cli_args.seed
    output_filename = cli_args.output or 'selected_test_holdout_1000.json'

    print('SELECT TEST HOLDOUT (1,000 companies)')
    print('Seed: %d' % seed)
    print('=' * 60)

    # Load expanded training pool
    pool_path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
    with open(pool_path, 'r', encoding='utf-8') as f:
        pool = json.load(f)
    print('Pool size: %d' % len(pool))

    # Load permanent holdout to double-check exclusion
    holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
    with open(holdout_path, 'r', encoding='utf-8') as f:
        hdata = json.load(f)
    holdout_codes = set(c['company_code'] for c in hdata.get('companies', hdata))
    pool = [c for c in pool if c['company_code'] not in holdout_codes]
    print('After permanent holdout exclusion: %d' % len(pool))

    # Stratify by naics_group x region
    cells = defaultdict(list)
    for c in pool:
        cls = c.get('classifications', {})
        key = (cls.get('naics_group', 'Other'), cls.get('region', 'Other'))
        cells[key].append(c)

    print('Strata (naics_group x region): %d cells' % len(cells))

    # Proportional allocation: each cell gets floor(TARGET * cell_size / pool_size)
    # with remainder distributed to largest cells
    total_pool = len(pool)
    allocations = {}
    for key, companies in cells.items():
        allocations[key] = max(1, int(TARGET * len(companies) / total_pool))

    # Adjust to hit exactly TARGET
    allocated = sum(allocations.values())
    if allocated < TARGET:
        # Add to largest cells
        sorted_keys = sorted(cells.keys(), key=lambda k: len(cells[k]), reverse=True)
        for key in sorted_keys:
            if allocated >= TARGET:
                break
            allocations[key] += 1
            allocated += 1
    elif allocated > TARGET:
        # Remove from smallest cells (but keep minimum 1)
        sorted_keys = sorted(cells.keys(), key=lambda k: len(cells[k]))
        for key in sorted_keys:
            if allocated <= TARGET:
                break
            if allocations[key] > 1:
                allocations[key] -= 1
                allocated -= 1

    print('Target allocation: %d' % sum(allocations.values()))

    # Sample from each cell
    random.seed(seed)
    selected = []
    for key, count in allocations.items():
        cell_companies = cells[key]
        if count >= len(cell_companies):
            # Take all if cell is smaller than allocation
            sampled = cell_companies
        else:
            sampled = random.sample(cell_companies, count)
        selected.extend(sampled)

    print('Selected: %d companies' % len(selected))

    # Print distribution
    print('')
    print('By NAICS Group:')
    group_counts = defaultdict(int)
    for c in selected:
        group_counts[c['classifications']['naics_group']] += 1
    for group, count in sorted(group_counts.items(), key=lambda x: -x[1]):
        pool_count = sum(1 for c in pool if c['classifications']['naics_group'] == group)
        print('  %-45s %3d / %5d (%.1f%%)' % (group, count, pool_count,
              100 * count / pool_count if pool_count else 0))

    print('')
    print('By Region:')
    region_counts = defaultdict(int)
    for c in selected:
        region_counts[c['classifications']['region']] += 1
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        print('  %-20s %d' % (region, count))

    # Save
    output = {
        'description': 'Test holdout set (1000 companies, stratified by naics_group x region)',
        'seed': seed,
        'n_companies': len(selected),
        'source': 'expanded_training_v6.json (2019-2020, all EEO-1 files)',
        'companies': selected,
    }
    output_path = os.path.join(SCRIPT_DIR, output_filename)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('')
    print('Output: %s' % output_path)

    # Verify no overlap with permanent holdout
    test_codes = set(c['company_code'] for c in selected)
    overlap = test_codes & holdout_codes
    if overlap:
        print('ERROR: %d companies overlap with permanent holdout!' % len(overlap))
    else:
        print('Verified: 0 overlap with permanent holdout')

    print('Done.')


if __name__ == '__main__':
    main()
