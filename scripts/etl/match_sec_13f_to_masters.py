"""
Match SEC 13F issuer names to master_employers.

24Q-9: Stockholders. Builds sec_13f_issuer_master_map -- a one-row-per-
distinct-issuer-name table that bridges 13F holdings (which name companies
by issuer name + CUSIP) to our master_employers universe.

Why a separate map: in our data model, a master is the TARGET being held,
not the source-system FILER, so this match doesn't fit the usual
master_employer_source_ids pattern (which links masters to source records
*about* them).

Strategy:
  1. Distinct issuer names from sec_13f_holdings (millions of rows collapse
     to ~30K distinct issuers).
  2. Restrict candidate masters to those already linked to source_system='sec'
     (517K SEC-bridged masters). This keeps the match space tractable and
     biases toward truly public targets.
  3. Two-tier match:
       (a) Exact: name_of_issuer_norm == canonical_name
       (b) Trigram: similarity > 0.85 via pg_trgm
  4. For each issuer keep best match (highest similarity, lowest master_id
     for stability).

Usage:
    py scripts/etl/match_sec_13f_to_masters.py             # commits
    py scripts/etl/match_sec_13f_to_masters.py --dry-run   # preview, rolls back

Run time: ~30-90 seconds (the trigram pass is the long part).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


DDL_TABLE = """
DROP TABLE IF EXISTS sec_13f_issuer_master_map CASCADE;
CREATE TABLE sec_13f_issuer_master_map (
    name_of_issuer_norm TEXT PRIMARY KEY,
    master_id           INTEGER NOT NULL,
    canonical_name      TEXT NOT NULL,
    match_method        TEXT NOT NULL,
    match_confidence    NUMERIC(4, 3) NOT NULL,
    matched_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sec_13f_issuer_map_master ON sec_13f_issuer_master_map (master_id);
"""


def run(dry_run: bool = False) -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Codex 2026-05-02 finding #2 fix: keep DDL inside the transaction
        # so --dry-run actually rolls back the schema reset. Postgres
        # supports DDL inside transactions (DROP TABLE IF EXISTS + CREATE
        # TABLE both transactional). Previous version ran them in
        # autocommit, so --dry-run silently destroyed the existing map.
        cur.execute(DDL_TABLE)

        # Step 1: Stage candidate masters (those with SEC source link).
        # We add canonical_name_norm with the same normalization the 13F
        # loader applied to issuers, so the match is apples-to-apples.
        print("Staging candidate masters (SEC-linked)...")
        cur.execute("DROP TABLE IF EXISTS tmp_sec_master_candidates")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_sec_master_candidates AS
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
                ) AS canonical_norm
            FROM master_employers m
            WHERE EXISTS (
                SELECT 1 FROM master_employer_source_ids sid
                WHERE sid.master_id = m.master_id
                  AND sid.source_system = 'sec'
            )
            """
        )
        cur.execute("CREATE INDEX ON tmp_sec_master_candidates (canonical_norm)")
        cur.execute("CREATE INDEX ON tmp_sec_master_candidates USING gin (canonical_norm gin_trgm_ops)")
        cur.execute("SELECT COUNT(*) FROM tmp_sec_master_candidates")
        n_candidates = cur.fetchone()[0]
        print(f"  {n_candidates:,} candidate masters")

        # Step 2: Stage distinct issuers.
        # Codex 2026-05-02 finding #1 fix: do NOT second-pass-strip suffixes
        # here. The loader's _norm_issuer already stripped one suffix, so
        # `name_of_issuer_norm` is the canonical form stored in
        # sec_13f_holdings. If we strip again here, the map's key
        # ("apple") won't equality-join back to holdings ("apple inc"),
        # and the endpoint reports `is_matched=true` but zero holdings
        # for any issuer that had two strippable suffixes (e.g.
        # "X Inc Holdings"). Use name_of_issuer_norm directly.
        print("Staging distinct 13F issuers...")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_13f_issuers AS
            SELECT DISTINCT name_of_issuer_norm AS issuer_norm
            FROM sec_13f_holdings
            WHERE name_of_issuer_norm IS NOT NULL
              AND length(name_of_issuer_norm) >= 3
            """
        )
        cur.execute("SELECT COUNT(*) FROM tmp_13f_issuers")
        n_issuers = cur.fetchone()[0]
        print(f"  {n_issuers:,} distinct issuers")

        # Step 3: Tier A -- exact match.
        print("Matching tier A (exact)...")
        t0 = time.time()
        cur.execute(
            """
            INSERT INTO sec_13f_issuer_master_map
                (name_of_issuer_norm, master_id, canonical_name,
                 match_method, match_confidence)
            SELECT DISTINCT ON (i.issuer_norm)
                i.issuer_norm,
                c.master_id,
                c.canonical_name,
                'exact',
                1.000
            FROM tmp_13f_issuers i
            JOIN tmp_sec_master_candidates c
              ON c.canonical_norm = i.issuer_norm
            ORDER BY i.issuer_norm, c.master_id
            ON CONFLICT (name_of_issuer_norm) DO NOTHING
            """
        )
        n_exact = cur.rowcount or 0
        print(f"  +{n_exact:,} exact matches ({time.time()-t0:.0f}s)")

        # Step 4: Tier B -- trigram similarity for the rest.
        # The pg_trgm threshold default is 0.3; we set 0.85 here to keep
        # signal-to-noise high. We use the % operator with set_limit().
        print("Matching tier B (trigram >= 0.85)...")
        t1 = time.time()
        cur.execute("SELECT set_limit(0.85)")
        cur.execute(
            """
            INSERT INTO sec_13f_issuer_master_map
                (name_of_issuer_norm, master_id, canonical_name,
                 match_method, match_confidence)
            SELECT DISTINCT ON (i.issuer_norm)
                i.issuer_norm,
                c.master_id,
                c.canonical_name,
                'trigram',
                round(similarity(c.canonical_norm, i.issuer_norm)::numeric, 3)
            FROM tmp_13f_issuers i
            JOIN tmp_sec_master_candidates c
              ON c.canonical_norm % i.issuer_norm
            WHERE NOT EXISTS (
                SELECT 1 FROM sec_13f_issuer_master_map m
                WHERE m.name_of_issuer_norm = i.issuer_norm
            )
            ORDER BY i.issuer_norm, similarity(c.canonical_norm, i.issuer_norm) DESC, c.master_id
            ON CONFLICT (name_of_issuer_norm) DO NOTHING
            """
        )
        n_trigram = cur.rowcount or 0
        print(f"  +{n_trigram:,} trigram matches ({time.time()-t1:.0f}s)")

        # Stats
        cur.execute("SELECT COUNT(*) FROM sec_13f_issuer_master_map")
        n_total = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(DISTINCT master_id) FROM sec_13f_issuer_master_map"
        )
        n_masters = cur.fetchone()[0]
        coverage_pct = (n_total / n_issuers * 100) if n_issuers else 0
        print()
        print(f"TOTAL: {n_total:,} of {n_issuers:,} issuers matched ({coverage_pct:.1f}%)")
        print(f"       across {n_masters:,} distinct masters.")

        # Top matches sample. Note: the project's default cursor returns
        # tuples (not RealDictCursor); index by position.
        print("\nSample top matches (by master holdings count):")
        cur.execute(
            """
            SELECT m.canonical_name, m.master_id, m.match_method, m.match_confidence,
                   COUNT(h.id) AS holdings
            FROM sec_13f_issuer_master_map m
            JOIN sec_13f_holdings h ON h.name_of_issuer_norm = m.name_of_issuer_norm
            GROUP BY m.canonical_name, m.master_id, m.match_method, m.match_confidence
            ORDER BY holdings DESC
            LIMIT 8
            """
        )
        for r in cur.fetchall():
            canonical_name, master_id, method, conf, holdings = r
            name_disp = (canonical_name or "")[:40]
            print(
                f"  master={master_id:<8d} {name_disp:<40s} "
                f"method={method:<8s} conf={conf} holdings={holdings:,}"
            )

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
