"""
Post-orphan-fix cleanup addressing Codex/Gemini review feedback.

1. Add is_historical column to f7_employers_deduped (both reviewers agree)
2. Create v_f7_employers_current view for post-2020 consumers
3. Remove 387 duplicate relation rows (Codex finding #1)
4. Re-generate employer_name_aggressive using canonical normalizer (Codex finding #4)

Run: py scripts/etl/post_orphan_fix_cleanup.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

# Import canonical normalizer (directory is named 'import' which is a reserved word)
import importlib.util
_normalizer_path = os.path.join(os.path.dirname(__file__), '..', 'import', 'name_normalizer.py')
_spec = importlib.util.spec_from_file_location("name_normalizer", _normalizer_path)
_name_normalizer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_name_normalizer)
normalize_employer_aggressive = _name_normalizer.normalize_employer_aggressive


def step1_add_is_historical(cur):
    """Add is_historical boolean column. TRUE for pre-2020 employers."""
    print("\n--- Step 1: Add is_historical column ---")

    # Add column if not exists
    cur.execute("""
        ALTER TABLE f7_employers_deduped
        ADD COLUMN IF NOT EXISTS is_historical BOOLEAN DEFAULT FALSE
    """)

    # Set TRUE for pre-2020 employers
    cur.execute("""
        UPDATE f7_employers_deduped
        SET is_historical = TRUE
        WHERE latest_notice_date < '2020-01-01'
          AND is_historical IS NOT TRUE
    """)
    updated = cur.rowcount
    print(f"  Marked {updated:,} employers as is_historical = TRUE")

    # Verify counts
    cur.execute("""
        SELECT is_historical, COUNT(*) as cnt
        FROM f7_employers_deduped
        GROUP BY is_historical
        ORDER BY is_historical
    """)
    for row in cur.fetchall():
        label = "Historical (pre-2020)" if row[0] else "Current (post-2020)"
        print(f"  {label}: {row[1]:,}")


def step2_create_current_view(cur):
    """Create view for queries that only need current/active employers."""
    print("\n--- Step 2: Create v_f7_employers_current view ---")

    cur.execute("""
        CREATE OR REPLACE VIEW v_f7_employers_current AS
        SELECT * FROM f7_employers_deduped
        WHERE is_historical IS NOT TRUE
    """)
    print("  Created v_f7_employers_current (post-2020 employers only)")

    cur.execute("SELECT COUNT(*) FROM v_f7_employers_current")
    count = cur.fetchone()[0]
    print(f"  View count: {count:,}")


def step3_dedup_relations(cur):
    """Remove 387 duplicate relation rows (same employer_id + union_file_number + notice_date)."""
    print("\n--- Step 3: Remove duplicate relations ---")

    # Count before
    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    before = cur.fetchone()[0]

    # Count duplicates
    cur.execute("""
        SELECT SUM(cnt - 1) FROM (
            SELECT COUNT(*) as cnt
            FROM f7_union_employer_relations
            GROUP BY employer_id, union_file_number, notice_date
            HAVING COUNT(*) > 1
        ) sub
    """)
    dup_count = cur.fetchone()[0] or 0
    print(f"  Duplicate rows to remove: {dup_count:,}")

    if dup_count == 0:
        print("  No duplicates found.")
        return

    # Delete duplicates, keeping the row with the lowest ctid (first physical row)
    cur.execute("""
        DELETE FROM f7_union_employer_relations
        WHERE ctid NOT IN (
            SELECT MIN(ctid)
            FROM f7_union_employer_relations
            GROUP BY employer_id, union_file_number, notice_date
        )
    """)
    deleted = cur.rowcount
    print(f"  Deleted {deleted:,} duplicate rows")

    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    after = cur.fetchone()[0]
    print(f"  Relations: {before:,} -> {after:,}")


def step4_fix_aggressive_names(cur):
    """Re-generate employer_name_aggressive using canonical Python normalizer.

    The orphan fix used an ad-hoc SQL regex which differs from the canonical
    normalize_employer_aggressive() function in name_normalizer.py.
    Re-apply the canonical version to all historical employers.
    """
    print("\n--- Step 4: Re-normalize employer_name_aggressive (canonical) ---")

    # Fetch all historical employers that need normalization
    cur.execute("""
        SELECT employer_id, employer_name
        FROM f7_employers_deduped
        WHERE is_historical = TRUE
          AND employer_name IS NOT NULL
    """)
    rows = cur.fetchall()
    print(f"  Historical employers to normalize: {len(rows):,}")

    if not rows:
        return

    # Batch normalize using canonical Python function
    batch_size = 5000
    total_updated = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        updates = []
        for employer_id, employer_name in batch:
            try:
                normalized = normalize_employer_aggressive(employer_name)
                updates.append((normalized, employer_id))
            except Exception:
                # If normalization fails, use simple UPPER TRIM
                updates.append((employer_name.upper().strip() if employer_name else None, employer_id))

        # Bulk update
        from psycopg2.extras import execute_batch
        execute_batch(cur,
            "UPDATE f7_employers_deduped SET employer_name_aggressive = %s WHERE employer_id = %s",
            updates,
            page_size=1000
        )
        total_updated += len(updates)
        if (i + batch_size) % 20000 == 0 or i + batch_size >= len(rows):
            print(f"  Normalized {total_updated:,}/{len(rows):,}")

    print(f"  Done. Updated {total_updated:,} employer_name_aggressive values")

    # Show sample before/after
    cur.execute("""
        SELECT employer_name, employer_name_aggressive
        FROM f7_employers_deduped
        WHERE is_historical = TRUE
        ORDER BY employer_name
        LIMIT 5
    """)
    print("\n  Sample normalizations:")
    for name, agg in cur.fetchall():
        print(f"    {(name or '')[:50]:<50} -> {(agg or '')[:50]}")


def main():
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        step1_add_is_historical(cur)
        step2_create_current_view(cur)
        step3_dedup_relations(cur)
        step4_fix_aggressive_names(cur)

        # Refresh materialized views
        print("\n--- Refreshing materialized views ---")
        for mv in ['mv_employer_features', 'mv_employer_search', 'mv_whd_employer_agg']:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW {mv}")
                print(f"  Refreshed {mv}")
            except Exception as e:
                conn.rollback()
                print(f"  FAILED {mv}: {str(e)[:80]}")

        conn.commit()
        print("\n  COMMITTED all changes.")

        # Final stats
        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM f7_employers_deduped) as total,
                (SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = TRUE) as historical,
                (SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical IS NOT TRUE) as current,
                (SELECT COUNT(*) FROM f7_union_employer_relations) as relations,
                (SELECT COUNT(*) FROM f7_union_employer_relations r
                 LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
                 WHERE d.employer_id IS NULL) as orphans
        """)
        row = cur.fetchone()
        print(f"\n  Final state:")
        print(f"    Total employers:      {row[0]:,}")
        print(f"    Historical (pre-2020): {row[1]:,}")
        print(f"    Current (post-2020):   {row[2]:,}")
        print(f"    Total relations:       {row[3]:,}")
        print(f"    Orphaned relations:    {row[4]:,}")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        conn.rollback()
        print("  ROLLED BACK.")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
