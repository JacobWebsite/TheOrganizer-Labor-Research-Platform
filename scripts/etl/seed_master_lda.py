"""
Match LDA clients to master_employers and link them via
master_employer_source_ids (source_system='lda').

24Q-39 Political. Sister script to seed_master_fec.py / seed_master_epa_echo.py.
LDA's `client_id` is treated as the `source_id` in master_employer_source_ids.

Strategy (mirrors the SEC 13F matcher minus the SEC-link bias):
  1. Stage candidate masters with normalized canonical name + state.
  2. Distinct LDA clients keyed on name_norm + state (an LDA client is
     keyed by `id` in our schema, but the same legal entity can have
     multiple LDA client rows from re-filings; we keep all of them).
  3. Two-tier match: exact (canonical_name == lda.name_norm AND state ==
     state) -> trigram (similarity >= 0.85 with state filter).
  4. Insert one row per (master_id, 'lda', client_id) into
     master_employer_source_ids.

Codex finding from 2026-05-02 wrapup applied here: schema setup runs
inside the same transaction as the inserts, so --dry-run actually rolls
back without leaving DDL committed.

Usage:
    py scripts/etl/seed_master_lda.py             # commits
    py scripts/etl/seed_master_lda.py --dry-run   # rolls back

Run time: ~30-90 seconds depending on volume of clients and trigram pass.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


def run(dry_run: bool) -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        # No DDL outside the transaction; everything is rollback-safe.
        # We just insert into master_employer_source_ids -- no new tables.

        # Step 1: stage candidate masters.
        #
        # Restricted to masters that have at least one cross-source link
        # (SEC, Mergent, BMF, 990, F7, NLRB, OSHA). Pure-source-only
        # masters (single-source loaders that haven't been bridged) are
        # excluded -- they balloon the candidate set 10x and the trigram
        # pass against 5.7M rows times out (~49 min observed before kill).
        # LDA clients are real lobbying entities; they overwhelmingly
        # match to multi-source masters in our universe (large public
        # firms, big nonprofits, trade associations).
        print("Staging candidate masters (multi-source-linked)...")
        cur.execute("DROP TABLE IF EXISTS tmp_lda_master_candidates")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_lda_master_candidates AS
            SELECT
                m.master_id,
                m.canonical_name,
                regexp_replace(
                    regexp_replace(
                        lower(m.canonical_name),
                        '\\s+(inc|incorporated|corporation|corp|company|co|ltd|plc|llc|l\\.?p\\.?|holdings|group)\\s*$',
                        ''
                    ),
                    '[^a-z0-9 ]+', ' ', 'g'
                ) AS canonical_norm,
                upper(coalesce(m.state, '')) AS state_key
            FROM master_employers m
            WHERE m.canonical_name IS NOT NULL
              AND length(m.canonical_name) >= 3
              AND EXISTS (
                  SELECT 1 FROM master_employer_source_ids sid
                  WHERE sid.master_id = m.master_id
                    AND sid.source_system IN ('sec','mergent','bmf','990','f7','nlrb','gleif')
              )
            """
        )
        cur.execute("CREATE INDEX ON tmp_lda_master_candidates (canonical_norm, state_key)")
        cur.execute("CREATE INDEX ON tmp_lda_master_candidates USING gin (canonical_norm gin_trgm_ops)")
        cur.execute("SELECT COUNT(*) FROM tmp_lda_master_candidates")
        n_candidates = cur.fetchone()[0]
        print(f"  {n_candidates:,} candidate masters")

        # Step 2: stage distinct LDA clients (by id; we need every id since
        # we link master->client_id 1:1).
        print("Staging distinct LDA clients...")
        cur.execute("DROP TABLE IF EXISTS tmp_lda_clients")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_lda_clients AS
            SELECT
                c.id::text AS client_id,
                c.name_norm,
                upper(coalesce(c.state, '')) AS state_key
            FROM lda_clients c
            WHERE c.name_norm IS NOT NULL AND length(c.name_norm) >= 3
            """
        )
        cur.execute("CREATE INDEX ON tmp_lda_clients (name_norm, state_key)")
        cur.execute("SELECT COUNT(*) FROM tmp_lda_clients")
        n_clients = cur.fetchone()[0]
        print(f"  {n_clients:,} LDA clients")

        # Step 3: Tier A -- exact match on (name_norm, state).
        # Keep the lowest master_id for stability when an LDA name maps
        # to >1 master in the same state.
        print("Matching tier A (exact)...")
        t0 = time.time()
        cur.execute(
            """
            INSERT INTO master_employer_source_ids
                (master_id, source_system, source_id, match_confidence, matched_at)
            SELECT DISTINCT ON (lc.client_id)
                m.master_id,
                'lda',
                lc.client_id,
                1.000,
                NOW()
            FROM tmp_lda_clients lc
            JOIN tmp_lda_master_candidates m
              ON m.canonical_norm = lc.name_norm
             AND m.state_key      = lc.state_key
             AND lc.state_key <> ''
            ORDER BY lc.client_id, m.master_id
            ON CONFLICT (master_id, source_system, source_id) DO NOTHING
            """
        )
        n_exact = cur.rowcount or 0
        print(f"  +{n_exact:,} exact matches ({time.time()-t0:.0f}s)")

        # Step 4: Tier B -- trigram. SKIPPED in this version.
        #
        # Two attempts (0.85 and 0.92 thresholds) timed out >19 min against
        # 85K LDA clients x ~150K candidate masters, even with state filter
        # and a GIN trigram index on canonical_norm. The query plan
        # apparently can't push the state predicate beneath the trigram
        # operator with the current temp-table layout.
        #
        # Tier A (exact) gives us the high-confidence matches we want
        # (Apple, Walmart, Boeing, etc -- the names trade associations
        # and lobbying firms actually use). Tier B fuzzy is a future
        # follow-up that should:
        #   1) materialize tmp_lda_clients per state, run a separate
        #      trigram join per state in a loop, OR
        #   2) use sqlite_blocks-style (state, name_prefix) blocking, OR
        #   3) externalize via Python similarity loop with an in-memory
        #      RapidFuzz scan over the state-filtered candidate slice.
        n_trigram = 0
        print("Matching tier B (trigram): SKIPPED -- see seed_master_lda.py docstring for plan.")

        # Stats
        cur.execute(
            "SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'lda'"
        )
        n_total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(DISTINCT master_id)
            FROM master_employer_source_ids
            WHERE source_system = 'lda'
            """
        )
        n_masters = cur.fetchone()[0]
        coverage_pct = (n_total / n_clients * 100) if n_clients else 0
        print()
        print(
            f"TOTAL: {n_total:,} of {n_clients:,} clients matched "
            f"({coverage_pct:.1f}%)"
        )
        print(f"       across {n_masters:,} distinct masters.")

        # Sample top matches by lobbying spend so we can eyeball quality.
        print("\nSample top matches (by total LDA spend on linked filings):")
        cur.execute(
            """
            SELECT m.canonical_name, sid.master_id,
                   COUNT(DISTINCT f.filing_uuid) AS n_filings,
                   SUM(COALESCE(f.income, 0)) + SUM(COALESCE(f.expenses, 0)) AS total_spend
            FROM master_employer_source_ids sid
            JOIN master_employers m ON m.master_id = sid.master_id
            JOIN lda_filings f ON f.client_id::text = sid.source_id
            WHERE sid.source_system = 'lda'
            GROUP BY m.canonical_name, sid.master_id
            ORDER BY total_spend DESC NULLS LAST
            LIMIT 10
            """
        )
        for r in cur.fetchall():
            name, mid, n_f, spend = r
            disp = (name or "")[:45]
            print(f"  master={mid:<8d} {disp:<45s} filings={n_f:>4} spend=${(spend or 0):>15,.0f}")

        if dry_run:
            conn.rollback()
            print("\nDRY RUN -- rolled back.")
        else:
            conn.commit()
            print("\nCommitted.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
