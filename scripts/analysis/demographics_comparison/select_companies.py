"""Scan EEO-1 data, filter candidates, group by 7 benchmark axes.

Filters:
1. Single-unit: COMPANY code appears only once per YEAR
2. NAICS present
3. TOTAL10 >= 100
4. ZIP resolves to a county with LODES data
5. ACS has data for the NAICS prefix + state
6. Prefer FY2020, else FY2019

Outputs candidates grouped by 7 benchmark axes for user review.
"""
import sys
import os
import csv
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

from config import EEO1_CSV
from eeo1_parser import _safe_int


# State abbreviation -> FIPS mapping
STATE_FIPS = {
    'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06',
    'CO': '08', 'CT': '09', 'DE': '10', 'DC': '11', 'FL': '12',
    'GA': '13', 'HI': '15', 'ID': '16', 'IL': '17', 'IN': '18',
    'IA': '19', 'KS': '20', 'KY': '21', 'LA': '22', 'ME': '23',
    'MD': '24', 'MA': '25', 'MI': '26', 'MN': '27', 'MS': '28',
    'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33',
    'NJ': '34', 'NM': '35', 'NY': '36', 'NC': '37', 'ND': '38',
    'OH': '39', 'OK': '40', 'OR': '41', 'PA': '42', 'PR': '72',
    'RI': '44', 'SC': '45', 'SD': '46', 'TN': '47', 'TX': '48',
    'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53', 'WV': '54',
    'WI': '55', 'WY': '56',
}

# Benchmark axes with target NAICS prefixes
AXES = {
    1: {
        'label': 'Industry signal dominates',
        'desc': 'Nursing home, defense mfg',
        'naics_targets': ['6231', '3364', '6111', '2111'],
    },
    2: {
        'label': 'Geography signal dominates',
        'desc': 'Warehouse, food processing, hotel',
        'naics_targets': ['493', '3116', '7211', '4931', '4441'],
    },
    3: {
        'label': 'Demographic stratification',
        'desc': 'Large hotel/hospital',
        'naics_targets': ['7211', '622', '6221', '7224'],
        'min_size': 500,
    },
    4: {
        'label': 'Size extremes',
        'desc': 'One 100-200 and one 1000+',
        'naics_targets': [],  # any
    },
    5: {
        'label': 'Geography edge cases',
        'desc': 'Majority-minority or rural county',
        'naics_targets': [],  # any
    },
    6: {
        'label': 'Known hard case',
        'desc': 'Staffing agency (expected failure)',
        'naics_targets': ['5613', '56131', '56132'],
    },
    7: {
        'label': 'In organizing universe',
        'desc': 'Cross-ref with existing targets',
        'naics_targets': [],  # any
    },
}


def load_and_filter(csv_path=None):
    """Load EEO-1 CSV, apply base filters, return filtered rows."""
    csv_path = csv_path or EEO1_CSV
    print('Loading EEO-1 data from %s ...' % csv_path)

    rows = []
    with open(csv_path, 'r', encoding='cp1252') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print('  Total rows: %d' % len(rows))

    # Count companies per year to find single-unit
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

        # Filter 1: Single-unit
        if company_year_counts.get((company, str(year)), 0) > 1:
            continue

        # Filter 2: NAICS present
        if not naics or len(naics) < 2:
            continue

        # Filter 3: TOTAL10 >= 100
        if total < 100:
            continue

        # Filter 4: ZIP present
        if not zipcode or len(zipcode) < 5:
            continue

        # Prefer 2020, accept 2019
        if year not in (2020, 2019, 2018):
            continue

        filtered.append(row)

    print('  After base filters (single-unit, NAICS, size>=100, ZIP, year): %d' % len(filtered))

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


def check_data_availability(rows, cur):
    """Check which candidates have LODES + ACS data available."""
    valid = []
    skip_lodes = 0
    skip_acs = 0

    for i, row in enumerate(rows):
        if i % 500 == 0 and i > 0:
            print('  Checked %d/%d ...' % (i, len(rows)))

        zipcode = (row.get('ZIPCODE') or '').strip()[:5]
        naics = (row.get('NAICS') or '').strip()
        state = (row.get('STATE') or '').strip()
        state_fips = STATE_FIPS.get(state, '')

        # Resolve ZIP -> county
        cur.execute(
            "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
            [zipcode])
        county_row = cur.fetchone()
        if not county_row:
            skip_lodes += 1
            continue
        county_fips = county_row['county_fips']

        # Check LODES
        cur.execute(
            "SELECT demo_total_jobs FROM cur_lodes_geo_metrics WHERE county_fips = %s",
            [county_fips])
        lodes_row = cur.fetchone()
        if not lodes_row or float(lodes_row['demo_total_jobs'] or 0) == 0:
            skip_lodes += 1
            continue

        # Check ACS (try NAICS4 or 2-digit)
        naics4 = naics[:4]
        if not state_fips:
            state_fips = county_fips[:2]
        has_acs = False
        for n in [naics4, naics[:2]]:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM cur_acs_workforce_demographics "
                "WHERE naics4 = %s AND state_fips = %s AND sex IN ('1','2')",
                [n, state_fips])
            if cur.fetchone()['cnt'] > 0:
                has_acs = True
                break
        if not has_acs:
            skip_acs += 1
            continue

        # Store resolved fields
        row['_county_fips'] = county_fips
        row['_state_fips'] = state_fips
        row['_naics4'] = naics4
        row['_lodes_jobs'] = float(lodes_row['demo_total_jobs'])
        valid.append(row)

    print('  Skipped (no LODES): %d' % skip_lodes)
    print('  Skipped (no ACS): %d' % skip_acs)
    print('  Valid candidates: %d' % len(valid))
    return valid


def classify_by_axis(candidates, cur):
    """Classify candidates into benchmark axes."""
    axis_candidates = defaultdict(list)

    # Check for majority-minority counties (axis 5)
    minority_counties = set()
    cur.execute("""
        SELECT county_fips FROM cur_lodes_geo_metrics
        WHERE pct_minority > 0.50 AND demo_total_jobs > 100
    """)
    for r in cur.fetchall():
        minority_counties.add(r['county_fips'])

    # Check for existing targets (axis 7) -- optional, skip if table doesn't exist
    target_eins = set()
    try:
        cur.execute("SELECT DISTINCT ein FROM master_employers WHERE ein IS NOT NULL LIMIT 50000")
        for r in cur.fetchall():
            target_eins.add(r['ein'])
    except Exception:
        pass

    for row in candidates:
        naics = (row.get('NAICS') or '').strip()
        total = _safe_int(row.get('TOTAL10', 0))
        county = row.get('_county_fips', '')
        name = (row.get('CONAME') or row.get('NAME', '')).strip()

        info = {
            'row': row,
            'name': name,
            'naics': naics,
            'state': row.get('STATE', ''),
            'total': total,
            'county_fips': county,
            'company': row.get('COMPANY', ''),
            'year': _safe_int(row.get('YEAR', 0)),
            'zipcode': (row.get('ZIPCODE') or '').strip(),
        }

        # Axis 1: Industry signal dominant
        for prefix in AXES[1]['naics_targets']:
            if naics.startswith(prefix):
                axis_candidates[1].append(info)
                break

        # Axis 2: Geography signal dominant
        for prefix in AXES[2]['naics_targets']:
            if naics.startswith(prefix):
                axis_candidates[2].append(info)
                break

        # Axis 3: Demographic stratification (large companies in service industries)
        if total >= 500:
            for prefix in AXES[3]['naics_targets']:
                if naics.startswith(prefix):
                    axis_candidates[3].append(info)
                    break

        # Axis 4: Size extremes
        if total >= 100 and total <= 200:
            info_copy = dict(info)
            info_copy['_size_label'] = 'small (100-200)'
            axis_candidates[4].append(info_copy)
        elif total >= 1000:
            info_copy = dict(info)
            info_copy['_size_label'] = 'large (1000+)'
            axis_candidates[4].append(info_copy)

        # Axis 5: Geography edge cases
        if county in minority_counties:
            info_copy = dict(info)
            info_copy['_geo_label'] = 'majority-minority county'
            axis_candidates[5].append(info_copy)

        # Axis 6: Staffing agencies
        for prefix in AXES[6]['naics_targets']:
            if naics.startswith(prefix):
                axis_candidates[6].append(info)
                break

        # Axis 7: In organizing universe
        duns = (row.get('DUNS') or '').strip()
        if duns and duns in target_eins:
            axis_candidates[7].append(info)

    return axis_candidates


def print_candidates(axis_candidates):
    """Print candidates grouped by axis for user review."""
    print('')
    print('=' * 78)
    print('EEO-1 COMPANY CANDIDATES BY BENCHMARK AXIS')
    print('=' * 78)

    for axis_num in sorted(AXES.keys()):
        axis = AXES[axis_num]
        cands = axis_candidates.get(axis_num, [])
        print('')
        print('AXIS %d: %s' % (axis_num, axis.get('label', '')))
        print('  %s' % axis.get('desc', ''))
        print('  Candidates: %d' % len(cands))
        print('-' * 78)

        # Sort by total descending, show top 10
        cands.sort(key=lambda c: c['total'], reverse=True)
        for i, c in enumerate(cands[:10]):
            extra = ''
            if '_size_label' in c:
                extra = ' [%s]' % c['_size_label']
            if '_geo_label' in c:
                extra = ' [%s]' % c['_geo_label']
            print('  %2d. %-35s %s  NAICS=%s  N=%d  %s%s' % (
                i + 1,
                c['name'][:35],
                c['state'],
                c['naics'][:6],
                c['total'],
                c['company'],
                extra,
            ))

    print('')
    print('=' * 78)
    print('INSTRUCTIONS:')
    print('  1. Review candidates above')
    print('  2. Pick ~10 companies covering all 7 axes')
    print('  3. Update config.py VALIDATION_COMPANIES with selected companies')
    print('  4. Run: py scripts/analysis/demographics_comparison/run_comparison.py')
    print('=' * 78)


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Load and filter
    rows = load_and_filter()

    # Step 2: Check data availability
    print('')
    print('Checking data availability (LODES + ACS) ...')
    candidates = check_data_availability(rows, cur)

    # Step 3: Classify by axis
    print('')
    print('Classifying by benchmark axes ...')
    axis_candidates = classify_by_axis(candidates, cur)

    # Step 4: Print for user review
    print_candidates(axis_candidates)

    # Summary stats
    all_naics = defaultdict(int)
    for c in candidates:
        all_naics[c.get('NAICS', '')[:2]] += 1
    print('')
    print('NAICS sector distribution of valid candidates:')
    for naics, count in sorted(all_naics.items(), key=lambda x: -x[1])[:15]:
        print('  %s: %d' % (naics, count))

    conn.close()


if __name__ == '__main__':
    main()
