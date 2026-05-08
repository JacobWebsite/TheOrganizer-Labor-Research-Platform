"""V11 Demographics: Shrinkage + per-tier dampening + K-fold on all EEO-1 companies.

Improvements over V10:
  1. Bayesian shrinkage on calibration offsets (James-Stein style)
     - Eliminates hard min bucket sizes; small buckets shrink toward parent
  2. Cross-validated dampening parameters (d_race, d_hisp, d_gender)
     - Found via inner validation split within each fold
  3. Smooth hierarchy transitions (unified with #1 via recursive shrinkage)
  4. Per-diversity-tier dampening parameters
     - Separate d_race/d_hisp/d_gender per diversity tier

Validation:
  5-fold stratified CV on ALL EEO-1 companies with NAICS codes.
  Every company gets an honest out-of-sample prediction.

Usage:
    py scripts/analysis/demographics_comparison/run_v11_kfold.py
    py scripts/analysis/demographics_comparison/run_v11_kfold.py --kappa 15
    py scripts/analysis/demographics_comparison/run_v11_kfold.py --folds 10
"""
import contextlib
import io
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
from cached_loaders_v6 import (
    CachedLoadersV6, cached_method_v6_full, cached_expert_f,
)
from classifiers import classify_naics_group
from config import get_census_region
from data_loaders import zip_to_county
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from methodologies_v5 import RACE_CATS, smoothed_ipf, expert_a_smoothed_ipf
from run_v9_2 import (
    get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    get_gender, blend_hispanic,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
    train_calibration_v92, apply_calibration_v92,
)
from run_v10 import (
    build_records,
    scenario_v92_race, scenario_v92_full,
    BLACK_WEIGHTS, BLEND_A,
    get_hispanic_county_tier, train_hispanic_calibration,
    apply_hispanic_calibration,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

# Shrinkage hyperparameter: prior sample size for James-Stein
DEFAULT_KAPPA = 20


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@contextlib.contextmanager
def suppress_stdout():
    """Suppress print output during repetitive training calls."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


# ================================================================
# IMPROVEMENT 1+3: BAYESIAN SHRINKAGE CALIBRATION
# ================================================================

def _compute_shrunk(raw_offsets, parent_fn, kappa, max_offset):
    """Apply recursive James-Stein shrinkage from root to leaves.

    Each level's offset is shrunk toward its parent:
        shrunk = alpha * raw + (1 - alpha) * parent_shrunk
        alpha  = n / (n + kappa)

    parent_fn(full_key) -> parent_full_key or None
    """
    shrunk = {}
    # Process levels from coarsest (root) to finest (leaves)
    for level in ["global", "ind", "reg_ind", "dt_ind", "dt_reg_ind",
                   "ht_ind", "ht_reg_ind"]:
        for k, (raw, n) in raw_offsets.items():
            if k[2] != level:
                continue
            if level == "global":
                shrunk[k] = (max(-max_offset, min(max_offset, raw)), n)
            else:
                parent_key = parent_fn(k)
                parent_off = 0.0
                if parent_key and parent_key in shrunk:
                    parent_off = shrunk[parent_key][0]
                alpha = n / (n + kappa)
                val = alpha * raw + (1 - alpha) * parent_off
                val = max(-max_offset, min(max_offset, val))
                shrunk[k] = (val, n)
    return shrunk


def _parent_dt_key(k):
    """Parent mapping for diversity-tier hierarchy."""
    dim_cat = k[:2]  # e.g. ("race", "Black")
    hk = k[2:]        # e.g. ("dt_reg_ind", "Med-High", "South", "Healthcare/Social (62)")
    level = hk[0]
    if level == "dt_reg_ind":
        # (dt_reg_ind, dt, region, ng) -> (dt_ind, dt, ng)
        return dim_cat + ("dt_ind", hk[1], hk[3])
    elif level == "dt_ind":
        # (dt_ind, dt, ng) -> (ind, ng)
        return dim_cat + ("ind", hk[2])
    elif level == "reg_ind":
        # (reg_ind, region, ng) -> (ind, ng)
        return dim_cat + ("ind", hk[2])
    elif level == "ind":
        # (ind, ng) -> (global,)
        return dim_cat + ("global",)
    return None


def _parent_ht_key(k):
    """Parent mapping for hispanic-tier hierarchy."""
    dim_cat = k[:2]
    hk = k[2:]
    level = hk[0]
    if level == "ht_reg_ind":
        return dim_cat + ("ht_ind", hk[1], hk[3])
    elif level == "ht_ind":
        return dim_cat + ("ind", hk[2])
    elif level == "reg_ind":
        return dim_cat + ("ind", hk[2])
    elif level == "ind":
        return dim_cat + ("global",)
    return None


def train_shrunk_calibration(train_records, scenario_fn,
                              kappa=DEFAULT_KAPPA, max_offset=20.0):
    """Train calibration with Bayesian shrinkage (improvements 1+3).

    No minimum bucket sizes. Small buckets shrink toward parent level.
    Hierarchy: dt_reg_ind -> dt_ind -> ind -> global
                                       ^
               reg_ind ----------------+
    """
    buckets = defaultdict(list)
    for rec in train_records:
        pred = scenario_fn(rec)
        if not pred:
            continue
        dt = rec["diversity_tier"]
        region = rec["region"]
        ng = rec["naics_group"]
        keys = [
            ("dt_reg_ind", dt, region, ng),
            ("dt_ind", dt, ng),
            ("reg_ind", region, ng),
            ("ind", ng),
            ("global",),
        ]
        rp, ra = pred.get("race"), rec["truth"]["race"]
        if rp and ra:
            for c in RACE_CATS:
                if c in rp and c in ra:
                    err = rp[c] - ra[c]
                    for key in keys:
                        buckets[("race", c) + key].append(err)
        hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
        if hp and ha and "Hispanic" in hp and "Hispanic" in ha:
            err = hp["Hispanic"] - ha["Hispanic"]
            for key in keys:
                buckets[("hisp", "Hispanic") + key].append(err)
        gp, ga = pred.get("gender"), rec["truth"]["gender"]
        if gp and ga and "Female" in gp and "Female" in ga:
            err = gp["Female"] - ga["Female"]
            for key in keys:
                buckets[("gender", "Female") + key].append(err)

    raw = {}
    for k, errs in buckets.items():
        if errs:
            raw[k] = (sum(errs) / len(errs), len(errs))

    return _compute_shrunk(raw, _parent_dt_key, kappa, max_offset)


def train_shrunk_hispanic_cal(train_records, scenario_fn,
                                kappa=DEFAULT_KAPPA, max_offset=15.0):
    """Hispanic-specific calibration with Bayesian shrinkage.

    Uses Hispanic county tier instead of diversity tier.
    """
    buckets = defaultdict(list)
    for rec in train_records:
        pred = scenario_fn(rec)
        if not pred:
            continue
        hp, ha = pred.get("hispanic"), rec["truth"]["hispanic"]
        if not hp or not ha or "Hispanic" not in hp or "Hispanic" not in ha:
            continue
        county_hisp = rec["signals"].get("county_hisp_pct")
        ht = get_hispanic_county_tier(county_hisp)
        region = rec["region"]
        ng = rec["naics_group"]
        err = hp["Hispanic"] - ha["Hispanic"]
        keys = [
            ("ht_reg_ind", ht, region, ng),
            ("ht_ind", ht, ng),
            ("reg_ind", region, ng),
            ("ind", ng),
            ("global",),
        ]
        for key in keys:
            buckets[("hisp", "Hispanic") + key].append(err)

    raw = {}
    for k, errs in buckets.items():
        if errs:
            raw[k] = (sum(errs) / len(errs), len(errs))

    return _compute_shrunk(raw, _parent_ht_key, kappa, max_offset)


def apply_shrunk_calibration(pred, rec, offsets, hisp_offsets,
                              d_race=0.85, d_hisp=0.50, d_gender=0.95):
    """Apply shrunk calibration offsets.

    Race/gender: diversity-tier hierarchy from offsets.
    Hispanic: hispanic-tier hierarchy from hisp_offsets.
    Always uses the most specific available bucket (already shrunk toward parent).
    """
    result = {}
    dt = rec["diversity_tier"]
    region = rec["region"]
    ng = rec["naics_group"]

    hierarchy_dt = [
        ("dt_reg_ind", dt, region, ng),
        ("dt_ind", dt, ng),
        ("reg_ind", region, ng),
        ("ind", ng),
        ("global",),
    ]

    def get_best(dim, cat, hier, offs):
        for key in hier:
            full_key = (dim, cat) + key
            if full_key in offs:
                return offs[full_key][0]
        return None

    # Race
    if pred.get("race"):
        cal = {}
        for c in RACE_CATS:
            v = pred["race"].get(c, 0.0)
            off = get_best("race", c, hierarchy_dt, offsets)
            if off is not None:
                v -= off * d_race
            cal[c] = max(0.0, v)
        total = sum(cal.values())
        if total > 0:
            cal = {k: round(v * 100 / total, 4) for k, v in cal.items()}
        result["race"] = cal
    else:
        result["race"] = pred.get("race")

    # Hispanic (hispanic-tier hierarchy)
    if pred.get("hispanic"):
        county_hisp = rec["signals"].get("county_hisp_pct")
        ht = get_hispanic_county_tier(county_hisp)
        hierarchy_ht = [
            ("ht_reg_ind", ht, region, ng),
            ("ht_ind", ht, ng),
            ("reg_ind", region, ng),
            ("ind", ng),
            ("global",),
        ]
        hv = pred["hispanic"].get("Hispanic", 0.0)
        off = get_best("hisp", "Hispanic", hierarchy_ht, hisp_offsets)
        if off is not None:
            hv -= off * d_hisp
        hv = max(0.0, min(100.0, hv))
        result["hispanic"] = {"Hispanic": round(hv, 4), "Not Hispanic": round(100 - hv, 4)}
    else:
        result["hispanic"] = pred.get("hispanic")

    # Gender
    if pred.get("gender"):
        fv = pred["gender"].get("Female", 50.0)
        off = get_best("gender", "Female", hierarchy_dt, offsets)
        if off is not None:
            fv -= off * d_gender
        fv = max(0.0, min(100.0, fv))
        result["gender"] = {"Male": round(100 - fv, 4), "Female": round(fv, 4)}
    else:
        result["gender"] = pred.get("gender")

    return result


# ================================================================
# IMPROVEMENT 2+4: PER-TIER DAMPENING VIA INNER CV
# ================================================================

def search_dampening(val_recs, cal, hisp_cal, tier=None):
    """Grid search for (d_race, d_hisp, d_gender) on validation records.

    If tier is specified, only evaluates on that diversity tier.
    Returns best params dict.
    """
    if tier:
        val_recs = [r for r in val_recs if r["diversity_tier"] == tier]
    if len(val_recs) < 20:
        return {"d_race": 0.85, "d_hisp": 0.50, "d_gender": 0.95}

    d_race_grid = [0.70, 0.80, 0.85, 0.90, 0.95]
    d_hisp_grid = [0.20, 0.30, 0.40, 0.50, 0.60]
    d_gender_grid = [0.85, 0.90, 0.95, 1.00]

    best_score = 999
    best = {"d_race": 0.85, "d_hisp": 0.50, "d_gender": 0.95}

    for dr in d_race_grid:
        for dh in d_hisp_grid:
            for dg in d_gender_grid:
                def fn(rec, _dr=dr, _dh=dh, _dg=dg):
                    pred = scenario_v92_full(rec)
                    if not pred:
                        return None
                    return apply_shrunk_calibration(
                        pred, rec, cal, hisp_cal, _dr, _dh, _dg)

                m = evaluate(val_recs, fn)
                if not m:
                    continue
                # Guard rails: don't accept params that blow up race
                if m["race"] > 4.70 or m["p30"] > 8.0:
                    continue
                # Combined objective: race-weighted composite
                score = m["race"] * 3 + m["hisp"] + m["gender"]
                if score < best_score:
                    best_score = score
                    best = {"d_race": dr, "d_hisp": dh, "d_gender": dg}

    return best


def find_per_tier_dampening(val_recs, cal, hisp_cal):
    """Find optimal dampening per diversity tier (improvement 4).

    Falls back to global params for tiers with too few validation records.
    """
    global_params = search_dampening(val_recs, cal, hisp_cal)

    tier_params = {}
    for tier in ["Low", "Med-Low", "Med-High", "High", "unknown"]:
        tier_val = [r for r in val_recs if r["diversity_tier"] == tier]
        if len(tier_val) >= 30:
            tier_params[tier] = search_dampening(val_recs, cal, hisp_cal, tier=tier)
        else:
            tier_params[tier] = global_params

    return tier_params, global_params


# ================================================================
# LOAD ALL EEO-1 COMPANIES WITH NAICS
# ================================================================

def load_all_companies(cl, cur, pool_only=False):
    """Load all EEO-1 companies with NAICS codes.

    1. Pool companies (expanded_training_v6 + permanent holdout) from checkpoint
    2. Additional EEO-1 companies not in pool (generate predictions on-the-fly)
       (skipped if pool_only=True)

    Returns (companies_list, rec_lookup_dict).
    """
    # Load pool
    pool = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v6.json"))
    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"] if isinstance(perm_data, dict) else perm_data

    pool_codes = {c["company_code"] for c in pool}
    all_pool = pool + [c for c in perm_companies if c["company_code"] not in pool_codes]
    pool_all_codes = {c["company_code"] for c in all_pool}

    # Load checkpoint
    print("  Loading checkpoint...")
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    print("  Pool companies: %d" % len(all_pool))
    print("  Checkpoint records: %d" % len(rec_lookup))

    if pool_only:
        print("  --pool-only: skipping extra EEO-1 loading")
        print("  Total unique companies: %d" % len(all_pool))
        return all_pool, rec_lookup

    # Load ALL EEO-1 data for companies not in pool
    print("  Loading all EEO-1 CSVs...")
    try:
        eeo1_rows = load_all_eeo1_data()
    except Exception as e:
        print("  WARNING: Could not load all EEO-1 CSVs: %s" % e)
        print("  Proceeding with pool companies only.")
        eeo1_rows = []

    extra_companies = []
    extra_count = 0
    skip_count = 0
    seen_extra = set()
    progress_interval = 5000

    for row_idx, row in enumerate(eeo1_rows):
        if row_idx > 0 and row_idx % progress_interval == 0:
            print("    ... processed %d/%d rows (extra=%d skip=%d)" % (
                row_idx, len(eeo1_rows), extra_count, skip_count))
            sys.stdout.flush()
        parsed = parse_eeo1_row(row)
        if not parsed:
            continue
        code = parsed["company_code"]
        naics = parsed.get("naics", "")
        if not naics or len(naics) < 4:
            skip_count += 1
            continue
        if code in pool_all_codes or code in seen_extra:
            continue
        if code in rec_lookup:
            # Has checkpoint data but not in pool -- rare edge case
            # Add to pool list so it gets processed
            seen_extra.add(code)
            state = parsed.get("state", "")
            zipcode = parsed.get("zipcode", "")
            naics4 = naics[:4]
            county_fips = zip_to_county(cur, zipcode) if zipcode else None
            if not county_fips:
                skip_count += 1
                continue
            extra_companies.append({
                "company_code": code,
                "name": parsed.get("name", ""),
                "naics": naics,
                "state": state,
                "zipcode": zipcode,
                "total": parsed.get("total", 0),
                "year": parsed.get("year", 0),
                "county_fips": county_fips,
                "state_fips": county_fips[:2],
                "classifications": {
                    "naics_group": classify_naics_group(naics4),
                    "region": get_census_region(state),
                },
            })
            extra_count += 1
            continue

        # Company not in checkpoint -- generate expert predictions
        state = parsed.get("state", "")
        zipcode = parsed.get("zipcode", "")
        naics4 = naics[:4]
        county_fips = zip_to_county(cur, zipcode) if zipcode else None
        if not county_fips:
            skip_count += 1
            continue
        state_fips = county_fips[:2]
        cbsa_code = cl.get_county_cbsa(county_fips) or ""

        try:
            d_result = cached_method_v6_full(
                cl, naics4, state_fips, county_fips,
                cbsa_code=cbsa_code, zipcode=zipcode)
        except Exception:
            d_result = {}
        try:
            a_result = expert_a_smoothed_ipf(cur, naics4, state_fips, county_fips)
        except Exception:
            a_result = {}
        try:
            f_result = cached_expert_f(
                cl, naics4, state_fips, county_fips, cbsa_code=cbsa_code)
        except Exception:
            f_result = {}

        expert_preds = {
            "D": {"race": d_result.get("race"),
                   "hispanic": d_result.get("hispanic"),
                   "gender": d_result.get("gender")},
            "A": {"race": a_result.get("race"),
                   "hispanic": a_result.get("hispanic"),
                   "gender": a_result.get("gender")},
            "F": {"gender": f_result.get("gender")},
        }

        if not expert_preds["D"].get("race"):
            skip_count += 1
            continue

        truth = {
            "race": parsed["race"],
            "hispanic": parsed["hispanic"],
            "gender": parsed["gender"],
            "total_employees": parsed.get("total", 0),
        }

        rec_lookup[code] = {
            "company_code": code,
            "truth": truth,
            "expert_preds": expert_preds,
        }
        seen_extra.add(code)

        extra_companies.append({
            "company_code": code,
            "name": parsed.get("name", ""),
            "naics": naics,
            "state": state,
            "zipcode": zipcode,
            "total": parsed.get("total", 0),
            "year": parsed.get("year", 0),
            "county_fips": county_fips,
            "state_fips": state_fips,
            "classifications": {
                "naics_group": classify_naics_group(naics4),
                "region": get_census_region(state),
            },
        })
        extra_count += 1

    print("  Extra EEO-1 companies: %d (skipped %d)" % (extra_count, skip_count))

    # Merge and deduplicate
    all_companies = all_pool + extra_companies
    seen = set()
    deduped = []
    for c in all_companies:
        code = c["company_code"]
        if code not in seen:
            seen.add(code)
            deduped.append(c)

    print("  Total unique companies: %d" % len(deduped))
    return deduped, rec_lookup


# ================================================================
# STRATIFIED K-FOLD SPLIT
# ================================================================

def stratified_kfold(records, k=5, seed=2026):
    """Assign each record to a fold, stratified by NAICS group x region.

    Returns dict: company_code -> fold_index (0..k-1)
    """
    strata = defaultdict(list)
    for rec in records:
        key = (rec["naics_group"], rec["region"])
        strata[key].append(rec["company_code"])

    rng = random.Random(seed)
    fold_map = {}

    for _key, codes in strata.items():
        rng.shuffle(codes)
        for i, code in enumerate(codes):
            fold_map[code] = i % k

    return fold_map


# ================================================================
# V11 PIPELINE PER FOLD
# ================================================================

def train_fold_pipeline(train_recs, all_recs, kappa=DEFAULT_KAPPA):
    """Train V11 pipeline on training records for one fold.

    1. Split train into 80% inner-train, 20% inner-val
    2. Train Hispanic weights on inner-train
    3. Train shrunk calibration on inner-train
    4. Find per-tier dampening on inner-val
    5. Retrain everything on FULL training set with found dampening
    6. Return prediction function

    Returns (predict_fn, tier_params, global_params).
    """
    rng = random.Random(42)
    shuffled = train_recs[:]
    rng.shuffle(shuffled)
    split = int(len(shuffled) * 0.80)
    inner_train = shuffled[:split]
    inner_val = shuffled[split:]

    # --- INNER: Train for dampening search ---
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}

    with suppress_stdout():
        industry_weights_inner = train_industry_weights(inner_train)
        tier_weights_inner = train_tier_weights(inner_train)
    hisp_fn_inner = make_hispanic_predictor(
        industry_weights_inner, tier_weights_inner, default_weights)
    for rec in all_recs:
        rec["hispanic_pred"] = hisp_fn_inner(rec)

    inner_cal = train_shrunk_calibration(
        inner_train, scenario_v92_full, kappa=kappa)
    inner_hisp_cal = train_shrunk_hispanic_cal(
        inner_train, scenario_v92_full, kappa=kappa)

    # Find per-tier dampening on inner-val (not used for calibration)
    tier_params, global_params = find_per_tier_dampening(
        inner_val, inner_cal, inner_hisp_cal)

    # --- FULL: Retrain on full training set ---
    with suppress_stdout():
        industry_weights = train_industry_weights(train_recs)
        tier_weights_full = train_tier_weights(train_recs)
    hisp_fn = make_hispanic_predictor(
        industry_weights, tier_weights_full, default_weights)
    for rec in all_recs:
        rec["hispanic_pred"] = hisp_fn(rec)

    cal = train_shrunk_calibration(
        train_recs, scenario_v92_full, kappa=kappa)
    hisp_cal = train_shrunk_hispanic_cal(
        train_recs, scenario_v92_full, kappa=kappa)

    # Count shrunk buckets
    level_counts = defaultdict(int)
    for k in cal:
        level_counts[k[2]] += 1
    for level in ["dt_reg_ind", "dt_ind", "reg_ind", "ind", "global"]:
        n = level_counts.get(level, 0)
        if n > 0:
            print("    cal %-15s %4d buckets" % (level, n))

    # Build prediction function
    def predict(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        tier = rec["diversity_tier"]
        params = tier_params.get(tier, global_params)
        return apply_shrunk_calibration(
            pred, rec, cal, hisp_cal,
            params["d_race"], params["d_hisp"], params["d_gender"])

    return predict, tier_params, global_params


# ================================================================
# K-FOLD RUNNER
# ================================================================

def run_kfold(records, k=5, kappa=DEFAULT_KAPPA, seed=2026):
    """Run K-fold cross-validation with V11 pipeline.

    Returns (predictions_list, fold_metrics_list, tier_params_list).
    """
    fold_map = stratified_kfold(records, k=k, seed=seed)

    fold_counts = defaultdict(int)
    for code, fold in fold_map.items():
        fold_counts[fold] += 1
    for i in range(k):
        print("  Fold %d: %d companies" % (i, fold_counts[i]))

    all_predictions = []
    fold_metrics = []
    all_tier_params = []

    for fold_idx in range(k):
        t0 = time.time()
        train_recs = [r for r in records
                      if fold_map.get(r["company_code"]) != fold_idx]
        test_recs = [r for r in records
                     if fold_map.get(r["company_code"]) == fold_idx]

        print("\n  --- Fold %d: train=%d test=%d ---" % (
            fold_idx, len(train_recs), len(test_recs)))

        predict_fn, tier_params, global_params = train_fold_pipeline(
            train_recs, records, kappa=kappa)

        all_tier_params.append(tier_params)

        # Print tier dampening for this fold
        print("    Dampening: global d_race=%.2f d_hisp=%.2f d_gender=%.2f" % (
            global_params["d_race"], global_params["d_hisp"],
            global_params["d_gender"]))
        for tier in ["Low", "Med-Low", "Med-High", "High"]:
            p = tier_params.get(tier, global_params)
            if p != global_params:
                print("    %-12s d_race=%.2f d_hisp=%.2f d_gender=%.2f" % (
                    tier, p["d_race"], p["d_hisp"], p["d_gender"]))

        # Evaluate on test
        m = evaluate(test_recs, predict_fn)
        if m:
            print("    Race=%.3f Hisp=%.3f Gender=%.3f | "
                  "P>20=%.1f%% P>30=%.1f%% AbsBias=%.3f" % (
                      m["race"], m["hisp"], m["gender"],
                      m["p20"], m["p30"], m["abs_bias"]))
            fold_metrics.append(m)

        # Collect predictions
        for rec in test_recs:
            pred = predict_fn(rec)
            all_predictions.append({
                "company_code": rec["company_code"],
                "name": rec.get("name", ""),
                "naics_group": rec["naics_group"],
                "region": rec["region"],
                "diversity_tier": rec["diversity_tier"],
                "total_employees": rec.get("total_employees", 0),
                "prediction": pred,
                "truth": rec["truth"],
                "fold": fold_idx,
            })

        print("    Fold %d complete in %.0fs" % (fold_idx, time.time() - t0))

    return all_predictions, fold_metrics, all_tier_params


# ================================================================
# BASELINES FOR COMPARISON
# ================================================================

def run_v10_insample(records):
    """Run V10 pipeline IN-SAMPLE (trains and evaluates on same data)."""
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    with suppress_stdout():
        iw = train_industry_weights(records)
        tw = train_tier_weights(records)
    hisp_fn = make_hispanic_predictor(iw, tw, default_weights)
    for rec in records:
        rec["hispanic_pred"] = hisp_fn(rec)

    std_cal = train_calibration_v92(records, scenario_v92_full, max_offset=20.0)
    hisp_cal = train_hispanic_calibration(records, scenario_v92_full, max_offset=15.0)

    def v10_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, std_cal, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal, 0.50)
        return result

    return evaluate(records, v10_fn)


def run_census_only(records):
    """Run expert predictions with NO calibration (pure census)."""
    default_weights = {"pums": 0.30, "ipf_ind": 0.30, "tract": 0.40}
    for rec in records:
        result = blend_hispanic(rec["signals"], default_weights)
        if result and "Hispanic" in result:
            rec["hispanic_pred"] = {
                "Hispanic": result["Hispanic"],
                "Not Hispanic": result["Not Hispanic"],
            }
        else:
            rec["hispanic_pred"] = None

    def census_fn(rec):
        return scenario_v92_full(rec)

    return evaluate(records, census_fn)


# ================================================================
# AGGREGATE METRICS FROM PREDICTIONS
# ================================================================

def compute_aggregate_metrics(predictions):
    """Compute overall metrics from K-fold predictions."""
    rm, hm, gm, me = [], [], [], []
    rp_all, ra_all = [], []

    for p in predictions:
        pred = p["prediction"]
        truth = p["truth"]
        if not pred:
            continue
        rp, ra = pred.get("race"), truth.get("race")
        if rp and ra:
            m = mae_dict(rp, ra, RACE_CATS)
            if m is not None:
                rm.append(m)
                mx = max_cat_error(rp, ra, RACE_CATS)
                if mx is not None:
                    me.append(mx)
                rp_all.append(rp)
                ra_all.append(ra)
        hp, ha = pred.get("hispanic"), truth.get("hispanic")
        if hp and ha:
            m = mae_dict(hp, ha, HISP_CATS)
            if m is not None:
                hm.append(m)
        gp, ga = pred.get("gender"), truth.get("gender")
        if gp and ga:
            m = mae_dict(gp, ga, GENDER_CATS)
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

    return {
        "race": sum(rm) / n,
        "hisp": sum(hm) / len(hm) if hm else 0,
        "gender": sum(gm) / len(gm) if gm else 0,
        "p20": sum(1 for e in me if e > 20) / len(me) * 100 if me else 0,
        "p30": sum(1 for e in me if e > 30) / len(me) * 100 if me else 0,
        "abs_bias": sum(ab) / len(ab) if ab else 0,
        "n": n,
    }


# ================================================================
# REPORTING HELPERS
# ================================================================

def print_comparison_table(m_census, m_v10, m_v11):
    """Print side-by-side comparison of three models."""
    print("  | %-15s | %-12s | %-12s | %-12s |" % (
        "Metric", "Census-only", "V10 in-samp", "V11 K-fold"))
    print("  |%s|%s|%s|%s|" % ("-" * 17, "-" * 14, "-" * 14, "-" * 14))
    for name, key, fmt in [
        ("Race MAE", "race", "%.3f"),
        ("Hispanic MAE", "hisp", "%.3f"),
        ("Gender MAE", "gender", "%.3f"),
        ("P>20pp", "p20", "%.1f%%"),
        ("P>30pp", "p30", "%.1f%%"),
        ("Abs Bias", "abs_bias", "%.3f"),
        ("N companies", "n", "%d"),
    ]:
        vc = fmt % m_census[key] if m_census else "N/A"
        vv = fmt % m_v10[key] if m_v10 else "N/A"
        v1 = fmt % m_v11[key] if m_v11 else "N/A"
        print("  | %-15s | %-12s | %-12s | %-12s |" % (name, vc, vv, v1))


def print_breakdown_by(predictions, group_key, label):
    """Print metrics broken down by a grouping key."""
    groups = defaultdict(list)
    for p in predictions:
        groups[p[group_key]].append(p)

    print("  %-40s %5s  %8s %8s %8s" % (label, "N", "Race", "Hisp", "Gender"))
    for group, preds in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(preds) < 10:
            continue
        m = compute_aggregate_metrics(preds)
        if m:
            print("  %-40s %5d  %7.3f  %7.3f  %7.3f" % (
                str(group)[:40], m["n"], m["race"], m["hisp"], m["gender"]))


# ================================================================
# MAIN
# ================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="V11 Demographics K-fold CV")
    parser.add_argument("--kappa", type=float, default=DEFAULT_KAPPA,
                        help="Shrinkage prior sample size (default: %d)" % DEFAULT_KAPPA)
    parser.add_argument("--folds", type=int, default=5,
                        help="Number of CV folds (default: 5)")
    parser.add_argument("--seed", type=int, default=2026,
                        help="Random seed for fold assignment")
    parser.add_argument("--pool-only", action="store_true",
                        help="Only use pool companies (skip extra EEO-1 loading)")
    args = parser.parse_args()

    t0 = time.time()
    print("V11 DEMOGRAPHICS: SHRINKAGE + PER-TIER DAMPENING + K-FOLD CV")
    print("=" * 80)
    print("  kappa=%g  folds=%d  seed=%d" % (args.kappa, args.folds, args.seed))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # --- Load all companies ---
    print("\n--- LOADING ALL EEO-1 COMPANIES ---")
    companies, rec_lookup = load_all_companies(cl, cur, pool_only=args.pool_only)

    # --- Build records ---
    print("\n--- BUILDING RECORDS ---")
    records = build_records(companies, rec_lookup, cl)
    print("  Valid records: %d" % len(records))

    # Distribution summary
    ng_counts = defaultdict(int)
    reg_counts = defaultdict(int)
    tier_counts = defaultdict(int)
    for r in records:
        ng_counts[r["naics_group"]] += 1
        reg_counts[r["region"]] += 1
        tier_counts[r["diversity_tier"]] += 1
    print("  Regions: %s" % ", ".join(
        "%s=%d" % (k, v) for k, v in sorted(reg_counts.items())))
    print("  Tiers: %s" % ", ".join(
        "%s=%d" % (k, v) for k, v in sorted(tier_counts.items())))
    print("  Top sectors:")
    for ng, cnt in sorted(ng_counts.items(), key=lambda x: -x[1])[:8]:
        print("    %-40s %5d" % (ng[:40], cnt))

    # --- Census-only baseline ---
    print("\n" + "=" * 80)
    print("CENSUS-ONLY BASELINE (zero calibration)")
    print("=" * 80)
    m_census = run_census_only(records)
    if m_census:
        print("  Race=%.3f Hisp=%.3f Gender=%.3f | "
              "P>20=%.1f%% P>30=%.1f%% AbsBias=%.3f (N=%d)" % (
                  m_census["race"], m_census["hisp"], m_census["gender"],
                  m_census["p20"], m_census["p30"], m_census["abs_bias"],
                  m_census["n"]))

    # --- V10 in-sample baseline ---
    print("\n" + "=" * 80)
    print("V10 IN-SAMPLE BASELINE (NOT out-of-sample -- for reference only)")
    print("=" * 80)
    m_v10 = run_v10_insample(records)
    if m_v10:
        print("  Race=%.3f Hisp=%.3f Gender=%.3f | "
              "P>20=%.1f%% P>30=%.1f%% AbsBias=%.3f (N=%d)" % (
                  m_v10["race"], m_v10["hisp"], m_v10["gender"],
                  m_v10["p20"], m_v10["p30"], m_v10["abs_bias"],
                  m_v10["n"]))

    # --- V11 K-fold ---
    print("\n" + "=" * 80)
    print("V11 %d-FOLD CROSS-VALIDATION (out-of-sample)" % args.folds)
    print("=" * 80)
    predictions, fold_metrics, tier_params = run_kfold(
        records, k=args.folds, kappa=args.kappa, seed=args.seed)

    # --- Aggregate results ---
    m_v11 = compute_aggregate_metrics(predictions)

    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS (%d companies, all out-of-sample)" % len(predictions))
    print("=" * 80)
    if m_v11:
        print("  Race MAE:     %.3f" % m_v11["race"])
        print("  Hispanic MAE: %.3f" % m_v11["hisp"])
        print("  Gender MAE:   %.3f" % m_v11["gender"])
        print("  P>20pp:       %.1f%%" % m_v11["p20"])
        print("  P>30pp:       %.1f%%" % m_v11["p30"])
        print("  Abs Bias:     %.3f" % m_v11["abs_bias"])

    # --- Comparison table ---
    print("\n" + "=" * 80)
    print("COMPARISON: Census-only vs V10 (in-sample) vs V11 (out-of-sample)")
    print("=" * 80)
    print_comparison_table(m_census, m_v10, m_v11)

    if m_census and m_v11:
        cal_gain_race = m_census["race"] - m_v11["race"]
        cal_gain_hisp = m_census["hisp"] - m_v11["hisp"]
        cal_gain_gender = m_census["gender"] - m_v11["gender"]
        print("\n  Calibration gain (census -> V11):")
        print("    Race: %.3f pp" % cal_gain_race)
        print("    Hispanic: %.3f pp" % cal_gain_hisp)
        print("    Gender: %.3f pp" % cal_gain_gender)

    if m_v10 and m_v11:
        gap_race = m_v11["race"] - m_v10["race"]
        gap_hisp = m_v11["hisp"] - m_v10["hisp"]
        gap_gender = m_v11["gender"] - m_v10["gender"]
        print("\n  V11 out-of-sample vs V10 in-sample:")
        print("    Race: %+.3f pp (positive = V11 higher/worse)" % gap_race)
        print("    Hispanic: %+.3f pp" % gap_hisp)
        print("    Gender: %+.3f pp" % gap_gender)
        print("    (V10 in-sample is artificially good -- expect V11 to be higher)")

    # --- Breakdowns ---
    print("\n" + "=" * 80)
    print("V11 BY DIVERSITY TIER")
    print("=" * 80)
    print_breakdown_by(predictions, "diversity_tier", "Tier")

    print("\n" + "=" * 80)
    print("V11 BY SECTOR")
    print("=" * 80)
    print_breakdown_by(predictions, "naics_group", "Sector")

    print("\n" + "=" * 80)
    print("V11 BY REGION")
    print("=" * 80)
    print_breakdown_by(predictions, "region", "Region")

    # --- Fold stability ---
    print("\n" + "=" * 80)
    print("FOLD STABILITY")
    print("=" * 80)
    if fold_metrics:
        print("  | %-5s | %-8s | %-8s | %-8s | %-7s | %-7s |" % (
            "Fold", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
        print("  |%s|%s|%s|%s|%s|%s|" % (
            "-" * 7, "-" * 10, "-" * 10, "-" * 10, "-" * 9, "-" * 9))
        for i, m in enumerate(fold_metrics):
            print("  | %-5d | %-8.3f | %-8.3f | %-8.3f | %-6.1f%% | %-6.1f%% |" % (
                i, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"]))
        avg_r = sum(m["race"] for m in fold_metrics) / len(fold_metrics)
        avg_h = sum(m["hisp"] for m in fold_metrics) / len(fold_metrics)
        avg_g = sum(m["gender"] for m in fold_metrics) / len(fold_metrics)
        std_r = (sum((m["race"] - avg_r) ** 2 for m in fold_metrics)
                 / len(fold_metrics)) ** 0.5
        print("  Mean Race: %.3f +/- %.3f" % (avg_r, std_r))

    # --- Per-tier dampening summary ---
    print("\n" + "=" * 80)
    print("PER-TIER DAMPENING (across folds)")
    print("=" * 80)
    for fold_idx, tp in enumerate(tier_params):
        parts = []
        for tier in ["Low", "Med-Low", "Med-High", "High"]:
            p = tp.get(tier, {})
            parts.append("%s:r%.2f/h%.2f/g%.2f" % (
                tier[:4], p.get("d_race", 0), p.get("d_hisp", 0),
                p.get("d_gender", 0)))
        print("  Fold %d: %s" % (fold_idx, "  ".join(parts)))

    # --- Save predictions ---
    out_path = os.path.join(SCRIPT_DIR, "v11_kfold_predictions.json")
    serializable = []
    for p in predictions:
        sp = {
            "company_code": p["company_code"],
            "name": p["name"],
            "naics_group": p["naics_group"],
            "region": p["region"],
            "diversity_tier": p["diversity_tier"],
            "total_employees": p["total_employees"],
            "fold": p["fold"],
        }
        pred = p["prediction"]
        truth = p["truth"]
        if pred:
            sp["pred_race"] = pred.get("race")
            sp["pred_hispanic"] = pred.get("hispanic")
            sp["pred_gender"] = pred.get("gender")
        sp["truth_race"] = truth.get("race")
        sp["truth_hispanic"] = truth.get("hispanic")
        sp["truth_gender"] = truth.get("gender")

        if pred and pred.get("race") and truth.get("race"):
            sp["race_mae"] = mae_dict(pred["race"], truth["race"], RACE_CATS)
            sp["max_error"] = max_cat_error(
                pred["race"], truth["race"], RACE_CATS)
        if pred and pred.get("hispanic") and truth.get("hispanic"):
            sp["hisp_mae"] = mae_dict(
                pred["hispanic"], truth["hispanic"], HISP_CATS)
        if pred and pred.get("gender") and truth.get("gender"):
            sp["gender_mae"] = mae_dict(
                pred["gender"], truth["gender"], GENDER_CATS)
        serializable.append(sp)

    save_json(out_path, {
        "meta": {
            "model": "V11",
            "method": "%d-fold stratified CV" % args.folds,
            "kappa": args.kappa,
            "seed": args.seed,
            "n_companies": len(predictions),
            "improvements": [
                "1. Bayesian shrinkage on calibration (kappa=%g)" % args.kappa,
                "2. Cross-validated dampening parameters",
                "3. Smooth hierarchy transitions (via shrinkage)",
                "4. Per-diversity-tier dampening",
            ],
        },
        "aggregate_v11_oos": {k: v for k, v in m_v11.items()} if m_v11 else {},
        "census_baseline": {k: v for k, v in m_census.items()
                            if k not in ("max_errors", "race_bias")} if m_census else {},
        "v10_insample": {k: v for k, v in m_v10.items()
                         if k not in ("max_errors", "race_bias")} if m_v10 else {},
        "fold_metrics": [{k: v for k, v in m.items()
                          if k not in ("max_errors", "race_bias")}
                         for m in fold_metrics],
        "predictions": serializable,
    })
    print("\n  Predictions saved to: %s" % out_path)
    print("  (%d companies)" % len(serializable))

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
