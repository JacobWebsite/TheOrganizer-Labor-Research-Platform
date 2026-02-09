import os
"""
CHECKPOINT 5: Verification and Documentation
Final validation and summary report for federal integration
"""

import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 5: Verification and Documentation")
print("=" * 80)

# ============================================================================
# VERIFICATION 1: Data Integrity
# ============================================================================
print("\n" + "=" * 80)
print("1. DATA INTEGRITY CHECKS")
print("=" * 80)

# Check record counts
cur.execute("SELECT COUNT(*) FROM federal_agencies;")
agency_count = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM federal_bargaining_units;")
unit_count = cur.fetchone()[0]

cur.execute("SELECT SUM(total_in_unit) FROM federal_bargaining_units;")
worker_count = cur.fetchone()[0]

print(f"\n  Federal Agencies:      {agency_count:,}")
print(f"  Bargaining Units:      {unit_count:,}")
print(f"  Workers Covered:       {worker_count:,}")

# Check for nulls in key fields
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(agency_name) as has_agency,
        COUNT(union_acronym) as has_union,
        COUNT(total_in_unit) as has_workers
    FROM federal_bargaining_units;
""")
row = cur.fetchone()
print(f"\n  Data Completeness:")
print(f"    Has agency name:     {row[1]:,} / {row[0]:,} ({row[1]/row[0]*100:.1f}%)")
print(f"    Has union:           {row[2]:,} / {row[0]:,} ({row[2]/row[0]*100:.1f}%)")
print(f"    Has worker count:    {row[3]:,} / {row[0]:,} ({row[3]/row[0]*100:.1f}%)")

# ============================================================================
# VERIFICATION 2: OLMS Linkage Quality
# ============================================================================
print("\n" + "=" * 80)
print("2. OLMS LINKAGE QUALITY")
print("=" * 80)

cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(olms_file_number) as direct_link,
        COUNT(*) - COUNT(olms_file_number) as no_direct_link
    FROM federal_bargaining_units
    WHERE status = 'Active';
""")
row = cur.fetchone()
print(f"\n  Direct OLMS Link (via OlmrNumber):")
print(f"    Linked:              {row[1]:,} / {row[0]:,} ({row[1]/row[0]*100:.1f}%)")
print(f"    Unlinked:            {row[2]:,} / {row[0]:,} ({row[2]/row[0]*100:.1f}%)")

# Check if linked file numbers exist in lm_data
cur.execute("""
    SELECT COUNT(DISTINCT fbu.olms_file_number)
    FROM federal_bargaining_units fbu
    WHERE fbu.olms_file_number IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM lm_data lm 
        WHERE lm.f_num::text = fbu.olms_file_number
    );
""")
valid_links = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(DISTINCT olms_file_number)
    FROM federal_bargaining_units
    WHERE olms_file_number IS NOT NULL;
""")
total_links = cur.fetchone()[0]

print(f"\n  OLMS File Number Validation:")
print(f"    Valid (found in lm_data): {valid_links:,} / {total_links:,}")

# ============================================================================
# VERIFICATION 3: Comparison with OLMS Membership Data
# ============================================================================
print("\n" + "=" * 80)
print("3. COMPARISON: FLRA vs OLMS MEMBERSHIP")
print("=" * 80)

# FLRA data by union
cur.execute("""
    SELECT union_acronym, SUM(total_in_unit) as flra_workers
    FROM federal_bargaining_units
    WHERE status = 'Active' AND union_acronym IS NOT NULL
    GROUP BY union_acronym
    ORDER BY flra_workers DESC
    LIMIT 10;
""")
flra_by_union = {row[0]: row[1] for row in cur.fetchall()}

# OLMS NHQ data for same unions
cur.execute("""
    SELECT aff_abbr, members
    FROM lm_data
    WHERE yr_covered = 2024
    AND state = 'DC'
    AND aff_abbr IN ('AFGE','NTEU','NFFE','NAGE','NATCA','NNU','AFSA','PASS')
    AND form_type = 'LM-2'
    ORDER BY members DESC;
""")
olms_by_union = {}
for row in cur.fetchall():
    if row[0] not in olms_by_union:  # Take first (largest) per affiliation
        olms_by_union[row[0]] = row[1]

print(f"\n  {'Union':<10} {'FLRA Workers':>15} {'OLMS Members':>15} {'Ratio':>10}")
print("  " + "-" * 55)
for union in ['AFGE', 'NTEU', 'NFFE', 'NAGE']:
    flra = flra_by_union.get(union, 0)
    olms = olms_by_union.get(union, 0)
    ratio = flra / olms if olms else 0
    print(f"  {union:<10} {flra or 0:>15,} {olms or 0:>15,} {ratio:>10.2f}")

# ============================================================================
# VERIFICATION 4: Sample Records
# ============================================================================
print("\n" + "=" * 80)
print("4. SAMPLE RECORDS")
print("=" * 80)

print("\n  Largest Bargaining Units:")
cur.execute("""
    SELECT agency_name, union_acronym, total_in_unit, 
           CASE WHEN olms_file_number IS NOT NULL THEN 'Yes' ELSE 'No' END as olms_linked
    FROM federal_bargaining_units
    WHERE status = 'Active'
    ORDER BY total_in_unit DESC NULLS LAST
    LIMIT 10;
""")
print(f"  {'Agency':<45} {'Union':<8} {'Workers':>10} {'OLMS':>6}")
print("  " + "-" * 75)
for row in cur.fetchall():
    print(f"  {(row[0] or 'Unknown')[:45]:<45} {row[1] or 'N/A':<8} {row[2] or 0:>10,} {row[3]:>6}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("FEDERAL PUBLIC SECTOR INTEGRATION - FINAL SUMMARY")
print("=" * 80)

print(f"""
DATA LOADED:
  - Federal Agencies:       {agency_count:,}
  - Bargaining Units:       {unit_count:,}
  - Workers Covered:        {worker_count:,}
  
OLMS LINKAGE:
  - Direct file links:      {row[1]:,} ({row[1]/row[0]*100:.1f}%)
  - Via affiliation match:  Remaining units linked to NHQ filings
  
TABLES CREATED:
  - federal_agencies
  - federal_bargaining_units
  - flra_olms_union_map
  
VIEWS CREATED:
  - flra_olms_crosswalk
  - flra_olms_enhanced_crosswalk
  - public_sector_employers
  - all_employers_unified
  - sector_summary
  - union_sector_coverage

NEXT STEPS:
  1. Add state PERB data (NY, CA, etc.) to public_sector_employers
  2. Add NCES school district data for teachers
  3. Geocode federal facility locations
  4. Update API endpoints for sector filtering
""")

# ============================================================================
# SAMPLE QUERIES FOR DOCUMENTATION
# ============================================================================
print("\n" + "=" * 80)
print("SAMPLE QUERIES")
print("=" * 80)

print("""
-- Get all AFGE bargaining units with worker counts
SELECT agency_name, activity, total_in_unit, olms_file_number
FROM federal_bargaining_units
WHERE union_acronym = 'AFGE' AND status = 'Active'
ORDER BY total_in_unit DESC;

-- Compare private vs public sector by union
SELECT union_acronym, sector_code, SUM(workers_covered) as workers
FROM all_employers_unified
GROUP BY union_acronym, sector_code
ORDER BY union_acronym, sector_code;

-- Get federal workers by agency
SELECT agency_name, SUM(total_in_unit) as workers
FROM federal_bargaining_units
GROUP BY agency_name
ORDER BY workers DESC;

-- Link federal units to OLMS financials
SELECT 
    fbu.agency_name,
    fbu.union_acronym,
    fbu.total_in_unit as flra_workers,
    lm.members as olms_members,
    lm.ttl_assets,
    lm.ttl_receipts
FROM federal_bargaining_units fbu
JOIN lm_data lm ON fbu.olms_file_number = lm.f_num::text
WHERE lm.yr_covered = 2024;
""")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 5 COMPLETE - FEDERAL INTEGRATION FINISHED")
print("=" * 80)
