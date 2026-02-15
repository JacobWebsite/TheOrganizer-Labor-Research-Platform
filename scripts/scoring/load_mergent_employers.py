"""
Load Mergent Employer Data into PostgreSQL
Processes ~14,000 employers from 7 CSV/Excel files, auto-categorizes by NAICS
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
import os
import re

from db_config import get_connection
# Database connection
conn = get_connection()
cur = conn.cursor()

# Base path for CSV files
base_path = r"C:\Users\jakew\Downloads\labor-data-project\AFSCME case example NY"

# Files to process
files = [
    "1_2000_other_industries_advancesearch18488938096983ac1794e51.csv",
    "2001_4000_other_industries_advancesearch8908858966983ac4faff74.csv",
    "4001_6000_other_industries_advancesearch5505435806983ac81d50bb.csv",
    "6001_8000_other_industries_advancesearch10671607656983ace3e6154.csv",
    "8001_10000_other_industries_advancesearch18620684906983ad182ec58.csv",
    "10001_12000_other_industries_advancesearch18312885316983ad6c0726f.csv",
    "12001_14000_other_industries_advancesearch19488114456983adce287fa.csv",
]

# NAICS to sector mapping
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
    '712': 'MUSEUMS',  # Already loaded
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
            ein = '0' + ein  # Pad with leading zero
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
        elif len(z) == 9:
            z = z[:5]  # Take first 5
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
    """Normalize company name for matching"""
    if not name or pd.isna(name):
        return None
    name = str(name).upper().strip()
    # Remove common suffixes
    for suffix in [' LLC', ' INC', ' CORP', ' LTD', ' CO', ' COMPANY', ' CORPORATION',
                   ' INCORPORATED', ' LIMITED', '.', ',', '"', "'", ' THE']:
        name = name.replace(suffix, '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_sales(val):
    """Parse sales value from string like $283,250,000,000"""
    if pd.isna(val) or val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        val = str(val).replace('$', '').replace(',', '').strip()
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


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
    naics_str = str(int(float(naics_code)))[:3]
    return SECTOR_MAP.get(naics_str, 'OTHER')


# Load all files
print("=" * 60)
print("LOADING MERGENT EMPLOYER DATA")
print("=" * 60)

all_dfs = []
for fname in files:
    fpath = os.path.join(base_path, fname)
    df = pd.read_excel(fpath, engine='openpyxl')
    df['source_file'] = fname
    all_dfs.append(df)
    print(f"Loaded {fname}: {len(df)} rows")

combined = pd.concat(all_dfs, ignore_index=True)
print(f"\nTotal rows: {len(combined)}")

# Check for existing DUNS in database (from museum data)
cur.execute("SELECT duns FROM mergent_employers WHERE duns IS NOT NULL")
existing_duns = set(r[0] for r in cur.fetchall())
print(f"Existing DUNS in database: {len(existing_duns)}")

# Clean and transform data
print("\nProcessing data...")

records = []
skipped = 0
duplicates = 0

for idx, row in combined.iterrows():
    duns = clean_duns(row.get('D-U-N-S@ Number'))

    # Skip if DUNS already exists
    if duns and duns in existing_duns:
        duplicates += 1
        continue

    # Track this DUNS to avoid duplicates within this load
    if duns:
        existing_duns.add(duns)

    company_name = row.get('Company Name')
    if not company_name or pd.isna(company_name):
        skipped += 1
        continue

    naics_primary = row.get('Primary NAICS Code')
    sector = get_sector(naics_primary)

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
        str(row.get('Physical Address'))[:500] if row.get('Physical Address') else None,
        str(row.get('Physical City'))[:100] if row.get('Physical City') else None,
        clean_state(row.get('Physical State')),
        clean_zip(row.get('Physical Zipcode')),
        str(row.get('Physical County'))[:100] if row.get('Physical County') else None,
        row.get('Latitude'),
        row.get('Longtitude'),  # Note: typo in source
        str(row.get('Mailing Address'))[:500] if row.get('Mailing Address') else None,
        str(row.get('Mailing City'))[:100] if row.get('Mailing City') else None,
        clean_state(row.get('Mailing State')),
        clean_zip(row.get('Mailing Zipcode')),
        parse_employees(row.get('Employee this Site')),
        parse_employees(row.get('Employee All Sites')),
        parse_sales(row.get('Sales')),
        row.get('Sales'),  # Raw sales string
        int(float(row.get('Year of Founding'))) if pd.notna(row.get('Year of Founding')) else None,
        str(int(float(naics_primary)))[:6] if pd.notna(naics_primary) else None,
        row.get('Primary NAICS Description'),
        str(row.get('Secondary NAICS Code'))[:20] if row.get('Secondary NAICS Code') else None,
        row.get('Secondary NAICS Description'),
        None,  # sic_primary
        row.get('Line of Business'),
        str(row.get('Phone No'))[:20] if row.get('Phone No') else None,
        row.get('Web Address (URL)'),
        sector,  # sector_category
        row.get('Manufacturing Indicator') == 'Manufacturer',
        row.get('Minority Owned Indicator') == 'Yes',
        row.get('source_file'),
    ))

print(f"Records to insert: {len(records)}")
print(f"Skipped (no name): {skipped}")
print(f"Duplicates (already in DB): {duplicates}")

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

conn.commit()
print(f"Inserted {cur.rowcount} records")

# Verify by sector
print("\n" + "=" * 60)
print("SECTOR DISTRIBUTION")
print("=" * 60)

cur.execute("""
    SELECT sector_category, COUNT(*),
           SUM(employees_site) as total_employees,
           COUNT(CASE WHEN ein IS NOT NULL THEN 1 END) as with_ein
    FROM mergent_employers
    GROUP BY sector_category
    ORDER BY COUNT(*) DESC
""")

print(f"\n{'Sector':<25} {'Count':>8} {'Employees':>12} {'With EIN':>10}")
print("-" * 60)
for row in cur.fetchall():
    emp = f"{row[2]:,}" if row[2] else "N/A"
    print(f"{row[0] or 'NULL':<25} {row[1]:>8,} {emp:>12} {row[3]:>10,}")

# Get total counts
cur.execute("SELECT COUNT(*), SUM(employees_site) FROM mergent_employers")
total, total_emp = cur.fetchone()
print(f"\n{'TOTAL':<25} {total:>8,} {total_emp:>12,}")

cur.close()
conn.close()

print("\n" + "=" * 60)
print("LOAD COMPLETE")
print("=" * 60)
