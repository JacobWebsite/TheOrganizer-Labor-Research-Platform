"""Build QWI demographic cache -- optimized version.

Uses csv.reader (not DictReader) for 3x speed. Processes rh and sa files
for all 51 states, auto-detects latest year per state.

Usage:
    py scripts/analysis/demographics_comparison/build_qwi_cache_fast.py
"""
import csv
import gzip
import json
import os
import sys
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

# QWI race codes -> our categories
RACE_CODES = {'A1': 'White', 'A2': 'Black', 'A3': 'AIAN', 'A4': 'Asian', 'A5': 'NHOPI', 'A7': 'Two+'}
MIN_EMP = 10


def find_col_indices(header):
    """Build column index map from header row."""
    idx = {}
    for i, col in enumerate(header):
        idx[col] = i
    return idx


def process_rh_state(state):
    """Process race/Hispanic file for one state. Returns (cells_dict, year_used)."""
    fname = 'qwi_%s_rh_f_gc_n4_op_u.csv.gz' % state
    fpath = os.path.join(QWI_DIR, state, fname)
    if not os.path.exists(fpath):
        return {}, None

    # Accumulate data: key=(county, naics4, year, qtr) -> {total, race_A1..A7, hispanic}
    data = {}
    years_seen = set()

    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        ci = find_col_indices(header)

        i_geo = ci['geography']
        i_ind = ci['industry']
        i_year = ci['year']
        i_qtr = ci['quarter']
        i_race = ci['race']
        i_eth = ci['ethnicity']
        i_emp = ci['Emp']
        i_semp = ci['sEmp']

        for row in reader:
            year = int(row[i_year])
            if year < 2016:
                continue

            semp = row[i_semp]
            emp_str = row[i_emp]
            if semp != '1' or not emp_str:
                continue

            years_seen.add(year)
            county = row[i_geo]
            naics4 = row[i_ind]
            qtr = row[i_qtr]
            race = row[i_race]
            eth = row[i_eth]
            emp = float(emp_str)

            key = (county, naics4, year, qtr)

            if key not in data:
                data[key] = {}

            if race == 'A0' and eth == 'A0':
                data[key]['total'] = emp
            if race in RACE_CODES and eth == 'A0':
                data[key]['r_' + race] = emp
            if race == 'A0' and eth == 'A2':
                data[key]['hispanic'] = emp

    if not years_seen:
        return {}, None

    best_year = max(years_seen)

    # Average across quarters for best_year
    by_cell = defaultdict(lambda: defaultdict(list))
    for (county, naics4, year, qtr), metrics in data.items():
        if year != best_year:
            continue
        if 'total' not in metrics:
            continue
        key = county + ':' + naics4
        by_cell[key]['total'].append(metrics['total'])
        by_cell[key]['county'] = county
        by_cell[key]['naics4'] = naics4
        for rc in RACE_CODES:
            rk = 'r_' + rc
            if rk in metrics:
                by_cell[key][rk].append(metrics[rk])
        if 'hispanic' in metrics:
            by_cell[key]['hispanic'].append(metrics['hispanic'])

    cells = {}
    for key, metrics in by_cell.items():
        avg_total = sum(metrics['total']) / len(metrics['total'])
        if avg_total < 1:
            continue

        cell = {
            'county': metrics['county'],
            'naics4': metrics['naics4'],
            'emp': round(avg_total, 1),
        }

        # Race percentages
        race_pcts = {}
        for rc, cat in RACE_CODES.items():
            rk = 'r_' + rc
            if rk in metrics and metrics[rk]:
                avg = sum(metrics[rk]) / len(metrics[rk])
                race_pcts[cat] = round(100.0 * avg / avg_total, 4)
        if race_pcts:
            total_r = sum(race_pcts.values())
            if total_r > 0:
                race_pcts = {k: round(v * 100.0 / total_r, 4) for k, v in race_pcts.items()}
            cell['race'] = race_pcts

        # Hispanic
        if 'hispanic' in metrics and metrics['hispanic']:
            avg_h = sum(metrics['hispanic']) / len(metrics['hispanic'])
            h_pct = round(100.0 * avg_h / avg_total, 4)
            cell['hispanic'] = {'Hispanic': h_pct, 'Not Hispanic': round(100 - h_pct, 4)}

        cells[key] = cell

    # Free memory
    del data, by_cell

    return cells, best_year


def process_sa_state(state, cells):
    """Process sex/age file for one state. Adds gender to existing cells dict.
    Returns year_used."""
    fname = 'qwi_%s_sa_f_gc_n4_op_u.csv.gz' % state
    fpath = os.path.join(QWI_DIR, state, fname)
    if not os.path.exists(fpath):
        return None

    data = {}
    years_seen = set()

    with gzip.open(fpath, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        ci = find_col_indices(header)

        i_geo = ci['geography']
        i_ind = ci['industry']
        i_year = ci['year']
        i_qtr = ci['quarter']
        i_sex = ci['sex']
        i_age = ci['agegrp']
        i_emp = ci['Emp']
        i_semp = ci['sEmp']

        for row in reader:
            year = int(row[i_year])
            if year < 2016:
                continue
            if row[i_age] != 'A00':  # all ages only
                continue
            semp = row[i_semp]
            emp_str = row[i_emp]
            if semp != '1' or not emp_str:
                continue

            years_seen.add(year)
            county = row[i_geo]
            naics4 = row[i_ind]
            qtr = row[i_qtr]
            sex = row[i_sex]
            emp = float(emp_str)

            key = (county, naics4, year, qtr)
            if key not in data:
                data[key] = {}

            if sex == '0':
                data[key]['total'] = emp
            elif sex == '2':
                data[key]['female'] = emp

    if not years_seen:
        return None

    best_year = max(years_seen)

    # Average across quarters
    by_cell = defaultdict(lambda: defaultdict(list))
    for (county, naics4, year, qtr), metrics in data.items():
        if year != best_year:
            continue
        if 'total' not in metrics:
            continue
        key = county + ':' + naics4
        by_cell[key]['total'].append(metrics['total'])
        by_cell[key]['county'] = county
        by_cell[key]['naics4'] = naics4
        if 'female' in metrics:
            by_cell[key]['female'].append(metrics['female'])

    for key, metrics in by_cell.items():
        avg_total = sum(metrics['total']) / len(metrics['total'])
        if avg_total < 1:
            continue

        if 'female' in metrics and metrics['female']:
            avg_f = sum(metrics['female']) / len(metrics['female'])
            f_pct = round(100.0 * avg_f / avg_total, 4)
            gender = {'Male': round(100 - f_pct, 4), 'Female': f_pct}

            if key in cells:
                cells[key]['gender'] = gender
            else:
                cells[key] = {
                    'county': metrics['county'],
                    'naics4': metrics['naics4'],
                    'emp': round(avg_total, 1),
                    'gender': gender,
                }

    del data, by_cell
    return best_year


def build_fallbacks(cells):
    """Build fallback aggregates: county_n2, county_all, state_n4, state_n2."""
    accum = {
        'county_n2': defaultdict(lambda: defaultdict(float)),
        'county_all': defaultdict(lambda: defaultdict(float)),
        'state_n4': defaultdict(lambda: defaultdict(float)),
        'state_n2': defaultdict(lambda: defaultdict(float)),
    }

    for key, cell in cells.items():
        county = cell['county']
        naics4 = cell['naics4']
        naics2 = naics4[:2]
        state_fips = county[:2]
        emp = cell.get('emp', 0)
        if emp < MIN_EMP:
            continue

        levels = {
            'county_n2': county + ':' + naics2,
            'county_all': county,
            'state_n4': state_fips + ':' + naics4,
            'state_n2': state_fips + ':' + naics2,
        }

        for level_name, lkey in levels.items():
            a = accum[level_name][lkey]
            if 'race' in cell:
                for cat, pct in cell['race'].items():
                    a['r_' + cat] += pct * emp / 100.0
                a['t_race'] += emp
            if 'hispanic' in cell:
                a['hisp'] += cell['hispanic']['Hispanic'] * emp / 100.0
                a['t_hisp'] += emp
            if 'gender' in cell:
                a['fem'] += cell['gender']['Female'] * emp / 100.0
                a['t_gender'] += emp

    result = {}
    for level_name, level_data in accum.items():
        level_result = {}
        for lkey, a in level_data.items():
            cell = {}
            if a['t_race'] > 0:
                race = {}
                for cat in ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']:
                    val = a.get('r_' + cat, 0)
                    if val > 0:
                        race[cat] = round(100.0 * val / a['t_race'], 4)
                total_r = sum(race.values())
                if total_r > 0:
                    race = {k: round(v * 100.0 / total_r, 4) for k, v in race.items()}
                cell['race'] = race
            if a['t_hisp'] > 0:
                hp = round(100.0 * a['hisp'] / a['t_hisp'], 4)
                cell['hispanic'] = {'Hispanic': hp, 'Not Hispanic': round(100 - hp, 4)}
            if a['t_gender'] > 0:
                fp = round(100.0 * a['fem'] / a['t_gender'], 4)
                cell['gender'] = {'Male': round(100 - fp, 4), 'Female': fp}
            if cell:
                level_result[lkey] = cell
        result[level_name] = level_result
    return result


def main():
    print('Building QWI demographic cache (fast version)')
    print('=' * 60)
    t0 = time.time()

    all_cells = {}
    state_years = {}

    for i, state in enumerate(STATES):
        t1 = time.time()
        sys.stdout.write('[%d/%d] %s...' % (i + 1, len(STATES), state.upper()))
        sys.stdout.flush()

        state_cells, rh_year = process_rh_state(state)
        sa_year = process_sa_state(state, state_cells)

        all_cells.update(state_cells)
        state_years[state.upper()] = {'rh': rh_year, 'sa': sa_year}

        elapsed = time.time() - t1
        print(' %.0fs (rh=%s sa=%s, +%d cells, total=%d)' % (
            elapsed, rh_year or 'NONE', sa_year or 'NONE',
            len(state_cells), len(all_cells)))

    # Filter
    filtered = {k: v for k, v in all_cells.items() if v.get('emp', 0) >= MIN_EMP}

    has_race = sum(1 for v in filtered.values() if 'race' in v)
    has_hisp = sum(1 for v in filtered.values() if 'hispanic' in v)
    has_gender = sum(1 for v in filtered.values() if 'gender' in v)
    has_all = sum(1 for v in filtered.values() if 'race' in v and 'hispanic' in v and 'gender' in v)

    print('\nTotal cells: %d (emp >= %d: %d)' % (len(all_cells), MIN_EMP, len(filtered)))
    print('Coverage: race=%d hisp=%d gender=%d all=%d' % (has_race, has_hisp, has_gender, has_all))

    # Fallbacks
    print('\nBuilding fallbacks...')
    fallbacks = build_fallbacks(filtered)
    for level, data in fallbacks.items():
        print('  %s: %d' % (level, len(data)))

    # State years summary
    print('\nState years:')
    for st in sorted(state_years.keys()):
        y = state_years[st]
        print('  %s: rh=%s sa=%s' % (st, y['rh'] or 'NONE', y['sa'] or 'NONE'))

    # Save
    output = {
        'metadata': {
            'min_year': 2016,
            'min_emp': MIN_EMP,
            'n_states': len(STATES),
            'n_primary_cells': len(filtered),
            'state_years': state_years,
            'coverage': {'race': has_race, 'hispanic': has_hisp,
                         'gender': has_gender, 'all_three': has_all},
            'build_time_sec': round(time.time() - t0, 1),
        },
        'primary': filtered,
        'fallbacks': fallbacks,
    }

    out_path = os.path.join(SCRIPT_DIR, 'qwi_county_naics4_cache.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print('\nSaved: %s (%.1f MB)' % (out_path, size_mb))
    print('Total: %.0fs (%.1f min)' % (time.time() - t0, (time.time() - t0) / 60))


if __name__ == '__main__':
    main()
