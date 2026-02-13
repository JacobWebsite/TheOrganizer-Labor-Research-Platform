import os
"""
CHECKPOINT 4 CORRECTED: Use the RECONCILED private sector view
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 4 CORRECTED: Using Reconciled Private Sector Data")
print("=" * 80)

# Check reconciled view structure
print("\n--- v_f7_reconciled_private_sector columns ---")
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'v_f7_reconciled_private_sector'
    ORDER BY ordinal_position;
""")
cols = [r[0] for r in cur.fetchall()]
print(f"Columns: {cols}")

# Drop and recreate views
print("\n--- Recreating unified views ---")
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")

cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (from RECONCILED F-7 data)
SELECT 
    'PVT-' || employer_id::text as unified_id,
    employer_name,
    NULL::text as sub_employer,
    city || ', ' || state as location_description,
    'PRIVATE_EMPLOYER' as employer_type,
    'PRIVATE' as sector_code,
    state,
    NULL::numeric as lat,
    NULL::numeric as lon,
    affiliation as union_acronym,
    NULL::text as union_name,
    NULL::text as local_number,
    NULL::text as f_num,
    reconciled_workers as workers_covered,
    NULL::integer as year_recognized,
    FALSE as is_consolidated_unit,
    'National Labor Relations Act (NLRA)' as governing_law,
    'F-7 (Reconciled)' as data_source,
    match_type
FROM v_f7_reconciled_private_sector

UNION ALL

-- Public sector employers (federal from FLRA)
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
    data_source,
    NULL::text as match_type
FROM public_sector_employers;
""")
print("  [OK] Created all_employers_unified view (using reconciled data)")

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
print("CORRECTED UNIFIED SECTOR SUMMARY")
print("=" * 80)

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print(f"\n  {'Sector':<10} {'Employers':>12} {'Unique':>10} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 60)
total_emp, total_uniq, total_work = 0, 0, 0
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>12,} {row[2]:>10,} {row[3]:>14,.0f} {row[4]:>8}")
    total_emp += row[1]
    total_uniq += row[2]
    total_work += row[3]
print("  " + "-" * 60)
print(f"  {'TOTAL':<10} {total_emp:>12,} {total_uniq:>10,} {total_work:>14,.0f}")

# Top employers
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
    print(f"  {row[0]:<8} {(row[1] or 'Unknown')[:35]:<35} {row[2] or 'N/A':<10} {row[3] or 0:>10,.0f}")

# Unions in both sectors
cur.execute("""
    SELECT 
        union_acronym,
        SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private_workers,
        SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal_workers,
        SUM(workers_covered) as total_workers
    FROM all_employers_unified
    WHERE union_acronym IS NOT NULL
    GROUP BY union_acronym
    HAVING SUM(workers_covered) > 10000
    ORDER BY total_workers DESC
    LIMIT 20;
""")
print("\n  Top 20 Unions by Sector (>10K workers):")
print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
print("  " + "-" * 52)
for row in cur.fetchall():
    print(f"  {row[0]:<12} {row[1]:>12,.0f} {row[2]:>12,.0f} {row[3]:>12,.0f}")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 4 CORRECTED - COMPLETE")
print("=" * 80)
print("""
Now using reconciled data:
  - Private: ~7.5M workers (was 15.5M raw)
  - Federal: ~1.3M workers (newly added)
  - Combined: ~8.8M total

The reconciled view applies adjustment factors for:
  - Multi-employer associations (NAME_INFERRED)
  - Duplicate filings
  - Federal sector contamination reduction
""")
