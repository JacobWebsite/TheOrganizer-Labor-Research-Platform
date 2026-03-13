"""Test all promising expert combinations for race/hispanic/gender.

Tests which expert produces the best race vector, hispanic, and gender
when combined with the industry+adaptive Hispanic estimator and calibration.
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

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]
SPLIT_SEED = 20260311


def load_json(p):
    with open(p, "r") as f:
        return json.load(f)


def main():
    t0 = time.time()

    # Load V9.1 trained weights
    v91 = load_json(os.path.join(SCRIPT_DIR, "v9_1_partial_lock_results.json"))
    industry_weights = v91["trained_weights"]["industry_weights"]
    tier_weights = v91["trained_weights"]["tier_weights"]
    default_weights = v91["trained_weights"]["default_weights"]

    # Load checkpoint
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    all_recs = cp["all_records"]
    rec_lookup = {r["company_code"]: r for r in all_recs}

    # Build splits
    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"] if isinstance(perm_data, dict) else perm_data
    perm_codes = {c["company_code"] for c in perm_companies}
    pool = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v6.json"))
    non_perm = [c for c in pool if c["company_code"] not in perm_codes]
    rng = random.Random(SPLIT_SEED)
    shuffled = non_perm[:]
    rng.shuffle(shuffled)
    train_codes = {c["company_code"] for c in shuffled[:10000]}
    dev_codes = {c["company_code"] for c in shuffled[10000:]}

    # Connect for Hispanic signals
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Build records
    print("Building records with Hispanic signals...")
    records = []
    all_companies = list(shuffled[:10000]) + list(shuffled[10000:]) + list(perm_companies)
    for idx, company in enumerate(all_companies, 1):
        if idx % 3000 == 0:
            print("  %d/%d (%.0fs)" % (idx, len(all_companies), time.time() - t0))
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
        naics_2 = naics4[:2] if naics4 else None

        signals = {}
        signals["pums"] = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
        acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
        signals["acs"] = acs_hisp
        ind_hisp, _ = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
        signals["ind_lodes"] = ind_hisp
        county_hisp = cl.get_lodes_hispanic(county_fips)
        signals["county_lodes"] = county_hisp
        signals["ipf_ind"] = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
        tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
        signals["tract"] = tract_data.get("hispanic") if tract_data else None
        occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
        if occ_chain and occ_chain.get("Hispanic") is not None:
            signals["occ_chain"] = {"Hispanic": occ_chain["Hispanic"],
                                     "Not Hispanic": 100.0 - occ_chain["Hispanic"]}
        else:
            signals["occ_chain"] = None
        signals["county_hisp_pct"] = (county_hisp["Hispanic"]
                                       if county_hisp and "Hispanic" in county_hisp else None)

        records.append({
            "company_code": code,
            "naics_group": naics_group,
            "region": region,
            "truth": truth,
            "expert_preds": cp_rec["expert_preds"],
            "signals": signals,
        })

    train_recs = [r for r in records if r["company_code"] in train_codes]
    dev_recs = [r for r in records if r["company_code"] in dev_codes]
    perm_recs = [r for r in records if r["company_code"] in perm_codes]
    print("Records: train=%d dev=%d perm=%d (%.0fs)" % (
        len(train_recs), len(dev_recs), len(perm_recs), time.time() - t0))

    # Hispanic predictor
    def blend_hispanic(signals, weights):
        sources = []
        for name, w in weights.items():
            if w <= 0:
                continue
            sig = signals.get(name)
            if sig and "Hispanic" in sig:
                sources.append((sig, w))
        if not sources:
            for fb in ["acs", "county_lodes"]:
                sig = signals.get(fb)
                if sig and "Hispanic" in sig:
                    return sig
            return None
        if len(sources) == 1:
            return sources[0][0]
        return _blend_dicts(sources, HISP_CATS)

    def hisp_predict(rec):
        ng = rec["naics_group"]
        if ng in industry_weights:
            weights = industry_weights[ng]
        else:
            county_hisp = rec["signals"].get("county_hisp_pct")
            if county_hisp is None:
                tier = "medium"
            elif county_hisp < 10:
                tier = "low"
            elif county_hisp < 25:
                tier = "medium"
            else:
                tier = "high"
            weights = tier_weights.get(tier, default_weights)
        result = blend_hispanic(rec["signals"], weights)
        if result and "Hispanic" in result:
            return {"Hispanic": result["Hispanic"], "Not Hispanic": result["Not Hispanic"]}
        return None

    # Metrics
    def mae_vec(p, a, cats):
        v = [abs(p.get(c, 0) - a.get(c, 0)) for c in cats if c in p and c in a]
        return sum(v) / len(v) if v else None

    def max_cat_err(p, a, cats):
        v = [abs(p.get(c, 0) - a.get(c, 0)) for c in cats if c in p and c in a]
        return max(v) if v else None

    def evaluate(recs, scenario_fn):
        race_maes, hisp_maes, gender_maes, max_errs = [], [], [], []
        race_preds, race_acts = [], []
        for rec in recs:
            pred = scenario_fn(rec)
            if not pred:
                continue
            rp = pred.get("race")
            ra = rec["truth"]["race"]
            if rp and ra:
                m = mae_vec(rp, ra, RACE_CATS)
                if m is not None:
                    race_maes.append(m)
                mx = max_cat_err(rp, ra, RACE_CATS)
                if mx is not None:
                    max_errs.append(mx)
                race_preds.append(rp)
                race_acts.append(ra)
            hp = pred.get("hispanic")
            ha = rec["truth"]["hispanic"]
            if hp and ha:
                m = mae_vec(hp, ha, HISP_CATS)
                if m is not None:
                    hisp_maes.append(m)
            gp = pred.get("gender")
            ga = rec["truth"]["gender"]
            if gp and ga:
                m = mae_vec(gp, ga, GENDER_CATS)
                if m is not None:
                    gender_maes.append(m)
        n = len(race_maes)
        if not n:
            return None
        abs_bias_vals = []
        for c in RACE_CATS:
            errs = [race_preds[i].get(c, 0) - race_acts[i].get(c, 0)
                    for i in range(len(race_preds))
                    if c in race_preds[i] and c in race_acts[i]]
            if errs:
                abs_bias_vals.append(abs(sum(errs) / len(errs)))
        return {
            "n": n,
            "race": sum(race_maes) / n,
            "hisp": sum(hisp_maes) / len(hisp_maes) if hisp_maes else 0,
            "gender": sum(gender_maes) / len(gender_maes) if gender_maes else 0,
            "p20": sum(1 for e in max_errs if e > 20) / len(max_errs) * 100 if max_errs else 0,
            "p30": sum(1 for e in max_errs if e > 30) / len(max_errs) * 100 if max_errs else 0,
            "abs_bias": sum(abs_bias_vals) / len(abs_bias_vals) if abs_bias_vals else 0,
        }

    def hs_tail(recs, scenario_fn):
        subset = [r for r in recs
                  if r["naics_group"] == "Healthcare/Social (62)" and r["region"] == "South"]
        max_errs = []
        for rec in subset:
            pred = scenario_fn(rec)
            if not pred or not pred.get("race"):
                continue
            mx = max_cat_err(pred["race"], rec["truth"]["race"], RACE_CATS)
            if mx is not None:
                max_errs.append(mx)
        n = len(max_errs)
        return {
            "n": n,
            "p20": sum(1 for e in max_errs if e > 20) / n * 100 if n else 0,
            "p30": sum(1 for e in max_errs if e > 30) / n * 100 if n else 0,
        }

    # Calibration
    def train_cal(train_records, scenario_fn):
        buckets = defaultdict(list)
        for rec in train_records:
            pred = scenario_fn(rec)
            if not pred:
                continue
            key = (rec["region"], rec["naics_group"])
            rp = pred.get("race")
            ra = rec["truth"]["race"]
            if rp and ra:
                for c in RACE_CATS:
                    if c in rp and c in ra:
                        buckets[("race", c, key)].append(rp[c] - ra[c])
            hp = pred.get("hispanic")
            ha = rec["truth"]["hispanic"]
            if hp and ha and "Hispanic" in hp and "Hispanic" in ha:
                buckets[("hisp", "Hispanic", key)].append(hp["Hispanic"] - ha["Hispanic"])
        offsets = {}
        for k, errs in buckets.items():
            if len(errs) >= 20:
                offsets[k] = sum(errs) / len(errs)
        return offsets

    def apply_cal(pred, rec, offsets, d=0.5):
        result = {}
        key = (rec["region"], rec["naics_group"])
        if pred.get("race"):
            cal = {}
            for c in RACE_CATS:
                v = pred["race"].get(c, 0.0)
                off = offsets.get(("race", c, key))
                if off is not None:
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
            off = offsets.get(("hisp", "Hispanic", key))
            if off is not None:
                hv -= off * d
            hv = max(0.0, min(100.0, hv))
            result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
        else:
            result["hispanic"] = pred.get("hispanic")
        result["gender"] = pred.get("gender")
        return result

    # Scenario builder
    def make_scenario(race_exp, hisp_mode, gender_exp):
        def fn(rec):
            ep = rec["expert_preds"]
            # Race
            if race_exp == "D+V6":
                d_race = ep.get("D", {}).get("race")
                v6_race = ep.get("V6-Full", {}).get("race")
                if d_race and v6_race:
                    race = {c: round((d_race.get(c, 0) + v6_race.get(c, 0)) / 2, 4) for c in RACE_CATS}
                else:
                    race = d_race or v6_race
            else:
                p = ep.get(race_exp)
                race = p.get("race") if p else None
            # Hispanic
            if hisp_mode == "new":
                hispanic = hisp_predict(rec)
            else:
                p = ep.get(race_exp)
                hispanic = p.get("hispanic") if p else None
            # Gender
            p = ep.get(gender_exp)
            gender = p.get("gender") if p else None
            if not gender:
                for fb in ["F", "V6-Full", "D", "G"]:
                    p2 = ep.get(fb)
                    if p2 and p2.get("gender"):
                        gender = p2["gender"]
                        break
            return {"race": race, "hispanic": hispanic, "gender": gender}
        return fn

    # Define combinations
    combos = [
        ("D solo (baseline)",    "D",    None,  "D"),
        ("D+new+F",              "D",    "new", "F"),
        ("D+new+V6",             "D",    "new", "V6-Full"),
        ("V6+new+F",             "V6-Full", "new", "F"),
        ("V6+new+V6",            "V6-Full", "new", "V6-Full"),
        ("D+V6_blend+new+F",    "D+V6", "new", "F"),
        ("D+V6_blend+new+V6",   "D+V6", "new", "V6-Full"),
        ("B+new+F",              "B",    "new", "F"),
    ]

    # PRE-CALIBRATION
    print("\nEXPERT COMBINATION COMPARISON -- PRE-CALIBRATION (Perm 1,000)")
    print("=" * 120)
    print("%-25s  %-7s %-7s %-7s %-7s %-7s %-7s %-8s %-8s %s" % (
        "Combo", "Race", "Hisp", "Gender", "P>20", "P>30", "AbsBias", "HS_P20", "HS_P30", "n"))
    for name, race_e, hisp_m, gen_e in combos:
        fn = make_scenario(race_e, hisp_m, gen_e)
        m = evaluate(perm_recs, fn)
        hs = hs_tail(perm_recs, fn)
        if m:
            print("%-25s  %-7.3f %-7.3f %-7.3f %-6.1f%% %-6.1f%% %-7.3f  %-6.1f%%  %-6.1f%%  %d" % (
                name, m["race"], m["hisp"], m["gender"],
                m["p20"], m["p30"], m["abs_bias"], hs["p20"], hs["p30"], m["n"]))

    # POST-CALIBRATION
    print("\nEXPERT COMBINATION COMPARISON -- POST-CALIBRATION d=0.5 (Perm 1,000)")
    print("=" * 120)
    print("%-25s  %-7s %-7s %-7s %-7s %-7s %-7s %-8s %-8s %s" % (
        "Combo", "Race", "Hisp", "Gender", "P>20", "P>30", "AbsBias", "HS_P20", "HS_P30", "n"))
    for name, race_e, hisp_m, gen_e in combos:
        fn = make_scenario(race_e, hisp_m, gen_e)
        offsets = train_cal(train_recs, fn)

        def cal_fn(rec, _fn=fn, _off=offsets):
            pred = _fn(rec)
            if not pred:
                return None
            return apply_cal(pred, rec, _off)

        m = evaluate(perm_recs, cal_fn)
        hs = hs_tail(perm_recs, cal_fn)
        if m:
            print("%-25s  %-7.3f %-7.3f %-7.3f %-6.1f%% %-6.1f%% %-7.3f  %-6.1f%%  %-6.1f%%  %d" % (
                name, m["race"], m["hisp"], m["gender"],
                m["p20"], m["p30"], m["abs_bias"], hs["p20"], hs["p30"], m["n"]))

    # 7/7 ACCEPTANCE for promising combos
    print("\n7/7 ACCEPTANCE CHECK (post-cal, Perm 1,000)")
    print("=" * 80)
    for name, race_e, hisp_m, gen_e in combos:
        if hisp_m != "new":
            continue
        fn = make_scenario(race_e, hisp_m, gen_e)
        offsets = train_cal(train_recs, fn)

        def cal_fn(rec, _fn=fn, _off=offsets):
            pred = _fn(rec)
            if not pred:
                return None
            return apply_cal(pred, rec, _off)

        m = evaluate(perm_recs, cal_fn)
        hs = hs_tail(perm_recs, cal_fn)
        if not m:
            continue
        checks = {
            "race_mae": (m["race"], 4.50, m["race"] < 4.50),
            "hisp_mae": (m["hisp"], 8.00, m["hisp"] < 8.00),
            "gender":   (m["gender"], 12.00, m["gender"] < 12.00),
            "abs_bias": (m["abs_bias"], 1.10, m["abs_bias"] < 1.10),
            "p_gt_20":  (m["p20"], 16.0, m["p20"] < 16.0),
            "p_gt_30":  (m["p30"], 6.0, m["p30"] < 6.0),
            "hs_tail":  (hs["p20"], 15.0, hs["p20"] < 15.0),
        }
        passed = sum(1 for _, _, p in checks.values() if p)
        print("\n  %s: %d/7" % (name, passed))
        for k, (v, t, ok) in checks.items():
            print("    %-10s  %.3f  target <%.2f  %s" % (k, v, t, "PASS" if ok else "FAIL"))

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
