"""Main comparison script: run all 6 methods against EEO-1 ground truth.

Usage:
    py scripts/analysis/demographics_comparison/run_comparison.py

Requires VALIDATION_COMPANIES to be populated in config.py.
"""
import sys
import os
import csv
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

# Local imports (same directory)
sys.path.insert(0, os.path.dirname(__file__))
from config import VALIDATION_COMPANIES, RACE_CATEGORIES, GENDER_CATEGORIES, HISPANIC_CATEGORIES
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county, zip_to_state_fips
from methodologies import ALL_METHODS
from metrics import compute_all_metrics
from bds_hc_check import check_company


def get_ground_truth(eeo1_rows, company_code, year):
    """Extract ground truth from EEO-1 for a specific company."""
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code and _safe_int(row.get('YEAR')) == year:
            return parse_eeo1_row(row)
    # Try any year
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code:
            return parse_eeo1_row(row)
    return None


def run_all_methods(cur, naics4, state_fips, county_fips):
    """Run all 6 methods and return results dict."""
    results = {}
    for name, method_fn in ALL_METHODS.items():
        try:
            result = method_fn(cur, naics4, state_fips, county_fips)
            results[name] = result
        except Exception as e:
            print('    WARNING: %s failed: %s' % (name, str(e)[:80]))
            results[name] = {'race': None, 'hispanic': None, 'gender': None}
    return results


def print_company_results(company_info, truth, method_results, all_metrics):
    """Print results for one company."""
    print('')
    print('COMPANY: %s (%s, NAICS %s, N=%d)' % (
        company_info.get('name', '?'),
        company_info.get('state', '?'),
        company_info.get('naics', '?')[:6],
        truth['total'],
    ))
    print('Axis: %s' % company_info.get('axis_label', '?'))

    # Actual values
    print('Actual Race:  ' + '  '.join(
        '%s=%.0f%%' % (k, truth['race'][k]) for k in RACE_CATEGORIES
        if truth['race'].get(k, 0) >= 0.5))
    print('Actual Gender: F=%.0f%% M=%.0f%%' % (
        truth['gender']['Female'], truth['gender']['Male']))
    print('Actual Hispanic: H=%.0f%% NH=%.0f%%' % (
        truth['hispanic']['Hispanic'], truth['hispanic']['Not Hispanic']))

    print('-' * 78)
    print('%-22s | %8s | %10s | %10s | %s' % (
        'Method', 'Race MAE', 'Race Hell.', 'Gender MAE', 'Worst Cat'))
    print('-' * 78)

    for method_name in ALL_METHODS:
        m = all_metrics.get(method_name, {})
        race_m = m.get('race', {})
        gender_m = m.get('gender', {})

        race_mae = '%.1f' % race_m['mae'] if race_m.get('mae') is not None else 'N/A'
        race_hell = '%.3f' % race_m['hellinger'] if race_m.get('hellinger') is not None else 'N/A'
        gender_mae = '%.1f' % gender_m['mae'] if gender_m.get('mae') is not None else 'N/A'

        # Worst category from signed errors
        worst = ''
        if race_m.get('signed'):
            worst_cat = max(race_m['signed'], key=lambda k: abs(race_m['signed'][k]))
            worst_val = race_m['signed'][worst_cat]
            sign = '+' if worst_val > 0 else ''
            worst = '%s(%s%.0f)' % (worst_cat, sign, worst_val)

        print('%-22s | %8s | %10s | %10s | %s' % (
            method_name, race_mae, race_hell, gender_mae, worst))


def compute_overall_summary(all_company_metrics):
    """Compute cross-company summary statistics."""
    method_stats = defaultdict(lambda: {
        'race_maes': [], 'race_hellingers': [],
        'gender_maes': [], 'hisp_maes': [],
        'race_wins': 0, 'gender_wins': 0,
    })

    for company_name, method_metrics in all_company_metrics.items():
        best_race_mae = float('inf')
        best_race_method = None
        best_gender_mae = float('inf')
        best_gender_method = None

        for method_name, dims in method_metrics.items():
            race_m = dims.get('race', {})
            gender_m = dims.get('gender', {})
            hisp_m = dims.get('hispanic', {})

            if race_m.get('mae') is not None:
                method_stats[method_name]['race_maes'].append(race_m['mae'])
                if race_m['mae'] < best_race_mae:
                    best_race_mae = race_m['mae']
                    best_race_method = method_name
            if race_m.get('hellinger') is not None:
                method_stats[method_name]['race_hellingers'].append(race_m['hellinger'])
            if gender_m.get('mae') is not None:
                method_stats[method_name]['gender_maes'].append(gender_m['mae'])
                if gender_m['mae'] < best_gender_mae:
                    best_gender_mae = gender_m['mae']
                    best_gender_method = method_name
            if hisp_m.get('mae') is not None:
                method_stats[method_name]['hisp_maes'].append(hisp_m['mae'])

        if best_race_method:
            method_stats[best_race_method]['race_wins'] += 1
        if best_gender_method:
            method_stats[best_gender_method]['gender_wins'] += 1

    return method_stats


def print_overall_summary(method_stats):
    """Print cross-company summary."""
    print('')
    print('=' * 78)
    print('OVERALL SUMMARY')
    print('=' * 78)
    print('%-22s | %12s | %13s | %9s | %11s' % (
        'Method', 'Avg Race MAE', 'Avg Hellinger', 'Race Wins', 'Gender Wins'))
    print('-' * 78)

    for method_name in ALL_METHODS:
        s = method_stats[method_name]
        avg_race = '%.1f' % (sum(s['race_maes']) / len(s['race_maes'])) if s['race_maes'] else 'N/A'
        avg_hell = '%.3f' % (sum(s['race_hellingers']) / len(s['race_hellingers'])) if s['race_hellingers'] else 'N/A'

        print('%-22s | %12s | %13s | %9d | %11d' % (
            method_name, avg_race, avg_hell,
            s['race_wins'], s['gender_wins'],
        ))


def print_bias_analysis(all_company_metrics, all_truths):
    """Analyze systematic biases."""
    print('')
    print('=' * 78)
    print('BIAS ANALYSIS')
    print('=' * 78)

    # Collect signed errors across all methods and companies
    for method_name in ALL_METHODS:
        cat_errors = defaultdict(list)
        for company_name, method_metrics in all_company_metrics.items():
            dims = method_metrics.get(method_name, {})
            for dim_name in ['race', 'hispanic']:
                m = dims.get(dim_name, {})
                if m and m.get('signed'):
                    for cat, err in m['signed'].items():
                        cat_errors[(dim_name, cat)].append(err)

        biases = []
        for (dim, cat), errors in cat_errors.items():
            avg_err = sum(errors) / len(errors) if errors else 0
            if abs(avg_err) >= 1.5:
                direction = 'overestimates' if avg_err > 0 else 'underestimates'
                biases.append((dim, cat, avg_err, direction))

        if biases:
            print('%s:' % method_name)
            for dim, cat, avg_err, direction in sorted(biases, key=lambda x: -abs(x[2])):
                print('  %s %s %s by avg %.1fpp' % (direction, dim, cat, abs(avg_err)))


def write_csv_results(all_company_metrics, all_truths, output_path):
    """Write detailed results to CSV."""
    rows = []
    for company_name, method_metrics in all_company_metrics.items():
        truth = all_truths.get(company_name, {})
        for method_name, dims in method_metrics.items():
            for dim_name in ['race', 'gender', 'hispanic']:
                m = dims.get(dim_name, {})
                if m:
                    row = {
                        'company': company_name,
                        'method': method_name,
                        'dimension': dim_name,
                        'mae': m.get('mae'),
                        'rmse': m.get('rmse'),
                        'hellinger': m.get('hellinger'),
                        'max_error': m.get('max_error'),
                        'max_error_cat': m.get('max_error_cat'),
                    }
                    # Add signed errors
                    if m.get('signed'):
                        for cat, err in m['signed'].items():
                            row['signed_%s' % cat] = err
                    rows.append(row)

    if rows:
        # Collect all column names
        all_cols = set()
        for r in rows:
            all_cols.update(r.keys())
        cols = ['company', 'method', 'dimension', 'mae', 'rmse', 'hellinger',
                'max_error', 'max_error_cat'] + sorted(
            c for c in all_cols if c.startswith('signed_'))

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        print('Results written to %s' % output_path)


def main():
    if not VALIDATION_COMPANIES:
        print('ERROR: No validation companies configured.')
        print('Run select_companies.py first, then populate VALIDATION_COMPANIES in config.py.')
        print('')
        print('Running in demo mode with first eligible EEO-1 companies...')
        run_demo_mode()
        return

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print('DEMOGRAPHICS METHODOLOGY COMPARISON')
    print('%d companies, %d methods, EEO-1 ground truth' % (
        len(VALIDATION_COMPANIES), len(ALL_METHODS)))
    print('=' * 78)

    eeo1_rows = load_eeo1_data()

    all_company_metrics = {}
    all_truths = {}

    for ci, company in enumerate(VALIDATION_COMPANIES):
        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        zipcode = company.get('zipcode', '')
        state = company.get('state', '')

        # Get ground truth
        truth = get_ground_truth(eeo1_rows, company_code, year)
        if not truth:
            print('\nWARNING: No EEO-1 data for %s (code=%s, year=%d)' % (
                company.get('name', '?'), company_code, year))
            continue

        # Resolve geography
        county_fips = zip_to_county(cur, zipcode)
        state_fips = zip_to_state_fips(cur, zipcode)
        if not county_fips:
            print('\nWARNING: Cannot resolve ZIP %s for %s' % (zipcode, truth['name']))
            continue

        # Run all methods
        method_results = run_all_methods(cur, naics4, state_fips, county_fips)

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

        company_label = company.get('name', truth['name'])
        all_company_metrics[company_label] = company_metrics
        all_truths[company_label] = truth

        # Print per-company results
        print_company_results(company, truth, method_results, company_metrics)

    # Overall summary
    if all_company_metrics:
        method_stats = compute_overall_summary(all_company_metrics)
        print_overall_summary(method_stats)
        print_bias_analysis(all_company_metrics, all_truths)

        # BDS-HC plausibility check
        print('')
        print('=' * 78)
        print('BDS-HC PLAUSIBILITY CHECK')
        print('=' * 78)
        print('%-20s | %6s | %7s | %14s | %18s | %s' % (
            'Company', 'Sector', 'Size', 'Est % Minority', 'BDS-HC Modal', 'In Range?'))
        print('-' * 78)

        # Use M1 Baseline estimates for BDS check
        for ci, company in enumerate(VALIDATION_COMPANIES):
            truth = all_truths.get(company.get('name', ''), None)
            if not truth:
                continue
            naics = company.get('naics', '')
            # Calculate non-White % from truth
            minority_pct = 100.0 - truth['race'].get('White', 0)
            bds = check_company(naics, truth['total'], minority_pct,
                                truth['gender'].get('Female'),
                                truth['hispanic'].get('Hispanic'))
            race_check = bds.get('race', {})
            in_range = 'YES' if race_check.get('in_range') else ('NO' if race_check.get('in_range') is False else '?')
            print('%-20s | %6s | %7s | %13.0f%% | %18s | %s' % (
                company.get('name', '?')[:20],
                naics[:2],
                'small' if truth['total'] < 500 else 'large',
                minority_pct,
                race_check.get('modal_bucket', 'N/A'),
                in_range,
            ))

        # Write CSV
        output_dir = os.path.dirname(__file__)
        csv_path = os.path.join(output_dir, 'demographics_comparison_results.csv')
        write_csv_results(all_company_metrics, all_truths, csv_path)

    conn.close()


def run_demo_mode():
    """Run with auto-selected companies when VALIDATION_COMPANIES is empty."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    eeo1_rows = load_eeo1_data()
    print('Loaded %d EEO-1 rows' % len(eeo1_rows))

    # Auto-select first 5 eligible companies
    demo_companies = []
    seen = set()
    for row in eeo1_rows:
        company = row.get('COMPANY', '')
        year = _safe_int(row.get('YEAR', 0))
        naics = (row.get('NAICS') or '').strip()
        total = _safe_int(row.get('TOTAL10', 0))
        zipcode = (row.get('ZIPCODE') or '').strip()[:5]

        if company in seen or not naics or total < 200 or not zipcode or year < 2019:
            continue

        county_fips = zip_to_county(cur, zipcode)
        if not county_fips:
            continue
        state_fips = county_fips[:2]

        # Check LODES
        cur.execute(
            "SELECT demo_total_jobs FROM cur_lodes_geo_metrics WHERE county_fips = %s",
            [county_fips])
        lodes_row = cur.fetchone()
        if not lodes_row or float(lodes_row['demo_total_jobs'] or 0) == 0:
            continue

        truth = parse_eeo1_row(row)
        if not truth:
            continue

        seen.add(company)
        demo_companies.append({
            'name': truth['name'],
            'naics': naics,
            'naics4': naics[:4],
            'state': row.get('STATE', ''),
            'state_fips': state_fips,
            'county_fips': county_fips,
            'truth': truth,
            'year': year,
            'axis_label': 'auto-selected',
        })

        if len(demo_companies) >= 5:
            break

    print('Auto-selected %d companies for demo' % len(demo_companies))
    print('=' * 78)

    all_company_metrics = {}
    all_truths = {}

    for dc in demo_companies:
        truth = dc['truth']
        method_results = run_all_methods(cur, dc['naics4'], dc['state_fips'], dc['county_fips'])

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

        all_company_metrics[dc['name']] = company_metrics
        all_truths[dc['name']] = truth

        print_company_results(dc, truth, method_results, company_metrics)

    if all_company_metrics:
        method_stats = compute_overall_summary(all_company_metrics)
        print_overall_summary(method_stats)
        print_bias_analysis(all_company_metrics, all_truths)

    conn.close()


if __name__ == '__main__':
    main()
