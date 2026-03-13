"""
Load ~14,000 D&B (Dun & Bradstreet) employers from Mergent Intellect export files
covering states AL through FL (Alabama, Alaska, Arizona, Arkansas, California,
Colorado, Connecticut, Delaware, District of Columbia, Florida).

Files are Excel (.xlsx) internally with .csv extensions, downloaded from Mergent
advanced search. Each file has ~2,000 employers sorted by revenue descending.
File 1 contains 27 FORTUNE-rank continuation rows (null Company Name) to skip.

Deduplicates by DUNS against existing mergent_employers records.
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
import os
import re

from db_config import get_connection

# ============================================================
# CONFIGURE: Source files
# ============================================================
BASE_PATH = r"C:\Users\jakew\Downloads"
FILE_PREFIX = "Alabama_to_florida_"

# Auto-discover files
FILES = sorted([f for f in os.listdir(BASE_PATH) if f.startswith(FILE_PREFIX) and f.endswith('.csv')])

# NAICS to sector mapping (same as existing loaders)
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
    """Clean EIN - remove non-numeric, zero-pad to 9 chars"""
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
    """Clean ZIP code - zero-pad to 5 digits, truncate 9-digit"""
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
    """Normalize company name for matching"""
    if not name or pd.isna(name):
        return None
    name = str(name).lower().strip()
    for suffix in [' llc', ' inc', ' corp', ' ltd', ' co', ' company', ' corporation',
                   ' incorporated', ' limited', '.', ',', '"', "'", ' the']:
        name = name.replace(suffix, '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_employees(val):
    """Parse employee count - strip commas"""
    if pd.isna(val) or val is None:
        return None
    try:
        val = str(val).replace(',', '')
        return int(float(val))
    except (ValueError, TypeError):
        return None


def parse_sales(val):
    """Parse sales amount - strip $ and commas, return numeric"""
    if pd.isna(val) or val is None:
        return None, None
    raw = str(val).strip()
    try:
        numeric = float(raw.replace('$', '').replace(',', ''))
        return numeric, raw
    except (ValueError, TypeError):
        return None, raw


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
print("LOADING D&B EMPLOYERS (AL-FL, ~14,000)")
print("=" * 60)

if not FILES:
    print(f"ERROR: No files found with prefix '{FILE_PREFIX}' in {BASE_PATH}")
    exit(1)

print(f"Found {len(FILES)} files:")
for f in FILES:
    print(f"  {f}")

# Load all files
all_dfs = []
for fname in FILES:
    fpath = os.path.join(BASE_PATH, fname)
    df = pd.read_excel(fpath, engine='openpyxl')
    df['source_file'] = fname
    all_dfs.append(df)
    null_names = df['Company Name'].isna().sum()
    real = len(df) - null_names
    print(f"  Loaded {fname}: {len(df)} rows ({null_names} rank-only, {real} employers)")

combined = pd.concat(all_dfs, ignore_index=True)
print(f"\nTotal rows from files: {len(combined)}")

# Database connection
conn = get_connection()
cur = conn.cursor()

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
state_counts = {}

for idx, row in combined.iterrows():
    company_name = row.get('Company Name')
    if not company_name or pd.isna(company_name):
        skipped_no_name += 1
        continue

    duns = clean_duns(row.get('D-U-N-S@ Number'))

    # Skip if DUNS already exists in DB or current batch
    if duns and duns in existing_duns:
        skipped_dups += 1
        continue

    # Track this DUNS to avoid duplicates within this load
    if duns:
        existing_duns.add(duns)

    naics_primary = row.get('Primary NAICS Code')
    sector = get_sector(naics_primary)
    state = clean_state(row.get('Physical State'))

    sector_counts[sector] = sector_counts.get(sector, 0) + 1
    if state:
        state_counts[state] = state_counts.get(state, 0) + 1

    sales_amount, sales_raw = parse_sales(row.get('Sales'))

    records.append((
        duns,
        clean_ein(row.get('Employer ID Number (EIN)')),
        clean_duns(row.get('Global Duns No')),
        clean_duns(row.get('Immediate Parent Duns No')),
        row.get('Immediate Parent Name') if pd.notna(row.get('Immediate Parent Name')) else None,
        clean_duns(row.get('Domestic Parent Duns No')),
        row.get('Domestic Parent Name') if pd.notna(row.get('Domestic Parent Name')) else None,
        str(company_name).strip(),
        normalize_name(company_name),
        str(row.get('Trade Style')).strip() if pd.notna(row.get('Trade Style')) else None,
        str(row.get('Former Name')).strip() if pd.notna(row.get('Former Name')) else None,
        str(row.get('Company Type')).strip() if pd.notna(row.get('Company Type')) else None,
        str(row.get('Subsidiary Status')).strip() if pd.notna(row.get('Subsidiary Status')) else None,
        str(row.get('Location Type')).strip() if pd.notna(row.get('Location Type')) else None,
        str(row.get('Physical Address'))[:500] if pd.notna(row.get('Physical Address')) else None,
        str(row.get('Physical City'))[:100] if pd.notna(row.get('Physical City')) else None,
        state,
        clean_zip(row.get('Physical Zipcode')),
        str(row.get('Physical County'))[:100] if pd.notna(row.get('Physical County')) else None,
        float(row.get('Latitude')) if pd.notna(row.get('Latitude')) else None,
        float(row.get('Longtitude')) if pd.notna(row.get('Longtitude')) else None,
        str(row.get('Mailing Address'))[:500] if pd.notna(row.get('Mailing Address')) else None,
        str(row.get('Mailing City'))[:100] if pd.notna(row.get('Mailing City')) else None,
        clean_state(row.get('Mailing State')),
        clean_zip(row.get('Mailing Zipcode')),
        parse_employees(row.get('Employee this Site')),
        parse_employees(row.get('Employee All Sites')),
        sales_amount,
        sales_raw,
        int(float(row.get('Year of Founding'))) if pd.notna(row.get('Year of Founding')) else None,
        str(int(float(naics_primary)))[:6] if pd.notna(naics_primary) else None,
        str(row.get('Primary NAICS Description')).strip() if pd.notna(row.get('Primary NAICS Description')) else None,
        str(row.get('Secondary NAICS Code'))[:20] if pd.notna(row.get('Secondary NAICS Code')) else None,
        str(row.get('Secondary NAICS Description')).strip() if pd.notna(row.get('Secondary NAICS Description')) else None,
        str(row.get('Line of Business')).strip() if pd.notna(row.get('Line of Business')) else None,
        str(row.get('Phone No'))[:20] if pd.notna(row.get('Phone No')) else None,
        str(row.get('Web Address (URL)')).strip() if pd.notna(row.get('Web Address (URL)')) else None,
        sector,
        row.get('Manufacturing Indicator') == 'Manufacturer',
        row.get('Minority Owned Indicator') == 'Yes',
        row.get('source_file'),
    ))

print(f"\nRecords to insert: {len(records)}")
print(f"Skipped (null Company Name / rank rows): {skipped_no_name}")
print(f"Skipped (DUNS already in DB): {skipped_dups}")

# Insert records
if records:
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
            naics_secondary, naics_secondary_desc,
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
else:
    inserted = 0
    print("No records to insert.")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("STATE DISTRIBUTION (NEW RECORDS)")
print("=" * 60)
print(f"\n{'State':<8} {'Count':>8}")
print("-" * 18)
for st, count in sorted(state_counts.items(), key=lambda x: -x[1]):
    print(f"{st:<8} {count:>8,}")

print("\n" + "=" * 60)
print("SECTOR DISTRIBUTION (NEW RECORDS)")
print("=" * 60)
print(f"\n{'Sector':<30} {'Count':>8}")
print("-" * 40)
for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
    print(f"{sector:<30} {count:>8,}")

# Final DB totals
print("\n" + "=" * 60)
print("FINAL DATABASE TOTALS")
print("=" * 60)

cur.execute("SELECT COUNT(*) FROM mergent_employers")
total = cur.fetchone()[0]
print(f"Total mergent_employers: {total:,}")

cur.execute("""
    SELECT state, COUNT(*) FROM mergent_employers
    WHERE state IN ('AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL')
    GROUP BY state ORDER BY COUNT(*) DESC
""")
print(f"\nAL-FL state breakdown:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

cur.close()
conn.close()

print("\n" + "=" * 60)
print("LOAD COMPLETE")
print("Next steps:")
print("  1. PYTHONPATH=. py scripts/etl/build_crosswalk.py")
print("  2. py scripts/etl/seed_master_from_sources.py --source mergent")
print("  3. Rebuild MVs (see CLAUDE.md for order)")
print("=" * 60)
