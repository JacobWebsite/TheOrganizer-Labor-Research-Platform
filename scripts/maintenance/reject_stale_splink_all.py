"""Reject stale Splink matches with name_similarity < 0.80 across ALL sources.

Applies the D1 decision (0.80 floor) uniformly to SAM, WHD, 990, SEC, and any
other source that still has active Splink matches below the floor.
OSHA was already cleaned by reject_stale_osha.py.

Usage:
    python scripts/maintenance/reject_stale_splink_all.py --dry-run
    python scripts/maintenance/reject_stale_splink_all.py --commit
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.commit and not args.dry_run:
        print("Specify --dry-run or --commit")
        return

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Count by source
    cur.execute("""
        SELECT source_system,
               COUNT(*) AS cnt,
               MIN((evidence->>'name_similarity')::float) AS min_sim,
               AVG((evidence->>'name_similarity')::float) AS avg_sim,
               MAX((evidence->>'name_similarity')::float) AS max_sim
        FROM unified_match_log
        WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
          AND status = 'active'
          AND (evidence->>'name_similarity')::float < 0.80
        GROUP BY source_system
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()

    if not rows:
        print("No active Splink matches below 0.80 floor found.")
        conn.close()
        return

    total = 0
    print("Active Splink matches with name_similarity < 0.80:")
    print(f"{'Source':<12} {'Count':>8} {'Min Sim':>8} {'Avg Sim':>8} {'Max Sim':>8}")
    print("-" * 52)
    for r in rows:
        print(f"{r['source_system']:<12} {r['cnt']:>8} {r['min_sim']:>8.3f} {r['avg_sim']:>8.3f} {r['max_sim']:>8.3f}")
        total += r["cnt"]
    print(f"{'TOTAL':<12} {total:>8}")

    if args.dry_run:
        # Show samples
        print("\nSample matches per source (5 each):")
        for r in rows:
            src = r["source_system"]
            cur.execute("""
                SELECT evidence->>'source_name' AS src_name,
                       evidence->>'target_name' AS tgt_name,
                       (evidence->>'name_similarity')::float AS sim,
                       evidence->>'state' AS state
                FROM unified_match_log
                WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
                  AND status = 'active'
                  AND source_system = %s
                  AND (evidence->>'name_similarity')::float < 0.80
                ORDER BY (evidence->>'name_similarity')::float DESC
                LIMIT 5
            """, (src,))
            samples = cur.fetchall()
            print(f"\n  {src}:")
            for s in samples:
                sn = (s["src_name"] or "?")[:35]
                tn = (s["tgt_name"] or "?")[:35]
                print(f"    {sn:35s} <-> {tn:35s} sim={s['sim']:.3f} {s['state']}")
        print(f"\n[DRY-RUN] Would supersede {total} matches. Use --commit to apply.")
    else:
        cur.execute("""
            UPDATE unified_match_log
            SET status = 'superseded'
            WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
              AND status = 'active'
              AND (evidence->>'name_similarity')::float < 0.80
        """)
        updated = cur.rowcount
        conn.commit()
        print(f"\nSuperseded {updated} matches across all sources.")

        # Verify
        cur.execute("""
            SELECT source_system, COUNT(*) AS cnt
            FROM unified_match_log
            WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
              AND status = 'active'
            GROUP BY source_system
            ORDER BY cnt DESC
        """)
        print("\nRemaining active Splink matches (all >= 0.80):")
        for r2 in cur.fetchall():
            print(f"  {r2['source_system']:<12} {r2['cnt']:>8}")

    conn.close()


if __name__ == "__main__":
    main()
