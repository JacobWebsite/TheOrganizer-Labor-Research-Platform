#!/usr/bin/env python3
"""
Seed master_employer_source_ids from PPP loan curated data.

Enrichment-only: links PPP borrowers to EXISTING master employers.
Does NOT create new master_employer rows (PPP has millions of borrowers,
most are tiny businesses not relevant as organizing targets).

Match strategy:
  - Normalized name + state exact match to master_employers (confidence 0.85)
  - source_id = borrower_name||'|'||borrower_state composite key

Usage:
  python scripts/etl/seed_master_ppp.py
  python scripts/etl/seed_master_ppp.py --dry-run
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
    """Add 'ppp' to CHECK constraints on master tables if missing."""
    for tbl, col, con_name, new_val in [
        ('master_employer_source_ids', 'source_system', 'chk_master_source_system', 'ppp'),
        ('master_employers', 'source_origin', 'chk_master_source_origin', 'ppp'),
    ]:
        cur.execute("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = %s::regclass AND conname = %s
        """, (tbl, con_name))
        row = cur.fetchone()
        if row and new_val not in row[0]:
            import re
            vals = re.findall(r"'([^']+)'", row[0])
            vals.append(new_val)
            allowed_sql = "(" + ", ".join(f"'{v}'::text" for v in vals) + ")"
            print(f"  Adding '{new_val}' to {tbl}.{con_name}...")
            cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT {con_name}")
            cur.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT {con_name} CHECK ({col} IN {allowed_sql})")
            conn.commit()
            print(f"  Constraint {con_name} updated.")


def seed_ppp(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # Name+state match: link PPP borrowers to existing masters
    stats["name_state_match"] = run_sql(cur, """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (p.borrower_name, p.borrower_state)
            m.master_id,
            'ppp',
            p.borrower_name || '|' || COALESCE(p.borrower_state, ''),
            0.85,
            NOW()
        FROM cur_ppp_employer_rollup p
        JOIN master_employers m
          ON m.canonical_name = TRIM(REGEXP_REPLACE(LOWER(p.borrower_name), '[^a-z0-9 ]', ' ', 'g'))
         AND COALESCE(m.state, '') = COALESCE(p.borrower_state, '')
        WHERE p.borrower_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'ppp'
                AND sid.source_id = p.borrower_name || '|' || COALESCE(p.borrower_state, '')
          )
        ORDER BY p.borrower_name, p.borrower_state, m.data_quality_score DESC
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
    """)

    return stats


def print_stats(stats: Dict[str, int]) -> None:
    print("[ppp]")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    total = sum(stats.values())
    print(f"  --- Total source links: {total:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed master_employers from PPP loans")
    parser.add_argument("--dry-run", action="store_true", help="Rollback at end")
    args = parser.parse_args()

    conn = get_connection()

    try:
        # Update CHECK constraints first (DDL needs autocommit)
        conn.autocommit = True
        with conn.cursor() as cur:
            ensure_check_constraints(conn, cur)

        # Seed in a transaction
        conn.autocommit = False
        with conn.cursor() as cur:
            print_stats(seed_ppp(cur))

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
