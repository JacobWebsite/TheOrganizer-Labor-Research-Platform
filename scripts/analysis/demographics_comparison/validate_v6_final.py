"""V6 Final Validation: Full pipeline with dimension-specific estimation,
expert routing, gender bounds, and tiered confidence flags.

Evaluates V6 pipeline on permanent holdout and produces acceptance report.

Output: V6_FINAL_REPORT.md

Usage:
    py scripts/analysis/demographics_comparison/validate_v6_final.py
    py scripts/analysis/demographics_comparison/validate_v6_final.py --holdout permanent
    py scripts/analysis/demographics_comparison/validate_v6_final.py --holdout training
"""
import sys
import os
import json
import math
import time
import pickle
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from metrics import composite_score, mae
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_method_9b, cached_method_g1, cached_method_v6_full,
    cached_expert_e, cached_expert_f, cached_expert_g,
)
from cached_loaders_v5 import cached_method_3c_v5, cached_expert_a, cached_expert_b
from cached_loaders_v2 import cached_method_3b
from methodologies_v6 import apply_gender_bounds
from methodologies_v5 import RACE_CATS
from methodologies_v3 import OPTIMAL_DAMPENING_BY_GROUP
from classifiers import classify_naics_group, classify_region
from config import (
    EXPERT_E_INDUSTRIES, EXPERT_F_INDUSTRIES, NAICS_GENDER_BENCHMARKS,
    HIGH_GEOGRAPHIC_NAICS, get_census_region, get_county_minority_tier,
    REGIONAL_CALIBRATION_INDUSTRIES,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']

# Load trained gate model
_gate_path = os.path.join(SCRIPT_DIR, 'gate_v2.pkl')
GATE_MODEL = None
if os.path.exists(_gate_path):
    with open(_gate_path, 'rb') as _f:
        GATE_MODEL = pickle.load(_f)

# Expert dispatch: gate class name -> callable
EXPERT_DISPATCH = {
    'A': lambda cl, n4, sf, cf, **kw: cached_expert_a(cl, n4, sf, cf),
    'B': lambda cl, n4, sf, cf, **kw: cached_expert_b(cl, n4, sf, cf),
    'D': lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    'E': lambda cl, n4, sf, cf, **kw: cached_expert_e(cl, n4, sf, cf, **kw),
    'F': lambda cl, n4, sf, cf, **kw: cached_expert_f(cl, n4, sf, cf, **kw),
    'G': lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    'V6': lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}

# Load training-derived calibration (per-segment with global fallback)
_cal_path = os.path.join(SCRIPT_DIR, 'calibration_v2.json')
CALIBRATION = {}
if os.path.exists(_cal_path):
    with open(_cal_path, 'r', encoding='utf-8') as _f:
        CALIBRATION = json.load(_f)

# V8: Load NAICS4 vocabulary for gate features
_naics4_vocab_path = os.path.join(SCRIPT_DIR, 'naics4_vocab.pkl')
NAICS4_VOCAB = {}
if os.path.exists(_naics4_vocab_path):
    with open(_naics4_vocab_path, 'rb') as _f:
        NAICS4_VOCAB = pickle.load(_f)


def apply_calibration(result, expert_key, naics_group=None,
                      state=None, county_minority_pct=None,
                      dampening_rescale=1.0):
    """Apply segment-specific calibration corrections to race/hispanic/gender.

    V8 fallback hierarchy for REGIONAL_CALIBRATION_INDUSTRIES:
      1. county_tier sub-key (e.g. "Healthcare/Social (62)|county_tier:high")
      2. region sub-key (e.g. "Healthcare/Social (62)|region:South")
      3. industry-level key (e.g. "Healthcare/Social (62)")
      4. _global

    For other industries: industry-level -> _global (unchanged).

    dampening_rescale: multiply corrections by this factor to test different
    dampening values without retraining (e.g. 0.85/0.80 = 1.0625).

    Returns (result, calibration_level) where calibration_level is a string
    indicating which fallback was used.
    """
    expert_cal = CALIBRATION.get(expert_key, {})
    if not expert_cal:
        return result, 'none'

    calibration_level = 'global'

    for dim in ('race', 'hispanic', 'gender'):
        if not result.get(dim):
            continue

        global_cal = expert_cal.get('_global', {}).get(dim, {})

        # Build fallback chain for this company
        cal_chain = []

        if naics_group and naics_group in REGIONAL_CALIBRATION_INDUSTRIES:
            # V8: try county_tier and region sub-keys first
            if county_minority_pct is not None:
                tier = get_county_minority_tier(county_minority_pct)
                tier_key = '%s|county_tier:%s' % (naics_group, tier)
                tier_cal = expert_cal.get(tier_key, {}).get(dim, {})
                if tier_cal:
                    cal_chain.append(('county_tier', tier_cal))

            if state:
                region = get_census_region(state)
                region_key = '%s|region:%s' % (naics_group, region)
                region_cal = expert_cal.get(region_key, {}).get(dim, {})
                if region_cal:
                    cal_chain.append(('region', region_cal))

        # Industry-level
        seg_cal = expert_cal.get(naics_group, {}).get(dim, {}) if naics_group else {}
        if seg_cal:
            cal_chain.append(('industry', seg_cal))

        # Global fallback
        cal_chain.append(('global', global_cal))

        cats = list(result[dim].keys())
        for cat in cats:
            correction = 0.0
            level_used = 'global'

            for level_name, cal_dict in cal_chain:
                entry = cal_dict.get(cat, {})
                if isinstance(entry, dict) and 'correction' in entry:
                    correction = entry['correction']
                    level_used = level_name
                    break
                elif isinstance(entry, (int, float)):
                    correction = -entry * 0.15
                    level_used = level_name
                    break

            result[dim][cat] = result[dim][cat] + correction * dampening_rescale
            if dim == 'race' and level_used != 'global':
                calibration_level = level_used

        # Re-normalize to 100
        total = sum(result[dim].get(c, 0) for c in cats)
        if total > 0:
            for c in cats:
                result[dim][c] = round(result[dim][c] * 100.0 / total, 2)

    return result, calibration_level


# ============================================================
# Tiered Confidence Flags (Step 25)
# ============================================================

def compute_data_quality_score(company, cl, county_fips, naics4, cbsa_code):
    """Compute data quality score (0-1) based on data availability.

    Higher = more data sources available = more confident estimate.
    """
    score = 0.0
    checks = 0

    # ACS state data (always available)
    acs = cl.get_acs_race(naics4, company.get('state_fips', ''))
    score += 1.0 if acs else 0.0
    checks += 1

    # LODES county data
    lodes = cl.get_lodes_race(county_fips)
    score += 1.0 if lodes else 0.0
    checks += 1

    # PUMS metro data
    cbsa = cbsa_code
    naics_2 = naics4[:2] if naics4 else None
    pums = cl.get_pums_race(cbsa, naics_2) if cbsa else None
    score += 1.0 if pums else 0.0
    checks += 1

    # QCEW concentration
    qcew = cl.get_qcew_concentration(county_fips, naics_2) if naics_2 else None
    score += 1.0 if qcew else 0.0
    checks += 1

    # Tract data
    tract_fips = cl.get_zip_to_best_tract(company.get('zipcode', ''))
    tract = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
    score += 1.0 if tract else 0.0
    checks += 1

    # Occupation data (for gender)
    occ = cl.get_occupation_mix(naics4)
    score += 1.0 if occ else 0.0
    checks += 1

    return score / checks if checks > 0 else 0.0


def compute_confidence_tier(data_quality, gate_confidence, gender_flags):
    """Compute Red/Yellow/Green confidence tier.

    Thresholds calibrated for a 7-class gate (uniform = 1/7 ~ 0.143).
    Red: data_quality < 0.4 OR gate_confidence < 0.20 OR hard gender bound hit
    Yellow: data_quality < 0.7 OR gate_confidence < 0.35 OR soft gender bound
    Green: otherwise
    """
    has_hard_flag = any('hard' in f for f in gender_flags)
    has_soft_flag = any('soft' in f for f in gender_flags)

    if data_quality < 0.4 or gate_confidence < 0.20 or has_hard_flag:
        return 'RED'
    elif data_quality < 0.7 or gate_confidence < 0.35 or has_soft_flag:
        return 'YELLOW'
    else:
        return 'GREEN'


# ============================================================
# V6 Pipeline: predict_v6
# ============================================================

def _build_gate_features(company, cl, naics4, state_fips, county_fips,
                          zipcode, cbsa_code, naics_group, region, size_bucket):
    """Build the same feature vector the gate was trained on.

    V8: 6 categorical + 10 numeric = 16 features.
    New features: naics4_encoded, abs_minority_owner_share, transit_score,
    transit_tier_encoded.
    """
    import numpy as np
    from train_gate_v2 import compute_shannon_entropy

    # LODES minority share (categorical)
    lodes_race = cl.get_lodes_race(county_fips)
    if lodes_race:
        lodes_white = lodes_race.get('White', 0)
        lodes_minority_pct = 100.0 - lodes_white
        if lodes_minority_pct < 25:
            lodes_minority_share = 'Low (<25%)'
        elif lodes_minority_pct <= 50:
            lodes_minority_share = 'Medium (25-50%)'
        else:
            lodes_minority_share = 'High (>50%)'
    else:
        lodes_minority_share = 'Medium (25-50%)'

    naics_2 = naics4[:2] if naics4 else '99'

    # Categorical
    X_cat = [naics_group, region, size_bucket, lodes_minority_share, naics_2]

    # Numeric (must match train_gate_v2 order exactly)
    naics_2d_qcew = naics4[:2] if naics4 else None
    qcew_data = cl.get_qcew_concentration(county_fips, naics_2d_qcew)
    qcew_lq_val = float(qcew_data['location_quotient']) if qcew_data else 1.0
    raw_pay = qcew_data['avg_annual_pay'] if qcew_data and qcew_data['avg_annual_pay'] else 50000
    qcew_pay_val = math.log(max(raw_pay, 1000))

    acs_race = cl.get_acs_race(naics4, state_fips)
    acs_white = acs_race.get('White', 0) if acs_race else 0
    lodes_white_val = lodes_race.get('White', 0) if lodes_race else 0
    acs_lodes_div = abs(acs_white - lodes_white_val)

    tract_fips = cl.get_zip_to_best_tract(zipcode)
    tract_race = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
    tract_entropy = compute_shannon_entropy(tract_race, RACE_CATS)

    naics_2d = naics4[:2] if naics4 else None
    pums_race = cl.get_pums_race(cbsa_code, naics_2d) if cbsa_code else None
    has_pums = 1.0 if pums_race is not None else 0.0
    has_tract = 1.0 if tract_race is not None else 0.0
    occ_mix = cl.get_occupation_mix(naics4)
    has_occ = 1.0 if occ_mix else 0.0

    # V8 new features
    # naics4_encoded: use vocabulary from training (0 = "other"/unknown)
    naics4_code = naics4[:4] if naics4 else ''
    naics4_encoded = NAICS4_VOCAB.get(naics4_code, 0)

    # ABS minority owner share
    abs_data = cl.get_abs_owner_density(county_fips)
    abs_minority_share = abs_data['minority_share'] if abs_data else -1.0

    # Transit score
    transit_data = cl.get_transit_score(zipcode) if zipcode else None
    transit_score_val = transit_data['transit_score'] if transit_data else -1.0
    transit_tier_map = {'none': 0, 'minimal': 1, 'moderate': 2, 'high': 3}
    transit_tier_encoded = transit_tier_map.get(
        transit_data['transit_tier'], -1) if transit_data else -1

    X_num = [qcew_lq_val, qcew_pay_val, acs_lodes_div, tract_entropy,
             has_pums, has_tract, has_occ,
             naics4_encoded, abs_minority_share, transit_score_val]

    X_row = np.array([X_cat + [str(v) for v in X_num]]).reshape(1, -1)
    return X_row


def predict_v6(company, cl, cur):
    """Run V7 prediction pipeline with gate-based expert routing.

    1. Build features, query gate model for expert probabilities
    2. Apply soft routing overrides (Expert E boost for Finance, B for high-geo)
    3. Run top expert, apply segment calibration
    4. Apply CPS gender shrinkage and gender bounds
    5. Compute confidence tier

    Falls back to V6-Full if gate model not loaded.
    Returns (result_dict, metadata_dict).
    """
    naics = company.get('naics', '')
    naics4 = naics[:4]
    state_fips = company.get('state_fips', '')
    county_fips = company.get('county_fips', '')
    zipcode = company.get('zipcode', '')
    cls = company.get('classifications', {})
    naics_group = cls.get('naics_group', '')
    if not naics_group:
        naics_group = classify_naics_group(naics4)
    region = cls.get('region', classify_region(company.get('state', '')))
    size_bucket = cls.get('size', '100-999')

    # CBSA lookup
    cbsa_code = ''
    if county_fips:
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

    naics_2 = naics4[:2] if naics4 else ''

    # --- Gate-based routing ---
    gate_probs = {}
    gate_confidence = 0.50

    if GATE_MODEL is not None:
        try:
            import numpy as np
            X_row = _build_gate_features(
                company, cl, naics4, state_fips, county_fips,
                zipcode, cbsa_code, naics_group, region, size_bucket)
            pipeline = GATE_MODEL['pipeline']
            proba = pipeline.predict_proba(X_row)[0]
            classes = GATE_MODEL['classes']
            gate_probs = {cls_name: float(p) for cls_name, p in zip(classes, proba)}
        except Exception:
            gate_probs = {}

    # If gate failed, default probabilities
    if not gate_probs:
        gate_probs = {'V6': 1.0}

    # --- Soft routing overrides ---

    # Expert E boost for Finance/Utilities
    if naics_group in EXPERT_E_INDUSTRIES:
        current_e = gate_probs.get('E', 0.0)
        if current_e < 0.70:
            gate_probs['E'] = 0.70
            others = {k: v for k, v in gate_probs.items() if k != 'E'}
            others_total = sum(others.values())
            if others_total > 0:
                scale = 0.30 / others_total
                for k in others:
                    gate_probs[k] = others[k] * scale

    # Cap Expert E for non-Finance/Utilities sectors (Phase 0B)
    if naics_group not in EXPERT_E_INDUSTRIES:
        if gate_probs.get('E', 0) > 0.30:
            excess = gate_probs['E'] - 0.30
            gate_probs['E'] = 0.30
            others = {k: v for k, v in gate_probs.items() if k != 'E'}
            others_total = sum(others.values())
            if others_total > 0:
                scale = (others_total + excess) / others_total
                for k in others:
                    gate_probs[k] *= scale

    # Expert B boost for high-geographic sectors
    if naics_2 in HIGH_GEOGRAPHIC_NAICS:
        current_b = gate_probs.get('B', 0.0)
        if current_b < 0.45:
            gate_probs['B'] = 0.45
            others = {k: v for k, v in gate_probs.items() if k != 'B'}
            others_total = sum(others.values())
            if others_total > 0:
                scale = 0.55 / others_total
                for k in others:
                    gate_probs[k] = others[k] * scale

    # Expert G soft boost for Healthcare (Phase 0D)
    if naics_group == 'Healthcare/Social (62)':
        current_g = gate_probs.get('G', 0.0)
        if current_g < 0.20:
            boost = 0.20 - current_g
            gate_probs['G'] = 0.20
            others = {k: v for k, v in gate_probs.items() if k != 'G'}
            others_total = sum(others.values())
            if others_total > 0:
                scale = (1.0 - 0.20) / others_total
                for k in others:
                    gate_probs[k] = others[k] * scale

    # --- Run top expert ---
    best_expert = max(gate_probs, key=gate_probs.get)
    gate_confidence = gate_probs[best_expert]

    expert_fn = EXPERT_DISPATCH.get(best_expert)
    if expert_fn:
        try:
            result = expert_fn(cl, naics4, state_fips, county_fips,
                               cbsa_code=cbsa_code, zipcode=zipcode,
                               naics_group=naics_group)
        except Exception:
            result = None
    else:
        result = None

    # Fallback to V6-Full if top expert returned nothing
    if result is None or not result.get('race'):
        try:
            result = cached_method_v6_full(cl, naics4, state_fips, county_fips,
                                            cbsa_code=cbsa_code, zipcode=zipcode)
            best_expert = 'V6'
            gate_confidence = gate_probs.get('V6', 0.50)
        except Exception:
            result = None

    expert_used = best_expert
    if result is None:
        return None, {'expert_used': expert_used, 'confidence_tier': 'RED'}

    # Compute county minority pct for calibration fallback
    lodes_race_cal = cl.get_lodes_race(county_fips)
    county_minority_pct = None
    if lodes_race_cal:
        county_minority_pct = 100.0 - lodes_race_cal.get('White', 0)

    # Get dampening rescale from outer scope (set by --dampening arg)
    _dampening_rescale = getattr(predict_v6, '_dampening_rescale', 1.0)

    # Apply segment-specific calibration with regional fallback (V8)
    result, cal_level = apply_calibration(
        result, expert_used, naics_group=naics_group,
        state=company.get('state', ''),
        county_minority_pct=county_minority_pct,
        dampening_rescale=_dampening_rescale,
    )

    # CPS benchmark shrinkage for gender
    cps_benchmark = NAICS_GENDER_BENCHMARKS.get(naics_2)
    if result.get('gender') and cps_benchmark is not None:
        distance_from_50 = abs(cps_benchmark - 50.0)
        if distance_from_50 > 20:
            shrink_weight = 0.31
        elif distance_from_50 > 10:
            shrink_weight = 0.24
        else:
            shrink_weight = 0.14
        raw_female = result['gender'].get('Female', 50.0)
        shrunk_female = (1 - shrink_weight) * raw_female + shrink_weight * cps_benchmark
        result['gender'] = {
            'Female': round(shrunk_female, 2),
            'Male': round(100.0 - shrunk_female, 2),
        }

    # Apply gender bounds
    gender_flags = []
    if result.get('gender'):
        result['gender'], gender_flags = apply_gender_bounds(result['gender'], naics4)

    # Compute confidence
    data_quality = compute_data_quality_score(company, cl, county_fips, naics4, cbsa_code)
    confidence_tier = compute_confidence_tier(data_quality, gate_confidence, gender_flags)

    # YELLOW floor for Admin/Staffing (Phase 0C)
    naics_2_conf = naics4[:2] if naics4 else ''
    if naics_2_conf in HIGH_GEOGRAPHIC_NAICS and confidence_tier == 'GREEN':
        confidence_tier = 'YELLOW'

    metadata = {
        'expert_used': expert_used,
        'data_quality': round(data_quality, 3),
        'gate_confidence': round(gate_confidence, 3),
        'confidence_tier': confidence_tier,
        'gender_flags': gender_flags,
        'gate_probs': {k: round(v, 3) for k, v in sorted(gate_probs.items(), key=lambda x: -x[1])[:3]},
        'calibration_level': cal_level,
    }

    return result, metadata


# ============================================================
# Main validation
# ============================================================

def load_companies(holdout_type='permanent'):
    """Load company set for evaluation.

    If holdout_type ends in '.json', loads that file directly (relative to
    SCRIPT_DIR). Otherwise uses named presets: permanent, test, training.
    """
    if holdout_type.endswith('.json'):
        # Custom holdout file
        if os.path.isabs(holdout_type):
            path = holdout_type
        else:
            path = os.path.join(SCRIPT_DIR, holdout_type)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('companies', data)
    elif holdout_type == 'permanent':
        path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('companies', data)
    elif holdout_type == 'test':
        path = os.path.join(SCRIPT_DIR, 'selected_test_holdout_1000.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('companies', data)
    else:
        path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='V6 Final Validation')
    parser.add_argument('--holdout', default='test',
                        help='Which company set to evaluate on (permanent, test, training, or path to .json)')
    parser.add_argument('--no-gate', action='store_true',
                        help='Disable gate model (V6-only baseline)')
    parser.add_argument('--dampening', type=float, default=0.80,
                        help='Dampening factor for calibration (default: 0.80, baked-in)')
    args = parser.parse_args()

    if args.no_gate:
        global GATE_MODEL
        GATE_MODEL = None
        print('Gate model DISABLED (V6-only mode)')

    # Compute dampening rescale factor (Phase 0A)
    dampening_rescale = args.dampening / 0.80
    predict_v6._dampening_rescale = dampening_rescale
    if abs(dampening_rescale - 1.0) > 0.001:
        print('Dampening: %.2f (rescale factor: %.4f)' % (args.dampening, dampening_rescale))


    t0 = time.time()
    print('V6 FINAL VALIDATION')
    print('=' * 100)

    companies = load_companies(args.holdout)
    print('Holdout: %s (%d companies)' % (args.holdout, len(companies)))

    print('Loading all EEO-1 files...')
    eeo1_rows = load_all_eeo1_data()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Accumulators
    methods = {
        'V5 M3c (baseline)': [],
        'V6 Pipeline': [],
    }
    actuals = {m: [] for m in methods}
    hisp_preds = {m: [] for m in methods}
    hisp_actuals = {m: [] for m in methods}
    gender_preds = {m: [] for m in methods}
    gender_actuals = {m: [] for m in methods}

    tier_counts = {'RED': 0, 'YELLOW': 0, 'GREEN': 0}
    expert_counts = defaultdict(int)
    cal_level_counts = defaultdict(int)
    per_group_results = defaultdict(lambda: {'preds': [], 'actuals': []})
    company_details = []  # per-company metadata for distribution analysis
    skipped = 0

    for i, company in enumerate(companies):
        if (i + 1) % 50 == 0:
            print('  %d/%d...' % (i + 1, len(companies)))

        code = company.get('company_code', '')
        zipcode = company.get('zipcode', '')
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')

        if not county_fips and zipcode:
            county_fips = zip_to_county(cur, zipcode) or ''
            company['county_fips'] = county_fips
        if not state_fips and county_fips:
            state_fips = county_fips[:2]
            company['state_fips'] = state_fips
        if not county_fips:
            skipped += 1
            continue

        # Ground truth
        truth = None
        for row in eeo1_rows:
            if row.get('COMPANY') == code:
                truth = parse_eeo1_row(row)
                break
        if not truth or not truth.get('race'):
            skipped += 1
            continue

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic')
        actual_gender = truth.get('gender')
        naics4 = company.get('naics', '')[:4]

        # V5 baseline
        try:
            m3c = cached_method_3c_v5(cl, naics4, state_fips, county_fips)
        except Exception:
            m3c = {'race': None, 'hispanic': None, 'gender': None}

        # V6 pipeline
        v6_result, meta = predict_v6(company, cl, cur)
        tier_counts[meta.get('confidence_tier', 'RED')] += 1
        expert_counts[meta.get('expert_used', 'unknown')] += 1
        cal_level_counts[meta.get('calibration_level', 'none')] += 1

        naics_group = company.get('classifications', {}).get('naics_group', '')
        if not naics_group:
            naics_group = classify_naics_group(naics4)

        for method_name, result in [('V5 M3c (baseline)', m3c), ('V6 Pipeline', v6_result)]:
            if result and result.get('race'):
                methods[method_name].append(result['race'])
                actuals[method_name].append(actual_race)
                if method_name == 'V6 Pipeline':
                    per_group_results[naics_group]['preds'].append(result['race'])
                    per_group_results[naics_group]['actuals'].append(actual_race)
            if result and result.get('hispanic') and actual_hisp:
                hisp_preds[method_name].append(result['hispanic'])
                hisp_actuals[method_name].append(actual_hisp)
            if result and result.get('gender') and actual_gender:
                gender_preds[method_name].append(result['gender'])
                gender_actuals[method_name].append(actual_gender)

        # Track per-company detail for distribution analysis
        if v6_result and v6_result.get('race'):
            keys = [k for k in RACE_CATS if k in v6_result['race'] and k in actual_race]
            if keys:
                max_err = max(abs(v6_result['race'][k] - actual_race[k]) for k in keys)
                company_mae = sum(abs(v6_result['race'][k] - actual_race[k]) for k in keys) / len(keys)
                # Find which category had the worst error
                worst_cat = max(keys, key=lambda k: abs(v6_result['race'][k] - actual_race[k]))
                worst_dir = v6_result['race'][worst_cat] - actual_race[worst_cat]
                size_bucket = company.get('classifications', {}).get('size', '100-999')
                total_emp = company.get('total_employees', 0)
                company_details.append({
                    'name': company.get('name', ''),
                    'naics_group': naics_group,
                    'region': classify_region(company.get('state', '')),
                    'state': company.get('state', ''),
                    'size_bucket': size_bucket,
                    'total_employees': total_emp,
                    'expert': meta.get('expert_used', ''),
                    'max_error': max_err,
                    'company_mae': company_mae,
                    'worst_cat': worst_cat,
                    'worst_dir': worst_dir,
                    'data_quality': meta.get('data_quality', 0),
                })

    elapsed = time.time() - t0
    total_eval = len(methods['V6 Pipeline'])
    total_comp = total_eval + skipped
    print('')
    print('Processed %d/%d companies in %.1fs (%d skipped)' % (
        total_eval, total_comp, elapsed, skipped))

    # Compute final metrics
    print('')
    print('=' * 100)
    print('FINAL RESULTS')
    print('=' * 100)

    results = {}
    for mn in methods:
        cs = composite_score(methods[mn], actuals[mn], RACE_CATS)
        if not cs:
            continue
        h_mae_vals = []
        for p, a in zip(hisp_preds[mn], hisp_actuals[mn]):
            keys = [k for k in HISP_CATS if k in p and k in a]
            if keys:
                h_mae_vals.append(sum(abs(p[k] - a[k]) for k in keys) / len(keys))
        h_mae = sum(h_mae_vals) / len(h_mae_vals) if h_mae_vals else None

        g_mae_vals = []
        for p, a in zip(gender_preds[mn], gender_actuals[mn]):
            keys = [k for k in GENDER_CATS if k in p and k in a]
            if keys:
                g_mae_vals.append(sum(abs(p[k] - a[k]) for k in keys) / len(keys))
        g_mae = sum(g_mae_vals) / len(g_mae_vals) if g_mae_vals else None

        results[mn] = {
            'race_mae': cs['avg_mae'],
            'p_gt_20pp': cs['p_gt_20pp'],
            'p_gt_30pp': cs['p_gt_30pp'],
            'abs_bias': cs['mean_abs_bias'],
            'composite': cs['composite'],
            'hisp_mae': h_mae,
            'gender_mae': g_mae,
            'n': cs['n_companies'],
        }

        print('%-20s | Race=%.3f P>20=%.1f%% P>30=%.1f%% Bias=%.3f Hisp=%s Gend=%s N=%d' % (
            mn, cs['avg_mae'], cs['p_gt_20pp'] * 100, cs['p_gt_30pp'] * 100,
            cs['mean_abs_bias'],
            '%.3f' % h_mae if h_mae else 'N/A',
            '%.3f' % g_mae if g_mae else 'N/A',
            cs['n_companies']))

    # Confidence tiers
    total_tiers = sum(tier_counts.values())
    print('')
    print('Confidence Tiers:')
    for tier in ['GREEN', 'YELLOW', 'RED']:
        ct = tier_counts[tier]
        print('  %s: %d (%.1f%%)' % (tier, ct, 100.0 * ct / total_tiers if total_tiers > 0 else 0))

    print('')
    print('Expert routing:')
    for exp, cnt in sorted(expert_counts.items()):
        print('  %s: %d' % (exp, cnt))

    print('')
    print('Calibration level usage:')
    for level, cnt in sorted(cal_level_counts.items()):
        print('  %s: %d' % (level, cnt))

    # Per-segment MAE
    print('')
    print('Per-industry-group Race MAE:')
    group_maes = {}
    for group_name, data in sorted(per_group_results.items()):
        cs = composite_score(data['preds'], data['actuals'], RACE_CATS)
        if cs and cs['n_companies'] >= 5:
            group_maes[group_name] = cs['avg_mae']
            print('  %-40s MAE=%.3f N=%d' % (group_name, cs['avg_mae'], cs['n_companies']))

    # Per-category signed bias diagnostic
    v6_preds = methods.get('V6 Pipeline', [])
    v6_acts = actuals.get('V6 Pipeline', [])
    if v6_preds:
        print('')
        print('V6 Per-category signed bias (pred - actual):')
        for cat in RACE_CATS:
            signed_errors = [p.get(cat, 0) - a.get(cat, 0) for p, a in zip(v6_preds, v6_acts)]
            mean_se = sum(signed_errors) / len(signed_errors) if signed_errors else 0
            print('  %-8s mean_signed_error = %+.3f' % (cat, mean_se))
        # Gender signed bias
        v6_gp = gender_preds.get('V6 Pipeline', [])
        v6_ga = gender_actuals.get('V6 Pipeline', [])
        if v6_gp:
            for cat in GENDER_CATS:
                signed_errors = [p.get(cat, 0) - a.get(cat, 0) for p, a in zip(v6_gp, v6_ga)]
                mean_se = sum(signed_errors) / len(signed_errors) if signed_errors else 0
                print('  %-8s mean_signed_error = %+.3f' % (cat, mean_se))

    # Max-error distribution for V6 Pipeline
    if v6_preds:
        max_errors = []
        for p, a in zip(v6_preds, v6_acts):
            keys = [k for k in RACE_CATS if k in p and k in a]
            if keys:
                max_errors.append(max(abs(p[k] - a[k]) for k in keys))
        if max_errors:
            thresholds = [1, 3, 5, 10, 15, 20, 30]
            print('')
            print('Max race category error distribution (V6 Pipeline):')
            prev = 0
            for t in thresholds:
                count = sum(1 for e in max_errors if prev < e <= t)
                pct = 100.0 * count / len(max_errors)
                print('  %3d < err <= %2d pp:  %4d companies  (%5.1f%%)' % (prev, t, count, pct))
                prev = t
            count_over = sum(1 for e in max_errors if e > 30)
            pct_over = 100.0 * count_over / len(max_errors)
            print('       err >  30 pp:  %4d companies  (%5.1f%%)' % (count_over, pct_over))
            print('  Total: %d companies' % len(max_errors))

    # Error bucket profiling
    if company_details:
        thresholds = [1, 3, 5, 10, 15, 20, 30, float('inf')]
        bucket_labels = ['0-1', '1-3', '3-5', '5-10', '10-15', '15-20', '20-30', '>30']
        buckets = {label: [] for label in bucket_labels}
        for cd in company_details:
            e = cd['max_error']
            prev = 0
            for t, label in zip(thresholds, bucket_labels):
                if e <= t:
                    buckets[label].append(cd)
                    break
                prev = t

        print('')
        print('=' * 100)
        print('ERROR BUCKET PROFILING')
        print('=' * 100)

        for label in bucket_labels:
            items = buckets[label]
            if not items:
                continue
            n = len(items)
            print('')
            print('--- Bucket: max error %s pp  (%d companies, %.1f%%) ---' % (
                label, n, 100.0 * n / len(company_details)))

            # Industry breakdown (top 5)
            ind_counts = defaultdict(int)
            for cd in items:
                ind_counts[cd['naics_group']] += 1
            top_inds = sorted(ind_counts.items(), key=lambda x: -x[1])[:5]
            print('  Top industries: %s' % ', '.join(
                '%s(%d)' % (k, v) for k, v in top_inds))

            # Expert breakdown
            exp_counts = defaultdict(int)
            for cd in items:
                exp_counts[cd['expert']] += 1
            print('  Expert routing: %s' % ', '.join(
                '%s:%d' % (k, v) for k, v in sorted(exp_counts.items())))

            # Region breakdown
            reg_counts = defaultdict(int)
            for cd in items:
                reg_counts[cd['region']] += 1
            print('  Regions: %s' % ', '.join(
                '%s:%d' % (k, v) for k, v in sorted(reg_counts.items())))

            # Size breakdown
            size_counts = defaultdict(int)
            for cd in items:
                size_counts[cd['size_bucket']] += 1
            print('  Sizes: %s' % ', '.join(
                '%s:%d' % (k, v) for k, v in sorted(size_counts.items())))

            # Worst category breakdown
            cat_counts = defaultdict(int)
            for cd in items:
                cat_counts[cd['worst_cat']] += 1
            print('  Worst category: %s' % ', '.join(
                '%s:%d' % (k, v) for k, v in sorted(cat_counts.items(), key=lambda x: -x[1])))

            # Avg data quality
            avg_dq = sum(cd['data_quality'] for cd in items) / n
            avg_mae = sum(cd['company_mae'] for cd in items) / n
            print('  Avg data quality: %.2f  Avg race MAE: %.1f' % (avg_dq, avg_mae))

            # For >20pp buckets, show direction of worst errors
            if label in ('20-30', '>30'):
                over_counts = defaultdict(lambda: {'over': 0, 'under': 0})
                for cd in items:
                    if cd['worst_dir'] > 0:
                        over_counts[cd['worst_cat']]['over'] += 1
                    else:
                        over_counts[cd['worst_cat']]['under'] += 1
                print('  Error direction: %s' % ', '.join(
                    '%s(over:%d/under:%d)' % (k, v['over'], v['under'])
                    for k, v in sorted(over_counts.items(), key=lambda x: -(x[1]['over']+x[1]['under']))))

    # V6 targets check
    v6 = results.get('V6 Pipeline', {})
    print('')
    print('=' * 100)
    print('V6 ACCEPTANCE CRITERIA')
    print('=' * 100)
    red_rate = tier_counts['RED'] / total_tiers * 100 if total_tiers > 0 else 100
    checks = [
        ('Race MAE < 4.50 pp', v6.get('race_mae', 99), 4.50),
        ('P>20pp < 16%%', v6.get('p_gt_20pp', 1) * 100, 16.0),
        ('P>30pp < 6%%', v6.get('p_gt_30pp', 1) * 100, 6.0),
        ('Abs Bias < 1.10', v6.get('abs_bias', 99), 1.10),
        ('Hispanic MAE < 8.00 pp', v6.get('hisp_mae', 99) or 99, 8.00),
        ('Gender MAE < 12.00 pp', v6.get('gender_mae', 99) or 99, 12.00),
        ('Red flag rate < 15%%', red_rate, 15.0),
    ]
    passed = 0
    for label, actual_val, target in checks:
        status = 'PASS' if actual_val < target else 'FAIL'
        if status == 'PASS':
            passed += 1
        print('  [%s] %s: actual=%.3f, target=%.3f' % (
            'x' if status == 'PASS' else ' ', label, actual_val, target))
    print('')
    print('Result: %d/%d criteria passed' % (passed, len(checks)))

    # Write report
    report_path = os.path.join(SCRIPT_DIR, 'V6_FINAL_REPORT.md')
    _write_report(report_path, results, tier_counts, expert_counts,
                  group_maes, args.holdout, total_eval, skipped, elapsed, checks)
    print('Report: %s' % report_path)
    conn.close()


def _write_report(path, results, tier_counts, expert_counts, group_maes,
                  holdout_type, n_processed, n_skipped, elapsed, checks):
    """Write V6_FINAL_REPORT.md."""
    lines = [
        '# V6 Final Validation Report',
        '',
        '**Holdout:** %s' % holdout_type,
        '**Companies:** %d processed, %d skipped' % (n_processed, n_skipped),
        '**Runtime:** %.1fs' % elapsed,
        '',
        '---',
        '',
        '## Results',
        '',
        '| Method | Race MAE | P>20pp | P>30pp | Abs Bias | Hisp MAE | Gender MAE | N |',
        '|--------|---------|--------|--------|----------|----------|------------|---|',
    ]
    for mn, r in results.items():
        h_str = '%.3f' % r['hisp_mae'] if r['hisp_mae'] else 'N/A'
        g_str = '%.3f' % r['gender_mae'] if r['gender_mae'] else 'N/A'
        lines.append('| %s | %.3f | %.1f%% | %.1f%% | %.3f | %s | %s | %d |' % (
            mn, r['race_mae'], r['p_gt_20pp'] * 100, r['p_gt_30pp'] * 100,
            r['abs_bias'], h_str, g_str, r['n']))

    lines.extend(['', '## Confidence Tiers', ''])
    total = sum(tier_counts.values())
    for tier in ['GREEN', 'YELLOW', 'RED']:
        ct = tier_counts[tier]
        lines.append('- **%s:** %d (%.1f%%)' % (tier, ct, 100.0 * ct / total if total > 0 else 0))

    lines.extend(['', '## Expert Routing', ''])
    for exp, cnt in sorted(expert_counts.items()):
        lines.append('- %s: %d companies' % (exp, cnt))

    lines.extend(['', '## Per-Industry-Group Race MAE', ''])
    lines.append('| Industry Group | Race MAE |')
    lines.append('|---------------|---------|')
    for gn, gm in sorted(group_maes.items(), key=lambda x: x[1]):
        lines.append('| %s | %.3f |' % (gn, gm))

    lines.extend(['', '## Acceptance Criteria', ''])
    passed = 0
    for label, actual_val, target in checks:
        status = 'PASS' if actual_val < target else 'FAIL'
        if status == 'PASS':
            passed += 1
        lines.append('- [%s] %s: actual=%.3f, target=%.3f' % (
            'x' if status == 'PASS' else ' ', label, actual_val, target))
    lines.append('')
    lines.append('**Result: %d/%d criteria passed**' % (passed, len(checks)))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
