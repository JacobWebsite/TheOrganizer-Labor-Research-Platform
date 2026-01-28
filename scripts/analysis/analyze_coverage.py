"""
Private Sector Coverage Analysis
Uses F7 employer counts with median unit sizes to estimate coverage.
Avoids double-counting from multiple contracts for same workers.
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Public sector employer exclusion patterns
PUBLIC_SECTOR_EXCLUSIONS = '''
    AND employer_name NOT ILIKE '%%postal service%%'
    AND employer_name NOT ILIKE '%%usps%%'
    AND employer_name NOT ILIKE '%%department of%%'
    AND employer_name NOT ILIKE '%%dep''t of%%'
    AND employer_name NOT ILIKE '%%veterans affairs%%'
    AND employer_name NOT ILIKE '%%federal%%'
    AND employer_name NOT ILIKE '%%u.s. government%%'
    AND employer_name NOT ILIKE '%%state of %%'
    AND employer_name NOT ILIKE '%%city of %%'
    AND employer_name NOT ILIKE '%%county of %%'
    AND employer_name NOT ILIKE '%%board of education%%'
    AND employer_name NOT ILIKE '%%school district%%'
    AND employer_name NOT ILIKE '%%public school%%'
    AND employer_name NOT ILIKE '%%municipality%%'
    AND employer_name NOT ILIKE '%%transit authority%%'
    AND employer_name NOT ILIKE '%%housing authority%%'
    AND employer_name NOT ILIKE '%%HUD/%%'
'''

print('=' * 70)
print('PRIVATE SECTOR COVERAGE ANALYSIS')
print('=' * 70)
print()
print('Method: F7 employer counts × median unit sizes')
print('        Avoids double-counting from multiple contracts per employer')
print('        Public sector employers filtered out')
print()

# Overall F7 statistics
cur.execute(f'''
    SELECT
        COUNT(*) as employer_count,
        SUM(latest_unit_size) as total_raw,
        AVG(latest_unit_size)::int as avg_size,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size)::int as median_size,
        MAX(latest_unit_size) as max_size
    FROM f7_employers
    WHERE latest_unit_size IS NOT NULL
      AND latest_unit_size > 0
      AND latest_unit_size < 500000
      {PUBLIC_SECTOR_EXCLUSIONS}
''')

stats = cur.fetchone()
estimated = stats['employer_count'] * stats['median_size']

print('F7 PRIVATE EMPLOYER STATISTICS')
print('-' * 50)
print(f"Unique employers:         {stats['employer_count']:>15,}")
print(f"Raw sum (with duplication): {stats['total_raw']:>13,}")
print(f"Average unit size:        {stats['avg_size']:>15,}")
print(f"Median unit size:         {stats['median_size']:>15,}")
print()
print(f"Estimated workers:        {estimated:>15,}")
print(f"  (employers × median)")

# VR additions
cur.execute('SELECT SUM(num_employees) as total FROM nlrb_voluntary_recognition WHERE num_employees IS NOT NULL')
vr = cur.fetchone()['total'] or 0
print(f"+ Voluntary Recognition:  {vr:>15,}")
total_coverage = estimated + vr
print(f"TOTAL COVERAGE:           {total_coverage:>15,}")

# BLS comparison
print()
print('=' * 70)
print('COMPARISON TO BLS BENCHMARK')
print('=' * 70)
bls = 7300000
print(f"BLS Private Sector Union Members:  {bls:>12,}")
print(f"Platform Coverage:                 {total_coverage:>12,}")
print(f"Difference:                        {bls - total_coverage:>12,}")
print(f"Coverage Rate:                     {total_coverage/bls*100:>11.1f}%")

# Coverage by union
print()
print('=' * 70)
print('COVERAGE BY UNION AFFILIATION')
print('=' * 70)

cur.execute(f'''
    WITH classified AS (
        SELECT
            CASE
                WHEN latest_union_name ILIKE '%%teamster%%' OR latest_union_name ILIKE '%%ibt%%' THEN 'IBT'
                WHEN latest_union_name ILIKE '%%seiu%%' THEN 'SEIU'
                WHEN latest_union_name ILIKE '%%ufcw%%' THEN 'UFCW'
                WHEN latest_union_name ILIKE '%%uaw%%' THEN 'UAW'
                WHEN latest_union_name ILIKE '%%carpenter%%' OR latest_union_name ILIKE '%%cja%%' THEN 'CJA'
                WHEN latest_union_name ILIKE '%%ibew%%' OR latest_union_name ILIKE '%%electrical%%' THEN 'IBEW'
                WHEN latest_union_name ILIKE '%%usw%%' OR latest_union_name ILIKE '%%steelworker%%' THEN 'USW'
                WHEN latest_union_name ILIKE '%%liuna%%' OR latest_union_name ILIKE '%%laborer%%int%%' THEN 'LIUNA'
                WHEN latest_union_name ILIKE '%%operating engineer%%' OR latest_union_name ILIKE '%%iuoe%%' THEN 'IUOE'
                WHEN latest_union_name ILIKE '%%cwa%%' OR latest_union_name ILIKE '%%communication%%' THEN 'CWA'
                WHEN latest_union_name ILIKE '%%unite here%%' THEN 'UNITHERE'
                WHEN latest_union_name ILIKE '%%iatse%%' THEN 'IATSE'
                WHEN latest_union_name ILIKE '%%sag-aftra%%' OR latest_union_name ILIKE '%%screen actor%%'
                     OR latest_union_name ILIKE '%%sag%%' OR latest_union_name ILIKE '%%aftra%%' THEN 'SAG-AFTRA'
                WHEN latest_union_name ILIKE '%%machinist%%' OR latest_union_name ILIKE '%%iam%%' THEN 'IAM'
                WHEN latest_union_name ILIKE '%%nurse%%' OR latest_union_name ILIKE '%%nnu%%' THEN 'NNU'
                WHEN latest_union_name ILIKE '%%longshoremen%%' OR latest_union_name ILIKE '%%ila %%' THEN 'ILA'
                WHEN latest_union_name ILIKE '%%ppf%%' OR latest_union_name ILIKE '%%pipe%%fitter%%' THEN 'PPF'
                WHEN latest_union_name ILIKE '%%sheet metal%%' OR latest_union_name ILIKE '%%smart%%' THEN 'SMART'
                WHEN latest_union_name ILIKE '%%bricklayer%%' OR latest_union_name ILIKE '%%bac%%' THEN 'BAC'
                WHEN latest_union_name ILIKE '%%painter%%' THEN 'PAINTERS'
                WHEN latest_union_name ILIKE '%%atu%%' OR latest_union_name ILIKE '%%transit union%%' THEN 'ATU'
                ELSE 'OTHER'
            END as union_aff,
            employer_id,
            employer_name,
            latest_unit_size
        FROM f7_employers
        WHERE latest_unit_size IS NOT NULL
          AND latest_unit_size > 0
          AND latest_unit_size < 500000
          {PUBLIC_SECTOR_EXCLUSIONS}
    )
    SELECT
        union_aff,
        COUNT(*) as employers,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size)::int as median_size,
        (COUNT(*) * PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size))::bigint as est_workers,
        MAX(latest_unit_size) as max_unit
    FROM classified
    GROUP BY union_aff
    ORDER BY est_workers DESC
''')

print(f'{"Union":<12} {"Employers":>10} {"Median":>8} {"Est Workers":>12} {"Max Unit":>10}')
print('-' * 60)

grand_total = 0
rows = cur.fetchall()
for row in rows:
    grand_total += row['est_workers']
    if row['est_workers'] > 20000:
        print(f"{row['union_aff']:<12} {row['employers']:>10,} {row['median_size']:>8,} {row['est_workers']:>12,} {row['max_unit']:>10,}")

print('-' * 60)
print(f'{"TOTAL":<12} {"":>10} {"":>8} {grand_total:>12,}')

# Large bargaining units
print()
print('=' * 70)
print('LARGEST PRIVATE SECTOR BARGAINING UNITS')
print('(Multi-employer contracts show union name)')
print('=' * 70)

cur.execute(f'''
    SELECT
        CASE
            WHEN employer_name ILIKE '%%all signator%%' OR employer_name ILIKE '%%various%%'
                 OR employer_name ILIKE '%%multiple%%' OR employer_name ILIKE '%%joint policy%%'
            THEN latest_union_name
            ELSE employer_name
        END as display_name,
        latest_unit_size,
        city,
        state
    FROM f7_employers
    WHERE latest_unit_size >= 5000
      AND latest_unit_size < 500000
      {PUBLIC_SECTOR_EXCLUSIONS}
    ORDER BY latest_unit_size DESC
    LIMIT 20
''')

print(f'\n{"Name":<50} {"Workers":>10} {"Location":<15}')
print('-' * 80)
for row in cur.fetchall():
    name = (row['display_name'] or '')[:48]
    loc = f"{row['city'] or ''}, {row['state'] or ''}"[:13]
    print(f'{name:<50} {row["latest_unit_size"]:>10,} {loc:<15}')

conn.close()
