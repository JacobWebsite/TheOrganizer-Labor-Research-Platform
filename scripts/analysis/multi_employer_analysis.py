import os
"""Multi-employer agreement analysis and handling"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

print('='*70)
print('MULTI-EMPLOYER ANALYSIS - CURRENT STATE')
print('='*70)

# Current totals
cur.execute('''
    SELECT COUNT(*) as employers, SUM(latest_unit_size) as total_workers
    FROM f7_employers_deduped
''')
row = cur.fetchone()
total_workers = row[1] or 0
print(f'\nCurrent: {row[0]:,} employers, {total_workers:,} total workers')
print(f'BLS Benchmark: 7,200,000 workers')
print(f'Current ratio: {total_workers/7200000*100:.1f}% of BLS')

# Check for SAG-AFTRA pattern
print('\n' + '='*70)
print('SAG-AFTRA PATTERN (Screen Actors Guild)')
print('='*70)
cur.execute('''
    SELECT employer_name, city, state, latest_unit_size, latest_union_name, latest_union_fnum
    FROM f7_employers_deduped
    WHERE latest_union_name ILIKE '%SAG%'
       OR latest_union_name ILIKE '%screen actor%'
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 20
''')
sag_total = 0
sag_count = 0
for row in cur.fetchall():
    workers = row[3] or 0
    sag_total += workers
    sag_count += 1
    print(f'  {workers:>8,} | fnum={row[5]} | {row[0][:50]}')
print(f'\n  SAG-AFTRA: {sag_count} records, {sag_total:,} total (should be ~165K once)')

# Check unions with multiple employer entries
print('\n' + '='*70)
print('UNIONS WITH MULTIPLE EMPLOYER ENTRIES (potential multi-employer)')
print('='*70)
cur.execute('''
    SELECT latest_union_fnum,
           MAX(latest_union_name) as union_name,
           COUNT(*) as employer_count,
           SUM(latest_unit_size) as total_workers,
           MAX(latest_unit_size) as max_workers,
           SUM(latest_unit_size) - MAX(latest_unit_size) as excess
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum
    HAVING COUNT(*) > 1 AND SUM(latest_unit_size) > 10000
    ORDER BY SUM(latest_unit_size) - MAX(latest_unit_size) DESC
    LIMIT 25
''')
print(f'{"Union Name":<45} | {"Emps":>5} | {"Total":>10} | {"Max":>10} | {"Excess":>10}')
print('-'*95)
for row in cur.fetchall():
    name = (row[1] or 'Unknown')[:45]
    print(f'{name:<45} | {row[2]:>5} | {row[3]:>10,} | {row[4]:>10,} | {row[5]:>10,}')

# Check signatory patterns
print('\n' + '='*70)
print('SIGNATORY PATTERNS (Building Trades, Entertainment)')
print('='*70)
cur.execute('''
    SELECT employer_name, latest_unit_size, latest_union_name
    FROM f7_employers_deduped
    WHERE employer_name ILIKE '%signator%'
       OR employer_name ILIKE '%all employers%'
       OR employer_name ILIKE '%various%employer%'
       OR employer_name ILIKE 'AGC %'
       OR city ILIKE 'various'
       OR city ILIKE 'multiple'
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 20
''')
for row in cur.fetchall():
    workers = row[1] or 0
    print(f'  {workers:>8,} | {row[0][:40]} | {(row[2] or "")[:30]}')

# Federal employers
print('\n' + '='*70)
print('FEDERAL EMPLOYERS (should exclude from BLS comparison)')
print('='*70)
cur.execute('''
    SELECT employer_name, latest_unit_size, city, state
    FROM f7_employers_deduped
    WHERE employer_name ILIKE '%department of veteran%'
       OR employer_name ILIKE '%postal service%'
       OR employer_name ILIKE '%u.s. department%'
       OR employer_name ILIKE '%dept of%'
       OR employer_name ILIKE 'USPS%'
       OR employer_name ILIKE '%federal%government%'
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 15
''')
fed_total = 0
for row in cur.fetchall():
    workers = row[1] or 0
    fed_total += workers
    print(f'  {workers:>8,} | {row[0][:50]}')
print(f'\n  Federal employers shown: {fed_total:,} workers')

# Corrupted records
print('\n' + '='*70)
print('CORRUPTED RECORDS')
print('='*70)
cur.execute('''
    SELECT employer_id, employer_name, latest_unit_size, latest_union_name
    FROM f7_employers_deduped
    WHERE latest_union_name ILIKE '%water temperature%'
       OR latest_union_name ILIKE '%saltwater%'
       OR LENGTH(latest_union_name) > 200
    LIMIT 10
''')
for row in cur.fetchall():
    print(f'  ID: {row[0]} | {row[1][:40]} | Workers: {row[2]}')
    print(f'    Union: {(row[3] or "")[:80]}...')

conn.close()
