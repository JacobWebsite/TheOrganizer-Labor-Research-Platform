#!/usr/bin/env python
"""
Phase 2: Prepare batches for LLM sub-agent processing.
Reads candidates_scored.json, splits into method-specific batches,
writes compact batch files that agents can read and judge.
"""

import json
import os

DIR = os.path.dirname(__file__)
INPUT = os.path.join(DIR, "candidates_scored.json")
BATCH_DIR = os.path.join(DIR, "batches")
os.makedirs(BATCH_DIR, exist_ok=True)

with open(INPUT) as f:
    pairs = json.load(f)

print(f"Total pairs: {len(pairs):,}")

# --- Categorize ---
auto_dup = [p for p in pairs if p["classification"] == "auto_duplicate"]
auto_diff = [p for p in pairs if p["classification"] == "auto_different"]
ambiguous = [p for p in pairs if p["classification"] == "ambiguous"]

print(f"Auto-duplicate: {len(auto_dup):,}")
print(f"Auto-different: {len(auto_diff):,}")
print(f"Ambiguous: {len(ambiguous):,}")

# Sort ambiguous by composite descending
ambiguous.sort(key=lambda x: -x["scores"]["composite"])

# --- Tier the ambiguous pairs ---
tier_a = [p for p in ambiguous if p["scores"]["composite"] >= 0.55]
tier_b = [p for p in ambiguous if 0.40 <= p["scores"]["composite"] < 0.55]
tier_c = [p for p in ambiguous if p["scores"]["composite"] < 0.40]

print("\nAmbiguous tiers:")
print(f"  Tier A (>=0.55): {len(tier_a):,}")
print(f"  Tier B (0.40-0.55): {len(tier_b):,}")
print(f"  Tier C (<0.40): {len(tier_c):,}")

def compact(pair):
    """Compact representation for agent consumption."""
    return {
        "id1": pair["id1"],
        "id2": pair["id2"],
        "name1": pair["display_name_1"],
        "name2": pair["display_name_2"],
        "cname1": pair["canonical_name_1"],
        "cname2": pair["canonical_name_2"],
        "city1": pair["city_1"],
        "city2": pair["city_2"],
        "zip1": pair["zip_1"],
        "zip2": pair["zip_2"],
        "ein1": pair["ein_1"],
        "ein2": pair["ein_2"],
        "naics1": pair["naics_1"],
        "naics2": pair["naics_2"],
        "src1": pair["source_1"],
        "src2": pair["source_2"],
        "emp1": pair["employee_count_1"],
        "emp2": pair["employee_count_2"],
        "pub1": pair["is_public_1"],
        "pub2": pair["is_public_2"],
        "np1": pair["is_nonprofit_1"],
        "np2": pair["is_nonprofit_2"],
        "web1": pair["website_1"],
        "web2": pair["website_2"],
        "ind1": pair["industry_1"],
        "ind2": pair["industry_2"],
        "methods": pair["blocking_methods"],
        "composite": pair["scores"]["composite"],
        "name_std_sim": pair["scores"]["name_standard_sim"],
        "name_agg_sim": pair["scores"]["name_aggressive_sim"],
        "ein_match": pair["scores"]["ein_match"],
        "ein_conflict": pair["scores"]["ein_conflict"],
        "zip_match": pair["scores"]["zip_exact"],
        "city_match": pair["scores"]["city_match"],
    }

def write_batch(name, data):
    path = os.path.join(BATCH_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump([compact(p) for p in data], f, indent=1)
    print(f"  {name}: {len(data)} pairs -> {path}")

# --- Write batches ---
print("\nWriting batches...")

# Batch 1: Auto-duplicates (for verification)
write_batch("verify_auto_duplicates", auto_dup)

# Batch 2: Tier A ambiguous - highest priority for detailed LLM review
# Split into chunks of ~150 for manageable agent processing
for i in range(0, len(tier_a), 150):
    chunk = tier_a[i:i+150]
    write_batch(f"tier_a_chunk_{i//150}", chunk)

# Batch 3: Tier B - split into chunks of 200
for i in range(0, len(tier_b), 200):
    chunk = tier_b[i:i+200]
    write_batch(f"tier_b_chunk_{i//200}", chunk)

# Batch 4: Tier C - sample 500 for spot-check
import random
random.seed(42)
tier_c_sample = random.sample(tier_c, min(500, len(tier_c)))
write_batch("tier_c_sample", tier_c_sample)

# Batch 5: Auto-different spot-check (random 200)
auto_diff_sample = random.sample(auto_diff, min(200, len(auto_diff)))
write_batch("verify_auto_different", auto_diff_sample)

# --- Summary ---
print("\n--- Batch Summary ---")
batches = os.listdir(BATCH_DIR)
total_pairs = 0
for b in sorted(batches):
    path = os.path.join(BATCH_DIR, b)
    with open(path) as f:
        data = json.load(f)
    total_pairs += len(data)
    print(f"  {b}: {len(data)} pairs")
print(f"\nTotal pairs across all batches: {total_pairs:,}")
