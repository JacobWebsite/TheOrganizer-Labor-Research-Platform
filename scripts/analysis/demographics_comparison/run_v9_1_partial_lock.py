"""V9.1 Partial-Lock IPF: lock small race categories, scale White/Black, industry+adaptive Hispanic.

Architecture:
  - LOCK Asian(D), AIAN(G), NHOPI(B), Two+(F) from best experts
  - FREE White(D) + Black(G) proportionally scaled to fill remaining budget
  - Hispanic: industry+adaptive estimator (grid-searched on training)
  - Gender: Expert F
  - Calibration: region x industry at dampening=0.5 (Phase 5)

Reuses prediction checkpoint from run_v9_best_of_ipf.py for expert preds.
"""
import copy
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
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from methodologies import _blend_dicts
from methodologies_v5 import RACE_CATS, smoothed_ipf

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]
SPLIT_SEED = 20260311

# Expert -> category locks (from V9 training winners)
LOCKED_CATS = {
    "Asian": "D",
    "AIAN": "G",
    "NHOPI": "B",
    "Two+": "F",
}
FREE_CATS = {
    "White": "D",
    "Black": "G",
}
GENDER_EXPERT = "F"

# Prediction checkpoint from V9
PREDICTION_CHECKPOINT = os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "v9_1_partial_lock_results.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ================================================================
# TRUTH LOOKUP
# ================================================================
def build_truth_lookup():
    eeo1_rows = load_all_eeo1_data()
    by_code_year = {}
    by_code = defaultdict(list)
    for row in eeo1_rows:
        code = (row.get("COMPANY") or "").strip()
        year = int(float(row.get("YEAR", 0) or 0))
        if not code:
            continue
        parsed = parse_eeo1_row(row)
        if not parsed:
            continue
        by_code_year[(code, year)] = parsed
        by_code[code].append(parsed)
    for code in by_code:
        by_code[code].sort(key=lambda r: r.get("year", 0), reverse=True)
    return by_code_year, by_code


def get_truth(company, by_code_year, by_code):
    code = company["company_code"]
    year = company.get("year")
    truth = by_code_year.get((code, year))
    if truth:
        return truth
    vals = by_code.get(code, [])
    return vals[0] if vals else None


# ================================================================
# SPLITS
# ================================================================
def build_splits():
    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"] if isinstance(perm_data, dict) else perm_data
    perm_codes = {c["company_code"] for c in perm_companies}

    pool = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v6.json"))
    non_perm_pool = [c for c in pool if c["company_code"] not in perm_codes]

    rng = random.Random(SPLIT_SEED)
    shuffled = non_perm_pool[:]
    rng.shuffle(shuffled)
    train = shuffled[:10000]
    dev = shuffled[10000:]

    return {
        "perm_companies": perm_companies,
        "perm_codes": perm_codes,
        "train_companies": train,
        "train_codes": {c["company_code"] for c in train},
        "dev_companies": dev,
        "dev_codes": {c["company_code"] for c in dev},
    }


# ================================================================
# METRIC HELPERS
# ================================================================
def abs_err(pred, actual, cat):
    if not pred or not actual or cat not in pred or cat not in actual:
        return None
    return abs(pred[cat] - actual[cat])


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def mae_dict(pred, actual, cats):
    vals = [abs_err(pred, actual, cat) for cat in cats]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def max_cat_error(pred, actual, cats):
    vals = [abs_err(pred, actual, cat) for cat in cats]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def signed_bias(preds, actuals, cats):
    out = {}
    for cat in cats:
        errs = []
        for pred, actual in zip(preds, actuals):
            if pred and actual and cat in pred and cat in actual:
                errs.append(pred[cat] - actual[cat])
        out[cat] = sum(errs) / len(errs) if errs else None
    return out


def mean_abs_bias(preds, actuals, cats):
    biases = signed_bias(preds, actuals, cats)
    vals = [abs(v) for v in biases.values() if v is not None]
    return sum(vals) / len(vals) if vals else None


# ================================================================
# HISPANIC SIGNAL COLLECTION AND BLENDING
# ================================================================
def get_raw_signals(cl, rec):
    """Get all Hispanic signal sources for a record."""
    naics4 = rec["naics4"]
    state_fips = rec["state_fips"]
    county_fips = rec["county_fips"]
    cbsa_code = rec.get("cbsa_code", "")
    naics_group = rec.get("naics_group", "")
    zipcode = rec.get("zipcode", "")
    naics_2 = naics4[:2] if naics4 else None

    signals = {}

    # 1. PUMS metro
    pums_hisp = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
    signals["pums"] = pums_hisp

    # 2. ACS industry x state
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    signals["acs"] = acs_hisp

    # 3. Industry LODES (county x industry)
    ind_hisp, ind_source = cl.get_industry_or_county_lodes_hispanic(county_fips, naics4)
    signals["ind_lodes"] = ind_hisp
    signals["ind_lodes_source"] = ind_source

    # 4. County LODES
    county_hisp = cl.get_lodes_hispanic(county_fips)
    signals["county_lodes"] = county_hisp

    # 5. IPF of ACS + industry LODES
    ipf_hisp = smoothed_ipf(acs_hisp, ind_hisp, HISP_CATS)
    signals["ipf_ind"] = ipf_hisp

    # 6. Tract (multi-tract ensemble)
    tract_data = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_hisp = tract_data.get("hispanic") if tract_data else None
    signals["tract"] = tract_hisp

    # 7. Occ-chain
    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)
    if occ_chain and occ_chain.get("Hispanic") is not None:
        signals["occ_chain"] = {
            "Hispanic": occ_chain["Hispanic"],
            "Not Hispanic": 100.0 - occ_chain["Hispanic"],
        }
    else:
        signals["occ_chain"] = None

    # 8. County Hispanic % (context signal for tier classification)
    if county_hisp and "Hispanic" in county_hisp:
        signals["county_hisp_pct"] = county_hisp["Hispanic"]
    else:
        signals["county_hisp_pct"] = None

    return signals


def blend_hispanic(signals, weights):
    """Blend Hispanic estimates using named weight dict."""
    sources = []
    for name, w in weights.items():
        if w <= 0:
            continue
        sig = signals.get(name)
        if sig and "Hispanic" in sig:
            sources.append((sig, w))
    if not sources:
        for fallback in ["acs", "county_lodes"]:
            sig = signals.get(fallback)
            if sig and "Hispanic" in sig:
                return sig
        return None
    if len(sources) == 1:
        return sources[0][0]
    return _blend_dicts(sources, HISP_CATS)


# ================================================================
# GRID SEARCH: INDUSTRY + TIER WEIGHTS (trained on training set)
# ================================================================
def evaluate_hispanic(records, pred_fn):
    """Evaluate Hispanic predictions. pred_fn(rec) -> float or None."""
    errors = []
    signed_errs = []
    for rec in records:
        pred = pred_fn(rec)
        if pred is None:
            continue
        # Handle both float and dict returns
        if isinstance(pred, dict):
            pred = pred.get("Hispanic")
            if pred is None:
                continue
        truth = rec["truth_hispanic"]
        err = abs(pred - truth)
        errors.append(err)
        signed_errs.append(pred - truth)
    if not errors:
        return {"mae": None, "n": 0}
    n = len(errors)
    mae = sum(errors) / n
    bias = sum(signed_errs) / n
    p10 = sum(1 for e in errors if e > 10) / n * 100
    p15 = sum(1 for e in errors if e > 15) / n * 100
    p20 = sum(1 for e in errors if e > 20) / n * 100
    return {
        "mae": round(mae, 3),
        "bias": round(bias, 3),
        "n": n,
        "p_gt_10pp": round(p10, 2),
        "p_gt_15pp": round(p15, 2),
        "p_gt_20pp": round(p20, 2),
    }


def train_industry_weights(train_records):
    """Grid search for industry-specific Hispanic blend weights."""
    high_bias_industries = [
        "Food/Bev Manufacturing (311,312)",
        "Accommodation/Food Svc (72)",
        "Construction (23)",
        "Agriculture/Mining (11,21)",
        "Transport Equip Mfg (336)",
    ]
    industry_weights = {}
    for ng in high_bias_industries:
        ind_recs = [r for r in train_records if r["naics_group"] == ng]
        if len(ind_recs) < 30:
            continue
        best_mae = 999
        best_w = None
        for w_pums in [0.1, 0.2, 0.3, 0.4, 0.5]:
            for w_ipf in [0.0, 0.1, 0.2, 0.3]:
                for w_tract in [0.2, 0.3, 0.4, 0.5, 0.6]:
                    for w_occ in [0.0, 0.1, 0.2, 0.3]:
                        weights = {"pums": w_pums, "ipf_ind": w_ipf,
                                   "tract": w_tract, "occ_chain": w_occ}

                        def pred_fn(rec, w=weights):
                            result = blend_hispanic(rec["signals"], w)
                            return result["Hispanic"] if result and "Hispanic" in result else None

                        stats = evaluate_hispanic(ind_recs, pred_fn)
                        if stats["mae"] is not None and stats["mae"] < best_mae:
                            best_mae = stats["mae"]
                            best_w = weights.copy()

        industry_weights[ng] = best_w
        active = {k: v for k, v in best_w.items() if v > 0}
        print("  %-35s n=%-4d  MAE=%.3f  weights=%s" % (ng[:35], len(ind_recs), best_mae, active))

    return industry_weights


def train_tier_weights(train_records):
    """Grid search for tier-adaptive Hispanic blend weights."""
    hisp_tiers = {"low": [], "medium": [], "high": []}
    for rec in train_records:
        county_hisp = rec["signals"].get("county_hisp_pct")
        if county_hisp is None:
            hisp_tiers["medium"].append(rec)
        elif county_hisp < 10:
            hisp_tiers["low"].append(rec)
        elif county_hisp < 25:
            hisp_tiers["medium"].append(rec)
        else:
            hisp_tiers["high"].append(rec)

    print("  Tier sizes: low=%d, medium=%d, high=%d" % (
        len(hisp_tiers["low"]), len(hisp_tiers["medium"]), len(hisp_tiers["high"])))

    tier_best_weights = {}
    for tier_name, tier_recs in hisp_tiers.items():
        if not tier_recs:
            continue
        best_mae = 999
        best_w = None
        for w_pums in [0.1, 0.2, 0.3, 0.4]:
            for w_ipf in [0.1, 0.2, 0.3, 0.4]:
                for w_tract in [0.2, 0.3, 0.4, 0.5]:
                    for w_occ in [0.0, 0.1, 0.2]:
                        weights = {"pums": w_pums, "ipf_ind": w_ipf,
                                   "tract": w_tract, "occ_chain": w_occ}

                        def pred_fn(rec, w=weights):
                            result = blend_hispanic(rec["signals"], w)
                            return result["Hispanic"] if result and "Hispanic" in result else None

                        stats = evaluate_hispanic(tier_recs, pred_fn)
                        if stats["mae"] is not None and stats["mae"] < best_mae:
                            best_mae = stats["mae"]
                            best_w = weights.copy()

        tier_best_weights[tier_name] = best_w
        active = {k: v for k, v in best_w.items() if v > 0}
        print("  %s tier: MAE=%.3f  weights=%s" % (tier_name, best_mae, active))

    return tier_best_weights


def make_hispanic_predictor(industry_weights, tier_best_weights, default_weights):
    """Build the industry+adaptive Hispanic predictor function."""
    def predict(rec):
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
            weights = tier_best_weights.get(tier, default_weights)

        result = blend_hispanic(rec["signals"], weights)
        if result and "Hispanic" in result:
            return {"Hispanic": result["Hispanic"], "Not Hispanic": result["Not Hispanic"]}
        return None
    return predict


# ================================================================
# PARTIAL-LOCK RACE ASSEMBLY
# ================================================================
def assemble_partial_lock_race(rec):
    """Lock Asian(D), AIAN(G), NHOPI(B), Two+(F); scale White(D)+Black(G)."""
    expert_preds = rec["expert_preds"]

    # Get locked category values
    locked_sum = 0.0
    locked_values = {}
    for cat, expert in LOCKED_CATS.items():
        pred = expert_preds.get(expert)
        race = pred.get("race") if pred else None
        if not race or cat not in race:
            # Fallback: try other experts in order
            for fallback_exp in ["D", "G", "F", "B", "E", "A", "V6-Full"]:
                fb_pred = expert_preds.get(fallback_exp)
                fb_race = fb_pred.get("race") if fb_pred else None
                if fb_race and cat in fb_race:
                    race = fb_race
                    break
        if not race or cat not in race:
            locked_values[cat] = 0.0
        else:
            locked_values[cat] = race[cat]
        locked_sum += locked_values[cat]

    # Get raw White(D) and Black(G)
    d_pred = expert_preds.get("D")
    d_race = d_pred.get("race") if d_pred else None
    g_pred = expert_preds.get("G")
    g_race = g_pred.get("race") if g_pred else None

    raw_white = d_race.get("White", 50.0) if d_race else 50.0
    raw_black = g_race.get("Black", 10.0) if g_race else 10.0

    # Budget for White + Black
    budget = max(100.0 - locked_sum, 0.0)

    # Proportional scaling
    raw_sum = raw_white + raw_black
    if raw_sum > 0:
        white_final = budget * raw_white / raw_sum
        black_final = budget * raw_black / raw_sum
    else:
        white_final = budget * 0.7
        black_final = budget * 0.3

    result = {
        "White": round(white_final, 4),
        "Black": round(black_final, 4),
    }
    result.update({cat: round(v, 4) for cat, v in locked_values.items()})

    return result


def assemble_partial_lock_gender(rec):
    """Use Expert F for gender."""
    f_pred = rec["expert_preds"].get("F")
    if f_pred and f_pred.get("gender"):
        return f_pred["gender"]
    # Fallback chain
    for exp in ["D", "G", "E", "B", "A", "V6-Full"]:
        pred = rec["expert_preds"].get(exp)
        if pred and pred.get("gender"):
            return pred["gender"]
    return {"Male": 50.0, "Female": 50.0}


# ================================================================
# EVALUATION
# ================================================================
def evaluate_scenario(records, scenario_func):
    """Full scorecard evaluation."""
    preds_race, actuals_race = [], []
    preds_hisp, actuals_hisp = [], []
    preds_gender, actuals_gender = [], []
    race_maes, black_maes, gender_maes, hisp_maes = [], [], [], []
    max_errors = []

    for rec in records:
        pred = scenario_func(rec)
        if not pred:
            continue
        race_pred = pred.get("race")
        race_actual = rec["truth"]["race"]
        race_mae = mae_dict(race_pred, race_actual, RACE_CATS)
        if race_mae is not None:
            race_maes.append(race_mae)
            preds_race.append(race_pred)
            actuals_race.append(race_actual)
            mx = max_cat_error(race_pred, race_actual, RACE_CATS)
            if mx is not None:
                max_errors.append(mx)
            b_mae = abs_err(race_pred, race_actual, "Black")
            if b_mae is not None:
                black_maes.append(b_mae)

        hisp_pred = pred.get("hispanic")
        hisp_actual = rec["truth"]["hispanic"]
        hisp_mae = mae_dict(hisp_pred, hisp_actual, HISP_CATS)
        if hisp_mae is not None:
            hisp_maes.append(hisp_mae)
            preds_hisp.append(hisp_pred)
            actuals_hisp.append(hisp_actual)

        gender_pred = pred.get("gender")
        gender_actual = rec["truth"]["gender"]
        g_mae = mae_dict(gender_pred, gender_actual, GENDER_CATS)
        if g_mae is not None:
            gender_maes.append(g_mae)
            preds_gender.append(gender_pred)
            actuals_gender.append(gender_actual)

    return {
        "n": len(race_maes),
        "race_mae": mean(race_maes),
        "black_mae": mean(black_maes),
        "hisp_mae": mean(hisp_maes),
        "gender_mae": mean(gender_maes),
        "p_gt_20pp": (sum(1 for e in max_errors if e > 20.0) / len(max_errors) * 100.0) if max_errors else None,
        "p_gt_30pp": (sum(1 for e in max_errors if e > 30.0) / len(max_errors) * 100.0) if max_errors else None,
        "abs_bias": mean_abs_bias(preds_race, actuals_race, RACE_CATS),
        "race_bias": signed_bias(preds_race, actuals_race, RACE_CATS),
        "hisp_bias": signed_bias(preds_hisp, actuals_hisp, HISP_CATS),
        "gender_bias": signed_bias(preds_gender, actuals_gender, GENDER_CATS),
    }


def healthcare_south_tail(records, scenario_func):
    subset = [
        rec for rec in records
        if rec["naics_group"] == "Healthcare/Social (62)" and rec["region"] == "South"
    ]
    max_errors = []
    for rec in subset:
        pred = scenario_func(rec)
        if not pred or not pred.get("race"):
            continue
        mx = max_cat_error(pred["race"], rec["truth"]["race"], RACE_CATS)
        if mx is not None:
            max_errors.append(mx)
    n = len(max_errors)
    return {
        "count": n,
        "p_gt_20pp": (sum(1 for e in max_errors if e > 20.0) / n * 100.0) if n else None,
        "p_gt_30pp": (sum(1 for e in max_errors if e > 30.0) / n * 100.0) if n else None,
    }


def breakdown_race_mae(records, scenario_func, key_name, key_values):
    out = {}
    for key in key_values:
        subset = [rec for rec in records if rec.get(key_name) == key]
        metric = evaluate_scenario(subset, scenario_func)
        out[key] = metric["race_mae"]
    return out


def print_scorecard(label, metrics, hs_tail):
    print("  %-20s  Race=%.3f  Black=%.3f  Hisp=%.3f  Gender=%.3f  |  P>20=%.1f%%  P>30=%.1f%%  AbsBias=%.3f  |  HS_P>20=%.1f%%  HS_P>30=%.1f%%" % (
        label,
        metrics["race_mae"] or 0,
        metrics["black_mae"] or 0,
        metrics["hisp_mae"] or 0,
        metrics["gender_mae"] or 0,
        metrics["p_gt_20pp"] or 0,
        metrics["p_gt_30pp"] or 0,
        metrics["abs_bias"] or 0,
        hs_tail["p_gt_20pp"] or 0,
        hs_tail["p_gt_30pp"] or 0,
    ))


# ================================================================
# CALIBRATION (Phase 5: region x industry, dampening=0.5)
# ================================================================
def train_calibration(train_records, scenario_func):
    """Learn region x industry calibration offsets from training data."""
    buckets = defaultdict(list)
    for rec in train_records:
        pred = scenario_func(rec)
        if not pred:
            continue
        key = (rec["region"], rec["naics_group"])
        # Race bias per category
        race_pred = pred.get("race")
        race_actual = rec["truth"]["race"]
        if race_pred and race_actual:
            for cat in RACE_CATS:
                if cat in race_pred and cat in race_actual:
                    buckets[("race", cat, key)].append(race_pred[cat] - race_actual[cat])
        # Hispanic bias
        hisp_pred = pred.get("hispanic")
        hisp_actual = rec["truth"]["hispanic"]
        if hisp_pred and hisp_actual:
            if "Hispanic" in hisp_pred and "Hispanic" in hisp_actual:
                buckets[("hisp", "Hispanic", key)].append(
                    hisp_pred["Hispanic"] - hisp_actual["Hispanic"])

    # Compute mean bias per bucket (only if n >= 20)
    cal_offsets = {}
    for bucket_key, errors in buckets.items():
        if len(errors) >= 20:
            cal_offsets[bucket_key] = sum(errors) / len(errors)
    return cal_offsets


def apply_calibration(pred, rec, cal_offsets, dampening=0.5):
    """Apply calibration offsets to a prediction."""
    result = {}
    key = (rec["region"], rec["naics_group"])

    # Calibrate race
    if pred.get("race"):
        cal_race = {}
        for cat in RACE_CATS:
            val = pred["race"].get(cat, 0.0)
            offset = cal_offsets.get(("race", cat, key))
            if offset is not None:
                val -= offset * dampening
            cal_race[cat] = max(0.0, val)
        # Re-normalize to 100
        total = sum(cal_race.values())
        if total > 0:
            cal_race = {k: round(v * 100.0 / total, 4) for k, v in cal_race.items()}
        result["race"] = cal_race
    else:
        result["race"] = pred.get("race")

    # Calibrate Hispanic
    if pred.get("hispanic"):
        hisp_val = pred["hispanic"].get("Hispanic", 0.0)
        offset = cal_offsets.get(("hisp", "Hispanic", key))
        if offset is not None:
            hisp_val -= offset * dampening
        hisp_val = max(0.0, min(100.0, hisp_val))
        result["hispanic"] = {"Hispanic": round(hisp_val, 4), "Not Hispanic": round(100.0 - hisp_val, 4)}
    else:
        result["hispanic"] = pred.get("hispanic")

    # Gender passes through uncalibrated
    result["gender"] = pred.get("gender")
    return result


# ================================================================
# ACCEPTANCE CRITERIA (7/7)
# ================================================================
def check_acceptance(metrics, hs_tail):
    """Check 7 acceptance criteria. Returns dict of {criterion: (value, target, pass)}."""
    checks = {}
    checks["race_mae"] = (metrics["race_mae"], 4.50, metrics["race_mae"] is not None and metrics["race_mae"] < 4.50)
    checks["hisp_mae"] = (metrics["hisp_mae"], 8.00, metrics["hisp_mae"] is not None and metrics["hisp_mae"] < 8.00)
    checks["gender_mae"] = (metrics["gender_mae"], 12.00, metrics["gender_mae"] is not None and metrics["gender_mae"] < 12.00)
    checks["abs_bias"] = (metrics["abs_bias"], 1.10, metrics["abs_bias"] is not None and metrics["abs_bias"] < 1.10)
    checks["p_gt_20pp"] = (metrics["p_gt_20pp"], 16.0, metrics["p_gt_20pp"] is not None and metrics["p_gt_20pp"] < 16.0)
    checks["p_gt_30pp"] = (metrics["p_gt_30pp"], 6.0, metrics["p_gt_30pp"] is not None and metrics["p_gt_30pp"] < 6.0)
    hs_p20 = hs_tail.get("p_gt_20pp")
    checks["hs_tail"] = (hs_p20, 15.0, hs_p20 is not None and hs_p20 < 15.0)
    return checks


# ================================================================
# MAIN
# ================================================================
def main():
    t0 = time.time()
    print("V9.1 PARTIAL-LOCK + INDUSTRY+ADAPTIVE HISPANIC")
    print("=" * 80)

    # --- Load splits ---
    splits = build_splits()
    all_companies = splits["train_companies"] + splits["dev_companies"] + list(splits["perm_companies"])
    print("Training: %d | Dev: %d | Permanent: %d" % (
        len(splits["train_companies"]), len(splits["dev_companies"]),
        len(splits["perm_companies"])))

    # --- Load prediction checkpoint (expert preds) ---
    if os.path.exists(PREDICTION_CHECKPOINT):
        checkpoint = load_json(PREDICTION_CHECKPOINT)
        checkpoint_records = checkpoint.get("all_records", [])
        print("Loaded expert prediction checkpoint: %d records" % len(checkpoint_records))
        expert_lookup = {}
        for rec in checkpoint_records:
            expert_lookup[rec["company_code"]] = rec
    else:
        print("ERROR: Prediction checkpoint not found: %s" % PREDICTION_CHECKPOINT)
        print("Run run_v9_best_of_ipf.py first to generate expert predictions.")
        sys.exit(1)

    # --- Load truth ---
    by_code_year, by_code = build_truth_lookup()

    # --- Connect and build Hispanic signals ---
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("\nCollecting Hispanic signals for all companies...")
    all_records = []
    missing_expert = 0
    missing_truth = 0
    for idx, company in enumerate(all_companies, 1):
        if idx % 2000 == 0:
            print("  %d/%d (%.0fs)" % (idx, len(all_companies), time.time() - t0))

        code = company["company_code"]
        checkpoint_rec = expert_lookup.get(code)
        if not checkpoint_rec:
            missing_expert += 1
            continue

        truth = checkpoint_rec.get("truth")
        if not truth or not truth.get("race") or not truth.get("hispanic"):
            missing_truth += 1
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

        rec = {
            "company_code": code,
            "name": company.get("name"),
            "naics4": naics4,
            "naics_group": naics_group,
            "region": region,
            "county_fips": county_fips,
            "state_fips": state_fips,
            "state": state,
            "zipcode": zipcode,
            "cbsa_code": cbsa_code,
            "truth": truth,
            "truth_hispanic": truth["hispanic"]["Hispanic"],
            "expert_preds": checkpoint_rec["expert_preds"],
        }
        rec["signals"] = get_raw_signals(cl, rec)
        all_records.append(rec)

    print("Records built: %d (missing expert: %d, missing truth: %d)" % (
        len(all_records), missing_expert, missing_truth))

    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    dev_records = [r for r in all_records if r["company_code"] in splits["dev_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    all_holdout = dev_records + perm_records
    print("Split: train=%d, dev=%d, perm=%d" % (
        len(train_records), len(dev_records), len(perm_records)))

    # ================================================================
    # PHASE 1: Train Hispanic weights on training set
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 1: TRAIN INDUSTRY+ADAPTIVE HISPANIC WEIGHTS")
    print("=" * 80)

    # Default weights (best 3-signal from prior work)
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}

    print("\nIndustry-specific weight optimization:")
    industry_weights = train_industry_weights(train_records)

    print("\nTier-adaptive weight optimization:")
    tier_best_weights = train_tier_weights(train_records)

    # Build Hispanic predictor
    hisp_pred_fn = make_hispanic_predictor(industry_weights, tier_best_weights, default_weights)

    # Evaluate Hispanic alone
    print("\nHispanic MAE comparison:")
    for set_name, records in [("Training", train_records), ("All holdout", all_holdout),
                               ("Dev", dev_records), ("Permanent", perm_records)]:
        stats = evaluate_hispanic(records, hisp_pred_fn)
        print("  %-15s  MAE=%.3f  bias=%+.3f  P>10=%.1f%%  P>20=%.1f%%" % (
            set_name, stats["mae"] or 0, stats["bias"] or 0,
            stats["p_gt_10pp"] or 0, stats["p_gt_20pp"] or 0))

    # ================================================================
    # PHASE 2: Assemble predictions
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 2: HYBRID ASSEMBLY (D race + new Hispanic + F gender)")
    print("=" * 80)

    # Attach predictions to all records
    for rec in all_records:
        rec["partial_lock_race"] = assemble_partial_lock_race(rec)
        rec["partial_lock_gender"] = assemble_partial_lock_gender(rec)
        rec["partial_lock_hispanic"] = hisp_pred_fn(rec)

    def scenario_partial_lock(rec):
        return {
            "race": rec["partial_lock_race"],
            "hispanic": rec["partial_lock_hispanic"],
            "gender": rec["partial_lock_gender"],
        }

    def scenario_d_solo(rec):
        return rec["expert_preds"].get("D")

    def scenario_hybrid(rec):
        """D race (intact) + industry+adaptive Hispanic + F gender."""
        d_pred = rec["expert_preds"].get("D")
        race = d_pred.get("race") if d_pred else None
        gender = assemble_partial_lock_gender(rec)  # Expert F
        hispanic = rec["partial_lock_hispanic"]
        return {"race": race, "hispanic": hispanic, "gender": gender}

    # ================================================================
    # PHASE 3: Evaluate pre-calibration
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 3: PRE-CALIBRATION SCORECARD")
    print("=" * 80)

    scenarios = {
        "D_solo": scenario_d_solo,
        "V9.1_partial_lock": scenario_partial_lock,
        "V9.1_hybrid": scenario_hybrid,
    }

    for set_name, records in [("All 2,525", all_holdout),
                               ("Dev 1,525", dev_records),
                               ("Perm 1,000", perm_records)]:
        print("\n--- %s ---" % set_name)
        for sc_name, sc_fn in scenarios.items():
            metrics = evaluate_scenario(records, sc_fn)
            hs_tail = healthcare_south_tail(records, sc_fn)
            print_scorecard(sc_name, metrics, hs_tail)

    # Race bias details
    print("\nRace bias (Perm 1,000):")
    for sc_name, sc_fn in scenarios.items():
        metrics = evaluate_scenario(perm_records, sc_fn)
        bias = metrics.get("race_bias", {})
        parts = ["  %-20s" % sc_name]
        for cat in RACE_CATS:
            b = bias.get(cat)
            parts.append("%s=%+.2f" % (cat, b if b is not None else 0))
        print("  ".join(parts))

    # Regional breakdown
    print("\nRegional Race MAE (Perm 1,000):")
    regions = ["South", "West", "Northeast", "Midwest"]
    print("  %-20s  %-8s %-8s %-8s %-8s" % ("Scenario", "South", "West", "NE", "MW"))
    for sc_name, sc_fn in scenarios.items():
        reg_maes = breakdown_race_mae(perm_records, sc_fn, "region", regions)
        print("  %-20s  %-8s %-8s %-8s %-8s" % (
            sc_name,
            "%.3f" % reg_maes["South"] if reg_maes["South"] else "--",
            "%.3f" % reg_maes["West"] if reg_maes["West"] else "--",
            "%.3f" % reg_maes["Northeast"] if reg_maes["Northeast"] else "--",
            "%.3f" % reg_maes["Midwest"] if reg_maes["Midwest"] else "--",
        ))

    # ================================================================
    # PHASE 3b: STOP GATE CHECK
    # ================================================================
    print("\n" + "=" * 80)
    print("STOP GATE: Healthcare South tail rates (All 2,525)")
    print("=" * 80)

    d_hs = healthcare_south_tail(all_holdout, scenario_d_solo)
    pl_hs = healthcare_south_tail(all_holdout, scenario_partial_lock)
    hy_hs = healthcare_south_tail(all_holdout, scenario_hybrid)
    print("  D solo:         n=%-3d  P>20pp=%.1f%%  P>30pp=%.1f%%" % (
        d_hs["count"], d_hs["p_gt_20pp"] or 0, d_hs["p_gt_30pp"] or 0))
    print("  V9.1 partial:   n=%-3d  P>20pp=%.1f%%  P>30pp=%.1f%%" % (
        pl_hs["count"], pl_hs["p_gt_20pp"] or 0, pl_hs["p_gt_30pp"] or 0))
    print("  V9.1 hybrid:    n=%-3d  P>20pp=%.1f%%  P>30pp=%.1f%%" % (
        hy_hs["count"], hy_hs["p_gt_20pp"] or 0, hy_hs["p_gt_30pp"] or 0))

    stop_passes_pl = (
        pl_hs["p_gt_20pp"] is not None
        and d_hs["p_gt_20pp"] is not None
        and pl_hs["p_gt_20pp"] <= d_hs["p_gt_20pp"]
        and pl_hs["p_gt_30pp"] <= d_hs["p_gt_30pp"]
    )
    stop_passes_hy = (
        hy_hs["p_gt_20pp"] is not None
        and d_hs["p_gt_20pp"] is not None
        and hy_hs["p_gt_20pp"] <= d_hs["p_gt_20pp"]
        and hy_hs["p_gt_30pp"] <= d_hs["p_gt_30pp"]
    )
    stop_passes = stop_passes_pl or stop_passes_hy
    print("  STOP GATE partial: %s" % ("PASS" if stop_passes_pl else "FAIL"))
    print("  STOP GATE hybrid:  %s" % ("PASS" if stop_passes_hy else "FAIL"))
        # Still save results and continue to show what we have

    # ================================================================
    # PHASE 4: CALIBRATION (region x industry, d=0.5)
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 4: CALIBRATION (region x industry, dampening=0.5)")
    print("=" * 80)

    cal_offsets_pl = train_calibration(train_records, scenario_partial_lock)
    cal_offsets_hy = train_calibration(train_records, scenario_hybrid)
    print("  Calibration buckets (partial-lock): %d" % len(cal_offsets_pl))
    print("  Calibration buckets (hybrid): %d" % len(cal_offsets_hy))

    def scenario_partial_lock_cal(rec):
        pred = scenario_partial_lock(rec)
        if not pred:
            return None
        return apply_calibration(pred, rec, cal_offsets_pl, dampening=0.5)

    def scenario_hybrid_cal(rec):
        pred = scenario_hybrid(rec)
        if not pred:
            return None
        return apply_calibration(pred, rec, cal_offsets_hy, dampening=0.5)

    scenarios_cal = {
        "D_solo": scenario_d_solo,
        "V9.1_PL_pre": scenario_partial_lock,
        "V9.1_PL_post": scenario_partial_lock_cal,
        "V9.1_HY_pre": scenario_hybrid,
        "V9.1_HY_post": scenario_hybrid_cal,
    }

    for set_name, records in [("All 2,525", all_holdout),
                               ("Dev 1,525", dev_records),
                               ("Perm 1,000", perm_records)]:
        print("\n--- %s ---" % set_name)
        for sc_name, sc_fn in scenarios_cal.items():
            metrics = evaluate_scenario(records, sc_fn)
            hs_tail = healthcare_south_tail(records, sc_fn)
            print_scorecard(sc_name, metrics, hs_tail)

    # ================================================================
    # PHASE 5: 7/7 ACCEPTANCE TEST (Perm 1,000)
    # ================================================================
    print("\n" + "=" * 80)
    print("PHASE 5: 7/7 ACCEPTANCE TEST (Permanent holdout, 1,000)")
    print("=" * 80)

    # Test all variants
    for variant_name, variant_fn in [("V9.1 PL pre-cal", scenario_partial_lock),
                                      ("V9.1 PL post-cal", scenario_partial_lock_cal),
                                      ("V9.1 HY pre-cal", scenario_hybrid),
                                      ("V9.1 HY post-cal", scenario_hybrid_cal)]:
        metrics = evaluate_scenario(perm_records, variant_fn)
        hs_tail = healthcare_south_tail(perm_records, variant_fn)
        checks = check_acceptance(metrics, hs_tail)

        passed = sum(1 for _, _, p in checks.values() if p)
        print("\n  %s: %d/7 criteria passed" % (variant_name, passed))
        for name, (value, target, ok) in checks.items():
            status = "PASS" if ok else "FAIL"
            print("    %-12s  value=%-8s  target=<%-6s  %s" % (
                name,
                "%.3f" % value if value is not None else "N/A",
                "%.2f" % target,
                status,
            ))

    # ================================================================
    # PHASE 6: SECTOR BREAKDOWN
    # ================================================================
    print("\n" + "=" * 80)
    print("SECTOR BREAKDOWN (Perm 1,000)")
    print("=" * 80)

    sectors = [
        "Healthcare/Social (62)", "Admin/Staffing (56)", "Finance/Insurance (52)",
        "Retail Trade (44-45)", "Manufacturing (31-33)", "Professional/Tech (54)",
        "Construction (23)", "Accommodation/Food Svc (72)",
    ]
    best_variant = scenario_hybrid_cal
    print("  %-35s  %-8s %-8s %-8s %-8s" % ("Sector", "Race", "Hisp", "P>20pp", "n"))
    for sector in sectors:
        subset = [r for r in perm_records if r["naics_group"] == sector]
        if not subset:
            continue
        m = evaluate_scenario(subset, best_variant)
        print("  %-35s  %-8s %-8s %-8s %-8d" % (
            sector[:35],
            "%.3f" % m["race_mae"] if m["race_mae"] else "--",
            "%.3f" % m["hisp_mae"] if m["hisp_mae"] else "--",
            "%.1f%%" % m["p_gt_20pp"] if m["p_gt_20pp"] is not None else "--",
            m["n"],
        ))

    # ================================================================
    # SAVE RESULTS
    # ================================================================
    perm_d_metrics = evaluate_scenario(perm_records, scenario_d_solo)
    perm_hs_d = healthcare_south_tail(perm_records, scenario_d_solo)

    perm_metrics_pl_pre = evaluate_scenario(perm_records, scenario_partial_lock)
    perm_metrics_pl_post = evaluate_scenario(perm_records, scenario_partial_lock_cal)
    perm_hs_pl_pre = healthcare_south_tail(perm_records, scenario_partial_lock)
    perm_hs_pl_post = healthcare_south_tail(perm_records, scenario_partial_lock_cal)

    perm_metrics_hy_pre = evaluate_scenario(perm_records, scenario_hybrid)
    perm_metrics_hy_post = evaluate_scenario(perm_records, scenario_hybrid_cal)
    perm_hs_hy_pre = healthcare_south_tail(perm_records, scenario_hybrid)
    perm_hs_hy_post = healthcare_south_tail(perm_records, scenario_hybrid_cal)

    result = {
        "run_date": "2026-03-11",
        "model": "V9.1",
        "split_seed": SPLIT_SEED,
        "architecture": {
            "partial_lock": {"locked": LOCKED_CATS, "free": FREE_CATS},
            "hybrid": "D_race + industry_adaptive_hispanic + F_gender",
            "gender": GENDER_EXPERT,
            "hispanic": "industry+adaptive",
        },
        "trained_weights": {
            "industry_weights": industry_weights,
            "tier_weights": tier_best_weights,
            "default_weights": default_weights,
        },
        "calibration": {
            "method": "region_x_industry",
            "dampening": 0.5,
            "n_buckets_pl": len(cal_offsets_pl),
            "n_buckets_hy": len(cal_offsets_hy),
        },
        "stop_gate": {
            "partial_lock_passes": stop_passes_pl,
            "hybrid_passes": stop_passes_hy,
            "d_solo": d_hs,
            "partial_lock": pl_hs,
            "hybrid": hy_hs,
        },
        "perm_1000": {
            "d_solo": {"metrics": perm_d_metrics, "hs_tail": perm_hs_d},
            "partial_lock_precal": {
                "metrics": perm_metrics_pl_pre, "hs_tail": perm_hs_pl_pre,
                "acceptance": {k: {"value": v, "target": t, "pass": p}
                               for k, (v, t, p) in check_acceptance(perm_metrics_pl_pre, perm_hs_pl_pre).items()},
            },
            "partial_lock_postcal": {
                "metrics": perm_metrics_pl_post, "hs_tail": perm_hs_pl_post,
                "acceptance": {k: {"value": v, "target": t, "pass": p}
                               for k, (v, t, p) in check_acceptance(perm_metrics_pl_post, perm_hs_pl_post).items()},
            },
            "hybrid_precal": {
                "metrics": perm_metrics_hy_pre, "hs_tail": perm_hs_hy_pre,
                "acceptance": {k: {"value": v, "target": t, "pass": p}
                               for k, (v, t, p) in check_acceptance(perm_metrics_hy_pre, perm_hs_hy_pre).items()},
            },
            "hybrid_postcal": {
                "metrics": perm_metrics_hy_post, "hs_tail": perm_hs_hy_post,
                "acceptance": {k: {"value": v, "target": t, "pass": p}
                               for k, (v, t, p) in check_acceptance(perm_metrics_hy_post, perm_hs_hy_post).items()},
            },
        },
    }

    save_json(OUTPUT_JSON, result)
    print("\nResults saved: %s" % OUTPUT_JSON)
    print("Runtime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
