"""V11 Full Results Report: breakdowns by race category, gender, industry, size, geography."""
import json
import os
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(__file__)
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def load_predictions():
    path = os.path.join(SCRIPT_DIR, "v11_kfold_predictions.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def safe_abs(a, b):
    if a is None or b is None:
        return None
    return abs(a - b)


def compute_race_breakdown(preds):
    """Per-race-category MAE and signed bias."""
    cat_errors = {c: [] for c in RACE_CATS}
    cat_biases = {c: [] for c in RACE_CATS}
    for p in preds:
        pr = p.get("pred_race")
        tr = p.get("truth_race")
        if not pr or not tr:
            continue
        for c in RACE_CATS:
            if c in pr and c in tr:
                cat_errors[c].append(abs(pr[c] - tr[c]))
                cat_biases[c].append(pr[c] - tr[c])
    return cat_errors, cat_biases


def compute_gender_breakdown(preds):
    """Gender MAE and signed bias for Male and Female."""
    errors = {"Male": [], "Female": []}
    biases = {"Male": [], "Female": []}
    for p in preds:
        pg = p.get("pred_gender")
        tg = p.get("truth_gender")
        if not pg or not tg:
            continue
        for g in ["Male", "Female"]:
            if g in pg and g in tg:
                errors[g].append(abs(pg[g] - tg[g]))
                biases[g].append(pg[g] - tg[g])
    return errors, biases


def compute_hispanic_breakdown(preds):
    """Hispanic MAE and signed bias."""
    errors = []
    biases = []
    for p in preds:
        ph = p.get("pred_hispanic")
        th = p.get("truth_hispanic")
        if not ph or not th:
            continue
        if "Hispanic" in ph and "Hispanic" in th:
            errors.append(abs(ph["Hispanic"] - th["Hispanic"]))
            biases.append(ph["Hispanic"] - th["Hispanic"])
    return errors, biases


def mean(vals):
    return sum(vals) / len(vals) if vals else 0


def median(vals):
    if not vals:
        return 0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2
    return s[n // 2]


def pct_over(vals, threshold):
    if not vals:
        return 0
    return sum(1 for v in vals if v > threshold) / len(vals) * 100


def group_metrics(preds, group_key):
    """Compute metrics grouped by a key."""
    groups = defaultdict(list)
    for p in preds:
        groups[p.get(group_key, "Unknown")].append(p)
    return groups


def compute_full_metrics(preds):
    """Full metrics for a list of prediction dicts."""
    race_maes = []
    max_errors = []
    hisp_maes = []
    gender_maes = []
    for p in preds:
        rm = p.get("race_mae")
        if rm is not None:
            race_maes.append(rm)
        me = p.get("max_error")
        if me is not None:
            max_errors.append(me)
        hm = p.get("hisp_mae")
        if hm is not None:
            hisp_maes.append(hm)
        gm = p.get("gender_mae")
        if gm is not None:
            gender_maes.append(gm)
    n = len(race_maes)
    if not n:
        return None
    return {
        "n": n,
        "race_mae": mean(race_maes),
        "race_median": median(race_maes),
        "hisp_mae": mean(hisp_maes) if hisp_maes else 0,
        "gender_mae": mean(gender_maes) if gender_maes else 0,
        "p20": pct_over(max_errors, 20),
        "p30": pct_over(max_errors, 30),
        "p10": pct_over(max_errors, 10),
    }


def classify_size(total):
    if total is None or total == 0:
        return "Unknown"
    if total < 100:
        return "1-99"
    if total < 500:
        return "100-499"
    if total < 1000:
        return "500-999"
    if total < 5000:
        return "1,000-4,999"
    if total < 10000:
        return "5,000-9,999"
    return "10,000+"


def main():
    data = load_predictions()
    preds = data["predictions"]
    agg = data.get("aggregate_v11_oos", {})

    print("V11 FULL RESULTS REPORT")
    print("=" * 90)
    print("  Model: V11 (Bayesian shrinkage + per-tier dampening)")
    print("  Method: 5-fold stratified CV, all out-of-sample")
    print("  Companies: %d" % len(preds))
    print()

    # ================================================================
    # 1. AGGREGATE
    # ================================================================
    print("=" * 90)
    print("1. AGGREGATE METRICS")
    print("=" * 90)
    m = compute_full_metrics(preds)
    if m:
        print("  Race MAE:       %.3f (median: %.3f)" % (m["race_mae"], m["race_median"]))
        print("  Hispanic MAE:   %.3f" % m["hisp_mae"])
        print("  Gender MAE:     %.3f" % m["gender_mae"])
        print("  P>10pp:         %.1f%%" % m["p10"])
        print("  P>20pp:         %.1f%%" % m["p20"])
        print("  P>30pp:         %.1f%%" % m["p30"])
    print()

    # ================================================================
    # 2. PER RACE CATEGORY
    # ================================================================
    print("=" * 90)
    print("2. PER RACE CATEGORY (absolute error and signed bias)")
    print("=" * 90)
    cat_errors, cat_biases = compute_race_breakdown(preds)
    print("  %-8s %6s  %8s  %8s  %8s  %8s  %8s" % (
        "Category", "N", "MAE", "Median", "Bias", "P>10pp", "P>20pp"))
    print("  " + "-" * 68)
    for c in RACE_CATS:
        errs = cat_errors[c]
        bias = cat_biases[c]
        if errs:
            print("  %-8s %6d  %8.3f  %8.3f  %+8.3f  %7.1f%%  %7.1f%%" % (
                c, len(errs), mean(errs), median(errs), mean(bias),
                pct_over(errs, 10), pct_over(errs, 20)))

    print()
    print("  Interpretation:")
    print("  - Positive bias = model OVERESTIMATES that category")
    print("  - Negative bias = model UNDERESTIMATES that category")
    print()

    # ================================================================
    # 3. HISPANIC
    # ================================================================
    print("=" * 90)
    print("3. HISPANIC ESTIMATION")
    print("=" * 90)
    h_errs, h_biases = compute_hispanic_breakdown(preds)
    if h_errs:
        print("  N:       %d" % len(h_errs))
        print("  MAE:     %.3f" % mean(h_errs))
        print("  Median:  %.3f" % median(h_errs))
        print("  Bias:    %+.3f (positive = overestimates Hispanic %%)" % mean(h_biases))
        print("  P>10pp:  %.1f%%" % pct_over(h_errs, 10))
        print("  P>20pp:  %.1f%%" % pct_over(h_errs, 20))

        # Hispanic by county Hispanic concentration
        print()
        print("  Hispanic MAE by county Hispanic concentration:")
        hisp_tiers = defaultdict(list)
        for p in preds:
            ph = p.get("pred_hispanic")
            th = p.get("truth_hispanic")
            if not ph or not th or "Hispanic" not in ph or "Hispanic" not in th:
                continue
            # Use truth Hispanic to bucket
            actual_h = th["Hispanic"]
            if actual_h < 10:
                tier = "<10% Hispanic"
            elif actual_h < 25:
                tier = "10-25% Hispanic"
            elif actual_h < 50:
                tier = "25-50% Hispanic"
            else:
                tier = "50%+ Hispanic"
            hisp_tiers[tier].append(abs(ph["Hispanic"] - th["Hispanic"]))
        print("  %-20s %6s  %8s  %8s" % ("Actual Hispanic %", "N", "MAE", "Median"))
        print("  " + "-" * 46)
        for tier in ["<10% Hispanic", "10-25% Hispanic", "25-50% Hispanic", "50%+ Hispanic"]:
            errs = hisp_tiers.get(tier, [])
            if errs:
                print("  %-20s %6d  %8.3f  %8.3f" % (tier, len(errs), mean(errs), median(errs)))
    print()

    # ================================================================
    # 4. GENDER
    # ================================================================
    print("=" * 90)
    print("4. GENDER ESTIMATION")
    print("=" * 90)
    g_errs, g_biases = compute_gender_breakdown(preds)
    for g in ["Male", "Female"]:
        errs = g_errs[g]
        bias = g_biases[g]
        if errs:
            print("  %s:" % g)
            print("    MAE:     %.3f (median: %.3f)" % (mean(errs), median(errs)))
            print("    Bias:    %+.3f" % mean(bias))
            print("    P>10pp:  %.1f%%  P>20pp: %.1f%%  P>30pp: %.1f%%" % (
                pct_over(errs, 10), pct_over(errs, 20), pct_over(errs, 30)))

    # Gender by actual female %
    print()
    print("  Gender MAE by actual female %%:")
    gender_tiers = defaultdict(list)
    for p in preds:
        pg = p.get("pred_gender")
        tg = p.get("truth_gender")
        if not pg or not tg or "Female" not in pg or "Female" not in tg:
            continue
        actual_f = tg["Female"]
        if actual_f < 20:
            tier = "<20% Female"
        elif actual_f < 40:
            tier = "20-40% Female"
        elif actual_f < 60:
            tier = "40-60% Female"
        elif actual_f < 80:
            tier = "60-80% Female"
        else:
            tier = "80%+ Female"
        gender_tiers[tier].append(abs(pg["Female"] - tg["Female"]))
    print("  %-20s %6s  %8s  %8s" % ("Actual Female %", "N", "MAE", "Median"))
    print("  " + "-" * 46)
    for tier in ["<20% Female", "20-40% Female", "40-60% Female", "60-80% Female", "80%+ Female"]:
        errs = gender_tiers.get(tier, [])
        if errs:
            print("  %-20s %6d  %8.3f  %8.3f" % (tier, len(errs), mean(errs), median(errs)))
    print()

    # ================================================================
    # 5. BY INDUSTRY (NAICS GROUP)
    # ================================================================
    print("=" * 90)
    print("5. BY INDUSTRY (NAICS GROUP)")
    print("=" * 90)
    industry_groups = group_metrics(preds, "naics_group")
    print("  %-45s %5s  %7s  %7s  %7s  %6s  %6s" % (
        "Industry", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    print("  " + "-" * 90)
    for sector, sp in sorted(industry_groups.items(), key=lambda x: -len(x[1])):
        m = compute_full_metrics(sp)
        if m and m["n"] >= 10:
            print("  %-45s %5d  %7.3f  %7.3f  %7.3f  %5.1f%%  %5.1f%%" % (
                sector[:45], m["n"], m["race_mae"], m["hisp_mae"],
                m["gender_mae"], m["p20"], m["p30"]))

    # Per-industry race category breakdown
    print()
    print("  Per-industry RACE CATEGORY MAE (top sectors):")
    print("  %-35s %5s  %7s  %7s  %7s  %7s  %7s  %7s" % (
        "Industry", "N", "White", "Black", "Asian", "AIAN", "NHOPI", "Two+"))
    print("  " + "-" * 95)
    for sector, sp in sorted(industry_groups.items(), key=lambda x: -len(x[1])):
        if len(sp) < 50:
            continue
        cat_e = {c: [] for c in RACE_CATS}
        for p in sp:
            pr = p.get("pred_race")
            tr = p.get("truth_race")
            if not pr or not tr:
                continue
            for c in RACE_CATS:
                if c in pr and c in tr:
                    cat_e[c].append(abs(pr[c] - tr[c]))
        n = len(cat_e["White"])
        if n >= 50:
            print("  %-35s %5d  %7.2f  %7.2f  %7.2f  %7.2f  %7.2f  %7.2f" % (
                sector[:35], n,
                mean(cat_e["White"]), mean(cat_e["Black"]),
                mean(cat_e["Asian"]), mean(cat_e["AIAN"]),
                mean(cat_e["NHOPI"]), mean(cat_e["Two+"])))
    print()

    # ================================================================
    # 6. BY FIRM SIZE
    # ================================================================
    print("=" * 90)
    print("6. BY FIRM SIZE")
    print("=" * 90)
    # Add size classification
    for p in preds:
        p["size_bucket"] = classify_size(p.get("total_employees"))
    size_groups = group_metrics(preds, "size_bucket")
    print("  %-15s %5s  %7s  %7s  %7s  %6s  %6s" % (
        "Size", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    print("  " + "-" * 62)
    for size in ["1-99", "100-499", "500-999", "1,000-4,999", "5,000-9,999", "10,000+", "Unknown"]:
        sp = size_groups.get(size, [])
        m = compute_full_metrics(sp)
        if m and m["n"] >= 10:
            print("  %-15s %5d  %7.3f  %7.3f  %7.3f  %5.1f%%  %5.1f%%" % (
                size, m["n"], m["race_mae"], m["hisp_mae"],
                m["gender_mae"], m["p20"], m["p30"]))
    print()

    # ================================================================
    # 7. BY REGION
    # ================================================================
    print("=" * 90)
    print("7. BY REGION")
    print("=" * 90)
    region_groups = group_metrics(preds, "region")
    print("  %-15s %5s  %7s  %7s  %7s  %6s  %6s" % (
        "Region", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    print("  " + "-" * 62)
    for region in ["South", "West", "Northeast", "Midwest"]:
        sp = region_groups.get(region, [])
        m = compute_full_metrics(sp)
        if m:
            print("  %-15s %5d  %7.3f  %7.3f  %7.3f  %5.1f%%  %5.1f%%" % (
                region, m["n"], m["race_mae"], m["hisp_mae"],
                m["gender_mae"], m["p20"], m["p30"]))

    # Per-region race category breakdown
    print()
    print("  Per-region RACE CATEGORY MAE:")
    print("  %-15s %5s  %7s  %7s  %7s  %7s  %7s  %7s" % (
        "Region", "N", "White", "Black", "Asian", "AIAN", "NHOPI", "Two+"))
    print("  " + "-" * 70)
    for region in ["South", "West", "Northeast", "Midwest"]:
        sp = region_groups.get(region, [])
        cat_e = {c: [] for c in RACE_CATS}
        for p in sp:
            pr = p.get("pred_race")
            tr = p.get("truth_race")
            if not pr or not tr:
                continue
            for c in RACE_CATS:
                if c in pr and c in tr:
                    cat_e[c].append(abs(pr[c] - tr[c]))
        n = len(cat_e["White"])
        if n:
            print("  %-15s %5d  %7.2f  %7.2f  %7.2f  %7.2f  %7.2f  %7.2f" % (
                region, n,
                mean(cat_e["White"]), mean(cat_e["Black"]),
                mean(cat_e["Asian"]), mean(cat_e["AIAN"]),
                mean(cat_e["NHOPI"]), mean(cat_e["Two+"])))
    print()

    # ================================================================
    # 8. BY DIVERSITY TIER
    # ================================================================
    print("=" * 90)
    print("8. BY DIVERSITY TIER (county minority %)")
    print("=" * 90)
    tier_groups = group_metrics(preds, "diversity_tier")
    print("  %-15s %5s  %7s  %7s  %7s  %6s  %6s" % (
        "Tier", "N", "Race", "Hisp", "Gender", "P>20", "P>30"))
    print("  " + "-" * 62)
    for tier in ["Low", "Med-Low", "Med-High", "High"]:
        sp = tier_groups.get(tier, [])
        m = compute_full_metrics(sp)
        if m:
            print("  %-15s %5d  %7.3f  %7.3f  %7.3f  %5.1f%%  %5.1f%%" % (
                tier, m["n"], m["race_mae"], m["hisp_mae"],
                m["gender_mae"], m["p20"], m["p30"]))
    print()

    # ================================================================
    # 9. WORST CASES
    # ================================================================
    print("=" * 90)
    print("9. ERROR DISTRIBUTION")
    print("=" * 90)
    race_maes = [p["race_mae"] for p in preds if p.get("race_mae") is not None]
    max_errors = [p["max_error"] for p in preds if p.get("max_error") is not None]
    hisp_maes = [p["hisp_mae"] for p in preds if p.get("hisp_mae") is not None]
    gender_maes = [p["gender_mae"] for p in preds if p.get("gender_mae") is not None]

    print("  Race MAE distribution:")
    for threshold in [2, 3, 4, 5, 7, 10, 15, 20]:
        pct = sum(1 for v in race_maes if v <= threshold) / len(race_maes) * 100
        print("    <= %2dpp: %5.1f%% (%d companies)" % (
            threshold, pct, sum(1 for v in race_maes if v <= threshold)))

    print()
    print("  Max single-category error distribution:")
    for threshold in [5, 10, 15, 20, 30, 40, 50]:
        pct = sum(1 for v in max_errors if v <= threshold) / len(max_errors) * 100
        print("    <= %2dpp: %5.1f%% (%d companies)" % (
            threshold, pct, sum(1 for v in max_errors if v <= threshold)))

    print()
    print("  Gender MAE distribution:")
    for threshold in [3, 5, 7, 10, 15, 20, 30]:
        pct = sum(1 for v in gender_maes if v <= threshold) / len(gender_maes) * 100
        print("    <= %2dpp: %5.1f%% (%d companies)" % (
            threshold, pct, sum(1 for v in gender_maes if v <= threshold)))

    print()
    print("  Hispanic MAE distribution:")
    for threshold in [2, 5, 7, 10, 15, 20, 30]:
        pct = sum(1 for v in hisp_maes if v <= threshold) / len(hisp_maes) * 100
        print("    <= %2dpp: %5.1f%% (%d companies)" % (
            threshold, pct, sum(1 for v in hisp_maes if v <= threshold)))

    print()

    # ================================================================
    # 10. REGION x INDUSTRY HEATMAP (Race MAE)
    # ================================================================
    print("=" * 90)
    print("10. REGION x INDUSTRY (Race MAE, min 20 companies)")
    print("=" * 90)
    # Build cross-tab
    sectors_ordered = [s for s, sp in sorted(industry_groups.items(), key=lambda x: -len(x[1]))
                       if len(sp) >= 100][:12]
    regions = ["South", "West", "Northeast", "Midwest"]

    header = "  %-30s" % ""
    for r in regions:
        header += " %10s" % r[:10]
    print(header)
    print("  " + "-" * (30 + 11 * len(regions)))

    for sector in sectors_ordered:
        row = "  %-30s" % sector[:30]
        for region in regions:
            subset = [p for p in preds
                      if p.get("naics_group") == sector and p.get("region") == region]
            m = compute_full_metrics(subset)
            if m and m["n"] >= 20:
                row += " %9.2f" % m["race_mae"]
            else:
                row += "        --"
        print(row)

    print()
    print("=" * 90)
    print("END OF REPORT")
    print("=" * 90)


if __name__ == "__main__":
    main()
