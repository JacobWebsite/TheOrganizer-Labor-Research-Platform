"""Analyze Hispanic bias patterns and test calibration strategies.

Questions:
1. What's the bias by region/state? (Is West systematically different?)
2. Should calibration be national, regional, or state-level?
3. How much dampening (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)?
4. Does industry x region help?
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


# State FIPS to name mapping (for display)
STATE_NAMES = {
    '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA',
    '08': 'CO', '09': 'CT', '10': 'DE', '11': 'DC', '12': 'FL',
    '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN',
    '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME',
    '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS',
    '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH',
    '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
    '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI',
    '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX', '49': 'UT',
    '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI',
    '56': 'WY', '72': 'PR',
}

# High-Hispanic states (>15% Hispanic population)
HIGH_HISP_STATES = {'04', '06', '08', '09', '12', '32', '34', '35', '36', '48'}


def main():
    t0 = time.time()
    print('HISPANIC CALIBRATION ANALYSIS')
    print('=' * 80)

    splits = build_splits()
    all_companies = (splits['train_companies'] + splits['dev_companies']
                     + list(splits['perm_companies']))
    by_code_year, by_code = build_truth_lookup()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Build records with predictions
    print('Building records and predictions...')
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
            'state': state,
            'zipcode': zipcode,
            'cbsa_code': cbsa_code,
            'truth': truth,
        }

        pred = hisp_pums_industry_tract(cl, rec)
        if pred and 'Hispanic' in pred:
            rec['pred_hispanic'] = pred['Hispanic']
            rec['truth_hispanic'] = truth['hispanic']['Hispanic']
            rec['error'] = pred['Hispanic'] - truth['hispanic']['Hispanic']
            rec['abs_error'] = abs(rec['error'])
            all_records.append(rec)

    train_records = [r for r in all_records if r['company_code'] in splits['train_codes']]
    dev_records = [r for r in all_records if r['company_code'] in splits['dev_codes']]
    perm_records = [r for r in all_records if r['company_code'] in splits['perm_codes']]
    all_holdout = dev_records + perm_records

    print('Records: train=%d, dev=%d, perm=%d' % (
        len(train_records), len(dev_records), len(perm_records)))

    # ================================================================
    # PART 1: Bias patterns by region
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 1: BIAS BY REGION (training set)')
    print('=' * 80)

    for region in ['South', 'West', 'Northeast', 'Midwest']:
        subset = [r for r in train_records if r['region'] == region]
        if not subset:
            continue
        errors = [r['error'] for r in subset]
        abs_errors = [r['abs_error'] for r in subset]
        mean_bias = sum(errors) / len(errors)
        mae = sum(abs_errors) / len(abs_errors)
        median_truth = sorted([r['truth_hispanic'] for r in subset])[len(subset) // 2]
        print('  %-12s n=%-5d  bias=%+6.2f  MAE=%.3f  median_truth_hisp=%.1f%%' % (
            region, len(subset), mean_bias, mae, median_truth))

    # ================================================================
    # PART 2: Bias by state (top 15 states by count)
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 2: BIAS BY STATE (training set, top 20 by count)')
    print('=' * 80)

    state_groups = defaultdict(list)
    for r in train_records:
        state_groups[r['state_fips']].append(r)

    state_stats = []
    for sf, recs in state_groups.items():
        if len(recs) < 20:
            continue
        errors = [r['error'] for r in recs]
        abs_errors = [r['abs_error'] for r in recs]
        truths = [r['truth_hispanic'] for r in recs]
        state_stats.append({
            'state_fips': sf,
            'state': STATE_NAMES.get(sf, sf),
            'n': len(recs),
            'bias': sum(errors) / len(errors),
            'mae': sum(abs_errors) / len(abs_errors),
            'median_truth': sorted(truths)[len(truths) // 2],
            'mean_truth': sum(truths) / len(truths),
        })

    state_stats.sort(key=lambda x: x['n'], reverse=True)
    print('  %-5s  %-6s  %-8s  %-8s  %-10s  %-10s' % (
        'State', 'N', 'Bias', 'MAE', 'Med Truth', 'Mean Truth'))
    for s in state_stats[:20]:
        marker = ' ***' if abs(s['bias']) > 3.0 else ''
        print('  %-5s  %-6d  %+7.2f   %-8.3f  %-10.1f  %-10.1f%s' % (
            s['state'], s['n'], s['bias'], s['mae'],
            s['median_truth'], s['mean_truth'], marker))

    # ================================================================
    # PART 3: Bias by NAICS group (training set)
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 3: BIAS BY NAICS GROUP (training set, n>=50)')
    print('=' * 80)

    naics_groups = defaultdict(list)
    for r in train_records:
        naics_groups[r['naics_group']].append(r)

    naics_stats = []
    for ng, recs in naics_groups.items():
        if len(recs) < 50:
            continue
        errors = [r['error'] for r in recs]
        abs_errors = [r['abs_error'] for r in recs]
        naics_stats.append({
            'naics_group': ng,
            'n': len(recs),
            'bias': sum(errors) / len(errors),
            'mae': sum(abs_errors) / len(abs_errors),
        })

    naics_stats.sort(key=lambda x: abs(x['bias']), reverse=True)
    print('  %-35s  %-6s  %-8s  %-8s' % ('NAICS Group', 'N', 'Bias', 'MAE'))
    for s in naics_stats:
        marker = ' ***' if abs(s['bias']) > 3.0 else ''
        print('  %-35s  %-6d  %+7.2f   %-8.3f%s' % (
            s['naics_group'][:35], s['n'], s['bias'], s['mae'], marker))

    # ================================================================
    # PART 4: Bias by region x industry (training set)
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 4: BIAS BY REGION x TOP INDUSTRIES (training set, n>=30)')
    print('=' * 80)

    region_naics = defaultdict(list)
    for r in train_records:
        region_naics[(r['region'], r['naics_group'])].append(r)

    ri_stats = []
    for (region, ng), recs in region_naics.items():
        if len(recs) < 30:
            continue
        errors = [r['error'] for r in recs]
        abs_errors = [r['abs_error'] for r in recs]
        ri_stats.append({
            'key': '%s | %s' % (region, ng[:25]),
            'n': len(recs),
            'bias': sum(errors) / len(errors),
            'mae': sum(abs_errors) / len(abs_errors),
        })

    ri_stats.sort(key=lambda x: abs(x['bias']), reverse=True)
    print('  %-45s  %-6s  %-8s  %-8s' % ('Region | Industry', 'N', 'Bias', 'MAE'))
    for s in ri_stats[:20]:
        print('  %-45s  %-6d  %+7.2f   %-8.3f' % (
            s['key'], s['n'], s['bias'], s['mae']))

    # ================================================================
    # PART 5: Test calibration strategies
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 5: CALIBRATION STRATEGIES')
    print('=' * 80)

    # Strategy 1: Global (single correction for all companies)
    # Strategy 2: By region (4 corrections)
    # Strategy 3: By state tier (high-hisp states vs rest)
    # Strategy 4: By region x industry (fine-grained)
    # Strategy 5: By state (per-state correction, min N=30)

    dampening_values = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

    # Compute corrections from training data
    # Global
    global_bias = sum(r['error'] for r in train_records) / len(train_records)

    # Regional
    region_bias = {}
    for region in ['South', 'West', 'Northeast', 'Midwest']:
        subset = [r for r in train_records if r['region'] == region]
        if subset:
            region_bias[region] = sum(r['error'] for r in subset) / len(subset)

    # State-tier (high-hisp vs rest)
    high_hisp_recs = [r for r in train_records if r['state_fips'] in HIGH_HISP_STATES]
    low_hisp_recs = [r for r in train_records if r['state_fips'] not in HIGH_HISP_STATES]
    tier_bias = {
        'high': sum(r['error'] for r in high_hisp_recs) / len(high_hisp_recs) if high_hisp_recs else 0,
        'low': sum(r['error'] for r in low_hisp_recs) / len(low_hisp_recs) if low_hisp_recs else 0,
    }

    # Per-state (min N=30)
    state_bias = {}
    for sf, recs in state_groups.items():
        if len(recs) >= 30:
            state_bias[sf] = sum(r['error'] for r in recs) / len(recs)

    # Region x industry (min N=30)
    ri_bias = {}
    for (region, ng), recs in region_naics.items():
        if len(recs) >= 30:
            ri_bias[(region, ng)] = sum(r['error'] for r in recs) / len(recs)

    print('\nCorrections learned from training:')
    print('  Global bias: %+.3f' % global_bias)
    print('  Region biases: %s' % {k: round(v, 3) for k, v in region_bias.items()})
    print('  State-tier biases: high-hisp=%+.3f, rest=%+.3f' % (
        tier_bias['high'], tier_bias['low']))
    print('  Per-state corrections available: %d states' % len(state_bias))
    print('  Region x industry corrections available: %d cells' % len(ri_bias))

    def apply_calibration(rec, strategy, dampening):
        pred = rec['pred_hispanic']
        correction = 0.0

        if strategy == 'none':
            return pred
        elif strategy == 'global':
            correction = global_bias
        elif strategy == 'region':
            correction = region_bias.get(rec['region'], global_bias)
        elif strategy == 'state_tier':
            tier = 'high' if rec['state_fips'] in HIGH_HISP_STATES else 'low'
            correction = tier_bias[tier]
        elif strategy == 'state':
            correction = state_bias.get(rec['state_fips'], region_bias.get(rec['region'], global_bias))
        elif strategy == 'region_industry':
            correction = ri_bias.get(
                (rec['region'], rec['naics_group']),
                region_bias.get(rec['region'], global_bias))
        elif strategy == 'state_then_region':
            # Hierarchical: state if N>=30, else region, else global
            correction = state_bias.get(
                rec['state_fips'],
                region_bias.get(rec['region'], global_bias))
        elif strategy == 'state_then_ri':
            # State first, then region x industry, then region, then global
            if rec['state_fips'] in state_bias:
                correction = state_bias[rec['state_fips']]
            elif (rec['region'], rec['naics_group']) in ri_bias:
                correction = ri_bias[(rec['region'], rec['naics_group'])]
            elif rec['region'] in region_bias:
                correction = region_bias[rec['region']]
            else:
                correction = global_bias

        calibrated = pred - correction * dampening
        return max(0.0, min(100.0, calibrated))

    strategies = ['none', 'global', 'region', 'state_tier', 'state',
                  'region_industry', 'state_then_region', 'state_then_ri']

    # Test all strategies x dampening on ALL THREE sets
    for set_name, records in [('TRAINING (10,000)', train_records),
                               ('ALL HOLDOUT (2,525)', all_holdout),
                               ('DEV (1,525)', dev_records),
                               ('PERMANENT (1,000)', perm_records)]:
        print('\n--- %s ---' % set_name)
        print('  %-25s' % 'Strategy', end='')
        for d in dampening_values:
            print('  d=%.1f ' % d, end='')
        print()

        for strategy in strategies:
            print('  %-25s' % strategy, end='')
            for d in dampening_values:
                errors = []
                for rec in records:
                    calibrated = apply_calibration(rec, strategy, d)
                    errors.append(abs(calibrated - rec['truth_hispanic']))
                mae = sum(errors) / len(errors)
                print('  %.3f' % mae, end='')
            print()

    # ================================================================
    # PART 6: Best strategy deep dive
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 6: BEST STRATEGY DEEP DIVE')
    print('=' * 80)

    # Find best strategy x dampening on dev set
    best_mae = 999
    best_combo = None
    for strategy in strategies:
        for d in dampening_values:
            errors = []
            for rec in dev_records:
                calibrated = apply_calibration(rec, strategy, d)
                errors.append(abs(calibrated - rec['truth_hispanic']))
            mae = sum(errors) / len(errors)
            if mae < best_mae:
                best_mae = mae
                best_combo = (strategy, d)

    print('Best on dev: %s @ dampening=%.1f -> MAE=%.3f' % (
        best_combo[0], best_combo[1], best_mae))

    # Apply best to all sets with detailed breakdown
    strategy, dampening = best_combo
    for set_name, records in [('All holdout', all_holdout),
                               ('Dev', dev_records),
                               ('Permanent', perm_records)]:
        print('\n--- %s with %s @ d=%.1f ---' % (set_name, strategy, dampening))
        errors = []
        signed = []
        for rec in records:
            calibrated = apply_calibration(rec, strategy, dampening)
            err = abs(calibrated - rec['truth_hispanic'])
            errors.append(err)
            signed.append(calibrated - rec['truth_hispanic'])

        mae = sum(errors) / len(errors)
        bias = sum(signed) / len(signed)
        p10 = sum(1 for e in errors if e > 10) / len(errors) * 100
        p15 = sum(1 for e in errors if e > 15) / len(errors) * 100
        p20 = sum(1 for e in errors if e > 20) / len(errors) * 100
        print('  MAE=%.3f  bias=%+.3f  P>10pp=%.1f%%  P>15pp=%.1f%%  P>20pp=%.1f%%' % (
            mae, bias, p10, p15, p20))

        # Regional breakdown
        for region in ['South', 'West', 'Northeast', 'Midwest']:
            subset = [r for r in records if r['region'] == region]
            if not subset:
                continue
            reg_errors = []
            for rec in subset:
                calibrated = apply_calibration(rec, strategy, dampening)
                reg_errors.append(abs(calibrated - rec['truth_hispanic']))
            reg_mae = sum(reg_errors) / len(reg_errors)
            print('    %-12s MAE=%.3f  n=%d' % (region, reg_mae, len(subset)))

    # ================================================================
    # PART 7: Compare pre vs post calibration
    # ================================================================
    print('\n' + '=' * 80)
    print('PART 7: PRE vs POST CALIBRATION SUMMARY (permanent holdout)')
    print('=' * 80)

    strategy, dampening = best_combo
    pre_errors = [r['abs_error'] for r in perm_records]
    post_errors = []
    for rec in perm_records:
        calibrated = apply_calibration(rec, strategy, dampening)
        post_errors.append(abs(calibrated - rec['truth_hispanic']))

    pre_mae = sum(pre_errors) / len(pre_errors)
    post_mae = sum(post_errors) / len(post_errors)

    print('  Pre-calibration:  MAE=%.3f' % pre_mae)
    print('  Post-calibration: MAE=%.3f (%s @ d=%.1f)' % (
        post_mae, strategy, dampening))
    print('  Improvement:      %.3f pp' % (pre_mae - post_mae))
    print('  V8 post-cal ref:  MAE=7.111')
    print('  V6 post-cal ref:  MAE=7.752')

    print('\nRuntime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
