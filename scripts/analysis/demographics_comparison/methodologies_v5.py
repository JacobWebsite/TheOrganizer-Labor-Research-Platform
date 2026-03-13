"""V5 estimation methodologies: smoothed IPF, routing fixes, Expert models.

New features:
    - apply_floor() + smoothed IPF wrappers (fix zero-collapse)
    - M8-V5 and M5e-V5 with Admin/Staffing -> M1B routing fix
    - Expert A: Smoothed Dampened IPF with EEO-1 prior + alpha shrinkage
    - Expert B: Tract-Heavy Geography Model (35/25/40)
"""
import math

from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_lodes_pct_minority,
    get_tract_race, get_tract_hispanic, get_tract_gender,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf, _normalize,
    OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import (
    _variable_dampened_ipf, OPTIMAL_DAMPENING_BY_GROUP,
    _classify_m5_category, _zip_to_best_tract,
)
from config import (
    get_industry_weights, RACE_CATEGORIES,
    M8_M1B_HISPANIC_INDUSTRIES,
)
from classifiers import classify_naics_group, classify_region

RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']


# ============================================================
# IPF Smoothing Floor
# ============================================================
SMOOTHING_FLOOR = 0.1  # 0.1 percentage points (data is 0-100 scale)


def apply_floor(dist, floor=SMOOTHING_FLOOR):
    """Apply a minimum floor to all categories to prevent zero-collapse in IPF.

    Preserves metadata keys (starting with '_'). Renormalizes to maintain
    original total after flooring.
    """
    if dist is None:
        return None
    floored = {k: max(v, floor) for k, v in dist.items() if not k.startswith('_')}
    total = sum(floored.values())
    if total == 0:
        return dist
    # Preserve original scale (typically sums to ~100)
    orig_total = sum(v for k, v in dist.items() if not k.startswith('_'))
    if orig_total == 0:
        orig_total = 100.0
    result = {k: round(v * orig_total / total, 4) for k, v in floored.items()}
    # Preserve metadata keys
    for k, v in dist.items():
        if k.startswith('_'):
            result[k] = v
    return result


def smoothed_ipf(m1, m2, categories):
    """IPF with floored inputs to prevent zero-collapse."""
    return _ipf_two_marginals(apply_floor(m1), apply_floor(m2), categories)


def smoothed_dampened_ipf(m1, m2, categories):
    """Dampened IPF with floored inputs."""
    return _dampened_ipf(apply_floor(m1), apply_floor(m2), categories)


def smoothed_variable_dampened_ipf(m1, m2, categories, alpha):
    """Variable dampened IPF with floored inputs."""
    return _variable_dampened_ipf(apply_floor(m1), apply_floor(m2), categories, alpha)


# ============================================================
# M3e-V5: Finance/Utilities-Routed Variable Dampening (smoothed)
# Same as V4 M3e but uses smoothed IPF
# ============================================================
def method_3e_v5(cur, naics4, state_fips, county_fips):
    """M3e-V5: M3e with smoothed IPF to prevent zero-collapse."""
    group = classify_naics_group(naics4)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# M3c-V5: Variable Dampened IPF (smoothed)
# ============================================================
def method_3c_v5(cur, naics4, state_fips, county_fips):
    """M3c-V5: Variable dampened IPF with smoothing floor."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# M2c-V5: ZIP-Tract with PUMS fallback (smoothed)
# ============================================================
def method_2c_v5(cur, naics4, state_fips, county_fips, zipcode=''):
    """M2c-V5: Three-Layer with smoothed IPF."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    tract_fips = _zip_to_best_tract(cur, zipcode)
    tract_race = get_lodes_tract_race(cur, tract_fips) if tract_fips else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    tract_gender = get_lodes_tract_gender(cur, tract_fips) if tract_fips else None

    if tract_race is None:
        tract_race = get_tract_race(cur, county_fips)
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)
    if tract_gender is None:
        tract_gender = get_tract_gender(cur, county_fips)

    return {
        'race': _blend_dicts([
            (acs_race, 0.50), (lodes_race, 0.30), (tract_race, 0.20)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], HISP_CATS),
        'gender': _blend_dicts([
            (acs_gender, 0.50), (lodes_gender, 0.30), (tract_gender, 0.20)
        ], GENDER_CATS),
    }


# ============================================================
# M5e-V5: Industry-Category Routing (Admin/Staffing fix)
# ============================================================
def method_5e_v5(cur, naics4, state_fips, county_fips, zipcode=''):
    """M5e-V5: Industry dispatcher with Admin/Staffing -> M1B fix.

    OLD: Admin/Staffing -> M4e (occupation variance trim)
    NEW: Admin/Staffing -> M1b (learned weight blend)
    """
    category = _classify_m5_category(naics4)
    group = classify_naics_group(naics4)

    if category == 'occupation':
        if group in ('Finance/Insurance (52)', 'Utilities (22)'):
            return _run_m3_ipf_v5(cur, naics4, state_fips, county_fips)
        elif group == 'Admin/Staffing (56)':
            # FIX: route to M1b instead of M4e
            return _run_m1b_v5(cur, naics4, state_fips, county_fips)
        else:
            return _run_m3c_v5(cur, naics4, state_fips, county_fips)
    elif category == 'local_labor':
        return _run_m3d_v5(cur, naics4, state_fips, county_fips)
    elif category == 'manufacturing':
        if group == 'Computer/Electrical Mfg (334-335)':
            return _run_m1b_v5(cur, naics4, state_fips, county_fips)
        else:
            return _run_m3c_v5(cur, naics4, state_fips, county_fips)
    else:
        return _run_m3c_v5(cur, naics4, state_fips, county_fips)


# ============================================================
# M8-V5: Adaptive Context Router (Admin/Staffing fix)
# ============================================================
def method_8_v5(cur, naics4, state_fips, county_fips,
                naics_group='', county_minority_share=None,
                urbanicity='', state_abbr='', zipcode='', **kwargs):
    """M8-V5: Adaptive router with Admin/Staffing -> M1B fix.

    Race Router changes from V4:
    - Admin/Staffing (56) now routes to M1B instead of M4E
    - All IPF uses smoothed variants
    """
    if not naics_group:
        naics_group = classify_naics_group(naics4)
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if county_minority_share is None:
        county_minority_share = get_lodes_pct_minority(cur, county_fips)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    min_share = county_minority_share if county_minority_share is not None else 0.0
    routing_used = 'M3C'

    if naics_group == 'Finance/Insurance (52)':
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Utilities (22)':
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Admin/Staffing (56)':
        # FIX: route to M1B instead of M4E
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        race_result = _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], RACE_CATS)
        routing_used = 'M1B'
    elif min_share > 0.50:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        race_result = _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], RACE_CATS)
        routing_used = 'M1B'
    elif urbanicity == 'Suburban' and min_share < 0.25:
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif region == 'Midwest':
        if min_share > 0.20:
            race_result = smoothed_dampened_ipf(acs_race, lodes_race, RACE_CATS)
        else:
            race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3D'
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50)
        race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)
        routing_used = 'M3C'

    # === HISPANIC ROUTER ===
    hispanic_routing = 'M2C'
    if naics_group in M8_M1B_HISPANIC_INDUSTRIES:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        hisp_result = _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], HISP_CATS)
        hispanic_routing = 'M1B'
    else:
        tract_fips = _zip_to_best_tract(cur, zipcode) if zipcode else None
        tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
        if tract_hisp is None:
            tract_hisp = get_tract_hispanic(cur, county_fips)
        hisp_result = _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], HISP_CATS)
        hispanic_routing = 'M2C'

    # === GENDER: Always smoothed IPF ===
    gender_result = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

    return {
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        'routing_used': routing_used,
        'hispanic_routing': hispanic_routing,
    }


# ============================================================
# Expert A: Smoothed Dampened IPF + EEO-1 prior + alpha shrinkage
# (Populated in Run 3; placeholder for now)
# ============================================================

# National EEO-1 prior -- will be computed from EEO-1 CSV at module load
# These are reasonable defaults based on national workforce data
NATIONAL_EEO1_PRIOR = {
    'White': 60.0, 'Black': 13.0, 'Asian': 7.0,
    'AIAN': 1.0, 'NHOPI': 0.3, 'Two+': 2.7,
}

# Count of companies per NAICS group in 997-company training set
# Will be populated by generate_oof_predictions_v5.py
NAICS_GROUP_COUNTS = {}

PRIOR_WEIGHT = 2.0  # How much weight to give EEO-1 prior in smoothing


def _prior_smooth(dist, prior, weight=PRIOR_WEIGHT):
    """Smooth a distribution toward the national EEO-1 prior.

    For each category: smoothed_k = dist_k + weight * prior_k
    Then renormalize to original total.
    """
    if dist is None:
        return None
    cats = [k for k in dist if not k.startswith('_')]
    smoothed = {k: dist.get(k, 0) + weight * prior.get(k, 0) for k in cats}
    total = sum(smoothed.values())
    if total == 0:
        return dist
    orig_total = sum(dist.get(k, 0) for k in cats)
    if orig_total == 0:
        orig_total = 100.0
    result = {k: round(v * orig_total / total, 4) for k, v in smoothed.items()}
    for k, v in dist.items():
        if k.startswith('_'):
            result[k] = v
    return result


def expert_a_smoothed_ipf(cur, naics4, state_fips, county_fips, **kwargs):
    """Expert A: M3c + smoothing + EEO-1 prior + alpha shrinkage.

    1. Apply EEO-1 prior smoothing to ACS and LODES
    2. Shrink alpha toward 0.50 for small NAICS groups
    3. Run variable dampened IPF with smoothing floor
    """
    group = classify_naics_group(naics4)
    alpha_learned = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    # Alpha shrinkage: pull toward 0.50 for small NAICS groups
    n_segment = NAICS_GROUP_COUNTS.get(group, 5)
    alpha_final = (n_segment * alpha_learned + 5 * 0.50) / (n_segment + 5)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)

    # Apply EEO-1 prior smoothing
    acs_smooth = _prior_smooth(acs_race, NATIONAL_EEO1_PRIOR)
    lodes_smooth = _prior_smooth(lodes_race, NATIONAL_EEO1_PRIOR)

    # Smoothed variable dampened IPF
    race_result = smoothed_variable_dampened_ipf(acs_smooth, lodes_smooth, RACE_CATS, alpha_final)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# Expert B: Tract-Heavy Geography Model (35/25/40)
# ============================================================
def expert_b_tract_heavy(cur, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """Expert B: 35/25/40 ACS/LODES/Tract blend for ALL dimensions.

    Tract gets the highest weight (40%). Falls back to residential tract
    if workplace tract unavailable. If no tract at all, renormalize w1/w2.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # Tract data
    tract_fips = _zip_to_best_tract(cur, zipcode) if zipcode else None
    tract_race = get_lodes_tract_race(cur, tract_fips) if tract_fips else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    tract_gender = get_lodes_tract_gender(cur, tract_fips) if tract_fips else None

    # Fallback to residential tract
    if tract_race is None:
        tract_race = get_tract_race(cur, county_fips)
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)
    if tract_gender is None:
        tract_gender = get_tract_gender(cur, county_fips)

    # Weights: 35/25/40 with tract getting highest
    w1, w2, w3 = 0.35, 0.25, 0.40

    return {
        'race': _blend_dicts([
            (acs_race, w1), (lodes_race, w2), (tract_race, w3)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (acs_hisp, w1), (lodes_hisp, w2), (tract_hisp, w3)
        ], HISP_CATS),
        'gender': _blend_dicts([
            (acs_gender, w1), (lodes_gender, w2), (tract_gender, w3)
        ], GENDER_CATS),
    }


# ============================================================
# V5 Helper methods (smoothed versions)
# ============================================================

def _run_m3_ipf_v5(cur, naics4, state_fips, county_fips):
    """Run M3 original IPF with smoothing."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    return {
        'race': smoothed_ipf(acs_race, lodes_race, RACE_CATS),
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m3c_v5(cur, naics4, state_fips, county_fips):
    """Run M3c variable dampened IPF with smoothing."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    return {
        'race': smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m3d_v5(cur, naics4, state_fips, county_fips):
    """Run M3d selective dampening with smoothing."""
    pct_min = get_lodes_pct_minority(cur, county_fips)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    if pct_min is not None and pct_min > 0.20:
        race_result = smoothed_dampened_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m1b_v5(cur, naics4, state_fips, county_fips):
    """Run M1b learned weights."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    return {
        'race': _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], RACE_CATS),
        'hispanic': _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], HISP_CATS),
        'gender': _blend_dicts([(acs_gender, acs_w), (lodes_gender, lodes_w)], GENDER_CATS),
    }


# Methods that need extra kwargs
V5_METHODS_NEED_EXTRA = {
    'M2c-V5 PUMS-ZIP-Tract',
    'M5e-V5 Ind-Dispatch',
    'M8-V5 Adaptive-Router',
    'Expert-B Tract-Heavy',
}

# Registry of all V5 methods
ALL_V5_METHODS = {
    'M3c-V5 Smooth-Var-Damp': method_3c_v5,
    'M3e-V5 Smooth-Fin-Route': method_3e_v5,
    'M2c-V5 PUMS-ZIP-Tract': method_2c_v5,
    'M5e-V5 Ind-Dispatch': method_5e_v5,
    'M8-V5 Adaptive-Router': method_8_v5,
    'Expert-A Smooth-IPF': expert_a_smoothed_ipf,
    'Expert-B Tract-Heavy': expert_b_tract_heavy,
}
