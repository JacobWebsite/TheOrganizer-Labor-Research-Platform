"""Fine-grained dampening search for V9.2 to find combos passing HS_P20 + P20.

Uses the V9.2 records (already built) to search a much finer dampening grid,
looking for configurations that simultaneously pass P>20pp < 16.0% AND
HC South P>20pp < 15.0%.
"""
import json
import os
import random
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
from methodologies import _blend_dicts
from methodologies_v5 import RACE_CATS, smoothed_ipf

# Import V9.2 components
from run_v9_2 import (
    build_splits, get_raw_signals, collect_black_signals,
    blend_hispanic, train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    scenario_v91_hybrid, get_gender,
    train_calibration_v91, train_calibration_v92,
    apply_calibration_v91, apply_calibration_v92,
    evaluate, check_7_criteria, print_acceptance,
    apply_black_adjustment, grid_search_black_weights,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def main():
    t0 = time.time()
    print("V9.2 FINE-GRAINED DAMPENING TUNING")
    print("=" * 120)

    # Load V9.1 trained weights
    v91 = load_json(os.path.join(SCRIPT_DIR, "v9_1_partial_lock_results.json"))
    industry_weights_v91 = v91["trained_weights"]["industry_weights"]
    tier_weights_v91 = v91["trained_weights"]["tier_weights"]
    default_weights_v91 = v91["trained_weights"]["default_weights"]

    # Load V9.2 trained weights
    v92 = load_json(os.path.join(SCRIPT_DIR, "v9_2_results.json"))

    # Load splits and checkpoint
    splits = build_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Build records
    print("Building records...")
    all_companies = splits["train_companies"] + splits["dev_companies"] + list(splits["perm_companies"])
    all_records = []
    for company in all_companies:
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
            "company_code": code,
            "name": company.get("name"),
            "naics4": naics4,
            "naics_group": naics_group,
            "region": region,
            "county_fips": county_fips,
            "state_fips": state_fips,
            "state": state,
            "zipcode": zipcode,
            "cbsa_code": cbsa_code,
            "truth": truth,
            "truth_hispanic": truth["hispanic"]["Hispanic"],
            "expert_preds": cp_rec["expert_preds"],
            "county_minority_pct": county_minority_pct,
            "diversity_tier": diversity_tier,
            "total_employees": truth.get("total_employees", 0),
        }
        rec["signals"] = get_raw_signals(cl, rec)
        rec["black_signals"] = collect_black_signals(rec, cl)
        all_records.append(rec)

    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    dev_records = [r for r in all_records if r["company_code"] in splits["dev_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    print("train=%d dev=%d perm=%d (%.0fs)" % (
        len(train_records), len(dev_records), len(perm_records), time.time() - t0))

    # Train Hispanic weights on V9.2 training set
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)

    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Train both calibration styles
    cal_v91 = train_calibration_v91(train_records, scenario_v91_hybrid)
    cal_v92 = train_calibration_v92(train_records, scenario_v91_hybrid, max_offset=15.0)

    # Also try different max_offset caps
    cal_v92_cap10 = train_calibration_v92(train_records, scenario_v91_hybrid, max_offset=10.0)
    cal_v92_cap12 = train_calibration_v92(train_records, scenario_v91_hybrid, max_offset=12.0)
    cal_v92_cap20 = train_calibration_v92(train_records, scenario_v91_hybrid, max_offset=20.0)

    # ================================================================
    # FINE-GRAINED DAMPENING SEARCH
    # ================================================================
    print("\n" + "=" * 120)
    print("FINE-GRAINED DAMPENING SEARCH")
    print("=" * 120)

    configs = [
        ("V91_cal", cal_v91, apply_calibration_v91),
        ("V92_cap10", cal_v92_cap10, apply_calibration_v92),
        ("V92_cap12", cal_v92_cap12, apply_calibration_v92),
        ("V92_cap15", cal_v92, apply_calibration_v92),
        ("V92_cap20", cal_v92_cap20, apply_calibration_v92),
    ]

    dr_range = [x / 10 for x in range(2, 11)]  # 0.2 to 1.0
    dh_range = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7]
    dg_range = [0.0, 0.3, 0.5, 0.7, 1.0]

    all_results = []

    for cal_name, cal_offsets, apply_fn in configs:
        best_pass = 0
        best_total = 999
        best_combo = None

        for dr in dr_range:
            for dh in dh_range:
                for dg in dg_range:
                    def cal_fn(rec, _dr=dr, _dh=dh, _dg=dg, _cal=cal_offsets, _apply=apply_fn):
                        pred = scenario_v91_hybrid(rec)
                        if not pred:
                            return None
                        return _apply(pred, rec, _cal, _dr, _dh, _dg)

                    m = evaluate(perm_records, cal_fn)
                    if not m:
                        continue
                    checks = check_7_criteria(m)
                    passed = sum(1 for _, _, p in checks.values() if p)
                    total = m["race"] + m["gender"] + m["p20"] + m["p30"]

                    all_results.append({
                        "cal": cal_name, "dr": dr, "dh": dh, "dg": dg,
                        "passed": passed, "total": total,
                        "race": m["race"], "p20": m["p20"], "p30": m["p30"],
                        "hisp": m["hisp"], "gender": m["gender"],
                        "abs_bias": m["abs_bias"], "hs_p20": m["hs_p20"],
                    })

                    if passed > best_pass or (passed == best_pass and total < best_total):
                        best_pass = passed
                        best_total = total
                        best_combo = (dr, dh, dg, m)

        if best_combo:
            dr, dh, dg, m = best_combo
            print("%-12s  best: d=%.1f/%.1f/%.1f  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%%" % (
                cal_name, dr, dh, dg, best_pass,
                m["race"], m["p20"], m["p30"], m["hs_p20"]))

    # Find ALL configurations passing >= 5 criteria, sorted by total
    print("\n" + "=" * 120)
    print("ALL COMBOS PASSING >= 6/7 (sorted by total score)")
    print("=" * 120)
    print("%-12s  %4s %4s %4s  %4s  %6s %6s %6s %6s %6s %6s %6s" % (
        "Cal", "dr", "dh", "dg", "Pass", "Race", "P20", "P30", "Hisp", "Gend", "Bias", "HS_20"))
    good = [r for r in all_results if r["passed"] >= 6]
    good.sort(key=lambda x: (-x["passed"], x["total"]))
    for r in good[:50]:
        print("%-12s  %.1f  %.1f  %.1f   %d    %.3f %5.1f%% %5.1f%% %.3f %.3f %.3f %5.1f%%" % (
            r["cal"], r["dr"], r["dh"], r["dg"], r["passed"],
            r["race"], r["p20"], r["p30"], r["hisp"], r["gender"], r["abs_bias"], r["hs_p20"]))

    # Find combos passing P20 AND HS_P20
    print("\n" + "=" * 120)
    print("COMBOS PASSING BOTH P>20pp < 16% AND HC South P>20pp < 15%")
    print("=" * 120)
    both = [r for r in all_results if r["p20"] < 16.0 and r["hs_p20"] < 15.0]
    both.sort(key=lambda x: (-x["passed"], x["total"]))
    if both:
        print("%-12s  %4s %4s %4s  %4s  %6s %6s %6s %6s %6s %6s %6s" % (
            "Cal", "dr", "dh", "dg", "Pass", "Race", "P20", "P30", "Hisp", "Gend", "Bias", "HS_20"))
        for r in both[:30]:
            print("%-12s  %.1f  %.1f  %.1f   %d    %.3f %5.1f%% %5.1f%% %.3f %.3f %.3f %5.1f%%" % (
                r["cal"], r["dr"], r["dh"], r["dg"], r["passed"],
                r["race"], r["p20"], r["p30"], r["hisp"], r["gender"], r["abs_bias"], r["hs_p20"]))
    else:
        print("  NONE FOUND. P20 and HS_P20 may be in tension with this training split.")

    # Also look at the borderline cases
    print("\n" + "=" * 120)
    print("BEST COMBOS BY HS_P20 (where P>20pp < 17%)")
    print("=" * 120)
    borderline = [r for r in all_results if r["p20"] < 17.0]
    borderline.sort(key=lambda x: x["hs_p20"])
    print("%-12s  %4s %4s %4s  %4s  %6s %6s %6s %6s" % (
        "Cal", "dr", "dh", "dg", "Pass", "Race", "P20", "P30", "HS_20"))
    for r in borderline[:20]:
        print("%-12s  %.1f  %.1f  %.1f   %d    %.3f %5.1f%% %5.1f%% %5.1f%%" % (
            r["cal"], r["dr"], r["dh"], r["dg"], r["passed"],
            r["race"], r["p20"], r["p30"], r["hs_p20"]))

    # HC South deep dive: what's the perm holdout HS subset like?
    hs_sub = [r for r in perm_records
              if r["naics_group"] == "Healthcare/Social (62)" and r["region"] == "South"]
    print("\n\nHC South perm holdout: n=%d" % len(hs_sub))
    if hs_sub:
        # Show county diversity distribution
        tier_counts = defaultdict(int)
        for r in hs_sub:
            tier_counts[r["diversity_tier"]] += 1
        print("  Diversity tiers: %s" % ", ".join(
            "%s=%d" % (t, n) for t, n in sorted(tier_counts.items())))

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
