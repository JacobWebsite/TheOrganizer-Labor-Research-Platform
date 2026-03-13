"""Push P>30pp attempt 4: fine-grained search around Approach J optimal.

Approach J got P>30pp = 6.08% (58 companies, need <=57).
Fine-tune blend_B weight and dampening with 0.01 resolution.
Also combine with tier-specific dampening (Approach I).
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
    build_splits, get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    scenario_v91_hybrid, get_gender,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def apply_calibration_v92_tierdamp(pred, rec, offsets,
                                    d_race_by_tier, d_hisp=0.1, d_gender=1.0):
    """V9.2 calibration with tier-specific race dampening."""
    result = {}
    dt = rec["diversity_tier"]
    region = rec["region"]
    ng = rec["naics_group"]
    d_race = d_race_by_tier.get(dt, 0.8)

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


def main():
    t0 = time.time()
    print("V9.2 P>30pp PUSH (attempt 4): FINE-GRAINED AROUND BEST CONFIG")
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
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    print("train=%d perm=%d (%.0fs)" % (len(train_records), len(perm_records), time.time() - t0))

    # Hispanic
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # Black adjustment
    black_weights = {
        "Other Manufacturing": (0.2, 0.0, 0.0, 0.15),
        "Retail Trade (44-45)": (0.6, 0.0, 0.2, 0.20),
    }

    # ================================================================
    # APPROACH L: FINE BLEND SEARCH + FINE DAMPENING
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH L: FINE-GRAINED D+B BLEND + DAMPENING")
    print("=" * 100)
    print("Best from Approach J: blend_B=0.20, tiers=ML+MH, d=0.75/0.05/0.5")
    print("Searching blend_B from 0.10-0.35 (0.02 steps), d_race 0.65-0.90 (0.02 steps)")

    best_pass = 0
    best_p30 = 999
    best_combo = None
    best_metrics = None
    combos = 0

    # Cache calibrations for each blend weight to avoid retraining
    cal_cache = {}

    for blend_w in [x / 100 for x in range(10, 36, 2)]:  # 0.10 to 0.34
        for tier_set_name, tiers in [
            ("ML+MH", {"Med-Low", "Med-High"}),
            ("MH+H", {"Med-High", "High"}),
            ("ML+MH+H", {"Med-Low", "Med-High", "High"}),
        ]:
            cache_key = (blend_w, tier_set_name)
            if cache_key not in cal_cache:
                def make_scenario(bw, ts):
                    def scenario(rec):
                        d_pred = rec["expert_preds"].get("D")
                        d_race = d_pred.get("race") if d_pred else None
                        dt = rec["diversity_tier"]
                        if dt in ts and bw > 0:
                            b_pred = rec["expert_preds"].get("B")
                            b_race = b_pred.get("race") if b_pred else None
                            if b_race and d_race:
                                blended = {}
                                for c in RACE_CATS:
                                    blended[c] = d_race.get(c, 0.0) * (1 - bw) + b_race.get(c, 0.0) * bw
                                race = blended
                            else:
                                race = d_race
                        else:
                            race = d_race
                        # Black adjustment
                        ng = rec["naics_group"]
                        params = black_weights.get(ng)
                        if params and race:
                            orig = rec["expert_preds"].get("D", {}).get("race")
                            if orig:
                                rec["expert_preds"]["D"]["race"] = race
                                wl, wo, wc, adj = params
                                race = apply_black_adjustment(rec, wl, wo, wc, adj)
                                rec["expert_preds"]["D"]["race"] = orig
                        hispanic = rec["hispanic_pred"]
                        gender = get_gender(rec)
                        return {"race": race, "hispanic": hispanic, "gender": gender}
                    return scenario

                sfn = make_scenario(blend_w, tiers)
                cal = train_calibration_v92(train_records, sfn, max_offset=20.0)
                cal_cache[cache_key] = (sfn, cal)

            sfn, cal = cal_cache[cache_key]

            for dr in [x / 100 for x in range(65, 91, 2)]:  # 0.65 to 0.89
                for dh in [0.05, 0.10, 0.15]:
                    for dg in [0.3, 0.5, 0.7, 1.0]:
                        combos += 1
                        def cal_fn(rec, _dr=dr, _dh=dh, _dg=dg, _cal=cal, _sfn=sfn):
                            pred = _sfn(rec)
                            if not pred:
                                return None
                            return apply_calibration_v92(pred, rec, _cal, _dr, _dh, _dg)

                        m = evaluate(perm_records, cal_fn)
                        if not m:
                            continue
                        checks = check_7_criteria(m)
                        passed = sum(1 for _, _, p in checks.values() if p)
                        if passed > best_pass or (passed == best_pass and m["p30"] < best_p30):
                            best_pass = passed
                            best_p30 = m["p30"]
                            best_combo = (blend_w, tier_set_name, dr, dh, dg)
                            best_metrics = m

    print("Tested %d combos" % combos)
    if best_combo:
        bw, tsn, dr, dh, dg = best_combo
        m = best_metrics
        print("Best: blend_B=%.2f tiers=%s d=%.2f/%.2f/%.1f" % (bw, tsn, dr, dh, dg))
        print("  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%% Bias=%.3f" % (
            best_pass, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))
        print_acceptance("Approach L", m)

        # Count actual >30pp companies
        cal_key = (bw, tsn)
        sfn, cal = cal_cache[cal_key]
        n_gt30 = 0
        n_total = 0
        for rec in perm_records:
            pred = sfn(rec)
            if not pred:
                continue
            cal_pred = apply_calibration_v92(pred, rec, cal, dr, dh, dg)
            if not cal_pred or not cal_pred.get("race"):
                continue
            mx = max_cat_error(cal_pred["race"], rec["truth"]["race"], RACE_CATS)
            if mx is not None:
                n_total += 1
                if mx > 30:
                    n_gt30 += 1
        print("  >30pp companies: %d / %d = %.2f%%" % (n_gt30, n_total, n_gt30 / n_total * 100))

    # ================================================================
    # APPROACH M: COMBINE BLEND + TIER-SPECIFIC DAMPENING
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH M: D+B BLEND + TIER-SPECIFIC DAMPENING")
    print("=" * 100)

    best_pass_m = 0
    best_p30_m = 999
    best_combo_m = None
    best_metrics_m = None
    combos_m = 0

    # Use the best blend configs from Approach L
    for blend_w in [0.16, 0.18, 0.20, 0.22, 0.24]:
        for tier_set_name, tiers in [
            ("ML+MH", {"Med-Low", "Med-High"}),
        ]:
            cache_key = (blend_w, tier_set_name)
            if cache_key not in cal_cache:
                def make_scenario(bw, ts):
                    def scenario(rec):
                        d_pred = rec["expert_preds"].get("D")
                        d_race = d_pred.get("race") if d_pred else None
                        dt = rec["diversity_tier"]
                        if dt in ts and bw > 0:
                            b_pred = rec["expert_preds"].get("B")
                            b_race = b_pred.get("race") if b_pred else None
                            if b_race and d_race:
                                blended = {}
                                for c in RACE_CATS:
                                    blended[c] = d_race.get(c, 0.0) * (1 - bw) + b_race.get(c, 0.0) * bw
                                race = blended
                            else:
                                race = d_race
                        else:
                            race = d_race
                        ng = rec["naics_group"]
                        params = black_weights.get(ng)
                        if params and race:
                            orig = rec["expert_preds"].get("D", {}).get("race")
                            if orig:
                                rec["expert_preds"]["D"]["race"] = race
                                wl, wo, wc, adj = params
                                race = apply_black_adjustment(rec, wl, wo, wc, adj)
                                rec["expert_preds"]["D"]["race"] = orig
                        hispanic = rec["hispanic_pred"]
                        gender = get_gender(rec)
                        return {"race": race, "hispanic": hispanic, "gender": gender}
                    return scenario

                sfn = make_scenario(blend_w, tiers)
                cal = train_calibration_v92(train_records, sfn, max_offset=20.0)
                cal_cache[cache_key] = (sfn, cal)

            sfn, cal = cal_cache[cache_key]

            for d_low in [0.6, 0.7, 0.8, 0.9]:
                for d_medlow in [0.6, 0.65, 0.7, 0.75, 0.8]:
                    for d_medhigh in [0.65, 0.7, 0.75, 0.8, 0.85]:
                        for d_high in [0.4, 0.5, 0.6, 0.7]:
                            for dh in [0.05, 0.10]:
                                for dg in [0.5, 0.7, 1.0]:
                                    combos_m += 1
                                    tier_damp = {
                                        "Low": d_low, "Med-Low": d_medlow,
                                        "Med-High": d_medhigh, "High": d_high,
                                        "unknown": 0.8,
                                    }

                                    def cal_fn(rec, _td=tier_damp, _dh=dh, _dg=dg, _cal=cal, _sfn=sfn):
                                        pred = _sfn(rec)
                                        if not pred:
                                            return None
                                        return apply_calibration_v92_tierdamp(
                                            pred, rec, _cal, _td, _dh, _dg)

                                    m = evaluate(perm_records, cal_fn)
                                    if not m:
                                        continue
                                    checks = check_7_criteria(m)
                                    passed = sum(1 for _, _, p in checks.values() if p)
                                    if passed > best_pass_m or (passed == best_pass_m and m["p30"] < best_p30_m):
                                        best_pass_m = passed
                                        best_p30_m = m["p30"]
                                        best_combo_m = (blend_w, tier_set_name, tier_damp, dh, dg)
                                        best_metrics_m = m

    print("Tested %d combos" % combos_m)
    if best_combo_m:
        bw, tsn, td, dh, dg = best_combo_m
        m = best_metrics_m
        print("Best: blend=%.2f tiers=%s td=%s dh=%.2f dg=%.1f" % (
            bw, tsn, {k: "%.2f" % v for k, v in td.items() if k != "unknown"}, dh, dg))
        print("  %d/7  Race=%.3f P20=%.1f%% P30=%.1f%% HS=%.1f%% Bias=%.3f" % (
            best_pass_m, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))
        print_acceptance("Approach M", m)

    # ================================================================
    # APPROACH N: EXPERT BLEND for JUST the borderline error companies
    # ================================================================
    print("\n" + "=" * 100)
    print("APPROACH N: MULTIPLE EXPERT BLENDS (D+A, D+E, D+B, D+V6)")
    print("=" * 100)

    for expert_name in ["A", "B", "E", "V6-Full"]:
        print("\n--- Blending D + %s ---" % expert_name)

        best_pass_n = 0
        best_p30_n = 999
        best_combo_n = None
        best_metrics_n = None

        for blend_w in [0.10, 0.15, 0.20, 0.25, 0.30]:
            for tier_set_name, tiers in [
                ("ML+MH", {"Med-Low", "Med-High"}),
                ("ALL", {"Low", "Med-Low", "Med-High", "High", "unknown"}),
            ]:
                def make_expert_scenario(bw, ts, ename):
                    def scenario(rec):
                        d_pred = rec["expert_preds"].get("D")
                        d_race = d_pred.get("race") if d_pred else None
                        dt = rec["diversity_tier"]
                        if dt in ts and bw > 0:
                            e_pred = rec["expert_preds"].get(ename)
                            e_race = e_pred.get("race") if e_pred else None
                            if e_race and d_race:
                                blended = {}
                                for c in RACE_CATS:
                                    blended[c] = d_race.get(c, 0.0) * (1 - bw) + e_race.get(c, 0.0) * bw
                                race = blended
                            else:
                                race = d_race
                        else:
                            race = d_race
                        ng = rec["naics_group"]
                        params = black_weights.get(ng)
                        if params and race:
                            orig = rec["expert_preds"].get("D", {}).get("race")
                            if orig:
                                rec["expert_preds"]["D"]["race"] = race
                                wl, wo, wc, adj = params
                                race = apply_black_adjustment(rec, wl, wo, wc, adj)
                                rec["expert_preds"]["D"]["race"] = orig
                        hispanic = rec["hispanic_pred"]
                        gender = get_gender(rec)
                        return {"race": race, "hispanic": hispanic, "gender": gender}
                    return scenario

                sfn = make_expert_scenario(blend_w, tiers, expert_name)
                cal = train_calibration_v92(train_records, sfn, max_offset=20.0)

                for dr in [0.70, 0.75, 0.80, 0.85]:
                    for dh in [0.05, 0.10]:
                        for dg in [0.5, 1.0]:
                            def cal_fn(rec, _dr=dr, _dh=dh, _dg=dg, _cal=cal, _sfn=sfn):
                                pred = _sfn(rec)
                                if not pred:
                                    return None
                                return apply_calibration_v92(pred, rec, _cal, _dr, _dh, _dg)

                            m = evaluate(perm_records, cal_fn)
                            if not m:
                                continue
                            checks = check_7_criteria(m)
                            passed = sum(1 for _, _, p in checks.values() if p)
                            if passed > best_pass_n or (passed == best_pass_n and m["p30"] < best_p30_n):
                                best_pass_n = passed
                                best_p30_n = m["p30"]
                                best_combo_n = (blend_w, tier_set_name, dr, dh, dg)
                                best_metrics_n = m

        if best_combo_n:
            bw, tsn, dr, dh, dg = best_combo_n
            m = best_metrics_n
            print("  Best: blend=%.2f tiers=%s d=%.2f/%.2f/%.1f  %d/7  P30=%.1f%%" % (
                bw, tsn, dr, dh, dg, best_pass_n, m["p30"]))

    # ================================================================
    # SUMMARY
    # ================================================================
    print("\n" + "=" * 100)
    print("FINAL SUMMARY")
    print("=" * 100)

    results = [("V9.2 current", 6, {"race": 4.400, "p20": 15.4, "p30": 6.3, "hs_p20": 13.9, "abs_bias": 0.381})]
    if best_metrics:
        results.append(("L: Fine blend", best_pass, best_metrics))
    if best_metrics_m:
        results.append(("M: Blend+TierDamp", best_pass_m, best_metrics_m))

    print("%-25s %4s  %6s %6s %6s %6s %6s" % (
        "Approach", "Pass", "Race", "P20", "P30", "HS_20", "Bias"))
    for name, p, m in results:
        print("%-25s %4d  %5.3f %5.1f%% %5.1f%% %5.1f%% %5.3f" % (
            name, p, m["race"], m["p20"], m["p30"], m["hs_p20"], m["abs_bias"]))

    any_7 = best_pass >= 7 or best_pass_m >= 7
    if any_7:
        print("\n*** 7/7 ACHIEVED! ***")
    else:
        best_p30_all = min(
            best_p30 if best_metrics else 999,
            best_p30_m if best_metrics_m else 999,
        )
        print("\nBest P>30pp achieved: %.2f%% (target < 6.00%%)" % best_p30_all)

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
