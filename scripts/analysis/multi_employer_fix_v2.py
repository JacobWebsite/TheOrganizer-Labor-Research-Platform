import os
"""
Multi-employer agreement handling - v2: More selective deduplication
Only exclude clear duplicates, not legitimate separate employers
"""
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
print('MULTI-EMPLOYER FIX v2 - More Selective Approach')
print('='*70)

# Reset all flags
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

# ============================================================================
# Category 1: SAG-AFTRA (clear multi-employer - all signatories share one pool)
# ============================================================================
print('\n1. SAG-AFTRA signatories (clear duplication)...')
cur.execute('''
    WITH sag_employers AS (
        SELECT employer_id, latest_unit_size,
               ROW_NUMBER() OVER (ORDER BY latest_unit_size DESC) as rn
        FROM f7_employers_deduped
        WHERE latest_union_fnum = 391
           OR latest_union_name ILIKE '%SAG%AFTRA%'
           OR latest_union_name ILIKE '%screen actor%'
    )
    UPDATE f7_employers_deduped f
    SET multi_employer_group_id = 1,
        is_primary_in_group = (s.rn = 1),
        exclude_from_counts = (s.rn > 1),
        exclude_reason = CASE WHEN s.rn > 1 THEN 'SAG_AFTRA_SIGNATORY' ELSE NULL END
    FROM sag_employers s
    WHERE f.employer_id = s.employer_id
''')
print(f'   {cur.rowcount} records processed')
conn.commit()

# ============================================================================
# Category 2: Federal employers (not private sector)
# ============================================================================
print('\n2. Federal employers (exclude from BLS private sector)...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'FEDERAL_EMPLOYER'
    WHERE (employer_name ILIKE '%department of veteran%'
       OR employer_name ILIKE '%postal service%'
       OR employer_name ILIKE '%u.s. department%'
       OR employer_name ILIKE '%u.s. dept%'
       OR employer_name ILIKE 'USPS %'
       OR employer_name ILIKE '%dept of defense%')
      AND exclude_reason IS NULL
''')
print(f'   {cur.rowcount} records marked')
conn.commit()

# ============================================================================
# Category 3: Corrupted records
# ============================================================================
print('\n3. Corrupted records...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'CORRUPTED_DATA'
    WHERE (latest_union_name ILIKE '%water temperature%'
       OR latest_union_name ILIKE '%saltwater%')
      AND exclude_reason IS NULL
''')
print(f'   {cur.rowcount} records marked')
conn.commit()

# ============================================================================
# Category 4: Clear signatory patterns (AGC, "All Signatories", etc.)
# These represent multiple employers under one agreement
# ============================================================================
print('\n4. Clear signatory/association patterns...')
cur.execute('''
    UPDATE f7_employers_deduped
    SET exclude_from_counts = TRUE,
        exclude_reason = 'SIGNATORY_PATTERN',
        multi_employer_group_id = COALESCE(latest_union_fnum, 0) + 2000
    WHERE (employer_name ILIKE 'AGC %'
       OR employer_name ILIKE 'AGC of %'
       OR employer_name ILIKE '%all signator%'
       OR employer_name ILIKE '%signatories to%'
       OR employer_name ILIKE 'various %contractor%'
       OR employer_name ILIKE 'various employers%'
       OR employer_name ILIKE 'multiple %'
       OR employer_name ILIKE '%company list%'
       OR city ILIKE 'various'
       OR city ILIKE 'multiple')
      AND exclude_reason IS NULL
      AND latest_unit_size >= 1000
''')
print(f'   {cur.rowcount} records marked')
conn.commit()

# ============================================================================
# Category 5: Duplicate worker counts within same union
# If same union has multiple entries with IDENTICAL large worker counts,
# those are duplicates (keep only one)
# ============================================================================
print('\n5. Duplicate worker counts within same union...')
cur.execute('''
    WITH duplicates AS (
        SELECT employer_id, latest_union_fnum, latest_unit_size,
               ROW_NUMBER() OVER (
                   PARTITION BY latest_union_fnum, latest_unit_size
                   ORDER BY employer_id
               ) as rn,
               COUNT(*) OVER (PARTITION BY latest_union_fnum, latest_unit_size) as cnt
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND latest_unit_size >= 1000
          AND exclude_reason IS NULL
    )
    UPDATE f7_employers_deduped f
    SET exclude_from_counts = TRUE,
        exclude_reason = 'DUPLICATE_WORKER_COUNT',
        multi_employer_group_id = d.latest_union_fnum + 3000
    FROM duplicates d
    WHERE f.employer_id = d.employer_id
      AND d.rn > 1
      AND d.cnt > 1
''')
print(f'   {cur.rowcount} records marked')
conn.commit()

# ============================================================================
# Category 6: Very large discrepancy within union (likely data error)
# If one employer in a union shows 100x more workers than the median,
# it's likely a data entry error
# ============================================================================
print('\n6. Outlier worker counts (potential data errors)...')
cur.execute('''
    WITH union_stats AS (
        SELECT latest_union_fnum,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY latest_unit_size) as median_workers,
               MAX(latest_unit_size) as max_workers,
               COUNT(*) as emp_count
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND latest_unit_size > 0
          AND exclude_reason IS NULL
        GROUP BY latest_union_fnum
        HAVING COUNT(*) >= 3
           AND MAX(latest_unit_size) > percentile_cont(0.5) WITHIN GROUP (ORDER BY latest_unit_size) * 50
    )
    UPDATE f7_employers_deduped f
    SET exclude_from_counts = TRUE,
        exclude_reason = 'OUTLIER_WORKER_COUNT'
    FROM union_stats us
    WHERE f.latest_union_fnum = us.latest_union_fnum
      AND f.latest_unit_size = us.max_workers
      AND f.latest_unit_size > us.median_workers * 50
      AND f.exclude_reason IS NULL
''')
print(f'   {cur.rowcount} records marked')
conn.commit()

# ============================================================================
# VALIDATION
# ============================================================================
print('\n' + '='*70)
print('VALIDATION RESULTS')
print('='*70)

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
print(f'  Counted workers: {row[2]:,}')
print(f'  Excluded workers: {row[3]:,}')
print(f'  Excluded records: {row[4]:,}')
print(f'\n  BLS Benchmark: 7,200,000')
print(f'  Before: {row[1]/7200000*100:.1f}% of BLS')
print(f'  After:  {row[2]/7200000*100:.1f}% of BLS')

# Breakdown by reason
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
    workers = row[2] or 0
    print(f'    {row[0]:<30} | {row[1]:>6} employers | {workers:>12,} workers')

conn.close()
print('\n' + '='*70)
print('COMPLETE')
print('='*70)
