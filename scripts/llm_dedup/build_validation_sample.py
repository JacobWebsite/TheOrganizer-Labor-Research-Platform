"""
Build the stratified 45K pair sample for the 2026-04-21 LLM validation batch.

Reads all per-state CSVs produced by national_dry_run.py:
  - tier_B_pairs_<STATE>.csv
  - tier_C_pairs_<STATE>.csv
  - tier_D_pairs_<STATE>.csv
  - hierarchy_edges_<STATE>.csv

Applies stratification quotas:
  Dedup budget (20K)
    - Tier B residual:           5,000 (91% precision validation)
    - Tier C/D residual:        15,000 (main rule-discovery payload)
  Hierarchy budget (25K)
    - H4 small (size 2-3):       8,000 (resolves broad-parent concern)
    - H4 MOSTLY_GENERIC:         4,000 (direct verdict on 129 flagged)
    - H4 medium (size 4-10):     4,000 (mid-size sanity)
    - H9 subsidiary:             4,000 (unvalidated rule)
    - H12 division:              1,000 (rare but high-value)
  Floors (applied on top of stratification, not double-counted):
    - 990-involved (any tier):   >=4,000 minimum
    - Each state in target list: >=1,000 minimum

Output: validation_sample_45k.json (single flat list, ready for the batch prep
script to render into Haiku requests).

Reproducible via random.seed(2026).
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)


OUT_JSON = os.path.join(DIR, "validation_sample_45k.json")
SUMMARY_JSON = os.path.join(DIR, "validation_sample_summary.json")

# Target states for the 18-state run (NY intentionally excluded -- we already
# have 31K Haiku labels from the 2026-04-16 batch).
TARGET_STATES = [
    # Already have Tier A merged (4): re-sample residual only
    "CA", "TX", "FL",
    # Industrial Midwest (4)
    "IL", "OH", "MI", "PA",
    # South / Southeast (4)
    "GA", "NC", "TN", "VA",
    # New England / Atlantic (2)
    "MA", "NJ",
    # Mountain / West (2)
    "WA", "AZ",
    # Plains / Agri (1)
    "MN",
    # DC metro (1)
    "DC",
]

# Budget per pair-type bucket
BUDGETS = {
    "dedup_tier_B":           5_000,
    "dedup_tier_C":          10_000,
    "dedup_tier_D":           5_000,
    "hierarchy_h4_small":     8_000,
    "hierarchy_h4_generic":   4_000,
    "hierarchy_h4_medium":    4_000,
    "hierarchy_h9":           4_000,
    "hierarchy_h12":          1_000,
}
TOTAL_BUDGET = sum(BUDGETS.values())  # 41K (leaves 4K cushion for floors/990)

FLOOR_990_PAIRS = 4_000
FLOOR_PER_STATE = 1_000

# For MOSTLY_GENERIC detection (matches analyze_small_clusters.py)
DANGER_KEYWORDS = {
    "partners", "fund", "funds", "capital", "holdings", "group",
    "trust", "ventures", "portfolio", "portfolios", "global",
    "investments", "management", "advisors", "partner",
}


def is_mostly_generic(parent_name: str) -> bool:
    tokens = parent_name.split()
    if len(tokens) != 2:
        return False
    t0, t1 = tokens[0], tokens[1]
    has_danger = t0 in DANGER_KEYWORDS or t1 in DANGER_KEYWORDS
    distinct_tok = t1 if t0 in DANGER_KEYWORDS else t0
    return has_danger and len(distinct_tok) < 5


def load_dedup_csv(path: str, tier_label: str, state: str) -> list[dict]:
    """Load a tier_B/C/D pairs CSV, tag each pair with its state + tier."""
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["pair_type"] = "dedup"
                r["tier_bucket"] = tier_label
                r["state"] = state
                out.append(r)
    except FileNotFoundError:
        pass
    return out


def load_hierarchy_csv(path: str, state: str) -> list[dict]:
    """Load hierarchy_edges CSV and bucket edges by rule + cluster size."""
    # First pass: count H4 cluster sizes (distinct masters per parent_candidate_name)
    cluster_members = defaultdict(set)
    edges_raw = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                edges_raw.append(r)
                if r.get("rule") == "H4":
                    p = r.get("parent_candidate_name", "")
                    if r.get("master_id_1"):
                        cluster_members[p].add(r["master_id_1"])
                    if r.get("master_id_2"):
                        cluster_members[p].add(r["master_id_2"])
    except FileNotFoundError:
        return []

    # Second pass: tag each edge with its hierarchy bucket
    out = []
    for r in edges_raw:
        rule = r.get("rule")
        r["pair_type"] = "hierarchy"
        r["state"] = state
        r["hier_rule"] = rule
        if rule == "H4":
            p = r.get("parent_candidate_name", "")
            size = len(cluster_members[p])
            r["cluster_size"] = size
            r["mostly_generic"] = is_mostly_generic(p)
            if r["mostly_generic"]:
                r["tier_bucket"] = "hierarchy_h4_generic"
            elif size <= 3:
                r["tier_bucket"] = "hierarchy_h4_small"
            elif size <= 10:
                r["tier_bucket"] = "hierarchy_h4_medium"
            else:
                # Large clusters (size > 10) skipped for sampling budget; the
                # top-30 spot-check already covered these.
                continue
        elif rule == "H9":
            r["tier_bucket"] = "hierarchy_h9"
        elif rule == "H12":
            r["tier_bucket"] = "hierarchy_h12"
        else:
            continue
        out.append(r)
    return out


def normalize_to_pair_dict(raw: dict) -> dict:
    """Flatten either a dedup-CSV row or a hierarchy-edge row into a uniform
    pair dict for Haiku rendering. Keys match validation_judge_prompt naming."""
    if raw["pair_type"] == "dedup":
        return {
            "pair_type": "dedup",
            "state": raw.get("state", ""),
            "tier_bucket": raw.get("tier_bucket", ""),
            "engine_tier": raw.get("tier", ""),
            "engine_rule": raw.get("rule", ""),
            "engine_confidence": raw.get("confidence", ""),
            "id1": raw.get("id1"),
            "id2": raw.get("id2"),
            "display_name_1": raw.get("name1", ""),
            "display_name_2": raw.get("name2", ""),
            "canonical_name_1": raw.get("cname1", ""),
            "canonical_name_2": raw.get("cname2", ""),
            "city_1": raw.get("city1", ""),
            "city_2": raw.get("city2", ""),
            "state_1": raw.get("state", ""),
            "state_2": raw.get("state", ""),
            "zip_1": raw.get("zip1", ""),
            "zip_2": raw.get("zip2", ""),
            "ein_1": raw.get("ein1", ""),
            "ein_2": raw.get("ein2", ""),
            "naics_1": raw.get("naics1", ""),
            "naics_2": raw.get("naics2", ""),
            "source_1": raw.get("src1", ""),
            "source_2": raw.get("src2", ""),
            "is_nonprofit_1": raw.get("np1", ""),
            "is_nonprofit_2": raw.get("np2", ""),
            "is_public_1": raw.get("pub1", ""),
            "is_public_2": raw.get("pub2", ""),
            "employee_count_1": raw.get("emp1", ""),
            "employee_count_2": raw.get("emp2", ""),
            "industry_1": raw.get("ind1", ""),
            "industry_2": raw.get("ind2", ""),
        }
    # hierarchy pair
    return {
        "pair_type": "hierarchy",
        "state": raw.get("state", ""),
        "tier_bucket": raw.get("tier_bucket", ""),
        "engine_rule": raw.get("rule", ""),
        "hier_rule": raw.get("hier_rule", ""),
        "cluster_size": raw.get("cluster_size", ""),
        "parent_candidate_name": raw.get("parent_candidate_name", ""),
        "mostly_generic": raw.get("mostly_generic", False),
        "id1": raw.get("master_id_1") or raw.get("parent_id") or "",
        "id2": raw.get("master_id_2") or raw.get("child_id") or "",
        "display_name_1": raw.get("name_1", ""),
        "display_name_2": raw.get("name_2", ""),
        "zip_1": raw.get("zip_1", ""),
        "zip_2": raw.get("zip_2", ""),
        "source_1": raw.get("src_1", ""),
        "source_2": raw.get("src_2", ""),
        "engine_confidence": raw.get("confidence", ""),
    }


def stratify_and_sample(all_dedup: list[dict], all_hier: list[dict]) -> list[dict]:
    """Sample per-bucket quotas with state proportionality + floors."""
    rng = random.Random(2026)

    # Group by bucket
    by_bucket = defaultdict(list)
    for r in all_dedup:
        by_bucket[r["tier_bucket"]].append(r)
    for r in all_hier:
        by_bucket[r["tier_bucket"]].append(r)

    selected: list[dict] = []
    for bucket, budget in BUDGETS.items():
        pool = by_bucket.get(bucket, [])
        if not pool:
            print(f"  WARN: bucket {bucket!r} has NO pairs available "
                  f"(budget={budget})")
            continue
        # Within the bucket, try to distribute across states
        by_state = defaultdict(list)
        for r in pool:
            by_state[r.get("state", "??")].append(r)

        # Per-state quota = budget / # states, floor at FLOOR_PER_STATE / len(buckets)
        n_states = len(by_state)
        per_state_target = max(1, budget // max(1, n_states))

        picked_from_bucket = []
        for st, state_pool in by_state.items():
            if len(state_pool) <= per_state_target:
                picked_from_bucket.extend(state_pool)
            else:
                picked_from_bucket.extend(rng.sample(state_pool, per_state_target))

        # If we overshot the bucket budget, downsample
        if len(picked_from_bucket) > budget:
            picked_from_bucket = rng.sample(picked_from_bucket, budget)

        # If we undershot (rare state with insufficient pool), top up from largest states
        if len(picked_from_bucket) < budget:
            rest = [r for r in pool if r not in picked_from_bucket]
            needed = budget - len(picked_from_bucket)
            if rest:
                picked_from_bucket.extend(rng.sample(rest, min(needed, len(rest))))

        selected.extend(picked_from_bucket)
        print(f"  {bucket:30s} picked {len(picked_from_bucket):>5,} "
              f"(budget {budget:>5,}) from pool {len(pool):>7,}")

    # Deduplicate by (id1, id2) unordered pair.
    # Dedup-CSV rows use "id1"/"id2"; hierarchy rows use "master_id_1"/
    # "master_id_2" (H4) or "parent_id"/"child_id" (H9/H12). Canonicalize first.
    def _canon_key(r):
        a = r.get("id1") or r.get("master_id_1") or r.get("parent_id") or ""
        b = r.get("id2") or r.get("master_id_2") or r.get("child_id") or ""
        return tuple(sorted([str(a), str(b)]))

    seen = set()
    deduped = []
    for r in selected:
        key = _canon_key(r)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # 990 floor check: do we have >=4K pairs involving 990?
    def _involves_990(r):
        s1 = (r.get("src1") or r.get("src_1") or "").lower()
        s2 = (r.get("src2") or r.get("src_2") or "").lower()
        return s1 == "990" or s2 == "990"

    n_990 = sum(1 for r in deduped if _involves_990(r))
    if n_990 < FLOOR_990_PAIRS:
        deficit = FLOOR_990_PAIRS - n_990
        print(f"\n  990 floor check: {n_990:,} / {FLOOR_990_PAIRS:,}  "
              f"(deficit {deficit:,}, topping up from unsampled 990 pool)")
        # Top up from unsampled pool
        all_pool = all_dedup + all_hier
        unsampled_990 = [
            r for r in all_pool
            if _involves_990(r)
            and tuple(sorted([str(r.get("id1") or r.get("master_id_1")
                                  or r.get("parent_id") or ""),
                              str(r.get("id2") or r.get("master_id_2")
                                  or r.get("child_id") or "")])) not in seen
        ]
        rng.shuffle(unsampled_990)
        for r in unsampled_990[:deficit]:
            deduped.append(r)

    return deduped


def main():
    print(f"Scanning CSVs for {len(TARGET_STATES)} states...")
    all_dedup = []
    all_hier = []

    for state in TARGET_STATES:
        state_dedup = 0
        for tier in ("B", "C", "D"):
            path = os.path.join(DIR, f"tier_{tier}_pairs_{state}.csv")
            rows = load_dedup_csv(path, f"dedup_tier_{tier}", state)
            all_dedup.extend(rows)
            state_dedup += len(rows)

        hier_path = os.path.join(DIR, f"hierarchy_edges_{state}.csv")
        hier_rows = load_hierarchy_csv(hier_path, state)
        all_hier.extend(hier_rows)

        print(f"  {state:3s}  dedup={state_dedup:>7,}  hier={len(hier_rows):>7,}")

    print(f"\nTotal pool: {len(all_dedup):,} dedup + {len(all_hier):,} hierarchy "
          f"= {len(all_dedup)+len(all_hier):,}")

    print(f"\nStratified sampling (budget total = {TOTAL_BUDGET:,}):")
    sampled = stratify_and_sample(all_dedup, all_hier)

    # Normalize into flat pair dicts
    print(f"\nNormalizing {len(sampled):,} sampled pairs...")
    pairs = [normalize_to_pair_dict(r) for r in sampled]

    # Summary stats
    bucket_counts = Counter(p["tier_bucket"] for p in pairs)
    state_counts = Counter(p["state"] for p in pairs)
    type_counts = Counter(p["pair_type"] for p in pairs)
    source_combos = Counter()
    for p in pairs:
        s1 = (p.get("source_1") or "").lower() or "?"
        s2 = (p.get("source_2") or "").lower() or "?"
        key = tuple(sorted([s1, s2]))
        source_combos[key] += 1

    print(f"\nFinal sample: {len(pairs):,} pairs")
    print("  By bucket:")
    for b, n in bucket_counts.most_common():
        print(f"    {b:30s} {n:>6,}")
    print("  By pair_type:")
    for t, n in type_counts.most_common():
        print(f"    {t:30s} {n:>6,}")
    print(f"  By state (top 10 of {len(state_counts)}):")
    for st, n in state_counts.most_common(10):
        print(f"    {st:3s} {n:>6,}")
    print("  Top 10 source combos:")
    for combo, n in source_combos.most_common(10):
        print(f"    {'x'.join(combo):30s} {n:>6,}")

    # Write
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(pairs, f, default=str)
    print(f"\nWrote {len(pairs):,} pairs -> {OUT_JSON}")

    # Summary JSON for downstream tools
    summary = {
        "total_pairs": len(pairs),
        "prompt_version": "v2.0-validation",
        "target_states": TARGET_STATES,
        "budgets": BUDGETS,
        "actual_by_bucket": dict(bucket_counts),
        "actual_by_state": dict(state_counts),
        "actual_by_type": dict(type_counts),
        "top_source_combos": [
            {"combo": list(c), "count": n}
            for c, n in source_combos.most_common(20)
        ],
    }
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
