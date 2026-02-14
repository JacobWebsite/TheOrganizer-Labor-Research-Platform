"""
Flag low-confidence matches in osha_f7_matches and whd_f7_matches.
Adds a `low_confidence` BOOLEAN column (default FALSE) and sets it TRUE
for any match with confidence < 0.6. Does NOT delete any rows.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from db_config import get_connection

def main():
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    tables = ['osha_f7_matches', 'whd_f7_matches']

    # Step 1: Check if low_confidence column already exists
    print("=" * 70)
    print("STEP 1: Check existing columns")
    print("=" * 70)
    for tbl in tables:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'low_confidence'
        """, (tbl,))
        exists = cur.fetchone()
        print(f"  {tbl}.low_confidence exists: {bool(exists)}")

    # Step 2: Add column if not exists
    print("\nSTEP 2: Adding low_confidence column (IF NOT EXISTS)")
    for tbl in tables:
        cur.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS low_confidence BOOLEAN DEFAULT FALSE;")
        print(f"  {tbl}: ALTER TABLE complete")
    conn.commit()

    # Step 3: Check what the confidence column is actually called
    print("\nSTEP 3: Discover confidence-related columns")
    for tbl in tables:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name LIKE '%%confid%%'
            ORDER BY column_name
        """, (tbl,))
        cols = [r[0] for r in cur.fetchall()]
        print(f"  {tbl}: {cols}")

    # Also check for score-like columns in case confidence is named differently
    for tbl in tables:
        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (tbl,))
        all_cols = cur.fetchall()
        print(f"\n  All columns in {tbl}:")
        for col_name, col_type in all_cols:
            print(f"    {col_name} ({col_type})")

    # Step 4: Flag matches below 0.6 confidence
    print("\n" + "=" * 70)
    print("STEP 4: Flagging matches with confidence < 0.6")
    print("=" * 70)

    # First reset all to FALSE to be idempotent
    for tbl in tables:
        cur.execute(f"UPDATE {tbl} SET low_confidence = FALSE WHERE low_confidence IS TRUE;")

    # Now flag low-confidence matches
    for tbl in tables:
        # Check if 'confidence' column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'confidence'
        """, (tbl,))
        has_confidence = cur.fetchone()

        if has_confidence:
            cur.execute(f"UPDATE {tbl} SET low_confidence = TRUE WHERE confidence < 0.6;")
            flagged = cur.rowcount
            print(f"  {tbl}: flagged {flagged:,} rows with confidence < 0.6")
        else:
            # Try match_confidence, match_score or similarity_score
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND column_name IN ('match_confidence', 'match_score', 'similarity_score', 'score')
            """, (tbl,))
            alt = cur.fetchone()
            if alt:
                col = alt[0]
                cur.execute(f"UPDATE {tbl} SET low_confidence = TRUE WHERE {col} < 0.6;")
                flagged = cur.rowcount
                print(f"  {tbl}: flagged {flagged:,} rows with {col} < 0.6")
            else:
                print(f"  {tbl}: WARNING - no confidence/score column found! Skipping.")

    conn.commit()

    # Step 5: Summary stats
    print("\n" + "=" * 70)
    print("STEP 5: Summary Statistics")
    print("=" * 70)

    # Determine confidence column name for each table
    conf_cols = {}
    for tbl in tables:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name IN ('confidence', 'match_confidence', 'match_score', 'similarity_score', 'score')
            ORDER BY CASE column_name WHEN 'confidence' THEN 1 WHEN 'match_confidence' THEN 2 WHEN 'match_score' THEN 3 WHEN 'similarity_score' THEN 4 ELSE 5 END
            LIMIT 1
        """, (tbl,))
        row = cur.fetchone()
        conf_cols[tbl] = row[0] if row else None

    # Build dynamic summary query
    parts = []
    for tbl in tables:
        cc = conf_cols[tbl]
        if cc:
            parts.append(f"""
                SELECT
                    '{tbl}' as table_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN low_confidence THEN 1 ELSE 0 END) as flagged_low,
                    ROUND(100.0 * SUM(CASE WHEN low_confidence THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as pct_low,
                    ROUND(AVG({cc})::numeric, 3) as avg_confidence,
                    MIN({cc}) as min_confidence,
                    MAX({cc}) as max_confidence
                FROM {tbl}
            """)
        else:
            parts.append(f"""
                SELECT
                    '{tbl}' as table_name,
                    COUNT(*) as total,
                    0 as flagged_low,
                    0.0 as pct_low,
                    NULL::numeric as avg_confidence,
                    NULL::numeric as min_confidence,
                    NULL::numeric as max_confidence
                FROM {tbl}
            """)

    cur.execute(" UNION ALL ".join(parts))
    rows = cur.fetchall()

    print(f"\n  {'Table':<25} {'Total':>10} {'Flagged':>10} {'% Low':>8} {'Avg Conf':>10} {'Min':>8} {'Max':>8}")
    print(f"  {'-'*23}  {'-'*10} {'-'*10} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
    for r in rows:
        tbl, total, flagged, pct, avg_c, min_c, max_c = r
        avg_str = f"{avg_c:.3f}" if avg_c is not None else "N/A"
        min_str = f"{min_c:.3f}" if min_c is not None else "N/A"
        max_str = f"{max_c:.3f}" if max_c is not None else "N/A"
        pct_str = f"{pct:.1f}%" if pct is not None else "N/A"
        print(f"  {tbl:<25} {total:>10,} {flagged:>10,} {pct_str:>8} {avg_str:>10} {min_str:>8} {max_str:>8}")

    # Step 6: Distribution by match_method for flagged matches
    print("\n" + "=" * 70)
    print("STEP 6: Flagged matches by match_method")
    print("=" * 70)

    for tbl in tables:
        cc = conf_cols[tbl]
        # Check if match_method column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'match_method'
        """, (tbl,))
        has_method = cur.fetchone()

        if not has_method:
            # Try match_tier or match_type
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND column_name IN ('match_tier', 'match_type', 'tier')
                LIMIT 1
            """, (tbl,))
            alt = cur.fetchone()
            method_col = alt[0] if alt else None
        else:
            method_col = 'match_method'

        print(f"\n  {tbl} (grouped by {method_col or 'N/A'}):")
        if method_col and cc:
            cur.execute(f"""
                SELECT {method_col}, COUNT(*) as flagged,
                       ROUND(AVG({cc})::numeric, 3) as avg_conf,
                       ROUND(MIN({cc})::numeric, 3) as min_conf
                FROM {tbl}
                WHERE low_confidence
                GROUP BY {method_col}
                ORDER BY flagged DESC
            """)
            method_rows = cur.fetchall()
            if method_rows:
                print(f"    {'Method':<35} {'Flagged':>10} {'Avg Conf':>10} {'Min Conf':>10}")
                print(f"    {'-'*33}  {'-'*10} {'-'*10} {'-'*10}")
                for mr in method_rows:
                    method, flagged, avg_c, min_c = mr
                    print(f"    {str(method):<35} {flagged:>10,} {avg_c:>10.3f} {min_c:>10.3f}")
            else:
                print("    (no flagged rows)")
        else:
            print("    (no method/confidence column found)")

    # Step 7: Also show NOT-flagged summary for comparison
    print("\n" + "=" * 70)
    print("STEP 7: High-confidence matches (NOT flagged) by method")
    print("=" * 70)

    for tbl in tables:
        cc = conf_cols[tbl]
        # Reuse method_col detection
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name IN ('match_method', 'match_tier', 'match_type', 'tier')
            ORDER BY CASE column_name WHEN 'match_method' THEN 1 WHEN 'match_tier' THEN 2 ELSE 3 END
            LIMIT 1
        """, (tbl,))
        row = cur.fetchone()
        method_col = row[0] if row else None

        print(f"\n  {tbl} (grouped by {method_col or 'N/A'}):")
        if method_col and cc:
            cur.execute(f"""
                SELECT {method_col}, COUNT(*) as total,
                       ROUND(AVG({cc})::numeric, 3) as avg_conf,
                       ROUND(MIN({cc})::numeric, 3) as min_conf
                FROM {tbl}
                WHERE NOT low_confidence
                GROUP BY {method_col}
                ORDER BY total DESC
            """)
            method_rows = cur.fetchall()
            if method_rows:
                print(f"    {'Method':<35} {'Count':>10} {'Avg Conf':>10} {'Min Conf':>10}")
                print(f"    {'-'*33}  {'-'*10} {'-'*10} {'-'*10}")
                for mr in method_rows:
                    method, total, avg_c, min_c = mr
                    print(f"    {str(method):<35} {total:>10,} {avg_c:>10.3f} {min_c:>10.3f}")
            else:
                print("    (no high-confidence rows)")

    cur.close()
    conn.close()
    print("\nDone.")

if __name__ == '__main__':
    main()
