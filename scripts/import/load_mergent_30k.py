"""
Load ~30K new Mergent Intellect NY employers into mergent_employers table.
Deduplicates by DUNS against existing records. Same column mapping as original loader.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
import os
import re

# ============================================================
# CONFIGURE: File path(s) to load
# ============================================================
base_path = r"C:\Users\jakew\Downloads\labor-data-project\New York all companies above 1 m"

# Auto-discover all CSV/Excel files in the directory
files = sorted([f for f in os.listdir(base_path) if f.endswith('.csv') or f.endswith('.xlsx')])

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

# NAICS to sector mapping (same as original loader)
SECTOR_MAP = {
    '621': 'HEALTHCARE_AMBULATORY',
    '622': 'HEALTHCARE_HOSPITALS',
    '623': 'HEALTHCARE_NURSING',
    '624': 'SOCIAL_SERVICES',
    '611': 'EDUCATION',
    '561': 'BUILDING_SERVICES',
    '541': 'PROFESSIONAL',
    '485': 'TRANSIT',
    '488': 'TRANSIT',
    '221': 'UTILITIES',
    '721': 'HOSPITALITY',
    '722': 'FOOD_SERVICE',
    '813': 'CIVIC_ORGANIZATIONS',
    '921': 'GOVERNMENT',
    '922': 'GOVERNMENT',
    '923': 'GOVERNMENT',
    '924': 'GOVERNMENT',
    '925': 'GOVERNMENT',
    '926': 'GOVERNMENT',
    '513': 'BROADCASTING',
    '516': 'PUBLISHING',
    '519': 'INFORMATION',
    '562': 'WASTE_MGMT',
    '811': 'REPAIR_SERVICES',
    '711': 'ARTS_ENTERTAINMENT',
    '712': 'MUSEUMS',
}


def clean_duns(val):
    """Clean DUNS number - remove dashes"""
    if pd.isna(val) or val is None:
        return None
    return str(val).replace('-', '').strip()


def clean_ein(val):
    """Clean EIN - remove non-numeric"""
    if pd.isna(val) or val is None:
        return None
    try:
        ein = str(int(float(val)))
        if len(ein) == 8:
            ein = '0' + ein
        return ein
    except (ValueError, TypeError):
        return None


def clean_zip(val):
    """Clean ZIP code"""
    if pd.isna(val) or val is None:
        return None
    try:
        z = str(int(float(val)))
        if len(z) == 4:
            z = '0' + z
        elif len(z) > 5:
            z = z[:5]
        return z
    except (ValueError, TypeError):
        return str(val)[:5] if val else None


def clean_state(val):
    """Convert state name to 2-letter abbreviation"""
    STATE_MAP = {
        'NEW YORK': 'NY', 'CALIFORNIA': 'CA', 'TEXAS': 'TX', 'FLORIDA': 'FL',
        'ILLINOIS': 'IL', 'PENNSYLVANIA': 'PA', 'OHIO': 'OH', 'GEORGIA': 'GA',
        'NORTH CAROLINA': 'NC', 'MICHIGAN': 'MI', 'NEW JERSEY': 'NJ', 'VIRGINIA': 'VA',
        'WASHINGTON': 'WA', 'ARIZONA': 'AZ', 'MASSACHUSETTS': 'MA', 'TENNESSEE': 'TN',
        'INDIANA': 'IN', 'MARYLAND': 'MD', 'MISSOURI': 'MO', 'WISCONSIN': 'WI',
        'COLORADO': 'CO', 'MINNESOTA': 'MN', 'SOUTH CAROLINA': 'SC', 'ALABAMA': 'AL',
        'LOUISIANA': 'LA', 'KENTUCKY': 'KY', 'OREGON': 'OR', 'OKLAHOMA': 'OK',
        'CONNECTICUT': 'CT', 'UTAH': 'UT', 'IOWA': 'IA', 'NEVADA': 'NV',
        'ARKANSAS': 'AR', 'MISSISSIPPI': 'MS', 'KANSAS': 'KS', 'NEW MEXICO': 'NM',
        'NEBRASKA': 'NE', 'WEST VIRGINIA': 'WV', 'IDAHO': 'ID', 'HAWAII': 'HI',
        'NEW HAMPSHIRE': 'NH', 'MAINE': 'ME', 'MONTANA': 'MT', 'RHODE ISLAND': 'RI',
        'DELAWARE': 'DE', 'SOUTH DAKOTA': 'SD', 'NORTH DAKOTA': 'ND', 'ALASKA': 'AK',
        'VERMONT': 'VT', 'WYOMING': 'WY', 'DISTRICT OF COLUMBIA': 'DC',
    }
    if pd.isna(val) or val is None:
        return None
    val = str(val).strip().upper()
    if len(val) <= 2:
        return val[:2]
    return STATE_MAP.get(val, val[:2])


def normalize_name(name):
    """Normalize company name for matching (lowercase to match existing DB convention)"""
    if not name or pd.isna(name):
        return None
    name = str(name).lower().strip()
    for suffix in [' llc', ' inc', ' corp', ' ltd', ' co', ' company', ' corporation',
                   ' incorporated', ' limited', '.', ',', '"', "'", ' the']:
        name = name.replace(suffix, '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_employees(val):
    """Parse employee count"""
    if pd.isna(val) or val is None:
        return None
    try:
        val = str(val).replace(',', '')
        return int(float(val))
    except (ValueError, TypeError):
        return None


def get_sector(naics_code):
    """Map NAICS code to sector category"""
    if pd.isna(naics_code) or naics_code is None:
        return 'OTHER'
    try:
        naics_str = str(int(float(naics_code)))[:3]
    except (ValueError, TypeError):
        return 'OTHER'
    return SECTOR_MAP.get(naics_str, 'OTHER')


# ============================================================
# MAIN LOAD
# ============================================================
print("=" * 60)
print("LOADING NEW MERGENT EMPLOYER DATA (NY ~30K)")
print("=" * 60)

# Load all files
all_dfs = []
for fname in files:
    fpath = os.path.join(base_path, fname)
    try:
        df = pd.read_excel(fpath, engine='openpyxl')
    except Exception:
        df = pd.read_csv(fpath)
    df['source_file'] = fname
    all_dfs.append(df)
    print(f"  Loaded {fname}: {len(df)} rows")

combined = pd.concat(all_dfs, ignore_index=True)
print(f"\nTotal rows from files: {len(combined)}")

# Check for existing DUNS in database
cur.execute("SELECT duns FROM mergent_employers WHERE duns IS NOT NULL")
existing_duns = set(r[0] for r in cur.fetchall())
print(f"Existing DUNS in database: {len(existing_duns)}")

# Process records
print("\nProcessing data...")

records = []
skipped_no_name = 0
skipped_dups = 0
sector_counts = {}
other_naics = {}

for idx, row in combined.iterrows():
    duns = clean_duns(row.get('D-U-N-S@ Number'))

    # Skip if DUNS already exists
    if duns and duns in existing_duns:
        skipped_dups += 1
        continue

    # Track this DUNS to avoid duplicates within this load
    if duns:
        existing_duns.add(duns)

    company_name = row.get('Company Name')
    if not company_name or pd.isna(company_name):
        skipped_no_name += 1
        continue

    naics_primary = row.get('Primary NAICS Code')
    sector = get_sector(naics_primary)

    # Track sector distribution
    sector_counts[sector] = sector_counts.get(sector, 0) + 1

    # Track OTHER NAICS codes for review
    if sector == 'OTHER' and pd.notna(naics_primary):
        try:
            code_3 = str(int(float(naics_primary)))[:3]
            other_naics[code_3] = other_naics.get(code_3, 0) + 1
        except (ValueError, TypeError):
            pass

    # No Sales column in these files
    records.append((
        duns,
        clean_ein(row.get('Employer ID Number (EIN)')),
        clean_duns(row.get('Global Duns No')),
        clean_duns(row.get('Immediate Parent Duns No')),
        row.get('Immediate Parent Name'),
        clean_duns(row.get('Domestic Parent Duns No')),
        row.get('Domestic Parent Name'),
        str(company_name).strip(),
        normalize_name(company_name),
        row.get('Trade Style'),
        row.get('Former Name'),
        row.get('Company Type'),
        row.get('Subsidiary Status'),
        row.get('Location Type'),
        str(row.get('Physical Address'))[:500] if pd.notna(row.get('Physical Address')) else None,
        str(row.get('Physical City'))[:100] if pd.notna(row.get('Physical City')) else None,
        clean_state(row.get('Physical State')),
        clean_zip(row.get('Physical Zipcode')),
        str(row.get('Physical County'))[:100] if pd.notna(row.get('Physical County')) else None,
        row.get('Latitude'),
        row.get('Longtitude'),  # Note: typo in Mergent source
        str(row.get('Mailing Address'))[:500] if pd.notna(row.get('Mailing Address')) else None,
        str(row.get('Mailing City'))[:100] if pd.notna(row.get('Mailing City')) else None,
        clean_state(row.get('Mailing State')),
        clean_zip(row.get('Mailing Zipcode')),
        parse_employees(row.get('Employee this Site')),
        parse_employees(row.get('Employee All Sites')),
        None,  # sales_amount - not in these files
        None,  # sales_raw - not in these files
        int(float(row.get('Year of Founding'))) if pd.notna(row.get('Year of Founding')) else None,
        str(int(float(naics_primary)))[:6] if pd.notna(naics_primary) else None,
        row.get('Primary NAICS Description'),
        str(row.get('Secondary NAICS Code'))[:20] if pd.notna(row.get('Secondary NAICS Code')) else None,
        row.get('Secondary NAICS Description'),
        None,  # sic_primary
        row.get('Line of Business'),
        str(row.get('Phone No'))[:20] if pd.notna(row.get('Phone No')) else None,
        row.get('Web Address (URL)'),
        sector,  # sector_category
        row.get('Manufacturing Indicator') == 'Manufacturer',
        row.get('Minority Owned Indicator') == 'Yes',
        row.get('source_file'),
    ))

print(f"\nRecords to insert: {len(records)}")
print(f"Skipped (no name): {skipped_no_name}")
print(f"Skipped (DUNS already in DB): {skipped_dups}")

# Insert records
print("\nInserting records...")

execute_values(cur, """
    INSERT INTO mergent_employers (
        duns, ein, global_duns, parent_duns, parent_name,
        domestic_parent_duns, domestic_parent_name,
        company_name, company_name_normalized, trade_name, former_name,
        company_type, subsidiary_status, location_type,
        street_address, city, state, zip, county,
        latitude, longitude,
        mailing_address, mailing_city, mailing_state, mailing_zip,
        employees_site, employees_all_sites, sales_amount, sales_raw,
        year_founded, naics_primary, naics_primary_desc,
        naics_secondary, naics_secondary_desc, sic_primary,
        line_of_business, phone, website,
        sector_category, manufacturing_indicator, minority_owned,
        source_file
    )
    VALUES %s
    ON CONFLICT DO NOTHING
""", records, page_size=1000)

inserted = cur.rowcount
conn.commit()
print(f"Inserted: {inserted}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SECTOR DISTRIBUTION (NEW RECORDS)")
print("=" * 60)
print(f"\n{'Sector':<30} {'Count':>8}")
print("-" * 40)
for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
    print(f"{sector:<30} {count:>8,}")

if other_naics:
    print("\n" + "=" * 60)
    print("UNMAPPED NAICS CODES (mapped to OTHER)")
    print("=" * 60)
    print(f"\n{'NAICS 3-digit':<15} {'Count':>8}")
    print("-" * 25)
    for code, count in sorted(other_naics.items(), key=lambda x: -x[1]):
        print(f"{code:<15} {count:>8,}")

# Final DB totals
print("\n" + "=" * 60)
print("FINAL DATABASE TOTALS")
print("=" * 60)

cur.execute("""
    SELECT sector_category, COUNT(*),
           SUM(employees_site) as total_employees,
           COUNT(CASE WHEN ein IS NOT NULL THEN 1 END) as with_ein
    FROM mergent_employers
    GROUP BY sector_category
    ORDER BY COUNT(*) DESC
""")

print(f"\n{'Sector':<30} {'Count':>8} {'Employees':>12} {'With EIN':>10}")
print("-" * 65)
for row in cur.fetchall():
    emp = f"{row[2]:,}" if row[2] else "N/A"
    print(f"{row[0] or 'NULL':<30} {row[1]:>8,} {emp:>12} {row[3]:>10,}")

cur.execute("SELECT COUNT(*), SUM(employees_site) FROM mergent_employers")
total, total_emp = cur.fetchone()
emp_str = f"{total_emp:,}" if total_emp else "N/A"
print(f"\n{'TOTAL':<30} {total:>8,} {emp_str:>12}")

cur.close()
conn.close()

print("\n" + "=" * 60)
print("LOAD COMPLETE")
print("Next steps:")
print("  1. py scripts/scoring/run_mergent_matching.py")
print("  2. py scripts/scoring/match_labor_violations.py")
print("  3. py scripts/scoring/create_sector_views.py")
print("  4. REFRESH MATERIALIZED VIEW mv_employer_search")
print("=" * 60)
