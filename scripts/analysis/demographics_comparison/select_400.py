"""Select 400 training companies excluding both prior sets (200 + holdout 200).

Reuses the same stratified selection logic from select_200.py
but excludes companies already in selected_200.json and
selected_holdout_200.json.

Usage:
    py scripts/analysis/demographics_comparison/select_400.py

Outputs:
    selected_400.json in the same directory.
"""
import sys
import os
import json
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from select_200 import (
    load_and_filter_relaxed, build_candidate_pool, stratified_select,
    print_coverage, MIN_PER_BUCKET,
)
from select_companies import check_data_availability

TARGET_N = 400

SCRIPT_DIR = os.path.dirname(__file__)
ORIGINAL_FILE = os.path.join(SCRIPT_DIR, 'selected_200.json')
HOLDOUT_FILE = os.path.join(SCRIPT_DIR, 'selected_holdout_200.json')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'selected_400.json')


def load_all_prior_codes():
    """Load company codes from both selected_200.json and selected_holdout_200.json."""
    all_codes = set()

    for label, filepath in [('original 200', ORIGINAL_FILE),
                            ('holdout 200', HOLDOUT_FILE)]:
        if not os.path.exists(filepath):
            print('ERROR: %s not found.' % filepath)
            sys.exit(1)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        codes = set(c['company_code'] for c in data)
        print('Loaded %d codes from %s (%s)' % (len(codes), os.path.basename(filepath), label))
        all_codes |= codes

    print('Total prior codes to exclude: %d' % len(all_codes))
    return all_codes


def check_bucket_coverage(selected, candidates):
    """Verify all dimension buckets have >= MIN_PER_BUCKET companies."""
    dims = ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']

    # Collect all known buckets from the full candidate pool
    all_buckets = defaultdict(set)
    for c in candidates:
        for dim in dims:
            all_buckets[dim].add(c['classifications'][dim])

    # Count selected per bucket
    bucket_counts = defaultdict(int)
    for c in selected:
        for dim in dims:
            bucket_counts[(dim, c['classifications'][dim])] += 1

    under_filled = []
    for dim in dims:
        for bucket in sorted(all_buckets[dim]):
            count = bucket_counts.get((dim, bucket), 0)
            if count < MIN_PER_BUCKET:
                under_filled.append((dim, bucket, count))

    if under_filled:
        print('')
        print('WARNING: %d buckets have fewer than %d companies:' % (
            len(under_filled), MIN_PER_BUCKET))
        for dim, bucket, count in under_filled:
            print('  %-18s | %-30s | %d (need %d)' % (dim, bucket, count, MIN_PER_BUCKET))
        return False
    else:
        print('Verified: all dimension buckets have >= %d companies' % MIN_PER_BUCKET)
        return True


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Load both prior sets to exclude
    prior_codes = load_all_prior_codes()

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

    # Step 4: Exclude all prior companies (original 200 + holdout 200)
    filtered = [c for c in candidates if c['company_code'] not in prior_codes]
    excluded = len(candidates) - len(filtered)
    print('Excluded %d prior companies, %d candidates remain' % (
        excluded, len(filtered)))

    if len(filtered) < TARGET_N:
        print('WARNING: Only %d candidates available (target %d)' % (
            len(filtered), TARGET_N))

    # Step 5: Stratified sampling (same algorithm, same seed logic)
    print('')
    print('Running stratified selection for %d companies...' % TARGET_N)
    selected = stratified_select(filtered, TARGET_N)
    print('Selected: %d companies' % len(selected))

    # Verify no overlap with either prior set
    selected_codes = set(c['company_code'] for c in selected)
    overlap = selected_codes & prior_codes
    if overlap:
        print('ERROR: %d companies overlap with prior sets!' % len(overlap))
        for code in sorted(overlap):
            print('  Overlap: %s' % code)
        sys.exit(1)
    print('Verified: zero overlap with original 200')
    print('Verified: zero overlap with holdout 200')

    # Step 6: Post-selection bucket coverage check
    print('')
    print('Checking bucket coverage (all buckets >= %d)...' % MIN_PER_BUCKET)
    check_bucket_coverage(selected, filtered)

    # Step 7: Print coverage
    print_coverage(selected)

    # Step 8: Write JSON (strip internal _truth field)
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
