#!/usr/bin/env python
"""
Phase 4: Generate human-readable dedup report.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

DIR = Path(__file__).parent
RESULTS = DIR / "results"


def load(name):
    with open(RESULTS / name) as f:
        return json.load(f)


def main():
    full = load("ensemble_full_results.json")
    dupes = load("duplicates_found.json")
    related = load("related_found.json")
    disagree = load("heuristic_disagreements.json")

    lines = []
    w = lines.append

    w("=" * 80)
    w("LLM-ASSISTED DEDUPLICATION REPORT")
    w("20,000 Random NY Employers from master_employers")
    w("=" * 80)
    w("")

    # --- Overview ---
    w("## METHODOLOGY")
    w("")
    w("1. EXTRACTION: 20,000 random employers from master_employers WHERE state='NY'")
    w("   Sources: bmf(5248), corpwatch(4484), mergent(3077), sec(1806), sam(1597),")
    w("   osha(1228), f7(792), whd(776), gleif(707), 990(154), nlrb(131)")
    w("")
    w("2. BLOCKING: 6 strategies generated 29,212 candidate pairs:")
    w("   - EIN exact match: 12 pairs")
    w("   - Exact canonical name: 32 pairs")
    w("   - Normalized name (strip suffixes/punctuation): 186 pairs")
    w("   - Sorted token match: 1,290 pairs")
    w("   - ZIP + name prefix: 10,512 pairs")
    w("   - City + name prefix: 25,598 pairs")
    w("")
    w("3. HEURISTIC TRIAGE: Cheap scoring classified pairs as:")
    w("   - Auto-duplicate (high confidence match): 607")
    w("   - Ambiguous (needs LLM review): 15,381")
    w("   - Auto-different (clearly different): 13,224")
    w("")
    w("4. LLM ENSEMBLE: 5 Claude sub-agents each developed specialized dedup logic:")
    w("   - Name Analysis: focus on name variants, abbreviations, series detection")
    w("   - Location: geographic signals interacting with name similarity")
    w("   - Business Identity: EIN, NAICS, entity type, employee count")
    w("   - Cross-Source: source-aware thresholds, naming pattern differences")
    w("   - Holistic: weighted point-based system combining all signals")
    w("   Each method independently classified all 29,212 pairs.")
    w("   Final verdict via confidence-weighted majority vote.")
    w("")

    # --- Results ---
    w("=" * 80)
    w("## RESULTS SUMMARY")
    w("=" * 80)
    w("")
    vc = Counter(r["ensemble_verdict"] for r in full)
    w(f"Total pairs evaluated: {len(full):,}")
    w(f"  DUPLICATE (same entity):              {vc.get('DUPLICATE', 0):>6,}")
    w(f"  RELATED (parent/sub, branch, family):  {vc.get('RELATED', 0):>6,}")
    w(f"  DIFFERENT (not the same):              {vc.get('DIFFERENT', 0):>6,}")
    w("")

    # Confidence breakdown
    w("Confidence breakdown:")
    for v in ["DUPLICATE", "RELATED", "DIFFERENT"]:
        subset = [r for r in full if r["ensemble_verdict"] == v]
        confs = Counter(r["ensemble_confidence"] for r in subset)
        w(f"  {v}:  HIGH={confs.get('HIGH',0):,}  MEDIUM={confs.get('MEDIUM',0):,}  LOW={confs.get('LOW',0):,}")
    w("")

    # Heuristic override analysis
    w("Heuristic vs LLM Ensemble comparison:")
    for hclass in ["auto_duplicate", "ambiguous", "auto_different"]:
        subset = [r for r in full if r["heuristic_class"] == hclass]
        if not subset:
            continue
        vcts = Counter(r["ensemble_verdict"] for r in subset)
        w(f"\n  {hclass} ({len(subset):,} pairs from heuristic):")
        for v in ["DUPLICATE", "RELATED", "DIFFERENT"]:
            if vcts.get(v, 0) > 0:
                w(f"    -> Ensemble says {v}: {vcts[v]:,} ({100*vcts[v]/len(subset):.1f}%)")
    w("")

    # --- Top Duplicate Examples ---
    w("=" * 80)
    w("## TOP DUPLICATE EXAMPLES (highest confidence)")
    w("=" * 80)

    # High-confidence duplicates
    high_dupes = [d for d in dupes if d["ensemble_confidence"] == "HIGH"]
    # Prioritize cross-source and ambiguous-to-duplicate
    cross_source_dupes = [d for d in high_dupes if d.get("source_1") != d.get("source_2")]
    upgraded_dupes = [d for d in high_dupes if d["heuristic_class"] == "ambiguous"]

    w(f"\nHigh-confidence duplicates: {len(high_dupes)}")
    w(f"  Cross-source (most valuable): {len(cross_source_dupes)}")
    w(f"  Upgraded from ambiguous: {len(upgraded_dupes)}")
    w("")

    # Show 10 best cross-source duplicates
    w("### Cross-source duplicates (same company found in different gov databases):")
    shown = 0
    for d in cross_source_dupes[:15]:
        shown += 1
        w(f"\n  {shown}. \"{d['display_name_1']}\" ({d.get('source_1','')})")
        w(f"     \"{d['display_name_2']}\" ({d.get('source_2','')})")
        w(f"     Location: {d.get('city_1','?')}/{d.get('zip_1','?')} vs {d.get('city_2','?')}/{d.get('zip_2','?')}")
        e1, e2 = d.get("ein_1"), d.get("ein_2")
        if e1 and e2 and e1 == e2:
            w(f"     EIN: {e1} (MATCH)")
        elif e1 or e2:
            w(f"     EIN: {e1 or 'None'} vs {e2 or 'None'}")
        w(f"     Confidence: {d['ensemble_confidence']} | Agreement: {d['agreement_ratio']:.0%}")
        # Show first 2 method reasons
        for reason in d.get("per_method_reasoning", [])[:2]:
            w(f"     {reason[:120]}")

    # Show 10 best upgraded-from-ambiguous
    w("\n\n### Upgraded from ambiguous (new discoveries by LLM ensemble):")
    shown = 0
    for d in upgraded_dupes[:15]:
        shown += 1
        w(f"\n  {shown}. \"{d['display_name_1']}\" ({d.get('source_1','')})")
        w(f"     \"{d['display_name_2']}\" ({d.get('source_2','')})")
        w(f"     Location: {d.get('city_1','?')}/{d.get('zip_1','?')} vs {d.get('city_2','?')}/{d.get('zip_2','?')}")
        w(f"     Heuristic composite: {d['heuristic_composite']:.4f}")
        w(f"     Ensemble: {d['ensemble_verdict']}/{d['ensemble_confidence']} | Votes: {d['vote_counts']}")
        for reason in d.get("per_method_reasoning", [])[:2]:
            w(f"     {reason[:120]}")

    # --- Top Related Examples ---
    w("\n\n" + "=" * 80)
    w("## TOP RELATED EXAMPLES (parent/subsidiary, branches, fund families)")
    w("=" * 80)

    high_related = [r for r in related if r["ensemble_confidence"] == "HIGH"]
    w(f"\nHigh-confidence related: {len(high_related)}")

    # Categorize related pairs
    fund_family = []
    possible_branch = []
    parent_sub = []
    other_related = []
    for r in related:
        reasons_text = " ".join(r.get("per_method_reasoning", []))
        if "series" in reasons_text.lower() or "fund" in reasons_text.lower() or "trust" in reasons_text.lower():
            fund_family.append(r)
        elif "branch" in reasons_text.lower() or "location" in reasons_text.lower():
            possible_branch.append(r)
        elif "parent" in reasons_text.lower() or "subsidiary" in reasons_text.lower() or "holding" in reasons_text.lower():
            parent_sub.append(r)
        else:
            other_related.append(r)

    w(f"\n  Fund families/series: {len(fund_family)}")
    w(f"  Possible branches: {len(possible_branch)}")
    w(f"  Parent/subsidiary: {len(parent_sub)}")
    w(f"  Other related: {len(other_related)}")

    w("\n### Fund family examples:")
    for r in fund_family[:5]:
        w(f"  - \"{r['display_name_1']}\"")
        w(f"    \"{r['display_name_2']}\"")
        w(f"    Sources: {r.get('source_1','?')}/{r.get('source_2','?')} | {r.get('city_1','?')}")

    if parent_sub:
        w("\n### Parent/subsidiary examples:")
        for r in parent_sub[:5]:
            w(f"  - \"{r['display_name_1']}\"")
            w(f"    \"{r['display_name_2']}\"")
            w(f"    Sources: {r.get('source_1','?')}/{r.get('source_2','?')}")

    # --- Heuristic Override Examples ---
    w("\n\n" + "=" * 80)
    w("## HEURISTIC OVERRIDES (where LLM corrected the heuristic)")
    w("=" * 80)

    # auto_duplicate -> DIFFERENT (heuristic was wrong)
    overturned = [d for d in disagree if "auto_duplicate" in d.get("disagreement", "")]
    w(f"\nHeuristic said auto_duplicate but LLM says otherwise: {len(overturned)}")
    w("(These are mostly numbered fund series the heuristic couldn't distinguish)")
    for d in overturned[:8]:
        w(f"\n  \"{d['display_name_1']}\"")
        w(f"  \"{d['display_name_2']}\"")
        w(f"  Heuristic: auto_duplicate (composite={d['heuristic_composite']:.4f})")
        w(f"  Ensemble: {d['ensemble_verdict']}/{d['ensemble_confidence']} | Votes: {d['vote_counts']}")
        # Find the name analysis reason
        for reason in d.get("per_method_reasoning", []):
            if "method_name_analysis" in reason:
                w(f"  Name Analysis: {reason[22:150]}")
                break

    # auto_different -> DUPLICATE (hidden dupes the heuristic missed)
    hidden = [r for r in full if r["heuristic_class"] == "auto_different" and r["ensemble_verdict"] != "DIFFERENT"]
    if hidden:
        w(f"\n\nHeuristic said auto_different but LLM found matches: {len(hidden)}")
        for h in hidden[:5]:
            w(f"  \"{h['display_name_1']}\" vs \"{h['display_name_2']}\"")
            w(f"  Ensemble: {h['ensemble_verdict']}/{h['ensemble_confidence']}")

    # --- Method Agreement Analysis ---
    w("\n\n" + "=" * 80)
    w("## METHOD AGREEMENT ANALYSIS")
    w("=" * 80)

    method_names = ["method_name_analysis", "method_location", "method_business_identity",
                    "method_cross_source", "method_holistic"]

    w("\nPer-method verdict distribution across all 29,212 pairs:")
    method_totals = {m: Counter() for m in method_names}
    for r in full:
        for reason in r.get("per_method_reasoning", []):
            for m in method_names:
                if m in reason:
                    # Extract verdict
                    after = reason.split("] ")[1] if "] " in reason else ""
                    verdict = after.split("/")[0] if "/" in after else "?"
                    method_totals[m][verdict] += 1

    for m in method_names:
        short = m.replace("method_", "")
        cts = method_totals[m]
        w(f"  {short:20s}: DUP={cts.get('DUPLICATE',0):>5,}  REL={cts.get('RELATED',0):>5,}  DIFF={cts.get('DIFFERENT',0):>5,}")

    # Agreement strength
    agreement = Counter()
    for r in full:
        ratio = r["agreement_ratio"]
        if ratio >= 0.8:
            agreement["strong (80%+)"] += 1
        elif ratio >= 0.6:
            agreement["moderate (60-80%)"] += 1
        else:
            agreement["weak (<60%)"] += 1
    w(f"\nAgreement levels:")
    for level in sorted(agreement):
        w(f"  {level}: {agreement[level]:,}")

    # Most contentious pairs (lowest agreement)
    contentious = sorted(full, key=lambda x: x["agreement_ratio"])[:10]
    w(f"\n### Most contentious pairs (methods disagree most):")
    for c in contentious:
        w(f"  \"{c['display_name_1'][:50]}\" vs \"{c['display_name_2'][:50]}\"")
        w(f"  Votes: {c['vote_counts']} -> {c['ensemble_verdict']}/{c['ensemble_confidence']}")

    # --- Source Analysis ---
    w("\n\n" + "=" * 80)
    w("## SOURCE PAIR ANALYSIS")
    w("=" * 80)

    source_pairs = defaultdict(lambda: Counter())
    for r in full:
        s1, s2 = r.get("source_1", "?"), r.get("source_2", "?")
        key = tuple(sorted([s1, s2]))
        source_pairs[key][r["ensemble_verdict"]] += 1

    w("\nDuplicates and Related by source pair:")
    interesting = [(k, v) for k, v in source_pairs.items()
                   if v.get("DUPLICATE", 0) + v.get("RELATED", 0) > 0]
    interesting.sort(key=lambda x: -(x[1].get("DUPLICATE", 0) + x[1].get("RELATED", 0)))
    for (s1, s2), cts in interesting[:20]:
        total = sum(cts.values())
        dup = cts.get("DUPLICATE", 0)
        rel = cts.get("RELATED", 0)
        diff = cts.get("DIFFERENT", 0)
        w(f"  {s1}/{s2}: {total:,} pairs -> DUP={dup}, REL={rel}, DIFF={diff} ({100*(dup+rel)/total:.0f}% match rate)")

    # --- Key Findings ---
    w("\n\n" + "=" * 80)
    w("## KEY FINDINGS")
    w("=" * 80)

    dup_from_ambiguous = len([r for r in full if r["heuristic_class"] == "ambiguous" and r["ensemble_verdict"] == "DUPLICATE"])
    rel_from_ambiguous = len([r for r in full if r["heuristic_class"] == "ambiguous" and r["ensemble_verdict"] == "RELATED"])
    overturned_dup = len([r for r in full if r["heuristic_class"] == "auto_duplicate" and r["ensemble_verdict"] != "DUPLICATE"])

    w(f"""
1. OUT OF 20,000 NY EMPLOYERS, the pipeline found:
   - {vc.get('DUPLICATE',0):,} duplicate pairs (same entity, different records)
   - {vc.get('RELATED',0):,} related pairs (parent/subsidiary, fund families, branches)
   This represents significant data redundancy in the master table.

2. THE LLM ENSEMBLE CORRECTED THE HEURISTIC IN {overturned_dup:,} CASES:
   The simple string-similarity heuristic classified 607 pairs as auto-duplicate,
   but the LLM ensemble overturned {overturned_dup:,} of them ({100*overturned_dup/607:.0f}%).
   Most were numbered fund series (e.g., "Defined Asset Funds Series 51 vs 58")
   that look identical to a string matcher but are legally distinct entities.

3. THE LLM ENSEMBLE FOUND {dup_from_ambiguous:,} NEW DUPLICATES the heuristic missed:
   These were classified as "ambiguous" by the heuristic but the ensemble
   confidently identified them as the same entity using multi-signal reasoning.

4. {rel_from_ambiguous:,} RELATED ENTITIES were identified:
   The RELATED category is a unique LLM contribution -- heuristics can only say
   "same" or "different," but the LLM methods can reason about corporate
   relationships (parent/subsidiary, fund families, branches).

5. METHOD COMPARISON shows different strengths:
   - Name Analysis: most conservative, best at catching false positives (fund series)
   - Location: moderately aggressive, good at confirming cross-source matches
   - Business Identity: EIN-focused, very reliable when EIN data exists
   - Cross-Source: source-aware thresholds, catches naming convention differences
   - Holistic: most nuanced RELATED detection, but tends toward over-classification
""")

    # Write report
    report_path = RESULTS / "DEDUP_REPORT.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written to {report_path}")
    print(f"({len(lines)} lines)")

    # Also print to stdout
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
