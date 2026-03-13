"""
Download ACS 5-year tract-level demographics from Census Bureau API.

Fetches race, hispanic origin, sex, education, income, and employment
data for all census tracts in the US, then loads into acs_tract_demographics.

Census API docs: https://api.census.gov/data.html
Register for a free API key: https://api.census.gov/data/key_signup.html

Usage:
    py scripts/etl/download_acs_tract_demographics.py                   # download + load
    py scripts/etl/download_acs_tract_demographics.py --key YOUR_KEY    # with API key
    py scripts/etl/download_acs_tract_demographics.py --year 2023       # specific year
    py scripts/etl/download_acs_tract_demographics.py --state 06        # single state
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)


# 52 state FIPS codes (50 states + DC + PR)
STATE_FIPS = [
    '01', '02', '04', '05', '06', '08', '09', '10', '11', '12',
    '13', '15', '16', '17', '18', '19', '20', '21', '22', '23',
    '24', '25', '26', '27', '28', '29', '30', '31', '32', '33',
    '34', '35', '36', '37', '38', '39', '40', '41', '42', '44',
    '45', '46', '47', '48', '49', '50', '51', '53', '54', '55',
    '56', '72',
]

BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# ACS variable definitions
RACE_VARS = {
    'B02001_001E': 'total_population',
    'B02001_002E': 'pop_white',
    'B02001_003E': 'pop_black',
    'B02001_004E': 'pop_aian',
    'B02001_005E': 'pop_asian',
    'B02001_006E': 'pop_nhpi',
    'B02001_007E': 'pop_other_race',
    'B02001_008E': 'pop_two_plus',
}

HISPANIC_VARS = {
    'B03002_012E': 'pop_hispanic',
    'B03002_002E': 'pop_not_hispanic',
}

SEX_VARS = {
    'B01001_002E': 'pop_male',
    'B01001_026E': 'pop_female',
}

# Education (25+): B15003
# 002-016 = less than HS, 017-018 = HS/GED, 019-021 = some college/associates,
# 022 = bachelors, 023-025 = graduate
EDU_VARS = {
    'B15003_001E': 'pop_25plus',
    # No HS: sum of 002-016
    'B15003_002E': 'edu_no_hs_002', 'B15003_003E': 'edu_no_hs_003',
    'B15003_004E': 'edu_no_hs_004', 'B15003_005E': 'edu_no_hs_005',
    'B15003_006E': 'edu_no_hs_006', 'B15003_007E': 'edu_no_hs_007',
    'B15003_008E': 'edu_no_hs_008', 'B15003_009E': 'edu_no_hs_009',
    'B15003_010E': 'edu_no_hs_010', 'B15003_011E': 'edu_no_hs_011',
    'B15003_012E': 'edu_no_hs_012', 'B15003_013E': 'edu_no_hs_013',
    'B15003_014E': 'edu_no_hs_014', 'B15003_015E': 'edu_no_hs_015',
    'B15003_016E': 'edu_no_hs_016',
    # HS/GED: 017-018
    'B15003_017E': 'edu_hs_017', 'B15003_018E': 'edu_hs_018',
    # Some college / associates: 019-021
    'B15003_019E': 'edu_sc_019', 'B15003_020E': 'edu_sc_020',
    'B15003_021E': 'edu_sc_021',
    # Bachelors: 022
    'B15003_022E': 'edu_bachelors',
    # Graduate: 023-025
    'B15003_023E': 'edu_grad_023', 'B15003_024E': 'edu_grad_024',
    'B15003_025E': 'edu_grad_025',
}

INCOME_VARS = {
    'B19013_001E': 'median_household_income',
}

EMPLOYMENT_VARS = {
    'B23025_002E': 'labor_force',
    'B23025_004E': 'employed',
    'B23025_005E': 'unemployed',
}

# Combine all -- we'll fetch in groups to stay under URL length limits
ALL_GROUPS = [
    ('race', RACE_VARS),
    ('hispanic', HISPANIC_VARS),
    ('sex', SEX_VARS),
    ('education', EDU_VARS),
    ('income', INCOME_VARS),
    ('employment', EMPLOYMENT_VARS),
]


def safe_int(val):
    """Convert Census API value to int, handling None/-666666666/negatives."""
    if val is None:
        return None
    try:
        v = int(val)
        return v if v >= 0 else None
    except (ValueError, TypeError):
        return None


def fetch_acs_data(year, state_fips, var_dict, api_key=None):
    """Fetch ACS variables for all tracts in a state."""
    var_list = ','.join(var_dict.keys())
    url = BASE_URL.format(year=year)
    params = {
        'get': var_list,
        'for': 'tract:*',
        'in': 'state:%s' % state_fips,
    }
    if api_key:
        params['key'] = api_key

    for attempt in range(1, 4):
        try:
            response = requests.get(url, params=params, timeout=60)
            if response.status_code == 204:
                return {}
            response.raise_for_status()
            data = response.json()
            if not data or len(data) < 2:
                return {}

            headers = data[0]
            results = {}
            for row in data[1:]:
                row_dict = dict(zip(headers, row))
                st = row_dict.get('state', '')
                county = row_dict.get('county', '')
                tract = row_dict.get('tract', '')
                tract_fips = st + county + tract

                parsed = {}
                for var_code, col_name in var_dict.items():
                    parsed[col_name] = safe_int(row_dict.get(var_code))
                results[tract_fips] = parsed
            return results

        except requests.exceptions.RequestException as e:
            if attempt < 3:
                time.sleep(2 * attempt)
            else:
                print("    FAILED for state %s: %s" % (state_fips, str(e)[:80]))
                return {}
    return {}


def merge_tract_data(all_data, new_data):
    """Merge new variable data into accumulated tract data."""
    for tract_fips, vals in new_data.items():
        if tract_fips not in all_data:
            all_data[tract_fips] = {}
        all_data[tract_fips].update(vals)


def compute_percentages(row):
    """Compute derived percentage columns from raw counts."""
    total_pop = row.get('total_population') or 0

    if total_pop > 0:
        female = row.get('pop_female') or 0
        row['pct_female'] = round(100.0 * female / total_pop, 2)

        minority = total_pop - (row.get('pop_white') or 0)
        row['pct_minority'] = round(100.0 * minority / total_pop, 2)

        hispanic = row.get('pop_hispanic') or 0
        row['pct_hispanic'] = round(100.0 * hispanic / total_pop, 2)
    else:
        row['pct_female'] = None
        row['pct_minority'] = None
        row['pct_hispanic'] = None

    pop_25plus = row.get('pop_25plus') or 0
    if pop_25plus > 0:
        bachelors_plus = (row.get('edu_bachelors') or 0) + (row.get('edu_graduate') or 0)
        row['pct_bachelors_plus'] = round(100.0 * bachelors_plus / pop_25plus, 2)
    else:
        row['pct_bachelors_plus'] = None

    labor_force = row.get('labor_force') or 0
    unemployed = row.get('unemployed') or 0
    if labor_force > 0:
        row['unemployment_rate'] = round(100.0 * unemployed / labor_force, 2)
    else:
        row['unemployment_rate'] = None


def aggregate_education(row):
    """Sum education sub-variables into aggregate columns."""
    # No HS: sum 002-016
    no_hs = 0
    for i in range(2, 17):
        no_hs += row.pop('edu_no_hs_%03d' % i, 0) or 0
    row['edu_no_hs'] = no_hs

    # HS/GED: 017-018
    hs = (row.pop('edu_hs_017', 0) or 0) + (row.pop('edu_hs_018', 0) or 0)
    row['edu_hs'] = hs

    # Some college: 019-021
    sc = 0
    for i in range(19, 22):
        sc += row.pop('edu_sc_%03d' % i, 0) or 0
    row['edu_some_college'] = sc

    # Graduate: 023-025
    grad = 0
    for i in range(23, 26):
        grad += row.pop('edu_grad_%03d' % i, 0) or 0
    row['edu_graduate'] = grad


def main():
    api_key = None
    year = 2022
    single_state = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--key' and i + 1 < len(args):
            api_key = args[i + 1]
            i += 2
        elif args[i] == '--year' and i + 1 < len(args):
            year = int(args[i + 1])
            i += 2
        elif args[i] == '--state' and i + 1 < len(args):
            single_state = args[i + 1]
            i += 2
        else:
            i += 1

    states = [single_state] if single_state else STATE_FIPS

    print("=" * 70)
    print("DOWNLOAD ACS TRACT DEMOGRAPHICS")
    print("Year: %d | States: %d | API key: %s" % (
        year, len(states), "provided" if api_key else "not set (rate-limited)"))
    print("=" * 70)

    # Collect all tract data
    all_tracts = {}
    total_api_calls = 0

    for si, state_fips in enumerate(states):
        print("\n[%d/%d] State %s..." % (si + 1, len(states), state_fips))

        for group_name, var_dict in ALL_GROUPS:
            data = fetch_acs_data(year, state_fips, var_dict, api_key)
            total_api_calls += 1
            merge_tract_data(all_tracts, data)

            # Rate limit if no API key
            if not api_key:
                time.sleep(0.5)

        print("  Tracts so far: %d" % len(all_tracts))

    print("\n\nTotal tracts fetched: %d" % len(all_tracts))
    print("Total API calls: %d" % total_api_calls)

    if not all_tracts:
        print("No data fetched. Check API key and network.")
        return

    # Process education aggregates and percentages
    for tract_fips, row in all_tracts.items():
        aggregate_education(row)
        compute_percentages(row)

    # Load into database
    print("\nLoading into acs_tract_demographics...")
    conn = get_connection()
    cur = conn.cursor()

    # Clear existing data for this year
    cur.execute("DELETE FROM acs_tract_demographics WHERE acs_year = %s", [year])
    deleted = cur.rowcount
    if deleted:
        print("  Cleared %d existing rows for year %d" % (deleted, year))

    inserted = 0
    errors = 0
    for tract_fips, row in all_tracts.items():
        if len(tract_fips) != 11:
            errors += 1
            continue

        state_fips_code = tract_fips[:2]
        county_fips_code = tract_fips[:5]

        try:
            cur.execute("""
                INSERT INTO acs_tract_demographics (
                    tract_fips, state_fips, county_fips,
                    total_population, pop_white, pop_black, pop_aian, pop_asian,
                    pop_nhpi, pop_other_race, pop_two_plus,
                    pop_hispanic, pop_not_hispanic,
                    pop_male, pop_female, pop_25plus,
                    edu_no_hs, edu_hs, edu_some_college, edu_bachelors, edu_graduate,
                    median_household_income,
                    labor_force, employed, unemployed,
                    pct_female, pct_minority, pct_hispanic,
                    pct_bachelors_plus, unemployment_rate,
                    acs_year
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s
                )
                ON CONFLICT (tract_fips) DO UPDATE SET
                    total_population = EXCLUDED.total_population,
                    pop_white = EXCLUDED.pop_white,
                    pop_black = EXCLUDED.pop_black,
                    pop_aian = EXCLUDED.pop_aian,
                    pop_asian = EXCLUDED.pop_asian,
                    pop_nhpi = EXCLUDED.pop_nhpi,
                    pop_other_race = EXCLUDED.pop_other_race,
                    pop_two_plus = EXCLUDED.pop_two_plus,
                    pop_hispanic = EXCLUDED.pop_hispanic,
                    pop_not_hispanic = EXCLUDED.pop_not_hispanic,
                    pop_male = EXCLUDED.pop_male,
                    pop_female = EXCLUDED.pop_female,
                    pop_25plus = EXCLUDED.pop_25plus,
                    edu_no_hs = EXCLUDED.edu_no_hs,
                    edu_hs = EXCLUDED.edu_hs,
                    edu_some_college = EXCLUDED.edu_some_college,
                    edu_bachelors = EXCLUDED.edu_bachelors,
                    edu_graduate = EXCLUDED.edu_graduate,
                    median_household_income = EXCLUDED.median_household_income,
                    labor_force = EXCLUDED.labor_force,
                    employed = EXCLUDED.employed,
                    unemployed = EXCLUDED.unemployed,
                    pct_female = EXCLUDED.pct_female,
                    pct_minority = EXCLUDED.pct_minority,
                    pct_hispanic = EXCLUDED.pct_hispanic,
                    pct_bachelors_plus = EXCLUDED.pct_bachelors_plus,
                    unemployment_rate = EXCLUDED.unemployment_rate,
                    acs_year = EXCLUDED.acs_year,
                    loaded_at = CURRENT_TIMESTAMP
            """, (
                tract_fips, state_fips_code, county_fips_code,
                row.get('total_population'), row.get('pop_white'), row.get('pop_black'),
                row.get('pop_aian'), row.get('pop_asian'),
                row.get('pop_nhpi'), row.get('pop_other_race'), row.get('pop_two_plus'),
                row.get('pop_hispanic'), row.get('pop_not_hispanic'),
                row.get('pop_male'), row.get('pop_female'), row.get('pop_25plus'),
                row.get('edu_no_hs'), row.get('edu_hs'), row.get('edu_some_college'),
                row.get('edu_bachelors'), row.get('edu_graduate'),
                row.get('median_household_income'),
                row.get('labor_force'), row.get('employed'), row.get('unemployed'),
                row.get('pct_female'), row.get('pct_minority'), row.get('pct_hispanic'),
                row.get('pct_bachelors_plus'), row.get('unemployment_rate'),
                year,
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print("  Error on tract %s: %s" % (tract_fips, str(e)[:80]))

    conn.commit()
    conn.close()

    print("\n" + "=" * 70)
    print("LOAD COMPLETE")
    print("=" * 70)
    print("  Inserted/updated: %d" % inserted)
    print("  Errors: %d" % errors)
    print("  Total tracts: %d" % len(all_tracts))


if __name__ == '__main__':
    main()
