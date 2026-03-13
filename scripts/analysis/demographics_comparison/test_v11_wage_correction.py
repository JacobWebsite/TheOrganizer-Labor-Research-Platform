"""V11 Wage-Tier Residual Correction Test.

Tests whether QCEW county x industry wage data can improve V10 predictions
via residual corrections grouped by wage tier.

Hypothesis: Companies in low-wage areas may have systematically different
demographic compositions (especially Hispanic) that V10 underpredicts.

Steps:
  1. Load V10 baseline (same setup as test_v11_extended_signals.py)
  2. Load QCEW county x industry wages (NAICS3 level)
  3. Compute wage_ratio = local_wage / national_avg_wage per company
  4. Assign wage tiers: low (<0.80), below_avg (0.80-1.00), above_avg (1.00-1.20), high (>1.20)
  5. Run diagnostic: V10 MAE by wage tier on training set
  6. Train residual corrections by wage tier
  7. Test at dampening [0.25, 0.50, 0.75, 1.0] on perm holdout
  8. Test continuous wage ratio modifier for Hispanic dimension
  9. If anything improves, validate on sealed holdout

Usage:
    py scripts/analysis/demographics_comparison/test_v11_wage_correction.py
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
from test_v11_extended_signals import (
    train_residual_correction, apply_residual_correction,
    diagnostic_mae_by_tier, check_spread,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]


# ================================================================
# WAGE SIGNAL HELPERS
# ================================================================
def get_wage_tier(ratio):
    """Classify wage ratio into tiers."""
    if ratio is None:
        return None
    if ratio < 0.80:
        return "low"
    elif ratio < 1.00:
        return "below_avg"
    elif ratio < 1.20:
        return "above_avg"
    else:
        return "high"


# ================================================================
# MAIN
# ================================================================
def main():
    t0 = time.time()
    print("V11 Wage-Tier Residual Correction Test")
    print("=" * 80)

    # ============================================================
    # PHASE 0: Setup (same as test_v11_extended_signals.py)
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
    # PHASE 1: Load QCEW Wage Data
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 1: Load QCEW Wage Data")
    print("=" * 80)

    # County-level wages (area_fips NOT LIKE '%000')
    print("\n  Loading county x NAICS3 wages...")
    cur.execute("""
        SELECT area_fips, industry_code, avg_annual_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips NOT LIKE '%%000'
    """)
    qcew_county_wages = {}
    for row in cur.fetchall():
        fips = row["area_fips"]
        ind = row["industry_code"]
        qcew_county_wages[(fips, ind)] = float(row["avg_annual_pay"])
    print("  Loaded %d (county, NAICS3) wage entries" % len(qcew_county_wages))

    # State-level wages as fallback (area_fips like 'XX000')
    print("  Loading state x NAICS3 wages (fallback)...")
    cur.execute("""
        SELECT area_fips, industry_code, avg_annual_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips LIKE '%%000'
    """)
    qcew_state_wages = {}
    for row in cur.fetchall():
        state_fips_2 = row["area_fips"][:2]
        ind = row["industry_code"]
        qcew_state_wages[(state_fips_2, ind)] = float(row["avg_annual_pay"])
    print("  Loaded %d (state, NAICS3) wage entries" % len(qcew_state_wages))

    # National average wage per NAICS3 (average across county-level entries)
    print("  Computing national NAICS3 wage averages...")
    cur.execute("""
        SELECT industry_code, AVG(avg_annual_pay) as avg_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips NOT LIKE '%%000'
        GROUP BY industry_code
    """)
    national_wages = {}
    for row in cur.fetchall():
        national_wages[row["industry_code"]] = float(row["avg_pay"])
    print("  Loaded %d national NAICS3 wage averages" % len(national_wages))

    # ============================================================
    # PHASE 2: Assign Wage Ratios to Companies
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 2: Assign Wage Ratios to Companies")
    print("=" * 80)

    def compute_wage_ratio(rec):
        """Compute wage_ratio = local_wage / national_avg_wage."""
        county = rec.get("county_fips", "")
        naics4 = rec.get("naics4", "")
        state_fips = rec.get("state_fips", "")
        naics3 = naics4[:3] if len(naics4) >= 3 else naics4

        # Try county x NAICS3
        local_wage = qcew_county_wages.get((county, naics3))
        source = "county"

        # Fallback to state x NAICS3
        if not local_wage:
            local_wage = qcew_state_wages.get((state_fips, naics3))
            source = "state"

        nat_wage = national_wages.get(naics3)

        if local_wage and nat_wage and nat_wage > 0:
            return local_wage / nat_wage, source
        return None, None

    # Assign wage ratio and tier to all records
    wage_coverage = 0
    source_counts = defaultdict(int)
    tier_counts = defaultdict(int)
    wage_ratios_all = []

    for rec in all_records:
        ratio, source = compute_wage_ratio(rec)
        rec["wage_ratio"] = ratio
        rec["wage_tier"] = get_wage_tier(ratio)
        if ratio is not None:
            wage_coverage += 1
            source_counts[source] += 1
            tier_counts[rec["wage_tier"]] += 1
            wage_ratios_all.append(ratio)

    print("  Wage ratio coverage: %d / %d (%.1f%%)" % (
        wage_coverage, len(all_records), 100.0 * wage_coverage / len(all_records)))
    print("  Source breakdown:")
    for src in ["county", "state"]:
        print("    %-8s: %d" % (src, source_counts.get(src, 0)))
    print("  Tier distribution:")
    for tier in ["low", "below_avg", "above_avg", "high"]:
        print("    %-12s: %d" % (tier, tier_counts.get(tier, 0)))

    if wage_ratios_all:
        wage_ratios_all.sort()
        n = len(wage_ratios_all)
        print("  Wage ratio stats:")
        print("    Min=%.3f  P25=%.3f  Median=%.3f  P75=%.3f  Max=%.3f  Mean=%.3f" % (
            wage_ratios_all[0],
            wage_ratios_all[n // 4],
            wage_ratios_all[n // 2],
            wage_ratios_all[3 * n // 4],
            wage_ratios_all[-1],
            sum(wage_ratios_all) / n))

    # ============================================================
    # PHASE 3: Diagnostic -- V10 MAE by Wage Tier (Training Set)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 3: Diagnostic -- V10 MAE by Wage Tier (Training Set)")
    print("=" * 80)

    wage_diag = diagnostic_mae_by_tier(
        train_records, v10_fn,
        lambda r: r.get("wage_tier"),
        "Wage Tier", dims_all)

    skip_dims = {}
    for dim_name in ["race", "hispanic", "gender"]:
        dim_key = "hisp" if dim_name == "hispanic" else dim_name
        skip_dims[dim_name] = not check_spread(wage_diag, dim_key)

    # Also show MAE on perm holdout by wage tier for reference
    print("\n  V10 MAE by wage tier (perm holdout):")
    perm_wage_diag = diagnostic_mae_by_tier(
        perm_records, v10_fn,
        lambda r: r.get("wage_tier"),
        "Wage Tier", dims_all)

    # ============================================================
    # PHASE 4: Train + Test Wage Tier Residual Corrections
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 4: Wage Tier Residual Corrections")
    print("=" * 80)

    wage_configs = []

    if all(skip_dims.values()):
        print("\n  All dimensions below 0.1pp spread -- skipping wage corrections")
    else:
        print("\n  Training residual corrections by wage tier...")
        wage_offsets = train_residual_correction(
            train_records, v10_fn,
            lambda r: r.get("wage_tier"),
            dims_all, min_bucket=30, max_offset=10.0)

        print("  Trained %d correction buckets" % len(wage_offsets))
        for k, (off, n) in sorted(wage_offsets.items()):
            print("    %-40s: offset=%+.2f n=%d" % (str(k), off, n))

        # Grid search dampening on perm holdout
        print("\n  Testing wage tier corrections (perm holdout):")
        print("  | %-10s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
            "Dampening", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 12, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

        for damp in [0.25, 0.50, 0.75, 1.0]:
            def wage_fn(rec, _d=damp, _off=wage_offsets):
                pred = v10_fn(rec)
                if not pred:
                    return None
                return apply_residual_correction(pred, rec, _off,
                                                 lambda r: r.get("wage_tier"), _d)

            m = evaluate(perm_records, wage_fn)
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
            wage_configs.append({
                "type": "wage_tier", "dampening": damp, "metrics": m,
                "gaps": {"race": r_gap, "hisp": h_gap, "gender": g_gap},
                "offsets": wage_offsets,
            })

    # ============================================================
    # PHASE 5: Continuous Wage Ratio Modifier (Hispanic-specific)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 5: Continuous Wage Ratio -> Hispanic Modifier")
    print("=" * 80)

    # Train linear coefficient: wage_ratio (centered) predicts Hispanic error
    train_wage_hisp = []
    for rec in train_records:
        if rec["wage_ratio"] is None:
            continue
        pred = v10_fn(rec)
        if not pred or not pred.get("hispanic"):
            continue
        actual_h = rec["truth"]["hispanic"].get("Hispanic")
        pred_h = pred["hispanic"].get("Hispanic")
        if actual_h is not None and pred_h is not None:
            train_wage_hisp.append((rec["wage_ratio"], pred_h - actual_h))

    if len(train_wage_hisp) < 100:
        print("  Insufficient data for continuous Hispanic modifier (%d records)" % len(train_wage_hisp))
    else:
        # Center the wage ratio
        wage_mean = sum(x for x, _ in train_wage_hisp) / len(train_wage_hisp)
        print("  Mean wage ratio: %.4f" % wage_mean)
        print("  N records with wage + Hispanic data: %d" % len(train_wage_hisp))

        # OLS: y = beta * (wage_ratio - mean)
        # where y = pred_hispanic - actual_hispanic (positive = overprediction)
        sum_xy = sum((x - wage_mean) * y for x, y in train_wage_hisp)
        sum_xx = sum((x - wage_mean) ** 2 for x, y in train_wage_hisp)
        beta_hisp = sum_xy / sum_xx if sum_xx > 0 else 0.0

        print("  Linear Hispanic beta: %.4f" % beta_hisp)
        print("  Interpretation: +0.10 wage ratio --> Hispanic prediction %+.3fpp correction" % (-beta_hisp * 0.10))
        print("  (Positive beta = high-wage areas overpredicted --> correct downward)")

        # Diagnostic: correlation between wage ratio and Hispanic error
        mean_y = sum(y for _, y in train_wage_hisp) / len(train_wage_hisp)
        ss_res = sum((y - beta_hisp * (x - wage_mean)) ** 2 for x, y in train_wage_hisp)
        ss_tot = sum((y - mean_y) ** 2 for x, y in train_wage_hisp)
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        print("  R-squared (wage ratio -> Hispanic error): %.6f" % r_squared)

        # Also check race and gender betas for reference
        for dim_name, dim_key, cats in [
            ("race", "race", RACE_CATS),
            ("gender", "gender", GENDER_CATS),
        ]:
            dim_xy = []
            for rec in train_records:
                if rec["wage_ratio"] is None:
                    continue
                pred = v10_fn(rec)
                if not pred or not pred.get(dim_name):
                    continue
                a = rec["truth"].get(dim_name)
                if not a:
                    continue
                main_cat = cats[0]
                if main_cat in pred[dim_name] and main_cat in a:
                    dim_xy.append((rec["wage_ratio"], pred[dim_name][main_cat] - a[main_cat]))

            if len(dim_xy) > 100:
                dim_mean = sum(x for x, _ in dim_xy) / len(dim_xy)
                sxy = sum((x - dim_mean) * y for x, y in dim_xy)
                sxx = sum((x - dim_mean) ** 2 for x, y in dim_xy)
                dim_beta = sxy / sxx if sxx > 0 else 0.0
                print("  %s beta (reference): %.4f (%s, n=%d)" % (
                    dim_name, dim_beta, cats[0], len(dim_xy)))

        # Test scaled betas on perm holdout
        print("\n  Testing continuous Hispanic modifier (perm holdout):")
        print("  | %-12s | %-10s | %-8s | %-8s | %-10s |" % (
            "Beta Scale", "Beta Used", "Hisp MAE", "Delta", "Notes"))
        print("  |%s|%s|%s|%s|%s|" % (
            "-" * 14, "-" * 12, "-" * 10, "-" * 10, "-" * 12))

        hisp_continuous_configs = []
        for beta_scale in [0.25, 0.50, 0.75, 1.0]:
            beta_used = beta_hisp * beta_scale

            def linear_hisp_fn(rec, _beta=beta_used, _mean=wage_mean):
                pred = v10_fn(rec)
                if not pred or not pred.get("hispanic"):
                    return pred
                if rec["wage_ratio"] is None:
                    return pred
                correction = _beta * (rec["wage_ratio"] - _mean)
                result = {}
                for dim_name in ["race", "gender"]:
                    result[dim_name] = pred.get(dim_name)
                hv = pred["hispanic"].get("Hispanic", 0.0) - correction
                hv = max(0.0, min(100.0, hv))
                result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
                return result

            m = evaluate(perm_records, linear_hisp_fn)
            gap = m["hisp"] - m_v10_perm["hisp"]
            note = "IMPROVED" if gap < -0.01 else ("neutral" if abs(gap) < 0.01 else "worse")
            print("  | %-12.2f | %-10.4f | %-8.3f | %+7.3f | %-10s |" % (
                beta_scale, beta_used, m["hisp"], gap, note))
            hisp_continuous_configs.append({
                "type": "hisp_continuous", "beta_scale": beta_scale,
                "beta": beta_used, "wage_mean": wage_mean,
                "metrics": m, "hisp_gap": gap,
            })

        # Also test combined: tier correction + continuous Hispanic
        if wage_configs:
            best_tier_cfg = None
            best_tier_imp = 0.0
            for c in wage_configs:
                total_imp = -(c["gaps"]["race"] + c["gaps"]["hisp"] + c["gaps"]["gender"])
                if total_imp > best_tier_imp:
                    best_tier_imp = total_imp
                    best_tier_cfg = c

            if best_tier_cfg:
                print("\n  Testing combined: wage tier (d=%.2f) + continuous Hispanic:" % (
                    best_tier_cfg["dampening"]))
                print("  | %-12s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
                    "Beta Scale", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
                print("  |%s|%s|%s|%s|%s|%s|" % (
                    "-" * 14, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

                for beta_scale in [0.25, 0.50, 0.75, 1.0]:
                    beta_used = beta_hisp * beta_scale
                    _tier_off = best_tier_cfg["offsets"]
                    _tier_damp = best_tier_cfg["dampening"]

                    def combo_fn(rec, _beta=beta_used, _mean=wage_mean,
                                 _toff=_tier_off, _tdamp=_tier_damp):
                        pred = v10_fn(rec)
                        if not pred:
                            return None
                        # Apply tier correction first
                        pred = apply_residual_correction(pred, rec, _toff,
                                                         lambda r: r.get("wage_tier"), _tdamp)
                        # Then apply continuous Hispanic
                        if rec["wage_ratio"] is not None and pred.get("hispanic"):
                            correction = _beta * (rec["wage_ratio"] - _mean)
                            hv = pred["hispanic"].get("Hispanic", 0.0) - correction
                            hv = max(0.0, min(100.0, hv))
                            pred = dict(pred)
                            pred["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
                        return pred

                    m = evaluate(perm_records, combo_fn)
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

                    print("  | %-12.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                        beta_scale, m["race"], m["hisp"], m["gender"],
                        m["p20"], m["p30"], " ".join(notes)))

    # ============================================================
    # PHASE 6: Sealed Holdout Validation (if improvements found)
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 6: Sealed Holdout Validation")
    print("=" * 80)

    # Collect candidates that improved on perm
    candidates = []

    # Tier-based configs
    for c in wage_configs:
        total_imp = -(c["gaps"]["race"] + c["gaps"]["hisp"] + c["gaps"]["gender"])
        if total_imp > 0.01:
            _off = c["offsets"]
            _damp = c["dampening"]
            candidates.append({
                "label": "wage_tier(d=%.2f)" % c["dampening"],
                "make_fn": lambda rec, _o=_off, _d=_damp: (
                    apply_residual_correction(v10_fn(rec), rec, _o,
                                              lambda r: r.get("wage_tier"), _d)
                    if v10_fn(rec) else None),
                "total_imp_perm": total_imp,
                "perm_metrics": c["metrics"],
            })

    # Continuous Hispanic configs
    if len(train_wage_hisp) >= 100:
        for c in hisp_continuous_configs:
            if c["hisp_gap"] < -0.01:
                _beta = c["beta"]
                _mean = c["wage_mean"]
                candidates.append({
                    "label": "hisp_continuous(b=%.2f)" % c["beta_scale"],
                    "make_fn": lambda rec, _b=_beta, _m=_mean: (
                        _apply_hisp_continuous(v10_fn(rec), rec, _b, _m)
                        if v10_fn(rec) else None),
                    "total_imp_perm": -c["hisp_gap"],
                    "perm_metrics": c["metrics"],
                })

    # Sort by total improvement
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

            notes = ""
            if m_seal["race"] < m_v10_sealed["race"] and m_seal["hisp"] < m_v10_sealed["hisp"]:
                notes = "BOTH REPLICATE"
            elif m_seal["race"] < m_v10_sealed["race"]:
                notes = "race replicates"
            elif m_seal["hisp"] < m_v10_sealed["hisp"]:
                notes = "hisp replicates"
            elif m_seal["gender"] < m_v10_sealed["gender"]:
                notes = "gender replicates"

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

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    any_improvement = False
    if wage_configs:
        best_race = min(c["gaps"]["race"] for c in wage_configs)
        best_hisp = min(c["gaps"]["hisp"] for c in wage_configs)
        best_gender = min(c["gaps"]["gender"] for c in wage_configs)
        print("  Best wage tier improvements (perm holdout):")
        print("    Race:    %+.3f pp" % best_race)
        print("    Hisp:    %+.3f pp" % best_hisp)
        print("    Gender:  %+.3f pp" % best_gender)
        if best_race < -0.01 or best_hisp < -0.01 or best_gender < -0.01:
            any_improvement = True

    if len(train_wage_hisp) >= 100 and hisp_continuous_configs:
        best_cont = min(c["hisp_gap"] for c in hisp_continuous_configs)
        print("  Best continuous Hispanic improvement: %+.3f pp" % best_cont)
        if best_cont < -0.01:
            any_improvement = True

    if not any_improvement:
        print("\n  CONCLUSION: Wage tier signal does NOT improve V10.")
        print("  The model's existing calibration hierarchy already captures")
        print("  wage-related demographic variation through county/industry tiers.")
    else:
        print("\n  CONCLUSION: Wage signal shows some improvement -- check sealed validation above.")

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


def _apply_hisp_continuous(pred, rec, beta, wage_mean):
    """Apply continuous Hispanic wage correction."""
    if not pred:
        return None
    if rec.get("wage_ratio") is None or not pred.get("hispanic"):
        return pred
    correction = beta * (rec["wage_ratio"] - wage_mean)
    result = {}
    for dim_name in ["race", "gender"]:
        result[dim_name] = pred.get(dim_name)
    hv = pred["hispanic"].get("Hispanic", 0.0) - correction
    hv = max(0.0, min(100.0, hv))
    result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
    return result


if __name__ == "__main__":
    main()
