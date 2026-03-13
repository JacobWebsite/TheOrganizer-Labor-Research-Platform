"""Build gate training data from V4 comparison results + DB features.

Reads comparison_all_v4_detailed.csv, computes per-company best method for race,
and assembles features for training a routing gate model.

Output: gate_training_data.csv (997 rows with features + labels)

Usage:
    py scripts/analysis/demographics_comparison/build_gate_training_data.py
"""
import sys
import os
import csv
import json
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v3 import CachedLoadersV3
from data_loaders import zip_to_county
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)

# 5 candidate methods for the gate
GATE_METHODS = [
    'M3b Damp-IPF',
    'M3 IPF',
    'M2c ZIP-Tract',
    'M3c Var-Damp-IPF',
    'M1b Learned-Wt',
]

# Hard segment indicators
HARD_SEGMENTS = {
    'Finance/Insurance (52)': 'is_finance_insurance',
    'Admin/Staffing (56)': 'is_admin_staffing',
    'Healthcare/Social (62)': 'is_healthcare',
}


def load_v4_detailed():
    """Load comparison_all_v4_detailed.csv and extract per-company race MAE."""
    csv_path = os.path.join(SCRIPT_DIR, 'comparison_all_v4_detailed.csv')
    if not os.path.exists(csv_path):
        print('ERROR: %s not found. Run run_comparison_all_v4.py first.' % csv_path)
        sys.exit(1)

    # {company_code: {method_name: race_mae}}
    company_method_maes = defaultdict(dict)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('dimension') != 'race':
                continue
            method = row.get('method', '')
            if method not in GATE_METHODS:
                continue
            company_code = row.get('company_code', '')
            mae_str = row.get('mae', '')
            if mae_str and company_code:
                try:
                    company_method_maes[company_code][method] = float(mae_str)
                except ValueError:
                    pass

    print('Loaded race MAEs for %d companies across %d methods' % (
        len(company_method_maes), len(GATE_METHODS)))
    return company_method_maes


def load_companies():
    """Load all_companies_v4.json."""
    json_path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
    if not os.path.exists(json_path):
        print('ERROR: %s not found.' % json_path)
        sys.exit(1)
    with open(json_path, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    return {c['company_code']: c for c in companies}


def build_features(company_dict, cl, cur):
    """Build feature dict for one company."""
    naics = company_dict.get('naics', '')
    naics4 = naics[:4]
    naics_group = company_dict.get('classifications', {}).get('naics_group', '')
    if not naics_group:
        naics_group = classify_naics_group(naics)

    state_abbr = company_dict.get('state', '')
    region = classify_region(state_abbr)
    urbanicity = company_dict.get('classifications', {}).get('urbanicity', '')
    size_bucket = company_dict.get('classifications', {}).get('size', '')
    zipcode = company_dict.get('zipcode', '')
    county_fips = company_dict.get('county_fips', '')
    state_fips = company_dict.get('state_fips', '')

    if not county_fips:
        county_fips = zip_to_county(cur, zipcode)
    if not state_fips and county_fips:
        state_fips = county_fips[:2]

    # Numeric features
    county_minority_share = cl.get_lodes_pct_minority(county_fips) if county_fips else None

    # LODES-based minority share classification (replaces EEO-1 ground truth)
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

    # ACS-LODES disagreement
    acs_race = cl.get_acs_race(naics4, state_fips) if naics4 and state_fips else None
    lodes_race = cl.get_lodes_race(county_fips) if county_fips else None
    acs_lodes_disagreement = None
    if acs_race and lodes_race:
        acs_white = acs_race.get('White', 0)
        lodes_white = lodes_race.get('White', 0)
        acs_lodes_disagreement = abs(acs_white - lodes_white)

    # Tract data availability
    has_tract_data = False
    if zipcode:
        tract_fips = cl.get_zip_to_best_tract(zipcode)
        if tract_fips:
            tract_race = cl.get_lodes_tract_race(tract_fips)
            has_tract_data = tract_race is not None

    # Boolean features
    is_finance_insurance = 1 if naics_group == 'Finance/Insurance (52)' else 0
    is_admin_staffing = 1 if naics_group == 'Admin/Staffing (56)' else 0
    is_healthcare = 1 if naics_group == 'Healthcare/Social (62)' else 0

    return {
        'naics_group': naics_group,
        'region': region,
        'urbanicity': urbanicity,
        'size_bucket': size_bucket,
        'county_minority_share': county_minority_share,
        'lodes_minority_share': lodes_minority_share,
        'acs_lodes_disagreement': acs_lodes_disagreement,
        'has_tract_data': 1 if has_tract_data else 0,
        'is_finance_insurance': is_finance_insurance,
        'is_admin_staffing': is_admin_staffing,
        'is_healthcare': is_healthcare,
    }


def main():
    print('BUILD GATE TRAINING DATA')
    print('=' * 60)

    # Load V4 results
    company_method_maes = load_v4_detailed()

    # Load company metadata
    companies = load_companies()

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV3(cur)

    # Build training data
    rows = []
    method_wins = defaultdict(int)

    for company_code, method_maes in company_method_maes.items():
        company = companies.get(company_code)
        if not company:
            continue

        # Find best method
        if not method_maes:
            continue
        best_method = min(method_maes.keys(), key=lambda m: method_maes[m])
        method_wins[best_method] += 1

        # Build features
        features = build_features(company, cl, cur)

        row = {
            'company_code': company_code,
            'best_method': best_method,
        }
        # Add per-method MAEs
        for method in GATE_METHODS:
            safe_key = method.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')
            row['mae_%s' % safe_key] = method_maes.get(method, None)

        # Add features
        row.update(features)
        rows.append(row)

    print('Built %d training rows' % len(rows))
    print('')
    print('Best method distribution:')
    for method in GATE_METHODS:
        pct = 100.0 * method_wins[method] / len(rows) if rows else 0
        print('  %-22s  %d (%.1f%%)' % (method, method_wins[method], pct))

    # Write CSV
    output_path = os.path.join(SCRIPT_DIR, 'gate_training_data.csv')
    if rows:
        cols = list(rows[0].keys())
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)
        print('')
        print('Output: %s (%d rows)' % (output_path, len(rows)))

    cl.print_stats()
    conn.close()


if __name__ == '__main__':
    main()
