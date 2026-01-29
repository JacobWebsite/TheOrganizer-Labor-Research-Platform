"""
CHECKPOINT 1: Execute Schema Creation - Run full SQL file
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear", 
    user="postgres",
    password="Juniordog33!"
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 1: Creating Federal Public Sector Schema")
print("=" * 80)

# Execute statements directly
print("\n--- Creating Tables ---")

# 1. Drop existing
cur.execute("DROP TABLE IF EXISTS federal_bargaining_units CASCADE;")
cur.execute("DROP TABLE IF EXISTS federal_agencies CASCADE;")
cur.execute("DROP TABLE IF EXISTS flra_olms_union_map CASCADE;")
print("  [OK] Dropped existing tables")

# 2. Create federal_agencies
cur.execute("""
CREATE TABLE federal_agencies (
    agency_id SERIAL PRIMARY KEY,
    cpdf_code VARCHAR(10) UNIQUE,
    agency_name VARCHAR(255) NOT NULL,
    agency_name_normalized VARCHAR(255),
    sub_agency VARCHAR(255),
    sector_code VARCHAR(30) DEFAULT 'FEDERAL',
    governing_law VARCHAR(100) DEFAULT 'Federal Service Labor-Management Relations Act (FSLMRA)',
    total_employees INTEGER DEFAULT 0,
    total_bargaining_units INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
""")
print("  [OK] Created table: federal_agencies")

# 3. Create federal_bargaining_units
cur.execute("""
CREATE TABLE federal_bargaining_units (
    unit_id INTEGER PRIMARY KEY,
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
print("  [OK] Created table: federal_bargaining_units")

# 4. Create indexes
cur.execute("CREATE INDEX idx_fed_bu_cpdf ON federal_bargaining_units(cpdf_code);")
cur.execute("CREATE INDEX idx_fed_bu_union ON federal_bargaining_units(union_acronym);")
cur.execute("CREATE INDEX idx_fed_bu_olms ON federal_bargaining_units(olms_file_number);")
cur.execute("CREATE INDEX idx_fed_bu_agency ON federal_bargaining_units(agency_name);")
cur.execute("CREATE INDEX idx_fed_bu_status ON federal_bargaining_units(status);")
cur.execute("CREATE INDEX idx_fed_agencies_cpdf ON federal_agencies(cpdf_code);")
print("  [OK] Created indexes")

# 5. Create union mapping table
cur.execute("""
CREATE TABLE flra_olms_union_map (
    flra_acronym VARCHAR(20) PRIMARY KEY,
    olms_aff_abbr VARCHAR(20),
    union_name VARCHAR(255),
    notes TEXT
);
""")
print("  [OK] Created table: flra_olms_union_map")

# 6. Insert union mappings
mappings = [
    ('AFGE', 'AFGE', 'American Federation of Government Employees', 'Largest federal union'),
    ('NTEU', 'NTEU', 'National Treasury Employees Union', 'IRS and Treasury'),
    ('NFFE', 'NFFE', 'National Federation of Federal Employees', 'IAM affiliate'),
    ('NAGE', 'NAGE', 'National Association of Government Employees', 'SEIU affiliate'),
    ('AFSCME', 'AFSCME', 'American Federation of State County and Municipal Employees', None),
    ('NALC', 'NALC', 'National Association of Letter Carriers', 'Postal'),
    ('APWU', 'APWU', 'American Postal Workers Union', 'Postal'),
    ('NPMHU', 'NPMHU', 'National Postal Mail Handlers Union', 'LIUNA affiliate'),
    ('NATCA', 'NATCA', 'National Air Traffic Controllers Association', 'Air traffic'),
    ('PASS', 'PASS', 'Professional Aviation Safety Specialists', 'FAA'),
    ('AFSA', 'AFSA', 'American Foreign Service Association', 'State Dept'),
    ('IFPTE', 'IFPTE', 'International Federation of Professional and Technical Engineers', None),
    ('NNU', 'NNU', 'National Nurses United', 'VA nurses'),
    ('IAMAW', 'IAM', 'International Association of Machinists', None),
    ('LIUNA', 'LIUNA', 'Laborers International Union', None),
    ('IBEW', 'IBEW', 'International Brotherhood of Electrical Workers', None),
    ('IUOE', 'IUOE', 'International Union of Operating Engineers', None),
    ('PPF', 'PPF', 'Plumbers and Pipefitters', None),
    ('SMW', 'SMART', 'Sheet Metal Workers', None),
    ('UBC', 'UBC', 'United Brotherhood of Carpenters', None),
    ('BBF', 'BBF', 'Boilermakers', None),
    ('FOP', 'FOP', 'Fraternal Order of Police', 'Federal police'),
    ('IAFF', 'IAFF', 'International Association of Fire Fighters', 'Federal fire'),
    ('SEIU', 'SEIU', 'Service Employees International Union', None),
    ('IBT', 'IBT', 'International Brotherhood of Teamsters', None),
    ('ACT', 'ACT', 'Association of Civilian Technicians', 'National Guard technicians'),
    ('MTC', 'MTC', 'Metal Trades Council', 'Navy yards/shipyards'),
    ('PESO', 'PESO', 'Professional and Scientific Employees Organization', None),
    ('OPEIU', 'OPEIU', 'Office and Professional Employees International Union', None),
]

cur.executemany("""
    INSERT INTO flra_olms_union_map (flra_acronym, olms_aff_abbr, union_name, notes)
    VALUES (%s, %s, %s, %s);
""", mappings)
print(f"  [OK] Loaded {len(mappings)} union mappings")

# Verify
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('federal_agencies', 'federal_bargaining_units', 'flra_olms_union_map')
    ORDER BY table_name;
""")
tables = cur.fetchall()

print("\nTables created:")
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t[0]};")
    count = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM information_schema.columns WHERE table_name = '{t[0]}';")
    col_count = cur.fetchone()[0]
    print(f"  - {t[0]}: {col_count} columns, {count} rows")

print("\nKey Union Mappings:")
cur.execute("""
    SELECT flra_acronym, olms_aff_abbr 
    FROM flra_olms_union_map 
    WHERE flra_acronym IN ('AFGE','NTEU','NFFE','NAGE','NATCA','SEIU')
    ORDER BY flra_acronym;
""")
for row in cur.fetchall():
    print(f"  {row[0]:10} -> {row[1]}")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 1 COMPLETE")
print("=" * 80)
print("""
Schema ready:
  - federal_agencies: Will hold ~100 federal agencies as employers
  - federal_bargaining_units: Will hold 5,291 FLRA bargaining units  
  - flra_olms_union_map: 29 union acronym mappings (FLRA -> OLMS)

Next: Type 'continue checkpoint 2' to load the FLRA data
""")
