"""Test simple scaling corrections for Hispanic underestimation.

Methodological question: is it sound to apply a multiplicative or additive
correction trained on ground truth? Yes, IF:
  1. Correction is learned on training set only (no data leakage)
  2. Correction is simple enough to not overfit (1-2 parameters)
  3. Improvement holds on out-of-sample data (dev + permanent holdout)

This is standard bias correction / post-hoc calibration, widely used in
survey statistics (ratio estimation) and weather forecasting (MOS).

Tests:
  A. Multiplicative: pred * scale_factor
  B. Additive: pred + offset
  C. Linear: pred * slope + intercept (2 params, fit via least-squares)
  D. Piecewise: different scale below/above a threshold
  E. Capped multiplicative: pred * scale, capped at 100
"""
import sys
import os
import json
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from methodologies_v5 import smoothed_ipf, RACE_CATS
from methodologies import _blend_dicts
from classifiers import classify_naics_group
from config import get_census_region

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
SPLIT_SEED = 20260311


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_truth_lookup():
    eeo1_rows = load_all_eeo1_data()
    by_code_year = {}
    by_code = defaultdict(list)
    for row in eeo1_rows:
        code = (row.get('COMPANY') or '').strip()
        year = int(float(row.get('YEAR', 0) or 0))
        if not code:
            continue
        parsed = parse_eeo1_row(row)
        if not parsed:
            continue
        by_code_year[(code, year)] = parsed
        by_code[code].append(parsed)
    for code in by_code:
        by_code[code].sort(key=lambda r: r.get('year', 0), reverse=True)
    return by_code_year, by_code


def get_truth(company, by_code_year, by_code):
    code = company['company_code']
    year = company.get('year')
    truth = by_code_year.get((code, year))
    if truth:
        return truth
    vals = by_code.get(code, [])
    return vals[0] if vals else None


def build_splits():
    perm_data = load_json(os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json'))
    perm_companies = perm_data['companies'] if isinstance(perm_data, dict) else perm_data
    perm_codes = {c['company_code'] for c in perm_companies}
    pool = load_json(os.path.join(SCRIPT_DIR, 'expanded_training_v6.json'))
    non_perm_pool = [c for c in pool if c['company_code'] not in perm_codes]
    import random
    rng = random.Random(SPLIT_SEED)
    shuffled = non_perm_pool[:]
    rng.shuffle(shuffled)
    train = shuffled[:10000]
    dev = shuffled[10000:]
    return {
        'perm_companies': perm_companies,
        'perm_codes': perm_codes,
        'train_companies': train,
        'train_codes': {c['company_code'] for c in train},
        'dev_companies': dev,
        'dev_codes': {c['company_code'] for c in dev},
    }


def hisp_pums_industry_tract(cl, rec):
    """The winning method G from test_improved_hispanic.py."""
    naics4 = rec['naics4']
    state_fips = rec['state_fips']
    county_fips = rec['county_fips']
    cbsa_code = rec.get('cbsa_code', '')
    zipcode = rec.get('zipcode', '')
    naics_2 = naics4[:2] if naics4 else None

    pums_hisp = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None

    sources = []
    if pums_hisp:
        sources.append((pums_hisp, 0.30))
    if ipf_hisp:
        sources.append((ipf_hisp, 0.30))
    if tract_hisp:
        sources.append((tract_hisp, 0.40))

    if not sources:
        return acs_hisp
    if len(sources) == 1:
        return sources[0][0]
    return _blend_dicts(sources, HISP_CATS)


def evaluate(records, transform_fn=None):
    errors = []
    signed = []
    for rec in records:
        pred = rec['pred_hispanic']
        if transform_fn:
            pred = transform_fn(pred)
        pred = max(0.0, min(100.0, pred))
        truth = rec['truth_hispanic']
        errors.append(abs(pred - truth))
        signed.append(pred - truth)
    n = len(errors)
    mae = sum(errors) / n
    bias = sum(signed) / n
    p10 = sum(1 for e in errors if e > 10) / n * 100
    p15 = sum(1 for e in errors if e > 15) / n * 100
    p20 = sum(1 for e in errors if e > 20) / n * 100
    return {
        'mae': round(mae, 3), 'bias': round(bias, 3), 'n': n,
        'p10': round(p10, 1), 'p15': round(p15, 1), 'p20': round(p20, 1),
    }


def eval_by_region(records, transform_fn=None):
    out = {}
    for region in ['South', 'West', 'Northeast', 'Midwest']:
        subset = [r for r in records if r['region'] == region]
        if subset:
            out[region] = evaluate(subset, transform_fn)
    return out


def fit_linear(records):
    """Fit y = a*x + b via least squares on training data."""
    n = len(records)
    sx = sum(r['pred_hispanic'] for r in records)
    sy = sum(r['truth_hispanic'] for r in records)
    sxx = sum(r['pred_hispanic'] ** 2 for r in records)
    sxy = sum(r['pred_hispanic'] * r['truth_hispanic'] for r in records)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-10:
        return 1.0, 0.0
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return a, b


def main():
    t0 = time.time()
    print('HISPANIC SCALING CORRECTION TEST')
    print('=' * 80)

    splits = build_splits()
    all_companies = (splits['train_companies'] + splits['dev_companies']
                     + list(splits['perm_companies']))
    by_code_year, by_code = build_truth_lookup()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print('Building records...')
    all_records = []
    for idx, company in enumerate(all_companies, 1):
        if idx % 2000 == 0:
            print('  %d/%d (%.0fs)' % (idx, len(all_companies), time.time() - t0))

        truth = get_truth(company, by_code_year, by_code)
        if not truth or not truth.get('hispanic'):
            continue

        naics = company.get('naics', '')
        naics4 = naics[:4]
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')
        zipcode = company.get('zipcode', '')
        state = company.get('state', '')
        naics_group = (company.get('classifications', {}).get('naics_group')
                       or classify_naics_group(naics4))
        region = (company.get('classifications', {}).get('region')
                  or get_census_region(state))
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

        rec = {
            'company_code': company['company_code'],
            'naics4': naics4,
            'naics_group': naics_group,
            'region': region,
            'county_fips': county_fips,
            'state_fips': state_fips,
            'zipcode': zipcode,
            'cbsa_code': cbsa_code,
            'truth': truth,
            'truth_hispanic': truth['hispanic']['Hispanic'],
        }

        pred = hisp_pums_industry_tract(cl, rec)
        if pred and 'Hispanic' in pred:
            rec['pred_hispanic'] = pred['Hispanic']
            all_records.append(rec)

    train_records = [r for r in all_records if r['company_code'] in splits['train_codes']]
    dev_records = [r for r in all_records if r['company_code'] in splits['dev_codes']]
    perm_records = [r for r in all_records if r['company_code'] in splits['perm_codes']]
    all_holdout = dev_records + perm_records

    print('Records: train=%d, dev=%d, perm=%d\n' % (
        len(train_records), len(dev_records), len(perm_records)))

    # ================================================================
    # Fit parameters on TRAINING only
    # ================================================================

    # A. Optimal multiplicative factor: minimize MAE
    #    Scan scale from 1.0 to 1.4
    print('A. MULTIPLICATIVE SCALING: pred * scale')
    print('-' * 60)
    best_scale = 1.0
    best_scale_mae = 999
    for s100 in range(100, 141):
        scale = s100 / 100.0
        fn = lambda p, sc=scale: p * sc
        stats = evaluate(train_records, fn)
        if stats['mae'] < best_scale_mae:
            best_scale_mae = stats['mae']
            best_scale = scale
    print('  Optimal scale (training): %.2f -> MAE=%.3f' % (best_scale, best_scale_mae))

    # Show grid
    print('\n  Scale   Train    Dev      Perm     AllHO')
    for s100 in range(100, 136, 2):
        scale = s100 / 100.0
        fn = lambda p, sc=scale: p * sc
        t = evaluate(train_records, fn)
        d = evaluate(dev_records, fn)
        p = evaluate(perm_records, fn)
        h = evaluate(all_holdout, fn)
        marker = ' <--' if s100 == int(best_scale * 100) else ''
        print('  %.2f    %.3f    %.3f    %.3f    %.3f%s' % (
            scale, t['mae'], d['mae'], p['mae'], h['mae'], marker))

    # B. Additive
    print('\nB. ADDITIVE: pred + offset')
    print('-' * 60)
    best_offset = 0.0
    best_offset_mae = 999
    for o10 in range(0, 61):
        offset = o10 / 10.0
        fn = lambda p, off=offset: p + off
        stats = evaluate(train_records, fn)
        if stats['mae'] < best_offset_mae:
            best_offset_mae = stats['mae']
            best_offset = offset
    print('  Optimal offset (training): +%.1f -> MAE=%.3f' % (best_offset, best_offset_mae))

    print('\n  Offset  Train    Dev      Perm     AllHO')
    for o10 in range(0, 50, 5):
        offset = o10 / 10.0
        fn = lambda p, off=offset: p + off
        t = evaluate(train_records, fn)
        d = evaluate(dev_records, fn)
        p = evaluate(perm_records, fn)
        h = evaluate(all_holdout, fn)
        marker = ' <--' if o10 == int(best_offset * 10) else ''
        print('  +%.1f    %.3f    %.3f    %.3f    %.3f%s' % (
            offset, t['mae'], d['mae'], p['mae'], h['mae'], marker))

    # C. Linear: pred * slope + intercept
    print('\nC. LINEAR: pred * slope + intercept')
    print('-' * 60)
    slope, intercept = fit_linear(train_records)
    print('  Fitted: pred * %.4f + %.4f' % (slope, intercept))
    fn_linear = lambda p: p * slope + intercept

    # D. Piecewise: different scale below/above threshold
    print('\nD. PIECEWISE: scale_lo below threshold, scale_hi above')
    print('-' * 60)
    best_pw = {'mae': 999}
    for thresh in [5, 10, 15, 20]:
        for s_lo_10 in range(10, 25):
            for s_hi_10 in range(8, 16):
                s_lo = s_lo_10 / 10.0
                s_hi = s_hi_10 / 10.0
                fn = lambda p, t=thresh, sl=s_lo, sh=s_hi: p * sl if p < t else p * sh
                stats = evaluate(train_records, fn)
                if stats['mae'] < best_pw['mae']:
                    best_pw = {
                        'mae': stats['mae'],
                        'thresh': thresh,
                        's_lo': s_lo,
                        's_hi': s_hi,
                    }
    print('  Best piecewise (training): thresh=%d, lo=%.1f, hi=%.1f -> MAE=%.3f' % (
        best_pw['thresh'], best_pw['s_lo'], best_pw['s_hi'], best_pw['mae']))
    fn_pw = lambda p: p * best_pw['s_lo'] if p < best_pw['thresh'] else p * best_pw['s_hi']

    # E. Dampened multiplicative: pred * (1 + (scale-1) * dampening)
    print('\nE. DAMPENED SCALING: pred * (1 + (optimal_scale-1) * d)')
    print('-' * 60)
    print('  Using optimal scale=%.2f' % best_scale)
    print('\n  Damp    Train    Dev      Perm     AllHO')
    for d10 in range(0, 11, 2):
        damp = d10 / 10.0
        eff_scale = 1.0 + (best_scale - 1.0) * damp
        fn = lambda p, sc=eff_scale: p * sc
        t = evaluate(train_records, fn)
        dv = evaluate(dev_records, fn)
        pm = evaluate(perm_records, fn)
        h = evaluate(all_holdout, fn)
        print('  %.1f     %.3f    %.3f    %.3f    %.3f  (eff_scale=%.3f)' % (
            damp, t['mae'], dv['mae'], pm['mae'], h['mae'], eff_scale))

    # ================================================================
    # FINAL COMPARISON
    # ================================================================
    print('\n' + '=' * 80)
    print('FINAL COMPARISON')
    print('=' * 80)

    transforms = {
        'none':           lambda p: p,
        'mult_%.2f' % best_scale: lambda p: p * best_scale,
        'add_+%.1f' % best_offset: lambda p: p + best_offset,
        'linear':         fn_linear,
        'piecewise':      fn_pw,
        'mult_damp_0.5':  lambda p: p * (1.0 + (best_scale - 1.0) * 0.5),
        'mult_damp_0.7':  lambda p: p * (1.0 + (best_scale - 1.0) * 0.7),
    }

    for set_name, records in [('Training', train_records),
                               ('All holdout', all_holdout),
                               ('Dev', dev_records),
                               ('Permanent', perm_records)]:
        print('\n--- %s ---' % set_name)
        print('  %-22s  %-7s  %-8s  %-7s  %-7s  %-7s' % (
            'Transform', 'MAE', 'Bias', 'P>10', 'P>15', 'P>20'))
        for name, fn in transforms.items():
            stats = evaluate(records, fn)
            print('  %-22s  %.3f  %+6.3f  %5.1f%%  %5.1f%%  %5.1f%%' % (
                name, stats['mae'], stats['bias'],
                stats['p10'], stats['p15'], stats['p20']))

    # Regional breakdown for best methods on permanent
    print('\n--- Regional MAE (Permanent 1,000) ---')
    print('  %-22s  %-8s %-8s %-8s %-8s' % ('Transform', 'South', 'West', 'NE', 'MW'))
    for name, fn in transforms.items():
        regions = eval_by_region(perm_records, fn)
        print('  %-22s  %-8s %-8s %-8s %-8s' % (
            name,
            '%.3f' % regions['South']['mae'],
            '%.3f' % regions['West']['mae'],
            '%.3f' % regions['Northeast']['mae'],
            '%.3f' % regions['Midwest']['mae'],
        ))

    # Industry breakdown for best methods on permanent
    print('\n--- Top industry MAE (Permanent 1,000) ---')
    top_industries = [
        'Healthcare/Social (62)', 'Admin/Staffing (56)',
        'Finance/Insurance (52)', 'Construction (23)',
        'Professional/Technical (54)',
    ]
    for name, fn in [('none', transforms['none']),
                     ('mult_%.2f' % best_scale, transforms['mult_%.2f' % best_scale]),
                     ('linear', transforms['linear']),
                     ('piecewise', transforms['piecewise'])]:
        print('\n  %s:' % name)
        for ng in top_industries:
            subset = [r for r in perm_records if r['naics_group'] == ng]
            if subset:
                stats = evaluate(subset, fn)
                print('    %-30s  MAE=%.3f  bias=%+.3f  n=%d' % (
                    ng, stats['mae'], stats['bias'], stats['n']))

    # Methodological soundness summary
    print('\n' + '=' * 80)
    print('METHODOLOGICAL SOUNDNESS')
    print('=' * 80)
    print("""
  This is ratio estimation / bias correction, a standard technique:

  1. RATIO ESTIMATION (Cochran, 1977): In survey sampling, when an
     auxiliary variable (census demographics) systematically under/over-
     estimates the target (actual workforce demographics), multiplying
     by the ratio of means (truth/pred) is the minimum-variance
     unbiased estimator under proportional bias.

  2. MODEL OUTPUT STATISTICS (MOS): In weather forecasting, raw model
     output is routinely post-corrected using linear regression on
     historical forecast/observation pairs. Our linear transform
     (pred * slope + intercept) is exactly this.

  3. PLATT SCALING: In machine learning, logistic regression on model
     outputs to calibrate probabilities. Our multiplicative/additive
     corrections are simpler versions of this.

  Requirements for soundness:
  - Correction fit on training data only:              YES
  - Evaluated on held-out data:                        YES (dev + perm)
  - Correction has few parameters (avoids overfit):    YES (1-2 params)
  - Improvement holds out-of-sample:                   CHECK ABOVE

  The key question: does the bias generalize? If the underestimation is
  structural (census data systematically undercounts Hispanic workers
  because it measures residential, not workplace, demographics), then
  the correction should be stable across samples. If the bias is random
  or sample-specific, the correction would overfit.
""")

    print('Reference: V8 post-cal=7.111, V6 post-cal=7.752')
    print('Runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
