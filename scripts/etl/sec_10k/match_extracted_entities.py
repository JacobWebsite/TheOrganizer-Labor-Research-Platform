"""Match SEC 10-K extracted entity mentions to master_employers.

Bridges Agent 1's heuristic-extracted entity mentions (suppliers /
customers / distribution partners pulled from 10-K text) to our
master_employers universe so the API can surface relationship
networks (24Q-16 Suppliers, 24Q-19 Customers, 24Q-17 Distribution).

Pipeline (per extracted entity row):
  1. Resolve parent_master_id from filer's CIK via
     master_employer_source_ids (source_system='sec').
  2. Cascade against master_employers:
       Tier A -- exact:        normalize(entity_text) == canonical_name
       Tier B -- alias:        entity_text matches an entry in
                                config/employer_aliases.json (and the
                                alias-collision exclude_terms guard
                                rules out false positives like
                                Cleveland-Cliffs vs Cleveland Clinic)
       Tier C -- trigram:      pg_trgm similarity >= 0.85 against
                                canonical_name; uses the existing GIN
                                index idx_master_employers_canonical_name_trgm
       Tier D -- unmatched:    insert with child_master_id=NULL so the
                                API can still display the entity name
                                as a textual mention (no link).
  3. Insert into sec_10k_relationship_links with ON CONFLICT DO NOTHING
     so the script is idempotent and can be re-run safely.

Reuses existing helpers:
  - src/python/matching/name_normalization.normalize_name_aggressive
    for matching against master_employers.canonical_name (which is
    already aggressive-stripped lowercase).
  - api/routers/employers._load_aliases() pattern for alias-collision
    guard (matches the rematch executor's R7-7 logic).

Sample-only run by default (--limit 100). Full pipeline deferred until
Agent 1 finishes loading sec_10k_extracted_entities at scale.

Usage:
    py scripts/etl/sec_10k/match_extracted_entities.py
    py scripts/etl/sec_10k/match_extracted_entities.py --limit 500
    py scripts/etl/sec_10k/match_extracted_entities.py --commit \\
        --report-csv docs/scratch/sec_10k_matches_sample.csv

ASCII-only print output (Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection  # noqa: E402

# Canonical normalizer (single source of truth) -- src/python/matching
from src.python.matching.name_normalization import (  # noqa: E402
    normalize_name_aggressive,
)


# ---------------------------------------------------------------------------
# DDL: output table for relationship links
# ---------------------------------------------------------------------------
# Note: parent/child master_id are BIGINT (master_employers PK type).
# child_master_id is NULL when no match -- enforces only that the entity
# was extracted and resolved against the source filer; it does NOT
# enforce that we found a matching internal entity.
# UNIQUE constraint is on (source_entity_id, relationship_type) -- one
# relationship row per extracted entity. The earlier 4-column constraint
# allowed an entity that was once unmatched (child_master_id=NULL) to
# coexist with a later matched row (child_master_id=42), inflating
# total_extracted. The new constraint plus ON CONFLICT DO UPDATE means
# re-running the matcher upgrades NULL -> matched in place.
DDL = """
CREATE TABLE IF NOT EXISTS sec_10k_relationship_links (
  id BIGSERIAL PRIMARY KEY,
  parent_master_id BIGINT NOT NULL,
  child_master_id BIGINT,
  child_text TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  source_entity_id BIGINT NOT NULL REFERENCES sec_10k_extracted_entities(id) ON DELETE CASCADE,
  confidence NUMERIC(4,3),
  match_method TEXT,
  source_filing_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT sec_10k_relationship_links_entity_type_uq
    UNIQUE (source_entity_id, relationship_type)
);
CREATE INDEX IF NOT EXISTS ix_sec10kl_parent ON sec_10k_relationship_links(parent_master_id, relationship_type);
CREATE INDEX IF NOT EXISTS ix_sec10kl_child ON sec_10k_relationship_links(child_master_id);

-- Migrate older constraint shapes from earlier sessions of this script.
-- Two prior shapes existed: the original 4-column UNIQUE (without NULLS
-- NOT DISTINCT) and the 4-column UNIQUE NULLS NOT DISTINCT variant.
-- Both are wrong because an unmatched->matched upgrade leaks duplicates.
ALTER TABLE sec_10k_relationship_links
  DROP CONSTRAINT IF EXISTS
    sec_10k_relationship_links_parent_master_id_child_master_id_re_key,
  DROP CONSTRAINT IF EXISTS
    sec_10k_relationship_links_parent_master_id_child_master_id_relationship_type_source_entity_id_key;

-- Add the new constraint if it isn't already present. CREATE TABLE
-- IF NOT EXISTS above is a no-op when the table already exists, so the
-- inline UNIQUE never lands on legacy installs -- this block is what
-- actually gets the constraint there.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'sec_10k_relationship_links_entity_type_uq'
  ) THEN
    EXECUTE 'ALTER TABLE sec_10k_relationship_links '
            'ADD CONSTRAINT sec_10k_relationship_links_entity_type_uq '
            'UNIQUE (source_entity_id, relationship_type)';
  END IF;
END $$;
"""

# Map entity section_type -> relationship_type. The extractor in Agent 1
# tags each mention with the section it came from; we translate that into
# a downstream-friendly label. Section types not in this table get a
# best-effort fallback (we map by keyword); unrecognized rows are
# emitted with relationship_type='supplier' as a safe default since
# most 10-K entity mentions surface in supplier-context language.
SECTION_TO_RELATIONSHIP = {
    "suppliers": "supplier",
    "supply_chain": "supplier",
    "customers": "customer",
    "major_customers": "customer",
    "distribution": "distribution",
    "distributors": "distribution",
}

# ---------------------------------------------------------------------------
# Alias loader (mirrors api/routers/employers.py::_load_aliases pattern)
# ---------------------------------------------------------------------------
_ALIAS_PATH = PROJECT_ROOT / "config" / "employer_aliases.json"
_ALIAS_CACHE: list[dict] | None = None


def load_aliases() -> list[dict]:
    """Read config/employer_aliases.json. Fail-open: empty list if the
    file is missing or malformed. Same shape the search endpoint uses
    so the alias-collision guard stays in sync."""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        _ALIAS_CACHE = []
        try:
            data = json.loads(_ALIAS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return _ALIAS_CACHE
        if isinstance(data, dict):
            entries = data.get("aliases", [])
            if isinstance(entries, list):
                _ALIAS_CACHE = [e for e in entries if isinstance(e, dict)]
    return _ALIAS_CACHE


def alias_lookup(entity_text: str, aliases: list[dict]) -> tuple[str, list[str]] | None:
    """If entity_text matches an alias entry, return (canonical_name,
    exclude_terms). Otherwise None.

    Match rule: if any alias substring appears in lowered entity_text.
    Exact opposite of the search endpoint's "user query matches alias"
    semantics, but the inputs are symmetric -- both directions ask
    "does this text reference this canonical org?".
    """
    if not entity_text:
        return None
    text_lc = entity_text.lower()
    for entry in aliases:
        for alias in entry.get("aliases", []):
            if alias and alias in text_lc:
                return (
                    entry.get("canonical_name", ""),
                    [e.lower() for e in entry.get("exclude_terms", [])],
                )
    return None


def alias_collision_guard(entity_text: str, master_canonical: str,
                          exclude_terms: list[str]) -> bool:
    """True if the candidate master_canonical contains any of the
    exclude_terms. This catches the Cleveland Clinic -> Cleveland-Cliffs
    case (entity_text='cleveland clinic' should NOT match a master row
    whose canonical_name contains 'cleveland-cliffs').
    """
    if not exclude_terms:
        return False
    canonical_lc = (master_canonical or "").lower()
    return any(excl in canonical_lc for excl in exclude_terms)


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def resolve_filer_to_master(cur, cik: Any) -> int | None:
    """CIK -> master_id via master_employer_source_ids.source_system='sec'.

    cik may arrive as int (sec_10k_extracted_entities.cik is BIGINT) but
    master_employer_source_ids.source_id is TEXT, so cast to text.
    Returns the FIRST master_id (lowest by tie-break order) since a CIK
    can occasionally map to multiple master rows from prior dedup mistakes.
    """
    if cik is None:
        return None
    cur.execute(
        """
        SELECT master_id
          FROM master_employer_source_ids
         WHERE source_system = 'sec'
           AND source_id = %s
         ORDER BY master_id
         LIMIT 1
        """,
        (str(cik),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return int(row[0] if isinstance(row, tuple) else row["master_id"])


def lookup_filing_date(cur, cik: Any, accession: str) -> Any:
    """Pull filing_date from sec_10k_filings_to_download. May be NULL."""
    if cik is None or not accession:
        return None
    cur.execute(
        """
        SELECT filing_date
          FROM sec_10k_filings_to_download
         WHERE cik = %s AND accession = %s
         LIMIT 1
        """,
        (int(cik), accession),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row[0] if isinstance(row, tuple) else row["filing_date"]


# ---------------------------------------------------------------------------
# Match cascade
# ---------------------------------------------------------------------------

def _looks_like_company(text: str) -> bool:
    """Quick guard against obvious non-company strings (page numbers,
    section headings, single short tokens, dollar amounts, etc.).
    Trigram against `'1'` or `'see note 5'` against 4M masters wastes
    cycles and produces noise.
    """
    if not text:
        return False
    t = text.strip()
    if len(t) < 4:
        return False
    if t.isdigit():
        return False
    # Must contain at least 1 letter
    if not re.search(r"[A-Za-z]", t):
        return False
    return True


def match_entity(cur, entity_text: str, aliases: list[dict],
                 trigram_floor: float = 0.85) -> tuple[int | None, float, str]:
    """Run the cascade. Returns (master_id_or_None, confidence, method).

    method values: 'exact' | 'alias' | 'trigram' | 'unmatched'
    """
    if not _looks_like_company(entity_text):
        return (None, 0.0, "unmatched")

    # ------------------------------------------------------------------
    # Tier B: alias dictionary (run BEFORE exact so that "Cleveland
    # Clinic" routes to Cleveland Clinic Foundation even when the
    # canonical_name also contains "foundation"). The alias-collision
    # guard then prevents Cleveland-Cliffs from sneaking in.
    # ------------------------------------------------------------------
    alias_hit = alias_lookup(entity_text, aliases)
    exclude_terms: list[str] = []
    if alias_hit is not None:
        canonical_name, exclude_terms = alias_hit
        # Look up the master row for this canonical_name. We re-normalize
        # it through the same aggressive function we use on the entity,
        # then equality-match against canonical_name (which IS aggressive
        # form already, per the master_employers DDL convention).
        canonical_norm = normalize_name_aggressive(canonical_name)
        if canonical_norm:
            cur.execute(
                """
                SELECT master_id, canonical_name
                  FROM master_employers
                 WHERE canonical_name = %s
                 ORDER BY master_id
                 LIMIT 1
                """,
                (canonical_norm,),
            )
            row = cur.fetchone()
            if row:
                mid = row[0] if isinstance(row, tuple) else row["master_id"]
                cname = row[1] if isinstance(row, tuple) else row["canonical_name"]
                # Sanity check: even though we picked a canonical_name
                # explicitly, run the exclude_terms guard so a bug
                # in the alias config can't slip a collision through.
                if not alias_collision_guard(entity_text, cname, exclude_terms):
                    return (int(mid), 1.0, "alias")

    # ------------------------------------------------------------------
    # Tier A: exact normalized match. Use the aggressive form because
    # master_employers.canonical_name is stored that way.
    # ------------------------------------------------------------------
    norm_agg = normalize_name_aggressive(entity_text)
    if norm_agg and len(norm_agg) >= 4:
        cur.execute(
            """
            SELECT master_id, canonical_name
              FROM master_employers
             WHERE canonical_name = %s
             ORDER BY master_id
             LIMIT 1
            """,
            (norm_agg,),
        )
        row = cur.fetchone()
        if row:
            mid = row[0] if isinstance(row, tuple) else row["master_id"]
            cname = row[1] if isinstance(row, tuple) else row["canonical_name"]
            if not alias_collision_guard(entity_text, cname, exclude_terms):
                return (int(mid), 1.0, "exact")

    # ------------------------------------------------------------------
    # Tier C: trigram via pg_trgm (uses the existing GIN index).
    # We set the per-session similarity floor with set_limit() so the
    # `%` operator returns only candidates above 0.85. Take the top 5
    # (similarity DESC, master_id ASC for stable ties), then run the
    # alias-collision guard before accepting.
    # ------------------------------------------------------------------
    if norm_agg and len(norm_agg) >= 4:
        cur.execute("SELECT set_limit(%s)", (float(trigram_floor),))
        cur.execute(
            """
            SELECT master_id, canonical_name,
                   similarity(canonical_name, %s) AS sim
              FROM master_employers
             WHERE canonical_name %% %s
             ORDER BY sim DESC, master_id ASC
             LIMIT 5
            """,
            (norm_agg, norm_agg),
        )
        for row in cur.fetchall() or []:
            if isinstance(row, tuple):
                mid, cname, sim = row
            else:
                mid, cname, sim = row["master_id"], row["canonical_name"], row["sim"]
            if alias_collision_guard(entity_text, cname, exclude_terms):
                continue
            return (int(mid), float(sim), "trigram")

    return (None, 0.0, "unmatched")


def section_to_relationship(section_type: str) -> str:
    """Map section_type -> relationship_type. Fallback: 'supplier'."""
    if not section_type:
        return "supplier"
    s = section_type.strip().lower()
    if s in SECTION_TO_RELATIONSHIP:
        return SECTION_TO_RELATIONSHIP[s]
    # Substring fallback for variants like 'item_1_business_suppliers'
    for k, v in SECTION_TO_RELATIONSHIP.items():
        if k in s:
            return v
    return "supplier"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def fetch_entities(cur, limit: int | None) -> list[dict]:
    """Read N rows from sec_10k_extracted_entities. Returns dicts."""
    sql = """
        SELECT id, accession_number, cik, section_type, entity_text,
               context, position_offset, created_at
          FROM sec_10k_extracted_entities
         ORDER BY id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    cols = [d.name for d in cur.description]
    return [
        rec if isinstance(rec, dict) else dict(zip(cols, rec))
        for rec in cur.fetchall() or []
    ]


def insert_link(cur, parent_id: int, child_id: int | None, child_text: str,
                rel_type: str, source_entity_id: int, confidence: float,
                match_method: str, filing_date: Any) -> bool:
    """Idempotent insert keyed on (source_entity_id, relationship_type).

    On conflict, UPDATE so a previously unmatched row (child_master_id=NULL,
    method='unmatched') gets upgraded to a matched row in place when the
    matcher is re-run with new alias / trigram coverage.

    Returns True if a NEW row was written, False if the conflict path ran.
    """
    cur.execute(
        """
        INSERT INTO sec_10k_relationship_links (
          parent_master_id, child_master_id, child_text,
          relationship_type, source_entity_id,
          confidence, match_method, source_filing_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT sec_10k_relationship_links_entity_type_uq
        DO UPDATE SET
          parent_master_id   = EXCLUDED.parent_master_id,
          child_master_id    = EXCLUDED.child_master_id,
          child_text         = EXCLUDED.child_text,
          confidence         = EXCLUDED.confidence,
          match_method       = EXCLUDED.match_method,
          source_filing_date = EXCLUDED.source_filing_date
        WHERE
          -- Only overwrite when the new row improves the match. Avoids
          -- regressing a real match back to 'unmatched' on a re-run that
          -- happens to sample fewer aliases.
          sec_10k_relationship_links.match_method = 'unmatched'
          OR EXCLUDED.match_method <> 'unmatched'
        RETURNING (xmax = 0) AS inserted
        """,
        (parent_id, child_id, child_text, rel_type, source_entity_id,
         round(confidence, 3) if confidence else None, match_method, filing_date),
    )
    row = cur.fetchone()
    if row is None:
        # The WHERE on the UPDATE branch suppressed both insert and update.
        return False
    # psycopg2 dict-cursor returns a mapping; tuple-cursor returns a tuple.
    inserted = row[0] if not isinstance(row, dict) else row.get("inserted")
    return bool(inserted)


def run(limit: int | None, commit: bool, report_csv: str | None,
        trigram_floor: float = 0.85) -> dict:
    """Main entry point. Returns a stats dict."""
    print("=" * 70)
    print("SEC 10-K EXTRACTED ENTITY MATCHER")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    # Confirm input table exists (Agent 1 may not have finished yet).
    cur.execute(
        "SELECT to_regclass('public.sec_10k_extracted_entities')"
    )
    if cur.fetchone()[0] is None:
        print("INPUT TABLE MISSING: sec_10k_extracted_entities does not exist.")
        print("  Agent 1 has not yet created the table. Aborting.")
        cur.close()
        conn.close()
        return {"error": "input_table_missing"}

    # CREATE TABLE IF NOT EXISTS for the output (idempotent)
    cur.execute(DDL)
    conn.commit()
    print("Output table sec_10k_relationship_links ready.")

    aliases = load_aliases()
    print(f"Loaded {len(aliases)} alias entries from {_ALIAS_PATH.name}")

    rows = fetch_entities(cur, limit)
    if not rows:
        print("No rows in sec_10k_extracted_entities. Nothing to match.")
        cur.close()
        conn.close()
        return {"rows_in": 0}
    print(f"Read {len(rows):,} extracted entity rows (limit={limit}).")
    print()

    # Stats accumulators
    stats = {
        "rows_in":        len(rows),
        "rows_written":   0,
        "rows_skipped":   0,            # filer CIK didn't resolve
        "rows_dup":       0,            # ON CONFLICT short-circuited
        "by_method":      {"exact": 0, "alias": 0, "trigram": 0, "unmatched": 0},
        "by_relationship": {},
        "examples_match": [],           # 10 successful matches for the report
        "examples_miss":  [],           # 10 unmatched rows for the report
    }

    # Cache: cik -> master_id (a single 10-K has thousands of mentions
    # for the same parent; one lookup is enough)
    parent_cache: dict[Any, int | None] = {}
    filing_cache: dict[tuple, Any] = {}

    t0 = time.time()
    for i, ent in enumerate(rows):
        eid = ent["id"]
        cik = ent.get("cik")
        accession = ent.get("accession_number") or ""
        text = (ent.get("entity_text") or "").strip()
        section = ent.get("section_type") or ""

        # Cache filer resolution per CIK
        if cik in parent_cache:
            parent_id = parent_cache[cik]
        else:
            parent_id = resolve_filer_to_master(cur, cik)
            parent_cache[cik] = parent_id

        if parent_id is None:
            # Filer CIK has no master link -- can't anchor the
            # relationship. Skip with a stat tick rather than write
            # an orphan row. (Re-run later after seed_master_sec.py.)
            stats["rows_skipped"] += 1
            continue

        # Cache filing-date lookup per (cik, accession)
        cache_key = (cik, accession)
        if cache_key in filing_cache:
            filing_date = filing_cache[cache_key]
        else:
            filing_date = lookup_filing_date(cur, cik, accession)
            filing_cache[cache_key] = filing_date

        rel_type = section_to_relationship(section)
        match_id, confidence, method = match_entity(cur, text, aliases, trigram_floor)

        stats["by_method"][method] = stats["by_method"].get(method, 0) + 1
        stats["by_relationship"][rel_type] = stats["by_relationship"].get(rel_type, 0) + 1

        # Sample collection for the scratch report
        if method != "unmatched" and len(stats["examples_match"]) < 10:
            stats["examples_match"].append({
                "entity_text": text,
                "method":      method,
                "confidence":  round(confidence, 3),
                "child_id":    match_id,
                "rel_type":    rel_type,
            })
        elif method == "unmatched" and len(stats["examples_miss"]) < 10:
            stats["examples_miss"].append({
                "entity_text": text,
                "rel_type":    rel_type,
            })

        wrote = insert_link(
            cur, parent_id, match_id, text, rel_type, eid,
            confidence, method, filing_date,
        )
        if wrote:
            stats["rows_written"] += 1
        else:
            stats["rows_dup"] += 1

        if (i + 1) % 100 == 0:
            print(f"  ... processed {i + 1:,} rows; "
                  f"matched={stats['by_method']['exact'] + stats['by_method']['alias'] + stats['by_method']['trigram']:,}, "
                  f"unmatched={stats['by_method']['unmatched']:,}")

    if commit:
        conn.commit()
        print(f"\nCommitted {stats['rows_written']:,} new rows.")
    else:
        conn.rollback()
        print(f"\nDRY-RUN: rolled back. Would have written "
              f"{stats['rows_written']:,} new rows.")

    print(f"\nElapsed: {time.time() - t0:.1f}s")
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    matched = sum(stats["by_method"].get(k, 0)
                  for k in ("exact", "alias", "trigram"))
    in_scope = stats["rows_in"] - stats["rows_skipped"]
    rate_pct = (100 * matched / in_scope) if in_scope else 0.0
    print(f"  rows_in:           {stats['rows_in']:,}")
    print(f"  rows_skipped (no filer master_id): {stats['rows_skipped']:,}")
    print(f"  in-scope:          {in_scope:,}")
    print(f"  matched (link to a master): {matched:,} ({rate_pct:.1f}%)")
    print(f"  rows_written:      {stats['rows_written']:,}")
    print(f"  rows_dup (ON CONFLICT): {stats['rows_dup']:,}")
    print()
    print("  by method:")
    for k in ("exact", "alias", "trigram", "unmatched"):
        print(f"    {k:<10} {stats['by_method'].get(k, 0):>6,}")
    print()
    print("  by relationship_type:")
    for k, v in sorted(stats["by_relationship"].items(), key=lambda x: -x[1]):
        print(f"    {k:<14} {v:>6,}")

    # Optional CSV report (kept lightweight; full report goes in scratch md)
    if report_csv:
        import csv
        with open(report_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "entity_text", "method", "confidence", "child_id", "rel_type"
            ])
            w.writeheader()
            for r in stats["examples_match"]:
                w.writerow(r)
        print(f"\nWrote sample CSV: {report_csv}")

    cur.close()
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Match SEC 10-K extracted entities to master_employers"
    )
    parser.add_argument("--limit", type=int, default=100,
                        help="Max entity rows to process (default 100, sample)")
    parser.add_argument("--commit", action="store_true",
                        help="Commit writes (default: dry-run, rolled back)")
    parser.add_argument("--report-csv", type=str, default=None,
                        help="Optional path for sample-match CSV")
    parser.add_argument("--trigram-floor", type=float, default=0.85,
                        help="pg_trgm similarity floor (default 0.85)")
    args = parser.parse_args()
    run(limit=args.limit, commit=args.commit, report_csv=args.report_csv,
        trigram_floor=args.trigram_floor)


if __name__ == "__main__":
    main()
