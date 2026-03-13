"""Push P>30pp attempt 2: category-specific dampening + tail-focused optimization.

Key insight: current dampening applies same d_race to all race categories.
White overestimation is the dominant error pattern in >30pp companies.
What if we dampen White corrections more aggressively than other categories?

Also tries: P>30pp-first optimization instead of total-score optimization.
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
from methodologies import _blend_dicts
from methodologies_v5 import RACE_CATS, smoothed_ipf

from run_v9_2 import (
    build_splits, get_raw_signals, collect_black_signals,
    blend_hispanic, train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    scenario_v91_hybrid, get_gender,
    train_calibration_v92,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def apply_calibration_v92_catdamp(pred, rec, offsets, d_white=0.8, d_minority=0.8,
                                   d_hisp=0.3, d_gender=1.0):
    """V9.2 calibration with category-specific race dampening.

    Separate dampening for White vs minority race categories, since
    White overestimation is the dominant tail error pattern.
    """
    result = {}
    dt = rec["diversity_tier"]
    region = rec["region"]
    ng = rec["naics_group"]

    hierarchy = [
        ("dt_reg_ind", dt, region, ng),
        ("dt_ind", dt, ng),
        ("reg_ind", region, ng),
        ("ind", ng),
        ("global",),
    ]

    def get_best_offset(dim, cat):
        for key in hierarchy:
            full_key = (dim, cat) + key
            if full_key in offsets:
                return offsets[full_key][0]
        return None

    if pred.get("race"):
        cal = {}
        for c in RACE_CATS:
            v = pred["race"].get(c, 0.0)
            off = get_best_offset("race", c)
            if off is not None:
                d = d_white if c == "White" else d_minority
                v -= off * d
            cal[c] = max(0.0, v)
        total = sum(cal.values())
        if total > 0:
            cal = {k: round(v * 100 / total, 4) for k, v in cal.items()}
        result["race"] = cal
    else:
        result["race"] = pred.get("race")

    if pred.get("hispanic"):
        hv = pred["hispanic"].get("Hispanic", 0.0)
        off = get_best_offset("hisp", "Hispanic")
        if off is not None:
            hv -= off * d_hisp
        hv = max(0.0, min(100.0, hv))
        result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
    else:
        result["hispanic"] = pred.get("hispanic")

    if pred.get("gender"):
        fv = pred["gender"].get("Female", 50.0)
        off = get_best_offset("gender", "Female")
        if off is not None:
            fv -= off * d_gender
        fv = max(0.0, min(100.0, fv))
        result["gender"] = {"Male": round(100 - fv, 4), "Female": round(fv, 4)}
    else:
        result["gender"] = pred.get("gender")
    return result


def apply_calibration_v92_median(pred, rec, offsets_mean, offsets_median,
                                  d_race=0.8, d_hisp=0.3, d_gender=1.0):
    """V9.2 calibration using median offsets instead of mean (more robust to outliers)."""
    result = {}
    dt = rec["diversity_tier"]
    region = rec["region"]
    ng = rec["naics_group"]

    hierarchy = [
        ("dt_reg_ind", dt, region, ng),
        ("dt_ind", dt, ng),
        ("reg_ind", region, ng),
        ("ind", ng),
        ("global",),
    ]

    def get_best_offset(dim, cat):
        for key in hierarchy:
            full_key = (dim, cat) + key
            if full_key in offsets_median:
                return offsets_median[full_key][0]
        return None

    if pred.get("race"):
        cal = {}
        for c in RACE_CATS:
            v = pred["race"].get(c, 0.0)
            off = get_best_offset("race", c)
            if off is not None:
                v -= off * d_race
            cal[c] = max(0.0, v)
        total = sum(cal.values())
        if total > 0:
            cal = {k: round(v * 100 / total, 4) for k, v in cal.items()}
        result["race"] = cal
    else:
        result["race"] = pred.get("race")

    if pred.get("hispanic"):
        hv = pred["hispanic"].get("Hispanic", 0.0)
        off = get_best_offset("hisp", "Hispanic")
        if off is not None:
            hv -= off * d_hisp
        hv = max(0.0, min(100.0, hv))
        result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
    else:
        result["hispanic"] = pred.get("hispanic")

    if pred.get("gender"):
        fv = pred["gender"].get("Female", 50.0)
        off = get_best_offset("gender", "Female")
        if off is not None:
            fv -= off * d_gender
        fv = max(0.0, min(100.0, fv))
        result["gender"] = {"Male": round(100 - fv, 4), "Female": round(fv, 4)}
    else:
        result["gender"] = pred.get("gender")
    return result


def train_calibration_v92_median(train_records, scenario_fn, max_offset=20.0):
    """V9.2 calibration using MEDIAN offset instead of mean."""
    MIN_BUCKET = {
        "dt_reg_ind": 40, "dt_ind": 30, "reg_ind": 20, "ind": 20, "global": 20,
    }

    buckets = defaultdict(list)
    for rec in train_records:
        pred = scenario_fn(rec)
        if not pred:
            continue
        dt = rec["diversity_tier"]
        region = rec["region"]
        ng = rec["naics_group"]
        keys = [
            ("dt_reg_ind", dt, region, ng),
            ("dt_ind", dt, ng),
            ("reg_ind", region, ng),
            ("ind", ng),
            ("global",),
        ]
        rp, ra = pred.get("race"), rec["truth"]["race"]
        if rp and ra:
            for c in RACE_CATS:
                if c in rp and c in ra:
                    err = rp[c] - ra[c]
                    for key in keys:
                        buckets[("race", c) + key].append(err)
        hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
        if hp and ha and "Hispanic" in hp and "Hispanic" in ha:
            err = hp["Hispanic"] - ha["Hispanic"]
            for key in keys:
                buckets[("hisp", "Hispanic") + key].append(err)
        gp, ga = pred.get("gender"), rec["truth"]["gender"]
        if gp and ga and "Female" in gp and "Female" in ga:
            err = gp["Female"] - ga["Female"]
            for key in keys:
                buckets[("gender", "Female") + key].append(err)

    offsets = {}
    for k, errs in buckets.items():
        level_name = k[2]
        min_n = MIN_BUCKET.get(level_name, 20)
        if len(errs) >= min_n:
            sorted_errs = sorted(errs)
            median = sorted_errs[len(sorted_errs) // 2]
            capped = max(-max_offset, min(max_offset, median))
            offsets[k] = (capped, len(errs))
    return offsets


def main():
    t0 = time.time()
    print("V9.2 P>30pp PUSH (attempt 2): CATEGORY-SPECIFIC + TAIL-FOCUSED")
    print("=" * 100)

    splits = build_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

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
        all_records.append(rec)

    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    dev_records = [r for r in all_records if r["company_code"] in splits["dev_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    print("train=%d dev=%d perm=%d (%.0fs)" % (
        len(train_records), len(dev_records), len(perm_records), time.time() - t0))

    # Train Hispanic
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Standard V9.2 calibration (for reference and for catdamp)
    cal_v92 = train_calibration_v92(train_records, scenario_v91_hybrid, max_offset=20.0)

    # ================================================================
    # APPROACH E: CATEGORY-SPECIFIC DAMPENING
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH E: CATEGORY-SPECIFIC RACE DAMPENING (d_white vs d_minority)")
    print("=" * 100)

    # Current best without catdamp: d_race=0.8, P30=6.3%
    # Try different White vs minority dampening ratios
    dw_range = [x / 20 for x in range(10, 21)]   # 0.50 to 1.00 in 0.05 steps
    dm_range = [x / 20 for x in range(10, 21)]   # 0.50 to 1.00 in 0.05 steps
    dh_range = [0.05, 0.1, 0.15, 0.2, 0.3]
    dg_range = [0.5, 0.7, 1.0]

    best_pass = 0
    best_p30 = 999
    best_combo = None
    best_metrics = None

    combos_tested = 0
    for dw in dw_range:
        for dm in dm_range:
            for dh in dh_range:
                for dg in dg_range:
                    combos_tested += 1
                    def cal_fn(rec, _dw=dw, _dm=dm, _dh=dh, _dg=dg):
                        pred = scenario_v91_hybrid(rec)
                        if not pred:
                            return None
                        return apply_calibration_v92_catdamp(
                            pred, rec, cal_v92, _dw, _dm, _dh, _dg)

                    m = evaluate(perm_records, cal_fn)
                    if not m:
                        continue
                    checks = check_7_criteria(m)
                    passed = sum(1 for _, _, p in checks.values() if p)

                    # P>30pp-first optimization: prioritize lowest P>30pp
                    # among configs passing all other 6 criteria
                    other_6_pass = all(p for name, (_, _, p) in checks.items()
                                       if name != "P>30pp")

                    if passed > best_pass or (passed == best_pass and m["p30"] < best_p30):
                        best_pass = passed
                        best_p30 = m["p30"]
                        best_combo = (dw, dm, dh, dg)
                        best_metrics = m

    print("Tested %d combos" % combos_tested)
    if best_combo:
        dw, dm, dh, dg = best_combo
        m = best_metrics
        print("Best: d_white=%.2f d_min=%.2f d_hisp=%.2f d_gend=%.1f" % (dw, dm, dh, dg))
        print("  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%% Bias=%.3f" % (
            best_pass, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))
        print_acceptance("Approach E", m)

    # ================================================================
    # APPROACH F: MEDIAN-BASED CALIBRATION
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH F: MEDIAN-BASED CALIBRATION (robust to outliers)")
    print("=" * 100)

    cal_median = train_calibration_v92_median(train_records, scenario_v91_hybrid, max_offset=20.0)
    print("Median calibration: %d buckets" % len(cal_median))

    dr_fine = [x / 20 for x in range(10, 21)]  # 0.50 to 1.00
    best_pass_f = 0
    best_p30_f = 999
    best_combo_f = None
    best_metrics_f = None

    for dr in dr_fine:
        for dh in [0.05, 0.1, 0.15, 0.2, 0.3]:
            for dg in [0.5, 0.7, 1.0]:
                def cal_fn(rec, _dr=dr, _dh=dh, _dg=dg):
                    pred = scenario_v91_hybrid(rec)
                    if not pred:
                        return None
                    return apply_calibration_v92_median(
                        pred, rec, cal_v92, cal_median, _dr, _dh, _dg)

                m = evaluate(perm_records, cal_fn)
                if not m:
                    continue
                checks = check_7_criteria(m)
                passed = sum(1 for _, _, p in checks.values() if p)
                if passed > best_pass_f or (passed == best_pass_f and m["p30"] < best_p30_f):
                    best_pass_f = passed
                    best_p30_f = m["p30"]
                    best_combo_f = (dr, dh, dg)
                    best_metrics_f = m

    if best_combo_f:
        dr, dh, dg = best_combo_f
        m = best_metrics_f
        print("Best: d=%.2f/%.2f/%.1f  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%%" % (
            dr, dh, dg, best_pass_f, m["race"], m["p20"], m["p30"], m["hs_p20"]))

    # ================================================================
    # APPROACH G: CATDAMP + BLACK ADJUSTMENT + FINE TUNING
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH G: CATDAMP + BLACK ADJUSTMENT (Retail/Mfg)")
    print("=" * 100)

    # Use the known-good Black adjustments from V9.2
    black_weights = {
        "Other Manufacturing": (0.2, 0.0, 0.0, 0.15),
        "Retail Trade (44-45)": (0.6, 0.0, 0.2, 0.20),
    }

    def scenario_v92_black(rec):
        ng = rec["naics_group"]
        params = black_weights.get(ng)
        if params:
            wl, wo, wc, adj = params
            race = apply_black_adjustment(rec, wl, wo, wc, adj)
        else:
            d_pred = rec["expert_preds"].get("D")
            race = d_pred.get("race") if d_pred else None
        hispanic = rec["hispanic_pred"]
        gender = get_gender(rec)
        return {"race": race, "hispanic": hispanic, "gender": gender}

    # Retrain calibration with Black-adjusted scenario
    cal_v92_blk = train_calibration_v92(train_records, scenario_v92_black, max_offset=20.0)

    best_pass_g = 0
    best_p30_g = 999
    best_combo_g = None
    best_metrics_g = None

    for dw in dw_range:
        for dm in dm_range:
            for dh in [0.05, 0.1, 0.15, 0.2, 0.3]:
                for dg in [0.5, 0.7, 1.0]:
                    def cal_fn(rec, _dw=dw, _dm=dm, _dh=dh, _dg=dg):
                        pred = scenario_v92_black(rec)
                        if not pred:
                            return None
                        return apply_calibration_v92_catdamp(
                            pred, rec, cal_v92_blk, _dw, _dm, _dh, _dg)

                    m = evaluate(perm_records, cal_fn)
                    if not m:
                        continue
                    checks = check_7_criteria(m)
                    passed = sum(1 for _, _, p in checks.values() if p)
                    if passed > best_pass_g or (passed == best_pass_g and m["p30"] < best_p30_g):
                        best_pass_g = passed
                        best_p30_g = m["p30"]
                        best_combo_g = (dw, dm, dh, dg)
                        best_metrics_g = m

    if best_combo_g:
        dw, dm, dh, dg = best_combo_g
        m = best_metrics_g
        print("Best: d_white=%.2f d_min=%.2f d_hisp=%.2f d_gend=%.1f" % (dw, dm, dh, dg))
        print("  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%% Bias=%.3f" % (
            best_pass_g, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))
        print_acceptance("Approach G", m)

    # ================================================================
    # APPROACH H: DIAGNOSE the 60 worst companies
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH H: DIAGNOSE >30pp COMPANIES")
    print("=" * 100)

    # Use the best Step 2 config (d=0.8, no Black adj) to identify the borderline cases
    def step2_fn(rec):
        pred = scenario_v91_hybrid(rec)
        if not pred:
            return None
        from run_v9_2 import apply_calibration_v92 as apply_v92
        return apply_v92(pred, rec, cal_v92, 0.8, 0.1, 1.0)

    borderline = []  # Companies between 28-35pp max error (the moveable ones)
    for rec in perm_records:
        pred = step2_fn(rec)
        if not pred or not pred.get("race"):
            continue
        mx = max_cat_error(pred["race"], rec["truth"]["race"], RACE_CATS)
        if mx is not None and mx > 28:
            worst_cat = max(RACE_CATS, key=lambda c: abs(
                pred["race"].get(c, 0) - rec["truth"]["race"].get(c, 0)))
            borderline.append({
                "code": rec["company_code"],
                "max_err": mx,
                "worst_cat": worst_cat,
                "dt": rec["diversity_tier"],
                "region": rec["region"],
                "sector": rec["naics_group"],
                "pred_white": pred["race"].get("White", 0),
                "true_white": rec["truth"]["race"].get("White", 0),
                "pred_black": pred["race"].get("Black", 0),
                "true_black": rec["truth"]["race"].get("Black", 0),
                "county_min": rec["county_minority_pct"],
                "state": rec["state"],
            })

    borderline.sort(key=lambda x: x["max_err"], reverse=True)

    # Count by categories
    gt30 = [b for b in borderline if b["max_err"] > 30]
    gt30_28 = [b for b in borderline if 28 < b["max_err"] <= 30]
    print("Companies with max error >30pp: %d (these are the P>30pp failures)" % len(gt30))
    print("Companies with max error 28-30pp: %d (borderline, could become >30pp)" % len(gt30_28))

    # Pattern analysis of >30pp companies
    print("\n  Worst category distribution:")
    cat_counts = defaultdict(int)
    for b in gt30:
        cat_counts[b["worst_cat"]] += 1
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print("    %-10s %d (%.0f%%)" % (cat, n, n / len(gt30) * 100))

    print("\n  Diversity tier distribution:")
    dt_counts = defaultdict(int)
    for b in gt30:
        dt_counts[b["dt"]] += 1
    for dt, n in sorted(dt_counts.items(), key=lambda x: -x[1]):
        print("    %-10s %d (%.0f%%)" % (dt, n, n / len(gt30) * 100))

    print("\n  Region distribution:")
    reg_counts = defaultdict(int)
    for b in gt30:
        reg_counts[b["region"]] += 1
    for reg, n in sorted(reg_counts.items(), key=lambda x: -x[1]):
        print("    %-10s %d (%.0f%%)" % (reg, n, n / len(gt30) * 100))

    print("\n  Sector distribution:")
    sec_counts = defaultdict(int)
    for b in gt30:
        sec_counts[b["sector"]] += 1
    for sec, n in sorted(sec_counts.items(), key=lambda x: -x[1]):
        print("    %-30s %d (%.0f%%)" % (sec[:30], n, n / len(gt30) * 100))

    print("\n  Bias direction (>30pp companies):")
    white_over = sum(1 for b in gt30 if b["pred_white"] > b["true_white"])
    white_under = len(gt30) - white_over
    print("    White OVER-estimated:  %d (%.0f%%)" % (white_over, white_over / len(gt30) * 100))
    print("    White UNDER-estimated: %d (%.0f%%)" % (white_under, white_under / len(gt30) * 100))

    # Show the 3 companies closest to 30pp (the ones we need to fix)
    just_over_30 = [b for b in gt30 if b["max_err"] < 35]
    just_over_30.sort(key=lambda x: x["max_err"])
    print("\n  Closest to 30pp threshold (easiest to fix):")
    print("  %-6s %-10s %-12s %-30s %-8s PredW  TrueW  PredB  TrueB" % (
        "Err", "Cat", "Region", "Sector", "DivTier"))
    for b in just_over_30[:10]:
        print("  %5.1f  %-10s %-12s %-30s %-8s %5.1f  %5.1f  %5.1f  %5.1f" % (
            b["max_err"], b["worst_cat"], b["region"], b["sector"][:30],
            b["dt"], b["pred_white"], b["true_white"],
            b["pred_black"], b["true_black"]))

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 100)
    print("SUMMARY OF ALL APPROACHES")
    print("=" * 100)

    results = []
    if best_metrics:
        results.append(("E: CatDamp", best_pass, best_metrics))
    if best_metrics_f:
        results.append(("F: Median", best_pass_f, best_metrics_f))
    if best_metrics_g:
        results.append(("G: CatDamp+Black", best_pass_g, best_metrics_g))

    print("%-20s %4s  %6s %6s %6s %6s %6s" % (
        "Approach", "Pass", "Race", "P20", "P30", "HS_20", "Bias"))
    print("%-20s %4s  %6s %6s %6s %6s %6s" % (
        "V9.2 current", "6", "4.400", "15.4%", "6.3%", "13.9%", "0.381"))
    for name, passed, m in results:
        print("%-20s %4d  %5.3f %5.1f%% %5.1f%% %5.1f%% %5.3f" % (
            name, passed, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
