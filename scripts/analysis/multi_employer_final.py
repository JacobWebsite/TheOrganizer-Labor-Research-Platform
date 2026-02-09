import os
"""
Multi-employer agreement handling - Final version
Creates views and finalizes deduplication
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
print('MULTI-EMPLOYER FINAL - Additional Deduplication + Views')
print('='*70)

# Additional rule: Identical round-number worker counts appearing 10+ times
print('\n1. Marking repeated identical worker counts (10+ occurrences)...')
cur.execute('''
    WITH repeated AS (
        SELECT employer_id, latest_union_fnum, latest_unit_size,
               ROW_NUMBER() OVER (
                   PARTITION BY latest_union_fnum, latest_unit_size
                   ORDER BY employer_id
               ) as rn,
               COUNT(*) OVER (PARTITION BY latest_union_fnum, latest_unit_size) as cnt
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND latest_unit_size >= 50
          AND exclude_reason IS NULL
    )
    UPDATE f7_employers_deduped f
    SET exclude_from_counts = TRUE,
        exclude_reason = 'REPEATED_WORKER_COUNT'
    FROM repeated r
    WHERE f.employer_id = r.employer_id
      AND r.rn > 1
      AND r.cnt >= 10
''')
print(f'   {cur.rowcount} additional records marked')
conn.commit()

# Check final totals
print('\n' + '='*70)
print('FINAL VALIDATION')
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
counted = row[2]
print(f'\n  Total employers: {row[0]:,}')
print(f'  Total workers (raw): {row[1]:,}')
print(f'  Counted workers: {counted:,}')
print(f'  Excluded workers: {row[3]:,}')
print(f'  Excluded records: {row[4]:,}')
print(f'\n  BLS Benchmark: 7,200,000')
print(f'  Before: {row[1]/7200000*100:.1f}% of BLS')
print(f'  After:  {counted/7200000*100:.1f}% of BLS')

# Breakdown
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

# ============================================================================
# CREATE VIEWS
# ============================================================================
print('\n' + '='*70)
print('CREATING VIEWS')
print('='*70)

# View 1: For BLS counts (only included records)
print('\n  Creating v_f7_for_bls_counts...')
cur.execute('''
    DROP VIEW IF EXISTS v_f7_for_bls_counts CASCADE;
    CREATE VIEW v_f7_for_bls_counts AS
    SELECT *
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
''')
conn.commit()

# View 2: Multi-employer group summary
print('  Creating v_multi_employer_groups...')
cur.execute('''
    DROP VIEW IF EXISTS v_multi_employer_groups CASCADE;
    CREATE VIEW v_multi_employer_groups AS
    SELECT
        multi_employer_group_id,
        MAX(latest_union_name) as union_name,
        MAX(CASE WHEN is_primary_in_group THEN employer_name END) as primary_employer,
        COUNT(*) as employers_in_agreement,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        SUM(latest_unit_size) as total_reported_workers,
        STRING_AGG(employer_name, '; ' ORDER BY latest_unit_size DESC) as all_employers
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
    GROUP BY multi_employer_group_id
''')
conn.commit()

# View 3: Employer with agreement context
print('  Creating v_employer_with_agreements...')
cur.execute('''
    DROP VIEW IF EXISTS v_employer_with_agreements CASCADE;
    CREATE VIEW v_employer_with_agreements AS
    SELECT
        f.*,
        CASE
            WHEN f.multi_employer_group_id IS NOT NULL THEN
                'Part of multi-employer agreement with ' ||
                (SELECT COUNT(*) - 1 FROM f7_employers_deduped f2
                 WHERE f2.multi_employer_group_id = f.multi_employer_group_id) ||
                ' other employers'
            WHEN f.exclude_reason = 'FEDERAL_EMPLOYER' THEN
                'Federal employer (excluded from private sector counts)'
            WHEN f.exclude_reason = 'CORRUPTED_DATA' THEN
                'Data quality issue (excluded from counts)'
            ELSE NULL
        END as agreement_note
    FROM f7_employers_deduped f
''')
conn.commit()

# View 4: Summary statistics view
print('  Creating v_f7_dedup_summary...')
cur.execute('''
    DROP VIEW IF EXISTS v_f7_dedup_summary CASCADE;
    CREATE VIEW v_f7_dedup_summary AS
    SELECT
        'Total Employers' as metric,
        COUNT(*)::text as value
    FROM f7_employers_deduped
    UNION ALL
    SELECT
        'Total Workers (Raw)',
        SUM(latest_unit_size)::text
    FROM f7_employers_deduped
    UNION ALL
    SELECT
        'Counted Workers (Deduplicated)',
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END)::text
    FROM f7_employers_deduped
    UNION ALL
    SELECT
        'Excluded Workers',
        SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END)::text
    FROM f7_employers_deduped
    UNION ALL
    SELECT
        'BLS Coverage %',
        ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1)::text || '%'
    FROM f7_employers_deduped
''')
conn.commit()

print('\n  Views created successfully!')

# Show view counts
print('\n  View record counts:')
for view in ['v_f7_for_bls_counts', 'v_multi_employer_groups', 'v_employer_with_agreements']:
    cur.execute(f'SELECT COUNT(*) FROM {view}')
    print(f'    {view}: {cur.fetchone()[0]:,} records')

conn.close()
print('\n' + '='*70)
print('COMPLETE')
print('='*70)
