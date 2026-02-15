"""
Post-merge refresh: refresh materialized views, sector views, and check BLS alignment.

Run this after merge operations (merge_f7_enhanced.py, review_true_duplicates.py).

Steps:
1. Refresh mv_employer_search materialized view
2. Recreate sector organizing views
3. BLS private sector alignment check

Usage:
    py scripts/cleanup/post_merge_refresh.py
"""
import psycopg2
import subprocess
import sys
import os
import time

from db_config import get_connection
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLS_PRIVATE_BENCHMARK = 7_200_000


def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    print("=" * 70)
    print("POST-MERGE REFRESH")
    print("=" * 70)

    # =========================================================================
    # Step 1: Refresh mv_employer_search
    # =========================================================================
    print("\nStep 1: Refreshing mv_employer_search materialized view...")
    t0 = time.time()

    try:
        # Check if MV exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_employer_search'
            )
        """)
        mv_exists = cur.fetchone()[0]

        if mv_exists:
            cur.execute("REFRESH MATERIALIZED VIEW mv_employer_search")
            elapsed = time.time() - t0
            cur.execute("SELECT COUNT(*) FROM mv_employer_search")
            mv_count = cur.fetchone()[0]
            print("  Refreshed: %d rows (%.1fs)" % (mv_count, elapsed))
        else:
            print("  WARNING: mv_employer_search does not exist!")
            print("  Run: py scripts/etl/setup_unified_search.py")
    except Exception as e:
        print("  ERROR refreshing MV: %s" % str(e))

    # =========================================================================
    # Step 2: Recreate sector views
    # =========================================================================
    print("\nStep 2: Refreshing sector organizing views...")
    t0 = time.time()

    sector_script = os.path.join(BASE_DIR, 'scripts', 'scoring', 'create_sector_views.py')
    try:
        result = subprocess.run(
            [sys.executable, sector_script],
            capture_output=True, text=True, timeout=120,
            cwd=BASE_DIR
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            # Count lines that mention sector creation
            lines = result.stdout.strip().split('\n')
            sector_lines = [l for l in lines if '[' in l and ']' in l]
            print("  Sector views recreated: %d sectors (%.1fs)" % (len(sector_lines), elapsed))
        else:
            print("  ERROR: sector view creation failed")
            print("  stderr: %s" % result.stderr[:200])
    except FileNotFoundError:
        print("  WARNING: %s not found" % sector_script)
    except Exception as e:
        print("  ERROR: %s" % str(e))

    # =========================================================================
    # Step 3: BLS alignment check
    # =========================================================================
    print("\nStep 3: BLS private sector alignment check...")

    cur.execute("""
        SELECT
            COUNT(*) as total_employers,
            SUM(latest_unit_size) as total_workers_raw,
            SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
            SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END) as excluded_workers,
            COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_count
        FROM f7_employers_deduped
    """)
    row = cur.fetchone()
    total_employers = row[0]
    total_raw = row[1] or 0
    counted = row[2] or 0
    excluded_workers = row[3] or 0
    excluded_count = row[4]

    pct = counted / BLS_PRIVATE_BENCHMARK * 100

    print("  Total employers:     %d" % total_employers)
    print("  Total workers (raw): %s" % format(total_raw, ','))
    print("  Counted workers:     %s" % format(counted, ','))
    print("  Excluded workers:    %s (%d records)" % (format(excluded_workers, ','), excluded_count))
    print()
    print("  BLS Benchmark:       %s" % format(BLS_PRIVATE_BENCHMARK, ','))
    print("  Coverage:            %.1f%%" % pct)

    if 90 <= pct <= 110:
        print("  Status: PASS (within 90-110%%)")
    elif 85 <= pct <= 115:
        print("  Status: WARNING (%.1f%% - close to bounds)" % pct)
    else:
        print("  Status: FAIL (%.1f%% - outside 90-110%%)" % pct)

    # Exclusion breakdown
    print("\n  Exclusion breakdown:")
    cur.execute("""
        SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
               COUNT(*) as employers,
               SUM(latest_unit_size) as workers
        FROM f7_employers_deduped
        GROUP BY exclude_reason
        ORDER BY SUM(latest_unit_size) DESC
    """)
    for row in cur.fetchall():
        reason = row[0]
        emp_count = row[1]
        workers = row[2] or 0
        print("    %-30s | %6d employers | %12s workers" % (reason, emp_count, format(workers, ',')))

    # =========================================================================
    # Step 4: Crosswalk orphan check
    # =========================================================================
    print("\nStep 4: Crosswalk orphan check...")

    try:
        cur.execute("""
            SELECT COUNT(*) as orphans
            FROM corporate_identifier_crosswalk c
            WHERE c.f7_employer_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM f7_employers_deduped f
                  WHERE f.employer_id = c.f7_employer_id
              )
        """)
        orphan_count = cur.fetchone()[0]

        if orphan_count == 0:
            print("  PASS: No orphan crosswalk rows (all f7_employer_ids are valid)")
        else:
            print("  WARNING: %d crosswalk rows reference non-existent F7 employers" % orphan_count)
            # Show examples
            cur.execute("""
                SELECT c.f7_employer_id, c.gleif_lei, c.mergent_duns
                FROM corporate_identifier_crosswalk c
                WHERE c.f7_employer_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_employers_deduped f
                      WHERE f.employer_id = c.f7_employer_id
                  )
                LIMIT 5
            """)
            examples = cur.fetchall()
            for ex in examples:
                print("    f7_id=%s lei=%s duns=%s" % (ex[0], ex[1], ex[2]))

            # Auto-fix: check merge log for where these should point
            print("  Attempting auto-fix via merge log...")
            cur.execute("""
                UPDATE corporate_identifier_crosswalk c
                SET f7_employer_id = ml.kept_id
                FROM f7_employer_merge_log ml
                WHERE c.f7_employer_id = ml.deleted_id
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_employers_deduped f
                      WHERE f.employer_id = c.f7_employer_id
                  )
            """)
            fixed = cur.rowcount
            if fixed > 0:
                print("  Fixed %d orphan crosswalk rows via merge log" % fixed)

            # Check remaining orphans
            cur.execute("""
                SELECT COUNT(*) as remaining
                FROM corporate_identifier_crosswalk c
                WHERE c.f7_employer_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_employers_deduped f
                      WHERE f.employer_id = c.f7_employer_id
                  )
            """)
            remaining = cur.fetchone()[0]
            if remaining > 0:
                print("  WARNING: %d orphan crosswalk rows remain (no merge log entry found)" % remaining)
            else:
                print("  All orphan crosswalk rows resolved")

    except Exception as e:
        print("  ERROR checking crosswalk: %s" % str(e))

    # =========================================================================
    # Step 5: Merge log summary
    # =========================================================================
    print("\n" + "-" * 70)
    print("Merge log summary:")
    try:
        cur.execute("""
            SELECT COUNT(*) as total_merges,
                   SUM(f7_relations_updated) as f7_rel,
                   SUM(vr_records_updated) as vr,
                   SUM(nlrb_participants_updated) as nlrb,
                   SUM(osha_matches_updated) as osha_upd,
                   SUM(osha_conflicts_deleted) as osha_del,
                   SUM(mergent_updated) as mergent,
                   SUM(COALESCE(crosswalk_updated, 0)) as crosswalk
            FROM f7_employer_merge_log
        """)
        log = cur.fetchone()
        if log and log[0]:
            print("  Total merges executed: %d" % log[0])
            print("  Downstream updates:")
            print("    f7_relations:       %d" % (log[1] or 0))
            print("    vr_records:         %d" % (log[2] or 0))
            print("    nlrb_participants:  %d" % (log[3] or 0))
            print("    osha_updated:       %d" % (log[4] or 0))
            print("    osha_conflicts:     %d (deleted)" % (log[5] or 0))
            print("    mergent:            %d" % (log[6] or 0))
            print("    crosswalk:          %d" % (log[7] or 0))
        else:
            print("  No merges logged yet.")
    except Exception:
        print("  Merge log table not found (run merges first).")

    print("\n" + "=" * 70)
    print("POST-MERGE REFRESH COMPLETE")
    print("=" * 70)

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
