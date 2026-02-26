"""Supersede active fuzzy matches below a similarity threshold.

Targets match_methods: FUZZY_SPLINK_ADAPTIVE, FUZZY_TRIGRAM, SPLINK_PROB.
Uses the confidence_score column directly (not evidence JSON).

Usage:
    py scripts/maintenance/reject_low_fuzzy.py                 # dry-run at 0.85
    py scripts/maintenance/reject_low_fuzzy.py --floor 0.80    # dry-run at 0.80
    py scripts/maintenance/reject_low_fuzzy.py --commit        # persist changes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

FUZZY_METHODS = ("FUZZY_SPLINK_ADAPTIVE", "FUZZY_TRIGRAM", "SPLINK_PROB")

# Adapter tables that the scorecard reads from directly.
# These must be cleaned in sync with unified_match_log.
ADAPTER_TABLES = {
    "osha_f7_matches": "match_confidence",
    "whd_f7_matches": "match_confidence",
    "sam_f7_matches": "match_confidence",
}


def main():
    parser = argparse.ArgumentParser(
        description="Supersede low-confidence fuzzy matches"
    )
    parser.add_argument(
        "--floor", type=float, default=0.85,
        help="Minimum allowed confidence_score (default: 0.85)",
    )
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Preview what will be affected
        cur.execute(
            """
            SELECT match_method, source_system,
                   COUNT(*) as cnt,
                   ROUND(AVG(confidence_score)::numeric, 3) as avg_sim,
                   ROUND(MIN(confidence_score)::numeric, 3) as min_sim,
                   ROUND(MAX(confidence_score)::numeric, 3) as max_sim
            FROM unified_match_log
            WHERE status = 'active'
              AND match_method = ANY(%s)
              AND confidence_score < %s
            GROUP BY match_method, source_system
            ORDER BY cnt DESC
            """,
            (list(FUZZY_METHODS), args.floor),
        )
        rows = cur.fetchall()

        total = 0
        print(f"Active fuzzy matches below {args.floor} to supersede:")
        print(f"{'Method':30s} {'Source':12s} {'Count':>7s} {'Avg':>7s} {'Min':>7s} {'Max':>7s}")
        print("-" * 75)
        for method, source, cnt, avg_s, min_s, max_s in rows:
            print(f"{method:30s} {source:12s} {cnt:>7d} {avg_s:>7} {min_s:>7} {max_s:>7}")
            total += cnt
        print(f"{'TOTAL':30s} {'':12s} {total:>7d}")
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
              AND match_method = ANY(%s)
              AND confidence_score < %s
            """,
            (list(FUZZY_METHODS), args.floor),
        )
        print(f"Distinct F7 employers affected: {cur.fetchone()[0]}")

        # Perform the update
        reason = f"below_fuzzy_floor_{args.floor:.2f}"
        cur.execute(
            """
            UPDATE unified_match_log
            SET status = 'superseded',
                evidence = COALESCE(evidence, '{}'::jsonb)
                    || jsonb_build_object(
                        'superseded_reason', %s,
                        'superseded_at', NOW()::text
                    )
            WHERE status = 'active'
              AND match_method = ANY(%s)
              AND confidence_score < %s
            """,
            (reason, list(FUZZY_METHODS), args.floor),
        )
        affected = cur.rowcount
        print(f"Rows updated: {affected:,}")

        # Show remaining active fuzzy match counts
        cur.execute(
            """
            SELECT COUNT(*) as remaining,
                   ROUND(MIN(confidence_score)::numeric, 3) as new_min,
                   ROUND(AVG(confidence_score)::numeric, 3) as new_avg
            FROM unified_match_log
            WHERE status = 'active'
              AND match_method = ANY(%s)
            """,
            (list(FUZZY_METHODS),),
        )
        rem, new_min, new_avg = cur.fetchone()
        print(f"Remaining active fuzzy matches: {rem:,} (min={new_min}, avg={new_avg})")

        # Clean adapter tables (scorecard reads these, not unified_match_log)
        print("\n--- Adapter table cleanup ---")
        for table, conf_col in ADAPTER_TABLES.items():
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE match_method = ANY(%s)
                  AND {conf_col} < %s
                """,
                (list(FUZZY_METHODS), args.floor),
            )
            cnt = cur.fetchone()[0]
            if cnt > 0:
                cur.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE match_method = ANY(%s)
                      AND {conf_col} < %s
                    """,
                    (list(FUZZY_METHODS), args.floor),
                )
                print(f"  {table}: deleted {cur.rowcount:,} fuzzy rows below {args.floor}")
            else:
                print(f"  {table}: no fuzzy rows below {args.floor}")

        if args.commit:
            conn.commit()
            print("Committed.")
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
