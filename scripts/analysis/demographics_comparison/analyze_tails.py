"""Analyze the distribution of tail errors (P>20pp, P>30pp) by every dimension.

Uses the best V9.1 hybrid: D race + industry+adaptive Hispanic + F gender,
calibrated at d_race=0.8, d_hisp=0.3, d_gender=1.0.
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

    # Build company lookup for size info
    company_lookup = {}
    all_companies = list(shuffled[:10000]) + list(shuffled[10000:]) + list(perm_companies)
    for c in all_companies:
        company_lookup[c["company_code"]] = c

    print("Building records...")
    records = []
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

        # Get employee count from truth
        total_employees = truth.get("total_employees", 0)

        # County minority %
        lodes_race = cl.get_lodes_race(cf)
        county_minority_pct = (100.0 - lodes_race.get("White", 0.0)) if lodes_race else None

        records.append({
            "company_code": code, "naics_group": ng, "region": region,
            "state": st, "county_fips": cf, "naics4": naics4,
            "truth": truth, "expert_preds": cp_rec["expert_preds"],
            "signals": signals, "total_employees": total_employees,
            "county_minority_pct": county_minority_pct,
        })

    train_recs = [r for r in records if r["company_code"] in train_codes]
    perm_recs = [r for r in records if r["company_code"] in perm_codes]
    all_holdout = [r for r in records if r["company_code"] not in train_codes]
    print("train=%d perm=%d all_holdout=%d (%.0fs)" % (
        len(train_recs), len(perm_recs), len(all_holdout), time.time() - t0))

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

    # Compute per-record errors
    print("\nComputing per-record errors...")
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

        # Find which category caused the max error
        cat_errors = {}
        worst_cat = None
        worst_err = 0
        for c in RACE_CATS:
            if c in race_pred and c in race_actual:
                e = abs(race_pred[c] - race_actual[c])
                cat_errors[c] = e
                if e > worst_err:
                    worst_err = e
                    worst_cat = c

        # Size bucket
        emp = rec["total_employees"]
        if emp <= 0:
            size_bucket = "unknown"
        elif emp < 100:
            size_bucket = "<100"
        elif emp < 250:
            size_bucket = "100-249"
        elif emp < 500:
            size_bucket = "250-499"
        elif emp < 1000:
            size_bucket = "500-999"
        elif emp < 5000:
            size_bucket = "1000-4999"
        else:
            size_bucket = "5000+"

        # County diversity bucket
        cm = rec["county_minority_pct"]
        if cm is None:
            diversity_bucket = "unknown"
        elif cm < 15:
            diversity_bucket = "<15% minority"
        elif cm < 30:
            diversity_bucket = "15-30% minority"
        elif cm < 50:
            diversity_bucket = "30-50% minority"
        else:
            diversity_bucket = "50%+ minority"

        # NAICS 2-digit
        naics2 = rec["naics4"][:2] if rec["naics4"] else "??"

        error_records.append({
            "company_code": rec["company_code"],
            "max_err": max_err,
            "worst_cat": worst_cat,
            "cat_errors": cat_errors,
            "region": rec["region"],
            "naics_group": rec["naics_group"],
            "state": rec["state"],
            "size_bucket": size_bucket,
            "total_employees": emp,
            "diversity_bucket": diversity_bucket,
            "county_minority_pct": cm,
            "naics2": naics2,
        })

    total = len(error_records)
    gt20 = [r for r in error_records if r["max_err"] > 20]
    gt30 = [r for r in error_records if r["max_err"] > 30]
    print("Total: %d, P>20pp: %d (%.1f%%), P>30pp: %d (%.1f%%)" % (
        total, len(gt20), len(gt20) / total * 100, len(gt30), len(gt30) / total * 100))

    # ================================================================
    # BREAKDOWNS
    # ================================================================
    def print_breakdown(title, key_fn, recs, sort_by_rate=True):
        print("\n" + "=" * 90)
        print(title)
        print("=" * 90)
        buckets = defaultdict(list)
        for r in recs:
            k = key_fn(r)
            buckets[k].append(r)

        rows = []
        for k, items in buckets.items():
            n = len(items)
            n20 = sum(1 for r in items if r["max_err"] > 20)
            n30 = sum(1 for r in items if r["max_err"] > 30)
            avg_err = sum(r["max_err"] for r in items) / n
            median_err = sorted(r["max_err"] for r in items)[n // 2]
            p95_err = sorted(r["max_err"] for r in items)[int(n * 0.95)] if n >= 5 else None
            rows.append((k, n, n20, n30, avg_err, median_err, p95_err))

        if sort_by_rate:
            rows.sort(key=lambda x: x[3] / x[1] if x[1] > 0 else 0, reverse=True)
        else:
            rows.sort(key=lambda x: x[0])

        print("%-35s  %5s  %6s %7s  %6s %7s  %7s %7s %7s" % (
            "Bucket", "n", "n>20", "P>20pp", "n>30", "P>30pp", "AvgMax", "MedMax", "P95Max"))
        for k, n, n20, n30, avg, med, p95 in rows:
            p95_str = "%.1f" % p95 if p95 is not None else "--"
            print("%-35s  %5d  %6d %6.1f%%  %6d %6.1f%%  %7.1f %7.1f %7s" % (
                str(k)[:35], n, n20, n20 / n * 100, n30, n30 / n * 100, avg, med, p95_str))

    # 1. By NAICS group (sector)
    print_breakdown("BY SECTOR (NAICS GROUP)", lambda r: r["naics_group"], error_records)

    # 2. By region
    print_breakdown("BY REGION", lambda r: r["region"], error_records)

    # 3. By region x sector (top problem areas)
    print_breakdown("BY REGION x SECTOR", lambda r: "%s | %s" % (r["region"], r["naics_group"]), error_records)

    # 4. By firm size
    print_breakdown("BY FIRM SIZE", lambda r: r["size_bucket"], error_records, sort_by_rate=False)

    # 5. By county diversity
    print_breakdown("BY COUNTY DIVERSITY", lambda r: r["diversity_bucket"], error_records)

    # 6. By worst category (which race category causes the tail error)
    print_breakdown("BY WORST CATEGORY (which race cat causes max error)", lambda r: r["worst_cat"], error_records)

    # 7. By state (top 15 states by tail rate)
    print("\n" + "=" * 90)
    print("BY STATE (sorted by P>30pp rate, min n=10)")
    print("=" * 90)
    state_buckets = defaultdict(list)
    for r in error_records:
        state_buckets[r["state"]].append(r)
    state_rows = []
    for st, items in state_buckets.items():
        n = len(items)
        if n < 10:
            continue
        n20 = sum(1 for r in items if r["max_err"] > 20)
        n30 = sum(1 for r in items if r["max_err"] > 30)
        avg_err = sum(r["max_err"] for r in items) / n
        state_rows.append((st, n, n20, n30, avg_err))
    state_rows.sort(key=lambda x: x[3] / x[1], reverse=True)
    print("%-6s  %5s  %6s %7s  %6s %7s  %7s" % ("State", "n", "n>20", "P>20pp", "n>30", "P>30pp", "AvgMax"))
    for st, n, n20, n30, avg in state_rows[:20]:
        print("%-6s  %5d  %6d %6.1f%%  %6d %6.1f%%  %7.1f" % (
            st, n, n20, n20 / n * 100, n30, n30 / n * 100, avg))

    # 8. Distribution of max error magnitudes
    print("\n" + "=" * 90)
    print("MAX ERROR DISTRIBUTION (Perm 1,000)")
    print("=" * 90)
    err_vals = sorted(r["max_err"] for r in error_records)
    percentiles = [10, 25, 50, 75, 90, 95, 99]
    for p in percentiles:
        idx = int(len(err_vals) * p / 100)
        idx = min(idx, len(err_vals) - 1)
        print("  P%d: %.1f pp" % (p, err_vals[idx]))
    print("  Mean: %.1f pp" % (sum(err_vals) / len(err_vals)))

    # Histogram
    bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 50), (50, 100)]
    print("\n  Max error histogram:")
    for lo, hi in bins:
        count = sum(1 for e in err_vals if lo <= e < hi)
        bar = "#" * (count // 2)
        print("  %2d-%2d pp: %4d (%5.1f%%)  %s" % (lo, hi, count, count / len(err_vals) * 100, bar))

    # 9. P>30pp deep dive: what do these companies look like?
    print("\n" + "=" * 90)
    print("P>30pp COMPANIES: DEEP DIVE (n=%d)" % len(gt30))
    print("=" * 90)
    gt30_sorted = sorted(gt30, key=lambda r: r["max_err"], reverse=True)
    print("%-12s %-25s %-8s %-8s %-6s %-8s %-35s" % (
        "MaxErr", "WorstCat", "Region", "State", "Emp", "CtyMin%", "Sector"))
    for r in gt30_sorted[:30]:
        print("%-12.1f %-25s %-8s %-8s %-6s %-8s %-35s" % (
            r["max_err"], r["worst_cat"], r["region"], r["state"],
            str(r["total_employees"]) if r["total_employees"] > 0 else "?",
            "%.0f%%" % r["county_minority_pct"] if r["county_minority_pct"] is not None else "?",
            r["naics_group"][:35]))

    # 10. Which category is responsible for the >20pp errors?
    print("\n" + "=" * 90)
    print("WHICH CATEGORY DRIVES >20pp ERRORS?")
    print("=" * 90)
    cat_counts = defaultdict(int)
    cat_total_err = defaultdict(float)
    for r in gt20:
        cat_counts[r["worst_cat"]] += 1
        cat_total_err[r["worst_cat"]] += r["max_err"]
    print("%-10s  %5s  %6s  %8s" % ("Category", "Count", "Share", "AvgErr"))
    for cat in sorted(cat_counts.keys(), key=lambda c: cat_counts[c], reverse=True):
        n = cat_counts[cat]
        print("%-10s  %5d  %5.1f%%  %8.1f" % (
            cat, n, n / len(gt20) * 100, cat_total_err[cat] / n))

    print("\nRuntime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
