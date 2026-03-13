"""BDS-HC plausibility check.

Reads BDS-HC CSV files for sector x firm-size x demographic dimension,
determines the modal bucket for a company's type, and checks whether
the winning method's estimate falls within that bucket.

BDS-HC bucket structure:
  a) less than 10%
  b) 10% to 25%
  c) 25% to 50%
  d) 50% to 75%
  e) 75% to 90%
  f) greater than 90%
  z) N/A (suppressed)
"""
import csv
import os
from config import BDS_DIR


# Bucket ranges (midpoint and range)
BUCKET_RANGES = {
    'a': (0, 10, 5.0),      # 0-10%, midpoint 5
    'b': (10, 25, 17.5),    # 10-25%, midpoint 17.5
    'c': (25, 50, 37.5),    # 25-50%, midpoint 37.5
    'd': (50, 75, 62.5),    # 50-75%, midpoint 62.5
    'e': (75, 90, 82.5),    # 75-90%, midpoint 82.5
    'f': (90, 100, 95.0),   # 90-100%, midpoint 95
}

BUCKET_LABELS = {
    'a': 'a) <10%',
    'b': 'b) 10-25%',
    'c': 'c) 25-50%',
    'd': 'd) 50-75%',
    'e': 'e) 75-90%',
    'f': 'f) >90%',
}

# NAICS 2-digit -> BDS sector code mapping
# BDS uses 2-digit NAICS as sector codes
NAICS_TO_SECTOR = {str(i): str(i) for i in range(11, 100)}


def _size_bucket(headcount):
    """Map headcount to BDS ifsizecoarse bucket."""
    if headcount < 20:
        return 'a) 1 to 19'
    elif headcount < 500:
        return 'b) 20 to 499'
    else:
        return 'c) 500+'


def _load_bds_file(filename, sector_col='sector', demo_col='im_race'):
    """Load a BDS CSV into a structured dict.

    Returns dict keyed by (sector/state, size_bucket, demo_bucket) -> {firms, emp}
    """
    filepath = os.path.join(BDS_DIR, filename)
    if not os.path.exists(filepath):
        return {}

    data = {}
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row.get('year', 0))
            # Use most recent year available
            if year < 2018:
                continue
            key = (
                row.get(sector_col, '').strip(),
                row.get('ifsizecoarse', '').strip(),
                row.get(demo_col, '').strip(),
            )
            firms_str = row.get('firms', '').strip()
            emp_str = row.get('emp', '').strip()
            try:
                firms = int(firms_str) if firms_str else 0
            except ValueError:
                firms = 0  # Suppressed values (D, S, etc.)
            try:
                emp = int(emp_str) if emp_str else 0
            except ValueError:
                emp = 0
            # Accumulate (may have multiple years)
            if key not in data:
                data[key] = {'firms': 0, 'emp': 0, 'year': year}
            if year >= data[key]['year']:
                data[key] = {'firms': firms, 'emp': emp, 'year': year}
    return data


def get_modal_bucket(data, sector_or_state, size_bucket, demo_buckets='abcdef'):
    """Find the modal (most-employment) bucket for a sector/state + size.

    Returns (bucket_letter, emp_count, total_emp) or (None, 0, 0).
    """
    best_bucket = None
    best_emp = 0
    total_emp = 0

    for bucket in demo_buckets:
        key = (sector_or_state, size_bucket, bucket)
        # Try with and without label format
        for k in [key, (sector_or_state, size_bucket, '%s)' % bucket)]:
            if k in data:
                emp = data[k]['emp']
                total_emp += emp
                if emp > best_emp:
                    best_emp = emp
                    best_bucket = bucket
                break

        # Try with full label
        for label_key in data:
            if (label_key[0] == sector_or_state and
                label_key[1] == size_bucket and
                label_key[2].startswith(bucket + ')')):
                emp = data[label_key]['emp']
                total_emp += emp
                if emp > best_emp:
                    best_emp = emp
                    best_bucket = bucket
                break

    return best_bucket, best_emp, total_emp


def estimate_in_bucket(estimate_pct, bucket_letter):
    """Check if an estimate percentage falls within a BDS bucket's range."""
    if bucket_letter not in BUCKET_RANGES:
        return False
    lo, hi, _ = BUCKET_RANGES[bucket_letter]
    return lo <= estimate_pct <= hi


def check_company(naics, headcount, estimate_minority_pct,
                   estimate_female_pct=None, estimate_hispanic_pct=None):
    """Run BDS-HC plausibility check for one company.

    Returns dict with results per demographic dimension.
    """
    sector = naics[:2]
    size_bucket = _size_bucket(headcount)
    results = {}

    # Race (minority %)
    race_data = _load_bds_file('bds2022_sec_ifzc_im_r.csv', 'sector', 'im_race')
    if race_data:
        modal, modal_emp, total_emp = get_modal_bucket(race_data, sector, size_bucket)
        in_range = estimate_in_bucket(estimate_minority_pct, modal) if modal else None
        results['race'] = {
            'sector': sector,
            'size': size_bucket,
            'estimate_pct': estimate_minority_pct,
            'modal_bucket': BUCKET_LABELS.get(modal, 'N/A') if modal else 'N/A',
            'modal_emp': modal_emp,
            'total_emp': total_emp,
            'in_range': in_range,
        }

    # Sex (female %)
    if estimate_female_pct is not None:
        sex_data = _load_bds_file('bds2022_sec_ifzc_im_sex.csv', 'sector', 'im_sex')
        if sex_data:
            modal, modal_emp, total_emp = get_modal_bucket(sex_data, sector, size_bucket)
            in_range = estimate_in_bucket(estimate_female_pct, modal) if modal else None
            results['sex'] = {
                'sector': sector,
                'size': size_bucket,
                'estimate_pct': estimate_female_pct,
                'modal_bucket': BUCKET_LABELS.get(modal, 'N/A') if modal else 'N/A',
                'in_range': in_range,
            }

    # Hispanic
    if estimate_hispanic_pct is not None:
        hisp_data = _load_bds_file('bds2022_sec_ifzc_im_h.csv', 'sector', 'im_hispanic')
        if hisp_data:
            modal, modal_emp, total_emp = get_modal_bucket(hisp_data, sector, size_bucket)
            in_range = estimate_in_bucket(estimate_hispanic_pct, modal) if modal else None
            results['hispanic'] = {
                'sector': sector,
                'size': size_bucket,
                'estimate_pct': estimate_hispanic_pct,
                'modal_bucket': BUCKET_LABELS.get(modal, 'N/A') if modal else 'N/A',
                'in_range': in_range,
            }

    return results


def check_company_state(naics, state_fips, headcount, estimate_minority_pct):
    """BDS-HC check using state-level file instead of sector-level."""
    size_bucket = _size_bucket(headcount)
    race_data = _load_bds_file('bds2022_st_ifzc_im_r.csv', 'st', 'im_race')
    if not race_data:
        return None

    modal, modal_emp, total_emp = get_modal_bucket(race_data, state_fips, size_bucket)
    in_range = estimate_in_bucket(estimate_minority_pct, modal) if modal else None
    return {
        'state': state_fips,
        'size': size_bucket,
        'estimate_pct': estimate_minority_pct,
        'modal_bucket': BUCKET_LABELS.get(modal, 'N/A') if modal else 'N/A',
        'in_range': in_range,
    }
