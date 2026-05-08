"""V12 QWI Detailed Breakdown Analysis.

Compares V10 baseline vs V12 QWI across every dimension:
  - By industry (NAICS group)
  - By geography (region + diversity tier)
  - By company size
  - By race category (per-category MAE and bias)
  - Large error analysis (>10pp, >20pp, >30pp in any single category)
  - QWI coverage impact (exact match vs fallback vs no QWI)

Usage:
    py scripts/analysis/demographics_comparison/v12_detailed_analysis.py
"""
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from config import RACE_CATEGORIES as RACE_CATS

from run_v9_2 import (
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_gender,
    train_calibration_v92, apply_calibration_v92,
)
from run_v10 import (
    build_v10_splits, build_records, load_json, scenario_v92_full,
)
from run_v12_qwi import (
    QWICache, scenario_qwi_replace_acs,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

D_RACE = 0.85
D_HISP = 0.50
D_GENDER = 0.95


def get_size_bucket(total_employees):
    """Classify company by employee count."""
    if total_employees is None or total_employees == 0:
        return "Unknown"
    elif total_employees < 100:
        return "<100"
    elif total_employees < 500:
        return "100-499"
    elif total_employees < 1000:
        return "500-999"
    elif total_employees < 5000:
        return "1K-5K"
    elif total_employees < 10000:
        return "5K-10K"
    elif total_employees < 50000:
        return "10K-50K"
    else:
        return "50K+"


def compute_per_company_errors(records, pred_fn):
    """Compute detailed per-company errors for a prediction function."""
    results = []
    for rec in records:
        pred = pred_fn(rec)
        if not pred:
            continue
        truth = rec["truth"]
        entry = {
            "code": rec["company_code"],
            "name": rec.get("name", ""),
            "naics4": rec["naics4"],
            "naics_group": rec["naics_group"],
            "region": rec["region"],
            "diversity_tier": rec["diversity_tier"],
            "county_fips": rec["county_fips"],
            "state": rec.get("state", ""),
            "total_employees": rec.get("total_employees", 0),
            "size_bucket": get_size_bucket(rec.get("total_employees")),
        }

        # Race errors
        if pred.get("race") and truth.get("race"):
            race_errs = {}
            for cat in RACE_CATS:
                if cat in pred["race"] and cat in truth["race"]:
                    race_errs[cat] = pred["race"][cat] - truth["race"][cat]
            entry["race_errors"] = race_errs
            entry["race_mae"] = sum(abs(v) for v in race_errs.values()) / len(race_errs) if race_errs else None
            entry["race_max_err"] = max(abs(v) for v in race_errs.values()) if race_errs else None
            entry["race_pred"] = pred["race"]
            entry["race_truth"] = truth["race"]

        # Hispanic errors
        if pred.get("hispanic") and truth.get("hispanic"):
            h_pred = pred["hispanic"].get("Hispanic", 0)
            h_truth = truth["hispanic"].get("Hispanic", 0)
            entry["hisp_error"] = h_pred - h_truth
            entry["hisp_mae"] = abs(h_pred - h_truth)

        # Gender errors
        if pred.get("gender") and truth.get("gender"):
            f_pred = pred["gender"].get("Female", 50)
            f_truth = truth["gender"].get("Female", 50)
            entry["gender_error"] = f_pred - f_truth
            entry["gender_mae"] = abs(f_pred - f_truth)

        results.append(entry)
    return results


def print_breakdown(label, v10_errors, v12_errors, group_key):
    """Print side-by-side breakdown by a grouping key."""
    # Group companies
    v10_groups = defaultdict(list)
    v12_groups = defaultdict(list)
    for e in v10_errors:
        v10_groups[e[group_key]].append(e)
    for e in v12_errors:
        v12_groups[e[group_key]].append(e)

    all_keys = sorted(set(list(v10_groups.keys()) + list(v12_groups.keys())))

    print("\n" + "=" * 110)
    print("BREAKDOWN BY %s" % label.upper())
    print("=" * 110)
    print("  %-35s | %4s | %8s %8s %6s | %8s %8s %6s | %8s |" % (
        label, "N", "V10 Race", "V12 Race", "Delta",
        "V10 Hisp", "V12 Hisp", "Delta", "V12 Gend"))
    print("  %s|%s|%s|%s|" % (
        "-" * 37, "-" * 6,
        "-" * 27, "-" * 27, ))

    for key in all_keys:
        v10_list = v10_groups.get(key, [])
        v12_list = v12_groups.get(key, [])
        n = len(v10_list)
        if n < 5:
            continue

        v10_race = [e["race_mae"] for e in v10_list if e.get("race_mae") is not None]
        v12_race = [e["race_mae"] for e in v12_list if e.get("race_mae") is not None]
        v10_hisp = [e["hisp_mae"] for e in v10_list if e.get("hisp_mae") is not None]
        v12_hisp = [e["hisp_mae"] for e in v12_list if e.get("hisp_mae") is not None]
        v12_gend = [e["gender_mae"] for e in v12_list if e.get("gender_mae") is not None]

        v10_r = sum(v10_race) / len(v10_race) if v10_race else 0
        v12_r = sum(v12_race) / len(v12_race) if v12_race else 0
        v10_h = sum(v10_hisp) / len(v10_hisp) if v10_hisp else 0
        v12_h = sum(v12_hisp) / len(v12_hisp) if v12_hisp else 0
        v12_g = sum(v12_gend) / len(v12_gend) if v12_gend else 0

        race_delta = v12_r - v10_r
        hisp_delta = v12_h - v10_h
        race_marker = "**" if race_delta < -0.1 else "++" if race_delta > 0.1 else "  "

        key_str = str(key)[:35]
        print("  %-35s | %4d | %8.3f %8.3f %+5.3f%s | %8.3f %8.3f %+5.3f  | %8.3f |" % (
            key_str, n, v10_r, v12_r, race_delta, race_marker,
            v10_h, v12_h, hisp_delta, v12_g))


def print_per_category_errors(label, v10_errors, v12_errors):
    """Print per-race-category MAE and signed bias."""
    print("\n" + "=" * 110)
    print("PER-CATEGORY RACE ERRORS (%s)" % label)
    print("=" * 110)

    print("\n  %-10s | %8s %8s %6s | %8s %8s %6s | %8s %8s |" % (
        "Category", "V10 MAE", "V12 MAE", "Delta",
        "V10 Bias", "V12 Bias", "Delta",
        "V10 P>10", "V12 P>10"))
    print("  %s|%s|%s|%s|" % (
        "-" * 12, "-" * 27, "-" * 27, "-" * 19))

    for cat in RACE_CATS:
        v10_errs = [e["race_errors"][cat] for e in v10_errors
                    if e.get("race_errors") and cat in e["race_errors"]]
        v12_errs = [e["race_errors"][cat] for e in v12_errors
                    if e.get("race_errors") and cat in e["race_errors"]]

        if not v10_errs or not v12_errs:
            continue

        v10_mae = sum(abs(e) for e in v10_errs) / len(v10_errs)
        v12_mae = sum(abs(e) for e in v12_errs) / len(v12_errs)
        v10_bias = sum(v10_errs) / len(v10_errs)
        v12_bias = sum(v12_errs) / len(v12_errs)
        v10_p10 = 100 * sum(1 for e in v10_errs if abs(e) > 10) / len(v10_errs)
        v12_p10 = 100 * sum(1 for e in v12_errs if abs(e) > 10) / len(v12_errs)

        mae_delta = v12_mae - v10_mae
        bias_delta = v12_bias - v10_bias

        print("  %-10s | %8.3f %8.3f %+5.3f  | %+8.3f %+8.3f %+5.3f  | %7.1f%% %7.1f%% |" % (
            cat, v10_mae, v12_mae, mae_delta,
            v10_bias, v12_bias, bias_delta,
            v10_p10, v12_p10))

    # Hispanic
    v10_hisp = [e["hisp_error"] for e in v10_errors if e.get("hisp_error") is not None]
    v12_hisp = [e["hisp_error"] for e in v12_errors if e.get("hisp_error") is not None]
    if v10_hisp and v12_hisp:
        print("  %-10s | %8.3f %8.3f %+5.3f  | %+8.3f %+8.3f %+5.3f  | %7.1f%% %7.1f%% |" % (
            "Hispanic",
            sum(abs(e) for e in v10_hisp) / len(v10_hisp),
            sum(abs(e) for e in v12_hisp) / len(v12_hisp),
            sum(abs(e) for e in v12_hisp) / len(v12_hisp) - sum(abs(e) for e in v10_hisp) / len(v10_hisp),
            sum(v10_hisp) / len(v10_hisp),
            sum(v12_hisp) / len(v12_hisp),
            sum(v12_hisp) / len(v12_hisp) - sum(v10_hisp) / len(v10_hisp),
            100 * sum(1 for e in v10_hisp if abs(e) > 10) / len(v10_hisp),
            100 * sum(1 for e in v12_hisp if abs(e) > 10) / len(v12_hisp)))

    # Gender
    v10_gend = [e["gender_error"] for e in v10_errors if e.get("gender_error") is not None]
    v12_gend = [e["gender_error"] for e in v12_errors if e.get("gender_error") is not None]
    if v10_gend and v12_gend:
        print("  %-10s | %8.3f %8.3f %+5.3f  | %+8.3f %+8.3f %+5.3f  | %7.1f%% %7.1f%% |" % (
            "Gender(F)",
            sum(abs(e) for e in v10_gend) / len(v10_gend),
            sum(abs(e) for e in v12_gend) / len(v12_gend),
            sum(abs(e) for e in v12_gend) / len(v12_gend) - sum(abs(e) for e in v10_gend) / len(v10_gend),
            sum(v10_gend) / len(v10_gend),
            sum(v12_gend) / len(v12_gend),
            sum(v12_gend) / len(v12_gend) - sum(v10_gend) / len(v10_gend),
            100 * sum(1 for e in v10_gend if abs(e) > 10) / len(v10_gend),
            100 * sum(1 for e in v12_gend if abs(e) > 10) / len(v12_gend)))


def print_large_error_analysis(label, v10_errors, v12_errors):
    """Analyze companies with very large errors."""
    print("\n" + "=" * 110)
    print("LARGE ERROR ANALYSIS (%s)" % label)
    print("=" * 110)

    thresholds = [10, 15, 20, 25, 30]

    # Race: max category error > threshold
    print("\n  Companies with max single-category RACE error > threshold:")
    print("  %-12s | %8s %8s %8s | %8s %8s %8s |" % (
        "Threshold", "V10 N", "V10 %", "", "V12 N", "V12 %", "Delta"))
    print("  %s|%s|%s|" % ("-" * 14, "-" * 27, "-" * 27))

    v10_with_race = [e for e in v10_errors if e.get("race_max_err") is not None]
    v12_with_race = [e for e in v12_errors if e.get("race_max_err") is not None]

    for thresh in thresholds:
        v10_n = sum(1 for e in v10_with_race if e["race_max_err"] > thresh)
        v12_n = sum(1 for e in v12_with_race if e["race_max_err"] > thresh)
        v10_pct = 100 * v10_n / len(v10_with_race) if v10_with_race else 0
        v12_pct = 100 * v12_n / len(v12_with_race) if v12_with_race else 0
        delta = v12_n - v10_n
        print("  >%dpp       | %8d %7.1f%%          | %8d %7.1f%%  %+6d   |" % (
            thresh, v10_n, v10_pct, v12_n, v12_pct, delta))

    # Hispanic: error > threshold
    print("\n  Companies with HISPANIC error > threshold:")
    print("  %-12s | %8s %8s %8s | %8s %8s %8s |" % (
        "Threshold", "V10 N", "V10 %", "", "V12 N", "V12 %", "Delta"))
    print("  %s|%s|%s|" % ("-" * 14, "-" * 27, "-" * 27))

    v10_with_hisp = [e for e in v10_errors if e.get("hisp_mae") is not None]
    v12_with_hisp = [e for e in v12_errors if e.get("hisp_mae") is not None]

    for thresh in thresholds:
        v10_n = sum(1 for e in v10_with_hisp if e["hisp_mae"] > thresh)
        v12_n = sum(1 for e in v12_with_hisp if e["hisp_mae"] > thresh)
        v10_pct = 100 * v10_n / len(v10_with_hisp) if v10_with_hisp else 0
        v12_pct = 100 * v12_n / len(v12_with_hisp) if v12_with_hisp else 0
        delta = v12_n - v10_n
        print("  >%dpp       | %8d %7.1f%%          | %8d %7.1f%%  %+6d   |" % (
            thresh, v10_n, v10_pct, v12_n, v12_pct, delta))

    # Gender: error > threshold
    print("\n  Companies with GENDER error > threshold:")
    print("  %-12s | %8s %8s %8s | %8s %8s %8s |" % (
        "Threshold", "V10 N", "V10 %", "", "V12 N", "V12 %", "Delta"))
    print("  %s|%s|%s|" % ("-" * 14, "-" * 27, "-" * 27))

    v10_with_gend = [e for e in v10_errors if e.get("gender_mae") is not None]
    v12_with_gend = [e for e in v12_errors if e.get("gender_mae") is not None]

    for thresh in thresholds:
        v10_n = sum(1 for e in v10_with_gend if e["gender_mae"] > thresh)
        v12_n = sum(1 for e in v12_with_gend if e["gender_mae"] > thresh)
        v10_pct = 100 * v10_n / len(v10_with_gend) if v10_with_gend else 0
        v12_pct = 100 * v12_n / len(v12_with_gend) if v12_with_gend else 0
        delta = v12_n - v10_n
        print("  >%dpp       | %8d %7.1f%%          | %8d %7.1f%%  %+6d   |" % (
            thresh, v10_n, v10_pct, v12_n, v12_pct, delta))

    # Worst 20 companies by race error — compare V10 vs V12
    print("\n  WORST 20 COMPANIES BY RACE ERROR (V12):")
    print("  %-6s %-30s %-12s %-10s | %7s %7s %7s |" % (
        "Code", "Name", "Industry", "Region",
        "V10 MAE", "V12 MAE", "Delta"))
    print("  %s|%s|" % ("-" * 72, "-" * 25))

    v12_sorted = sorted(v12_with_race, key=lambda e: e["race_mae"], reverse=True)
    v10_lookup = {e["code"]: e for e in v10_with_race}

    for e12 in v12_sorted[:20]:
        e10 = v10_lookup.get(e12["code"])
        v10_mae = e10["race_mae"] if e10 else 0
        delta = e12["race_mae"] - v10_mae
        name = (e12["name"] or "")[:30]
        ng = (e12["naics_group"] or "")[:12]
        print("  %-6s %-30s %-12s %-10s | %7.2f %7.2f %+6.2f  |" % (
            e12["code"], name, ng, e12["region"],
            v10_mae, e12["race_mae"], delta))

    # Companies that GOT WORSE with V12
    print("\n  COMPANIES WHERE V12 IS WORSE THAN V10 (race MAE increased >0.5pp):")
    print("  %-6s %-30s %-12s %-10s | %7s %7s %7s | %-20s |" % (
        "Code", "Name", "Industry", "DivTier",
        "V10 MAE", "V12 MAE", "Delta", "Worst Cat"))
    print("  %s|%s|%s|" % ("-" * 72, "-" * 25, "-" * 22))

    worse_companies = []
    for e12 in v12_with_race:
        e10 = v10_lookup.get(e12["code"])
        if not e10:
            continue
        delta = e12["race_mae"] - e10["race_mae"]
        if delta > 0.5:
            # Find worst category
            worst_cat = ""
            worst_delta = 0
            if e12.get("race_errors") and e10.get("race_errors"):
                for cat in RACE_CATS:
                    if cat in e12["race_errors"] and cat in e10["race_errors"]:
                        cat_delta = abs(e12["race_errors"][cat]) - abs(e10["race_errors"][cat])
                        if cat_delta > worst_delta:
                            worst_delta = cat_delta
                            worst_cat = "%s (+%.1f)" % (cat, cat_delta)
            worse_companies.append((e12, e10, delta, worst_cat))

    worse_companies.sort(key=lambda x: x[2], reverse=True)
    for e12, e10, delta, worst_cat in worse_companies[:30]:
        name = (e12["name"] or "")[:30]
        ng = (e12["naics_group"] or "")[:12]
        print("  %-6s %-30s %-12s %-10s | %7.2f %7.2f %+6.2f  | %-20s |" % (
            e12["code"], name, ng, e12["diversity_tier"],
            e10["race_mae"], e12["race_mae"], delta, worst_cat))

    print("\n  Total worse by >0.5pp: %d / %d (%.1f%%)" % (
        len(worse_companies), len(v12_with_race),
        100 * len(worse_companies) / len(v12_with_race) if v12_with_race else 0))
    print("  Total worse by >1.0pp: %d" % sum(1 for _, _, d, _ in worse_companies if d > 1.0))
    print("  Total worse by >2.0pp: %d" % sum(1 for _, _, d, _ in worse_companies if d > 2.0))


def print_qwi_coverage_analysis(label, v12_errors, qwi):
    """Analyze results by QWI data availability."""
    print("\n" + "=" * 110)
    print("QWI COVERAGE IMPACT (%s)" % label)
    print("=" * 110)

    exact = []
    fallback = []
    for e in v12_errors:
        has_exact = qwi.get_race_exact(e["county_fips"], e["naics4"]) is not None
        if has_exact:
            exact.append(e)
        else:
            fallback.append(e)

    print("\n  %-25s | %5s | %8s | %8s | %8s | %8s |" % (
        "QWI Coverage", "N", "Race MAE", "Hisp MAE", "Gend MAE", "Max>20pp"))
    print("  %s|%s|%s|%s|%s|%s|" % (
        "-" * 27, "-" * 7, "-" * 10, "-" * 10, "-" * 10, "-" * 10))

    for name, group in [("Exact county x NAICS4", exact), ("Fallback/aggregated", fallback), ("All", v12_errors)]:
        if not group:
            continue
        race_maes = [e["race_mae"] for e in group if e.get("race_mae") is not None]
        hisp_maes = [e["hisp_mae"] for e in group if e.get("hisp_mae") is not None]
        gend_maes = [e["gender_mae"] for e in group if e.get("gender_mae") is not None]
        p20 = sum(1 for e in group if e.get("race_max_err") and e["race_max_err"] > 20)

        print("  %-25s | %5d | %8.3f | %8.3f | %8.3f | %7.1f%% |" % (
            name, len(group),
            sum(race_maes) / len(race_maes) if race_maes else 0,
            sum(hisp_maes) / len(hisp_maes) if hisp_maes else 0,
            sum(gend_maes) / len(gend_maes) if gend_maes else 0,
            100 * p20 / len(group) if group else 0))


def print_error_distribution(label, v10_errors, v12_errors):
    """Print error distribution histograms."""
    print("\n" + "=" * 110)
    print("ERROR DISTRIBUTION (%s)" % label)
    print("=" * 110)

    # Race MAE distribution
    bins = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 10), (10, 15), (15, 20), (20, 100)]
    print("\n  Race MAE distribution:")
    print("  %-12s | %8s %8s | %8s %8s |" % ("Range", "V10 N", "V10 %", "V12 N", "V12 %"))
    print("  %s|%s|%s|" % ("-" * 14, "-" * 19, "-" * 19))

    v10_race = [e["race_mae"] for e in v10_errors if e.get("race_mae") is not None]
    v12_race = [e["race_mae"] for e in v12_errors if e.get("race_mae") is not None]

    for lo, hi in bins:
        v10_n = sum(1 for e in v10_race if lo <= e < hi)
        v12_n = sum(1 for e in v12_race if lo <= e < hi)
        v10_pct = 100 * v10_n / len(v10_race) if v10_race else 0
        v12_pct = 100 * v12_n / len(v12_race) if v12_race else 0
        label_str = "%d-%dpp" % (lo, hi) if hi < 100 else "%d+pp" % lo
        print("  %-12s | %8d %7.1f%% | %8d %7.1f%% |" % (
            label_str, v10_n, v10_pct, v12_n, v12_pct))

    # Percentile comparison
    print("\n  Race MAE percentiles:")
    print("  %-12s | %8s | %8s | %8s |" % ("Percentile", "V10", "V12", "Delta"))
    print("  %s|%s|%s|%s|" % ("-" * 14, "-" * 10, "-" * 10, "-" * 10))

    v10_sorted = sorted(v10_race)
    v12_sorted = sorted(v12_race)
    for pct in [25, 50, 75, 90, 95, 99]:
        idx = int(len(v10_sorted) * pct / 100)
        v10_val = v10_sorted[min(idx, len(v10_sorted) - 1)]
        v12_val = v12_sorted[min(idx, len(v12_sorted) - 1)]
        print("  P%-11d | %8.3f | %8.3f | %+7.3f |" % (pct, v10_val, v12_val, v12_val - v10_val))


def main():
    t0 = time.time()
    print("V12 QWI DETAILED BREAKDOWN ANALYSIS")
    print("=" * 110)

    # Load QWI
    qwi = QWICache()

    # Load data
    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nBuilding records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d sealed=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Train Hispanic weights
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # ================================================================
    # Build V10 baseline predictions
    # ================================================================
    print("\nTraining V10 baseline calibration...")
    v10_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    def v10_final(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, v10_cal, D_RACE, D_HISP, D_GENDER)

    # ================================================================
    # Build V12 best config: QWI race + V10 Hispanic + QWI gender
    # ================================================================
    print("Training V12 calibration (QWI race + V10 Hispanic + QWI gender)...")

    def v12_scenario(rec):
        race = scenario_qwi_replace_acs(rec, qwi)
        hispanic = rec.get("hispanic_pred")
        qwi_gender = qwi.get_gender(rec['county_fips'], rec['naics4'])
        gender = qwi_gender if qwi_gender else get_gender(rec)
        return {"race": race, "hispanic": hispanic, "gender": gender}

    v12_cal = train_calibration_v92(train_records, v12_scenario, max_offset=20.0)

    def v12_final(rec):
        pred = v12_scenario(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, v12_cal, D_RACE, D_HISP, D_GENDER)

    # ================================================================
    # Compute per-company errors on BOTH holdouts
    # ================================================================
    for holdout_name, holdout_records in [
        ("PERMANENT HOLDOUT", perm_records),
        ("SEALED HOLDOUT", v10_records),
    ]:
        print("\n\n" + "#" * 110)
        print("# %s (n=%d)" % (holdout_name, len(holdout_records)))
        print("#" * 110)

        print("\nComputing per-company errors...")
        v10_errors = compute_per_company_errors(holdout_records, v10_final)
        v12_errors = compute_per_company_errors(holdout_records, v12_final)

        # Overall summary
        v10_race_maes = [e["race_mae"] for e in v10_errors if e.get("race_mae") is not None]
        v12_race_maes = [e["race_mae"] for e in v12_errors if e.get("race_mae") is not None]
        v10_hisp_maes = [e["hisp_mae"] for e in v10_errors if e.get("hisp_mae") is not None]
        v12_hisp_maes = [e["hisp_mae"] for e in v12_errors if e.get("hisp_mae") is not None]
        v10_gend_maes = [e["gender_mae"] for e in v10_errors if e.get("gender_mae") is not None]
        v12_gend_maes = [e["gender_mae"] for e in v12_errors if e.get("gender_mae") is not None]

        print("\n  OVERALL SUMMARY:")
        print("  %-15s | %8s | %8s | %8s |" % ("Metric", "V10", "V12", "Delta"))
        print("  %s|%s|%s|%s|" % ("-" * 17, "-" * 10, "-" * 10, "-" * 10))
        print("  %-15s | %8.3f | %8.3f | %+7.3f |" % (
            "Race MAE",
            sum(v10_race_maes) / len(v10_race_maes),
            sum(v12_race_maes) / len(v12_race_maes),
            sum(v12_race_maes) / len(v12_race_maes) - sum(v10_race_maes) / len(v10_race_maes)))
        print("  %-15s | %8.3f | %8.3f | %+7.3f |" % (
            "Hispanic MAE",
            sum(v10_hisp_maes) / len(v10_hisp_maes),
            sum(v12_hisp_maes) / len(v12_hisp_maes),
            sum(v12_hisp_maes) / len(v12_hisp_maes) - sum(v10_hisp_maes) / len(v10_hisp_maes)))
        print("  %-15s | %8.3f | %8.3f | %+7.3f |" % (
            "Gender MAE",
            sum(v10_gend_maes) / len(v10_gend_maes),
            sum(v12_gend_maes) / len(v12_gend_maes),
            sum(v12_gend_maes) / len(v12_gend_maes) - sum(v10_gend_maes) / len(v10_gend_maes)))

        # All breakdowns
        print_breakdown("Industry (NAICS Group)", v10_errors, v12_errors, "naics_group")
        print_breakdown("Region", v10_errors, v12_errors, "region")
        print_breakdown("Diversity Tier", v10_errors, v12_errors, "diversity_tier")
        print_breakdown("Company Size", v10_errors, v12_errors, "size_bucket")
        print_per_category_errors(holdout_name, v10_errors, v12_errors)
        print_error_distribution(holdout_name, v10_errors, v12_errors)
        print_large_error_analysis(holdout_name, v10_errors, v12_errors)
        print_qwi_coverage_analysis(holdout_name, v12_errors, qwi)

    cur.close()
    conn.close()
    print("\n\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == '__main__':
    main()
