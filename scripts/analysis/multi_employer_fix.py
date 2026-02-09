import os
"""
Multi-employer agreement handling - Phase 1: Schema and Grouping
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

print('='*70)
print('PHASE 1: ADD TRACKING COLUMNS')
print('='*70)

# Add new columns
cur.execute('''
    ALTER TABLE f7_employers_deduped
    ADD COLUMN IF NOT EXISTS multi_employer_group_id INTEGER,
    ADD COLUMN IF NOT EXISTS is_primary_in_group BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS group_max_workers INTEGER,
    ADD COLUMN IF NOT EXISTS exclude_from_counts BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS exclude_reason VARCHAR(50)
''')
conn.commit()
print('  Added tracking columns')

print('\n' + '='*70)
print('PHASE 2: IDENTIFY AND GROUP MULTI-EMPLOYER AGREEMENTS')
print('='*70)

# Reset all flags first
cur.execute('''
    UPDATE f7_employers_deduped
    SET multi_employer_group_id = NULL,
        is_primary_in_group = TRUE,
        group_max_workers = NULL,
        exclude_from_counts = FALSE,
        exclude_reason = NULL
''')
conn.commit()
print('  Reset all flags')

# Group 1: SAG-AFTRA (special handling - all signatories are same pool)
print('\n  Grouping SAG-AFTRA signatories...')
cur.execute('''
    WITH sag_employers AS (
        SELECT employer_id, latest_unit_size
        FROM f7_employers_deduped
        WHERE latest_union_fnum = 391
           OR latest_union_name ILIKE '%SAG%AFTRA%'
           OR latest_union_name ILIKE '%screen actor%'
    ),
    sag_max AS (
        SELECT MAX(latest_unit_size) as max_workers FROM sag_employers
    )
    UPDATE f7_employers_deduped f
    SET multi_employer_group_id = 1,
        group_max_workers = (SELECT max_workers FROM sag_max),
        is_primary_in_group = (f.latest_unit_size = (SELECT max_workers FROM sag_max)),
        exclude_from_counts = (f.latest_unit_size != (SELECT max_workers FROM sag_max)),
        exclude_reason = CASE
            WHEN f.latest_unit_size != (SELECT max_workers FROM sag_max)
            THEN 'MULTI_EMPLOYER_SECONDARY'
            ELSE NULL
        END
    FROM sag_employers s
    WHERE f.employer_id = s.employer_id
''')
sag_count = cur.rowcount
conn.commit()
print(f'    SAG-AFTRA: {sag_count} records grouped')

# Group 2: Federal employers (exclude entirely)
print('\n  Marking federal employers...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'FEDERAL_EMPLOYER'
    WHERE (employer_name ILIKE '%department of veteran%'
       OR employer_name ILIKE '%postal service%'
       OR employer_name ILIKE '%u.s. department%'
       OR employer_name ILIKE '%u.s. dept%'
       OR employer_name ILIKE 'USPS%'
       OR employer_name ILIKE '%federal%government%'
       OR employer_name ILIKE '%dept of defense%')
      AND exclude_reason IS NULL
''')
fed_count = cur.rowcount
conn.commit()
print(f'    Federal employers: {fed_count} records marked')

# Group 3: Corrupted records
print('\n  Marking corrupted records...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'CORRUPTED_DATA'
    WHERE (latest_union_name ILIKE '%water temperature%'
       OR latest_union_name ILIKE '%saltwater%'
       OR LENGTH(latest_union_name) > 200)
      AND exclude_reason IS NULL
''')
corrupt_count = cur.rowcount
conn.commit()
print(f'    Corrupted records: {corrupt_count} records marked')

# Group 4-N: Other unions with multiple employers (same union fnum)
print('\n  Grouping other multi-employer unions...')
cur.execute('''
    WITH union_groups AS (
        SELECT latest_union_fnum,
               COUNT(*) as emp_count,
               MAX(latest_unit_size) as max_workers,
               SUM(latest_unit_size) as total_workers
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND multi_employer_group_id IS NULL
          AND exclude_reason IS NULL
        GROUP BY latest_union_fnum
        HAVING COUNT(*) > 1
           AND MAX(latest_unit_size) > 0
           AND SUM(latest_unit_size) > MAX(latest_unit_size) * 1.5
    )
    UPDATE f7_employers_deduped f
    SET multi_employer_group_id = f.latest_union_fnum + 1000,
        group_max_workers = ug.max_workers,
        is_primary_in_group = (f.latest_unit_size = ug.max_workers),
        exclude_from_counts = (f.latest_unit_size != ug.max_workers
                               AND f.latest_unit_size < ug.max_workers * 0.9),
        exclude_reason = CASE
            WHEN f.latest_unit_size != ug.max_workers
                 AND f.latest_unit_size < ug.max_workers * 0.9
            THEN 'MULTI_EMPLOYER_SECONDARY'
            ELSE NULL
        END
    FROM union_groups ug
    WHERE f.latest_union_fnum = ug.latest_union_fnum
      AND f.multi_employer_group_id IS NULL
      AND f.exclude_reason IS NULL
''')
multi_count = cur.rowcount
conn.commit()
print(f'    Other multi-employer: {multi_count} records grouped')

# Special handling for AGC signatories
print('\n  Grouping AGC (building trades) signatories...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'BUILDING_TRADES_SIGNATORY'
    WHERE (employer_name ILIKE 'AGC %'
       OR employer_name ILIKE '%signator%'
       OR employer_name ILIKE '%all employers%'
       OR city ILIKE 'various'
       OR city ILIKE 'multiple')
      AND exclude_reason IS NULL
      AND latest_unit_size > 1000
''')
agc_count = cur.rowcount
conn.commit()
print(f'    AGC/Signatory patterns: {agc_count} records marked')

print('\n' + '='*70)
print('PHASE 3: VALIDATION')
print('='*70)

# Before/After comparison
cur.execute('''
    SELECT
        COUNT(*) as total_employers,
        SUM(latest_unit_size) as total_workers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END) as excluded_workers,
        COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_count
    FROM f7_employers_deduped
''')
row = cur.fetchone()
print(f'\n  Total employers: {row[0]:,}')
print(f'  Total workers (raw): {row[1]:,}')
print(f'  Counted workers (deduplicated): {row[2]:,}')
print(f'  Excluded workers: {row[3]:,}')
print(f'  Excluded employer records: {row[4]:,}')
print(f'\n  BLS Benchmark: 7,200,000')
print(f'  Before: {row[1]/7200000*100:.1f}% of BLS')
print(f'  After:  {row[2]/7200000*100:.1f}% of BLS')

# Breakdown by exclusion reason
print('\n  Exclusion breakdown:')
cur.execute('''
    SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
           COUNT(*) as employers,
           SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    GROUP BY exclude_reason
    ORDER BY SUM(latest_unit_size) DESC
''')
for row in cur.fetchall():
    print(f'    {row[0]:<30} | {row[1]:>6} employers | {row[2]:>12,} workers')

# Top groups by deduplication savings
print('\n  Top 10 multi-employer groups by dedup savings:')
cur.execute('''
    SELECT multi_employer_group_id,
           MAX(latest_union_name) as union_name,
           COUNT(*) as employers,
           SUM(latest_unit_size) as total_workers,
           MAX(group_max_workers) as counted_workers,
           SUM(latest_unit_size) - MAX(group_max_workers) as savings
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
    GROUP BY multi_employer_group_id
    HAVING SUM(latest_unit_size) > MAX(group_max_workers)
    ORDER BY SUM(latest_unit_size) - MAX(group_max_workers) DESC
    LIMIT 10
''')
print(f'  {"Union":<40} | {"Emps":>5} | {"Total":>10} | {"Counted":>10} | {"Savings":>10}')
print('  ' + '-'*90)
for row in cur.fetchall():
    name = (row[1] or 'Unknown')[:40]
    print(f'  {name:<40} | {row[2]:>5} | {row[3]:>10,} | {row[4]:>10,} | {row[5]:>10,}')

conn.commit()
conn.close()
print('\n' + '='*70)
print('PHASE 1-3 COMPLETE')
print('='*70)
