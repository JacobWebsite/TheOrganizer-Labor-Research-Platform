#!/usr/bin/env python3
"""
Chunked seeding for master_employers from Mergent and BMF.

Runs one bucket per invocation so long transactions can be avoided.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunked master seeding")
    parser.add_argument("--source", choices=["mergent", "bmf"], required=True)
    parser.add_argument("--bucket", type=int, required=True)
    parser.add_argument("--buckets", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def count_bucket(cur, source: str, buckets: int, bucket: int) -> int:
    if source == "mergent":
        cur.execute(
            """
            SELECT COUNT(*)
            FROM mergent_employers me
            WHERE me.id IS NOT NULL
              AND mod(me.id, %s) = %s
            """,
            (buckets, bucket),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM irs_bmf b
            WHERE b.ein IS NOT NULL
              AND b.org_name IS NOT NULL
              AND mod(abs(hashtext(b.ein)), %s) = %s
            """,
            (buckets, bucket),
        )
    return cur.fetchone()[0]


def seed_mergent_bucket(cur, buckets: int, bucket: int) -> dict:
    stats = {}

    cur.execute(
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
        JOIN mergent_employers me
          ON me.duns = c.mergent_duns
        WHERE c.mergent_duns IS NOT NULL
          AND me.id IS NOT NULL
          AND mod(me.id, %s) = %s
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = c.mergent_duns
          )
        """,
        (buckets, bucket),
    )
    stats["crosswalk"] = cur.rowcount

    cur.execute(
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
        WHERE me.id IS NOT NULL
          AND mod(me.id, %s) = %s
          AND COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """,
        (buckets, bucket),
    )
    stats["ein_match"] = cur.rowcount

    cur.execute(
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
        WHERE me.id IS NOT NULL
          AND mod(me.id, %s) = %s
          AND COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, '')) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """,
        (buckets, bucket),
    )
    stats["name_state_match"] = cur.rowcount

    cur.execute(
        """
        WITH me_candidates AS (
            SELECT
                me.id,
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
            WHERE me.id IS NOT NULL
              AND mod(me.id, %s) = %s
              AND COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
              AND COALESCE(NULLIF(me.company_name, ''), NULLIF(me.trade_name, '')) IS NOT NULL
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            COALESCE(mc.canonical_name, 'unknown_mergent_' || mc.src_id),
            mc.display_name, mc.city, mc.state, mc.zip, mc.naics,
            mc.employees,
            CASE WHEN mc.employees IS NOT NULL THEN 'mergent' ELSE NULL END,
            mc.ein,
            FALSE, FALSE, FALSE, FALSE,
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
        """,
        (buckets, bucket),
    )
    stats["new_master"] = cur.rowcount

    cur.execute(
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
        WHERE me.id IS NOT NULL
          AND mod(me.id, %s) = %s
          AND COALESCE(NULLIF(me.duns, ''), me.id::TEXT) IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'mergent'
                AND sid.source_id = COALESCE(NULLIF(me.duns, ''), me.id::TEXT)
          )
        """,
        (buckets, bucket),
    )
    stats["source_ids_new"] = cur.rowcount

    cur.execute(
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
          AND me.id IS NOT NULL
          AND mod(me.id, %s) = %s
          AND (
              (m.ein IS NULL AND me.ein IS NOT NULL)
              OR (m.employee_count IS NULL AND COALESCE(me.employees_all_sites, me.employees_site) IS NOT NULL)
          )
        """,
        (buckets, bucket),
    )
    stats["enrich_updates"] = cur.rowcount

    return stats


def seed_bmf_bucket(cur, buckets: int, bucket: int) -> dict:
    stats = {}

    cur.execute(
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
          AND mod(abs(hashtext(b.ein)), %s) = %s
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """,
        (buckets, bucket),
    )
    stats["ein_match"] = cur.rowcount

    cur.execute(
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
          AND mod(abs(hashtext(b.ein)), %s) = %s
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """,
        (buckets, bucket),
    )
    stats["name_state_match"] = cur.rowcount

    cur.execute(
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
              AND mod(abs(hashtext(b.ein)), %s) = %s
        )
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
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
            FALSE, FALSE, FALSE, TRUE,
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
        """,
        (buckets, bucket),
    )
    stats["new_master"] = cur.rowcount

    cur.execute(
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
          AND b.org_name IS NOT NULL
          AND mod(abs(hashtext(b.ein)), %s) = %s
          AND NOT EXISTS (
              SELECT 1
              FROM master_employer_source_ids sid
              WHERE sid.source_system = 'bmf'
                AND sid.source_id = b.ein
          )
        """,
        (buckets, bucket),
    )
    stats["source_ids_new"] = cur.rowcount

    cur.execute(
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
          AND mod(abs(hashtext(b.ein)), %s) = %s
          AND (m.is_nonprofit = FALSE OR m.ein IS NULL)
        """,
        (buckets, bucket),
    )
    stats["nonprofit_updates"] = cur.rowcount

    return stats


def main() -> int:
    args = parse_args()
    if args.bucket < 0 or args.bucket >= args.buckets:
        print("ERROR: bucket must be in [0, buckets-1]")
        return 1

    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            bucket_count = count_bucket(cur, args.source, args.buckets, args.bucket)
            if args.source == "mergent":
                stats = seed_mergent_bucket(cur, args.buckets, args.bucket)
            else:
                stats = seed_bmf_bucket(cur, args.buckets, args.bucket)

        if args.dry_run:
            conn.rollback()
            status = "rolled_back"
        else:
            conn.commit()
            status = "committed"

        print(
            f"source={args.source} bucket={args.bucket}/{args.buckets} "
            f"bucket_count={bucket_count} status={status} "
            + " ".join([f"{k}={v}" for k, v in stats.items()])
        )
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
