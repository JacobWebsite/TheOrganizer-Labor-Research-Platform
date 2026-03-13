"""Run 11 methods (M1-M5 + M1b-M5b + M7) on companies, report summaries + CSV.

Usage:
    py scripts/analysis/demographics_comparison/run_comparison_200_v2.py
    py scripts/analysis/demographics_comparison/run_comparison_200_v2.py --companies selected_holdout_200.json

Requires selected_200.json or specified JSON (from select_200.py / select_holdout_200.py).
Uses CachedLoadersV2 for all methods (original M1-M5 + new M1b-M5b, M7).
M6 is excluded (identical to M3).
"""
import sys
import os
import json
import csv
import time
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from config import RACE_CATEGORIES, GENDER_CATEGORIES, HISPANIC_CATEGORIES
from eeo1_parser import load_eeo1_data, parse_eeo1_row, _safe_int
from data_loaders import zip_to_county, zip_to_state_fips
from metrics import compute_all_metrics
from cached_loaders import ALL_CACHED_METHODS
from cached_loaders_v2 import CachedLoadersV2, ALL_V2_CACHED_METHODS

SCRIPT_DIR = os.path.dirname(__file__)
DIMS_5D = ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']
DIM_LABELS = {
    'naics_group': 'INDUSTRY GROUP',
    'size': 'WORKFORCE SIZE',
    'region': 'REGION',
    'minority_share': 'MINORITY SHARE',
    'urbanicity': 'URBANICITY',
}

# Build combined method registry: M1-M5 (no M6) + M1b-M5b, M7
COMBINED_METHODS = {}
for name, fn in ALL_CACHED_METHODS.items():
    if 'M6' in name:
        continue  # M6 eliminated (identical to M3)
    COMBINED_METHODS[name] = fn
COMBINED_METHODS.update(ALL_V2_CACHED_METHODS)

METHOD_NAMES = list(COMBINED_METHODS.keys())

# Short labels for table display (11 methods)
SHORT_LABELS = {
    'M1 Baseline (60/40)': 'M1',
    'M2 Three-Layer (50/30/20)': 'M2',
    'M3 IPF': 'M3',
    'M4 Occ-Weighted': 'M4',
    'M5 Variable-Weight': 'M5',
    'M1b Learned-Wt': '1b',
    'M2b Workplace-Tract': '2b',
    'M3b Damp-IPF': '3b',
    'M4b State-Occ': '4b',
    'M5b Min-Adapt': '5b',
    'M7 Hybrid': 'M7',
}


def parse_args():
    parser = argparse.ArgumentParser(description='Run V2 demographics comparison')
    parser.add_argument('--companies', default='selected_200.json',
                        help='JSON file with selected companies (default: selected_200.json)')
    return parser.parse_args()


def load_selected(filepath):
    """Load selected companies JSON."""
    full_path = filepath if os.path.isabs(filepath) else os.path.join(SCRIPT_DIR, filepath)
    if not os.path.exists(full_path):
        print('ERROR: %s not found.' % full_path)
        sys.exit(1)
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f), full_path


def get_ground_truth(eeo1_rows, company_code, year):
    """Extract ground truth from EEO-1 for a specific company."""
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code and _safe_int(row.get('YEAR')) == year:
            return parse_eeo1_row(row)
    for row in eeo1_rows:
        if row.get('COMPANY') == company_code:
            return parse_eeo1_row(row)
    return None


def run_all_methods(cl, naics4, state_fips, county_fips):
    """Run all 11 methods using cached loaders."""
    results = {}
    for name, method_fn in COMBINED_METHODS.items():
        try:
            results[name] = method_fn(cl, naics4, state_fips, county_fips)
        except Exception as e:
            print('    WARNING: %s failed: %s' % (name, str(e)[:80]))
            results[name] = {'race': None, 'hispanic': None, 'gender': None}
    return results


def compute_method_metrics(method_results, truth):
    """Compute metrics for all methods against truth."""
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
    return company_metrics


def compute_overall_summary(all_metrics):
    """Compute cross-company summary statistics."""
    method_stats = defaultdict(lambda: {
        'race_maes': [], 'race_hellingers': [],
        'gender_maes': [], 'hisp_maes': [],
        'race_wins': 0, 'gender_wins': 0,
    })

    for company_key, method_metrics in all_metrics.items():
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


def print_dimension_tables(all_results):
    """Print 5 dimension summary tables (Race MAE) for 11 methods."""
    short_names = [SHORT_LABELS.get(m, m[:4]) for m in METHOD_NAMES]

    for dim_key in DIMS_5D:
        dim_label = DIM_LABELS.get(dim_key, dim_key)
        print('')
        print('BY %s (Race MAE)' % dim_label)
        print('=' * 120)

        # Gather buckets
        bucket_data = defaultdict(lambda: defaultdict(list))
        for entry in all_results:
            bucket = entry['classifications'][dim_key]
            for method_name, dims in entry['metrics'].items():
                race_m = dims.get('race', {})
                if race_m.get('mae') is not None:
                    bucket_data[bucket][method_name].append(race_m['mae'])

        # Header
        header = '%-26s | %3s' % ('Group', 'N')
        for sn in short_names:
            header += ' | %5s' % sn
        header += ' | Best'
        print(header)
        print('-' * 120)

        for bucket in sorted(bucket_data.keys()):
            methods = bucket_data[bucket]
            n = max(len(v) for v in methods.values()) if methods else 0
            row_str = '%-26s | %3d' % (bucket[:26], n)
            best_mae = float('inf')
            best_method = ''
            for i, method_name in enumerate(METHOD_NAMES):
                maes = methods.get(method_name, [])
                if maes:
                    avg = sum(maes) / len(maes)
                    row_str += ' | %5.1f' % avg
                    if avg < best_mae:
                        best_mae = avg
                        best_method = short_names[i]
                else:
                    row_str += ' | %5s' % 'N/A'
            row_str += ' | %s' % best_method
            print(row_str)


def print_overall_summary(method_stats, n_companies):
    """Print cross-company summary."""
    print('')
    print('=' * 90)
    print('OVERALL SUMMARY (%d companies, %d methods)' % (n_companies, len(METHOD_NAMES)))
    print('=' * 90)
    print('%-22s | %8s | %9s | %5s | %6s' % (
        'Method', 'Race MAE', 'Hellinger', 'R-Win', 'G-Win'))
    print('-' * 90)

    for method_name in METHOD_NAMES:
        s = method_stats[method_name]
        avg_race = '%.2f' % (sum(s['race_maes']) / len(s['race_maes'])) if s['race_maes'] else 'N/A'
        avg_hell = '%.4f' % (sum(s['race_hellingers']) / len(s['race_hellingers'])) if s['race_hellingers'] else 'N/A'
        label = SHORT_LABELS.get(method_name, method_name[:4])
        print('%-22s | %8s | %9s | %5d | %6d' % (
            method_name, avg_race, avg_hell,
            s['race_wins'], s['gender_wins']))


def print_bias_by_dimension(all_results):
    """Print bias analysis grouped by each classification dimension."""
    print('')
    print('=' * 90)
    print('BIAS ANALYSIS BY DIMENSION')
    print('=' * 90)

    for dim_key in DIMS_5D:
        dim_label = DIM_LABELS.get(dim_key, dim_key)
        print('')
        print('BIAS BY %s' % dim_label)
        print('-' * 90)

        bucket_entries = defaultdict(list)
        for entry in all_results:
            bucket = entry['classifications'][dim_key]
            bucket_entries[bucket].append(entry)

        for method_name in METHOD_NAMES:
            biases = []
            for bucket in sorted(bucket_entries.keys()):
                entries = bucket_entries[bucket]
                cat_errors = defaultdict(list)
                for entry in entries:
                    race_m = entry['metrics'].get(method_name, {}).get('race', {})
                    if race_m and race_m.get('signed'):
                        for cat, err in race_m['signed'].items():
                            cat_errors[cat].append(err)

                for cat in ['White', 'Black', 'Hispanic']:
                    errors = cat_errors.get(cat, [])
                    if not errors:
                        continue
                    avg_err = sum(errors) / len(errors)
                    if abs(avg_err) >= 2.0:
                        direction = 'overestimates' if avg_err > 0 else 'underestimates'
                        biases.append((bucket, cat, avg_err, direction))

            if biases:
                label = SHORT_LABELS.get(method_name, method_name[:4])
                print('%s (%s):' % (label, method_name))
                for bucket, cat, avg_err, direction in biases:
                    print('  %s: %s %s by avg %.1fpp' % (
                        bucket[:26], direction, cat, abs(avg_err)))


def write_detailed_csv(all_results, output_path):
    """Write one row per (company, method, dimension)."""
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
                     'naics_group', 'size_bucket', 'region', 'minority_share', 'urbanicity']
        signed_cols = sorted(c for c in all_cols if c.startswith('signed_'))
        cols = base_cols + signed_cols

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        print('Detailed CSV: %s (%d rows)' % (output_path, len(rows)))


def write_summary_csv(all_results, output_path):
    """Write one row per (classification_dimension, bucket, method)."""
    rows = []
    for dim_key in DIMS_5D:
        bucket_data = defaultdict(lambda: defaultdict(lambda: {
            'race_maes': [], 'gender_maes': [], 'hisp_maes': [],
            'race_hellingers': [], 'wins': 0}))

        bucket_wins = defaultdict(lambda: defaultdict(int))
        for entry in all_results:
            bucket = entry['classifications'][dim_key]
            best_mae = float('inf')
            best_method = None
            for method_name, dims in entry['metrics'].items():
                race_m = dims.get('race', {})
                gender_m = dims.get('gender', {})
                hisp_m = dims.get('hispanic', {})
                if race_m.get('mae') is not None:
                    bucket_data[bucket][method_name]['race_maes'].append(race_m['mae'])
                    if race_m['mae'] < best_mae:
                        best_mae = race_m['mae']
                        best_method = method_name
                if race_m.get('hellinger') is not None:
                    bucket_data[bucket][method_name]['race_hellingers'].append(race_m['hellinger'])
                if gender_m.get('mae') is not None:
                    bucket_data[bucket][method_name]['gender_maes'].append(gender_m['mae'])
                if hisp_m.get('mae') is not None:
                    bucket_data[bucket][method_name]['hisp_maes'].append(hisp_m['mae'])
            if best_method:
                bucket_wins[bucket][best_method] += 1

        for bucket in sorted(bucket_data.keys()):
            for method_name in METHOD_NAMES:
                d = bucket_data[bucket][method_name]
                n = len(d['race_maes'])
                rows.append({
                    'classification_dim': dim_key,
                    'bucket': bucket,
                    'method': method_name,
                    'n_companies': n,
                    'avg_mae_race': round(sum(d['race_maes']) / n, 2) if n else None,
                    'avg_mae_gender': round(sum(d['gender_maes']) / len(d['gender_maes']), 2) if d['gender_maes'] else None,
                    'avg_mae_hispanic': round(sum(d['hisp_maes']) / len(d['hisp_maes']), 2) if d['hisp_maes'] else None,
                    'avg_hellinger_race': round(sum(d['race_hellingers']) / len(d['race_hellingers']), 4) if d['race_hellingers'] else None,
                    'win_count': bucket_wins[bucket].get(method_name, 0),
                })

    if rows:
        cols = ['classification_dim', 'bucket', 'method', 'n_companies',
                'avg_mae_race', 'avg_mae_gender', 'avg_mae_hispanic',
                'avg_hellinger_race', 'win_count']
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
        print('Summary CSV:  %s (%d rows)' % (output_path, len(rows)))


def main():
    args = parse_args()
    t0 = time.time()

    # Derive output filenames from input
    input_basename = os.path.splitext(os.path.basename(args.companies))[0]
    if 'holdout' in input_basename:
        tag = 'holdout_200'
    elif '200' in input_basename:
        tag = 'original_200'
    else:
        tag = input_basename

    # Load selected companies
    companies, full_path = load_selected(args.companies)
    print('DEMOGRAPHICS COMPARISON V2 (11 methods)')
    print('Input: %s' % full_path)
    print('%d companies, %d methods' % (len(companies), len(COMBINED_METHODS)))
    print('Methods: %s' % ', '.join(SHORT_LABELS.get(m, m) for m in METHOD_NAMES))
    print('=' * 90)

    # Load EEO-1 data
    print('Loading EEO-1 ground truth...')
    eeo1_rows = load_eeo1_data()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV2(cur)

    all_results = []
    skipped = 0

    for i, company in enumerate(companies):
        if (i + 1) % 20 == 0 or i == 0:
            elapsed = time.time() - t0
            print('  Processing %d/%d (%.0fs elapsed)...' % (i + 1, len(companies), elapsed))

        company_code = company['company_code']
        year = company.get('year', 2020)
        naics = company.get('naics', '')
        naics4 = naics[:4]
        zipcode = company.get('zipcode', '')
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')

        # Get ground truth
        truth = get_ground_truth(eeo1_rows, company_code, year)
        if not truth:
            skipped += 1
            continue

        # Resolve geography if not in JSON
        if not county_fips:
            county_fips = zip_to_county(cur, zipcode)
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
        if not county_fips:
            skipped += 1
            continue

        # Run all 11 methods
        method_results = run_all_methods(cl, naics4, state_fips, county_fips)

        # Compute metrics
        company_metrics = compute_method_metrics(method_results, truth)

        all_results.append({
            'name': company.get('name', truth['name']),
            'company_code': company_code,
            'classifications': company.get('classifications', {}),
            'metrics': company_metrics,
            'truth': truth,
        })

    elapsed = time.time() - t0
    print('')
    print('Processed %d companies in %.1fs (%d skipped)' % (
        len(all_results), elapsed, skipped))

    # Cache stats
    cl.print_stats()

    # Count non-null estimates
    total_estimates = 0
    null_estimates = 0
    for entry in all_results:
        for method_name, dims in entry['metrics'].items():
            for dim in ['race', 'gender', 'hispanic']:
                total_estimates += 1
                if not dims.get(dim, {}).get('mae'):
                    null_estimates += 1
    print('Estimates: %d total, %d non-null, %d null' % (
        total_estimates, total_estimates - null_estimates, null_estimates))

    if not all_results:
        print('No results to summarize.')
        conn.close()
        return

    # Print dimension tables
    print_dimension_tables(all_results)

    # Overall summary
    all_metrics = {e['company_code']: e['metrics'] for e in all_results}
    method_stats = compute_overall_summary(all_metrics)
    print_overall_summary(method_stats, len(all_results))

    # Bias analysis
    print_bias_by_dimension(all_results)

    # Write CSVs
    print('')
    print('Writing CSV files...')
    detail_path = os.path.join(SCRIPT_DIR, 'comparison_%s_v2_detailed.csv' % tag)
    summary_path = os.path.join(SCRIPT_DIR, 'comparison_%s_v2_summary.csv' % tag)
    write_detailed_csv(all_results, detail_path)
    write_summary_csv(all_results, summary_path)

    print('')
    print('Done in %.1fs' % (time.time() - t0))
    conn.close()


if __name__ == '__main__':
    main()
