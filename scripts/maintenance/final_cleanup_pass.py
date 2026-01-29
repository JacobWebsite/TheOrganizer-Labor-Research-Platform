"""
Final pass - fix remaining identifiable employers
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("Final Cleanup Pass")
print("=" * 80)

cur.execute("DROP VIEW IF EXISTS v_f7_private_sector_cleaned CASCADE;")

cur.execute("""
CREATE VIEW v_f7_private_sector_cleaned AS
SELECT 
    employer_id,
    employer_name,
    city,
    state,
    naics,
    CASE 
        -- Auto/Heavy equipment
        WHEN employer_name ILIKE '%stellantis%' OR employer_name ILIKE '%FCA US%' THEN 'UAW'
        WHEN employer_name ILIKE '%caterpillar%' THEN 'UAW'
        WHEN employer_name ILIKE '%daimler%truck%' THEN 'UAW'
        WHEN employer_name ILIKE '%general motors%' THEN 'UAW'
        WHEN employer_name ILIKE '%ford motor%' THEN 'UAW'
        WHEN employer_name ILIKE '%john deere%' OR employer_name ILIKE '%deere & co%' THEN 'UAW'
        WHEN employer_name ILIKE '%mack trucks%' THEN 'UAW'
        
        -- Telecom
        WHEN employer_name ILIKE '%AT&T%' AND affiliation IN ('UNKNOWN', 'SAGAFTRA') THEN 'CWA'
        WHEN employer_name ILIKE '%ATT %' THEN 'CWA'
        WHEN employer_name ILIKE '%bellsouth%' THEN 'CWA'
        WHEN employer_name ILIKE '%verizon%' THEN 'CWA'
        WHEN employer_name ILIKE '%t-mobile%' THEN 'CWA'
        
        -- Healthcare
        WHEN employer_name ILIKE '%kaiser perman%' THEN 'SEIU'
        WHEN employer_name ILIKE '%stanford health%' THEN 'SEIU'
        WHEN employer_name ILIKE '%corewell health%' THEN 'SEIU'
        
        -- Utilities
        WHEN employer_name ILIKE '%xcel energy%' THEN 'IBEW'
        WHEN employer_name ILIKE '%socal%gas%' OR employer_name ILIKE '%southern california gas%' THEN 'IBEW'
        WHEN employer_name ILIKE '%pacific gas%' OR employer_name ILIKE '%pg&e%' THEN 'IBEW'
        WHEN employer_name ILIKE 'GE' OR employer_name ILIKE 'GE %' THEN 'IUE-CWA'
        
        -- Maritime
        WHEN employer_name ILIKE '%maritime%association%' THEN 'ILA'
        WHEN employer_name ILIKE '%maritime%alliance%' THEN 'ILA'
        WHEN employer_name ILIKE '%USMX%' THEN 'ILA'
        
        -- Package/Freight
        WHEN employer_name ILIKE '%united parcel%' OR employer_name ILIKE '%UPS%' THEN 'IBT'
        WHEN employer_name ILIKE '%DHL%' THEN 'IBT'
        
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
        WHEN employer_name ILIKE '%fred meyer%' THEN 'UFCW'
        WHEN employer_name ILIKE '%save mart%' OR employer_name ILIKE '%lucky%' THEN 'UFCW'
        WHEN employer_name ILIKE '%california processors%' THEN 'IBT'
        
        -- Building trades
        WHEN employer_name ILIKE '%iron workers%' OR employer_name ILIKE '%ironworkers%' THEN 'IW'
        WHEN employer_name ILIKE '%CIEC%' THEN 'IW'
        WHEN employer_name ILIKE '%IW Employers%' THEN 'IW'
        WHEN employer_name ILIKE '%bricklayer%' THEN 'BAC'
        WHEN employer_name ILIKE '%carpenters%' AND affiliation = 'UNKNOWN' THEN 'CJA'
        WHEN employer_name ILIKE '%boilermaker%' THEN 'BBF'
        WHEN employer_name ILIKE '%builders association%' THEN 'LIUNA'
        WHEN employer_name ILIKE '%lake county contractors%' THEN 'LIUNA'
        WHEN employer_name ILIKE '%convention center contractors%' THEN 'CJA'
        WHEN employer_name ILIKE '%painting%glazing%employer%' THEN 'IUPAT'
        WHEN employer_name ILIKE '%general contractors%' THEN 'LIUNA'
        WHEN employer_name ILIKE '%SMACNA%' THEN 'SMART'
        WHEN employer_name ILIKE '%door contractors%' THEN 'CJA'
        WHEN employer_name ILIKE '%northwest employers association%' THEN 'LIUNA'
        WHEN employer_name ILIKE '%building division%ICI%' THEN 'LIUNA'
        
        -- Aerospace/Defense/Shipbuilding
        WHEN employer_name ILIKE '%lockheed%' THEN 'IAM'
        WHEN employer_name ILIKE '%boeing%' THEN 'IAM'
        WHEN employer_name ILIKE '%raytheon%' THEN 'IAM'
        WHEN employer_name ILIKE '%northrop%' THEN 'IAM'
        WHEN employer_name ILIKE '%bath iron works%' THEN 'IAM'
        WHEN employer_name ILIKE '%huntington ingalls%' OR employer_name ILIKE '%ingalls ship%' THEN 'USW'
        WHEN employer_name ILIKE '%electric boat%' OR employer_name ILIKE '%general dynamics%' THEN 'IAM'
        
        -- Airlines
        WHEN employer_name ILIKE '%american airlines%' THEN 'AFA'
        WHEN employer_name ILIKE '%united airlines%' THEN 'AFA'
        WHEN employer_name ILIKE '%delta air%' THEN 'AFA'
        WHEN employer_name ILIKE '%southwest airlines%' THEN 'TWU'
        
        -- Entertainment
        WHEN employer_name ILIKE '%productions%LLC%' AND affiliation = 'UNKNOWN' THEN 'IATSE'
        WHEN employer_name ILIKE '%theatrical%basic%agreement%' THEN 'SAG-AFTRA'
        WHEN employer_name ILIKE '%directors guild%' THEN 'DGA'
        WHEN employer_name ILIKE '%LORT%' OR employer_name ILIKE '%league of resident theatres%' THEN 'AEA'
        WHEN employer_name ILIKE '%symphony%opera%ballet%' THEN 'AFM'
        WHEN employer_name ILIKE '%live television%' THEN 'IATSE'
        WHEN employer_name ILIKE '%disney%' AND affiliation = 'UNKNOWN' THEN 'IATSE'
        
        -- Casinos/Hotels
        WHEN employer_name ILIKE '%MGM%' OR employer_name ILIKE '%bellagio%' OR employer_name ILIKE '%aria%' THEN 'UNITE HERE'
        WHEN employer_name ILIKE '%caesars%' OR employer_name ILIKE '%desert palace%' THEN 'UNITE HERE'
        WHEN employer_name ILIKE '%mandalay%' THEN 'UNITE HERE'
        
        ELSE affiliation
    END as affiliation,
    match_type,
    f7_reported_workers,
    reconciled_workers
FROM v_f7_reconciled_private_sector
WHERE 
    -- Exclude federal
    employer_name NOT ILIKE '%veteran%affairs%'
    AND employer_name NOT ILIKE '%postal service%'
    AND employer_name NOT ILIKE 'u.s. department%'
    AND employer_name NOT ILIKE 'united states department%'
    AND employer_name NOT ILIKE '%department of labor%'
    AND employer_name NOT ILIKE '%department of education%'
    AND employer_name NOT ILIKE '%department of energy%'
    AND employer_name NOT ILIKE '%department of health%human%'
    AND employer_name NOT ILIKE '%department of the navy%'
    AND employer_name NOT ILIKE '%social security admin%'
    AND employer_name NOT ILIKE 'HUD/%'
    AND employer_name NOT ILIKE '%federal%tribal%'
    AND employer_name NOT ILIKE '%internal revenue service%'
    AND employer_name NOT ILIKE '%national weather service%'
    AND employer_name NOT ILIKE '%NOAA%'
    AND employer_name NOT ILIKE '%puget sound naval%'
    AND employer_name NOT ILIKE '%naval shipyard%'
    AND employer_name NOT ILIKE '%army%air force exchange%'
    AND employer_name NOT ILIKE '%DOD %'
    AND employer_name NOT ILIKE '%U.S. Army%'
    
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
    AND employer_name NOT ILIKE '%city schools%'
    AND employer_name NOT ILIKE '%public schools%'
    
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
    AND employer_name NOT ILIKE '%labor relations division%'
    AND employer_name NOT ILIKE '%south atlantic employers%'
    
    -- Exclude typos
    AND employer_name NOT ILIKE '%kaiser permanenteeee%'
    
    -- Exclude misclassifications
    AND NOT (employer_name ILIKE '%AT&T%' AND affiliation = 'SAGAFTRA')
    AND NOT (employer_name ILIKE '%dep''t of vet%' AND affiliation = 'UNKNOWN')
    
    -- Exclude federal unions
    AND (affiliation NOT IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE') OR affiliation IS NULL);
""")
print("  [OK] Created final cleaned view")

# Final results
cur.execute("SELECT COUNT(*), SUM(reconciled_workers) FROM v_f7_private_sector_cleaned;")
r = cur.fetchone()
print(f"\nFinal cleaned: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL;
""")
r = cur.fetchone()
print(f"Remaining UNKNOWN: {r[0]:,} employers, {r[1] or 0:,.0f} workers ({r[1]/6650000*100:.1f}% of total)")

# Top 15 UNKNOWN
print("\n--- Top 15 Still UNKNOWN (these are likely legitimate small unknowns) ---")
cur.execute("""
    SELECT employer_name, reconciled_workers
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    ORDER BY reconciled_workers DESC
    LIMIT 15;
""")
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>8,.0f}")

conn.close()
