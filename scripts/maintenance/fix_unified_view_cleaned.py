import os
"""
Fix unified view to use cleaned private sector data
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("FIXING UNIFIED VIEW - Using Cleaned Private Sector Data")
print("=" * 80)

# Check the cleaned view structure
print("\n--- Checking v_f7_private_sector_cleaned ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'v_f7_private_sector_cleaned'
    ORDER BY ordinal_position;
""")
print("Columns:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check counts
cur.execute("SELECT COUNT(*), SUM(reconciled_workers) FROM v_f7_private_sector_cleaned;")
row = cur.fetchone()
print(f"\nCleaned private sector: {row[0]:,} employers, {row[1] or 0:,.0f} workers")

# Drop and recreate views
print("\n--- Recreating unified views ---")
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")

# Create unified view using CLEANED private sector
cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (from CLEANED F-7 data)
SELECT 
    'PVT-' || employer_id as unified_id,
    employer_name,
    city as sub_employer,
    NULL::text as location_description,
    'PRIVATE_EMPLOYER' as employer_type,
    'PRIVATE' as sector_code,
    state,
    NULL::numeric as lat,
    NULL::numeric as lon,
    affiliation as union_acronym,
    NULL::text as union_name,
    NULL::text as local_number,
    NULL::text as f_num,
    reconciled_workers::integer as workers_covered,
    NULL::integer as year_recognized,
    FALSE as is_consolidated_unit,
    'National Labor Relations Act (NLRA)' as governing_law,
    'F-7' as data_source
FROM v_f7_private_sector_cleaned

UNION ALL

-- Public sector employers (federal)
SELECT 
    employer_id as unified_id,
    employer_name,
    sub_agency as sub_employer,
    location_description,
    employer_type,
    sector_code,
    state,
    lat,
    lon,
    union_acronym,
    union_name,
    local_number,
    f_num,
    workers_covered,
    year_recognized,
    is_consolidated_unit,
    governing_law,
    data_source
FROM public_sector_employers;
""")
print("  [OK] Created all_employers_unified (using cleaned data)")

# Create sector_summary
cur.execute("""
CREATE VIEW sector_summary AS
SELECT 
    sector_code,
    COUNT(*) as employer_count,
    COUNT(DISTINCT employer_name) as unique_employers,
    COALESCE(SUM(workers_covered), 0) as total_workers,
    COUNT(DISTINCT union_acronym) as union_count
FROM all_employers_unified
GROUP BY sector_code;
""")
print("  [OK] Created sector_summary")

# Create union_sector_coverage
cur.execute("""
CREATE VIEW union_sector_coverage AS
SELECT 
    union_acronym,
    sector_code,
    COUNT(*) as employer_count,
    COALESCE(SUM(workers_covered), 0) as workers_covered
FROM all_employers_unified
WHERE union_acronym IS NOT NULL
GROUP BY union_acronym, sector_code
ORDER BY union_acronym, sector_code;
""")
print("  [OK] Created union_sector_coverage")

# Verify results
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print("\nSector Summary (CORRECTED):")
print(f"  {'Sector':<10} {'Employers':>12} {'Unique':>10} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 60)
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>12,} {row[2]:>10,} {row[3]:>14,} {row[4]:>8}")

# Compare to BLS benchmark
print("\n--- Comparison to BLS Benchmark ---")
print("  BLS 2024 private sector union members: ~7.2 million")
print("  BLS 2024 federal sector union members: ~1.1 million")

conn.close()
print("\n[DONE] Views fixed - restart API to see changes")
