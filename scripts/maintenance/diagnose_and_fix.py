"""Diagnose and fix the private sector coverage issue"""
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
print('DIAGNOSING PRIVATE SECTOR QUERY ISSUE')
print('='*80)

# Check what the check_f7_adjustments query returns
print('\n1. ORIGINAL CLASSIFICATION QUERY (from check_f7_adjustments)')
print('-'*80)
cur.execute('''
    SELECT
        CASE
            WHEN naics IN ('92', '61') THEN 'Public (NAICS)'
            WHEN employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%']) THEN 'Public (Name)'
            WHEN exclude_reason = 'FEDERAL_EMPLOYER' THEN 'Federal'
            ELSE 'Private'
        END as sector,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
    FROM f7_employers_deduped
    GROUP BY 1
    ORDER BY 2 DESC
''')
for row in cur.fetchall():
    print(f"   {row['sector']}: {row['counted_workers']:,}")

# Check the problematic query
print('\n2. PROBLEMATIC QUERY DEBUG')
print('-'*80)
cur.execute('''
    SELECT COUNT(*) as cnt,
           SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers
    FROM f7_employers_deduped
    WHERE NOT (
        naics IN ('92', '61')
        OR employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%'])
        OR exclude_reason = 'FEDERAL_EMPLOYER'
    )
''')
row = cur.fetchone()
print(f"   Employers: {row['cnt']:,}")
print(f"   Workers: {row['workers']:,}")

# Check what's happening with exclude_reason
print('\n3. EXCLUDE_REASON VALUES')
print('-'*80)
cur.execute('SELECT DISTINCT exclude_reason FROM f7_employers_deduped')
for row in cur.fetchall():
    print(f"   '{row['exclude_reason']}'")

# Check if the issue is with NULL handling
print('\n4. CHECK NULL HANDLING')
print('-'*80)
cur.execute('''
    SELECT
        exclude_reason IS NULL as is_null,
        COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY exclude_reason IS NULL
''')
for row in cur.fetchall():
    print(f"   exclude_reason IS NULL = {row['is_null']}: {row['cnt']:,} rows")

# The correct query should handle NULLs properly
print('\n5. CORRECTED QUERY')
print('-'*80)
cur.execute('''
    SELECT
        COALESCE(state, 'XX') as state,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers
    FROM f7_employers_deduped
    WHERE naics NOT IN ('92', '61')
      AND NOT (employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%']))
      AND (exclude_reason IS NULL OR exclude_reason != 'FEDERAL_EMPLOYER')
    GROUP BY COALESCE(state, 'XX')
''')
total = 0
state_data = {}
for row in cur.fetchall():
    state = row['state']
    workers = row['workers'] or 0
    if state and len(state) == 2 and state != 'XX':
        state_data[state] = workers
        total += workers

print(f"   Total private workers: {total:,}")
print(f"   States: {len(state_data)}")

# Now fix the state_coverage_comparison table
print('\n6. RESTORING AND UPDATING STATE_COVERAGE_COMPARISON')
print('-'*80)

# Get EPI benchmarks
cur.execute('SELECT state, epi_private FROM state_coverage_comparison WHERE state != %s', ['DC'])
epi_by_state = {r['state']: r['epi_private'] for r in cur.fetchall()}

updates = []
for state, workers in state_data.items():
    if state in epi_by_state:
        epi = epi_by_state[state]
        if epi and epi > 0:
            coverage_pct = round(workers / epi * 100, 1)

            if coverage_pct > 115:
                flag = 'PRIVATE_OVER'
            elif coverage_pct < 65:
                flag = 'PRIVATE_UNDER'
            else:
                flag = None

            updates.append((workers, coverage_pct, flag, state))

print(f'   Updating {len(updates)} states...')
cur.executemany('''
    UPDATE state_coverage_comparison
    SET platform_private = %s,
        private_coverage_pct = %s,
        private_flag = %s,
        last_updated = NOW()
    WHERE state = %s
''', updates)

# Update totals
cur.execute('''
    UPDATE state_coverage_comparison
    SET platform_total = platform_private + platform_public,
        total_coverage_pct = ROUND((platform_private + platform_public)::numeric / NULLIF(epi_total, 0) * 100, 1)
''')

conn.commit()
print('   Updates committed.')

# Verify
print('\n7. FINAL TOTALS (excl DC)')
print('-'*80)
cur.execute('''
    SELECT SUM(platform_private) as pp,
           SUM(epi_private) as ep,
           SUM(platform_public) as pub,
           SUM(epi_public) as epub,
           SUM(platform_total) as pt,
           SUM(epi_total) as et
    FROM state_coverage_comparison
    WHERE state != 'DC'
''')
row = cur.fetchone()
print(f'   Private: {row["pp"]:,} / {row["ep"]:,} = {row["pp"]/row["ep"]*100:.1f}%')
print(f'   Public:  {row["pub"]:,} / {row["epub"]:,} = {row["pub"]/row["epub"]*100:.1f}%')
print(f'   Total:   {row["pt"]:,} / {row["et"]:,} = {row["pt"]/row["et"]*100:.1f}%')

conn.close()
print('\nDone!')
