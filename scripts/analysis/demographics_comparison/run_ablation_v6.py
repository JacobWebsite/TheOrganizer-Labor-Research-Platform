"""V6 Ablation Study Runner.

Runs experiments A through H to measure the marginal contribution of each
new V6 data source and method, comparing against V5 baselines.

Experiments:
    A: Industry-LODES only (M9a vs M3c baseline)
    B: QCEW weighting only (M9b vs M3c baseline)
    C: A+B combined (M9c vs M3c baseline)
    D: Multi-tract only (M2c-Multi vs M2c-V5 baseline)
    E: Metro ACS only (M2c-Metro vs M2c-V5 baseline)
    F: All race sources combined (M9c vs M3c-V5)
    G: Gender occupation model (G1 vs V5 gender)
    H: Hispanic geography model (H1 vs V5 hispanic)

Output: V6_ABLATION_REPORT.md

Usage:
    py scripts/analysis/demographics_comparison/run_ablation_v6.py
    py scripts/analysis/demographics_comparison/run_ablation_v6.py --holdout permanent
    py scripts/analysis/demographics_comparison/run_ablation_v6.py --holdout training
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from metrics import composite_score, mae
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_method_9a, cached_method_9b, cached_method_9c,
    cached_method_3c_ind, cached_method_1b_qcew,
    cached_method_2c_multi, cached_method_2c_metro,
    cached_method_g1, cached_method_h1,
    cached_method_v6_full,
)
from cached_loaders_v5 import (
    cached_method_3c_v5, cached_method_2c_v5,
    cached_method_8_v5, cached_expert_a, cached_expert_b,
)
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']


def load_companies(holdout_type='training'):
    """Load company set for evaluation.

    holdout_type:
      'training' - 997 V5 training companies (all_companies_v4.json)
      'permanent' - 1000 permanent holdout (selected_permanent_holdout_1000.json)
    """
    if holdout_type == 'permanent':
        path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('companies', data)
    else:
        path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)


def resolve_company_geo(company, cur):
    """Ensure company has county_fips and state_fips."""
    county_fips = company.get('county_fips', '')
    state_fips = company.get('state_fips', '')
    zipcode = company.get('zipcode', '')

    if not county_fips and zipcode:
        county_fips = zip_to_county(cur, zipcode)
        company['county_fips'] = county_fips
    if not state_fips and county_fips:
        state_fips = county_fips[:2]
        company['state_fips'] = state_fips

    return county_fips, state_fips


def get_cbsa_for_county(cur, county_fips):
    """Look up CBSA code for a county."""
    if not county_fips:
        return ''
    cur.execute(
        "SELECT cbsa_code FROM cbsa_counties WHERE fips_full = %s LIMIT 1",
        [county_fips])
    row = cur.fetchone()
    return row['cbsa_code'] if row else ''


def run_method(method_fn, cl, company, **extra_kwargs):
    """Run a method safely, returning result or empty dict on error."""
    naics = company.get('naics', '')
    naics4 = naics[:4]
    state_fips = company.get('state_fips', '')
    county_fips = company.get('county_fips', '')
    try:
        return method_fn(cl, naics4, state_fips, county_fips, **extra_kwargs)
    except Exception:
        return {'race': None, 'hispanic': None, 'gender': None}


def compute_dimension_mae(preds, actuals, cats):
    """Compute average MAE across companies for one dimension."""
    maes = []
    for pred, actual in zip(preds, actuals):
        if pred is None or actual is None:
            continue
        keys = [k for k in cats if k in pred and k in actual]
        if keys:
            maes.append(sum(abs(pred[k] - actual[k]) for k in keys) / len(keys))
    return sum(maes) / len(maes) if maes else None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='V6 Ablation Study')
    parser.add_argument('--holdout', default='training',
                        choices=['training', 'permanent'],
                        help='Which company set to evaluate on')
    args = parser.parse_args()

    t0 = time.time()
    print('V6 ABLATION STUDY')
    print('=' * 100)
    print('Holdout type: %s' % args.holdout)

    companies = load_companies(args.holdout)
    print('Loaded %d companies' % len(companies))

    eeo1_rows = load_eeo1_data()
    print('Loaded %d EEO-1 rows' % len(eeo1_rows))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Define all methods to run
    # Key = method name, Value = (function, needs_extra_kwargs)
    all_methods = {
        # V5 baselines
        'M3c-V5 (baseline)': (cached_method_3c_v5, False),
        'M2c-V5 (3-layer)': (cached_method_2c_v5, True),
        'M8-V5 (router)': (cached_method_8_v5, True),
        'Expert-A': (cached_expert_a, False),
        'Expert-B': (cached_expert_b, True),
        # V6 new methods
        'M9a Ind-LODES': (cached_method_9a, False),
        'M9b QCEW-Adapt': (cached_method_9b, False),
        'M9c Combined': (cached_method_9c, False),
        'M3c-IND': (cached_method_3c_ind, False),
        'M1b-QCEW': (cached_method_1b_qcew, False),
        'M2c-Multi': (cached_method_2c_multi, True),
        'M2c-Metro': (cached_method_2c_metro, True),
        'G1 Occ-Gender': (cached_method_g1, True),
        'H1 Geo-Hisp': (cached_method_h1, True),
        'V6-Full': (cached_method_v6_full, True),
    }

    # Accumulators
    race_preds = {m: [] for m in all_methods}
    race_actuals = {m: [] for m in all_methods}
    hisp_preds = {m: [] for m in all_methods}
    hisp_actuals = {m: [] for m in all_methods}
    gender_preds = {m: [] for m in all_methods}
    gender_actuals = {m: [] for m in all_methods}

    skipped = 0
    processed = 0

    for i, company in enumerate(companies):
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print('  %d/%d (%.1fs, cache: %d hits, %d misses)' % (
                i + 1, len(companies), elapsed, cl.hits, cl.misses))

        code = company.get('company_code', '')
        county_fips, state_fips = resolve_company_geo(company, cur)
        if not county_fips:
            skipped += 1
            continue

        # Ground truth
        truth = None
        for row in eeo1_rows:
            if row.get('COMPANY') == code:
                truth = parse_eeo1_row(row)
                break
        if not truth or not truth.get('race'):
            skipped += 1
            continue

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic')
        actual_gender = truth.get('gender')

        # Build extra kwargs
        zipcode = company.get('zipcode', '')
        cbsa_code = get_cbsa_for_county(cur, county_fips)
        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', '')
        if not naics_group:
            naics_group = classify_naics_group(company.get('naics', '')[:4])
        state_abbr = company.get('state', '')
        urbanicity = cls.get('urbanicity', '')

        extra = {
            'zipcode': zipcode,
            'cbsa_code': cbsa_code,
            'naics_group': naics_group,
            'state_abbr': state_abbr,
            'urbanicity': urbanicity,
        }

        processed += 1

        for method_name, (method_fn, needs_extra) in all_methods.items():
            kwargs = extra if needs_extra else {}
            result = run_method(method_fn, cl, company, **kwargs)

            if result and result.get('race'):
                race_preds[method_name].append(result['race'])
                race_actuals[method_name].append(actual_race)
            if result and result.get('hispanic') and actual_hisp:
                hisp_preds[method_name].append(result['hispanic'])
                hisp_actuals[method_name].append(actual_hisp)
            if result and result.get('gender') and actual_gender:
                gender_preds[method_name].append(result['gender'])
                gender_actuals[method_name].append(actual_gender)

    elapsed = time.time() - t0
    print('')
    print('Processed %d companies in %.1fs (%d skipped)' % (processed, elapsed, skipped))
    print('Cache: %d hits, %d misses (%.1f%% hit rate)' % (
        cl.hits, cl.misses,
        100.0 * cl.hits / (cl.hits + cl.misses) if (cl.hits + cl.misses) > 0 else 0))

    # Compute results
    print('')
    print('=' * 100)
    print('ABLATION RESULTS')
    print('=' * 100)

    header = '%-22s | %8s | %7s | %7s | %7s | %10s | %8s | %8s | %3s' % (
        'Method', 'Race MAE', 'P>20pp', 'P>30pp', 'AbsBias',
        'Composite', 'Hisp MAE', 'GendMAE', 'N')
    print(header)
    print('-' * len(header))

    results = {}
    for method_name in all_methods:
        cs = composite_score(race_preds[method_name], race_actuals[method_name], RACE_CATS)
        h_mae = compute_dimension_mae(hisp_preds[method_name], hisp_actuals[method_name], HISP_CATS)
        g_mae = compute_dimension_mae(gender_preds[method_name], gender_actuals[method_name], GENDER_CATS)

        if cs:
            results[method_name] = {
                'race_mae': cs['avg_mae'],
                'p_gt_20pp': cs['p_gt_20pp'],
                'p_gt_30pp': cs['p_gt_30pp'],
                'abs_bias': cs['mean_abs_bias'],
                'composite': cs['composite'],
                'hisp_mae': h_mae,
                'gender_mae': g_mae,
                'n': cs['n_companies'],
            }
            print('%-22s | %8.3f | %6.1f%% | %6.1f%% | %7.3f | %10.3f | %8s | %8s | %3d' % (
                method_name,
                cs['avg_mae'],
                cs['p_gt_20pp'] * 100,
                cs['p_gt_30pp'] * 100,
                cs['mean_abs_bias'],
                cs['composite'],
                '%.3f' % h_mae if h_mae else 'N/A',
                '%.3f' % g_mae if g_mae else 'N/A',
                cs['n_companies'],
            ))
        else:
            print('%-22s | %8s | %7s | %7s | %7s | %10s | %8s | %8s | %3s' % (
                method_name, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', '0'))

    # Generate ablation report
    report_path = os.path.join(SCRIPT_DIR, 'V6_ABLATION_REPORT.md')
    _write_report(report_path, results, args.holdout, processed, skipped, elapsed)
    print('')
    print('Report written to: %s' % report_path)

    conn.close()


def _write_report(path, results, holdout_type, n_processed, n_skipped, elapsed_s):
    """Write V6_ABLATION_REPORT.md."""
    baseline = results.get('M3c-V5 (baseline)', {})
    b_race = baseline.get('race_mae', 0)
    b_hisp = baseline.get('hisp_mae', 0)
    b_gender = baseline.get('gender_mae', 0)

    lines = [
        '# V6 Ablation Study Report',
        '',
        '**Holdout:** %s' % holdout_type,
        '**Companies:** %d processed, %d skipped' % (n_processed, n_skipped),
        '**Runtime:** %.1fs' % elapsed_s,
        '',
        '---',
        '',
        '## Full Results Table',
        '',
        '| Method | Race MAE | P>20pp | P>30pp | Abs Bias | Composite | Hisp MAE | Gender MAE | N |',
        '|--------|---------|--------|--------|----------|-----------|----------|------------|---|',
    ]

    for method_name, r in sorted(results.items(), key=lambda x: x[1].get('composite', 999)):
        h_str = '%.3f' % r['hisp_mae'] if r['hisp_mae'] else 'N/A'
        g_str = '%.3f' % r['gender_mae'] if r['gender_mae'] else 'N/A'
        lines.append(
            '| %s | %.3f | %.1f%% | %.1f%% | %.3f | %.3f | %s | %s | %d |' % (
                method_name,
                r['race_mae'], r['p_gt_20pp'] * 100, r['p_gt_30pp'] * 100,
                r['abs_bias'], r['composite'],
                h_str, g_str, r['n']))

    lines.extend(['', '---', '', '## Ablation Analysis', ''])

    # Experiment A: Industry-LODES
    m9a = results.get('M9a Ind-LODES', {})
    if m9a and b_race:
        delta = m9a.get('race_mae', 0) - b_race
        lines.append('### Experiment A: Industry-LODES (M9a vs M3c-V5)')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (b_race, m9a.get('race_mae', 0), delta))
        lines.append('')

    # Experiment B: QCEW
    m9b = results.get('M9b QCEW-Adapt', {})
    if m9b and b_race:
        delta = m9b.get('race_mae', 0) - b_race
        lines.append('### Experiment B: QCEW Adaptive (M9b vs M3c-V5)')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (b_race, m9b.get('race_mae', 0), delta))
        lines.append('')

    # Experiment C: Combined
    m9c = results.get('M9c Combined', {})
    if m9c and b_race:
        delta = m9c.get('race_mae', 0) - b_race
        lines.append('### Experiment C: Combined (M9c vs M3c-V5)')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (b_race, m9c.get('race_mae', 0), delta))
        lines.append('')

    # Experiment D: Multi-tract
    m2c_base = results.get('M2c-V5 (3-layer)', {})
    m2c_multi = results.get('M2c-Multi', {})
    if m2c_multi and m2c_base:
        delta = m2c_multi.get('race_mae', 0) - m2c_base.get('race_mae', 0)
        lines.append('### Experiment D: Multi-Tract (M2c-Multi vs M2c-V5)')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (
            m2c_base.get('race_mae', 0), m2c_multi.get('race_mae', 0), delta))
        lines.append('')

    # Experiment E: Metro ACS
    m2c_metro = results.get('M2c-Metro', {})
    if m2c_metro and m2c_base:
        delta = m2c_metro.get('race_mae', 0) - m2c_base.get('race_mae', 0)
        lines.append('### Experiment E: Metro ACS (M2c-Metro vs M2c-V5)')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (
            m2c_base.get('race_mae', 0), m2c_metro.get('race_mae', 0), delta))
        lines.append('')

    # Experiment F: All combined
    v6_full = results.get('V6-Full', {})
    if v6_full and b_race:
        delta = v6_full.get('race_mae', 0) - b_race
        lines.append('### Experiment F: V6-Full vs M3c-V5')
        lines.append('- Race MAE: %.3f -> %.3f (delta: %+.3f pp)' % (b_race, v6_full.get('race_mae', 0), delta))
        lines.append('')

    # Experiment G: Gender
    g1 = results.get('G1 Occ-Gender', {})
    if g1 and b_gender:
        delta = (g1.get('gender_mae') or 0) - b_gender
        lines.append('### Experiment G: Occupation-Weighted Gender (G1 vs V5 gender)')
        lines.append('- Gender MAE: %.3f -> %s (delta: %+.3f pp)' % (
            b_gender, '%.3f' % g1['gender_mae'] if g1.get('gender_mae') else 'N/A', delta))
        lines.append('')

    # Experiment H: Hispanic
    h1 = results.get('H1 Geo-Hisp', {})
    if h1 and b_hisp:
        delta = (h1.get('hisp_mae') or 0) - b_hisp
        lines.append('### Experiment H: Geography-Heavy Hispanic (H1 vs V5 hispanic)')
        lines.append('- Hispanic MAE: %.3f -> %s (delta: %+.3f pp)' % (
            b_hisp, '%.3f' % h1['hisp_mae'] if h1.get('hisp_mae') else 'N/A', delta))
        lines.append('')

    # V6 targets check
    lines.extend(['---', '', '## V6 Target Check', ''])
    v6 = results.get('V6-Full', {})
    if v6:
        checks = [
            ('Race MAE < 4.50 pp', v6.get('race_mae', 99), 4.50),
            ('P>20pp < 16%%', (v6.get('p_gt_20pp', 1) * 100), 16.0),
            ('P>30pp < 6%%', (v6.get('p_gt_30pp', 1) * 100), 6.0),
            ('Abs Bias < 1.10', v6.get('abs_bias', 99), 1.10),
            ('Hispanic MAE < 8.00 pp', v6.get('hisp_mae', 99) or 99, 8.00),
            ('Gender MAE < 12.00 pp', v6.get('gender_mae', 99) or 99, 12.00),
        ]
        for label, actual_val, target in checks:
            status = 'PASS' if actual_val < target else 'FAIL'
            lines.append('- [%s] %s: actual=%.3f, target=%.3f' % (
                'x' if status == 'PASS' else ' ', label, actual_val, target))
    lines.append('')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
