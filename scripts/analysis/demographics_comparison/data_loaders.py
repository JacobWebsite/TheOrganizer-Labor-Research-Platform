"""Data loaders for demographics comparison.

Reuses query patterns from demo_blend_prototype.py.
All functions take a cursor and return normalized dicts.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))


def _pct(n, d):
    return round(100.0 * float(n) / float(d), 2) if d and float(d) > 0 else 0.0


def zip_to_county(cur, zipcode):
    """Resolve a ZIP code to county_fips via zip_county_crosswalk."""
    zipcode = str(zipcode).strip().zfill(5)
    cur.execute(
        "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
        [zipcode])
    row = cur.fetchone()
    return row['county_fips'] if row else None


def zip_to_state_fips(cur, zipcode):
    """Resolve a ZIP code to state_fips (first 2 digits of county_fips)."""
    county = zip_to_county(cur, zipcode)
    if county and len(county) >= 2:
        return county[:2]
    return None


def get_acs_race_nonhispanic(cur, naics4, state_fips):
    """Get ACS non-Hispanic race breakdown for an industry x state.

    Filters to hispanic='0' so race categories are non-Hispanic,
    aligning with EEO-1's mutually exclusive categories.

    Returns dict {White: pct, Black: pct, Asian: pct, AIAN: pct, NHOPI: pct, Two+: pct}
    or None if no data.
    """
    # Try exact NAICS4, then 2-digit fallback, then state-wide
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4, '0']:
        where = "WHERE naics4 = %s AND hispanic = '0'"
        params = [naics_val]
        if state_fips:
            where += " AND state_fips = %s"
            params.append(state_fips)

        cur.execute(
            "SELECT race, SUM(weighted_workers) as w "
            "FROM cur_acs_workforce_demographics "
            + where + " AND race IN ('1','2','3','4','5','6','7','8','9') "
            "GROUP BY race", params)
        rows = {r['race']: float(r['w']) for r in cur.fetchall()}
        if rows:
            t = sum(rows.values())
            if t > 0:
                return {
                    'White': _pct(rows.get('1', 0), t),
                    'Black': _pct(rows.get('2', 0), t),
                    'AIAN': _pct(rows.get('3', 0), t),
                    'Asian': _pct(rows.get('4', 0) + rows.get('5', 0) + rows.get('6', 0), t),
                    'NHOPI': _pct(rows.get('5', 0), t),  # 5 is sometimes NHOPI
                    'Two+': _pct(rows.get('8', 0) + rows.get('9', 0) + rows.get('7', 0), t),
                    '_total_workers': t,
                    '_naics_used': naics_val,
                }
    return None


def get_acs_race_nonhispanic_v2(cur, naics4, state_fips):
    """Get ACS non-Hispanic race breakdown -- improved grouping.

    ACS/IPUMS race codes:
      1=White, 2=Black, 3=AIAN, 4=Asian, 5=Asian/Pacific, 6=Other,
      7=Two major races, 8=Three+ races, 9=Two minor+major

    We combine: Asian = codes 4+5, NHOPI = 0 (ACS doesn't separate NHOPI in IPUMS),
    Two+ = codes 7+8+9, Other = code 6.

    Since IPUMS doesn't separate NHOPI from Asian, we set NHOPI=0 for ACS.
    """
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4, '0']:
        where = "WHERE naics4 = %s AND hispanic = '0'"
        params = [naics_val]
        if state_fips:
            where += " AND state_fips = %s"
            params.append(state_fips)

        cur.execute(
            "SELECT race, SUM(weighted_workers) as w "
            "FROM cur_acs_workforce_demographics "
            + where + " AND race IN ('1','2','3','4','5','6','7','8','9') "
            "GROUP BY race", params)
        rows = {r['race']: float(r['w']) for r in cur.fetchall()}
        if rows:
            t = sum(rows.values())
            if t > 0:
                asian_nhopi = rows.get('4', 0) + rows.get('5', 0)
                two_plus = rows.get('7', 0) + rows.get('8', 0) + rows.get('9', 0)
                other = rows.get('6', 0)
                return {
                    'White': _pct(rows.get('1', 0), t),
                    'Black': _pct(rows.get('2', 0), t),
                    'Asian': _pct(asian_nhopi, t),
                    'AIAN': _pct(rows.get('3', 0), t),
                    'NHOPI': 0.0,  # IPUMS doesn't separate NHOPI
                    'Two+': _pct(two_plus + other, t),
                    '_total_workers': t,
                    '_naics_used': naics_val,
                }
    return None


def get_acs_hispanic(cur, naics4, state_fips):
    """Get ACS Hispanic/Not Hispanic breakdown for industry x state.

    IPUMS HISPAN: 0=Not Hispanic, 1-4=Hispanic varieties.

    Returns dict {Hispanic: pct, Not Hispanic: pct} or None.
    """
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4, '0']:
        where = "WHERE naics4 = %s"
        params = [naics_val]
        if state_fips:
            where += " AND state_fips = %s"
            params.append(state_fips)

        cur.execute(
            "SELECT hispanic, SUM(weighted_workers) as w "
            "FROM cur_acs_workforce_demographics "
            + where + " GROUP BY hispanic", params)
        rows = {r['hispanic']: float(r['w']) for r in cur.fetchall()}
        if rows:
            not_hisp = rows.get('0', 0)
            is_hisp = sum(v for k, v in rows.items() if k != '0' and k is not None)
            t = not_hisp + is_hisp
            if t > 0:
                return {
                    'Hispanic': _pct(is_hisp, t),
                    'Not Hispanic': _pct(not_hisp, t),
                }
    return None


def get_acs_gender(cur, naics4, state_fips):
    """Get ACS gender breakdown for industry x state.

    IPUMS SEX: 1=Male, 2=Female.

    Returns dict {Male: pct, Female: pct} or None.
    """
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4, '0']:
        where = "WHERE naics4 = %s"
        params = [naics_val]
        if state_fips:
            where += " AND state_fips = %s"
            params.append(state_fips)

        cur.execute(
            "SELECT sex, SUM(weighted_workers) as w "
            "FROM cur_acs_workforce_demographics "
            + where + " AND sex IN ('1','2') GROUP BY sex", params)
        rows = {r['sex']: float(r['w']) for r in cur.fetchall()}
        if rows:
            t = sum(rows.values())
            if t > 0:
                return {
                    'Male': _pct(rows.get('1', 0), t),
                    'Female': _pct(rows.get('2', 0), t),
                }
    return None


def get_lodes_race(cur, county_fips):
    """Get LODES county-level race breakdown.

    LODES has: jobs_white, jobs_black, jobs_native (AIAN),
    jobs_asian, jobs_pacific (NHOPI), jobs_two_plus_races.

    Returns dict matching EEO-1 categories or None.
    """
    cur.execute(
        "SELECT * FROM cur_lodes_geo_metrics WHERE county_fips = %s",
        [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['demo_total_jobs'])
    if dt == 0:
        return None
    return {
        'White': _pct(row['jobs_white'], dt),
        'Black': _pct(row['jobs_black'], dt),
        'Asian': _pct(row['jobs_asian'], dt),
        'AIAN': _pct(row['jobs_native'], dt),
        'NHOPI': _pct(row['jobs_pacific'], dt),
        'Two+': _pct(row['jobs_two_plus_races'], dt),
        '_demo_total': dt,
    }


def get_lodes_hispanic(cur, county_fips):
    """Get LODES county-level Hispanic breakdown."""
    cur.execute(
        "SELECT jobs_hispanic, jobs_not_hispanic, demo_total_jobs "
        "FROM cur_lodes_geo_metrics WHERE county_fips = %s",
        [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['demo_total_jobs'])
    if dt == 0:
        return None
    return {
        'Hispanic': _pct(row['jobs_hispanic'], dt),
        'Not Hispanic': _pct(row['jobs_not_hispanic'], dt),
    }


def get_lodes_gender(cur, county_fips):
    """Get LODES county-level gender breakdown."""
    cur.execute(
        "SELECT jobs_male, jobs_female, demo_total_jobs "
        "FROM cur_lodes_geo_metrics WHERE county_fips = %s",
        [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['demo_total_jobs'])
    if dt == 0:
        return None
    return {
        'Male': _pct(row['jobs_male'], dt),
        'Female': _pct(row['jobs_female'], dt),
    }


def get_tract_race(cur, county_fips):
    """Get tract-level residential race breakdown aggregated to county.

    Uses population columns from acs_tract_demographics.
    Note: ACS tract data includes Hispanic in race categories (not mutually exclusive),
    but we use it as a third layer signal regardless.
    """
    cur.execute("""
        SELECT SUM(total_population) as total_pop,
               SUM(pop_white) as white, SUM(pop_black) as black,
               SUM(pop_asian) as asian, SUM(pop_aian) as aian,
               SUM(pop_nhpi) as nhpi,
               SUM(pop_other_race) as other_race,
               SUM(pop_two_plus) as two_plus,
               SUM(pop_hispanic) as hispanic,
               SUM(pop_not_hispanic) as not_hispanic,
               SUM(pop_male) as male, SUM(pop_female) as female
        FROM acs_tract_demographics
        WHERE county_fips = %s
    """, [county_fips])
    row = cur.fetchone()
    if not row or not row['total_pop'] or float(row['total_pop']) == 0:
        return None

    tp = float(row['total_pop'])
    race_total = sum(float(row[c] or 0) for c in [
        'white', 'black', 'asian', 'aian', 'nhpi', 'other_race', 'two_plus'])
    if race_total == 0:
        race_total = tp

    return {
        'White': _pct(row['white'], race_total),
        'Black': _pct(row['black'], race_total),
        'Asian': _pct(row['asian'], race_total),
        'AIAN': _pct(row['aian'], race_total),
        'NHOPI': _pct(row['nhpi'], race_total),
        'Two+': _pct(float(row['other_race'] or 0) + float(row['two_plus'] or 0), race_total),
    }


def get_tract_hispanic(cur, county_fips):
    """Get tract-level Hispanic breakdown aggregated to county."""
    cur.execute("""
        SELECT SUM(pop_hispanic) as hispanic,
               SUM(pop_not_hispanic) as not_hispanic
        FROM acs_tract_demographics
        WHERE county_fips = %s
    """, [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    h = float(row['hispanic'] or 0)
    nh = float(row['not_hispanic'] or 0)
    t = h + nh
    if t == 0:
        return None
    return {
        'Hispanic': _pct(h, t),
        'Not Hispanic': _pct(nh, t),
    }


def get_tract_gender(cur, county_fips):
    """Get tract-level gender breakdown aggregated to county."""
    cur.execute("""
        SELECT SUM(pop_male) as male, SUM(pop_female) as female
        FROM acs_tract_demographics
        WHERE county_fips = %s
    """, [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    m = float(row['male'] or 0)
    f = float(row['female'] or 0)
    t = m + f
    if t == 0:
        return None
    return {
        'Male': _pct(m, t),
        'Female': _pct(f, t),
    }


def get_occupation_mix(cur, naics4):
    """Get occupation mix for an industry from BLS occupation matrix.

    Returns list of (soc_code, pct_of_industry) or empty list.
    Uses fallback: exact NAICS -> 3-digit prefix -> 2-digit sector.
    """
    # BLS industry codes are NAICS-based but may have different formats
    # Try exact match, then prefix matches
    for code in [naics4, naics4 + '00', naics4[:3] + '000', naics4[:3], naics4[:3] + '0', naics4[:2] + '0000', naics4[:2]]:
        cur.execute(
            "SELECT occupation_code, percent_of_industry "
            "FROM bls_industry_occupation_matrix "
            "WHERE industry_code = %s AND LOWER(occupation_type) = 'line item' "
            "AND percent_of_industry IS NOT NULL "
            "ORDER BY percent_of_industry DESC",
            [code])
        rows = cur.fetchall()
        if rows:
            return [(r['occupation_code'], float(r['percent_of_industry'])) for r in rows]

    # Try LIKE match
    cur.execute(
        "SELECT occupation_code, percent_of_industry "
        "FROM bls_industry_occupation_matrix "
        "WHERE industry_code LIKE %s AND LOWER(occupation_type) = 'line item' "
        "AND percent_of_industry IS NOT NULL "
        "ORDER BY percent_of_industry DESC LIMIT 50",
        [naics4[:3] + '%'])
    rows = cur.fetchall()
    if rows:
        return [(r['occupation_code'], float(r['percent_of_industry'])) for r in rows]

    return []


def get_acs_by_occupation(cur, soc_code, state_fips, dimension='race'):
    """Get ACS demographics for a specific occupation (SOC code) and state.

    dimension: 'race', 'hispanic', or 'gender'

    Returns dict matching the requested dimension categories, or None.
    """
    # SOC codes in ACS may be stored differently (e.g., with/without dashes)
    soc_variants = [soc_code, soc_code.replace('-', '')]

    for soc in soc_variants:
        if dimension == 'race':
            cur.execute(
                "SELECT race, SUM(weighted_workers) as w "
                "FROM cur_acs_workforce_demographics "
                "WHERE soc_code = %s AND state_fips = %s AND hispanic = '0' "
                "AND race IN ('1','2','3','4','5','6','7','8','9') "
                "GROUP BY race", [soc, state_fips])
            rows = {r['race']: float(r['w']) for r in cur.fetchall()}
            if rows:
                t = sum(rows.values())
                if t > 0:
                    asian = rows.get('4', 0) + rows.get('5', 0)
                    two_plus = rows.get('7', 0) + rows.get('8', 0) + rows.get('9', 0) + rows.get('6', 0)
                    return {
                        'White': _pct(rows.get('1', 0), t),
                        'Black': _pct(rows.get('2', 0), t),
                        'Asian': _pct(asian, t),
                        'AIAN': _pct(rows.get('3', 0), t),
                        'NHOPI': 0.0,
                        'Two+': _pct(two_plus, t),
                        '_workers': t,
                    }

        elif dimension == 'hispanic':
            cur.execute(
                "SELECT hispanic, SUM(weighted_workers) as w "
                "FROM cur_acs_workforce_demographics "
                "WHERE soc_code = %s AND state_fips = %s "
                "GROUP BY hispanic", [soc, state_fips])
            rows = {r['hispanic']: float(r['w']) for r in cur.fetchall()}
            if rows:
                not_h = rows.get('0', 0)
                is_h = sum(v for k, v in rows.items() if k != '0' and k is not None)
                t = not_h + is_h
                if t > 0:
                    return {
                        'Hispanic': _pct(is_h, t),
                        'Not Hispanic': _pct(not_h, t),
                    }

        elif dimension == 'gender':
            cur.execute(
                "SELECT sex, SUM(weighted_workers) as w "
                "FROM cur_acs_workforce_demographics "
                "WHERE soc_code = %s AND state_fips = %s "
                "AND sex IN ('1','2') GROUP BY sex", [soc, state_fips])
            rows = {r['sex']: float(r['w']) for r in cur.fetchall()}
            if rows:
                t = sum(rows.values())
                if t > 0:
                    return {
                        'Male': _pct(rows.get('1', 0), t),
                        'Female': _pct(rows.get('2', 0), t),
                    }

    return None


def has_acs_data(cur, naics4, state_fips):
    """Check if ACS has data for this NAICS + state combo."""
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4]:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM cur_acs_workforce_demographics "
            "WHERE naics4 = %s AND state_fips = %s AND sex IN ('1','2')",
            [naics_val, state_fips])
        if cur.fetchone()['cnt'] > 0:
            return True
    return False


def has_lodes_data(cur, county_fips):
    """Check if LODES has data for this county."""
    cur.execute(
        "SELECT COUNT(*) as cnt FROM cur_lodes_geo_metrics WHERE county_fips = %s",
        [county_fips])
    return cur.fetchone()['cnt'] > 0


# ============================================================
# V2 loaders (added for improved methods M1b-M5b, M7)
# ============================================================

def zip_to_tract(cur, zipcode, county_fips):
    """Approximate tract lookup for a ZIP within a county.

    Finds the tract with the most jobs in cur_lodes_tract_metrics
    for the given county. Returns tract_fips or None.
    """
    if not zipcode or not county_fips:
        return None
    cur.execute(
        "SELECT tract_fips FROM cur_lodes_tract_metrics "
        "WHERE county_fips = %s ORDER BY total_jobs DESC LIMIT 1",
        [county_fips])
    row = cur.fetchone()
    return row['tract_fips'] if row else None


def get_lodes_tract_race(cur, tract_fips):
    """Get LODES workplace tract-level race breakdown.

    Returns dict {White, Black, Asian, AIAN, NHOPI, Two+} or None.
    """
    if not tract_fips:
        return None
    cur.execute(
        "SELECT * FROM cur_lodes_tract_metrics WHERE tract_fips = %s",
        [tract_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['total_jobs'])
    if dt == 0:
        return None
    return {
        'White': _pct(row['jobs_white'], dt),
        'Black': _pct(row['jobs_black'], dt),
        'Asian': _pct(row['jobs_asian'], dt),
        'AIAN': _pct(row['jobs_native'], dt),
        'NHOPI': _pct(row['jobs_pacific'], dt),
        'Two+': _pct(row['jobs_two_plus_races'], dt),
        '_total_jobs': dt,
    }


def get_lodes_tract_hispanic(cur, tract_fips):
    """Get LODES workplace tract-level Hispanic breakdown."""
    if not tract_fips:
        return None
    cur.execute(
        "SELECT jobs_hispanic, jobs_not_hispanic, total_jobs "
        "FROM cur_lodes_tract_metrics WHERE tract_fips = %s",
        [tract_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['total_jobs'])
    if dt == 0:
        return None
    return {
        'Hispanic': _pct(row['jobs_hispanic'], dt),
        'Not Hispanic': _pct(row['jobs_not_hispanic'], dt),
    }


def get_lodes_tract_gender(cur, tract_fips):
    """Get LODES workplace tract-level gender breakdown."""
    if not tract_fips:
        return None
    cur.execute(
        "SELECT jobs_male, jobs_female, total_jobs "
        "FROM cur_lodes_tract_metrics WHERE tract_fips = %s",
        [tract_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['total_jobs'])
    if dt == 0:
        return None
    return {
        'Male': _pct(row['jobs_male'], dt),
        'Female': _pct(row['jobs_female'], dt),
    }


def get_state_occupation_mix(cur, naics4, state_fips):
    """Get state-level occupation proportions from ACS workforce data.

    Returns list of (soc_code, pct_of_total) for top 30 occupations,
    or empty list if no data.

    Fallback cascade: exact NAICS4 -> 2-digit prefix -> all industries.
    """
    for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4, '']:
        where = "WHERE soc_code IS NOT NULL AND soc_code != ''"
        params = []
        if naics_val:
            where += " AND naics4 = %s"
            params.append(naics_val)
        if state_fips:
            where += " AND state_fips = %s"
            params.append(state_fips)

        cur.execute(
            "SELECT soc_code, SUM(weighted_workers) AS w "
            "FROM cur_acs_workforce_demographics "
            + where + " GROUP BY soc_code ORDER BY w DESC",
            params)
        rows = cur.fetchall()
        if rows:
            total = sum(float(r['w']) for r in rows)
            if total > 0:
                result = []
                for r in rows[:30]:
                    result.append((r['soc_code'], float(r['w']) * 100.0 / total))
                return result
    return []


def get_lodes_pct_minority(cur, county_fips):
    """Get pct_minority from cur_lodes_geo_metrics.

    Returns float (0-1) or None.
    """
    if not county_fips:
        return None
    cur.execute(
        "SELECT pct_minority FROM cur_lodes_geo_metrics WHERE county_fips = %s",
        [county_fips])
    row = cur.fetchone()
    if not row or row['pct_minority'] is None:
        return None
    return float(row['pct_minority'])


# ============================================================
# V6 loaders (added for V6 demographics model)
# ============================================================

def get_lodes_minority_share(cur, county_fips):
    """Get LODES minority share as a classification category.
    Returns 'Low (<25%)', 'Medium (25-50%)', or 'High (>50%)'.
    Uses LODES county data instead of EEO-1 ground truth.
    """
    pct = get_lodes_pct_minority(cur, county_fips)
    if pct is None:
        return 'Medium (25-50%)'  # default
    minority = pct * 100.0  # pct_minority is 0-1
    if minority < 25:
        return 'Low (<25%)'
    elif minority <= 50:
        return 'Medium (25-50%)'
    else:
        return 'High (>50%)'


def get_lodes_industry_race(cur, county_fips, naics_2digit):
    """Get LODES county demographics weighted by industry employment.
    Uses CNS codes from lodes_county_industry_demographics table.
    Returns dict {White, Black, Asian, AIAN, NHOPI, Two+} or None.
    """
    # Import mapping here to avoid circular imports
    try:
        from config import NAICS_TO_CNS
    except ImportError:
        return None

    cns_code = NAICS_TO_CNS.get(naics_2digit)
    if not cns_code or not county_fips:
        return None

    try:
        cur.execute(
            "SELECT * FROM lodes_county_industry_demographics "
            "WHERE county_fips = %s AND cns_code = %s",
            [county_fips, cns_code])
        row = cur.fetchone()
    except Exception:
        # Table may not exist yet (ETL not run)
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        return None
    if not row:
        return None
    dt = float(row['total_industry_jobs'])
    if dt == 0:
        return None
    return {
        'White': _pct(row['jobs_white'], dt),
        'Black': _pct(row['jobs_black'], dt),
        'Asian': _pct(row['jobs_asian'], dt),
        'AIAN': _pct(row['jobs_native'], dt),
        'NHOPI': _pct(row['jobs_pacific'], dt),
        'Two+': _pct(row['jobs_two_plus_races'], dt),
        '_industry_total': dt,
        '_cns_code': cns_code,
    }


def get_lodes_industry_hispanic(cur, county_fips, naics_2digit):
    """Get LODES county Hispanic demographics weighted by industry employment.
    Uses CNS codes from lodes_county_industry_demographics table.
    Returns dict {Hispanic: pct, Not Hispanic: pct} or None.
    """
    try:
        from config import NAICS_TO_CNS
    except ImportError:
        return None

    cns_code = NAICS_TO_CNS.get(naics_2digit)
    if not cns_code or not county_fips:
        return None

    try:
        cur.execute(
            "SELECT jobs_hispanic, jobs_not_hispanic, total_industry_jobs "
            "FROM lodes_county_industry_demographics "
            "WHERE county_fips = %s AND cns_code = %s",
            [county_fips, cns_code])
        row = cur.fetchone()
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        return None
    if not row:
        return None
    dt = float(row['total_industry_jobs'])
    if dt == 0:
        return None
    return {
        'Hispanic': _pct(row['jobs_hispanic'], dt),
        'Not Hispanic': _pct(row['jobs_not_hispanic'], dt),
        '_industry_total': dt,
        '_cns_code': cns_code,
    }


def get_qcew_concentration(cur, county_fips, naics_2digit):
    """Get QCEW industry concentration for county x industry.
    Returns dict with location_quotient, industry_share, avg_annual_pay or None.
    """
    if not county_fips or not naics_2digit:
        return None

    # QCEW uses combined codes for some industries
    NAICS_TO_QCEW = {
        '31': '31-33', '32': '31-33', '33': '31-33',
        '44': '44-45', '45': '44-45',
        '48': '48-49', '49': '48-49',
    }
    qcew_code = NAICS_TO_QCEW.get(naics_2digit, naics_2digit)

    cur.execute(
        "SELECT lq_annual_avg_emplvl, avg_annual_pay, annual_avg_emplvl "
        "FROM qcew_annual "
        "WHERE area_fips = %s AND industry_code = %s "
        "ORDER BY year DESC LIMIT 1",
        [county_fips, qcew_code])
    row = cur.fetchone()
    if not row or row['lq_annual_avg_emplvl'] is None:
        return None
    return {
        'location_quotient': float(row['lq_annual_avg_emplvl']),
        'avg_annual_pay': int(row['avg_annual_pay']) if row['avg_annual_pay'] else None,
        'annual_avg_emplvl': int(row['annual_avg_emplvl']) if row['annual_avg_emplvl'] else None,
    }


def get_acs_race_metro(cur, naics_code, cbsa_code):
    """Get ACS race demographics at metro level (more precise than state).
    Uses metro_cbsa column in cur_acs_workforce_demographics.
    Returns dict {White, Black, Asian, AIAN, NHOPI, Two+} or None.
    """
    if not cbsa_code:
        return None

    for naics_val in [naics_code, naics_code[:2] if len(naics_code) >= 2 else naics_code]:
        cur.execute(
            "SELECT race, SUM(weighted_workers) as w "
            "FROM cur_acs_workforce_demographics "
            "WHERE naics4 = %s AND metro_cbsa = %s AND hispanic = '0' "
            "AND race IN ('1','2','3','4','5','6','7','8','9') "
            "GROUP BY race", [naics_val, cbsa_code])
        rows = {r['race']: float(r['w']) for r in cur.fetchall()}
        if rows:
            t = sum(rows.values())
            if t > 0:
                asian_nhopi = rows.get('4', 0) + rows.get('5', 0)
                two_plus = rows.get('7', 0) + rows.get('8', 0) + rows.get('9', 0) + rows.get('6', 0)
                return {
                    'White': _pct(rows.get('1', 0), t),
                    'Black': _pct(rows.get('2', 0), t),
                    'Asian': _pct(asian_nhopi, t),
                    'AIAN': _pct(rows.get('3', 0), t),
                    'NHOPI': 0.0,
                    'Two+': _pct(two_plus, t),
                    '_total_workers': t,
                    '_naics_used': naics_val,
                    '_data_source': 'acs_metro',
                }
    return None


def get_multi_tract_demographics(cur, zipcode):
    """Get demographics averaged across ALL tracts in ZIP,
    weighted by LODES employment counts (bus_ratio).
    Returns dict with race, hispanic, gender sub-dicts or None.
    """
    if not zipcode:
        return None

    cur.execute(
        "SELECT zt.tract_geoid, zt.bus_ratio, "
        "lt.total_jobs, lt.jobs_white, lt.jobs_black, lt.jobs_native, "
        "lt.jobs_asian, lt.jobs_pacific, lt.jobs_two_plus_races, "
        "lt.jobs_hispanic, lt.jobs_not_hispanic, lt.jobs_male, lt.jobs_female "
        "FROM zip_tract_crosswalk zt "
        "JOIN cur_lodes_tract_metrics lt ON lt.tract_fips = zt.tract_geoid "
        "WHERE zt.zip_code = %s AND lt.total_jobs > 0",
        [zipcode])
    rows = cur.fetchall()
    if not rows:
        return None

    # Weight by total_jobs * bus_ratio
    total_weight = 0.0
    race_accum = {'White': 0, 'Black': 0, 'Asian': 0, 'AIAN': 0, 'NHOPI': 0, 'Two+': 0}
    hisp_accum = {'Hispanic': 0, 'Not Hispanic': 0}
    gender_accum = {'Male': 0, 'Female': 0}

    for row in rows:
        w = float(row['total_jobs']) * float(row['bus_ratio'])
        if w <= 0:
            continue
        total_weight += w
        race_accum['White'] += float(row['jobs_white']) * float(row['bus_ratio'])
        race_accum['Black'] += float(row['jobs_black']) * float(row['bus_ratio'])
        race_accum['Asian'] += float(row['jobs_asian']) * float(row['bus_ratio'])
        race_accum['AIAN'] += float(row['jobs_native']) * float(row['bus_ratio'])
        race_accum['NHOPI'] += float(row['jobs_pacific']) * float(row['bus_ratio'])
        race_accum['Two+'] += float(row['jobs_two_plus_races']) * float(row['bus_ratio'])
        hisp_accum['Hispanic'] += float(row['jobs_hispanic']) * float(row['bus_ratio'])
        hisp_accum['Not Hispanic'] += float(row['jobs_not_hispanic']) * float(row['bus_ratio'])
        gender_accum['Male'] += float(row['jobs_male']) * float(row['bus_ratio'])
        gender_accum['Female'] += float(row['jobs_female']) * float(row['bus_ratio'])

    if total_weight == 0:
        return None

    race_total = sum(race_accum.values())
    hisp_total = sum(hisp_accum.values())
    gender_total = sum(gender_accum.values())

    result = {}
    if race_total > 0:
        result['race'] = {k: _pct(v, race_total) for k, v in race_accum.items()}
    if hisp_total > 0:
        result['hispanic'] = {k: _pct(v, hisp_total) for k, v in hisp_accum.items()}
    if gender_total > 0:
        result['gender'] = {k: _pct(v, gender_total) for k, v in gender_accum.items()}
    result['_tract_count'] = len(rows)
    result['_total_weight'] = total_weight
    return result if result.get('race') else None


def get_occupation_mix_local(cur, naics_code, cbsa_code):
    """Get local (metro-level) occupation mix from OES data.
    Returns list of (occ_code, employment) or empty list.
    """
    if not cbsa_code:
        return []

    # OES area_type=4 is MSA, naics='000000' is all-industry
    cur.execute(
        "SELECT occ_code, tot_emp FROM oes_occupation_wages "
        "WHERE area = %s AND area_type = 4 "
        "AND o_group = 'detailed' AND tot_emp IS NOT NULL "
        "ORDER BY tot_emp DESC",
        [cbsa_code])
    rows = cur.fetchall()
    if rows:
        return [(r['occ_code'], int(r['tot_emp'])) for r in rows]
    return []


def get_pct_female_by_occupation(cur, soc_code):
    """Get percent female for an occupation from CPS Table 11.
    Returns float (0-100) or None.
    """
    if not soc_code:
        return None
    try:
        cur.execute(
            "SELECT pct_women FROM cps_occ_gender_2025 WHERE soc_code = %s",
            [soc_code])
        row = cur.fetchone()
        if row and row['pct_women'] is not None:
            return float(row['pct_women'])

        # Try broad SOC (e.g., '29-0000' for all healthcare practitioners)
        broad_soc = soc_code[:3] + '0000'
        cur.execute(
            "SELECT pct_women FROM cps_occ_gender_2025 WHERE soc_code = %s",
            [broad_soc])
        row = cur.fetchone()
        if row and row['pct_women'] is not None:
            return float(row['pct_women'])
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
    return None


def get_occ_chain_demographics(cur, naics_group, state_fips):
    """Get occupation-chain demographic estimate for a NAICS group x state.

    Uses precomputed occ_local_demographics table built by
    build_occ_chain_table.py. Returns dict with race/gender/hispanic
    percentages, or None if no data for this combination.

    This implements the three-way chain:
      BLS industry occupation mix x OES local weights x ACS state occupation demographics
    """
    if not naics_group or not state_fips:
        return None
    try:
        cur.execute("""
            SELECT pct_female, pct_asian, pct_white, pct_black,
                   pct_hispanic, pct_aian, occs_matched, pct_industry_covered
            FROM occ_local_demographics
            WHERE naics_group = %s AND state_fips = %s
        """, [naics_group, state_fips])
        row = cur.fetchone()
    except Exception:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        return None

    if not row:
        return None

    # Only return if coverage is sufficient to be reliable
    if (row['occs_matched'] or 0) < 5 or (row['pct_industry_covered'] or 0) < 20:
        return None

    return {
        'Female': float(row['pct_female'] or 0),
        'Male': 100.0 - float(row['pct_female'] or 0),
        'Asian': float(row['pct_asian'] or 0),
        'White': float(row['pct_white'] or 0),
        'Black': float(row['pct_black'] or 0),
        'Hispanic': float(row['pct_hispanic'] or 0),
        'AIAN': float(row['pct_aian'] or 0),
        'NHOPI': 0.0,  # not separately tracked
        'Two+': max(0.0, 100.0 - float(row['pct_white'] or 0)
                    - float(row['pct_black'] or 0) - float(row['pct_asian'] or 0)
                    - float(row['pct_aian'] or 0)),
        '_occs_matched': int(row['occs_matched'] or 0),
        '_pct_covered': float(row['pct_industry_covered'] or 0),
        '_data_source': 'occ_chain_local',
    }
