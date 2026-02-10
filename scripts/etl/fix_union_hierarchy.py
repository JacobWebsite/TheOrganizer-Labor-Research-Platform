"""
Fix union hierarchy orphans - unions in unions_master without union_hierarchy entries.

Strategy:
  1. Match orphans to parent international by aff_abbr
  2. Classify hierarchy_level (LOCAL, INTERNATIONAL, FEDERATION)
  3. Set count_members = FALSE (conservative - won't inflate BLS total)
  4. Insert into union_hierarchy

Usage:
    py scripts/etl/fix_union_hierarchy.py             # Dry run
    py scripts/etl/fix_union_hierarchy.py --apply      # Apply changes
"""
import os
import sys
import re
import argparse
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from db_config import get_connection


def classify_hierarchy_level(union_name, aff_abbr, is_federation, members):
    """Determine hierarchy level from union name and attributes."""
    name_upper = (union_name or '').upper()

    if is_federation:
        return 'FEDERATION'

    # Check for federation/department keywords
    if re.search(r'\b(FEDERATION|DEPT\s+AFL|TRADES\s+DEPT|TRADES\s+COUNCIL)\b', name_upper):
        return 'FEDERATION'

    # Check for international/national keywords
    if re.search(r'\b(INTERNATIONAL|INTL|NATIONAL|NATL)\b', name_upper):
        # But not "international local" or "international brotherhood" locals
        if not re.search(r'\bLOCAL\b', name_upper):
            return 'INTERNATIONAL'

    # Check for intermediate bodies (district councils, conferences, etc.)
    if re.search(r'\b(DISTRICT\s+COUNCIL|DISTRICT\s+LODGE|CONFERENCE|JOINT\s+(BOARD|COUNCIL))\b', name_upper):
        return 'INTERMEDIATE'

    return 'LOCAL'


def get_count_reason(level, parent_fnum):
    """Generate reason for count_members flag."""
    if level == 'FEDERATION':
        return 'Federation - aggregates other unions'
    elif level == 'INTERNATIONAL':
        return 'International - members counted via locals'
    elif level == 'INTERMEDIATE':
        return 'Intermediate body - members counted via locals'
    elif parent_fnum:
        return f'Local under parent {parent_fnum} - already counted'
    else:
        return 'Unaffiliated local - already counted in existing totals'


def main():
    parser = argparse.ArgumentParser(description="Fix union hierarchy orphans")
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print("=" * 60)
    print("Union Hierarchy Orphan Fix")
    print("=" * 60)

    # Get all orphans
    cur.execute("""
        SELECT um.f_num, um.union_name, um.aff_abbr, um.members,
               um.sector, um.state, um.is_federation
        FROM unions_master um
        LEFT JOIN union_hierarchy uh ON um.f_num = uh.f_num
        WHERE uh.f_num IS NULL
        ORDER BY um.members DESC NULLS LAST
    """)
    orphans = cur.fetchall()
    print(f"\nOrphans found: {len(orphans):,}")

    # Build parent map: aff_abbr -> international f_num
    cur.execute("""
        SELECT aff_abbr, f_num, union_name
        FROM union_hierarchy
        WHERE hierarchy_level = 'INTERNATIONAL'
    """)
    parent_map = {}
    for aff, fnum, name in cur.fetchall():
        parent_map[aff] = (fnum, name)
    print(f"Parent internationals: {len(parent_map):,}")

    # Classify and prepare inserts
    inserts = []
    level_counts = Counter()
    parent_counts = Counter()

    for f_num, union_name, aff_abbr, members, sector, state, is_fed in orphans:
        level = classify_hierarchy_level(union_name, aff_abbr, is_fed, members)
        level_counts[level] += 1

        # Find parent
        parent_fnum = None
        parent_name = None
        if level == 'LOCAL' and aff_abbr in parent_map:
            parent_fnum, parent_name = parent_map[aff_abbr]
            parent_counts['linked'] += 1
        elif level == 'LOCAL':
            parent_counts['no_parent'] += 1
        else:
            parent_counts['is_parent'] += 1

        # count_members = FALSE for all new entries (conservative)
        # Existing BLS totals already account for these unions
        count_members = False
        count_reason = get_count_reason(level, parent_fnum)

        inserts.append({
            'f_num': f_num,
            'union_name': union_name,
            'aff_abbr': aff_abbr,
            'hierarchy_level': level,
            'parent_fnum': parent_fnum,
            'parent_name': parent_name,
            'count_members': count_members,
            'count_reason': count_reason,
            'members_2024': members,
        })

    # Summary
    print(f"\nClassification:")
    for level, cnt in level_counts.most_common():
        print(f"  {level}: {cnt:,}")

    print(f"\nParent linking:")
    for key, cnt in parent_counts.most_common():
        print(f"  {key}: {cnt:,}")

    # Apply
    if args.apply:
        print(f"\n[APPLYING] Inserting {len(inserts):,} hierarchy entries...")
        for entry in inserts:
            cur.execute("""
                INSERT INTO union_hierarchy
                    (f_num, union_name, aff_abbr, hierarchy_level,
                     parent_fnum, parent_name, count_members, count_reason, members_2024)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (f_num) DO NOTHING
            """, (
                entry['f_num'], entry['union_name'], entry['aff_abbr'],
                entry['hierarchy_level'], entry['parent_fnum'], entry['parent_name'],
                entry['count_members'], entry['count_reason'], entry['members_2024'],
            ))
        conn.commit()

        # Verify
        cur.execute('SELECT COUNT(*) FROM union_hierarchy')
        total_h = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM unions_master')
        total_m = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM unions_master um
            LEFT JOIN union_hierarchy uh ON um.f_num = uh.f_num
            WHERE uh.f_num IS NULL
        """)
        remaining = cur.fetchone()[0]

        print(f"  Inserted: {len(inserts):,}")
        print(f"  union_hierarchy: {total_h:,}")
        print(f"  unions_master: {total_m:,}")
        print(f"  Remaining orphans: {remaining:,}")
        print(f"  Coverage: {(total_m - remaining) / total_m:.1%}")
    else:
        print(f"\n[DRY RUN] Would insert {len(inserts):,} entries. Use --apply to write.")

    conn.close()


if __name__ == '__main__':
    main()
