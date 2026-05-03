"""Re-optimize Expert D race weights on full V10 training set (10,525 companies).

Current Expert D: uniform dampened IPF of ACS + LODES (no per-industry weights).
This was never optimized -- the weights in OPTIMAL_WEIGHTS_BY_GROUP were trained
on 200 companies and aren't even used by Expert D.

This script:
  Phase 1: Grid search optimal ACS/LODES/tract weights per industry group
           (fast -- just compares blended predictions to EEO-1 truth)
  Phase 2: Full V10 pipeline evaluation with best weights
           (slower -- re-trains calibration, evaluates on both holdouts)

Usage:
    py scripts/analysis/demographics_comparison/reoptimize_race_weights.py
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
from methodologies import _blend_dicts
from methodologies_v5 import RACE_CATS, smoothed_ipf

from run_v9_2 import (
    apply_calibration_v92,
    mae_dict, evaluate,
)
from run_v10 import (
    build_v10_splits, build_records, scenario_v92_full,
    load_json, SCRIPT_DIR, train_hispanic_calibration, apply_hispanic_calibration,
    make_v92_pipeline,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def get_raw_race_data(cl, rec):
    """Get raw ACS race, LODES race, and tract race for a company."""
    naics4 = rec["naics4"]
    state_fips = rec["state_fips"]
    county_fips = rec["county_fips"]
    zipcode = rec.get("zipcode", "")

    acs_race = cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_race = tract_data.get("race") if tract_data else None

    return acs_race, lodes_race, tract_race


def blend_race(acs, lodes, tract, acs_w, lodes_w, tract_w):
    """Weighted blend of up to 3 race sources."""
    sources = []
    if acs and acs_w > 0:
        sources.append((acs, acs_w))
    if lodes and lodes_w > 0:
        sources.append((lodes, lodes_w))
    if tract and tract_w > 0:
        sources.append((tract, tract_w))
    if not sources:
        return None
    return _blend_dicts(sources, RACE_CATS)


def ipf_blend_race(acs, lodes, tract, acs_w, lodes_w, tract_w):
    """IPF-based blend: first IPF ACS+LODES, then blend with tract."""
    if not acs and not lodes:
        return tract
    if not acs:
        ipf_result = lodes
    elif not lodes:
        ipf_result = acs
    else:
        # Weight the IPF inputs
        weighted_acs = {c: acs.get(c, 0) * acs_w for c in RACE_CATS}
        weighted_lodes = {c: lodes.get(c, 0) * lodes_w for c in RACE_CATS}
        # Normalize
        acs_total = sum(weighted_acs.values())
        lodes_total = sum(weighted_lodes.values())
        if acs_total > 0:
            weighted_acs = {c: v / acs_total * 100 for c, v in weighted_acs.items()}
        if lodes_total > 0:
            weighted_lodes = {c: v / lodes_total * 100 for c, v in weighted_lodes.items()}
        ipf_result = smoothed_ipf(weighted_acs, weighted_lodes, RACE_CATS)

    if tract and tract_w > 0:
        ipf_w = acs_w + lodes_w
        return _blend_dicts([(ipf_result, ipf_w), (tract, tract_w)], RACE_CATS)
    return ipf_result


def main():
    t0 = time.time()
    print("=" * 80)
    print("Expert D Race Weight Re-optimization (Full Training Set)")
    print("=" * 80)

    # Load data
    print("\nLoading V10 splits and checkpoint...")
    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("Building records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Load raw race data for all records
    print("\nLoading raw ACS/LODES/tract race data for all companies...")
    coverage = {"acs": 0, "lodes": 0, "tract": 0}
    for rec in all_records:
        acs, lodes, tract = get_raw_race_data(cl, rec)
        rec["raw_acs_race"] = acs
        rec["raw_lodes_race"] = lodes
        rec["raw_tract_race"] = tract
        if acs:
            coverage["acs"] += 1
        if lodes:
            coverage["lodes"] += 1
        if tract:
            coverage["tract"] += 1
    print("  ACS: %d/%d (%.1f%%)" % (coverage["acs"], len(all_records),
          100.0 * coverage["acs"] / len(all_records)))
    print("  LODES: %d/%d (%.1f%%)" % (coverage["lodes"], len(all_records),
          100.0 * coverage["lodes"] / len(all_records)))
    print("  Tract: %d/%d (%.1f%%)" % (coverage["tract"], len(all_records),
          100.0 * coverage["tract"] / len(all_records)))

    # ================================================================
    # PHASE 1: Quick grid search per industry group
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 1: Grid Search Optimal Weights per Industry Group")
    print("=" * 80)

    # Get V10 baseline Expert D race MAE for comparison
    print("\nV10 baseline (checkpoint Expert D, uniform dampened IPF):")
    baseline_errs_by_group = defaultdict(list)
    for rec in train_records:
        d_race = rec["expert_preds"].get("D", {}).get("race")
        truth_race = rec["truth"].get("race")
        if d_race and truth_race:
            err = mae_dict(d_race, truth_race, RACE_CATS)
            if err is not None:
                baseline_errs_by_group[rec["naics_group"]].append(err)
                baseline_errs_by_group["_ALL_"].append(err)

    print("  %-35s %6s %8s" % ("Industry Group", "N", "Race MAE"))
    for group in sorted(baseline_errs_by_group.keys()):
        if group == "_ALL_":
            continue
        errs = baseline_errs_by_group[group]
        if len(errs) >= 30:
            print("  %-35s %6d %8.3f" % (group[:35], len(errs), sum(errs) / len(errs)))
    all_baseline = baseline_errs_by_group["_ALL_"]
    print("  %-35s %6d %8.3f" % ("OVERALL", len(all_baseline), sum(all_baseline) / len(all_baseline)))

    # Grid search
    print("\nGrid searching (ACS x LODES x Tract weights)...")
    weight_grid = []
    for acs_w in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        for lodes_w in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
            for tract_w in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
                if acs_w + lodes_w + tract_w > 0:
                    weight_grid.append((acs_w, lodes_w, tract_w))

    # Group records by industry
    groups = defaultdict(list)
    for rec in train_records:
        groups[rec["naics_group"]].append(rec)

    best_weights = {}
    print("\n  %-35s %6s %8s %8s %8s  %s" % (
        "Industry Group", "N", "Old MAE", "New MAE", "Delta", "Best Weights"))

    for group in sorted(groups.keys()):
        recs = groups[group]
        if len(recs) < 20:
            # Too few to optimize, use default
            best_weights[group] = (0.5, 0.5, 0.0)
            continue

        old_mae = sum(baseline_errs_by_group[group]) / len(baseline_errs_by_group[group])
        best_mae = 999
        best_w = (0.5, 0.5, 0.0)

        for acs_w, lodes_w, tract_w in weight_grid:
            errs = []
            for rec in recs:
                pred = blend_race(
                    rec["raw_acs_race"], rec["raw_lodes_race"], rec["raw_tract_race"],
                    acs_w, lodes_w, tract_w)
                truth = rec["truth"].get("race")
                if pred and truth:
                    err = mae_dict(pred, truth, RACE_CATS)
                    if err is not None:
                        errs.append(err)
            if errs:
                m = sum(errs) / len(errs)
                if m < best_mae:
                    best_mae = m
                    best_w = (acs_w, lodes_w, tract_w)

        best_weights[group] = best_w
        delta = best_mae - old_mae
        print("  %-35s %6d %8.3f %8.3f %+7.3f  ACS=%.1f LODES=%.1f Tract=%.1f" % (
            group[:35], len(recs), old_mae, best_mae, delta,
            best_w[0], best_w[1], best_w[2]))

    # Overall with per-group optimal weights
    all_errs_new = []
    all_errs_old = []
    for rec in train_records:
        w = best_weights.get(rec["naics_group"], (0.5, 0.5, 0.0))
        pred = blend_race(
            rec["raw_acs_race"], rec["raw_lodes_race"], rec["raw_tract_race"],
            w[0], w[1], w[2])
        truth = rec["truth"].get("race")
        if pred and truth:
            err = mae_dict(pred, truth, RACE_CATS)
            if err is not None:
                all_errs_new.append(err)

        d_race = rec["expert_preds"].get("D", {}).get("race")
        if d_race and truth:
            err = mae_dict(d_race, truth, RACE_CATS)
            if err is not None:
                all_errs_old.append(err)

    old_overall = sum(all_errs_old) / len(all_errs_old)
    new_overall = sum(all_errs_new) / len(all_errs_new)
    print("\n  OVERALL Expert D Race MAE:")
    print("    Old (uniform dampened IPF): %.3f" % old_overall)
    print("    New (per-industry blend):   %.3f (%+.3f)" % (new_overall, new_overall - old_overall))

    # ================================================================
    # PHASE 2: Full V10 pipeline with new Expert D
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 2: Full V10 Pipeline with Re-optimized Expert D")
    print("=" * 80)

    # Replace Expert D race predictions with new weights
    print("\nReplacing Expert D race predictions...")
    replaced = 0
    for rec in all_records:
        w = best_weights.get(rec["naics_group"], (0.5, 0.5, 0.0))
        new_d_race = blend_race(
            rec["raw_acs_race"], rec["raw_lodes_race"], rec["raw_tract_race"],
            w[0], w[1], w[2])
        if new_d_race:
            if "D" not in rec["expert_preds"]:
                rec["expert_preds"]["D"] = {}
            rec["expert_preds"]["D"]["race"] = new_d_race
            replaced += 1
    print("  Replaced %d / %d Expert D race predictions" % (replaced, len(all_records)))

    # Re-train Hispanic weights and calibration
    print("\nRe-training V10 pipeline...")
    final_fn_v10, cal_v10, _, _ = make_v92_pipeline(
        train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5)
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    def v10_new_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, cal_v10, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal, 0.50)
        return result

    # Evaluate on holdouts
    print("\n--- New V10 with re-optimized Expert D ---")
    m_new_perm = evaluate(perm_records, v10_new_fn)
    m_new_sealed = evaluate(v10_records, v10_new_fn)
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_new_perm["race"], m_new_perm["hisp"], m_new_perm["gender"],
        m_new_perm["p20"], m_new_perm["p30"]))
    print("  Sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_new_sealed["race"], m_new_sealed["hisp"], m_new_sealed["gender"],
        m_new_sealed["p20"], m_new_sealed["p30"]))

    # Now reload original Expert D and get baseline for comparison
    print("\n--- Reloading original Expert D for baseline comparison ---")
    for rec in all_records:
        code = rec["company_code"]
        cp_rec = rec_lookup.get(code)
        if cp_rec and cp_rec.get("expert_preds"):
            rec["expert_preds"] = cp_rec["expert_preds"]

    final_fn_base, cal_base, _, _ = make_v92_pipeline(
        train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5)
    hisp_cal_base = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    def v10_base_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, cal_base, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal_base, 0.50)
        return result

    m_base_perm = evaluate(perm_records, v10_base_fn)
    m_base_sealed = evaluate(v10_records, v10_base_fn)
    print("\n--- Original V10 baseline ---")
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_base_perm["race"], m_base_perm["hisp"], m_base_perm["gender"],
        m_base_perm["p20"], m_base_perm["p30"]))
    print("  Sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_base_sealed["race"], m_base_sealed["hisp"], m_base_sealed["gender"],
        m_base_sealed["p20"], m_base_sealed["p30"]))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\n  %-25s %8s %8s %8s %8s %8s" % (
        "Metric", "Old Perm", "New Perm", "Delta", "Old Seal", "New Seal"))
    for metric, label in [("race", "Race MAE"), ("hisp", "Hisp MAE"),
                          ("gender", "Gender MAE"), ("p20", "P>20pp"), ("p30", "P>30pp")]:
        old_p = m_base_perm[metric]
        new_p = m_new_perm[metric]
        old_s = m_base_sealed[metric]
        new_s = m_new_sealed[metric]
        fmt = "%.3f" if metric in ("race", "hisp", "gender") else "%.1f%%"
        print("  %-25s %8s %8s %+8s %8s %8s" % (
            label,
            fmt % old_p, fmt % new_p, fmt % (new_p - old_p),
            fmt % old_s, fmt % new_s))

    # Save best weights
    weights_path = os.path.join(SCRIPT_DIR, "optimized_race_weights.json")
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump({
            "best_weights": {k: {"acs": v[0], "lodes": v[1], "tract": v[2]}
                            for k, v in best_weights.items()},
            "baseline_perm": {"race": m_base_perm["race"], "hisp": m_base_perm["hisp"],
                             "gender": m_base_perm["gender"]},
            "new_perm": {"race": m_new_perm["race"], "hisp": m_new_perm["hisp"],
                        "gender": m_new_perm["gender"]},
            "baseline_sealed": {"race": m_base_sealed["race"]},
            "new_sealed": {"race": m_new_sealed["race"]},
        }, f, indent=2)
    print("\nWeights saved to %s" % weights_path)

    elapsed = time.time() - t0
    print("\nDone in %.1f minutes." % (elapsed / 60))
    conn.close()


if __name__ == "__main__":
    main()
