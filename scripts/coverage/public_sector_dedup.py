import psycopg2

conn = psycopg2.connect(
    host="localhost", 
    dbname="olms_multiyear", 
    user="postgres", 
    password="Juniordog33!"
)
cur = conn.cursor()

print("=" * 80)
print("DEDUPLICATED PUBLIC SECTOR MEMBERSHIP ANALYSIS")
print("=" * 80)

# Get NHQ-level counts (avoid double-counting)
print("\nMethod: Use National Headquarters filings only")
print("=" * 80)

# Federal unions - take DC headquarters
cur.execute("""
    SELECT aff_abbr, COALESCE(members,0) as members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr IN ('AFGE','APWU','NALC','NFFE','NTEU','NPMHU')
    AND (unit_name IS NULL OR unit_name = '')
    ORDER BY members DESC;
""")

print("\n1. FEDERAL EMPLOYEES (NHQ only):")
print("-" * 50)
fed_dedup = 0
for row in cur.fetchall():
    print(f"   {row[0]:10} {row[1]:>12,.0f}")
    fed_dedup += row[1]
print(f"   {'SUBTOTAL':10} {fed_dedup:>12,.0f}")

# Teachers - NEA national
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'NEA'
    AND (unit_name IS NULL OR unit_name = '');
""")
nea_nhq = cur.fetchone()[0] or 0

# Teachers - AFT national
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'AFT'
    AND (unit_name IS NULL OR unit_name = '');
""")
aft_nhq = cur.fetchone()[0] or 0

print("\n2. TEACHERS (NHQ only):")
print("-" * 50)
print(f"   NEA:        {nea_nhq:>12,.0f}")
print(f"   AFT:        {aft_nhq:>12,.0f}")
print(f"   Raw total:  {nea_nhq + aft_nhq:>12,.0f}")
# ~900K are dual NEA/AFT members
overlap = 900000
teacher_adjusted = nea_nhq + aft_nhq - overlap
print(f"   Overlap:    {-overlap:>12,.0f} (est. dual members)")
print(f"   SUBTOTAL:   {teacher_adjusted:>12,.0f}")

# AFSCME - DC headquarters
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'AFSCME'
    AND (unit_name IS NULL OR unit_name = '');
""")
afscme_nhq = cur.fetchone()[0] or 0

print("\n3. AFSCME (NHQ only):")
print("-" * 50)
print(f"   AFSCME:     {afscme_nhq:>12,.0f}")

# IAFF - DC headquarters
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'IAFF'
    AND (unit_name IS NULL OR unit_name = '');
""")
iaff_nhq = cur.fetchone()[0] or 0

print("\n4. IAFF - Firefighters (NHQ only):")
print("-" * 50)
print(f"   IAFF:       {iaff_nhq:>12,.0f}")

# FOP - independent locals (sum all)
cur.execute("""
    SELECT COALESCE(SUM(members),0) FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'FOP';
""")
fop_total = cur.fetchone()[0] or 0

# FOP is complicated - national reports 373K but locals add more
# Let's just use national
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND aff_abbr = 'FOP'
    AND union_name LIKE '%NATIONAL%'
    LIMIT 1;
""")
fop_result = cur.fetchone()
fop_nhq = fop_result[0] if fop_result else fop_total

print("\n5. FOP - Police (NHQ):")
print("-" * 50)
print(f"   FOP:        {fop_nhq:>12,.0f}")

# SEIU - ~40% are public sector
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'SEIU'
    AND (unit_name IS NULL OR unit_name = '');
""")
seiu_nhq = cur.fetchone()[0] or 0
seiu_public = int(seiu_nhq * 0.40)

print("\n6. SEIU (Public portion ~40%):")
print("-" * 50)
print(f"   SEIU Total: {seiu_nhq:>12,.0f}")
print(f"   Public est: {seiu_public:>12,.0f}")

# CWA - ~25% public sector
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'CWA'
    AND (unit_name IS NULL OR unit_name = '');
""")
cwa_nhq = cur.fetchone()[0] or 0
cwa_public = int(cwa_nhq * 0.25)

print("\n7. CWA (Public portion ~25%):")
print("-" * 50)
print(f"   CWA Total:  {cwa_nhq:>12,.0f}")
print(f"   Public est: {cwa_public:>12,.0f}")

# ATU - Transit (mostly public)
cur.execute("""
    SELECT COALESCE(members,0) FROM lm_data
    WHERE yr_covered = 2024 
    AND state = 'DC'
    AND aff_abbr = 'ATU'
    AND (unit_name IS NULL OR unit_name = '');
""")
atu_result = cur.fetchone()
atu_nhq = atu_result[0] if atu_result else 0

# Try alternate lookup
if atu_nhq == 0:
    cur.execute("""
        SELECT COALESCE(SUM(members),0) FROM lm_data
        WHERE yr_covered = 2024 AND aff_abbr = 'ATU';
    """)
    atu_nhq = cur.fetchone()[0] or 0
    atu_nhq = int(atu_nhq * 0.5)  # Rough dedup

print("\n8. ATU - Transit Workers (~85% public):")
print("-" * 50)
print(f"   ATU:        {atu_nhq:>12,.0f}")

# Now calculate total
print("\n" + "=" * 80)
print("SUMMARY: OLMS PUBLIC SECTOR COVERAGE")
print("=" * 80)

total = fed_dedup + teacher_adjusted + afscme_nhq + iaff_nhq + fop_nhq + seiu_public + cwa_public + atu_nhq

print(f"""
CATEGORY                    MEMBERS
--------------------------------------------
Federal employees:      {fed_dedup:>12,.0f}
Teachers (adj.):        {teacher_adjusted:>12,.0f}
AFSCME:                 {afscme_nhq:>12,.0f}
IAFF (Firefighters):    {iaff_nhq:>12,.0f}
FOP (Police):           {fop_nhq:>12,.0f}
SEIU (public portion):  {seiu_public:>12,.0f}
CWA (public portion):   {cwa_public:>12,.0f}
ATU (Transit):          {atu_nhq:>12,.0f}
============================================
TOTAL IN OLMS:          {total:>12,.0f}

BLS BENCHMARK:              7,000,000
--------------------------------------------
COVERAGE RATIO:             {total/7000000*100:.1f}%
GAP:                    {7000000 - total:>12,.0f}
""")

# What employers do we have?
print("=" * 80)
print("EMPLOYER DATA STATUS")
print("=" * 80)

# Check if we have F-7 employers for public sector unions
cur.execute("""
    SELECT COUNT(DISTINCT employer_name) 
    FROM employers_deduped;
""")
result = cur.fetchone()
f7_employers = result[0] if result else 0

print(f"""
F-7 Employer Records:       {f7_employers:>12,.0f}
  - These are PRIVATE SECTOR only (NLRA)
  
PUBLIC SECTOR EMPLOYERS:              0
  - No F-7 equivalent for public sector
  - Federal agencies: Need FLRA data
  - State/local: Need state PERB data
  - Schools: Need NCES district data
""")

conn.close()
