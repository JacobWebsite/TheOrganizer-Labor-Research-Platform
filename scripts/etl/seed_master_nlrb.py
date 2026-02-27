#!/usr/bin/env python3
"""
Seed master_employers from unmatched NLRB employer participants.

These are employers that appear in NLRB proceedings (elections, ULP cases)
but were never matched to an F7 employer. They represent non-union employers
that had organizing attempts -- extremely valuable targeting signal.

Three-step pattern:
  1. Bridge: Link matched NLRB participants to existing masters via F7 source_ids
  2. Name+State: Match remaining NLRB employers to existing masters by name + state
  3. Insert: Create new master rows for truly unmatched NLRB employers

Usage:
  python scripts/etl/seed_master_nlrb.py
  python scripts/etl/seed_master_nlrb.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection


def run_sql(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.rowcount if cur.rowcount is not None else 0


def seed_nlrb(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Bridge: Link already-matched NLRB participants to masters via F7 source_ids.
    #    matched_employer_id in nlrb_participants points to F7 employer_id (TEXT).
    stats["nlrb_source_ids_from_f7_bridge"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT
            f7sid.master_id,
            'nlrb',
            p.case_number,
            LEAST(1.0, COALESCE(p.match_confidence, 0.90)),
            NOW()
        FROM nlrb_participants p
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = p.matched_employer_id::TEXT
        WHERE p.matched_employer_id IS NOT NULL
          AND p.participant_type IN ('Employer', 'Charged Party / Respondent')
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'nlrb'
                AND sid.source_id = p.case_number
                AND sid.master_id = f7sid.master_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 2) Name+State: Match unmatched NLRB employer participants to existing masters.
    #    Only process Employer and Charged Party types (skip unions, individuals).
    stats["nlrb_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (p.case_number, p.participant_name)
            m.master_id,
            'nlrb',
            p.case_number,
            0.85,
            NOW()
        FROM nlrb_participants p
        JOIN master_employers m
          ON m.canonical_name = COALESCE(
              NULLIF(
                  trim(regexp_replace(lower(COALESCE(p.participant_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                  ''
              ),
              'unknown_nlrb'
          )
         AND COALESCE(m.state, '') = COALESCE(p.state, '')
        WHERE p.matched_employer_id IS NULL
          AND p.participant_type IN ('Employer', 'Charged Party / Respondent')
          AND p.participant_name IS NOT NULL
          AND length(trim(p.participant_name)) > 3
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'nlrb'
                AND sid.source_id = p.case_number
                AND sid.master_id = m.master_id
          )
        ORDER BY p.case_number, p.participant_name, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 3) Insert: Create new master rows for truly unmatched NLRB employers.
    #    Deduplicate by participant_name + state before inserting.
    stats["nlrb_new_master_rows"] = run_sql(
        cur,
        """
        WITH nlrb_candidates AS (
            SELECT DISTINCT ON (canonical_name, COALESCE(state, ''))
                p.case_number,
                COALESCE(
                    NULLIF(
                        trim(regexp_replace(lower(COALESCE(p.participant_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                        ''
                    ),
                    'unknown_nlrb_' || p.case_number
                ) AS canonical_name,
                p.participant_name AS display_name,
                p.city,
                p.state,
                p.zip AS zip
            FROM nlrb_participants p
            WHERE p.matched_employer_id IS NULL
              AND p.participant_type IN ('Employer', 'Charged Party / Respondent')
              AND p.participant_name IS NOT NULL
              AND length(trim(p.participant_name)) > 3
              AND NOT EXISTS (
                  SELECT 1
                  FROM master_employer_source_ids sid
                  WHERE sid.source_system = 'nlrb'
                    AND sid.source_id = p.case_number
              )
            ORDER BY
                canonical_name,
                COALESCE(state, ''),
                p.case_number
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            nc.canonical_name,
            nc.display_name,
            nc.city,
            nc.state,
            nc.zip,
            NULL,
            NULL,
            NULL,
            NULL,
            FALSE,
            FALSE,
            FALSE,
            FALSE,
            'nlrb',
            45.00
        FROM nlrb_candidates nc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.canonical_name = nc.canonical_name
              AND COALESCE(m.state, '') = COALESCE(nc.state, '')
              AND COALESCE(m.city, '') = COALESCE(nc.city, '')
        )
        """
    )

    # 4) Backfill source IDs for newly created NLRB-origin masters.
    #    Link all case_numbers for this employer to the new master.
    stats["nlrb_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'nlrb',
            p.case_number,
            0.70,
            NOW()
        FROM nlrb_participants p
        JOIN master_employers m
          ON m.source_origin = 'nlrb'
         AND m.display_name = p.participant_name
         AND COALESCE(m.state, '') = COALESCE(p.state, '')
         AND COALESCE(m.city, '') = COALESCE(p.city, '')
        WHERE p.matched_employer_id IS NULL
          AND p.participant_type IN ('Employer', 'Charged Party / Respondent')
          AND p.participant_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'nlrb'
                AND sid.source_id = p.case_number
                AND sid.master_id = m.master_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    return stats


def print_stats(stats: Dict[str, int]) -> None:
    print("[nlrb]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    total_links = sum(v for k, v in stats.items() if 'source_ids' in k)
    total_new = stats.get('nlrb_new_master_rows', 0)
    print(f"  --- Total source links: {total_links:,}")
    print(f"  --- Total new masters: {total_new:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed master_employers from NLRB participants")
    parser.add_argument("--dry-run", action="store_true", help="Rollback at end")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print_stats(seed_nlrb(cur))

        if args.dry_run:
            conn.rollback()
            print("\nDry run complete. Transaction rolled back.")
        else:
            conn.commit()
            print("\nSeeding complete. Transaction committed.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
