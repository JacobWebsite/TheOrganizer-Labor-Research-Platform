"""Build QWI demographic cache from raw Census QWI files.

Processes all 51 state QWI files (rh = race/Hispanic, sa = sex/age) into a single
JSON cache keyed by county_fips x NAICS4, with race, Hispanic, and gender percentages.

Input files:
  QWI/R2026Q1/{state}/qwi_{state}_rh_f_gc_n4_op_u.csv.gz  (race x ethnicity)
  QWI/R2026Q1/{state}/qwi_{state}_sa_f_gc_n4_op_u.csv.gz  (sex x age)

Output:
  scripts/analysis/demographics_comparison/qwi_county_naics4_cache.json

Usage:
    py scripts/analysis/demographics_comparison/build_qwi_cache.py [--year 2024] [--min-emp 10]
"""
import argparse
import csv
import gzip
import json
import os
import time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
QWI_DIR = os.path.join(PROJECT_ROOT, 'QWI', 'R2026Q1')

STATES = [
    'ak', 'al', 'ar', 'az', 'ca', 'co', 'ct', 'dc', 'de', 'fl',
    'ga', 'hi', 'ia', 'id', 'il', 'in', 'ks', 'ky', 'la', 'ma',
    'md', 'me', 'mi', 'mn', 'mo', 'ms', 'mt', 'nc', 'nd', 'ne',
    'nh', 'nj', 'nm', 'nv', 'ny', 'oh', 'ok', 'or', 'pa', 'pr',
    'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'va', 'vt', 'wa', 'wi',
    'wv', 'wy',
]

# QWI race codes -> our race categories
RACE_MAP = {
    'A1': 'White',
    'A2': 'Black',
    'A3': 'AIAN',
    'A4': 'Asian',
    'A5': 'NHOPI',
    'A7': 'Two+',
}

# QWI ethnicity codes
ETH_HISPANIC = 'A2'
ETH_NOT_HISPANIC = 'A1'
ETH_ALL = 'A0'

# QWI sex codes
SEX_ALL = '0'
SEX_MALE = '1'
SEX_FEMALE = '2'


def process_rh_file(state, min_year, cells):
    """Process a race/Hispanic QWI file for one state.

    Extracts race and Hispanic percentages for county x NAICS4 cells.
    Uses the latest available year >= min_year. Averages across quarters.
    Returns the year used (or None if no data).
    """
    fname = 'qwi_%s_rh_f_gc_n4_op_u.csv.gz' % state
    fpath = os.path.join(QWI_DIR, state, fname)
    if not os.path.exists(fpath):
        print('  WARNING: %s not found, skipping' % fname)
        return None

    # First pass: collect all data for years >= min_year, keyed by year
    by_year = defaultdict(lambda: defaultdict(dict))  # year -> (county, naics4, qtr) -> metrics

    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row['year'])
            if year < min_year:
                continue
            if row['sEmp'] != '1' or not row['Emp']:
                continue

            county = row['geography']
            naics4 = row['industry']
            qtr = row['quarter']
            race = row['race']
            eth = row['ethnicity']
            emp = float(row['Emp'])

            qkey = (county, naics4, qtr)

            if race == 'A0' and eth == ETH_ALL:
                by_year[year][qkey]['total'] = emp
            if race in RACE_MAP and eth == ETH_ALL:
                by_year[year][qkey]['race_' + race] = emp
            if race == 'A0' and eth == ETH_HISPANIC:
                by_year[year][qkey]['hispanic'] = emp
            if race == 'A0' and eth == ETH_NOT_HISPANIC:
                by_year[year][qkey]['not_hispanic'] = emp

    if not by_year:
        return None

    # Use the latest year with data
    best_year = max(by_year.keys())
    quarterly = by_year[best_year]

    # Average across quarters for each county x naics4
    by_cell = defaultdict(lambda: defaultdict(list))
    for (county, naics4, qtr), metrics in quarterly.items():
        key = (county, naics4)
        if 'total' in metrics:
            by_cell[key]['total'].append(metrics['total'])
            for rc in RACE_MAP:
                rkey = 'race_' + rc
                if rkey in metrics:
                    by_cell[key][rkey].append(metrics[rkey])
            if 'hispanic' in metrics:
                by_cell[key]['hispanic'].append(metrics['hispanic'])
            if 'not_hispanic' in metrics:
                by_cell[key]['not_hispanic'].append(metrics['not_hispanic'])

    # Convert to percentages
    for (county, naics4), metrics in by_cell.items():
        key = county + ':' + naics4
        avg_total = sum(metrics['total']) / len(metrics['total'])
        if avg_total < 1:
            continue

        if key not in cells:
            cells[key] = {'county': county, 'naics4': naics4, 'emp': round(avg_total, 1)}

        # Race percentages
        race_pcts = {}
        for rc, cat_name in RACE_MAP.items():
            rkey = 'race_' + rc
            if rkey in metrics and metrics[rkey]:
                avg_race = sum(metrics[rkey]) / len(metrics[rkey])
                race_pcts[cat_name] = round(100.0 * avg_race / avg_total, 4)

        if race_pcts:
            total_race = sum(race_pcts.values())
            if total_race > 0:
                for cat in race_pcts:
                    race_pcts[cat] = round(race_pcts[cat] * 100.0 / total_race, 4)
            cells[key]['race'] = race_pcts

        # Hispanic percentages
        if 'hispanic' in metrics and metrics['hispanic']:
            avg_hisp = sum(metrics['hispanic']) / len(metrics['hispanic'])
            hisp_pct = round(100.0 * avg_hisp / avg_total, 4)
            cells[key]['hispanic'] = {
                'Hispanic': hisp_pct,
                'Not Hispanic': round(100.0 - hisp_pct, 4),
            }

    return best_year


def process_sa_file(state, min_year, cells):
    """Process a sex/age QWI file for one state.

    Extracts gender percentages for county x NAICS4 cells.
    Uses age=A00 (all ages) rows only. Uses latest available year >= min_year.
    Returns the year used (or None if no data).
    """
    fname = 'qwi_%s_sa_f_gc_n4_op_u.csv.gz' % state
    fpath = os.path.join(QWI_DIR, state, fname)
    if not os.path.exists(fpath):
        print('  WARNING: %s not found, skipping' % fname)
        return None

    by_year = defaultdict(lambda: defaultdict(dict))

    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row['year'])
            if year < min_year:
                continue
            if row['agegrp'] != 'A00':
                continue
            if row['sEmp'] != '1' or not row['Emp']:
                continue

            county = row['geography']
            naics4 = row['industry']
            qtr = row['quarter']
            sex = row['sex']
            emp = float(row['Emp'])

            qkey = (county, naics4, qtr)

            if sex == SEX_ALL:
                by_year[year][qkey]['total'] = emp
            elif sex == SEX_MALE:
                by_year[year][qkey]['male'] = emp
            elif sex == SEX_FEMALE:
                by_year[year][qkey]['female'] = emp

    if not by_year:
        return None

    best_year = max(by_year.keys())
    quarterly = by_year[best_year]

    # Average across quarters
    by_cell = defaultdict(lambda: defaultdict(list))
    for (county, naics4, qtr), metrics in quarterly.items():
        key = (county, naics4)
        if 'total' in metrics:
            by_cell[key]['total'].append(metrics['total'])
            if 'male' in metrics:
                by_cell[key]['male'].append(metrics['male'])
            if 'female' in metrics:
                by_cell[key]['female'].append(metrics['female'])

    for (county, naics4), metrics in by_cell.items():
        key = county + ':' + naics4
        avg_total = sum(metrics['total']) / len(metrics['total'])
        if avg_total < 1:
            continue

        if key not in cells:
            cells[key] = {'county': county, 'naics4': naics4, 'emp': round(avg_total, 1)}

        if 'female' in metrics and metrics['female']:
            avg_female = sum(metrics['female']) / len(metrics['female'])
            female_pct = round(100.0 * avg_female / avg_total, 4)
            cells[key]['gender'] = {
                'Male': round(100.0 - female_pct, 4),
                'Female': female_pct,
            }

    return best_year


def build_fallback_aggregates(cells, min_emp):
    """Build fallback aggregates for cells with suppressed data.

    Fallback cascade:
      1. county x NAICS4 (primary - already in cells)
      2. county x NAICS2 (aggregate from all NAICS4 in same 2-digit)
      3. county-wide (all industries in county)
      4. state x NAICS4 (aggregate across counties)
      5. state x NAICS2 (broadest)

    Returns separate dicts for each fallback level.
    """
    # county x NAICS2
    county_n2 = defaultdict(lambda: {'race': defaultdict(float), 'hisp': 0, 'not_hisp': 0,
                                      'male': 0, 'female': 0, 'total_race': 0,
                                      'total_hisp': 0, 'total_gender': 0})
    # county-wide
    county_all = defaultdict(lambda: {'race': defaultdict(float), 'hisp': 0, 'not_hisp': 0,
                                       'male': 0, 'female': 0, 'total_race': 0,
                                       'total_hisp': 0, 'total_gender': 0})
    # state x NAICS4
    state_n4 = defaultdict(lambda: {'race': defaultdict(float), 'hisp': 0, 'not_hisp': 0,
                                     'male': 0, 'female': 0, 'total_race': 0,
                                     'total_hisp': 0, 'total_gender': 0})
    # state x NAICS2
    state_n2 = defaultdict(lambda: {'race': defaultdict(float), 'hisp': 0, 'not_hisp': 0,
                                     'male': 0, 'female': 0, 'total_race': 0,
                                     'total_hisp': 0, 'total_gender': 0})

    for key, cell in cells.items():
        county = cell['county']
        naics4 = cell['naics4']
        naics2 = naics4[:2]
        state_fips = county[:2]
        emp = cell.get('emp', 0)

        if emp < min_emp:
            continue

        # Weight by employment
        if 'race' in cell:
            for cat, pct in cell['race'].items():
                val = pct * emp / 100.0
                county_n2[(county, naics2)]['race'][cat] += val
                county_all[county]['race'][cat] += val
                state_n4[(state_fips, naics4)]['race'][cat] += val
                state_n2[(state_fips, naics2)]['race'][cat] += val
            county_n2[(county, naics2)]['total_race'] += emp
            county_all[county]['total_race'] += emp
            state_n4[(state_fips, naics4)]['total_race'] += emp
            state_n2[(state_fips, naics2)]['total_race'] += emp

        if 'hispanic' in cell:
            hisp_val = cell['hispanic']['Hispanic'] * emp / 100.0
            county_n2[(county, naics2)]['hisp'] += hisp_val
            county_all[county]['hisp'] += hisp_val
            state_n4[(state_fips, naics4)]['hisp'] += hisp_val
            state_n2[(state_fips, naics2)]['hisp'] += hisp_val
            county_n2[(county, naics2)]['total_hisp'] += emp
            county_all[county]['total_hisp'] += emp
            state_n4[(state_fips, naics4)]['total_hisp'] += emp
            state_n2[(state_fips, naics2)]['total_hisp'] += emp

        if 'gender' in cell:
            female_val = cell['gender']['Female'] * emp / 100.0
            county_n2[(county, naics2)]['female'] += female_val
            county_all[county]['female'] += female_val
            state_n4[(state_fips, naics4)]['female'] += female_val
            state_n2[(state_fips, naics2)]['female'] += female_val
            county_n2[(county, naics2)]['total_gender'] += emp
            county_all[county]['total_gender'] += emp
            state_n4[(state_fips, naics4)]['total_gender'] += emp
            state_n2[(state_fips, naics2)]['total_gender'] += emp

    def finalize(agg):
        """Convert accumulated counts to percentage dicts."""
        result = {}
        for key, data in agg.items():
            cell = {}
            if data['total_race'] > 0:
                race = {}
                for cat, val in data['race'].items():
                    race[cat] = round(100.0 * val / data['total_race'], 4)
                total_r = sum(race.values())
                if total_r > 0:
                    race = {k: round(v * 100.0 / total_r, 4) for k, v in race.items()}
                cell['race'] = race
            if data['total_hisp'] > 0:
                hisp_pct = round(100.0 * data['hisp'] / data['total_hisp'], 4)
                cell['hispanic'] = {'Hispanic': hisp_pct, 'Not Hispanic': round(100 - hisp_pct, 4)}
            if data['total_gender'] > 0:
                fem_pct = round(100.0 * data['female'] / data['total_gender'], 4)
                cell['gender'] = {'Male': round(100 - fem_pct, 4), 'Female': fem_pct}
            if cell:
                str_key = ':'.join(str(k) for k in key) if isinstance(key, tuple) else str(key)
                result[str_key] = cell
        return result

    return {
        'county_n2': finalize(county_n2),
        'county_all': finalize(county_all),
        'state_n4': finalize(state_n4),
        'state_n2': finalize(state_n2),
    }


def main():
    parser = argparse.ArgumentParser(description='Build QWI demographic cache')
    parser.add_argument('--min-year', type=int, default=2016,
                        help='Earliest year to consider (default: 2016). Uses latest available per state.')
    parser.add_argument('--min-emp', type=int, default=10, help='Min employment for inclusion (default: 10)')
    parser.add_argument('--states', nargs='*', help='Process only these states (default: all)')
    args = parser.parse_args()

    min_year = args.min_year
    min_emp = args.min_emp
    states = args.states or STATES

    print('Building QWI demographic cache')
    print('  Min year: %d (uses latest available per state)' % min_year)
    print('  Min employment: %d' % min_emp)
    print('  States: %d' % len(states))
    print()

    t0 = time.time()
    cells = {}
    state_years = {}

    for i, state in enumerate(states):
        t1 = time.time()
        print('[%d/%d] Processing %s...' % (i + 1, len(states), state.upper()), end='', flush=True)

        rh_year = process_rh_file(state, min_year, cells)
        sa_year = process_sa_file(state, min_year, cells)
        state_years[state.upper()] = {'rh': rh_year, 'sa': sa_year}

        yr_str = 'rh=%s sa=%s' % (rh_year or 'NONE', sa_year or 'NONE')
        print(' %.1fs (%s, cells: %d)' % (time.time() - t1, yr_str, len(cells)))

    print('\nTotal primary cells: %d' % len(cells))

    # Filter by min employment
    filtered = {k: v for k, v in cells.items() if v.get('emp', 0) >= min_emp}
    print('Cells with emp >= %d: %d' % (min_emp, len(filtered)))

    # Count coverage
    has_race = sum(1 for v in filtered.values() if 'race' in v)
    has_hisp = sum(1 for v in filtered.values() if 'hispanic' in v)
    has_gender = sum(1 for v in filtered.values() if 'gender' in v)
    has_all = sum(1 for v in filtered.values() if 'race' in v and 'hispanic' in v and 'gender' in v)
    print('Coverage: race=%d (%.1f%%) hispanic=%d (%.1f%%) gender=%d (%.1f%%) all_three=%d (%.1f%%)' % (
        has_race, 100 * has_race / len(filtered) if filtered else 0,
        has_hisp, 100 * has_hisp / len(filtered) if filtered else 0,
        has_gender, 100 * has_gender / len(filtered) if filtered else 0,
        has_all, 100 * has_all / len(filtered) if filtered else 0,
    ))

    # Build fallback aggregates
    print('\nBuilding fallback aggregates...')
    fallbacks = build_fallback_aggregates(filtered, min_emp)
    for level, data in fallbacks.items():
        print('  %s: %d cells' % (level, len(data)))

    # Print state year summary
    print('\nState year coverage:')
    for st in sorted(state_years.keys()):
        yrs = state_years[st]
        print('  %s: rh=%s sa=%s' % (st, yrs['rh'] or 'NONE', yrs['sa'] or 'NONE'))

    # Save
    output = {
        'metadata': {
            'min_year': min_year,
            'min_emp': min_emp,
            'n_states': len(states),
            'n_primary_cells': len(filtered),
            'state_years': state_years,
            'coverage': {
                'race': has_race,
                'hispanic': has_hisp,
                'gender': has_gender,
                'all_three': has_all,
            },
            'build_time_sec': round(time.time() - t0, 1),
        },
        'primary': filtered,
        'fallbacks': fallbacks,
    }

    out_path = os.path.join(SCRIPT_DIR, 'qwi_county_naics4_cache.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print('\nSaved to %s (%.1f MB)' % (out_path, size_mb))
    print('Total time: %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
