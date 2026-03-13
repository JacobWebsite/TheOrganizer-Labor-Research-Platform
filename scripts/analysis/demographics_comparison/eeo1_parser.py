"""Parse EEO-1 CSV into ground truth demographic dictionaries.

EEO-1 uses mutually exclusive race/ethnicity categories.
Job category 10 = total row (all job categories combined).

Column mapping for totals (job category 10):
  Total headcount: TOTAL10
  White:    WHF10 + WHM10
  Black:    BLKF10 + BLKM10
  Hispanic: HISPF10 + HISPM10
  Asian:    ASIANF10 + ASIANM10
  AIAN:     AIANF10 + AIANM10
  NHOPI:    NHOPIF10 + NHOPIM10
  Two+:     TOMRF10 + TOMRM10
  Female:   FT10
  Male:     MT10
"""
import csv
import os
from config import EEO1_CSV, EEO1_ALL_CSVS


def _safe_int(val):
    """Convert to int, treating blanks and non-numeric as 0."""
    if val is None or val == '':
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def parse_eeo1_row(row):
    """Parse a single EEO-1 CSV row into a ground truth dict.

    Returns dict with:
      name, company_code, year, naics, state, zipcode, total,
      gender: {Male: pct, Female: pct},
      race: {White: pct, Black: pct, Asian: pct, AIAN: pct, NHOPI: pct, Two+: pct},
      hispanic: {Hispanic: pct, Not Hispanic: pct}
    """
    total = _safe_int(row.get('TOTAL10', 0))
    if total == 0:
        return None

    # Gender
    female = _safe_int(row.get('FT10', 0))
    male = _safe_int(row.get('MT10', 0))
    gender_total = female + male

    # Race (each is mutually exclusive of Hispanic in EEO-1)
    white = _safe_int(row.get('WHF10', 0)) + _safe_int(row.get('WHM10', 0))
    black = _safe_int(row.get('BLKF10', 0)) + _safe_int(row.get('BLKM10', 0))
    asian = _safe_int(row.get('ASIANF10', 0)) + _safe_int(row.get('ASIANM10', 0))
    aian = _safe_int(row.get('AIANF10', 0)) + _safe_int(row.get('AIANM10', 0))
    nhopi = _safe_int(row.get('NHOPIF10', 0)) + _safe_int(row.get('NHOPIM10', 0))
    two_plus = _safe_int(row.get('TOMRF10', 0)) + _safe_int(row.get('TOMRM10', 0))
    hispanic = _safe_int(row.get('HISPF10', 0)) + _safe_int(row.get('HISPM10', 0))

    # Race total = all non-Hispanic race categories
    race_total = white + black + asian + aian + nhopi + two_plus
    # Hispanic total = Hispanic + non-Hispanic race
    hisp_total = hispanic + race_total

    def pct(n, d):
        return round(100.0 * n / d, 2) if d > 0 else 0.0

    return {
        'name': (row.get('CONAME') or row.get('NAME', '')).strip(),
        'company_code': row.get('COMPANY', ''),
        'year': _safe_int(row.get('YEAR', 0)),
        'naics': (row.get('NAICS') or '').strip(),
        'state': (row.get('STATE') or '').strip(),
        'zipcode': (row.get('ZIPCODE') or '').strip(),
        'total': total,
        'gender': {
            'Male': pct(male, gender_total),
            'Female': pct(female, gender_total),
        },
        'race': {
            'White': pct(white, race_total),
            'Black': pct(black, race_total),
            'Asian': pct(asian, race_total),
            'AIAN': pct(aian, race_total),
            'NHOPI': pct(nhopi, race_total),
            'Two+': pct(two_plus, race_total),
        },
        'hispanic': {
            'Hispanic': pct(hispanic, hisp_total),
            'Not Hispanic': pct(race_total, hisp_total),
        },
    }


def load_eeo1_data(csv_path=None):
    """Load all rows from the EEO-1 CSV.

    Returns list of dicts (one per row).
    """
    csv_path = csv_path or EEO1_CSV
    rows = []
    with open(csv_path, 'r', encoding='cp1252') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_all_eeo1_data():
    """Load ALL EEO-1 CSV files (objectors + nonobjectors + supplements).

    Deduplicates by (COMPANY, YEAR) -- keeps first occurrence.
    Returns list of dicts (one per unique company-year).
    """
    seen = set()
    all_rows = []
    for csv_path in EEO1_ALL_CSVS:
        if not os.path.exists(csv_path):
            continue
        count = 0
        dupes = 0
        with open(csv_path, 'r', encoding='cp1252') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get('COMPANY', ''), row.get('YEAR', ''))
                if key in seen:
                    dupes += 1
                    continue
                seen.add(key)
                all_rows.append(row)
                count += 1
        print('  Loaded %s: %d rows (%d dupes skipped)' % (
            os.path.basename(csv_path), count, dupes))
    print('  Total unique company-year rows: %d' % len(all_rows))
    return all_rows


def parse_company(rows, company_code, year=None):
    """Parse ground truth for a specific company code + year.

    If year is None, uses the most recent year available.
    """
    matches = [r for r in rows if r.get('COMPANY') == company_code]
    if year:
        matches = [r for r in matches if _safe_int(r.get('YEAR')) == year]
    if not matches:
        return None
    # Use most recent year
    matches.sort(key=lambda r: _safe_int(r.get('YEAR', 0)), reverse=True)
    return parse_eeo1_row(matches[0])


if __name__ == '__main__':
    # Quick test: parse first few rows
    rows = load_eeo1_data()
    print('Total EEO-1 rows: %d' % len(rows))
    count = 0
    for row in rows[:20]:
        parsed = parse_eeo1_row(row)
        if parsed and parsed['total'] >= 100:
            print('')
            print('  %s (%s, NAICS=%s, N=%d)' % (
                parsed['name'], parsed['state'], parsed['naics'], parsed['total']))
            print('  Gender: M=%.1f%% F=%.1f%%' % (
                parsed['gender']['Male'], parsed['gender']['Female']))
            print('  Race: W=%.1f%% B=%.1f%% A=%.1f%% AIAN=%.1f%% NHOPI=%.1f%% Two+=%.1f%%' % (
                parsed['race']['White'], parsed['race']['Black'],
                parsed['race']['Asian'], parsed['race']['AIAN'],
                parsed['race']['NHOPI'], parsed['race']['Two+']))
            print('  Hispanic: H=%.1f%% NH=%.1f%%' % (
                parsed['hispanic']['Hispanic'], parsed['hispanic']['Not Hispanic']))
            count += 1
            if count >= 5:
                break
