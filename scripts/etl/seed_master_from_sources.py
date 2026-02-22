#!/usr/bin/env python3
"""
Seed master_employers from SAM, Mergent, and BMF in match-first order.

Usage:
  python scripts/etl/seed_master_from_sources.py --source sam
  python scripts/etl/seed_master_from_sources.py --source mergent
  python scripts/etl/seed_master_from_sources.py --source bmf
  python scripts/etl/seed_master_from_sources.py --source all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

# Project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection


def run_sql(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.rowcount if cur.rowcount is not None else 0


def seed_sam(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Attach SAM UEIs to existing F7-seeded masters via sam_f7_matches.
    stats["sam_source_ids_from_f7_matches"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            f7sid.master_id,
            'sam',
            s.uei,
            LEAST(1.0, COALESCE(s.match_confidence, 1.0)),
            NOW()
        FROM sam_f7_matches s
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = s.f7_employer_id
        WHERE s.uei IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'sam'
                AND sid.source_id = s.uei
          )
        """
    )

    # 2) Match remaining SAM entities by canonical name + state.
    stats["sam_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'sam',
            s.uei,
            0.90,
            NOW()
        FROM sam_entities s
        JOIN master_employers m
          ON m.canonical_name = COALESCE(NULLIF(s.name_aggressive, ''), NULLIF(s.name_normalized, ''))
         AND COALESCE(m.state, '') = COALESCE(s.physical_state, '')
        WHERE s.uei IS NOT NULL
          AND COALESCE(NULLIF(s.name_aggressive, ''), NULLIF(s.name_normalized, '')) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'sam'
                AND sid.source_id = s.uei
          )
        """
    )

    # 3) Insert truly unmatched SAM entities as new masters.
    stats["sam_new_master_rows"] = run_sql(
        cur,
        """
        WITH sam_candidates AS (
            SELECT
                s.uei,
                COALESCE(NULLIF(s.name_aggressive, ''), NULLIF(s.name_normalized, '')) AS canonical_name,
                COALESCE(NULLIF(s.legal_business_name, ''), NULLIF(s.dba_name, '')) AS display_name,
                s.physical_city AS city,
                s.physical_state AS state,
                s.physical_zip AS zip,
                s.naics_primary AS naics
            FROM sam_entities s
            WHERE s.uei IS NOT NULL
              AND COALESCE(NULLIF(s.legal_business_name, ''), NULLIF(s.dba_name, '')) IS NOT NULL
        )
        INSERT INTO master_employers (
            canonical_name,
            display_name,
            city,
            state,
            zip,
            naics,
            employee_count,
            employee_count_source,
            ein,
            is_union,
            is_public,
            is_federal_contractor,
            is_nonprofit,
            source_origin,
            data_quality_score
        )
        SELECT
            COALESCE(sc.canonical_name, 'unknown_sam_' || sc.uei),
            sc.display_name,
            sc.city,
            sc.state,
            sc.zip,
            sc.naics,
            NULL,
            NULL,
            NULL,
            FALSE,
            FALSE,
            TRUE,
            FALSE,
            'sam',
            45.00
        FROM sam_candidates sc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employer_source_ids sid
            WHERE sid.source_system = 'sam'
              AND sid.source_id = sc.uei
        )
          AND NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.canonical_name = COALESCE(sc.canonical_name, 'unknown_sam_' || sc.uei)
              AND COALESCE(m.state, '') = COALESCE(sc.state, '')
              AND COALESCE(m.city, '') = COALESCE(sc.city, '')
              AND COALESCE(m.zip, '') = COALESCE(sc.zip, '')
        )
        """
    )

    # 4) Backfill source IDs for SAM-origin rows.
    stats["sam_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'sam',
            s.uei,
            0.70,
            NOW()
        FROM sam_entities s
        JOIN master_employers m
          ON m.source_origin = 'sam'
         AND m.display_name = COALESCE(NULLIF(s.legal_business_name, ''), NULLIF(s.dba_name, ''))
         AND COALESCE(m.state, '') = COALESCE(s.physical_state, '')
         AND COALESCE(m.city, '') = COALESCE(s.physical_city, '')
         AND COALESCE(m.zip, '') = COALESCE(s.physical_zip, '')
        WHERE s.uei IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'sam'
                AND sid.source_id = s.uei
          )
        """
    )

    # 5) Mark matched/seeded SAM employers as federal contractors.
    stats["sam_federal_contractor_updates"] = run_sql(
        cur,
        """
        UPDATE master_employers m
        SET is_federal_contractor = TRUE,
            updated_at = NOW()
        WHERE NOT m.is_federal_contractor
          AND EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.master_id = m.master_id
                AND sid.source_system = 'sam'
          )
        """
    )

    return stats


def seed_mergent(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Attach Mergent IDs via corporate crosswalk (f7 -> duns).
    stats["mergent_source_ids_from_crosswalk"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            f7sid.master_id,
            'mergent',
            c.mergent_duns,
            1.0,
            NOW()
        FROM corporate_identifier_crosswalk c
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = c.f7_employer_id
        WHERE c.mergent_duns IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = c.mergent_duns
          )
        """
    )

    # 2) Match remaining Mergent rows by EIN.
    stats["mergent_source_ids_by_ein"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'mergent',
            COALESCE(NULLIF(me.duns, ''), me.id::TEXT),
            0.95,
            NOW()
        FROM mergent_employers me
        JOIN master_employers m
          ON m.ein IS NOT NULL
         AND m.ein = me.ein
        WHERE COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """
    )

    # 3) Match by canonical name + state.
    stats["mergent_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'mergent',
            COALESCE(NULLIF(me.duns, ''), me.id::TEXT),
            0.90,
            NOW()
        FROM mergent_employers me
        JOIN master_employers m
          ON m.canonical_name = COALESCE(NULLIF(me.company_name_normalized, ''), lower(me.company_name))
         AND COALESCE(m.state, '') = COALESCE(me.state, '')
        WHERE COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, '')) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """
    )

    # 4) Insert unmatched as new master rows.
    stats["mergent_new_master_rows"] = run_sql(
        cur,
        """
        WITH me_candidates AS (
            SELECT
                COALESCE(NULLIF(me.duns, ''), me.id::TEXT) AS src_id,
                COALESCE(NULLIF(me.company_name_normalized, ''), lower(me.company_name)) AS canonical_name,
                COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, '')) AS display_name,
                me.city,
                me.state,
                me.zip,
                me.naics_primary AS naics,
                COALESCE(me.employees_all_sites, me.employees_site) AS employees,
                me.ein
            FROM mergent_employers me
            WHERE COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
              AND COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, '')) IS NOT NULL
        )
        INSERT INTO master_employers (
            canonical_name,
            display_name,
            city,
            state,
            zip,
            naics,
            employee_count,
            employee_count_source,
            ein,
            is_union,
            is_public,
            is_federal_contractor,
            is_nonprofit,
            source_origin,
            data_quality_score
        )
        SELECT
            COALESCE(mc.canonical_name, 'unknown_mergent_' || mc.src_id),
            mc.display_name,
            mc.city,
            mc.state,
            mc.zip,
            mc.naics,
            mc.employees,
            CASE WHEN mc.employees IS NOT NULL THEN 'mergent' ELSE NULL END,
            mc.ein,
            FALSE,
            FALSE,
            FALSE,
            FALSE,
            'mergent',
            55.00
        FROM me_candidates mc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employer_source_ids sid
            WHERE sid.source_system = 'mergent'
              AND sid.source_id = mc.src_id
        )
          AND NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.canonical_name = COALESCE(mc.canonical_name, 'unknown_mergent_' || mc.src_id)
              AND COALESCE(m.state, '') = COALESCE(mc.state, '')
              AND COALESCE(m.city, '') = COALESCE(mc.city, '')
              AND COALESCE(m.zip, '') = COALESCE(mc.zip, '')
        )
        """
    )

    # 5) Backfill source IDs for newly seeded Mergent rows.
    stats["mergent_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'mergent',
            COALESCE(NULLIF(me.duns, ''), me.id::TEXT),
            0.70,
            NOW()
        FROM mergent_employers me
        JOIN master_employers m
          ON m.source_origin = 'mergent'
         AND m.display_name = COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, ''))
         AND COALESCE(m.state, '') = COALESCE(me.state, '')
         AND COALESCE(m.city, '') = COALESCE(me.city, '')
         AND COALESCE(m.zip, '') = COALESCE(me.zip, '')
        WHERE COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """
    )

    # 6) Enrich flags and fields from mapped source IDs.
    stats["mergent_ein_updates"] = run_sql(
        cur,
        """
        UPDATE master_employers m
        SET
            ein = COALESCE(m.ein, me.ein),
            employee_count = COALESCE(m.employee_count, COALESCE(me.employees_all_sites, me.employees_site)),
            employee_count_source = COALESCE(
                m.employee_count_source,
                CASE WHEN COALESCE(me.employees_all_sites, me.employees_site) IS NOT NULL THEN 'mergent' ELSE NULL END
            ),
            updated_at = NOW()
        FROM master_employer_source_ids sid
        JOIN mergent_employers me
          ON sid.source_system = 'mergent'
         AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
        WHERE sid.master_id = m.master_id
          AND (
              (m.ein IS NULL AND me.ein IS NOT NULL)
              OR (m.employee_count IS NULL AND COALESCE(me.employees_all_sites, me.employees_site) IS NOT NULL)
          )
        """
    )

    return stats


def seed_bmf(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) Match BMF by EIN to existing masters (high confidence).
    stats["bmf_source_ids_by_ein"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'bmf',
            b.ein,
            0.98,
            NOW()
        FROM irs_bmf b
        JOIN master_employers m
          ON m.ein IS NOT NULL
         AND m.ein = b.ein
        WHERE b.ein IS NOT NULL
          AND b.org_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """
    )

    # 2) Match remaining by canonical name + state.
    stats["bmf_source_ids_name_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'bmf',
            b.ein,
            0.90,
            NOW()
        FROM irs_bmf b
        JOIN master_employers m
          ON m.canonical_name = b.name_normalized
         AND COALESCE(m.state, '') = COALESCE(b.state, '')
        WHERE b.ein IS NOT NULL
          AND b.org_name IS NOT NULL
          AND b.name_normalized IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """
    )

    # 3) Insert unmatched BMF rows as new masters.
    stats["bmf_new_master_rows"] = run_sql(
        cur,
        """
        WITH bmf_candidates AS (
            SELECT
                b.ein,
                COALESCE(NULLIF(b.name_normalized, ''), lower(b.org_name)) AS canonical_name,
                b.org_name AS display_name,
                b.city,
                b.state,
                b.zip_code AS zip
            FROM irs_bmf b
            WHERE b.ein IS NOT NULL
              AND b.org_name IS NOT NULL
        )
        INSERT INTO master_employers (
            canonical_name,
            display_name,
            city,
            state,
            zip,
            naics,
            employee_count,
            employee_count_source,
            ein,
            is_union,
            is_public,
            is_federal_contractor,
            is_nonprofit,
            source_origin,
            data_quality_score
        )
        SELECT
            COALESCE(bc.canonical_name, 'unknown_bmf_' || bc.ein),
            bc.display_name,
            bc.city,
            bc.state,
            bc.zip,
            NULL,
            NULL,
            NULL,
            bc.ein,
            FALSE,
            FALSE,
            FALSE,
            TRUE,
            'bmf',
            35.00
        FROM bmf_candidates bc
        WHERE NOT EXISTS (
            SELECT 1
            FROM master_employer_source_ids sid
            WHERE sid.source_system = 'bmf'
              AND sid.source_id = bc.ein
        )
          AND NOT EXISTS (
            SELECT 1
            FROM master_employers m
            WHERE m.ein = bc.ein
               OR (
                    m.canonical_name = COALESCE(bc.canonical_name, 'unknown_bmf_' || bc.ein)
                AND COALESCE(m.state, '') = COALESCE(bc.state, '')
                AND COALESCE(m.city, '') = COALESCE(bc.city, '')
               )
        )
        """
    )

    # 4) Backfill source IDs for BMF-origin rows.
    stats["bmf_source_ids_for_new_rows"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'bmf',
            b.ein,
            0.70,
            NOW()
        FROM irs_bmf b
        JOIN master_employers m
          ON m.source_origin = 'bmf'
         AND m.ein = b.ein
        WHERE b.ein IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """
    )

    # 5) Set nonprofit flag and fill EIN for mapped masters.
    stats["bmf_nonprofit_updates"] = run_sql(
        cur,
        """
        UPDATE master_employers m
        SET
            is_nonprofit = TRUE,
            ein = COALESCE(m.ein, b.ein),
            updated_at = NOW()
        FROM master_employer_source_ids sid
        JOIN irs_bmf b
          ON sid.source_system = 'bmf'
         AND sid.source_id = b.ein
        WHERE sid.master_id = m.master_id
          AND (m.is_nonprofit = FALSE OR m.ein IS NULL)
        """
    )

    return stats


def print_stats(label: str, stats: Dict[str, int]) -> None:
    print(f"[{label}]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed master_employers from source systems")
    parser.add_argument(
        "--source",
        choices=["sam", "mergent", "bmf", "all"],
        required=True,
        help="Source wave to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run inside transaction and rollback at the end",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            if args.source in ("sam", "all"):
                print_stats("sam", seed_sam(cur))
            if args.source in ("mergent", "all"):
                print_stats("mergent", seed_mergent(cur))
            if args.source in ("bmf", "all"):
                print_stats("bmf", seed_bmf(cur))

        if args.dry_run:
            conn.rollback()
            print("Dry run complete. Transaction rolled back.")
        else:
            conn.commit()
            print("Seeding complete. Transaction committed.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
