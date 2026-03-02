"""
Score change report -- snapshot before rebuild, compare after.

Usage:
    py scripts/scoring/score_change_report.py snapshot  # before rebuild
    py scripts/scoring/score_change_report.py compare   # after rebuild
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


SNAPSHOT_TABLE = "_score_snapshot"


def do_snapshot(conn):
    """Save current scores to a temporary table for later comparison."""
    cur = conn.cursor()

    # Drop old snapshot if it exists
    cur.execute(f"DROP TABLE IF EXISTS {SNAPSHOT_TABLE}")
    conn.commit()

    # Create snapshot from current MV
    cur.execute(f"""
        CREATE TABLE {SNAPSHOT_TABLE} AS
        SELECT
            employer_id,
            employer_name,
            weighted_score,
            score_tier,
            factors_available,
            score_osha,
            score_nlrb,
            score_whd,
            score_contracts,
            score_union_proximity,
            score_financial,
            score_industry_growth,
            score_size,
            score_similarity
        FROM mv_unified_scorecard
    """)
    conn.commit()

    cur.execute(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE}")
    cnt = cur.fetchone()[0]
    print(f"Snapshot saved: {cnt:,} rows in {SNAPSHOT_TABLE}")
    cur.close()


def do_compare(conn):
    """Compare snapshot to current MV and report changes."""
    cur = conn.cursor()

    # Check snapshot exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s AND table_schema = 'public'
        )
    """, (SNAPSHOT_TABLE,))
    if not cur.fetchone()[0]:
        print(f"ERROR: No snapshot table '{SNAPSHOT_TABLE}' found.")
        print("Run 'snapshot' subcommand first.")
        cur.close()
        return 1

    # --- Tier migration counts ---
    print("\n" + "=" * 60)
    print("  TIER MIGRATION")
    print("=" * 60)

    cur.execute(f"""
        SELECT
            s.score_tier AS old_tier,
            m.score_tier AS new_tier,
            COUNT(*) AS cnt
        FROM {SNAPSHOT_TABLE} s
        JOIN mv_unified_scorecard m ON m.employer_id = s.employer_id
        WHERE s.score_tier != m.score_tier
        GROUP BY s.score_tier, m.score_tier
        ORDER BY cnt DESC
    """)
    migrations = cur.fetchall()

    if not migrations:
        print("  No tier changes detected.")
    else:
        total_changed = sum(r[2] for r in migrations)
        print(f"  Total employers with tier change: {total_changed:,}")
        print()
        print(f"  {'Old Tier':<15s} {'New Tier':<15s} {'Count':>8s}")
        print(f"  {'-' * 15} {'-' * 15} {'-' * 8}")
        for old_tier, new_tier, cnt in migrations:
            print(f"  {old_tier:<15s} {new_tier:<15s} {cnt:>8,}")

    # Summary: upgrades vs downgrades
    tier_order = {'Priority': 1, 'Strong': 2, 'Promising': 3, 'Moderate': 4, 'Low': 5}
    upgrades = sum(r[2] for r in migrations if tier_order.get(r[1], 9) < tier_order.get(r[0], 9))
    downgrades = sum(r[2] for r in migrations if tier_order.get(r[1], 9) > tier_order.get(r[0], 9))
    print(f"\n  Upgrades:   {upgrades:>8,}")
    print(f"  Downgrades: {downgrades:>8,}")

    # --- Top 20 biggest score changes ---
    print("\n" + "=" * 60)
    print("  TOP 20 BIGGEST SCORE CHANGES")
    print("=" * 60)

    cur.execute(f"""
        SELECT
            m.employer_id,
            COALESCE(m.employer_name, '(unknown)') AS name,
            s.weighted_score AS old_score,
            m.weighted_score AS new_score,
            ROUND((m.weighted_score - s.weighted_score)::numeric, 2) AS delta
        FROM {SNAPSHOT_TABLE} s
        JOIN mv_unified_scorecard m ON m.employer_id = s.employer_id
        WHERE s.weighted_score IS NOT NULL AND m.weighted_score IS NOT NULL
        ORDER BY ABS(m.weighted_score - s.weighted_score) DESC
        LIMIT 20
    """)
    rows = cur.fetchall()

    if not rows:
        print("  No score changes detected.")
    else:
        print(f"\n  {'Employer ID':<20s} {'Name':<30s} {'Old':>6s} {'New':>6s} {'Delta':>7s}")
        print(f"  {'-' * 20} {'-' * 30} {'-' * 6} {'-' * 6} {'-' * 7}")
        for eid, name, old_s, new_s, delta in rows:
            name_trunc = (name[:27] + "...") if len(name) > 30 else name
            sign = "+" if delta and delta > 0 else ""
            print(f"  {eid:<20s} {name_trunc:<30s} {old_s:>6.2f} {new_s:>6.2f} {sign}{delta:>6.2f}")

    # --- Factor coverage changes ---
    print("\n" + "=" * 60)
    print("  FACTOR COVERAGE CHANGES")
    print("=" * 60)

    factors = [
        'score_osha', 'score_nlrb', 'score_whd', 'score_contracts',
        'score_union_proximity', 'score_financial', 'score_industry_growth',
        'score_size', 'score_similarity',
    ]

    # Get total counts
    cur.execute(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE}")
    old_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
    new_total = cur.fetchone()[0]

    print(f"\n  {'Factor':<25s} {'Old %':>8s} {'New %':>8s} {'Change':>8s}")
    print(f"  {'-' * 25} {'-' * 8} {'-' * 8} {'-' * 8}")

    for factor in factors:
        cur.execute(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE} WHERE {factor} IS NOT NULL")
        old_cnt = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM mv_unified_scorecard WHERE {factor} IS NOT NULL")
        new_cnt = cur.fetchone()[0]

        old_pct = (100.0 * old_cnt / old_total) if old_total else 0
        new_pct = (100.0 * new_cnt / new_total) if new_total else 0
        change = new_pct - old_pct
        sign = "+" if change > 0 else ""

        print(f"  {factor:<25s} {old_pct:>7.1f}% {new_pct:>7.1f}% {sign}{change:>6.1f}pp")

    # --- Score distribution summary ---
    print("\n" + "=" * 60)
    print("  SCORE DISTRIBUTION SHIFT")
    print("=" * 60)

    for label, table in [("Before", SNAPSHOT_TABLE), ("After", "mv_unified_scorecard")]:
        cur.execute(f"""
            SELECT
                ROUND(MIN(weighted_score)::numeric, 2),
                ROUND(AVG(weighted_score)::numeric, 2),
                ROUND(MAX(weighted_score)::numeric, 2),
                COUNT(*)
            FROM {table}
            WHERE weighted_score IS NOT NULL
        """)
        mn, avg, mx, cnt = cur.fetchone()
        print(f"  {label:8s}: min={mn}  avg={avg}  max={mx}  (n={cnt:,})")

    print()
    cur.close()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Score change report -- snapshot before rebuild, compare after."
    )
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('snapshot', help='Save current scores to snapshot table')
    sub.add_parser('compare', help='Compare snapshot to current MV')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    conn = get_connection()
    try:
        if args.command == 'snapshot':
            do_snapshot(conn)
        elif args.command == 'compare':
            rc = do_compare(conn)
            if rc:
                sys.exit(rc)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
