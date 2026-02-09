import os
"""
Update unified view to use cleaned private sector data
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Updating Unified View with Cleaned Data")
print("=" * 80)

# Drop and recreate unified views
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")

print("\n--- Creating all_employers_unified with cleaned data ---")
cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (CLEANED)
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
    'F-7 (Cleaned)' as data_source,
    match_type
FROM v_f7_private_sector_cleaned

UNION ALL

-- Federal sector employers
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
print("  [OK] Created all_employers_unified")

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
print("  [OK] Created summary views")

# ============================================================================
# Final Summary
# ============================================================================
print("\n" + "=" * 80)
print("FINAL CLEANED UNIFIED SUMMARY")
print("=" * 80)

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print(f"\n  {'Sector':<10} {'Employers':>12} {'Unique':>10} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 60)
total_emp, total_work = 0, 0
for row in cur.fetchall():
    print(f"  {row[0]:<10} {row[1]:>12,} {row[2]:>10,} {row[3]:>14,.0f} {row[4]:>8}")
    total_emp += row[1]
    total_work += row[3]
print("  " + "-" * 60)
print(f"  {'TOTAL':<10} {total_emp:>12,} {'':<10} {total_work:>14,.0f}")

# Compare to BLS benchmarks
print("\n" + "-" * 60)
print("  COMPARISON TO BLS BENCHMARKS (2024):")
print("  " + "-" * 40)
print(f"  Private sector workers: {6692947:>12,} (BLS: ~7.3M)")
print(f"  Federal workers:        {1284167:>12,} (BLS: ~1.3M)")
print(f"  Total covered:          {total_work:>12,.0f}")
print("  " + "-" * 40)
print("  Gap analysis:")
print(f"    Private: within {abs(7300000-6692947)/7300000*100:.1f}% of BLS")
print(f"    Federal: within {abs(1300000-1284167)/1300000*100:.1f}% of BLS")

# Top employers overall
print("\n--- Top 15 Largest Employers (All Sectors) ---")
cur.execute("""
    SELECT sector_code, employer_name, union_acronym, workers_covered
    FROM all_employers_unified
    WHERE workers_covered > 0
    AND union_acronym IS NOT NULL 
    AND union_acronym != 'UNKNOWN'
    ORDER BY workers_covered DESC
    LIMIT 15;
""")
print(f"  {'Sector':<8} {'Employer':<35} {'Union':<10} {'Workers':>10}")
print("  " + "-" * 70)
for row in cur.fetchall():
    print(f"  {row[0]:<8} {(row[1] or 'Unknown')[:35]:<35} {row[2] or 'N/A':<10} {row[3] or 0:>10,.0f}")

# Unions in both sectors
print("\n--- Unions Active in BOTH Private & Federal ---")
cur.execute("""
    SELECT 
        union_acronym,
        SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private,
        SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal,
        SUM(workers_covered) as total
    FROM all_employers_unified
    WHERE union_acronym IS NOT NULL AND union_acronym != 'UNKNOWN'
    GROUP BY union_acronym
    HAVING SUM(CASE WHEN sector_code = 'PRIVATE' THEN 1 ELSE 0 END) > 0
       AND SUM(CASE WHEN sector_code = 'FEDERAL' THEN 1 ELSE 0 END) > 0
    ORDER BY total DESC
    LIMIT 15;
""")
print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
print("  " + "-" * 52)
for row in cur.fetchall():
    print(f"  {row[0]:<12} {row[1]:>12,.0f} {row[2]:>12,.0f} {row[3]:>12,.0f}")

conn.close()

print("\n" + "=" * 80)
print("DATA CLEANUP COMPLETE")
print("=" * 80)
