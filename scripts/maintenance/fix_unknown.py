import os
"""
Fix UNKNOWN affiliations and add more exclusions
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Fixing UNKNOWN Affiliations")
print("=" * 80)

# Drop and recreate with comprehensive fixes
cur.execute("DROP VIEW IF EXISTS v_f7_private_sector_cleaned CASCADE;")

print("\n--- Creating v_f7_private_sector_cleaned with affiliation fixes ---")
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
        -- Auto industry
        WHEN employer_name ILIKE '%stellantis%' OR employer_name ILIKE '%FCA US%' THEN 'UAW'
        WHEN employer_name ILIKE '%caterpillar%' THEN 'UAW'
        WHEN employer_name ILIKE '%daimler%truck%' THEN 'UAW'
        WHEN employer_name ILIKE '%general motors%' THEN 'UAW'
        WHEN employer_name ILIKE '%ford motor%' THEN 'UAW'
        
        -- Telecom
        WHEN employer_name ILIKE '%AT&T%' AND affiliation IN ('UNKNOWN', 'SAGAFTRA') THEN 'CWA'
        WHEN employer_name ILIKE '%ATT %' THEN 'CWA'
        WHEN employer_name ILIKE '%bellsouth%' THEN 'CWA'
        WHEN employer_name ILIKE '%verizon%' THEN 'CWA'
        WHEN employer_name ILIKE '%t-mobile%' THEN 'CWA'
        
        -- Healthcare
        WHEN employer_name ILIKE '%kaiser perman%' THEN 'SEIU'
        
        -- Utilities
        WHEN employer_name ILIKE '%xcel energy%' THEN 'IBEW'
        WHEN employer_name ILIKE '%socal%gas%' THEN 'IBEW'
        WHEN employer_name ILIKE '%pacific gas%' OR employer_name ILIKE '%pg&e%' THEN 'IBEW'
        
        -- Maritime
        WHEN employer_name ILIKE '%maritime%association%' THEN 'ILA'
        WHEN employer_name ILIKE '%maritime%alliance%' THEN 'ILA'
        
        -- Grocery/Retail
        WHEN employer_name ILIKE '%kroger%' THEN 'UFCW'
        WHEN employer_name ILIKE '%safeway%' THEN 'UFCW'
        WHEN employer_name ILIKE '%albertson%' THEN 'UFCW'
        WHEN employer_name ILIKE '%stop & shop%' OR employer_name ILIKE '%stop and shop%' THEN 'UFCW'
        WHEN employer_name ILIKE '%vons%' THEN 'UFCW'
        WHEN employer_name ILIKE '%ralphs%' THEN 'UFCW'
        WHEN employer_name ILIKE '%food 4 less%' THEN 'UFCW'
        WHEN employer_name ILIKE '%stater bros%' THEN 'UFCW'
        WHEN employer_name ILIKE '%tops markets%' THEN 'UFCW'
        WHEN employer_name ILIKE '%jewel%food%' THEN 'UFCW'
        WHEN employer_name ILIKE '%giant food%' THEN 'UFCW'
        WHEN employer_name ILIKE '%meijer%' THEN 'UFCW'
        
        -- Building trades
        WHEN employer_name ILIKE '%iron workers%' OR employer_name ILIKE '%ironworkers%' THEN 'IW'
        WHEN employer_name ILIKE '%CIEC%' THEN 'IW'
        WHEN employer_name ILIKE '%bricklayer%' THEN 'BAC'
        WHEN employer_name ILIKE '%carpenters%' AND affiliation = 'UNKNOWN' THEN 'CJA'
        
        -- Aerospace/Defense
        WHEN employer_name ILIKE '%lockheed%' THEN 'IAM'
        WHEN employer_name ILIKE '%boeing%' THEN 'IAM'
        WHEN employer_name ILIKE '%raytheon%' THEN 'IAM'
        WHEN employer_name ILIKE '%northrop%' THEN 'IAM'
        
        -- Entertainment (film/TV production companies)
        WHEN employer_name ILIKE '%productions%LLC%' AND affiliation = 'UNKNOWN' THEN 'IATSE'
        WHEN employer_name ILIKE '%theatrical%basic%agreement%' THEN 'SAG-AFTRA'
        WHEN employer_name ILIKE '%directors guild%' THEN 'DGA'
        WHEN employer_name ILIKE '%league of resident theatres%' OR employer_name ILIKE '%LORT%' THEN 'AEA'
        
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
    AND employer_name NOT ILIKE '%internal revenue service%'
    AND employer_name NOT ILIKE '%national weather service%'
    AND employer_name NOT ILIKE '%NOAA%'
    AND employer_name NOT ILIKE '%puget sound naval%'
    AND employer_name NOT ILIKE '%naval shipyard%'
    
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
    AND employer_name NOT ILIKE '%county schools%'
    
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
    AND employer_name NOT ILIKE 'company lists%'
    AND employer_name NOT ILIKE 'employer negotiating committee%'
    
    -- Exclude typos/duplicates
    AND employer_name NOT ILIKE '%kaiser permanenteeee%'
    
    -- Exclude misclassifications
    AND NOT (employer_name ILIKE '%AT&T%' AND affiliation = 'SAGAFTRA')
    AND NOT (employer_name ILIKE '%dep''t of vet%' AND affiliation = 'UNKNOWN')
    
    -- Exclude federal unions
    AND (affiliation NOT IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE') OR affiliation IS NULL);
""")
print("  [OK] Created v_f7_private_sector_cleaned with affiliation fixes")

# Check results
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned;
""")
r = cur.fetchone()
print(f"\nCleaned: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

# Remaining UNKNOWN
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL;
""")
r = cur.fetchone()
print(f"Remaining UNKNOWN: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

# Top UNKNOWN still remaining
print("\n--- Top 30 Still UNKNOWN ---")
cur.execute("""
    SELECT employer_name, city, state, reconciled_workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    ORDER BY reconciled_workers DESC
    LIMIT 30;
""")
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:45]:<45} {(r[1] or '')[:12]:<12} {r[2] or '':<3} {r[3] or 0:>8,.0f}")

# By union after fixes
print("\n--- Top 20 Unions After Fixes ---")
cur.execute("""
    SELECT 
        affiliation,
        COUNT(*) as employers,
        SUM(reconciled_workers) as workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation IS NOT NULL AND affiliation != 'UNKNOWN'
    GROUP BY affiliation
    ORDER BY workers DESC
    LIMIT 20;
""")
print(f"{'Union':<15} {'Employers':>10} {'Workers':>12}")
print("-" * 40)
for r in cur.fetchall():
    print(f"{r[0]:<15} {r[1]:>10,} {r[2] or 0:>12,.0f}")

conn.close()
