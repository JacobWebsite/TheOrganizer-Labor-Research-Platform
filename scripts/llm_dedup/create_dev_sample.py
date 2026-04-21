#!/usr/bin/env python
"""Create a stratified sample of 100 pairs for agent rule development."""
import json
import os
import random
random.seed(42)

DIR = os.path.dirname(__file__)
with open(os.path.join(DIR, "candidates_scored.json")) as f:
    pairs = json.load(f)

auto_dup = [p for p in pairs if p["classification"] == "auto_duplicate"]
auto_diff = [p for p in pairs if p["classification"] == "auto_different"]
ambiguous = [p for p in pairs if p["classification"] == "ambiguous"]

# Tier ambiguous by composite
tier_a = [p for p in ambiguous if p["scores"]["composite"] >= 0.55]
tier_b = [p for p in ambiguous if 0.40 <= p["scores"]["composite"] < 0.55]
tier_c = [p for p in ambiguous if p["scores"]["composite"] < 0.40]

def sample(lst, n):
    return random.sample(lst, min(n, len(lst)))

dev = []
dev.extend(sample(auto_dup, 20))
dev.extend(sample(tier_a, 25))
dev.extend(sample(tier_b, 25))
dev.extend(sample(tier_c, 15))
dev.extend(sample(auto_diff, 15))

# Shuffle and add labels
random.shuffle(dev)
for i, p in enumerate(dev):
    p["sample_idx"] = i

# Write compact version
compact = []
for p in dev:
    compact.append({
        "idx": p["sample_idx"],
        "heuristic_class": p["classification"],
        "composite": p["scores"]["composite"],
        "id1": p["id1"], "id2": p["id2"],
        "name1": p["display_name_1"], "name2": p["display_name_2"],
        "cname1": p["canonical_name_1"], "cname2": p["canonical_name_2"],
        "city1": p.get("city_1"), "city2": p.get("city_2"),
        "zip1": p.get("zip_1"), "zip2": p.get("zip_2"),
        "ein1": p.get("ein_1"), "ein2": p.get("ein_2"),
        "naics1": p.get("naics_1"), "naics2": p.get("naics_2"),
        "src1": p.get("source_1"), "src2": p.get("source_2"),
        "emp1": p.get("employee_count_1"), "emp2": p.get("employee_count_2"),
        "pub1": p.get("is_public_1"), "pub2": p.get("is_public_2"),
        "np1": p.get("is_nonprofit_1"), "np2": p.get("is_nonprofit_2"),
        "web1": p.get("website_1"), "web2": p.get("website_2"),
        "ind1": p.get("industry_1"), "ind2": p.get("industry_2"),
        "methods": p.get("blocking_methods"),
        "scores": p["scores"],
    })

path = os.path.join(DIR, "dev_sample_100.json")
with open(path, "w") as f:
    json.dump(compact, f, indent=1)
print(f"Wrote {len(compact)} pairs to {path}")

# Also show distribution
from collections import Counter
classes = Counter(p["heuristic_class"] for p in dev)
print(f"Distribution: {dict(classes)}")
