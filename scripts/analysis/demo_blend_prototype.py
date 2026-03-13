"""Prototype: Blended workplace demographics estimate.

Example: Nursing home (NAICS 6231) in Passaic County, NJ.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def pct(n, d):
    return round(100.0 * float(n) / float(d), 1) if d and float(d) > 0 else 0.0


def get_acs_workforce(cur, naics4, state_fips=None):
    where = 'WHERE naics4 = %s'
    params = [naics4]
    if state_fips:
        where += ' AND state_fips = %s'
        params.append(state_fips)

    result = {}

    # Sex
    cur.execute(
        "SELECT sex, SUM(weighted_workers) as w FROM cur_acs_workforce_demographics "
        + where + " AND sex IN ('1','2') GROUP BY sex", params)
    sex = {r['sex']: float(r['w']) for r in cur.fetchall()}
    t = sum(sex.values())
    result['pct_female'] = pct(sex.get('2', 0), t)
    result['pct_male'] = pct(sex.get('1', 0), t)

    # Race
    cur.execute(
        "SELECT race, SUM(weighted_workers) as w FROM cur_acs_workforce_demographics "
        + where + " AND race IN ('1','2','3','4','5','6') GROUP BY race", params)
    race = {r['race']: float(r['w']) for r in cur.fetchall()}
    t = sum(race.values())
    result['pct_white'] = pct(race.get('1', 0), t)
    result['pct_black'] = pct(race.get('2', 0), t)
    result['pct_asian'] = pct(race.get('4', 0), t)
    result['pct_aian'] = pct(race.get('3', 0), t)
    result['pct_other'] = pct(race.get('6', 0) + race.get('5', 0), t)

    # Hispanic -- IPUMS HISPAN codes:
    # 0=Not Hispanic, 1=Mexican, 2=Puerto Rican, 3=Cuban, 4=Other
    cur.execute(
        "SELECT hispanic, SUM(weighted_workers) as w FROM cur_acs_workforce_demographics "
        + where + " GROUP BY hispanic", params)
    hisp = {r['hispanic']: float(r['w']) for r in cur.fetchall()}
    not_hisp = hisp.get('0', 0)
    is_hisp = sum(v for k, v in hisp.items() if k != '0')
    t = not_hisp + is_hisp
    result['pct_hispanic'] = pct(is_hisp, t)

    # Age
    cur.execute(
        "SELECT age_bucket, SUM(weighted_workers) as w FROM cur_acs_workforce_demographics "
        + where + " AND age_bucket != '0' GROUP BY age_bucket", params)
    age = {r['age_bucket']: float(r['w']) for r in cur.fetchall()}
    t = sum(age.values())
    result['pct_under25'] = pct(age.get('u25', 0), t)
    result['pct_25_34'] = pct(age.get('25_34', 0), t)
    result['pct_35_44'] = pct(age.get('35_44', 0), t)
    result['pct_45_54'] = pct(age.get('45_54', 0), t)
    result['pct_55_64'] = pct(age.get('55_64', 0), t)
    result['pct_65plus'] = pct(age.get('65p', 0), t)

    # Education -- IPUMS EDUC codes:
    # 00=N/A, 01-05=No HS, 06=HS/GED, 07-08=Some college, 10=Bachelors, 11=Graduate+
    cur.execute(
        "SELECT education, SUM(weighted_workers) as w FROM cur_acs_workforce_demographics "
        + where + " AND education != '00' GROUP BY education", params)
    edu = {r['education']: float(r['w']) for r in cur.fetchall()}
    t = sum(edu.values())
    no_hs = sum(edu.get(c, 0) for c in ['01', '02', '03', '04', '05'])
    result['pct_no_hs'] = pct(no_hs, t)
    result['pct_hs'] = pct(edu.get('06', 0), t)
    result['pct_some_college'] = pct(edu.get('07', 0) + edu.get('08', 0), t)
    result['pct_bachelors'] = pct(edu.get('10', 0), t)
    result['pct_graduate'] = pct(edu.get('11', 0), t)
    result['total_workers'] = sum(sex.values())
    return result


def get_lodes(cur, county_fips):
    cur.execute(
        'SELECT * FROM cur_lodes_geo_metrics WHERE county_fips = %s',
        [county_fips])
    row = cur.fetchone()
    if not row:
        return None
    dt = float(row['demo_total_jobs'])
    if dt == 0:
        return None
    return {
        'demo_total': dt,
        'total_jobs': float(row['total_jobs']),
        'pct_female': pct(row['jobs_female'], dt),
        'pct_white': pct(row['jobs_white'], dt),
        'pct_black': pct(row['jobs_black'], dt),
        'pct_asian': pct(float(row['jobs_asian']) + float(row['jobs_pacific']), dt),
        'pct_hispanic': pct(row['jobs_hispanic'], dt),
        'pct_no_hs': pct(row['jobs_edu_less_than_hs'], dt),
        'pct_hs': pct(row['jobs_edu_hs'], dt),
        'pct_some_college': pct(row['jobs_edu_some_college'], dt),
        'pct_bachelors_plus': pct(row['jobs_edu_bachelors_plus'], dt),
        'pct_under25': pct(row['jobs_age_29_or_younger'], row['total_jobs']),
        'pct_30_54': pct(row['jobs_age_30_to_54'], row['total_jobs']),
        'pct_55plus': pct(row['jobs_age_55_plus'], row['total_jobs']),
    }


def get_tract_avg(cur, county_fips):
    cur.execute("""
        SELECT AVG(pct_female) as pct_f, AVG(pct_minority) as pct_min,
               AVG(pct_hispanic) as pct_h, AVG(pct_bachelors_plus) as pct_ba,
               AVG(unemployment_rate) as unemp,
               AVG(median_household_income) as med_inc,
               COUNT(*) as tracts
        FROM acs_tract_demographics WHERE county_fips = %s
    """, [county_fips])
    row = cur.fetchone()
    if not row or not row['tracts']:
        return None
    return {
        'tracts': int(row['tracts']),
        'pct_female': float(row['pct_f'] or 0),
        'pct_minority': float(row['pct_min'] or 0),
        'pct_hispanic': float(row['pct_h'] or 0),
        'pct_bachelors_plus': float(row['pct_ba'] or 0),
        'unemployment_rate': float(row['unemp'] or 0),
        'median_income': int(float(row['med_inc'] or 0)),
    }


def blend(ind, lodes_val, tract_val, w_ind=0.50, w_lodes=0.30, w_tract=0.20):
    """Weighted blend with graceful fallback when layers are missing."""
    parts, weights = [], []
    if ind is not None:
        parts.append(ind * w_ind); weights.append(w_ind)
    if lodes_val is not None:
        parts.append(lodes_val * w_lodes); weights.append(w_lodes)
    if tract_val is not None:
        parts.append(tract_val * w_tract); weights.append(w_tract)
    if not weights:
        return None
    return round(sum(parts) / sum(weights), 1)


def main():
    naics = '6231'
    state = '34'
    county = '34031'

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    nat = get_acs_workforce(cur, naics)
    nj = get_acs_workforce(cur, naics, state)
    lodes = get_lodes(cur, county)
    tract = get_tract_avg(cur, county)

    # --- Blended estimates ---
    est_female = blend(nj['pct_female'], lodes['pct_female'], tract['pct_female'])
    est_white = blend(nj['pct_white'], lodes['pct_white'], 100 - tract['pct_minority'])
    est_black = blend(nj['pct_black'], lodes['pct_black'], None)
    est_asian = blend(nj['pct_asian'], lodes['pct_asian'], None)
    est_other = max(0, round(100 - est_white - est_black - est_asian, 1))
    est_hispanic = blend(nj['pct_hispanic'], lodes['pct_hispanic'], tract['pct_hispanic'])

    print('=' * 78)
    print('ESTIMATED WORKPLACE DEMOGRAPHICS: Nursing Home (NAICS 6231)')
    print('Location: Passaic County, NJ (FIPS 34031)')
    print('=' * 78)
    print('')
    print('%-30s %10s %10s %15s' % ('Dimension', 'National', 'NJ', 'Passaic Est.'))
    print('-' * 78)

    print('')
    print('GENDER')
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Female', nat['pct_female'], nj['pct_female'], est_female))
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Male', nat['pct_male'], nj['pct_male'], 100 - est_female))

    print('')
    print('RACE')
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'White', nat['pct_white'], nj['pct_white'], est_white))
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Black/African American', nat['pct_black'], nj['pct_black'], est_black))
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Asian', nat['pct_asian'], nj['pct_asian'], est_asian))
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Other/Two+', nat['pct_other'], nj['pct_other'], est_other))

    print('')
    print('ETHNICITY')
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Hispanic/Latino', nat['pct_hispanic'], nj['pct_hispanic'], est_hispanic))
    print('  %-28s %9.1f%% %9.1f%% %12.1f%%' % (
        'Not Hispanic/Latino', 100 - nat['pct_hispanic'],
        100 - nj['pct_hispanic'], 100 - est_hispanic))

    print('')
    print('AGE')
    print('  %-28s %9.1f%% %9.1f%%' % ('Under 25', nat['pct_under25'], nj['pct_under25']))
    print('  %-28s %9.1f%% %9.1f%%' % ('25-34', nat['pct_25_34'], nj['pct_25_34']))
    print('  %-28s %9.1f%% %9.1f%%' % ('35-44', nat['pct_35_44'], nj['pct_35_44']))
    print('  %-28s %9.1f%% %9.1f%%' % ('45-54', nat['pct_45_54'], nj['pct_45_54']))
    print('  %-28s %9.1f%% %9.1f%%' % ('55-64', nat['pct_55_64'], nj['pct_55_64']))
    print('  %-28s %9.1f%% %9.1f%%' % ('65+', nat['pct_65plus'], nj['pct_65plus']))

    print('')
    print('EDUCATION')
    print('  %-28s %9.1f%% %9.1f%%' % ('No HS diploma', nat['pct_no_hs'], nj['pct_no_hs']))
    print('  %-28s %9.1f%% %9.1f%%' % ('HS diploma/GED', nat['pct_hs'], nj['pct_hs']))
    print('  %-28s %9.1f%% %9.1f%%' % ('Some college/Associates', nat['pct_some_college'], nj['pct_some_college']))
    print('  %-28s %9.1f%% %9.1f%%' % ("Bachelor's", nat['pct_bachelors'], nj['pct_bachelors']))
    print('  %-28s %9.1f%% %9.1f%%' % ('Graduate+', nat['pct_graduate'], nj['pct_graduate']))

    print('')
    print('LOCAL CONTEXT')
    print('  Passaic County median household income: $%s' % f"{tract['median_income']:,}")
    print('  Passaic County unemployment rate: %.1f%%' % tract['unemployment_rate'])
    print('  Passaic County census tracts: %d' % tract['tracts'])

    print('')
    print('SAMPLE SIZES')
    print('  National ACS nursing home workers: %s' % f"{int(nat['total_workers']):,}")
    print('  NJ ACS nursing home workers: %s' % f"{int(nj['total_workers']):,}")
    print('  Passaic County LODES all-industry jobs: %s' % f"{int(lodes['demo_total']):,}")

    print('')
    print('METHODOLOGY')
    print('  Passaic Estimate = 50%% NJ nursing home workforce (ACS industry x state)')
    print('                   + 30%% Passaic County all-industry workers (LODES)')
    print('                   + 20%% Passaic County residential population (ACS tract)')
    print('')
    print('  The industry profile dominates (50%%) because job type determines')
    print('  who gets hired. LODES adjusts (30%%) for who actually works in this')
    print('  county across all industries. Tract data adjusts (20%%) for local')
    print('  labor pool availability.')

    conn.close()


if __name__ == '__main__':
    main()
