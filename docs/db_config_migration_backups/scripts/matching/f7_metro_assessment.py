import os
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host='localhost', 
    port=5432, 
    database='olms_multiyear', 
    user='postgres', 
    password=os.environ.get('DB_PASSWORD', '')
)

print("="*100)
print("F-7 DATA ASSESSMENT FOR METRO/INDUSTRY ANALYSIS")
print("="*100)

# Check F7 employer table structure
print("\n1. F7 EMPLOYERS TABLE STRUCTURE")
print("-"*50)
cols = pd.read_sql("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers'
    ORDER BY ordinal_position
""", conn)
print(cols.to_string())

# Check geographic data completeness
print("\n\n2. GEOGRAPHIC DATA COMPLETENESS")
print("-"*50)
geo_stats = pd.read_sql("""
    SELECT 
        COUNT(*) as total_employers,
        COUNT(state) as has_state,
        COUNT(city) as has_city,
        COUNT(zip) as has_zip,
        COUNT(latitude) as has_geocode,
        COUNT(DISTINCT state) as unique_states
    FROM f7_employers
""", conn)
print(geo_stats.T.to_string())

# Check NAICS coverage
print("\n\n3. INDUSTRY (NAICS) DATA COMPLETENESS")
print("-"*50)
naics_stats = pd.read_sql("""
    SELECT 
        COUNT(*) as total,
        COUNT(naics) as has_naics,
        ROUND(100.0 * COUNT(naics) / COUNT(*), 1) as naics_pct,
        COUNT(DISTINCT naics) as unique_naics
    FROM f7_employers
""", conn)
print(naics_stats.T.to_string())

# NAICS distribution (if any)
print("\n\n4. NAICS CODE DISTRIBUTION (Top 20)")
print("-"*50)
naics_dist = pd.read_sql("""
    SELECT 
        COALESCE(naics, 'MISSING') as naics,
        COUNT(*) as employers,
        SUM(latest_unit_size) as total_workers
    FROM f7_employers
    GROUP BY naics
    ORDER BY employers DESC
    LIMIT 20
""", conn)
print(naics_dist.to_string())

# State distribution
print("\n\n5. TOP 15 STATES BY EMPLOYER COUNT")
print("-"*50)
state_dist = pd.read_sql("""
    SELECT 
        COALESCE(state, 'MISSING') as state,
        COUNT(*) as employers,
        SUM(latest_unit_size) as total_workers,
        COUNT(latitude) as geocoded
    FROM f7_employers
    GROUP BY state
    ORDER BY employers DESC
    LIMIT 15
""", conn)
print(state_dist.to_string())

# Check if we have county or CBSA data
print("\n\n6. EXISTING COUNTY/CBSA DATA CHECK")
print("-"*50)
try:
    cbsa = pd.read_sql("SELECT COUNT(*) FROM f7_employers WHERE cbsa_code IS NOT NULL", conn)
    print(f"Employers with CBSA code: {cbsa.iloc[0,0]}")
except:
    print("No CBSA code column exists yet")

try:
    county = pd.read_sql("SELECT COUNT(*) FROM f7_employers WHERE county_fips IS NOT NULL", conn)
    print(f"Employers with county FIPS: {county.iloc[0,0]}")
except:
    print("No county_fips column exists yet")

# Sample of geocoded employers
print("\n\n7. SAMPLE GEOCODED EMPLOYERS (for verification)")
print("-"*50)
sample = pd.read_sql("""
    SELECT employer_name, city, state, zip, latitude, longitude, naics
    FROM f7_employers
    WHERE latitude IS NOT NULL
    ORDER BY latest_unit_size DESC
    LIMIT 10
""", conn)
print(sample.to_string())

# Check ZIP code format
print("\n\n8. ZIP CODE FORMAT CHECK")
print("-"*50)
zip_check = pd.read_sql("""
    SELECT 
        LENGTH(zip) as zip_length,
        COUNT(*) as count
    FROM f7_employers
    WHERE zip IS NOT NULL
    GROUP BY LENGTH(zip)
    ORDER BY count DESC
""", conn)
print(zip_check.to_string())

conn.close()

print("\n\n" + "="*100)
print("RECOMMENDATIONS FOR METRO/INDUSTRY ENRICHMENT")
print("="*100)
print("""
PHASE 1: Add CBSA (Metro/Micro) Codes
--------------------------------------
Option A: Use ZIP-to-CBSA crosswalk (Census provides this)
  - Download: HUD USPS ZIP Code Crosswalk Files
  - URL: https://www.huduser.gov/portal/datasets/usps_crosswalk.html
  - Maps ZIP codes to CBSA, County, Tract

Option B: Use lat/long to CBSA (for geocoded records)  
  - Download CBSA shapefiles from Census TIGER
  - Point-in-polygon matching
  - More accurate than ZIP codes

PHASE 2: Enrich NAICS Codes
--------------------------------------
- F-7 forms should have employer industry - need to check raw data
- Can infer from employer name (e.g., "Ford Motor" = Manufacturing)
- Can match to other databases (SEC, D&B) via employer name

PHASE 3: Add Employment Denominators
--------------------------------------
- Download County Business Patterns by NAICS by County
- Aggregate to CBSA level
- Calculate: F7_workers / CBP_employment = coverage rate

PHASE 4: Integrate UnionStats MSA Data
--------------------------------------
- Already have UnionStats MSA files (1986-2024)
- Join by CBSA code for union density benchmarks
""")
