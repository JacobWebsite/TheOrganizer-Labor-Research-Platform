"""
Diagnostic script for missing unions (orphan file numbers).

Reports on orphaned union file numbers in f7_union_employer_relations
that have no corresponding entry in unions_master.

Usage:
    py scripts/analysis/verify_missing_unions.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # 1. Exact orphan count and worker total
    cur.execute("""
        SELECT COUNT(DISTINCT r.union_file_number) AS orphan_fnums,
               COUNT(*) AS orphan_rows,
               COALESCE(SUM(r.bargaining_unit_size), 0) AS orphan_workers
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
    """)
    row = cur.fetchone()
    print("=" * 70)
    print("MISSING UNIONS DIAGNOSTIC")
    print("=" * 70)
    print(f"Orphan file numbers:  {row[0]:,}")
    print(f"Orphan relation rows: {row[1]:,}")
    print(f"Orphan workers:       {row[2]:,}")

    # 2. Total relation rows (for context)
    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    total_rows = cur.fetchone()[0]
    print(f"Total relation rows:  {total_rows:,}")
    print(f"Orphan pct:           {row[1] / total_rows * 100:.1f}%")

    # 3. Crosswalk-resolvable fnums
    cur.execute("""
        WITH orphans AS (
            SELECT DISTINCT r.union_file_number
            FROM f7_union_employer_relations r
            LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
            WHERE u.f_num IS NULL
        )
        SELECT o.union_file_number,
               c.matched_fnum,
               c.matched_union_name,
               c.match_method,
               c.confidence,
               CASE WHEN u2.f_num IS NOT NULL THEN 'YES' ELSE 'NO' END AS in_master
        FROM orphans o
        JOIN f7_fnum_crosswalk c ON c.f7_fnum = o.union_file_number
        LEFT JOIN unions_master u2 ON u2.f_num = c.matched_fnum::text
        ORDER BY o.union_file_number, c.confidence DESC NULLS LAST
    """)
    xwalk = cur.fetchall()
    print(f"\n--- Crosswalk-resolvable orphans ---")
    if xwalk:
        print(f"{'Orphan':>8} {'Target':>8} {'In Master':>9} {'Conf':>5}  Name")
        print(f"{'------':>8} {'------':>8} {'---------':>9} {'----':>5}  ----")
        for r in xwalk:
            name = (r[2] or "")[:50]
            print(f"{r[0]:>8} {r[1]:>8} {r[5]:>9} {r[4] or 0:>5.2f}  {name}")
    else:
        print("  None found.")

    # 4. CWA District 7 (fnum 12590)
    print(f"\n--- CWA District 7 (fnum 12590) ---")
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(bargaining_unit_size), 0)
        FROM f7_union_employer_relations
        WHERE union_file_number = 12590
    """)
    cwa = cur.fetchone()
    print(f"  Relations: {cwa[0]:,}, Workers: {cwa[1]:,}")

    # Check if 12590 is still an orphan
    cur.execute("SELECT f_num FROM unions_master WHERE f_num = '12590'")
    if cur.fetchone():
        print("  Status: RESOLVED (exists in unions_master)")
    else:
        print("  Status: STILL ORPHANED")

    # Show successor locals from crosswalk
    cur.execute("""
        SELECT c.matched_fnum, c.matched_union_name, c.confidence,
               CASE WHEN u.f_num IS NOT NULL THEN 'YES' ELSE 'NO' END AS in_master,
               u.union_name, u.state
        FROM f7_fnum_crosswalk c
        LEFT JOIN unions_master u ON u.f_num = c.matched_fnum::text
        WHERE c.f7_fnum = 12590
        ORDER BY c.confidence DESC NULLS LAST
    """)
    successors = cur.fetchall()
    if successors:
        print(f"  Successor locals ({len(successors)}):")
        for s in successors:
            master_name = s[4] or s[1] or "?"
            in_m = s[3]
            state = s[5] or "?"
            print(f"    {s[0]:>8} [{in_m}] {master_name[:45]}  state={state}")
    else:
        print("  No crosswalk entries found.")

    # Show state distribution of 12590 employer relations
    cur.execute("""
        SELECT e.state, COUNT(*) AS cnt, COALESCE(SUM(r.bargaining_unit_size), 0) AS workers
        FROM f7_union_employer_relations r
        JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
        WHERE r.union_file_number = 12590
        GROUP BY e.state
        ORDER BY workers DESC
    """)
    states = cur.fetchall()
    if states:
        print(f"  State distribution of employers:")
        for s in states:
            print(f"    {s[0] or '?':>3}: {s[1]:>3} relations, {s[2]:>6,} workers")

    # 5. Top 20 unresolved fnums by worker count
    print(f"\n--- Top 20 unresolved fnums by worker count ---")
    cur.execute("""
        SELECT r.union_file_number,
               COUNT(*) AS relation_count,
               COALESCE(SUM(r.bargaining_unit_size), 0) AS total_workers
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
        GROUP BY r.union_file_number
        ORDER BY total_workers DESC
        LIMIT 20
    """)
    top20 = cur.fetchall()
    print(f"{'Fnum':>8} {'Rels':>5} {'Workers':>8}")
    print(f"{'----':>8} {'----':>5} {'-------':>8}")
    for r in top20:
        print(f"{r[0]:>8} {r[1]:>5} {r[2]:>8,}")

    # 6. lm_data filing history for orphan fnums
    print(f"\n--- lm_data filing history for orphan fnums ---")
    cur.execute("""
        WITH orphans AS (
            SELECT DISTINCT r.union_file_number
            FROM f7_union_employer_relations r
            LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
            WHERE u.f_num IS NULL
        )
        SELECT COUNT(DISTINCT o.union_file_number) AS with_lm,
               (SELECT COUNT(DISTINCT union_file_number) FROM orphans) - COUNT(DISTINCT o.union_file_number) AS without_lm
        FROM orphans o
        JOIN lm_data lm ON lm.f_num = o.union_file_number::text
    """)
    lm = cur.fetchone()
    print(f"  With lm_data history:    {lm[0]:,}")
    print(f"  Without lm_data history: {lm[1]:,}")

    if lm[0] > 0:
        cur.execute("""
            WITH orphans AS (
                SELECT DISTINCT r.union_file_number
                FROM f7_union_employer_relations r
                LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
                WHERE u.f_num IS NULL
            )
            SELECT o.union_file_number,
                   lm.union_name,
                   MIN(lm.yr_covered) AS earliest,
                   MAX(lm.yr_covered) AS latest,
                   COUNT(*) AS filings
            FROM orphans o
            JOIN lm_data lm ON lm.f_num = o.union_file_number::text
            GROUP BY o.union_file_number, lm.union_name
            ORDER BY MAX(lm.yr_covered) DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\n  Top orphans with lm_data (by latest filing):")
            print(f"  {'Fnum':>8} {'Earliest':>8} {'Latest':>8} {'Filings':>7}  Name")
            for r in rows:
                name = (r[1] or "")[:45]
                print(f"  {r[0]:>8} {r[2] or '?':>8} {r[3] or '?':>8} {r[4]:>7}  {name}")

    # 7. pg_trgm name matches
    print(f"\n--- pg_trgm name similarity matches ---")
    if lm[0] > 0:
        cur.execute("""
            WITH orphan_names AS (
                SELECT DISTINCT ON (lm.f_num) lm.f_num, lm.union_name
                FROM lm_data lm
                JOIN (
                    SELECT DISTINCT r.union_file_number
                    FROM f7_union_employer_relations r
                    LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
                    WHERE u.f_num IS NULL
                ) o ON lm.f_num = o.union_file_number::text
                WHERE lm.union_name IS NOT NULL
                ORDER BY lm.f_num, lm.yr_covered DESC
            )
            SELECT bn.f_num, bn.union_name,
                   u.f_num AS match_fnum, u.union_name AS match_name,
                   similarity(LOWER(bn.union_name), LOWER(u.union_name)) AS sim
            FROM orphan_names bn
            CROSS JOIN LATERAL (
                SELECT u2.f_num, u2.union_name
                FROM unions_master u2
                WHERE similarity(LOWER(bn.union_name), LOWER(u2.union_name)) >= 0.7
                ORDER BY similarity(LOWER(bn.union_name), LOWER(u2.union_name)) DESC
                LIMIT 1
            ) u
            ORDER BY sim DESC
            LIMIT 20
        """)
        matches = cur.fetchall()
        if matches:
            for r in matches:
                print(f"  {r[0]:>8} '{r[1][:35]}' -> {r[2]:>8} '{r[3][:35]}' sim={r[4]:.3f}")
        else:
            print("  No matches at >= 0.7 threshold.")
    else:
        print("  Skipped (no orphan fnums have lm_data names to match).")

    # 8. Resolution log table status
    print(f"\n--- Resolution log table ---")
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'union_fnum_resolution_log'
        ) AS e
    """)
    if cur.fetchone()[0]:
        cur.execute("SELECT COUNT(*) FROM union_fnum_resolution_log")
        cnt = cur.fetchone()[0]
        print(f"  Exists, {cnt:,} entries.")
    else:
        print("  Does not exist yet.")

    print(f"\n{'=' * 70}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
