"""Recover NAICS codes for EEO-1 companies missing them.

Strategy 1: Cross-year backfill - if a company has NAICS in any year, use it for all years.
Strategy 2: Cross-reference from database tables (osha_establishments, sam_entities, master_employers).

Output: recovered_naics_mappings.json with recovery mappings and statistics.
"""
import sys
import os
import json
import csv
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from eeo1_parser import load_eeo1_data
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def normalize_name(name):
    """Normalize company name for matching: uppercase, strip, remove punctuation."""
    import re
    if not name:
        return ''
    name = name.upper().strip()
    # Remove common suffixes and punctuation for better matching
    name = re.sub(r'[^A-Z0-9 ]', '', name)
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def main():
    print('=' * 70)
    print('NAICS Recovery for EEO-1 Companies')
    print('=' * 70)
    print()

    # ------------------------------------------------------------------
    # Step 1: Load EEO-1 data and build company index
    # ------------------------------------------------------------------
    print('[1/5] Loading EEO-1 data...')
    rows = load_eeo1_data()
    print('  Total rows: %d' % len(rows))

    # Build company index: code -> {name, state, years: {year: naics}}
    companies = {}
    for r in rows:
        code = (r.get('COMPANY') or '').strip()
        name = (r.get('CONAME') or r.get('NAME') or '').strip()
        year = (r.get('YEAR') or '').strip()
        naics = (r.get('NAICS') or '').strip()
        state = (r.get('STATE') or '').strip()
        zipcode = (r.get('ZIPCODE') or '').strip()

        if not code:
            continue

        if code not in companies:
            companies[code] = {
                'name': name,
                'state': state,
                'zipcode': zipcode,
                'years': {},
            }
        companies[code]['years'][year] = naics
        # Keep updating name/state in case later rows have better data
        if name and not companies[code]['name']:
            companies[code]['name'] = name
        if state and not companies[code]['state']:
            companies[code]['state'] = state

    print('  Unique company codes: %d' % len(companies))

    # Categorize companies
    has_all = []
    cross_year_recoverable = []
    needs_external = []

    for code, info in companies.items():
        naics_vals = [v for v in info['years'].values() if v]
        blank_years = [y for y, v in info['years'].items() if not v]

        if not naics_vals:
            needs_external.append(code)
        elif blank_years:
            cross_year_recoverable.append(code)
        else:
            has_all.append(code)

    print()
    print('  Companies with NAICS in ALL years: %d' % len(has_all))
    print('  Companies with NAICS in SOME years (cross-year): %d' % len(cross_year_recoverable))
    print('  Companies with NAICS in NO years (external): %d' % len(needs_external))

    # ------------------------------------------------------------------
    # Step 2: Cross-year backfill
    # ------------------------------------------------------------------
    print()
    print('[2/5] Cross-year NAICS backfill...')

    recovery_mappings = {}  # code -> {naics, source, source_detail}
    cross_year_count = 0
    cross_year_rows_recovered = 0

    for code in cross_year_recoverable:
        info = companies[code]
        # Get the NAICS from any year that has it (prefer most common)
        naics_vals = [v for v in info['years'].values() if v]
        # Use the most common NAICS (in case different years have different codes)
        from collections import Counter
        naics_counts = Counter(naics_vals)
        best_naics = naics_counts.most_common(1)[0][0]

        blank_years = [y for y, v in info['years'].items() if not v]
        cross_year_count += 1
        cross_year_rows_recovered += len(blank_years)

        recovery_mappings[code] = {
            'company_name': info['name'],
            'state': info['state'],
            'naics': best_naics,
            'source': 'cross_year_backfill',
            'source_detail': 'Found in %d of %d years' % (
                len(naics_vals), len(info['years'])),
            'years_recovered': blank_years,
        }

    print('  Recovered %d companies (%d year-rows) via cross-year backfill' % (
        cross_year_count, cross_year_rows_recovered))

    # ------------------------------------------------------------------
    # Step 3: External lookup - build lookup dictionaries from DB
    # ------------------------------------------------------------------
    print()
    print('[3/5] Loading external NAICS sources from database...')

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # 3a: OSHA establishments - name + state -> naics_code
    print('  Loading osha_establishments...')
    cur.execute("""
        SELECT UPPER(TRIM(estab_name)) AS name_norm,
               UPPER(TRIM(site_state)) AS state,
               naics_code
        FROM osha_establishments
        WHERE naics_code IS NOT NULL
          AND naics_code != ''
          AND estab_name IS NOT NULL
    """)
    osha_lookup = {}  # (norm_name, state) -> naics
    osha_count = 0
    for row in cur:
        key = (normalize_name(row['name_norm']), (row['state'] or '').strip())
        if key[0] and key[1]:
            osha_lookup[key] = row['naics_code'].strip()
            osha_count += 1
    print('    OSHA entries with NAICS: %d (unique keys: %d)' % (osha_count, len(osha_lookup)))

    # 3b: SAM entities - name + state -> naics_primary
    print('  Loading sam_entities...')
    cur.execute("""
        SELECT UPPER(TRIM(legal_business_name)) AS name_norm,
               UPPER(TRIM(physical_state)) AS state,
               naics_primary
        FROM sam_entities
        WHERE naics_primary IS NOT NULL
          AND naics_primary != ''
          AND legal_business_name IS NOT NULL
    """)
    sam_lookup = {}  # (norm_name, state) -> naics
    sam_count = 0
    for row in cur:
        key = (normalize_name(row['name_norm']), (row['state'] or '').strip())
        if key[0] and key[1]:
            sam_lookup[key] = row['naics_primary'].strip()
            sam_count += 1
    print('    SAM entries with NAICS: %d (unique keys: %d)' % (sam_count, len(sam_lookup)))

    # Also try SAM DBA names
    print('  Loading sam_entities DBA names...')
    cur.execute("""
        SELECT UPPER(TRIM(dba_name)) AS name_norm,
               UPPER(TRIM(physical_state)) AS state,
               naics_primary
        FROM sam_entities
        WHERE naics_primary IS NOT NULL
          AND naics_primary != ''
          AND dba_name IS NOT NULL
          AND dba_name != ''
    """)
    sam_dba_lookup = {}
    sam_dba_count = 0
    for row in cur:
        key = (normalize_name(row['name_norm']), (row['state'] or '').strip())
        if key[0] and key[1]:
            sam_dba_lookup[key] = row['naics_primary'].strip()
            sam_dba_count += 1
    print('    SAM DBA entries with NAICS: %d (unique keys: %d)' % (sam_dba_count, len(sam_dba_lookup)))

    # 3c: master_employers - name + state -> naics
    print('  Loading master_employers...')
    cur.execute("""
        SELECT UPPER(TRIM(display_name)) AS name_norm,
               UPPER(TRIM(state)) AS state,
               naics
        FROM master_employers
        WHERE naics IS NOT NULL
          AND naics != ''
          AND display_name IS NOT NULL
    """)
    master_lookup = {}  # (norm_name, state) -> naics
    master_count = 0
    for row in cur:
        key = (normalize_name(row['name_norm']), (row['state'] or '').strip())
        if key[0] and key[1]:
            master_lookup[key] = row['naics'].strip()
            master_count += 1
    print('    Master entries with NAICS: %d (unique keys: %d)' % (master_count, len(master_lookup)))

    # Also try canonical_name
    print('  Loading master_employers canonical names...')
    cur.execute("""
        SELECT UPPER(TRIM(canonical_name)) AS name_norm,
               UPPER(TRIM(state)) AS state,
               naics
        FROM master_employers
        WHERE naics IS NOT NULL
          AND naics != ''
          AND canonical_name IS NOT NULL
    """)
    master_canon_lookup = {}
    master_canon_count = 0
    for row in cur:
        key = (normalize_name(row['name_norm']), (row['state'] or '').strip())
        if key[0] and key[1]:
            master_canon_lookup[key] = row['naics'].strip()
            master_canon_count += 1
    print('    Master canonical entries with NAICS: %d (unique keys: %d)' % (
        master_canon_count, len(master_canon_lookup)))

    conn.close()

    # ------------------------------------------------------------------
    # Step 4: Match external sources
    # ------------------------------------------------------------------
    print()
    print('[4/5] Matching %d companies against external sources...' % len(needs_external))

    osha_matches = 0
    sam_matches = 0
    sam_dba_matches = 0
    master_matches = 0
    master_canon_matches = 0
    still_missing = 0

    for code in needs_external:
        info = companies[code]
        norm_name = normalize_name(info['name'])
        state = (info['state'] or '').strip().upper()

        if not norm_name or not state:
            still_missing += 1
            continue

        key = (norm_name, state)

        # Try OSHA first (most reliable NAICS source)
        if key in osha_lookup:
            recovery_mappings[code] = {
                'company_name': info['name'],
                'state': info['state'],
                'naics': osha_lookup[key],
                'source': 'osha_establishments',
                'source_detail': 'Matched by name+state',
                'years_recovered': list(info['years'].keys()),
            }
            osha_matches += 1
            continue

        # Try master_employers display_name
        if key in master_lookup:
            recovery_mappings[code] = {
                'company_name': info['name'],
                'state': info['state'],
                'naics': master_lookup[key],
                'source': 'master_employers',
                'source_detail': 'Matched by display_name+state',
                'years_recovered': list(info['years'].keys()),
            }
            master_matches += 1
            continue

        # Try master_employers canonical_name
        if key in master_canon_lookup:
            recovery_mappings[code] = {
                'company_name': info['name'],
                'state': info['state'],
                'naics': master_canon_lookup[key],
                'source': 'master_employers_canonical',
                'source_detail': 'Matched by canonical_name+state',
                'years_recovered': list(info['years'].keys()),
            }
            master_canon_matches += 1
            continue

        # Try SAM legal name
        if key in sam_lookup:
            recovery_mappings[code] = {
                'company_name': info['name'],
                'state': info['state'],
                'naics': sam_lookup[key],
                'source': 'sam_entities',
                'source_detail': 'Matched by legal_business_name+state',
                'years_recovered': list(info['years'].keys()),
            }
            sam_matches += 1
            continue

        # Try SAM DBA name
        if key in sam_dba_lookup:
            recovery_mappings[code] = {
                'company_name': info['name'],
                'state': info['state'],
                'naics': sam_dba_lookup[key],
                'source': 'sam_entities_dba',
                'source_detail': 'Matched by dba_name+state',
                'years_recovered': list(info['years'].keys()),
            }
            sam_dba_matches += 1
            continue

        still_missing += 1

    print()
    print('  External source matches:')
    print('    OSHA establishments:         %4d' % osha_matches)
    print('    Master employers (display):  %4d' % master_matches)
    print('    Master employers (canonical):%4d' % master_canon_matches)
    print('    SAM entities (legal name):   %4d' % sam_matches)
    print('    SAM entities (DBA name):     %4d' % sam_dba_matches)
    print('    Still missing:               %4d' % still_missing)
    total_external = osha_matches + sam_matches + sam_dba_matches + master_matches + master_canon_matches
    print('    Total external recovered:    %4d of %d' % (total_external, len(needs_external)))

    # ------------------------------------------------------------------
    # Step 5: Summary and save
    # ------------------------------------------------------------------
    print()
    print('[5/5] Summary and save...')
    print()
    print('=' * 70)
    print('NAICS RECOVERY RESULTS')
    print('=' * 70)
    print()
    print('Total unique company codes:            %5d' % len(companies))
    print('Already had NAICS in all years:        %5d' % len(has_all))
    print()
    print('--- Recovery ---')
    print('Cross-year backfill:                   %5d companies' % cross_year_count)
    print('OSHA establishments:                   %5d companies' % osha_matches)
    print('Master employers (display_name):       %5d companies' % master_matches)
    print('Master employers (canonical_name):     %5d companies' % master_canon_matches)
    print('SAM entities (legal_business_name):    %5d companies' % sam_matches)
    print('SAM entities (dba_name):               %5d companies' % sam_dba_matches)
    print('                                       -----')
    total_recovered = cross_year_count + total_external
    print('TOTAL RECOVERED:                       %5d companies' % total_recovered)
    print()
    print('Still missing NAICS:                   %5d companies' % still_missing)
    print()

    # Calculate row-level impact
    rows_with_naics_before = sum(1 for r in rows if (r.get('NAICS') or '').strip())
    rows_recoverable = 0
    for code, mapping in recovery_mappings.items():
        rows_recoverable += len(mapping.get('years_recovered', []))

    print('Row-level impact:')
    print('  Rows with NAICS before recovery:     %5d of %d (%.1f%%)' % (
        rows_with_naics_before, len(rows),
        100.0 * rows_with_naics_before / len(rows) if len(rows) > 0 else 0))
    print('  Rows recoverable:                    %5d' % rows_recoverable)
    print('  Rows with NAICS after recovery:      %5d of %d (%.1f%%)' % (
        rows_with_naics_before + rows_recoverable, len(rows),
        100.0 * (rows_with_naics_before + rows_recoverable) / len(rows) if len(rows) > 0 else 0))

    # Save mappings
    output = {
        'metadata': {
            'total_company_codes': len(companies),
            'had_naics_all_years': len(has_all),
            'cross_year_recovered': cross_year_count,
            'osha_recovered': osha_matches,
            'master_display_recovered': master_matches,
            'master_canonical_recovered': master_canon_matches,
            'sam_legal_recovered': sam_matches,
            'sam_dba_recovered': sam_dba_matches,
            'total_recovered': total_recovered,
            'still_missing': still_missing,
            'rows_before': rows_with_naics_before,
            'rows_recoverable': rows_recoverable,
            'rows_total': len(rows),
        },
        'recovery_by_source': {
            'cross_year_backfill': cross_year_count,
            'osha_establishments': osha_matches,
            'master_employers': master_matches,
            'master_employers_canonical': master_canon_matches,
            'sam_entities': sam_matches,
            'sam_entities_dba': sam_dba_matches,
        },
        'mappings': recovery_mappings,
    }

    output_path = os.path.join(os.path.dirname(__file__), 'recovered_naics_mappings.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=True)

    print()
    print('Saved recovery mappings to:')
    print('  %s' % os.path.abspath(output_path))
    print()
    print('  Total mappings: %d' % len(recovery_mappings))

    # Print a few examples from each source
    print()
    print('--- Sample recoveries ---')
    sources_seen = defaultdict(int)
    for code, m in sorted(recovery_mappings.items()):
        src = m['source']
        if sources_seen[src] < 3:
            print('  [%s] %s (%s) -> NAICS %s (via %s)' % (
                code, m['company_name'][:40], m['state'], m['naics'], src))
            sources_seen[src] += 1
        if all(v >= 3 for v in sources_seen.values()) and len(sources_seen) >= 4:
            break


if __name__ == '__main__':
    main()
