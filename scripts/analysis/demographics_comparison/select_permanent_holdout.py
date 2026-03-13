"""Select 400 permanent holdout companies from the full EEO-1 pool.

Stratified by 18 industry groups x 4 regions (72 cells).
Uses random.seed(42) for reproducibility.

Usage:
    py scripts/analysis/demographics_comparison/select_permanent_holdout.py

Outputs:
    selected_permanent_holdout_400.json in the same directory.
"""
import sys
import os
import json
import random
from collections import defaultdict
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..')))
sys.path.insert(0, SCRIPT_DIR)

from config import EEO1_CSV
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from classifiers import classify_naics_group, classify_region, NAICS_GROUPS, REGION_STATES

TARGET_N = 400
FLOOR_PER_CELL = 5
CAP_PER_CELL = 40
SEED = 42

OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_400.json')

# 18 named industry groups (same order as classifiers.py)
INDUSTRY_GROUP_NAMES = [label for label, _ in NAICS_GROUPS]
REGION_NAMES = sorted(REGION_STATES.keys())  # Midwest, Northeast, South, West


def load_and_filter_pool():
    """Load all EEO-1 rows, parse, filter to valid companies, deduplicate."""
    raw_rows = load_eeo1_data()
    print('Total EEO-1 rows: %d' % len(raw_rows))

    # Parse each row and filter
    parsed = []
    for row in raw_rows:
        p = parse_eeo1_row(row)
        if p is None:
            continue
        if p['total'] < 10:
            continue
        naics = p.get('naics', '')
        if not naics or len(naics) < 2:
            continue
        state = p.get('state', '')
        if not state or len(state) != 2:
            continue
        parsed.append(p)

    print('After filtering (total>=10, valid NAICS, valid state): %d' % len(parsed))

    # Deduplicate by company_code: keep most recent year
    by_code = defaultdict(list)
    for p in parsed:
        by_code[p['company_code']].append(p)

    deduped = []
    for code, entries in by_code.items():
        entries.sort(key=lambda x: x['year'], reverse=True)
        deduped.append(entries[0])

    print('After dedup (most recent year per company): %d unique companies' % len(deduped))
    return deduped


def classify_pool(companies):
    """Add naics_group and region classification to each company dict."""
    for c in companies:
        c['naics_group'] = classify_naics_group(c['naics'])
        c['region'] = classify_region(c['state'])
    return companies


def stratified_select(companies, target_n=TARGET_N):
    """Stratified selection across 18 industry groups x 4 regions.

    Floor = FLOOR_PER_CELL per cell (if available), cap = CAP_PER_CELL.
    Only uses named groups and named regions (excludes 'Other').
    """
    random.seed(SEED)

    # Build strata: (naics_group, region) -> list of companies
    strata = defaultdict(list)
    skipped_other = 0
    for c in companies:
        ng = c['naics_group']
        rg = c['region']
        # Only include companies in one of the 18 named groups and 4 named regions
        if ng not in INDUSTRY_GROUP_NAMES or rg not in REGION_NAMES:
            skipped_other += 1
            continue
        strata[(ng, rg)].append(c)

    if skipped_other:
        print('Skipped %d companies with Other industry/region' % skipped_other)

    total_cells = len(INDUSTRY_GROUP_NAMES) * len(REGION_NAMES)
    populated_cells = len(strata)
    print('Strata grid: %d industry x %d region = %d cells (%d populated)' % (
        len(INDUSTRY_GROUP_NAMES), len(REGION_NAMES), total_cells, populated_cells))

    total_available = sum(len(v) for v in strata.values())
    print('Total eligible in grid: %d' % total_available)

    # Phase 1: Take floor from each cell (up to FLOOR_PER_CELL)
    selected = []
    selected_codes = set()
    cell_counts = defaultdict(int)

    for key in sorted(strata.keys()):
        pool = strata[key]
        random.shuffle(pool)
        n_take = min(FLOOR_PER_CELL, len(pool))
        for c in pool[:n_take]:
            selected.append(c)
            selected_codes.add(c['company_code'])
            cell_counts[key] += 1

    print('After floor phase: %d selected' % len(selected))

    # Phase 2: Fill remaining quota proportionally, respecting cap
    remaining_target = target_n - len(selected)
    if remaining_target > 0:
        # Build pool of unselected candidates still in grid
        unselected_by_cell = defaultdict(list)
        for key, pool in strata.items():
            for c in pool:
                if c['company_code'] not in selected_codes:
                    unselected_by_cell[key].append(c)

        # Compute how many more each cell can give
        # Distribute proportionally to cell pool size, capped
        cell_remaining_capacity = {}
        total_unselected = 0
        for key in sorted(unselected_by_cell.keys()):
            available = len(unselected_by_cell[key])
            capacity = min(available, CAP_PER_CELL - cell_counts.get(key, 0))
            capacity = max(0, capacity)
            cell_remaining_capacity[key] = capacity
            total_unselected += capacity

        if total_unselected > 0:
            # Proportional allocation
            for key in sorted(cell_remaining_capacity.keys()):
                cap = cell_remaining_capacity[key]
                if cap <= 0:
                    continue
                n_extra = min(cap, max(1, round(remaining_target * cap / total_unselected)))
                pool = unselected_by_cell[key]
                random.shuffle(pool)
                for c in pool[:n_extra]:
                    if c['company_code'] not in selected_codes:
                        selected.append(c)
                        selected_codes.add(c['company_code'])
                        cell_counts[key] += 1

    print('After proportional phase: %d selected' % len(selected))

    # Phase 3: If still under target, add more from any cell under cap
    if len(selected) < target_n:
        all_unselected = []
        for key, pool in strata.items():
            if cell_counts.get(key, 0) >= CAP_PER_CELL:
                continue
            for c in pool:
                if c['company_code'] not in selected_codes:
                    all_unselected.append((key, c))
        random.shuffle(all_unselected)
        for key, c in all_unselected:
            if len(selected) >= target_n:
                break
            if cell_counts.get(key, 0) >= CAP_PER_CELL:
                continue
            if c['company_code'] not in selected_codes:
                selected.append(c)
                selected_codes.add(c['company_code'])
                cell_counts[key] += 1

    # Trim if over target - remove proportionally from largest cells
    if len(selected) > target_n:
        excess = len(selected) - target_n
        # Group selected by cell
        cell_selected = defaultdict(list)
        for c in selected:
            cell_selected[(c['naics_group'], c['region'])].append(c)
        # Sort cells by size descending, remove from largest first
        sorted_cells = sorted(cell_selected.keys(),
                              key=lambda k: len(cell_selected[k]), reverse=True)
        removed_codes = set()
        for _ in range(excess):
            for key in sorted_cells:
                if len(cell_selected[key]) > FLOOR_PER_CELL:
                    removed = cell_selected[key].pop()
                    removed_codes.add(removed['company_code'])
                    cell_counts[key] -= 1
                    break
        selected = [c for c in selected if c['company_code'] not in removed_codes]

    return selected, cell_counts


def print_stratification_summary(selected, cell_counts):
    """Print summary of stratification across industry x region."""
    print('')
    print('STRATIFICATION SUMMARY (%d companies)' % len(selected))
    print('=' * 80)

    # Header row
    header = '%-35s' % 'Industry Group'
    for rg in REGION_NAMES:
        header += ' | %8s' % rg
    header += ' | %8s' % 'Total'
    print(header)
    print('-' * 80)

    # Rows by industry group
    grand_total = 0
    region_totals = defaultdict(int)
    for ng in INDUSTRY_GROUP_NAMES:
        row_str = '%-35s' % ng[:35]
        row_total = 0
        for rg in REGION_NAMES:
            count = cell_counts.get((ng, rg), 0)
            row_str += ' | %8d' % count
            row_total += count
            region_totals[rg] += count
        row_str += ' | %8d' % row_total
        grand_total += row_total
        print(row_str)

    print('-' * 80)
    footer = '%-35s' % 'Total'
    for rg in REGION_NAMES:
        footer += ' | %8d' % region_totals[rg]
    footer += ' | %8d' % grand_total
    print(footer)

    # Region distribution
    print('')
    print('Region distribution:')
    for rg in REGION_NAMES:
        print('  %-12s: %d' % (rg, region_totals[rg]))

    # Industry distribution
    print('')
    print('Industry distribution:')
    industry_counts = defaultdict(int)
    for c in selected:
        industry_counts[c['naics_group']] += 1
    for ng in INDUSTRY_GROUP_NAMES:
        print('  %-35s: %d' % (ng, industry_counts.get(ng, 0)))


def assert_no_holdout_contamination(training_ids, holdout_file=None):
    """Verify no training company IDs appear in the permanent holdout set.

    Args:
        training_ids: set or list of company_code strings used for training.
        holdout_file: path to the holdout JSON file. Defaults to OUTPUT_FILE.

    Raises:
        AssertionError if any overlap is found.
    """
    holdout_file = holdout_file or OUTPUT_FILE
    if not os.path.exists(holdout_file):
        raise FileNotFoundError('Holdout file not found: %s' % holdout_file)

    with open(holdout_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    holdout_ids = set()
    # Handle both top-level list and dict-with-companies format
    if isinstance(data, dict):
        companies = data.get('companies', [])
    else:
        companies = data
    for c in companies:
        holdout_ids.add(c['company_code'])

    training_set = set(training_ids)
    overlap = training_set & holdout_ids
    assert len(overlap) == 0, (
        'Holdout contamination: %d training companies found in holdout set: %s'
        % (len(overlap), sorted(overlap)[:10])
    )
    return True


def load_v5_training_ids():
    """Load V5 training company codes to exclude from holdout."""
    v5_path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
    if not os.path.exists(v5_path):
        return set()
    with open(v5_path, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    return {c['company_code'] for c in companies}


def main():
    print('SELECT PERMANENT HOLDOUT (400 companies)')
    print('=' * 60)
    print('Seed: %d' % SEED)
    print('Target: %d companies' % TARGET_N)
    print('Grid: %d industry groups x %d regions' % (
        len(INDUSTRY_GROUP_NAMES), len(REGION_NAMES)))
    print('Floor per cell: %d, Cap per cell: %d' % (FLOOR_PER_CELL, CAP_PER_CELL))
    print('')

    # Step 1: Load and filter
    pool = load_and_filter_pool()

    # Step 1b: Exclude V5 training companies
    v5_ids = load_v5_training_ids()
    if v5_ids:
        before = len(pool)
        pool = [c for c in pool if c['company_code'] not in v5_ids]
        print('Excluded %d V5 training companies, pool now: %d' % (before - len(pool), len(pool)))

    # Step 2: Classify
    print('')
    print('Classifying companies...')
    pool = classify_pool(pool)

    # Step 3: Stratified selection
    print('')
    print('Running stratified selection...')
    selected, cell_counts = stratified_select(pool, TARGET_N)
    print('Final selected: %d companies' % len(selected))

    # Step 4: Print summary
    print_stratification_summary(selected, cell_counts)

    # Step 5: Build output
    output = {
        'metadata': {
            'selection_date': str(date.today()),
            'total_pool_size': len(pool),
            'seed': SEED,
            'version': '1.0',
        },
        'companies': [],
    }

    for c in selected:
        output['companies'].append({
            'name': c['name'],
            'company_code': c['company_code'],
            'year': c['year'],
            'naics': c['naics'],
            'state': c['state'],
            'zipcode': c['zipcode'],
            'naics_group': c['naics_group'],
            'region': c['region'],
            'total': c['total'],
            'race': c['race'],
            'hispanic': c['hispanic'],
            'gender': c['gender'],
        })

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('')
    print('Wrote %s (%d companies)' % (OUTPUT_FILE, len(output['companies'])))

    # Verify self-consistency
    codes = [c['company_code'] for c in output['companies']]
    assert len(codes) == len(set(codes)), 'Duplicate company codes in output!'
    print('Verified: no duplicate company codes')


if __name__ == '__main__':
    main()
