"""
Resolve historical employers by matching them against current employers.

Identifies which historical employers are actually the same as current ones
(name changed, merged, etc.) and creates merge candidates for review.

Usage:
    py scripts/matching/resolve_historical_employers.py
    py scripts/matching/resolve_historical_employers.py --dry-run
    py scripts/matching/resolve_historical_employers.py --threshold 0.5
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)


def find_merge_candidates(conn, threshold=0.4, dry_run=False):
    """Match historical employers against current using pre-computed name columns."""
    print("Loading historical employers...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT employer_id, employer_name, name_standard, name_aggressive,
                   state, city, naics
            FROM f7_employers_deduped
            WHERE is_historical = true
              AND name_standard IS NOT NULL
        """)
        historical = cur.fetchall()
        print(f"  Found {len(historical):,} historical employers")

    if not historical:
        print("No historical employers to resolve.")
        return

    # Match in batches using SQL
    candidates = []
    batch_size = 500
    total = len(historical)

    for i in range(0, total, batch_size):
        batch = historical[i:i + batch_size]
        done = min(i + batch_size, total)

        with conn.cursor() as cur:
            for h in batch:
                h_id, h_name, h_std, h_agg, h_state, h_city, h_naics = h

                if not h_std or not h_state:
                    continue

                # Tier 1: Exact name_standard + state match
                cur.execute("""
                    SELECT employer_id, employer_name, name_standard
                    FROM f7_employers_deduped
                    WHERE (is_historical IS NULL OR is_historical = false)
                      AND name_standard = %s AND UPPER(state) = %s
                      AND employer_id != %s
                    LIMIT 1
                """, [h_std, h_state.upper() if h_state else '', h_id])
                row = cur.fetchone()
                if row:
                    candidates.append({
                        "historical_id": h_id,
                        "current_id": row[0],
                        "method": "EXACT_NAME_STATE",
                        "score": 0.95,
                        "evidence": {
                            "historical_name": h_name,
                            "current_name": row[1],
                            "matched_on": "name_standard + state",
                        },
                    })
                    continue

                # Tier 2: Exact name_aggressive + state
                if h_agg:
                    cur.execute("""
                        SELECT employer_id, employer_name
                        FROM f7_employers_deduped
                        WHERE (is_historical IS NULL OR is_historical = false)
                          AND name_aggressive = %s AND UPPER(state) = %s
                          AND employer_id != %s
                        LIMIT 1
                    """, [h_agg, h_state.upper() if h_state else '', h_id])
                    row = cur.fetchone()
                    if row:
                        candidates.append({
                            "historical_id": h_id,
                            "current_id": row[0],
                            "method": "AGGRESSIVE_NAME_STATE",
                            "score": 0.80,
                            "evidence": {
                                "historical_name": h_name,
                                "current_name": row[1],
                                "matched_on": "name_aggressive + state",
                            },
                        })
                        continue

                # Tier 3: Fuzzy name + state (if pg_trgm available)
                try:
                    cur.execute("""
                        SELECT employer_id, employer_name,
                               similarity(name_standard, %s) as sim
                        FROM f7_employers_deduped
                        WHERE (is_historical IS NULL OR is_historical = false)
                          AND UPPER(state) = %s
                          AND name_standard %% %s
                          AND similarity(name_standard, %s) >= %s
                          AND employer_id != %s
                        ORDER BY sim DESC
                        LIMIT 1
                    """, [h_std, h_state.upper() if h_state else '',
                          h_std, h_std, threshold, h_id])
                    row = cur.fetchone()
                    if row:
                        candidates.append({
                            "historical_id": h_id,
                            "current_id": row[0],
                            "method": "FUZZY_NAME_STATE",
                            "score": round(float(row[2]), 3),
                            "evidence": {
                                "historical_name": h_name,
                                "current_name": row[1],
                                "similarity": round(float(row[2]), 3),
                                "matched_on": "fuzzy name_standard + state",
                            },
                        })
                except Exception:
                    pass  # pg_trgm not available

        print(f"  Processed {done:,} / {total:,} -- {len(candidates):,} candidates so far")

    print(f"\nFound {len(candidates):,} merge candidates")

    # Method distribution
    from collections import Counter
    methods = Counter(c["method"] for c in candidates)
    for method, count in methods.most_common():
        print(f"  {method:30s} {count:>6,}")

    if dry_run:
        print("\n[DRY RUN] Would insert candidates. Showing top 5:")
        for c in candidates[:5]:
            print(f"  {c['historical_id'][:16]} -> {c['current_id'][:16]} "
                  f"({c['method']}, {c['score']:.2f})")
        return

    # Write to historical_merge_candidates
    from psycopg2.extras import execute_batch
    sql = """
        INSERT INTO historical_merge_candidates
            (historical_employer_id, current_employer_id, match_method,
             confidence_score, evidence, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
        ON CONFLICT (historical_employer_id, current_employer_id) DO NOTHING
    """
    rows = [
        (c["historical_id"], c["current_id"], c["method"],
         c["score"], json.dumps(c["evidence"]))
        for c in candidates
    ]
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()

    # Verify
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM historical_merge_candidates")
        total_candidates = cur.fetchone()[0]
        cur.execute("""
            SELECT match_method, COUNT(*)
            FROM historical_merge_candidates
            GROUP BY match_method ORDER BY COUNT(*) DESC
        """)
        print(f"\nTotal merge candidates in table: {total_candidates:,}")
        for row in cur.fetchall():
            print(f"  {row[0]:30s} {row[1]:>6,}")


def main():
    parser = argparse.ArgumentParser(description="Resolve historical employers")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.4,
                        help="Fuzzy similarity threshold (default 0.4)")
    args = parser.parse_args()

    conn = get_connection()
    try:
        find_merge_candidates(conn, args.threshold, args.dry_run)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
