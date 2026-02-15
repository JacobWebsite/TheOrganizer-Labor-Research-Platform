import os
from db_config import get_connection
"""
Fix remaining double-counting: signatory patterns and true duplicate filings.

Two fixes:
1. SIGNATORY PATTERNS: Extend existing pattern matching to all sizes (was >= 1000)
2. SAME-NAME IDENTICAL-SIZE: Exclude duplicate filings where same union + same size
   + similar employer name in same city (true duplicate filings, not different bargaining units)

Usage:
    py scripts/cleanup/fix_double_counting.py                # DRY RUN
    py scripts/cleanup/fix_double_counting.py --apply        # Apply changes
"""
import psycopg2
import sys
import re

DRY_RUN = '--apply' not in sys.argv

conn = get_connection()
cur = conn.cursor()

print("=" * 70)
print("FIX DOUBLE-COUNTING")
print("=" * 70)
print("Mode: %s" % ('DRY RUN' if DRY_RUN else '*** APPLYING ***'))

# Current state
cur.execute("""
    SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END),
           COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END)
    FROM f7_employers_deduped
""")
r = cur.fetchone()
current_workers = r[0]
current_counted = r[1]
print("\nCurrent: %s workers counted across %d employers" % (
    '{:,}'.format(current_workers), current_counted))

# =========================================================================
# FIX 1: SIGNATORY PATTERNS - remove size threshold
# =========================================================================
print("\n" + "=" * 70)
print("FIX 1: SIGNATORY PATTERNS (remove size minimum)")
print("=" * 70)

# Core signatory patterns (same as existing exclusion logic but no size filter)
cur.execute("""
    SELECT employer_id, employer_name, city, state, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (employer_name ILIKE 'AGC %%'
        OR employer_name ILIKE 'AGC of %%'
        OR employer_name ILIKE '%%all signator%%'
        OR employer_name ILIKE '%%signatories to%%'
        OR employer_name ILIKE 'various %%contractor%%'
        OR employer_name ILIKE 'various employers%%'
        OR employer_name ILIKE '%%multiple employer%%'
        OR employer_name ILIKE '%%company list%%'
        OR city ILIKE 'various'
        OR city ILIKE 'multiple'
        OR employer_name ILIKE '%%& various%%'
        OR employer_name ILIKE '%%various contractor%%'
        OR employer_name ILIKE '%%(various)%%'
        OR employer_name ILIKE '%%signatory contractor%%'
        OR employer_name ILIKE '%%signatory %%employer%%'
        OR employer_name ILIKE '%%signatory %%highway%%'
        OR employer_name ILIKE '%%signatory %%build%%'
        OR employer_name ILIKE '%%signatory %%industr%%')
    ORDER BY latest_unit_size DESC
""")
sig_rows = cur.fetchall()
sig_ids = [r[0] for r in sig_rows]
sig_workers = sum(r[4] or 0 for r in sig_rows)

print("\n  Found %d signatory-pattern employers (%s workers):" % (len(sig_rows), '{:,}'.format(sig_workers)))
for r in sig_rows[:25]:
    print("    %-55s | %s, %s | %s" % (
        (r[1] or '')[:55], r[2] or '', r[3] or '', '{:,}'.format(r[4] or 0)))
if len(sig_rows) > 25:
    print("    ... and %d more" % (len(sig_rows) - 25))

# =========================================================================
# FIX 2: SAME-NAME IDENTICAL-SIZE DUPLICATES
# =========================================================================
print("\n" + "=" * 70)
print("FIX 2: SAME-NAME IDENTICAL-SIZE DUPLICATES")
print("=" * 70)

# Find groups where same union + same size + same city + similar name
# This catches true duplicate filings but NOT different bargaining units
cur.execute("""
    SELECT employer_id, employer_name, employer_name_aggressive, city, state,
           latest_unit_size, latest_union_fnum, latest_union_name, street
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND latest_unit_size >= 100
      AND latest_union_fnum IS NOT NULL
    ORDER BY latest_union_fnum, latest_unit_size, city, employer_name_aggressive
""")
all_employers = cur.fetchall()

# Group by union + size + city
from collections import defaultdict
groups = defaultdict(list)
for r in all_employers:
    key = (r[6], r[5], (r[3] or '').lower().strip())  # union_fnum, size, city
    groups[key].append({
        'employer_id': r[0],
        'employer_name': r[1],
        'aggressive_name': r[2],
        'city': r[3],
        'state': r[4],
        'size': r[5],
        'union_fnum': r[6],
        'union_name': r[7],
        'street': r[8],
    })


def names_are_similar(name1, name2):
    """Check if two employer names are similar enough to be duplicates."""
    if not name1 or not name2:
        return False
    # Aggressive names are already lowercased and stripped
    if name1 == name2:
        return True
    # Check if one contains the other
    if name1 in name2 or name2 in name1:
        return True
    # Check if they share a long common prefix (>= 15 chars)
    prefix_len = 0
    for a, b in zip(name1, name2):
        if a == b:
            prefix_len += 1
        else:
            break
    if prefix_len >= 15:
        return True
    return False


dup_ids_to_exclude = []  # (employer_id, reason_detail)

for key, emps in groups.items():
    if len(emps) < 2:
        continue

    # Within this union+size+city group, find name-similar clusters
    # Use simple pairwise matching
    used = set()
    for i in range(len(emps)):
        if i in used:
            continue
        cluster = [i]
        for j in range(i + 1, len(emps)):
            if j in used:
                continue
            if names_are_similar(emps[i]['aggressive_name'], emps[j]['aggressive_name']):
                cluster.append(j)
                used.add(j)

        if len(cluster) >= 2:
            used.update(cluster)
            # Keep the first one (alphabetically first aggressive name), exclude rest
            cluster_emps = [emps[idx] for idx in cluster]
            cluster_emps.sort(key=lambda x: (x['aggressive_name'] or ''))
            keeper = cluster_emps[0]
            for emp in cluster_emps[1:]:
                # Don't re-exclude signatory patterns (already handled above)
                if emp['employer_id'] not in sig_ids:
                    dup_ids_to_exclude.append((
                        emp['employer_id'],
                        'same as %s (%s x%d in %s)' % (
                            keeper['employer_name'][:30],
                            '{:,}'.format(emp['size']),
                            len(cluster),
                            emp['city'] or 'unknown')
                    ))

dup_workers = 0
# Look up sizes
dup_id_set = set(d[0] for d in dup_ids_to_exclude)
for r in all_employers:
    if r[0] in dup_id_set:
        dup_workers += r[5] or 0

print("\n  Found %d same-name duplicate filings (%s workers):" % (
    len(dup_ids_to_exclude), '{:,}'.format(dup_workers)))

# Show examples
shown = 0
for emp_id, reason in dup_ids_to_exclude[:30]:
    # Find the employer
    for r in all_employers:
        if r[0] == emp_id:
            print("    %-45s | %s, %s | %6s | %s" % (
                (r[1] or '')[:45], r[3] or '', r[4] or '',
                '{:,}'.format(r[5] or 0), reason[:40]))
            break
    shown += 1
if len(dup_ids_to_exclude) > 30:
    print("    ... and %d more" % (len(dup_ids_to_exclude) - 30))

# =========================================================================
# COMBINED IMPACT
# =========================================================================
print("\n" + "=" * 70)
print("COMBINED IMPACT")
print("=" * 70)

total_excluded = len(sig_ids) + len(dup_ids_to_exclude)
total_workers_excluded = sig_workers + dup_workers

print("\n  Signatory patterns:    %4d employers, %8s workers" % (len(sig_ids), '{:,}'.format(sig_workers)))
print("  Same-name duplicates:  %4d employers, %8s workers" % (len(dup_ids_to_exclude), '{:,}'.format(dup_workers)))
print("  Total:                 %4d employers, %8s workers" % (total_excluded, '{:,}'.format(total_workers_excluded)))
print()
print("  Before: %s workers (%.1f%% BLS)" % ('{:,}'.format(current_workers), current_workers / 7200000 * 100))
after = current_workers - total_workers_excluded
print("  After:  %s workers (%.1f%% BLS)" % ('{:,}'.format(after), after / 7200000 * 100))

# =========================================================================
# APPLY
# =========================================================================
if DRY_RUN:
    print("\n" + "=" * 70)
    print("DRY RUN COMPLETE - No changes made")
    print("=" * 70)
    print("\nTo apply, run:")
    print("  py scripts/cleanup/fix_double_counting.py --apply")
else:
    print("\n" + "=" * 70)
    print("APPLYING CHANGES")
    print("=" * 70)

    # Fix 1: Signatory patterns
    if sig_ids:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET exclude_from_counts = TRUE,
                exclude_reason = 'SIGNATORY_PATTERN'
            WHERE employer_id = ANY(%s)
              AND exclude_from_counts = FALSE
        """, (sig_ids,))
        print("\n  Signatory patterns excluded: %d" % cur.rowcount)

    # Fix 2: Same-name duplicates
    dup_only_ids = [d[0] for d in dup_ids_to_exclude]
    if dup_only_ids:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET exclude_from_counts = TRUE,
                exclude_reason = 'DUPLICATE_WORKER_COUNT'
            WHERE employer_id = ANY(%s)
              AND exclude_from_counts = FALSE
        """, (dup_only_ids,))
        print("  Same-name duplicates excluded: %d" % cur.rowcount)

    conn.commit()

    # Verify
    cur.execute("""
        SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END),
               COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END)
        FROM f7_employers_deduped
    """)
    r = cur.fetchone()
    print("\n  New counted: %s workers across %d employers" % ('{:,}'.format(r[0]), r[1]))
    print("  BLS coverage: %.1f%%" % (r[0] / 7200000 * 100))

    print("\n" + "=" * 70)
    print("CHANGES APPLIED SUCCESSFULLY")
    print("=" * 70)

conn.close()
