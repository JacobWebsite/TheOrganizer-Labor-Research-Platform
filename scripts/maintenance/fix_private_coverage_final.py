"""Fix private sector coverage with proper NULL handling"""
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
print('FIXING PRIVATE SECTOR COVERAGE')
print('='*80)

# The correct way to get private sector:
# Use the SAME CASE logic as check_f7_adjustments, then filter for 'Private'
print('\n1. GETTING PRIVATE SECTOR BY STATE (correct logic)')
print('-'*80)

cur.execute('''
    WITH classified AS (
        SELECT
            state,
            latest_unit_size,
            exclude_from_counts,
            CASE
                WHEN naics IN ('92', '61') THEN 'Public'
                WHEN employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%']) THEN 'Public'
                WHEN exclude_reason = 'FEDERAL_EMPLOYER' THEN 'Federal'
                ELSE 'Private'
            END as sector
        FROM f7_employers_deduped
    )
    SELECT
        COALESCE(state, 'XX') as state,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers
    FROM classified
    WHERE sector = 'Private'
    GROUP BY COALESCE(state, 'XX')
''')

state_data = {}
total = 0
for row in cur.fetchall():
    state = row['state']
    workers = row['workers'] or 0
    if state and len(state) == 2 and state != 'XX':
        state_data[state] = workers
        total += workers

print(f'   Total private workers: {total:,}')
print(f'   Expected: ~6,044,437')
print(f'   Match: {abs(total - 6044437) < 1000}')
print(f'   States: {len(state_data)}')

# Top 10 states
print('\n   Top 10 states:')
for state, workers in sorted(state_data.items(), key=lambda x: -x[1])[:10]:
    print(f'      {state}: {workers:,}')

# Update state_coverage_comparison
print('\n2. UPDATING STATE_COVERAGE_COMPARISON')
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

# Final verification
print('\n3. FINAL TOTALS (excl DC)')
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
pp = row["pp"]
ep = row["ep"]
pub = row["pub"]
epub = row["epub"]
pt = row["pt"]
et = row["et"]

print(f'   Private: {pp:,} / {ep:,} = {pp/ep*100:.1f}%')
print(f'   Public:  {pub:,} / {epub:,} = {pub/epub*100:.1f}%')
print(f'   Total:   {pt:,} / {et:,} = {pt/et*100:.1f}%')

# Compare to original CSV values
print('\n4. COMPARISON TO ORIGINAL CSV')
print('-'*80)
print(f'   Original CSV Private: 6,272,420 (87.0%)')
print(f'   New Deduplicated:     {pp:,} ({pp/ep*100:.1f}%)')
print(f'   Difference:           {pp - 6272420:+,}')
print(f'')
print(f'   The reduction of ~{6272420 - pp:,} workers reflects:')
print(f'   - Multi-employer agreement deduplication')
print(f'   - SAG-AFTRA signatory removal')
print(f'   - Outlier/corrupted data removal')

conn.close()
print('\nDone!')
