import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('F-7 vs OPM: FEDERAL EMPLOYER MISCLASSIFICATION CHECK')
print('='*70)

# OPM shows 1.28M in bargaining units, actual members ~1M (Janus opt-out)
# BLS shows ~1.8M federal union members total

print('''
OPM FEDERAL BENCHMARK:
  Bargaining Unit Size: 1,284,167
  Estimated Members:    ~1,000,000 (after Janus opt-outs)
  BLS Federal Workers:  ~1,800,000 (union + non-union)
''')

# 1. Check what's in F-7 with FEDERAL sector
print('\n### 1. F-7 Employers with FEDERAL Sector ###')
cur.execute("""
    SELECT 
        f.employer_name,
        f.latest_unit_size,
        u.aff_abbr,
        u.union_name
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised = 'FEDERAL'
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 25
""")
print(f"{'Employer':<55} {'Workers':>10} {'Union':>8}")
print('-'*78)
fed_total = 0
for row in cur.fetchall():
    print(f"{row['employer_name'][:55]:<55} {row['latest_unit_size'] or 0:>10,} {row['aff_abbr']:>8}")
    fed_total += row['latest_unit_size'] or 0

# 2. Check for federal agency keywords in PRIVATE sector
print('\n\n### 2. Potential Federal Employers MISCLASSIFIED as PRIVATE ###')
federal_keywords = [
    'department of', 'veterans', 'va ', 'usps', 'postal', 
    'air force', 'army', 'navy', 'marine', 'coast guard',
    'social security', 'irs', 'internal revenue', 'fbi', 'dea',
    'homeland security', 'tsa', 'customs', 'border', 'ice ',
    'federal', 'u.s.', 'united states', 'national guard'
]

cur.execute("""
    SELECT 
        f.employer_name,
        f.latest_unit_size,
        u.aff_abbr,
        u.sector_revised
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised = 'PRIVATE'
    AND (
        f.employer_name ILIKE '%department of%'
        OR f.employer_name ILIKE '%veterans%'
        OR f.employer_name ILIKE '% va %'
        OR f.employer_name ILIKE '%postal%'
        OR f.employer_name ILIKE '%usps%'
        OR f.employer_name ILIKE '%air force%'
        OR f.employer_name ILIKE '%army %'
        OR f.employer_name ILIKE '%navy %'
        OR f.employer_name ILIKE '%marine corps%'
        OR f.employer_name ILIKE '%coast guard%'
        OR f.employer_name ILIKE '%social security%'
        OR f.employer_name ILIKE '%irs %'
        OR f.employer_name ILIKE '%internal revenue%'
        OR f.employer_name ILIKE '%homeland security%'
        OR f.employer_name ILIKE '%tsa %'
        OR f.employer_name ILIKE '%customs%'
        OR f.employer_name ILIKE '%border patrol%'
        OR f.employer_name ILIKE '%federal %'
        OR f.employer_name ILIKE '%u.s. %'
        OR f.employer_name ILIKE '%national guard%'
    )
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 30
""")
print(f"{'Employer':<55} {'Workers':>10} {'Union':>8} {'Sector':>12}")
print('-'*90)
private_fed = 0
for row in cur.fetchall():
    print(f"{row['employer_name'][:55]:<55} {row['latest_unit_size'] or 0:>10,} {row['aff_abbr'] or 'N/A':>8} {row['sector_revised'] or 'N/A':>12}")
    private_fed += row['latest_unit_size'] or 0

print(f'\nTotal potentially misclassified: {private_fed:,}')

# 3. Check USPS specifically
print('\n\n### 3. USPS (Postal) in F-7 ###')
cur.execute("""
    SELECT 
        f.employer_name,
        f.latest_unit_size,
        u.aff_abbr,
        u.sector_revised
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.employer_name ILIKE '%postal%'
       OR f.employer_name ILIKE '%usps%'
       OR f.employer_name ILIKE '%post office%'
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
postal_total = 0
for row in cur.fetchall():
    print(f"  {row['employer_name'][:50]}: {row['latest_unit_size'] or 0:,} ({row['aff_abbr']}, {row['sector_revised']})")
    postal_total += row['latest_unit_size'] or 0
print(f'\nTotal Postal in F-7: {postal_total:,}')

# 4. Summary by union for FEDERAL sector
print('\n\n### 4. FEDERAL Sector Summary by Union ###')
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
print(f"{'Union':<15} {'Employers':>12} {'F-7 Workers':>15}")
print('-'*45)
total_fed_f7 = 0
for row in cur.fetchall():
    print(f"{row['aff_abbr']:<15} {row['employers']:>12,} {row['workers'] or 0:>15,}")
    total_fed_f7 += row['workers'] or 0
print(f"{'TOTAL':<15} {'':>12} {total_fed_f7:>15,}")

conn.close()

print('\n\n' + '='*70)
print('CONCLUSION')
print('='*70)
print(f'''
OPM Federal Bargaining Units:       1,284,167
OPM Estimated Members (~78%):       ~1,000,000

F-7 FEDERAL Sector Total:           {total_fed_f7:,}

KEY ISSUE: F-7 is NLRA (private sector). Federal employees use FSLMRA.
These {total_fed_f7:,} workers in F-7 FEDERAL sector are DATA ANOMALIES.

Possible explanations:
1. Private contractors working AT federal facilities
2. Non-appropriated fund (NAF) employees (technically private)
3. Data entry errors (wrong form filed)
4. TVA and USPS (semi-independent agencies)
''')
