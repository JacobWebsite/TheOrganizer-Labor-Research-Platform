"""Update state_coverage_comparison with deduplicated F7 private sector counts"""
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
print('UPDATING PRIVATE SECTOR COVERAGE FROM DEDUPLICATED F7')
print('='*80)

# Get current totals
print('\n1. CURRENT STATE_COVERAGE_COMPARISON TOTALS (excl DC)')
print('-'*80)
cur.execute('''
    SELECT SUM(platform_private) as current_private,
           SUM(epi_private) as epi_private
    FROM state_coverage_comparison
    WHERE state != 'DC'
''')
row = cur.fetchone()
current_private = row['current_private']
epi_private = row['epi_private']
print(f'   Current Platform Private: {current_private:,}')
print(f'   EPI Private Benchmark:    {epi_private:,}')
print(f'   Current Coverage:         {current_private/epi_private*100:.1f}%')

# Get new F7 deduplicated private sector by state
# Private = everything EXCEPT public sector (NAICS 92, 61, government names, federal)
# Use EXACT same classification as check_f7_adjustments.py
print('\n2. CALCULATING NEW F7 PRIVATE SECTOR BY STATE')
print('-'*80)
cur.execute('''
    SELECT
        COALESCE(state, 'XX') as state,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers
    FROM f7_employers_deduped
    WHERE NOT (
        naics IN ('92', '61')
        OR employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%'])
        OR exclude_reason = 'FEDERAL_EMPLOYER'
    )
    GROUP BY COALESCE(state, 'XX')
''')

new_by_state = {}
total_new = 0
for row in cur.fetchall():
    state = row['state']
    workers = row['workers'] or 0
    if state and len(state) == 2 and state != 'XX':
        new_by_state[state] = workers
        total_new += workers

print(f'   New F7 Private Total: {total_new:,}')
print(f'   States with data: {len(new_by_state)}')

# Verify against expected total
print(f'   Expected total: ~6,044,437')
print(f'   Difference: {total_new - 6044437:+,}')

# Show top 10 states
print('\n   Top 10 states:')
for i, (state, workers) in enumerate(sorted(new_by_state.items(), key=lambda x: -x[1])[:10]):
    print(f'      {state}: {workers:,}')

# Get comparison of old vs new by state
print('\n3. CHANGES BY STATE (Top 15 by absolute change)')
print('-'*80)
cur.execute('SELECT state, platform_private, epi_private FROM state_coverage_comparison WHERE state != %s', ['DC'])
old_by_state = {r['state']: (r['platform_private'], r['epi_private']) for r in cur.fetchall()}

changes = []
for state, new_workers in new_by_state.items():
    if state in old_by_state:
        old_workers, epi = old_by_state[state]
        change = new_workers - old_workers
        changes.append((state, old_workers, new_workers, change, epi))

changes.sort(key=lambda x: abs(x[3]), reverse=True)
print(f'{"State":<6} | {"Old":>12} | {"New":>12} | {"Change":>12} | {"New %":>8}')
print('-'*60)
for state, old, new, change, epi in changes[:15]:
    pct = new / epi * 100 if epi else 0
    print(f'{state:<6} | {old:>12,} | {new:>12,} | {change:>+12,} | {pct:>7.1f}%')

# Update state_coverage_comparison
print('\n4. UPDATING STATE_COVERAGE_COMPARISON')
print('-'*80)

updates = []
for state, workers in new_by_state.items():
    if state in old_by_state:
        _, epi = old_by_state[state]
        if epi and epi > 0:
            coverage_pct = round(workers / epi * 100, 1)

            # Determine flag based on methodology:
            # PRIVATE_OVER: >115%
            # PRIVATE_UNDER: <65%
            # Everything else (65-115%): No flag (acceptable)
            if coverage_pct > 115:
                flag = 'PRIVATE_OVER'
            elif coverage_pct < 65:
                flag = 'PRIVATE_UNDER'
            else:
                flag = None

            updates.append((workers, coverage_pct, flag, state))

# Execute updates
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

# Verify new totals
print('\n5. NEW TOTALS (excl DC)')
print('-'*80)
cur.execute('''
    SELECT SUM(platform_private) as new_private,
           SUM(epi_private) as epi_private,
           SUM(platform_public) as platform_public,
           SUM(epi_public) as epi_public,
           SUM(platform_total) as platform_total,
           SUM(epi_total) as epi_total
    FROM state_coverage_comparison
    WHERE state != 'DC'
''')
row = cur.fetchone()
new_priv = row['new_private']
epi_priv = row['epi_private']
plat_pub = row['platform_public']
epi_pub = row['epi_public']
plat_tot = row['platform_total']
epi_tot = row['epi_total']

print(f'   Private Sector:')
print(f'      Platform: {new_priv:,}')
print(f'      EPI:      {epi_priv:,}')
print(f'      Coverage: {new_priv/epi_priv*100:.1f}%')

print(f'\n   Public Sector (unchanged):')
print(f'      Platform: {plat_pub:,}')
print(f'      EPI:      {epi_pub:,}')
print(f'      Coverage: {plat_pub/epi_pub*100:.1f}%')

print(f'\n   Total:')
print(f'      Platform: {plat_tot:,}')
print(f'      EPI:      {epi_tot:,}')
print(f'      Coverage: {plat_tot/epi_tot*100:.1f}%')

# Summary
print('\n' + '='*80)
print('SUMMARY')
print('='*80)
print(f'''
BEFORE UPDATE:
   Private: 6,272,420 (87.0% of EPI)

AFTER UPDATE (with F7 deduplication):
   Private: {new_priv:,} ({new_priv/epi_priv*100:.1f}% of EPI)

The reduction reflects removal of:
- Multi-employer agreement double-counting
- SAG-AFTRA signatory duplicates
- Outlier/corrupted data
- Federal employers
''')

conn.close()
print('Done!')
