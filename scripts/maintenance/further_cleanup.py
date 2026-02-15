import os
from db_config import get_connection
"""
Further cleanup - more aggressive filtering
"""
import psycopg2

conn = get_connection()
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Further Data Cleanup")
print("=" * 80)

# Check remaining SAG-AFTRA suspicious entries
print("\n--- Remaining SAG-AFTRA entries to review ---")
cur.execute("""
    SELECT employer_name, reconciled_workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'SAGAFTRA'
    ORDER BY reconciled_workers DESC
    LIMIT 15;
""")
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>10,.0f}")

# Drop and recreate with more aggressive cleaning
cur.execute("DROP VIEW IF EXISTS v_f7_private_sector_cleaned CASCADE;")

print("\n--- Creating improved v_f7_private_sector_cleaned ---")
cur.execute("""
CREATE VIEW v_f7_private_sector_cleaned AS
SELECT *
FROM v_f7_reconciled_private_sector
WHERE 
    -- Exclude federal employers
    employer_name NOT ILIKE '%veteran%affairs%'
    AND employer_name NOT ILIKE '%postal service%'
    AND employer_name NOT ILIKE '%department of labor%'
    AND employer_name NOT ILIKE '%department of education%'
    AND employer_name NOT ILIKE '%department of energy%'
    AND employer_name NOT ILIKE '%department of health%human%'
    AND employer_name NOT ILIKE '%department of the navy%'
    AND employer_name NOT ILIKE '%social security admin%'
    AND employer_name NOT ILIKE 'HUD/%'
    AND employer_name NOT ILIKE '%federal%tribal%'
    AND employer_name NOT ILIKE 'u.s. department%'
    AND employer_name NOT ILIKE 'united states department%'
    
    -- Exclude state/local government
    AND employer_name NOT ILIKE 'state of %'
    AND employer_name NOT ILIKE '% state of %bargaining%'
    AND employer_name NOT ILIKE 'city of %'
    AND employer_name NOT ILIKE 'county of %'
    AND employer_name NOT ILIKE '% county of %'
    AND employer_name NOT ILIKE '%department of corrections%'
    AND employer_name NOT ILIKE '%department of transportation%'
    AND employer_name NOT ILIKE 'wa state %'
    AND employer_name NOT ILIKE 'illinois %department%'
    
    -- Exclude multi-employer placeholders
    AND employer_name NOT ILIKE '%all signator%'
    AND employer_name NOT ILIKE '%signatories to%'
    AND employer_name NOT ILIKE 'signatories %'
    AND employer_name NOT ILIKE '%signatory %'
    AND employer_name NOT ILIKE 'multiple companies%'
    AND employer_name NOT ILIKE '%2016-2019 commercial%'
    AND employer_name NOT ILIKE '%2021 SAG-AFTRA%'
    AND employer_name NOT ILIKE 'AFTRA 2013%'
    AND employer_name NOT ILIKE 'joint policy commit%'
    AND employer_name NOT ILIKE 'MBA %'
    AND employer_name NOT ILIKE 'AGC and various%'
    
    -- Exclude obvious misclassifications
    AND NOT (employer_name ILIKE '%AT&T%' AND affiliation = 'SAGAFTRA')
    AND NOT (employer_name ILIKE '%dep''t of vet%' AND affiliation = 'UNKNOWN')
    
    -- Exclude federal unions
    AND (affiliation NOT IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE') OR affiliation IS NULL);
""")
print("  [OK] Created improved v_f7_private_sector_cleaned")

# Check results
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned;
""")
r = cur.fetchone()
print(f"\nCleaned private sector: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

# Top employers after cleaning
print("\n--- Top 20 Employers After Further Cleaning ---")
cur.execute("""
    SELECT employer_name, reconciled_workers, affiliation, match_type
    FROM v_f7_private_sector_cleaned
    ORDER BY reconciled_workers DESC
    LIMIT 20;
""")
print(f"{'Employer':<50} {'Workers':>10} {'Union':<10} {'Type'}")
print("-" * 85)
for r in cur.fetchall():
    print(f"{(r[0] or 'Unknown')[:50]:<50} {r[1] or 0:>10,.0f} {r[2] or 'N/A':<10} {r[3]}")

# UNKNOWN employers - these need review
print("\n--- Large UNKNOWN Affiliations (>5K workers) ---")
cur.execute("""
    SELECT employer_name, reconciled_workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    ORDER BY reconciled_workers DESC
    LIMIT 15;
""")
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>10,.0f}")

conn.close()
