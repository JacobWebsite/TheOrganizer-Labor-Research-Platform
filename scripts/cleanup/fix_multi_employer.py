import os
from db_config import get_connection
"""
Fix multi-employer group assignments in f7_employers_deduped.

Fixes:
1. Groups with 0 primaries -> assign largest employer as primary
2. Groups with >1 primaries -> keep largest, demote others
3. Excluded records without reason -> set 'LEGACY_EXCLUSION'

Usage:
  py scripts/cleanup/fix_multi_employer.py           # dry-run (default)
  py scripts/cleanup/fix_multi_employer.py --apply    # apply changes
"""
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

DRY_RUN = '--apply' not in sys.argv
BLS_PRIVATE_BENCHMARK = 7_200_000

conn = get_connection()

mode_label = 'DRY RUN' if DRY_RUN else 'APPLYING CHANGES'
print('=' * 70)
print(f'MULTI-EMPLOYER GROUP FIX ({mode_label})')
print('=' * 70)

if not DRY_RUN:
    print('  ** Changes WILL be committed to the database **')
else:
    print('  No changes will be made. Use --apply to execute.')

total_fixed = 0

# ============================================================================
# Fix 1: Groups with 0 primaries
# ============================================================================
print('\n--- Fix 1: Groups with 0 primaries ---')

cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute('''
    SELECT multi_employer_group_id,
           COUNT(*) as total_in_group
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
    GROUP BY multi_employer_group_id
    HAVING SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) = 0
''')
zero_primary_groups = cur.fetchall()

if not zero_primary_groups:
    print('  No groups with 0 primaries. Nothing to fix.')
else:
    print(f'  Found {len(zero_primary_groups)} group(s) with 0 primaries.')
    fix1_count = 0
    for g in zero_primary_groups:
        gid = g['multi_employer_group_id']
        # Find the best candidate: largest unit_size, break ties by employer_id
        cur.execute('''
            SELECT employer_id, employer_name, latest_unit_size
            FROM f7_employers_deduped
            WHERE multi_employer_group_id = %s
            ORDER BY latest_unit_size DESC NULLS LAST, employer_id
            LIMIT 1
        ''', (gid,))
        best = cur.fetchone()
        if best:
            print(f'    group {gid}: set primary -> {best["employer_name"][:45]} (workers={best["latest_unit_size"]})')
            if not DRY_RUN:
                cur.execute('''
                    UPDATE f7_employers_deduped
                    SET is_primary_in_group = TRUE
                    WHERE employer_id = %s
                ''', (best['employer_id'],))
            fix1_count += 1
    print(f'  Would fix: {fix1_count} group(s)')
    total_fixed += fix1_count

# ============================================================================
# Fix 2: Groups with >1 primaries
# ============================================================================
print('\n--- Fix 2: Groups with >1 primaries ---')

cur.execute('''
    SELECT multi_employer_group_id,
           SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) as primary_count,
           COUNT(*) as total_in_group
    FROM f7_employers_deduped
    WHERE multi_employer_group_id IS NOT NULL
    GROUP BY multi_employer_group_id
    HAVING SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) > 1
''')
multi_primary_groups = cur.fetchall()

if not multi_primary_groups:
    print('  No groups with >1 primaries. Nothing to fix.')
else:
    print(f'  Found {len(multi_primary_groups)} group(s) with >1 primaries.')
    fix2_count = 0
    for g in multi_primary_groups:
        gid = g['multi_employer_group_id']
        # Find all primaries, keep the one with largest unit_size
        cur.execute('''
            SELECT employer_id, employer_name, latest_unit_size
            FROM f7_employers_deduped
            WHERE multi_employer_group_id = %s AND is_primary_in_group = TRUE
            ORDER BY latest_unit_size DESC NULLS LAST, employer_id
        ''', (gid,))
        primaries = cur.fetchall()
        # Keep first (largest), demote the rest
        keep = primaries[0]
        demote = primaries[1:]
        demote_ids = [r['employer_id'] for r in demote]
        print(f'    group {gid}: keep {keep["employer_name"][:35]} (workers={keep["latest_unit_size"]}), demote {len(demote)} others')
        if not DRY_RUN and demote_ids:
            cur.execute('''
                UPDATE f7_employers_deduped
                SET is_primary_in_group = FALSE
                WHERE employer_id = ANY(%s)
            ''', (demote_ids,))
        fix2_count += len(demote)
    print(f'  Would demote: {fix2_count} record(s)')
    total_fixed += fix2_count

# ============================================================================
# Fix 3: Excluded records without reason
# ============================================================================
print('\n--- Fix 3: Excluded records without reason ---')

cur.execute('''
    SELECT COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
      AND (exclude_reason IS NULL OR exclude_reason = '')
''')
missing_reason_count = cur.fetchone()['cnt']

if missing_reason_count == 0:
    print('  All excluded records have reasons. Nothing to fix.')
else:
    print(f'  Found {missing_reason_count} excluded record(s) without a reason.')
    # Show some examples
    cur.execute('''
        SELECT employer_id, employer_name, latest_union_name, latest_unit_size
        FROM f7_employers_deduped
        WHERE exclude_from_counts = TRUE
          AND (exclude_reason IS NULL OR exclude_reason = '')
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 5
    ''')
    for r in cur.fetchall():
        print(f'    {r["employer_name"][:45]:<45} | workers={r["latest_unit_size"]}')

    if not DRY_RUN:
        cur.execute('''
            UPDATE f7_employers_deduped
            SET exclude_reason = 'LEGACY_EXCLUSION'
            WHERE exclude_from_counts = TRUE
              AND (exclude_reason IS NULL OR exclude_reason = '')
        ''')
        print(f'  Set exclude_reason = LEGACY_EXCLUSION for {cur.rowcount} record(s)')
    else:
        print(f'  Would set exclude_reason = LEGACY_EXCLUSION for {missing_reason_count} record(s)')
    total_fixed += missing_reason_count

# ============================================================================
# Commit or rollback
# ============================================================================
if DRY_RUN:
    conn.rollback()
    print(f'\n  DRY RUN complete. {total_fixed} issue(s) identified.')
    print('  Re-run with --apply to commit changes.')
else:
    conn.commit()
    print(f'\n  COMMITTED {total_fixed} fix(es) to database.')

# ============================================================================
# Post-fix verification (re-run all 5 checks)
# ============================================================================
if not DRY_RUN:
    print('\n' + '=' * 70)
    print('POST-FIX VERIFICATION')
    print('=' * 70)

    post_results = []

    # Check 1: group primaries
    cur.execute('''
        SELECT multi_employer_group_id,
               SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) as primary_count
        FROM f7_employers_deduped
        WHERE multi_employer_group_id IS NOT NULL
        GROUP BY multi_employer_group_id
        HAVING SUM(CASE WHEN is_primary_in_group THEN 1 ELSE 0 END) != 1
    ''')
    bad = cur.fetchall()
    if not bad:
        post_results.append(('1. Group primaries', 'PASS', 'All groups have exactly 1 primary'))
    else:
        zero = sum(1 for r in bad if r['primary_count'] == 0)
        multi = sum(1 for r in bad if r['primary_count'] > 1)
        post_results.append(('1. Group primaries', 'FAIL', f'{zero} zero, {multi} multi'))

    # Check 2: exclusion reasons
    cur.execute('''
        SELECT COUNT(*) as cnt FROM f7_employers_deduped
        WHERE exclude_from_counts = TRUE AND (exclude_reason IS NULL OR exclude_reason = '')
    ''')
    cnt = cur.fetchone()['cnt']
    if cnt == 0:
        post_results.append(('2. Exclusion reasons', 'PASS', 'All excluded records have reasons'))
    else:
        post_results.append(('2. Exclusion reasons', 'FAIL', f'{cnt} missing reason'))

    # Check 3: primaries not excluded (only flag mixed groups, not fully-excluded groups)
    cur.execute('''
        WITH group_info AS (
            SELECT multi_employer_group_id,
                   SUM(CASE WHEN exclude_from_counts = FALSE THEN 1 ELSE 0 END) as counted_members
            FROM f7_employers_deduped
            WHERE multi_employer_group_id IS NOT NULL
            GROUP BY multi_employer_group_id
        )
        SELECT COUNT(*) as cnt
        FROM f7_employers_deduped f
        JOIN group_info g ON f.multi_employer_group_id = g.multi_employer_group_id
        WHERE f.is_primary_in_group = TRUE
          AND f.exclude_from_counts = TRUE
          AND f.multi_employer_group_id IS NOT NULL
          AND g.counted_members > 0
    ''')
    cnt = cur.fetchone()['cnt']
    if cnt == 0:
        post_results.append(('3. Primary not excluded', 'PASS', 'No problematic group primaries'))
    else:
        post_results.append(('3. Primary not excluded', 'FAIL', f'{cnt} group primaries excluded in mixed groups'))

    # Check 4: BLS coverage
    cur.execute('''
        SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted
        FROM f7_employers_deduped
    ''')
    counted = cur.fetchone()['counted'] or 0
    pct = counted / BLS_PRIVATE_BENCHMARK * 100
    if 90 <= pct <= 110:
        post_results.append(('4. BLS coverage', 'PASS', f'{pct:.1f}%'))
    else:
        post_results.append(('4. BLS coverage', 'FAIL', f'{pct:.1f}%'))

    # Check 5: large union double-counting
    cur.execute('''
        SELECT COUNT(*) as cnt FROM (
            SELECT latest_union_fnum
            FROM f7_employers_deduped
            WHERE exclude_from_counts = FALSE AND latest_union_fnum IS NOT NULL
            GROUP BY latest_union_fnum, latest_union_name
            HAVING SUM(latest_unit_size) > 500000
        ) sub
    ''')
    cnt = cur.fetchone()['cnt']
    if cnt == 0:
        post_results.append(('5. Union double-count', 'PASS', 'No union > 500K'))
    else:
        post_results.append(('5. Union double-count', 'WARN', f'{cnt} union(s) > 500K'))

    print(f'  {"Check":<30} | {"Status":<6} | Details')
    print(f'  {"-"*30}-+-{"-"*6}-+-{"-"*40}')
    for name, status, details in post_results:
        print(f'  {name:<30} | {status:<6} | {details}')

    pass_count = sum(1 for _, s, _ in post_results if s == 'PASS')
    fail_count = sum(1 for _, s, _ in post_results if s == 'FAIL')
    warn_count = sum(1 for _, s, _ in post_results if s == 'WARN')
    print(f'\n  {pass_count} PASS, {fail_count} FAIL, {warn_count} WARN')

conn.close()
print('\n' + '=' * 70)
print('COMPLETE')
print('=' * 70)
