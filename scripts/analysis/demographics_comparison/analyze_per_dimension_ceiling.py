"""Analyze per-dimension expert selection ceiling.

For each company in the holdout, runs all experts and determines:
1. Current approach: gate picks 1 expert for everything
2. Per-dimension oracle: best expert for race, best for Hispanic, best for gender
3. Per-category oracle: best expert for White, best for Black, best for Asian, etc.
4. Per-segment patterns: which expert is consistently best for each dimension
   in each industry x region x urbanity segment

This tells us the theoretical ceiling of a dimension-specific ensemble.

Usage:
    py analyze_per_dimension_ceiling.py --holdout selected_permanent_holdout_1000.json
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

EXPERTS = {
    'A': lambda cl, n4, sf, cf, **kw: cached_expert_a(cl, n4, sf, cf),
    'B': lambda cl, n4, sf, cf, **kw: cached_expert_b(cl, n4, sf, cf),
    'D': lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    'E': lambda cl, n4, sf, cf, **kw: cached_expert_e(cl, n4, sf, cf, **kw),
    'F': lambda cl, n4, sf, cf, **kw: cached_expert_f(cl, n4, sf, cf, **kw),
    'G': lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    'V6': lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}


def mae_for_dim(pred, actual, cats):
    """MAE for a single dimension."""
    if not pred or not actual:
        return None
    errors = []
    for cat in cats:
        if cat in pred and cat in actual:
            errors.append(abs(pred[cat] - actual[cat]))
    return sum(errors) / len(errors) if errors else None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--holdout', default='selected_permanent_holdout_1000.json')
    args = parser.parse_args()

    t0 = time.time()
    print('PER-DIMENSION EXPERT CEILING ANALYSIS')
    print('=' * 70)

    # Load holdout
    holdout_path = os.path.join(SCRIPT_DIR, args.holdout)
    with open(holdout_path) as f:
        holdout_data = json.load(f)
    companies = holdout_data if isinstance(holdout_data, list) else holdout_data.get('companies', [])
    print('Holdout: %s (%d companies)' % (args.holdout, len(companies)))

    # Load EEO-1
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

    # Track per-company, per-expert results
    # For each company: {expert: {race: {cat: pred}, hispanic: {...}, gender: {...}}}
    all_results = []

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

        # Urbanity from LODES
        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race:
            county_minority_pct = 100.0 - lodes_race.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        # Run ALL experts
        expert_preds = {}
        for exp_name, exp_fn in EXPERTS.items():
            try:
                result = exp_fn(cl, naics4, state_fips, county_fips,
                                cbsa_code=cbsa_code, zipcode=zipcode,
                                naics_group=naics_group)
            except Exception:
                result = None
            if result:
                expert_preds[exp_name] = result

        if not expert_preds:
            continue

        all_results.append({
            'company_code': code,
            'naics_group': naics_group,
            'region': region,
            'county_tier': county_tier,
            'state': state_abbr,
            'actual_race': actual_race,
            'actual_hisp': actual_hisp,
            'actual_gender': actual_gender,
            'expert_preds': expert_preds,
        })

    print('\nProcessed %d companies in %.0fs' % (len(all_results), time.time() - t0))
    print()

    # ================================================================
    # ANALYSIS 1: Current vs Oracle approaches
    # ================================================================
    print('=' * 70)
    print('ANALYSIS 1: Approach Comparison (no calibration)')
    print('=' * 70)

    # For each company, compute errors under different selection strategies
    current_race_errors = []  # gate picks 1 expert (simulate: best-race-MAE expert)
    oracle_perdim_race = []   # best expert for race, separate best for hisp, gender
    oracle_percat_race = []   # best expert for EACH race category independently
    oracle_perdim_hisp = []
    oracle_percat_hisp = []
    oracle_perdim_gender = []
    oracle_percat_gender = []

    # Also track: for each expert, what's their MAE when they ARE best?
    expert_race_maes = {e: [] for e in EXPERTS}
    expert_hisp_maes = {e: [] for e in EXPERTS}
    expert_gender_maes = {e: [] for e in EXPERTS}

    # Per-segment: which expert wins each dimension most often?
    segment_dim_wins = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # segment_dim_wins[segment_key][dimension][expert] = count

    # Per-category: which expert wins for each race category?
    cat_expert_errors = defaultdict(lambda: defaultdict(list))
    # cat_expert_errors[category][expert] = [abs_errors]

    for rec in all_results:
        actual_race = rec['actual_race']
        actual_hisp = rec['actual_hisp']
        actual_gender = rec['actual_gender']
        preds = rec['expert_preds']

        segment_key = '%s|%s|%s' % (rec['naics_group'], rec['region'], rec['county_tier'])

        # --- Race dimension ---
        race_maes_by_expert = {}
        for exp, result in preds.items():
            if result.get('race'):
                m = mae_for_dim(result['race'], actual_race, RACE_CATS)
                if m is not None:
                    race_maes_by_expert[exp] = m
                    expert_race_maes[exp].append(m)

        if race_maes_by_expert:
            # Current: best overall race MAE expert
            best_race_exp = min(race_maes_by_expert, key=race_maes_by_expert.get)
            current_race_errors.append(race_maes_by_expert[best_race_exp])
            oracle_perdim_race.append(race_maes_by_expert[best_race_exp])
            segment_dim_wins[segment_key]['race'][best_race_exp] += 1

            # Per-category oracle: for each race cat, pick best expert independently
            cat_errors = []
            for cat in RACE_CATS:
                best_cat_err = None
                for exp, result in preds.items():
                    if result.get('race') and cat in result['race'] and cat in actual_race:
                        err = abs(result['race'][cat] - actual_race[cat])
                        cat_expert_errors[cat][exp].append(err)
                        if best_cat_err is None or err < best_cat_err:
                            best_cat_err = err
                if best_cat_err is not None:
                    cat_errors.append(best_cat_err)
            if cat_errors:
                oracle_percat_race.append(sum(cat_errors) / len(cat_errors))

        # --- Hispanic dimension ---
        if actual_hisp:
            hisp_maes = {}
            for exp, result in preds.items():
                if result.get('hispanic'):
                    m = mae_for_dim(result['hispanic'], actual_hisp, HISP_CATS)
                    if m is not None:
                        hisp_maes[exp] = m
                        expert_hisp_maes[exp].append(m)
            if hisp_maes:
                best_hisp_exp = min(hisp_maes, key=hisp_maes.get)
                oracle_perdim_hisp.append(hisp_maes[best_hisp_exp])
                segment_dim_wins[segment_key]['hispanic'][best_hisp_exp] += 1

        # --- Gender dimension ---
        if actual_gender:
            gender_maes = {}
            for exp, result in preds.items():
                if result.get('gender'):
                    m = mae_for_dim(result['gender'], actual_gender, GENDER_CATS)
                    if m is not None:
                        gender_maes[exp] = m
                        expert_gender_maes[exp].append(m)
            if gender_maes:
                best_gender_exp = min(gender_maes, key=gender_maes.get)
                oracle_perdim_gender.append(gender_maes[best_gender_exp])
                segment_dim_wins[segment_key]['gender'][best_gender_exp] += 1

    # Print results
    print()
    print('Race MAE by approach (pre-calibration):')
    print('  Current (1 best expert):      %.3f pp (N=%d)' % (
        sum(current_race_errors) / len(current_race_errors), len(current_race_errors)))
    print('  Oracle per-category (best expert per race cat): %.3f pp (N=%d)' % (
        sum(oracle_percat_race) / len(oracle_percat_race), len(oracle_percat_race)))
    improvement = (1 - sum(oracle_percat_race) / sum(current_race_errors)) * 100
    print('  --> Per-category oracle improves race MAE by %.1f%%' % improvement)

    print()
    if oracle_perdim_hisp:
        print('Hispanic MAE (best expert for Hispanic): %.3f pp (N=%d)' % (
            sum(oracle_perdim_hisp) / len(oracle_perdim_hisp), len(oracle_perdim_hisp)))
    if oracle_perdim_gender:
        print('Gender MAE (best expert for gender):     %.3f pp (N=%d)' % (
            sum(oracle_perdim_gender) / len(oracle_perdim_gender), len(oracle_perdim_gender)))

    # ================================================================
    # ANALYSIS 2: Per-expert average MAE by dimension
    # ================================================================
    print()
    print('=' * 70)
    print('ANALYSIS 2: Expert Performance by Dimension (pre-calibration)')
    print('=' * 70)
    print()
    print('%-8s %10s %10s %10s %10s %10s %10s' % (
        'Expert', 'Race MAE', 'Race N', 'Hisp MAE', 'Hisp N', 'Gender MAE', 'Gender N'))
    print('-' * 68)
    for exp in sorted(EXPERTS.keys()):
        r = expert_race_maes[exp]
        h = expert_hisp_maes[exp]
        g = expert_gender_maes[exp]
        r_mae = sum(r) / len(r) if r else 0
        h_mae = sum(h) / len(h) if h else 0
        g_mae = sum(g) / len(g) if g else 0
        print('%-8s %10.3f %10d %10.3f %10d %10.3f %10d' % (
            exp, r_mae, len(r), h_mae, len(h), g_mae, len(g)))

    # ================================================================
    # ANALYSIS 3: Per-category best expert
    # ================================================================
    print()
    print('=' * 70)
    print('ANALYSIS 3: Best Expert per Race Category (pre-calibration)')
    print('=' * 70)
    print()
    for cat in RACE_CATS:
        print('%s:' % cat)
        expert_avg = {}
        for exp in sorted(EXPERTS.keys()):
            errs = cat_expert_errors[cat][exp]
            if errs:
                avg = sum(errs) / len(errs)
                expert_avg[exp] = avg
                print('  %-6s: avg abs error = %.3f pp (N=%d)' % (exp, avg, len(errs)))
        if expert_avg:
            best = min(expert_avg, key=expert_avg.get)
            print('  --> Best for %s: Expert %s (%.3f pp)' % (cat, best, expert_avg[best]))
        print()

    # ================================================================
    # ANALYSIS 4: Per-segment dimension winners
    # ================================================================
    print()
    print('=' * 70)
    print('ANALYSIS 4: Best Expert by Segment x Dimension')
    print('=' * 70)
    print()
    print('Top segments (>= 10 companies):')
    print()

    for segment_key in sorted(segment_dim_wins.keys()):
        total = sum(segment_dim_wins[segment_key].get('race', {}).values())
        if total < 10:
            continue

        print('--- %s (N=%d) ---' % (segment_key, total))
        for dim in ['race', 'hispanic', 'gender']:
            wins = segment_dim_wins[segment_key].get(dim, {})
            if wins:
                sorted_wins = sorted(wins.items(), key=lambda x: -x[1])
                top3 = ', '.join('%s:%d' % (e, c) for e, c in sorted_wins[:3])
                winner = sorted_wins[0]
                pct = winner[1] / sum(wins.values()) * 100
                print('  %-10s winner: %s (%.0f%%)  [%s]' % (dim, winner[0], pct, top3))
        print()

    # ================================================================
    # ANALYSIS 5: What a 2-model system could look like
    # ================================================================
    print()
    print('=' * 70)
    print('ANALYSIS 5: Simulated 2-Model Blend')
    print('=' * 70)
    print()
    print('Testing: for each company, average the top-2 experts per dimension')
    print()

    blend2_race_errors = []
    blend3_race_errors = []
    blend_all_race_errors = []

    for rec in all_results:
        actual_race = rec['actual_race']
        preds = rec['expert_preds']

        # Collect all expert race predictions
        expert_race_preds = {}
        for exp, result in preds.items():
            if result.get('race'):
                expert_race_preds[exp] = result['race']

        if len(expert_race_preds) < 2:
            continue

        # Rank experts by race MAE for THIS company
        expert_maes = {}
        for exp, pred_race in expert_race_preds.items():
            m = mae_for_dim(pred_race, actual_race, RACE_CATS)
            if m is not None:
                expert_maes[exp] = m

        if len(expert_maes) < 2:
            continue

        sorted_experts = sorted(expert_maes.keys(), key=lambda e: expert_maes[e])

        # Blend top 2
        top2_preds = [expert_race_preds[sorted_experts[i]] for i in range(min(2, len(sorted_experts)))]
        blended2 = {}
        for cat in RACE_CATS:
            vals = [p.get(cat, 0) for p in top2_preds]
            blended2[cat] = sum(vals) / len(vals)
        m2 = mae_for_dim(blended2, actual_race, RACE_CATS)
        if m2 is not None:
            blend2_race_errors.append(m2)

        # Blend top 3
        top3_preds = [expert_race_preds[sorted_experts[i]] for i in range(min(3, len(sorted_experts)))]
        blended3 = {}
        for cat in RACE_CATS:
            vals = [p.get(cat, 0) for p in top3_preds]
            blended3[cat] = sum(vals) / len(vals)
        m3 = mae_for_dim(blended3, actual_race, RACE_CATS)
        if m3 is not None:
            blend3_race_errors.append(m3)

        # Blend all experts (simple average)
        all_preds = list(expert_race_preds.values())
        blended_all = {}
        for cat in RACE_CATS:
            vals = [p.get(cat, 0) for p in all_preds]
            blended_all[cat] = sum(vals) / len(vals)
        ma = mae_for_dim(blended_all, actual_race, RACE_CATS)
        if ma is not None:
            blend_all_race_errors.append(ma)

    print('Race MAE comparison (pre-calibration, oracle ranking):')
    print('  Single best expert:    %.3f pp' % (sum(current_race_errors) / len(current_race_errors)))
    print('  Average top 2:         %.3f pp' % (sum(blend2_race_errors) / len(blend2_race_errors)))
    print('  Average top 3:         %.3f pp' % (sum(blend3_race_errors) / len(blend3_race_errors)))
    print('  Average ALL experts:   %.3f pp' % (sum(blend_all_race_errors) / len(blend_all_race_errors)))
    print('  Per-category oracle:   %.3f pp' % (sum(oracle_percat_race) / len(oracle_percat_race)))
    print()
    print('NOTE: "oracle" means we know the ground truth and pick the best.')
    print('A real system would need to predict which expert is best without')
    print('knowing the answer. But this shows the theoretical ceiling.')

    # ================================================================
    # ANALYSIS 6: How often do different experts win different dimensions
    # for the SAME company?
    # ================================================================
    print()
    print('=' * 70)
    print('ANALYSIS 6: Dimension Disagreement Rate')
    print('=' * 70)
    print()
    print('How often is the best expert for race DIFFERENT from best for')
    print('Hispanic or gender for the same company?')
    print()

    same_race_hisp = 0
    diff_race_hisp = 0
    same_race_gender = 0
    diff_race_gender = 0

    for rec in all_results:
        actual_race = rec['actual_race']
        actual_hisp = rec['actual_hisp']
        actual_gender = rec['actual_gender']
        preds = rec['expert_preds']

        # Best race expert
        race_maes = {}
        for exp, result in preds.items():
            if result.get('race'):
                m = mae_for_dim(result['race'], actual_race, RACE_CATS)
                if m is not None:
                    race_maes[exp] = m
        if not race_maes:
            continue
        best_race = min(race_maes, key=race_maes.get)

        # Best Hispanic expert
        if actual_hisp:
            hisp_maes = {}
            for exp, result in preds.items():
                if result.get('hispanic'):
                    m = mae_for_dim(result['hispanic'], actual_hisp, HISP_CATS)
                    if m is not None:
                        hisp_maes[exp] = m
            if hisp_maes:
                best_hisp = min(hisp_maes, key=hisp_maes.get)
                if best_race == best_hisp:
                    same_race_hisp += 1
                else:
                    diff_race_hisp += 1

        # Best gender expert
        if actual_gender:
            gender_maes = {}
            for exp, result in preds.items():
                if result.get('gender'):
                    m = mae_for_dim(result['gender'], actual_gender, GENDER_CATS)
                    if m is not None:
                        gender_maes[exp] = m
            if gender_maes:
                best_gender = min(gender_maes, key=gender_maes.get)
                if best_race == best_gender:
                    same_race_gender += 1
                else:
                    diff_race_gender += 1

    total_rh = same_race_hisp + diff_race_hisp
    total_rg = same_race_gender + diff_race_gender
    if total_rh:
        print('Race vs Hispanic: same expert %.1f%%, different %.1f%% (N=%d)' % (
            same_race_hisp / total_rh * 100, diff_race_hisp / total_rh * 100, total_rh))
    if total_rg:
        print('Race vs Gender:   same expert %.1f%%, different %.1f%% (N=%d)' % (
            same_race_gender / total_rg * 100, diff_race_gender / total_rg * 100, total_rg))

    if total_rh and total_rg:
        print()
        if diff_race_hisp / total_rh > 0.5 or diff_race_gender / total_rg > 0.5:
            print('==> HIGH disagreement: a per-dimension approach could help significantly')
        elif diff_race_hisp / total_rh > 0.3 or diff_race_gender / total_rg > 0.3:
            print('==> MODERATE disagreement: per-dimension approach has potential')
        else:
            print('==> LOW disagreement: same expert tends to be best across dimensions')

    print()
    print('Total runtime: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
