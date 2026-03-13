"""Debug script: investigate why M4c and M4d produce identical output to M4.

Root cause hypothesis:
- get_acs_by_occupation() returns the same data regardless of state_fips
  because the ACS occupation table may only store national data (state_fips='0').
- Top-10 vs top-30 may produce identical weighted averages when employment
  is heavily concentrated in top occupations.

This script picks 2 test companies and runs targeted diagnostics.

Usage:
    py scripts/analysis/demographics_comparison/debug_m4_family.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from data_loaders import (
    get_occupation_mix, get_acs_by_occupation, get_acs_race_nonhispanic_v2,
    get_lodes_race,
)
from methodologies import method_4_occupation_weighted, _build_occ_weighted
from methodologies_v3 import (
    method_4c_top10_occ, method_4d_state_top5_occ,
    _build_occ_weighted_topn, _build_state_top5_national_rest,
)

SCRIPT_DIR = os.path.dirname(__file__)
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def load_test_companies():
    """Pick 2 test companies that have BLS occupation data.

    We need NAICS codes that match bls_industry_occupation_matrix.
    Accommodation(721), Healthcare(621), Food Mfg(311) tend to have data.
    Falls back to iterating all companies and testing for occ_mix.
    """
    filepath = os.path.join(SCRIPT_DIR, 'selected_400.json')
    with open(filepath, 'r', encoding='utf-8') as f:
        companies = json.load(f)

    # Prefer NAICS groups with known BLS occupation data
    preferred_groups = [
        'Accommodation/Food Svc (72)',
        'Healthcare/Social (62)',
        'Food/Bev Manufacturing (311,312)',
        'Retail Trade (44-45)',
        'Construction (23)',
        'Admin/Staffing (56)',
        'Transportation/Warehousing (48-49)',
    ]

    selected = []
    for target_group in preferred_groups:
        if len(selected) >= 2:
            break
        for c in companies:
            group = c.get('classifications', {}).get('naics_group', '')
            if group == target_group:
                selected.append(c)
                break

    # Fallback: just pick first two
    while len(selected) < 2 and len(companies) > len(selected):
        selected.append(companies[len(selected)])

    return selected


def check_occupation_type_case(cur):
    """Check for case mismatch in occupation_type filter."""
    print('')
    print('=' * 80)
    print('OCCUPATION_TYPE CASE CHECK')
    print('=' * 80)

    cur.execute("SELECT DISTINCT occupation_type FROM bls_industry_occupation_matrix")
    types = cur.fetchall()
    actual_types = [r['occupation_type'] for r in types]
    print('Actual occupation_type values in DB: %s' % actual_types)

    code_filter = "'Line item'"
    print('Code filter value: %s' % code_filter)

    if actual_types and 'Line item' not in actual_types:
        print('')
        print('** CASE MISMATCH FOUND **')
        print('get_occupation_mix() queries: occupation_type = \'Line item\'')
        print('But DB contains: %s' % actual_types)
        print('This means get_occupation_mix() ALWAYS returns empty list!')
        print('ALL M4 variants (M4, M4c, M4d) hit the fallback path -> identical output.')
        print('')
        print('FIX: Update data_loaders.py get_occupation_mix() to use:')
        print("  occupation_type = '%s'" % actual_types[0])
        print('  OR use: LOWER(occupation_type) = \'line item\'')

        # Verify: check how many rows would match with correct case
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM bls_industry_occupation_matrix "
            "WHERE occupation_type = %s AND percent_of_industry IS NOT NULL",
            [actual_types[0]])
        correct_count = cur.fetchone()['cnt']
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM bls_industry_occupation_matrix "
            "WHERE occupation_type = 'Line item' AND percent_of_industry IS NOT NULL")
        wrong_count = cur.fetchone()['cnt']
        print('')
        print('Rows matching correct case (%s): %d' % (actual_types[0], correct_count))
        print('Rows matching wrong case (Line item): %d' % wrong_count)
        return True
    else:
        print('No case mismatch -- occupation_type = \'Line item\' matches.')
        return False


def analyze_company(cur, company, case_mismatch=False):
    """Run full M4 family diagnostics for one company."""
    name = company.get('name', 'Unknown')
    naics = company.get('naics', '')
    naics4 = naics[:4]
    state_fips = company.get('state_fips', '')
    county_fips = company.get('county_fips', '')
    group = company.get('classifications', {}).get('naics_group', '')

    print('')
    print('=' * 80)
    print('COMPANY: %s' % name)
    print('NAICS: %s  Group: %s  State FIPS: %s  County FIPS: %s' % (
        naics, group, state_fips, county_fips))
    print('=' * 80)

    # 1. Get full occupation mix (using standard function)
    occ_mix = get_occupation_mix(cur, naics4)

    # If case mismatch, also try with correct case
    if not occ_mix and case_mismatch:
        print('  Standard get_occupation_mix returned empty (case mismatch bug)')
        # Manual query with correct case
        for code in [naics4, naics4 + '00', naics4[:3] + '000', naics4[:2] + '0000']:
            cur.execute(
                "SELECT occupation_code, percent_of_industry "
                "FROM bls_industry_occupation_matrix "
                "WHERE industry_code = %s AND LOWER(occupation_type) = 'line item' "
                "AND percent_of_industry IS NOT NULL "
                "ORDER BY percent_of_industry DESC",
                [code])
            rows = cur.fetchall()
            if rows:
                occ_mix = [(r['occupation_code'], float(r['percent_of_industry'])) for r in rows]
                print('  FOUND %d occupations with corrected query (code=%s)' % (len(occ_mix), code))
                break

    if not occ_mix:
        print('  NO OCCUPATION MIX DATA -- M4 family will use fallback')
        return

    print('')
    print('OCCUPATION MIX (%d occupations total):' % len(occ_mix))
    print('  %-12s  %6s  %s' % ('SOC Code', 'Pct', 'Cumulative'))
    cumulative = 0.0
    for i, (soc, pct) in enumerate(occ_mix[:30]):
        cumulative += pct
        marker = ' <-- top-10 boundary' if i == 9 else ''
        print('  %-12s  %5.1f%%  %5.1f%%%s' % (soc, pct, cumulative, marker))

    # 2. Compare state vs national ACS for each occupation
    print('')
    print('STATE vs NATIONAL ACS BY OCCUPATION (race):')
    print('  %-12s  %-8s  %-8s  %s' % ('SOC', 'State', 'National', 'Same?'))

    state_none_count = 0
    national_none_count = 0
    identical_count = 0

    for soc, pct in occ_mix[:15]:
        state_demo = get_acs_by_occupation(cur, soc, state_fips, 'race')
        national_demo = get_acs_by_occupation(cur, soc, '0', 'race')

        state_str = 'None' if state_demo is None else '%.1f%%W' % state_demo.get('White', 0)
        national_str = 'None' if national_demo is None else '%.1f%%W' % national_demo.get('White', 0)

        if state_demo is None:
            state_none_count += 1
        if national_demo is None:
            national_none_count += 1

        same = 'N/A'
        if state_demo and national_demo:
            diffs = [abs(state_demo.get(k, 0) - national_demo.get(k, 0)) for k in RACE_CATS]
            max_diff = max(diffs) if diffs else 0
            if max_diff < 0.01:
                same = 'IDENTICAL'
                identical_count += 1
            else:
                same = 'diff=%.2f' % max_diff
        elif state_demo is None and national_demo is not None:
            same = 'STATE_MISSING'
        elif state_demo is not None and national_demo is None:
            same = 'NATIONAL_MISSING'

        print('  %-12s  %-8s  %-8s  %s' % (soc, state_str, national_str, same))

    print('')
    print('  State None: %d/%d  National None: %d/%d  Identical: %d' % (
        state_none_count, min(15, len(occ_mix)),
        national_none_count, min(15, len(occ_mix)),
        identical_count))

    # 3. Build weighted estimates at different top-N levels
    print('')
    print('WEIGHTED ESTIMATES BY TOP-N (race, White %%):')
    for top_n in [5, 10, 15, 20, 30]:
        result = _build_occ_weighted_topn(cur, occ_mix, state_fips, 'race', RACE_CATS, top_n=top_n)
        if result:
            print('  Top-%2d: White=%.2f  Black=%.2f  Asian=%.2f' % (
                top_n, result.get('White', 0), result.get('Black', 0), result.get('Asian', 0)))
        else:
            print('  Top-%2d: None' % top_n)

    # 4. Run M4, M4c, M4d and compare outputs
    print('')
    print('METHOD OUTPUTS (race):')
    m4_result = method_4_occupation_weighted(cur, naics4, state_fips, county_fips)
    m4c_result = method_4c_top10_occ(cur, naics4, state_fips, county_fips)
    m4d_result = method_4d_state_top5_occ(cur, naics4, state_fips, county_fips)

    for label, result in [('M4 ', m4_result), ('M4c', m4c_result), ('M4d', m4d_result)]:
        race = result.get('race') if result else None
        if race:
            vals = '  '.join('%s=%.2f' % (k, race.get(k, 0)) for k in RACE_CATS)
            print('  %s: %s' % (label, vals))
        else:
            print('  %s: None' % label)

    # Check if identical
    if m4_result and m4c_result and m4d_result:
        m4_race = m4_result.get('race', {})
        m4c_race = m4c_result.get('race', {})
        m4d_race = m4d_result.get('race', {})

        m4_vs_m4c = max(abs(m4_race.get(k, 0) - m4c_race.get(k, 0)) for k in RACE_CATS)
        m4_vs_m4d = max(abs(m4_race.get(k, 0) - m4d_race.get(k, 0)) for k in RACE_CATS)
        m4c_vs_m4d = max(abs(m4c_race.get(k, 0) - m4d_race.get(k, 0)) for k in RACE_CATS)

        print('')
        print('  Max category diff M4 vs M4c: %.4f %s' % (
            m4_vs_m4c, '** IDENTICAL **' if m4_vs_m4c < 0.01 else ''))
        print('  Max category diff M4 vs M4d: %.4f %s' % (
            m4_vs_m4d, '** IDENTICAL **' if m4_vs_m4d < 0.01 else ''))
        print('  Max category diff M4c vs M4d: %.4f %s' % (
            m4c_vs_m4d, '** IDENTICAL **' if m4c_vs_m4d < 0.01 else ''))

    # 5. Occupation concentration analysis
    print('')
    print('OCCUPATION CONCENTRATION:')
    total_pct = sum(pct for _, pct in occ_mix)
    top10_pct = sum(pct for _, pct in occ_mix[:10])
    top5_pct = sum(pct for _, pct in occ_mix[:5])
    print('  Top 5: %.1f%%  Top 10: %.1f%%  Total (%d occs): %.1f%%' % (
        top5_pct, top10_pct, len(occ_mix), total_pct))


def main():
    companies = load_test_companies()

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # First check for occupation_type case mismatch
    case_mismatch = check_occupation_type_case(cur)

    for company in companies:
        analyze_company(cur, company, case_mismatch=case_mismatch)

    # Summary diagnosis
    print('')
    print('=' * 80)
    print('ROOT CAUSE DIAGNOSIS')
    print('=' * 80)
    print('''
If most state-level ACS occupation queries return the same data as national,
then M4d's state/national split produces the same weighted average as M4.

If top-10 occupations cover 80%+ of employment, then M4c's top-10 trim
produces nearly identical weighted averages as M4's top-30.

Both conditions together explain why M4 = M4c = M4d.

IMPLICATION FOR V4: M4e (Demographic-Variance Occupation Trim) should
differ from M4 because it FILTERS occupations based on demographic
deviation, not just employment share. This changes which occupations
contribute, not just how many.
''')

    conn.close()


if __name__ == '__main__':
    main()
