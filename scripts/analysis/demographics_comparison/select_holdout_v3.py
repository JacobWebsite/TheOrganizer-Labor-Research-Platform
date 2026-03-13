"""Select fresh holdout 200 companies for V3.

Excludes all companies used in:
- selected_200.json (original training)
- selected_holdout_200.json (original holdout)
- selected_400.json (V3 training)

Usage:
    py scripts/analysis/demographics_comparison/select_holdout_v3.py

Outputs:
    selected_holdout_v3.json in the same directory.
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
    print_coverage, MIN_PER_BUCKET,
)
from select_companies import check_data_availability

TARGET_N = 200
SCRIPT_DIR = os.path.dirname(__file__)
EXCLUDE_FILES = [
    os.path.join(SCRIPT_DIR, 'selected_200.json'),
    os.path.join(SCRIPT_DIR, 'selected_holdout_200.json'),
    os.path.join(SCRIPT_DIR, 'selected_400.json'),
]
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'selected_holdout_v3.json')


def load_all_used_codes():
    """Load company codes from all prior selection files."""
    all_codes = set()
    for filepath in EXCLUDE_FILES:
        if not os.path.exists(filepath):
            print('ERROR: %s not found.' % filepath)
            sys.exit(1)
        with open(filepath, 'r', encoding='utf-8') as f:
            companies = json.load(f)
        codes = set(c['company_code'] for c in companies)
        print('  %s: %d companies' % (os.path.basename(filepath), len(codes)))
        all_codes.update(codes)
    print('Total excluded: %d unique company codes' % len(all_codes))
    return all_codes


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print('Loading company codes to exclude...')
    used_codes = load_all_used_codes()

    rows = load_and_filter_relaxed()

    print('')
    print('Checking data availability (LODES + ACS)...')
    valid = check_data_availability(rows, cur)

    print('')
    print('Building candidate pool with 5D classification...')
    candidates = build_candidate_pool(valid, cur)

    filtered = [c for c in candidates if c['company_code'] not in used_codes]
    excluded = len(candidates) - len(filtered)
    print('Excluded %d used companies, %d candidates remain' % (excluded, len(filtered)))

    if len(filtered) < TARGET_N:
        print('WARNING: Only %d candidates available (target %d)' % (len(filtered), TARGET_N))

    print('')
    print('Running stratified selection for %d holdout companies...' % TARGET_N)
    selected = stratified_select(filtered, TARGET_N)
    print('Selected: %d holdout companies' % len(selected))

    # Verify no overlap
    selected_codes = set(c['company_code'] for c in selected)
    overlap = selected_codes & used_codes
    if overlap:
        print('ERROR: %d companies overlap with prior sets!' % len(overlap))
        sys.exit(1)
    print('Verified: zero overlap with all prior sets')

    print_coverage(selected)

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
