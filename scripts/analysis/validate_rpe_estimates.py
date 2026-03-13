"""
Dual RPE Validation: NLRB Elections + 990 Self-Reported.

Runs two independent ground truths side by side to cross-validate whether
geographic RPE (state/county) improves workforce size estimates over national.

Ground Truth A: NLRB whole-company elections (~200-900 cases)
  - eligible_voters * supervisor_multiplier = actual employees
  - Filtered to small single-location employers where BU ~ whole workforce

Ground Truth B: 990 self-reported employees (~7,500 cases)
  - 990 filers report both revenue and total_employees directly

Usage:
  py scripts/analysis/validate_rpe_estimates.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ---------------------------------------------------------------------------
# Shared utilities (kept from original)
# ---------------------------------------------------------------------------

def get_rpe_estimate(rpe_lookup, naics, state=None, county_fips=None,
                     geo_level='national'):
    """Find best RPE match for a NAICS code at the specified geo level.

    Returns (rpe_value, matched_naics_length) or (None, None).
    """
    if not naics:
        return None, None

    naics = naics.strip()

    for length in range(len(naics), 1, -1):
        prefix = naics[:length]
        if geo_level == 'county' and county_fips:
            key = ('county', county_fips, prefix)
        elif geo_level == 'state' and state:
            key = ('state', state, prefix)
        else:
            key = ('national', '', prefix)
        if key in rpe_lookup:
            return rpe_lookup[key], length

    return None, None


def compute_metrics(estimates):
    """Compute accuracy metrics for a list of (estimated, actual) pairs."""
    if not estimates:
        return {}

    n = len(estimates)
    ratios = []
    abs_errors = []
    within_25 = 0
    within_50 = 0
    within_3x = 0

    for est, actual in estimates:
        ratio = est / actual
        ratios.append(ratio)
        abs_error = abs(est - actual) / actual
        abs_errors.append(abs_error)

        if 0.75 <= ratio <= 1.333:
            within_25 += 1
        if 0.5 <= ratio <= 2.0:
            within_50 += 1
        if 0.333 <= ratio <= 3.0:
            within_3x += 1

    abs_errors.sort()
    ratios.sort()
    median_err = abs_errors[len(abs_errors) // 2] * 100
    median_ratio = ratios[len(ratios) // 2]

    return {
        'n': n,
        'median_err': median_err,
        'median_ratio': median_ratio,
        'within_25_pct': within_25 / n * 100,
        'within_50_pct': within_50 / n * 100,
        'within_3x_pct': within_3x / n * 100,
    }


def format_row(label, m):
    """Format a metrics row for the comparison table."""
    if not m:
        return (f"{label:10s}  {'n/a':>6s}  {'n/a':>8s}  "
                f"{'n/a':>9s}  {'n/a':>9s}  {'n/a':>9s}")
    return (f"{label:10s}  {m['n']:>6,}  {m['median_err']:>7.1f}%  "
            f"{m['within_25_pct']:>8.1f}%  {m['within_50_pct']:>8.1f}%  "
            f"{m['within_3x_pct']:>8.1f}%")


# ---------------------------------------------------------------------------
# Data loading functions
# ---------------------------------------------------------------------------

def load_rpe_lookup(cur):
    """Load RPE ratios from census_rpe_ratios into a lookup dict."""
    cur.execute("""
        SELECT COALESCE(geo_level, 'national') AS gl,
               COALESCE(state, '') AS st,
               COALESCE(county_fips, '') AS cf,
               naics_code, rpe
        FROM census_rpe_ratios
        WHERE rpe > 0
    """)
    rpe_lookup = {}
    for gl, st, cf, naics_code, rpe in cur.fetchall():
        if gl == 'county' and cf:
            key = ('county', cf, naics_code)
        elif gl == 'state' and st:
            key = ('state', st, naics_code)
        else:
            key = ('national', '', naics_code)
        rpe_lookup[key] = float(rpe)
    return rpe_lookup


def load_zip_county_crosswalk(cur):
    """Load ZIP -> county FIPS mapping."""
    cur.execute("SELECT zip_code, county_fips FROM zip_county_crosswalk")
    return {r[0]: r[1] for r in cur.fetchall()}


def build_supervisor_ratio_lookup(cur):
    """Build NAICS prefix -> supervisor multiplier from BLS occupation matrix.

    Management = SOC 11-xxxx
    First-line supervisors = occupation_title ILIKE '%first-line supervisor%'
    multiplier = 1 / (1 - supervisor_pct)

    BLS industry_code is 6-digit (e.g. '622000'). Strip trailing zeros to get
    NAICS prefix. Skip composite codes with hyphens or letters.
    """
    cur.execute("""
        SELECT industry_code,
               SUM(employment_2024) AS total_emp,
               SUM(CASE WHEN occupation_code LIKE '11-%%'
                        THEN employment_2024 ELSE 0 END) AS mgmt_emp,
               SUM(CASE WHEN occupation_title ILIKE '%%first-line supervisor%%'
                        THEN employment_2024 ELSE 0 END) AS sup_emp
        FROM bls_industry_occupation_matrix
        WHERE employment_2024 > 0
        GROUP BY industry_code
        HAVING SUM(employment_2024) > 0
    """)

    lookup = {}  # naics_prefix -> multiplier
    for industry_code, total_emp, mgmt_emp, sup_emp in cur.fetchall():
        # Skip composite codes (contain hyphens or letters)
        if re.search(r'[A-Za-z\-]', industry_code):
            continue

        total_emp = float(total_emp)
        mgmt_emp = float(mgmt_emp)
        sup_emp = float(sup_emp)

        if total_emp <= 0:
            continue

        supervisor_pct = (mgmt_emp + sup_emp) / total_emp
        # Cap at reasonable range to avoid extreme multipliers
        supervisor_pct = min(supervisor_pct, 0.40)
        multiplier = 1.0 / (1.0 - supervisor_pct)

        # Strip trailing zeros to get NAICS prefix
        naics_prefix = industry_code.rstrip('0')
        if naics_prefix:
            lookup[naics_prefix] = multiplier

    return lookup


def get_supervisor_multiplier(naics, lookup):
    """Cascade lookup for supervisor multiplier, default 1.15."""
    if not naics:
        return 1.15

    naics = naics.strip()
    # Try progressively shorter prefixes
    for length in range(len(naics), 0, -1):
        prefix = naics[:length]
        if prefix in lookup:
            return lookup[prefix]

    return 1.15


# ---------------------------------------------------------------------------
# Ground truth queries
# ---------------------------------------------------------------------------

def fetch_ground_truth_a(cur):
    """Fetch NLRB election records linked to 990 filers.

    Returns rows of (case_number, eligible_voters, state, naics,
                     latest_unit_size, zip, total_revenue, total_employees_990).
    """
    cur.execute("""
        SELECT DISTINCT ON (ne.case_number)
            ne.case_number, ne.eligible_voters,
            f7.state, f7.naics, f7.latest_unit_size, f7.zip,
            n9.total_revenue, n9.total_employees
        FROM nlrb_elections ne
        JOIN nlrb_participants np ON np.case_number = ne.case_number
            AND np.participant_type = 'Employer'
            AND np.matched_employer_id IS NOT NULL
        JOIN f7_employers_deduped f7 ON f7.employer_id = np.matched_employer_id
        JOIN national_990_f7_matches nm ON nm.f7_employer_id = f7.employer_id
        JOIN national_990_filers n9 ON n9.id = nm.n990_id
        WHERE ne.eligible_voters > 0 AND n9.total_revenue > 0
          AND f7.naics IS NOT NULL AND LENGTH(TRIM(f7.naics)) >= 2
          AND f7.state IS NOT NULL
        ORDER BY ne.case_number, nm.match_confidence DESC NULLS LAST
    """)
    return cur.fetchall()


def fetch_ground_truth_b(cur):
    """Fetch 990 self-reported employees, DISTINCT ON ein.

    Returns rows of (ein, total_revenue, total_employees, state, naics, zip).
    """
    cur.execute("""
        SELECT DISTINCT ON (nm.ein)
            nm.ein, n9.total_revenue, n9.total_employees,
            f7.state, f7.naics, f7.zip
        FROM national_990_f7_matches nm
        JOIN national_990_filers n9 ON n9.id = nm.n990_id
        JOIN f7_employers_deduped f7 ON f7.employer_id = nm.f7_employer_id
        WHERE n9.total_revenue > 0
          AND n9.total_employees > 0
          AND f7.naics IS NOT NULL AND LENGTH(TRIM(f7.naics)) >= 2
          AND f7.state IS NOT NULL
        ORDER BY nm.ein, nm.match_confidence DESC NULLS LAST
    """)
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------

def run_validation(records, rpe_lookup, zip_to_county):
    """Run RPE validation on a list of records.

    Each record must be a dict with keys:
      revenue, actual_emp, naics, state, zip

    Returns dict with keys: national, state, county (each a metrics dict),
    plus breakdowns: by_size, by_naics2, by_match_depth.
    """
    results = {
        'national': [], 'state': [], 'county': [],
        'by_size': {
            '<25': {'nat': [], 'st': [], 'co': []},
            '25-100': {'nat': [], 'st': [], 'co': []},
            '100-500': {'nat': [], 'st': [], 'co': []},
            '500+': {'nat': [], 'st': [], 'co': []},
        },
        'by_naics2': {},
        'by_match_depth': {'nat': {}, 'st': {}, 'co': {}},
    }

    for rec in records:
        revenue = rec['revenue']
        actual_emp = rec['actual_emp']
        naics = rec['naics']
        state = rec['state']
        zipcode = rec.get('zip')

        if actual_emp <= 0 or revenue <= 0:
            continue

        # County FIPS from ZIP
        county_fips = None
        if zipcode:
            clean_zip = str(zipcode).strip()[:5]
            county_fips = zip_to_county.get(clean_zip)

        # Size bucket
        if actual_emp < 25:
            size_bucket = '<25'
        elif actual_emp < 100:
            size_bucket = '25-100'
        elif actual_emp < 500:
            size_bucket = '100-500'
        else:
            size_bucket = '500+'

        naics_2 = naics[:2] if naics else '??'
        if naics_2 not in results['by_naics2']:
            results['by_naics2'][naics_2] = {'nat': [], 'st': [], 'co': []}

        # National
        rpe_val, match_len = get_rpe_estimate(rpe_lookup, naics,
                                               geo_level='national')
        if rpe_val and rpe_val > 0:
            est = revenue / rpe_val
            pair = (est, actual_emp)
            results['national'].append(pair)
            results['by_size'][size_bucket]['nat'].append(pair)
            results['by_naics2'][naics_2]['nat'].append(pair)
            ml = match_len or 0
            results['by_match_depth']['nat'].setdefault(ml, []).append(pair)

        # State
        rpe_val, match_len = get_rpe_estimate(rpe_lookup, naics, state=state,
                                               geo_level='state')
        if rpe_val and rpe_val > 0:
            est = revenue / rpe_val
            pair = (est, actual_emp)
            results['state'].append(pair)
            results['by_size'][size_bucket]['st'].append(pair)
            results['by_naics2'][naics_2]['st'].append(pair)
            ml = match_len or 0
            results['by_match_depth']['st'].setdefault(ml, []).append(pair)

        # County
        if county_fips:
            rpe_val, match_len = get_rpe_estimate(rpe_lookup, naics,
                                                   county_fips=county_fips,
                                                   geo_level='county')
            if rpe_val and rpe_val > 0:
                est = revenue / rpe_val
                pair = (est, actual_emp)
                results['county'].append(pair)
                results['by_size'][size_bucket]['co'].append(pair)
                results['by_naics2'][naics_2]['co'].append(pair)
                ml = match_len or 0
                results['by_match_depth']['co'].setdefault(ml, []).append(pair)

    # Compute metrics
    return {
        'nat_m': compute_metrics(results['national']),
        'st_m': compute_metrics(results['state']),
        'co_m': compute_metrics(results['county']),
        'by_size': results['by_size'],
        'by_naics2': results['by_naics2'],
        'by_match_depth': results['by_match_depth'],
    }


def print_validation_results(label, result):
    """Print formatted validation results for one ground truth."""
    nat_m = result['nat_m']
    st_m = result['st_m']
    co_m = result['co_m']

    print()
    print("=" * 70)
    print(f"=== {label} ===")
    print("=" * 70)
    header = (f"{'Level':10s}  {'n':>6s}  {'Med.Err':>8s}  "
              f"{'Within25%':>9s}  {'Within50%':>9s}  {'Within3x':>9s}")
    print(header)
    print("-" * 70)
    print(format_row("National", nat_m))
    print(format_row("State", st_m))
    print(format_row("County", co_m))

    # Size breakdown
    print()
    print("--- By Employer Size ---")
    print(f"{'Size':10s}  {'Level':8s}  {'n':>6s}  {'Med.Err':>8s}  "
          f"{'W50%':>7s}  {'W3x':>7s}")
    print("-" * 58)
    for bucket in ['<25', '25-100', '100-500', '500+']:
        for level, key in [('National', 'nat'), ('State', 'st'),
                           ('County', 'co')]:
            m = compute_metrics(result['by_size'][bucket][key])
            if m:
                print(f"{bucket:10s}  {level:8s}  {m['n']:>6,}  "
                      f"{m['median_err']:>7.1f}%  {m['within_50_pct']:>6.1f}%  "
                      f"{m['within_3x_pct']:>6.1f}%")

    # Sector breakdown (top 10)
    print()
    print("--- By Sector (2-digit NAICS, top 10) ---")
    by_n2 = result['by_naics2']
    sector_counts = [(n2, len(v['nat'])) for n2, v in by_n2.items()
                     if len(v['nat']) >= 10]
    sector_counts.sort(key=lambda x: -x[1])
    print(f"{'NAICS':6s}  {'Level':8s}  {'n':>6s}  {'Med.Err':>8s}  "
          f"{'W50%':>7s}  {'W3x':>7s}")
    print("-" * 55)
    for naics_2, _ in sector_counts[:10]:
        for level, key in [('National', 'nat'), ('State', 'st'),
                           ('County', 'co')]:
            m = compute_metrics(by_n2[naics_2][key])
            if m and m['n'] >= 5:
                print(f"{naics_2:6s}  {level:8s}  {m['n']:>6,}  "
                      f"{m['median_err']:>7.1f}%  {m['within_50_pct']:>6.1f}%  "
                      f"{m['within_3x_pct']:>6.1f}%")

    # Match depth breakdown
    print()
    print("--- By NAICS Match Depth ---")
    print(f"{'Depth':6s}  {'Level':8s}  {'n':>6s}  {'Med.Err':>8s}  "
          f"{'W50%':>7s}  {'W3x':>7s}")
    print("-" * 55)
    bd = result['by_match_depth']
    all_depths = sorted(set(list(bd['nat'].keys()) + list(bd['st'].keys())
                            + list(bd['co'].keys())))
    for depth in all_depths:
        for level, key in [('National', 'nat'), ('State', 'st'),
                           ('County', 'co')]:
            ests = bd[key].get(depth, [])
            m = compute_metrics(ests)
            if m and m['n'] >= 5:
                print(f"{depth:>4d}d   {level:8s}  {m['n']:>6,}  "
                      f"{m['median_err']:>7.1f}%  {m['within_50_pct']:>6.1f}%  "
                      f"{m['within_3x_pct']:>6.1f}%")


def print_cross_summary(result_a, result_b):
    """Print side-by-side cross-validation summary."""
    print()
    print("=" * 70)
    print("=== CROSS-VALIDATION SUMMARY ===")
    print("=" * 70)

    def delta_str(geo_m, nat_m, key):
        if not geo_m or not nat_m:
            return 'n/a'
        d = geo_m[key] - nat_m[key]
        sign = '+' if d >= 0 else ''
        return f"{sign}{d:.1f}pp"

    print(f"{'Metric':25s}  {'GT-A (NLRB)':>14s}  {'GT-B (990)':>14s}")
    print("-" * 58)

    # State improvement (Within50%)
    a_st = delta_str(result_a['st_m'], result_a['nat_m'], 'within_50_pct')
    b_st = delta_str(result_b['st_m'], result_b['nat_m'], 'within_50_pct')
    print(f"{'State W50% vs National':25s}  {a_st:>14s}  {b_st:>14s}")

    # County improvement (Within50%)
    a_co = delta_str(result_a['co_m'], result_a['nat_m'], 'within_50_pct')
    b_co = delta_str(result_b['co_m'], result_b['nat_m'], 'within_50_pct')
    print(f"{'County W50% vs National':25s}  {a_co:>14s}  {b_co:>14s}")

    # State improvement (Median Error)
    a_st_e = delta_str(result_a['st_m'], result_a['nat_m'], 'median_err')
    b_st_e = delta_str(result_b['st_m'], result_b['nat_m'], 'median_err')
    print(f"{'State Med.Err vs National':25s}  {a_st_e:>14s}  {b_st_e:>14s}")

    # County improvement (Median Error)
    a_co_e = delta_str(result_a['co_m'], result_a['nat_m'], 'median_err')
    b_co_e = delta_str(result_b['co_m'], result_b['nat_m'], 'median_err')
    print(f"{'County Med.Err vs National':25s}  {a_co_e:>14s}  {b_co_e:>14s}")

    # Sample sizes
    a_n = result_a['nat_m'].get('n', 0) if result_a['nat_m'] else 0
    b_n = result_b['nat_m'].get('n', 0) if result_b['nat_m'] else 0
    print(f"{'Sample size (national)':25s}  {a_n:>14,}  {b_n:>14,}")

    # Directional agreement
    a_st_val = (result_a['st_m'] or {}).get('within_50_pct', 0) - \
               (result_a['nat_m'] or {}).get('within_50_pct', 0)
    b_st_val = (result_b['st_m'] or {}).get('within_50_pct', 0) - \
               (result_b['nat_m'] or {}).get('within_50_pct', 0)
    a_co_val = (result_a['co_m'] or {}).get('within_50_pct', 0) - \
               (result_a['nat_m'] or {}).get('within_50_pct', 0)
    b_co_val = (result_b['co_m'] or {}).get('within_50_pct', 0) - \
               (result_b['nat_m'] or {}).get('within_50_pct', 0)

    state_agree = (a_st_val > 0) == (b_st_val > 0)
    county_agree = (a_co_val > 0) == (b_co_val > 0)
    print()
    print(f"State direction agreement:  {'YES' if state_agree else 'NO'} "
          f"(both {'positive' if a_st_val > 0 else 'negative'})"
          if state_agree else
          f"State direction agreement:  NO "
          f"(GT-A {'positive' if a_st_val > 0 else 'negative'}, "
          f"GT-B {'positive' if b_st_val > 0 else 'negative'})")
    print(f"County direction agreement: {'YES' if county_agree else 'NO'} "
          f"(both {'positive' if a_co_val > 0 else 'negative'})"
          if county_agree else
          f"County direction agreement: NO "
          f"(GT-A {'positive' if a_co_val > 0 else 'negative'}, "
          f"GT-B {'positive' if b_co_val > 0 else 'negative'})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    conn = get_connection()
    cur = conn.cursor()

    # ---- Load shared data ----
    print("Loading RPE ratios...")
    rpe_lookup = load_rpe_lookup(cur)
    national_cnt = sum(1 for k in rpe_lookup if k[0] == 'national')
    state_cnt = sum(1 for k in rpe_lookup if k[0] == 'state')
    county_cnt = sum(1 for k in rpe_lookup if k[0] == 'county')
    print(f"  National: {national_cnt:,}, State: {state_cnt:,}, "
          f"County: {county_cnt:,}")

    print("Loading ZIP->county crosswalk...")
    zip_to_county = load_zip_county_crosswalk(cur)
    print(f"  {len(zip_to_county):,} ZIPs")

    print("Building supervisor ratio lookup from BLS matrix...")
    sup_lookup = build_supervisor_ratio_lookup(cur)
    print(f"  {len(sup_lookup):,} NAICS prefixes with supervisor ratios")
    # Show some examples
    sample_prefixes = sorted(sup_lookup.keys())[:5]
    for p in sample_prefixes:
        print(f"    NAICS {p}: multiplier {sup_lookup[p]:.3f}")

    # ==================================================================
    # GROUND TRUTH A: NLRB whole-company elections
    # ==================================================================
    print("\n--- Ground Truth A: NLRB Elections ---")
    print("Fetching NLRB elections linked to 990 filers...")
    raw_a = fetch_ground_truth_a(cur)
    print(f"  Raw records (before filter): {len(raw_a):,}")

    records_a = []
    filtered_reasons = {'no_known_emp': 0, 'too_large': 0,
                        'low_coverage': 0, 'no_revenue': 0}

    for (case_number, eligible_voters, state, naics, latest_unit_size,
         zipcode, total_revenue, total_employees_990) in raw_a:

        eligible_voters = float(eligible_voters)
        total_revenue = float(total_revenue)

        # Known employee count: prefer 990 total_employees, fall back to
        # f7 latest_unit_size
        known_emp = None
        if total_employees_990 and float(total_employees_990) > 0:
            known_emp = float(total_employees_990)
        elif latest_unit_size and float(latest_unit_size) > 0:
            known_emp = float(latest_unit_size)

        if not known_emp or known_emp <= 0:
            filtered_reasons['no_known_emp'] += 1
            continue

        # Small single-location filter
        if known_emp >= 200:
            filtered_reasons['too_large'] += 1
            continue

        # Bargaining unit must be substantial share of workforce
        coverage = eligible_voters / known_emp
        if coverage < 0.5:
            filtered_reasons['low_coverage'] += 1
            continue

        if total_revenue <= 0:
            filtered_reasons['no_revenue'] += 1
            continue

        # Compute actual employees via supervisor multiplier
        multiplier = get_supervisor_multiplier(naics, sup_lookup)
        actual_emp = eligible_voters * multiplier

        records_a.append({
            'revenue': total_revenue,
            'actual_emp': actual_emp,
            'naics': naics,
            'state': state,
            'zip': zipcode,
            'case_number': case_number,
            'eligible_voters': eligible_voters,
            'multiplier': multiplier,
        })

    print(f"  After whole-company filter: {len(records_a):,}")
    print(f"  Filtered out: no_known_emp={filtered_reasons['no_known_emp']}, "
          f"too_large={filtered_reasons['too_large']}, "
          f"low_coverage={filtered_reasons['low_coverage']}, "
          f"no_revenue={filtered_reasons['no_revenue']}")

    if records_a:
        mults = [r['multiplier'] for r in records_a]
        mults.sort()
        print(f"  Supervisor multiplier range: "
              f"{mults[0]:.3f} - {mults[-1]:.3f} "
              f"(median {mults[len(mults)//2]:.3f})")

    result_a = run_validation(records_a, rpe_lookup, zip_to_county)
    print_validation_results(
        "GROUND TRUTH A: NLRB Elections (whole-company units)", result_a)

    # ==================================================================
    # GROUND TRUTH B: 990 Self-Reported Employees
    # ==================================================================
    print("\n--- Ground Truth B: 990 Self-Reported ---")
    print("Fetching 990 filers with self-reported employees...")
    raw_b = fetch_ground_truth_b(cur)
    print(f"  Raw records: {len(raw_b):,}")

    records_b = []
    for (ein, total_revenue, total_employees, state, naics, zipcode) in raw_b:
        total_revenue = float(total_revenue)
        total_employees = float(total_employees)

        if total_employees <= 0 or total_revenue <= 0:
            continue

        records_b.append({
            'revenue': total_revenue,
            'actual_emp': total_employees,
            'naics': naics,
            'state': state,
            'zip': zipcode,
        })

    print(f"  Valid records: {len(records_b):,}")

    result_b = run_validation(records_b, rpe_lookup, zip_to_county)
    print_validation_results(
        "GROUND TRUTH B: 990 Self-Reported Employees", result_b)

    # ==================================================================
    # Cross-validation summary
    # ==================================================================
    print_cross_summary(result_a, result_b)

    conn.close()
    print("\nDual validation complete.")


if __name__ == '__main__':
    main()
