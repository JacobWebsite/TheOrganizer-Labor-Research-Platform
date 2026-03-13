"""Run V4+V5 methods on all 997 companies, report summaries + CSV.

V5 Run 1 evaluation:
- All V4 methods (unchanged, for comparison)
- V5 methods: smoothed IPF + PUMS metro + Admin/Staffing routing fix
- Composite scores for all methods
- PUMS coverage tracking per company

Usage:
    py scripts/analysis/demographics_comparison/run_comparison_v5_run1.py
"""
import sys
import os
import json
import csv
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from config import RACE_CATEGORIES, GENDER_CATEGORIES, HISPANIC_CATEGORIES
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county, zip_to_state_fips
from metrics import compute_all_metrics, composite_score
from cached_loaders import ALL_CACHED_METHODS
from cached_loaders_v2 import ALL_V2_CACHED_METHODS
from cached_loaders_v3 import ALL_V3_CACHED_METHODS, V3_METHODS_NEED_EXTRA
from cached_loaders_v4 import ALL_V4_CACHED_METHODS, V4_METHODS_NEED_EXTRA
from cached_loaders_v5 import (
    CachedLoadersV5, ALL_V5_CACHED_METHODS, V5_METHODS_NEED_EXTRA,
)
from classifiers import classify_naics_group

SCRIPT_DIR = os.path.dirname(__file__)

# Build combined method registry: V4 + V5
COMBINED_METHODS = {}

# 5 originals (no M6)
for name, fn in ALL_CACHED_METHODS.items():
    if 'M6' in name:
        continue
    COMBINED_METHODS[name] = fn

# 2 V2 survivors
V2_SURVIVORS = {'M1b Learned-Wt', 'M3b Damp-IPF'}
for name, fn in ALL_V2_CACHED_METHODS.items():
    if name in V2_SURVIVORS:
        COMBINED_METHODS[name] = fn

# All V3
COMBINED_METHODS.update(ALL_V3_CACHED_METHODS)

# All V4
COMBINED_METHODS.update(ALL_V4_CACHED_METHODS)

# All V5
COMBINED_METHODS.update(ALL_V5_CACHED_METHODS)

ALL_METHODS_NEED_EXTRA = V3_METHODS_NEED_EXTRA | V4_METHODS_NEED_EXTRA | V5_METHODS_NEED_EXTRA
METHOD_NAMES = list(COMBINED_METHODS.keys())

# Short labels
SHORT_LABELS = {
    'M1 Baseline (60/40)': 'M1',
    'M2 Three-Layer (50/30/20)': 'M2',
    'M3 IPF': 'M3',
    'M4 Occ-Weighted': 'M4',
    'M5 Variable-Weight': 'M5',
    'M1b Learned-Wt': '1b',
    'M3b Damp-IPF': '3b',
    'M1c CV-Learned-Wt': '1c',
    'M1d Regional-Wt': '1d',
    'M2c ZIP-Tract': '2c',
    'M3c Var-Damp-IPF': '3c',
    'M3d Select-Damp': '3d',
    'M4c Top10-Occ': '4c',
    'M4d State-Top5': '4d',
    'M5c CV-Var-Wt': '5c',
    'M5d Corr-Min-Adapt': '5d',
    'M3e Fin-Route-IPF': '3e',
    'M3f Min-Ind-Thresh': '3f',
    'M1e Hi-Min-Floor': '1e',
    'M4e Var-Occ-Trim': '4e',
    'M2d Amp-Tract': '2d',
    'M5e Ind-Dispatch': '5e',
    'M8 Adaptive-Router': 'M8',
    'M3c-V5 Smooth-Var-Damp': '3cV5',
    'M3e-V5 Smooth-Fin-Route': '3eV5',
    'M2c-V5 PUMS-ZIP-Tract': '2cV5',
    'M5e-V5 Ind-Dispatch': '5eV5',
    'M8-V5 Adaptive-Router': 'M8V5',
    'Expert-A Smooth-IPF': 'ExpA',
    'Expert-B Tract-Heavy': 'ExpB',
}


def load_selected(filepath='all_companies_v4.json'):
    """Load selected companies JSON."""
    full_path = filepath if os.path.isabs(filepath) else os.path.join(SCRIPT_DIR, filepath)
    if not os.path.exists(full_path):
        print('ERROR: %s not found.' % full_path)
        sys.exit(1)
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f), full_path


def get_ground_truth(eeo1_rows, company_code, year):
    """Extract ground truth from EEO-1."""
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code and _safe_int(row.get('YEAR')) == year:
            return parse_eeo1_row(row)
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code:
            return parse_eeo1_row(row)
    return None


def run_all_methods(cl, naics4, state_fips, county_fips,
                    state_abbr='', zipcode='',
                    naics_group='', county_minority_share=None,
                    urbanicity=''):
    """Run all methods using cached loaders."""
    results = {}
    for name, method_fn in COMBINED_METHODS.items():
        try:
            if name in ALL_METHODS_NEED_EXTRA:
                results[name] = method_fn(
                    cl, naics4, state_fips, county_fips,
                    state_abbr=state_abbr, zipcode=zipcode,
                    naics_group=naics_group,
                    county_minority_share=county_minority_share,
                    urbanicity=urbanicity)
            else:
                results[name] = method_fn(cl, naics4, state_fips, county_fips)
        except Exception as e:
            print('    WARNING: %s failed: %s' % (name, str(e)[:80]))
            results[name] = {'race': None, 'hispanic': None, 'gender': None}
    return results


def check_zero_collapse(result):
    """Check if any race category is exactly 0.000."""
    race = result.get('race')
    if race is None:
        return False
    for cat in ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']:
        if race.get(cat) == 0.0 or race.get(cat) == 0:
            return True
    return False


def main():
    t0 = time.time()

    companies, full_path = load_selected()
    print('V5 RUN 1: Demographics Comparison')
    print('=' * 100)
    print('Input: %s' % full_path)
    print('%d companies, %d methods (%d V5 new)' % (
        len(companies), len(COMBINED_METHODS), len(ALL_V5_CACHED_METHODS)))
    print('V5 methods: %s' % ', '.join(ALL_V5_CACHED_METHODS.keys()))
    print('=' * 100)

    # Load EEO-1 ground truth
    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    # Connect with V5 loaders
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV5(cur)

    # Check if PUMS table exists
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'pums_metro_demographics'
        ) AS e
    """)
    pums_exists = cur.fetchone()['e']
    if not pums_exists:
        print('WARNING: pums_metro_demographics table does not exist.')
        print('  Run load_pums_metro.py first for PUMS metro data.')
        print('  Continuing without PUMS (all companies will use acs_state).')

    all_results = []
    skipped = 0
    pums_count = 0
    zero_collapse_counts = defaultdict(int)

    for i, company in enumerate(companies):
        if (i + 1) % 50 == 0 or i == 0:
            elapsed = time.time() - t0
            print('  Processing %d/%d (%.0fs elapsed)...' % (i + 1, len(companies), elapsed))

        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        zipcode = company.get('zipcode', '')
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')
        state_abbr = company.get('state', '')

        truth = get_ground_truth(eeo1_rows, company_code, year)
        if not truth:
            skipped += 1
            continue

        if not county_fips:
            county_fips = zip_to_county(cur, zipcode)
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        naics_group = company.get('classifications', {}).get('naics_group', '')
        urbanicity = company.get('classifications', {}).get('urbanicity', '')
        county_minority_share = cl.get_lodes_pct_minority(county_fips)

        # Run all methods
        method_results = run_all_methods(
            cl, naics4, state_fips, county_fips,
            state_abbr=state_abbr, zipcode=zipcode,
            naics_group=naics_group,
            county_minority_share=county_minority_share,
            urbanicity=urbanicity)

        # Track PUMS coverage (from V5 methods)
        data_source = 'acs_state'
        for v5_name in ALL_V5_CACHED_METHODS:
            v5_result = method_results.get(v5_name, {})
            if v5_result and v5_result.get('_data_source') == 'pums_metro':
                data_source = 'pums_metro'
                break
        if data_source == 'pums_metro':
            pums_count += 1

        # Check zero collapse for V5 methods
        for v5_name in ALL_V5_CACHED_METHODS:
            v5_result = method_results.get(v5_name, {})
            if v5_result and check_zero_collapse(v5_result):
                zero_collapse_counts[v5_name] += 1

        # Extract routing info
        m8_result = method_results.get('M8 Adaptive-Router', {})
        m8_routing = m8_result.get('routing_used', '') if m8_result else ''
        m8v5_result = method_results.get('M8-V5 Adaptive-Router', {})
        m8v5_routing = m8v5_result.get('routing_used', '') if m8v5_result else ''

        # Compute metrics
        company_metrics = {}
        for method_name, result in method_results.items():
            method_dims = {}
            for dim in ['race', 'gender', 'hispanic']:
                est = result.get(dim) if result else None
                actual = truth.get(dim)
                if est and actual:
                    method_dims[dim] = compute_all_metrics(est, actual)
                else:
                    method_dims[dim] = {}
            company_metrics[method_name] = method_dims

        all_results.append({
            'name': company.get('name', truth['name']),
            'company_code': company_code,
            'classifications': company.get('classifications', {}),
            'metrics': company_metrics,
            'truth': truth,
            'source_set': company.get('source_set', ''),
            'data_source': data_source,
            'm8_routing': m8_routing,
            'm8v5_routing': m8v5_routing,
            'method_results': {n: r for n, r in method_results.items()},
        })

    elapsed = time.time() - t0
    print('')
    print('Processed %d companies in %.1fs (%d skipped)' % (
        len(all_results), elapsed, skipped))
    cl.print_stats()

    if not all_results:
        print('No results to summarize.')
        conn.close()
        return

    # ============================================================
    # V5 Verification Checks
    # ============================================================
    print('')
    print('=' * 100)
    print('V5 RUN 1 VERIFICATION')
    print('=' * 100)

    # Check 1: Admin/Staffing routes to M1B in M8-V5
    admin_m1b_count = sum(1 for r in all_results if r['m8v5_routing'] == 'M1B'
                          and r['classifications'].get('naics_group') == 'Admin/Staffing (56)')
    admin_total = sum(1 for r in all_results
                      if r['classifications'].get('naics_group') == 'Admin/Staffing (56)')
    admin_m4e_v4 = sum(1 for r in all_results if r['m8_routing'] == 'M4E'
                       and r['classifications'].get('naics_group') == 'Admin/Staffing (56)')
    print('')
    print('CHECK 1: Admin/Staffing routing')
    print('  V4 M8: %d/%d Admin/Staffing -> M4E' % (admin_m4e_v4, admin_total))
    print('  V5 M8: %d/%d Admin/Staffing -> M1B' % (admin_m1b_count, admin_total))
    print('  %s' % ('PASS' if admin_m1b_count == admin_total else 'FAIL'))

    # Check 2: No V5 method produces 0.000 for any race category
    print('')
    print('CHECK 2: Zero-collapse in V5 methods')
    any_zeros = False
    for v5_name, count in zero_collapse_counts.items():
        if count > 0:
            print('  WARNING: %s has %d companies with zero race values' % (v5_name, count))
            any_zeros = True
    if not any_zeros:
        print('  PASS: No V5 method produces 0.000 for any race category')
    else:
        print('  FAIL: Some V5 methods have zero-collapse')

    # Check 3: PUMS coverage
    pums_pct = 100.0 * pums_count / len(all_results) if all_results else 0
    print('')
    print('CHECK 3: PUMS metro coverage')
    print('  %d/%d companies (%.1f%%) use pums_metro data' % (
        pums_count, len(all_results), pums_pct))
    print('  %s' % ('PASS' if pums_pct >= 50 else 'BELOW TARGET (want >=50%%)'))

    # ============================================================
    # Composite Scores
    # ============================================================
    print('')
    print('=' * 100)
    print('COMPOSITE SCORES (all methods)')
    print('=' * 100)
    print('%-28s | %9s | %8s | %8s | %8s | %10s' % (
        'Method', 'Composite', 'Race MAE', 'P>20pp', 'P>30pp', 'Abs Bias'))
    print('-' * 100)

    method_composites = {}
    for method_name in METHOD_NAMES:
        preds = []
        actuals = []
        for entry in all_results:
            est = entry['method_results'].get(method_name, {}).get('race')
            act = entry['truth'].get('race')
            if est and act:
                preds.append(est)
                actuals.append(act)

        comp = composite_score(preds, actuals)
        if comp:
            method_composites[method_name] = comp

    # Sort by composite score
    sorted_methods = sorted(method_composites.keys(),
                            key=lambda m: method_composites[m]['composite'])

    for method_name in sorted_methods:
        c = method_composites[method_name]
        label = SHORT_LABELS.get(method_name, method_name[:6])
        print('%-28s | %9.3f | %8.3f | %7.3f%% | %7.3f%% | %10.3f' % (
            method_name, c['composite'], c['avg_mae'],
            c['p_gt_20pp'] * 100, c['p_gt_30pp'] * 100, c['mean_abs_bias']))

    # ============================================================
    # M8-V5 Routing Distribution
    # ============================================================
    print('')
    print('=' * 100)
    print('M8-V5 ROUTING DISTRIBUTION')
    print('=' * 100)

    route_counts = defaultdict(int)
    route_maes = defaultdict(list)
    for entry in all_results:
        routing = entry.get('m8v5_routing', '')
        if routing:
            route_counts[routing] += 1
        m8v5_race = entry['metrics'].get('M8-V5 Adaptive-Router', {}).get('race', {})
        if m8v5_race.get('mae') is not None and routing:
            route_maes[routing].append(m8v5_race['mae'])

    print('  %-15s | %5s | %8s' % ('Route', 'Count', 'Avg MAE'))
    print('  ' + '-' * 40)
    for route in sorted(route_counts.keys()):
        maes = route_maes.get(route, [])
        avg = '%.2f' % (sum(maes) / len(maes)) if maes else 'N/A'
        print('  %-15s | %5d | %8s' % (route, route_counts[route], avg))
    print('  %-15s | %5d |' % ('TOTAL', sum(route_counts.values())))

    # ============================================================
    # Overall Race MAE Summary (top 15)
    # ============================================================
    print('')
    print('=' * 100)
    print('RACE MAE RANKING (top 15)')
    print('=' * 100)

    race_maes = {}
    for method_name in METHOD_NAMES:
        maes = []
        for entry in all_results:
            race_m = entry['metrics'].get(method_name, {}).get('race', {})
            if race_m.get('mae') is not None:
                maes.append(race_m['mae'])
        if maes:
            race_maes[method_name] = sum(maes) / len(maes)

    sorted_by_mae = sorted(race_maes.keys(), key=lambda m: race_maes[m])
    for i, method_name in enumerate(sorted_by_mae[:15]):
        v5_tag = ' [V5]' if 'V5' in method_name or 'Expert' in method_name else ''
        print('  %2d. %-28s  %.2f%s' % (i + 1, method_name, race_maes[method_name], v5_tag))

    # ============================================================
    # Write CSV
    # ============================================================
    print('')
    print('Writing CSV files...')

    detail_path = os.path.join(SCRIPT_DIR, 'comparison_v5_run1_detailed.csv')
    rows = []
    for entry in all_results:
        cls = entry['classifications']
        for method_name, dims in entry['metrics'].items():
            for dim_name in ['race', 'gender', 'hispanic']:
                m = dims.get(dim_name, {})
                if not m:
                    continue
                row = {
                    'company': entry['name'],
                    'company_code': entry['company_code'],
                    'method': method_name,
                    'dimension': dim_name,
                    'mae': m.get('mae'),
                    'rmse': m.get('rmse'),
                    'hellinger': m.get('hellinger'),
                    'max_error': m.get('max_error'),
                    'max_error_cat': m.get('max_error_cat'),
                    'naics_group': cls.get('naics_group', ''),
                    'size_bucket': cls.get('size', ''),
                    'region': cls.get('region', ''),
                    'minority_share': cls.get('minority_share', ''),
                    'urbanicity': cls.get('urbanicity', ''),
                    'source_set': entry.get('source_set', ''),
                    'data_source': entry.get('data_source', ''),
                }
                if m.get('signed'):
                    for cat, err in m['signed'].items():
                        row['signed_%s' % cat] = err
                rows.append(row)

    if rows:
        all_cols = set()
        for r in rows:
            all_cols.update(r.keys())
        base_cols = ['company', 'company_code', 'method', 'dimension',
                     'mae', 'rmse', 'hellinger', 'max_error', 'max_error_cat',
                     'naics_group', 'size_bucket', 'region', 'minority_share',
                     'urbanicity', 'source_set', 'data_source']
        signed_cols = sorted(c for c in all_cols if c.startswith('signed_'))
        cols = base_cols + signed_cols

        with open(detail_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        print('Detailed CSV: %s (%d rows)' % (detail_path, len(rows)))

    # Composite scores CSV
    comp_path = os.path.join(SCRIPT_DIR, 'composite_scores_v5_run1.csv')
    if method_composites:
        comp_rows = []
        for method_name in sorted_methods:
            c = method_composites[method_name]
            comp_rows.append({
                'method': method_name,
                'composite': c['composite'],
                'avg_mae': c['avg_mae'],
                'p_gt_20pp': c['p_gt_20pp'],
                'p_gt_30pp': c['p_gt_30pp'],
                'mean_abs_bias': c['mean_abs_bias'],
                'n_companies': c['n_companies'],
                'is_v5': 'V5' in method_name or 'Expert' in method_name,
            })
        with open(comp_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=comp_rows[0].keys())
            writer.writeheader()
            writer.writerows(comp_rows)
        print('Composite CSV: %s (%d rows)' % (comp_path, len(comp_rows)))

    print('')
    print('Done in %.1fs' % (time.time() - t0))
    conn.close()


if __name__ == '__main__':
    main()
