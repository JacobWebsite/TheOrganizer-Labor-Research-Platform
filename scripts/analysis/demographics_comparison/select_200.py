"""Stratified sampling: select 200 EEO-1 companies across 5 dimensions.

Usage:
    py scripts/analysis/demographics_comparison/select_200.py

Outputs:
    selected_200.json in the same directory.
"""
import sys
import os
import csv
import json
import random
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from config import EEO1_CSV
from eeo1_parser import _safe_int, parse_eeo1_row
from select_companies import STATE_FIPS, check_data_availability
from classifiers import (
    classify_naics_group, classify_size, classify_region,
    classify_minority, batch_classify_urbanicity, classify_all,
)

TARGET_N = 200
MIN_PER_BUCKET = 3
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), 'selected_200.json')


def load_and_filter_relaxed(csv_path=None):
    """Load EEO-1 CSV with TOTAL10 >= 50 (relaxed to fill 1-99 bucket)."""
    csv_path = csv_path or EEO1_CSV
    print('Loading EEO-1 data from %s ...' % csv_path)

    rows = []
    with open(csv_path, 'r', encoding='cp1252') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print('  Total rows: %d' % len(rows))

    company_year_counts = defaultdict(int)
    for row in rows:
        key = (row.get('COMPANY', ''), row.get('YEAR', ''))
        company_year_counts[key] += 1

    filtered = []
    for row in rows:
        company = row.get('COMPANY', '')
        year = _safe_int(row.get('YEAR', 0))
        naics = (row.get('NAICS') or '').strip()
        total = _safe_int(row.get('TOTAL10', 0))
        zipcode = (row.get('ZIPCODE') or '').strip()

        if company_year_counts.get((company, str(year)), 0) > 1:
            continue
        if not naics or len(naics) < 2:
            continue
        if total < 50:  # relaxed from 100
            continue
        if not zipcode or len(zipcode) < 5:
            continue
        if year not in (2020, 2019, 2018):
            continue
        filtered.append(row)

    print('  After base filters (single-unit, NAICS, size>=50, ZIP, year): %d' % len(filtered))

    # Deduplicate: keep most recent year per company
    by_company = defaultdict(list)
    for row in filtered:
        by_company[row['COMPANY']].append(row)

    deduped = []
    for company, company_rows in by_company.items():
        company_rows.sort(key=lambda r: _safe_int(r.get('YEAR', 0)), reverse=True)
        deduped.append(company_rows[0])

    print('  After dedup (most recent year): %d unique companies' % len(deduped))
    return deduped


def build_candidate_pool(valid_rows, cur):
    """Parse EEO-1 truth and classify each candidate into 5D."""
    # Collect all unique county_fips for batch urbanicity query
    county_fips_set = set()
    for row in valid_rows:
        cf = row.get('_county_fips', '')
        if cf:
            county_fips_set.add(cf)

    print('  Batch-classifying urbanicity for %d counties...' % len(county_fips_set))
    urbanicity_map = batch_classify_urbanicity(cur, county_fips_set)

    candidates = []
    parse_fail = 0
    for row in valid_rows:
        truth = parse_eeo1_row(row)
        if not truth or truth['total'] == 0:
            parse_fail += 1
            continue

        state = (row.get('STATE') or '').strip()
        naics = (row.get('NAICS') or '').strip()
        county_fips = row.get('_county_fips', '')
        state_fips = row.get('_state_fips', '')
        urbanicity = urbanicity_map.get(county_fips, 'Rural')

        classifications = classify_all(state, naics, truth['total'], truth, urbanicity)

        candidates.append({
            'company_code': truth['company_code'],
            'name': truth['name'],
            'year': truth['year'],
            'naics': naics,
            'state': state,
            'zipcode': (row.get('ZIPCODE') or '').strip()[:5],
            'county_fips': county_fips,
            'state_fips': state_fips,
            'total': truth['total'],
            'classifications': classifications,
            '_truth': truth,  # kept for selection, stripped before JSON output
        })

    if parse_fail:
        print('  Skipped %d rows (parse failure)' % parse_fail)
    print('  Candidate pool: %d companies' % len(candidates))
    return candidates


def stratified_select(candidates, target_n=TARGET_N):
    """Greedy stratified selection maximizing 5D coverage.

    1. Compute target count per NAICS group proportional to pool.
    2. Within each group, pick candidates that fill under-represented buckets.
    3. Post-selection: ensure every bucket in every dimension has >= MIN_PER_BUCKET.
    """
    random.seed(42)

    # Group candidates by NAICS group
    by_naics = defaultdict(list)
    for c in candidates:
        by_naics[c['classifications']['naics_group']].append(c)

    # Compute target per group
    total_pool = len(candidates)
    targets = {}
    for group, members in by_naics.items():
        targets[group] = max(MIN_PER_BUCKET, round(target_n * len(members) / total_pool))

    # Adjust targets to sum to target_n
    target_sum = sum(targets.values())
    if target_sum != target_n:
        diff = target_n - target_sum
        # Adjust largest groups
        sorted_groups = sorted(targets.keys(), key=lambda g: len(by_naics[g]), reverse=True)
        for g in sorted_groups:
            if diff == 0:
                break
            if diff > 0:
                targets[g] += 1
                diff -= 1
            elif targets[g] > MIN_PER_BUCKET:
                targets[g] -= 1
                diff += 1

    # Track bucket fill counts across all 5 dimensions
    dims = ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']
    bucket_counts = defaultdict(int)  # (dim, bucket) -> count

    selected = []
    selected_codes = set()

    def coverage_score(c):
        """Higher score = fills more under-represented buckets."""
        score = 0
        for dim in dims:
            bucket = c['classifications'][dim]
            count = bucket_counts.get((dim, bucket), 0)
            if count < MIN_PER_BUCKET:
                score += (MIN_PER_BUCKET - count) * 10
            elif count < 8:
                score += 1
        return score

    # Select within each NAICS group
    for group in sorted(targets.keys()):
        group_target = targets[group]
        pool = by_naics[group]
        random.shuffle(pool)

        # Sort by coverage score (highest first) each iteration
        group_selected = []
        remaining = list(pool)
        while len(group_selected) < group_target and remaining:
            remaining.sort(key=coverage_score, reverse=True)
            best = remaining.pop(0)
            if best['company_code'] in selected_codes:
                continue
            group_selected.append(best)
            selected_codes.add(best['company_code'])
            for dim in dims:
                bucket_counts[(dim, best['classifications'][dim])] += 1

        selected.extend(group_selected)

    # Post-selection: check all buckets have >= MIN_PER_BUCKET
    # Collect all known buckets
    all_buckets = defaultdict(set)
    for c in candidates:
        for dim in dims:
            all_buckets[dim].add(c['classifications'][dim])

    under_filled = []
    for dim in dims:
        for bucket in all_buckets[dim]:
            count = bucket_counts.get((dim, bucket), 0)
            if count < MIN_PER_BUCKET:
                under_filled.append((dim, bucket, count))

    # Try to fill under-represented buckets by swapping from over-represented
    if under_filled:
        # Build pool of unselected candidates
        unselected = [c for c in candidates if c['company_code'] not in selected_codes]
        for dim, bucket, count in under_filled:
            needed = MIN_PER_BUCKET - count
            # Find candidates in this bucket
            fill_pool = [c for c in unselected if c['classifications'][dim] == bucket]
            random.shuffle(fill_pool)
            for c in fill_pool[:needed]:
                if c['company_code'] in selected_codes:
                    continue
                # Find an over-represented candidate to swap out
                # Look for selected companies in the most over-represented bucket of this dim
                over_buckets = sorted(
                    all_buckets[dim],
                    key=lambda b: bucket_counts.get((dim, b), 0),
                    reverse=True)
                swapped = False
                for ob in over_buckets:
                    if bucket_counts.get((dim, ob), 0) <= MIN_PER_BUCKET + 1:
                        break
                    # Find a selected company in this over-represented bucket
                    for i, s in enumerate(selected):
                        if s['classifications'][dim] == ob:
                            # Swap
                            old = selected.pop(i)
                            selected_codes.discard(old['company_code'])
                            for d in dims:
                                bucket_counts[(d, old['classifications'][d])] -= 1
                            selected.append(c)
                            selected_codes.add(c['company_code'])
                            for d in dims:
                                bucket_counts[(d, c['classifications'][d])] += 1
                            swapped = True
                            break
                    if swapped:
                        break
                if not swapped and len(selected) < target_n:
                    # Just add without swapping if under target
                    selected.append(c)
                    selected_codes.add(c['company_code'])
                    for d in dims:
                        bucket_counts[(d, c['classifications'][d])] += 1

    # Trim to target if over
    if len(selected) > target_n:
        selected = selected[:target_n]

    return selected


def print_coverage(selected):
    """Print coverage summary table."""
    dims = ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']
    dim_labels = {
        'naics_group': 'Industry',
        'size': 'Size',
        'region': 'Region',
        'minority_share': 'Minority Share',
        'urbanicity': 'Urbanicity',
    }

    print('')
    print('COVERAGE SUMMARY (%d companies)' % len(selected))
    print('=' * 60)
    print('%-18s | %-30s | %5s' % ('DIMENSION', 'BUCKET', 'COUNT'))
    print('-' * 60)

    for dim in dims:
        counts = defaultdict(int)
        for c in selected:
            counts[c['classifications'][dim]] += 1
        for bucket in sorted(counts.keys()):
            print('%-18s | %-30s | %5d' % (
                dim_labels.get(dim, dim), bucket, counts[bucket]))
        print('-' * 60)


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Load and filter (relaxed threshold)
    rows = load_and_filter_relaxed()

    # Step 2: Check data availability (reuse existing function)
    print('')
    print('Checking data availability (LODES + ACS)...')
    valid = check_data_availability(rows, cur)

    # Step 3: Parse truth & classify
    print('')
    print('Building candidate pool with 5D classification...')
    candidates = build_candidate_pool(valid, cur)

    if len(candidates) < TARGET_N:
        print('WARNING: Only %d candidates available (target %d)' % (
            len(candidates), TARGET_N))

    # Step 4: Stratified sampling
    print('')
    print('Running stratified selection for %d companies...' % TARGET_N)
    selected = stratified_select(candidates, TARGET_N)
    print('Selected: %d companies' % len(selected))

    # Step 5: Print coverage
    print_coverage(selected)

    # Step 6: Write JSON (strip internal _truth field)
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
