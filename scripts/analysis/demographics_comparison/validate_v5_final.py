"""V5 Final Validation: Gate v1 + Expert models on fresh holdout.

Runs all competing methods on selected_fresh_holdout_v5.json companies
and produces a pass/fail report.

Output: V5_FINAL_REPORT.md

Usage:
    py scripts/analysis/demographics_comparison/validate_v5_final.py
"""
import sys
import os
import json
import pickle
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county
from metrics import compute_all_metrics, composite_score, mae
from cached_loaders_v5 import (
    CachedLoadersV5, cached_method_3c_v5, cached_method_3e_v5,
    cached_method_8_v5, cached_expert_a, cached_expert_b,
)
from cached_loaders_v2 import cached_method_3b
from cached_loaders_v4 import cached_method_8
from methodologies_v5 import (
    smoothed_variable_dampened_ipf, NATIONAL_EEO1_PRIOR,
    _prior_smooth, RACE_CATS,
)
from methodologies_v3 import OPTIMAL_DAMPENING_BY_GROUP
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']

# Hard segments for BDS nudge
HARD_SEGMENTS = {
    'Healthcare/Social (62)', 'Admin/Staffing (56)',
    'Food/Bev Manufacturing (311,312)', 'Accommodation/Food Svc (72)',
}


def load_gate_v1():
    """Load gate_v1.pkl and calibration_v1.json."""
    model_path = os.path.join(SCRIPT_DIR, 'gate_v1.pkl')
    cal_path = os.path.join(SCRIPT_DIR, 'calibration_v1.json')

    if not os.path.exists(model_path):
        print('WARNING: gate_v1.pkl not found, will use Expert D (M3b) as fallback')
        return None, {}

    with open(model_path, 'rb') as f:
        gate = pickle.load(f)

    calibration = {}
    if os.path.exists(cal_path):
        with open(cal_path, 'r', encoding='utf-8') as f:
            calibration = json.load(f)

    return gate, calibration


def load_bds_benchmarks(cur):
    """Load BDS-HC benchmarks from DB."""
    try:
        cur.execute("""
            SELECT geo_type, geo_key, size_bucket, dimension,
                   est_pct, dominant_bucket, concentration
            FROM bds_hc_estimated_benchmarks
        """)
        rows = cur.fetchall()
        benchmarks = {}
        for row in rows:
            key = (row['geo_type'], row['geo_key'], row['size_bucket'], row['dimension'])
            benchmarks[key] = {
                'est_pct': float(row['est_pct']),
                'dominant_bucket': row['dominant_bucket'],
                'concentration': float(row['concentration']),
            }
        return benchmarks
    except Exception:
        return {}


def apply_calibration(pred_race, expert, calibration):
    """Apply OOF calibration bias correction to race prediction."""
    if not pred_race or expert not in calibration:
        return pred_race

    biases = calibration[expert]
    corrected = {}
    for cat in RACE_CATS:
        val = pred_race.get(cat, 0)
        bias = biases.get(cat, 0)
        corrected[cat] = max(0, val - bias)

    # Renormalize
    total = sum(corrected.values())
    if total > 0:
        corrected = {k: round(v * 100.0 / total, 2) for k, v in corrected.items()}
    return corrected


def apply_bds_nudge(pred_race, naics_group, headcount, benchmarks):
    """Apply BDS-HC benchmark nudge (conservative)."""
    if not pred_race or not benchmarks:
        return pred_race

    sector = naics_group[:2] if len(naics_group) >= 2 else ''
    # Extract 2-digit NAICS from group name
    import re
    match = re.search(r'\((\d{2})', naics_group)
    if match:
        sector = match.group(1)
    else:
        return pred_race

    from bds_hc_check import _size_bucket
    size_bucket = _size_bucket(headcount)

    key = ('sector', sector, size_bucket, 'race')
    bds = benchmarks.get(key)
    if not bds:
        return pred_race

    concentration = bds['concentration']
    est_pct = bds['est_pct']  # This is minority %

    # Conservative: only nudge if concentration is low (diverse bracket distribution)
    if concentration > 0.60:
        return pred_race  # Validation only, no nudge

    # Determine nudge weight
    is_hard = naics_group in HARD_SEGMENTS
    nudge_weight = 0.15 if is_hard else 0.10

    # BDS est_pct is minority %, our pred is race categories
    # Compute our predicted minority %
    pred_minority = 100.0 - pred_race.get('White', 0)

    # Nudge toward BDS estimate
    target_minority = (1 - nudge_weight) * pred_minority + nudge_weight * est_pct
    delta = target_minority - pred_minority

    # Apply delta proportionally to minority categories
    if abs(delta) < 0.5:
        return pred_race

    nudged = dict(pred_race)
    # Adjust White and redistribute to minority categories
    nudged['White'] = max(0, nudged.get('White', 0) - delta)
    minority_cats = [c for c in RACE_CATS if c != 'White']
    minority_total = sum(nudged.get(c, 0) for c in minority_cats)
    if minority_total > 0:
        for c in minority_cats:
            share = nudged.get(c, 0) / minority_total
            nudged[c] = nudged.get(c, 0) + delta * share

    # Renormalize
    total = sum(nudged.get(c, 0) for c in RACE_CATS)
    if total > 0:
        nudged = {c: round(nudged.get(c, 0) * 100.0 / total, 2) for c in RACE_CATS}
    return nudged


def predict_gate_v1(company, cl, cur, gate, calibration):
    """Run Gate v1 prediction for one company."""
    try:
        import numpy as np
    except ImportError:
        return None, {}

    naics = company.get('naics', '')
    naics4 = naics[:4]
    state_fips = company.get('state_fips', '')
    county_fips = company.get('county_fips', '')
    zipcode = company.get('zipcode', '')
    cls = company.get('classifications', {})
    naics_group = cls.get('naics_group', 'Other')
    headcount = company.get('total', 100)

    if gate is None:
        # Fallback to Expert D (M3b)
        result = cached_method_3b(cl, naics4, state_fips, county_fips)
        return result, {'expert_used': 'D', 'confidence_score': 0.0,
                       'data_source': 'acs_state', 'review_flag': True,
                       'review_reasons': ['no_gate_model']}

    # Build features for gate
    region = cls.get('region', 'Other')
    urbanicity = cls.get('urbanicity', 'Rural')
    size_bucket = cls.get('size', '100-999')
    # Use LODES-derived minority share instead of EEO-1 ground truth
    county_minority_share = cl.get_lodes_pct_minority(county_fips) if county_fips else None
    if county_minority_share is not None:
        minority_pct = county_minority_share * 100.0
        if minority_pct < 25:
            lodes_minority_share = 'Low (<25%)'
        elif minority_pct <= 50:
            lodes_minority_share = 'Medium (25-50%)'
        else:
            lodes_minority_share = 'High (>50%)'
    else:
        lodes_minority_share = 'Medium (25-50%)'
    alpha_used = str(OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50))

    cat_features = [naics_group, region, urbanicity, size_bucket, lodes_minority_share]
    X = np.array([cat_features + [alpha_used]])

    # Predict
    pipeline = gate['pipeline']
    try:
        probs = pipeline.predict_proba(X)[0]
        expert_names = list(pipeline.named_steps['classifier'].classes_)
        best_idx = int(np.argmax(probs))
        expert = expert_names[best_idx]
        confidence = float(probs[best_idx])
    except Exception:
        expert = 'D'
        confidence = 0.0
        expert_names = ['A', 'B', 'D']
        probs = np.array([0.0, 0.0, 1.0])

    # Run all experts
    expert_results = {}
    try:
        expert_results['A'] = cached_expert_a(cl, naics4, state_fips, county_fips)
    except Exception:
        pass
    try:
        expert_results['B'] = cached_expert_b(cl, naics4, state_fips, county_fips, zipcode=zipcode)
    except Exception:
        pass
    try:
        expert_results['D'] = cached_method_3b(cl, naics4, state_fips, county_fips)
    except Exception:
        pass

    # Soft routing: probability-weighted blend
    result = None
    if expert_results:
        blended_race = {}
        blended_hisp = {}
        blended_gender = {}
        total_weight = 0.0
        for i, exp_name in enumerate(expert_names):
            if exp_name in expert_results and expert_results[exp_name]:
                w = float(probs[i])
                er = expert_results[exp_name]
                if er.get('race'):
                    for cat in RACE_CATS:
                        blended_race[cat] = blended_race.get(cat, 0) + w * er['race'].get(cat, 0)
                if er.get('hispanic'):
                    for cat in HISP_CATS:
                        blended_hisp[cat] = blended_hisp.get(cat, 0) + w * er['hispanic'].get(cat, 0)
                if er.get('gender'):
                    for cat in GENDER_CATS:
                        blended_gender[cat] = blended_gender.get(cat, 0) + w * er['gender'].get(cat, 0)
                total_weight += w

        if total_weight > 0 and blended_race:
            result = {
                'race': {c: round(v / total_weight, 2) for c, v in blended_race.items()},
                'hispanic': {c: round(v / total_weight, 2) for c, v in blended_hisp.items()} if blended_hisp else None,
                'gender': {c: round(v / total_weight, 2) for c, v in blended_gender.items()} if blended_gender else None,
                '_data_source': 'soft_blend',
            }

    # Apply calibration to the blended result
    if result and result.get('race'):
        result['race'] = apply_calibration(result['race'], expert, calibration)

    # Compute disagreement between experts for review flag
    all_expert_preds = {}
    try:
        r = cached_expert_a(cl, naics4, state_fips, county_fips).get('race')
        if r:
            all_expert_preds['A'] = r
    except Exception:
        pass
    try:
        r = cached_expert_b(
            cl, naics4, state_fips, county_fips, zipcode=zipcode).get('race')
        if r:
            all_expert_preds['B'] = r
    except Exception:
        pass
    try:
        r = cached_method_3b(cl, naics4, state_fips, county_fips).get('race')
        if r:
            all_expert_preds['D'] = r
    except Exception:
        pass

    max_disagreement = 0.0
    experts_with_preds = list(all_expert_preds.keys())
    for i in range(len(experts_with_preds)):
        for j in range(i + 1, len(experts_with_preds)):
            e1, e2 = experts_with_preds[i], experts_with_preds[j]
            for cat in RACE_CATS:
                diff = abs(all_expert_preds[e1].get(cat, 0) - all_expert_preds[e2].get(cat, 0))
                max_disagreement = max(max_disagreement, diff)

    data_source = result.get('_data_source', 'acs_state') if result else 'acs_state'

    # Review flags
    review_reasons = []
    if confidence < 0.45:
        review_reasons.append('low_gate_confidence_%.2f' % confidence)
    if max_disagreement >= 10.0:
        review_reasons.append('expert_disagreement_%.1fpp' % max_disagreement)
    if data_source == 'acs_state':
        review_reasons.append('no_pums_metro_data')

    metadata = {
        'expert_used': expert,
        'confidence_score': round(confidence, 3),
        'data_source': data_source,
        'review_flag': len(review_reasons) > 0,
        'review_reasons': review_reasons,
    }

    return result, metadata


def main():
    t0 = time.time()
    print('V5 FINAL VALIDATION')
    print('=' * 100)

    # Load holdout
    holdout_path = os.path.join(SCRIPT_DIR, 'selected_fresh_holdout_v5.json')
    if not os.path.exists(holdout_path):
        print('ERROR: %s not found. Run build_fresh_holdout_v5.py first.' % holdout_path)
        sys.exit(1)
    with open(holdout_path, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    print('Fresh holdout: %d companies' % len(companies))

    # Load models
    gate, calibration = load_gate_v1()
    if gate:
        print('Gate v1 CV accuracy: %.3f' % gate['cv_accuracy'])

    eeo1_rows = load_eeo1_data()

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV5(cur)

    # Accumulators per method
    methods = {
        'M3b (baseline)': [],
        'M8 (V4)': [],
        'Expert A': [],
        'Expert B': [],
        'Expert D': [],
        'Gate v1': [],
    }
    method_actuals = {m: [] for m in methods}
    method_hisp_preds = {m: [] for m in methods}
    method_hisp_actuals = {m: [] for m in methods}
    method_gender_preds = {m: [] for m in methods}
    method_gender_actuals = {m: [] for m in methods}

    gate_metadata = []
    skipped = 0

    for i, company in enumerate(companies):
        if (i + 1) % 50 == 0:
            print('  Processing %d/%d...' % (i + 1, len(companies)))

        code = company['company_code']
        naics = company.get('naics', '')
        naics4 = naics[:4]
        zipcode = company.get('zipcode', '')
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')
        state_abbr = company.get('state', '')

        if not county_fips:
            county_fips = zip_to_county(cur, zipcode)
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        # Ground truth
        truth = None
        for row in eeo1_rows:
            if row.get('COMPANY') == code:
                truth = parse_eeo1_row(row)
                break
        if not truth:
            skipped += 1
            continue

        actual_race = truth.get('race')
        actual_hisp = truth.get('hispanic')
        actual_gender = truth.get('gender')
        if not actual_race:
            skipped += 1
            continue

        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', '')
        urbanicity = cls.get('urbanicity', '')

        # Run each method
        try:
            m3b = cached_method_3b(cl, naics4, state_fips, county_fips)
        except Exception:
            m3b = {'race': None, 'hispanic': None, 'gender': None}
        try:
            m8 = cached_method_8(
                cl, naics4, state_fips, county_fips,
                naics_group=naics_group, urbanicity=urbanicity,
                state_abbr=state_abbr, zipcode=zipcode)
        except Exception:
            m8 = {'race': None, 'hispanic': None, 'gender': None}
        try:
            exp_a = cached_expert_a(cl, naics4, state_fips, county_fips)
        except Exception:
            exp_a = {'race': None, 'hispanic': None, 'gender': None}
        try:
            exp_b = cached_expert_b(cl, naics4, state_fips, county_fips, zipcode=zipcode)
        except Exception:
            exp_b = {'race': None, 'hispanic': None, 'gender': None}

        # Gate v1
        gate_result, meta = predict_gate_v1(
            company, cl, cur, gate, calibration)
        gate_metadata.append(meta)

        # Expert D = M3b
        results_map = {
            'M3b (baseline)': m3b,
            'M8 (V4)': m8,
            'Expert A': exp_a,
            'Expert B': exp_b,
            'Expert D': m3b,
            'Gate v1': gate_result,
        }

        for method_name, result in results_map.items():
            if result and result.get('race'):
                methods[method_name].append(result['race'])
                method_actuals[method_name].append(actual_race)
            if result and result.get('hispanic') and actual_hisp:
                method_hisp_preds[method_name].append(result['hispanic'])
                method_hisp_actuals[method_name].append(actual_hisp)
            if result and result.get('gender') and actual_gender:
                method_gender_preds[method_name].append(result['gender'])
                method_gender_actuals[method_name].append(actual_gender)

    elapsed = time.time() - t0
    print('')
    print('Processed %d companies in %.1fs (%d skipped)' % (
        len(methods['Gate v1']), elapsed, skipped))

    # Compute scores
    print('')
    print('=' * 100)
    print('FINAL RESULTS')
    print('=' * 100)
    print('%-20s | %9s | %8s | %7s | %7s | %10s | %8s | %8s' % (
        'Method', 'Composite', 'Race MAE', 'P>20pp', 'P>30pp', 'Abs Bias',
        'Hisp MAE', 'Gend MAE'))
    print('-' * 100)

    results_table = {}
    for method_name in ['M3b (baseline)', 'M8 (V4)', 'Expert A', 'Expert B', 'Expert D', 'Gate v1']:
        comp = composite_score(methods[method_name], method_actuals[method_name])

        # Hispanic MAE
        hisp_mae = None
        if method_hisp_preds[method_name]:
            hisp_maes = []
            for p, a in zip(method_hisp_preds[method_name], method_hisp_actuals[method_name]):
                m = mae(p, a)
                if m is not None:
                    hisp_maes.append(m)
            if hisp_maes:
                hisp_mae = sum(hisp_maes) / len(hisp_maes)

        # Gender MAE
        gend_mae = None
        if method_gender_preds[method_name]:
            gend_maes = []
            for p, a in zip(method_gender_preds[method_name], method_gender_actuals[method_name]):
                m = mae(p, a)
                if m is not None:
                    gend_maes.append(m)
            if gend_maes:
                gend_mae = sum(gend_maes) / len(gend_maes)

        results_table[method_name] = {
            'composite': comp,
            'hisp_mae': hisp_mae,
            'gend_mae': gend_mae,
        }

        if comp:
            print('%-20s | %9.3f | %8.3f | %6.2f%% | %6.2f%% | %10.3f | %8s | %8s' % (
                method_name, comp['composite'], comp['avg_mae'],
                comp['p_gt_20pp'] * 100, comp['p_gt_30pp'] * 100, comp['mean_abs_bias'],
                '%.3f' % hisp_mae if hisp_mae else 'N/A',
                '%.3f' % gend_mae if gend_mae else 'N/A'))

    # Gate v1 metadata summary
    print('')
    print('Gate v1 Metadata:')
    expert_counts = defaultdict(int)
    review_count = 0
    for meta in gate_metadata:
        expert_counts[meta.get('expert_used', 'D')] += 1
        if meta.get('review_flag'):
            review_count += 1
    for expert in sorted(expert_counts.keys()):
        print('  Expert %s: %d companies' % (expert, expert_counts[expert]))
    print('  Review flagged: %d/%d' % (review_count, len(gate_metadata)))

    # Acceptance criteria
    print('')
    print('=' * 100)
    print('ACCEPTANCE CRITERIA')
    print('=' * 100)

    gate_comp = results_table.get('Gate v1', {}).get('composite')
    m3b_comp = results_table.get('M3b (baseline)', {}).get('composite')

    criteria = []

    # 1. Gate v1 race MAE < M3b
    if gate_comp and m3b_comp:
        pass1 = gate_comp['avg_mae'] < m3b_comp['avg_mae']
        criteria.append(('Race MAE < M3b', pass1,
                        '%.3f vs %.3f' % (gate_comp['avg_mae'], m3b_comp['avg_mae'])))
    else:
        criteria.append(('Race MAE < M3b', False, 'N/A'))

    # 2. P(>30pp) no worse than V4
    if gate_comp and m3b_comp:
        pass2 = gate_comp['p_gt_30pp'] <= m3b_comp['p_gt_30pp'] + 0.01
        criteria.append(('P>30pp no worse', pass2,
                        '%.3f vs %.3f' % (gate_comp['p_gt_30pp'], m3b_comp['p_gt_30pp'])))
    else:
        criteria.append(('P>30pp no worse', False, 'N/A'))

    # 3. Mean abs signed bias lower than V4
    if gate_comp and m3b_comp:
        pass3 = gate_comp['mean_abs_bias'] < m3b_comp['mean_abs_bias']
        criteria.append(('Lower bias', pass3,
                        '%.3f vs %.3f' % (gate_comp['mean_abs_bias'], m3b_comp['mean_abs_bias'])))
    else:
        criteria.append(('Lower bias', False, 'N/A'))

    # 4. Hispanic no worse
    gate_hisp = results_table.get('Gate v1', {}).get('hisp_mae')
    m3b_hisp = results_table.get('M3b (baseline)', {}).get('hisp_mae')
    if gate_hisp and m3b_hisp:
        pass4 = gate_hisp <= m3b_hisp + 0.5
        criteria.append(('Hispanic no worse', pass4,
                        '%.3f vs %.3f' % (gate_hisp, m3b_hisp)))
    else:
        criteria.append(('Hispanic no worse', False, 'N/A'))

    # 5. Gender no worse
    gate_gend = results_table.get('Gate v1', {}).get('gend_mae')
    m3b_gend = results_table.get('M3b (baseline)', {}).get('gend_mae')
    if gate_gend and m3b_gend:
        pass5 = gate_gend <= m3b_gend + 0.5
        criteria.append(('Gender no worse', pass5,
                        '%.3f vs %.3f' % (gate_gend, m3b_gend)))
    else:
        criteria.append(('Gender no worse', False, 'N/A'))

    all_pass = all(c[1] for c in criteria)

    for name, passed, detail in criteria:
        status = 'PASS' if passed else 'FAIL'
        print('  [%s] %s (%s)' % (status, name, detail))

    print('')
    print('OVERALL: %s' % ('ALL CRITERIA PASS' if all_pass else 'SOME CRITERIA FAIL'))

    # Write report
    report_path = os.path.join(SCRIPT_DIR, 'V5_FINAL_REPORT.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('# V5 Final Validation Report\n\n')
        f.write('Date: %s\n\n' % time.strftime('%Y-%m-%d'))
        f.write('## Summary\n\n')
        f.write('- Fresh holdout: %d companies\n' % len(methods['Gate v1']))
        f.write('- Skipped: %d\n' % skipped)
        if gate:
            f.write('- Gate v1 CV accuracy: %.3f\n' % gate['cv_accuracy'])
        f.write('\n## Results\n\n')
        f.write('| Method | Composite | Race MAE | P>20pp | P>30pp | Abs Bias | Hisp MAE | Gend MAE |\n')
        f.write('|--------|-----------|----------|--------|--------|----------|----------|----------|\n')
        for method_name in ['M3b (baseline)', 'M8 (V4)', 'Expert A', 'Expert B', 'Expert D', 'Gate v1']:
            r = results_table.get(method_name, {})
            comp = r.get('composite')
            hisp = r.get('hisp_mae')
            gend = r.get('gend_mae')
            if comp:
                f.write('| %s | %.3f | %.3f | %.2f%% | %.2f%% | %.3f | %s | %s |\n' % (
                    method_name, comp['composite'], comp['avg_mae'],
                    comp['p_gt_20pp'] * 100, comp['p_gt_30pp'] * 100,
                    comp['mean_abs_bias'],
                    '%.3f' % hisp if hisp else 'N/A',
                    '%.3f' % gend if gend else 'N/A'))
        f.write('\n## Gate v1 Routing\n\n')
        for expert in sorted(expert_counts.keys()):
            f.write('- Expert %s: %d companies\n' % (expert, expert_counts[expert]))
        f.write('- Review flagged: %d/%d\n' % (review_count, len(gate_metadata)))
        f.write('\n## Acceptance Criteria\n\n')
        for name, passed, detail in criteria:
            f.write('- [%s] %s (%s)\n' % ('PASS' if passed else 'FAIL', name, detail))
        f.write('\n**Overall: %s**\n' % ('ALL PASS' if all_pass else 'SOME FAIL'))

    print('Report: %s' % report_path)
    conn.close()


if __name__ == '__main__':
    main()
