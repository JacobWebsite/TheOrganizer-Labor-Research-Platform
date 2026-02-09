import os
"""
Agent B: Union Hierarchy Audit - Read-Only
Checks for orphan locals, inactive unions, potential mergers, double-counting,
and membership total integrity in union_hierarchy.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

BLS_BENCHMARK = 14_300_000

print("=" * 70)
print("UNION HIERARCHY AUDIT (Read-Only)")
print("=" * 70)

issues = []

# ============================================================================
# Check 1: Orphan Locals (LOCAL with NULL parent_fnum)
# ============================================================================
print("\n--- Check 1: Orphan Locals ---")
print("LOCAL-level unions with no parent_fnum assigned.\n")

cur.execute("""
    SELECT COUNT(*) as cnt
    FROM union_hierarchy
    WHERE hierarchy_level = 'LOCAL' AND parent_fnum IS NULL
""")
orphan_count = cur.fetchone()['cnt']
print(f"Orphan locals (NULL parent_fnum): {orphan_count:,}")

if orphan_count > 0:
    cur.execute("""
        SELECT f_num, union_name, aff_abbr, members_2024, count_members
        FROM union_hierarchy
        WHERE hierarchy_level = 'LOCAL' AND parent_fnum IS NULL
        ORDER BY COALESCE(members_2024, 0) DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("\nTop 10 orphan locals by membership:")
    for r in rows:
        counted = "[COUNTED]" if r['count_members'] else "[not counted]"
        members = f"{r['members_2024']:,}" if r['members_2024'] else "NULL"
        print(f"  f_num={r['f_num']}: {r['union_name']} (aff={r['aff_abbr']}) -- members={members} {counted}")

    # Check how many orphans have a matching INTERNATIONAL by aff_abbr
    cur.execute("""
        SELECT COUNT(*) as cnt
        FROM union_hierarchy orphan
        WHERE orphan.hierarchy_level = 'LOCAL'
          AND orphan.parent_fnum IS NULL
          AND EXISTS (
              SELECT 1 FROM union_hierarchy intl
              WHERE intl.hierarchy_level = 'INTERNATIONAL'
                AND intl.aff_abbr = orphan.aff_abbr
          )
    """)
    linkable = cur.fetchone()['cnt']
    print(f"\nOrphans with a matching INTERNATIONAL by aff_abbr: {linkable:,} (auto-linkable)")
    print(f"Orphans without a matching INTERNATIONAL: {orphan_count - linkable:,} (need manual review)")

severity = "WARNING" if orphan_count > 100 else "INFO"
issues.append(("Orphan Locals", orphan_count, severity))

# ============================================================================
# Check 2: Inactive Unions (no LM filing since 2020)
# ============================================================================
print("\n--- Check 2: Inactive Unions ---")
print("Unions in hierarchy with no lm_data filing since 2020.\n")

cur.execute("""
    SELECT h.f_num, h.union_name, h.hierarchy_level, h.members_2024, h.count_members
    FROM union_hierarchy h
    WHERE NOT EXISTS (
        SELECT 1 FROM lm_data l WHERE l.f_num = h.f_num AND l.yr_covered >= 2020
    )
""")
inactive_rows = cur.fetchall()
inactive_count = len(inactive_rows)
inactive_counted = [r for r in inactive_rows if r['count_members']]
inactive_counted_members = sum(r['members_2024'] or 0 for r in inactive_counted)

print(f"Inactive unions (no filing since 2020): {inactive_count:,}")
print(f"  Of those, count_members=TRUE: {len(inactive_counted):,}")
print(f"  Sum of members_2024 for counted inactives: {inactive_counted_members:,}")

if inactive_counted:
    print(f"\n  This means {inactive_counted_members:,} members may be inflating totals.")
    print(f"\n  Top 10 inactive counted unions by membership:")
    sorted_inactive = sorted(inactive_counted, key=lambda r: r['members_2024'] or 0, reverse=True)
    for r in sorted_inactive[:10]:
        members = f"{r['members_2024']:,}" if r['members_2024'] else "NULL"
        print(f"    f_num={r['f_num']}: {r['union_name']} ({r['hierarchy_level']}) -- members={members}")

# Breakdown by hierarchy level
print("\n  Inactive by hierarchy level:")
level_counts = {}
for r in inactive_rows:
    lvl = r['hierarchy_level']
    level_counts[lvl] = level_counts.get(lvl, 0) + 1
for lvl in ['FEDERATION', 'INTERNATIONAL', 'INTERMEDIATE', 'LOCAL']:
    if lvl in level_counts:
        print(f"    {lvl}: {level_counts[lvl]:,}")

severity = "CRITICAL" if inactive_counted_members > 100_000 else ("WARNING" if len(inactive_counted) > 0 else "INFO")
issues.append(("Inactive Counted Unions", len(inactive_counted), severity))

# ============================================================================
# Check 3: Potential Mergers
# ============================================================================
print("\n--- Check 3: Potential Mergers ---")
print("Unions under the same parent with similar names (first 15 chars).\n")

cur.execute("""
    SELECT h1.f_num as f_num_1, h1.union_name as name_1,
           h2.f_num as f_num_2, h2.union_name as name_2,
           h1.parent_fnum,
           h1.members_2024 as members_1, h2.members_2024 as members_2,
           h1.count_members as counted_1, h2.count_members as counted_2
    FROM union_hierarchy h1
    JOIN union_hierarchy h2 ON h1.parent_fnum = h2.parent_fnum
        AND h1.f_num < h2.f_num
        AND LEFT(LOWER(h1.union_name), 15) = LEFT(LOWER(h2.union_name), 15)
    WHERE h1.parent_fnum IS NOT NULL
    ORDER BY COALESCE(h1.members_2024, 0) + COALESCE(h2.members_2024, 0) DESC
""")
merger_rows = cur.fetchall()
merger_count = len(merger_rows)
both_counted = [r for r in merger_rows if r['counted_1'] and r['counted_2']]

print(f"Potential merger pairs (same parent + similar name): {merger_count:,}")
print(f"Pairs where BOTH are counted: {len(both_counted):,}")

if merger_rows:
    print(f"\nTop 15 potential merger pairs:")
    for r in merger_rows[:15]:
        c1 = "[COUNTED]" if r['counted_1'] else ""
        c2 = "[COUNTED]" if r['counted_2'] else ""
        m1 = f"{r['members_1']:,}" if r['members_1'] else "0"
        m2 = f"{r['members_2']:,}" if r['members_2'] else "0"
        print(f"  Parent={r['parent_fnum']}:")
        print(f"    {r['f_num_1']}: {r['name_1']} (members={m1}) {c1}")
        print(f"    {r['f_num_2']}: {r['name_2']} (members={m2}) {c2}")

severity = "WARNING" if len(both_counted) > 10 else "INFO"
issues.append(("Potential Merger Pairs", merger_count, severity))
issues.append(("Both-Counted Merger Pairs", len(both_counted), severity))

# ============================================================================
# Check 4: Double-Counting Check
# ============================================================================
print("\n--- Check 4: Double-Counting Check ---")
print("INTERNATIONAL unions counted alongside their also-counted locals.\n")

cur.execute("""
    SELECT h.f_num, h.union_name, h.members_2024,
           COUNT(c.f_num) as local_count,
           SUM(CASE WHEN c.count_members THEN 1 ELSE 0 END) as locals_counted,
           SUM(CASE WHEN c.count_members THEN COALESCE(c.members_2024, 0) ELSE 0 END) as locals_counted_members
    FROM union_hierarchy h
    JOIN union_hierarchy c ON c.parent_fnum = h.f_num
    WHERE h.hierarchy_level = 'INTERNATIONAL' AND h.count_members = TRUE
    GROUP BY h.f_num, h.union_name, h.members_2024
    HAVING SUM(CASE WHEN c.count_members THEN 1 ELSE 0 END) > 0
    ORDER BY SUM(CASE WHEN c.count_members THEN COALESCE(c.members_2024, 0) ELSE 0 END) DESC
""")
double_rows = cur.fetchall()
double_count = len(double_rows)
total_double_members = sum(r['locals_counted_members'] for r in double_rows)

print(f"INTERNATIONAL unions counted where locals are ALSO counted: {double_count:,}")
print(f"Total members in those double-counted locals: {total_double_members:,}")

if double_rows:
    print(f"\nThese internationals are counted AND have counted locals:")
    for r in double_rows[:15]:
        parent_m = f"{r['members_2024']:,}" if r['members_2024'] else "NULL"
        print(f"  f_num={r['f_num']}: {r['union_name']}")
        print(f"    International members: {parent_m} | Locals: {r['local_count']:,} total, {r['locals_counted']:,} counted ({r['locals_counted_members']:,} members)")

severity = "CRITICAL" if double_count > 0 else "INFO"
issues.append(("Double-Counted Internationals", double_count, severity))

# ============================================================================
# Check 5: Membership Totals
# ============================================================================
print("\n--- Check 5: Membership Totals ---")
print("Current counted membership vs BLS benchmark.\n")

# Total counted
cur.execute("""
    SELECT SUM(COALESCE(members_2024, 0)) as total
    FROM union_hierarchy
    WHERE count_members = TRUE
""")
total_counted = cur.fetchone()['total'] or 0
print(f"Total counted members (count_members=TRUE): {total_counted:,}")
print(f"BLS benchmark:                              {BLS_BENCHMARK:,}")
coverage = (total_counted / BLS_BENCHMARK * 100) if BLS_BENCHMARK else 0
print(f"Coverage:                                   {coverage:.1f}%")

# By hierarchy level
print(f"\nCounted members by hierarchy level:")
cur.execute("""
    SELECT hierarchy_level,
           COUNT(*) as union_count,
           SUM(CASE WHEN count_members THEN 1 ELSE 0 END) as counted_unions,
           SUM(CASE WHEN count_members THEN COALESCE(members_2024, 0) ELSE 0 END) as counted_members,
           SUM(COALESCE(members_2024, 0)) as total_members
    FROM union_hierarchy
    GROUP BY hierarchy_level
    ORDER BY
        CASE hierarchy_level
            WHEN 'FEDERATION' THEN 1
            WHEN 'INTERNATIONAL' THEN 2
            WHEN 'INTERMEDIATE' THEN 3
            WHEN 'LOCAL' THEN 4
        END
""")
for r in cur.fetchall():
    print(f"  {r['hierarchy_level']:15s}: {r['counted_unions']:,} counted / {r['union_count']:,} total unions -> {r['counted_members']:,} counted members (of {r['total_members']:,} reported)")

# Top 10 counted unions
print(f"\nTop 10 counted unions by membership:")
cur.execute("""
    SELECT f_num, union_name, hierarchy_level, members_2024
    FROM union_hierarchy
    WHERE count_members = TRUE
    ORDER BY COALESCE(members_2024, 0) DESC
    LIMIT 10
""")
for r in cur.fetchall():
    members = f"{r['members_2024']:,}" if r['members_2024'] else "NULL"
    print(f"  f_num={r['f_num']}: {r['union_name']} ({r['hierarchy_level']}) -- {members}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 70)
print("AUDIT SUMMARY")
print("=" * 70)
print(f"\n{'Issue':<35s} {'Count':>10s} {'Severity':>10s}")
print("-" * 58)
for label, count, sev in issues:
    print(f"  {label:<33s} {count:>10,} {sev:>10s}")

print(f"\nMembership totals:")
print(f"  Current counted:  {total_counted:>14,}")
print(f"  BLS benchmark:    {BLS_BENCHMARK:>14,}")
print(f"  Coverage:         {coverage:>13.1f}%")

if any(s == 'CRITICAL' for _, _, s in issues):
    print("\n[!] CRITICAL issues found - run fix_union_hierarchy.py to resolve")
elif any(s == 'WARNING' for _, _, s in issues):
    print("\n[!] WARNING issues found - review recommended")
else:
    print("\n[OK] No critical issues found")

print("\n" + "=" * 70)
print("Audit complete (read-only, no changes made)")
print("=" * 70)

cur.close()
conn.close()
