"""
Phase 1.5D: Mark dangling unified_match_log rows as orphaned.

A dangling row is one where target_id does not exist in f7_employers_deduped.

Default behavior:
- only updates status='active' dangling rows
- sets status='orphaned'
- annotates evidence JSONB with orphan metadata
- dry-run unless --commit is passed
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def summarize(cur, include_all_statuses: bool):
    status_filter = "" if include_all_statuses else "AND uml.status = 'active'"
    cur.execute(
        f"""
        SELECT uml.status, uml.source_system, COUNT(*)
        FROM unified_match_log uml
        LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
        WHERE f.employer_id IS NULL
          {status_filter}
        GROUP BY uml.status, uml.source_system
        ORDER BY COUNT(*) DESC
        """
    )
    return cur.fetchall()


def update_orphaned(cur, include_all_statuses: bool):
    status_filter = (
        "AND uml.status NOT IN ('orphaned')"
        if include_all_statuses
        else "AND uml.status = 'active'"
    )
    cur.execute(
        f"""
        WITH dangling AS (
            SELECT uml.id, uml.status
            FROM unified_match_log uml
            LEFT JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
            WHERE f.employer_id IS NULL
              {status_filter}
        )
        UPDATE unified_match_log uml
        SET status = 'orphaned',
            evidence = COALESCE(uml.evidence, '{{}}'::jsonb)
                || jsonb_build_object(
                    'orphan_reason', 'target_id_missing_in_f7_employers_deduped',
                    'orphaned_at', NOW()::text,
                    'prior_status', uml.status
                )
        FROM dangling d
        WHERE uml.id = d.id
        """
    )
    return cur.rowcount


def main():
    parser = argparse.ArgumentParser(description="Mark dangling unified_match_log rows as orphaned")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument(
        "--include-all-statuses",
        action="store_true",
        help="Mark dangling rows from any status (not just active)",
    )
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        print("Dangling rows before update:")
        before = summarize(cur, args.include_all_statuses)
        total_before = sum(r[2] for r in before)
        print(f"  total={total_before:,}")
        for status, source_system, cnt in before:
            print(f"  status={status:10s} source={source_system:8s} count={cnt:,}")

        updated = update_orphaned(cur, args.include_all_statuses)
        print(f"\nRows marked orphaned: {updated:,}")

        print("\nDangling rows after update (inside current transaction):")
        after = summarize(cur, args.include_all_statuses)
        total_after = sum(r[2] for r in after)
        print(f"  total={total_after:,}")
        for status, source_system, cnt in after:
            print(f"  status={status:10s} source={source_system:8s} count={cnt:,}")

        if args.commit:
            conn.commit()
            print("\nCommitted.")
        else:
            conn.rollback()
            print("\nDry-run complete (rolled back). Use --commit to persist.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

