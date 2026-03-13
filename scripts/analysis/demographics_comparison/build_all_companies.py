"""Merge 4 JSON company files into all_companies_v4.json for V4 evaluation.

Loads selected_200.json, selected_holdout_200.json, selected_400.json,
selected_holdout_v3.json, tags each with source_set, deduplicates by
company_code (keeps first seen), outputs all_companies_v4.json.

Usage:
    py scripts/analysis/demographics_comparison/build_all_companies.py
"""
import sys
import os
import json
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(__file__)

SOURCE_FILES = [
    ('selected_200.json', 'v2_train'),
    ('selected_holdout_200.json', 'v2_holdout'),
    ('selected_400.json', 'v3_train'),
    ('selected_holdout_v3.json', 'v3_holdout'),
]

OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')


def main():
    all_companies = []
    seen_codes = {}
    duplicates = []

    for filename, source_set in SOURCE_FILES:
        filepath = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(filepath):
            print('WARNING: %s not found, skipping.' % filepath)
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            companies = json.load(f)
        print('Loaded %d companies from %s (source_set=%s)' % (
            len(companies), filename, source_set))

        added = 0
        for company in companies:
            code = company['company_code']
            company['source_set'] = source_set
            if code in seen_codes:
                duplicates.append((code, company.get('name', ''),
                                   source_set, seen_codes[code]))
            else:
                seen_codes[code] = source_set
                all_companies.append(company)
                added += 1
        print('  Added %d new, %d duplicates' % (added, len(companies) - added))

    # Print summary
    print('')
    print('SUMMARY')
    print('=' * 60)
    print('Total unique companies: %d' % len(all_companies))
    print('Duplicates removed: %d' % len(duplicates))

    if duplicates:
        print('')
        print('Duplicate codes (first 10):')
        for code, name, dup_src, orig_src in duplicates[:10]:
            print('  %s (%s) -- in %s, kept from %s' % (
                code, name[:30], dup_src, orig_src))

    # Breakdown by source_set
    source_counts = defaultdict(int)
    for c in all_companies:
        source_counts[c['source_set']] += 1
    print('')
    print('By source_set:')
    for src in ['v2_train', 'v2_holdout', 'v3_train', 'v3_holdout']:
        print('  %-15s %d' % (src, source_counts.get(src, 0)))

    # Breakdown by naics_group
    naics_counts = defaultdict(int)
    region_counts = defaultdict(int)
    minority_counts = defaultdict(int)
    urbanicity_counts = defaultdict(int)
    for c in all_companies:
        cls = c.get('classifications', {})
        naics_counts[cls.get('naics_group', 'Unknown')] += 1
        region_counts[cls.get('region', 'Unknown')] += 1
        minority_counts[cls.get('minority_share', 'Unknown')] += 1
        urbanicity_counts[cls.get('urbanicity', 'Unknown')] += 1

    print('')
    print('By NAICS group:')
    for group in sorted(naics_counts.keys()):
        print('  %-40s %d' % (group, naics_counts[group]))

    print('')
    print('By region:')
    for region in sorted(region_counts.keys()):
        print('  %-20s %d' % (region, region_counts[region]))

    print('')
    print('By minority share:')
    for ms in sorted(minority_counts.keys()):
        print('  %-20s %d' % (ms, minority_counts[ms]))

    print('')
    print('By urbanicity:')
    for u in sorted(urbanicity_counts.keys()):
        print('  %-20s %d' % (u, urbanicity_counts[u]))

    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, indent=2, ensure_ascii=False)
    print('')
    print('Wrote %s (%d companies)' % (OUTPUT_FILE, len(all_companies)))


if __name__ == '__main__':
    main()
