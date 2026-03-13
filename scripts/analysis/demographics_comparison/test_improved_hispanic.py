"""Test improved Hispanic estimation using industry-specific LODES data.

Compares current approaches against new blends that leverage the
previously-unused lodes_county_industry_demographics Hispanic columns.

Uses the same train/dev/perm split as V9 for consistent comparison.
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
from cached_loaders_v5 import cached_method_3c_v5
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


# ============================================================
# Hispanic estimation methods
# ============================================================

def hisp_baseline_county_ipf(cl, naics4, state_fips, county_fips, **kw):
    """Current default: ACS industry x state + county LODES (no industry)."""
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    lodes_hisp = cl.get_lodes_hispanic(county_fips)
    return smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS)


def hisp_industry_lodes_ipf(cl, naics4, state_fips, county_fips, **kw):
    """NEW: ACS industry x state + industry-specific LODES."""
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    return smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)


def hisp_expert_b(cl, naics4, state_fips, county_fips, **kw):
    """Expert B approach: ACS + county LODES + tract (35/25/40)."""
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    lodes_hisp = cl.get_lodes_hispanic(county_fips)
    ipf_hisp = smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS)
    zipcode = kw.get('zipcode', '')
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None
    if ipf_hisp and tract_hisp:
        return _blend_dicts([(acs_hisp, 0.35), (ipf_hisp, 0.25), (tract_hisp, 0.40)], HISP_CATS)
    return ipf_hisp


def hisp_industry_lodes_tract_blend(cl, naics4, state_fips, county_fips, **kw):
    """NEW: ACS + industry LODES IPF + tract blend (35/25/40)."""
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    zipcode = kw.get('zipcode', '')
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None
    if ipf_hisp and tract_hisp:
        return _blend_dicts([(acs_hisp, 0.35), (ipf_hisp, 0.25), (tract_hisp, 0.40)], HISP_CATS)
    return ipf_hisp


def hisp_occ_chain(cl, naics4, state_fips, county_fips, **kw):
    """Expert G approach: 60% occ-chain + 40% ACS/county-LODES IPF."""
    naics_group = kw.get('naics_group') or classify_naics_group(naics4)
    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    lodes_hisp = cl.get_lodes_hispanic(county_fips)
    ipf_hisp = smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS)
    if occ_chain and occ_chain.get('Hispanic') is not None:
        occ_hisp = {
            'Hispanic': occ_chain['Hispanic'],
            'Not Hispanic': 100.0 - occ_chain['Hispanic'],
        }
        if ipf_hisp:
            return _blend_dicts([(occ_hisp, 0.60), (ipf_hisp, 0.40)], HISP_CATS)
        return occ_hisp
    return ipf_hisp


def hisp_occ_chain_industry_lodes(cl, naics4, state_fips, county_fips, **kw):
    """NEW: 60% occ-chain + 40% ACS/industry-LODES IPF."""
    naics_group = kw.get('naics_group') or classify_naics_group(naics4)
    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    if occ_chain and occ_chain.get('Hispanic') is not None:
        occ_hisp = {
            'Hispanic': occ_chain['Hispanic'],
            'Not Hispanic': 100.0 - occ_chain['Hispanic'],
        }
        if ipf_hisp:
            return _blend_dicts([(occ_hisp, 0.60), (ipf_hisp, 0.40)], HISP_CATS)
        return occ_hisp
    return ipf_hisp


def hisp_pums_industry_lodes_tract(cl, naics4, state_fips, county_fips, **kw):
    """NEW: PUMS metro (if avail) + industry LODES + tract, weighted blend."""
    cbsa_code = cl.get_county_cbsa(county_fips)
    naics_2 = naics4[:2] if naics4 else None
    pums_hisp = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    zipcode = kw.get('zipcode', '')
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


def hisp_three_layer_industry(cl, naics4, state_fips, county_fips, **kw):
    """NEW: Three-layer blend using industry LODES as the anchor.

    50% ACS industry x state (what the industry looks like statewide)
    30% industry LODES county (what THIS industry looks like HERE)
    20% tract (hyperlocal signal)
    """
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, source = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    zipcode = kw.get('zipcode', '')
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None

    sources = []
    if acs_hisp:
        sources.append((acs_hisp, 0.50))
    if ind_hisp:
        sources.append((ind_hisp, 0.30))
    if tract_hisp:
        sources.append((tract_hisp, 0.20))

    if not sources:
        return None
    if len(sources) == 1:
        return sources[0][0]
    return _blend_dicts(sources, HISP_CATS)


def hisp_occ_chain_three_layer(cl, naics4, state_fips, county_fips, **kw):
    """NEW: Occ-chain when available, else three-layer industry blend.

    If occ_chain available: 40% occ-chain + 30% ACS + 30% industry-LODES
    Else: 50% ACS + 30% industry-LODES + 20% tract
    """
    naics_group = kw.get('naics_group') or classify_naics_group(naics4)
    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)

    if occ_chain and occ_chain.get('Hispanic') is not None:
        occ_hisp = {
            'Hispanic': occ_chain['Hispanic'],
            'Not Hispanic': 100.0 - occ_chain['Hispanic'],
        }
        sources = [(occ_hisp, 0.40)]
        if acs_hisp:
            sources.append((acs_hisp, 0.30))
        if ipf_hisp:
            sources.append((ipf_hisp, 0.30))
        return _blend_dicts(sources, HISP_CATS)

    zipcode = kw.get('zipcode', '')
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get('hispanic') if tract_data else None

    sources = []
    if acs_hisp:
        sources.append((acs_hisp, 0.50))
    if ind_hisp:
        sources.append((ind_hisp, 0.30))
    if tract_hisp:
        sources.append((tract_hisp, 0.20))

    if not sources:
        return None
    if len(sources) == 1:
        return sources[0][0]
    return _blend_dicts(sources, HISP_CATS)


# ============================================================
# Evaluation
# ============================================================

METHODS = {
    'A_county_ipf': hisp_baseline_county_ipf,
    'B_expert_b_tract': hisp_expert_b,
    'C_industry_lodes_ipf': hisp_industry_lodes_ipf,
    'D_industry_tract_blend': hisp_industry_lodes_tract_blend,
    'E_occ_chain_county': hisp_occ_chain,
    'F_occ_chain_industry': hisp_occ_chain_industry_lodes,
    'G_pums_industry_tract': hisp_pums_industry_lodes_tract,
    'H_three_layer_industry': hisp_three_layer_industry,
    'I_occ_chain_three_layer': hisp_occ_chain_three_layer,
}


def evaluate_hispanic(records, method_fn, cl):
    """Evaluate a Hispanic estimation method on a set of records."""
    errors = []
    signed_errors = []
    for rec in records:
        truth_hisp = rec['truth'].get('hispanic')
        if not truth_hisp or 'Hispanic' not in truth_hisp:
            continue
        pred = method_fn(
            cl, rec['naics4'], rec['state_fips'], rec['county_fips'],
            zipcode=rec.get('zipcode', ''),
            naics_group=rec.get('naics_group', ''),
            cbsa_code=rec.get('cbsa_code', ''),
        )
        if not pred or 'Hispanic' not in pred:
            continue
        err = abs(pred['Hispanic'] - truth_hisp['Hispanic'])
        errors.append(err)
        signed_errors.append(pred['Hispanic'] - truth_hisp['Hispanic'])
    if not errors:
        return None
    n = len(errors)
    mae = sum(errors) / n
    bias = sum(signed_errors) / n
    p_gt_10 = sum(1 for e in errors if e > 10) / n * 100
    p_gt_15 = sum(1 for e in errors if e > 15) / n * 100
    p_gt_20 = sum(1 for e in errors if e > 20) / n * 100
    return {
        'n': n,
        'mae': round(mae, 3),
        'bias': round(bias, 3),
        'p_gt_10pp': round(p_gt_10, 2),
        'p_gt_15pp': round(p_gt_15, 2),
        'p_gt_20pp': round(p_gt_20, 2),
    }


def evaluate_by_region(records, method_fn, cl):
    regions = ['South', 'West', 'Northeast', 'Midwest']
    out = {}
    for region in regions:
        subset = [r for r in records if r.get('region') == region]
        result = evaluate_hispanic(subset, method_fn, cl)
        out[region] = result['mae'] if result else None
    return out


def evaluate_by_sector(records, method_fn, cl):
    sectors = ['Healthcare/Social (62)', 'Admin/Staffing (56)',
               'Finance/Insurance (52)', 'Construction (23)',
               'Accommodation/Food (72)']
    out = {}
    for sector in sectors:
        subset = [r for r in records if r.get('naics_group') == sector]
        result = evaluate_hispanic(subset, method_fn, cl)
        out[sector] = result['mae'] if result else None
    return out


def main():
    t0 = time.time()
    print('IMPROVED HISPANIC ESTIMATION TEST')
    print('=' * 80)

    # Build splits
    splits = build_splits()
    all_companies = (splits['train_companies'] + splits['dev_companies']
                     + list(splits['perm_companies']))
    print('Training: %d | Dev: %d | Permanent: %d' % (
        len(splits['train_companies']),
        len(splits['dev_companies']),
        len(splits['perm_companies']),
    ))

    # Load ground truth
    by_code_year, by_code = build_truth_lookup()

    # DB connection
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Quick sanity check: does industry LODES Hispanic data exist?
    test_result = cl.get_lodes_industry_hispanic('06037', '62')  # LA County, Healthcare
    print('Industry LODES Hispanic sanity check (LA County, Healthcare):')
    if test_result:
        print('  Hispanic: %.1f%%, Not Hispanic: %.1f%%' % (
            test_result['Hispanic'], test_result['Not Hispanic']))
    else:
        print('  No data found -- check if lodes_county_industry_demographics table has Hispanic columns')

    # Build records for all companies
    print('\nBuilding records...')
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

        all_records.append({
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
        })

    # Split records
    train_records = [r for r in all_records if r['company_code'] in splits['train_codes']]
    dev_records = [r for r in all_records if r['company_code'] in splits['dev_codes']]
    perm_records = [r for r in all_records if r['company_code'] in splits['perm_codes']]
    all_holdout = dev_records + perm_records

    print('Records with Hispanic truth: train=%d, dev=%d, perm=%d' % (
        len(train_records), len(dev_records), len(perm_records)))

    # Evaluate all methods on training set first (to pick winner)
    print('\n' + '=' * 80)
    print('PHASE 1: TRAINING SET EVALUATION (pick best method)')
    print('=' * 80)

    train_results = {}
    for name, fn in METHODS.items():
        result = evaluate_hispanic(train_records, fn, cl)
        train_results[name] = result
        if result:
            print('  %-30s MAE=%.3f  bias=%+.3f  P>10pp=%.1f%%  P>15pp=%.1f%%  n=%d' % (
                name, result['mae'], result['bias'],
                result['p_gt_10pp'], result['p_gt_15pp'], result['n']))

    # Sort by MAE
    ranked = sorted(
        [(n, r) for n, r in train_results.items() if r],
        key=lambda x: x[1]['mae'])

    print('\nRanking (training):')
    for i, (name, result) in enumerate(ranked, 1):
        marker = ' <-- WINNER' if i == 1 else ''
        gap = result['mae'] - ranked[0][1]['mae']
        print('  %d. %-30s MAE=%.3f  (+%.3f)%s' % (
            i, name, result['mae'], gap, marker))

    winner_name = ranked[0][0]
    winner_fn = METHODS[winner_name]

    # Phase 2: Evaluate on both holdouts
    print('\n' + '=' * 80)
    print('PHASE 2: HOLDOUT EVALUATION')
    print('=' * 80)

    for set_name, records in [('All 2,525 holdout', all_holdout),
                               ('Dev 1,525', dev_records),
                               ('Permanent 1,000', perm_records)]:
        print('\n--- %s ---' % set_name)
        for name, fn in METHODS.items():
            result = evaluate_hispanic(records, fn, cl)
            if result:
                print('  %-30s MAE=%.3f  bias=%+.3f  P>10pp=%.1f%%  P>15pp=%.1f%%  P>20pp=%.1f%%' % (
                    name, result['mae'], result['bias'],
                    result['p_gt_10pp'], result['p_gt_15pp'], result['p_gt_20pp']))

    # Phase 3: Regional breakdown for top methods
    print('\n' + '=' * 80)
    print('PHASE 3: REGIONAL BREAKDOWN (permanent holdout)')
    print('=' * 80)

    top_methods = [ranked[0][0], ranked[1][0], 'A_county_ipf', 'B_expert_b_tract']
    top_methods = list(dict.fromkeys(top_methods))  # dedupe preserving order

    print('\n%-30s  %-8s %-8s %-8s %-8s' % ('Method', 'South', 'West', 'NE', 'MW'))
    for name in top_methods:
        fn = METHODS[name]
        regions = evaluate_by_region(perm_records, fn, cl)
        print('%-30s  %-8s %-8s %-8s %-8s' % (
            name,
            '%.3f' % regions['South'] if regions['South'] else '--',
            '%.3f' % regions['West'] if regions['West'] else '--',
            '%.3f' % regions['Northeast'] if regions['Northeast'] else '--',
            '%.3f' % regions['Midwest'] if regions['Midwest'] else '--',
        ))

    # Phase 4: Sector breakdown for top methods
    print('\n' + '=' * 80)
    print('PHASE 4: SECTOR BREAKDOWN (permanent holdout)')
    print('=' * 80)

    for name in top_methods:
        fn = METHODS[name]
        sectors = evaluate_by_sector(perm_records, fn, cl)
        print('\n%-30s' % name)
        for sector, mae in sectors.items():
            print('  %-30s  MAE=%.3f' % (sector, mae) if mae else
                  '  %-30s  --' % sector)

    # Phase 5: Check coverage -- how often does industry LODES provide data?
    print('\n' + '=' * 80)
    print('PHASE 5: INDUSTRY LODES HISPANIC COVERAGE')
    print('=' * 80)

    ind_available = 0
    ind_total = 0
    for rec in all_holdout:
        ind_total += 1
        ind_hisp, source = cl.get_industry_or_county_lodes_hispanic(
            rec['county_fips'], rec['naics4'])
        if source == 'lodes_industry':
            ind_available += 1

    print('Industry-specific LODES Hispanic available: %d / %d (%.1f%%)' % (
        ind_available, ind_total,
        ind_available / ind_total * 100 if ind_total else 0))

    # Check occ-chain coverage
    occ_available = 0
    for rec in all_holdout:
        occ = cl.get_occ_chain_demographics(rec['naics_group'], rec['state_fips'])
        if occ and occ.get('Hispanic') is not None:
            occ_available += 1
    print('Occ-chain Hispanic available: %d / %d (%.1f%%)' % (
        occ_available, ind_total,
        occ_available / ind_total * 100 if ind_total else 0))

    # Summary
    print('\n' + '=' * 80)
    print('SUMMARY')
    print('=' * 80)
    print('Winner on training: %s' % winner_name)
    winner_perm = evaluate_hispanic(perm_records, winner_fn, cl)
    baseline_perm = evaluate_hispanic(perm_records, METHODS['A_county_ipf'], cl)
    expert_b_perm = evaluate_hispanic(perm_records, METHODS['B_expert_b_tract'], cl)

    print('\nPermanent holdout comparison:')
    print('  Current baseline (A/D/E/F): MAE=%.3f' % baseline_perm['mae'])
    print('  Expert B (current best):    MAE=%.3f' % expert_b_perm['mae'])
    print('  Winner (%s): MAE=%.3f' % (winner_name, winner_perm['mae']))
    print('  V8 post-cal reference:      MAE=7.111')
    print('  V6 post-cal reference:      MAE=7.752')

    improvement = expert_b_perm['mae'] - winner_perm['mae']
    print('\nImprovement over Expert B: %+.3f pp' % (-improvement)
          if improvement < 0 else
          '\nImprovement over Expert B: -%.3f pp' % improvement)

    print('\nCache stats: %d hits, %d misses (%.1f%% hit rate)' % (
        cl.hits, cl.misses,
        cl.hits / (cl.hits + cl.misses) * 100 if (cl.hits + cl.misses) else 0))
    print('Runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
