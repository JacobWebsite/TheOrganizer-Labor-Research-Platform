"""
Diagnostic queries for search dedup investigation.
Run before and after rebuild_search_mv.py to quantify the impact.

Usage: py scripts/analysis/diagnose_search_dedup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("SEARCH DEDUP DIAGNOSTIC")
    print("=" * 70)

    # 1. Total rows by source_type
    print("\n1. mv_employer_search rows by source_type:")
    try:
        cur.execute("""
            SELECT source_type, COUNT(*) AS cnt
            FROM mv_employer_search
            GROUP BY source_type
            ORDER BY cnt DESC
        """)
        for row in cur.fetchall():
            print(f"   {row[0]}: {row[1]:,}")
        cur.execute("SELECT COUNT(*) FROM mv_employer_search")
        print(f"   TOTAL: {cur.fetchone()[0]:,}")
    except Exception as e:
        print(f"   ERROR: {e}")
        conn.rollback()

    # 2. F7 rows: grouped vs ungrouped, canonical vs non, historical vs current
    print("\n2. F7 employers breakdown:")
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE canonical_group_id IS NOT NULL) AS grouped,
            COUNT(*) FILTER (WHERE canonical_group_id IS NULL) AS ungrouped,
            COUNT(*) FILTER (WHERE is_canonical_rep = TRUE) AS canonical_reps,
            COUNT(*) FILTER (WHERE is_historical = TRUE) AS historical,
            COUNT(*) FILTER (WHERE is_historical = FALSE) AS current_rows
        FROM f7_employers_deduped
    """)
    row = cur.fetchone()
    print(f"   Total:          {row[0]:,}")
    print(f"   Grouped:        {row[1]:,}")
    print(f"   Ungrouped:      {row[2]:,}")
    print(f"   Canonical reps: {row[3]:,}")
    print(f"   Historical:     {row[4]:,}")
    print(f"   Current:        {row[5]:,}")

    # Estimate after dedup
    cur.execute("""
        SELECT COUNT(*)
        FROM f7_employers_deduped
        WHERE NOT is_historical
          AND (canonical_group_id IS NULL OR is_canonical_rep = TRUE)
    """)
    deduped = cur.fetchone()[0]
    print(f"\n   After dedup (current + canonical/ungrouped): {deduped:,}")
    print(f"   Reduction from {row[0]:,}: {row[0] - deduped:,} rows "
          f"({100.0 * (row[0] - deduped) / row[0]:.1f}%)")

    # 3. Top 20 most-duplicated employer names
    print("\n3. Top 20 most-duplicated employer names (by name_aggressive):")
    cur.execute("""
        SELECT name_aggressive, COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE NOT is_historical) AS current_cnt,
               array_agg(DISTINCT state ORDER BY state) AS states
        FROM f7_employers_deduped
        WHERE name_aggressive IS NOT NULL
        GROUP BY name_aggressive
        HAVING COUNT(*) >= 5
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        states = row[3][:5] if row[3] else []
        states_str = ','.join(str(s) for s in states)
        print(f"   {str(row[0])[:45]:<45} {row[1]:>4} rows "
              f"({row[2]:>4} current)  [{states_str}]")

    # 4. Search simulation
    print("\n4. Search simulation (rows per term in current MV):")
    for term in ['starbucks', 'ford', 'amazon', 'walmart', 'verizon', 'kaiser']:
        try:
            cur.execute("""
                SELECT COUNT(*)
                FROM mv_employer_search
                WHERE similarity(search_name, %s) > 0.2
            """, [term])
            cnt = cur.fetchone()[0]
            print(f"   '{term}': {cnt:,} rows")
        except Exception:
            print(f"   '{term}': (similarity not available)")
            conn.rollback()
            break

    # 5. Group size distribution
    print("\n5. Canonical group size distribution:")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE member_count >= 20) AS g20plus,
            COUNT(*) FILTER (WHERE member_count >= 10 AND member_count < 20) AS g10_19,
            COUNT(*) FILTER (WHERE member_count >= 5 AND member_count < 10) AS g5_9,
            COUNT(*) FILTER (WHERE member_count >= 2 AND member_count < 5) AS g2_4
        FROM employer_canonical_groups
    """)
    row = cur.fetchone()
    print(f"   20+ members:  {row[0]:,} groups")
    print(f"   10-19:        {row[1]:,} groups")
    print(f"   5-9:          {row[2]:,} groups")
    print(f"   2-4:          {row[3]:,} groups")

    # 6. Impact estimate
    print("\n6. Impact estimate:")
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    total_f7 = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*)
        FROM f7_employers_deduped
        WHERE NOT is_historical
          AND (canonical_group_id IS NULL OR is_canonical_rep = TRUE)
    """)
    after_f7 = cur.fetchone()[0]

    try:
        cur.execute(
            "SELECT COUNT(*) FROM mv_employer_search WHERE source_type != 'F7'"
        )
        non_f7 = cur.fetchone()[0]
    except Exception:
        non_f7 = 0
        conn.rollback()

    print(f"   F7 before:   {total_f7:,}")
    print(f"   F7 after:    {after_f7:,}")
    print(f"   Non-F7:      {non_f7:,} (unchanged)")
    print(f"   MV total:    {after_f7 + non_f7:,} (estimated)")

    cur.close()
    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
