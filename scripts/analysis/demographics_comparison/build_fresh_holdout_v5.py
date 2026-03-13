"""Select fresh holdout companies for V5 final validation.

Selects 200-250 companies from EEO-1 pool that were NOT in the 997 training set,
stratified across 5 dimensions.

Output: selected_fresh_holdout_v5.json

Usage:
    py scripts/analysis/demographics_comparison/build_fresh_holdout_v5.py
"""
import sys
import os
import json
import csv
import random
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from config import EEO1_CSV
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county
from classifiers import (
    classify_naics_group, classify_region, classify_size,
    classify_minority, batch_classify_urbanicity,
)

SCRIPT_DIR = os.path.dirname(__file__)
TARGET_SIZE = 225  # Target 200-250


def load_used_companies():
    """Load company codes already used in training."""
    used = set()
    json_path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            companies = json.load(f)
        for c in companies:
            used.add(c['company_code'])

    # Also exclude holdout sets
    for holdout_file in ['selected_holdout_v3.json', 'selected_holdout_200.json']:
        holdout_path = os.path.join(SCRIPT_DIR, holdout_file)
        if os.path.exists(holdout_path):
            with open(holdout_path, 'r', encoding='utf-8') as f:
                holdout = json.load(f)
            for c in holdout:
                used.add(c['company_code'])

    print('Already used: %d company codes' % len(used))
    return used


def main():
    random.seed(42)
    print('BUILD FRESH HOLDOUT V5')
    print('=' * 60)

    # Load all EEO-1 companies
    eeo1_rows = load_eeo1_data()
    print('Total EEO-1 rows: %d' % len(eeo1_rows))

    used = load_used_companies()

    # Parse all companies and filter
    candidates = []
    seen_codes = set()
    for row in eeo1_rows:
        code = row.get('COMPANY', '').strip()
        if code in used or code in seen_codes:
            continue
        parsed = parse_eeo1_row(row)
        if not parsed:
            continue
        if parsed['total'] < 50:
            continue
        naics = parsed.get('naics', '')
        if not naics or len(naics) < 4:
            continue
        state = parsed.get('state', '')
        zipcode = parsed.get('zipcode', '')
        if not state or not zipcode:
            continue
        candidates.append(parsed)
        seen_codes.add(code)

    print('Eligible candidates: %d' % len(candidates))

    # Resolve geography
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Resolve county_fips for all candidates
    for c in candidates:
        county = zip_to_county(cur, c['zipcode'])
        c['county_fips'] = county or ''
        c['state_fips'] = county[:2] if county else ''

    # Filter candidates with valid county
    candidates = [c for c in candidates if c['county_fips']]
    print('With valid county: %d' % len(candidates))

    # Batch classify urbanicity
    county_set = set(c['county_fips'] for c in candidates)
    urbanicity_map = batch_classify_urbanicity(cur, county_set)

    # Classify all candidates
    for c in candidates:
        minority_cls = classify_minority(c)
        c['classifications'] = {
            'naics_group': classify_naics_group(c['naics']),
            'size': classify_size(c['total']),
            'region': classify_region(c['state']),
            'minority_share': minority_cls,
            'urbanicity': urbanicity_map.get(c['county_fips'], 'Rural'),
        }

    # Stratified sampling across 5 dimensions
    # Group candidates by (naics_group, size, region, minority_share, urbanicity)
    strata = defaultdict(list)
    for c in candidates:
        cls = c['classifications']
        key = (cls['naics_group'], cls['size'], cls['region'],
               cls['minority_share'], cls['urbanicity'])
        strata[key].append(c)

    print('Unique strata: %d' % len(strata))

    # Sample proportionally from each stratum
    selected = []
    n_per_stratum = max(1, TARGET_SIZE // len(strata)) if strata else 1

    # First pass: take at least 1 from each stratum
    for key, pool in sorted(strata.items()):
        n = min(n_per_stratum, len(pool))
        selected.extend(random.sample(pool, n))

    # If under target, sample more from larger strata
    if len(selected) < TARGET_SIZE:
        already_selected = set(c['company_code'] for c in selected)
        remaining = [c for c in candidates if c['company_code'] not in already_selected]
        random.shuffle(remaining)
        need = TARGET_SIZE - len(selected)
        selected.extend(remaining[:need])

    # If over target, trim
    if len(selected) > TARGET_SIZE + 25:
        selected = selected[:TARGET_SIZE]

    print('Selected: %d companies' % len(selected))

    # Print distribution
    print('')
    print('Distribution:')
    for dim in ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']:
        counts = defaultdict(int)
        for c in selected:
            counts[c['classifications'][dim]] += 1
        print('  %s: %s' % (dim, dict(sorted(counts.items()))))

    # Build output
    output = []
    for c in selected:
        output.append({
            'name': c['name'],
            'company_code': c['company_code'],
            'year': c['year'],
            'naics': c['naics'],
            'state': c['state'],
            'zipcode': c['zipcode'],
            'county_fips': c['county_fips'],
            'state_fips': c['state_fips'],
            'total': c['total'],
            'classifications': c['classifications'],
            'source_set': 'fresh_holdout_v5',
        })

    output_path = os.path.join(SCRIPT_DIR, 'selected_fresh_holdout_v5.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print('Output: %s' % output_path)

    conn.close()


if __name__ == '__main__':
    main()
