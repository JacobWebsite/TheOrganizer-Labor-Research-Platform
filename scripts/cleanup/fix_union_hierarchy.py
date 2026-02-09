"""
Agent B: Union Hierarchy Fix Script
Fixes orphan locals, inactive unions, and exports ambiguous cases for review.
Default: --dry-run (no changes). Use --apply to commit changes.
"""

import argparse
import csv
import os
import psycopg2
from psycopg2.extras import RealDictCursor

parser = argparse.ArgumentParser(description="Fix union_hierarchy issues")
parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
args = parser.parse_args()

DRY_RUN = not args.apply
BLS_BENCHMARK = 14_300_000
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

mode_label = "DRY RUN" if DRY_RUN else "APPLY"
print("=" * 70)
print(f"UNION HIERARCHY FIXES ({mode_label})")
print("=" * 70)

# ============================================================================
# Capture "before" totals
# ============================================================================
cur.execute("""
    SELECT SUM(COALESCE(members_2024, 0)) as total
    FROM union_hierarchy
    WHERE count_members = TRUE
""")
before_total = cur.fetchone()['total'] or 0
print(f"\nBefore: {before_total:,} counted members")

# ============================================================================
# Fix 1: Flag Inactive Unions
# ============================================================================
print("\n--- Fix 1: Flag Inactive Unions (no filing since 2020) ---")

cur.execute("""
    SELECT h.f_num, h.union_name, h.hierarchy_level, h.members_2024
    FROM union_hierarchy h
    WHERE h.count_members = TRUE
      AND NOT EXISTS (
          SELECT 1 FROM lm_data l WHERE l.f_num = h.f_num AND l.yr_covered >= 2020
      )
    ORDER BY COALESCE(h.members_2024, 0) DESC
""")
inactive_counted = cur.fetchall()
inactive_members = sum(r['members_2024'] or 0 for r in inactive_counted)

print(f"Inactive unions with count_members=TRUE: {len(inactive_counted):,}")
print(f"Members to remove from count: {inactive_members:,}")

if inactive_counted:
    for r in inactive_counted[:10]:
        members = f"{r['members_2024']:,}" if r['members_2024'] else "0"
        print(f"  f_num={r['f_num']}: {r['union_name']} ({r['hierarchy_level']}) -- {members} members")
    if len(inactive_counted) > 10:
        print(f"  ... and {len(inactive_counted) - 10} more")

if not DRY_RUN and inactive_counted:
    fnums = [r['f_num'] for r in inactive_counted]
    cur.execute("""
        UPDATE union_hierarchy
        SET count_members = FALSE,
            count_reason = 'INACTIVE: No filing since 2020'
        WHERE f_num = ANY(%s)
          AND count_members = TRUE
    """, (fnums,))
    print(f"  -> Updated {cur.rowcount} records: count_members=FALSE")
elif DRY_RUN:
    print(f"  -> DRY RUN: Would update {len(inactive_counted)} records")

# ============================================================================
# Fix 2: Link Orphan Locals to Parents
# ============================================================================
print("\n--- Fix 2: Link Orphan Locals to Parents ---")

# Find orphan locals that have a matching INTERNATIONAL by aff_abbr
cur.execute("""
    SELECT orphan.f_num, orphan.union_name, orphan.aff_abbr,
           intl.f_num as intl_fnum, intl.union_name as intl_name
    FROM union_hierarchy orphan
    JOIN LATERAL (
        SELECT f_num, union_name
        FROM union_hierarchy
        WHERE hierarchy_level = 'INTERNATIONAL'
          AND aff_abbr = orphan.aff_abbr
        ORDER BY COALESCE(members_2024, 0) DESC
        LIMIT 1
    ) intl ON TRUE
    WHERE orphan.hierarchy_level = 'LOCAL'
      AND orphan.parent_fnum IS NULL
    ORDER BY orphan.union_name
""")
linkable = cur.fetchall()
print(f"Orphan locals with matching INTERNATIONAL: {len(linkable):,}")

if linkable:
    for r in linkable[:10]:
        print(f"  f_num={r['f_num']}: {r['union_name']} (aff={r['aff_abbr']}) -> parent={r['intl_fnum']} ({r['intl_name']})")
    if len(linkable) > 10:
        print(f"  ... and {len(linkable) - 10} more")

if not DRY_RUN and linkable:
    linked = 0
    for r in linkable:
        cur.execute("""
            UPDATE union_hierarchy
            SET parent_fnum = %s,
                parent_name = %s
            WHERE f_num = %s
              AND parent_fnum IS NULL
        """, (r['intl_fnum'], r['intl_name'], r['f_num']))
        linked += cur.rowcount
    print(f"  -> Linked {linked} orphan locals to their international parent")
elif DRY_RUN:
    print(f"  -> DRY RUN: Would link {len(linkable)} orphan locals")

# Count remaining orphans (no matching international)
cur.execute("""
    SELECT COUNT(*) as cnt
    FROM union_hierarchy
    WHERE hierarchy_level = 'LOCAL'
      AND parent_fnum IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM union_hierarchy intl
          WHERE intl.hierarchy_level = 'INTERNATIONAL'
            AND intl.aff_abbr = union_hierarchy.aff_abbr
      )
""")
remaining = cur.fetchone()['cnt']
print(f"Remaining orphans (no matching international): {remaining:,} (need manual review)")

# ============================================================================
# Fix 3: Export Ambiguous Cases
# ============================================================================
print("\n--- Fix 3: Export Ambiguous Cases for Manual Review ---")

os.makedirs(DATA_DIR, exist_ok=True)
csv_path = os.path.join(DATA_DIR, "hierarchy_review.csv")

review_rows = []

# 3a: Potential mergers
cur.execute("""
    SELECT 'POTENTIAL_MERGER' as issue_type,
           h1.f_num as f_num_1, h1.union_name as name_1,
           h1.members_2024 as members_1, h1.count_members as counted_1,
           h2.f_num as f_num_2, h2.union_name as name_2,
           h2.members_2024 as members_2, h2.count_members as counted_2,
           h1.parent_fnum
    FROM union_hierarchy h1
    JOIN union_hierarchy h2 ON h1.parent_fnum = h2.parent_fnum
        AND h1.f_num < h2.f_num
        AND LEFT(LOWER(h1.union_name), 15) = LEFT(LOWER(h2.union_name), 15)
    WHERE h1.parent_fnum IS NOT NULL
    ORDER BY COALESCE(h1.members_2024, 0) + COALESCE(h2.members_2024, 0) DESC
""")
mergers = cur.fetchall()
for r in mergers:
    review_rows.append({
        'issue_type': 'POTENTIAL_MERGER',
        'f_num': r['f_num_1'],
        'union_name': r['name_1'],
        'members_2024': r['members_1'],
        'count_members': r['counted_1'],
        'related_f_num': r['f_num_2'],
        'related_name': r['name_2'],
        'related_members': r['members_2'],
        'related_counted': r['counted_2'],
        'parent_fnum': r['parent_fnum'],
        'notes': 'Same parent, similar name (first 15 chars match)'
    })

# 3b: Orphans without matching international
cur.execute("""
    SELECT f_num, union_name, aff_abbr, members_2024, count_members
    FROM union_hierarchy
    WHERE hierarchy_level = 'LOCAL'
      AND parent_fnum IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM union_hierarchy intl
          WHERE intl.hierarchy_level = 'INTERNATIONAL'
            AND intl.aff_abbr = union_hierarchy.aff_abbr
      )
    ORDER BY COALESCE(members_2024, 0) DESC
""")
unlinked_orphans = cur.fetchall()
for r in unlinked_orphans:
    review_rows.append({
        'issue_type': 'ORPHAN_NO_INTERNATIONAL',
        'f_num': r['f_num'],
        'union_name': r['union_name'],
        'members_2024': r['members_2024'],
        'count_members': r['count_members'],
        'related_f_num': '',
        'related_name': '',
        'related_members': '',
        'related_counted': '',
        'parent_fnum': '',
        'notes': f"LOCAL with no parent; aff_abbr={r['aff_abbr']} has no INTERNATIONAL"
    })

# 3c: Double-counted internationals
cur.execute("""
    SELECT h.f_num, h.union_name, h.members_2024,
           COUNT(c.f_num) as local_count,
           SUM(CASE WHEN c.count_members THEN 1 ELSE 0 END) as locals_counted,
           SUM(CASE WHEN c.count_members THEN COALESCE(c.members_2024, 0) ELSE 0 END) as locals_members
    FROM union_hierarchy h
    JOIN union_hierarchy c ON c.parent_fnum = h.f_num
    WHERE h.hierarchy_level = 'INTERNATIONAL' AND h.count_members = TRUE
    GROUP BY h.f_num, h.union_name, h.members_2024
    HAVING SUM(CASE WHEN c.count_members THEN 1 ELSE 0 END) > 0
    ORDER BY SUM(CASE WHEN c.count_members THEN COALESCE(c.members_2024, 0) ELSE 0 END) DESC
""")
double_counted = cur.fetchall()
for r in double_counted:
    review_rows.append({
        'issue_type': 'DOUBLE_COUNTING',
        'f_num': r['f_num'],
        'union_name': r['union_name'],
        'members_2024': r['members_2024'],
        'count_members': True,
        'related_f_num': '',
        'related_name': f"{r['locals_counted']} counted locals",
        'related_members': r['locals_members'],
        'related_counted': True,
        'parent_fnum': '',
        'notes': f"INTL counted + {r['locals_counted']} locals also counted ({r['locals_members']:,} members)"
    })

# Write CSV
if review_rows:
    fieldnames = ['issue_type', 'f_num', 'union_name', 'members_2024', 'count_members',
                  'related_f_num', 'related_name', 'related_members', 'related_counted',
                  'parent_fnum', 'notes']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)
    print(f"Exported {len(review_rows)} rows to {csv_path}")
    print(f"  POTENTIAL_MERGER:        {sum(1 for r in review_rows if r['issue_type'] == 'POTENTIAL_MERGER')}")
    print(f"  ORPHAN_NO_INTERNATIONAL: {sum(1 for r in review_rows if r['issue_type'] == 'ORPHAN_NO_INTERNATIONAL')}")
    print(f"  DOUBLE_COUNTING:         {sum(1 for r in review_rows if r['issue_type'] == 'DOUBLE_COUNTING')}")
else:
    print("No ambiguous cases to export.")

# ============================================================================
# Commit or rollback
# ============================================================================
if DRY_RUN:
    conn.rollback()
    print("\n[DRY RUN] All changes rolled back. Use --apply to commit.")
else:
    conn.commit()
    print("\nAll changes committed.")

# ============================================================================
# Verification: Re-check totals
# ============================================================================
print("\n--- Verification ---")

cur.execute("""
    SELECT SUM(COALESCE(members_2024, 0)) as total
    FROM union_hierarchy
    WHERE count_members = TRUE
""")
after_total = cur.fetchone()['total'] or 0

print(f"  Before:        {before_total:>14,}")
print(f"  After:         {after_total:>14,}")
print(f"  Difference:    {after_total - before_total:>+14,}")
print(f"  BLS benchmark: {BLS_BENCHMARK:>14,}")
after_coverage = (after_total / BLS_BENCHMARK * 100) if BLS_BENCHMARK else 0
print(f"  Coverage:      {after_coverage:>13.1f}%")

if DRY_RUN:
    projected = before_total - inactive_members
    projected_coverage = (projected / BLS_BENCHMARK * 100) if BLS_BENCHMARK else 0
    print(f"\n  Projected after applying fixes:")
    print(f"    Counted members: {projected:>14,}")
    print(f"    Coverage:        {projected_coverage:>13.1f}%")

print("\n" + "=" * 70)
print(f"Fix script complete ({mode_label})")
print("=" * 70)

cur.close()
conn.close()
