"""
Investigate the 60,373 orphaned f7_union_employer_relations rows.
Are they real additional bargaining relationships, pre-dedup duplicates,
or public sector employers not in the deduped table?
"""
import sys
sys.path.insert(0, r'C:\Users\jakew\Downloads\labor-data-project')
from db_config import get_connection
import psycopg2.extras

def run_query(cur, label, sql, fetch='all'):
    print(f"\n{'='*80}")
    print(f"QUERY {label}")
    print(f"{'='*80}")
    cur.execute(sql)
    if fetch == 'all':
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return rows, cols
    return None, None

def print_table(rows, cols, max_rows=None):
    if not rows:
        print("  (no rows)")
        return
    # Calculate column widths
    widths = [len(c) for c in cols]
    display_rows = rows[:max_rows] if max_rows else rows
    for row in display_rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val) if val is not None else 'NULL'))
    # Print header
    header = ' | '.join(c.ljust(widths[i]) for i, c in enumerate(cols))
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    # Print rows
    for row in display_rows:
        line = ' | '.join(
            (str(v) if v is not None else 'NULL').ljust(widths[i])
            for i, v in enumerate(row)
        )
        print(f"  {line}")
    if max_rows and len(rows) > max_rows:
        print(f"  ... ({len(rows) - max_rows} more rows)")

def main():
    conn = get_connection()
    cur = conn.cursor()

    # ---- Baseline counts ----
    print("\n" + "#"*80)
    print("# BASELINE COUNTS")
    print("#"*80)
    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    total_relations = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    deduped_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM f7_employers")
    raw_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM f7_employer_merge_log")
    merge_log_count = cur.fetchone()[0]
    print(f"  f7_union_employer_relations: {total_relations:,}")
    print(f"  f7_employers_deduped:        {deduped_count:,}")
    print(f"  f7_employers (raw):          {raw_count:,}")
    print(f"  f7_employer_merge_log:       {merge_log_count:,}")

    # Confirm orphan count
    cur.execute("""
        SELECT COUNT(DISTINCT r.employer_id)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    orphan_ids = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    orphan_rows = cur.fetchone()[0]
    print(f"\n  Orphaned distinct employer_ids: {orphan_ids:,}")
    print(f"  Orphaned relation rows:        {orphan_rows:,}")

    # ---- Query 1: Orphans in merge log ----
    # Merge log uses: deleted_id (the one removed) -> kept_id (the survivor)
    rows, cols = run_query(cur, "1: Orphaned employer_ids that appear in f7_employer_merge_log (as deleted_id)", """
        SELECT COUNT(DISTINCT r.employer_id)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
        WHERE d.employer_id IS NULL
    """)
    print(f"  Result: {rows[0][0]:,} orphaned employer_ids are in the merge log (as deleted_id)")

    # ---- Query 2: Orphans NOT in merge log ----
    rows, cols = run_query(cur, "2: Orphaned employer_ids NOT in merge log", """
        SELECT COUNT(DISTINCT r.employer_id)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
        WHERE d.employer_id IS NULL AND m.deleted_id IS NULL
    """)
    not_in_merge = rows[0][0]
    print(f"  Result: {not_in_merge:,} orphaned employer_ids are NOT in the merge log")

    # ---- Query 3: Do orphans (not in merge log) exist in raw f7_employers? ----
    rows, cols = run_query(cur, "3: Orphans NOT in merge log - do they exist in raw f7_employers?", """
        SELECT COUNT(DISTINCT r.employer_id) as total_orphan_ids,
               COUNT(DISTINCT CASE WHEN fe.employer_id IS NOT NULL THEN r.employer_id END) as in_raw_f7,
               COUNT(DISTINCT CASE WHEN fe.employer_id IS NULL THEN r.employer_id END) as not_in_raw_f7
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
        LEFT JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL AND m.deleted_id IS NULL
    """)
    print_table(rows, cols)

    # ---- Query 4: Sample raw f7_employers records for orphans not in merge log ----
    rows, cols = run_query(cur, "4: Sample 20 raw f7_employers records for orphans NOT in merge log", """
        SELECT fe.employer_id, fe.employer_name, fe.state, fe.city, fe.naics
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
        JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL AND m.deleted_id IS NULL
        ORDER BY fe.employer_name
        LIMIT 20
    """)
    print_table(rows, cols)

    # ---- Query 5: Orphans with exact name+state match in deduped ----
    rows, cols = run_query(cur, "5: Orphans (not in merge log, in raw f7) with exact name+state match in deduped", """
        SELECT COUNT(DISTINCT orphans.employer_id) as orphan_with_dedup_match
        FROM (
            SELECT DISTINCT r.employer_id
            FROM f7_union_employer_relations r
            LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
            LEFT JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
            WHERE d.employer_id IS NULL AND m.deleted_id IS NULL
        ) orphans
        JOIN f7_employers fe ON orphans.employer_id = fe.employer_id
        JOIN f7_employers_deduped d2 ON UPPER(TRIM(fe.employer_name)) = UPPER(TRIM(d2.employer_name))
            AND UPPER(TRIM(fe.state)) = UPPER(TRIM(d2.state))
    """)
    match_count = rows[0][0]
    print(f"  Result: {match_count:,} orphans have exact name+state match in deduped table")
    print(f"  That leaves {not_in_merge - match_count:,} orphans with NO match in deduped table")

    # ---- Query 6: Workers covered by orphaned relations ----
    rows, cols = run_query(cur, "6: Workers covered by orphaned relations", """
        SELECT
            CASE WHEN m.deleted_id IS NOT NULL THEN 'IN_MERGE_LOG' ELSE 'NOT_IN_MERGE_LOG' END as category,
            COUNT(*) as relation_count,
            COALESCE(SUM(r.bargaining_unit_size), 0) as total_workers
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
        WHERE d.employer_id IS NULL
        GROUP BY 1
        ORDER BY 1
    """)
    print_table(rows, cols)

    # ---- Query 7: Structure of f7_employer_merge_log ----
    rows, cols = run_query(cur, "7: f7_employer_merge_log structure (sample 5)", """
        SELECT id, merge_date, kept_id, deleted_id, kept_name, deleted_name, similarity_score,
               f7_union_employer_relations_updated
        FROM f7_employer_merge_log LIMIT 5
    """)
    print_table(rows, cols)

    # ---- Query 8: Raw f7 IDs not in deduped ----
    rows, cols = run_query(cur, "8: Raw f7_employers IDs not in deduped table", """
        SELECT COUNT(*) as raw_not_in_deduped,
               (SELECT COUNT(*) FROM f7_employers_deduped) as deduped_count,
               (SELECT COUNT(*) FROM f7_employers) as total_raw
        FROM f7_employers fe
        WHERE NOT EXISTS (SELECT 1 FROM f7_employers_deduped d WHERE d.employer_id = fe.employer_id)
    """)
    print_table(rows, cols)

    # ---- BONUS Query 9: What percentage of orphan relations point to IDs that simply aren't in raw f7 at all? ----
    rows, cols = run_query(cur, "BONUS 9: Orphan relations whose employer_id is NOT in raw f7_employers either", """
        SELECT COUNT(*) as relation_count,
               COUNT(DISTINCT r.employer_id) as distinct_ids
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL AND fe.employer_id IS NULL
    """)
    print_table(rows, cols)

    # ---- BONUS Query 10: Check if the deduped table was built from a SUBSET of raw f7 ----
    rows, cols = run_query(cur, "BONUS 10: Distribution of raw f7 IDs - in deduped, in merge log, or neither", """
        SELECT
            CASE
                WHEN d.employer_id IS NOT NULL THEN 'IN_DEDUPED'
                WHEN m.deleted_id IS NOT NULL THEN 'IN_MERGE_LOG_ONLY'
                ELSE 'NEITHER'
            END as category,
            COUNT(*) as employer_count
        FROM f7_employers fe
        LEFT JOIN f7_employers_deduped d ON fe.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON fe.employer_id = m.deleted_id
        GROUP BY 1
        ORDER BY 2 DESC
    """)
    print_table(rows, cols)

    # ---- BONUS Query 11: What columns does f7_employers have? ----
    rows, cols = run_query(cur, "BONUS 11: f7_employers table columns", """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'f7_employers'
        ORDER BY ordinal_position
    """)
    print_table(rows, cols)

    # ---- BONUS Query 12: Does f7_employers have a sector or public/private indicator? ----
    rows, cols = run_query(cur, "BONUS 12: f7_employers_deduped table columns", """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'f7_employers_deduped'
        ORDER BY ordinal_position
    """)
    print_table(rows, cols)

    # ---- BONUS Query 13: How many raw f7 employers are in NEITHER deduped NOR merge log? Sample them. ----
    rows, cols = run_query(cur, "BONUS 13: Sample 20 raw f7 employers in NEITHER deduped NOR merge log", """
        SELECT fe.employer_id, fe.employer_name, fe.state, fe.city
        FROM f7_employers fe
        LEFT JOIN f7_employers_deduped d ON fe.employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON fe.employer_id = m.deleted_id
        WHERE d.employer_id IS NULL AND m.deleted_id IS NULL
        ORDER BY fe.employer_name
        LIMIT 20
    """)
    print_table(rows, cols)

    # ---- BONUS Query 14: Compare ID ranges ----
    rows, cols = run_query(cur, "BONUS 14: Compare ID ranges - raw vs deduped", """
        SELECT
            'f7_employers' as source,
            MIN(employer_id) as min_id,
            MAX(employer_id) as max_id,
            COUNT(*) as count
        FROM f7_employers
        UNION ALL
        SELECT
            'f7_employers_deduped',
            MIN(employer_id),
            MAX(employer_id),
            COUNT(*)
        FROM f7_employers_deduped
    """)
    print_table(rows, cols)

    # ---- BONUS Query 15: Do all kept_ids exist in deduped? ----
    rows, cols = run_query(cur, "BONUS 15: Merge log - do kept_ids all exist in deduped?", """
        SELECT
            COUNT(*) as total_merge_entries,
            COUNT(DISTINCT deleted_id) as distinct_deleted_ids,
            COUNT(DISTINCT kept_id) as distinct_kept_ids,
            COUNT(DISTINCT CASE WHEN d.employer_id IS NOT NULL THEN m.kept_id END) as kept_ids_in_deduped,
            COUNT(DISTINCT CASE WHEN d.employer_id IS NULL THEN m.kept_id END) as kept_ids_NOT_in_deduped
        FROM f7_employer_merge_log m
        LEFT JOIN f7_employers_deduped d ON m.kept_id = d.employer_id
    """)
    print_table(rows, cols)

    # ---- BONUS Query 16: Check f7_union_employer_relations_updated column ----
    rows, cols = run_query(cur, "BONUS 16: How many merge log entries updated relations?", """
        SELECT
            SUM(CASE WHEN f7_union_employer_relations_updated IS NULL THEN 1 ELSE 0 END) as null_count,
            SUM(CASE WHEN f7_union_employer_relations_updated = 0 THEN 1 ELSE 0 END) as zero_count,
            SUM(CASE WHEN f7_union_employer_relations_updated > 0 THEN 1 ELSE 0 END) as nonzero_count,
            SUM(COALESCE(f7_union_employer_relations_updated, 0)) as total_relations_updated
        FROM f7_employer_merge_log
    """)
    print_table(rows, cols)

    # ---- BONUS Query 17: Check if relations table has orphans that SHOULD have been repointed ----
    rows, cols = run_query(cur, "BONUS 17: Relations with deleted_id that were NOT repointed to kept_id", """
        SELECT COUNT(*) as relations_still_pointing_to_deleted_id
        FROM f7_union_employer_relations r
        JOIN f7_employer_merge_log m ON r.employer_id = m.deleted_id
    """)
    print(f"  Result: {rows[0][0]:,} relations still point to a deleted (merged) employer_id")
    print("  These SHOULD have been repointed to the kept_id during merge!")

    # ---- BONUS Query 18: Check the gap between raw f7 and deduped ----
    rows, cols = run_query(cur, "BONUS 18: Did f7_employers_deduped originate from a DIFFERENT ingestion than f7_employers?", """
        SELECT 'IDs in deduped NOT in raw' as check_type,
               COUNT(*) as count
        FROM f7_employers_deduped d
        WHERE NOT EXISTS (SELECT 1 FROM f7_employers fe WHERE fe.employer_id = d.employer_id)
        UNION ALL
        SELECT 'IDs in raw NOT in deduped',
               COUNT(*)
        FROM f7_employers fe
        WHERE NOT EXISTS (SELECT 1 FROM f7_employers_deduped d WHERE d.employer_id = fe.employer_id)
    """)
    print_table(rows, cols)

    # ---- SUMMARY ----
    print("\n\n" + "#"*80)
    print("# SUMMARY AND DIAGNOSIS")
    print("#"*80)
    print("""
The orphaned relations problem has potentially THREE distinct populations:

1. MERGE LOG orphans: employer_ids that were merged by Splink dedup.
   The merge log records deleted_id -> kept_id mappings.
   If relations still point to deleted_ids, the merge script's
   f7_union_employer_relations UPDATE did not execute properly.
   FIX: UPDATE f7_union_employer_relations SET employer_id = m.kept_id
        FROM f7_employer_merge_log m
        WHERE employer_id = m.deleted_id

2. NON-MERGE-LOG orphans IN raw f7_employers: employer_ids that exist
   in the raw table but were never carried into f7_employers_deduped
   and never logged as merged. These were likely dropped during dedup
   without being recorded -- possibly filtered out (e.g., by a WHERE
   clause in the initial dedup load).

3. Phantom IDs: employer_ids in relations that don't exist in raw
   f7_employers OR deduped. These would be data integrity issues from
   the original SQLite ingestion.
""")

    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
