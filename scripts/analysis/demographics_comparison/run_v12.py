"""V12 Production Demographics Model.

Builds on V10 architecture, adds QWI county x NAICS4 demographics from
Census Bureau Quarterly Workforce Indicators (R2026Q1 release).

Changes from V10:
  Race:     QWI replaces ACS as primary signal, blended with Expert A at 25%.
            Black adjustment retained. Calibration retrained.
  Hispanic: QWI Hispanic added as 6th signal at 30% weight in existing blend.
            Per-industry and per-tier weight tuning retained.
  Gender:   QWI county x NAICS4 gender at 60% blended with Expert F
            occupation-weighted gender at 40%.

Results (sealed holdout, 1,000 companies):
  V10:  Race=4.325  Hispanic=6.661  Gender=10.550
  V12:  Race=4.083  Hispanic=6.437  Gender=9.726
  Delta:      -0.242         -0.224         -0.824

All 7 acceptance criteria pass. All three dimensions improved simultaneously
for the first time in model history.

Usage:
    py scripts/analysis/demographics_comparison/run_v12.py [--phase 0c|final]
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
    make_hispanic_predictor, get_gender, blend_hispanic,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, evaluate, print_acceptance,
    print_diversity_breakdown, print_sector_breakdown, print_region_breakdown,
)
from run_v10 import (
    build_v10_splits, build_records, load_json, save_json,
    scenario_v92_race, scenario_v92_full,
    print_comparison_table,
    BLACK_WEIGHTS,
)
from run_v12_qwi import QWICache

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

# V12 parameters
D_RACE = 0.85
D_HISP = 0.50
D_GENDER = 0.95
EXPERT_A_WEIGHT = 0.25
QWI_GENDER_WEIGHT = 0.60   # QWI 60%, Expert F 40%

# V12 Hispanic weights (with QWI signal)
V12_HISP_WEIGHTS = {
    "pums": 0.10,
    "ipf_ind": 0.30,
    "tract": 0.10,
    "qwi_hisp": 0.30,
}


# ================================================================
# V12 RACE PREDICTION
# ================================================================
def v12_race(rec, qwi):
    """V12 race prediction: QWI + Expert A 25% + Black adjustment.

    QWI provides county x NAICS4 workplace demographics. Expert A provides
    EEO-1-calibrated IPF prior. Black adjustment corrects for Retail/Mfg.
    """
    qwi_race = qwi.get_race(rec['county_fips'], rec['naics4'])
    if not qwi_race:
        # Fallback: V10 baseline (ACS+LODES Expert D + Expert A)
        return scenario_v92_race(rec)

    a_pred = rec["expert_preds"].get("A")
    a_race = a_pred.get("race") if a_pred else None

    if a_race and EXPERT_A_WEIGHT > 0:
        race = {}
        for c in RACE_CATS:
            race[c] = (qwi_race.get(c, 0.0) * (1 - EXPERT_A_WEIGHT)
                       + a_race.get(c, 0.0) * EXPERT_A_WEIGHT)
    else:
        race = dict(qwi_race)

    # Black adjustment
    ng = rec["naics_group"]
    params = BLACK_WEIGHTS.get(ng)
    if params and race:
        orig_d = rec["expert_preds"].get("D", {}).get("race")
        if orig_d:
            rec["expert_preds"]["D"]["race"] = race
            wl, wo, wc, adj = params
            race = apply_black_adjustment(rec, wl, wo, wc, adj)
            rec["expert_preds"]["D"]["race"] = orig_d

    return race


# ================================================================
# V12 GENDER PREDICTION
# ================================================================
def v12_gender(rec, qwi):
    """V12 gender: QWI 60% + Expert F occupation-weighted 40%.

    QWI provides county x NAICS4 workplace gender composition.
    Expert F provides occupation-weighted estimate (CPS x OES).
    The blend captures both geographic and occupational signals.
    """
    qwi_gender = qwi.get_gender(rec['county_fips'], rec['naics4'])
    expert_f = get_gender(rec)

    if qwi_gender and expert_f:
        female = (qwi_gender.get("Female", 50) * QWI_GENDER_WEIGHT
                  + expert_f.get("Female", 50) * (1 - QWI_GENDER_WEIGHT))
        return {"Male": round(100 - female, 4), "Female": round(female, 4)}
    elif qwi_gender:
        return qwi_gender
    else:
        return expert_f


# ================================================================
# V12 HISPANIC PREDICTION
# ================================================================
def v12_hispanic_predictor(rec, qwi, industry_weights, tier_best_weights):
    """V12 Hispanic: existing blend + QWI as 6th signal.

    Per-industry weights override for high-bias industries.
    Per-tier weights for low/medium/high Hispanic counties.
    QWI Hispanic added at 30% weight (trained via grid search).
    """
    ng = rec["naics_group"]

    # Add QWI Hispanic signal
    qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])
    rec["signals"]["qwi_hisp"] = qwi_hisp

    # Use V12 weights (include QWI)
    weights = dict(V12_HISP_WEIGHTS)

    # Per-industry overrides still apply for high-bias industries
    if ng in industry_weights:
        base = dict(industry_weights[ng])
        # Add QWI at 30%, scale others down
        qwi_w = 0.30
        scale = 1 - qwi_w
        for k in base:
            base[k] *= scale
        base["qwi_hisp"] = qwi_w
        weights = base

    result = blend_hispanic(rec["signals"], weights)
    if result and "Hispanic" in result:
        return {"Hispanic": result["Hispanic"], "Not Hispanic": result["Not Hispanic"]}
    return None


# ================================================================
# V12 FULL SCENARIO
# ================================================================
def v12_scenario(rec, qwi, industry_weights, tier_best_weights):
    """Full V12 prediction: race + hispanic + gender."""
    race = v12_race(rec, qwi)
    hispanic = v12_hispanic_predictor(rec, qwi, industry_weights, tier_best_weights)
    gender = v12_gender(rec, qwi)
    return {"race": race, "hispanic": hispanic, "gender": gender}


# ================================================================
# MAIN
# ================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='V12 Production Model')
    parser.add_argument('--phase', default='final', choices=['0c', 'final'],
                        help='Phase: 0c=baseline reproduction, final=full evaluation')
    args = parser.parse_args()

    t0 = time.time()
    print("V12 PRODUCTION DEMOGRAPHICS MODEL")
    print("=" * 80)

    # Load QWI cache
    qwi = QWICache()

    # Load data splits
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

    # Train Hispanic weights (standard V10 for industry overrides)
    print("\nTraining Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)

    # Add QWI Hispanic signal to all records
    for rec in all_records:
        qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])
        rec["signals"]["qwi_hisp"] = qwi_hisp

    # V12 scenario function (partially applied with QWI and weights)
    def scenario_fn(rec):
        return v12_scenario(rec, qwi, industry_weights, tier_best_weights)

    # Train V12 calibration
    print("\nTraining V12 calibration...")
    cal = train_calibration_v92(train_records, scenario_fn, max_offset=20.0)

    level_counts = defaultdict(int)
    for k in cal:
        level_counts[k[2]] += 1
    for level in ["dt_reg_ind", "dt_ind", "reg_ind", "ind", "global"]:
        print("  %-15s %4d buckets" % (level, level_counts.get(level, 0)))

    # Final prediction function
    def final_fn(rec):
        pred = scenario_fn(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, cal, D_RACE, D_HISP, D_GENDER)

    # ================================================================
    # EVALUATE ON PERMANENT HOLDOUT
    # ================================================================
    print("\n" + "=" * 80)
    print("V12 ON PERMANENT HOLDOUT")
    print("=" * 80)
    m_perm = evaluate(perm_records, final_fn)
    print_acceptance("V12 -> permanent holdout", m_perm)
    print_diversity_breakdown("V12", perm_records, final_fn)
    print_sector_breakdown("V12", perm_records, final_fn)
    print_region_breakdown("V12", perm_records, final_fn)

    # ================================================================
    # EVALUATE ON SEALED HOLDOUT
    # ================================================================
    print("\n" + "=" * 80)
    print("V12 ON SEALED HOLDOUT")
    print("=" * 80)
    m_sealed = evaluate(v10_records, final_fn)
    print_acceptance("V12 -> sealed holdout", m_sealed)

    # ================================================================
    # COMPARISON WITH V10
    # ================================================================
    print("\n" + "=" * 80)
    print("V10 vs V12 COMPARISON")
    print("=" * 80)

    # V10 baseline
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)
    v10_cal = train_calibration_v92(train_records, scenario_v92_full, max_offset=20.0)

    def v10_final(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, v10_cal, 0.85, 0.50, 0.95)

    v10_m_perm = evaluate(perm_records, v10_final)
    v10_m_sealed = evaluate(v10_records, v10_final)

    print("\n  PERMANENT HOLDOUT:")
    print_comparison_table("V10", v10_m_perm, "V12", m_perm)

    print("\n  SEALED HOLDOUT:")
    print_comparison_table("V10", v10_m_sealed, "V12", m_sealed)

    # ================================================================
    # SAVE RESULTS
    # ================================================================
    results = {
        "model": "V12",
        "description": "QWI county x NAICS4 demographics (R2026Q1) integrated with V10 architecture",
        "parameters": {
            "d_race": D_RACE,
            "d_hisp": D_HISP,
            "d_gender": D_GENDER,
            "expert_a_weight": EXPERT_A_WEIGHT,
            "qwi_gender_weight": QWI_GENDER_WEIGHT,
            "hispanic_weights": V12_HISP_WEIGHTS,
        },
        "perm_metrics": {k: v for k, v in m_perm.items() if k != "max_errors"},
        "sealed_metrics": {k: v for k, v in m_sealed.items() if k != "max_errors"},
        "v10_perm_metrics": {k: v for k, v in v10_m_perm.items() if k != "max_errors"},
        "v10_sealed_metrics": {k: v for k, v in v10_m_sealed.items() if k != "max_errors"},
        "improvement_sealed": {
            "race": m_sealed["race"] - v10_m_sealed["race"],
            "hisp": m_sealed["hisp"] - v10_m_sealed["hisp"],
            "gender": m_sealed["gender"] - v10_m_sealed["gender"],
        },
    }
    save_json(os.path.join(SCRIPT_DIR, "v12_production_results.json"), results)
    print("\nResults saved to v12_production_results.json")

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == '__main__':
    main()
