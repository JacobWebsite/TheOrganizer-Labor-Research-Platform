#!/usr/bin/env python3
"""
Clean up duplicate EPA ECHO origin masters created by the 2026-04-30 first
run of seed_master_epa_echo.py. The seed script is fixed for future runs
(see commit comments in scripts/etl/seed_master_epa_echo.py); this script
repairs the data left behind by the buggy first pass.

Open Problem reference:
  Open Problems/EPA Master Duplicates from 2026-04-30 Seed.md

Symptoms:
  - 1,924 (canonical_name, state, city) tuples have multiple master rows
    all with source_origin='epa_echo'
  - 4,384 EPA registry_ids are linked to multiple master_ids (some up to
    28 distinct masters per facility)

Approach:
  1) Identify dup groups: (canonical_name, COALESCE(state,''), COALESCE(city,''))
     where multiple masters exist AND every master in the group has
     source_origin='epa_echo' (we never touch non-epa origin rows).
  2) Pick keeper per group: highest data_quality_score, then lowest master_id
     for stability.
  3) Re-link master_employer_source_ids: move source_ids from losers ->
     keeper, ON CONFLICT DO NOTHING (drops the duplicates that are exactly
     why we're here).
  4) Verify each loser has source_origin='epa_echo' AND no non-epa source
     links remain attached AFTER the relink (defensive). Skip otherwise.
  5) DELETE the orphaned losers.
  6) Print before/after counts and verification queries.

What this script does NOT do:
  - It does NOT refresh MVs. Run scripts/scoring/refresh_all.py separately.
  - It does NOT change the seed script (already fixed).
  - It does NOT touch any non-epa-origin master rows.

Usage:
  py scripts/maintenance/cleanup_epa_echo_duplicates.py --dry-run
  py scripts/maintenance/cleanup_epa_echo_duplicates.py            # commits

Run time: ~30-60 seconds.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


def precounts(cur) -> Dict[str, int]:
    """Snapshot counts before doing any work, for the diff at the end."""
    out: Dict[str, int] = {}

    cur.execute("SELECT COUNT(*) FROM master_employers")
    out["masters_total"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM master_employers WHERE source_origin = 'epa_echo'")
    out["masters_epa_origin"] = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT canonical_name, COALESCE(state,''), COALESCE(city,''), COUNT(*) AS n
            FROM master_employers
            WHERE source_origin = 'epa_echo'
            GROUP BY 1, 2, 3
            HAVING COUNT(*) > 1
        ) t
        """
    )
    out["dup_groups"] = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT source_id, COUNT(DISTINCT master_id) AS n
            FROM master_employer_source_ids
            WHERE source_system = 'epa_echo'
            GROUP BY 1
            HAVING COUNT(DISTINCT master_id) > 1
        ) t
        """
    )
    out["over_linked_registry_ids"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'epa_echo'")
    out["epa_source_id_links"] = cur.fetchone()[0]

    return out


def stage_keepers(cur) -> int:
    """Build a temp table mapping every duplicate (canonical_name, state, city)
    group to its keeper master_id. Returns row count.

    We require ALL masters in a group to be source_origin='epa_echo' so we
    never accidentally collapse an epa-origin row into a non-epa one or
    vice versa.

    Tiebreak: highest data_quality_score, then lowest master_id.
    """
    cur.execute("DROP TABLE IF EXISTS tmp_epa_dedup_groups")
    cur.execute(
        """
        CREATE TEMP TABLE tmp_epa_dedup_groups AS
        WITH groups AS (
            SELECT
                canonical_name,
                COALESCE(state, '') AS state_key,
                COALESCE(city, '')  AS city_key,
                COUNT(*) AS n_masters,
                BOOL_AND(source_origin = 'epa_echo') AS all_epa_origin
            FROM master_employers
            GROUP BY canonical_name, COALESCE(state,''), COALESCE(city,'')
            HAVING COUNT(*) > 1
        ),
        ranked AS (
            SELECT
                m.master_id,
                m.canonical_name,
                COALESCE(m.state, '') AS state_key,
                COALESCE(m.city, '')  AS city_key,
                m.data_quality_score,
                ROW_NUMBER() OVER (
                    PARTITION BY m.canonical_name, COALESCE(m.state,''), COALESCE(m.city,'')
                    ORDER BY m.data_quality_score DESC NULLS LAST, m.master_id ASC
                ) AS rk
            FROM master_employers m
            JOIN groups g
              ON g.canonical_name = m.canonical_name
             AND g.state_key      = COALESCE(m.state,'')
             AND g.city_key       = COALESCE(m.city,'')
            WHERE g.all_epa_origin
        )
        SELECT
            r.master_id,
            r.canonical_name,
            r.state_key,
            r.city_key,
            (SELECT master_id FROM ranked r2
              WHERE r2.canonical_name = r.canonical_name
                AND r2.state_key      = r.state_key
                AND r2.city_key       = r.city_key
                AND r2.rk = 1) AS keeper_master_id,
            (r.rk = 1) AS is_keeper
        FROM ranked r
        """
    )
    cur.execute("CREATE INDEX ON tmp_epa_dedup_groups (master_id)")
    cur.execute("CREATE INDEX ON tmp_epa_dedup_groups (keeper_master_id)")
    cur.execute("SELECT COUNT(*) FROM tmp_epa_dedup_groups")
    n_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tmp_epa_dedup_groups WHERE NOT is_keeper")
    n_losers = cur.fetchone()[0]
    print(f"  staged {n_total:,} masters in dup groups ({n_losers:,} losers)")
    return n_losers


def relink_source_ids(cur) -> int:
    """Move every source_id link from a loser master to its group's keeper.

    Use INSERT ... ON CONFLICT DO NOTHING so over-linked registry_ids
    collapse cleanly. Then delete the loser-side links.
    """
    # Step A: insert keeper-side links (skip duplicates).
    cur.execute(
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            g.keeper_master_id,
            sid.source_system,
            sid.source_id,
            sid.match_confidence,
            sid.matched_at
        FROM master_employer_source_ids sid
        JOIN tmp_epa_dedup_groups g
          ON g.master_id = sid.master_id
         AND NOT g.is_keeper
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )
    n_relinked = cur.rowcount or 0
    print(f"  relinked {n_relinked:,} source_id rows to keepers")

    # Step B: delete the now-redundant loser-side links.
    cur.execute(
        """
        DELETE FROM master_employer_source_ids sid
        USING tmp_epa_dedup_groups g
        WHERE sid.master_id = g.master_id
          AND NOT g.is_keeper
        """
    )
    n_deleted_links = cur.rowcount or 0
    print(f"  deleted {n_deleted_links:,} source_id rows from losers")
    return n_relinked


def verify_loser_safety(cur) -> int:
    """Defensive: confirm every loser is now (a) source_origin='epa_echo'
    AND (b) has zero source_id links remaining. Returns number of losers
    that ARE safe to delete; the rest are skipped and reported."""
    cur.execute(
        """
        CREATE TEMP TABLE tmp_epa_dedup_losers_safe AS
        SELECT g.master_id
        FROM tmp_epa_dedup_groups g
        JOIN master_employers m ON m.master_id = g.master_id
        WHERE NOT g.is_keeper
          AND m.source_origin = 'epa_echo'
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.master_id = g.master_id
          )
        """
    )
    cur.execute("CREATE INDEX ON tmp_epa_dedup_losers_safe (master_id)")
    cur.execute("SELECT COUNT(*) FROM tmp_epa_dedup_losers_safe")
    n_safe = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(*) FROM tmp_epa_dedup_groups g
        WHERE NOT g.is_keeper
          AND NOT EXISTS (SELECT 1 FROM tmp_epa_dedup_losers_safe s WHERE s.master_id = g.master_id)
        """
    )
    n_unsafe = cur.fetchone()[0]
    print(f"  losers safe to delete: {n_safe:,}    unsafe (skipping): {n_unsafe:,}")
    return n_safe


def delete_losers(cur) -> int:
    cur.execute(
        """
        DELETE FROM master_employers m
        USING tmp_epa_dedup_losers_safe s
        WHERE m.master_id = s.master_id
        """
    )
    n = cur.rowcount or 0
    print(f"  deleted {n:,} loser master rows")
    return n


def postcounts(cur) -> Dict[str, int]:
    return precounts(cur)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roll back at end. Use this first to preview the diff.",
    )
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        print("Pre-cleanup state:")
        before = precounts(cur)
        for k, v in before.items():
            print(f"  {k:<28s} {v:>12,}")

        print("\nStaging keepers + losers...")
        n_losers = stage_keepers(cur)
        if n_losers == 0:
            print("\nNothing to clean up.")
            conn.rollback()
            return

        print("\nRelinking source_ids to keepers...")
        relink_source_ids(cur)

        print("\nVerifying losers are safe to delete...")
        verify_loser_safety(cur)

        print("\nDeleting safe losers...")
        delete_losers(cur)

        print("\nPost-cleanup state:")
        after = postcounts(cur)
        for k, v in after.items():
            delta = v - before.get(k, 0)
            sign = "+" if delta >= 0 else ""
            print(f"  {k:<28s} {v:>12,}   ({sign}{delta:,})")

        if args.dry_run:
            conn.rollback()
            print("\nDRY RUN -- rolled back. Re-run without --dry-run to commit.")
        else:
            conn.commit()
            print("\nCommitted.")
            print("\nNext: refresh mv_target_data_sources and mv_target_scorecard.")
            print("      e.g. py scripts/scoring/refresh_all.py --skip-gower")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
