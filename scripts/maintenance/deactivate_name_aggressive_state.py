"""Supersede active NAME_AGGRESSIVE_STATE matches in unified_match_log.

NAME_AGGRESSIVE_STATE has a ~47% false-positive rate at 0.75 confidence.
This script deactivates all active matches using that method.

Usage:
    py scripts/maintenance/deactivate_name_aggressive_state.py            # dry-run
    py scripts/maintenance/deactivate_name_aggressive_state.py --commit   # persist changes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

MATCH_METHOD = "NAME_AGGRESSIVE_STATE"

# Adapter tables that the scorecard reads from directly.
# These must be cleaned in sync with unified_match_log.
ADAPTER_TABLES = {
    "osha_f7_matches": "match_method",
    "whd_f7_matches": "match_method",
    "sam_f7_matches": "match_method",
}


def main():
    parser = argparse.ArgumentParser(
        description="Supersede active NAME_AGGRESSIVE_STATE matches (47%% FP rate)"
    )
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Preview what will be affected
        cur.execute(
            """
            SELECT source_system,
                   COUNT(*) as cnt,
                   ROUND(AVG(confidence_score)::numeric, 3) as avg_conf,
                   ROUND(MIN(confidence_score)::numeric, 3) as min_conf,
                   ROUND(MAX(confidence_score)::numeric, 3) as max_conf
            FROM unified_match_log
            WHERE status = 'active'
              AND match_method = %s
            GROUP BY source_system
            ORDER BY cnt DESC
            """,
            (MATCH_METHOD,),
        )
        rows = cur.fetchall()

        total = 0
        print(f"Active {MATCH_METHOD} matches to supersede:")
        print(f"{'Source':12s} {'Count':>7s} {'Avg':>7s} {'Min':>7s} {'Max':>7s}")
        print("-" * 45)
        for source, cnt, avg_c, min_c, max_c in rows:
            print(f"{source:12s} {cnt:>7d} {avg_c:>7} {min_c:>7} {max_c:>7}")
            total += cnt
        print(f"{'TOTAL':12s} {total:>7d}")
        print()

        if total == 0:
            print("Nothing to do.")
            return

        # Count distinct employers affected
        cur.execute(
            """
            SELECT COUNT(DISTINCT target_id)
            FROM unified_match_log
            WHERE status = 'active'
              AND match_method = %s
            """,
            (MATCH_METHOD,),
        )
        print(f"Distinct F7 employers affected: {cur.fetchone()[0]}")

        # Perform the update
        cur.execute(
            """
            UPDATE unified_match_log
            SET status = 'superseded',
                evidence = COALESCE(evidence, '{}'::jsonb)
                    || jsonb_build_object(
                        'superseded_reason', 'NAME_AGGRESSIVE_STATE deactivated - 47%% FP rate at 0.75 confidence',
                        'superseded_at', NOW()::text
                    )
            WHERE status = 'active'
              AND match_method = %s
            """,
            (MATCH_METHOD,),
        )
        affected = cur.rowcount
        print(f"Rows updated: {affected:,}")

        # Show remaining active match counts for context
        cur.execute(
            """
            SELECT COUNT(*) as total_active
            FROM unified_match_log
            WHERE status = 'active'
            """
        )
        remaining = cur.fetchone()[0]
        print(f"Remaining total active matches: {remaining:,}")

        # Clean adapter tables (scorecard reads these, not unified_match_log)
        print("\n--- Adapter table cleanup ---")
        for table, method_col in ADAPTER_TABLES.items():
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE {method_col} = %s
                """,
                (MATCH_METHOD,),
            )
            cnt = cur.fetchone()[0]
            if cnt > 0:
                cur.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE {method_col} = %s
                    """,
                    (MATCH_METHOD,),
                )
                print(f"  {table}: deleted {cur.rowcount:,} {MATCH_METHOD} rows")
            else:
                print(f"  {table}: no {MATCH_METHOD} rows found")

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
