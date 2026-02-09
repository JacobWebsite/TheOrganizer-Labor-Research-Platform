import os
"""
CHECKPOINT 2: Load FLRA Federal Bargaining Unit Data
FIXED: Use auto-generated ID since source ID is per-agency, not per-unit
"""

import psycopg2
import pandas as pd
import re

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 2: Loading FLRA Federal Bargaining Unit Data")
print("=" * 80)

# Load CSV
csv_path = r"C:\Users\jakew\Downloads\federal workers and contracts_OPM.csv"
df = pd.read_csv(csv_path, low_memory=False, encoding='utf-8')
print(f"\nLoaded {len(df):,} records from CSV")
print(f"Unique agency IDs: {df['ID'].nunique()}")
print(f"(Each agency can have multiple unions = multiple bargaining units)")

# Clean data functions
def clean_int(val):
    if pd.isna(val) or val == '' or val == 'None':
        return None
    try:
        return int(float(val))
    except:
        return None

def clean_str(val, max_len=None):
    if pd.isna(val) or str(val).strip() == 'None':
        return None
    result = str(val).strip()
    if max_len and len(result) > max_len:
        result = result[:max_len]
    return result if result else None

def clean_bool(val):
    if pd.isna(val):
        return False
    return str(val).lower() in ('yes', 'true', '1')

def normalize_agency_name(name):
    if not name:
        return None
    name = str(name).upper().strip()
    name = re.sub(r'^DEPARTMENT OF THE\s+', 'DEPARTMENT OF ', name)
    name = re.sub(r'^DEPT\.?\s+OF\s+', 'DEPARTMENT OF ', name)
    return name

# Recreate table with SERIAL primary key
print("\n--- Recreating table with auto-increment ID ---")
cur.execute("DROP TABLE IF EXISTS federal_bargaining_units CASCADE;")
cur.execute("""
CREATE TABLE federal_bargaining_units (
    unit_id SERIAL PRIMARY KEY,
    source_agency_id INTEGER,
    bus_code VARCHAR(10),
    cpdf_code VARCHAR(10),
    agency_name VARCHAR(255),
    sub_agency VARCHAR(255),
    activity VARCHAR(500),
    unit_description TEXT,
    unit_history TEXT,
    union_acronym VARCHAR(20),
    union_name VARCHAR(255),
    local_number VARCHAR(100),
    affiliation VARCHAR(255),
    olms_file_number VARCHAR(20),
    year_recognized INTEGER,
    is_national_exclusive BOOLEAN DEFAULT FALSE,
    is_consolidated_unit BOOLEAN DEFAULT FALSE,
    is_non_appropriated_fund BOOLEAN DEFAULT FALSE,
    blue_collar_employees INTEGER DEFAULT 0,
    white_collar_employees INTEGER DEFAULT 0,
    non_professional_employees INTEGER DEFAULT 0,
    total_in_unit INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
""")
cur.execute("CREATE INDEX idx_fed_bu_cpdf ON federal_bargaining_units(cpdf_code);")
cur.execute("CREATE INDEX idx_fed_bu_union ON federal_bargaining_units(union_acronym);")
cur.execute("CREATE INDEX idx_fed_bu_olms ON federal_bargaining_units(olms_file_number);")
cur.execute("CREATE INDEX idx_fed_bu_agency ON federal_bargaining_units(agency_name);")
cur.execute("CREATE INDEX idx_fed_bu_source_id ON federal_bargaining_units(source_agency_id);")
print("  [OK] Table recreated with auto-increment ID")

# Clear and reload agencies
cur.execute("DELETE FROM federal_agencies;")
cur.execute("ALTER SEQUENCE federal_agencies_agency_id_seq RESTART WITH 1;")

# ============================================================================
# STEP 1: Load Agencies
# ============================================================================
print("\n--- Step 1: Loading Federal Agencies ---")

agency_data = df.groupby('CpdfCode').agg({
    'Agency': 'first',
    'SubAgency': 'first', 
    'TotalInBargainingUnit': 'sum',
    'ID': 'count'
}).reset_index()

insert_agency_sql = """
    INSERT INTO federal_agencies 
    (cpdf_code, agency_name, agency_name_normalized, sub_agency, total_employees, total_bargaining_units)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (cpdf_code) DO UPDATE SET
        total_employees = EXCLUDED.total_employees,
        total_bargaining_units = EXCLUDED.total_bargaining_units,
        updated_at = NOW();
"""

agency_count = 0
for _, row in agency_data.iterrows():
    cpdf = clean_str(row['CpdfCode'])
    name = clean_str(row['Agency'])
    if cpdf and name:
        cur.execute(insert_agency_sql, (
            cpdf,
            name,
            normalize_agency_name(name),
            clean_str(row['SubAgency']),
            clean_int(row['TotalInBargainingUnit']),
            clean_int(row['ID'])
        ))
        agency_count += 1

print(f"  [OK] Loaded {agency_count} unique federal agencies")

# ============================================================================
# STEP 2: Load Bargaining Units
# ============================================================================
print("\n--- Step 2: Loading Bargaining Units ---")

insert_unit_sql = """
    INSERT INTO federal_bargaining_units (
        source_agency_id, bus_code, cpdf_code, agency_name, sub_agency, activity,
        unit_description, unit_history, union_acronym, union_name, local_number,
        affiliation, olms_file_number, year_recognized, is_national_exclusive,
        is_consolidated_unit, is_non_appropriated_fund, blue_collar_employees,
        white_collar_employees, non_professional_employees, total_in_unit, status
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    );
"""

unit_count = 0
error_count = 0
total_workers = 0

for idx, row in df.iterrows():
    try:
        olms_num = clean_str(row.get('OlmrNumber'))
        if olms_num:
            olms_num = re.sub(r'[^\d]', '', str(olms_num))
            if not olms_num:
                olms_num = None
        
        workers = clean_int(row.get('TotalInBargainingUnit')) or 0
        total_workers += workers
            
        cur.execute(insert_unit_sql, (
            clean_int(row.get('ID')),  # source_agency_id
            clean_str(row.get('BusCode'), 10),
            clean_str(row.get('CpdfCode'), 10),
            clean_str(row.get('Agency'), 255),
            clean_str(row.get('SubAgency'), 255),
            clean_str(row.get('Activity'), 500),
            clean_str(row.get('UnitDescription')),
            clean_str(row.get('UnitHistory')),
            clean_str(row.get('UnionAcronym'), 20),
            clean_str(row.get('UnionName'), 255),
            clean_str(row.get('Local'), 100),
            clean_str(row.get('Affiliation'), 255),
            olms_num,
            clean_int(row.get('YearRecognized')),
            clean_bool(row.get('NationalExclusive')),
            clean_bool(row.get('ConsolidatedUnit')),
            clean_bool(row.get('NonAppropriatedFunding')),
            clean_int(row.get('BlueCollarEmployees')),
            clean_int(row.get('WhiteCollarEmployees')),
            clean_int(row.get('NonProfessionalEmployees')),
            workers,
            clean_str(row.get('Status'), 20) or 'Active'
        ))
        unit_count += 1
        
        if unit_count % 500 == 0:
            print(f"  ... loaded {unit_count:,} units")
            
    except Exception as e:
        error_count += 1
        if error_count <= 5:
            print(f"  [ERR] Row {idx}: {str(e)[:80]}")

print(f"  [OK] Loaded {unit_count:,} bargaining units ({error_count} errors)")

# ============================================================================
# STEP 3: Summary Statistics
# ============================================================================
print("\n" + "=" * 80)
print("LOAD SUMMARY")
print("=" * 80)

cur.execute("SELECT COUNT(*) FROM federal_agencies;")
print(f"\nFederal Agencies: {cur.fetchone()[0]:,}")

cur.execute("SELECT COUNT(*) FROM federal_bargaining_units;")
bu_count = cur.fetchone()[0]
print(f"Bargaining Units: {bu_count:,}")

cur.execute("SELECT COALESCE(SUM(total_in_unit), 0) FROM federal_bargaining_units;")
total = cur.fetchone()[0]
print(f"Total Workers: {total:,}")

# By union
cur.execute("""
    SELECT union_acronym, COUNT(*) as units, COALESCE(SUM(total_in_unit), 0) as workers
    FROM federal_bargaining_units
    WHERE union_acronym IS NOT NULL
    GROUP BY union_acronym
    ORDER BY workers DESC
    LIMIT 15;
""")
print("\nTop 15 Unions by Workers:")
print(f"  {'Union':<12} {'Units':>7} {'Workers':>12}")
print("  " + "-" * 35)
for row in cur.fetchall():
    print(f"  {row[0]:<12} {row[1]:>7,} {row[2]:>12,}")

# By agency (consolidated)
cur.execute("""
    SELECT 
        CASE 
            WHEN agency_name ILIKE '%ARMY%' THEN 'DEPARTMENT OF THE ARMY'
            WHEN agency_name ILIKE '%NAVY%' THEN 'DEPARTMENT OF THE NAVY'
            WHEN agency_name ILIKE '%AIR FORCE%' THEN 'DEPARTMENT OF THE AIR FORCE'
            WHEN agency_name ILIKE '%VETERAN%' THEN 'DEPARTMENT OF VETERANS AFFAIRS'
            ELSE UPPER(agency_name)
        END as agency_normalized,
        COUNT(*) as units,
        COALESCE(SUM(total_in_unit), 0) as workers
    FROM federal_bargaining_units
    GROUP BY 1
    ORDER BY workers DESC
    LIMIT 15;
""")
print("\nTop 15 Agencies by Workers:")
print(f"  {'Agency':<45} {'Units':>6} {'Workers':>10}")
print("  " + "-" * 65)
for row in cur.fetchall():
    name = (row[0] or 'Unknown')[:45]
    print(f"  {name:<45} {row[1]:>6,} {row[2]:>10,}")

# OLMS linkage
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(olms_file_number) as with_olms
    FROM federal_bargaining_units;
""")
row = cur.fetchone()
pct = row[1]/row[0]*100 if row[0] > 0 else 0
print(f"\nOLMS Linkage Status:")
print(f"  With OLMS file number: {row[1]:,} ({pct:.1f}%)")
print(f"  Without OLMS number:   {row[0]-row[1]:,} ({100-pct:.1f}%)")

# Largest units
cur.execute("""
    SELECT agency_name, union_acronym, total_in_unit, olms_file_number
    FROM federal_bargaining_units
    WHERE total_in_unit > 0
    ORDER BY total_in_unit DESC
    LIMIT 10;
""")
print("\nTop 10 Largest Bargaining Units:")
print(f"  {'Agency':<35} {'Union':<8} {'Workers':>10}")
print("  " + "-" * 60)
for row in cur.fetchall():
    print(f"  {(row[0] or 'Unknown')[:35]:<35} {row[1] or 'N/A':<8} {row[2] or 0:>10,}")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 2 COMPLETE")
print("=" * 80)
print(f"""
Data loaded:
  - {agency_count} federal agencies
  - {unit_count:,} bargaining units
  - {total_workers:,} federal workers covered

Next: Type 'continue checkpoint 3' to create OLMS linkages
""")
