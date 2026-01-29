"""
CHECKPOINT 4: Create Unified Public Sector Views
Enables sector toggle (private vs public) in the platform
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
print("CHECKPOINT 4: Creating Unified Public Sector Views")
print("=" * 80)

# ============================================================================
# STEP 1: Drop existing views
# ============================================================================
print("\n--- Step 1: Cleaning up existing views ---")
for view in ['union_sector_coverage', 'sector_summary', 'all_employers_unified', 'public_sector_employers']:
    cur.execute(f"DROP VIEW IF EXISTS {view} CASCADE;")
print("  [OK] Dropped existing views")

# ============================================================================
# STEP 2: Create public_sector_employers view
# ============================================================================
print("\n--- Step 2: Creating public_sector_employers view ---")

cur.execute("""
CREATE VIEW public_sector_employers AS
SELECT 
    'FED-' || fbu.unit_id::text as employer_id,
    fbu.agency_name as employer_name,
    fbu.sub_agency,
    fbu.activity as location_description,
    'FEDERAL_AGENCY' as employer_type,
    'FEDERAL' as sector_code,
    'DC' as state,
    NULL::numeric as lat,
    NULL::numeric as lon,
    fbu.union_acronym,
    fbu.union_name,
    fbu.local_number,
    fbu.olms_file_number as f_num,
    fbu.total_in_unit as workers_covered,
    fbu.year_recognized,
    fbu.is_consolidated_unit,
    'Federal Service Labor-Management Relations Act' as governing_law,
    'FLRA/OPM' as data_source
FROM federal_bargaining_units fbu
WHERE fbu.status = 'Active';
""")
print("  [OK] Created public_sector_employers view")

# Verify
cur.execute("SELECT COUNT(*), SUM(workers_covered) FROM public_sector_employers;")
row = cur.fetchone()
print(f"  Public sector employers: {row[0]:,} records, {row[1]:,} workers")

# ============================================================================
# STEP 3: Check if employers_deduped exists for private sector
# ============================================================================
print("\n--- Step 3: Checking for private sector data ---")

cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'employers_deduped'
    );
""")
has_private = cur.fetchone()[0]
print(f"  Private sector table (employers_deduped) exists: {has_private}")

if has_private:
    cur.execute("SELECT COUNT(*), SUM(workers_covered) FROM employers_deduped;")
    row = cur.fetchone()
    print(f"  Private sector employers: {row[0]:,} records, {row[1] or 0:,} workers")

# ============================================================================
# STEP 4: Create all_employers_unified view
# ============================================================================
print("\n--- Step 4: Creating all_employers_unified view ---")

if has_private:
    cur.execute("""
    CREATE VIEW all_employers_unified AS
    
    -- Private sector employers (from F-7 data)
    SELECT 
        'PVT-' || employer_id::text as unified_id,
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
    FROM employers_deduped
    
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
    print("  [OK] Created all_employers_unified view (private + public)")
else:
    cur.execute("""
    CREATE VIEW all_employers_unified AS
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
    print("  [OK] Created all_employers_unified view (public only)")

# ============================================================================
# STEP 5: Create sector_summary view
# ============================================================================
print("\n--- Step 5: Creating sector_summary view ---")

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
print("  [OK] Created sector_summary view")

# ============================================================================
# STEP 6: Create union_sector_coverage view
# ============================================================================
print("\n--- Step 6: Creating union_sector_coverage view ---")

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
print("  [OK] Created union_sector_coverage view")

# ============================================================================
# STEP 7: Summary Statistics
# ============================================================================
print("\n" + "=" * 80)
print("UNIFIED VIEW SUMMARY")
print("=" * 80)

# Sector summary
cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC;")
print("\n  Sector Summary:")
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
print("\n  Top 15 Unions by Sector:")
print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
print("  " + "-" * 52)
for row in cur.fetchall():
    print(f"  {row[0]:<12} {row[1]:>12,} {row[2]:>12,} {row[3]:>12,}")

# Sample records
cur.execute("""
    SELECT sector_code, employer_name, union_acronym, workers_covered, data_source
    FROM all_employers_unified
    WHERE workers_covered > 0
    ORDER BY workers_covered DESC
    LIMIT 10;
""")
print("\n  Top 10 Largest Employer-Union Relationships:")
print(f"  {'Sector':<8} {'Employer':<35} {'Union':<8} {'Workers':>10}")
print("  " + "-" * 70)
for row in cur.fetchall():
    print(f"  {row[0]:<8} {(row[1] or 'Unknown')[:35]:<35} {row[2] or 'N/A':<8} {row[3] or 0:>10,}")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 4 COMPLETE")
print("=" * 80)
print("""
Views created:
  - public_sector_employers: Federal agencies as employers
  - all_employers_unified: Combined private + public sectors
  - sector_summary: Quick stats by sector
  - union_sector_coverage: Union presence by sector

The platform can now toggle between:
  - PRIVATE sector (F-7 employer notices)
  - FEDERAL sector (FLRA bargaining units)
  - Future: STATE/LOCAL sectors

Next: Type 'continue checkpoint 5' for verification and documentation
""")
