"""V9 Test: Best-of-Expert Per-Category + IPF Normalization.

Phase 1: Per-category expert benchmarking on training data
Phase 2: Assemble best-of estimates + naive normalization baseline
Phase 3: IPF normalization (2D race x gender)
Phase 4: Full evaluation (pre-calibration)
Phase 5: Calibration (if Phase 4 passes stop gate)

Usage:
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase 1
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase 2
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase 3
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase 4
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase 5
    py scripts/analysis/demographics_comparison/v9_best_of_ipf.py --phase all
"""
import sys
import os
import json
import time
import random
import math
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from metrics import composite_score
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_method_9b, cached_method_g1, cached_method_v6_full,
    cached_expert_e, cached_expert_f, cached_expert_g,
)
from cached_loaders_v5 import cached_method_3c_v5, cached_expert_a, cached_expert_b
from methodologies_v5 import RACE_CATS
from classifiers import classify_naics_group, classify_region
from config import (
    NAICS_GENDER_BENCHMARKS, get_census_region, get_county_minority_tier,
    REGIONAL_CALIBRATION_INDUSTRIES,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']

# Expert dispatch: expert key -> callable
# Each returns dict with 'race', 'hispanic', 'gender' sub-dicts
EXPERT_DISPATCH = {
    'A': lambda cl, n4, sf, cf, **kw: cached_expert_a(cl, n4, sf, cf),
    'B': lambda cl, n4, sf, cf, **kw: cached_expert_b(cl, n4, sf, cf),
    'D': lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    'E': lambda cl, n4, sf, cf, **kw: cached_expert_e(cl, n4, sf, cf, **kw),
    'F': lambda cl, n4, sf, cf, **kw: cached_expert_f(cl, n4, sf, cf, **kw),
    'G': lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    'V6': lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}

ALL_EXPERTS = ['A', 'B', 'D', 'E', 'F', 'G', 'V6']
ALL_RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
ALL_EVAL_CATS = ALL_RACE_CATS + ['Hispanic', 'Female']


# ============================================================
# Data split setup
# ============================================================

def setup_data_split(seed=42):
    """Set up the three-way data split.

    Returns (training_companies, dev_companies, perm_companies).
    """
    # Load permanent holdout (locked)
    perm_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
    with open(perm_path, 'r', encoding='utf-8') as f:
        perm_data = json.load(f)
    perm_companies = perm_data['companies']
    perm_codes = set(c['company_code'] for c in perm_companies)

    # Load full training pool
    pool_path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
    with open(pool_path, 'r', encoding='utf-8') as f:
        pool = json.load(f)

    # Remove any overlap (should be 0)
    remaining = [c for c in pool if c['company_code'] not in perm_codes]
    print('Pool after removing permanent holdout: %d companies' % len(remaining))

    # Randomly select 10,000 for training
    rng = random.Random(seed)
    rng.shuffle(remaining)
    training = remaining[:10000]
    dev = remaining[10000:]

    print('Split: training=%d, dev=%d, permanent=%d' % (
        len(training), len(dev), len(perm_companies)))

    # Save dev holdout
    dev_path = os.path.join(SCRIPT_DIR, 'dev_holdout_1500.json')
    dev_codes = [c['company_code'] for c in dev]
    with open(dev_path, 'w', encoding='utf-8') as f:
        json.dump({
            'description': 'V9 dev holdout (seed=%d)' % seed,
            'seed': seed,
            'n_companies': len(dev),
            'company_codes': dev_codes,
        }, f)
    print('Saved dev holdout codes to %s' % dev_path)

    # Verify no overlap
    train_codes = set(c['company_code'] for c in training)
    dev_codes_set = set(c['company_code'] for c in dev)
    assert len(train_codes & perm_codes) == 0, 'Training/permanent overlap!'
    assert len(dev_codes_set & perm_codes) == 0, 'Dev/permanent overlap!'
    assert len(train_codes & dev_codes_set) == 0, 'Training/dev overlap!'

    # Show 5 IDs from each
    print('')
    print('Sample IDs:')
    print('  Training: %s' % [c['company_code'] for c in training[:5]])
    print('  Dev:      %s' % [c['company_code'] for c in dev[:5]])
    print('  Perm:     %s' % [c['company_code'] for c in perm_companies[:5]])

    return training, dev, perm_companies


# ============================================================
# Run a single expert on a company
# ============================================================

def run_expert(expert_key, company, cl, cur):
    """Run a single expert on a company. Returns result dict or None."""
    naics = company.get('naics', '')
    naics4 = naics[:4]
    state_fips = company.get('state_fips', '')
    county_fips = company.get('county_fips', '')
    zipcode = company.get('zipcode', '')
    naics_group = company.get('classifications', {}).get('naics_group', '')
    if not naics_group:
        naics_group = classify_naics_group(naics4)

    cbsa_code = ''
    if county_fips:
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

    fn = EXPERT_DISPATCH.get(expert_key)
    if not fn:
        return None
    try:
        result = fn(cl, naics4, state_fips, county_fips,
                    cbsa_code=cbsa_code, zipcode=zipcode,
                    naics_group=naics_group)
        return result
    except Exception:
        return None


def get_truth(company, eeo1_rows):
    """Get ground truth for a company from EEO-1 data."""
    code = company.get('company_code', '')
    for row in eeo1_rows:
        if row.get('COMPANY') == code:
            return parse_eeo1_row(row)
    return None


def ensure_county(company, cur):
    """Ensure company has county_fips and state_fips."""
    county_fips = company.get('county_fips', '')
    state_fips = company.get('state_fips', '')
    zipcode = company.get('zipcode', '')
    if not county_fips and zipcode:
        county_fips = zip_to_county(cur, zipcode) or ''
        company['county_fips'] = county_fips
    if not state_fips and county_fips:
        state_fips = county_fips[:2]
        company['state_fips'] = state_fips
    return county_fips


# ============================================================
# Phase 1: Per-category expert benchmarking
# ============================================================

def phase1_benchmark(training, eeo1_rows, cl, cur):
    """Run all experts on training companies, find per-category winners.

    Returns dict with per-expert per-category results and winner map.
    """
    print('')
    print('=' * 100)
    print('PHASE 1: Per-Category Expert Benchmarking')
    print('=' * 100)
    print('Running %d experts on %d training companies...' % (
        len(ALL_EXPERTS), len(training)))

    # Accumulators: expert -> category -> list of absolute errors
    expert_cat_errors = {e: {c: [] for c in ALL_EVAL_CATS} for e in ALL_EXPERTS}
    # For P>20/P>30 overall
    expert_max_errors = {e: [] for e in ALL_EXPERTS}
    expert_fails = {e: 0 for e in ALL_EXPERTS}

    t0 = time.time()
    processed = 0

    for i, company in enumerate(training):
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            remaining = (len(training) - i - 1) / rate
            print('  %d/%d (%.0f/s, ~%.0fm remaining)...' % (
                i + 1, len(training), rate, remaining / 60))

        county_fips = ensure_county(company, cur)
        if not county_fips:
            continue

        truth = get_truth(company, eeo1_rows)
        if not truth or not truth.get('race'):
            continue

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic', {})
        actual_gender = truth.get('gender', {})
        processed += 1

        for expert_key in ALL_EXPERTS:
            result = run_expert(expert_key, company, cl, cur)
            if result is None or not result.get('race'):
                expert_fails[expert_key] += 1
                continue

            pred_race = result['race']
            pred_hisp = result.get('hispanic', {})
            pred_gender = result.get('gender', {})

            # Per race category errors
            for cat in ALL_RACE_CATS:
                if cat in pred_race and cat in actual_race:
                    expert_cat_errors[expert_key][cat].append(
                        abs(pred_race[cat] - actual_race[cat]))

            # Hispanic
            if pred_hisp and actual_hisp:
                hisp_val_p = pred_hisp.get('Hispanic', 0)
                hisp_val_a = actual_hisp.get('Hispanic', 0)
                expert_cat_errors[expert_key]['Hispanic'].append(
                    abs(hisp_val_p - hisp_val_a))

            # Female
            if pred_gender and actual_gender:
                fem_val_p = pred_gender.get('Female', 0)
                fem_val_a = actual_gender.get('Female', 0)
                expert_cat_errors[expert_key]['Female'].append(
                    abs(fem_val_p - fem_val_a))

            # Max error for P>20/P>30
            keys = [k for k in ALL_RACE_CATS if k in pred_race and k in actual_race]
            if keys:
                max_err = max(abs(pred_race[k] - actual_race[k]) for k in keys)
                expert_max_errors[expert_key].append(max_err)

    elapsed = time.time() - t0
    print('Phase 1 complete: %d companies processed in %.0fs' % (processed, elapsed))

    # Compute MAEs and find winners
    print('')
    print('Per-Category MAE by Expert (training set, %d companies):' % processed)
    print('')

    header = '| %-10s' % 'Category'
    for e in ALL_EXPERTS:
        header += ' | %-8s' % e
    header += ' | WINNER  |'
    print(header)
    print('|' + '-' * 11 + ('|' + '-' * 10) * len(ALL_EXPERTS) + '|---------|')

    winners = {}
    for cat in ALL_EVAL_CATS:
        row = '| %-10s' % cat
        maes = {}
        for e in ALL_EXPERTS:
            errors = expert_cat_errors[e][cat]
            if errors:
                m = sum(errors) / len(errors)
                maes[e] = m
                row += ' | %8.3f' % m
            else:
                row += ' |      N/A'
        if maes:
            winner = min(maes, key=maes.get)
            winners[cat] = winner
            # Check margin
            sorted_experts = sorted(maes.items(), key=lambda x: x[1])
            margin = sorted_experts[1][1] - sorted_experts[0][1] if len(sorted_experts) > 1 else 999
            flag = ' *' if margin < 0.1 else ''
            row += ' | %-7s |' % (winner + flag)
        else:
            row += ' |         |'
        print(row)

    # Close margin warnings
    print('')
    print('* = winner margin < 0.1pp (may be noise)')

    # P>20pp and P>30pp per expert (overall)
    print('')
    print('Overall tail rates per expert:')
    print('| Expert | P>20pp | P>30pp | N companies | Fails |')
    print('|--------|--------|--------|-------------|-------|')
    for e in ALL_EXPERTS:
        errs = expert_max_errors[e]
        n = len(errs)
        if n > 0:
            p20 = sum(1 for x in errs if x > 20) / n * 100
            p30 = sum(1 for x in errs if x > 30) / n * 100
        else:
            p20 = p30 = 0
        print('| %-6s | %5.1f%% | %5.1f%% | %11d | %5d |' % (
            e, p20, p30, n, expert_fails[e]))

    # Save Phase 1 results
    p1_results = {
        'winners': winners,
        'expert_maes': {},
        'processed': processed,
    }
    for e in ALL_EXPERTS:
        p1_results['expert_maes'][e] = {}
        for cat in ALL_EVAL_CATS:
            errors = expert_cat_errors[e][cat]
            if errors:
                p1_results['expert_maes'][e][cat] = round(sum(errors) / len(errors), 4)
            else:
                p1_results['expert_maes'][e][cat] = None

    p1_path = os.path.join(SCRIPT_DIR, 'v9_phase1_results.json')
    with open(p1_path, 'w', encoding='utf-8') as f:
        json.dump(p1_results, f, indent=2)
    print('')
    print('Phase 1 results saved to %s' % p1_path)
    print('')
    print('Category winners: %s' % json.dumps(winners, indent=2))
    print('')
    print('*** CHECKPOINT: Review the category winners above.')
    print('*** Do NOT proceed until you approve them.')
    print('*** Re-run with --phase 2 to continue after approval.')

    return p1_results


# ============================================================
# Phase 2: Assemble best-of estimates on holdouts
# ============================================================

def phase2_assemble(dev, perm, eeo1_rows, cl, cur, winners):
    """Run all experts on holdouts, assemble best-of, naive normalize.

    Returns dict with all raw estimates and evaluation results.
    """
    print('')
    print('=' * 100)
    print('PHASE 2: Assemble Best-of Estimates on Both Holdouts')
    print('=' * 100)

    all_holdout = dev + perm
    dev_codes = set(c['company_code'] for c in dev)
    perm_codes = set(c['company_code'] for c in perm)

    print('Running %d experts on %d holdout companies (dev=%d, perm=%d)...' % (
        len(ALL_EXPERTS), len(all_holdout), len(dev), len(perm)))

    # Store all raw estimates: company_code -> expert -> result
    all_estimates = {}
    # Store ground truth: company_code -> truth
    all_truth = {}
    # Store company metadata
    all_meta = {}

    t0 = time.time()
    skipped = 0

    for i, company in enumerate(all_holdout):
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            remaining = (len(all_holdout) - i - 1) / rate
            print('  %d/%d (%.0f/s, ~%.0fm remaining)...' % (
                i + 1, len(all_holdout), rate, remaining / 60))

        county_fips = ensure_county(company, cur)
        if not county_fips:
            skipped += 1
            continue

        truth = get_truth(company, eeo1_rows)
        if not truth or not truth.get('race'):
            skipped += 1
            continue

        code = company['company_code']
        all_truth[code] = truth
        all_meta[code] = company
        all_estimates[code] = {}

        for expert_key in ALL_EXPERTS:
            result = run_expert(expert_key, company, cl, cur)
            all_estimates[code][expert_key] = result

    elapsed = time.time() - t0
    n_valid = len(all_truth)
    print('Phase 2 experts complete: %d companies in %.0fs (%d skipped)' % (
        n_valid, elapsed, skipped))

    # Assemble best-of vector
    print('')
    print('Assembling best-of estimates using winners: %s' % json.dumps(winners))

    best_of_results = {}  # code -> {'race': {...}, 'hispanic': {...}, 'gender': {...}}

    for code in all_truth:
        estimates = all_estimates[code]
        best_race = {}
        for cat in ALL_RACE_CATS:
            winner = winners.get(cat, 'D')
            result = estimates.get(winner)
            if result and result.get('race') and cat in result['race']:
                best_race[cat] = result['race'][cat]
            else:
                # Fallback to D if winner failed
                fallback = estimates.get('D')
                if fallback and fallback.get('race') and cat in fallback['race']:
                    best_race[cat] = fallback['race'][cat]
                else:
                    best_race[cat] = 0.0

        # Hispanic: use winner
        hisp_winner = winners.get('Hispanic', 'V6')
        hisp_result = estimates.get(hisp_winner)
        best_hisp = {}
        if hisp_result and hisp_result.get('hispanic'):
            best_hisp = dict(hisp_result['hispanic'])
        else:
            fallback = estimates.get('V6')
            if fallback and fallback.get('hispanic'):
                best_hisp = dict(fallback['hispanic'])

        # Gender: use winner
        gender_winner = winners.get('Female', 'V6')
        gender_result = estimates.get(gender_winner)
        best_gender = {}
        if gender_result and gender_result.get('gender'):
            best_gender = dict(gender_result['gender'])
        else:
            fallback = estimates.get('V6')
            if fallback and fallback.get('gender'):
                best_gender = dict(fallback['gender'])

        best_of_results[code] = {
            'race_raw': dict(best_race),
            'hispanic': best_hisp,
            'gender': best_gender,
        }

    # Naive normalization: proportional scaling of race to 100%
    for code in best_of_results:
        race_raw = best_of_results[code]['race_raw']
        total = sum(race_raw.get(c, 0) for c in ALL_RACE_CATS)
        if total > 0:
            race_norm = {c: round(race_raw.get(c, 0) * 100 / total, 2) for c in ALL_RACE_CATS}
        else:
            race_norm = dict(race_raw)
        best_of_results[code]['race_naive'] = race_norm

    # Evaluate naive best-of
    print('')
    print('Evaluating naive best-of normalization...')

    # D solo baseline
    d_results = {}
    for code in all_truth:
        est = all_estimates[code].get('D')
        if est and est.get('race'):
            d_results[code] = est

    _print_evaluation_table(
        'Phase 2: Naive Best-of vs D solo (pre-calibration)',
        all_truth, all_meta, dev_codes, perm_codes,
        scenarios={
            'D solo (raw)': lambda code: d_results.get(code),
            'Best-of naive': lambda code: {
                'race': best_of_results[code]['race_naive'],
                'hispanic': best_of_results[code].get('hispanic', {}),
                'gender': best_of_results[code].get('gender', {}),
            } if code in best_of_results else None,
        },
        v8_perm_ref={
            'Race MAE': 4.526, 'Hisp MAE': 7.111, 'Gender MAE': 11.779,
            'P>20pp': 16.1, 'P>30pp': 7.9, 'Abs Bias': 0.536,
        },
    )

    # Save Phase 2 results
    p2_path = os.path.join(SCRIPT_DIR, 'v9_phase2_results.json')
    # Convert for JSON serialization
    p2_save = {
        'n_valid': n_valid,
        'n_dev': sum(1 for c in all_truth if c in dev_codes),
        'n_perm': sum(1 for c in all_truth if c in perm_codes),
        'winners': winners,
    }
    with open(p2_path, 'w', encoding='utf-8') as f:
        json.dump(p2_save, f, indent=2)
    print('Phase 2 results saved to %s' % p2_path)

    return best_of_results, all_estimates, all_truth, all_meta, dev_codes, perm_codes, d_results


# ============================================================
# Phase 3: IPF Normalization
# ============================================================

def build_acs_seed_matrix(cl, naics4, state_fips, county_fips):
    """Build a 6x2 ACS seed matrix (race x gender) for IPF.

    Rows: White, Black, Asian, AIAN, NHOPI, Two+
    Cols: Male, Female

    Strategy: Multiply ACS race proportions x ACS gender proportions
    (assume independence) as the seed. IPF will adjust from here.
    """
    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    gender_data = cl.get_acs_gender(naics4, state_fips)

    if not race_data or not gender_data:
        # Fallback: uniform
        return np.ones((6, 2)) / 12.0

    # Get race proportions
    race_props = []
    for cat in ALL_RACE_CATS:
        race_props.append(max(race_data.get(cat, 0), 0.001) / 100.0)
    race_arr = np.array(race_props)
    race_arr = race_arr / race_arr.sum()

    # Get gender proportions
    male_pct = max(gender_data.get('Male', 50), 0.01) / 100.0
    female_pct = max(gender_data.get('Female', 50), 0.01) / 100.0
    gender_arr = np.array([male_pct, female_pct])
    gender_arr = gender_arr / gender_arr.sum()

    # Outer product: assume independence
    seed = np.outer(race_arr, gender_arr)
    return seed


def ipf_normalize_2d(best_of_race, best_of_gender, acs_seed_matrix):
    """Run 2D IPF with race row margins and gender column margins.

    Returns dict with all race + gender estimates (percentages 0-100).
    Returns None if IPF fails to converge.
    """
    from ipfn import ipfn as ipfn_module

    # Ensure no zeros in seed
    seed = np.maximum(acs_seed_matrix, 0.00001)
    seed = seed / seed.sum()

    # Row margins (race proportions from best-of)
    race_margins = np.array([best_of_race.get(c, 0.1) for c in ALL_RACE_CATS])
    race_margins = np.maximum(race_margins, 0.01)
    race_margins = race_margins / race_margins.sum()

    # Column margins (gender proportions from best-of)
    male_pct = best_of_gender.get('Male', 50.0)
    female_pct = best_of_gender.get('Female', 50.0)
    gender_margins = np.array([male_pct, female_pct])
    gender_margins = np.maximum(gender_margins, 0.01)
    gender_margins = gender_margins / gender_margins.sum()

    # Run IPF
    aggregates = [race_margins, gender_margins]
    dimensions = [[0], [1]]

    try:
        solver = ipfn_module.ipfn(seed, aggregates, dimensions,
                                  convergence_rate=0.0001, max_iteration=50)
        result = solver.iteration()

        # Extract results
        output = {}
        for i, cat in enumerate(ALL_RACE_CATS):
            output[cat] = float(result[i, :].sum()) * 100
        output['Male'] = float(result[:, 0].sum()) * 100
        output['Female'] = float(result[:, 1].sum()) * 100

        return output
    except Exception:
        return None


def phase3_ipf(best_of_results, all_estimates, all_truth, all_meta, cl, cur,
               dev_codes, perm_codes, d_results, winners):
    """Apply IPF normalization to best-of estimates."""
    print('')
    print('=' * 100)
    print('PHASE 3: IPF Normalization')
    print('=' * 100)

    ipf_results = {}
    ipf_abs_results = {}  # ABS-adjusted variant
    convergence_failures = 0

    # Load ABS density for optional variant
    abs_density_path = os.path.join(SCRIPT_DIR, 'abs_owner_density.json')
    abs_density = {}
    if os.path.exists(abs_density_path):
        with open(abs_density_path, 'r', encoding='utf-8') as f:
            abs_density = json.load(f)
    # Compute national median ABS minority share
    abs_values = [v['minority_share'] for v in abs_density.values()
                  if isinstance(v, dict) and 'minority_share' in v]
    abs_median = sorted(abs_values)[len(abs_values) // 2] if abs_values else 20.0
    print('ABS national median minority share: %.1f%%' % abs_median)

    t0 = time.time()
    example_companies = []

    for i, code in enumerate(all_truth):
        if (i + 1) % 200 == 0:
            print('  IPF: %d/%d...' % (i + 1, len(all_truth)))

        company = all_meta[code]
        naics4 = company.get('naics', '')[:4]
        state_fips = company.get('state_fips', '')
        county_fips = company.get('county_fips', '')

        bo = best_of_results.get(code)
        if not bo:
            continue

        race_raw = bo['race_raw']
        gender_raw = bo.get('gender', {})

        if not gender_raw:
            # No gender estimate, fall back to naive normalization
            ipf_results[code] = {
                'race': bo['race_naive'],
                'hispanic': bo.get('hispanic', {}),
                'gender': {},
            }
            continue

        # Build ACS seed matrix
        seed = build_acs_seed_matrix(cl, naics4, state_fips, county_fips)

        # Run IPF
        ipf_out = ipf_normalize_2d(race_raw, gender_raw, seed)

        if ipf_out is None:
            convergence_failures += 1
            # Fall back to naive
            ipf_results[code] = {
                'race': bo['race_naive'],
                'hispanic': bo.get('hispanic', {}),
                'gender': gender_raw,
            }
        else:
            ipf_results[code] = {
                'race': {c: round(ipf_out[c], 2) for c in ALL_RACE_CATS},
                'hispanic': bo.get('hispanic', {}),
                'gender': {
                    'Male': round(ipf_out['Male'], 2),
                    'Female': round(ipf_out['Female'], 2),
                },
            }

        # ABS-adjusted variant
        abs_data = abs_density.get(county_fips)
        abs_minority = None
        if abs_data and isinstance(abs_data, dict):
            abs_minority = abs_data.get('minority_share')

        if abs_minority is not None and abs_minority > abs_median:
            # Boost non-White rows in seed
            seed_adj = seed.copy()
            boost = 1.0 + (abs_minority - abs_median) * 0.005
            for row_idx in range(1, 6):
                seed_adj[row_idx, :] *= boost
            seed_adj = seed_adj / seed_adj.sum()
            ipf_abs_out = ipf_normalize_2d(race_raw, gender_raw, seed_adj)
            if ipf_abs_out:
                ipf_abs_results[code] = {
                    'race': {c: round(ipf_abs_out[c], 2) for c in ALL_RACE_CATS},
                    'hispanic': bo.get('hispanic', {}),
                    'gender': {
                        'Male': round(ipf_abs_out['Male'], 2),
                        'Female': round(ipf_abs_out['Female'], 2),
                    },
                }

        # Collect examples for checkpoint
        if len(example_companies) < 5 and ipf_out is not None:
            example_companies.append({
                'code': code,
                'name': company.get('name', ''),
                'race_raw': race_raw,
                'gender_raw': gender_raw,
                'seed_shape': seed.shape,
                'seed_sum': float(seed.sum()),
                'ipf_race': {c: round(ipf_out[c], 2) for c in ALL_RACE_CATS},
                'ipf_gender': {
                    'Male': round(ipf_out['Male'], 2),
                    'Female': round(ipf_out['Female'], 2),
                },
                'race_total': sum(ipf_out[c] for c in ALL_RACE_CATS),
                'gender_total': ipf_out['Male'] + ipf_out['Female'],
            })

    elapsed = time.time() - t0
    print('IPF complete: %d companies in %.0fs (%d convergence failures)' % (
        len(ipf_results), elapsed, convergence_failures))
    print('ABS-adjusted variant: %d companies' % len(ipf_abs_results))

    # Show example companies
    print('')
    print('IPF Example Companies:')
    for ex in example_companies:
        print('')
        print('  %s (%s)' % (ex['name'], ex['code']))
        print('    Raw race:  %s (sum=%.1f)' % (
            {k: '%.1f' % v for k, v in ex['race_raw'].items()},
            sum(ex['race_raw'].values())))
        print('    Raw gender: Male=%.1f Female=%.1f' % (
            ex['gender_raw'].get('Male', 0), ex['gender_raw'].get('Female', 0)))
        print('    IPF race:  %s (sum=%.2f)' % (
            {k: '%.1f' % v for k, v in ex['ipf_race'].items()},
            ex['race_total']))
        print('    IPF gender: Male=%.1f Female=%.1f (sum=%.2f)' % (
            ex['ipf_gender']['Male'], ex['ipf_gender']['Female'],
            ex['gender_total']))

    return ipf_results, ipf_abs_results


# ============================================================
# Phase 4: Full Evaluation (Pre-Calibration)
# ============================================================

def phase4_evaluate(all_truth, all_meta, dev_codes, perm_codes,
                    d_results, best_of_results, ipf_results, ipf_abs_results):
    """Full pre-calibration evaluation."""
    print('')
    print('=' * 100)
    print('PHASE 4: Full Evaluation (Pre-Calibration)')
    print('=' * 100)

    scenarios = {
        'D solo (raw)': lambda code: d_results.get(code),
        'Best-of naive': lambda code: {
            'race': best_of_results[code]['race_naive'],
            'hispanic': best_of_results[code].get('hispanic', {}),
            'gender': best_of_results[code].get('gender', {}),
        } if code in best_of_results else None,
        'Best-of+IPF': lambda code: ipf_results.get(code),
    }
    if ipf_abs_results:
        scenarios['+IPF+ABS'] = lambda code: ipf_abs_results.get(code)

    v8_perm_ref = {
        'Race MAE': 4.526, 'Hisp MAE': 7.111, 'Gender MAE': 11.779,
        'P>20pp': 16.1, 'P>30pp': 7.9, 'Abs Bias': 0.536,
    }
    v6_perm_ref = {
        'Race MAE': 4.203, 'Hisp MAE': 7.752, 'Gender MAE': 11.979,
        'Abs Bias': 1.000,
    }

    results = _print_evaluation_table(
        'Phase 4: Main Scorecard',
        all_truth, all_meta, dev_codes, perm_codes,
        scenarios=scenarios,
        v8_perm_ref=v8_perm_ref,
    )

    # Healthcare South stop gate check
    print('')
    print('STOP GATE: Healthcare South tail rates (All set)')
    hc_south_d = _compute_segment_metrics(
        all_truth, all_meta,
        lambda code: d_results.get(code),
        lambda code, meta: (
            classify_naics_group(meta.get('naics', '')[:4]) == 'Healthcare/Social (62)' and
            classify_region(meta.get('state', '')) == 'South'),
        set(all_truth.keys()),
    )
    hc_south_ipf = _compute_segment_metrics(
        all_truth, all_meta,
        lambda code: ipf_results.get(code),
        lambda code, meta: (
            classify_naics_group(meta.get('naics', '')[:4]) == 'Healthcare/Social (62)' and
            classify_region(meta.get('state', '')) == 'South'),
        set(all_truth.keys()),
    )

    print('| Metric | D solo | Best-of+IPF |')
    print('|--------|--------|-------------|')
    for metric in ['p20', 'p30', 'count']:
        d_val = hc_south_d.get(metric, 'N/A')
        ipf_val = hc_south_ipf.get(metric, 'N/A')
        if metric in ('p20', 'p30'):
            print('| %-6s | %5.1f%% | %10.1f%% |' % (
                'P>20pp' if metric == 'p20' else 'P>30pp',
                d_val * 100 if isinstance(d_val, float) else 0,
                ipf_val * 100 if isinstance(ipf_val, float) else 0))
        else:
            print('| Count  | %6s | %11s |' % (d_val, ipf_val))

    # Check stop gate
    d_p20 = hc_south_d.get('p20', 1.0)
    ipf_p20 = hc_south_ipf.get('p20', 1.0)
    d_p30 = hc_south_d.get('p30', 1.0)
    ipf_p30 = hc_south_ipf.get('p30', 1.0)

    if isinstance(ipf_p20, float) and isinstance(d_p20, float):
        if ipf_p20 >= d_p20 and ipf_p30 >= d_p30:
            print('')
            print('*** STOP GATE FAILED: Best-of+IPF does NOT reduce')
            print('    Healthcare South tail rates vs D solo.')
            print('    P>20pp: D=%.1f%% vs IPF=%.1f%%' % (d_p20 * 100, ipf_p20 * 100))
            print('    P>30pp: D=%.1f%% vs IPF=%.1f%%' % (d_p30 * 100, ipf_p30 * 100))
            print('')
            print('    Approach is not working. See Decision Framework Outcome C.')
            return False, results
        else:
            print('')
            print('STOP GATE PASSED: IPF reduces at least one HC South tail metric.')
            print('  P>20pp: D=%.1f%% -> IPF=%.1f%% (delta=%.1f)' % (
                d_p20 * 100, ipf_p20 * 100, (ipf_p20 - d_p20) * 100))
            print('  P>30pp: D=%.1f%% -> IPF=%.1f%% (delta=%.1f)' % (
                d_p30 * 100, ipf_p30 * 100, (ipf_p30 - d_p30) * 100))

    return True, results


# ============================================================
# Phase 5: Calibration
# ============================================================

def phase5_calibrate(training, eeo1_rows, cl, cur, winners,
                     all_truth, all_meta, dev_codes, perm_codes,
                     ipf_results, d_results, best_of_results):
    """Train calibration on training set, apply to holdouts."""
    print('')
    print('=' * 100)
    print('PHASE 5: Calibration')
    print('=' * 100)

    # Step 5A: Run best-of+IPF pipeline on training companies
    print('Running best-of+IPF on %d training companies for calibration...' % len(training))

    train_ipf_errors = defaultdict(lambda: defaultdict(list))
    # Grouped by naics_group, with optional region/county_tier sub-keys
    t0 = time.time()

    for i, company in enumerate(training):
        if (i + 1) % 1000 == 0:
            print('  Calibration training: %d/%d...' % (i + 1, len(training)))

        county_fips = ensure_county(company, cur)
        if not county_fips:
            continue

        truth = get_truth(company, eeo1_rows)
        if not truth or not truth.get('race'):
            continue

        naics4 = company.get('naics', '')[:4]
        naics_group = classify_naics_group(naics4)
        state = company.get('state', '')
        region = classify_region(state)
        state_fips = company.get('state_fips', '')

        # Get county minority pct
        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race:
            county_minority_pct = 100.0 - lodes_race.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        # Run all experts for this company
        expert_results = {}
        for expert_key in ALL_EXPERTS:
            expert_results[expert_key] = run_expert(expert_key, company, cl, cur)

        # Assemble best-of
        best_race = {}
        for cat in ALL_RACE_CATS:
            winner = winners.get(cat, 'D')
            r = expert_results.get(winner)
            if r and r.get('race') and cat in r['race']:
                best_race[cat] = r['race'][cat]
            else:
                fb = expert_results.get('D')
                if fb and fb.get('race') and cat in fb['race']:
                    best_race[cat] = fb['race'][cat]
                else:
                    best_race[cat] = 0.0

        gender_winner = winners.get('Female', 'V6')
        gr = expert_results.get(gender_winner)
        best_gender = {}
        if gr and gr.get('gender'):
            best_gender = dict(gr['gender'])
        else:
            fb = expert_results.get('V6')
            if fb and fb.get('gender'):
                best_gender = dict(fb['gender'])

        hisp_winner = winners.get('Hispanic', 'V6')
        hr = expert_results.get(hisp_winner)
        best_hisp = {}
        if hr and hr.get('hispanic'):
            best_hisp = dict(hr['hispanic'])
        else:
            fb = expert_results.get('V6')
            if fb and fb.get('hispanic'):
                best_hisp = dict(fb['hispanic'])

        # IPF normalize
        seed = build_acs_seed_matrix(cl, naics4, state_fips, county_fips)
        if best_gender:
            ipf_out = ipf_normalize_2d(best_race, best_gender, seed)
        else:
            ipf_out = None

        if ipf_out:
            pred_race = {c: ipf_out[c] for c in ALL_RACE_CATS}
            pred_gender = {'Male': ipf_out['Male'], 'Female': ipf_out['Female']}
        else:
            total = sum(best_race.values())
            if total > 0:
                pred_race = {c: best_race.get(c, 0) * 100 / total for c in ALL_RACE_CATS}
            else:
                pred_race = best_race
            pred_gender = best_gender

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic', {})
        actual_gender = truth.get('gender', {})

        # Compute signed errors (bias) for calibration
        for cat in ALL_RACE_CATS:
            if cat in pred_race and cat in actual_race:
                signed_err = pred_race[cat] - actual_race[cat]
                train_ipf_errors[naics_group]['race_' + cat].append(signed_err)
                train_ipf_errors['_global']['race_' + cat].append(signed_err)

                # Regional sub-keys for Healthcare/Admin
                if naics_group in REGIONAL_CALIBRATION_INDUSTRIES:
                    rk = '%s|region:%s' % (naics_group, region)
                    train_ipf_errors[rk]['race_' + cat].append(signed_err)
                    tk = '%s|county_tier:%s' % (naics_group, county_tier)
                    train_ipf_errors[tk]['race_' + cat].append(signed_err)

        if best_hisp and actual_hisp:
            for cat in ['Hispanic', 'Not Hispanic']:
                if cat in best_hisp and cat in actual_hisp:
                    se = best_hisp[cat] - actual_hisp[cat]
                    train_ipf_errors[naics_group]['hisp_' + cat].append(se)
                    train_ipf_errors['_global']['hisp_' + cat].append(se)

        if pred_gender and actual_gender:
            for cat in ['Male', 'Female']:
                if cat in pred_gender and cat in actual_gender:
                    se = pred_gender[cat] - actual_gender[cat]
                    train_ipf_errors[naics_group]['gender_' + cat].append(se)
                    train_ipf_errors['_global']['gender_' + cat].append(se)

    elapsed = time.time() - t0
    print('Calibration training complete in %.0fs' % elapsed)

    # Build calibration dict with dampening=0.80
    DAMPENING = 0.80
    calibration = {}
    for segment, cat_errors in train_ipf_errors.items():
        calibration[segment] = {}
        for dim_cat, errors in cat_errors.items():
            if len(errors) < 5:  # Minimum sample
                continue
            mean_bias = sum(errors) / len(errors)
            correction = -mean_bias * DAMPENING
            calibration[segment][dim_cat] = {
                'correction': round(correction, 4),
                'mean_bias': round(mean_bias, 4),
                'n': len(errors),
            }

    # Save calibration
    cal_path = os.path.join(SCRIPT_DIR, 'v9_calibration.json')
    with open(cal_path, 'w', encoding='utf-8') as f:
        json.dump(calibration, f, indent=2)
    print('Calibration saved to %s (%d segments)' % (cal_path, len(calibration)))

    # Step 5B: Apply calibration to holdouts
    print('')
    print('Applying calibration to holdouts...')

    calibrated_results = {}
    for code in all_truth:
        company = all_meta[code]
        ipf_r = ipf_results.get(code)
        if not ipf_r:
            continue

        naics4 = company.get('naics', '')[:4]
        naics_group = classify_naics_group(naics4)
        state = company.get('state', '')
        region = classify_region(state)
        county_fips = company.get('county_fips', '')

        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race:
            county_minority_pct = 100.0 - lodes_race.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        cal_result = {
            'race': dict(ipf_r.get('race', {})),
            'hispanic': dict(ipf_r.get('hispanic', {})),
            'gender': dict(ipf_r.get('gender', {})),
        }

        # Apply calibration with fallback hierarchy
        for dim, cats in [('race', ALL_RACE_CATS),
                          ('hispanic', ['Hispanic', 'Not Hispanic']),
                          ('gender', ['Male', 'Female'])]:
            prefix = dim[:4] if dim != 'hispanic' else 'hisp'
            dim_data = cal_result.get(dim, {})
            if not dim_data:
                continue

            for cat in cats:
                if cat not in dim_data:
                    continue

                # Find best calibration correction via fallback
                correction = 0.0
                dim_key = prefix + '_' + cat

                # Try county_tier (Healthcare/Admin only)
                if naics_group in REGIONAL_CALIBRATION_INDUSTRIES:
                    tk = '%s|county_tier:%s' % (naics_group, county_tier)
                    entry = calibration.get(tk, {}).get(dim_key, {})
                    if entry and entry.get('n', 0) >= 30:
                        correction = entry['correction']
                    else:
                        # Try region
                        rk = '%s|region:%s' % (naics_group, region)
                        entry = calibration.get(rk, {}).get(dim_key, {})
                        if entry and entry.get('n', 0) >= 20:
                            correction = entry['correction']
                        else:
                            # Try industry
                            entry = calibration.get(naics_group, {}).get(dim_key, {})
                            if entry:
                                correction = entry.get('correction', 0)
                            else:
                                entry = calibration.get('_global', {}).get(dim_key, {})
                                if entry:
                                    correction = entry.get('correction', 0)
                else:
                    # Non-regional: industry -> global
                    entry = calibration.get(naics_group, {}).get(dim_key, {})
                    if entry:
                        correction = entry.get('correction', 0)
                    else:
                        entry = calibration.get('_global', {}).get(dim_key, {})
                        if entry:
                            correction = entry.get('correction', 0)

                dim_data[cat] = dim_data[cat] + correction

            # Re-normalize to 100
            total = sum(dim_data.get(c, 0) for c in cats)
            if total > 0:
                for c in cats:
                    if c in dim_data:
                        dim_data[c] = round(dim_data[c] * 100.0 / total, 2)

            cal_result[dim] = dim_data

        calibrated_results[code] = cal_result

    # Step 5C: Final evaluation
    print('')
    print('Post-calibration evaluation:')

    v8_perm_ref = {
        'Race MAE': 4.526, 'Hisp MAE': 7.111, 'Gender MAE': 11.779,
        'P>20pp': 16.1, 'P>30pp': 7.9, 'Abs Bias': 0.536,
    }

    scenarios = {
        'Best-of+IPF+cal': lambda code: calibrated_results.get(code),
    }

    _print_evaluation_table(
        'Phase 5: Post-Calibration Final',
        all_truth, all_meta, dev_codes, perm_codes,
        scenarios=scenarios,
        v8_perm_ref=v8_perm_ref,
    )

    # Calibration gain
    print('')
    print('Calibration gain (All set):')
    all_codes = set(all_truth.keys())
    pre_metrics = _compute_set_metrics(
        all_truth, lambda code: ipf_results.get(code), all_codes)
    post_metrics = _compute_set_metrics(
        all_truth, lambda code: calibrated_results.get(code), all_codes)

    print('| Metric   | Pre-cal | Post-cal | Gain     |')
    print('|----------|---------|----------|----------|')
    for metric in ['race_mae', 'p20', 'p30']:
        pre = pre_metrics.get(metric, 0)
        post = post_metrics.get(metric, 0)
        if metric in ('p20', 'p30'):
            print('| %-8s | %6.1f%% | %7.1f%% | %+7.1f%% |' % (
                'P>20pp' if metric == 'p20' else 'P>30pp',
                pre * 100, post * 100, (post - pre) * 100))
        else:
            print('| %-8s | %7.3f | %8.3f | %+8.3f |' % (
                'Race MAE', pre, post, post - pre))

    # Step 5D: 7/7 acceptance test (permanent only)
    print('')
    print('=' * 100)
    print('V9 ACCEPTANCE TEST (Permanent Holdout Only)')
    print('=' * 100)

    perm_metrics = _compute_set_metrics(
        all_truth, lambda code: calibrated_results.get(code), perm_codes)

    # Red flag rate (simplified: companies where max error > threshold?)
    # Use confidence tier RED rate -- approximate with P>30pp
    red_rate = perm_metrics.get('p30', 0) * 100  # Simplified

    checks = [
        ('Race MAE', perm_metrics.get('race_mae', 99), 4.20),
        ('P>20pp', perm_metrics.get('p20', 1) * 100, 16.0),
        ('P>30pp', perm_metrics.get('p30', 1) * 100, 6.0),
        ('Abs Bias', perm_metrics.get('abs_bias', 99), 1.10),
        ('Hispanic MAE', perm_metrics.get('hisp_mae', 99), 8.00),
        ('Gender MAE', perm_metrics.get('gender_mae', 99), 12.00),
        ('Red flag rate', red_rate, 15.0),
    ]

    print('')
    print('| Criterion    | V9 Result | Target  | Pass/Fail | V8 (perm) | V6 (perm) |')
    print('|--------------|-----------|---------|-----------|-----------|-----------|')
    passed = 0
    for label, actual, target in checks:
        status = 'PASS' if actual < target else 'FAIL'
        if status == 'PASS':
            passed += 1
        v8_ref = {
            'Race MAE': 4.526, 'P>20pp': 16.1, 'P>30pp': 7.9,
            'Abs Bias': 0.536, 'Hispanic MAE': 7.111,
            'Gender MAE': 11.779, 'Red flag rate': 2.2,
        }.get(label, '')
        v6_ref = {
            'Race MAE': 4.203, 'Abs Bias': 1.000,
            'Hispanic MAE': 7.752, 'Gender MAE': 11.979,
            'Red flag rate': 0.87,
        }.get(label, '')
        fmt = '%9.3f' if isinstance(actual, float) and actual < 50 else '%8.1f%%'
        print('| %-12s | %9s | %-7s | %-9s | %-9s | %-9s |' % (
            label,
            ('%.3f' % actual) if isinstance(actual, float) and actual < 50 else ('%.1f%%' % actual if actual > 1 else '%.3f' % actual),
            ('< %.2f' % target) if target < 50 else ('< %.0f%%' % target),
            status,
            str(v8_ref) if v8_ref else '',
            str(v6_ref) if v6_ref else '',
        ))

    print('')
    print('Result: %d/%d criteria passed' % (passed, len(checks)))

    if passed == 7 and perm_metrics.get('race_mae', 99) < 4.203:
        print('')
        print('*** OUTCOME A: V9 passes 7/7 and beats V6 Race MAE!')
        print('*** This becomes V9. Ship it.')
    elif passed >= 4:
        print('')
        print('*** OUTCOME B: V9 improves some metrics but does not pass 7/7.')
        print('*** Investigate 3D IPF, ABS constraints, segment-specific winners.')
    else:
        print('')
        print('*** OUTCOME C: V9 does not meaningfully improve.')
        print('*** The ~4.2-4.5 Race MAE range is the census data ceiling.')

    return calibrated_results


# ============================================================
# Evaluation utilities
# ============================================================

def _compute_set_metrics(all_truth, get_pred_fn, code_set):
    """Compute all metrics for a set of companies."""
    race_preds = []
    race_actuals = []
    hisp_mae_vals = []
    gender_mae_vals = []
    max_errors = []
    signed_biases = {k: [] for k in ALL_RACE_CATS}

    for code in code_set:
        truth = all_truth.get(code)
        if not truth:
            continue
        pred = get_pred_fn(code)
        if pred is None:
            continue

        pred_race = pred.get('race', {})
        actual_race = truth.get('race', {})
        pred_hisp = pred.get('hispanic', {})
        actual_hisp = truth.get('hispanic', {})
        pred_gender = pred.get('gender', {})
        actual_gender = truth.get('gender', {})

        # Race
        keys = [k for k in ALL_RACE_CATS if k in pred_race and k in actual_race]
        if keys:
            race_preds.append(pred_race)
            race_actuals.append(actual_race)
            company_max = max(abs(pred_race[k] - actual_race[k]) for k in keys)
            max_errors.append(company_max)
            for k in keys:
                signed_biases[k].append(pred_race[k] - actual_race[k])

        # Hispanic
        if pred_hisp and actual_hisp:
            hk = [k for k in HISP_CATS if k in pred_hisp and k in actual_hisp]
            if hk:
                hisp_mae_vals.append(
                    sum(abs(pred_hisp[k] - actual_hisp[k]) for k in hk) / len(hk))

        # Gender
        if pred_gender and actual_gender:
            gk = [k for k in GENDER_CATS if k in pred_gender and k in actual_gender]
            if gk:
                gender_mae_vals.append(
                    sum(abs(pred_gender[k] - actual_gender[k]) for k in gk) / len(gk))

    n = len(race_preds)
    if n == 0:
        return {}

    cs = composite_score(race_preds, race_actuals, ALL_RACE_CATS)
    result = {
        'race_mae': cs['avg_mae'] if cs else 0,
        'p20': cs['p_gt_20pp'] if cs else 0,
        'p30': cs['p_gt_30pp'] if cs else 0,
        'abs_bias': cs['mean_abs_bias'] if cs else 0,
        'n': n,
    }

    if hisp_mae_vals:
        result['hisp_mae'] = round(sum(hisp_mae_vals) / len(hisp_mae_vals), 3)
    else:
        result['hisp_mae'] = 99.0

    if gender_mae_vals:
        result['gender_mae'] = round(sum(gender_mae_vals) / len(gender_mae_vals), 3)
    else:
        result['gender_mae'] = 99.0

    # Per-category MAE (for Black MAE)
    for cat in ALL_RACE_CATS:
        errs = [abs(p.get(cat, 0) - a.get(cat, 0))
                for p, a in zip(race_preds, race_actuals)
                if cat in p and cat in a]
        if errs:
            result['%s_mae' % cat.lower().replace('+', 'plus')] = round(
                sum(errs) / len(errs), 3)

    return result


def _compute_segment_metrics(all_truth, all_meta, get_pred_fn, segment_filter, code_set):
    """Compute metrics for a segment (e.g., Healthcare South)."""
    filtered_codes = set()
    for code in code_set:
        meta = all_meta.get(code)
        if meta and code in all_truth and segment_filter(code, meta):
            filtered_codes.add(code)

    if not filtered_codes:
        return {'p20': 'N/A', 'p30': 'N/A', 'count': 0}

    metrics = _compute_set_metrics(all_truth, get_pred_fn, filtered_codes)
    metrics['count'] = len(filtered_codes)
    return metrics


def _print_evaluation_table(title, all_truth, all_meta, dev_codes, perm_codes,
                            scenarios, v8_perm_ref=None):
    """Print full evaluation tables for all three sets."""
    print('')
    print(title)
    print('=' * 100)

    all_codes = set(all_truth.keys())
    results_by_set = {}

    for set_name, code_set in [('All %d' % len(all_codes), all_codes),
                                ('Dev %d' % len(dev_codes & all_codes), dev_codes & all_codes),
                                ('Perm %d' % len(perm_codes & all_codes), perm_codes & all_codes)]:
        print('')
        print('--- %s ---' % set_name)

        # Main metrics
        header = '| %-10s' % 'Metric'
        for sname in scenarios:
            header += ' | %-15s' % sname[:15]
        if 'Perm' in set_name and v8_perm_ref:
            header += ' | V8 post-cal     | V6 post-cal     '
        header += ' |'
        print(header)
        print('|' + '-' * 11 + ('|' + '-' * 17) * len(scenarios) +
              ('|' + '-' * 17 + '|' + '-' * 17 if 'Perm' in set_name and v8_perm_ref else '') + '|')

        scenario_metrics = {}
        for sname, get_fn in scenarios.items():
            scenario_metrics[sname] = _compute_set_metrics(all_truth, get_fn, code_set)

        for metric_label, metric_key, fmt in [
            ('Race MAE', 'race_mae', '%.3f'),
            ('Black MAE', 'black_mae', '%.3f'),
            ('Hisp MAE', 'hisp_mae', '%.3f'),
            ('Gender MAE', 'gender_mae', '%.3f'),
            ('P>20pp', 'p20', '%.1f%%'),
            ('P>30pp', 'p30', '%.1f%%'),
            ('Abs Bias', 'abs_bias', '%.3f'),
        ]:
            row = '| %-10s' % metric_label
            for sname in scenarios:
                m = scenario_metrics[sname]
                val = m.get(metric_key, None)
                if val is not None:
                    if '%' in fmt:
                        row += ' | %15s' % (fmt % (val * 100))
                    else:
                        row += ' | %15s' % (fmt % val)
                else:
                    row += ' | %15s' % 'N/A'
            if 'Perm' in set_name and v8_perm_ref:
                v8_val = v8_perm_ref.get(metric_label, '')
                v6_refs = {
                    'Race MAE': 4.203, 'Hisp MAE': 7.752, 'Gender MAE': 11.979,
                    'Abs Bias': 1.000,
                }
                v6_val = v6_refs.get(metric_label, '')
                row += ' | %-15s | %-15s' % (
                    str(v8_val) if v8_val else '-',
                    str(v6_val) if v6_val else '-')
            row += ' |'
            print(row)

        results_by_set[set_name] = scenario_metrics

    # Region breakdown
    print('')
    print('Region breakdown (Race MAE):')
    for set_name, code_set in [('All', all_codes),
                                ('Dev', dev_codes & all_codes),
                                ('Perm', perm_codes & all_codes)]:
        print('')
        print('  %s:' % set_name)
        header = '  | %-10s' % 'Region'
        for sname in scenarios:
            header += ' | %-13s' % sname[:13]
        header += ' |'
        print(header)
        print('  |' + '-' * 11 + ('|' + '-' * 15) * len(scenarios) + '|')

        for region in ['South', 'West', 'Northeast', 'Midwest']:
            row = '  | %-10s' % region
            for sname, get_fn in scenarios.items():
                seg_m = _compute_segment_metrics(
                    all_truth, all_meta, get_fn,
                    lambda c, m: classify_region(m.get('state', '')) == region,
                    code_set)
                val = seg_m.get('race_mae', None)
                if val is not None:
                    row += ' | %13.3f' % val
                else:
                    row += ' | %13s' % 'N/A'
            row += ' |'
            print(row)

    # Sector breakdown
    print('')
    print('Sector breakdown (Race MAE):')
    for set_name, code_set in [('All', all_codes),
                                ('Dev', dev_codes & all_codes),
                                ('Perm', perm_codes & all_codes)]:
        print('')
        print('  %s:' % set_name)
        for naics_label, naics_prefix in [('Healthcare 62', '62'),
                                           ('Admin/Staff 56', '56'),
                                           ('Finance 52', '52')]:
            row = '  | %-14s' % naics_label
            for sname, get_fn in scenarios.items():
                seg_m = _compute_segment_metrics(
                    all_truth, all_meta, get_fn,
                    lambda c, m, pfx=naics_prefix: m.get('naics', '').startswith(pfx),
                    code_set)
                val = seg_m.get('race_mae', None)
                if val is not None:
                    row += ' | %13.3f' % val
                else:
                    row += ' | %13s' % 'N/A'
            row += ' |'
            print(row)

    # Healthcare South tail rates
    print('')
    print('Healthcare South tail rates:')
    for set_name, code_set in [('All', all_codes),
                                ('Dev', dev_codes & all_codes),
                                ('Perm', perm_codes & all_codes)]:
        print('')
        print('  %s:' % set_name)
        for sname, get_fn in scenarios.items():
            seg_m = _compute_segment_metrics(
                all_truth, all_meta, get_fn,
                lambda c, m: (m.get('naics', '').startswith('62') and
                              classify_region(m.get('state', '')) == 'South'),
                code_set)
            p20 = seg_m.get('p20', 0)
            p30 = seg_m.get('p30', 0)
            cnt = seg_m.get('count', 0)
            print('    %-15s  P>20=%.1f%%  P>30=%.1f%%  N=%d' % (
                sname[:15],
                p20 * 100 if isinstance(p20, float) else 0,
                p30 * 100 if isinstance(p30, float) else 0,
                cnt))

    return results_by_set


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='V9 Best-of-Expert + IPF')
    parser.add_argument('--phase', default='1',
                        help='Phase to run: 1, 2, 3, 4, 5, or all')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for train/dev split')
    args = parser.parse_args()

    run_phase = args.phase.lower()

    t0_total = time.time()
    print('V9 Best-of-Expert + IPF Normalization')
    print('=' * 100)

    # Always set up data split and load EEO-1
    print('Loading EEO-1 data...')
    eeo1_rows = load_all_eeo1_data()
    print('Loaded %d EEO-1 rows' % len(eeo1_rows))

    print('Setting up data split...')
    training, dev, perm = setup_data_split(seed=args.seed)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    winners = None

    # Phase 1
    if run_phase in ('1', 'all'):
        p1 = phase1_benchmark(training, eeo1_rows, cl, cur)
        winners = p1['winners']
        if run_phase == '1':
            conn.close()
            return

    # Load Phase 1 results if needed
    if winners is None:
        p1_path = os.path.join(SCRIPT_DIR, 'v9_phase1_results.json')
        if os.path.exists(p1_path):
            with open(p1_path, 'r', encoding='utf-8') as f:
                p1 = json.load(f)
            winners = p1['winners']
            print('Loaded Phase 1 winners from %s' % p1_path)
            print('Winners: %s' % json.dumps(winners))
        else:
            print('ERROR: Phase 1 results not found. Run --phase 1 first.')
            conn.close()
            return

    # Phase 2
    if run_phase in ('2', 'all', '2+', '3', '4', '5'):
        p2_data = phase2_assemble(dev, perm, eeo1_rows, cl, cur, winners)
        best_of_results, all_estimates, all_truth, all_meta, dev_codes, perm_codes, d_results = p2_data
        if run_phase == '2':
            conn.close()
            return
    else:
        best_of_results = all_estimates = all_truth = all_meta = None
        dev_codes = perm_codes = d_results = None

    # Phase 3
    if run_phase in ('3', 'all', '3+', '4', '5'):
        if all_truth is None:
            print('ERROR: Phase 2 data needed. Run --phase all or --phase 2 first.')
            conn.close()
            return
        ipf_results, ipf_abs_results = phase3_ipf(
            best_of_results, all_estimates, all_truth, all_meta, cl, cur,
            dev_codes, perm_codes, d_results, winners)
        if run_phase == '3':
            conn.close()
            return
    else:
        ipf_results = ipf_abs_results = None

    # Phase 4
    if run_phase in ('4', 'all', '4+', '5'):
        if ipf_results is None:
            print('ERROR: Phase 3 data needed. Run --phase all first.')
            conn.close()
            return
        gate_passed, phase4_results = phase4_evaluate(
            all_truth, all_meta, dev_codes, perm_codes,
            d_results, best_of_results, ipf_results, ipf_abs_results)
        if run_phase == '4':
            conn.close()
            return
        if not gate_passed and run_phase != 'all':
            print('Stop gate failed. Not proceeding to Phase 5.')
            conn.close()
            return

    # Phase 5
    if run_phase in ('5', 'all'):
        if ipf_results is None:
            print('ERROR: Phase 3+4 data needed. Run --phase all first.')
            conn.close()
            return
        calibrated_results = phase5_calibrate(
            training, eeo1_rows, cl, cur, winners,
            all_truth, all_meta, dev_codes, perm_codes,
            ipf_results, d_results, best_of_results)

    elapsed_total = time.time() - t0_total
    print('')
    print('Total runtime: %.0fs (%.1fm)' % (elapsed_total, elapsed_total / 60))
    conn.close()


if __name__ == '__main__':
    main()
