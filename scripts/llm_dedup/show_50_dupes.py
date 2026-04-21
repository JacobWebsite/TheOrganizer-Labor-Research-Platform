#!/usr/bin/env python
"""Print 50 diverse duplicates in a readable format for spot-checking."""
import json
import random
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
with open(RESULTS / "duplicates_found.json") as f:
    dupes = json.load(f)

# Stratified sample: mix of confidence levels and source types
high = [d for d in dupes if d["ensemble_confidence"] == "HIGH"]
med = [d for d in dupes if d["ensemble_confidence"] == "MEDIUM"]
low = [d for d in dupes if d["ensemble_confidence"] == "LOW"]

random.seed(99)
sample = []
sample.extend(random.sample(high, min(20, len(high))))
sample.extend(random.sample(med, min(20, len(med))))
sample.extend(random.sample(low, min(10, len(low))))
random.shuffle(sample)

for i, d in enumerate(sample, 1):
    n1 = d["display_name_1"] or ""
    n2 = d["display_name_2"] or ""
    c1 = d.get("city_1") or "?"
    c2 = d.get("city_2") or "?"
    z1 = d.get("zip_1") or "?"
    z2 = d.get("zip_2") or "?"
    e1 = d.get("ein_1") or "-"
    e2 = d.get("ein_2") or "-"
    s1 = d.get("source_1") or "?"
    s2 = d.get("source_2") or "?"
    conf = d["ensemble_confidence"]
    agree = d["agreement_ratio"]
    votes = d["vote_counts"]
    heur = d["heuristic_class"]
    comp = d["heuristic_composite"]

    # Get the most informative reasoning (pick the one with most detail)
    reasons = d.get("per_method_reasoning", [])
    # Pick name_analysis and one other
    name_reason = ""
    other_reason = ""
    for r in reasons:
        if "name_analysis" in r:
            name_reason = r.split("] ", 1)[1] if "] " in r else r
        elif not other_reason and ("business_identity" in r or "cross_source" in r):
            other_reason = r.split("] ", 1)[1] if "] " in r else r

    print(f"{'='*80}")
    print(f"#{i:02d}  Confidence: {conf}  |  Agreement: {agree:.0%}  |  Votes: {votes}")
    print(f"     Heuristic: {heur} (composite={comp:.4f})")
    print(f"  A: \"{n1}\"")
    print(f"     [{s1}]  {c1}, NY {z1}  EIN={e1}")
    print(f"  B: \"{n2}\"")
    print(f"     [{s2}]  {c2}, NY {z2}  EIN={e2}")
    if name_reason:
        print(f"  Name: {name_reason[:150]}")
    if other_reason:
        print(f"  ID:   {other_reason[:150]}")
    print()
