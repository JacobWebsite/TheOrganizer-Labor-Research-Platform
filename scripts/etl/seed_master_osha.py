#!/usr/bin/env python3
"""
Seed master_employers from OSHA establishments (non-union only).

Three-step pattern:
  1. Bridge: Link OSHA establishments to existing masters via osha_f7_matches -> F7 source_ids
  2. Name+State: Match remaining OSHA establishments to existing masters by canonical name + state
  3. Insert: Create new master rows for truly unmatched OSHA establishments

Filter: union_status != 'Y' (skip union OSHA establishments)

Usage:
  python scripts/etl/seed_master_osha.py
  python scripts/etl/seed_master_osha.py --dry-run
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


def seed_osha(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Bridge: Attach OSHA establishment_ids to existing masters via osha_f7_matches -> F7 source_ids.
    #    This links OSHA records that are already matched to F7 employers to their master rows.
    stats["osha_source_ids_from_f7_bridge"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            f7sid.master_id,
            'osha',
            ofm.establishment_id,
            LEAST(1.0, COALESCE(ofm.match_confidence, 0.90)),
            NOW()
        FROM osha_f7_matches ofm
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = ofm.f7_employer_id
        JOIN osha_establishments oe ON oe.establishment_id = ofm.establishment_id
        WHERE COALESCE(oe.union_status, 'N') != 'Y'
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'osha'
                AND sid.source_id = ofm.establishment_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 2) Name+State: Match remaining non-union OSHA establishments to existing masters
    #    by normalized name + state.
    stats["osha_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (oe.establishment_id)
            m.master_id,
            'osha',
            oe.establishment_id,
            0.85,
            NOW()
        FROM osha_establishments oe
        JOIN master_employers m
          ON m.canonical_name = COALESCE(
              NULLIF(
                  trim(regexp_replace(lower(COALESCE(oe.estab_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                  ''
              ),
              'unknown_osha_' || oe.establishment_id
          )
         AND COALESCE(m.state, '') = COALESCE(oe.site_state, '')
        WHERE COALESCE(oe.union_status, 'N') != 'Y'
          AND oe.estab_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'osha'
                AND sid.source_id = oe.establishment_id
          )
        ORDER BY oe.establishment_id, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 3) Insert: Create new master rows for truly unmatched non-union OSHA establishments.
    stats["osha_new_master_rows"] = run_sql(
        cur,
        """
        WITH osha_candidates AS (
            SELECT
                oe.establishment_id,
                COALESCE(
                    NULLIF(
                        trim(regexp_replace(lower(COALESCE(oe.estab_name, '')), '[^a-z0-9 ]', ' ', 'g')),
                        ''
                    ),
                    'unknown_osha_' || oe.establishment_id
                ) AS canonical_name,
                oe.estab_name AS display_name,
                oe.site_city AS city,
                oe.site_state AS state,
                oe.site_zip AS zip,
                oe.naics_code AS naics,
                oe.employee_count
            FROM osha_establishments oe
            WHERE COALESCE(oe.union_status, 'N') != 'Y'
              AND oe.estab_name IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM master_employer_source_ids sid
                  WHERE sid.source_system = 'osha'
                    AND sid.source_id = oe.establishment_id
              )
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            oc.canonical_name,
            oc.display_name,
            oc.city,
            oc.state,
            oc.zip,
            oc.naics,
            oc.employee_count,
            CASE WHEN oc.employee_count IS NOT NULL THEN 'osha' ELSE NULL END,
            NULL,
            FALSE,
            FALSE,
            FALSE,
            FALSE,
            'osha',
            40.00
        FROM osha_candidates oc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.canonical_name = oc.canonical_name
              AND COALESCE(m.state, '') = COALESCE(oc.state, '')
              AND COALESCE(m.city, '') = COALESCE(oc.city, '')
        )
        """
    )

    # 4) Backfill source IDs for newly created OSHA-origin masters.
    stats["osha_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'osha',
            oe.establishment_id,
            0.70,
            NOW()
        FROM osha_establishments oe
        JOIN master_employers m
          ON m.source_origin = 'osha'
         AND m.display_name = oe.estab_name
         AND COALESCE(m.state, '') = COALESCE(oe.site_state, '')
         AND COALESCE(m.city, '') = COALESCE(oe.site_city, '')
        WHERE COALESCE(oe.union_status, 'N') != 'Y'
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'osha'
                AND sid.source_id = oe.establishment_id
          )
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """
    )

    # 5) Enrich employee_count on existing masters from OSHA data where missing.
    stats["osha_employee_count_updates"] = run_sql(
        cur,
        """
        UPDATE master_employers m
        SET
            employee_count = oe.employee_count,
            employee_count_source = 'osha',
            updated_at = NOW()
        FROM master_employer_source_ids sid
        JOIN osha_establishments oe
          ON sid.source_system = 'osha'
         AND sid.source_id = oe.establishment_id
        WHERE sid.master_id = m.master_id
          AND m.employee_count IS NULL
          AND oe.employee_count IS NOT NULL
          AND oe.employee_count > 0
        """
    )

    return stats


def print_stats(stats: Dict[str, int]) -> None:
    print("[osha]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    total_links = sum(v for k, v in stats.items() if 'source_ids' in k)
    total_new = stats.get('osha_new_master_rows', 0)
    print(f"  --- Total source links: {total_links:,}")
    print(f"  --- Total new masters: {total_new:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed master_employers from OSHA establishments")
    parser.add_argument("--dry-run", action="store_true", help="Rollback at end")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print_stats(seed_osha(cur))

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
