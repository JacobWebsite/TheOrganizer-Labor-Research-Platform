import os
"""
Verify multi-employer group assignments in f7_employers_deduped.
READ-ONLY - does not modify any data.

Runs 5 checks:
1. Every group has exactly 1 primary
2. Excluded records have valid reason
3. Primaries not excluded
4. BLS coverage check
5. Large union double-counting
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)

BLS_PRIVATE_BENCHMARK = 7_200_000

results = []  # (check_name, status, details)

print('=' * 70)
print('MULTI-EMPLOYER GROUP VERIFICATION (read-only)')
print('=' * 70)

# ============================================================================
# Check 1: Every group has exactly 1 primary
# ============================================================================
print('\n--- Check 1: Every group has exactly 1 primary ---')

cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute('''
    SELECT multi_employer_group_id,
           SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) as primary_count,
           COUNT(*) as total_in_group
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
    GROUP BY multi_employer_group_id
    HAVING SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) != 1
''')
bad_groups = cur.fetchall()

zero_primary = [g for g in bad_groups if g['primary_count'] == 0]
multi_primary = [g for g in bad_groups if g['primary_count'] > 1]

if zero_primary:
    print(f'  [FAIL] {len(zero_primary)} group(s) with 0 primaries:')
    for g in zero_primary[:10]:
        print(f'    group_id={g["multi_employer_group_id"]}, members={g["total_in_group"]}')
    if len(zero_primary) > 10:
        print(f'    ... and {len(zero_primary) - 10} more')
else:
    print('  No groups with 0 primaries.')

if multi_primary:
    print(f'  [FAIL] {len(multi_primary)} group(s) with >1 primaries:')
    for g in multi_primary[:10]:
        print(f'    group_id={g["multi_employer_group_id"]}, primaries={g["primary_count"]}, members={g["total_in_group"]}')
    if len(multi_primary) > 10:
        print(f'    ... and {len(multi_primary) - 10} more')
else:
    print('  No groups with >1 primaries.')

if not bad_groups:
    results.append(('1. Group primaries', 'PASS', 'All groups have exactly 1 primary'))
else:
    details = []
    if zero_primary:
        details.append(f'{len(zero_primary)} with 0 primaries')
    if multi_primary:
        details.append(f'{len(multi_primary)} with >1 primaries')
    results.append(('1. Group primaries', 'FAIL', '; '.join(details)))

# Also count total groups for reference
cur.execute('''
    SELECT COUNT(DISTINCT multi_employer_group_id) as group_count,
           COUNT(*) as grouped_records
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
''')
group_stats = cur.fetchone()
print(f'  Total groups: {group_stats["group_count"]}, total grouped records: {group_stats["grouped_records"]}')

# ============================================================================
# Check 2: Excluded records have valid reason
# ============================================================================
print('\n--- Check 2: Excluded records have valid reason ---')

cur.execute('''
    SELECT COUNT(*) as missing_reason
    FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
      AND (exclude_reason IS NULL OR exclude_reason = '')
''')
row = cur.fetchone()
missing_count = row['missing_reason']

if missing_count == 0:
    print('  All excluded records have a documented reason.')
    results.append(('2. Exclusion reasons', 'PASS', 'All excluded records have reasons'))
else:
    print(f'  [FAIL] {missing_count} excluded record(s) have no reason.')
    # Show a few examples
    cur.execute('''
        SELECT employer_id, employer_name, latest_union_name, latest_unit_size
        FROM f7_employers_deduped
        WHERE exclude_from_counts = TRUE
          AND (exclude_reason IS NULL OR exclude_reason = '')
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 5
    ''')
    for r in cur.fetchall():
        print(f'    {r["employer_id"][:12]}.. | {r["employer_name"][:40]:<40} | workers={r["latest_unit_size"]}')
    results.append(('2. Exclusion reasons', 'FAIL', f'{missing_count} excluded without reason'))

# ============================================================================
# Check 3: Primaries not excluded
# ============================================================================
print('\n--- Check 3: Primaries not excluded ---')

# Only check records that are primary within an actual group (group_id IS NOT NULL).
# Records with is_primary_in_group=TRUE but group_id=NULL are just defaults.
#
# Additionally, distinguish two cases:
#  (a) Groups where ALL members are excluded (SIGNATORY_PATTERN, etc.) -- expected
#  (b) Groups where some members are counted but the primary is excluded -- problematic
cur.execute('''
    WITH group_info AS (
        SELECT multi_employer_group_id,
               SUM(CASE WHEN exclude_from_counts = FALSE THEN 1 ELSE 0 END) as counted_members,
               COUNT(*) as total_members
        FROM f7_employers_deduped
        WHERE multi_employer_group_id IS NOT NULL
        GROUP BY multi_employer_group_id
    )
    SELECT f.employer_id, f.employer_name, f.multi_employer_group_id, f.exclude_reason,
           g.counted_members, g.total_members
    FROM f7_employers_deduped f
    JOIN group_info g ON f.multi_employer_group_id = g.multi_employer_group_id
    WHERE f.is_primary_in_group = TRUE
      AND f.exclude_from_counts = TRUE
      AND f.multi_employer_group_id IS NOT NULL
''')
bad_primaries_in_group = cur.fetchall()

# Split into "all-excluded groups" (expected) vs "mixed groups" (problematic)
all_excluded = [r for r in bad_primaries_in_group if r['counted_members'] == 0]
mixed_groups = [r for r in bad_primaries_in_group if r['counted_members'] > 0]

# Also count the default-primary excluded records for info
cur.execute('''
    SELECT COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE is_primary_in_group = TRUE
      AND exclude_from_counts = TRUE
      AND multi_employer_group_id IS NULL
''')
default_primary_excluded = cur.fetchone()['cnt']

if not mixed_groups:
    print('  No problematic group primaries (primary excluded while other members counted).')
    if all_excluded:
        print(f'  (Info: {len(all_excluded)} group primaries excluded in fully-excluded groups -- expected)')
    results.append(('3. Primary not excluded', 'PASS', f'0 problematic; {len(all_excluded)} in fully-excluded groups'))
else:
    print(f'  [FAIL] {len(mixed_groups)} group primary(s) excluded while other members are counted:')
    for r in mixed_groups[:10]:
        print(f'    group={r["multi_employer_group_id"]} | {r["employer_name"][:40]:<40} | reason={r["exclude_reason"]} | counted={r["counted_members"]}/{r["total_members"]}')
    if len(mixed_groups) > 10:
        print(f'    ... and {len(mixed_groups) - 10} more')
    if all_excluded:
        print(f'  (Info: {len(all_excluded)} additional primaries in fully-excluded groups -- expected)')
    results.append(('3. Primary not excluded', 'FAIL', f'{len(mixed_groups)} problematic; {len(all_excluded)} expected'))

if default_primary_excluded > 0:
    print(f'  (Info: {default_primary_excluded} excluded records have default is_primary=TRUE but no group_id -- not a problem)')

# ============================================================================
# Check 4: BLS Coverage Check
# ============================================================================
print('\n--- Check 4: BLS Coverage Check ---')

cur.execute('''
    SELECT
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        SUM(latest_unit_size) as total_workers,
        COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_count,
        COUNT(*) as total_employers
    FROM f7_employers_deduped
''')
bls = cur.fetchone()
counted = bls['counted_workers'] or 0
total = bls['total_workers'] or 0
excluded_n = bls['excluded_count']
coverage_pct = counted / BLS_PRIVATE_BENCHMARK * 100 if BLS_PRIVATE_BENCHMARK else 0

print(f'  Total employers: {bls["total_employers"]:,}')
print(f'  Total workers (raw): {total:,}')
print(f'  Counted workers: {counted:,}')
print(f'  Excluded workers: {total - counted:,} ({excluded_n} records)')
print(f'  BLS Benchmark: {BLS_PRIVATE_BENCHMARK:,}')
print(f'  Coverage: {coverage_pct:.1f}%')

if 90 <= coverage_pct <= 110:
    results.append(('4. BLS coverage', 'PASS', f'{coverage_pct:.1f}% (target 90-110%)'))
else:
    direction = 'above' if coverage_pct > 110 else 'below'
    results.append(('4. BLS coverage', 'FAIL', f'{coverage_pct:.1f}% -- {direction} 90-110% target'))

# Breakdown by exclusion reason
print('\n  Exclusion breakdown:')
cur.execute('''
    SELECT COALESCE(exclude_reason, '(included)') as reason,
           COUNT(*) as employers,
           SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    GROUP BY exclude_reason
    ORDER BY SUM(latest_unit_size) DESC
''')
for r in cur.fetchall():
    workers = r['workers'] or 0
    print(f'    {r["reason"]:<30} | {r["employers"]:>6} employers | {workers:>12,} workers')

# ============================================================================
# Check 5: Large union double-counting
# ============================================================================
print('\n--- Check 5: Large union double-counting (>500K workers) ---')

cur.execute('''
    SELECT latest_union_fnum, latest_union_name,
           COUNT(*) as employer_count,
           SUM(latest_unit_size) as total_workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE AND latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum, latest_union_name
    HAVING SUM(latest_unit_size) > 500000
    ORDER BY SUM(latest_unit_size) DESC
''')
big_unions = cur.fetchall()

if not big_unions:
    print('  No union exceeds 500K counted workers.')
    results.append(('5. Union double-count', 'PASS', 'No union > 500K workers'))
else:
    print(f'  [WARN] {len(big_unions)} union(s) exceed 500K counted workers:')
    for u in big_unions:
        print(f'    fnum={u["latest_union_fnum"]} | {u["latest_union_name"][:45]:<45} | {u["employer_count"]:>5} employers | {u["total_workers"]:>10,} workers')
    results.append(('5. Union double-count', 'WARN', f'{len(big_unions)} union(s) > 500K workers'))

# ============================================================================
# Summary
# ============================================================================
print('\n' + '=' * 70)
print('VERIFICATION SUMMARY')
print('=' * 70)
print(f'  {"Check":<30} | {"Status":<6} | Details')
print(f'  {"-"*30}-+-{"-"*6}-+-{"-"*40}')
for name, status, details in results:
    print(f'  {name:<30} | {status:<6} | {details}')

pass_count = sum(1 for _, s, _ in results if s == 'PASS')
fail_count = sum(1 for _, s, _ in results if s == 'FAIL')
warn_count = sum(1 for _, s, _ in results if s == 'WARN')
print(f'\n  {pass_count} PASS, {fail_count} FAIL, {warn_count} WARN out of {len(results)} checks')

conn.close()
print('\n' + '=' * 70)
print('VERIFICATION COMPLETE')
print('=' * 70)
