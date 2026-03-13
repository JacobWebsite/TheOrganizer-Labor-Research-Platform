"""V11 Extended Signal Testing: Tract Education + Company Size + Occupation Profile.

Tests three new signal types that target different granularity than existing model:
  1. Tract-level education (84K tracts vs 50 states)
  4. Company size (company-specific, never used)
  6. Occupation profile + education gap (industry x local education interaction)

Each signal is tested as a residual correction on top of V10 predictions.
Early-exit logic skips blend tests when MAE variation by tier < 0.1pp.

Usage:
    py scripts/analysis/demographics_comparison/test_v11_extended_signals.py
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
    get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    get_gender,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
    blend_hispanic,
)
from run_v10 import (
    build_v10_splits, build_records, scenario_v92_full, scenario_v92_race,
    load_json, save_json, SCRIPT_DIR,
    train_hispanic_calibration, apply_hispanic_calibration, estimate_confidence,
    make_v92_pipeline, get_hispanic_county_tier,
)
from test_v11_signals import (
    EducationSignalBuilder, BLS_TO_ACS_EDU, blend_dicts,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

# Education tiers for occupation profile
EDU_YEAR_MAP = {
    "No formal educational credential": 12,
    "High school diploma or equivalent": 12,
    "Some college, no degree": 14,
    "Postsecondary nondegree award": 14,
    "Associate's degree": 14,
    "Bachelor's degree": 16,
    "Master's degree": 18,
    "Doctoral or professional degree": 18,
}


# ================================================================
# RESIDUAL CALIBRATION ARCHITECTURE
# ================================================================
def train_residual_correction(train_records, v10_fn, tier_fn, dims, min_bucket=30, max_offset=10.0):
    """Train per-dimension corrections grouped by a new signal tier.

    Args:
        train_records: list of record dicts
        v10_fn: function(rec) -> prediction dict
        tier_fn: function(rec) -> tier string (or None to skip)
        dims: list of (dim_name, cats) tuples, e.g. [("race", RACE_CATS)]
        min_bucket: minimum records per bucket
        max_offset: maximum correction magnitude

    Returns:
        dict of {(dim, cat, tier): offset}
    """
    buckets = defaultdict(list)
    for rec in train_records:
        tier = tier_fn(rec)
        if tier is None:
            continue
        pred = v10_fn(rec)
        if not pred:
            continue
        for dim_name, cats in dims:
            p = pred.get(dim_name)
            a = rec["truth"].get(dim_name)
            if not p or not a:
                continue
            for cat in cats:
                if cat in p and cat in a:
                    err = p[cat] - a[cat]
                    buckets[(dim_name, cat, tier)].append(err)

    offsets = {}
    for k, errs in buckets.items():
        if len(errs) >= min_bucket:
            raw = sum(errs) / len(errs)
            capped = max(-max_offset, min(max_offset, raw))
            offsets[k] = (capped, len(errs))
    return offsets


def apply_residual_correction(pred, rec, offsets, tier_fn, dampening=0.5):
    """Apply trained corrections: pred[dim][cat] -= offset * dampening.

    Returns a new prediction dict with corrections applied.
    """
    tier = tier_fn(rec)
    if tier is None:
        return pred

    result = {}
    for dim_name in ["race", "hispanic", "gender"]:
        p = pred.get(dim_name)
        if not p:
            result[dim_name] = p
            continue
        cats = RACE_CATS if dim_name == "race" else (HISP_CATS if dim_name == "hispanic" else GENDER_CATS)
        corrected = dict(p)
        applied = False
        for cat in cats:
            key = (dim_name, cat, tier)
            if key in offsets and cat in corrected:
                corrected[cat] -= offsets[key][0] * dampening
                applied = True
        if applied:
            # Clamp to 0-100 and renormalize
            for cat in cats:
                if cat in corrected:
                    corrected[cat] = max(0.0, corrected[cat])
            total = sum(corrected.get(c, 0.0) for c in cats)
            if total > 0:
                for cat in cats:
                    if cat in corrected:
                        corrected[cat] = corrected[cat] * 100.0 / total
        result[dim_name] = corrected
    return result


# ================================================================
# SIGNAL COMPUTATION
# ================================================================
def load_tract_education(cur):
    """Bulk-load tract-level education by ZIP code.

    Returns dict: zip_code -> weighted_pct_bachelors_plus (0-100 scale)
    """
    cur.execute("""
        SELECT zt.zip_code,
               SUM(zt.bus_ratio * COALESCE(at.pop_25plus, 1) * at.pct_bachelors_plus) /
               NULLIF(SUM(zt.bus_ratio * COALESCE(at.pop_25plus, 1)), 0) as weighted_edu
        FROM zip_tract_crosswalk zt
        JOIN acs_tract_demographics at ON at.tract_fips = zt.tract_geoid
        WHERE at.pct_bachelors_plus IS NOT NULL
        GROUP BY zt.zip_code
    """)
    result = {}
    for row in cur.fetchall():
        result[row["zip_code"]] = float(row["weighted_edu"])
    return result


def get_edu_tier(pct):
    """Classify education tier from pct_bachelors_plus."""
    if pct is None:
        return None
    if pct < 20:
        return "edu_low"
    elif pct <= 40:
        return "edu_med"
    else:
        return "edu_high"


def get_size_bucket(total_employees):
    """Classify company size bucket."""
    if total_employees is None or total_employees <= 0:
        return None
    if total_employees < 250:
        return "small"
    elif total_employees < 1000:
        return "medium"
    elif total_employees < 5000:
        return "large"
    else:
        return "xlarge"


def load_occupation_education(cur):
    """Load BLS occupation -> typical education for all industries.

    Returns dict: industry_code -> {
        'white_collar_ratio': float (0-1),
        'expected_edu_years': float (12-20),
        'expected_edu_normalized': float (0-100)
    }
    """
    cur.execute("""
        SELECT bom.industry_code, bom.occupation_code, bom.employment_2024,
               bp.typical_education
        FROM bls_industry_occupation_matrix bom
        JOIN bls_occupation_projections bp
          ON LEFT(bom.occupation_code, 7) = LEFT(bp.soc_code, 7)
        WHERE bp.typical_education IS NOT NULL
          AND bom.employment_2024 > 0
    """)

    industry_occ = defaultdict(lambda: defaultdict(float))
    industry_edu_years = defaultdict(lambda: defaultdict(float))

    for row in cur.fetchall():
        ind = row["industry_code"]
        edu_label = row["typical_education"]
        emp = float(row["employment_2024"])

        # White collar = bachelor's or higher
        acs_code = BLS_TO_ACS_EDU.get(edu_label)
        if acs_code in ("08", "10"):  # Bachelor's or Graduate
            industry_occ[ind]["bachelors_plus"] += emp
        industry_occ[ind]["total"] += emp

        # Expected education years
        years = EDU_YEAR_MAP.get(edu_label)
        if years:
            industry_edu_years[ind]["weighted_years"] += years * emp
            industry_edu_years[ind]["total"] += emp

    result = {}
    for ind in industry_occ:
        total = industry_occ[ind]["total"]
        if total <= 0:
            continue
        wc_ratio = industry_occ[ind]["bachelors_plus"] / total

        edu_total = industry_edu_years[ind]["total"]
        if edu_total > 0:
            avg_years = industry_edu_years[ind]["weighted_years"] / edu_total
        else:
            avg_years = 12.0

        # Normalize: (years - 12) / 8 * 100  (12=HS, 20=PhD -> 0-100)
        normalized = max(0.0, min(100.0, (avg_years - 12.0) / 8.0 * 100.0))

        result[ind] = {
            "white_collar_ratio": wc_ratio,
            "expected_edu_years": avg_years,
            "expected_edu_normalized": normalized,
        }
    return result


def get_industry_occ_profile(naics4, occ_data):
    """Look up occupation profile for a NAICS code, with fallbacks."""
    for code in [naics4 + "00", naics4[:4] + "00", naics4[:3] + "000", naics4[:2] + "0000"]:
        if code in occ_data:
            return occ_data[code]
    return None


def get_wc_tier(wc_ratio):
    """Classify white-collar ratio tier."""
    if wc_ratio is None:
        return None
    if wc_ratio < 0.20:
        return "wc_low"
    elif wc_ratio <= 0.50:
        return "wc_med"
    else:
        return "wc_high"


def get_gap_quintile(edu_gap):
    """Classify education gap into quintiles."""
    if edu_gap is None:
        return None
    if edu_gap < -20:
        return "gap_very_neg"
    elif edu_gap < -5:
        return "gap_neg"
    elif edu_gap <= 5:
        return "gap_neutral"
    elif edu_gap <= 20:
        return "gap_pos"
    else:
        return "gap_very_pos"


# ================================================================
# DIAGNOSTIC HELPERS
# ================================================================
def diagnostic_mae_by_tier(records, v10_fn, tier_fn, tier_label, dims):
    """Compute V10 MAE by tier for diagnostic purposes.

    Returns dict: {tier: {dim_name: mae}} and prints results.
    """
    tier_errors = defaultdict(lambda: defaultdict(list))
    for rec in records:
        tier = tier_fn(rec)
        if tier is None:
            continue
        pred = v10_fn(rec)
        if not pred:
            continue
        for dim_name, cats in dims:
            p = pred.get(dim_name)
            a = rec["truth"].get(dim_name)
            if p and a:
                m = mae_dict(p, a, cats)
                if m is not None:
                    tier_errors[tier][dim_name].append(m)

    print("\n  V10 MAE by %s:" % tier_label)
    header_dims = [d for d, _ in dims]
    print("  | %-20s | %5s | %s |" % (
        tier_label, "N", " | ".join("%-8s" % d for d in header_dims)))
    print("  |%s|%s|%s|" % (
        "-" * 22, "-" * 7,
        "|".join("-" * 10 for _ in header_dims)))

    tier_results = {}
    tiers_sorted = sorted(tier_errors.keys())
    for tier in tiers_sorted:
        errs = tier_errors[tier]
        n = max(len(v) for v in errs.values()) if errs else 0
        row = {}
        for dim_name in header_dims:
            vals = errs.get(dim_name, [])
            row[dim_name] = sum(vals) / len(vals) if vals else None
        tier_results[tier] = row

        vals_str = " | ".join(
            "%-8.3f" % row[d] if row[d] is not None else "%-8s" % "N/A"
            for d in header_dims)
        print("  | %-20s | %5d | %s |" % (tier, n, vals_str))

    # Check spread
    for dim_name in header_dims:
        vals = [r[dim_name] for r in tier_results.values() if r.get(dim_name) is not None]
        if vals:
            spread = max(vals) - min(vals)
            print("  %s spread: %.3f pp %s" % (
                dim_name, spread,
                "(SKIP - < 0.1pp)" if spread < 0.1 else "(SIGNIFICANT)"))

    return tier_results


def check_spread(tier_results, dim_name, threshold=0.1):
    """Check if spread exceeds threshold for a dimension."""
    vals = [r[dim_name] for r in tier_results.values() if r.get(dim_name) is not None]
    if not vals:
        return False
    return (max(vals) - min(vals)) >= threshold


# ================================================================
# MAIN
# ================================================================
def main():
    t0 = time.time()
    print("V11 Extended Signal Testing: Tract Education + Company Size + Occupation Profile")
    print("=" * 80)

    # ============================================================
    # PHASE 0: Setup
    # ============================================================
    print("\n--- Phase 0: Setup ---")
    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("Building records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Train V10 baseline
    print("\nTraining V10 baseline (Hispanic weights + calibration)...")
    final_fn_v10, cal_v10, _, _ = make_v92_pipeline(
        train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5)

    # Train Hispanic-specific calibration
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    # V10 prediction function
    def v10_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, cal_v10, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal, 0.50)
        return result

    # V10 baseline metrics
    print("\n" + "=" * 80)
    print("V10 BASELINE")
    print("=" * 80)
    m_v10_perm = evaluate(perm_records, v10_fn)
    m_v10_sealed = evaluate(v10_records, v10_fn)
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"],
        m_v10_perm["p20"], m_v10_perm["p30"]))
    print("  Sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_sealed["race"], m_v10_sealed["hisp"], m_v10_sealed["gender"],
        m_v10_sealed["p20"], m_v10_sealed["p30"]))

    dims_all = [
        ("race", RACE_CATS),
        ("hispanic", HISP_CATS),
        ("gender", GENDER_CATS),
    ]

    # ============================================================
    # PHASE 1: Compute Signals
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 1: Compute Signals")
    print("=" * 80)

    # Signal 1: Tract-level education
    print("\nLoading tract-level education...")
    tract_edu_map = load_tract_education(cur)
    print("  Loaded %d ZIP -> tract education mappings" % len(tract_edu_map))

    edu_coverage = 0
    for rec in all_records:
        zipcode = rec.get("zipcode", "")
        edu_val = tract_edu_map.get(zipcode)
        rec["tract_edu"] = edu_val
        rec["edu_tier"] = get_edu_tier(edu_val)
        if edu_val is not None:
            edu_coverage += 1
    print("  Tract education coverage: %d / %d (%.1f%%)" % (
        edu_coverage, len(all_records), 100.0 * edu_coverage / len(all_records)))

    # Signal 4: Company size
    print("\nComputing size buckets...")
    size_coverage = 0
    size_dist = defaultdict(int)
    for rec in all_records:
        total = rec.get("total_employees", 0)
        bucket = get_size_bucket(total)
        rec["size_bucket"] = bucket
        if bucket:
            size_coverage += 1
            size_dist[bucket] += 1
    print("  Size bucket coverage: %d / %d (%.1f%%)" % (
        size_coverage, len(all_records), 100.0 * size_coverage / len(all_records)))
    for b in ["small", "medium", "large", "xlarge"]:
        print("    %-8s: %d" % (b, size_dist.get(b, 0)))

    # Signal 6: Occupation profile
    print("\nLoading occupation education profiles...")
    occ_data = load_occupation_education(cur)
    print("  Loaded %d industry occupation profiles" % len(occ_data))

    occ_coverage = 0
    for rec in all_records:
        naics4 = rec["naics4"]
        profile = get_industry_occ_profile(naics4, occ_data)
        if profile:
            rec["white_collar_ratio"] = profile["white_collar_ratio"]
            rec["industry_expected_edu"] = profile["expected_edu_normalized"]
            occ_coverage += 1

            # Education gap (tract edu - white collar ratio * 100)
            if rec["tract_edu"] is not None:
                rec["edu_gap"] = rec["tract_edu"] - (profile["white_collar_ratio"] * 100)
            else:
                rec["edu_gap"] = None
        else:
            rec["white_collar_ratio"] = None
            rec["industry_expected_edu"] = None
            rec["edu_gap"] = None
    print("  Occupation profile coverage: %d / %d (%.1f%%)" % (
        occ_coverage, len(all_records), 100.0 * occ_coverage / len(all_records)))

    gap_coverage = sum(1 for r in all_records if r["edu_gap"] is not None)
    print("  Education gap coverage: %d / %d (%.1f%%)" % (
        gap_coverage, len(all_records), 100.0 * gap_coverage / len(all_records)))

    # ============================================================
    # PHASE 2: Signal 1 Tests (Tract Education)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 2: Signal 1 -- Tract-Level Education")
    print("=" * 80)

    # Diagnostic: MAE by education tier
    edu_diag = diagnostic_mae_by_tier(
        train_records, v10_fn,
        lambda r: r.get("edu_tier"),
        "Education Tier", dims_all)

    skip_edu = {}
    for dim_name in ["race", "hispanic", "gender"]:
        dim_key = "hisp" if dim_name == "hispanic" else dim_name
        skip_edu[dim_name] = not check_spread(edu_diag, dim_key)

    # Residual correction by edu tier
    if not all(skip_edu.values()):
        print("\n  Training residual corrections by education tier...")
        edu_offsets = train_residual_correction(
            train_records, v10_fn,
            lambda r: r.get("edu_tier"),
            dims_all, min_bucket=30, max_offset=10.0)

        print("  Trained %d correction buckets" % len(edu_offsets))
        for k, (off, n) in sorted(edu_offsets.items()):
            print("    %-40s: offset=%+.2f n=%d" % (str(k), off, n))

        # Grid search dampening
        print("\n  Testing education tier corrections (perm holdout):")
        print("  | %-10s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
            "Dampening", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 12, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

        edu_configs = []
        for damp in [0.25, 0.50, 0.75, 1.0]:
            def edu_fn(rec, _d=damp, _off=edu_offsets):
                pred = v10_fn(rec)
                if not pred:
                    return None
                return apply_residual_correction(pred, rec, _off,
                                                 lambda r: r.get("edu_tier"), _d)

            m = evaluate(perm_records, edu_fn)
            r_gap = m["race"] - m_v10_perm["race"]
            h_gap = m["hisp"] - m_v10_perm["hisp"]
            g_gap = m["gender"] - m_v10_perm["gender"]

            notes = []
            if r_gap < -0.01:
                notes.append("R+")
            if h_gap < -0.01:
                notes.append("H+")
            if g_gap < -0.01:
                notes.append("G+")

            print("  | %-10.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                damp, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"],
                " ".join(notes)))
            edu_configs.append({
                "type": "edu_tier", "dampening": damp, "metrics": m,
                "gaps": {"race": r_gap, "hisp": h_gap, "gender": g_gap},
                "offsets": edu_offsets,
            })

        # Continuous Hispanic modifier: linear coefficient
        print("\n  Testing continuous tract education -> Hispanic modifier...")
        edu_vals = [r["tract_edu"] for r in train_records if r["tract_edu"] is not None]
        edu_mean = sum(edu_vals) / len(edu_vals) if edu_vals else 30.0
        print("  Mean tract education: %.1f%%" % edu_mean)

        # Train linear coefficient on training set
        hisp_xy = []
        for rec in train_records:
            if rec["tract_edu"] is None:
                continue
            pred = v10_fn(rec)
            if not pred or not pred.get("hispanic"):
                continue
            actual_h = rec["truth"]["hispanic"].get("Hispanic")
            pred_h = pred["hispanic"].get("Hispanic")
            if actual_h is not None and pred_h is not None:
                x = rec["tract_edu"] - edu_mean
                y = pred_h - actual_h  # positive = overprediction
                hisp_xy.append((x, y))

        if len(hisp_xy) > 100:
            sum_xy = sum(x * y for x, y in hisp_xy)
            sum_xx = sum(x * x for x, y in hisp_xy)
            beta_hisp = sum_xy / sum_xx if sum_xx > 0 else 0.0
            print("  Linear Hispanic beta: %.4f (per 1pp edu above mean)" % beta_hisp)
            print("  Interpretation: +1pp tract education -> Hispanic prediction %+.3fpp correction" % (-beta_hisp))

            for beta_scale in [0.25, 0.50, 0.75, 1.0]:
                beta_used = beta_hisp * beta_scale

                def linear_hisp_fn(rec, _beta=beta_used, _mean=edu_mean):
                    pred = v10_fn(rec)
                    if not pred or not pred.get("hispanic"):
                        return pred
                    if rec["tract_edu"] is None:
                        return pred
                    correction = _beta * (rec["tract_edu"] - _mean)
                    result = dict(pred)
                    hv = pred["hispanic"].get("Hispanic", 0.0) - correction
                    hv = max(0.0, min(100.0, hv))
                    result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
                    return result

                m = evaluate(perm_records, linear_hisp_fn)
                gap = m["hisp"] - m_v10_perm["hisp"]
                print("    beta_scale=%.2f (beta=%.4f): Hisp=%.3f (%+.3f)" % (
                    beta_scale, beta_used, m["hisp"], gap))
    else:
        print("\n  All dimensions below 0.1pp spread -- skipping education corrections")
        edu_configs = []

    # ============================================================
    # PHASE 3: Signal 4 Tests (Company Size)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 3: Signal 4 -- Company Size")
    print("=" * 80)

    # Diagnostic: MAE by size bucket
    size_diag = diagnostic_mae_by_tier(
        train_records, v10_fn,
        lambda r: r.get("size_bucket"),
        "Size Bucket", dims_all)

    skip_size = {}
    for dim_name in ["race", "hispanic", "gender"]:
        dim_key = "hisp" if dim_name == "hispanic" else dim_name
        skip_size[dim_name] = not check_spread(size_diag, dim_key)

    size_configs = []
    if not all(skip_size.values()):
        print("\n  Training residual corrections by size bucket...")
        size_offsets = train_residual_correction(
            train_records, v10_fn,
            lambda r: r.get("size_bucket"),
            dims_all, min_bucket=30, max_offset=10.0)

        print("  Trained %d correction buckets" % len(size_offsets))
        for k, (off, n) in sorted(size_offsets.items()):
            print("    %-40s: offset=%+.2f n=%d" % (str(k), off, n))

        # Grid search dampening
        print("\n  Testing size corrections (perm holdout):")
        print("  | %-10s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
            "Dampening", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 12, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

        for damp in [0.25, 0.50, 0.75, 1.0]:
            def size_fn(rec, _d=damp, _off=size_offsets):
                pred = v10_fn(rec)
                if not pred:
                    return None
                return apply_residual_correction(pred, rec, _off,
                                                 lambda r: r.get("size_bucket"), _d)

            m = evaluate(perm_records, size_fn)
            r_gap = m["race"] - m_v10_perm["race"]
            h_gap = m["hisp"] - m_v10_perm["hisp"]
            g_gap = m["gender"] - m_v10_perm["gender"]

            notes = []
            if r_gap < -0.01:
                notes.append("R+")
            if h_gap < -0.01:
                notes.append("H+")
            if g_gap < -0.01:
                notes.append("G+")

            print("  | %-10.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                damp, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"],
                " ".join(notes)))
            size_configs.append({
                "type": "size", "dampening": damp, "metrics": m,
                "gaps": {"race": r_gap, "hisp": h_gap, "gender": g_gap},
                "offsets": size_offsets,
            })

        # Size x diversity tier cross-diagnostic
        print("\n  Size x Diversity Tier diagnostic (training set):")
        print("  | %-8s | %-8s | %5s | %-8s | %-8s | %-10s |" % (
            "Size", "DivTier", "N", "Race MAE", "Hisp MAE", "Gender MAE"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 10, "-" * 10, "-" * 7, "-" * 10, "-" * 10, "-" * 12))

        cross_errs = defaultdict(lambda: {"race": [], "hisp": [], "gender": []})
        for rec in train_records:
            sb = rec.get("size_bucket")
            dt = rec.get("diversity_tier")
            if not sb or not dt:
                continue
            pred = v10_fn(rec)
            if not pred:
                continue
            key = (sb, dt)
            for dim_name, cats in dims_all:
                p = pred.get(dim_name)
                a = rec["truth"].get(dim_name)
                dim_key = "hisp" if dim_name == "hispanic" else dim_name
                if p and a:
                    m = mae_dict(p, a, cats)
                    if m is not None:
                        cross_errs[key][dim_key].append(m)

        for (sb, dt) in sorted(cross_errs.keys()):
            errs = cross_errs[(sb, dt)]
            n = max(len(v) for v in errs.values()) if errs else 0
            if n < 10:
                continue
            r_mae = sum(errs["race"]) / len(errs["race"]) if errs["race"] else 0
            h_mae = sum(errs["hisp"]) / len(errs["hisp"]) if errs["hisp"] else 0
            g_mae = sum(errs["gender"]) / len(errs["gender"]) if errs["gender"] else 0
            print("  | %-8s | %-8s | %5d | %-8.3f | %-8.3f | %-10.3f |" % (
                sb, dt, n, r_mae, h_mae, g_mae))
    else:
        print("\n  All dimensions below 0.1pp spread -- skipping size corrections")

    # ============================================================
    # PHASE 4: Signal 6 Tests (Occupation Profile + Education Gap)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 4: Signal 6 -- Occupation Profile + Education Gap")
    print("=" * 80)

    # Diagnostic: MAE by white-collar ratio tier
    wc_diag = diagnostic_mae_by_tier(
        train_records, v10_fn,
        lambda r: get_wc_tier(r.get("white_collar_ratio")),
        "WC Ratio Tier", dims_all)

    # Diagnostic: MAE by education gap quintile
    gap_diag = diagnostic_mae_by_tier(
        train_records, v10_fn,
        lambda r: get_gap_quintile(r.get("edu_gap")),
        "Education Gap", dims_all)

    skip_wc = {}
    skip_gap = {}
    for dim_name in ["race", "hispanic", "gender"]:
        dim_key = "hisp" if dim_name == "hispanic" else dim_name
        skip_wc[dim_name] = not check_spread(wc_diag, dim_key)
        skip_gap[dim_name] = not check_spread(gap_diag, dim_key)

    gap_configs = []

    # Test WC ratio corrections
    if not all(skip_wc.values()):
        print("\n  Training residual corrections by WC ratio tier...")
        wc_offsets = train_residual_correction(
            train_records, v10_fn,
            lambda r: get_wc_tier(r.get("white_collar_ratio")),
            dims_all, min_bucket=30, max_offset=10.0)

        print("  Trained %d correction buckets" % len(wc_offsets))
        for k, (off, n) in sorted(wc_offsets.items()):
            print("    %-40s: offset=%+.2f n=%d" % (str(k), off, n))

        print("\n  Testing WC ratio corrections (perm holdout):")
        print("  | %-10s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
            "Dampening", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 12, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

        for damp in [0.25, 0.50, 0.75, 1.0]:
            def wc_fn(rec, _d=damp, _off=wc_offsets):
                pred = v10_fn(rec)
                if not pred:
                    return None
                return apply_residual_correction(pred, rec, _off,
                                                 lambda r: get_wc_tier(r.get("white_collar_ratio")), _d)

            m = evaluate(perm_records, wc_fn)
            r_gap = m["race"] - m_v10_perm["race"]
            h_gap = m["hisp"] - m_v10_perm["hisp"]
            g_gap = m["gender"] - m_v10_perm["gender"]

            notes = []
            if r_gap < -0.01:
                notes.append("R+")
            if h_gap < -0.01:
                notes.append("H+")
            if g_gap < -0.01:
                notes.append("G+")

            print("  | %-10.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                damp, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"],
                " ".join(notes)))

    # Test education gap as continuous modifier
    if not all(skip_gap.values()):
        print("\n  Training continuous education gap modifiers...")

        # Train linear coefficient per dimension
        for dim_name, cats in dims_all:
            dim_key = "hisp" if dim_name == "hispanic" else dim_name
            if skip_gap[dim_name]:
                print("    %s: skipped (no spread)" % dim_name)
                continue

            xy = []
            for rec in train_records:
                if rec["edu_gap"] is None:
                    continue
                pred = v10_fn(rec)
                if not pred or not pred.get(dim_name):
                    continue
                a = rec["truth"].get(dim_name)
                if not a:
                    continue
                # Use first category as proxy
                main_cat = cats[0]
                if main_cat in pred[dim_name] and main_cat in a:
                    x = rec["edu_gap"]
                    y = pred[dim_name][main_cat] - a[main_cat]
                    xy.append((x, y))

            if len(xy) < 100:
                print("    %s: insufficient data (%d)" % (dim_name, len(xy)))
                continue

            sum_xy = sum(x * y for x, y in xy)
            sum_xx = sum(x * x for x, y in xy)
            beta = sum_xy / sum_xx if sum_xx > 0 else 0.0
            print("    %s beta: %.5f (n=%d)" % (dim_name, beta, len(xy)))

        # Test gap quintile corrections
        print("\n  Training residual corrections by education gap quintile...")
        gap_offsets = train_residual_correction(
            train_records, v10_fn,
            lambda r: get_gap_quintile(r.get("edu_gap")),
            dims_all, min_bucket=30, max_offset=10.0)

        print("  Trained %d correction buckets" % len(gap_offsets))
        for k, (off, n) in sorted(gap_offsets.items()):
            print("    %-40s: offset=%+.2f n=%d" % (str(k), off, n))

        print("\n  Testing education gap corrections (perm holdout):")
        print("  | %-10s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
            "Dampening", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 12, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

        for damp in [0.25, 0.50, 0.75, 1.0]:
            def gap_fn(rec, _d=damp, _off=gap_offsets):
                pred = v10_fn(rec)
                if not pred:
                    return None
                return apply_residual_correction(pred, rec, _off,
                                                 lambda r: get_gap_quintile(r.get("edu_gap")), _d)

            m = evaluate(perm_records, gap_fn)
            r_gap = m["race"] - m_v10_perm["race"]
            h_gap = m["hisp"] - m_v10_perm["hisp"]
            g_gap = m["gender"] - m_v10_perm["gender"]

            notes = []
            if r_gap < -0.01:
                notes.append("R+")
            if h_gap < -0.01:
                notes.append("H+")
            if g_gap < -0.01:
                notes.append("G+")

            print("  | %-10.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                damp, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"],
                " ".join(notes)))
            gap_configs.append({
                "type": "gap", "dampening": damp, "metrics": m,
                "gaps": {"race": r_gap, "hisp": h_gap, "gender": g_gap},
                "offsets": gap_offsets,
            })
    else:
        print("\n  All dimensions below 0.1pp spread -- skipping gap corrections")

    # ============================================================
    # PHASE 5: Combination Tests
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 5: Combination Tests")
    print("=" * 80)

    # Collect best configs from each signal
    all_individual = edu_configs + size_configs + gap_configs
    # Filter to configs that improved at least one dimension
    improving = [c for c in all_individual
                 if any(c["gaps"][d] < -0.01 for d in ["race", "hisp", "gender"])]

    if not improving:
        print("\n  No individual signal improved any dimension by >0.01pp.")
        print("  Skipping combination tests.")
    else:
        # Group by type, take best dampening per type
        best_by_type = {}
        for c in improving:
            ctype = c["type"]
            total_imp = -(c["gaps"]["race"] + c["gaps"]["hisp"] + c["gaps"]["gender"])
            if ctype not in best_by_type or total_imp > best_by_type[ctype]["_total"]:
                best_by_type[ctype] = {**c, "_total": total_imp}

        types_available = list(best_by_type.keys())
        print("  Signals with improvement: %s" % ", ".join(types_available))

        if len(types_available) >= 2:
            print("\n  Testing combinations (perm holdout):")
            print("  | %-30s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
                "Config", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
            print("  |%s|%s|%s|%s|%s|%s|" % (
                "-" * 32, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

            combo_results = []

            # Test all 2-way and 3-way combinations
            from itertools import combinations
            for r_len in range(2, len(types_available) + 1):
                for combo in combinations(types_available, r_len):
                    configs = [best_by_type[t] for t in combo]

                    def combo_fn(rec, _configs=configs):
                        pred = v10_fn(rec)
                        if not pred:
                            return None
                        for cfg in _configs:
                            tier_fn_map = {
                                "edu_tier": lambda r: r.get("edu_tier"),
                                "size": lambda r: r.get("size_bucket"),
                                "gap": lambda r: get_gap_quintile(r.get("edu_gap")),
                            }
                            tfn = tier_fn_map.get(cfg["type"])
                            if tfn:
                                pred = apply_residual_correction(
                                    pred, rec, cfg["offsets"], tfn, cfg["dampening"])
                        return pred

                    m = evaluate(perm_records, combo_fn)
                    r_gap = m["race"] - m_v10_perm["race"]
                    h_gap = m["hisp"] - m_v10_perm["hisp"]
                    g_gap = m["gender"] - m_v10_perm["gender"]

                    label = "+".join("%s(d=%.2f)" % (t, best_by_type[t]["dampening"]) for t in combo)
                    notes = []
                    if r_gap < -0.01:
                        notes.append("R+")
                    if h_gap < -0.01:
                        notes.append("H+")
                    if g_gap < -0.01:
                        notes.append("G+")

                    print("  | %-30s | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                        label[:30], m["race"], m["hisp"], m["gender"],
                        m["p20"], m["p30"], " ".join(notes)))
                    combo_results.append({
                        "label": label, "combo": combo, "metrics": m,
                        "gaps": {"race": r_gap, "hisp": h_gap, "gender": g_gap},
                        "configs": configs,
                    })
        else:
            print("  Only one signal type improved -- no combinations to test")
            combo_results = []

    # ============================================================
    # PHASE 6: Sealed Holdout Validation
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 6: Sealed Holdout Validation")
    print("=" * 80)

    # Collect top configs for sealed validation
    candidates = []

    # Individual configs that improved
    for c in all_individual:
        total_imp = -(c["gaps"]["race"] + c["gaps"]["hisp"] + c["gaps"]["gender"])
        if total_imp > 0.01:
            candidates.append({
                "label": "%s(d=%.2f)" % (c["type"], c["dampening"]),
                "make_fn": lambda rec, _c=c: apply_residual_correction(
                    v10_fn(rec), rec, _c["offsets"],
                    {
                        "edu_tier": lambda r: r.get("edu_tier"),
                        "size": lambda r: r.get("size_bucket"),
                        "gap": lambda r: get_gap_quintile(r.get("edu_gap")),
                    }[_c["type"]], _c["dampening"]) if v10_fn(rec) else None,
                "total_imp_perm": total_imp,
                "perm_metrics": c["metrics"],
            })

    # Combination configs
    if improving and len(types_available) >= 2:
        for cr in combo_results:
            total_imp = -(cr["gaps"]["race"] + cr["gaps"]["hisp"] + cr["gaps"]["gender"])
            if total_imp > 0.01:
                candidates.append({
                    "label": cr["label"],
                    "make_fn": lambda rec, _configs=cr["configs"]: (
                        _apply_combo(v10_fn(rec), rec, _configs)
                        if v10_fn(rec) else None),
                    "total_imp_perm": total_imp,
                    "perm_metrics": cr["metrics"],
                })

    # Sort by total improvement on perm
    candidates.sort(key=lambda x: -x["total_imp_perm"])
    candidates = candidates[:8]  # Top 8

    if not candidates:
        print("\n  No candidates improved V10 on perm holdout. Nothing to validate.")
    else:
        print("\n  Validating top %d configs on sealed holdout:" % len(candidates))
        print("  | %-30s | %-10s | %-10s | %-12s | %-12s | %-12s |" % (
            "Config", "Race(perm)", "Race(seal)", "Hisp(perm)", "Hisp(seal)", "Gndr(seal)"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 32, "-" * 12, "-" * 12, "-" * 14, "-" * 14, "-" * 14))

        for cand in candidates:
            m_seal = evaluate(v10_records, cand["make_fn"])
            m_perm = cand["perm_metrics"]

            r_repl = m_seal["race"] <= m_v10_sealed["race"] + 0.05  # replicated if not worse by >0.05
            h_repl = m_seal["hisp"] <= m_v10_sealed["hisp"] + 0.05
            notes = ""
            if m_seal["race"] < m_v10_sealed["race"] and m_seal["hisp"] < m_v10_sealed["hisp"]:
                notes = "BOTH REPLICATE"
            elif m_seal["race"] < m_v10_sealed["race"]:
                notes = "race replicates"
            elif m_seal["hisp"] < m_v10_sealed["hisp"]:
                notes = "hisp replicates"

            print("  | %-30s | %-10.3f | %-10.3f | %-12.3f | %-12.3f | %-12.3f | %s" % (
                cand["label"][:30],
                m_perm["race"], m_seal["race"],
                m_perm["hisp"], m_seal["hisp"],
                m_seal["gender"], notes))

    # V10 baseline reference
    print("\n  V10 baseline:")
    print("    Perm:   Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"],
        m_v10_perm["p20"], m_v10_perm["p30"]))
    print("    Sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_sealed["race"], m_v10_sealed["hisp"], m_v10_sealed["gender"],
        m_v10_sealed["p20"], m_v10_sealed["p30"]))

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


def _apply_combo(pred, rec, configs):
    """Apply multiple residual corrections in sequence."""
    if not pred:
        return None
    tier_fn_map = {
        "edu_tier": lambda r: r.get("edu_tier"),
        "size": lambda r: r.get("size_bucket"),
        "gap": lambda r: get_gap_quintile(r.get("edu_gap")),
    }
    for cfg in configs:
        tfn = tier_fn_map.get(cfg["type"])
        if tfn:
            pred = apply_residual_correction(pred, rec, cfg["offsets"], tfn, cfg["dampening"])
    return pred


if __name__ == "__main__":
    main()
