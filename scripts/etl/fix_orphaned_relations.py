"""
Fix 60,373 orphaned f7_union_employer_relations rows (50.4% of all relations).

ROOT CAUSE: f7_employers_deduped was built with WHERE latest_notice_date >= '2020-01-01',
but f7_union_employer_relations has data back to 2010. The 56,291 orphaned employer_ids
all exist in raw f7_employers but were excluded from the deduped table by the date filter.

FIX STRATEGY (3 tiers):
  Tier 1: Repoint 2,710 orphans with exact name+state match in deduped
          (same employer, different filing year -> consolidate)
  Tier 2: Try normalized name matching (UPPER TRIM aggressive) for more matches
  Tier 3: INSERT remaining unmatched employers from raw f7_employers into
          f7_employers_deduped, preserving all historical relationships

After fix: orphan count should be 0. All union-employer relations resolvable via JOIN.

SAFETY:
  - DRY_RUN mode by default (set DRY_RUN=False to execute)
  - All changes in a single transaction (ROLLBACK on error)
  - Detailed statistics before and after
  - Handles duplicate relations (same employer+union after repointing)

USAGE:
  py scripts/etl/fix_orphaned_relations.py              # dry run (analysis only)
  py scripts/etl/fix_orphaned_relations.py --execute     # actually fix the data
  py scripts/etl/fix_orphaned_relations.py --tier1-only  # only repoint exact matches

REVIEW CHECKPOINT: Send this script to Codex and Gemini for review before --execute.
"""

import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def get_baseline(cur):
    """Get current orphan statistics."""
    stats = {}

    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    stats['total_relations'] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    stats['deduped_employers'] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM f7_employers")
    stats['raw_employers'] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    stats['orphaned_relations'] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT r.employer_id) FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    stats['orphaned_employer_ids'] = cur.fetchone()[0]

    cur.execute("""
        SELECT COALESCE(SUM(r.bargaining_unit_size), 0) FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    stats['orphaned_workers'] = cur.fetchone()[0]

    return stats


def print_stats(label, stats):
    """Print statistics block."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  Total relations:        {stats['total_relations']:>10,}")
    print(f"  Deduped employers:      {stats['deduped_employers']:>10,}")
    print(f"  Raw employers:          {stats['raw_employers']:>10,}")
    print(f"  Orphaned relations:     {stats['orphaned_relations']:>10,}  ({100*stats['orphaned_relations']/stats['total_relations']:.1f}%)")
    print(f"  Orphaned employer IDs:  {stats['orphaned_employer_ids']:>10,}")
    print(f"  Orphaned workers:       {stats['orphaned_workers']:>10,}")


# ============================================================================
# TIER 1: Repoint exact name+state matches
# ============================================================================
def tier1_exact_match(cur, dry_run=True):
    """
    Find orphaned employer_ids where the same employer_name + state exists
    in f7_employers_deduped (just a different filing year). Repoint relations
    to the deduped version.

    Handles 1:N matches by picking the deduped employer with the most recent
    notice date (most active version).
    """
    print("\n" + "#"*70)
    print("# TIER 1: Exact name+state repoint")
    print("#"*70)

    # Find all orphaned IDs with an exact name+state match in deduped
    # Use ROW_NUMBER to pick best match when multiple deduped employers share name+state
    cur.execute("""
        WITH orphan_employers AS (
            SELECT DISTINCT r.employer_id
            FROM f7_union_employer_relations r
            LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
            WHERE d.employer_id IS NULL
        ),
        matches AS (
            SELECT
                o.employer_id AS old_id,
                d.employer_id AS new_id,
                fe.employer_name AS old_name,
                d.employer_name AS new_name,
                fe.state,
                ROW_NUMBER() OVER (
                    PARTITION BY o.employer_id
                    ORDER BY d.latest_notice_date DESC NULLS LAST, d.filing_count DESC NULLS LAST
                ) AS rn
            FROM orphan_employers o
            JOIN f7_employers fe ON o.employer_id = fe.employer_id
            JOIN f7_employers_deduped d
                ON UPPER(TRIM(fe.employer_name)) = UPPER(TRIM(d.employer_name))
                AND UPPER(TRIM(COALESCE(fe.state, ''))) = UPPER(TRIM(COALESCE(d.state, '')))
            WHERE fe.employer_id != d.employer_id
        )
        SELECT old_id, new_id, old_name, new_name, state
        FROM matches
        WHERE rn = 1
    """)
    matches = cur.fetchall()
    print(f"  Found {len(matches):,} orphaned employer_ids with exact name+state match")

    if not matches:
        return 0, 0

    # Show sample matches
    print(f"\n  Sample matches (first 10):")
    print(f"  {'Old ID':<18} {'New ID':<18} {'Name':<45} {'State'}")
    print(f"  {'-'*18} {'-'*18} {'-'*45} {'-'*5}")
    for old_id, new_id, old_name, new_name, state in matches[:10]:
        print(f"  {old_id:<18} {new_id:<18} {(old_name or '')[:45]:<45} {state or ''}")

    # Count how many relations will be affected
    old_ids = [m[0] for m in matches]
    cur.execute("""
        SELECT COUNT(*) FROM f7_union_employer_relations
        WHERE employer_id = ANY(%s)
    """, (old_ids,))
    affected_relations = cur.fetchone()[0]
    print(f"\n  Relations to repoint: {affected_relations:,}")

    if dry_run:
        print("  [DRY RUN] No changes made.")
        return len(matches), affected_relations

    # Execute repointing
    # Use a temp table for bulk UPDATE (faster than individual UPDATEs)
    cur.execute("""
        CREATE TEMP TABLE tier1_mapping (
            old_id TEXT PRIMARY KEY,
            new_id TEXT NOT NULL
        )
    """)
    from psycopg2.extras import execute_values
    execute_values(cur,
        "INSERT INTO tier1_mapping (old_id, new_id) VALUES %s",
        [(m[0], m[1]) for m in matches],
        page_size=1000
    )

    # Before repointing, check for duplicate relations that would result
    # (same new_id + union_file_number + notice_date already exists)
    cur.execute("""
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        JOIN tier1_mapping m ON r.employer_id = m.old_id
        WHERE EXISTS (
            SELECT 1 FROM f7_union_employer_relations existing
            WHERE existing.employer_id = m.new_id
              AND existing.union_file_number = r.union_file_number
              AND existing.notice_date = r.notice_date
        )
    """)
    dup_count = cur.fetchone()[0]
    print(f"  Duplicate relations after repoint (will be removed): {dup_count:,}")

    # Delete the duplicates first (keep the existing one in deduped)
    cur.execute("""
        DELETE FROM f7_union_employer_relations r
        USING tier1_mapping m
        WHERE r.employer_id = m.old_id
          AND EXISTS (
              SELECT 1 FROM f7_union_employer_relations existing
              WHERE existing.employer_id = m.new_id
                AND existing.union_file_number = r.union_file_number
                AND existing.notice_date = r.notice_date
          )
    """)
    deleted_dups = cur.rowcount
    print(f"  Deleted {deleted_dups:,} duplicate relation rows")

    # Now repoint the remaining
    cur.execute("""
        UPDATE f7_union_employer_relations r
        SET employer_id = m.new_id
        FROM tier1_mapping m
        WHERE r.employer_id = m.old_id
    """)
    repointed = cur.rowcount
    print(f"  Repointed {repointed:,} relation rows to deduped employer_ids")

    cur.execute("DROP TABLE IF EXISTS tier1_mapping")
    return len(matches), repointed + deleted_dups


# ============================================================================
# TIER 2: Normalized name matching (employer_name_aggressive + state)
# ============================================================================
def tier2_normalized_match(cur, dry_run=True):
    """
    For remaining orphans, try matching via normalized names.
    f7_employers_deduped has employer_name_aggressive (uppercase, stripped suffixes).
    Raw f7_employers only has employer_name. Normalize inline for matching.
    """
    print("\n" + "#"*70)
    print("# TIER 2: Normalized name+state repoint")
    print("#"*70)

    # Build normalized versions of orphaned employer names and match
    # against employer_name_aggressive in deduped table
    cur.execute("""
        WITH orphan_employers AS (
            SELECT DISTINCT r.employer_id
            FROM f7_union_employer_relations r
            LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
            WHERE d.employer_id IS NULL
        ),
        matches AS (
            SELECT
                o.employer_id AS old_id,
                d.employer_id AS new_id,
                fe.employer_name AS old_name,
                d.employer_name AS new_name,
                fe.state,
                ROW_NUMBER() OVER (
                    PARTITION BY o.employer_id
                    ORDER BY d.latest_notice_date DESC NULLS LAST, d.filing_count DESC NULLS LAST
                ) AS rn
            FROM orphan_employers o
            JOIN f7_employers fe ON o.employer_id = fe.employer_id
            JOIN f7_employers_deduped d
                ON UPPER(TRIM(REGEXP_REPLACE(fe.employer_name, '\\s+', ' ', 'g')))
                   = UPPER(TRIM(d.employer_name_aggressive))
                AND UPPER(TRIM(COALESCE(fe.state, ''))) = UPPER(TRIM(COALESCE(d.state, '')))
            WHERE fe.employer_id != d.employer_id
              -- Exclude any already matched by Tier 1
              AND NOT EXISTS (
                  SELECT 1 FROM f7_employers_deduped d2
                  WHERE UPPER(TRIM(fe.employer_name)) = UPPER(TRIM(d2.employer_name))
                    AND UPPER(TRIM(COALESCE(fe.state, ''))) = UPPER(TRIM(COALESCE(d2.state, '')))
                    AND d2.employer_id != fe.employer_id
              )
        )
        SELECT old_id, new_id, old_name, new_name, state
        FROM matches
        WHERE rn = 1
    """)
    matches = cur.fetchall()
    print(f"  Found {len(matches):,} additional orphans with normalized name+state match")

    if not matches:
        return 0, 0

    # Show sample
    print(f"\n  Sample matches (first 10):")
    print(f"  {'Old Name':<40} -> {'New Name':<40} {'State'}")
    print(f"  {'-'*40}    {'-'*40} {'-'*5}")
    for old_id, new_id, old_name, new_name, state in matches[:10]:
        print(f"  {(old_name or '')[:40]:<40} -> {(new_name or '')[:40]:<40} {state or ''}")

    old_ids = [m[0] for m in matches]
    cur.execute("""
        SELECT COUNT(*) FROM f7_union_employer_relations
        WHERE employer_id = ANY(%s)
    """, (old_ids,))
    affected_relations = cur.fetchone()[0]
    print(f"\n  Relations to repoint: {affected_relations:,}")

    if dry_run:
        print("  [DRY RUN] No changes made.")
        return len(matches), affected_relations

    # Same pattern as Tier 1
    cur.execute("""
        CREATE TEMP TABLE tier2_mapping (
            old_id TEXT PRIMARY KEY,
            new_id TEXT NOT NULL
        )
    """)
    from psycopg2.extras import execute_values
    execute_values(cur,
        "INSERT INTO tier2_mapping (old_id, new_id) VALUES %s",
        [(m[0], m[1]) for m in matches],
        page_size=1000
    )

    # Remove duplicates
    cur.execute("""
        DELETE FROM f7_union_employer_relations r
        USING tier2_mapping m
        WHERE r.employer_id = m.old_id
          AND EXISTS (
              SELECT 1 FROM f7_union_employer_relations existing
              WHERE existing.employer_id = m.new_id
                AND existing.union_file_number = r.union_file_number
                AND existing.notice_date = r.notice_date
          )
    """)
    deleted_dups = cur.rowcount
    print(f"  Deleted {deleted_dups:,} duplicate relation rows")

    # Repoint
    cur.execute("""
        UPDATE f7_union_employer_relations r
        SET employer_id = m.new_id
        FROM tier2_mapping m
        WHERE r.employer_id = m.old_id
    """)
    repointed = cur.rowcount
    print(f"  Repointed {repointed:,} relation rows")

    cur.execute("DROP TABLE IF EXISTS tier2_mapping")
    return len(matches), repointed + deleted_dups


# ============================================================================
# TIER 3: Insert remaining unmatched employers into deduped table
# ============================================================================
def tier3_insert_historical(cur, dry_run=True):
    """
    For orphaned employer_ids that have NO match in deduped (truly historical
    employers with no post-2020 filing), INSERT them into f7_employers_deduped
    from the raw f7_employers table.

    These get all base columns from f7_employers. Enrichment columns
    (naics_detailed, WHD data, CBSA, etc.) are left NULL -- they can be
    populated later by re-running enrichment pipelines if needed.
    """
    print("\n" + "#"*70)
    print("# TIER 3: Insert unmatched historical employers into deduped table")
    print("#"*70)

    # Count remaining orphans
    cur.execute("""
        SELECT COUNT(DISTINCT r.employer_id)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    remaining_orphan_ids = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        WHERE d.employer_id IS NULL
    """)
    remaining_orphan_rows = cur.fetchone()[0]
    print(f"  Remaining orphaned employer IDs: {remaining_orphan_ids:,}")
    print(f"  Remaining orphaned relation rows: {remaining_orphan_rows:,}")

    if remaining_orphan_ids == 0:
        print("  No remaining orphans -- nothing to insert.")
        return 0

    # Verify all remaining orphans exist in raw f7_employers
    cur.execute("""
        SELECT COUNT(DISTINCT r.employer_id)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        LEFT JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL AND fe.employer_id IS NULL
    """)
    phantom = cur.fetchone()[0]
    if phantom > 0:
        print(f"  WARNING: {phantom:,} orphaned IDs not found in raw f7_employers either!")
        print(f"  These cannot be fixed. They will remain orphaned.")

    # Show date distribution of historical employers to insert
    cur.execute("""
        SELECT
            EXTRACT(YEAR FROM fe.latest_notice_date::date) AS year,
            COUNT(DISTINCT fe.employer_id) AS employers
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL
        GROUP BY 1
        ORDER BY 1
    """)
    year_dist = cur.fetchall()
    print(f"\n  Year distribution of historical employers to insert:")
    for year, count in year_dist:
        yr = int(year) if year else 'NULL'
        print(f"    {yr}: {count:,}")

    # Show state distribution (top 10)
    cur.execute("""
        SELECT fe.state, COUNT(DISTINCT fe.employer_id) AS employers
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
        JOIN f7_employers fe ON r.employer_id = fe.employer_id
        WHERE d.employer_id IS NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
    """)
    state_dist = cur.fetchall()
    print(f"\n  Top 10 states of historical employers:")
    for state, count in state_dist:
        print(f"    {state or 'NULL'}: {count:,}")

    if dry_run:
        print(f"\n  [DRY RUN] Would insert {remaining_orphan_ids:,} employers into f7_employers_deduped.")
        print("  Columns from raw f7_employers: employer_id, employer_name, city, state,")
        print("    street, zip, latest_notice_date, latest_unit_size, latest_union_fnum,")
        print("    latest_union_name, naics, healthcare_related, filing_count,")
        print("    potentially_defunct, latitude, longitude, geocode_status, data_quality_flag")
        print("  Enrichment columns (employer_name_aggressive, naics_detailed, WHD, CBSA, etc.) = NULL")
        return remaining_orphan_ids

    # Insert historical employers
    # Only insert columns that exist in the raw table. All enrichment columns
    # added during later phases will default to NULL.
    cur.execute("""
        INSERT INTO f7_employers_deduped (
            employer_id, employer_name, city, state, street, zip,
            latest_notice_date, latest_unit_size, latest_union_fnum,
            latest_union_name, naics, healthcare_related, filing_count,
            potentially_defunct, latitude, longitude, geocode_status,
            data_quality_flag
        )
        SELECT
            fe.employer_id, fe.employer_name, fe.city, fe.state, fe.street, fe.zip,
            fe.latest_notice_date, fe.latest_unit_size, fe.latest_union_fnum,
            fe.latest_union_name, fe.naics, fe.healthcare_related, fe.filing_count,
            fe.potentially_defunct, fe.latitude, fe.longitude, fe.geocode_status,
            fe.data_quality_flag
        FROM f7_employers fe
        WHERE fe.employer_id IN (
            SELECT DISTINCT r.employer_id
            FROM f7_union_employer_relations r
            LEFT JOIN f7_employers_deduped d ON r.employer_id = d.employer_id
            WHERE d.employer_id IS NULL
        )
        AND NOT EXISTS (
            SELECT 1 FROM f7_employers_deduped d WHERE d.employer_id = fe.employer_id
        )
    """)
    inserted = cur.rowcount
    print(f"  Inserted {inserted:,} historical employers into f7_employers_deduped")

    # Generate employer_name_aggressive for inserted rows (UPPER, strip suffixes)
    cur.execute("""
        UPDATE f7_employers_deduped
        SET employer_name_aggressive = UPPER(TRIM(
            REGEXP_REPLACE(
                REGEXP_REPLACE(employer_name,
                    '\\s*(INC\\.?|LLC|CORP\\.?|CO\\.?|LTD\\.?|LP|LLP|PLLC|PC|PA|NA|FSB|ASSN\\.?)\\s*$',
                    '', 'gi'),
                '\\s+', ' ', 'g')
        ))
        WHERE employer_name_aggressive IS NULL
          AND employer_name IS NOT NULL
    """)
    normalized = cur.rowcount
    print(f"  Generated employer_name_aggressive for {normalized:,} rows")

    return inserted


# ============================================================================
# POST-FIX: Refresh downstream
# ============================================================================
def refresh_views(cur):
    """Refresh materialized views that depend on f7_employers_deduped or relations."""
    print("\n" + "#"*70)
    print("# Refreshing materialized views")
    print("#"*70)

    # Find all materialized views
    cur.execute("""
        SELECT schemaname, matviewname
        FROM pg_matviews
        WHERE schemaname = 'public'
        ORDER BY matviewname
    """)
    views = cur.fetchall()
    print(f"  Found {len(views)} materialized views")

    refreshed = 0
    failed = 0
    for schema, name in views:
        try:
            cur.execute(f"REFRESH MATERIALIZED VIEW {name}")
            refreshed += 1
            print(f"    Refreshed: {name}")
        except Exception as e:
            # Some views may have dependencies or errors -- don't block
            cur.execute("ROLLBACK TO SAVEPOINT mv_refresh")
            failed += 1
            print(f"    FAILED: {name} -- {str(e)[:80]}")
        # Set savepoint before each attempt
        try:
            cur.execute("SAVEPOINT mv_refresh")
        except Exception:
            pass

    print(f"  Refreshed {refreshed}/{len(views)} views ({failed} failed)")


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description='Fix orphaned f7_union_employer_relations')
    parser.add_argument('--execute', action='store_true',
                        help='Actually execute changes (default: dry run)')
    parser.add_argument('--tier1-only', action='store_true',
                        help='Only run Tier 1 (exact name+state repoint)')
    parser.add_argument('--skip-tier3', action='store_true',
                        help='Skip Tier 3 (do not insert historical employers)')
    parser.add_argument('--skip-refresh', action='store_true',
                        help='Skip materialized view refresh')
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        print("=" * 70)
        print("  DRY RUN MODE -- No changes will be made")
        print("  Run with --execute to apply changes")
        print("=" * 70)
    else:
        print("=" * 70)
        print("  EXECUTE MODE -- Changes will be committed")
        print("=" * 70)

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Baseline
        before = get_baseline(cur)
        print_stats("BEFORE", before)

        # Tier 1
        t1_ids, t1_relations = tier1_exact_match(cur, dry_run=dry_run)

        # Tier 2
        if not args.tier1_only:
            t2_ids, t2_relations = tier2_normalized_match(cur, dry_run=dry_run)
        else:
            t2_ids, t2_relations = 0, 0

        # Tier 3
        if not args.tier1_only and not args.skip_tier3:
            t3_inserted = tier3_insert_historical(cur, dry_run=dry_run)
        else:
            t3_inserted = 0

        # After stats (even in dry run, shows projected state)
        if not dry_run:
            after = get_baseline(cur)
            print_stats("AFTER", after)

            # Refresh materialized views
            if not args.skip_refresh:
                cur.execute("SAVEPOINT mv_refresh")
                refresh_views(cur)

            # Commit
            print("\n  Committing changes...")
            conn.commit()
            print("  COMMITTED.")

            # Final verification
            final = get_baseline(cur)
            print_stats("FINAL VERIFICATION", final)
        else:
            # Project what would happen
            print("\n" + "#"*70)
            print("# PROJECTED RESULTS (dry run)")
            print("#"*70)
            projected_repoints = t1_relations + t2_relations
            print(f"  Tier 1 (exact name+state): {t1_ids:,} employers, {t1_relations:,} relations")
            print(f"  Tier 2 (normalized name):  {t2_ids:,} employers, {t2_relations:,} relations")
            print(f"  Tier 3 (insert historical): {t3_inserted:,} employers inserted")
            remaining = before['orphaned_employer_ids'] - t1_ids - t2_ids - t3_inserted
            print(f"\n  Projected remaining orphans: {max(0, remaining):,}")
            if remaining <= 0:
                print("  All orphans would be resolved!")

        # Summary
        print("\n" + "="*70)
        print("  SUMMARY")
        print("="*70)
        print(f"  Tier 1 repoints:   {t1_ids:,} employer IDs, {t1_relations:,} relations")
        print(f"  Tier 2 repoints:   {t2_ids:,} employer IDs, {t2_relations:,} relations")
        print(f"  Tier 3 inserts:    {t3_inserted:,} historical employers added to deduped table")
        if not dry_run:
            print(f"\n  Orphan rate:  {before['orphaned_relations']:,} -> {final['orphaned_relations']:,}")
            print(f"  Employer count: {before['deduped_employers']:,} -> {final['deduped_employers']:,}")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        if not dry_run:
            print("  Rolling back all changes...")
            conn.rollback()
            print("  ROLLED BACK.")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
