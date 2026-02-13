import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('SECTOR ANALYSIS: PUBLIC vs PRIVATE')
print('='*70)

# 1. Check if union_hierarchy has sector info
print('\n### 1. Check Union Hierarchy Sector Data ###')
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'union_hierarchy'
    ORDER BY ordinal_position
""")
cols = [r['column_name'] for r in cur.fetchall()]
print(f'Columns: {cols}')

# 2. Check unions_master for sector
print('\n### 2. Check Unions Master Sector Data ###')
cur.execute("""
    SELECT sector, COUNT(*) as cnt, SUM(members) as total_members
    FROM unions_master
    WHERE sector IS NOT NULL
    GROUP BY sector
    ORDER BY total_members DESC NULLS LAST
""")
print('Unions by sector (unions_master):')
for row in cur.fetchall():
    print(f"  {row['sector']}: {row['cnt']:,} unions, {row['total_members'] or 0:,} members")

# 3. Check what affiliations are clearly public sector
print('\n### 3. Known Public Sector Unions ###')
public_sector_unions = [
    ('AFGE', 'American Federation of Government Employees'),
    ('AFSCME', 'American Federation of State, County and Municipal Employees'),
    ('AFT', 'American Federation of Teachers'),
    ('NTEU', 'National Treasury Employees Union'),
    ('NFFE', 'National Federation of Federal Employees'),
    ('NATCA', 'National Air Traffic Controllers Association'),
    ('IAFF', 'International Association of Fire Fighters'),
    ('FOP', 'Fraternal Order of Police'),
    ('PBA', 'Police Benevolent Association'),
    ('NEA', 'National Education Association'),
]

for abbr, name in public_sector_unions:
    cur.execute("""
        SELECT COUNT(*) as cnt, SUM(members) as total
        FROM unions_master
        WHERE aff_abbr = %s OR union_name ILIKE %s
    """, (abbr, f'%{name}%'))
    result = cur.fetchone()
    print(f"  {abbr}: {result['cnt']} unions, {result['total'] or 0:,} members")

# 4. Check postal unions
print('\n### 4. Postal Unions ###')
postal_unions = ['APWU', 'NALC', 'NPMHU', 'NRLCA']
for abbr in postal_unions:
    cur.execute("""
        SELECT COUNT(*) as cnt, SUM(members) as total
        FROM unions_master
        WHERE aff_abbr = %s
    """, (abbr,))
    result = cur.fetchone()
    print(f"  {abbr}: {result['cnt']} unions, {result['total'] or 0:,} members")

# 5. Check union_hierarchy deduplicated by affiliation
print('\n### 5. Union Hierarchy Deduplicated by Affiliation ###')
cur.execute("""
    SELECT aff_abbr, COUNT(*) as cnt, SUM(members_2024) as total
    FROM union_hierarchy
    WHERE count_members = true
    GROUP BY aff_abbr
    ORDER BY total DESC NULLS LAST
    LIMIT 20
""")
print('Top 20 affiliations (deduplicated, count_members=true):')
for row in cur.fetchall():
    print(f"  {row['aff_abbr']}: {row['cnt']} unions, {row['total'] or 0:,} members")

# 6. What's the F-7 data situation?
print('\n### 6. F-7 Data Analysis ###')
print('Note: F-7 (Notice of Intent to Bargain) is PRIVATE SECTOR ONLY')
print('F-7 is filed by employers when a union files for representation')
print('Government/public sector uses different processes (FSLMRA, state laws)')

cur.execute("""
    SELECT COUNT(*) as employers, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NOT NULL
""")
f7_result = cur.fetchone()
print(f'\nF-7 Matched: {f7_result["employers"]:,} employers, {f7_result["workers"]:,} workers')

conn.close()
print('\n' + '='*70)
