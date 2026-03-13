"""V9 Quick Test: Expert G Two+ Clamp & D+G Blend Re-evaluation.

Clamps Expert G's Two+ predictions using county ACS data, then re-runs
the D+G blend to see if it beats V8 post-calibration.

Usage:
    py test_g_clamp_blend.py --holdout selected_permanent_holdout_1000.json
"""
import sys
import os
import json
import math
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from classifiers import classify_naics_group
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_method_v6_full, cached_expert_e, cached_expert_f, cached_expert_g,
)
from cached_loaders_v5 import cached_method_3c_v5, cached_expert_a, cached_expert_b
from methodologies_v5 import RACE_CATS
from config import get_census_region, get_county_minority_tier

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']
NATIONAL_TWO_PLUS = 3.5  # national average Two+ %


def clamp_two_plus(g_race, county_two_plus_pct):
    """Clamp Expert G's Two+ to max 2x the county rate, redistribute excess."""
    if not g_race:
        return g_race

    cap = county_two_plus_pct * 2.0 if county_two_plus_pct is not None else NATIONAL_TWO_PLUS * 2.0
    g_two = g_race.get('Two+', 0)

    if g_two <= cap:
        return dict(g_race)  # no clamping needed

    excess = g_two - cap
    clamped = dict(g_race)
    clamped['Two+'] = cap

    # Redistribute excess proportionally to other categories
    others = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI']
    others_total = sum(clamped.get(c, 0) for c in others)
    if others_total > 0:
        for c in others:
            share = clamped.get(c, 0) / others_total
            clamped[c] = clamped.get(c, 0) + excess * share
    else:
        # fallback: give excess to White
        clamped['White'] = clamped.get('White', 0) + excess

    return clamped


def build_blend(d_race, g_race_clamped):
    """D for White/Asian/AIAN/NHOPI/Two+, G (clamped) for Black only."""
    blended = {
        'White': d_race.get('White', 0),
        'Asian': d_race.get('Asian', 0),
        'AIAN': d_race.get('AIAN', 0),
        'NHOPI': d_race.get('NHOPI', 0),
        'Two+': d_race.get('Two+', 0),
        'Black': g_race_clamped.get('Black', 0),
    }
    # Normalize to 100
    total = sum(blended.values())
    if total > 0 and abs(total - 100.0) > 0.01:
        for c in blended:
            blended[c] = blended[c] * 100.0 / total
    return blended


def mae_cats(pred, actual, cats):
    errors = []
    for c in cats:
        if c in pred and c in actual:
            errors.append(abs(pred[c] - actual[c]))
    return sum(errors) / len(errors) if errors else None


def max_cat_error(pred, actual, cats):
    errors = []
    for c in cats:
        if c in pred and c in actual:
            errors.append(abs(pred[c] - actual[c]))
    return max(errors) if errors else None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--holdout', default='selected_permanent_holdout_1000.json')
    args = parser.parse_args()

    t0 = time.time()
    print('V9 TWO+ CLAMP TEST')
    print('=' * 70)

    holdout_path = os.path.join(SCRIPT_DIR, args.holdout)
    with open(holdout_path) as f:
        holdout_data = json.load(f)
    companies = holdout_data if isinstance(holdout_data, list) else holdout_data.get('companies', [])
    print('Holdout: %s (%d companies)' % (args.holdout, len(companies)))

    print('Loading EEO-1...')
    eeo1_rows = load_all_eeo1_data()
    eeo1_by_code = {}
    for row in eeo1_rows:
        code = (row.get('COMPANY') or '').strip()
        if code:
            eeo1_by_code.setdefault(code, []).append(row)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Collect per-company data for all scenarios
    all_company_data = []

    for i, company in enumerate(companies):
        if (i + 1) % 50 == 0:
            print('  %d/%d (%.0fs)...' % (i + 1, len(companies), time.time() - t0))

        code = company['company_code']
        naics = company.get('naics', '')
        naics4 = naics[:4]
        state_fips = company.get('state_fips', '')
        county_fips = company.get('county_fips', '')
        zipcode = company.get('zipcode', '')
        state_abbr = company.get('state', '')

        if not county_fips or not state_fips:
            continue

        eeo1_list = eeo1_by_code.get(code, [])
        if not eeo1_list:
            continue
        truth = parse_eeo1_row(eeo1_list[0])
        if not truth or not truth.get('race'):
            continue

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic')
        actual_gender = truth.get('gender')

        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', classify_naics_group(naics4))
        region = get_census_region(state_abbr)
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race:
            county_minority_pct = 100.0 - lodes_race.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        # Get county-level Two+ rate from ACS tract data
        # Use LODES race data which has Two+ from census
        county_two_plus = None
        if lodes_race and 'Two+' in lodes_race:
            county_two_plus = lodes_race['Two+']
        elif lodes_race and 'Multiracial' in lodes_race:
            county_two_plus = lodes_race['Multiracial']

        # Run Expert D
        try:
            d_result = cached_method_3c_v5(cl, naics4, state_fips, county_fips)
        except Exception:
            d_result = None

        # Run Expert G
        try:
            g_result = cached_expert_g(cl, naics4, state_fips, county_fips,
                                       cbsa_code=cbsa_code, zipcode=zipcode,
                                       naics_group=naics_group)
        except Exception:
            g_result = None

        if not d_result or not d_result.get('race'):
            continue
        if not g_result or not g_result.get('race'):
            continue

        d_race = d_result['race']
        g_race_raw = g_result['race']

        # Clamp G's Two+
        g_race_clamped = clamp_two_plus(g_race_raw, county_two_plus)

        # Build blends
        blend_raw = build_blend(d_race, g_race_raw)
        blend_clamped = build_blend(d_race, g_race_clamped)

        all_company_data.append({
            'code': code,
            'naics_group': naics_group,
            'region': region,
            'county_tier': county_tier,
            'state': state_abbr,
            'actual_race': actual_race,
            'actual_hisp': actual_hisp,
            'actual_gender': actual_gender,
            'd_race': d_race,
            'g_race_raw': g_race_raw,
            'g_race_clamped': g_race_clamped,
            'blend_raw': blend_raw,
            'blend_clamped': blend_clamped,
            'd_hisp': d_result.get('hispanic'),
            'g_hisp': g_result.get('hispanic'),
            'd_gender': d_result.get('gender'),
            'g_gender': g_result.get('gender'),
            'county_two_plus': county_two_plus,
        })

    n = len(all_company_data)
    print('\nProcessed %d companies in %.0fs' % (n, time.time() - t0))

    # ================================================================
    # STEP 2 CHECKPOINT: Sample 5 companies
    # ================================================================
    print()
    print('=' * 70)
    print('STEP 2: Sample Companies (raw G vs D vs truth)')
    print('=' * 70)
    print()

    # Pick 5 companies with visible Two+ over-prediction
    samples = sorted(all_company_data, key=lambda x: x['g_race_raw'].get('Two+', 0), reverse=True)[:5]
    for s in samples:
        print('Company %s (%s, %s)' % (s['code'], s['naics_group'], s['region']))
        print('  %-8s %8s %8s %8s %8s' % ('Cat', 'Truth', 'D', 'G raw', 'G clamp'))
        for cat in RACE_CATS:
            t_val = s['actual_race'].get(cat, 0)
            d_val = s['d_race'].get(cat, 0)
            g_raw = s['g_race_raw'].get(cat, 0)
            g_clamp = s['g_race_clamped'].get(cat, 0)
            print('  %-8s %8.1f %8.1f %8.1f %8.1f' % (cat, t_val, d_val, g_raw, g_clamp))
        g_sum = sum(s['g_race_clamped'].get(c, 0) for c in RACE_CATS)
        print('  Sum check (clamped G): %.1f' % g_sum)
        print()

    # ================================================================
    # STEP 4 CHECKPOINT: Sample 5 with blend
    # ================================================================
    print('=' * 70)
    print('STEP 4: Sample Companies (blend comparison)')
    print('=' * 70)
    print()

    # Pick 5 diverse companies
    samples2 = []
    seen_groups = set()
    for s in all_company_data:
        key = s['naics_group']
        if key not in seen_groups and len(samples2) < 5:
            samples2.append(s)
            seen_groups.add(key)

    for s in samples2:
        print('Company %s (%s, %s)' % (s['code'], s['naics_group'][:35], s['region']))
        print('  %-8s %8s %8s %8s %8s %8s' % ('Cat', 'Truth', 'D solo', 'Bld raw', 'Bld clmp', 'Diff'))
        for cat in RACE_CATS:
            t_val = s['actual_race'].get(cat, 0)
            d_val = s['d_race'].get(cat, 0)
            br = s['blend_raw'].get(cat, 0)
            bc = s['blend_clamped'].get(cat, 0)
            diff = bc - t_val
            print('  %-8s %8.1f %8.1f %8.1f %8.1f %+8.1f' % (cat, t_val, d_val, br, bc, diff))
        bc_sum = sum(s['blend_clamped'].get(c, 0) for c in RACE_CATS)
        print('  Blend clamped sum: %.1f' % bc_sum)
        print()

    # ================================================================
    # STEP 5: Full evaluation
    # ================================================================
    print('=' * 70)
    print('STEP 5: Full Evaluation on Permanent Holdout')
    print('=' * 70)
    print()

    # Compute metrics for each scenario
    scenarios = {
        'D solo': lambda c: c['d_race'],
        'G solo': lambda c: c['g_race_raw'],
        'G clamped': lambda c: c['g_race_clamped'],
        'D+G raw': lambda c: c['blend_raw'],
        'D+G clamp': lambda c: c['blend_clamped'],
    }

    print('%-14s %9s %9s %9s %9s %9s %9s' % (
        'Scenario', 'Race MAE', 'Black MAE', 'Hisp MAE', 'P>20pp', 'P>30pp', 'Abs Bias'))
    print('-' * 75)

    scenario_data = {}
    for name, get_pred in scenarios.items():
        race_maes = []
        max_errors = []
        black_abs_errors = []
        signed_white = []
        signed_black = []
        hisp_maes = []

        for c in all_company_data:
            pred = get_pred(c)
            actual = c['actual_race']

            m = mae_cats(pred, actual, RACE_CATS)
            mx = max_cat_error(pred, actual, RACE_CATS)
            if m is not None:
                race_maes.append(m)
            if mx is not None:
                max_errors.append(mx)

            # Black MAE
            if 'Black' in pred and 'Black' in actual:
                black_abs_errors.append(abs(pred['Black'] - actual['Black']))

            # Signed bias
            if 'White' in pred and 'White' in actual:
                signed_white.append(pred['White'] - actual['White'])
            if 'Black' in pred and 'Black' in actual:
                signed_black.append(pred['Black'] - actual['Black'])

            # Hispanic (use G for G-related, D for D-related)
            if name in ('G solo', 'G clamped'):
                h_pred = c['g_hisp']
            elif name in ('D+G raw', 'D+G clamp'):
                h_pred = c['g_hisp']  # G for Hispanic in blend
            else:
                h_pred = c['d_hisp']
            if h_pred and c['actual_hisp']:
                hm = mae_cats(h_pred, c['actual_hisp'], HISP_CATS)
                if hm is not None:
                    hisp_maes.append(hm)

        race_mae = sum(race_maes) / len(race_maes) if race_maes else 0
        black_mae = sum(black_abs_errors) / len(black_abs_errors) if black_abs_errors else 0
        hisp_mae = sum(hisp_maes) / len(hisp_maes) if hisp_maes else 0
        p20 = sum(1 for e in max_errors if e > 20) / len(max_errors) * 100 if max_errors else 0
        p30 = sum(1 for e in max_errors if e > 30) / len(max_errors) * 100 if max_errors else 0
        w_bias = sum(signed_white) / len(signed_white) if signed_white else 0
        b_bias = sum(signed_black) / len(signed_black) if signed_black else 0
        abs_bias = (abs(w_bias) + abs(b_bias)) / 2

        print('%-14s %9.3f %9.3f %9.3f %8.1f%% %8.1f%% %9.3f' % (
            name, race_mae, black_mae, hisp_mae, p20, p30, abs_bias))

        scenario_data[name] = {
            'race_maes': race_maes, 'max_errors': max_errors,
            'black_abs': black_abs_errors,
        }

    print()
    print('V8 post-cal reference: Race MAE=4.526, Hisp=7.111, P>20=16.1%%, P>30=7.9%%')

    # ================================================================
    # Regional breakdown
    # ================================================================
    print()
    print('=' * 70)
    print('PER-REGION RACE MAE')
    print('=' * 70)
    print()

    regions = ['South', 'West', 'Northeast', 'Midwest']
    print('%-14s' + ' %10s' * len(regions) % tuple(regions))
    print('-' * 54)

    for name, get_pred in scenarios.items():
        if name in ('G solo', 'G clamped'):
            continue  # skip G solo for brevity
        vals = []
        for region in regions:
            errs = []
            for c in all_company_data:
                if c['region'] == region:
                    m = mae_cats(get_pred(c), c['actual_race'], RACE_CATS)
                    if m is not None:
                        errs.append(m)
            vals.append('%.3f' % (sum(errs) / len(errs)) if errs else '--')
        print('%-14s' + ' %10s' * len(vals) % tuple(vals))

    # Region N counts
    vals = []
    for region in regions:
        cnt = sum(1 for c in all_company_data if c['region'] == region)
        vals.append('N=%d' % cnt)
    print('%-14s' % '' + ' %10s' * len(vals) % tuple(vals))

    # ================================================================
    # Per-sector breakdown
    # ================================================================
    print()
    print('=' * 70)
    print('PER-SECTOR RACE MAE (key sectors)')
    print('=' * 70)
    print()

    sectors = ['Healthcare/Social (62)', 'Admin/Staffing (56)', 'Finance/Insurance (52)',
               'Professional/Technical (54)', 'Construction (23)']
    print('%-14s' + ''.join(' %8s' for _ in sectors))
    header_sectors = tuple(s.split(' (')[0][:8] for s in sectors)
    print('%-14s' + ' %8s' * len(header_sectors) % header_sectors)
    print('-' * (14 + 9 * len(sectors)))

    for name, get_pred in scenarios.items():
        if name in ('G solo', 'G clamped'):
            continue
        vals = []
        for sector in sectors:
            errs = []
            for c in all_company_data:
                if c['naics_group'] == sector:
                    m = mae_cats(get_pred(c), c['actual_race'], RACE_CATS)
                    if m is not None:
                        errs.append(m)
            vals.append('%.2f' % (sum(errs) / len(errs)) if errs else '--')
        print('%-14s' + ' %8s' * len(vals) % tuple(vals))

    # Sector N counts
    vals = []
    for sector in sectors:
        cnt = sum(1 for c in all_company_data if c['naics_group'] == sector)
        vals.append('N=%d' % cnt)
    print('%-14s' % '' + ' %8s' * len(vals) % tuple(vals))

    # ================================================================
    # Per-category absolute error comparison
    # ================================================================
    print()
    print('=' * 70)
    print('PER-CATEGORY ABSOLUTE ERROR')
    print('=' * 70)
    print()

    print('%-14s' + ' %8s' * 6 % tuple(RACE_CATS))
    print('-' * (14 + 9 * 6))

    for name, get_pred in scenarios.items():
        vals = []
        for cat in RACE_CATS:
            errs = []
            for c in all_company_data:
                pred = get_pred(c)
                if cat in pred and cat in c['actual_race']:
                    errs.append(abs(pred[cat] - c['actual_race'][cat]))
            vals.append('%.2f' % (sum(errs) / len(errs)) if errs else '--')
        print('%-14s' + ' %8s' * len(vals) % tuple(vals))

    # ================================================================
    # Signed bias comparison
    # ================================================================
    print()
    print('=' * 70)
    print('SIGNED BIAS (pred - actual)')
    print('=' * 70)
    print()

    print('%-14s' + ' %8s' * 6 % tuple(RACE_CATS))
    print('-' * (14 + 9 * 6))

    for name, get_pred in scenarios.items():
        vals = []
        for cat in RACE_CATS:
            errs = []
            for c in all_company_data:
                pred = get_pred(c)
                if cat in pred and cat in c['actual_race']:
                    errs.append(pred[cat] - c['actual_race'][cat])
            vals.append('%+.2f' % (sum(errs) / len(errs)) if errs else '--')
        print('%-14s' + ' %8s' * len(vals) % tuple(vals))

    # ================================================================
    # Error distribution
    # ================================================================
    print()
    print('=' * 70)
    print('ERROR DISTRIBUTION (max error per company)')
    print('=' * 70)
    print()

    buckets = [(0, 1), (1, 3), (3, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 999)]
    labels = ['0-1', '1-3', '3-5', '5-10', '10-15', '15-20', '20-30', '>30']

    print('%-14s' + ' %7s' * len(labels) % tuple(labels))
    print('-' * (14 + 8 * len(labels)))

    for name, get_pred in scenarios.items():
        errors = []
        for c in all_company_data:
            mx = max_cat_error(get_pred(c), c['actual_race'], RACE_CATS)
            if mx is not None:
                errors.append(mx)
        total = len(errors)
        vals = []
        for lo, hi in buckets:
            if hi == 999:
                cnt = sum(1 for e in errors if e > lo)
            else:
                cnt = sum(1 for e in errors if lo < e <= hi or (lo == 0 and e <= hi))
            vals.append('%.1f%%' % (cnt / total * 100) if total else '--')
        print('%-14s' + ' %7s' * len(vals) % tuple(vals))

    # ================================================================
    # STEP 6: Worst 10 companies in D+G clamped blend
    # ================================================================
    print()
    print('=' * 70)
    print('STEP 6: 10 Worst Companies in D+G Clamped Blend')
    print('=' * 70)
    print()

    company_errors = []
    for c in all_company_data:
        pred = c['blend_clamped']
        actual = c['actual_race']
        cat_signed = {}
        for cat in RACE_CATS:
            if cat in pred and cat in actual:
                cat_signed[cat] = pred[cat] - actual[cat]
        if cat_signed:
            worst_cat = max(cat_signed, key=lambda k: abs(cat_signed[k]))
            company_errors.append({
                'code': c['code'],
                'naics_group': c['naics_group'],
                'region': c['region'],
                'state': c['state'],
                'max_error': abs(cat_signed[worst_cat]),
                'worst_cat': worst_cat,
                'worst_signed': cat_signed[worst_cat],
                # Also show D solo error for comparison
                'd_max': max_cat_error(c['d_race'], actual, RACE_CATS),
            })

    company_errors.sort(key=lambda x: -x['max_error'])

    print('%-8s %-35s %-10s %-5s %9s %-6s %9s' % (
        'Code', 'Industry', 'Region', 'State', 'Blend Err', 'Cat', 'D Err'))
    print('-' * 90)
    for c in company_errors[:10]:
        print('%-8s %-35s %-10s %-5s %+8.1f %-6s %8.1f' % (
            c['code'], c['naics_group'][:35], c['region'], c['state'],
            c['worst_signed'], c['worst_cat'],
            c['d_max'] if c['d_max'] is not None else 0))

    # ================================================================
    # DIAGNOSIS
    # ================================================================
    print()
    print('=' * 70)
    print('DIAGNOSIS')
    print('=' * 70)
    print()

    d_maes = [mae_cats(c['d_race'], c['actual_race'], RACE_CATS) for c in all_company_data]
    d_maes = [x for x in d_maes if x is not None]
    blend_raw_maes = [mae_cats(c['blend_raw'], c['actual_race'], RACE_CATS) for c in all_company_data]
    blend_raw_maes = [x for x in blend_raw_maes if x is not None]
    blend_clamp_maes = [mae_cats(c['blend_clamped'], c['actual_race'], RACE_CATS) for c in all_company_data]
    blend_clamp_maes = [x for x in blend_clamp_maes if x is not None]

    d_mae = sum(d_maes) / len(d_maes)
    br_mae = sum(blend_raw_maes) / len(blend_raw_maes)
    bc_mae = sum(blend_clamp_maes) / len(blend_clamp_maes)

    print('Q1: Did the Two+ clamp improve the D+G blend?')
    diff_clamp = br_mae - bc_mae
    print('    D+G raw:     %.3f' % br_mae)
    print('    D+G clamped: %.3f' % bc_mae)
    print('    Improvement: %.3f pp' % diff_clamp)
    if diff_clamp > 0.1:
        print('    --> YES: Two+ overflow was a major contributor.')
    elif diff_clamp > 0.01:
        print('    --> MODEST: Two+ clamp helps but the problem is deeper.')
    else:
        print('    --> NO: Two+ clamp made no difference. Problem is elsewhere.')

    print()
    print('Q2: Does the clamped blend beat V8 post-cal (4.526)?')
    print('    D+G clamped (pre-cal): %.3f' % bc_mae)
    print('    V8 post-calibration:   4.526')
    if bc_mae < 4.526:
        print('    --> YES: Even pre-cal blend beats V8 post-cal. V9 has strong legs.')
    elif bc_mae < 4.9:
        print('    --> PROMISING: Pre-cal blend at %.3f. With calibration (-0.3-0.5pp),' % bc_mae)
        print('       could reach %.1f-%.1f post-cal, competitive with V8.' % (bc_mae - 0.5, bc_mae - 0.3))
    else:
        print('    --> NO: Pre-cal blend at %.3f is too far from V8 post-cal.' % bc_mae)

    print()
    print('Q3: Does blend beat D solo?')
    print('    D solo:      %.3f' % d_mae)
    print('    D+G clamped: %.3f' % bc_mae)
    diff_d = d_mae - bc_mae
    print('    Improvement: %.3f pp' % diff_d)
    if diff_d > 0:
        print('    --> YES: G contributes useful Black signal even after blend.')
    else:
        print('    --> NO: G hurts even after clamping. D solo is better.')

    print()
    print('Total runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
