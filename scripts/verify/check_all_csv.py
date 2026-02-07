"""Check all Mergent CSV files for NAICS distribution"""
import pandas as pd
import os

base_path = r"C:\Users\jakew\Downloads\labor-data-project\AFSCME case example NY"
files = [
    "1_2000_other_industries_advancesearch18488938096983ac1794e51.csv",
    "2001_4000_other_industries_advancesearch8908858966983ac4faff74.csv",
    "4001_6000_other_industries_advancesearch5505435806983ac81d50bb.csv",
    "6001_8000_other_industries_advancesearch10671607656983ace3e6154.csv",
    "8001_10000_other_industries_advancesearch18620684906983ad182ec58.csv",
    "10001_12000_other_industries_advancesearch18312885316983ad6c0726f.csv",
    "12001_14000_other_industries_advancesearch19488114456983adce287fa.csv",
]

all_dfs = []
for fname in files:
    fpath = os.path.join(base_path, fname)
    df = pd.read_excel(fpath, engine='openpyxl')
    df['source_file'] = fname
    all_dfs.append(df)
    print(f"{fname}: {len(df)} rows")

combined = pd.concat(all_dfs, ignore_index=True)
print(f"\n=== TOTAL: {len(combined)} rows ===")

# Check for duplicates by DUNS
dups = combined.duplicated(subset=['D-U-N-S@ Number'], keep=False)
print(f"Duplicate DUNS entries: {dups.sum()}")
print(f"Unique employers: {combined['D-U-N-S@ Number'].nunique()}")

# NAICS distribution
print("\n=== NAICS 3-digit prefixes ===")
combined['naics_3'] = combined['Primary NAICS Code'].astype(str).str[:3]
naics_dist = combined['naics_3'].value_counts()
print(naics_dist)

print("\n\n=== Mapping to Sector Categories ===")
sector_map = {
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
}

combined['sector_category'] = combined['naics_3'].map(sector_map).fillna('OTHER')
sector_dist = combined['sector_category'].value_counts()
print(sector_dist)

# Check EIN coverage
ein_count = combined['Employer ID Number (EIN)'].notna().sum()
print(f"\n=== EIN Coverage: {ein_count}/{len(combined)} ({100*ein_count/len(combined):.1f}%) ===")

# Check employee data
emp_count = combined['Employee this Site'].notna().sum()
print(f"Employee count coverage: {emp_count}/{len(combined)} ({100*emp_count/len(combined):.1f}%)")
