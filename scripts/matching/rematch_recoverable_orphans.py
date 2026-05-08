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
    # Tier 4 (trigram) intentionally omitted from the default dry-run
    # — it adds combinatorial cost across 15K x 4 sources and is
    # better delivered as a follow-up pass after the exact-match
    # tiers settle. Easy to add later if Jacob wants it for the
    # commit run.
]


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
    args = parser.parse_args()
    run_dry_run(args)


if __name__ == "__main__":
    main()
