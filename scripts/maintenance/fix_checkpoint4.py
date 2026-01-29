"""
CHECKPOINT 4 FIX: Create proper unified view using v_employer_search
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 4: Creating Unified Private + Public Sector View")
print("=" * 80)

# Check v_employer_search sample
print("\n--- Sample from v_employer_search ---")
cur.execute("""
    SELECT employer_name, state, bargaining_unit_size, affiliation, union_name_lm
    FROM v_employer_search 
    WHERE bargaining_unit_size > 0
    ORDER BY bargaining_unit_size DESC 
    LIMIT 5;
""")
for row in cur.fetchall():
    print(f"  {row[0][:40]:<40} {row[1]} {row[2]:>8,} {row[3] or 'N/A'}")

# Drop and recreate views
print("\n--- Recreating unified views ---")
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")

cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (from F-7 via v_employer_search)
SELECT 
    'PVT-' || employer_id::text as unified_id,
    employer_name,
    NULL::text as sub_employer,
    city || ', ' || state as location_description,
    'PRIVATE_EMPLOYER' as employer_type,
    'PRIVATE' as sector_code,
    state,
    latitude as lat,
    longitude as lon,
    affiliation as union_acronym,
    affiliation_name as union_name,
    NULL::text as local_number,
    union_file_number::text as f_num,
    bargaining_unit_size as workers_covered,
    NULL::integer as year_recognized,
    FALSE as is_consolidated_unit,
    'National Labor Relations Act (NLRA)' as governing_law,
    'F-7' as data_source
FROM v_employer_search

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
print("  [OK] Created all_employers_unified view")

# Create summary views
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
print("  [OK] Created sector_summary and union_sector_coverage views")

# ============================================================================
# Summary Statistics
# ============================================================================
print("\n" + "=" * 80)
print("UNIFIED SECTOR SUMMARY")
print("=" * 80)

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print(f"\n  {'Sector':<10} {'Employers':>12} {'Unique':>10} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 60)
total_emp, total_uniq, total_work = 0, 0, 0
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>12,} {row[2]:>10,} {row[3]:>14,} {row[4]:>8}")
    total_emp += row[1]
    total_uniq += row[2]
    total_work += row[3]
print("  " + "-" * 60)
print(f"  {'TOTAL':<10} {total_emp:>12,} {total_uniq:>10,} {total_work:>14,}")

# Unions present in both sectors
cur.execute("""
    SELECT 
        union_acronym,
        SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private_workers,
        SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal_workers,
        SUM(workers_covered) as total_workers
    FROM all_employers_unified
    WHERE union_acronym IS NOT NULL
    GROUP BY union_acronym
    HAVING SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) > 0
       AND SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) > 0
    ORDER BY total_workers DESC
    LIMIT 15;
""")
results = cur.fetchall()
if results:
    print("\n  Unions Active in BOTH Private and Federal Sectors:")
    print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
    print("  " + "-" * 52)
    for row in results:
        print(f"  {row[0]:<12} {row[1]:>12,} {row[2]:>12,} {row[3]:>12,}")

# Top employers overall
cur.execute("""
    SELECT sector_code, employer_name, union_acronym, workers_covered
    FROM all_employers_unified
    WHERE workers_covered > 0
    ORDER BY workers_covered DESC
    LIMIT 15;
""")
print("\n  Top 15 Largest Employer-Union Relationships:")
print(f"  {'Sector':<8} {'Employer':<35} {'Union':<10} {'Workers':>10}")
print("  " + "-" * 70)
for row in cur.fetchall():
    print(f"  {row[0]:<8} {(row[1] or 'Unknown')[:35]:<35} {row[2] or 'N/A':<10} {row[3] or 0:>10,}")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 4 COMPLETE")
print("=" * 80)
print("""
Views created:
  - all_employers_unified: Combined private (71K) + federal (2.2K) employers
  - sector_summary: Quick stats by sector
  - union_sector_coverage: Union presence by sector

Platform can now toggle between PRIVATE and FEDERAL sectors!

Next: Type 'continue checkpoint 5' for final verification
""")
