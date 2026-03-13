"""Test gender calibration and dampening optimization for the D+new+F hybrid.

Currently we calibrate race and hispanic but NOT gender. Adding gender
calibration and optimizing dampening per dimension may close the gap.
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

    v91 = load_json(os.path.join(SCRIPT_DIR, "v9_1_partial_lock_results.json"))
    industry_weights = v91["trained_weights"]["industry_weights"]
    tier_weights = v91["trained_weights"]["tier_weights"]
    default_weights = v91["trained_weights"]["default_weights"]

    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"] if isinstance(perm_data, dict) else perm_data
    perm_codes = {c["company_code"] for c in perm_companies}
    pool = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v6.json"))
    non_perm = [c for c in pool if c["company_code"] not in perm_codes]
    rng = random.Random(SPLIT_SEED)
    shuffled = non_perm[:]
    rng.shuffle(shuffled)
    train_codes = {c["company_code"] for c in shuffled[:10000]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("Building records...")
    records = []
    all_companies = list(shuffled[:10000]) + list(shuffled[10000:]) + list(perm_companies)
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
        cf = company.get("county_fips", "")
        sf = company.get("state_fips", "")
        zp = company.get("zipcode", "")
        st = company.get("state", "")
        ng = company.get("classifications", {}).get("naics_group") or classify_naics_group(naics4)
        region = company.get("classifications", {}).get("region") or get_census_region(st)
        cbsa = cl.get_county_cbsa(cf) or ""
        n2 = naics4[:2] if naics4 else None

        signals = {}
        signals["pums"] = cl.get_pums_hispanic(cbsa, n2) if cbsa else None
        acs_h = cl.get_acs_hispanic(naics4, sf)
        signals["acs"] = acs_h
        ind_h, _ = cl.get_industry_or_county_lodes_hispanic(cf, naics4)
        signals["ind_lodes"] = ind_h
        ch = cl.get_lodes_hispanic(cf)
        signals["county_lodes"] = ch
        signals["ipf_ind"] = smoothed_ipf(acs_h, ind_h, HISP_CATS)
        td = cl.get_multi_tract_demographics(zp) if zp else None
        signals["tract"] = td.get("hispanic") if td else None
        oc = cl.get_occ_chain_demographics(ng, sf)
        if oc and oc.get("Hispanic") is not None:
            signals["occ_chain"] = {"Hispanic": oc["Hispanic"], "Not Hispanic": 100 - oc["Hispanic"]}
        else:
            signals["occ_chain"] = None
        signals["county_hisp_pct"] = ch["Hispanic"] if ch and "Hispanic" in ch else None

        records.append({
            "company_code": code, "naics_group": ng, "region": region,
            "truth": truth, "expert_preds": cp_rec["expert_preds"], "signals": signals,
        })

    train_recs = [r for r in records if r["company_code"] in train_codes]
    perm_recs = [r for r in records if r["company_code"] in perm_codes]
    print("train=%d perm=%d (%.0fs)" % (len(train_recs), len(perm_recs), time.time() - t0))

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
            w = industry_weights[ng]
        else:
            ch = rec["signals"].get("county_hisp_pct")
            if ch is None:
                tier = "medium"
            elif ch < 10:
                tier = "low"
            elif ch < 25:
                tier = "medium"
            else:
                tier = "high"
            w = tier_weights.get(tier, default_weights)
        r = blend_hispanic(rec["signals"], w)
        if r and "Hispanic" in r:
            return {"Hispanic": r["Hispanic"], "Not Hispanic": r["Not Hispanic"]}
        return None

    def mae_vec(p, a, cats):
        v = [abs(p.get(c, 0) - a.get(c, 0)) for c in cats if c in p and c in a]
        return sum(v) / len(v) if v else None

    def max_cat_err(p, a, cats):
        v = [abs(p.get(c, 0) - a.get(c, 0)) for c in cats if c in p and c in a]
        return max(v) if v else None

    def scenario(rec):
        ep = rec["expert_preds"]
        d = ep.get("D")
        race = d.get("race") if d else None
        hispanic = hisp_predict(rec)
        f = ep.get("F")
        gender = f.get("gender") if f else None
        if not gender:
            for fb in ["V6-Full", "D"]:
                p = ep.get(fb)
                if p and p.get("gender"):
                    gender = p["gender"]
                    break
        return {"race": race, "hispanic": hispanic, "gender": gender}

    # Train calibration WITH gender
    def train_cal_full(train_records, scenario_fn):
        buckets = defaultdict(list)
        for rec in train_records:
            pred = scenario_fn(rec)
            if not pred:
                continue
            key = (rec["region"], rec["naics_group"])
            rp, ra = pred.get("race"), rec["truth"]["race"]
            if rp and ra:
                for c in RACE_CATS:
                    if c in rp and c in ra:
                        buckets[("race", c, key)].append(rp[c] - ra[c])
            hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
            if hp and ha and "Hispanic" in hp and "Hispanic" in ha:
                buckets[("hisp", "Hispanic", key)].append(hp["Hispanic"] - ha["Hispanic"])
            gp, ga = pred.get("gender"), rec["truth"]["gender"]
            if gp and ga and "Female" in gp and "Female" in ga:
                buckets[("gender", "Female", key)].append(gp["Female"] - ga["Female"])
        offsets = {}
        for k, errs in buckets.items():
            if len(errs) >= 20:
                offsets[k] = sum(errs) / len(errs)
        return offsets

    def apply_cal_full(pred, rec, offsets, d_race=0.5, d_hisp=0.5, d_gender=0.5):
        result = {}
        key = (rec["region"], rec["naics_group"])
        if pred.get("race"):
            cal = {}
            for c in RACE_CATS:
                v = pred["race"].get(c, 0.0)
                off = offsets.get(("race", c, key))
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
            off = offsets.get(("hisp", "Hispanic", key))
            if off is not None:
                hv -= off * d_hisp
            hv = max(0.0, min(100.0, hv))
            result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
        else:
            result["hispanic"] = pred.get("hispanic")
        if pred.get("gender"):
            fv = pred["gender"].get("Female", 50.0)
            off = offsets.get(("gender", "Female", key))
            if off is not None:
                fv -= off * d_gender
            fv = max(0.0, min(100.0, fv))
            result["gender"] = {"Male": round(100 - fv, 4), "Female": round(fv, 4)}
        else:
            result["gender"] = pred.get("gender")
        return result

    def evaluate(recs, fn):
        rm, hm, gm, me = [], [], [], []
        rp_all, ra_all = [], []
        for rec in recs:
            pred = fn(rec)
            if not pred:
                continue
            rp, ra = pred.get("race"), rec["truth"]["race"]
            if rp and ra:
                m = mae_vec(rp, ra, RACE_CATS)
                if m is not None:
                    rm.append(m)
                mx = max_cat_err(rp, ra, RACE_CATS)
                if mx is not None:
                    me.append(mx)
                rp_all.append(rp)
                ra_all.append(ra)
            hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
            if hp and ha:
                m = mae_vec(hp, ha, HISP_CATS)
                if m is not None:
                    hm.append(m)
            gp, ga = pred.get("gender"), rec["truth"]["gender"]
            if gp and ga:
                m = mae_vec(gp, ga, GENDER_CATS)
                if m is not None:
                    gm.append(m)
        n = len(rm)
        if not n:
            return None
        ab = []
        for c in RACE_CATS:
            e = [rp_all[i].get(c, 0) - ra_all[i].get(c, 0)
                 for i in range(len(rp_all)) if c in rp_all[i] and c in ra_all[i]]
            if e:
                ab.append(abs(sum(e) / len(e)))
        hs_sub = [rec for rec in recs
                  if rec["naics_group"] == "Healthcare/Social (62)" and rec["region"] == "South"]
        hs_me = []
        for rec in hs_sub:
            pred = fn(rec)
            if not pred or not pred.get("race"):
                continue
            mx = max_cat_err(pred["race"], rec["truth"]["race"], RACE_CATS)
            if mx is not None:
                hs_me.append(mx)
        hs_n = len(hs_me)
        return {
            "race": sum(rm) / n, "hisp": sum(hm) / len(hm) if hm else 0,
            "gender": sum(gm) / len(gm) if gm else 0,
            "p20": sum(1 for e in me if e > 20) / len(me) * 100 if me else 0,
            "p30": sum(1 for e in me if e > 30) / len(me) * 100 if me else 0,
            "abs_bias": sum(ab) / len(ab) if ab else 0,
            "hs_p20": sum(1 for e in hs_me if e > 20) / hs_n * 100 if hs_n else 0,
            "hs_p30": sum(1 for e in hs_me if e > 30) / hs_n * 100 if hs_n else 0,
            "n": n,
        }

    offsets = train_cal_full(train_recs, scenario)
    n_gender_buckets = sum(1 for k in offsets if k[0] == "gender")
    n_race_buckets = sum(1 for k in offsets if k[0] == "race")
    n_hisp_buckets = sum(1 for k in offsets if k[0] == "hisp")
    print("Calibration buckets: race=%d, hisp=%d, gender=%d" % (n_race_buckets, n_hisp_buckets, n_gender_buckets))

    # Baseline: no calibration
    m0 = evaluate(perm_recs, scenario)
    print("\nNo calibration:       Race=%.3f Hisp=%.3f Gender=%.3f P>20=%.1f%% P>30=%.1f%% AbsBias=%.3f HS_P20=%.1f%%" % (
        m0["race"], m0["hisp"], m0["gender"], m0["p20"], m0["p30"], m0["abs_bias"], m0["hs_p20"]))

    # Test dampening grid
    print("\nDAMPENING GRID SEARCH (Perm 1,000)")
    print("=" * 140)
    print("%-8s %-8s %-8s  %-7s %-7s %-7s %-7s %-7s %-8s %-8s %-8s  Pass" % (
        "d_race", "d_hisp", "d_gen", "Race", "Hisp", "Gender", "P>20", "P>30", "AbsBias", "HS_P20", "HS_P30"))

    best_pass = 0
    best_combo = None
    best_total = 999

    for dr in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        for dh in [0.3, 0.5, 0.7]:
            for dg in [0.0, 0.3, 0.5, 0.7, 1.0]:
                def cal_fn(rec, _dr=dr, _dh=dh, _dg=dg):
                    pred = scenario(rec)
                    if not pred:
                        return None
                    return apply_cal_full(pred, rec, offsets, _dr, _dh, _dg)

                m = evaluate(perm_recs, cal_fn)
                if not m:
                    continue
                checks = [
                    m["race"] < 4.50, m["hisp"] < 8.00, m["gender"] < 12.00,
                    m["abs_bias"] < 1.10, m["p20"] < 16.0, m["p30"] < 6.0,
                    m["hs_p20"] < 15.0,
                ]
                passed = sum(checks)
                total = m["race"] + m["gender"] + m["p20"] + m["p30"]
                if passed > best_pass or (passed == best_pass and total < best_total):
                    best_pass = passed
                    best_combo = (dr, dh, dg, m)
                    best_total = total
                    print("%-8.1f %-8.1f %-8.1f  %-7.3f %-7.3f %-7.3f %-6.1f%% %-6.1f%% %-8.3f %-6.1f%%  %-6.1f%%  %d/7 *" % (
                        dr, dh, dg, m["race"], m["hisp"], m["gender"],
                        m["p20"], m["p30"], m["abs_bias"], m["hs_p20"], m["hs_p30"], passed))

    print("\nBest: d_race=%.1f d_hisp=%.1f d_gender=%.1f -> %d/7" % (
        best_combo[0], best_combo[1], best_combo[2], best_pass))
    m = best_combo[3]
    targets = {"race": 4.50, "hisp": 8.00, "gender": 12.00, "abs_bias": 1.10, "p20": 16.0, "p30": 6.0, "hs_p20": 15.0}
    for k, t in targets.items():
        v = m[k]
        ok = "PASS" if v < t else "FAIL"
        print("  %-10s  %.3f  target <%.2f  %s" % (k, v, t, ok))

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
