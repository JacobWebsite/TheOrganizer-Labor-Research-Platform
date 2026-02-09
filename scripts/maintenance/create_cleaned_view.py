import os
"""
Create cleaned private sector view with contamination removed
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Creating Cleaned Private Sector View")
print("=" * 80)

# Drop existing cleaned view if exists
cur.execute("DROP VIEW IF EXISTS v_f7_private_sector_cleaned CASCADE;")

# Create cleaned view with exclusions
print("\n--- Creating v_f7_private_sector_cleaned ---")
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
    AND employer_name NOT ILIKE '% state of %'
    AND employer_name NOT ILIKE 'city of %'
    AND employer_name NOT ILIKE 'county of %'
    AND employer_name NOT ILIKE '% county of %'
    AND employer_name NOT ILIKE '%department of corrections%'
    AND employer_name NOT ILIKE '%department of transportation%'
    
    -- Exclude multi-employer placeholders (these are aggregate counts, not real employers)
    AND employer_name NOT ILIKE '%all signator%'
    AND employer_name NOT ILIKE '%signatories to%'
    AND employer_name NOT ILIKE 'signatories %'
    AND employer_name NOT ILIKE '%signatory %'
    AND employer_name NOT ILIKE 'multiple companies%'
    
    -- Exclude obvious misclassifications
    AND NOT (employer_name ILIKE '%AT&T%' AND affiliation = 'SAGAFTRA')  -- AT&T is CWA, not SAG-AFTRA
    AND NOT (employer_name ILIKE '%dep''t of vet%' AND affiliation = 'UNKNOWN')  -- Federal
    
    -- Exclude federal unions that shouldn't have private sector employers
    AND (affiliation NOT IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE') OR affiliation IS NULL);
""")
print("  [OK] Created v_f7_private_sector_cleaned")

# Check results
cur.execute("""
    SELECT 
        COUNT(*) as count,
        SUM(reconciled_workers) as total
    FROM v_f7_private_sector_cleaned;
""")
r = cur.fetchone()
print(f"\nCleaned private sector: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

cur.execute("""
    SELECT 
        COUNT(*) as count,
        SUM(reconciled_workers) as total
    FROM v_f7_reconciled_private_sector;
""")
r2 = cur.fetchone()
print(f"Before cleaning: {r2[0]:,} employers, {r2[1] or 0:,.0f} workers")
print(f"Removed: {r2[0] - r[0]:,} employers, {(r2[1] or 0) - (r[1] or 0):,.0f} workers")

# Top employers after cleaning
print("\n--- Top 20 Employers After Cleaning ---")
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

# By union after cleaning
print("\n--- Top 15 Unions After Cleaning ---")
cur.execute("""
    SELECT 
        affiliation,
        COUNT(*) as employers,
        SUM(reconciled_workers) as workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation IS NOT NULL AND affiliation != 'UNKNOWN'
    GROUP BY affiliation
    ORDER BY workers DESC
    LIMIT 15;
""")
print(f"{'Union':<15} {'Employers':>10} {'Workers':>12}")
print("-" * 40)
for r in cur.fetchall():
    print(f"{r[0]:<15} {r[1]:>10,} {r[2] or 0:>12,.0f}")

conn.close()
