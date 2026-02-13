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
print('TEACHER UNION SECTOR ANALYSIS')
print('='*70)

# 1. Check AFT and NEA classification
print('\n### 1. AFT & NEA in unions_master ###')
cur.execute("""
    SELECT aff_abbr, sector, sector_revised, COUNT(*) as unions, SUM(members) as members
    FROM unions_master
    WHERE aff_abbr IN ('AFT', 'NEA')
    GROUP BY aff_abbr, sector, sector_revised
    ORDER BY members DESC NULLS LAST
""")
for row in cur.fetchall():
    print(f"  {row['aff_abbr']}: sector={row['sector']}, sector_revised={row['sector_revised']}")
    print(f"      {row['unions']} unions, {row['members'] or 0:,} members")

# 2. How much AFT/NEA appears in F-7?
print('\n### 2. AFT & NEA in F-7 Data ###')
cur.execute("""
    SELECT 
        u.aff_abbr,
        COUNT(DISTINCT f.employer_id) as employers,
        SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr IN ('AFT', 'NEA')
    GROUP BY u.aff_abbr
""")
aft_nea_f7 = 0
for row in cur.fetchall():
    print(f"  {row['aff_abbr']}: {row['employers']} employers, {row['workers'] or 0:,} workers")
    aft_nea_f7 += row['workers'] or 0

if aft_nea_f7 == 0:
    print("  (No AFT/NEA found in F-7 - correct, they're public sector)")

# 3. What employers have AFT unions?
print('\n### 3. Sample AFT Employers in F-7 (if any) ###')
cur.execute("""
    SELECT f.employer_name, f.city, f.state, f.latest_unit_size
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr = 'AFT'
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"  {row['employer_name'][:50]} ({row['state']}): {row['latest_unit_size'] or 0:,}")
else:
    print("  (No AFT employers in F-7)")

# 4. What's in the PUBLIC_SECTOR category in F-7?
print('\n### 4. All PUBLIC_SECTOR Unions in F-7 ###')
cur.execute("""
    SELECT 
        u.aff_abbr,
        u.union_name,
        COUNT(DISTINCT f.employer_id) as employers,
        SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised = 'PUBLIC_SECTOR'
    GROUP BY u.aff_abbr, u.union_name
    ORDER BY workers DESC NULLS LAST
    LIMIT 15
""")
print(f"{'Affiliation':<10} {'Union Name':<40} {'Employers':>10} {'Workers':>12}")
print('-'*75)
for row in cur.fetchall():
    print(f"{row['aff_abbr']:<10} {row['union_name'][:40]:<40} {row['employers']:>10,} {row['workers'] or 0:>12,}")

# 5. Summary
print('\n### 5. Summary ###')
cur.execute("""
    SELECT SUM(f.latest_unit_size) as total
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised = 'PUBLIC_SECTOR'
""")
public_f7 = cur.fetchone()['total'] or 0

cur.execute("""
    SELECT SUM(members) as total
    FROM unions_master
    WHERE aff_abbr IN ('AFT', 'NEA') AND sector_revised = 'PUBLIC_SECTOR'
""")
teacher_total = cur.fetchone()['total'] or 0

print(f'\n  Total PUBLIC_SECTOR in F-7:     {public_f7:,}')
print(f'  Total AFT+NEA members (OLMS):   {teacher_total:,}')
print(f'  Teachers NOT in F-7:            {teacher_total - aft_nea_f7:,} (correct - public schools)')

conn.close()
print('\n' + '='*70)
