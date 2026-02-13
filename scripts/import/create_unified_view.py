import os
"""
Create unified membership view combining OLMS LM data with Form 990 estimates
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

# Create unified membership view
sql = """
DROP VIEW IF EXISTS v_unified_membership CASCADE;
CREATE VIEW v_unified_membership AS

-- OLMS LM Data (private sector + some public)
SELECT 
    'OLMS_LM' as data_source,
    union_name as organization_name,
    aff_abbr as affiliation,
    CASE 
        WHEN desig_name = 'NHQ' THEN 'NATIONAL'
        WHEN desig_name = 'SA' THEN 'STATE'
        WHEN desig_name = 'DC' THEN 'COUNCIL'
        ELSE 'LOCAL'
    END as org_level,
    state,
    members as membership,
    NULL::decimal as dues_revenue,
    'HIGH' as confidence,
    yr_covered as data_year
FROM lm_data
WHERE yr_covered = 2024

UNION ALL

-- Form 990 Estimates (public sector gap fill)
SELECT 
    '990_EST' as data_source,
    organization_name,
    CASE 
        WHEN org_type LIKE 'NEA%' THEN 'NEA'
        WHEN org_type LIKE 'AFT%' THEN 'AFT'
        WHEN org_type LIKE 'FOP%' THEN 'FOP'
        WHEN org_type LIKE 'IAFF%' THEN 'IAFF'
        WHEN org_type LIKE 'SEIU%' THEN 'SEIU'
        WHEN org_type LIKE 'AFSCME%' THEN 'AFSCME'
        ELSE 'OTHER'
    END as affiliation,
    CASE 
        WHEN org_type LIKE '%NATIONAL' THEN 'NATIONAL'
        WHEN org_type LIKE '%STATE' THEN 'STATE'
        WHEN org_type LIKE '%COUNCIL' THEN 'COUNCIL'
        ELSE 'LOCAL'
    END as org_level,
    state,
    estimated_members as membership,
    dues_revenue,
    confidence_level as confidence,
    tax_year as data_year
FROM form_990_estimates
WHERE tax_year = 2024;
"""

cur.execute(sql)
conn.commit()
print('Created view: v_unified_membership')

# Create summary by affiliation
sql2 = """
DROP VIEW IF EXISTS v_unified_by_affiliation CASCADE;
CREATE VIEW v_unified_by_affiliation AS
SELECT 
    affiliation,
    data_source,
    COUNT(*) as org_count,
    SUM(membership) as total_members
FROM v_unified_membership
GROUP BY affiliation, data_source
ORDER BY total_members DESC;
"""
cur.execute(sql2)
conn.commit()
print('Created view: v_unified_by_affiliation')

# Query unified summary
cur.execute("""
    SELECT data_source, COUNT(*), SUM(membership)
    FROM v_unified_membership
    GROUP BY data_source
""")
rows = cur.fetchall()
print()
print('UNIFIED MEMBERSHIP SUMMARY')
print('=' * 50)
for r in rows:
    src = r[0] or 'Unknown'
    cnt = r[1] or 0
    mem = r[2] or 0
    print(f'  {src:<12} {cnt:>6} orgs  {mem:>12,} members')

# Total
cur.execute('SELECT COUNT(*), SUM(membership) FROM v_unified_membership')
total = cur.fetchone()
print('-' * 50)
print(f"  TOTAL       {total[0]:>6} orgs  {total[1]:>12,} members")

# Top affiliations
print()
print('TOP AFFILIATIONS (combined sources)')
print('=' * 50)
cur.execute("""
    SELECT affiliation, SUM(membership) as total
    FROM v_unified_membership
    GROUP BY affiliation
    ORDER BY total DESC
    LIMIT 10
""")
for r in cur.fetchall():
    aff = r[0] or 'Unknown'
    mem = r[1] or 0
    print(f'  {aff:<12} {mem:>12,}')

conn.close()
