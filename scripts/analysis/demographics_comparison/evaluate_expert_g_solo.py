"""Evaluate Expert G solo on the permanent holdout.

Runs Expert G on every company (not just the 14 the gate routes to) and
reports full metrics: Race MAE, per-category errors, error distribution,
signed bias, P>20pp, P>30pp, Hispanic MAE, Gender MAE.

Also compares to Expert D (the other proposed model) side by side.

Usage:
    py evaluate_expert_g_solo.py --holdout selected_permanent_holdout_1000.json
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
from classifiers import classify_naics_group, classify_region
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

EXPERTS_TO_TEST = {
    'D': lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    'G': lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    'V6': lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--holdout', default='selected_permanent_holdout_1000.json')
    args = parser.parse_args()

    t0 = time.time()
    print('EXPERT G SOLO EVALUATION')
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

    # Per-expert tracking
    results = {exp: {
        'race_maes': [],
        'max_errors': [],
        'signed_errors': defaultdict(list),
        'hisp_maes': [],
        'gender_maes': [],
        'per_cat_abs_errors': defaultdict(list),
        'per_industry': defaultdict(list),
        'per_region': defaultdict(list),
        'per_county_tier': defaultdict(list),
        'n_processed': 0,
        'n_failed': 0,
    } for exp in EXPERTS_TO_TEST}

    # Also track the 2-model blend: D for White/Asian/AIAN/NHOPI, G for Black/Two+
    blend_race_maes = []
    blend_max_errors = []
    blend_signed_errors = defaultdict(list)
    blend_per_industry = defaultdict(list)
    blend_per_region = defaultdict(list)

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

        # Run each expert
        expert_preds = {}
        for exp_name, exp_fn in EXPERTS_TO_TEST.items():
            try:
                result = exp_fn(cl, naics4, state_fips, county_fips,
                                cbsa_code=cbsa_code, zipcode=zipcode,
                                naics_group=naics_group)
            except Exception:
                result = None

            if not result or not result.get('race'):
                results[exp_name]['n_failed'] += 1
                continue

            results[exp_name]['n_processed'] += 1
            expert_preds[exp_name] = result
            pred_race = result['race']

            # Race MAE
            cat_errors = []
            for cat in RACE_CATS:
                if cat in pred_race and cat in actual_race:
                    err = pred_race[cat] - actual_race[cat]
                    abs_err = abs(err)
                    cat_errors.append(abs_err)
                    results[exp_name]['signed_errors'][cat].append(err)
                    results[exp_name]['per_cat_abs_errors'][cat].append(abs_err)

            if cat_errors:
                race_mae = sum(cat_errors) / len(cat_errors)
                max_err = max(cat_errors)
                results[exp_name]['race_maes'].append(race_mae)
                results[exp_name]['max_errors'].append(max_err)
                results[exp_name]['per_industry'][naics_group].append(race_mae)
                results[exp_name]['per_region'][region].append(race_mae)
                results[exp_name]['per_county_tier'][county_tier].append(race_mae)

            # Hispanic
            if result.get('hispanic') and actual_hisp:
                h_errors = []
                for cat in HISP_CATS:
                    if cat in result['hispanic'] and cat in actual_hisp:
                        h_errors.append(abs(result['hispanic'][cat] - actual_hisp[cat]))
                if h_errors:
                    results[exp_name]['hisp_maes'].append(sum(h_errors) / len(h_errors))

            # Gender
            if result.get('gender') and actual_gender:
                g_errors = []
                for cat in GENDER_CATS:
                    if cat in result['gender'] and cat in actual_gender:
                        g_errors.append(abs(result['gender'][cat] - actual_gender[cat]))
                if g_errors:
                    results[exp_name]['gender_maes'].append(sum(g_errors) / len(g_errors))

        # 2-model blend: D for White/Asian/AIAN/NHOPI, G for Black/Two+
        if 'D' in expert_preds and 'G' in expert_preds:
            d_race = expert_preds['D']['race']
            g_race = expert_preds['G']['race']

            blended = {
                'White': d_race.get('White', 0),
                'Asian': d_race.get('Asian', 0),
                'AIAN': d_race.get('AIAN', 0),
                'NHOPI': d_race.get('NHOPI', 0),
                'Black': g_race.get('Black', 0),
                'Two+': d_race.get('Two+', 0),  # D is ok for Two+ too
            }

            # Normalize to 100
            total = sum(blended.values())
            if total > 0:
                for cat in blended:
                    blended[cat] = blended[cat] * 100.0 / total

            cat_errors = []
            for cat in RACE_CATS:
                if cat in blended and cat in actual_race:
                    err = blended[cat] - actual_race[cat]
                    cat_errors.append(abs(err))
                    blend_signed_errors[cat].append(err)

            if cat_errors:
                blend_race_maes.append(sum(cat_errors) / len(cat_errors))
                blend_max_errors.append(max(cat_errors))
                blend_per_industry[naics_group].append(sum(cat_errors) / len(cat_errors))
                blend_per_region[region].append(sum(cat_errors) / len(cat_errors))

    print('\nProcessed in %.0fs' % (time.time() - t0))

    # ================================================================
    # RESULTS
    # ================================================================
    print()
    print('=' * 70)
    print('OVERALL METRICS (pre-calibration)')
    print('=' * 70)
    print()

    header = '%-12s %10s %10s %10s %10s %10s %10s %10s' % (
        'Expert', 'Race MAE', 'P>20pp', 'P>30pp', 'Hisp MAE', 'Gender MAE', 'N', 'Failed')
    print(header)
    print('-' * len(header))

    for exp in ['D', 'G', 'V6']:
        r = results[exp]
        n = len(r['race_maes'])
        if n == 0:
            continue
        race_mae = sum(r['race_maes']) / n
        p20 = sum(1 for e in r['max_errors'] if e > 20) / n * 100
        p30 = sum(1 for e in r['max_errors'] if e > 30) / n * 100
        hisp = sum(r['hisp_maes']) / len(r['hisp_maes']) if r['hisp_maes'] else 0
        gend = sum(r['gender_maes']) / len(r['gender_maes']) if r['gender_maes'] else 0
        print('%-12s %10.3f %9.1f%% %9.1f%% %10.3f %10.3f %10d %10d' % (
            exp, race_mae, p20, p30, hisp, gend, n, r['n_failed']))

    # Blend row
    if blend_race_maes:
        n = len(blend_race_maes)
        race_mae = sum(blend_race_maes) / n
        p20 = sum(1 for e in blend_max_errors if e > 20) / n * 100
        p30 = sum(1 for e in blend_max_errors if e > 30) / n * 100
        print('%-12s %10.3f %9.1f%% %9.1f%% %10s %10s %10d %10s' % (
            'D+G blend', race_mae, p20, p30, '--', '--', n, '--'))

    # ================================================================
    # SIGNED BIAS
    # ================================================================
    print()
    print('=' * 70)
    print('SIGNED BIAS BY CATEGORY (pred - actual)')
    print('=' * 70)
    print()
    header2 = '%-12s' + ' %10s' * 6 % tuple(RACE_CATS)
    print(header2)
    print('-' * len(header2))
    for exp in ['D', 'G', 'V6', 'D+G blend']:
        if exp == 'D+G blend':
            errs = blend_signed_errors
        else:
            errs = results[exp]['signed_errors']
        vals = []
        for cat in RACE_CATS:
            if errs[cat]:
                vals.append('%+.2f' % (sum(errs[cat]) / len(errs[cat])))
            else:
                vals.append('--')
        print('%-12s' % exp + ''.join(' %10s' % v for v in vals))

    # ================================================================
    # PER-CATEGORY ABSOLUTE ERROR
    # ================================================================
    print()
    print('=' * 70)
    print('PER-CATEGORY ABSOLUTE ERROR')
    print('=' * 70)
    print()
    print(header2)
    print('-' * len(header2))
    for exp in ['D', 'G', 'V6']:
        vals = []
        for cat in RACE_CATS:
            errs = results[exp]['per_cat_abs_errors'][cat]
            if errs:
                vals.append('%.2f' % (sum(errs) / len(errs)))
            else:
                vals.append('--')
        print('%-12s' % exp + ''.join(' %10s' % v for v in vals))

    # ================================================================
    # ERROR DISTRIBUTION
    # ================================================================
    print()
    print('=' * 70)
    print('ERROR DISTRIBUTION (max error per company)')
    print('=' * 70)
    print()

    buckets = [(0, 1), (1, 3), (3, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 999)]
    bucket_labels = ['0-1', '1-3', '3-5', '5-10', '10-15', '15-20', '20-30', '>30']

    header3 = '%-10s' + ' %8s' * len(bucket_labels) % tuple(bucket_labels)
    print(header3)
    print('-' * len(header3))

    for exp in ['D', 'G', 'V6', 'D+G blend']:
        if exp == 'D+G blend':
            errors = blend_max_errors
        else:
            errors = results[exp]['max_errors']
        n = len(errors)
        if n == 0:
            continue
        counts = []
        for lo, hi in buckets:
            c = sum(1 for e in errors if lo < e <= hi or (lo == 0 and e <= hi))
            counts.append('%.1f%%' % (c / n * 100))
        # fix >30 bucket
        c30 = sum(1 for e in errors if e > 30)
        counts[-1] = '%.1f%%' % (c30 / n * 100)
        print('%-10s' % exp + ''.join(' %8s' % c for c in counts))

    # ================================================================
    # PER-INDUSTRY RACE MAE
    # ================================================================
    print()
    print('=' * 70)
    print('PER-INDUSTRY RACE MAE')
    print('=' * 70)
    print()

    # Get all industries
    all_industries = set()
    for exp in ['D', 'G', 'V6']:
        all_industries.update(results[exp]['per_industry'].keys())
    all_industries.update(blend_per_industry.keys())

    print('%-45s %8s %8s %8s %8s' % ('Industry', 'D', 'G', 'V6', 'D+G'))
    print('-' * 77)
    for ind in sorted(all_industries):
        vals = []
        for exp in ['D', 'G', 'V6']:
            errs = results[exp]['per_industry'].get(ind, [])
            vals.append('%.2f' % (sum(errs) / len(errs)) if errs else '--')
        b_errs = blend_per_industry.get(ind, [])
        vals.append('%.2f' % (sum(b_errs) / len(b_errs)) if b_errs else '--')
        n_d = len(results['D']['per_industry'].get(ind, []))
        print('%-45s %8s %8s %8s %8s  (N=%d)' % (ind, vals[0], vals[1], vals[2], vals[3], n_d))

    # ================================================================
    # PER-REGION RACE MAE
    # ================================================================
    print()
    print('=' * 70)
    print('PER-REGION RACE MAE')
    print('=' * 70)
    print()

    print('%-15s %10s %10s %10s %10s' % ('Region', 'D', 'G', 'V6', 'D+G'))
    print('-' * 55)
    for region in ['South', 'West', 'Northeast', 'Midwest']:
        vals = []
        for exp in ['D', 'G', 'V6']:
            errs = results[exp]['per_region'].get(region, [])
            vals.append('%.3f' % (sum(errs) / len(errs)) if errs else '--')
        b_errs = blend_per_region.get(region, [])
        vals.append('%.3f' % (sum(b_errs) / len(b_errs)) if b_errs else '--')
        n_d = len(results['D']['per_region'].get(region, []))
        print('%-15s %10s %10s %10s %10s  (N=%d)' % (region, vals[0], vals[1], vals[2], vals[3], n_d))

    # ================================================================
    # PER-COUNTY-TIER RACE MAE
    # ================================================================
    print()
    print('=' * 70)
    print('PER-COUNTY-TIER RACE MAE')
    print('=' * 70)
    print()

    print('%-15s %10s %10s %10s' % ('County Tier', 'D', 'G', 'V6'))
    print('-' * 45)
    for tier in ['low', 'medium', 'high']:
        vals = []
        for exp in ['D', 'G', 'V6']:
            errs = results[exp]['per_county_tier'].get(tier, [])
            vals.append('%.3f' % (sum(errs) / len(errs)) if errs else '--')
        n_d = len(results['D']['per_county_tier'].get(tier, []))
        print('%-15s %10s %10s %10s  (N=%d)' % (tier, vals[0], vals[1], vals[2], n_d))

    # ================================================================
    # EXPERT G: WORST CASES
    # ================================================================
    print()
    print('=' * 70)
    print('EXPERT G: 20 WORST COMPANIES (highest max race error)')
    print('=' * 70)
    print()

    # Collect per-company data for G
    # Re-run to get company details for worst cases
    g_company_errors = []
    for i, company in enumerate(companies):
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
        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', classify_naics_group(naics4))
        region = get_census_region(state_abbr)
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

        try:
            result = cached_expert_g(cl, naics4, state_fips, county_fips,
                                     cbsa_code=cbsa_code, zipcode=zipcode,
                                     naics_group=naics_group)
        except Exception:
            result = None

        if not result or not result.get('race'):
            continue

        cat_errors = {}
        for cat in RACE_CATS:
            if cat in result['race'] and cat in actual_race:
                cat_errors[cat] = result['race'][cat] - actual_race[cat]

        if cat_errors:
            max_err_cat = max(cat_errors, key=lambda c: abs(cat_errors[c]))
            max_err = abs(cat_errors[max_err_cat])
            g_company_errors.append({
                'code': code,
                'naics_group': naics_group,
                'region': region,
                'state': state_abbr,
                'max_error': max_err,
                'worst_cat': max_err_cat,
                'worst_signed': cat_errors[max_err_cat],
            })

    g_company_errors.sort(key=lambda x: -x['max_error'])
    print('%-10s %-40s %-12s %-6s %10s %-8s' % (
        'Code', 'Industry', 'Region', 'State', 'Max Err', 'Worst Cat'))
    print('-' * 90)
    for c in g_company_errors[:20]:
        print('%-10s %-40s %-12s %-6s %+9.1f %-8s' % (
            c['code'], c['naics_group'][:40], c['region'], c['state'],
            c['worst_signed'], c['worst_cat']))

    print()
    print('Total runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
