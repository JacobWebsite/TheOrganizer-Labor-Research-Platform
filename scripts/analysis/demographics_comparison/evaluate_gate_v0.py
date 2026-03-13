"""Evaluate Gate v0 vs M8 on the 200-company holdout set.

Loads gate_v0.pkl, runs it on selected_holdout_v3.json companies,
compares against M8 and M3b baselines.

Output: GATE_V0_EVALUATION.md

Usage:
    py scripts/analysis/demographics_comparison/evaluate_gate_v0.py
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
from metrics import compute_all_metrics, composite_score
from cached_loaders_v3 import CachedLoadersV3
from cached_loaders_v2 import cached_method_3b, cached_method_1b
from cached_loaders_v3 import cached_method_3c, cached_method_2c, cached_method_3d
from cached_loaders_v4 import cached_method_8
from cached_loaders import cached_method_3
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)

# Gate candidate methods (must match training)
GATE_METHOD_FNS = {
    'M3b Damp-IPF': cached_method_3b,
    'M3 IPF': cached_method_3,
    'M2c ZIP-Tract': cached_method_2c,
    'M3c Var-Damp-IPF': cached_method_3c,
    'M1b Learned-Wt': cached_method_1b,
}


def load_gate_model():
    """Load gate_v0.pkl."""
    model_path = os.path.join(SCRIPT_DIR, 'gate_v0.pkl')
    if not os.path.exists(model_path):
        print('ERROR: %s not found. Run train_v5_gate.py first.' % model_path)
        sys.exit(1)
    with open(model_path, 'rb') as f:
        return pickle.load(f)


def load_holdout():
    """Load holdout companies."""
    json_path = os.path.join(SCRIPT_DIR, 'selected_holdout_v3.json')
    if not os.path.exists(json_path):
        print('ERROR: %s not found.' % json_path)
        sys.exit(1)
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_gate_features(company, cl, cur):
    """Build feature vector for gate prediction."""
    try:
        import numpy as np
    except ImportError:
        print('ERROR: numpy required')
        sys.exit(1)

    naics = company.get('naics', '')
    naics4 = naics[:4]
    naics_group = company.get('classifications', {}).get('naics_group', '')
    if not naics_group:
        naics_group = classify_naics_group(naics)

    state_abbr = company.get('state', '')
    region = classify_region(state_abbr)
    urbanicity = company.get('classifications', {}).get('urbanicity', '')
    size_bucket = company.get('classifications', {}).get('size', '')
    zipcode = company.get('zipcode', '')
    county_fips = company.get('county_fips', '')
    state_fips = company.get('state_fips', '')

    if not county_fips:
        county_fips = zip_to_county(cur, zipcode)
    if not state_fips and county_fips:
        state_fips = county_fips[:2]

    county_minority_share = cl.get_lodes_pct_minority(county_fips) if county_fips else 0.0
    if county_minority_share is None:
        county_minority_share = 0.0

    acs_race = cl.get_acs_race(naics4, state_fips) if naics4 and state_fips else None
    lodes_race = cl.get_lodes_race(county_fips) if county_fips else None
    acs_lodes_disagreement = 0.0
    if acs_race and lodes_race:
        acs_lodes_disagreement = abs(acs_race.get('White', 0) - lodes_race.get('White', 0))

    has_tract_data = 0
    if zipcode:
        tract_fips = cl.get_zip_to_best_tract(zipcode)
        if tract_fips:
            tract_race = cl.get_lodes_tract_race(tract_fips)
            has_tract_data = 1 if tract_race is not None else 0

    is_finance_insurance = 1 if naics_group == 'Finance/Insurance (52)' else 0
    is_admin_staffing = 1 if naics_group == 'Admin/Staffing (56)' else 0
    is_healthcare = 1 if naics_group == 'Healthcare/Social (62)' else 0

    # Build combined feature array matching training format
    cat_features = [naics_group, region, urbanicity, size_bucket]
    num_features = [county_minority_share, acs_lodes_disagreement]
    bool_features = [has_tract_data, is_finance_insurance, is_admin_staffing, is_healthcare]

    X = np.array([cat_features + [str(x) for x in num_features] + [str(x) for x in bool_features]])
    return X, county_fips, state_fips


def main():
    try:
        import numpy as np
    except ImportError:
        print('ERROR: numpy required')
        sys.exit(1)

    t0 = time.time()
    print('EVALUATE GATE V0')
    print('=' * 60)

    # Load model and holdout
    gate_model = load_gate_model()
    pipeline = gate_model['pipeline']
    print('Gate v0 CV accuracy: %.3f' % gate_model['cv_accuracy'])

    companies = load_holdout()
    print('Holdout companies: %d' % len(companies))

    # Load EEO-1
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV3(cur)

    # Results accumulators
    gate_preds = []
    gate_actuals = []
    m8_preds = []
    m8_actuals = []
    m3b_preds = []
    m3b_actuals = []

    gate_routing = defaultdict(int)
    skipped = 0

    for i, company in enumerate(companies):
        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        zipcode = company.get('zipcode', '')

        # Get ground truth
        truth = None
        for row in eeo1_rows:
            if row.get('COMPANY') == company_code:
                truth = parse_eeo1_row(row)
                break
        if not truth:
            skipped += 1
            continue

        # Build features
        X, county_fips, state_fips = build_gate_features(company, cl, cur)
        if not county_fips:
            county_fips = zip_to_county(cur, zipcode)
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        # Gate prediction
        try:
            predicted_method = pipeline.predict(X)[0]
        except Exception as e:
            predicted_method = 'M3b Damp-IPF'

        gate_routing[predicted_method] += 1

        # Run predicted method
        method_fn = GATE_METHOD_FNS.get(predicted_method)
        if method_fn:
            try:
                if predicted_method == 'M2c ZIP-Tract':
                    gate_result = method_fn(cl, naics4, state_fips, county_fips, zipcode=zipcode)
                else:
                    gate_result = method_fn(cl, naics4, state_fips, county_fips)
            except Exception:
                gate_result = cached_method_3b(cl, naics4, state_fips, county_fips)
        else:
            gate_result = cached_method_3b(cl, naics4, state_fips, county_fips)

        # Run M8 baseline
        naics_group = company.get('classifications', {}).get('naics_group', '')
        urbanicity = company.get('classifications', {}).get('urbanicity', '')
        state_abbr = company.get('state', '')
        try:
            m8_result = cached_method_8(
                cl, naics4, state_fips, county_fips,
                naics_group=naics_group, urbanicity=urbanicity,
                state_abbr=state_abbr, zipcode=zipcode)
        except Exception:
            m8_result = {'race': None, 'hispanic': None, 'gender': None}

        # Run M3b baseline
        m3b_result = cached_method_3b(cl, naics4, state_fips, county_fips)

        # Collect race predictions
        actual_race = truth.get('race')
        if gate_result and gate_result.get('race') and actual_race:
            gate_preds.append(gate_result['race'])
            gate_actuals.append(actual_race)
        if m8_result and m8_result.get('race') and actual_race:
            m8_preds.append(m8_result['race'])
            m8_actuals.append(actual_race)
        if m3b_result and m3b_result.get('race') and actual_race:
            m3b_preds.append(m3b_result['race'])
            m3b_actuals.append(actual_race)

    elapsed = time.time() - t0
    print('Processed %d companies in %.1fs (%d skipped)' % (
        len(gate_preds), elapsed, skipped))

    # Compute composite scores
    gate_comp = composite_score(gate_preds, gate_actuals)
    m8_comp = composite_score(m8_preds, m8_actuals)
    m3b_comp = composite_score(m3b_preds, m3b_actuals)

    print('')
    print('RESULTS ON HOLDOUT:')
    print('=' * 60)
    print('%-20s | %9s | %8s | %7s | %7s' % (
        'Method', 'Composite', 'Race MAE', 'P>20pp', 'P>30pp'))
    print('-' * 60)
    for name, comp in [('Gate v0', gate_comp), ('M8 (V4)', m8_comp), ('M3b (baseline)', m3b_comp)]:
        if comp:
            print('%-20s | %9.3f | %8.3f | %6.2f%% | %6.2f%%' % (
                name, comp['composite'], comp['avg_mae'],
                comp['p_gt_20pp'] * 100, comp['p_gt_30pp'] * 100))
        else:
            print('%-20s | %9s' % (name, 'N/A'))

    print('')
    print('Gate v0 routing distribution:')
    for method in sorted(gate_routing.keys()):
        print('  %-22s  %d' % (method, gate_routing[method]))

    # Decision
    gate_wins = False
    if gate_comp and m8_comp:
        gate_wins = gate_comp['composite'] < m8_comp['composite']

    decision = 'REPLACE M8 with Gate v0' if gate_wins else 'RETAIN M8 (Gate v0 not better)'
    print('')
    print('DECISION: %s' % decision)

    # Write report
    report_path = os.path.join(SCRIPT_DIR, 'GATE_V0_EVALUATION.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('# Gate v0 Evaluation Report\n\n')
        f.write('## Summary\n\n')
        f.write('- Holdout: %d companies (selected_holdout_v3.json)\n' % len(gate_preds))
        f.write('- Gate v0 CV accuracy: %.3f\n' % gate_model['cv_accuracy'])
        f.write('\n## Results\n\n')
        f.write('| Method | Composite | Race MAE | P>20pp | P>30pp | Abs Bias |\n')
        f.write('|--------|-----------|----------|--------|--------|----------|\n')
        for name, comp in [('Gate v0', gate_comp), ('M8 (V4)', m8_comp), ('M3b', m3b_comp)]:
            if comp:
                f.write('| %s | %.3f | %.3f | %.2f%% | %.2f%% | %.3f |\n' % (
                    name, comp['composite'], comp['avg_mae'],
                    comp['p_gt_20pp'] * 100, comp['p_gt_30pp'] * 100,
                    comp['mean_abs_bias']))
        f.write('\n## Decision\n\n')
        f.write('**%s**\n' % decision)
        f.write('\n## Gate v0 Routing\n\n')
        for method in sorted(gate_routing.keys()):
            f.write('- %s: %d companies\n' % (method, gate_routing[method]))

    print('Report: %s' % report_path)
    conn.close()


if __name__ == '__main__':
    main()
