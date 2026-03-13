"""Hispanic estimation v2: weight optimization and signal blending.

Tests:
1. Grid search over blend weights for PUMS/IPF/tract
2. Adding occ-chain as a 4th signal
3. Adaptive weights by county Hispanic concentration tier
4. Non-linear (multiplicative) calibration
5. Industry-specific weight overrides for high-bias industries
"""
import sys
import os
import json
import time
import itertools
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


def get_raw_signals(cl, rec):
    """Get all Hispanic signal sources for a record. Cached via CachedLoadersV6."""
    naics4 = rec['naics4']
    state_fips = rec['state_fips']
    county_fips = rec['county_fips']
    cbsa_code = rec.get('cbsa_code', '')
    zipcode = rec.get('zipcode', '')
    naics_group = rec.get('naics_group', '')
    naics_2 = naics4[:2] if naics4 else None

    signals = {}

    # 1. PUMS metro
    pums_hisp = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
    signals['pums'] = pums_hisp

    # 2. ACS industry x state
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    signals['acs'] = acs_hisp

    # 3. Industry LODES (county x industry)
    ind_hisp, ind_source = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    signals['ind_lodes'] = ind_hisp
    signals['ind_lodes_source'] = ind_source

    # 4. County LODES (non-industry-specific)
    county_hisp = cl.get_lodes_hispanic(county_fips)
    signals['county_lodes'] = county_hisp

    # 5. IPF of ACS + industry LODES
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    signals['ipf_ind'] = ipf_hisp

    # 6. IPF of ACS + county LODES
    ipf_county = smoothed_ipf(acs_hisp, county_hisp, HISP_CATS)
    signals['ipf_county'] = ipf_county

    # 7. Tract (multi-tract ensemble)
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None
    signals['tract'] = tract_hisp

    # 8. Occ-chain
    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
    if occ_chain and occ_chain.get('Hispanic') is not None:
        signals['occ_chain'] = {
            'Hispanic': occ_chain['Hispanic'],
            'Not Hispanic': 100.0 - occ_chain['Hispanic'],
        }
    else:
        signals['occ_chain'] = None

    # 9. County Hispanic population % from LODES (as a context signal)
    if county_hisp and 'Hispanic' in county_hisp:
        signals['county_hisp_pct'] = county_hisp['Hispanic']
    else:
        signals['county_hisp_pct'] = None

    return signals


def blend_hispanic(signals, weights):
    """Blend Hispanic estimates using named weight dict.

    weights keys: 'pums', 'ipf_ind', 'ipf_county', 'tract', 'occ_chain', 'acs', 'county_lodes', 'ind_lodes'
    """
    sources = []
    for name, w in weights.items():
        if w <= 0:
            continue
        sig = signals.get(name)
        if sig and 'Hispanic' in sig:
            sources.append((sig, w))
    if not sources:
        # Last resort fallback
        for fallback in ['acs', 'county_lodes']:
            sig = signals.get(fallback)
            if sig and 'Hispanic' in sig:
                return sig
        return None
    if len(sources) == 1:
        return sources[0][0]
    return _blend_dicts(sources, HISP_CATS)


def evaluate(records, pred_key='pred_hispanic'):
    errors = [r['abs_error'] for r in records if pred_key in r or 'abs_error' in r]
    if not errors:
        return None
    n = len(errors)
    mae = sum(errors) / n
    return mae


def evaluate_predictions(records, pred_fn):
    """Run pred_fn on each record, return MAE and detailed stats."""
    errors = []
    signed = []
    for rec in records:
        pred = pred_fn(rec)
        if pred is None:
            continue
        truth = rec['truth_hispanic']
        err = abs(pred - truth)
        errors.append(err)
        signed.append(pred - truth)
    if not errors:
        return {'mae': None, 'n': 0}
    n = len(errors)
    mae = sum(errors) / n
    bias = sum(signed) / n
    p10 = sum(1 for e in errors if e > 10) / n * 100
    p15 = sum(1 for e in errors if e > 15) / n * 100
    p20 = sum(1 for e in errors if e > 20) / n * 100
    return {
        'mae': round(mae, 3),
        'bias': round(bias, 3),
        'n': n,
        'p_gt_10pp': round(p10, 2),
        'p_gt_15pp': round(p15, 2),
        'p_gt_20pp': round(p20, 2),
    }


def main():
    t0 = time.time()
    print('HISPANIC ESTIMATION v2: WEIGHT OPTIMIZATION')
    print('=' * 80)

    splits = build_splits()
    all_companies = (splits['train_companies'] + splits['dev_companies']
                     + list(splits['perm_companies']))
    by_code_year, by_code = build_truth_lookup()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Build records with all signals
    print('Building records and collecting signals...')
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
            'truth_hispanic': truth['hispanic']['Hispanic'],
        }
        rec['signals'] = get_raw_signals(cl, rec)
        all_records.append(rec)

    train_records = [r for r in all_records if r['company_code'] in splits['train_codes']]
    dev_records = [r for r in all_records if r['company_code'] in splits['dev_codes']]
    perm_records = [r for r in all_records if r['company_code'] in splits['perm_codes']]

    print('Records: train=%d, dev=%d, perm=%d' % (
        len(train_records), len(dev_records), len(perm_records)))

    # ================================================================
    # TEST 1: Grid search over 3-signal weights (PUMS, IPF, tract)
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 1: GRID SEARCH - PUMS/IPF_IND/TRACT weights')
    print('=' * 80)

    weight_steps = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    best_3sig = {'mae': 999, 'weights': None}
    results_3sig = []

    for w_pums in weight_steps:
        for w_ipf in weight_steps:
            for w_tract in weight_steps:
                total = w_pums + w_ipf + w_tract
                if total < 0.5 or total > 1.5:
                    continue
                weights = {'pums': w_pums, 'ipf_ind': w_ipf, 'tract': w_tract}

                def pred_fn(rec, w=weights):
                    result = blend_hispanic(rec['signals'], w)
                    return result['Hispanic'] if result and 'Hispanic' in result else None

                stats = evaluate_predictions(train_records, pred_fn)
                if stats['mae'] is not None:
                    results_3sig.append((weights.copy(), stats['mae']))
                    if stats['mae'] < best_3sig['mae']:
                        best_3sig = {'mae': stats['mae'], 'weights': weights.copy()}

    results_3sig.sort(key=lambda x: x[1])
    print('Top 10 weight combos (training):')
    for weights, mae in results_3sig[:10]:
        print('  PUMS=%.2f  IPF=%.2f  TRACT=%.2f  -> MAE=%.3f' % (
            weights['pums'], weights['ipf_ind'], weights['tract'], mae))

    print('\nBest: %s -> MAE=%.3f' % (best_3sig['weights'], best_3sig['mae']))

    # ================================================================
    # TEST 2: Add occ-chain as 4th signal
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 2: GRID SEARCH - PUMS/IPF/TRACT/OCC_CHAIN weights')
    print('=' * 80)

    best_4sig = {'mae': 999, 'weights': None}
    results_4sig = []

    occ_weights = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30]
    # Use top-5 from test 1 as base, add occ-chain dimension
    top5_bases = results_3sig[:5]

    for base_weights, base_mae in top5_bases:
        for w_occ in occ_weights:
            weights = dict(base_weights)
            weights['occ_chain'] = w_occ

            def pred_fn(rec, w=weights):
                result = blend_hispanic(rec['signals'], w)
                return result['Hispanic'] if result and 'Hispanic' in result else None

            stats = evaluate_predictions(train_records, pred_fn)
            if stats['mae'] is not None:
                results_4sig.append((weights.copy(), stats['mae']))
                if stats['mae'] < best_4sig['mae']:
                    best_4sig = {'mae': stats['mae'], 'weights': weights.copy()}

    results_4sig.sort(key=lambda x: x[1])
    print('Top 10 weight combos with occ-chain (training):')
    for weights, mae in results_4sig[:10]:
        print('  PUMS=%.2f  IPF=%.2f  TRACT=%.2f  OCC=%.2f  -> MAE=%.3f' % (
            weights.get('pums', 0), weights.get('ipf_ind', 0),
            weights.get('tract', 0), weights.get('occ_chain', 0), mae))

    print('\nBest with occ-chain: %s -> MAE=%.3f' % (best_4sig['weights'], best_4sig['mae']))

    # ================================================================
    # TEST 3: Add ACS and county LODES as potential signals
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 3: BROADER SEARCH - add ACS and COUNTY_LODES')
    print('=' * 80)

    best_broad = {'mae': 999, 'weights': None}
    results_broad = []

    # Start from best 4-signal, add ACS and county_lodes
    for w_acs in [0.0, 0.10, 0.20]:
        for w_county in [0.0, 0.10, 0.20]:
            weights = dict(best_4sig['weights'])
            weights['acs'] = w_acs
            weights['county_lodes'] = w_county

            def pred_fn(rec, w=weights):
                result = blend_hispanic(rec['signals'], w)
                return result['Hispanic'] if result and 'Hispanic' in result else None

            stats = evaluate_predictions(train_records, pred_fn)
            if stats['mae'] is not None:
                results_broad.append((weights.copy(), stats['mae']))
                if stats['mae'] < best_broad['mae']:
                    best_broad = {'mae': stats['mae'], 'weights': weights.copy()}

    results_broad.sort(key=lambda x: x[1])
    print('Top 5 (training):')
    for weights, mae in results_broad[:5]:
        active = {k: v for k, v in weights.items() if v > 0}
        print('  %s  -> MAE=%.3f' % (active, mae))

    # ================================================================
    # TEST 4: Adaptive weights by county Hispanic tier
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 4: ADAPTIVE WEIGHTS BY COUNTY HISPANIC TIER')
    print('=' * 80)

    # Classify companies into Hispanic tiers based on county LODES
    hisp_tiers = {'low': [], 'medium': [], 'high': []}
    for rec in train_records:
        county_hisp = rec['signals'].get('county_hisp_pct')
        if county_hisp is None:
            hisp_tiers['medium'].append(rec)
        elif county_hisp < 10:
            hisp_tiers['low'].append(rec)
        elif county_hisp < 25:
            hisp_tiers['medium'].append(rec)
        else:
            hisp_tiers['high'].append(rec)

    print('Tier sizes: low=%d, medium=%d, high=%d' % (
        len(hisp_tiers['low']), len(hisp_tiers['medium']), len(hisp_tiers['high'])))

    # Find best weights per tier
    tier_best_weights = {}
    for tier_name, tier_recs in hisp_tiers.items():
        if not tier_recs:
            continue
        best_tier_mae = 999
        best_tier_w = None
        # Search over simplified grid
        for w_pums in [0.1, 0.2, 0.3, 0.4]:
            for w_ipf in [0.1, 0.2, 0.3, 0.4]:
                for w_tract in [0.2, 0.3, 0.4, 0.5]:
                    for w_occ in [0.0, 0.1, 0.2]:
                        weights = {'pums': w_pums, 'ipf_ind': w_ipf,
                                   'tract': w_tract, 'occ_chain': w_occ}

                        def pred_fn(rec, w=weights):
                            result = blend_hispanic(rec['signals'], w)
                            return result['Hispanic'] if result and 'Hispanic' in result else None

                        stats = evaluate_predictions(tier_recs, pred_fn)
                        if stats['mae'] is not None and stats['mae'] < best_tier_mae:
                            best_tier_mae = stats['mae']
                            best_tier_w = weights.copy()

        tier_best_weights[tier_name] = best_tier_w
        print('  %s tier: best weights=%s  MAE=%.3f' % (
            tier_name, {k: v for k, v in best_tier_w.items() if v > 0}, best_tier_mae))

    # Evaluate adaptive on training
    def adaptive_pred(rec):
        county_hisp = rec['signals'].get('county_hisp_pct')
        if county_hisp is None:
            tier = 'medium'
        elif county_hisp < 10:
            tier = 'low'
        elif county_hisp < 25:
            tier = 'medium'
        else:
            tier = 'high'
        weights = tier_best_weights.get(tier, best_4sig['weights'])
        result = blend_hispanic(rec['signals'], weights)
        return result['Hispanic'] if result and 'Hispanic' in result else None

    adaptive_train = evaluate_predictions(train_records, adaptive_pred)
    print('\n  Adaptive (training): MAE=%.3f' % adaptive_train['mae'])

    # ================================================================
    # TEST 5: Non-linear calibration (multiplicative)
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 5: NON-LINEAR CALIBRATION')
    print('=' * 80)

    # Use best weights to get raw predictions, then apply non-linear correction
    best_weights = best_4sig['weights']

    def get_raw_pred(rec):
        result = blend_hispanic(rec['signals'], best_weights)
        return result['Hispanic'] if result and 'Hispanic' in result else None

    # Bin predictions and compute average truth per bin
    bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 100)]
    print('\n  Prediction bins (training):')
    print('  %-12s  %-6s  %-10s  %-10s  %-10s' % ('Bin', 'N', 'Mean Pred', 'Mean Truth', 'Ratio'))
    bin_corrections = {}
    for lo, hi in bins:
        bin_recs = []
        for rec in train_records:
            pred = get_raw_pred(rec)
            if pred is not None and lo <= pred < hi:
                bin_recs.append((pred, rec['truth_hispanic']))
        if not bin_recs:
            continue
        mean_pred = sum(p for p, _ in bin_recs) / len(bin_recs)
        mean_truth = sum(t for _, t in bin_recs) / len(bin_recs)
        ratio = mean_truth / mean_pred if mean_pred > 0 else 1.0
        bin_corrections[(lo, hi)] = ratio
        print('  %2d-%2d        %-6d  %-10.2f  %-10.2f  %.3f' % (
            lo, hi, len(bin_recs), mean_pred, mean_truth, ratio))

    def nonlinear_pred(rec, dampening=0.5):
        pred = get_raw_pred(rec)
        if pred is None:
            return None
        for (lo, hi), ratio in bin_corrections.items():
            if lo <= pred < hi:
                correction = ratio
                # Dampen toward 1.0
                dampened_ratio = 1.0 + (correction - 1.0) * dampening
                return max(0.0, min(100.0, pred * dampened_ratio))
        return pred

    for d in [0.3, 0.5, 0.7, 1.0]:
        def nl_pred(rec, damp=d):
            return nonlinear_pred(rec, damp)
        stats = evaluate_predictions(train_records, nl_pred)
        print('  Non-linear d=%.1f (training): MAE=%.3f  bias=%+.3f' % (
            d, stats['mae'], stats['bias']))

    # ================================================================
    # TEST 6: Industry-specific weight overrides
    # ================================================================
    print('\n' + '=' * 80)
    print('TEST 6: INDUSTRY-SPECIFIC WEIGHT OVERRIDES')
    print('=' * 80)

    # For high-bias industries, find optimal weights
    high_bias_industries = [
        'Food/Bev Manufacturing (311,312)',
        'Accommodation/Food Svc (72)',
        'Construction (23)',
        'Agriculture/Mining (11,21)',
        'Transport Equip Mfg (336)',
    ]
    industry_weights = {}
    for ng in high_bias_industries:
        ind_recs = [r for r in train_records if r['naics_group'] == ng]
        if len(ind_recs) < 30:
            continue
        best_ind_mae = 999
        best_ind_w = None
        for w_pums in [0.1, 0.2, 0.3, 0.4, 0.5]:
            for w_ipf in [0.0, 0.1, 0.2, 0.3]:
                for w_tract in [0.2, 0.3, 0.4, 0.5, 0.6]:
                    for w_occ in [0.0, 0.1, 0.2, 0.3]:
                        weights = {'pums': w_pums, 'ipf_ind': w_ipf,
                                   'tract': w_tract, 'occ_chain': w_occ}

                        def pred_fn(rec, w=weights):
                            result = blend_hispanic(rec['signals'], w)
                            return result['Hispanic'] if result and 'Hispanic' in result else None

                        stats = evaluate_predictions(ind_recs, pred_fn)
                        if stats['mae'] is not None and stats['mae'] < best_ind_mae:
                            best_ind_mae = stats['mae']
                            best_ind_w = weights.copy()

        industry_weights[ng] = best_ind_w
        # Compare to default
        def default_pred(rec):
            result = blend_hispanic(rec['signals'], best_4sig['weights'])
            return result['Hispanic'] if result and 'Hispanic' in result else None
        default_stats = evaluate_predictions(ind_recs, default_pred)
        print('  %-35s n=%-4d  default=%.3f  optimized=%.3f  delta=%+.3f' % (
            ng[:35], len(ind_recs), default_stats['mae'], best_ind_mae,
            best_ind_mae - default_stats['mae']))
        active = {k: v for k, v in best_ind_w.items() if v > 0}
        print('    weights: %s' % active)

    # Build industry-override predictor
    def industry_override_pred(rec):
        ng = rec['naics_group']
        if ng in industry_weights:
            weights = industry_weights[ng]
        else:
            weights = best_4sig['weights']
        result = blend_hispanic(rec['signals'], weights)
        return result['Hispanic'] if result and 'Hispanic' in result else None

    ind_override_train = evaluate_predictions(train_records, industry_override_pred)
    print('\n  Industry-override (training): MAE=%.3f' % ind_override_train['mae'])

    # ================================================================
    # FINAL COMPARISON on all sets
    # ================================================================
    print('\n' + '=' * 80)
    print('FINAL COMPARISON')
    print('=' * 80)

    # Define all candidates
    def make_fixed_pred(weights):
        def pred_fn(rec):
            result = blend_hispanic(rec['signals'], weights)
            return result['Hispanic'] if result and 'Hispanic' in result else None
        return pred_fn

    candidates = {
        'v1_winner (30/30/40)': make_fixed_pred({'pums': 0.30, 'ipf_ind': 0.30, 'tract': 0.40}),
        'best_3sig': make_fixed_pred(best_3sig['weights']),
        'best_4sig': make_fixed_pred(best_4sig['weights']),
        'adaptive_tier': adaptive_pred,
        'industry_override': industry_override_pred,
    }

    # Add non-linear best
    best_nl_d = 0.5
    def nl_pred_best(rec):
        return nonlinear_pred(rec, best_nl_d)
    candidates['nonlinear_d0.5'] = nl_pred_best

    # Combined: industry override + non-linear
    def combined_pred(rec):
        ng = rec['naics_group']
        if ng in industry_weights:
            weights = industry_weights[ng]
        else:
            weights = best_4sig['weights']
        result = blend_hispanic(rec['signals'], weights)
        if not result or 'Hispanic' not in result:
            return None
        pred = result['Hispanic']
        for (lo, hi), ratio in bin_corrections.items():
            if lo <= pred < hi:
                dampened_ratio = 1.0 + (ratio - 1.0) * 0.5
                return max(0.0, min(100.0, pred * dampened_ratio))
        return pred
    candidates['combined'] = combined_pred

    # Combined + adaptive tier
    def combined_adaptive(rec):
        county_hisp = rec['signals'].get('county_hisp_pct')
        if county_hisp is None:
            tier = 'medium'
        elif county_hisp < 10:
            tier = 'low'
        elif county_hisp < 25:
            tier = 'medium'
        else:
            tier = 'high'
        ng = rec['naics_group']
        if ng in industry_weights:
            weights = industry_weights[ng]
        elif tier in tier_best_weights:
            weights = tier_best_weights[tier]
        else:
            weights = best_4sig['weights']
        result = blend_hispanic(rec['signals'], weights)
        return result['Hispanic'] if result and 'Hispanic' in result else None
    candidates['industry+adaptive'] = combined_adaptive

    for set_name, records in [('Training (10,000)', train_records),
                               ('All holdout (2,525)', dev_records + perm_records),
                               ('Dev (1,525)', dev_records),
                               ('Permanent (1,000)', perm_records)]:
        print('\n--- %s ---' % set_name)
        print('  %-28s  %-7s  %-8s  %-8s  %-8s  %-8s' % (
            'Method', 'MAE', 'Bias', 'P>10pp', 'P>15pp', 'P>20pp'))
        for name, pred_fn in candidates.items():
            stats = evaluate_predictions(records, pred_fn)
            if stats['mae'] is not None:
                print('  %-28s  %.3f  %+6.3f  %5.1f%%  %5.1f%%  %5.1f%%' % (
                    name, stats['mae'], stats['bias'],
                    stats['p_gt_10pp'], stats['p_gt_15pp'], stats['p_gt_20pp']))

    # Regional breakdown for top candidates
    print('\n--- Regional MAE (Permanent 1,000) ---')
    print('  %-28s  %-8s %-8s %-8s %-8s' % ('Method', 'South', 'West', 'NE', 'MW'))
    for name, pred_fn in candidates.items():
        reg_maes = {}
        for region in ['South', 'West', 'Northeast', 'Midwest']:
            subset = [r for r in perm_records if r['region'] == region]
            stats = evaluate_predictions(subset, pred_fn)
            reg_maes[region] = stats['mae']
        print('  %-28s  %-8s %-8s %-8s %-8s' % (
            name,
            '%.3f' % reg_maes['South'] if reg_maes['South'] else '--',
            '%.3f' % reg_maes['West'] if reg_maes['West'] else '--',
            '%.3f' % reg_maes['Northeast'] if reg_maes['Northeast'] else '--',
            '%.3f' % reg_maes['Midwest'] if reg_maes['Midwest'] else '--',
        ))

    print('\nReference: V8 post-cal=7.111, V6 post-cal=7.752')
    print('Runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
