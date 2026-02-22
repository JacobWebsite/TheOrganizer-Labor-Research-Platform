"""
Rebuild legacy match tables from active unified_match_log rows.

Run this AFTER source matching re-runs complete and BEFORE refreshing
materialized views that depend on legacy match tables.

Safety:
- Rebuilds only from `unified_match_log WHERE status='active'`
- Runs in one transaction and rolls back on error
- Supports `--dry-run` to print planned before/after counts without writes

Usage:
    py scripts/maintenance/rebuild_legacy_tables.py --dry-run
    py scripts/maintenance/rebuild_legacy_tables.py
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


@dataclass(frozen=True)
class LegacyTableConfig:
    table_name: str
    source_system: Optional[str]
    delete_sql: Optional[str]
    insert_sql: Optional[str]
    note: Optional[str] = None


CONFIGS: Dict[str, LegacyTableConfig] = {
    "osha_f7_matches": LegacyTableConfig(
        table_name="osha_f7_matches",
        source_system="osha",
        delete_sql="DELETE FROM osha_f7_matches",
        insert_sql="""
            INSERT INTO osha_f7_matches
                (establishment_id, f7_employer_id, match_method, match_confidence, match_source, low_confidence)
            SELECT
                uml.source_id,
                uml.target_id,
                uml.match_method,
                uml.confidence_score,
                'UML_REBUILD',
                (uml.confidence_band = 'LOW')
            FROM unified_match_log uml
            WHERE uml.status = 'active'
              AND uml.source_system = 'osha'
        """,
    ),
    "whd_f7_matches": LegacyTableConfig(
        table_name="whd_f7_matches",
        source_system="whd",
        delete_sql="DELETE FROM whd_f7_matches",
        insert_sql="""
            INSERT INTO whd_f7_matches
                (case_id, f7_employer_id, match_method, match_confidence, match_source, low_confidence)
            SELECT
                uml.source_id::bigint,
                uml.target_id,
                uml.match_method,
                uml.confidence_score,
                'UML_REBUILD',
                (uml.confidence_band = 'LOW')
            FROM unified_match_log uml
            WHERE uml.status = 'active'
              AND uml.source_system = 'whd'
        """,
    ),
    "sam_f7_matches": LegacyTableConfig(
        table_name="sam_f7_matches",
        source_system="sam",
        delete_sql="DELETE FROM sam_f7_matches",
        insert_sql="""
            INSERT INTO sam_f7_matches
                (uei, f7_employer_id, match_method, match_confidence, match_source)
            SELECT
                uml.source_id,
                uml.target_id,
                uml.match_method,
                uml.confidence_score,
                'UML_REBUILD'
            FROM unified_match_log uml
            WHERE uml.status = 'active'
              AND uml.source_system = 'sam'
        """,
    ),
    "national_990_f7_matches": LegacyTableConfig(
        table_name="national_990_f7_matches",
        source_system="990",
        delete_sql="DELETE FROM national_990_f7_matches",
        insert_sql="""
            INSERT INTO national_990_f7_matches
                (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (uml.source_id)
                uml.source_id::bigint AS n990_id,
                COALESCE(nf.ein, uml.evidence->>'ein') AS ein,
                uml.target_id AS f7_employer_id,
                uml.match_method,
                uml.confidence_score,
                'UML_REBUILD'
            FROM unified_match_log uml
            LEFT JOIN national_990_filers nf
                ON nf.id::text = uml.source_id
            WHERE uml.status = 'active'
              AND uml.source_system = '990'
            ORDER BY uml.source_id, uml.confidence_score DESC
        """,
    ),
    "nlrb_employer_xref": LegacyTableConfig(
        table_name="nlrb_employer_xref",
        source_system="nlrb",
        delete_sql="DELETE FROM nlrb_employer_xref",
        insert_sql="""
            INSERT INTO nlrb_employer_xref
                (nlrb_employer_name, nlrb_city, nlrb_state, f7_employer_id,
                 match_confidence, match_method, verified, notes)
            SELECT
                uml.evidence->>'nlrb_employer_name' AS nlrb_employer_name,
                uml.evidence->>'nlrb_city' AS nlrb_city,
                uml.evidence->>'nlrb_state' AS nlrb_state,
                uml.target_id AS f7_employer_id,
                uml.confidence_score AS match_confidence,
                uml.match_method,
                FALSE AS verified,
                'Rebuilt from unified_match_log active rows' AS notes
            FROM unified_match_log uml
            WHERE uml.status = 'active'
              AND uml.source_system = 'nlrb'
        """,
    ),
    # Exists in public schema but not currently sourced from unified_match_log.
    "usaspending_f7_matches": LegacyTableConfig(
        table_name="usaspending_f7_matches",
        source_system=None,
        delete_sql=None,
        insert_sql=None,
        note="No direct source_system mapping in unified_match_log; skipped.",
    ),
}


def discover_legacy_tables(cur) -> List[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND (
                table_name LIKE '%\\_f7\\_matches' ESCAPE '\\'
                OR table_name = 'nlrb_employer_xref'
              )
        ORDER BY table_name
        """
    )
    return [r[0] for r in cur.fetchall()]


def get_count(cur, table_name: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cur.fetchone()[0])


def get_insert_count(cur, source_system: str) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM unified_match_log
        WHERE status = 'active'
          AND source_system = %s
        """,
        [source_system],
    )
    return int(cur.fetchone()[0])


def rebuild_table(cur, cfg: LegacyTableConfig, dry_run: bool) -> Tuple[int, int]:
    before = get_count(cur, cfg.table_name)
    if cfg.source_system is None:
        return before, before

    planned = get_insert_count(cur, cfg.source_system)
    if dry_run:
        return before, planned

    cur.execute(cfg.delete_sql)
    cur.execute(cfg.insert_sql)
    after = get_count(cur, cfg.table_name)
    return before, after


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild legacy match tables from unified_match_log")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            discovered = discover_legacy_tables(cur)
            print("Discovered legacy tables:")
            for t in discovered:
                print(f"  - {t}")

            print("\nRebuild plan/results:")
            for table_name in discovered:
                cfg = CONFIGS.get(table_name)
                if not cfg:
                    print(f"  - {table_name}: no mapping configured; skipped")
                    continue
                if cfg.source_system is None:
                    print(f"  - {table_name}: skipped ({cfg.note})")
                    continue

                before, after_or_planned = rebuild_table(cur, cfg, args.dry_run)
                action = "planned_rows" if args.dry_run else "after_rows"
                print(
                    f"  - {table_name} [{cfg.source_system}]: "
                    f"before={before:,}, {action}={after_or_planned:,}"
                )

        if args.dry_run:
            conn.rollback()
            print("\nDry-run complete. No changes were written.")
        else:
            conn.commit()
            print("\nRebuild complete. Transaction committed.")
    except Exception as exc:
        conn.rollback()
        print(f"\nERROR: {exc}")
        print("Rolled back transaction.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
