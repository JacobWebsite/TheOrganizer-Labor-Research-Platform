#!/usr/bin/env python
"""
Phase 1: Blocking and Candidate Pair Generation
================================================
Generates candidate duplicate pairs from 20K NY employer sample
using 6 independent blocking strategies. Scores each pair with
cheap heuristics and classifies into auto-merge, ambiguous, and auto-skip.

Output: candidates_scored.json
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

sys.path.insert(0, r"C:\Users\jakew\.local\bin\Labor Data Project_real")

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "ny_sample_20k.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "candidates_scored.json")
STATS_PATH  = os.path.join(os.path.dirname(__file__), "blocking_stats.json")

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

LEGAL_SUFFIXES = re.compile(
    r"\b("
    r"llc|l\.l\.c|inc|incorporated|corp|corporation|company|co|ltd|limited|"
    r"lp|l\.p|llp|l\.l\.p|pc|p\.c|pllc|pa|p\.a|na|n\.a|sa|s\.a|"
    r"gmbh|plc|ag|bv|nv|se|srl|sarl|"
    r"group|holdings?|enterprises?|associates?|partners?|partnership|"
    r"services?|solutions?|consulting|consultants?|international|intl|"
    r"industries|industrial|technologies|technology|tech|"
    r"management|mgmt|financial|capital|investments?|"
    r"construction|contractors?|builders?|"
    r"medical|healthcare|health|hospital|"
    r"real\s*estate|properties|property|realty|"
    r"foundation|fund|trust|"
    r"of|the|and|an|a"
    r")\b",
    re.IGNORECASE,
)

PUNCT_RE = re.compile(r"[^a-z0-9\s]")
MULTI_SPACE = re.compile(r"\s+")

# Common abbreviation expansions
ABBREVS = {
    "hosp": "hospital",
    "ctr": "center",
    "cntrl": "central",
    "assn": "association",
    "dept": "department",
    "natl": "national",
    "govt": "government",
    "mfg": "manufacturing",
    "mgmt": "management",
    "sys": "systems",
    "svcs": "services",
    "svc": "service",
    "intl": "international",
    "univ": "university",
    "inst": "institute",
    "bldg": "building",
    "constr": "construction",
    "dev": "development",
    "dist": "distribution",
    "environ": "environmental",
    "equip": "equipment",
    "engr": "engineering",
    "eng": "engineering",
    "maint": "maintenance",
    "amer": "american",
    "ny": "new york",
    "nyc": "new york city",
}


def normalize_light(name: str) -> str:
    """Light normalization: lowercase, strip punctuation, collapse spaces."""
    name = name.lower().strip()
    name = PUNCT_RE.sub(" ", name)
    return MULTI_SPACE.sub(" ", name).strip()


def normalize_standard(name: str) -> str:
    """Standard: light + strip legal suffixes."""
    name = normalize_light(name)
    name = LEGAL_SUFFIXES.sub("", name)
    return MULTI_SPACE.sub(" ", name).strip()


def normalize_aggressive(name: str) -> str:
    """Aggressive: standard + expand abbreviations + remove short tokens."""
    name = normalize_standard(name)
    tokens = name.split()
    expanded = [ABBREVS.get(t, t) for t in tokens]
    # Remove single-character tokens and standalone numbers
    expanded = [t for t in expanded if len(t) > 1 and not t.isdigit()]
    return " ".join(expanded)


def sorted_tokens(name: str) -> str:
    """Sort tokens alphabetically for order-independent matching."""
    return " ".join(sorted(normalize_aggressive(name).split()))


def name_prefix(name: str, length: int = 5) -> str:
    n = normalize_standard(name).replace(" ", "")
    return n[:length] if len(n) >= length else n


def name_bigrams(name: str) -> set:
    """Character bigrams for Jaccard similarity."""
    n = normalize_standard(name)
    if len(n) < 2:
        return set()
    return {n[i : i + 2] for i in range(len(n) - 1)}


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def string_sim(a: str, b: str) -> float:
    """SequenceMatcher ratio (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def jaccard_sim(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def token_overlap(a: str, b: str) -> float:
    """Fraction of tokens shared between two strings."""
    ta = set(normalize_aggressive(a).split())
    tb = set(normalize_aggressive(b).split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    smaller = min(len(ta), len(tb))
    return inter / smaller if smaller else 0.0


def score_pair(r1: dict, r2: dict) -> dict:
    """Compute similarity scores for a candidate pair."""
    cn1, cn2 = r1["canonical_name"], r2["canonical_name"]

    scores = {}

    # Name similarities
    scores["name_exact"] = 1.0 if cn1 == cn2 else 0.0
    scores["name_standard_sim"] = string_sim(
        normalize_standard(cn1), normalize_standard(cn2)
    )
    scores["name_aggressive_sim"] = string_sim(
        normalize_aggressive(cn1), normalize_aggressive(cn2)
    )
    scores["name_sorted_token_sim"] = string_sim(
        sorted_tokens(cn1), sorted_tokens(cn2)
    )
    scores["name_bigram_jaccard"] = jaccard_sim(name_bigrams(cn1), name_bigrams(cn2))
    scores["name_token_overlap"] = token_overlap(cn1, cn2)

    # EIN
    e1, e2 = r1.get("ein"), r2.get("ein")
    scores["ein_match"] = 1.0 if (e1 and e2 and e1 == e2) else 0.0
    scores["ein_conflict"] = 1.0 if (e1 and e2 and e1 != e2) else 0.0

    # Location
    z1, z2 = (r1.get("zip") or ""), (r2.get("zip") or "")
    c1, c2 = (r1.get("city") or "").lower().strip(), (r2.get("city") or "").lower().strip()
    scores["zip_exact"] = 1.0 if (z1 and z2 and z1 == z2) else 0.0
    scores["zip5_match"] = 1.0 if (z1[:5] == z2[:5] and len(z1) >= 5 and len(z2) >= 5) else 0.0
    scores["city_match"] = 1.0 if (c1 and c2 and c1 == c2) else 0.0

    # NAICS
    n1, n2 = (r1.get("naics") or ""), (r2.get("naics") or "")
    scores["naics_exact"] = 1.0 if (n1 and n2 and n1 == n2) else 0.0
    scores["naics_2digit"] = 1.0 if (n1[:2] == n2[:2] and len(n1) >= 2 and len(n2) >= 2) else 0.0

    # Source
    scores["same_source"] = 1.0 if r1.get("source_origin") == r2.get("source_origin") else 0.0

    # Employee count similarity
    ec1, ec2 = r1.get("employee_count"), r2.get("employee_count")
    if ec1 and ec2 and ec1 > 0 and ec2 > 0:
        ratio = min(ec1, ec2) / max(ec1, ec2)
        scores["employee_ratio"] = ratio
    else:
        scores["employee_ratio"] = -1.0  # unknown

    # Composite score (weighted)
    composite = (
        scores["name_standard_sim"] * 0.20
        + scores["name_aggressive_sim"] * 0.15
        + scores["name_sorted_token_sim"] * 0.10
        + scores["name_bigram_jaccard"] * 0.05
        + scores["ein_match"] * 0.25
        + scores["zip5_match"] * 0.10
        + scores["city_match"] * 0.05
        + scores["naics_2digit"] * 0.05
        + scores["name_token_overlap"] * 0.05
    )
    # Penalty for EIN conflict
    if scores["ein_conflict"]:
        composite *= 0.5

    scores["composite"] = round(composite, 4)
    return scores


# ---------------------------------------------------------------------------
# Blocking strategies
# ---------------------------------------------------------------------------

MAX_GROUP = 100  # Skip degenerate groups (e.g., blank EIN buckets)


def _pairs_from_group(ids: list, method: str, candidates: dict):
    """Add all pairs from a group to the candidate dict."""
    if len(ids) < 2 or len(ids) > MAX_GROUP:
        return
    for a, b in combinations(sorted(ids), 2):
        key = (min(a, b), max(a, b))
        candidates.setdefault(key, set()).add(method)


def block_ein(records: list) -> dict:
    """Strategy 1: Group by exact EIN."""
    groups = defaultdict(list)
    for r in records:
        if r.get("ein"):
            groups[r["ein"]].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "ein_exact", cands)
    return cands


def block_exact_name(records: list) -> dict:
    """Strategy 2: Group by exact canonical_name."""
    groups = defaultdict(list)
    for r in records:
        groups[r["canonical_name"]].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "exact_name", cands)
    return cands


def block_normalized_name(records: list) -> dict:
    """Strategy 3: Group by standard-normalized name."""
    groups = defaultdict(list)
    for r in records:
        nn = normalize_standard(r["canonical_name"])
        if nn:
            groups[nn].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "normalized_name", cands)
    return cands


def block_sorted_tokens(records: list) -> dict:
    """Strategy 4: Group by sorted token representation."""
    groups = defaultdict(list)
    for r in records:
        st = sorted_tokens(r["canonical_name"])
        if st:
            groups[st].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "sorted_tokens", cands)
    return cands


def block_zip_name_prefix(records: list) -> dict:
    """Strategy 5: Group by ZIP + first 5 chars of normalized name."""
    groups = defaultdict(list)
    for r in records:
        z = r.get("zip")
        if z and r["canonical_name"]:
            pf = name_prefix(r["canonical_name"], 5)
            if pf:
                groups[f"{z}|{pf}"].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "zip_name_prefix", cands)
    return cands


def block_city_name_prefix(records: list) -> dict:
    """Strategy 6: Group by city + first 5 chars of normalized name."""
    groups = defaultdict(list)
    for r in records:
        city = (r.get("city") or "").lower().strip()
        if city and r["canonical_name"]:
            pf = name_prefix(r["canonical_name"], 5)
            if pf:
                groups[f"{city}|{pf}"].append(r["master_id"])
    cands = {}
    for ids in groups.values():
        _pairs_from_group(ids, "city_name_prefix", cands)
    return cands


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def classify_pair(scores: dict) -> str:
    """
    Classify a scored pair:
      - auto_duplicate: very high confidence, skip LLM
      - auto_different: very low confidence, skip LLM
      - ambiguous: send to LLM for judgment
    """
    c = scores["composite"]
    ein_match = scores["ein_match"]
    ein_conflict = scores["ein_conflict"]
    name_std = scores["name_standard_sim"]
    name_agg = scores["name_aggressive_sim"]

    # Auto-duplicate: same EIN + reasonable name similarity
    if ein_match and name_std >= 0.5:
        return "auto_duplicate"

    # Auto-duplicate: extremely high name similarity across all measures
    if name_std >= 0.95 and name_agg >= 0.95:
        return "auto_duplicate"

    # Auto-different: EIN conflict (different EINs) with low name similarity
    if ein_conflict and name_std < 0.8:
        return "auto_different"

    # Auto-different: very low composite
    if c < 0.25:
        return "auto_different"

    # Auto-different: low name similarity with no confirming signals
    if name_agg < 0.5 and not ein_match and scores["zip_exact"] < 1.0:
        return "auto_different"

    # Everything else is ambiguous -> send to LLM
    return "ambiguous"


def main():
    t0 = time.time()
    print("Loading sample data...")
    with open(SAMPLE_PATH) as f:
        records = json.load(f)
    print(f"  Loaded {len(records):,} records")

    by_id = {r["master_id"]: r for r in records}

    # Run all 6 blocking strategies
    print("\nRunning blocking strategies...")
    all_candidates = {}
    strategies = [
        ("1. EIN exact",           block_ein),
        ("2. Exact name",          block_exact_name),
        ("3. Normalized name",     block_normalized_name),
        ("4. Sorted tokens",       block_sorted_tokens),
        ("5. ZIP + name prefix",   block_zip_name_prefix),
        ("6. City + name prefix",  block_city_name_prefix),
    ]

    strategy_stats = {}
    for label, func in strategies:
        t1 = time.time()
        cands = func(records)
        elapsed = time.time() - t1
        # Merge into all_candidates
        for key, methods in cands.items():
            all_candidates.setdefault(key, set()).update(methods)
        unique_new = len(cands)
        print(f"  {label}: {unique_new:,} pairs ({elapsed:.2f}s)")
        strategy_stats[label] = unique_new

    print(f"\n  Total unique candidate pairs: {len(all_candidates):,}")

    # Score all pairs
    print("\nScoring candidate pairs...")
    scored_pairs = []
    t1 = time.time()
    for (id1, id2), methods in all_candidates.items():
        r1, r2 = by_id[id1], by_id[id2]
        scores = score_pair(r1, r2)
        classification = classify_pair(scores)
        scored_pairs.append({
            "id1": id1,
            "id2": id2,
            "display_name_1": r1["display_name"],
            "display_name_2": r2["display_name"],
            "canonical_name_1": r1["canonical_name"],
            "canonical_name_2": r2["canonical_name"],
            "city_1": r1.get("city"),
            "city_2": r2.get("city"),
            "zip_1": r1.get("zip"),
            "zip_2": r2.get("zip"),
            "ein_1": r1.get("ein"),
            "ein_2": r2.get("ein"),
            "naics_1": r1.get("naics"),
            "naics_2": r2.get("naics"),
            "source_1": r1.get("source_origin"),
            "source_2": r2.get("source_origin"),
            "employee_count_1": r1.get("employee_count"),
            "employee_count_2": r2.get("employee_count"),
            "is_public_1": r1.get("is_public"),
            "is_public_2": r2.get("is_public"),
            "is_nonprofit_1": r1.get("is_nonprofit"),
            "is_nonprofit_2": r2.get("is_nonprofit"),
            "website_1": r1.get("website"),
            "website_2": r2.get("website"),
            "industry_1": r1.get("industry_text"),
            "industry_2": r2.get("industry_text"),
            "blocking_methods": sorted(methods),
            "scores": scores,
            "classification": classification,
        })
    elapsed = time.time() - t1
    print(f"  Scored {len(scored_pairs):,} pairs in {elapsed:.2f}s")

    # Classification breakdown
    class_counts = defaultdict(int)
    for p in scored_pairs:
        class_counts[p["classification"]] += 1
    print("\nClassification breakdown:")
    for cls, cnt in sorted(class_counts.items()):
        print(f"  {cls}: {cnt:,}")

    # Method overlap stats
    method_counts = defaultdict(int)
    for p in scored_pairs:
        for m in p["blocking_methods"]:
            method_counts[m] += 1
    print("\nBlocking method contribution:")
    for m, cnt in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  {m}: {cnt:,} pairs")

    # Multi-method pairs
    multi = sum(1 for p in scored_pairs if len(p["blocking_methods"]) > 1)
    print(f"\n  Pairs found by multiple methods: {multi:,}")

    # Score distribution for ambiguous pairs
    ambiguous = [p for p in scored_pairs if p["classification"] == "ambiguous"]
    if ambiguous:
        composites = [p["scores"]["composite"] for p in ambiguous]
        composites.sort()
        print("\nAmbiguous pair composite score distribution:")
        print(f"  Min: {composites[0]:.4f}")
        print(f"  25th: {composites[len(composites)//4]:.4f}")
        print(f"  Median: {composites[len(composites)//2]:.4f}")
        print(f"  75th: {composites[3*len(composites)//4]:.4f}")
        print(f"  Max: {composites[-1]:.4f}")

    # Sort by composite score descending
    scored_pairs.sort(key=lambda x: -x["scores"]["composite"])

    # Convert sets to lists for JSON serialization
    for p in scored_pairs:
        p["blocking_methods"] = list(p["blocking_methods"])

    # Save
    with open(OUTPUT_PATH, "w") as f:
        json.dump(scored_pairs, f, indent=2, default=str)
    print(f"\nSaved {len(scored_pairs):,} scored pairs to {OUTPUT_PATH}")

    # Save stats
    stats = {
        "total_records": len(records),
        "total_candidate_pairs": len(all_candidates),
        "strategy_stats": strategy_stats,
        "classification_counts": dict(class_counts),
        "method_contribution": dict(method_counts),
        "multi_method_pairs": multi,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(STATS_PATH, "w") as f:
        json.dump(stats, f, indent=2)

    total = time.time() - t0
    print(f"\nTotal elapsed: {total:.1f}s")


if __name__ == "__main__":
    main()
