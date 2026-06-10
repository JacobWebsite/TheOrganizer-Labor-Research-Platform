"""F7 orphan rematch executor (Week 2 / B.3.x of the launch roadmap).

DRY-RUN BY DEFAULT. Writes nothing to the database.

Consumes the `_recoverable_f7_orphans` staging table built by
`identify_recoverable_orphans.py` (currently 15,537 candidates -- F7
employers that had a Splink-era match in the past, were superseded
when V2 retired Splink, and now have NO active match in any source).

For each candidate, attempts to find the best new match in each of
4 source systems (OSHA, WHD, 990, SAM) using V2-cascade methods at
the SQL layer:

    Tier  Method                          Confidence
    ----  ------------------------------  ----------
     1    NAME_STANDARD_STATE_ZIP_EXACT   1.00
     2    NAME_STANDARD_STATE_EXACT       0.98
     3    NAME_AGGRESSIVE_STATE_EXACT     0.92
     4    NAME_STANDARD_STATE_TRIGRAM     0.85-0.99 (deferred)

Every candidate is then run through the Haiku-distilled rule engine
(`scripts/llm_dedup/rule_engine.py::classify_pair_v2`, validated
against 31,532 Haiku-labeled pairs) which:
  * VETOES tier_series_demoted matches (H4 series fragments + reversed
    person-name pairs that the SQL can't see)
  * UPGRADES scores when tier_A or tier_B rules fire (e.g.,
    NAME_AGGRESSIVE 0.92 lifts to 0.96 when H16 source-diverse-address
    + H1 punctuation-invariant both fire)
  * ROUTES tier_C matches to a separate review-queue CSV instead of
    auto-writing them on --commit
  * TAGS every kept match with rule_engine_tier + rule_engine_rule +
    rule_engine_precision so the audit trail shows WHY each write
    happened

The best match across sources, per orphan, becomes the recommended
write. Per-source counts + sample matches at each tier go into a
CSV + summary report for review.

Usage (DRY-RUN, default — rule engine ON):
    py scripts/matching/rematch_recoverable_orphans.py
    py scripts/matching/rematch_recoverable_orphans.py --limit 1000
    py scripts/matching/rematch_recoverable_orphans.py \\
        --out-csv /tmp/orphan_rematch.csv \\
        --review-csv /tmp/orphan_rematch_review.csv

Usage (DIFF against the 2026-05-06 baseline run with rule engine off):
    py scripts/matching/rematch_recoverable_orphans.py --no-rule-engine

Usage (COMMIT, gated -- requires Jacob review of dry-run report first):
    py scripts/matching/rematch_recoverable_orphans.py --commit \\
        --min-score 0.96 \\
        --out-csv /tmp/orphan_rematch.csv

The --commit flag writes one unified_match_log row per matched orphan
with status='active', match_method=the V2 method that fired,
confidence_score=score (possibly upgraded by the rule engine), and
evidence carrying both the V2 method and the rule_engine verdict.
Conflict resolution: if an orphan already has an active match by the
time --commit runs (race with another rematch), the new write is
skipped, NOT overwritten — enforced inside a single
INSERT...SELECT...WHERE NOT EXISTS statement.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db_config import get_connection

# scripts/llm_dedup/rule_engine.py — Haiku-distilled rule engine
# (calibrated against 31,532 Haiku-labeled pairs from the 2026-04-16 NY
# singleton batch; H1-H16 + person-name demoter + EIN-conflict veto).
# Imported here so the rematch executor classifies every SQL-cascade
# candidate through the same engine that runs in the master-pair LLM
# dedup pipeline — eliminates the gap Jacob flagged: "are we using
# the logic we distilled from the anthropic api runs?" (B.3.x Option C
# integration, 2026-05-08).
from scripts.llm_dedup.rule_engine import classify_pair_v2  # noqa: E402,F401


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

# Sources to attempt matching against. Each entry:
#   (key, table, name_normalized_col, state_col, zip_col,
#    display_col, city_col, ein_col)
#
# display_col, city_col, ein_col were added 2026-05-08 (B.3.x Option C)
# so we can pull the additional fields the rule engine needs for H1-H16
# evaluation. ein_col is None for sources that don't carry a federal
# tax ID (OSHA, WHD, SAM) — the rule engine handles missing EINs by
# simply not firing H13 / not vetoing on EIN conflict.
#
# Order matters only for tie-breaking (sources earlier in the list win
# at equal score; OSHA first because it's the highest-recovery source
# per the F7 Orphan Rate Open Problem note).
SOURCES = [
    ("osha",  "osha_establishments", "estab_name_normalized",   "site_state",     "site_zip",
        "estab_name",          "site_city",      None),
    ("whd",   "whd_cases",           "name_normalized",         "state",          "zip_code",
        "trade_name",          "city",           None),
    ("990",   "national_990_filers", "name_normalized",         "state",          "zip_code",
        "business_name",       "city",           "ein"),
    ("sam",   "sam_entities",        "name_normalized",         "physical_state", "physical_zip",
        "legal_business_name", "physical_city",  None),
]

# Source-record-id columns by source.
SOURCE_ID_COL = {
    "osha": "establishment_id",
    "whd":  "case_id",
    "990":  "ein",
    "sam":  "uei",
}

# V2-cascade method tiers. Score is the floor we ASSIGN at write time
# (not a similarity threshold to filter on). Tiers are evaluated in
# order; first hit wins per (orphan, source) pair.
TIERS = [
    {
        "method": "NAME_STANDARD_STATE_ZIP_EXACT",
        "score": 1.00,
        "where": "f.name_standard = LOWER(s.{name_col}) AND f.state = s.{state_col} AND f.zip = s.{zip_col}",
        "requires_zip": True,
    },
    {
        "method": "NAME_STANDARD_STATE_EXACT",
        "score": 0.98,
        "where": "f.name_standard = LOWER(s.{name_col}) AND f.state = s.{state_col}",
        "requires_zip": False,
    },
    {
        "method": "NAME_AGGRESSIVE_STATE_EXACT",
        "score": 0.92,
        "where": "f.name_aggressive = LOWER(s.{name_col}) AND f.state = s.{state_col}",
        "requires_zip": False,
    },
    # Tier 4 (trigram) lives in attempt_match_trigram_fallback() and runs
    # only when --enable-trigram is passed. Off by default because it
    # adds combinatorial cost; on by request, it processes only the
    # ORPHANS THAT GOT NO MATCH from the 3 SQL exact tiers (~14,353 of
    # 15,537 candidates as of 2026-05-08). The rule engine is still
    # applied to every trigram candidate so H4 / person-name vetoes,
    # H16 upgrades, etc. all run the same as for SQL-cascade matches.
]


# ----------------------------------------------------------------------
# Tier 4: in-memory trigram fallback (added 2026-05-08, evening pass).
#
# Mirrors the V2 cascade's `_fuzzy_batch_inmemory_trigram` pattern from
# scripts/matching/deterministic_matcher.py but inverted: instead of
# matching new source records against F7, we match orphan F7 employers
# against source-system records.
#
# Strategy:
#   - State-block. For each US state, pull ALL source rows from osha,
#     whd, 990, sam at once (one query per source per state) and build
#     an in-memory trigram inverted index keyed on the source side's
#     normalized name column.
#   - For each orphan F7 employer in that state, compute character
#     trigrams of its `name_aggressive`, find candidate source rows via
#     the inverted index, score with rapidfuzz composite (token_sort +
#     token_set + JaroWinkler), accept the best per source if score
#     >= TRIGRAM_FLOOR (default 0.85).
#   - Pass each candidate through classify_pair_v2. The same vetoes
#     (H4 series, person-name, EIN-conflict) that protect the SQL-tier
#     candidates also protect trigram candidates.
#   - The score floor at WRITE time is set to 0.85 (probabilistic tier)
#     so the rule engine's UPGRADE rules (H2+H3 -> 0.96, H16 -> 0.96,
#     H2+H6 -> 0.91) lift well-corroborated trigram matches above the
#     0.92 threshold used for the committed run. To be conservative on
#     this evening's run we pass --min-score 0.91 so that ONLY rule-
#     engine-corroborated trigram matches make it to UML.
#
# Per-state runtime estimate: CA holds ~276K source rows; building a
# trigram index over 276K names is ~5-10M index entries (~1 GB peak).
# Index is dropped before moving to next state.
# ----------------------------------------------------------------------

def _char_trigrams(s: str) -> set:
    """Extract character trigrams from a string (matches V2 cascade)."""
    if not s:
        return set()
    s = " " + s + " "
    return {s[i:i+3] for i in range(len(s) - 2)}


def attempt_match_trigram_fallback(cur, unmatched_orphan_ids, args):
    """Run state-blocked in-memory trigram matching for orphans the SQL
    exact-match tiers missed.

    `unmatched_orphan_ids` is the set of F7 employer_ids to process
    (those with NO match from Tiers 1-3). For each, we look across all
    4 sources for the best trigram-similar source row in the same
    state.

    Returns a list of match dicts with the same shape as attempt_match()
    so the downstream rule-engine pass and best-by-orphan dedup work
    unchanged.
    """
    if not unmatched_orphan_ids:
        return []
    try:
        from rapidfuzz import fuzz as _rf_fuzz
        from rapidfuzz.distance import JaroWinkler as _JW
    except ImportError:
        print("  Tier 4: rapidfuzz unavailable, skipping trigram fallback")
        return []

    floor = args.trigram_floor
    print(f"  Tier 4 trigram fallback: floor={floor:.2f}, "
          f"unmatched orphan pool={len(unmatched_orphan_ids):,}")

    # Pull orphan F7 details once -- normalized names + state + zip + city.
    placeholders = ",".join(["%s"] * len(unmatched_orphan_ids))
    cur.execute(f"""
        SELECT employer_id, employer_name, name_aggressive, name_standard,
               state, zip, city
          FROM f7_employers_deduped
         WHERE employer_id IN ({placeholders})
           AND state IS NOT NULL
           AND name_aggressive IS NOT NULL AND name_aggressive <> ''
    """, list(unmatched_orphan_ids))
    orphans_by_state: dict[str, list[dict]] = {}
    for r in cur.fetchall() or []:
        rd = r if isinstance(r, dict) else dict(zip([d.name for d in cur.description], r))
        st = (rd.get("state") or "").strip()
        if not st:
            continue
        orphans_by_state.setdefault(st, []).append({
            "f7_employer_id":   rd["employer_id"],
            "f7_name":          (rd.get("employer_name") or "").strip(),
            "f7_name_agg":      (rd.get("name_aggressive") or "").lower(),
            "f7_name_std":      (rd.get("name_standard") or "").lower(),
            "f7_state":         st,
            "f7_zip":           rd.get("zip"),
            "f7_city":          rd.get("city"),
        })
    print(f"    Built orphan map: {sum(len(v) for v in orphans_by_state.values()):,} orphans across {len(orphans_by_state):,} states")

    matches: list[dict] = []
    states_sorted = sorted(orphans_by_state.keys())
    for st_idx, state in enumerate(states_sorted, 1):
        orphans = orphans_by_state[state]
        if not orphans:
            continue
        # Pre-compute trigrams of orphan aggressive names
        orphan_tgs = [(_char_trigrams(o["f7_name_agg"]), o) for o in orphans]
        orphan_tgs = [(tgs, o) for tgs, o in orphan_tgs if len(tgs) >= 4]
        if not orphan_tgs:
            continue

        # For each source, pull ALL rows in this state and build inverted
        # trigram index. Match every orphan against this state's pool.
        for source_key, table, name_col, state_col, zip_col, display_col, city_col, ein_col in SOURCES:
            src_id_col = SOURCE_ID_COL[source_key]
            src_display_expr = f"s.{display_col}" if display_col else "NULL"
            src_city_expr    = f"s.{city_col}"    if city_col    else "NULL"
            src_ein_expr     = f"s.{ein_col}"     if ein_col     else "NULL"
            cur.execute(f"""
                SELECT
                    s.{src_id_col}   AS source_id,
                    s.{name_col}     AS source_name_norm,
                    s.{zip_col}      AS source_zip,
                    {src_display_expr} AS source_display,
                    {src_city_expr}    AS source_city,
                    {src_ein_expr}     AS source_ein
                FROM {table} s
                WHERE s.{state_col} = %s
                  AND s.{name_col} IS NOT NULL
                  AND LENGTH(s.{name_col}) >= 4
            """, [state])
            cols = [d.name for d in cur.description]
            rows = cur.fetchall() or []
            if not rows:
                continue

            # Build inverted trigram index for this (state, source) cell
            inv_idx: dict[str, list[int]] = {}
            src_rows: list[dict] = []
            for raw in rows:
                rd = raw if isinstance(raw, dict) else dict(zip(cols, raw))
                if rd.get("source_id") is None or not rd.get("source_name_norm"):
                    continue
                idx = len(src_rows)
                src_rows.append(rd)
                src_name_lc = (rd["source_name_norm"] or "").lower()
                for tg in _char_trigrams(src_name_lc):
                    inv_idx.setdefault(tg, []).append(idx)

            # For each orphan, find best trigram match in this source
            from collections import Counter as _Counter
            for ortgs, orphan in orphan_tgs:
                cand_overlap = _Counter()
                for tg in ortgs:
                    bucket = inv_idx.get(tg)
                    if bucket:
                        for idx in bucket:
                            cand_overlap[idx] += 1
                if not cand_overlap:
                    continue
                # Pre-filter on minimum overlap
                min_overlap = max(4, int(len(ortgs) * 0.4))
                top_candidates = [
                    (idx, cnt) for idx, cnt in cand_overlap.most_common(20)
                    if cnt >= min_overlap
                ][:10]
                if not top_candidates:
                    continue

                best = (0.0, None)
                for idx, _overlap in top_candidates:
                    src_row = src_rows[idx]
                    src_name_lc = (src_row["source_name_norm"] or "").lower()
                    if not src_name_lc:
                        continue
                    # Single-token source names like "concepts" / "freeman"
                    # generate trigram overlaps with longer F7 names (e.g.
                    # "AV Concepts") that score above the floor but are
                    # almost certainly false positives. Require at least
                    # 2 tokens AND length >= 5 on the source name to gate
                    # this out. This trades a small amount of recall for
                    # a meaningful precision bump in the 0.92-0.95 band.
                    if len(src_name_lc) < 5:
                        continue
                    if len(src_name_lc.split()) < 2:
                        continue
                    # Composite score (matches V2 cascade pattern)
                    jw    = _JW.similarity(orphan["f7_name_agg"], src_name_lc)
                    tsr   = _rf_fuzz.token_set_ratio(orphan["f7_name_agg"], src_name_lc) / 100.0
                    ratio = _rf_fuzz.token_sort_ratio(orphan["f7_name_agg"], src_name_lc) / 100.0
                    composite = 0.35 * jw + 0.35 * tsr + 0.30 * ratio
                    if composite > best[0] and composite >= floor:
                        best = (composite, src_row)
                if best[1] is None:
                    continue
                score, src_row = best
                matches.append({
                    "f7_employer_id":   orphan["f7_employer_id"],
                    "f7_name":          orphan["f7_name"],
                    "f7_state":         orphan["f7_state"],
                    "f7_zip":           orphan["f7_zip"],
                    "f7_city":          orphan["f7_city"],
                    "source":           source_key,
                    "source_id":        str(src_row["source_id"]),
                    "source_name_norm": src_row["source_name_norm"],
                    "source_zip":       src_row.get("source_zip"),
                    "source_display":   src_row.get("source_display"),
                    "source_city":      src_row.get("source_city"),
                    "source_ein":       src_row.get("source_ein"),
                    "method":           "TRIGRAM_FALLBACK_STATE",
                    # Floor 0.85 means rule-engine UPGRADES are what
                    # carry trigram matches over commit thresholds.
                    "score":            round(score, 4),
                })
            # Drop the per-state-source index before next iteration
            del inv_idx
            del src_rows
        if st_idx % 10 == 0 or st_idx == len(states_sorted):
            print(f"    Tier 4: {st_idx}/{len(states_sorted)} states processed; "
                  f"{len(matches):,} candidate matches so far")
    return matches


def fetch_orphan_count(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM _recoverable_f7_orphans")
    row = cur.fetchone()
    return int(row[0] if isinstance(row, tuple) else row["count"])


SOURCES_BY_KEY = {
    s[0]: {
        "table":       s[1],
        "name_col":    s[2],
        "state_col":   s[3],
        "zip_col":     s[4],
        "display_col": s[5],
        "city_col":    s[6],
        "ein_col":     s[7],
    }
    for s in SOURCES
}


def attempt_match(cur, source, name_col, state_col, zip_col, tier, limit=None,
                  display_col=None, city_col=None, ein_col=None):
    """Run a single (source, tier) match attempt. Returns list of dicts.

    Pulls the additional fields the rule engine needs (display name, city,
    EIN, source zip) so the post-fetch pass can run classify_pair_v2
    without a second round-trip. Sources missing a column emit NULL.
    """
    if tier.get("requires_zip"):
        zip_filter = "AND f.zip IS NOT NULL AND f.zip <> ''"
    else:
        zip_filter = ""
    where = tier["where"].format(name_col=name_col, state_col=state_col, zip_col=zip_col)
    src_id_col = SOURCE_ID_COL[source]
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    # Optional columns: emit NULL if the source table doesn't carry that field.
    src_display_expr = f"s.{display_col}" if display_col else "NULL"
    src_city_expr    = f"s.{city_col}"    if city_col    else "NULL"
    src_ein_expr     = f"s.{ein_col}"     if ein_col     else "NULL"
    sql = f"""
        SELECT
            f.employer_id        AS f7_employer_id,
            f.employer_name      AS f7_name,
            f.state              AS f7_state,
            f.zip                AS f7_zip,
            f.city               AS f7_city,
            f.name_standard      AS f7_name_standard,
            s.{src_id_col}       AS source_id,
            s.{name_col}         AS source_name_norm,
            s.{state_col}        AS source_state,
            s.{zip_col}          AS source_zip,
            {src_display_expr}   AS source_display,
            {src_city_expr}      AS source_city,
            {src_ein_expr}       AS source_ein
        FROM f7_employers_deduped f
        JOIN _recoverable_f7_orphans o ON o.employer_id = f.employer_id
        JOIN {SOURCES_BY_KEY[source]['table']} s ON {where}
        WHERE f.name_standard IS NOT NULL AND f.state IS NOT NULL
        {zip_filter}
        {limit_clause}
    """
    cur.execute(sql)
    out = []
    for r in cur.fetchall() or []:
        rd = r if isinstance(r, dict) else dict(zip([d.name for d in cur.description], r))
        out.append({
            "f7_employer_id":   rd["f7_employer_id"],
            "f7_name":          (rd.get("f7_name") or "").strip(),
            "f7_state":         rd.get("f7_state"),
            "f7_zip":           rd.get("f7_zip"),
            "f7_city":          rd.get("f7_city"),
            "source":           source,
            "source_id":        str(rd["source_id"]) if rd.get("source_id") is not None else None,
            "source_name_norm": rd.get("source_name_norm"),
            "source_zip":       rd.get("source_zip"),
            "source_display":   rd.get("source_display"),
            "source_city":      rd.get("source_city"),
            "source_ein":       rd.get("source_ein"),
            "method":           tier["method"],
            "score":            tier["score"],
        })
    return out


# ----------------------------------------------------------------------
# Rule engine integration (B.3.x Option C, 2026-05-08)
# ----------------------------------------------------------------------

def _build_rule_engine_pair(match: dict) -> dict:
    """Build the flat dict that classify_pair_v2 expects from a rematch
    candidate. The rule engine was originally designed for master-pair
    classification; the same pair-shape works for F7-orphan ↔ source
    classification because all fields it consults are pair-symmetric.

    Notes on each field:
      - display_name_X / canonical_name_X: rule engine prefers
        canonical_name and falls back to display_name. F7 has no separate
        canonical column, so we set both to the F7 employer_name.
      - source_X: 'f7' vs the foreign source label ('osha', 'whd', '990',
        'sam') -- always different, so H3 (cross-source-corroboration)
        always passes the source-diversity guard.
      - zip5_match: computed from the raw zips. The rule engine consults
        this to gate ZIP-required rules (H6, H9, H11, H12, H15, H16).
      - ein_X: F7 has no EIN, so ein_1 is always None. ein_2 may be set
        for 990 rows. The rule engine handles missing EINs gracefully:
        H13 (EIN match alone) requires both EINs present so it never
        fires here; ein_conflict is also impossible.
      - name_standard_sim / name_aggressive_sim: derived from the V2
        method that fired. NAME_STANDARD_* implies the standard-form
        names matched exactly (sim=1.0); NAME_AGGRESSIVE means
        aggressive matched but standard might not, so we set
        standard_sim=0.85 (above H3's 0.85 floor) and aggressive_sim=1.0.
    """
    method = match.get("method", "")
    if method.startswith("NAME_STANDARD"):
        ns_sim, na_sim = 1.0, 1.0
    elif method.startswith("NAME_AGGRESSIVE"):
        ns_sim, na_sim = 0.85, 1.0
    elif method == "TRIGRAM_FALLBACK_STATE":
        # The trigram tier scores are composite (token_sort + token_set
        # + JaroWinkler). Use the actual score for both name_*_sim so
        # rules that gate on similarity floors (H3 0.85 floor, H13 0.50
        # floor) can fire correctly. This is what enables H3 + H1
        # (-> H14, Tier B) and H16 (-> Tier A) to upgrade trigram
        # matches when the address corroboration is present.
        sc = float(match.get("score") or 0.0)
        ns_sim, na_sim = sc, sc
    else:
        ns_sim, na_sim = 0.0, 0.0
    f7_zip5  = (match.get("f7_zip")     or "")[:5]
    src_zip5 = (match.get("source_zip") or "")[:5]
    zip5_match = 1.0 if (f7_zip5 and src_zip5 and f7_zip5 == src_zip5) else 0.0
    return {
        "display_name_1":      match.get("f7_name") or "",
        "display_name_2":      match.get("source_display") or match.get("source_name_norm") or "",
        "canonical_name_1":    match.get("f7_name") or "",
        "canonical_name_2":    match.get("source_display") or match.get("source_name_norm") or "",
        "source_1":            "f7",
        "source_2":            match.get("source") or "",
        "zip_1":               match.get("f7_zip"),
        "zip_2":               match.get("source_zip"),
        "ein_1":               None,                       # F7 carries no EIN
        "ein_2":               match.get("source_ein"),    # only 990 supplies one
        "city_1":              match.get("f7_city"),
        "city_2":              match.get("source_city"),
        "name_standard_sim":   ns_sim,
        "name_aggressive_sim": na_sim,
        "zip5_match":          zip5_match,
        "ein_match":           0,
        "ein_conflict":        0,
    }


def classify_with_rule_engine(match: dict) -> dict:
    """Apply classify_pair_v2 to a SQL-cascade match candidate.

    Mutates the match dict in place with rule_engine_tier /
    rule_engine_rule / rule_engine_precision. Also UPGRADES the score
    when the rule engine confirms a higher precision than the SQL
    method's static score (e.g., NAME_AGGRESSIVE 0.92 lifts to 0.96
    when H16 source-diverse-address fires).

    Caller policy:
      tier_series_demoted   -> DROP the match (rule engine veto)
      tier_A_auto_merge     -> keep, score upgraded to max(0.96, sql_score)
      tier_B_high_conf      -> keep, score upgraded to max(0.91, sql_score)
      tier_C_review         -> keep in main pool AND ALSO route to the
                               --review-csv file. Note: tier_C still gets
                               written on --commit if its score passes
                               --min-score; the review-csv is a parallel
                               audit artifact, not an additional gate. To
                               write only rule-engine-confirmed matches,
                               set --min-score 0.96 (or higher).
      tier_D_different      -> keep at SQL score (no rule fired but the
                               SQL exact-name match is still strong evidence)
    """
    pair = _build_rule_engine_pair(match)
    classification = classify_pair_v2(pair)
    match["rule_engine_tier"]      = classification.tier
    match["rule_engine_rule"]      = classification.rule or ""
    match["rule_engine_precision"] = classification.expected_precision
    if classification.tier == "tier_A_auto_merge":
        match["score"] = max(match["score"], 0.96)
    elif classification.tier == "tier_B_high_conf":
        match["score"] = max(match["score"], 0.91)
    return match


def run_dry_run(args):
    print("=" * 70)
    print("F7 ORPHAN REMATCH -- DRY RUN")
    print("=" * 70)
    conn = get_connection()
    cur = conn.cursor()

    n_orphans = fetch_orphan_count(cur)
    print(f"\nCandidate orphans: {n_orphans:,}")
    if args.limit:
        print(f"Limited to first {args.limit:,} candidates per (source, tier)")

    all_matches: list[dict] = []
    by_source: dict[str, dict] = {s[0]: {"by_tier": {}, "total": 0} for s in SOURCES}

    t0 = time.time()
    for source_key, _table, name_col, state_col, zip_col, display_col, city_col, ein_col in SOURCES:
        for tier in TIERS:
            ts = time.time()
            matches = attempt_match(
                cur, source_key, name_col, state_col, zip_col, tier, args.limit,
                display_col=display_col, city_col=city_col, ein_col=ein_col,
            )
            took = time.time() - ts
            n_unique_orphans = len({m["f7_employer_id"] for m in matches})
            by_source[source_key]["by_tier"][tier["method"]] = {
                "rows": len(matches),
                "unique_orphans": n_unique_orphans,
                "took_seconds": round(took, 2),
            }
            by_source[source_key]["total"] += n_unique_orphans
            print(f"  {source_key:>5} / {tier['method']:<32} -> {n_unique_orphans:>5} orphans ({len(matches):>5} rows) in {took:>5.1f}s")
            all_matches.extend(matches)
        print()

    # Tier 4: in-memory trigram fallback (added 2026-05-08 evening pass).
    # Only runs when --enable-trigram is passed. Targets ONLY orphans
    # the SQL exact-match tiers missed -- the still-unmatched pool.
    if args.enable_trigram:
        ts = time.time()
        # Build set of orphan IDs that already got at least one SQL match
        sql_matched_ids = {m["f7_employer_id"] for m in all_matches}
        cur.execute("SELECT employer_id FROM _recoverable_f7_orphans")
        all_orphan_ids = {
            (r[0] if isinstance(r, tuple) else r["employer_id"])
            for r in cur.fetchall() or []
        }
        # Subset to those still unmatched AND that don't already have an
        # ACTIVE UML match (e.g., from this morning's committed run).
        # Without this guard a re-run would re-process orphans whose
        # earlier match got committed and create duplicate work.
        if all_orphan_ids:
            placeholders = ",".join(["%s"] * len(all_orphan_ids))
            cur.execute(f"""
                SELECT DISTINCT target_id FROM unified_match_log
                 WHERE target_system='f7' AND status='active'
                   AND target_id IN ({placeholders})
            """, list(all_orphan_ids))
            already_active = {
                (r[0] if isinstance(r, tuple) else r["target_id"])
                for r in cur.fetchall() or []
            }
        else:
            already_active = set()
        unmatched_ids = sorted(all_orphan_ids - sql_matched_ids - already_active)
        if args.limit:
            unmatched_ids = unmatched_ids[: int(args.limit) * 4]
        print(f"\nTier 4 trigram: {len(unmatched_ids):,} orphans to process "
              f"(of {len(all_orphan_ids):,} candidates; "
              f"{len(sql_matched_ids):,} already SQL-matched, "
              f"{len(already_active):,} already active in UML)")
        trigram_matches = attempt_match_trigram_fallback(cur, unmatched_ids, args)
        took = time.time() - ts
        n_unique = len({m["f7_employer_id"] for m in trigram_matches})
        print(f"  Tier 4 trigram total: {n_unique:,} unique orphans "
              f"({len(trigram_matches):,} rows) in {took:.1f}s")
        all_matches.extend(trigram_matches)
        print()

    # Rule engine pass (B.3.x Option C, 2026-05-08).
    # Run the Haiku-distilled engine on every SQL-cascade candidate.
    # Veto on tier_series_demoted; tag the rest. The rule engine is
    # cheap pure-Python so this adds <1s on the full 15K candidate
    # set. Disabled with --no-rule-engine for diff-against-old-runs.
    review_queue: list[dict] = []
    if args.no_rule_engine:
        print("Rule engine: SKIPPED (--no-rule-engine)")
        print()
    else:
        re_t0 = time.time()
        re_counts: dict[str, int] = {
            "tier_series_demoted": 0,
            "tier_A_auto_merge":   0,
            "tier_B_high_conf":    0,
            "tier_C_review":       0,
            "tier_D_different":    0,
        }
        kept_matches: list[dict] = []
        for m in all_matches:
            classify_with_rule_engine(m)
            tier_name = m["rule_engine_tier"]
            re_counts[tier_name] = re_counts.get(tier_name, 0) + 1
            if tier_name == "tier_series_demoted":
                # VETO: H4-series-fragment or person-name false sibling.
                # Drop entirely — these are NEVER real duplicates.
                continue
            if tier_name == "tier_C_review":
                # Keep in main pool but ALSO surface for human review.
                review_queue.append(m)
            kept_matches.append(m)
        all_matches = kept_matches
        print(f"Rule engine pass: {sum(re_counts.values()):,} candidates classified in {time.time() - re_t0:.1f}s")
        for tier_name in ("tier_A_auto_merge", "tier_B_high_conf",
                          "tier_C_review", "tier_D_different",
                          "tier_series_demoted"):
            print(f"  {tier_name:<24} {re_counts[tier_name]:>6,}")
        print(f"  vetoed (dropped): {re_counts['tier_series_demoted']:,}")
        print(f"  review queue:     {len(review_queue):,}")
        print()

    # Best-match-per-orphan: keep highest-score tier; ties broken by
    # source-list order (OSHA wins over WHD wins over 990 wins over SAM).
    source_priority = {s[0]: i for i, s in enumerate(SOURCES)}
    best_by_orphan: dict[str, dict] = {}
    for m in all_matches:
        key = m["f7_employer_id"]
        cur_best = best_by_orphan.get(key)
        # Higher score wins; tie -> earlier source wins
        is_better = (
            cur_best is None
            or m["score"] > cur_best["score"]
            or (m["score"] == cur_best["score"]
                and source_priority[m["source"]] < source_priority[cur_best["source"]])
        )
        if is_better:
            best_by_orphan[key] = m

    print("=" * 70)
    print("\nSUMMARY")
    print("=" * 70)
    print(f"Distinct orphans with at least one candidate match: {len(best_by_orphan):,} / {n_orphans:,} ({100 * len(best_by_orphan) / n_orphans:.1f}%)")
    print()
    print(f"  {'source':<6} {'best-match orphans':>22}  {'best-method break-out':<60}")
    by_source_best: dict[str, dict[str, int]] = {s[0]: {} for s in SOURCES}
    for m in best_by_orphan.values():
        by_source_best[m["source"]][m["method"]] = by_source_best[m["source"]].get(m["method"], 0) + 1
    for src_tuple in SOURCES:
        src = src_tuple[0]
        total = sum(by_source_best[src].values())
        breakdown = ", ".join(f"{meth}: {n}" for meth, n in sorted(by_source_best[src].items(), key=lambda x: -x[1]))
        print(f"  {src:<6} {total:>22,}  {breakdown}")
    print()
    print("Score distribution among best matches:")
    score_bins: dict[str, int] = {}
    for m in best_by_orphan.values():
        bin = f"{m['score']:.2f}"
        score_bins[bin] = score_bins.get(bin, 0) + 1
    for s in sorted(score_bins.keys(), reverse=True):
        print(f"  {s}: {score_bins[s]:,}")

    # Optional CSV output
    if args.out_csv:
        # Keep the original 8 columns at the front (existing schema lock
        # in tests/test_rematch_recoverable_orphans.py). Append rule
        # engine columns at the end so older parsers still work.
        fieldnames = [
            "f7_employer_id", "f7_name", "f7_state",
            "source", "source_id", "source_name_norm",
            "method", "score",
            "rule_engine_tier", "rule_engine_rule", "rule_engine_precision",
        ]
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for m in best_by_orphan.values():
                w.writerow(m)
        print(f"\nWrote best-match CSV: {args.out_csv} ({len(best_by_orphan):,} rows)")

    # Optional review-queue CSV (rule_engine_tier == 'tier_C_review').
    # These are matches the rule engine flagged for human spot-check —
    # they pass the SQL exact-match floor but have weaker rule
    # corroboration. Don't auto-write; review first.
    if args.review_csv and review_queue:
        review_fields = [
            "f7_employer_id", "f7_name", "f7_state",
            "source", "source_id", "source_name_norm",
            "source_display", "source_city", "source_ein",
            "method", "score",
            "rule_engine_tier", "rule_engine_rule", "rule_engine_precision",
        ]
        with open(args.review_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=review_fields, extrasaction="ignore")
            w.writeheader()
            for m in review_queue:
                w.writerow(m)
        print(f"Wrote review-queue CSV: {args.review_csv} ({len(review_queue):,} rows)")

    # Sample matches per tier for spot-checking
    print()
    print("=" * 70)
    print("\nSAMPLE MATCHES (top 3 per tier per source) -- for review")
    print("=" * 70)
    seen = set()
    for src_tuple in SOURCES:
        source_key = src_tuple[0]
        for tier in TIERS:
            n = 0
            for m in all_matches:
                if m["source"] != source_key or m["method"] != tier["method"]:
                    continue
                if m["f7_employer_id"] in seen:
                    continue
                seen.add(m["f7_employer_id"])
                n += 1
                print(f"  {source_key} / {tier['method']}: f7={m['f7_name'][:35]!r:<37} -> source={m['source_name_norm'][:35]!r:<37} (state={m['f7_state']})")
                if n >= 3:
                    break

    print()
    print(f"Total runtime: {time.time() - t0:.1f}s")
    print()
    if args.commit:
        print("=" * 70)
        print(f"COMMIT MODE: would write {len(best_by_orphan):,} rows to unified_match_log")
        print("=" * 70)
        if args.min_score:
            kept = [m for m in best_by_orphan.values() if m["score"] >= args.min_score]
            print(f"After --min-score {args.min_score} filter: {len(kept):,} rows")
        else:
            kept = list(best_by_orphan.values())
        confirm = input(f"\nProceed with INSERT of {len(kept):,} rows into unified_match_log? [type 'yes' to confirm]: ")
        if confirm.strip().lower() == "yes":
            _commit_writes(conn, kept)
        else:
            print("Aborted. Nothing written.")
    else:
        print("DRY-RUN ONLY. To actually write matches:")
        print("  1. Review the CSV / summary above")
        print("  2. Pick a min-score threshold (default 0.92 == NAME_AGGRESSIVE)")
        print("  3. Re-run with --commit --min-score 0.92")

    cur.close()
    conn.close()


def _confidence_band(method: str) -> str:
    """Map V2 method name to the canonical confidence_band convention
    used elsewhere in unified_match_log. Aligns with how
    NAME_CITY_STATE_EXACT / NAME_AGGRESSIVE_STATE / etc. are already
    classified in the existing F7 active matches."""
    if method == "NAME_AGGRESSIVE_STATE_EXACT":
        return "MEDIUM"
    if method == "TRIGRAM_FALLBACK_STATE":
        # Probabilistic match — band lifted to MEDIUM by the rule engine
        # upgrade, otherwise LOW. Static "MEDIUM" here is fine because
        # the --min-score gate is what actually filters at write time.
        return "MEDIUM"
    return "HIGH"


def _commit_writes(conn, matches):
    """Write matches to unified_match_log atomically.

    Schema (verified vs `unified_match_log` definition 2026-05-06):
        run_id, source_system, source_id, target_system, target_id,
        match_method, match_tier (deterministic|probabilistic),
        confidence_band (HIGH|MEDIUM|LOW), confidence_score, evidence,
        status, created_at.

    Race protection: an `INSERT ... SELECT ... WHERE NOT EXISTS` form
    that's TOCTOU-safe vs concurrent rematch / nightly cron runs.
    Two parallel commit runs cannot double-insert the same target_id
    because the WHERE-NOT-EXISTS check happens inside the same SQL
    statement as the INSERT.

    (Codex finding 2026-05-06: prior check-then-insert was racy; prior
    INSERT used `match_score` + `matched_at` columns that don't exist
    in the actual schema -- would have failed at runtime in commit
    mode. Both fixed here.)
    """
    cur = conn.cursor()
    run_id = f"orphan_rematch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    print(f"\nrun_id: {run_id}")
    written = 0
    skipped_existing = 0
    t0 = time.time()
    for i, m in enumerate(matches):
        cur.execute(
            """
            INSERT INTO unified_match_log (
                run_id, source_system, source_id,
                target_system, target_id,
                match_method, match_tier, confidence_band, confidence_score,
                status, evidence, created_at
            )
            SELECT %(run_id)s, %(src)s, %(src_id)s,
                   'f7', %(tgt)s,
                   %(method)s, 'deterministic', %(band)s, %(score)s,
                   'active', %(evidence)s::jsonb, NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_match_log existing
                WHERE existing.target_system = 'f7'
                  AND existing.target_id = %(tgt)s
                  AND existing.status = 'active'
            )
            """,
            {
                "run_id":   run_id,
                "src":      m["source"],
                "src_id":   m["source_id"],
                "tgt":      m["f7_employer_id"],
                "method":   m["method"],
                "band":     _confidence_band(m["method"]),
                "score":    float(m["score"]),
                "evidence": json.dumps({
                    "source_name_norm":       m["source_name_norm"],
                    "rematch_run":            "B.3.x_orphan_recovery_2026_05_08",
                    # Rule engine verdict (B.3.x Option C). Null when
                    # --no-rule-engine was used. Lets us audit later
                    # which writes were rule-engine-corroborated vs
                    # SQL-only.
                    "rule_engine_tier":       m.get("rule_engine_tier"),
                    "rule_engine_rule":       m.get("rule_engine_rule"),
                    "rule_engine_precision":  m.get("rule_engine_precision"),
                }),
            },
        )
        if cur.rowcount == 1:
            written += 1
        else:
            # WHERE NOT EXISTS short-circuited (or the unique index on
            # (run_id, source_system, source_id, target_id) blocked).
            skipped_existing += 1
        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  ... committed {i + 1:,} rows; written={written:,} skipped_existing={skipped_existing:,}")
    conn.commit()
    print(f"\nWritten: {written:,} new rows")
    print(f"Skipped (target already had active match): {skipped_existing:,}")
    print(f"Time: {time.time() - t0:.1f}s")
    print()
    print("Roll-back if needed:")
    print("  UPDATE unified_match_log SET status='superseded'")
    print(f"   WHERE run_id = '{run_id}' AND status = 'active';")


def main():
    parser = argparse.ArgumentParser(description="Rematch F7 orphans against source pool (DRY-RUN by default)")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write to unified_match_log (REQUIRES interactive 'yes' confirmation)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Smoke-test mode: limit each (source, tier) query to N rows")
    parser.add_argument("--out-csv", type=str, default=None,
                        help="Path to write best-match CSV for review")
    parser.add_argument("--review-csv", type=str, default=None,
                        help="Path to write the rule-engine 'tier_C_review' subset "
                             "(matches that pass SQL exact-match but have weaker rule "
                             "corroboration; recommended pre-commit step)")
    parser.add_argument("--no-rule-engine", action="store_true",
                        help="Skip the Haiku-distilled rule engine pass. Useful for "
                             "diff-against-old-runs (the original 1,184-match dry-run "
                             "from 2026-05-06 was generated with this off).")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Apply this score floor at commit time (e.g. 0.92, 0.95, 1.00)")
    parser.add_argument("--enable-trigram", action="store_true",
                        help="Enable Tier 4 in-memory trigram fallback for orphans "
                             "the SQL exact-match tiers missed. Adds ~2-5min runtime "
                             "across 50 states. State-blocked + composite-scored + "
                             "rule-engine-vetoed (added 2026-05-08 evening).")
    parser.add_argument("--trigram-floor", type=float, default=0.85,
                        help="Composite-score floor for Tier 4 trigram (default 0.85). "
                             "Lower = more recall, less precision. The rule engine's "
                             "UPGRADE rules then lift well-corroborated trigram matches "
                             "to 0.91/0.96 so they pass --min-score gates.")
    args = parser.parse_args()
    run_dry_run(args)


if __name__ == "__main__":
    main()
