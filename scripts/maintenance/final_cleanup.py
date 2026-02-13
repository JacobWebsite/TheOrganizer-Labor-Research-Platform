import os
"""
Final cleanup - fix known affiliations and more exclusions
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Final Data Cleanup")
print("=" * 80)

# Drop and recreate with final cleaning
cur.execute("DROP VIEW IF EXISTS v_f7_private_sector_cleaned CASCADE;")

print("\n--- Creating final v_f7_private_sector_cleaned ---")
cur.execute("""
CREATE VIEW v_f7_private_sector_cleaned AS
SELECT 
    employer_id,
    employer_name,
    city,
    state,
    naics,
    -- Fix known affiliations
    CASE 
        WHEN employer_name ILIKE '%stellantis%' OR employer_name ILIKE '%FCA US%' THEN 'UAW'
        WHEN employer_name ILIKE '%american airlines%' THEN 'AFA'
        WHEN employer_name ILIKE '%kaiser perman%' THEN 'SEIU'
        WHEN employer_name ILIKE '%xcel energy%' THEN 'IBEW'
        WHEN employer_name ILIKE '%AT&T%' AND affiliation = 'UNKNOWN' THEN 'CWA'
        WHEN employer_name ILIKE '%bellsouth%' THEN 'CWA'
        WHEN employer_name ILIKE '%maritime%' AND employer_name ILIKE '%association%' THEN 'ILA'
        ELSE affiliation
    END as affiliation,
    match_type,
    f7_reported_workers,
    reconciled_workers
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
    AND employer_name NOT ILIKE '%school board%'
    AND employer_name NOT ILIKE '%school district%'
    AND employer_name NOT ILIKE '%board of education%'
    
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
    
    -- Exclude obvious typos/duplicates (will be captured by correct version)
    AND employer_name NOT ILIKE '%kaiser permanenteeee%'
    
    -- Exclude obvious misclassifications
    AND NOT (employer_name ILIKE '%AT&T%' AND affiliation = 'SAGAFTRA')
    AND NOT (employer_name ILIKE '%dep''t of vet%' AND affiliation = 'UNKNOWN')
    
    -- Exclude federal unions
    AND (affiliation NOT IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE') OR affiliation IS NULL);
""")
print("  [OK] Created final v_f7_private_sector_cleaned")

# Check results
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned;
""")
r = cur.fetchone()
print(f"\nFinal cleaned private sector: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

# Top employers
print("\n--- Top 20 Employers (Final) ---")
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

# By union
print("\n--- Top 15 Unions (Final) ---")
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

# UNKNOWN count
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL;
""")
r = cur.fetchone()
print(f"\nRemaining UNKNOWN: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

conn.close()
