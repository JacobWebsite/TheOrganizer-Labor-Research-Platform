import os
"""
Fix the unified view with correct column mappings
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
print("RECREATING UNIFIED VIEWS")
print("=" * 80)

# Drop existing views
print("\n--- Dropping existing views ---")
cur.execute("DROP VIEW IF EXISTS union_sector_coverage CASCADE;")
cur.execute("DROP VIEW IF EXISTS sector_summary CASCADE;")
cur.execute("DROP VIEW IF EXISTS all_employers_unified CASCADE;")
print("  [OK] Dropped")

# Create unified view using f7_employers_deduped for private sector
print("\n--- Creating all_employers_unified ---")
cur.execute("""
CREATE VIEW all_employers_unified AS

-- Private sector employers (from F-7 deduped data)
SELECT 
    'PVT-' || employer_id as unified_id,
    employer_name,
    city as sub_employer,
    street as location_description,
    'PRIVATE_EMPLOYER' as employer_type,
    'PRIVATE' as sector_code,
    state,
    latitude::numeric as lat,
    longitude::numeric as lon,
    latest_union_name as union_acronym,
    latest_union_name as union_name,
    NULL::text as local_number,
    latest_union_fnum::text as f_num,
    latest_unit_size as workers_covered,
    NULL::integer as year_recognized,
    FALSE as is_consolidated_unit,
    'National Labor Relations Act (NLRA)' as governing_law,
    'F-7' as data_source
FROM f7_employers_deduped
WHERE potentially_defunct = 0

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
print("  [OK] Created all_employers_unified")

# Create sector_summary
print("\n--- Creating sector_summary ---")
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
print("\n--- Creating union_sector_coverage ---")
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

# Sample records
cur.execute("""
    SELECT sector_code, employer_name, state, union_acronym, workers_covered
    FROM all_employers_unified
    WHERE workers_covered > 0
    ORDER BY workers_covered DESC
    LIMIT 10;
""")
print("\nTop 10 Largest Employer-Union Relationships:")
print(f"  {'Sector':<8} {'Employer':<35} {'State':<5} {'Union':<20} {'Workers':>10}")
print("  " + "-" * 85)
for row in cur.fetchall():
    print(f"  {row[0]:<8} {(row[1] or 'Unknown')[:35]:<35} {row[2] or 'N/A':<5} {(row[3] or 'N/A')[:20]:<20} {row[4] or 0:>10,}")

# Check geocoding
cur.execute("""
    SELECT sector_code, 
           COUNT(*) as total,
           COUNT(CASE WHEN lat IS NOT NULL THEN 1 END) as geocoded
    FROM all_employers_unified
    GROUP BY sector_code;
""")
print("\nGeocoding Status:")
for row in cur.fetchall():
    pct = row[2]/row[1]*100 if row[1] > 0 else 0
    print(f"  {row[0]}: {row[2]:,}/{row[1]:,} geocoded ({pct:.1f}%)")

conn.close()
print("\n[DONE] Views recreated successfully!")
