"""Analyze public sector union coverage against BLS/EPI benchmarks - v2"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('PUBLIC SECTOR UNION COVERAGE ANALYSIS v2')
print('='*80)

# First check EPI data structure
print('\n1. EPI DATA STRUCTURE')
print('-'*80)
cur.execute('''
    SELECT DISTINCT measure FROM epi_union_membership LIMIT 20
''')
print('Measures:', [r['measure'] for r in cur.fetchall()])

cur.execute('''
    SELECT DISTINCT demographic_group FROM epi_union_membership LIMIT 20
''')
print('Demographic groups:', [r['demographic_group'] for r in cur.fetchall()])

cur.execute('''
    SELECT DISTINCT group_value FROM epi_union_membership
    WHERE demographic_group = 'sector' OR demographic_group ILIKE '%sector%'
    LIMIT 30
''')
sectors = [r['group_value'] for r in cur.fetchall()]
print(f'Sector values: {sectors}')

# Get latest year
cur.execute('SELECT MAX(year) as max_year FROM epi_union_membership')
max_year = cur.fetchone()['max_year']
print(f'\nLatest year: {max_year}')

# Get national totals by sector
print('\n2. EPI UNION MEMBERSHIP BY SECTOR (National, {})'.format(max_year))
print('-'*80)
cur.execute('''
    SELECT group_value as sector, measure, value
    FROM epi_union_membership
    WHERE year = %s
      AND demographic_group = 'sector'
      AND geo_name = 'United States'
      AND measure IN ('union_members', 'covered_by_union', 'employed')
    ORDER BY group_value, measure
''', [max_year])
results = {}
for row in cur.fetchall():
    sector = row['sector']
    if sector not in results:
        results[sector] = {}
    results[sector][row['measure']] = row['value']

print(f"{'Sector':<35} | {'Members':>12} | {'Employed':>12} | {'Density':>8}")
print('-'*75)
for sector, data in sorted(results.items(), key=lambda x: -(x[1].get('union_members') or 0)):
    members = data.get('union_members', 0) or 0
    employed = data.get('employed', 0) or 0
    density = 100 * members / employed if employed else 0
    print(f"{sector:<35} | {members:>12,.0f} | {employed:>12,.0f} | {density:>7.1f}%")

# Check unions_master sector breakdown with member counts
print('\n3. OLMS UNIONS_MASTER BY SECTOR')
print('-'*80)
cur.execute('''
    SELECT sector,
           COUNT(*) as union_count,
           SUM(members) as total_members,
           AVG(members) as avg_members
    FROM unions_master
    WHERE sector IS NOT NULL
    GROUP BY sector
    ORDER BY SUM(members) DESC NULLS LAST
''')
print(f"{'Sector':<25} | {'Unions':>8} | {'Total Members':>15} | {'Avg Members':>12}")
print('-'*70)
for row in cur.fetchall():
    members = row['total_members'] or 0
    avg = row['avg_members'] or 0
    print(f"{row['sector']:<25} | {row['union_count']:>8,} | {members:>15,} | {avg:>12,.0f}")

# Public sector specific analysis
print('\n4. PUBLIC SECTOR DETAIL (FEDERAL + STATE/LOCAL)')
print('-'*80)

# Get OLMS data for federal and public sector
cur.execute('''
    SELECT sector, COUNT(*) as unions, SUM(members) as members
    FROM unions_master
    WHERE sector IN ('FEDERAL', 'PUBLIC_SECTOR')
    GROUP BY sector
''')
olms_public = {}
for row in cur.fetchall():
    olms_public[row['sector']] = row['members'] or 0
    print(f"  OLMS {row['sector']}: {row['members']:,} members")

olms_total_public = sum(olms_public.values())
print(f"\n  OLMS Total Public Sector: {olms_total_public:,}")

# Compare to BLS benchmark
bls_public_benchmark = 7_000_000  # ~7 million public sector union members
print(f"  BLS Benchmark (approx): {bls_public_benchmark:,}")
coverage = olms_total_public / bls_public_benchmark * 100
diff = (olms_total_public - bls_public_benchmark) / bls_public_benchmark * 100

print(f"\n  Coverage: {coverage:.1f}%")
print(f"  Difference from BLS: {diff:+.1f}%")

if abs(diff) <= 5:
    status = "TARGET (within 5%)"
elif abs(diff) <= 10:
    status = "ACCEPTABLE (within 10%)"
elif diff >= -15:
    status = "ACCEPTABLE (within 15% under)"
else:
    status = "NEEDS ATTENTION"
print(f"  Status: {status}")

# F7 employers in public sector
print('\n5. F7 EMPLOYERS - PUBLIC SECTOR BREAKDOWN')
print('-'*80)
cur.execute('''
    SELECT
        CASE
            WHEN naics = '92' THEN 'Public Admin (NAICS 92)'
            WHEN naics = '61' THEN 'Education (NAICS 61)'
            WHEN employer_name ILIKE '%school district%' THEN 'School District'
            WHEN employer_name ILIKE '%university%' OR employer_name ILIKE '%college%' THEN 'Higher Ed'
            WHEN employer_name ILIKE '%city of%' THEN 'City Government'
            WHEN employer_name ILIKE '%county of%' THEN 'County Government'
            WHEN employer_name ILIKE '%state of%' THEN 'State Government'
            WHEN employer_name ILIKE '%township%' THEN 'Township'
            WHEN employer_name ILIKE '%department of%' AND employer_name NOT ILIKE '%u.s.%' THEN 'State Dept'
            ELSE NULL
        END as govt_type,
        COUNT(*) as employers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers
    FROM f7_employers_deduped
    WHERE naics IN ('92', '61')
       OR employer_name ILIKE '%school district%'
       OR employer_name ILIKE '%university%'
       OR employer_name ILIKE '%college%'
       OR employer_name ILIKE '%city of%'
       OR employer_name ILIKE '%county of%'
       OR employer_name ILIKE '%state of%'
       OR employer_name ILIKE '%township%'
    GROUP BY 1
    HAVING COUNT(*) > 10
    ORDER BY 3 DESC
''')
f7_public_total = 0
for row in cur.fetchall():
    if row['govt_type']:
        workers = row['workers'] or 0
        f7_public_total += workers
        print(f"  {row['govt_type']:<30} | {row['employers']:>5} employers | {workers:>10,} workers")

print(f"\n  F7 Public Sector Total (deduplicated): {f7_public_total:,}")

# EPI state-by-state comparison for public sector
print('\n6. EPI STATE-LEVEL PUBLIC SECTOR (Top 15 states)')
print('-'*80)
cur.execute('''
    SELECT geo_name as state, value as members
    FROM epi_union_membership
    WHERE year = %s
      AND demographic_group = 'sector'
      AND group_value = 'Public sector'
      AND measure = 'union_members'
      AND geo_type = 'state'
    ORDER BY value DESC
    LIMIT 15
''', [max_year])
print(f"{'State':<25} | {'EPI Members':>12}")
print('-'*40)
for row in cur.fetchall():
    print(f"{row['state']:<25} | {row['members']:>12,.0f}")

conn.close()
