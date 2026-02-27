#!/usr/bin/env python3
"""
Seed master_employers from WHD (Wage and Hour Division) cases.

Three-step pattern:
  1. Bridge: Link WHD cases to existing masters via whd_f7_matches -> F7 source_ids
  2. Name+State: Match remaining WHD cases to existing masters by normalized name + state
  3. Insert: Create new master rows for truly unmatched WHD cases

Usage:
  python scripts/etl/seed_master_whd.py
  python scripts/etl/seed_master_whd.py --dry-run
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


def seed_whd(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Bridge: Attach WHD case_ids to existing masters via whd_f7_matches -> F7 source_ids.
    stats["whd_source_ids_from_f7_bridge"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            f7sid.master_id,
            'whd',
            wfm.case_id,
            LEAST(1.0, COALESCE(wfm.match_confidence, 0.90)),
            NOW()
        FROM whd_f7_matches wfm
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = wfm.f7_employer_id
        WHERE wfm.case_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'whd'
                AND sid.source_id = wfm.case_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 2) Name+State: Match remaining WHD cases to existing masters by normalized name + state.
    stats["whd_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (wc.case_id)
            m.master_id,
            'whd',
            wc.case_id,
            0.85,
            NOW()
        FROM whd_cases wc
        JOIN master_employers m
          ON m.canonical_name = COALESCE(wc.name_normalized, '')
         AND COALESCE(m.state, '') = COALESCE(wc.state, '')
        WHERE wc.case_id IS NOT NULL
          AND wc.name_normalized IS NOT NULL
          AND wc.name_normalized != ''
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'whd'
                AND sid.source_id = wc.case_id
          )
        ORDER BY wc.case_id, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 3) Insert: Create new master rows for truly unmatched WHD cases.
    stats["whd_new_master_rows"] = run_sql(
        cur,
        """
        WITH whd_candidates AS (
            SELECT
                wc.case_id,
                COALESCE(wc.name_normalized, 'unknown_whd_' || wc.case_id) AS canonical_name,
                COALESCE(NULLIF(wc.legal_name, ''), NULLIF(wc.trade_name, '')) AS display_name,
                wc.city,
                wc.state,
                wc.zip_code AS zip,
                wc.naics_code AS naics
            FROM whd_cases wc
            WHERE wc.case_id IS NOT NULL
              AND COALESCE(NULLIF(wc.legal_name, ''), NULLIF(wc.trade_name, '')) IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM master_employer_source_ids sid
                  WHERE sid.source_system = 'whd'
                    AND sid.source_id = wc.case_id
              )
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            wc.canonical_name,
            wc.display_name,
            wc.city,
            wc.state,
            wc.zip,
            wc.naics,
            NULL,
            NULL,
            NULL,
            FALSE,
            FALSE,
            FALSE,
            FALSE,
            'whd',
            35.00
        FROM whd_candidates wc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.canonical_name = wc.canonical_name
              AND COALESCE(m.state, '') = COALESCE(wc.state, '')
              AND COALESCE(m.city, '') = COALESCE(wc.city, '')
        )
        """
    )

    # 4) Backfill source IDs for newly created WHD-origin masters.
    stats["whd_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'whd',
            wc.case_id,
            0.70,
            NOW()
        FROM whd_cases wc
        JOIN master_employers m
          ON m.source_origin = 'whd'
         AND m.display_name = COALESCE(NULLIF(wc.legal_name, ''), NULLIF(wc.trade_name, ''))
         AND COALESCE(m.state, '') = COALESCE(wc.state, '')
         AND COALESCE(m.city, '') = COALESCE(wc.city, '')
        WHERE wc.case_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'whd'
                AND sid.source_id = wc.case_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    return stats


def print_stats(stats: Dict[str, int]) -> None:
    print("[whd]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    total_links = sum(v for k, v in stats.items() if 'source_ids' in k)
    total_new = stats.get('whd_new_master_rows', 0)
    print(f"  --- Total source links: {total_links:,}")
    print(f"  --- Total new masters: {total_new:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed master_employers from WHD cases")
    parser.add_argument("--dry-run", action="store_true", help="Rollback at end")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print_stats(seed_whd(cur))

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
