"""V10 Demographics Model.

Builds on V9.2 architecture. Targets Hispanic + Gender improvement.
Race is frozen (guard rails only, not optimized).

Phases:
  0C: Reproduce V9.2 baseline on both holdouts (V10 training set)
  1:  Enable Hispanic calibration (d_hisp grid search)
  2:  Gender expert blending
  3:  Confidence / reliability indicator
  5:  Final validation on sealed holdout

Usage:
    py scripts/analysis/demographics_comparison/run_v10.py --phase 0c
    py scripts/analysis/demographics_comparison/run_v10.py --phase 1a
    py scripts/analysis/demographics_comparison/run_v10.py --phase 2a
    ...
"""
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from classifiers import classify_naics_group
from config import get_census_region
from methodologies_v5 import RACE_CATS, smoothed_ipf

from run_v9_2 import (
    get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    get_gender,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
    print_diversity_breakdown, print_sector_breakdown, print_region_breakdown,
    blend_hispanic, train_tier_weights,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ================================================================
# V10 DATA SPLITS
# ================================================================
def build_v10_splits():
    """Load V10 training set plus both holdouts."""
    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"]
    perm_codes = {c["company_code"] for c in perm_companies}

    v10_data = load_json(os.path.join(SCRIPT_DIR, "selected_v10_sealed_holdout_1000.json"))
    v10_companies = v10_data["companies"]
    v10_codes = {c["company_code"] for c in v10_companies}

    train_list = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v10.json"))
    train_codes = {c["company_code"] for c in train_list}

    # Sanity checks
    assert len(train_codes & perm_codes) == 0, "PERM CONTAMINATION"
    assert len(train_codes & v10_codes) == 0, "V10 CONTAMINATION"
    assert len(perm_codes & v10_codes) == 0, "HOLDOUT OVERLAP"

    return {
        "train_companies": train_list,
        "train_codes": train_codes,
        "perm_companies": perm_companies,
        "perm_codes": perm_codes,
        "v10_companies": v10_companies,
        "v10_codes": v10_codes,
    }


def build_records(companies, rec_lookup, cl):
    """Build record dicts from company list + checkpoint lookup."""
    records = []
    for company in companies:
        code = company["company_code"]
        cp_rec = rec_lookup.get(code)
        if not cp_rec or not cp_rec.get("truth"):
            continue
        truth = cp_rec["truth"]
        if not truth.get("race") or not truth.get("hispanic"):
            continue
        naics = company.get("naics", "")
        naics4 = naics[:4]
        county_fips = company.get("county_fips", "")
        state_fips = company.get("state_fips", "")
        zipcode = company.get("zipcode", "")
        state = company.get("state", "")
        naics_group = (company.get("classifications", {}).get("naics_group")
                       or classify_naics_group(naics4))
        region = (company.get("classifications", {}).get("region")
                  or get_census_region(state))
        cbsa_code = cl.get_county_cbsa(county_fips) or ""
        lodes_race = cl.get_lodes_race(county_fips)
        county_minority_pct = (100.0 - lodes_race.get("White", 0.0)) if lodes_race else None
        diversity_tier = get_diversity_tier(county_minority_pct)
        rec = {
            "company_code": code, "name": company.get("name"),
            "naics4": naics4, "naics_group": naics_group, "region": region,
            "county_fips": county_fips, "state_fips": state_fips,
            "state": state, "zipcode": zipcode, "cbsa_code": cbsa_code,
            "truth": truth, "truth_hispanic": truth["hispanic"]["Hispanic"],
            "expert_preds": cp_rec["expert_preds"],
            "county_minority_pct": county_minority_pct,
            "diversity_tier": diversity_tier,
            "total_employees": truth.get("total_employees", 0),
        }
        rec["signals"] = get_raw_signals(cl, rec)
        rec["black_signals"] = collect_black_signals(rec, cl)
        records.append(rec)
    return records


# ================================================================
# V9.2 SCENARIO (frozen race architecture)
# ================================================================
BLACK_WEIGHTS = {
    "Other Manufacturing": (0.2, 0.0, 0.0, 0.15),
    "Retail Trade (44-45)": (0.6, 0.0, 0.2, 0.20),
}
BLEND_A = 0.25


def scenario_v92_race(rec):
    """D+A 75/25 blend + Black adjustment. FROZEN -- do not modify."""
    d_pred = rec["expert_preds"].get("D")
    d_race = d_pred.get("race") if d_pred else None
    a_pred = rec["expert_preds"].get("A")
    a_race = a_pred.get("race") if a_pred else None

    if a_race and d_race:
        race = {}
        for c in RACE_CATS:
            race[c] = d_race.get(c, 0.0) * (1 - BLEND_A) + a_race.get(c, 0.0) * BLEND_A
    else:
        race = d_race

    ng = rec["naics_group"]
    params = BLACK_WEIGHTS.get(ng)
    if params and race:
        orig = rec["expert_preds"].get("D", {}).get("race")
        if orig:
            rec["expert_preds"]["D"]["race"] = race
            wl, wo, wc, adj = params
            race = apply_black_adjustment(rec, wl, wo, wc, adj)
            rec["expert_preds"]["D"]["race"] = orig

    return race


def scenario_v92_full(rec):
    """Full V9.2: D+A race + Hispanic pred + F gender."""
    race = scenario_v92_race(rec)
    hispanic = rec["hispanic_pred"]
    gender = get_gender(rec)
    return {"race": race, "hispanic": hispanic, "gender": gender}


def make_v92_pipeline(train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5):
    """Train Hispanic weights + calibration, return final prediction function."""
    # Hispanic weights
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Train calibration
    cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    # Count buckets
    level_counts = defaultdict(int)
    for k in cal:
        level_counts[k[2]] += 1
    for level in ["dt_reg_ind", "dt_ind", "reg_ind", "ind", "global"]:
        print("  %-15s %4d buckets" % (level, level_counts.get(level, 0)))

    def final_fn(rec, _d_race=d_race, _d_hisp=d_hisp, _d_gender=d_gender):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, cal, _d_race, _d_hisp, _d_gender)

    return final_fn, cal, industry_weights, tier_best_weights


def print_comparison_table(label_a, m_a, label_b, m_b):
    """Print side-by-side comparison of two metric sets."""
    print("\n  | %-18s | %-15s | %-15s | %-8s |" % ("Criterion", label_a, label_b, "Gap"))
    print("  |%s|%s|%s|%s|" % ("-" * 20, "-" * 17, "-" * 17, "-" * 10))
    rows = [
        ("Race MAE", "race", "%.3f"),
        ("P>20pp", "p20", "%.1f%%"),
        ("P>30pp", "p30", "%.1f%%"),
        ("Abs Bias", "abs_bias", "%.3f"),
        ("Hispanic MAE", "hisp", "%.3f"),
        ("Gender MAE", "gender", "%.3f"),
        ("HC South P>20pp", "hs_p20", "%.1f%%"),
    ]
    for name, key, fmt in rows:
        va = m_a[key]
        vb = m_b[key]
        gap = vb - va
        sa = fmt % va
        sb = fmt % vb
        sg = "%+.3f" % gap if "%" not in fmt else "%+.1f%%" % gap
        print("  | %-18s | %-15s | %-15s | %-8s |" % (name, sa, sb, sg))


# ================================================================
# PHASE 0C: Baseline reproduction
# ================================================================
def phase_0c():
    t0 = time.time()
    print("PHASE 0C: Reproduce V9.2 baseline with V10 training set")
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nBuilding records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)

    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    print("\nTraining Hispanic weights on V10 training set...")
    final_fn, cal, _, _ = make_v92_pipeline(train_records, all_records)

    # Evaluate on permanent holdout
    print("\n" + "=" * 80)
    print("V9.2 BASELINE ON PERMANENT HOLDOUT (V10 training set)")
    print("=" * 80)
    m_perm = evaluate(perm_records, final_fn)
    print_acceptance("V9.2 (V10 train) -> perm holdout", m_perm)

    # Evaluate on V10 sealed holdout
    print("\n" + "=" * 80)
    print("V9.2 BASELINE ON V10 SEALED HOLDOUT")
    print("=" * 80)
    m_v10 = evaluate(v10_records, final_fn)
    print_acceptance("V9.2 (V10 train) -> V10 sealed", m_v10)

    # Side-by-side comparison
    print("\n" + "=" * 80)
    print("COMPARISON: Permanent vs V10 Sealed holdout")
    print("=" * 80)
    print_comparison_table("Perm holdout", m_perm, "V10 sealed", m_v10)

    # V9.2 original values for reference
    print("\n  V9.2 ORIGINAL (reference): Race=4.403 P20=15.4%% P30=5.9%% Hisp=6.778 Gender=11.160")
    print("  V9.2 on V10 train -> perm: Race=%.3f P20=%.1f%% P30=%.1f%% Hisp=%.3f Gender=%.3f" % (
        m_perm["race"], m_perm["p20"], m_perm["p30"], m_perm["hisp"], m_perm["gender"]))
    perm_gap = m_perm["race"] - 4.403
    print("  Perm Race MAE gap from original: %+.3f (limit: 0.20)" % perm_gap)

    if m_perm["race"] > 4.60:
        print("\n  *** WARNING: Race MAE > 4.60 on perm holdout! Training set reduction may have")
        print("  *** removed a critical calibration bucket. INVESTIGATE before proceeding.")
    else:
        print("\n  Baseline stable. Proceeding is safe.")

    # Breakdowns on perm holdout
    print("\n" + "=" * 80)
    print("BREAKDOWNS (permanent holdout)")
    print("=" * 80)
    print_diversity_breakdown("V9.2 baseline", perm_records, final_fn)
    print_sector_breakdown("V9.2 baseline", perm_records, final_fn)
    print_region_breakdown("V9.2 baseline", perm_records, final_fn)

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))

    return {
        "perm_metrics": {k: v for k, v in m_perm.items() if k != "max_errors"},
        "v10_metrics": {k: v for k, v in m_v10.items() if k != "max_errors"},
    }


# ================================================================
# PHASE 1A: Hispanic calibration grid search
# ================================================================
def phase_1a():
    t0 = time.time()
    print("PHASE 1A: Hispanic calibration grid search (d_hisp)")
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nBuilding records...")
    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    print("  train=%d perm=%d" % (len(train_records), len(perm_records)))

    # Train Hispanic weights + calibration (once)
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    print("\nTraining V9.2 calibration...")
    cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    # Grid search d_hisp
    d_hisp_grid = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    D_RACE = 0.85
    D_GENDER = 0.5

    print("\n" + "=" * 80)
    print("d_hisp GRID SEARCH (d_race=%.2f, d_gender=%.2f fixed)" % (D_RACE, D_GENDER))
    print("=" * 80)
    print("  | %-6s | %-8s | %-8s | %-7s | %-7s | %-10s | %-5s |" % (
        "d_hisp", "Hisp MAE", "Race MAE", "P>20pp", "P>30pp", "Gender MAE", "Notes"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 8, "-" * 10, "-" * 10, "-" * 9, "-" * 9, "-" * 12, "-" * 7))

    results = []
    best_hisp_mae = 999
    best_d_hisp = 0.05

    for d_hisp in d_hisp_grid:
        def final_fn(rec, _dh=d_hisp):
            pred = scenario_v92_full(rec)
            if not pred:
                return None
            return apply_calibration_v92(pred, rec, cal, D_RACE, _dh, D_GENDER)

        m = evaluate(perm_records, final_fn)
        if not m:
            continue

        notes = ""
        if d_hisp == 0.05:
            notes = "V9.2 baseline"
        elif m["race"] > 4.55:
            notes = "RACE GUARD"
        elif m["p30"] > 6.5:
            notes = "P30 GUARD"
        elif m["hisp"] < best_hisp_mae and m["race"] <= 4.55 and m["p30"] <= 6.5:
            notes = "BEST"
            best_hisp_mae = m["hisp"]
            best_d_hisp = d_hisp

        results.append({"d_hisp": d_hisp, "metrics": m, "notes": notes})
        print("  | %-6.2f | %-8.3f | %-8.3f | %-6.1f%% | %-6.1f%% | %-10.3f | %-5s |" % (
            d_hisp, m["hisp"], m["race"], m["p20"], m["p30"], m["gender"], notes))

    # Update "BEST" annotation on best result
    for r in results:
        if r["notes"] == "BEST" and r["d_hisp"] != best_d_hisp:
            r["notes"] = ""
    for r in results:
        if r["d_hisp"] == best_d_hisp and r["notes"] != "V9.2 baseline":
            r["notes"] = "BEST"

    print("\n  Best d_hisp: %.2f (Hispanic MAE: %.3f)" % (best_d_hisp, best_hisp_mae))
    baseline_hisp = [r for r in results if r["d_hisp"] == 0.05][0]["metrics"]["hisp"]
    improvement = baseline_hisp - best_hisp_mae
    print("  Improvement over baseline: %.3f pp" % improvement)

    if best_d_hisp == 0.05:
        print("\n  No d_hisp > 0.05 improved Hispanic MAE without violating guard rails.")
        print("  The problem is in the calibration corrections themselves, not dampening.")
        print("  Proceeding to Phase 1B to try Hispanic-specific hierarchy.")

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))
    return {"best_d_hisp": best_d_hisp, "best_hisp_mae": best_hisp_mae, "results": results}


# ================================================================
# PHASE 1B: Hispanic-specific calibration hierarchy
# ================================================================
def get_hispanic_county_tier(county_hisp_pct):
    """Hispanic-specific tier based on county Hispanic %."""
    if county_hisp_pct is None:
        return "med_hisp"
    if county_hisp_pct < 10:
        return "low_hisp"
    elif county_hisp_pct < 25:
        return "med_hisp"
    elif county_hisp_pct < 50:
        return "high_hisp"
    else:
        return "very_high_hisp"


def train_hispanic_calibration(train_records, scenario_fn, max_offset=15.0):
    """Hispanic-specific calibration hierarchy.

    Separate from race/gender calibration. Uses Hispanic county tier instead
    of diversity tier.

    Hierarchy:
      1. hispanic_tier x region x industry (min 40)
      2. hispanic_tier x industry (min 30)
      3. region x industry (min 20)
      4. industry (min 20)
      5. global (min 20)
    """
    MIN_BUCKET = {
        "ht_reg_ind": 40,
        "ht_ind": 30,
        "reg_ind": 20,
        "ind": 20,
        "global": 20,
    }

    buckets = defaultdict(list)
    for rec in train_records:
        pred = scenario_fn(rec)
        if not pred:
            continue
        hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
        if not hp or not ha or "Hispanic" not in hp or "Hispanic" not in ha:
            continue

        county_hisp = rec["signals"].get("county_hisp_pct")
        ht = get_hispanic_county_tier(county_hisp)
        region = rec["region"]
        ng = rec["naics_group"]

        err = hp["Hispanic"] - ha["Hispanic"]
        keys = [
            ("ht_reg_ind", ht, region, ng),
            ("ht_ind", ht, ng),
            ("reg_ind", region, ng),
            ("ind", ng),
            ("global",),
        ]
        for key in keys:
            buckets[("hisp", "Hispanic") + key].append(err)

    offsets = {}
    for k, errs in buckets.items():
        level_name = k[2]
        min_n = MIN_BUCKET.get(level_name, 20)
        if len(errs) >= min_n:
            raw_offset = sum(errs) / len(errs)
            capped = max(-max_offset, min(max_offset, raw_offset))
            offsets[k] = (capped, len(errs))
    return offsets


def apply_hispanic_calibration(pred, rec, hisp_offsets, d_hisp):
    """Apply Hispanic-specific calibration using Hispanic county tier hierarchy."""
    if not pred.get("hispanic"):
        return pred

    county_hisp = rec["signals"].get("county_hisp_pct")
    ht = get_hispanic_county_tier(county_hisp)
    region = rec["region"]
    ng = rec["naics_group"]

    hierarchy = [
        ("ht_reg_ind", ht, region, ng),
        ("ht_ind", ht, ng),
        ("reg_ind", region, ng),
        ("ind", ng),
        ("global",),
    ]

    off = None
    for key in hierarchy:
        full_key = ("hisp", "Hispanic") + key
        if full_key in hisp_offsets:
            off = hisp_offsets[full_key][0]
            break

    result = dict(pred)  # shallow copy
    if off is not None:
        hv = pred["hispanic"].get("Hispanic", 0.0)
        hv -= off * d_hisp
        hv = max(0.0, min(100.0, hv))
        result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}

    return result


def phase_1b(best_d_hisp_from_1a=None):
    t0 = time.time()
    print("PHASE 1B: Hispanic-specific calibration hierarchy")
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nBuilding records...")
    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    print("  train=%d perm=%d" % (len(train_records), len(perm_records)))

    # Train Hispanic weights
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Train STANDARD calibration (for race + gender)
    print("\nTraining standard V9.2 calibration (race + gender)...")
    std_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    # Train HISPANIC-SPECIFIC calibration
    print("\nTraining Hispanic-specific calibration hierarchy...")
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)
    level_counts = defaultdict(int)
    for k in hisp_cal:
        level_counts[k[2]] += 1
    for level in ["ht_reg_ind", "ht_ind", "reg_ind", "ind", "global"]:
        print("  %-15s %4d buckets" % (level, level_counts.get(level, 0)))

    # Grid search d_hisp with BOTH hierarchy types
    d_hisp_grid = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    D_RACE = 0.85
    D_GENDER = 0.5

    print("\n" + "=" * 80)
    print("d_hisp GRID: Standard hierarchy vs Hispanic-specific hierarchy")
    print("=" * 80)
    print("  | %-6s | %-10s | %-10s | %-8s | %-8s | %-7s | %-7s |" % (
        "d_hisp", "Hisp(std)", "Hisp(hsp)", "Race(s)", "Race(h)", "P30(s)", "P30(h)"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 8, "-" * 12, "-" * 12, "-" * 10, "-" * 10, "-" * 9, "-" * 9))

    best_hisp_mae = 999
    best_d_hisp = 0.05
    best_hierarchy = "standard"

    for d_hisp in d_hisp_grid:
        # Standard hierarchy
        def fn_std(rec, _dh=d_hisp):
            pred = scenario_v92_full(rec)
            if not pred:
                return None
            return apply_calibration_v92(pred, rec, std_cal, D_RACE, _dh, D_GENDER)

        # Hispanic-specific hierarchy (race+gender from std, hispanic from hisp_cal)
        def fn_hsp(rec, _dh=d_hisp):
            pred = scenario_v92_full(rec)
            if not pred:
                return None
            # Apply standard cal for race + gender only (d_hisp=0 to skip hispanic)
            result = apply_calibration_v92(pred, rec, std_cal, D_RACE, 0.0, D_GENDER)
            # Then apply Hispanic-specific calibration
            result = apply_hispanic_calibration(result, rec, hisp_cal, _dh)
            return result

        m_std = evaluate(perm_records, fn_std)
        m_hsp = evaluate(perm_records, fn_hsp)

        # Check for best
        for label, m, hier in [("std", m_std, "standard"), ("hsp", m_hsp, "hispanic")]:
            if m and m["race"] <= 4.55 and m["p30"] <= 6.5 and m["hisp"] < best_hisp_mae:
                best_hisp_mae = m["hisp"]
                best_d_hisp = d_hisp
                best_hierarchy = hier

        if m_std and m_hsp:
            print("  | %-6.2f | %-10.3f | %-10.3f | %-8.3f | %-8.3f | %-6.1f%% | %-6.1f%% |" % (
                d_hisp, m_std["hisp"], m_hsp["hisp"],
                m_std["race"], m_hsp["race"],
                m_std["p30"], m_hsp["p30"]))

    print("\n  Best: d_hisp=%.2f, hierarchy=%s, Hispanic MAE=%.3f" % (
        best_d_hisp, best_hierarchy, best_hisp_mae))

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))
    return {"best_d_hisp": best_d_hisp, "best_hierarchy": best_hierarchy,
            "best_hisp_mae": best_hisp_mae}


# ================================================================
# PHASE 1C: Hispanic breakdown analysis
# ================================================================
def phase_1c(best_d_hisp=0.05, use_hispanic_hierarchy=False):
    t0 = time.time()
    print("PHASE 1C: Hispanic breakdown analysis")
    print("=" * 80)
    print("  Config: d_hisp=%.2f, hierarchy=%s" % (
        best_d_hisp, "hispanic-specific" if use_hispanic_hierarchy else "standard"))

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]

    # Train
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    std_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    # Baseline (d_hisp=0.05)
    def fn_baseline(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, std_cal, 0.85, 0.05, 0.5)

    # V10 config
    if use_hispanic_hierarchy:
        hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

        def fn_v10(rec):
            pred = scenario_v92_full(rec)
            if not pred:
                return None
            result = apply_calibration_v92(pred, rec, std_cal, 0.85, 0.0, 0.5)
            result = apply_hispanic_calibration(result, rec, hisp_cal, best_d_hisp)
            return result
    else:
        def fn_v10(rec):
            pred = scenario_v92_full(rec)
            if not pred:
                return None
            return apply_calibration_v92(pred, rec, std_cal, 0.85, best_d_hisp, 0.5)

    # By Hispanic county tier
    print("\n  | %-22s | %3s | %-12s | %-12s | %-8s |" % (
        "Hispanic County Tier", "N", "Hisp MAE V92", "Hisp MAE V10", "Change"))
    print("  |%s|%s|%s|%s|%s|" % ("-" * 24, "-" * 5, "-" * 14, "-" * 14, "-" * 10))

    for tier_name, low, high in [("Low (<10%)", 0, 10), ("Med (10-25%)", 10, 25),
                                  ("High (25-50%)", 25, 50), ("Very High (50%+)", 50, 101)]:
        subset = [r for r in perm_records
                  if r["signals"].get("county_hisp_pct") is not None
                  and low <= r["signals"]["county_hisp_pct"] < high]
        if not subset:
            continue

        # Compute Hispanic MAE for each
        def hisp_mae(recs, fn):
            errs = []
            for rec in recs:
                pred = fn(rec)
                if pred and pred.get("hispanic"):
                    m = mae_dict(pred["hispanic"], rec["truth"]["hispanic"], HISP_CATS)
                    if m is not None:
                        errs.append(m)
            return sum(errs) / len(errs) if errs else None

        base = hisp_mae(subset, fn_baseline)
        v10 = hisp_mae(subset, fn_v10)
        change = v10 - base if base is not None and v10 is not None else None
        print("  | %-22s | %3d | %-12s | %-12s | %-8s |" % (
            tier_name, len(subset),
            "%.3f" % base if base else "--",
            "%.3f" % v10 if v10 else "--",
            "%+.3f" % change if change is not None else "--"))

    # By sector
    print("\n  | %-30s | %3s | %-12s | %-12s | %-8s |" % (
        "Sector", "N", "Hisp MAE V92", "Hisp MAE V10", "Change"))
    print("  |%s|%s|%s|%s|%s|" % ("-" * 32, "-" * 5, "-" * 14, "-" * 14, "-" * 10))
    sectors = ["Construction (23)", "Accommodation/Food Svc (72)",
               "Healthcare/Social (62)", "Food/Bev Manufacturing (311,312)",
               "Transportation/Warehousing (48-49)", "Admin/Staffing (56)"]
    for sector in sectors:
        subset = [r for r in perm_records if r["naics_group"] == sector]
        if len(subset) < 5:
            continue

        def hisp_mae(recs, fn):
            errs = []
            for rec in recs:
                pred = fn(rec)
                if pred and pred.get("hispanic"):
                    m = mae_dict(pred["hispanic"], rec["truth"]["hispanic"], HISP_CATS)
                    if m is not None:
                        errs.append(m)
            return sum(errs) / len(errs) if errs else None

        base = hisp_mae(subset, fn_baseline)
        v10 = hisp_mae(subset, fn_v10)
        change = v10 - base if base is not None and v10 is not None else None
        print("  | %-30s | %3d | %-12s | %-12s | %-8s |" % (
            sector[:30], len(subset),
            "%.3f" % base if base else "--",
            "%.3f" % v10 if v10 else "--",
            "%+.3f" % change if change is not None else "--"))

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))


# ================================================================
# PHASE 2A: Gender expert comparison
# ================================================================
def phase_2a():
    t0 = time.time()
    print("PHASE 2A: Gender expert comparison")
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]

    experts = ["F", "D", "A", "B", "V6-Full", "G"]
    print("\n  | %-10s | %-10s | %-15s | %-12s |" % (
        "Expert", "Gender MAE", "Gender Signed Bias", "Gender Wins"))
    print("  |%s|%s|%s|%s|" % ("-" * 12, "-" * 12, "-" * 17, "-" * 14))

    expert_errors = {}  # {expert: {company_code: gender_error}}

    for expert in experts:
        errs = []
        biases = []
        per_company = {}
        for rec in perm_records:
            ep = rec["expert_preds"].get(expert)
            if not ep or not ep.get("gender"):
                continue
            gender = ep["gender"]
            truth_gender = rec["truth"].get("gender")
            if not truth_gender:
                continue
            m = mae_dict(gender, truth_gender, GENDER_CATS)
            if m is not None:
                errs.append(m)
                per_company[rec["company_code"]] = m
                if "Female" in gender and "Female" in truth_gender:
                    biases.append(gender["Female"] - truth_gender["Female"])
        expert_errors[expert] = per_company
        mae = sum(errs) / len(errs) if errs else None
        bias = sum(biases) / len(biases) if biases else None
        print("  | %-10s | %-10s | %-15s | %-12d |" % (
            expert + (" (cur)" if expert == "F" else ""),
            "%.3f" % mae if mae else "--",
            "%+.3f" % bias if bias else "--",
            len(per_company)))

    # Gender Wins (best expert per company)
    print("\n  Gender Wins (lowest error per company):")
    win_counts = defaultdict(int)
    for code in set().union(*[set(v.keys()) for v in expert_errors.values()]):
        best_expert = None
        best_err = 999
        for expert in experts:
            err = expert_errors[expert].get(code)
            if err is not None and err < best_err:
                best_err = err
                best_expert = expert
        if best_expert:
            win_counts[best_expert] += 1

    for expert in experts:
        print("    %-10s %4d wins" % (expert, win_counts.get(expert, 0)))

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))
    return {"expert_errors": {e: len(v) for e, v in expert_errors.items()},
            "win_counts": dict(win_counts)}


# ================================================================
# PHASE 2B: Gender blending grid search
# ================================================================
def phase_2b(blend_candidate="D"):
    t0 = time.time()
    print("PHASE 2B: Gender blending grid search (F + %s)" % blend_candidate)
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]

    # Train Hispanic weights
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Grid search: F_weight x d_gender, with recalibrated for each
    f_weights = [1.0, 0.90, 0.85, 0.80, 0.75, 0.70, 0.60]
    d_gender_grid = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    print("\n  | %-8s | %-8s | %-8s | %-10s | %-8s | %-7s | %-5s |" % (
        "F_weight", "X_weight", "d_gender", "Gender MAE", "Race MAE", "P>20pp", "Notes"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 10, "-" * 10, "-" * 10, "-" * 12, "-" * 10, "-" * 9, "-" * 7))

    best_gender_mae = 999
    best_config = {"f_weight": 1.0, "d_gender": 0.5}

    for f_w in f_weights:
        x_w = round(1.0 - f_w, 2)

        def get_blended_gender(rec, _fw=f_w, _xw=x_w):
            ep = rec["expert_preds"]
            f_gender = ep.get("F", {}).get("gender")
            x_gender = ep.get(blend_candidate, {}).get("gender")
            if not f_gender:
                return get_gender(rec)
            if _xw == 0 or not x_gender:
                return f_gender
            return {
                "Male": f_gender.get("Male", 50) * _fw + x_gender.get("Male", 50) * _xw,
                "Female": f_gender.get("Female", 50) * _fw + x_gender.get("Female", 50) * _xw,
            }

        def scenario_with_blend(rec, _fw=f_w, _xw=x_w):
            race = scenario_v92_race(rec)
            hispanic = rec["hispanic_pred"]
            gender = get_blended_gender(rec, _fw, _xw)
            return {"race": race, "hispanic": hispanic, "gender": gender}

        # Train calibration with this gender blend
        cal = train_calibration_v92(train_records, scenario_with_blend, max_offset=20.0)

        for d_g in d_gender_grid:
            def final_fn(rec, _dg=d_g, _cal=cal):
                pred = scenario_with_blend(rec)
                if not pred:
                    return None
                return apply_calibration_v92(pred, rec, _cal, 0.85, 0.05, _dg)

            m = evaluate(perm_records, final_fn)
            if not m:
                continue

            notes = ""
            if f_w == 1.0 and d_g == 0.5:
                notes = "V9.2"
            elif m["race"] > 4.55:
                notes = "GUARD"
            elif m["p30"] > 6.5:
                notes = "GUARD"
            elif m["gender"] < best_gender_mae and m["race"] <= 4.55 and m["p30"] <= 6.5:
                best_gender_mae = m["gender"]
                best_config = {"f_weight": f_w, "d_gender": d_g}
                notes = "BEST"

            print("  | %-8.2f | %-8.2f | %-8.2f | %-10.3f | %-8.3f | %-6.1f%% | %-5s |" % (
                f_w, x_w, d_g, m["gender"], m["race"], m["p20"], notes))

    print("\n  Best config: F=%.2f %s=%.2f d_gender=%.2f -> Gender MAE=%.3f" % (
        best_config["f_weight"], blend_candidate, 1 - best_config["f_weight"],
        best_config["d_gender"], best_gender_mae))

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))
    return best_config


# ================================================================
# PHASE 3: Confidence / Reliability Indicator
# ================================================================
HIGH_ERROR_SECTORS = {
    "Healthcare/Social (62)",
    "Admin/Staffing (56)",
    "Transportation/Warehousing (48-49)",
    "Accommodation/Food Svc (72)",
}


def estimate_confidence(naics_group, diversity_tier, region):
    """Predict confidence in the demographic estimate.

    Returns: 'GREEN', 'YELLOW', or 'RED'
    """
    risk_points = 0

    # County diversity tier (strongest predictor)
    if diversity_tier == "High":
        risk_points += 4
    elif diversity_tier == "Med-High":
        risk_points += 2
    elif diversity_tier == "Med-Low":
        risk_points += 1
    # Low = 0

    # Sector risk
    if naics_group in HIGH_ERROR_SECTORS:
        risk_points += 2

    # Regional risk
    if region in ("West", "South"):
        risk_points += 1

    if risk_points >= 5:
        return "RED"
    elif risk_points >= 3:
        return "YELLOW"
    else:
        return "GREEN"


def phase_3(point_configs=None):
    t0 = time.time()
    print("PHASE 3: Confidence / Reliability Indicator")
    print("=" * 80)

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    all_companies = splits["train_companies"] + splits["perm_companies"]
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]

    # Train V10 pipeline (Hispanic-specific hierarchy + d_gender=0.95)
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Standard cal for race + gender
    std_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)
    # Hispanic-specific cal
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    D_RACE, D_HISP, D_GENDER = 0.85, 0.50, 0.95

    def final_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, std_cal, D_RACE, 0.0, D_GENDER)
        result = apply_hispanic_calibration(result, rec, hisp_cal, D_HISP)
        return result

    # Assign confidence tiers
    for rec in perm_records:
        rec["confidence"] = estimate_confidence(
            rec["naics_group"], rec["diversity_tier"], rec["region"])

    # Evaluate by tier
    print("\n  Checkpoint 3B: Confidence tier validation (permanent holdout)")
    print("  | %-8s | %3s | %7s | %-8s | %-8s | %-8s | %-8s | %-10s |" % (
        "Tier", "N", "% hold", "Race MAE", "P>20pp", "P>30pp", "Hisp MAE", "Gender MAE"))
    print("  |%s|%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 10, "-" * 5, "-" * 9, "-" * 10, "-" * 10, "-" * 10, "-" * 10, "-" * 12))

    tier_data = {}
    for tier in ["GREEN", "YELLOW", "RED"]:
        subset = [r for r in perm_records if r["confidence"] == tier]
        if not subset:
            continue
        m = evaluate(subset, final_fn)
        pct = len(subset) / len(perm_records) * 100
        tier_data[tier] = {"n": len(subset), "pct": pct, "metrics": m}
        print("  | %-8s | %3d | %6.1f%% | %-8.3f | %-7.1f%% | %-7.1f%% | %-8.3f | %-10.3f |" % (
            tier, len(subset), pct,
            m["race"], m["p20"], m["p30"], m["hisp"], m["gender"]))

    # Compute separation ratio
    if "GREEN" in tier_data and "RED" in tier_data:
        green_p20 = tier_data["GREEN"]["metrics"]["p20"]
        red_p20 = tier_data["RED"]["metrics"]["p20"]
        ratio = red_p20 / green_p20 if green_p20 > 0 else float("inf")
        print("\n  P>20pp ratio (RED / GREEN): %.1f:1" % ratio)
        if ratio >= 5:
            print("  GOOD: Confidence tiers are genuinely useful (>= 5:1 target)")
        else:
            print("  Ratio below 5:1 target. Consider adjusting thresholds.")
    else:
        ratio = None

    # Checkpoint 3C: Try alternative thresholds
    print("\n  Checkpoint 3C: Threshold tuning")
    print("  Testing alternative point configs...")

    configs = [
        # (name, dt_high, dt_medhigh, dt_medlow, sector_pts, region_pts, red_thresh, yellow_thresh)
        ("Default", 4, 2, 1, 2, 1, 5, 3),
        ("Tight", 5, 3, 1, 2, 1, 6, 3),
        ("Sector+", 4, 2, 1, 3, 1, 5, 3),
        ("Region0", 4, 2, 1, 2, 0, 5, 3),
        ("Red=4", 4, 2, 1, 2, 1, 4, 2),
        ("DT+", 5, 3, 1, 2, 1, 5, 3),
    ]

    print("  | %-10s | %3s | %3s | %3s | %6s | %6s | %6s | %6s | %5s |" % (
        "Config", "G_N", "Y_N", "R_N", "G_P20", "Y_P20", "R_P20", "Ratio", "Good?"))
    print("  |%s|%s|%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 12, "-" * 5, "-" * 5, "-" * 5, "-" * 8, "-" * 8, "-" * 8, "-" * 8, "-" * 7))

    best_ratio = 0
    best_config_name = "Default"

    for name, dt_h, dt_mh, dt_ml, sec_pts, reg_pts, red_t, yel_t in configs:
        # Reassign tiers
        for rec in perm_records:
            pts = 0
            dt = rec["diversity_tier"]
            if dt == "High":
                pts += dt_h
            elif dt == "Med-High":
                pts += dt_mh
            elif dt == "Med-Low":
                pts += dt_ml
            if rec["naics_group"] in HIGH_ERROR_SECTORS:
                pts += sec_pts
            if rec["region"] in ("West", "South"):
                pts += reg_pts
            if pts >= red_t:
                rec["confidence"] = "RED"
            elif pts >= yel_t:
                rec["confidence"] = "YELLOW"
            else:
                rec["confidence"] = "GREEN"

        tier_ns = {}
        tier_p20s = {}
        for tier in ["GREEN", "YELLOW", "RED"]:
            subset = [r for r in perm_records if r["confidence"] == tier]
            if subset:
                m = evaluate(subset, final_fn)
                tier_ns[tier] = len(subset)
                tier_p20s[tier] = m["p20"] if m else 0
            else:
                tier_ns[tier] = 0
                tier_p20s[tier] = 0

        g_p20 = tier_p20s.get("GREEN", 0)
        r_p20 = tier_p20s.get("RED", 0)
        r = r_p20 / g_p20 if g_p20 > 0 else 0
        good = "YES" if r >= 5 and 5 <= tier_ns.get("RED", 0) / len(perm_records) * 100 <= 20 else "no"

        if r > best_ratio and good == "YES":
            best_ratio = r
            best_config_name = name

        print("  | %-10s | %3d | %3d | %3d | %5.1f%% | %5.1f%% | %5.1f%% | %5.1f | %-5s |" % (
            name, tier_ns.get("GREEN", 0), tier_ns.get("YELLOW", 0), tier_ns.get("RED", 0),
            g_p20, tier_p20s.get("YELLOW", 0), r_p20, r, good))

    print("\n  Best config: %s (ratio: %.1f:1)" % (best_config_name, best_ratio))

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))


# ================================================================
# PHASE 5: Final Validation
# ================================================================
def phase_5():
    t0 = time.time()
    print("PHASE 5: FINAL V10 VALIDATION")
    print("=" * 80)
    print("V10 Config:")
    print("  Race:     D+A blend (75/25) + Black adj (frozen from V9.2)")
    print("  Hispanic: Hispanic-specific calibration hierarchy, d_hisp=0.50")
    print("  Gender:   Expert F only, d_gender=0.95")
    print("  Race dampening: d_race=0.85 (frozen)")
    print("  Confidence: GREEN/YELLOW/RED tiers")

    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nBuilding records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Train Hispanic weights
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Standard calibration (race + gender)
    print("\nTraining standard calibration (race + gender)...")
    std_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    # Hispanic-specific calibration
    print("\nTraining Hispanic-specific calibration...")
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    D_RACE, D_HISP, D_GENDER = 0.85, 0.50, 0.95

    def v10_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        # Race + gender from standard cal (d_hisp=0 to skip hispanic there)
        result = apply_calibration_v92(pred, rec, std_cal, D_RACE, 0.0, D_GENDER)
        # Hispanic from Hispanic-specific cal
        result = apply_hispanic_calibration(result, rec, hisp_cal, D_HISP)
        return result

    # V9.2 baseline for comparison
    def v92_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, std_cal, 0.85, 0.05, 0.50)

    # ================================================================
    # 5A: Configuration summary
    # ================================================================
    print("\n" + "=" * 80)
    print("5A: V10 Configuration Summary")
    print("=" * 80)
    print("  | %-25s | %-30s | %-30s | %-8s |" % ("Component", "V9.2 Config", "V10 Config", "Changed?"))
    print("  |%s|%s|%s|%s|" % ("-" * 27, "-" * 32, "-" * 32, "-" * 10))
    config_rows = [
        ("Race blend", "75% D + 25% A", "75% D + 25% A", "No"),
        ("Race dampening", "d_race = 0.85", "d_race = 0.85", "No"),
        ("Black adjustment", "Retail + Other Mfg", "Retail + Other Mfg", "No"),
        ("Hispanic weights", "industry+tier", "industry+tier", "No"),
        ("Hispanic dampening", "d_hisp = 0.05", "d_hisp = 0.50", "YES"),
        ("Hispanic calibration", "standard hierarchy", "Hispanic-specific hier.", "YES"),
        ("Hispanic cal cap", "20pp", "15pp", "YES"),
        ("Gender expert", "Expert F only", "Expert F only", "No"),
        ("Gender dampening", "d_gender = 0.50", "d_gender = 0.95", "YES"),
        ("Confidence tiers", "(none)", "GREEN/YELLOW/RED", "NEW"),
    ]
    for comp, v92, v10, changed in config_rows:
        print("  | %-25s | %-30s | %-30s | %-8s |" % (comp, v92, v10, changed))

    # ================================================================
    # 5B: Permanent holdout validation
    # ================================================================
    print("\n" + "=" * 80)
    print("5B: PERMANENT HOLDOUT VALIDATION (backward comparison)")
    print("=" * 80)

    m_v92_perm = evaluate(perm_records, v92_fn)
    m_v10_perm = evaluate(perm_records, v10_fn)

    guard_rails = [
        (1, "Race MAE", "race", "%.3f", 4.55, False),
        (2, "P>20pp", "p20", "%.1f%%", 16.5, False),
        (3, "P>30pp", "p30", "%.1f%%", 6.5, False),
        (4, "Abs Bias", "abs_bias", "%.3f", 1.10, False),
        (5, "Hispanic MAE", "hisp", "%.3f", 6.20, True),
        (6, "Gender MAE", "gender", "%.3f", 10.20, True),
        (7, "HC South P>20pp", "hs_p20", "%.1f%%", 15.5, False),
    ]

    print("  | # | %-18s | %-8s | %-8s | %-8s | %-10s | %-6s |" % (
        "Criterion", "V9.2", "V10", "Change", "Guard rail", "Status"))
    print("  |---|%s|%s|%s|%s|%s|%s|" % (
        "-" * 20, "-" * 10, "-" * 10, "-" * 10, "-" * 12, "-" * 8))

    all_pass = True
    for num, name, key, fmt, limit, is_target in guard_rails:
        v92_val = m_v92_perm[key]
        v10_val = m_v10_perm[key]
        change = v10_val - v92_val
        ok = v10_val < limit
        if not ok:
            all_pass = False
        label = "TARGET" if is_target else "< " + (fmt % limit).replace("%%", "%")
        status = "PASS" if ok else "FAIL"
        v92_str = fmt % v92_val
        v10_str = fmt % v10_val
        if "%" in fmt:
            chg_str = "%+.1f%%" % change
        else:
            chg_str = "%+.3f" % change
        print("  | %d | %-18s | %-8s | %-8s | %-8s | %-10s | %-6s |" % (
            num, name, v92_str, v10_str, chg_str, label, status))

    if all_pass:
        print("\n  ALL GUARD RAILS PASSED on permanent holdout.")
    else:
        print("\n  *** GUARD RAIL VIOLATION on permanent holdout! ***")

    # ================================================================
    # 5C: V10 Sealed holdout (HONEST evaluation)
    # ================================================================
    print("\n" + "=" * 80)
    print("5C: V10 SEALED HOLDOUT (honest evaluation, never used in optimization)")
    print("=" * 80)

    m_v92_v10 = evaluate(v10_records, v92_fn)
    m_v10_v10 = evaluate(v10_records, v10_fn)

    print("  | # | %-18s | %-12s | %-12s | %-8s |" % (
        "Criterion", "V9.2 (sealed)", "V10 (sealed)", "Change"))
    print("  |---|%s|%s|%s|%s|" % ("-" * 20, "-" * 14, "-" * 14, "-" * 10))

    for num, name, key, fmt, limit, is_target in guard_rails:
        v92_val = m_v92_v10[key]
        v10_val = m_v10_v10[key]
        change = v10_val - v92_val
        v92_str = fmt % v92_val
        v10_str = fmt % v10_val
        if "%" in fmt:
            chg_str = "%+.1f%%" % change
        else:
            chg_str = "%+.3f" % change
        print("  | %d | %-18s | %-12s | %-12s | %-8s |" % (
            num, name, v92_str, v10_str, chg_str))

    # Confidence tiers on sealed holdout
    print("\n  Confidence tiers on V10 sealed holdout:")
    for rec in v10_records:
        rec["confidence"] = estimate_confidence(
            rec["naics_group"], rec["diversity_tier"], rec["region"])

    print("  | %-8s | %3s | %-8s | %-8s | %-8s | %-8s | %-10s |" % (
        "Tier", "N", "Race MAE", "P>20pp", "P>30pp", "Hisp MAE", "Gender MAE"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 10, "-" * 5, "-" * 10, "-" * 10, "-" * 10, "-" * 10, "-" * 12))

    for tier in ["GREEN", "YELLOW", "RED"]:
        subset = [r for r in v10_records if r["confidence"] == tier]
        if not subset:
            continue
        m = evaluate(subset, v10_fn)
        print("  | %-8s | %3d | %-8.3f | %-7.1f%% | %-7.1f%% | %-8.3f | %-10.3f |" % (
            tier, len(subset), m["race"], m["p20"], m["p30"], m["hisp"], m["gender"]))

    # ================================================================
    # 5D: Cross-version comparison
    # ================================================================
    print("\n" + "=" * 80)
    print("5D: CROSS-VERSION COMPARISON")
    print("=" * 80)

    print("  | %-18s | %-10s | %-10s | %-10s | %-12s | %-12s |" % (
        "Metric", "V6 (325)", "V9.1", "V9.2", "V10 (perm)", "V10 (sealed)"))
    print("  |%s|%s|%s|%s|%s|%s|" % (
        "-" * 20, "-" * 12, "-" * 12, "-" * 12, "-" * 14, "-" * 14))

    cross_data = [
        ("Race MAE", 4.203, 4.483, 4.403, m_v10_perm["race"], m_v10_v10["race"]),
        ("P>20pp", 13.5, 17.1, 15.4, m_v10_perm["p20"], m_v10_v10["p20"]),
        ("P>30pp", 4.0, 7.7, 5.9, m_v10_perm["p30"], m_v10_v10["p30"]),
        ("Hispanic MAE", 7.752, 6.697, 6.778, m_v10_perm["hisp"], m_v10_v10["hisp"]),
        ("Gender MAE", 11.979, 10.798, 11.160, m_v10_perm["gender"], m_v10_v10["gender"]),
    ]
    for name, v6, v91, v92, v10p, v10s in cross_data:
        if name in ("P>20pp", "P>30pp"):
            print("  | %-18s | %9.1f%% | %9.1f%% | %9.1f%% | %11.1f%% | %11.1f%% |" % (
                name, v6, v91, v92, v10p, v10s))
        else:
            print("  | %-18s | %10.3f | %10.3f | %10.3f | %12.3f | %12.3f |" % (
                name, v6, v91, v92, v10p, v10s))

    # Breakdowns
    print("\n" + "=" * 80)
    print("DETAILED BREAKDOWNS (permanent holdout)")
    print("=" * 80)
    print_diversity_breakdown("V10", perm_records, v10_fn)
    print_sector_breakdown("V10", perm_records, v10_fn)
    print_region_breakdown("V10", perm_records, v10_fn)

    # Save results
    results = {
        "model": "V10",
        "config": {
            "race_blend": "75% D + 25% A",
            "black_adjustment": {"Other Manufacturing": [0.2, 0.0, 0.0, 0.15],
                                 "Retail Trade (44-45)": [0.6, 0.0, 0.2, 0.20]},
            "dampening": {"race": 0.85, "hisp": 0.50, "gender": 0.95},
            "hispanic_hierarchy": "hispanic-specific (cap 15pp)",
            "gender_expert": "F only",
            "confidence_tiers": "GREEN/YELLOW/RED",
        },
        "perm_metrics": {k: v for k, v in m_v10_perm.items() if k != "max_errors"},
        "sealed_metrics": {k: v for k, v in m_v10_v10.items() if k != "max_errors"},
        "v92_perm_baseline": {k: v for k, v in m_v92_perm.items() if k != "max_errors"},
        "v92_sealed_baseline": {k: v for k, v in m_v92_v10.items() if k != "max_errors"},
    }
    save_json(os.path.join(SCRIPT_DIR, "v10_results.json"), results)
    print("\nResults saved: v10_results.json")

    cur.close()
    conn.close()
    print("\nRuntime: %.0fs" % (time.time() - t0))


# ================================================================
# MAIN
# ================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="V10 Demographics Model")
    parser.add_argument("--phase", required=True,
                        help="Phase to run: 0c, 1a, 1b, 1c, 2a, 2b, 3, 5")
    parser.add_argument("--d-hisp", type=float, default=0.05,
                        help="Best d_hisp from Phase 1A (for 1b/1c)")
    parser.add_argument("--use-hisp-hierarchy", action="store_true",
                        help="Use Hispanic-specific hierarchy (for 1c)")
    parser.add_argument("--blend-candidate", default="D",
                        help="Expert to blend with F for gender (for 2b)")
    args = parser.parse_args()

    if args.phase == "0c":
        phase_0c()
    elif args.phase == "1a":
        phase_1a()
    elif args.phase == "1b":
        phase_1b()
    elif args.phase == "1c":
        phase_1c(best_d_hisp=args.d_hisp,
                 use_hispanic_hierarchy=args.use_hisp_hierarchy)
    elif args.phase == "2a":
        phase_2a()
    elif args.phase == "2b":
        phase_2b(blend_candidate=args.blend_candidate)
    elif args.phase == "3":
        phase_3()
    elif args.phase == "5":
        phase_5()
    else:
        print("Unknown phase: %s" % args.phase)
        print("Available: 0c, 1a, 1b, 1c, 2a, 2b, 3, 5")


if __name__ == "__main__":
    main()
