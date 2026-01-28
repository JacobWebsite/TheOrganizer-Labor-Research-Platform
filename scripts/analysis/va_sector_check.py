import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('VETERANS AFFAIRS SECTOR ANALYSIS')
print('='*70)

# 1. Search for VA employers in F-7
print('\n### 1. Veterans Affairs Employers in F-7 ###')
cur.execute("""
    SELECT 
        f.employer_name, 
        f.city, 
        f.state, 
        f.latest_unit_size,
        f.latest_union_name,
        u.aff_abbr,
        u.sector_revised
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.employer_name ILIKE '%veteran%'
       OR f.employer_name ILIKE '%VA %'
       OR f.employer_name ILIKE '%v.a.%'
       OR f.employer_name ILIKE '%dept of vet%'
       OR f.employer_name ILIKE '%department of vet%'
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 20
""")
va_total = 0
print(f'{"Employer":<50} {"Workers":>10} {"Union":>10} {"Sector":>15}')
print('-'*90)
for row in cur.fetchall():
    print(f"{row['employer_name'][:50]:<50} {row['latest_unit_size'] or 0:>10,} {row['aff_abbr'] or 'N/A':>10} {row['sector_revised'] or 'N/A':>15}")
    va_total += row['latest_unit_size'] or 0

print(f'\nTotal VA workers in F-7: {va_total:,}')

# 2. Check AFGE (federal employee union) in F-7
print('\n### 2. AFGE (Federal Employees) in F-7 ###')
cur.execute("""
    SELECT 
        u.sector_revised,
        COUNT(DISTINCT f.employer_id) as employers,
        SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr = 'AFGE'
    GROUP BY u.sector_revised
""")
for row in cur.fetchall():
    print(f"  AFGE sector_revised={row['sector_revised']}: {row['employers']} employers, {row['workers'] or 0:,} workers")

# 3. Sample AFGE employers
print('\n### 3. Sample AFGE Employers in F-7 ###')
cur.execute("""
    SELECT f.employer_name, f.latest_unit_size
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr = 'AFGE'
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row['employer_name'][:60]}: {row['latest_unit_size'] or 0:,}")

# 4. What's in FEDERAL sector in F-7?
print('\n### 4. All FEDERAL Sector in F-7 ###')
cur.execute("""
    SELECT 
        u.aff_abbr,
        COUNT(DISTINCT f.employer_id) as employers,
        SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised = 'FEDERAL'
    GROUP BY u.aff_abbr
    ORDER BY workers DESC NULLS LAST
""")
print(f'{"Union":<15} {"Employers":>12} {"Workers":>12}')
print('-'*42)
fed_total = 0
for row in cur.fetchall():
    print(f"{row['aff_abbr']:<15} {row['employers']:>12,} {row['workers'] or 0:>12,}")
    fed_total += row['workers'] or 0
print(f'{"TOTAL":<15} {"":>12} {fed_total:>12,}')

# 5. The problem - VA shouldn't be in F-7 at all!
print('\n### 5. ANALYSIS ###')
print('''
F-7 is the "Notice of Intent to Bargain" filed under the NLRA (private sector).
Federal employees (including VA) are covered by FSLMRA, not NLRA.
VA employees should NOT appear in F-7 data at all!

This suggests:
1. Data entry errors (VA mistakenly filed F-7)
2. Private contractors working AT VA facilities
3. Veterans service organizations (private nonprofits)
''')

conn.close()
print('='*70)
