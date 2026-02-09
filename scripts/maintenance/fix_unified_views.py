import os
"""
Fix the unified view to use the correct private sector source
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
print("FIXING UNIFIED VIEWS")
print("=" * 80)

# Check current unified view
cur.execute("SELECT sector_code, COUNT(*), SUM(workers_covered) FROM all_employers_unified GROUP BY sector_code;")
print("\nCurrent all_employers_unified:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,} records, {row[2] or 0:,} workers")

# Check v_f7_private_sector_cleaned columns
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'v_f7_private_sector_cleaned'
    ORDER BY ordinal_position;
""")
print("\nv_f7_private_sector_cleaned columns:")
cols = [r[0] for r in cur.fetchall()]
print(f"  {cols}")

# Sample the private sector view
cur.execute("SELECT * FROM v_f7_private_sector_cleaned LIMIT 1;")
sample = cur.fetchone()
print(f"\nSample row (first 5 values): {sample[:5] if sample else 'EMPTY'}")

# Recreate the unified view with correct source
print("\n--- Recreating all_employers_unified ---")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")

cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (from F-7 cleaned data)
SELECT 
    'PVT-' || COALESCE(employer_id::text, f_num::text || '-' || ROW_NUMBER() OVER ()::text) as unified_id,
    employer_name,
    NULL::text as sub_employer,
    NULL::text as location_description,
    'PRIVATE_EMPLOYER' as employer_type,
    'PRIVATE' as sector_code,
    state,
    lat,
    lon,
    aff_abbr as union_acronym,
    NULL::text as union_name,
    NULL::text as local_number,
    f_num,
    workers_covered,
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
print("  [OK] Recreated all_employers_unified")

# Recreate sector_summary
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
print("  [OK] Recreated sector_summary")

# Recreate union_sector_coverage
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
print("  [OK] Recreated union_sector_coverage")

# Verify
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print("\nSector Summary:")
print(f"  {'Sector':<10} {'Employers':>12} {'Unique':>10} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 60)
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>12,} {row[2]:>10,} {row[3]:>14,} {row[4]:>8}")

# Top unions by sector
cur.execute("""
    SELECT union_acronym, 
           SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private_workers,
           SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal_workers,
           SUM(workers_covered) as total_workers
    FROM all_employers_unified
    WHERE union_acronym IS NOT NULL
    GROUP BY union_acronym
    ORDER BY total_workers DESC
    LIMIT 15;
""")
print("\nTop 15 Unions by Combined Workers:")
print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
print("  " + "-" * 52)
for row in cur.fetchall():
    print(f"  {row[0]:<12} {row[1]:>12,} {row[2]:>12,} {row[3]:>12,}")

conn.close()
print("\n[DONE] Unified views fixed and verified")
