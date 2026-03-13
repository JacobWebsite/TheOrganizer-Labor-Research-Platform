"""Select holdout 200 companies excluding original 200.

Reuses the same stratified selection logic from select_200.py
but excludes companies already in selected_200.json.

Usage:
    py scripts/analysis/demographics_comparison/select_holdout_200.py

Outputs:
    selected_holdout_200.json in the same directory.
"""
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from select_200 import (
    load_and_filter_relaxed, build_candidate_pool, stratified_select,
    print_coverage, TARGET_N, MIN_PER_BUCKET,
)
from select_companies import check_data_availability

SCRIPT_DIR = os.path.dirname(__file__)
ORIGINAL_FILE = os.path.join(SCRIPT_DIR, 'selected_200.json')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'selected_holdout_200.json')


def load_original_codes():
    """Load company codes from original selected_200.json."""
    if not os.path.exists(ORIGINAL_FILE):
        print('ERROR: %s not found.' % ORIGINAL_FILE)
        sys.exit(1)
    with open(ORIGINAL_FILE, 'r', encoding='utf-8') as f:
        original = json.load(f)
    codes = set(c['company_code'] for c in original)
    print('Loaded %d original company codes to exclude' % len(codes))
    return codes


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Load original 200 codes to exclude
    original_codes = load_original_codes()

    # Step 1: Load and filter (same relaxed threshold)
    rows = load_and_filter_relaxed()

    # Step 2: Check data availability
    print('')
    print('Checking data availability (LODES + ACS)...')
    valid = check_data_availability(rows, cur)

    # Step 3: Parse truth & classify
    print('')
    print('Building candidate pool with 5D classification...')
    candidates = build_candidate_pool(valid, cur)

    # Step 4: Exclude original 200
    filtered = [c for c in candidates if c['company_code'] not in original_codes]
    excluded = len(candidates) - len(filtered)
    print('Excluded %d original companies, %d candidates remain' % (
        excluded, len(filtered)))

    if len(filtered) < TARGET_N:
        print('WARNING: Only %d candidates available (target %d)' % (
            len(filtered), TARGET_N))

    # Step 5: Stratified sampling (same algorithm, same seed logic)
    print('')
    print('Running stratified selection for %d holdout companies...' % TARGET_N)
    selected = stratified_select(filtered, TARGET_N)
    print('Selected: %d holdout companies' % len(selected))

    # Verify no overlap
    holdout_codes = set(c['company_code'] for c in selected)
    overlap = holdout_codes & original_codes
    if overlap:
        print('ERROR: %d companies overlap with original 200!' % len(overlap))
        sys.exit(1)
    print('Verified: zero overlap with original 200')

    # Step 6: Print coverage
    print_coverage(selected)

    # Step 7: Write JSON (strip internal _truth field)
    output = []
    for c in selected:
        out = dict(c)
        out.pop('_truth', None)
        output.append(out)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('')
    print('Wrote %s (%d companies)' % (OUTPUT_FILE, len(output)))

    conn.close()


if __name__ == '__main__':
    main()
