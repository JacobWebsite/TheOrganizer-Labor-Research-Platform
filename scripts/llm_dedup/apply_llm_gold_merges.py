"""
Apply Haiku-verified DUPLICATE merges from the 2026-04-21 LLM gold CSV.

Reads llm_gold_dedup_2026-04-21.csv, filters to pairs labeled DUPLICATE by
Haiku with confidence HIGH or MEDIUM that are NOT on our rule-engine's
auto-merge paths (pairs sitting in Tier C/D that our engine missed).
Builds transitive clusters via union-find, picks a winner per cluster,
and applies merges via the existing merge_one() procedure.

This is the "additional recall" from the 2026-04-21 $28 Haiku validation
batch: ~8,400 DUP verdicts the rule engine didn't auto-classify but that
Haiku confirmed as legitimate duplicates.

DESTRUCTIVE OPERATION: each merge DELETEs the loser row from master_employers
and moves source_ids to the winner. Reversal requires restore from backup.

Usage:
  # Default is --dry-run
  py scripts/llm_dedup/apply_llm_gold_merges.py

  # To actually apply
  py scripts/llm_dedup/apply_llm_gold_merges.py --apply --yes

  # Optional: restrict to HIGH confidence only (more conservative)
  py scripts/llm_dedup/apply_llm_gold_merges.py --apply --yes --high-only
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\jakew\.local\bin\Labor Data Project_real")
from db_config import get_connection  # noqa: E402

# Reuse the existing merge implementation
sys.path.insert(0, os.path.join(DIR, "..", "etl"))
import dedup_master_employers  # noqa: E402
from dedup_master_employers import merge_one  # noqa: E402

# MERGE_LOG_HAS_REASON / MERGE_LOG_HAS_MERGED_BY are set inside main() via
# global; without main() running they don't exist. Both columns exist in
# live schema, so set them True at import time.
dedup_master_employers.MERGE_LOG_HAS_REASON = True
dedup_master_employers.MERGE_LOG_HAS_MERGED_BY = True

GOLD_CSV = os.path.join(DIR, "llm_gold_dedup_2026-04-21.csv")
DEFAULT_PHASE = "llm_gold_v2_2026_04_21"


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            return x
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            if rx < ry:
                self.parent[ry] = rx
            else:
                self.parent[rx] = ry


def pick_winner(cluster_ids, employer_rows):
    """Priority:
      1. Most source_ids (consolidation preference)
      2. Has non-null EIN
      3. Lowest master_id (deterministic tiebreak)
    """
    candidates = [e for e in employer_rows if e.mid in cluster_ids]
    if not candidates:
        return min(cluster_ids)

    def key(e):
        return (getattr(e, "n_sources", 0),
                1 if (e.ein and e.ein.strip()) else 0,
                -e.mid)

    return max(candidates, key=key).mid


def load_cluster_members(conn, master_ids):
    """Fetch Employer rows for all master_ids."""
    if not master_ids:
        return {}
    from dedup_master_employers import fetch_employers
    cur = conn.cursor()
    employers = fetch_employers(cur, pk_col="master_id", ids=list(master_ids),
                                include_labor_org=True)
    rows = {e.mid: e for e in employers}
    cur.execute("""
        SELECT master_id, COUNT(*) FROM master_employer_source_ids
        WHERE master_id = ANY(%s) GROUP BY master_id
    """, (list(master_ids),))
    for mid, n in cur.fetchall():
        if mid in rows:
            rows[mid].n_sources = n
    cur.close()
    return rows


def load_gold_pairs(path, high_only=False):
    """Filter gold CSV to DUPLICATE verdicts the engine didn't auto-merge."""
    kept = []
    total = 0
    label_counts = defaultdict(int)
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            total += 1
            label_counts[r.get("label")] += 1
            if r.get("label") != "DUPLICATE":
                continue
            conf = (r.get("confidence") or "").upper()
            if high_only and conf != "HIGH":
                continue
            if conf not in ("HIGH", "MEDIUM"):
                # Skip LOW confidence verdicts
                continue
            tier = r.get("engine_tier") or ""
            # Skip pairs already auto-merged by engine (those go through
            # apply_rule_merges.py / national_dry_run.py flow).
            if tier in ("tier_A_auto_merge", "tier_B_high_conf"):
                continue
            try:
                id1 = int(r["id1"])
                id2 = int(r["id2"])
            except (KeyError, ValueError):
                continue
            kept.append({
                "id1": id1,
                "id2": id2,
                "confidence": conf,
                "primary_signal": r.get("primary_signal", ""),
                "engine_tier": tier,
                "engine_rule": r.get("engine_rule", ""),
                "state": r.get("state", ""),
                "name1": r.get("name1", ""),
                "name2": r.get("name2", ""),
                "src1": r.get("src1", ""),
                "src2": r.get("src2", ""),
            })
    print(f"Gold CSV contents ({total:,} rows):")
    for label, n in sorted(label_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label:15s} {n:>6,}")
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=GOLD_CSV,
                    help="Gold CSV path")
    ap.add_argument("--apply", action="store_true",
                    help="actually write to DB (default: dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="required with --apply")
    ap.add_argument("--batch", type=int, default=500,
                    help="commit every N merges")
    ap.add_argument("--phase", default=DEFAULT_PHASE,
                    help="merge_phase label")
    ap.add_argument("--high-only", action="store_true",
                    help="skip MEDIUM-confidence verdicts (safer)")
    args = ap.parse_args()

    if args.apply and not args.yes:
        print("ERROR: --apply requires --yes")
        return 1

    print(f"Loading gold pairs from {args.csv}")
    if args.high_only:
        print("  (filtering to HIGH-confidence DUPLICATEs only)")
    pairs = load_gold_pairs(args.csv, high_only=args.high_only)
    print(f"\n{len(pairs):,} DUPLICATE pairs kept (non-Tier-A/B, "
          f"{'HIGH only' if args.high_only else 'HIGH+MEDIUM'} confidence)")

    # Breakdown by signal + state for context
    sig_counts = defaultdict(int)
    tier_counts = defaultdict(int)
    state_counts = defaultdict(int)
    conf_counts = defaultdict(int)
    for p in pairs:
        sig_counts[p["primary_signal"]] += 1
        tier_counts[p["engine_tier"]] += 1
        state_counts[p["state"]] += 1
        conf_counts[p["confidence"]] += 1
    print("\nBy primary_signal:")
    for s, n in sorted(sig_counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {s:30s} {n:>5,}")
    print("\nBy engine_tier (all are C or D by filter):")
    for t, n in sorted(tier_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:25s} {n:>5,}")
    print("\nBy confidence:")
    for c, n in sorted(conf_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:10s} {n:>5,}")

    # Union-find
    uf = UnionFind()
    rules_by_pair = {}
    for p in pairs:
        uf.union(p["id1"], p["id2"])
        key = (min(p["id1"], p["id2"]), max(p["id1"], p["id2"]))
        rules_by_pair[key] = {
            "signal": p["primary_signal"],
            "confidence": p["confidence"],
        }

    clusters = defaultdict(set)
    for mid in uf.parent:
        clusters[uf.find(mid)].add(mid)
    all_ids = set(uf.parent.keys())
    print(f"\n{len(all_ids):,} distinct masters in pairs")
    print(f"{len(clusters):,} clusters after union-find")

    size_dist = defaultdict(int)
    for c in clusters.values():
        size_dist[len(c)] += 1
    print("Cluster size distribution:")
    for sz in sorted(size_dist):
        n = size_dist[sz]
        if sz >= 5 or n >= 50:
            print(f"  size {sz}: {n:,}")

    # Load employer rows
    print("\nLoading master_employer rows...")
    conn = get_connection()
    employers = load_cluster_members(conn, all_ids)
    print(f"  {len(employers):,}/{len(all_ids):,} masters found in DB")
    missing = all_ids - set(employers.keys())
    if missing:
        print(f"  WARNING: {len(missing):,} masters missing (already merged). "
              "Skipping those rows.")

    # Plan merges
    print("\nPlanning merges per cluster...")
    merge_plan = []
    for cluster in clusters.values():
        alive = [mid for mid in cluster if mid in employers]
        if len(alive) < 2:
            continue
        winner_id = pick_winner(alive, [employers[m] for m in alive])
        losers = [m for m in alive if m != winner_id]
        for loser_id in losers:
            pair_key = (min(winner_id, loser_id), max(winner_id, loser_id))
            meta = rules_by_pair.get(pair_key, {"signal": "transitive",
                                                 "confidence": "MEDIUM"})
            conf_map = {"HIGH": 0.98, "MEDIUM": 0.90}
            conf = conf_map.get(meta["confidence"], 0.90)
            merge_plan.append((winner_id, loser_id, meta["signal"],
                               meta["confidence"], conf))

    print(f"  {len(merge_plan):,} total merges planned")

    if not args.apply:
        print("\n*** DRY RUN -- no database writes. Use --apply --yes to execute. ***")
        conn.close()
        return 0

    # Apply
    print(f"\nApplying {len(merge_plan):,} merges (commit every {args.batch})...")
    cur = conn.cursor()
    applied = 0
    errors = 0
    t0 = time.time()
    for winner_id, loser_id, signal, conf_label, conf in merge_plan:
        winner = employers.get(winner_id)
        loser = employers.get(loser_id)
        if not winner or not loser:
            errors += 1
            continue
        try:
            merge_one(
                cur, pk_col="master_id", include_labor_org=True,
                winner=winner, loser=loser,
                phase=args.phase,
                conf=conf,
                ev={
                    "source": "llm_gold_v2_2026_04_21",
                    "primary_signal": signal,
                    "llm_confidence": conf_label,
                    "winner_n_sources": getattr(winner, "n_sources", 0),
                    "loser_n_sources": getattr(loser, "n_sources", 0),
                },
            )
            applied += 1
            employers.pop(loser_id, None)
        except Exception as e:
            errors += 1
            print(f"  ERROR {winner_id} <- {loser_id}: {type(e).__name__}: {e}")
            conn.rollback()
            cur = conn.cursor()
            continue

        if applied % args.batch == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = applied / elapsed if elapsed > 0 else 0
            eta = (len(merge_plan) - applied) / rate if rate > 0 else 0
            print(f"  {applied:,}/{len(merge_plan):,}  "
                  f"({rate:.1f}/s, ETA {eta/60:.1f}min)")
    conn.commit()
    cur.close()
    conn.close()
    elapsed = time.time() - t0
    print(f"\nDone. Applied {applied:,} merges in {elapsed:.1f}s. "
          f"Errors: {errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
