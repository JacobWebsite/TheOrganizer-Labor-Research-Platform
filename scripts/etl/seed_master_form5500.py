#!/usr/bin/env python3
"""
Seed master_employer_source_ids from Form 5500 curated data.

Enrichment-only: links Form 5500 sponsors to EXISTING master employers.
Does NOT create new master_employer rows.

Match strategy:
  1. EIN exact match to master_employers.ein (confidence 1.0)
  2. Name+state fallback against master_employers.canonical_name + state (confidence 0.85)

Usage:
  python scripts/etl/seed_master_form5500.py
  python scripts/etl/seed_master_form5500.py --dry-run
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


def ensure_check_constraints(conn, cur):
    """Add 'form5500' to CHECK constraints on master tables if missing."""
    for tbl, col, con_name, new_val in [
        ('master_employer_source_ids', 'source_system', 'chk_master_source_system', 'form5500'),
        ('master_employers', 'source_origin', 'chk_master_source_origin', 'form5500'),
    ]:
        cur.execute("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = %s::regclass AND conname = %s
        """, (tbl, con_name))
        row = cur.fetchone()
        if row and new_val not in row[0]:
            # Parse existing allowed values and add new one
            import re
            m = re.search(r"\((.+)\)", row[0])
            if m:
                existing = m.group(1)
                # Add new value
                new_allowed = existing.rstrip(")") + f", '{new_val}'::text)"
                # Simpler: just rebuild from scratch
                vals = re.findall(r"'([^']+)'", existing)
                vals.append(new_val)
                allowed_sql = "(" + ", ".join(f"'{v}'::text" for v in vals) + ")"
                print(f"  Adding '{new_val}' to {tbl}.{con_name}...")
                cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT {con_name}")
                cur.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT {con_name} CHECK ({col} IN {allowed_sql})")
                conn.commit()
                print(f"  Constraint {con_name} updated.")


def seed_form5500(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # 1) EIN exact match: high-confidence link via sponsor_ein = master.ein
    stats["ein_match"] = run_sql(cur, """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (f.sponsor_ein)
            m.master_id,
            'form5500',
            f.sponsor_ein,
            1.0,
            NOW()
        FROM cur_form5500_sponsor_rollup f
        JOIN master_employers m ON m.ein = f.sponsor_ein
        WHERE f.sponsor_ein IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'form5500'
                AND sid.source_id = f.sponsor_ein
          )
        ORDER BY f.sponsor_ein, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
    """)

    # 2) Name+state fallback for remaining unmatched sponsors
    stats["name_state_match"] = run_sql(cur, """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (f.sponsor_ein)
            m.master_id,
            'form5500',
            f.sponsor_ein,
            0.85,
            NOW()
        FROM cur_form5500_sponsor_rollup f
        JOIN master_employers m
          ON m.canonical_name = TRIM(REGEXP_REPLACE(LOWER(f.sponsor_name), '[^a-z0-9 ]', ' ', 'g'))
         AND COALESCE(m.state, '') = COALESCE(f.sponsor_state, '')
        WHERE f.sponsor_ein IS NOT NULL
          AND f.sponsor_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'form5500'
                AND sid.source_id = f.sponsor_ein
          )
        ORDER BY f.sponsor_ein, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
    """)

    return stats


def print_stats(stats: Dict[str, int]) -> None:
    print("[form5500]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    total = sum(stats.values())
    print(f"  --- Total source links: {total:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed master_employers from Form 5500")
    parser.add_argument("--dry-run", action="store_true", help="Rollback at end")
    args = parser.parse_args()

    conn = get_connection()

    try:
        # Update CHECK constraints first (DDL needs its own commit)
        conn.autocommit = True
        with conn.cursor() as cur:
            ensure_check_constraints(conn, cur)

        # Seed in a transaction
        conn.autocommit = False
        with conn.cursor() as cur:
            print_stats(seed_form5500(cur))

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
