"""V9 Hybrid Test: Expert D base + Occupation-chain adjustment.

Instead of using Expert G as a separate model, extract the occupation-chain
signal and use it to adjust Expert D's estimates. This avoids G's broken
Two+ residual while capturing G's occupation-based diversity signal.

Approach:
  1. Get Expert D's base estimate (IPF of ACS + LODES)
  2. Get the occupation-chain demographics (raw, before G's 70/30 blend)
  3. Compute the "occ_divergence" = occ_chain[cat] - D[cat] for key categories
  4. Apply a weighted adjustment: D_adjusted[cat] = D[cat] + weight * occ_divergence
  5. Test multiple adjustment weights (0.10 to 0.50) to find optimal

The key hypothesis: when occupation-chain says "this industry in this state
has more Black workers than the census geography suggests", that signal is
valuable because occupational composition captures workforce diversity that
county-level census data misses.

Usage:
    py test_hybrid_d_occ.py --holdout selected_permanent_holdout_1000.json
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
from cached_loaders_v6 import CachedLoadersV6
from cached_loaders_v5 import cached_method_3c_v5
from methodologies_v5 import RACE_CATS
from config import get_census_region, get_county_minority_tier

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']

# Categories where occ_chain signal is reliable
# Skip Two+ (garbage residual) and NHOPI (always 0 in occ_chain)
OCC_RELIABLE_CATS = ['White', 'Black', 'Asian', 'AIAN']


def build_hybrid(d_race, occ_chain, weight, adjust_cats=None):
    """Adjust D's estimate using occupation-chain divergence.

    For each category in adjust_cats:
        adjusted[cat] = D[cat] + weight * (occ_chain[cat] - D[cat])

    This is equivalent to: adjusted[cat] = (1-weight) * D[cat] + weight * occ_chain[cat]

    Categories NOT in adjust_cats keep D's original estimate.
    After adjustment, renormalize all categories to sum to 100%.
    """
    if adjust_cats is None:
        adjust_cats = OCC_RELIABLE_CATS

    result = {}
    for cat in RACE_CATS:
        d_val = d_race.get(cat, 0)
        if cat in adjust_cats and cat in occ_chain:
            occ_val = occ_chain.get(cat, 0)
            divergence = occ_val - d_val
            result[cat] = d_val + weight * divergence
        else:
            result[cat] = d_val

    # Clamp negatives
    for cat in RACE_CATS:
        result[cat] = max(0.0, result[cat])

    # Renormalize to 100
    total = sum(result[cat] for cat in RACE_CATS)
    if total > 0:
        for cat in RACE_CATS:
            result[cat] = result[cat] * 100.0 / total

    return result


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
    print('V9 HYBRID D + OCC-CHAIN TEST')
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

    # Collect per-company data
    all_data = []
    occ_available = 0
    occ_missing = 0

    for i, company in enumerate(companies):
        if (i + 1) % 100 == 0:
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

        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', classify_naics_group(naics4))
        region = get_census_region(state_abbr)
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race:
            county_minority_pct = 100.0 - lodes_race.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        # Expert D base estimate
        try:
            d_result = cached_method_3c_v5(cl, naics4, state_fips, county_fips)
        except Exception:
            d_result = None
        if not d_result or not d_result.get('race'):
            continue

        d_race = d_result['race']

        # Raw occupation-chain signal (NOT Expert G's blended output)
        occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
        has_occ = occ_chain is not None and occ_chain.get('_pct_covered', 0) >= 40

        if has_occ:
            occ_available += 1
        else:
            occ_missing += 1

        all_data.append({
            'code': code,
            'naics_group': naics_group,
            'region': region,
            'county_tier': county_tier,
            'state': state_abbr,
            'actual_race': actual_race,
            'actual_hisp': actual_hisp,
            'd_race': d_race,
            'occ_chain': occ_chain if has_occ else None,
            'has_occ': has_occ,
        })

    n = len(all_data)
    print('\nProcessed %d companies in %.0fs' % (n, time.time() - t0))
    print('Occ-chain available: %d (%.1f%%), missing: %d' % (
        occ_available, occ_available / n * 100, occ_missing))

    # ================================================================
    # Test multiple adjustment weights
    # ================================================================
    print()
    print('=' * 70)
    print('WEIGHT SWEEP: Optimal occ-chain adjustment weight')
    print('=' * 70)
    print()

    weights = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]

    print('%-8s %9s %9s %9s %9s %9s %9s %9s' % (
        'Weight', 'Race MAE', 'Black MAE', 'White MAE', 'P>20pp', 'P>30pp',
        'W bias', 'B bias'))
    print('-' * 80)

    best_weight = 0.0
    best_mae = 999.0
    weight_results = {}

    for w in weights:
        race_maes = []
        max_errors = []
        black_abs = []
        white_abs = []
        white_signed = []
        black_signed = []

        for c in all_data:
            if c['has_occ'] and w > 0:
                pred = build_hybrid(c['d_race'], c['occ_chain'], w)
            else:
                pred = c['d_race']

            m = mae_cats(pred, c['actual_race'], RACE_CATS)
            mx = max_cat_error(pred, c['actual_race'], RACE_CATS)
            if m is not None:
                race_maes.append(m)
            if mx is not None:
                max_errors.append(mx)

            if 'Black' in pred and 'Black' in c['actual_race']:
                black_abs.append(abs(pred['Black'] - c['actual_race']['Black']))
                black_signed.append(pred['Black'] - c['actual_race']['Black'])
            if 'White' in pred and 'White' in c['actual_race']:
                white_abs.append(abs(pred['White'] - c['actual_race']['White']))
                white_signed.append(pred['White'] - c['actual_race']['White'])

        race_mae = sum(race_maes) / len(race_maes)
        black_mae = sum(black_abs) / len(black_abs) if black_abs else 0
        white_mae = sum(white_abs) / len(white_abs) if white_abs else 0
        p20 = sum(1 for e in max_errors if e > 20) / len(max_errors) * 100
        p30 = sum(1 for e in max_errors if e > 30) / len(max_errors) * 100
        w_bias = sum(white_signed) / len(white_signed) if white_signed else 0
        b_bias = sum(black_signed) / len(black_signed) if black_signed else 0

        print('%-8s %9.3f %9.3f %9.3f %8.1f%% %8.1f%% %+8.2f %+8.2f' % (
            '%.2f' % w, race_mae, black_mae, white_mae, p20, p30, w_bias, b_bias))

        weight_results[w] = {
            'race_mae': race_mae, 'black_mae': black_mae, 'white_mae': white_mae,
            'p20': p20, 'p30': p30, 'w_bias': w_bias, 'b_bias': b_bias,
        }

        if race_mae < best_mae:
            best_mae = race_mae
            best_weight = w

    print()
    print('Best weight: %.2f (Race MAE: %.3f)' % (best_weight, best_mae))

    # ================================================================
    # Test Black-only adjustment (adjust only Black, let White stay from D)
    # ================================================================
    print()
    print('=' * 70)
    print('BLACK-ONLY ADJUSTMENT (adjust Black from occ, keep D for White)')
    print('=' * 70)
    print()

    print('%-8s %9s %9s %9s %9s %9s %9s %9s' % (
        'Weight', 'Race MAE', 'Black MAE', 'White MAE', 'P>20pp', 'P>30pp',
        'W bias', 'B bias'))
    print('-' * 80)

    best_bo_weight = 0.0
    best_bo_mae = 999.0

    for w in weights:
        race_maes = []
        max_errors = []
        black_abs = []
        white_abs = []
        white_signed = []
        black_signed = []

        for c in all_data:
            if c['has_occ'] and w > 0:
                pred = build_hybrid(c['d_race'], c['occ_chain'], w,
                                    adjust_cats=['Black'])
            else:
                pred = c['d_race']

            m = mae_cats(pred, c['actual_race'], RACE_CATS)
            mx = max_cat_error(pred, c['actual_race'], RACE_CATS)
            if m is not None:
                race_maes.append(m)
            if mx is not None:
                max_errors.append(mx)

            if 'Black' in pred and 'Black' in c['actual_race']:
                black_abs.append(abs(pred['Black'] - c['actual_race']['Black']))
                black_signed.append(pred['Black'] - c['actual_race']['Black'])
            if 'White' in pred and 'White' in c['actual_race']:
                white_abs.append(abs(pred['White'] - c['actual_race']['White']))
                white_signed.append(pred['White'] - c['actual_race']['White'])

        race_mae = sum(race_maes) / len(race_maes)
        black_mae = sum(black_abs) / len(black_abs) if black_abs else 0
        white_mae = sum(white_abs) / len(white_abs) if white_abs else 0
        p20 = sum(1 for e in max_errors if e > 20) / len(max_errors) * 100
        p30 = sum(1 for e in max_errors if e > 30) / len(max_errors) * 100
        w_bias = sum(white_signed) / len(white_signed) if white_signed else 0
        b_bias = sum(black_signed) / len(black_signed) if black_signed else 0

        print('%-8s %9.3f %9.3f %9.3f %8.1f%% %8.1f%% %+8.2f %+8.2f' % (
            '%.2f' % w, race_mae, black_mae, white_mae, p20, p30, w_bias, b_bias))

        if race_mae < best_bo_mae:
            best_bo_mae = race_mae
            best_bo_weight = w

    print()
    print('Best Black-only weight: %.2f (Race MAE: %.3f)' % (best_bo_weight, best_bo_mae))

    # ================================================================
    # Test with best weight: segment breakdown
    # ================================================================
    best_w = best_weight if best_weight > 0 else 0.15  # use 0.15 if 0.0 was best

    print()
    print('=' * 70)
    print('SEGMENT BREAKDOWN at weight=%.2f (all cats) vs D solo' % best_w)
    print('=' * 70)
    print()

    # Per-region
    print('PER-REGION:')
    print('%-15s %10s %10s %10s' % ('Region', 'D solo', 'Hybrid', 'Delta'))
    print('-' * 45)
    for region in ['South', 'West', 'Northeast', 'Midwest']:
        d_errs = []
        h_errs = []
        for c in all_data:
            if c['region'] != region:
                continue
            d_m = mae_cats(c['d_race'], c['actual_race'], RACE_CATS)
            if c['has_occ']:
                h_pred = build_hybrid(c['d_race'], c['occ_chain'], best_w)
            else:
                h_pred = c['d_race']
            h_m = mae_cats(h_pred, c['actual_race'], RACE_CATS)
            if d_m is not None:
                d_errs.append(d_m)
            if h_m is not None:
                h_errs.append(h_m)
        d_mae = sum(d_errs) / len(d_errs) if d_errs else 0
        h_mae = sum(h_errs) / len(h_errs) if h_errs else 0
        delta = h_mae - d_mae
        print('%-15s %10.3f %10.3f %+10.3f  (N=%d)' % (region, d_mae, h_mae, delta, len(d_errs)))

    # Per-industry (key sectors)
    print()
    print('PER-INDUSTRY:')
    sectors = ['Healthcare/Social (62)', 'Admin/Staffing (56)', 'Finance/Insurance (52)',
               'Professional/Technical (54)', 'Construction (23)']
    print('%-35s %10s %10s %10s' % ('Industry', 'D solo', 'Hybrid', 'Delta'))
    print('-' * 65)
    for sector in sectors:
        d_errs = []
        h_errs = []
        for c in all_data:
            if c['naics_group'] != sector:
                continue
            d_m = mae_cats(c['d_race'], c['actual_race'], RACE_CATS)
            if c['has_occ']:
                h_pred = build_hybrid(c['d_race'], c['occ_chain'], best_w)
            else:
                h_pred = c['d_race']
            h_m = mae_cats(h_pred, c['actual_race'], RACE_CATS)
            if d_m is not None:
                d_errs.append(d_m)
            if h_m is not None:
                h_errs.append(h_m)
        d_mae = sum(d_errs) / len(d_errs) if d_errs else 0
        h_mae = sum(h_errs) / len(h_errs) if h_errs else 0
        delta = h_mae - d_mae
        print('%-35s %10.3f %10.3f %+10.3f  (N=%d)' % (sector, d_mae, h_mae, delta, len(d_errs)))

    # Per-county-tier
    print()
    print('PER-COUNTY-TIER:')
    print('%-15s %10s %10s %10s' % ('Tier', 'D solo', 'Hybrid', 'Delta'))
    print('-' * 45)
    for tier in ['low', 'medium', 'high']:
        d_errs = []
        h_errs = []
        for c in all_data:
            if c['county_tier'] != tier:
                continue
            d_m = mae_cats(c['d_race'], c['actual_race'], RACE_CATS)
            if c['has_occ']:
                h_pred = build_hybrid(c['d_race'], c['occ_chain'], best_w)
            else:
                h_pred = c['d_race']
            h_m = mae_cats(h_pred, c['actual_race'], RACE_CATS)
            if d_m is not None:
                d_errs.append(d_m)
            if h_m is not None:
                h_errs.append(h_m)
        d_mae = sum(d_errs) / len(d_errs) if d_errs else 0
        h_mae = sum(h_errs) / len(h_errs) if h_errs else 0
        delta = h_mae - d_mae
        print('%-15s %10.3f %10.3f %+10.3f  (N=%d)' % (tier, d_mae, h_mae, delta, len(d_errs)))

    # ================================================================
    # Occ-chain coverage by sector
    # ================================================================
    print()
    print('=' * 70)
    print('OCC-CHAIN COVERAGE BY SECTOR')
    print('=' * 70)
    print()
    print('%-35s %8s %8s %8s' % ('Industry', 'Has Occ', 'Missing', '% Avail'))
    print('-' * 60)
    sector_counts = defaultdict(lambda: [0, 0])
    for c in all_data:
        if c['has_occ']:
            sector_counts[c['naics_group']][0] += 1
        else:
            sector_counts[c['naics_group']][1] += 1
    for sector in sorted(sector_counts.keys()):
        has, miss = sector_counts[sector]
        pct = has / (has + miss) * 100 if (has + miss) > 0 else 0
        print('%-35s %8d %8d %7.0f%%' % (sector, has, miss, pct))

    # ================================================================
    # Occ-chain divergence analysis
    # ================================================================
    print()
    print('=' * 70)
    print('OCC-CHAIN DIVERGENCE FROM D (companies with occ data)')
    print('=' * 70)
    print()
    print('How far does occ_chain differ from Expert D for each category?')
    print()

    div_by_cat = defaultdict(list)
    for c in all_data:
        if not c['has_occ']:
            continue
        for cat in OCC_RELIABLE_CATS:
            d_val = c['d_race'].get(cat, 0)
            o_val = c['occ_chain'].get(cat, 0)
            div_by_cat[cat].append(o_val - d_val)

    print('%-10s %10s %10s %10s %10s %10s' % (
        'Category', 'Mean Div', 'Median', 'Std Dev', 'Min', 'Max'))
    print('-' * 60)
    for cat in OCC_RELIABLE_CATS:
        divs = div_by_cat[cat]
        if not divs:
            continue
        divs_sorted = sorted(divs)
        mean_d = sum(divs) / len(divs)
        median_d = divs_sorted[len(divs) // 2]
        std_d = (sum((x - mean_d) ** 2 for x in divs) / len(divs)) ** 0.5
        print('%-10s %+10.2f %+10.2f %10.2f %+10.1f %+10.1f' % (
            cat, mean_d, median_d, std_d, min(divs), max(divs)))

    # ================================================================
    # Does the divergence predict error direction?
    # ================================================================
    print()
    print('=' * 70)
    print('DIVERGENCE vs ERROR DIRECTION (does occ-chain correct D?)')
    print('=' * 70)
    print()
    print('When occ_chain says "more Black than D", is D indeed under-predicting Black?')
    print()

    for cat in ['White', 'Black']:
        correct_direction = 0
        wrong_direction = 0
        no_divergence = 0

        for c in all_data:
            if not c['has_occ']:
                continue
            d_val = c['d_race'].get(cat, 0)
            o_val = c['occ_chain'].get(cat, 0)
            actual_val = c['actual_race'].get(cat, 0)

            divergence = o_val - d_val  # occ says more/less than D
            d_error = actual_val - d_val  # D's actual error (positive = D underestimates)

            if abs(divergence) < 1.0:
                no_divergence += 1
            elif divergence * d_error > 0:
                correct_direction += 1  # occ pushes in the right direction
            else:
                wrong_direction += 1

        total = correct_direction + wrong_direction
        if total > 0:
            pct_correct = correct_direction / total * 100
            print('  %s: occ-chain correction is right %.1f%% of the time (%d/%d, %d neutral)' % (
                cat, pct_correct, correct_direction, total, no_divergence))

    print()
    print('Total runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
