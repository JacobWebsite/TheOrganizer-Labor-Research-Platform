"""
Fix orphaned f7_employer_id values in nlrb_employer_xref.

Root cause: f7_employers_deduped uses a date filter (WHERE latest_notice_date >= '2020-01-01'),
so older employers are excluded. nlrb_employer_xref still references those old IDs.

Fix strategy:
  1. Investigate scope of orphans (merge log, raw f7, name+state match)
  2. Remap orphans found in f7_employer_merge_log -> new_employer_id
  3. Remap orphans with name+state match in f7_employers_deduped
  4. NULL out remaining orphans (historical, no match in current scope)
"""
import sys
sys.path.insert(0, r'C:\Users\jakew\Downloads\labor-data-project')

from db_config import get_connection


def main():
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # ---------------------------------------------------------------
    # PHASE 1: Investigation
    # ---------------------------------------------------------------
    print("=" * 70)
    print("PHASE 1: Investigating NLRB xref orphans")
    print("=" * 70)

    # Total orphans (f7_employer_id not in deduped)
    cur.execute("""
        SELECT COUNT(DISTINCT x.f7_employer_id)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    total_orphan_ids = cur.fetchone()[0]
    print(f"\nTotal orphaned f7_employer_ids (not in deduped): {total_orphan_ids:,}")

    # Total orphan rows
    cur.execute("""
        SELECT COUNT(*)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    total_orphan_rows = cur.fetchone()[0]
    print(f"Total orphan xref ROWS: {total_orphan_rows:,}")

    # How many orphaned IDs are in the merge log?
    cur.execute("""
        SELECT COUNT(DISTINCT x.f7_employer_id)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        JOIN f7_employer_merge_log m ON x.f7_employer_id = m.deleted_id
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    in_merge_log = cur.fetchone()[0]
    print(f"\nOrphans in merge log (can remap via merge): {in_merge_log:,}")

    # How many are in raw f7_employers but not deduped (date-filtered)?
    cur.execute("""
        SELECT COUNT(DISTINCT x.f7_employer_id)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        JOIN f7_employers fe ON x.f7_employer_id = fe.employer_id
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    in_raw_f7 = cur.fetchone()[0]
    print(f"Orphans in raw f7_employers (date-filtered out): {in_raw_f7:,}")

    # How many have a name+state match in deduped?
    cur.execute("""
        SELECT COUNT(DISTINCT x.f7_employer_id)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        JOIN f7_employers fe ON x.f7_employer_id = fe.employer_id
        JOIN f7_employers_deduped d2
            ON UPPER(TRIM(fe.employer_name)) = UPPER(TRIM(d2.employer_name))
            AND UPPER(TRIM(fe.state)) = UPPER(TRIM(d2.state))
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    has_name_state_match = cur.fetchone()[0]
    print(f"Orphans with name+state match in deduped: {has_name_state_match:,}")

    # Orphans NOT in merge log AND NOT having name+state match
    cur.execute("""
        SELECT COUNT(DISTINCT x.f7_employer_id)
        FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        LEFT JOIN f7_employer_merge_log m ON x.f7_employer_id = m.deleted_id
        LEFT JOIN (
            SELECT DISTINCT fe2.employer_id
            FROM f7_employers fe2
            JOIN f7_employers_deduped d3
                ON UPPER(TRIM(fe2.employer_name)) = UPPER(TRIM(d3.employer_name))
                AND UPPER(TRIM(fe2.state)) = UPPER(TRIM(d3.state))
        ) ns ON x.f7_employer_id = ns.employer_id
        WHERE d.employer_id IS NULL
          AND x.f7_employer_id IS NOT NULL
          AND m.deleted_id IS NULL
          AND ns.employer_id IS NULL
    """)
    truly_orphaned = cur.fetchone()[0]
    print(f"Truly orphaned (no merge log, no name+state match): {truly_orphaned:,}")

    # ---------------------------------------------------------------
    # PHASE 2: Remap via merge log
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 2: Remapping orphans via merge log")
    print("=" * 70)

    cur.execute("""
        UPDATE nlrb_employer_xref x
        SET f7_employer_id = m.kept_id
        FROM f7_employer_merge_log m
        WHERE x.f7_employer_id = m.deleted_id
        AND NOT EXISTS (
            SELECT 1 FROM f7_employers_deduped d
            WHERE d.employer_id = x.f7_employer_id
        )
    """)
    merge_remapped = cur.rowcount
    print(f"Rows remapped via merge log: {merge_remapped:,}")

    # ---------------------------------------------------------------
    # PHASE 3: Remap via name+state match
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 3: Remapping orphans via name+state match")
    print("=" * 70)

    # Use a subquery to pick one match if there are multiple (MIN for determinism)
    cur.execute("""
        UPDATE nlrb_employer_xref x
        SET f7_employer_id = sub.new_id
        FROM (
            SELECT DISTINCT ON (fe.employer_id)
                fe.employer_id AS old_id,
                d2.employer_id AS new_id
            FROM f7_employers fe
            JOIN f7_employers_deduped d2
                ON UPPER(TRIM(fe.employer_name)) = UPPER(TRIM(d2.employer_name))
                AND UPPER(TRIM(fe.state)) = UPPER(TRIM(d2.state))
            WHERE NOT EXISTS (
                SELECT 1 FROM f7_employers_deduped d
                WHERE d.employer_id = fe.employer_id
            )
            ORDER BY fe.employer_id, d2.employer_id
        ) sub
        WHERE x.f7_employer_id = sub.old_id
        AND NOT EXISTS (
            SELECT 1 FROM f7_employers_deduped d
            WHERE d.employer_id = x.f7_employer_id
        )
        AND x.f7_employer_id IS NOT NULL
    """)
    name_state_remapped = cur.rowcount
    print(f"Rows remapped via name+state match: {name_state_remapped:,}")

    # ---------------------------------------------------------------
    # PHASE 4: NULL out remaining orphans
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 4: Nulling out remaining orphans (historical, no match)")
    print("=" * 70)

    cur.execute("""
        UPDATE nlrb_employer_xref x
        SET f7_employer_id = NULL
        WHERE x.f7_employer_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM f7_employers_deduped d
            WHERE d.employer_id = x.f7_employer_id
        )
    """)
    nulled_rows = cur.rowcount
    print(f"Rows nulled (historical, no match): {nulled_rows:,}")

    # ---------------------------------------------------------------
    # PHASE 5: Final summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 5: Final summary")
    print("=" * 70)

    cur.execute("SELECT COUNT(*) FROM nlrb_employer_xref")
    total_rows = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM nlrb_employer_xref x
        JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
    """)
    valid_f7 = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM nlrb_employer_xref WHERE f7_employer_id IS NULL")
    null_f7 = cur.fetchone()[0]

    # Verify zero orphans remain
    cur.execute("""
        SELECT COUNT(*) FROM nlrb_employer_xref x
        LEFT JOIN f7_employers_deduped d ON x.f7_employer_id = d.employer_id
        WHERE d.employer_id IS NULL AND x.f7_employer_id IS NOT NULL
    """)
    remaining_orphans = cur.fetchone()[0]

    print(f"\n  Total xref rows:                   {total_rows:,}")
    print(f"  Rows with valid f7_employer_id:     {valid_f7:,}")
    print(f"  Rows with NULL f7_employer_id:      {null_f7:,}")
    print(f"  ---")
    print(f"  Rows remapped via merge log:        {merge_remapped:,}")
    print(f"  Rows remapped via name+state match: {name_state_remapped:,}")
    print(f"  Rows nulled (historical, no match): {nulled_rows:,}")
    print(f"  ---")
    print(f"  Remaining orphans:                  {remaining_orphans:,}")

    if remaining_orphans > 0:
        print("\n  WARNING: Still have orphaned f7_employer_ids!")
    else:
        print("\n  All orphans resolved.")

    # Commit
    conn.commit()
    print("\nChanges committed.")
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
