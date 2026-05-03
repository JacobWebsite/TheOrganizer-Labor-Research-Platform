#!/usr/bin/env python3
"""
Match FEC contributors and corporate PACs to master_employers.

24Q-38 Political. Two matching paths:

  PATH 1: PAC -> Sponsor (corporate PACs)
    fec_committees.connected_org_norm matches master_employers.canonical_name.
    Tells us "this firm has an active corporate PAC."
    Inserts into master_employer_source_ids with source_system='fec' and
    source_id = cmte_id (CMTE_ID is FEC's primary identifier).

  PATH 2: Individual donations rolled up by EMPLOYER
    fec_individual_contributions.employer_norm matches master_employers.canonical_name.
    Tells us "employees of this firm gave $X to candidates last cycle."
    Inserts an aggregated source link per (master_id, sample employer_norm)
    using a synthetic source_id = 'EMP-' || employer_norm hash. Carries the
    aggregated $$ in evidence (via match_confidence as a proxy for now;
    a full evidence column would require schema change).

The seed does NOT insert new master rows for unmatched FEC employer
strings. The FEC EMPLOYER field is free-text and would explode masters
with thousands of typo'd duplicates of existing employers. We only link
existing masters; extending beyond is a future cleanup task.

Usage:
    py scripts/etl/seed_master_fec.py
    py scripts/etl/seed_master_fec.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


def ensure_constraints_allow_fec(cur) -> bool:
    changed = False
    cur.execute("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conname = 'chk_master_source_system'
    """)
    row = cur.fetchone()
    if not (row and "'fec'" in row[0]):
        print("  Adding 'fec' to chk_master_source_system...")
        cur.execute("ALTER TABLE master_employer_source_ids DROP CONSTRAINT IF EXISTS chk_master_source_system")
        cur.execute("""
            ALTER TABLE master_employer_source_ids
            ADD CONSTRAINT chk_master_source_system
            CHECK (source_system = ANY (ARRAY[
                'f7','sam','mergent','osha','bmf','nlrb','sec','gleif',
                '990','manual','corpwatch','whd','ppp','form5500','epa_echo','fec'
            ]))
        """)
        changed = True
    return changed


def run_sql(cur, sql: str, *params) -> int:
    cur.execute(sql, params if params else None)
    return cur.rowcount if cur.rowcount is not None else 0


def seed_fec(cur) -> Dict[str, int]:
    stats: Dict[str, int] = {}

    # PATH 1: Corporate PACs (committees with a connected_org_nm matching a master)
    stats["fec_pac_links_to_existing_masters"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (fc.cmte_id)
            m.master_id,
            'fec',
            fc.cmte_id,
            0.90,
            NOW()
        FROM fec_committees fc
        JOIN master_employers m
          ON m.canonical_name = fc.connected_org_norm
         AND COALESCE(m.state, '') = COALESCE(fc.cmte_st, '')
        WHERE fc.connected_org_norm IS NOT NULL
          AND fc.cmte_tp IN ('Q','N','V','W')  -- separate segregated funds + nonqualified PACs
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'fec' AND sid.source_id = fc.cmte_id
          )
        ORDER BY fc.cmte_id, m.data_quality_score DESC NULLS LAST
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    # PATH 1B: Corporate PACs WITHOUT state agreement (looser match — many PACs
    # are HQ'd in DC but the company is elsewhere).
    stats["fec_pac_links_loose_state"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (fc.cmte_id)
            m.master_id,
            'fec',
            fc.cmte_id,
            0.75,
            NOW()
        FROM fec_committees fc
        JOIN master_employers m
          ON m.canonical_name = fc.connected_org_norm
        WHERE fc.connected_org_norm IS NOT NULL
          AND fc.cmte_tp IN ('Q','N','V','W')
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'fec' AND sid.source_id = fc.cmte_id
          )
        ORDER BY fc.cmte_id, m.data_quality_score DESC NULLS LAST
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    # PATH 2: Individual donations -- create one synthetic source_id per
    # (master_id, employer_norm) so the per-master donation totals can be
    # queried from master_employer_source_ids.source_id later.
    # Source_id format: 'INDIV-' || md5(employer_norm)::text first 8 chars.
    # Confidence is set high (0.95) because exact-name match on the
    # already-aggressive employer normalization is high-precision.
    stats["fec_indiv_employer_links"] = run_sql(
        cur,
        """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT DISTINCT ON (m.master_id, fic.employer_norm)
            m.master_id,
            'fec',
            'INDIV-' || SUBSTRING(MD5(fic.employer_norm), 1, 9),
            0.95,
            NOW()
        FROM fec_individual_contributions fic
        JOIN master_employers m
          ON m.canonical_name = fic.employer_norm
        WHERE fic.employer_norm IS NOT NULL
          AND fic.transaction_amt > 0
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'fec'
                AND sid.master_id = m.master_id
                AND sid.source_id = 'INDIV-' || SUBSTRING(MD5(fic.employer_norm), 1, 9)
          )
        ORDER BY m.master_id, fic.employer_norm, m.data_quality_score DESC NULLS LAST
        ON CONFLICT (master_id, source_system, source_id) DO NOTHING
        """,
    )

    return stats


def print_summary(cur):
    print("\nDistinct masters touched by FEC matching:")
    cur.execute("""
        SELECT
            COUNT(DISTINCT master_id) FILTER (WHERE source_id NOT LIKE 'INDIV-%') AS pac_masters,
            COUNT(DISTINCT master_id) FILTER (WHERE source_id LIKE 'INDIV-%')     AS indiv_masters,
            COUNT(DISTINCT master_id) AS any_fec_masters,
            COUNT(*) AS total_links
        FROM master_employer_source_ids
        WHERE source_system = 'fec'
    """)
    pac, indiv, any_, total = cur.fetchone()
    print(f"  Masters with corporate PAC:     {pac:>10,}")
    print(f"  Masters with employee donations:{indiv:>10,}")
    print(f"  Masters with any FEC presence:  {any_:>10,}")
    print(f"  Total FEC source-id links:       {total:>10,}")

    print("\nTop 10 masters by donation total (employee + PAC):")
    cur.execute("""
        WITH master_donations AS (
            SELECT m.master_id, m.display_name, m.state,
                   COALESCE(SUM(fic.transaction_amt), 0) AS indiv_total,
                   COUNT(DISTINCT fic.sub_id) AS indiv_count
            FROM master_employer_source_ids sid
            JOIN master_employers m ON m.master_id = sid.master_id
            LEFT JOIN fec_individual_contributions fic
              ON fic.employer_norm = m.canonical_name
            WHERE sid.source_system = 'fec' AND sid.source_id LIKE 'INDIV-%'
            GROUP BY m.master_id, m.display_name, m.state
        )
        SELECT * FROM master_donations
        ORDER BY indiv_total DESC LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"  {r[1][:42]:<42s} {r[2] or '?':<3s} ${r[3]:>14,.0f} ({r[4]:,} donations)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Roll back at end (preview counts only)")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        conn.autocommit = True
        if ensure_constraints_allow_fec(cur):
            print("  Constraints updated.")
        conn.autocommit = False

        cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'fec'")
        before = cur.fetchone()[0]

        print("\nSeeding FEC into master_employer_source_ids...")
        stats = seed_fec(cur)
        for k, v in stats.items():
            print(f"  {k:<40s} {v:>10,}")

        cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'fec'")
        after = cur.fetchone()[0]
        print(f"\nfec source-id links: {before:,} -> {after:,} (+{after - before:,})")

        print_summary(cur)

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
