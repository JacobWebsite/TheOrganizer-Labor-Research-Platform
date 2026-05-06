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
     1    NAME_STANDARD_STATE_EXACT       1.00
     2    NAME_STANDARD_STATE_ZIP_EXACT   1.00 (when zips agree)
     3    NAME_AGGRESSIVE_STATE_EXACT     0.95
     4    NAME_STANDARD_STATE_TRIGRAM     0.85-0.99 (similarity)

The best match across sources, per orphan, becomes the recommended
write. Per-source counts + sample matches at each tier go into a
CSV + summary report for review.

Usage (DRY-RUN, default):
    py scripts/matching/rematch_recoverable_orphans.py
    py scripts/matching/rematch_recoverable_orphans.py --limit 1000
    py scripts/matching/rematch_recoverable_orphans.py --min-score 0.90

Usage (COMMIT, gated -- requires Jacob review of dry-run report first):
    py scripts/matching/rematch_recoverable_orphans.py --commit \\
        --min-score 0.90 \\
        --out-csv /tmp/orphan_rematch_2026_05_06.csv

The --commit flag writes one unified_match_log row per matched
orphan with status='active', match_method=the V2 method that fired,
and source/target IDs filled in. Conflict resolution: if an orphan
already has an active match by the time --commit runs (race with
another rematch), the new write is skipped, NOT overwritten.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# Project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db_config import get_connection


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

# Sources to attempt matching against. Each entry: (source_system,
# table_name, name_normalized_col, state_col, zip_col).
# Order matters only for tie-breaking (sources earlier in the list win
# at equal score; OSHA first because it's the highest-recovery source
# per the F7 Orphan Rate Open Problem note).
SOURCES = [
    ("osha",  "osha_establishments", "estab_name_normalized",   "site_state",     "site_zip"),
    ("whd",   "whd_cases",           "name_normalized",         "state",          "zip_code"),
    ("990",   "national_990_filers", "name_normalized",         "state",          "zip_code"),
    ("sam",   "sam_entities",        "name_normalized",         "physical_state", "physical_zip"),
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


def attempt_match(cur, source, name_col, state_col, zip_col, tier, limit=None):
    """Run a single (source, tier) match attempt. Returns list of dicts."""
    if tier.get("requires_zip"):
        zip_filter = "AND f.zip IS NOT NULL AND f.zip <> ''"
    else:
        zip_filter = ""
    where = tier["where"].format(name_col=name_col, state_col=state_col, zip_col=zip_col)
    src_id_col = SOURCE_ID_COL[source]
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    sql = f"""
        SELECT
            f.employer_id        AS f7_employer_id,
            f.employer_name      AS f7_name,
            f.state              AS f7_state,
            f.name_standard      AS f7_name_standard,
            s.{src_id_col}       AS source_id,
            s.{name_col}         AS source_name_norm,
            s.{state_col}        AS source_state
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
            "source":           source,
            "source_id":        str(rd["source_id"]) if rd.get("source_id") is not None else None,
            "source_name_norm": rd.get("source_name_norm"),
            "method":           tier["method"],
            "score":            tier["score"],
        })
    return out


SOURCES_BY_KEY = {s[0]: {"table": s[1], "name_col": s[2], "state_col": s[3], "zip_col": s[4]} for s in SOURCES}


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
    for source_key, table, name_col, state_col, zip_col in SOURCES:
        for tier in TIERS:
            ts = time.time()
            matches = attempt_match(cur, source_key, name_col, state_col, zip_col, tier, args.limit)
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
    for src, _, _, _, _ in SOURCES:
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
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "f7_employer_id", "f7_name", "f7_state",
                "source", "source_id", "source_name_norm",
                "method", "score",
            ])
            w.writeheader()
            for m in best_by_orphan.values():
                w.writerow(m)
        print(f"\nWrote best-match CSV: {args.out_csv} ({len(best_by_orphan):,} rows)")

    # Sample matches per tier for spot-checking
    print()
    print("=" * 70)
    print("\nSAMPLE MATCHES (top 3 per tier per source) -- for review")
    print("=" * 70)
    seen = set()
    for source_key, _, _, _, _ in SOURCES:
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


def _commit_writes(conn, matches):
    """Write matches to unified_match_log. Skips orphans that already
    have an active match (race-protection)."""
    cur = conn.cursor()
    written = 0
    skipped_existing = 0
    t0 = time.time()
    for i, m in enumerate(matches):
        # Race-protection: re-check active status right before insert.
        cur.execute(
            """
            SELECT 1 FROM unified_match_log
            WHERE target_system = 'f7' AND target_id = %s AND status = 'active'
            LIMIT 1
            """,
            [m["f7_employer_id"]],
        )
        if cur.fetchone():
            skipped_existing += 1
            continue
        cur.execute(
            """
            INSERT INTO unified_match_log (
                source_system, source_id,
                target_system, target_id,
                match_method, match_score,
                status, matched_at,
                evidence
            ) VALUES (%s, %s, 'f7', %s, %s, %s, 'active', NOW(), %s)
            ON CONFLICT DO NOTHING
            """,
            [
                m["source"], m["source_id"],
                m["f7_employer_id"], m["method"],
                float(m["score"]),
                json.dumps({
                    "source_name_norm": m["source_name_norm"],
                    "rematch_run": "B.3.x_orphan_recovery_dryrun_2026_05_06",
                }),
            ],
        )
        written += cur.rowcount
        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  ... committed {i + 1:,} rows, written so far: {written:,}")
    conn.commit()
    print(f"\nWritten: {written:,} new rows")
    print(f"Skipped (already had active match): {skipped_existing:,}")
    print(f"Time: {time.time() - t0:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Rematch F7 orphans against source pool (DRY-RUN by default)")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write to unified_match_log (REQUIRES interactive 'yes' confirmation)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Smoke-test mode: limit each (source, tier) query to N rows")
    parser.add_argument("--out-csv", type=str, default=None,
                        help="Path to write best-match CSV for review")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Apply this score floor at commit time (e.g. 0.92, 0.95, 1.00)")
    args = parser.parse_args()
    run_dry_run(args)


if __name__ == "__main__":
    main()
