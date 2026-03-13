"""Generate V10 error distribution data for the report."""
import sys
import os
import json
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from run_v10 import (build_v10_splits, build_records, scenario_v92_full,
                     load_json, SCRIPT_DIR, train_hispanic_calibration,
                     apply_hispanic_calibration, estimate_confidence)
from run_v9_2 import (train_industry_weights, train_tier_weights,
                      make_hispanic_predictor, train_calibration_v92,
                      apply_calibration_v92, evaluate, mae_dict, max_cat_error,
                      RACE_CATS)
from db_config import get_connection
from psycopg2.extras import RealDictCursor
from cached_loaders_v6 import CachedLoadersV6

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def main():
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

    # Train V10 pipeline
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    std_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    def v10_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, std_cal, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal, 0.50)
        return result

    for rec in perm_records:
        rec["confidence"] = estimate_confidence(
            rec["naics_group"], rec["diversity_tier"], rec["region"])

    def dim_maes(subset, fn):
        errs_h, errs_g = [], []
        for rec in subset:
            pred = fn(rec)
            if not pred:
                continue
            h = mae_dict(pred.get("hispanic", {}), rec["truth"]["hispanic"], HISP_CATS)
            g = mae_dict(pred.get("gender", {}), rec["truth"]["gender"], GENDER_CATS)
            if h is not None:
                errs_h.append(h)
            if g is not None:
                errs_g.append(g)
        hm = sum(errs_h) / len(errs_h) if errs_h else 0
        gm = sum(errs_g) / len(errs_g) if errs_g else 0
        return hm, gm

    # BY SECTOR
    print("=== PER-DIMENSION BY SECTOR ===")
    print("%-40s %4s %7s %7s %7s %7s %7s" % ("Sector", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    sectors = sorted(set(r["naics_group"] for r in perm_records))
    for sector in sectors:
        subset = [r for r in perm_records if r["naics_group"] == sector]
        if len(subset) < 5:
            continue
        m = evaluate(subset, v10_fn)
        hm, gm = dim_maes(subset, v10_fn)
        print("%-40s %4d %7.3f %7.3f %7.3f %6.1f%% %6.1f%%" % (
            sector[:40], m["n"], m["race"], hm, gm, m["p20"], m["p30"]))

    # BY REGION
    print()
    print("=== PER-DIMENSION BY REGION ===")
    print("%-15s %4s %7s %7s %7s %7s %7s" % ("Region", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    for region in ["South", "West", "Northeast", "Midwest"]:
        subset = [r for r in perm_records if r["region"] == region]
        m = evaluate(subset, v10_fn)
        hm, gm = dim_maes(subset, v10_fn)
        print("%-15s %4d %7.3f %7.3f %7.3f %6.1f%% %6.1f%%" % (
            region, m["n"], m["race"], hm, gm, m["p20"], m["p30"]))

    # BY DIVERSITY TIER
    print()
    print("=== PER-DIMENSION BY DIVERSITY TIER ===")
    print("%-15s %4s %7s %7s %7s %7s %7s" % ("Tier", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    for tier in ["Low", "Med-Low", "Med-High", "High"]:
        subset = [r for r in perm_records if r["diversity_tier"] == tier]
        if not subset:
            continue
        m = evaluate(subset, v10_fn)
        hm, gm = dim_maes(subset, v10_fn)
        print("%-15s %4d %7.3f %7.3f %7.3f %6.1f%% %6.1f%%" % (
            tier, m["n"], m["race"], hm, gm, m["p20"], m["p30"]))

    # CONFIDENCE TIER FULL BREAKDOWN
    print()
    print("=== CONFIDENCE TIER FULL BREAKDOWN ===")
    print("%-10s %4s %7s %7s %7s %7s %7s" % ("Tier", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    for tier in ["GREEN", "YELLOW", "RED"]:
        subset = [r for r in perm_records if r["confidence"] == tier]
        if not subset:
            continue
        m = evaluate(subset, v10_fn)
        hm, gm = dim_maes(subset, v10_fn)
        print("%-10s %4d %7.3f %7.3f %7.3f %6.1f%% %6.1f%%" % (
            tier, m["n"], m["race"], hm, gm, m["p20"], m["p30"]))

    # WORST 20 COMPANIES
    print()
    print("=== WORST 20 COMPANIES (by max race category error) ===")
    worst = []
    for rec in perm_records:
        pred = v10_fn(rec)
        if not pred or not pred.get("race"):
            continue
        mx = max_cat_error(pred["race"], rec["truth"]["race"], RACE_CATS)
        if mx is not None:
            worst.append((mx, rec))
    worst.sort(key=lambda x: -x[0])
    print("%-8s %-40s %-15s %-10s %-10s %-6s" % (
        "MaxErr", "Company", "Sector", "DivTier", "Region", "Conf"))
    for mx, rec in worst[:20]:
        print("%-8.1f %-40s %-15s %-10s %-10s %-6s" % (
            mx, rec["name"][:40], rec["naics_group"][:15],
            rec["diversity_tier"], rec["region"], rec["confidence"]))

    # >30pp TAIL ANALYSIS
    print()
    print("=== >30pp TAIL ANALYSIS ===")
    tail = [(mx, rec) for mx, rec in worst if mx > 30]
    print("Total >30pp: %d / %d = %.1f%%" % (len(tail), len(worst), len(tail) / len(worst) * 100))

    sec_counts = defaultdict(int)
    for _, rec in tail:
        sec_counts[rec["naics_group"]] += 1
    print("By sector:")
    for sec, cnt in sorted(sec_counts.items(), key=lambda x: -x[1]):
        print("  %-40s %d" % (sec, cnt))

    conf_counts = defaultdict(int)
    for _, rec in tail:
        conf_counts[rec["confidence"]] += 1
    print("By confidence tier:")
    for tier in ["GREEN", "YELLOW", "RED"]:
        print("  %-10s %d (%.0f%%)" % (
            tier, conf_counts.get(tier, 0),
            conf_counts.get(tier, 0) / len(tail) * 100 if tail else 0))

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
