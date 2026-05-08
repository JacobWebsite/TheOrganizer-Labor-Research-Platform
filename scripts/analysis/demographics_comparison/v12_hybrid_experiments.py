"""V12 Hybrid Experiments: Combine QWI data with existing expert architecture.

Tests whether keeping structural aspects of old experts improves on raw QWI:
  H1: IPF(QWI, LODES) — reconcile two county-level sources
  H2: QWI + Expert A blend at various weights (0%, 5%, 10%, 15%, 25%)
  H3: QWI gender blended with Expert F at various weights
  H4: QWI Hispanic added as new signal in existing Hispanic blend
  H5: Full best-of-everything (combine winners from H1-H4)

Usage:
    py scripts/analysis/demographics_comparison/v12_hybrid_experiments.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from config import RACE_CATEGORIES as RACE_CATS
from methodologies_v5 import smoothed_ipf

from run_v9_2 import (
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_gender, blend_hispanic,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, evaluate,
)
from run_v10 import (
    build_v10_splits, build_records, load_json, save_json,
    scenario_v92_race, scenario_v92_full,
    BLACK_WEIGHTS,
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


def apply_black_adj(rec, race):
    """Apply Black adjustment to a race dict, preserving original expert D."""
    ng = rec["naics_group"]
    params = BLACK_WEIGHTS.get(ng)
    if not params or not race:
        return race
    orig_d = rec["expert_preds"].get("D", {}).get("race")
    if not orig_d:
        return race
    rec["expert_preds"]["D"]["race"] = race
    wl, wo, wc, adj = params
    result = apply_black_adjustment(rec, wl, wo, wc, adj)
    rec["expert_preds"]["D"]["race"] = orig_d
    return result


# ================================================================
# H1: IPF(QWI, LODES) — reconcile two county-level sources
# ================================================================
def scenario_h1_ipf_qwi_lodes(rec, qwi, expert_a_weight=0.0):
    """IPF blend of QWI (county x NAICS4) with LODES (county x NAICS2).

    QWI provides industry-specific county signal. LODES provides independent
    county workplace demographics. IPF reconciles them.
    """
    qwi_race = qwi.get_race(rec['county_fips'], rec['naics4'])
    if not qwi_race:
        return scenario_v92_race(rec)

    # Get LODES county demographics from cached loaders
    # LODES is stored in expert_preds indirectly. Extract the raw LODES signal.
    # The D expert already blended ACS+LODES. We need raw LODES.
    # It's available through the cached loaders in the record signals.
    # Actually, let's get it from the expert_preds structure.
    # The 'V6-Full' expert has raw sub-signals. But simplest: use IPF.

    # Get raw LODES from the data loaders through expert D
    # Expert D race = smoothed_ipf(ACS, LODES). We want smoothed_ipf(QWI, LODES).
    # We can get LODES from the county_minority_pct in the record.
    # Actually, the county LODES data IS accessible — it's what get_lodes_race returns.
    # But we don't have the cached loader here. Let's reconstruct from the
    # signals we DO have.

    # The expert_preds contain the pre-computed expert outputs, not raw signals.
    # For LODES, we need county-level race. The closest proxy is using
    # the difference between Expert D (ACS+LODES IPF) and Expert A (ACS-only IPF).
    # Actually, let's just use QWI directly since it already has county-level data.
    # The real value of IPF here is reconciling QWI (administrative records)
    # with LODES (workplace area characteristics).

    # Use smoothed_ipf to blend QWI with the existing D prediction
    d_pred = rec["expert_preds"].get("D")
    d_race = d_pred.get("race") if d_pred else None

    if d_race:
        # IPF: use QWI as row margins, D as column margins
        ipf_result = smoothed_ipf(qwi_race, d_race, RACE_CATS)
        if not ipf_result:
            ipf_result = qwi_race
    else:
        ipf_result = qwi_race

    # Optionally blend with Expert A
    if expert_a_weight > 0:
        a_pred = rec["expert_preds"].get("A")
        a_race = a_pred.get("race") if a_pred else None
        if a_race:
            race = {}
            for c in RACE_CATS:
                race[c] = ipf_result.get(c, 0.0) * (1 - expert_a_weight) + a_race.get(c, 0.0) * expert_a_weight
            ipf_result = race

    return apply_black_adj(rec, ipf_result)


# ================================================================
# H2: QWI + Expert A at various blend weights
# ================================================================
def scenario_h2_qwi_expert_a(rec, qwi, a_weight=0.10):
    """QWI as primary race signal, Expert A at variable weight."""
    qwi_race = qwi.get_race(rec['county_fips'], rec['naics4'])
    if not qwi_race:
        return scenario_v92_race(rec)

    a_pred = rec["expert_preds"].get("A")
    a_race = a_pred.get("race") if a_pred else None

    if a_race and a_weight > 0:
        race = {}
        for c in RACE_CATS:
            race[c] = qwi_race.get(c, 0.0) * (1 - a_weight) + a_race.get(c, 0.0) * a_weight
    else:
        race = qwi_race

    return apply_black_adj(rec, race)


# ================================================================
# H3: QWI gender blended with Expert F
# ================================================================
def get_gender_h3(rec, qwi, qwi_weight=0.50):
    """Blend QWI county x NAICS4 gender with Expert F occupation-weighted gender."""
    qwi_gender = qwi.get_gender(rec['county_fips'], rec['naics4'])
    expert_f_gender = get_gender(rec)  # Expert F from V10

    if qwi_gender and expert_f_gender:
        female = (qwi_gender.get("Female", 50) * qwi_weight
                  + expert_f_gender.get("Female", 50) * (1 - qwi_weight))
        return {"Male": round(100 - female, 4), "Female": round(female, 4)}
    elif qwi_gender:
        return qwi_gender
    else:
        return expert_f_gender


# ================================================================
# H4: QWI Hispanic as additional signal in blend
# ================================================================
def make_hispanic_predictor_with_qwi(industry_weights, tier_best_weights, default_weights, qwi):
    """Create Hispanic predictor that includes QWI as a signal source."""
    def predict(rec):
        ng = rec["naics_group"]

        # Get QWI Hispanic
        qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])

        # Determine base weights
        if ng in industry_weights:
            weights = dict(industry_weights[ng])
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
            weights = dict(tier_best_weights.get(tier, default_weights))

        # Add QWI Hispanic as a signal
        if qwi_hisp:
            rec["signals"]["qwi_hisp"] = qwi_hisp
            # Give QWI 20% weight, reduce others proportionally
            qwi_w = 0.20
            scale = 1 - qwi_w
            for k in weights:
                weights[k] *= scale
            weights["qwi_hisp"] = qwi_w

        result = blend_hispanic(rec["signals"], weights)
        if result and "Hispanic" in result:
            return {"Hispanic": result["Hispanic"], "Not Hispanic": result["Not Hispanic"]}
        return None
    return predict


def retrain_hispanic_with_qwi(train_records, qwi):
    """Full grid search for Hispanic weights including QWI as a signal."""
    # Add QWI Hispanic signal to all records
    for rec in train_records:
        qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])
        rec["signals"]["qwi_hisp"] = qwi_hisp

    # Grid search across all signal weights including QWI
    best_mae = 999
    best_weights = None

    for w_pums in [0.1, 0.2, 0.3]:
        for w_ipf in [0.1, 0.2, 0.3]:
            for w_tract in [0.1, 0.2, 0.3, 0.4]:
                for w_qwi in [0.0, 0.1, 0.15, 0.2, 0.25, 0.3]:
                    weights = {"pums": w_pums, "ipf_ind": w_ipf,
                               "tract": w_tract, "qwi_hisp": w_qwi}
                    errs = []
                    for rec in train_records:
                        result = blend_hispanic(rec["signals"], weights)
                        if result and "Hispanic" in result:
                            errs.append(abs(result["Hispanic"] - rec["truth_hispanic"]))
                    if errs:
                        m = sum(errs) / len(errs)
                        if m < best_mae:
                            best_mae = m
                            best_weights = weights.copy()

    active = {k: v for k, v in best_weights.items() if v > 0}
    print("  Best Hispanic weights (with QWI): MAE=%.3f weights=%s" % (best_mae, active))
    return best_weights, best_mae


def main():
    t0 = time.time()
    print("V12 HYBRID EXPERIMENTS")
    print("=" * 100)

    qwi = QWICache()

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

    # Standard Hispanic weights
    print("\nTraining standard Hispanic weights...")
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    industry_weights = train_industry_weights(train_records)
    tier_best_weights = train_tier_weights(train_records)
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)
    for rec in all_records:
        rec["hispanic_pred"] = hisp_pred_fn(rec)

    # ================================================================
    # Reference baselines
    # ================================================================
    print("\n" + "=" * 100)
    print("REFERENCE BASELINES")
    print("=" * 100)

    def eval_scenario(name, scenario_fn, holdout_records):
        cal = train_calibration_v92(train_records, scenario_fn, max_offset=20.0)
        def final_fn(rec, _sfn=scenario_fn, _cal=cal):
            pred = _sfn(rec)
            if not pred:
                return None
            return apply_calibration_v92(pred, rec, _cal, D_RACE, D_HISP, D_GENDER)
        m = evaluate(holdout_records, final_fn)
        return m, cal

    # V10 baseline
    v10_m_perm, v10_cal = eval_scenario("V10", scenario_v92_full, perm_records)
    v10_m_sealed = evaluate(v10_records, lambda rec: apply_calibration_v92(
        scenario_v92_full(rec), rec, v10_cal, D_RACE, D_HISP, D_GENDER) if scenario_v92_full(rec) else None)

    # V12a baseline (QWI replaces ACS, standard Hispanic, standard gender)
    def v12a_scenario(rec):
        race = scenario_qwi_replace_acs(rec, qwi)
        return {"race": race, "hispanic": rec.get("hispanic_pred"), "gender": get_gender(rec)}
    v12a_m_perm, v12a_cal = eval_scenario("V12a", v12a_scenario, perm_records)

    # V12f baseline (QWI race + QWI gender)
    def v12f_scenario(rec):
        race = scenario_qwi_replace_acs(rec, qwi)
        qwi_g = qwi.get_gender(rec['county_fips'], rec['naics4'])
        gender = qwi_g if qwi_g else get_gender(rec)
        return {"race": race, "hispanic": rec.get("hispanic_pred"), "gender": gender}
    v12f_m_perm, v12f_cal = eval_scenario("V12f", v12f_scenario, perm_records)

    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Scenario", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))
    for name, m in [("V10 baseline", v10_m_perm),
                    ("V12a (QWI race only)", v12a_m_perm),
                    ("V12f (QWI race + QWI gender)", v12f_m_perm)]:
        print("  %-40s | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
            name, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"]))

    # ================================================================
    # H1: IPF(QWI, Expert D) — reconcile QWI with existing D blend
    # ================================================================
    print("\n" + "=" * 100)
    print("H1: IPF(QWI, Expert D) — reconcile QWI with D's ACS+LODES blend")
    print("=" * 100)

    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Scenario", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))

    for a_w in [0.0, 0.05, 0.10, 0.15]:
        def h1_scenario(rec, _aw=a_w):
            race = scenario_h1_ipf_qwi_lodes(rec, qwi, expert_a_weight=_aw)
            return {"race": race, "hispanic": rec.get("hispanic_pred"), "gender": get_gender(rec)}
        m, _ = eval_scenario("H1 IPF(QWI,D) A=%.0f%%" % (a_w * 100), h1_scenario, perm_records)
        print("  H1: IPF(QWI, D) + A=%.0f%%              | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
            a_w * 100, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"]))

    # ================================================================
    # H2: QWI + Expert A weight sweep
    # ================================================================
    print("\n" + "=" * 100)
    print("H2: QWI + Expert A weight sweep")
    print("=" * 100)

    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Scenario", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))

    best_race = 999
    best_a = 0
    for a_w in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]:
        def h2_scenario(rec, _aw=a_w):
            race = scenario_h2_qwi_expert_a(rec, qwi, a_weight=_aw)
            return {"race": race, "hispanic": rec.get("hispanic_pred"), "gender": get_gender(rec)}
        m, _ = eval_scenario("H2 A=%d%%" % (a_w * 100), h2_scenario, perm_records)
        marker = ""
        if m["race"] < best_race and m["p30"] <= 6.5:
            best_race = m["race"]
            best_a = a_w
            marker = " BEST"
        print("  H2: QWI + Expert A=%.0f%%                | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |%s" % (
            a_w * 100, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"], marker))

    print("  Best Expert A weight: %.0f%% (Race MAE: %.3f)" % (best_a * 100, best_race))

    # ================================================================
    # H3: QWI gender + Expert F blend
    # ================================================================
    print("\n" + "=" * 100)
    print("H3: QWI gender + Expert F occupation-weighted gender blend")
    print("=" * 100)

    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Scenario", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))

    best_gender = 999
    best_gw = 0
    for gw in [0.0, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]:
        def h3_scenario(rec, _gw=gw):
            race = scenario_qwi_replace_acs(rec, qwi)
            hispanic = rec.get("hispanic_pred")
            gender = get_gender_h3(rec, qwi, qwi_weight=_gw)
            return {"race": race, "hispanic": hispanic, "gender": gender}
        m, _ = eval_scenario("H3 QWI_gender=%.0f%%" % (gw * 100), h3_scenario, perm_records)
        marker = ""
        if m["gender"] < best_gender:
            best_gender = m["gender"]
            best_gw = gw
            marker = " BEST"
        label = "Expert F only" if gw == 0 else ("QWI only" if gw == 1.0 else "QWI %.0f%% / F %.0f%%" % (gw*100, (1-gw)*100))
        print("  H3: %-34s | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |%s" % (
            label, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"], marker))

    print("  Best QWI gender weight: %.0f%% (Gender MAE: %.3f)" % (best_gw * 100, best_gender))

    # ================================================================
    # H4: QWI Hispanic as additional signal
    # ================================================================
    print("\n" + "=" * 100)
    print("H4: QWI Hispanic added to existing Hispanic blend")
    print("=" * 100)

    # Add QWI Hispanic signal to all records
    for rec in all_records:
        qwi_hisp = qwi.get_hispanic(rec['county_fips'], rec['naics4'])
        rec["signals"]["qwi_hisp"] = qwi_hisp

    # Grid search best weights with QWI
    print("\n  Grid searching Hispanic weights with QWI signal...")
    best_hisp_weights, best_hisp_mae_train = retrain_hispanic_with_qwi(train_records, qwi)

    # Apply best weights
    def make_hisp_pred_with_qwi(weights):
        def predict(rec):
            result = blend_hispanic(rec["signals"], weights)
            if result and "Hispanic" in result:
                return {"Hispanic": result["Hispanic"], "Not Hispanic": result["Not Hispanic"]}
            return None
        return predict

    hisp_with_qwi_fn = make_hisp_pred_with_qwi(best_hisp_weights)
    for rec in all_records:
        rec["hispanic_pred_qwi"] = hisp_with_qwi_fn(rec)

    # Compare: V10 Hispanic vs V10+QWI Hispanic
    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Scenario", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))

    # Without QWI Hispanic
    def h4_no_qwi(rec):
        race = scenario_qwi_replace_acs(rec, qwi)
        return {"race": race, "hispanic": rec.get("hispanic_pred"), "gender": get_gender(rec)}
    m_no, _ = eval_scenario("H4 standard Hispanic", h4_no_qwi, perm_records)

    # With QWI Hispanic
    def h4_with_qwi(rec):
        race = scenario_qwi_replace_acs(rec, qwi)
        return {"race": race, "hispanic": rec.get("hispanic_pred_qwi"), "gender": get_gender(rec)}
    m_with, _ = eval_scenario("H4 Hispanic+QWI", h4_with_qwi, perm_records)

    print("  H4: Standard Hispanic                 | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        m_no["race"], m_no["hisp"], m_no["gender"], m_no["p20"], m_no["p30"]))
    print("  H4: Hispanic+QWI signal               | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        m_with["race"], m_with["hisp"], m_with["gender"], m_with["p20"], m_with["p30"]))
    hisp_delta = m_with["hisp"] - m_no["hisp"]
    print("  Hispanic improvement from QWI signal: %+.3f" % hisp_delta)

    # ================================================================
    # H5: Full best-of-everything
    # ================================================================
    print("\n" + "=" * 100)
    print("H5: FULL BEST-OF-EVERYTHING COMBINATION")
    print("=" * 100)

    # Use best race (from H1/H2), best gender (from H3), best Hispanic (from H4)
    best_hisp_source = "qwi" if m_with["hisp"] < m_no["hisp"] else "standard"
    print("  Race: QWI + Expert A=%.0f%% (from H2)" % (best_a * 100))
    print("  Gender: QWI %.0f%% / Expert F %.0f%% (from H3)" % (best_gw * 100, (1 - best_gw) * 100))
    print("  Hispanic: %s (from H4)" % ("with QWI signal" if best_hisp_source == "qwi" else "standard V10"))

    def h5_scenario(rec):
        race = scenario_h2_qwi_expert_a(rec, qwi, a_weight=best_a)
        hisp = rec.get("hispanic_pred_qwi") if best_hisp_source == "qwi" else rec.get("hispanic_pred")
        gender = get_gender_h3(rec, qwi, qwi_weight=best_gw)
        return {"race": race, "hispanic": hisp, "gender": gender}

    h5_cal = train_calibration_v92(train_records, h5_scenario, max_offset=20.0)

    def h5_final(rec):
        pred = h5_scenario(rec)
        if not pred:
            return None
        return apply_calibration_v92(pred, rec, h5_cal, D_RACE, D_HISP, D_GENDER)

    h5_perm = evaluate(perm_records, h5_final)
    h5_sealed = evaluate(v10_records, h5_final)

    print("\n  %-40s | %8s %8s %8s | %7s %7s |" % (
        "Holdout", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  %s|%s|%s|" % ("-" * 42, "-" * 29, "-" * 17))

    print("  V10 permanent                          | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        v10_m_perm["race"], v10_m_perm["hisp"], v10_m_perm["gender"],
        v10_m_perm["p20"], v10_m_perm["p30"]))
    print("  V12a permanent                         | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        v12a_m_perm["race"], v12a_m_perm["hisp"], v12a_m_perm["gender"],
        v12a_m_perm["p20"], v12a_m_perm["p30"]))
    print("  H5 BEST permanent                      | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        h5_perm["race"], h5_perm["hisp"], h5_perm["gender"],
        h5_perm["p20"], h5_perm["p30"]))
    print("  V10 sealed                             | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        v10_m_sealed["race"], v10_m_sealed["hisp"], v10_m_sealed["gender"],
        v10_m_sealed["p20"], v10_m_sealed["p30"]))
    print("  H5 BEST sealed                         | %8.3f %8.3f %8.3f | %6.1f%% %6.1f%% |" % (
        h5_sealed["race"], h5_sealed["hisp"], h5_sealed["gender"],
        h5_sealed["p20"], h5_sealed["p30"]))

    # Total improvement
    print("\n  TOTAL IMPROVEMENT (sealed holdout):")
    print("    Race:     V10=%.3f -> H5=%.3f  (%+.3f)" % (
        v10_m_sealed["race"], h5_sealed["race"], h5_sealed["race"] - v10_m_sealed["race"]))
    print("    Hispanic: V10=%.3f -> H5=%.3f  (%+.3f)" % (
        v10_m_sealed["hisp"], h5_sealed["hisp"], h5_sealed["hisp"] - v10_m_sealed["hisp"]))
    print("    Gender:   V10=%.3f -> H5=%.3f  (%+.3f)" % (
        v10_m_sealed["gender"], h5_sealed["gender"], h5_sealed["gender"] - v10_m_sealed["gender"]))

    # Save configuration
    config = {
        "race_expert_a_weight": best_a,
        "gender_qwi_weight": best_gw,
        "hispanic_source": best_hisp_source,
        "hispanic_weights": best_hisp_weights if best_hisp_source == "qwi" else None,
        "d_race": D_RACE,
        "d_hisp": D_HISP,
        "d_gender": D_GENDER,
        "perm_metrics": {k: v for k, v in h5_perm.items() if k != "max_errors"},
        "sealed_metrics": {k: v for k, v in h5_sealed.items() if k != "max_errors"},
    }
    save_json(os.path.join(SCRIPT_DIR, "v12_best_config.json"), config)
    print("\n  Config saved to v12_best_config.json")

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == '__main__':
    main()
