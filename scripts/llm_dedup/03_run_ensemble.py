#!/usr/bin/env python
"""
Phase 3: Run all 5 LLM-developed dedup methods on ALL candidate pairs.
Uses majority voting with confidence weighting for final verdicts.
Writes comprehensive results to results/ directory.
"""

import importlib.util
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

DIR = Path(__file__).parent
CANDIDATES_PATH = DIR / "candidates_scored.json"
METHODS_DIR = DIR / "methods"
RESULTS_DIR = DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Confidence weights for voting
CONF_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
VERDICT_MAP = {"DUPLICATE": 2, "RELATED": 1, "DIFFERENT": 0}


def load_method(name: str):
    """Dynamically load a method module."""
    path = METHODS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.judge_pair


def load_candidates():
    with open(CANDIDATES_PATH) as f:
        return json.load(f)


def compact_pair(p: dict) -> dict:
    """Convert a full candidate pair to the compact format methods expect."""
    return {
        "id1": p["id1"],
        "id2": p["id2"],
        "name1": p["display_name_1"],
        "name2": p["display_name_2"],
        "cname1": p["canonical_name_1"],
        "cname2": p["canonical_name_2"],
        "city1": p.get("city_1"),
        "city2": p.get("city_2"),
        "zip1": p.get("zip_1"),
        "zip2": p.get("zip_2"),
        "ein1": p.get("ein_1"),
        "ein2": p.get("ein_2"),
        "naics1": p.get("naics_1"),
        "naics2": p.get("naics_2"),
        "src1": p.get("source_1"),
        "src2": p.get("source_2"),
        "emp1": p.get("employee_count_1"),
        "emp2": p.get("employee_count_2"),
        "pub1": p.get("is_public_1"),
        "pub2": p.get("is_public_2"),
        "np1": p.get("is_nonprofit_1"),
        "np2": p.get("is_nonprofit_2"),
        "web1": p.get("website_1"),
        "web2": p.get("website_2"),
        "ind1": p.get("industry_1"),
        "ind2": p.get("industry_2"),
        "methods": p.get("blocking_methods", []),
        "composite": p["scores"]["composite"],
        "scores": p["scores"],
    }


def vote(method_results: list) -> dict:
    """
    Majority vote with confidence weighting.
    Returns final verdict, confidence, and per-method breakdown.
    """
    if not method_results:
        return {"verdict": "DIFFERENT", "confidence": "LOW", "reasoning": "No methods produced results"}

    # Weighted voting
    verdict_scores = defaultdict(float)
    for r in method_results:
        v = r.get("verdict", "DIFFERENT")
        c = r.get("confidence", "LOW")
        weight = CONF_WEIGHT.get(c, 1)
        verdict_scores[v] += weight

    # Winner
    winner = max(verdict_scores, key=verdict_scores.get)
    total_weight = sum(verdict_scores.values())
    winner_weight = verdict_scores[winner]
    agreement_ratio = winner_weight / total_weight if total_weight > 0 else 0

    # Determine final confidence
    raw_votes = Counter(r.get("verdict", "DIFFERENT") for r in method_results)
    unanimity = raw_votes[winner] / len(method_results) if method_results else 0

    if unanimity >= 0.8 and agreement_ratio >= 0.7:
        final_conf = "HIGH"
    elif unanimity >= 0.6 or agreement_ratio >= 0.5:
        final_conf = "MEDIUM"
    else:
        final_conf = "LOW"

    # Compile reasoning from all methods
    reasons = []
    for r in method_results:
        method_name = r.get("_method", "unknown")
        reasons.append(f"[{method_name}] {r.get('verdict','?')}/{r.get('confidence','?')}: {r.get('reasoning','')}")

    return {
        "verdict": winner,
        "confidence": final_conf,
        "vote_counts": dict(raw_votes),
        "weighted_scores": {k: round(v, 2) for k, v in verdict_scores.items()},
        "agreement_ratio": round(agreement_ratio, 3),
        "reasoning": reasons,
    }


def main():
    t0 = time.time()

    # Load methods
    method_names = [
        "method_name_analysis",
        "method_location",
        "method_business_identity",
        "method_cross_source",
        "method_holistic",
    ]

    methods = {}
    for name in method_names:
        try:
            methods[name] = load_method(name)
            print(f"  Loaded {name}")
        except Exception as e:
            print(f"  FAILED to load {name}: {e}")

    print(f"\nLoaded {len(methods)}/{len(method_names)} methods")

    # Load all candidates
    print("\nLoading candidates...")
    all_pairs = load_candidates()
    print(f"  {len(all_pairs):,} total candidate pairs")

    # Process ALL pairs (not just ambiguous - we want methods to review auto-classified too)
    print("\nProcessing all pairs through all methods...")
    results = []
    errors = defaultdict(int)
    method_verdict_counts = {name: Counter() for name in methods}

    for i, pair in enumerate(all_pairs):
        if i % 5000 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(all_pairs) - i) / rate if rate > 0 else 0
            print(f"  {i:,}/{len(all_pairs):,} ({elapsed:.0f}s elapsed, ETA {eta:.0f}s)")

        cp = compact_pair(pair)
        method_results = []

        for name, func in methods.items():
            try:
                result = func(cp)
                result["_method"] = name
                method_results.append(result)
                method_verdict_counts[name][result.get("verdict", "ERROR")] += 1
            except Exception as e:
                errors[name] += 1
                method_results.append({
                    "_method": name,
                    "verdict": "DIFFERENT",
                    "confidence": "LOW",
                    "reasoning": f"ERROR: {str(e)[:100]}",
                })
                method_verdict_counts[name]["ERROR"] += 1

        # Ensemble vote
        final = vote(method_results)

        results.append({
            "id1": pair["id1"],
            "id2": pair["id2"],
            "display_name_1": pair["display_name_1"],
            "display_name_2": pair["display_name_2"],
            "city_1": pair.get("city_1"),
            "city_2": pair.get("city_2"),
            "zip_1": pair.get("zip_1"),
            "zip_2": pair.get("zip_2"),
            "ein_1": pair.get("ein_1"),
            "ein_2": pair.get("ein_2"),
            "source_1": pair.get("source_1"),
            "source_2": pair.get("source_2"),
            "heuristic_class": pair["classification"],
            "heuristic_composite": pair["scores"]["composite"],
            "blocking_methods": pair.get("blocking_methods", []),
            "ensemble_verdict": final["verdict"],
            "ensemble_confidence": final["confidence"],
            "vote_counts": final["vote_counts"],
            "weighted_scores": final["weighted_scores"],
            "agreement_ratio": final["agreement_ratio"],
            "per_method_reasoning": final["reasoning"],
        })

    elapsed = time.time() - t0
    print(f"\nProcessed {len(results):,} pairs in {elapsed:.1f}s")

    # --- Stats ---
    print("\n" + "=" * 70)
    print("ENSEMBLE RESULTS SUMMARY")
    print("=" * 70)

    # Overall verdict distribution
    verdict_counts = Counter(r["ensemble_verdict"] for r in results)
    print("\nFinal verdict distribution:")
    for v in ["DUPLICATE", "RELATED", "DIFFERENT"]:
        print(f"  {v}: {verdict_counts.get(v, 0):,}")

    # Confidence distribution
    conf_counts = Counter(r["ensemble_confidence"] for r in results)
    print("\nConfidence distribution:")
    for c in ["HIGH", "MEDIUM", "LOW"]:
        print(f"  {c}: {conf_counts.get(c, 0):,}")

    # By verdict + confidence
    print("\nVerdict x Confidence:")
    for v in ["DUPLICATE", "RELATED", "DIFFERENT"]:
        subset = [r for r in results if r["ensemble_verdict"] == v]
        confs = Counter(r["ensemble_confidence"] for r in subset)
        print(f"  {v}: HIGH={confs.get('HIGH',0):,}  MEDIUM={confs.get('MEDIUM',0):,}  LOW={confs.get('LOW',0):,}")

    # Heuristic vs ensemble comparison
    print("\nHeuristic vs Ensemble comparison:")
    for hclass in ["auto_duplicate", "ambiguous", "auto_different"]:
        subset = [r for r in results if r["heuristic_class"] == hclass]
        if not subset:
            continue
        vcts = Counter(r["ensemble_verdict"] for r in subset)
        print(f"  {hclass} ({len(subset):,} pairs):")
        for v in ["DUPLICATE", "RELATED", "DIFFERENT"]:
            if vcts.get(v, 0) > 0:
                print(f"    -> {v}: {vcts[v]:,} ({100*vcts[v]/len(subset):.1f}%)")

    # Per-method verdict distribution
    print("\nPer-method verdict distribution:")
    for name in methods:
        cts = method_verdict_counts[name]
        print(f"  {name}:")
        for v in ["DUPLICATE", "RELATED", "DIFFERENT", "ERROR"]:
            if cts.get(v, 0) > 0:
                print(f"    {v}: {cts[v]:,}")

    # Error report
    if errors:
        print("\nMethod errors:")
        for name, cnt in errors.items():
            print(f"  {name}: {cnt:,} errors")

    # Agreement analysis
    agreement_levels = Counter()
    for r in results:
        ratio = r["agreement_ratio"]
        if ratio >= 0.8:
            agreement_levels["strong (>=0.8)"] += 1
        elif ratio >= 0.6:
            agreement_levels["moderate (0.6-0.8)"] += 1
        else:
            agreement_levels["weak (<0.6)"] += 1
    print("\nMethod agreement levels:")
    for level, cnt in sorted(agreement_levels.items()):
        print(f"  {level}: {cnt:,}")

    # --- Save results ---

    # Full results
    full_path = RESULTS_DIR / "ensemble_full_results.json"
    with open(full_path, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print(f"\nFull results: {full_path}")

    # Duplicates only (sorted by confidence)
    dupes = [r for r in results if r["ensemble_verdict"] == "DUPLICATE"]
    dupes.sort(key=lambda x: -CONF_WEIGHT.get(x["ensemble_confidence"], 0))
    dupes_path = RESULTS_DIR / "duplicates_found.json"
    with open(dupes_path, "w") as f:
        json.dump(dupes, f, indent=1, default=str)
    print(f"Duplicates: {dupes_path} ({len(dupes):,} pairs)")

    # Related only
    related = [r for r in results if r["ensemble_verdict"] == "RELATED"]
    related.sort(key=lambda x: -CONF_WEIGHT.get(x["ensemble_confidence"], 0))
    related_path = RESULTS_DIR / "related_found.json"
    with open(related_path, "w") as f:
        json.dump(related, f, indent=1, default=str)
    print(f"Related: {related_path} ({len(related):,} pairs)")

    # Disagreements (where heuristic and ensemble disagree)
    disagreements = []
    for r in results:
        hclass = r["heuristic_class"]
        verdict = r["ensemble_verdict"]
        if hclass == "auto_duplicate" and verdict != "DUPLICATE":
            disagreements.append({**r, "disagreement": f"heuristic=auto_duplicate, ensemble={verdict}"})
        elif hclass == "auto_different" and verdict != "DIFFERENT":
            disagreements.append({**r, "disagreement": f"heuristic=auto_different, ensemble={verdict}"})
    disagree_path = RESULTS_DIR / "heuristic_disagreements.json"
    with open(disagree_path, "w") as f:
        json.dump(disagreements, f, indent=1, default=str)
    print(f"Heuristic disagreements: {disagree_path} ({len(disagreements):,} pairs)")

    # CSV summary for easy viewing
    csv_path = RESULTS_DIR / "summary.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("id1,id2,name1,name2,city1,city2,zip1,zip2,ein1,ein2,src1,src2,heuristic,composite,verdict,confidence,agreement,vote_dup,vote_rel,vote_diff\n")
        for r in results:
            if r["ensemble_verdict"] in ("DUPLICATE", "RELATED"):
                vc = r["vote_counts"]
                f.write(",".join([
                    str(r["id1"]), str(r["id2"]),
                    f'"{(r["display_name_1"] or "").replace(chr(34), "")}"',
                    f'"{(r["display_name_2"] or "").replace(chr(34), "")}"',
                    f'"{r.get("city_1") or ""}"', f'"{r.get("city_2") or ""}"',
                    str(r.get("zip_1") or ""), str(r.get("zip_2") or ""),
                    str(r.get("ein_1") or ""), str(r.get("ein_2") or ""),
                    str(r.get("source_1") or ""), str(r.get("source_2") or ""),
                    r["heuristic_class"], f'{r["heuristic_composite"]:.4f}',
                    r["ensemble_verdict"], r["ensemble_confidence"],
                    f'{r["agreement_ratio"]:.3f}',
                    str(vc.get("DUPLICATE", 0)), str(vc.get("RELATED", 0)), str(vc.get("DIFFERENT", 0)),
                ]) + "\n")
    print(f"CSV summary (DUPLICATE+RELATED only): {csv_path}")

    total_elapsed = time.time() - t0
    print(f"\nTotal elapsed: {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
