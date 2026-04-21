"""
Analyze the 2026-04-21 Haiku validation batch results.

Reads anthropic_batch_results.jsonl + anthropic_validation_batch_manifest.json
and produces:
  1. llm_gold_dedup_<date>.csv       -- all labeled dedup pairs
  2. llm_gold_hierarchy_<date>.csv   -- all labeled hierarchy pairs
  3. rule_candidates_<date>.csv      -- (label, primary_signal) clusters
                                        with >=30 members + >=95% same label
  4. matching_gap_analysis_<date>.csv -- DUP pairs our rule engine missed
  5. negative_rule_candidates_<date>.csv -- rules with precision leaks
  6. per_state_precision_<date>.csv  -- precision-per-state for each tier
  7. hierarchy_filter_<date>.csv     -- broad-parent clusters to reject

Usage:
  py scripts/llm_dedup/analyze_validation_results.py
  py scripts/llm_dedup/analyze_validation_results.py --results <path>
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_RESULTS = os.path.join(DIR, "anthropic_validation_batch_results.jsonl")
DEFAULT_MANIFEST = os.path.join(DIR, "anthropic_validation_batch_manifest.json")


def parse_verdict(content: str) -> dict | None:
    """Parse Haiku's JSON response. Robust to markdown fences, trailing prose,
    and truncated (MAX_OUTPUT_TOKENS-cut) responses.

    Returns None if no fields could be recovered at all."""
    import re
    content = content.strip()
    # Strip markdown fences (batch mode often wraps in ```json ... ```)
    if content.startswith("```"):
        content = content.lstrip("`")
        if content.startswith("json\n") or content.startswith("json "):
            content = content[5:]
        # Also strip trailing fence if present
        if content.rstrip().endswith("```"):
            content = content.rstrip().rstrip("`").rstrip()

    # Try direct parse first
    try:
        return json.loads(content)
    except Exception:
        pass

    # Try progressive substring from first '{' (handles trailing garbage)
    i = content.find("{")
    if i >= 0:
        for j in range(len(content), i, -1):
            try:
                return json.loads(content[i:j])
            except Exception:
                continue

    # Last resort: regex-extract individual fields from truncated responses.
    # Covers the common case where only the tail reasoning field got cut.
    if i < 0:
        return None
    tail = content[i:]
    d = {}
    for fld in ("label", "confidence", "primary_signal", "reasoning"):
        m = re.search(rf'"{fld}"\s*:\s*"([^"]*)"', tail)
        if m:
            d[fld] = m.group(1)
    # supporting_signals is an array; extract any string elements inside
    m_arr = re.search(r'"supporting_signals"\s*:\s*\[([^\]]*)\]', tail)
    if m_arr:
        d["supporting_signals"] = re.findall(r'"([^"]+)"', m_arr.group(1))
    return d if d else None


def load_results(results_path, manifest_path):
    """Load results JSONL + manifest, return list of dicts with joined metadata."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    lookup = manifest["pair_lookup"]

    out = []
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            cid = rec.get("custom_id")
            if not cid or cid not in lookup:
                continue
            meta = lookup[cid]
            result = rec.get("result", {})
            msg = result.get("message", {}) if result.get("type") == "succeeded" else {}
            content_blocks = msg.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text += block.get("text", "")
            verdict = parse_verdict(text) or {}

            row = {
                "custom_id": cid,
                "id1": meta.get("id1"),
                "id2": meta.get("id2"),
                "pair_type": meta.get("pair_type"),
                "tier_bucket": meta.get("tier_bucket"),
                "state": meta.get("state"),
                "engine_rule": meta.get("engine_rule") or "",
                "engine_tier": meta.get("engine_tier") or "",
                "hier_rule": meta.get("hier_rule") or "",
                "cluster_size": meta.get("cluster_size") or "",
                "parent_candidate_name": meta.get("parent_candidate_name") or "",
                "mostly_generic": meta.get("mostly_generic") or False,
                "name1": meta.get("name1") or "",
                "name2": meta.get("name2") or "",
                "src1": meta.get("src1") or "",
                "src2": meta.get("src2") or "",
                "label": verdict.get("label") or "PARSE_FAIL",
                "confidence": verdict.get("confidence") or "",
                "primary_signal": verdict.get("primary_signal") or "",
                "supporting_signals": ";".join(verdict.get("supporting_signals") or []),
                "reasoning": verdict.get("reasoning") or "",
                "raw_text": text[:500],
            }
            out.append(row)
    return out


def write_gold_csvs(results, out_dir, date_str):
    """Write llm_gold_{dedup,hierarchy}_<date>.csv."""
    dedup = [r for r in results if r["pair_type"] == "dedup"]
    hier = [r for r in results if r["pair_type"] == "hierarchy"]

    cols = ["id1", "id2", "pair_type", "tier_bucket", "state", "engine_rule",
            "engine_tier", "hier_rule", "cluster_size", "parent_candidate_name",
            "mostly_generic", "name1", "name2", "src1", "src2",
            "label", "confidence", "primary_signal", "supporting_signals",
            "reasoning"]

    for subset, label in [(dedup, "dedup"), (hier, "hierarchy")]:
        out_path = os.path.join(out_dir, f"llm_gold_{label}_{date_str}.csv")
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore",
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in subset:
                w.writerow(r)
        print(f"  Wrote {len(subset):,} {label} gold rows -> {out_path}")


def mine_rule_candidates(results, out_dir, date_str,
                         min_cluster=30, min_purity=0.95):
    """Cluster by (label, primary_signal, engine_rule). Any cluster meeting
    min_cluster size AND min_purity (>=95% same label) is a candidate rule."""
    by_cluster = defaultdict(list)
    for r in results:
        if r["label"] == "PARSE_FAIL":
            continue
        # Cluster by signal + engine_rule so we see "pairs the engine missed"
        key = (r["label"], r["primary_signal"], r["engine_rule"] or "<none>")
        by_cluster[key].append(r)

    candidates = []
    for (label, signal, engine_rule), pairs in by_cluster.items():
        if len(pairs) < min_cluster:
            continue
        # Purity: all pairs in cluster already share this label by construction,
        # so compute "how often does this (primary_signal, engine_rule) pair
        # PREDICT this label across the full dataset?"
        same_signal_engine = [
            r for r in results
            if r["primary_signal"] == signal and (r["engine_rule"] or "<none>") == engine_rule
            and r["label"] != "PARSE_FAIL"
        ]
        if not same_signal_engine:
            continue
        label_count = sum(1 for r in same_signal_engine if r["label"] == label)
        purity = label_count / len(same_signal_engine)
        if purity < min_purity:
            continue
        candidates.append({
            "label": label,
            "primary_signal": signal,
            "engine_rule": engine_rule,
            "cluster_size": len(pairs),
            "total_same_signal": len(same_signal_engine),
            "purity": round(purity, 4),
            "sample_pair_1": f"{pairs[0]['name1']} | {pairs[0]['name2']}",
            "sample_pair_2": (f"{pairs[1]['name1']} | {pairs[1]['name2']}"
                              if len(pairs) > 1 else ""),
            "sample_state": pairs[0]["state"],
        })

    candidates.sort(key=lambda c: (-c["cluster_size"], -c["purity"]))
    out_path = os.path.join(out_dir, f"rule_candidates_{date_str}.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        if candidates:
            w = csv.DictWriter(f, fieldnames=list(candidates[0].keys()),
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(candidates)
    print(f"  Found {len(candidates)} rule candidates -> {out_path}")


def matching_gap_analysis(results, out_dir, date_str):
    """For each DUP labeled pair, identify which match-tier would've caught it
    and which did not. Pairs where NO existing tier would've caught it are
    candidates for a new matching tier."""
    dups = [r for r in results if r["label"] == "DUPLICATE"
            and r["confidence"] in ("HIGH", "MEDIUM")]

    gaps = []
    for r in dups:
        # Map primary_signal -> matching-tier coverage
        sig = r["primary_signal"]
        if sig == "ein_match":
            tier_coverage = "T1_ein"
        elif sig in ("name_byte_identical", "address_full_match"):
            tier_coverage = "T2_exact"
        elif sig in ("name_punctuation_only_diff", "name_suffix_only_diff"):
            tier_coverage = "T4_normalized"
        elif sig == "name_minor_variant":
            tier_coverage = "T5_T6_fuzzy"
        elif sig in ("phone_match", "website_match", "shared_officer",
                     "address_minus_suite_match", "ein_prefix_match",
                     "dba_alias"):
            tier_coverage = "NO_TIER_NEW_CANDIDATE"
        else:
            tier_coverage = "UNKNOWN"

        if tier_coverage == "NO_TIER_NEW_CANDIDATE":
            gaps.append({
                "primary_signal": sig,
                "engine_rule": r["engine_rule"] or "<none>",
                "tier_bucket": r["tier_bucket"],
                "state": r["state"],
                "name1": r["name1"],
                "name2": r["name2"],
                "src1": r["src1"],
                "src2": r["src2"],
                "reasoning": r["reasoning"],
            })

    out_path = os.path.join(out_dir, f"matching_gap_analysis_{date_str}.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        if gaps:
            w = csv.DictWriter(f, fieldnames=list(gaps[0].keys()),
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(gaps)
    # Signal-count summary
    sig_counts = Counter(g["primary_signal"] for g in gaps)
    print(f"  {len(gaps)} DUP pairs outside existing match tiers:")
    for sig, n in sig_counts.most_common():
        print(f"    {sig:30s} {n:>4,}")
    print(f"  Wrote -> {out_path}")


def negative_rule_analysis(results, out_dir, date_str):
    """Where our engine rule said DUP-tier (Tier A/B) but Haiku says UNRELATED
    or BROKEN, those are precision leaks. Cluster by (engine_rule, primary_signal)."""
    leaks = [
        r for r in results
        if r["engine_tier"] in ("tier_A_auto_merge", "tier_B_high_conf")
        and r["label"] in ("UNRELATED", "BROKEN")
    ]

    by_cluster = defaultdict(list)
    for r in leaks:
        key = (r["engine_rule"] or "<none>", r["primary_signal"] or "<none>")
        by_cluster[key].append(r)

    rows = []
    for (rule, sig), pairs in sorted(by_cluster.items(), key=lambda kv: -len(kv[1])):
        # Count engine's total Tier A/B firings of this rule in the sample
        engine_firings = sum(1 for r in results
                             if (r["engine_rule"] or "<none>") == rule
                             and r["engine_tier"] in ("tier_A_auto_merge",
                                                      "tier_B_high_conf"))
        leak_rate = len(pairs) / max(1, engine_firings)
        rows.append({
            "engine_rule": rule,
            "primary_signal": sig,
            "leak_count": len(pairs),
            "engine_firings_sampled": engine_firings,
            "leak_rate": round(leak_rate, 4),
            "sample_pair_1": f"{pairs[0]['name1']} | {pairs[0]['name2']}",
            "sample_state": pairs[0]["state"],
        })

    out_path = os.path.join(out_dir, f"negative_rule_candidates_{date_str}.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(rows)
    print(f"  {len(leaks)} precision leaks in Tier A/B -> {out_path}")


def per_state_precision(results, out_dir, date_str):
    """Precision of each engine rule per state: what fraction of engine's
    Tier A/B pairs got labeled DUPLICATE by Haiku."""
    by_state_rule = defaultdict(lambda: {"n_ab": 0, "n_dup": 0})
    for r in results:
        if r["engine_tier"] not in ("tier_A_auto_merge", "tier_B_high_conf"):
            continue
        key = (r["state"], r["engine_rule"] or "<none>")
        by_state_rule[key]["n_ab"] += 1
        if r["label"] == "DUPLICATE":
            by_state_rule[key]["n_dup"] += 1

    rows = []
    for (state, rule), stats in sorted(by_state_rule.items()):
        if stats["n_ab"] < 10:  # too few to estimate
            continue
        prec = stats["n_dup"] / stats["n_ab"]
        rows.append({
            "state": state,
            "engine_rule": rule,
            "n_tier_ab": stats["n_ab"],
            "n_duplicate": stats["n_dup"],
            "precision": round(prec, 4),
        })
    out_path = os.path.join(out_dir, f"per_state_precision_{date_str}.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(rows)
    print(f"  {len(rows)} state x rule precision rows -> {out_path}")


def hierarchy_filter(results, out_dir, date_str):
    """For hierarchy pairs, cluster by parent_candidate_name. If >50% of pairs
    in that cluster are labeled UNRELATED or BROKEN, the parent is a reject."""
    by_parent = defaultdict(list)
    for r in results:
        if r["pair_type"] != "hierarchy":
            continue
        parent = r.get("parent_candidate_name") or ""
        if not parent:
            continue
        by_parent[parent].append(r)

    rows = []
    for parent, pairs in by_parent.items():
        if len(pairs) < 2:
            continue
        n_unrelated = sum(1 for r in pairs if r["label"] in ("UNRELATED", "BROKEN"))
        reject_rate = n_unrelated / len(pairs)
        if reject_rate > 0.30:  # >30% junk -> flag cluster for review
            rows.append({
                "parent_candidate_name": parent,
                "pairs_sampled": len(pairs),
                "unrelated_or_broken": n_unrelated,
                "reject_rate": round(reject_rate, 3),
                "mostly_generic_flag": pairs[0].get("mostly_generic", False),
                "cluster_size": pairs[0].get("cluster_size", ""),
                "sample_pair": f"{pairs[0]['name1']} | {pairs[0]['name2']}",
                "sample_state": pairs[0]["state"],
            })
    rows.sort(key=lambda r: (-r["reject_rate"], -r["pairs_sampled"]))
    out_path = os.path.join(out_dir, f"hierarchy_filter_{date_str}.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                               quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(rows)
    print(f"  {len(rows)} hierarchy clusters flagged for rejection -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=DEFAULT_RESULTS)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--out-dir", default=DIR)
    args = ap.parse_args()

    print(f"Loading {args.results}...")
    results = load_results(args.results, args.manifest)
    print(f"  {len(results):,} results joined to manifest")

    # Summary
    label_counts = Counter(r["label"] for r in results)
    print("  Label distribution:")
    for label, n in label_counts.most_common():
        print(f"    {label:15s} {n:>7,}")

    print("\n=== Writing gold CSVs ===")
    write_gold_csvs(results, args.out_dir, args.date)

    print("\n=== Rule candidate mining ===")
    mine_rule_candidates(results, args.out_dir, args.date)

    print("\n=== Matching-tier gap analysis ===")
    matching_gap_analysis(results, args.out_dir, args.date)

    print("\n=== Negative-rule analysis (precision leaks) ===")
    negative_rule_analysis(results, args.out_dir, args.date)

    print("\n=== Per-state precision ===")
    per_state_precision(results, args.out_dir, args.date)

    print("\n=== Hierarchy filter (broad-parent rejects) ===")
    hierarchy_filter(results, args.out_dir, args.date)

    print("\nDone.")


if __name__ == "__main__":
    sys.exit(main())
