"""
Agent C: Address & NAICS Coverage Gaps - Phase 1 (Read-Only)
Audits missing address fields, NAICS coverage, and enrichment potential
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import os

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 1: Coverage Gaps Audit - f7_employers_deduped")
print("=" * 70)

cur.execute("SELECT COUNT(*) as total FROM f7_employers_deduped")
total = cur.fetchone()['total']
print(f"Total f7_employers_deduped records: {total:,}")

# ============================================================================
# 1. Address field coverage
# ============================================================================
print("\n--- 1. Address Field Coverage ---")

cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN street IS NULL OR TRIM(street) = '' THEN 1 ELSE 0 END) as missing_street,
        SUM(CASE WHEN city IS NULL OR TRIM(city) = '' THEN 1 ELSE 0 END) as missing_city,
        SUM(CASE WHEN state IS NULL OR TRIM(state) = '' THEN 1 ELSE 0 END) as missing_state,
        SUM(CASE WHEN zip IS NULL OR TRIM(zip) = '' THEN 1 ELSE 0 END) as missing_zip,
        SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) as missing_lat,
        SUM(CASE WHEN longitude IS NULL THEN 1 ELSE 0 END) as missing_lon
    FROM f7_employers_deduped
""")
r = cur.fetchone()
print(f"  Missing street:    {r['missing_street']:>6,} ({r['missing_street']*100/total:.1f}%)")
print(f"  Missing city:      {r['missing_city']:>6,} ({r['missing_city']*100/total:.1f}%)")
print(f"  Missing state:     {r['missing_state']:>6,} ({r['missing_state']*100/total:.1f}%)")
print(f"  Missing zip:       {r['missing_zip']:>6,} ({r['missing_zip']*100/total:.1f}%)")
print(f"  Missing latitude:  {r['missing_lat']:>6,} ({r['missing_lat']*100/total:.1f}%)")
print(f"  Missing longitude: {r['missing_lon']:>6,} ({r['missing_lon']*100/total:.1f}%)")

# Missing by state
print("\n  Missing street by state (top 15):")
cur.execute("""
    SELECT state, COUNT(*) as total,
           SUM(CASE WHEN street IS NULL OR TRIM(street) = '' THEN 1 ELSE 0 END) as missing
    FROM f7_employers_deduped
    GROUP BY state
    HAVING SUM(CASE WHEN street IS NULL OR TRIM(street) = '' THEN 1 ELSE 0 END) > 0
    ORDER BY SUM(CASE WHEN street IS NULL OR TRIM(street) = '' THEN 1 ELSE 0 END) DESC
    LIMIT 15
""")
for r in cur.fetchall():
    pct = r['missing'] * 100 / r['total'] if r['total'] > 0 else 0
    print(f"    {r['state']}: {r['missing']:,}/{r['total']:,} ({pct:.1f}%)")

# Completely missing address (no street, city, or state)
cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE (street IS NULL OR TRIM(street) = '')
      AND (city IS NULL OR TRIM(city) = '')
      AND (state IS NULL OR TRIM(state) = '')
""")
r = cur.fetchone()
print(f"\n  Completely missing address (no street/city/state): {r['cnt']:,}")

# ============================================================================
# 2. NAICS coverage
# ============================================================================
print("\n--- 2. NAICS Coverage ---")

# Check which NAICS columns exist
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND column_name LIKE '%naics%'
    ORDER BY column_name
""")
naics_cols = [r['column_name'] for r in cur.fetchall()]
print(f"  NAICS columns in f7_employers_deduped: {naics_cols}")

for col in naics_cols:
    cur.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN {col} IS NULL OR TRIM(CAST({col} AS TEXT)) = '' THEN 1 ELSE 0 END) as missing
        FROM f7_employers_deduped
    """)
    r = cur.fetchone()
    pct = r['missing'] * 100 / r['total'] if r['total'] > 0 else 0
    print(f"  {col}: {r['missing']:,} missing ({pct:.1f}%)")

# NAICS source distribution (if naics_source exists)
if 'naics_source' in naics_cols:
    cur.execute("""
        SELECT naics_source, COUNT(*) as cnt
        FROM f7_employers_deduped
        GROUP BY naics_source
        ORDER BY COUNT(*) DESC
    """)
    print(f"\n  NAICS source distribution:")
    for r in cur.fetchall():
        print(f"    {r['naics_source'] or 'NULL'}: {r['cnt']:,}")

# ============================================================================
# 3. NAICS enrichment from OSHA matches
# ============================================================================
print("\n--- 3. NAICS Enrichment Potential from OSHA ---")

cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as f7_with_osha
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
""")
r = cur.fetchone()
print(f"  F7 employers with OSHA matches: {r['f7_with_osha']:,}")

# F7 without NAICS but with OSHA match that has NAICS
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as enrichable
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
    JOIN osha_establishments o ON m.establishment_id = o.establishment_id
    WHERE (f.naics IS NULL OR TRIM(CAST(f.naics AS TEXT)) = '')
      AND o.naics_code IS NOT NULL AND TRIM(CAST(o.naics_code AS TEXT)) != ''
""")
r = cur.fetchone()
print(f"  F7 without NAICS but OSHA has NAICS: {r['enrichable']:,}")

# ============================================================================
# 4. Address recovery from lm_data
# ============================================================================
print("\n--- 4. Address Recovery Potential from lm_data ---")

# Check if lm_data has address fields
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'lm_data'
    AND column_name IN ('street', 'address', 'addr', 'city', 'state', 'zip', 'zip_code')
    ORDER BY column_name
""")
lm_addr_cols = [r['column_name'] for r in cur.fetchall()]
print(f"  Address-related columns in lm_data: {lm_addr_cols}")

if lm_addr_cols:
    # Check if lm_data has street addresses for employers missing street in f7
    # Link: f7.latest_union_fnum = lm_data.f_num (union file number)
    print("  Checking if lm_data.street can fill f7 gaps (via latest_union_fnum)...")
    cur.execute("""
        SELECT COUNT(DISTINCT f.employer_id) as recoverable
        FROM f7_employers_deduped f
        JOIN lm_data l ON CAST(f.latest_union_fnum AS TEXT) = l.f_num
        WHERE (f.street IS NULL OR TRIM(f.street) = '')
          AND l.street IS NOT NULL AND TRIM(l.street) != ''
    """)
    r = cur.fetchone()
    print(f"  F7 missing street, recoverable from lm_data.street: {r['recoverable']:,}")
else:
    print("  No address columns found in lm_data")

# ============================================================================
# 5. Geocode coverage
# ============================================================================
print("\n--- 5. Geocode Coverage ---")

cur.execute("""
    SELECT
        SUM(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 ELSE 0 END) as geocoded,
        SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) as not_geocoded,
        SUM(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                  AND street IS NOT NULL AND TRIM(street) != '' THEN 1 ELSE 0 END) as geocoded_with_addr,
        SUM(CASE WHEN (latitude IS NULL OR longitude IS NULL)
                  AND street IS NOT NULL AND TRIM(street) != '' THEN 1 ELSE 0 END) as geocodable
    FROM f7_employers_deduped
""")
r = cur.fetchone()
print(f"  Geocoded: {r['geocoded']:,}")
print(f"  Not geocoded: {r['not_geocoded']:,}")
print(f"  Has address but no geocode (geocodable): {r['geocodable']:,}")

# ============================================================================
# 6. Coverage by f_num (union file number)
# ============================================================================
print("\n--- 6. F-Num Coverage ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
""")
r = cur.fetchone()
print(f"  Missing latest_union_fnum: {r['cnt']:,}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE latest_union_name IS NULL OR TRIM(latest_union_name) = ''
""")
r = cur.fetchone()
print(f"  Missing latest_union_name: {r['cnt']:,}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("Key coverage gaps identified above.")
print("Priority enrichment opportunities:")
print("  1. NAICS from OSHA matches")
print("  2. Address recovery from lm_data")
print("  3. Geocoding for addresses without lat/lon")
print("=" * 70)

cur.close()
conn.close()
print("\nPhase 1 audit complete (read-only, no changes made)")
