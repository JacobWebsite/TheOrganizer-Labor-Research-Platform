#!/usr/bin/env python3
"""
Seed master_employers from EPA ECHO facilities.

24Q-21 Environmental signal. Mirrors the seed_master_osha pattern:
  1. ALTER chk_master_source_system to include 'epa_echo' if needed.
  2. Name+State match: link active ECHO facilities to existing masters by
     normalized name + state.
  3. Insert: create new master rows for truly unmatched active ECHO facilities
     with at least one inspection or formal action (filters out millions of
     dormant low-signal facilities).

ECHO has no EIN; the strongest available identifier is name + state + zip.
We don't load dormant inactive facilities into masters (they'd dilute the
target_scorecard); they remain in epa_echo_facilities for potential later use.

Usage:
    py scripts/etl/seed_master_epa_echo.py
    py scripts/etl/seed_master_epa_echo.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


def ensure_constraints_allow_epa_echo(cur) -> bool:
    """Add 'epa_echo' to BOTH chk_master_source_system AND chk_master_source_origin.
    Returns True when any change was applied."""
    changed = False

    # source_system on master_employer_source_ids
    cur.execute("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conname = 'chk_master_source_system'
    """)
    row = cur.fetchone()
    if not (row and "'epa_echo'" in row[0]):
        print("  Updating chk_master_source_system to include 'epa_echo'...")
        cur.execute("ALTER TABLE master_employer_source_ids DROP CONSTRAINT IF EXISTS chk_master_source_system")
        cur.execute("""
            ALTER TABLE master_employer_source_ids
            ADD CONSTRAINT chk_master_source_system
            CHECK (source_system = ANY (ARRAY[
                'f7','sam','mergent','osha','bmf','nlrb','sec','gleif',
                '990','manual','corpwatch','whd','ppp','form5500','epa_echo'
            ]))
        """)
        changed = True

    # source_origin on master_employers
    cur.execute("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conname = 'chk_master_source_origin'
    """)
    row = cur.fetchone()
    if not (row and "'epa_echo'" in row[0]):
        print("  Updating chk_master_source_origin to include 'epa_echo'...")
        cur.execute("ALTER TABLE master_employers DROP CONSTRAINT IF EXISTS chk_master_source_origin")
        cur.execute("""
            ALTER TABLE master_employers
            ADD CONSTRAINT chk_master_source_origin
            CHECK (source_origin = ANY (ARRAY[
                'f7','sam','mergent','osha','bmf','nlrb','sec','manual',
                'corpwatch','whd','ppp','form5500','990','gleif','epa_echo'
            ]))
        """)
        changed = True

    return changed


def run_sql(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.rowcount if cur.rowcount is not None else 0


def seed_epa_echo(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Name+State+Zip match: highest-precision link to existing masters.
    #    We restrict to active facilities to avoid bridging dormant ones.
    stats["epa_source_ids_name_state_zip"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (ef.registry_id)
            m.master_id,
            'epa_echo',
            ef.registry_id,
            0.92,
            NOW()
        FROM epa_echo_facilities ef
        JOIN master_employers m
          ON m.canonical_name = COALESCE(
              NULLIF(
                  trim(regexp_replace(lower(COALESCE(ef.fac_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                  ''
              ),
              'unknown_epa_' || ef.registry_id
          )
         AND COALESCE(m.state, '') = COALESCE(ef.fac_state, '')
         AND COALESCE(m.zip, '') = LEFT(COALESCE(ef.fac_zip, ''), 5)
        WHERE ef.fac_active_flag = 'Y'
          AND ef.fac_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'epa_echo' AND sid.source_id = ef.registry_id
          )
        ORDER BY ef.registry_id, m.data_quality_score DESC NULLS LAST
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    # 2) Name+State match (no zip required): catches mismatched zip but same
    #    employer in same state. Lower confidence.
    stats["epa_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (ef.registry_id)
            m.master_id,
            'epa_echo',
            ef.registry_id,
            0.85,
            NOW()
        FROM epa_echo_facilities ef
        JOIN master_employers m
          ON m.canonical_name = COALESCE(
              NULLIF(
                  trim(regexp_replace(lower(COALESCE(ef.fac_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                  ''
              ),
              'unknown_epa_' || ef.registry_id
          )
         AND COALESCE(m.state, '') = COALESCE(ef.fac_state, '')
        WHERE ef.fac_active_flag = 'Y'
          AND ef.fac_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'epa_echo' AND sid.source_id = ef.registry_id
          )
        ORDER BY ef.registry_id, m.data_quality_score DESC NULLS LAST
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    # 3) Insert new masters for ECHO facilities with REAL signal (inspections
    #    OR formal actions). Skips ~80% of ECHO that are dormant registry
    #    entries with no enforcement history.
    #
    # Codex review 2026-04-30: the candidate CTE must dedup BEFORE the INSERT
    # to prevent multiple master rows from being created for the same
    # (canonical_name, state, city). The 2026-04-30 first run created 1,924
    # such duplicates because step 3 didn't dedup within the batch.
    # See `Open Problems/EPA Master Duplicates from 2026-04-30 Seed.md`.
    stats["epa_new_master_rows"] = run_sql(
        cur,
        """
        WITH echo_raw AS (
            SELECT
                ef.registry_id,
                COALESCE(
                    NULLIF(
                        trim(regexp_replace(lower(ef.fac_name), '[^a-z0-9 ]', ' ', 'g')),
                        ''
                    ),
                    'unknown_epa_' || ef.registry_id
                ) AS canonical_name,
                ef.fac_name AS display_name,
                ef.fac_city AS city,
                ef.fac_state AS state,
                LEFT(ef.fac_zip, 5) AS zip,
                LEFT(ef.fac_naics_codes, 6) AS naics,
                ef.fac_inspection_count + ef.fac_formal_action_count AS signal_strength
            FROM epa_echo_facilities ef
            WHERE ef.fac_active_flag = 'Y'
              AND ef.fac_name IS NOT NULL
              AND ef.fac_state IS NOT NULL
              AND (ef.fac_inspection_count > 0 OR ef.fac_formal_action_count > 0)
              AND NOT EXISTS (
                  SELECT 1 FROM master_employer_source_ids sid
                  WHERE sid.source_system = 'epa_echo' AND sid.source_id = ef.registry_id
              )
        ),
        echo_candidates AS (
            -- Collapse to one row per (canonical_name, state, city); pick the
            -- registry with the strongest signal as the representative.
            SELECT DISTINCT ON (canonical_name, COALESCE(state, ''), COALESCE(city, ''))
                registry_id, canonical_name, display_name, city, state, zip, naics
            FROM echo_raw
            ORDER BY canonical_name, COALESCE(state, ''), COALESCE(city, ''),
                     signal_strength DESC, registry_id
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            ec.canonical_name,
            ec.display_name,
            ec.city,
            ec.state,
            ec.zip,
            ec.naics,
            NULL,
            NULL,
            NULL,
            FALSE, FALSE, FALSE, FALSE,
            'epa_echo',
            35.00
        FROM echo_candidates ec
        WHERE NOT EXISTS (
            SELECT 1 FROM master_employers m
            WHERE m.canonical_name = ec.canonical_name
              AND COALESCE(m.state, '') = COALESCE(ec.state, '')
              AND COALESCE(m.city, '') = COALESCE(ec.city, '')
        )
        """,
    )

    # 4) Backfill source_ids for newly created EPA-origin masters.
    #
    # Codex review 2026-04-30: original join was display_name + state + city,
    # which fans out one registry_id to every duplicate master with the same
    # display_name in the same place. Using DISTINCT ON to pick exactly one
    # master per registry_id (highest data_quality_score, then lowest master_id
    # for stability) prevents the multi-master fan-out.
    stats["epa_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (ef.registry_id)
            m.master_id,
            'epa_echo',
            ef.registry_id,
            0.70,
            NOW()
        FROM epa_echo_facilities ef
        JOIN master_employers m
          ON m.source_origin = 'epa_echo'
         AND m.display_name = ef.fac_name
         AND COALESCE(m.state, '') = COALESCE(ef.fac_state, '')
         AND COALESCE(m.city, '') = COALESCE(ef.fac_city, '')
        WHERE ef.fac_active_flag = 'Y'
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'epa_echo' AND sid.source_id = ef.registry_id
          )
        ORDER BY ef.registry_id, m.data_quality_score DESC NULLS LAST, m.master_id
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Roll back at end (preview counts only)")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Ensure constraints allow epa_echo. Constraint changes need autocommit.
        conn.autocommit = True
        if ensure_constraints_allow_epa_echo(cur):
            print("  Constraints updated.")
        conn.autocommit = False

        # Pre-counts
        cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'epa_echo'")
        before_links = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM master_employers")
        before_masters = cur.fetchone()[0]

        print("\nSeeding EPA ECHO into master_employers...")
        stats = seed_epa_echo(cur)

        for k, v in stats.items():
            print(f"  {k:<40s} {v:>10,}")

        cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'epa_echo'")
        after_links = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM master_employers")
        after_masters = cur.fetchone()[0]

        print()
        print(f"epa_echo source links: {before_links:,} -> {after_links:,} (+{after_links - before_links:,})")
        print(f"master_employers:      {before_masters:,} -> {after_masters:,} (+{after_masters - before_masters:,})")

        if args.dry_run:
            conn.rollback()
            print("\nDry-run complete (rolled back). Use without --dry-run to commit.")
        else:
            conn.commit()
            print("\nCommitted.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
