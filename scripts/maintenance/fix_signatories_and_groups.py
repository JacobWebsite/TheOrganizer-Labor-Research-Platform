"""
Fix A: Flag signatory entries as excluded.
Fix C: Manual merge of split canonical groups.

Run: py scripts/maintenance/fix_signatories_and_groups.py [--dry-run]
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import psycopg2.extras
from db_config import get_connection


def fix_signatories(conn, dry_run=False):
    """Flag all signatory pattern entries as excluded."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find all signatory entries
    cur.execute("""
        SELECT employer_id, employer_name, state, latest_unit_size
        FROM f7_employers_deduped
        WHERE (employer_name ILIKE '%%signator%%'
               OR employer_name ILIKE '%%all signatories%%')
          AND exclude_from_counts = FALSE
        ORDER BY latest_unit_size DESC NULLS LAST
    """)
    rows = cur.fetchall()
    print(f"[fix-A] Found {len(rows)} unflagged signatory entries")

    if dry_run:
        for r in rows[:10]:
            print(f"  Would exclude: {r['employer_name'][:60]} (st={r['state'] or '??'}, size={r['latest_unit_size'] or 0:,})")
        if len(rows) > 10:
            print(f"  ... and {len(rows) - 10} more")
        return len(rows)

    ids = [r['employer_id'] for r in rows]
    if ids:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET exclude_from_counts = TRUE,
                exclude_reason = 'SIGNATORY_PATTERN'
            WHERE employer_id = ANY(%s)
        """, [ids])
        conn.commit()
        print(f"[fix-A] Flagged {len(ids)} signatory entries as excluded")

    return len(rows)


def fix_split_groups(conn, dry_run=False):
    """Manually merge obvious split canonical groups.

    Finds groups whose canonical_name differs only by trailing punctuation
    and merges them into one group.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find pairs of groups with same name_aggressive but different group_ids
    # (i.e., groups that SHOULD have been merged but weren't)
    cur.execute("""
        WITH group_names AS (
            SELECT g.group_id, g.canonical_name, g.state, g.member_count,
                   g.consolidated_workers,
                   REGEXP_REPLACE(
                       REGEXP_REPLACE(UPPER(g.canonical_name), '[^A-Z0-9 ]', '', 'g'),
                       '\\s+', ' ', 'g'
                   ) AS norm_name
            FROM employer_canonical_groups g
        )
        SELECT a.group_id AS keep_id, a.canonical_name AS keep_name,
               a.state AS keep_state, a.member_count AS keep_members,
               b.group_id AS merge_id, b.canonical_name AS merge_name,
               b.state AS merge_state, b.member_count AS merge_members
        FROM group_names a
        JOIN group_names b ON a.norm_name = b.norm_name
            AND COALESCE(a.state, '') = COALESCE(b.state, '')
            AND a.group_id < b.group_id
            AND a.member_count >= b.member_count
        ORDER BY a.member_count + b.member_count DESC
    """)
    pairs = cur.fetchall()
    print(f"[fix-C] Found {len(pairs)} split group pairs to merge")

    if dry_run:
        for p in pairs[:15]:
            print(f"  Merge: '{p['merge_name']}' ({p['merge_members']} members) "
                  f"-> '{p['keep_name']}' ({p['keep_members']} members) "
                  f"[state={p['keep_state'] or 'multi'}]")
        if len(pairs) > 15:
            print(f"  ... and {len(pairs) - 15} more")
        return len(pairs)

    merged = 0
    for p in pairs:
        keep_id = p['keep_id']
        merge_id = p['merge_id']

        # Move members from merge_id to keep_id
        cur.execute("""
            UPDATE f7_employers_deduped
            SET canonical_group_id = %s
            WHERE canonical_group_id = %s
        """, [keep_id, merge_id])
        moved = cur.rowcount

        # Update member_count and consolidated_workers on keep group
        cur.execute("""
            UPDATE employer_canonical_groups
            SET member_count = (
                    SELECT COUNT(*) FROM f7_employers_deduped
                    WHERE canonical_group_id = %s
                ),
                consolidated_workers = COALESCE((
                    SELECT SUM(latest_unit_size) FROM f7_employers_deduped
                    WHERE canonical_group_id = %s AND is_canonical_rep = TRUE
                ), 0)
            WHERE group_id = %s
        """, [keep_id, keep_id, keep_id])

        # Delete the merged group
        cur.execute("DELETE FROM employer_canonical_groups WHERE group_id = %s", [merge_id])
        merged += 1

        if merged <= 10:
            print(f"  Merged group {merge_id} ({moved} members) into {keep_id}")

    conn.commit()
    print(f"[fix-C] Merged {merged} groups")
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = get_connection()
    try:
        sig_count = fix_signatories(conn, dry_run=args.dry_run)
        merge_count = fix_split_groups(conn, dry_run=args.dry_run)

        print(f"\n--- Summary ---")
        print(f"Signatory entries flagged: {sig_count}")
        print(f"Split groups merged:       {merge_count}")

        if not args.dry_run:
            # Verify
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT COUNT(*) FROM f7_employers_deduped
                WHERE exclude_reason = 'SIGNATORY_PATTERN'
            """)
            print(f"Total SIGNATORY_PATTERN excluded: {cur.fetchone()['count']}")

            cur.execute("SELECT COUNT(*) FROM employer_canonical_groups")
            print(f"Total canonical groups: {cur.fetchone()['count']}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
