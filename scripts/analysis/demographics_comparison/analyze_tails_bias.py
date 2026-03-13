"""Analyze signed bias direction for tail errors by every dimension and race category.

For each bucket (sector, region, county diversity, size, state), shows the
mean signed error per race category: positive = overestimate, negative = underestimate.
Focuses on >20pp and >30pp tail companies.
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

        lodes_race = cl.get_lodes_race(cf)
        county_minority_pct = (100.0 - lodes_race.get("White", 0.0)) if lodes_race else None

        records.append({
            "company_code": code, "naics_group": ng, "region": region,
            "state": st, "county_fips": cf, "naics4": naics4,
            "truth": truth, "expert_preds": cp_rec["expert_preds"],
            "signals": signals, "county_minority_pct": county_minority_pct,
        })

    train_recs = [r for r in records if r["company_code"] in train_codes]
    perm_recs = [r for r in records if r["company_code"] in perm_codes]
    print("train=%d perm=%d (%.0fs)" % (len(train_recs), len(perm_recs), time.time() - t0))

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

    # Train calibration
    def train_cal_full(train_records):
        buckets = defaultdict(list)
        for rec in train_records:
            pred = scenario(rec)
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

    def apply_cal(pred, rec, offsets):
        result = {}
        key = (rec["region"], rec["naics_group"])
        if pred.get("race"):
            cal = {}
            for c in RACE_CATS:
                v = pred["race"].get(c, 0.0)
                off = offsets.get(("race", c, key))
                if off is not None:
                    v -= off * 0.8
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
                hv -= off * 0.3
            hv = max(0.0, min(100.0, hv))
            result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
        else:
            result["hispanic"] = pred.get("hispanic")
        if pred.get("gender"):
            fv = pred["gender"].get("Female", 50.0)
            off = offsets.get(("gender", "Female", key))
            if off is not None:
                fv -= off * 1.0
            fv = max(0.0, min(100.0, fv))
            result["gender"] = {"Male": round(100 - fv, 4), "Female": round(fv, 4)}
        else:
            result["gender"] = pred.get("gender")
        return result

    offsets = train_cal_full(train_recs)

    # Compute per-record signed errors
    print("\nComputing per-record signed errors...")
    error_records = []
    for rec in perm_recs:
        pred_raw = scenario(rec)
        if not pred_raw:
            continue
        pred = apply_cal(pred_raw, rec, offsets)
        if not pred or not pred.get("race"):
            continue

        race_pred = pred["race"]
        race_actual = rec["truth"]["race"]
        max_err = max_cat_err(race_pred, race_actual, RACE_CATS)
        if max_err is None:
            continue

        # Signed errors per category (positive = overestimate)
        signed = {}
        for c in RACE_CATS:
            if c in race_pred and c in race_actual:
                signed[c] = race_pred[c] - race_actual[c]

        # Hispanic signed error
        hisp_signed = None
        hp = pred.get("hispanic")
        ha = rec["truth"].get("hispanic")
        if hp and ha and "Hispanic" in hp and "Hispanic" in ha:
            hisp_signed = hp["Hispanic"] - ha["Hispanic"]

        # Gender signed error
        gender_signed = None
        gp = pred.get("gender")
        ga = rec["truth"].get("gender")
        if gp and ga and "Female" in gp and "Female" in ga:
            gender_signed = gp["Female"] - ga["Female"]

        cm = rec["county_minority_pct"]
        if cm is None:
            div_bucket = "unknown"
        elif cm < 15:
            div_bucket = "<15% minority"
        elif cm < 30:
            div_bucket = "15-30% minority"
        elif cm < 50:
            div_bucket = "30-50% minority"
        else:
            div_bucket = "50%+ minority"

        error_records.append({
            "max_err": max_err,
            "signed": signed,
            "hisp_signed": hisp_signed,
            "gender_signed": gender_signed,
            "region": rec["region"],
            "naics_group": rec["naics_group"],
            "state": rec["state"],
            "diversity_bucket": div_bucket,
        })

    total = len(error_records)
    all_recs = error_records
    gt20 = [r for r in error_records if r["max_err"] > 20]
    gt30 = [r for r in error_records if r["max_err"] > 30]
    le20 = [r for r in error_records if r["max_err"] <= 20]
    print("Total: %d, P>20pp: %d, P>30pp: %d" % (total, len(gt20), len(gt30)))

    # ================================================================
    # BIAS TABLE PRINTER
    # ================================================================
    cats_to_show = RACE_CATS + ["Hispanic", "Female"]

    def get_signed(r, cat):
        if cat == "Hispanic":
            return r["hisp_signed"]
        elif cat == "Female":
            return r["gender_signed"]
        else:
            return r["signed"].get(cat)

    def print_bias_table(title, key_fn, recs, min_n=5):
        print("\n" + "=" * 130)
        print(title)
        print("=" * 130)

        # Header
        header = "%-35s  %5s" % ("Bucket", "n")
        for c in cats_to_show:
            header += "  %8s" % c
        print(header)

        buckets = defaultdict(list)
        for r in recs:
            buckets[key_fn(r)].append(r)

        rows = []
        for k, items in buckets.items():
            n = len(items)
            if n < min_n:
                continue
            biases = {}
            for c in cats_to_show:
                vals = [get_signed(r, c) for r in items if get_signed(r, c) is not None]
                biases[c] = sum(vals) / len(vals) if vals else None
            rows.append((k, n, biases))

        rows.sort(key=lambda x: x[1], reverse=True)

        for k, n, biases in rows:
            line = "%-35s  %5d" % (str(k)[:35], n)
            for c in cats_to_show:
                b = biases[c]
                if b is not None:
                    line += "  %+8.2f" % b
                else:
                    line += "  %8s" % "--"
            print(line)

    # ================================================================
    # ALL COMPANIES
    # ================================================================
    print_bias_table("SIGNED BIAS -- ALL COMPANIES (Perm 1,000)", lambda r: "ALL", all_recs, min_n=1)

    # By tier (all, >20, >30)
    for tier_label, tier_recs in [("ALL", all_recs), (">20pp tail", gt20), (">30pp tail", gt30), ("<=20pp (good)", le20)]:
        print_bias_table(
            "SIGNED BIAS -- %s BY SECTOR" % tier_label,
            lambda r: r["naics_group"], tier_recs)

    for tier_label, tier_recs in [("ALL", all_recs), (">20pp tail", gt20), (">30pp tail", gt30)]:
        print_bias_table(
            "SIGNED BIAS -- %s BY REGION" % tier_label,
            lambda r: r["region"], tier_recs)

    for tier_label, tier_recs in [("ALL", all_recs), (">20pp tail", gt20), (">30pp tail", gt30)]:
        print_bias_table(
            "SIGNED BIAS -- %s BY COUNTY DIVERSITY" % tier_label,
            lambda r: r["diversity_bucket"], tier_recs)

    for tier_label, tier_recs in [("ALL", all_recs), (">20pp tail", gt20)]:
        print_bias_table(
            "SIGNED BIAS -- %s BY STATE (min n=8)" % tier_label,
            lambda r: r["state"], tier_recs, min_n=8)

    # ================================================================
    # OVER vs UNDER: for tail companies, how many over vs under per cat?
    # ================================================================
    print("\n" + "=" * 130)
    print("DIRECTION OF ERROR FOR >20pp TAIL COMPANIES (n=%d)" % len(gt20))
    print("=" * 130)
    print("%-10s  %6s %6s %6s  %8s %8s %8s" % (
        "Category", "Over", "Under", "Total", "AvgOver", "AvgUnder", "NetBias"))
    for c in cats_to_show:
        vals = [get_signed(r, c) for r in gt20 if get_signed(r, c) is not None]
        if not vals:
            continue
        over = [v for v in vals if v > 0]
        under = [v for v in vals if v < 0]
        avg_over = sum(over) / len(over) if over else 0
        avg_under = sum(under) / len(under) if under else 0
        net = sum(vals) / len(vals)
        print("%-10s  %6d %6d %6d  %+8.2f %+8.2f %+8.2f" % (
            c, len(over), len(under), len(vals), avg_over, avg_under, net))

    # Same for >30pp
    print("\n" + "=" * 130)
    print("DIRECTION OF ERROR FOR >30pp TAIL COMPANIES (n=%d)" % len(gt30))
    print("=" * 130)
    print("%-10s  %6s %6s %6s  %8s %8s %8s" % (
        "Category", "Over", "Under", "Total", "AvgOver", "AvgUnder", "NetBias"))
    for c in cats_to_show:
        vals = [get_signed(r, c) for r in gt30 if get_signed(r, c) is not None]
        if not vals:
            continue
        over = [v for v in vals if v > 0]
        under = [v for v in vals if v < 0]
        avg_over = sum(over) / len(over) if over else 0
        avg_under = sum(under) / len(under) if under else 0
        net = sum(vals) / len(vals)
        print("%-10s  %6d %6d %6d  %+8.2f %+8.2f %+8.2f" % (
            c, len(over), len(under), len(vals), avg_over, avg_under, net))

    # ================================================================
    # REGION x SECTOR for >20pp tail
    # ================================================================
    print_bias_table(
        "SIGNED BIAS -- >20pp TAIL BY REGION x SECTOR",
        lambda r: "%s | %s" % (r["region"], r["naics_group"]), gt20, min_n=3)

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
