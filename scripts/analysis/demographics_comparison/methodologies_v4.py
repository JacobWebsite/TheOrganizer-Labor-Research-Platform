"""V4 estimation methodologies: 7 new methods.

6 tweaked methods + 1 meta-method (M8 Adaptive Context Router).
Do not modify any existing V1/V2/V3 method files.

New methods:
    M3e  -- Finance/Utilities-Routed Variable Dampening
    M3f  -- Minority + Industry Threshold Tuning
    M1e  -- High-Minority Floor Constraint
    M4e  -- Demographic-Variance Occupation Trim
    M2d  -- Amplified Geographic Tract Layer
    M5e  -- Industry-Category Routing Dispatcher
    M8   -- Adaptive Context Router (meta-method)
"""
from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_occupation_mix, get_acs_by_occupation,
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_lodes_pct_minority,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf, _normalize,
    _build_occ_weighted, OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import (
    _variable_dampened_ipf, OPTIMAL_DAMPENING_BY_GROUP,
    OPTIMAL_WEIGHTS_V3_BY_GROUP, M5_CATEGORY_PREFIXES,
    _classify_m5_category, _zip_to_best_tract,
)
from config import (
    get_industry_weights, RACE_CATEGORIES,
    M4_VARIANCE_THRESHOLD, OPTIMAL_M3F_THRESHOLD, M8_M1B_HISPANIC_INDUSTRIES,
)
from classifiers import classify_naics_group, classify_region

RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']


# ============================================================
# M3e: Finance/Utilities-Routed Variable Dampening
# If Finance/Insurance or Utilities: use original IPF (M3)
# Else: use variable dampened IPF (M3c)
# ============================================================
def method_3e_fin_route_ipf(cur, naics4, state_fips, county_fips):
    """M3e: Route Finance/Utilities to original IPF, others to M3c."""
    group = classify_naics_group(naics4)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        race_result = _variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# M3f: Minority + Industry Threshold Tuning
# Finance/Utilities -> M3 IPF
# county_minority > threshold -> dampened IPF (M3b)
# Else -> M3 IPF
# ============================================================
def method_3f_min_ind_thresh(cur, naics4, state_fips, county_fips):
    """M3f: Industry + minority threshold routing."""
    group = classify_naics_group(naics4)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    else:
        pct_min = get_lodes_pct_minority(cur, county_fips)
        if pct_min is not None and pct_min > OPTIMAL_M3F_THRESHOLD:
            race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
        else:
            race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)

    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# M1e: High-Minority Floor Constraint
# Adjusts LODES weight floor based on county minority share
# ============================================================
def method_1e_hi_min_floor(cur, naics4, state_fips, county_fips):
    """M1e: M1b with LODES floor in high-minority counties."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_GROUP.get(group, (0.55, 0.45))

    pct_min = get_lodes_pct_minority(cur, county_fips)
    if pct_min is not None:
        if pct_min > 0.50:
            lodes_w = max(lodes_w, 0.40)
            acs_w = 1.0 - lodes_w
        elif pct_min > 0.30:
            lodes_w = max(lodes_w, 0.30)
            acs_w = 1.0 - lodes_w

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


# ============================================================
# M4e: Demographic-Variance Occupation Trim
# Filter out occupations whose White share deviates too far from baseline
# ============================================================
def method_4e_var_occ_trim(cur, naics4, state_fips, county_fips):
    """M4e: Occupation-weighted ACS with demographic-variance filtering.

    Excludes occupations whose White share deviates > M4_VARIANCE_THRESHOLD pp
    from the industry ACS baseline. Renormalizes remaining weights.
    70/30 blend with LODES.
    """
    occ_mix = get_occupation_mix(cur, naics4)
    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if not occ_mix:
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        return {
            'race': _blend_dicts([(acs_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
            'hispanic': _blend_dicts([(acs_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
            'gender': _blend_dicts([(acs_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
        }

    # Get industry ACS baseline White share
    baseline = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    baseline_white = baseline.get('White', 0) if baseline else 0

    # Filter occupations by White deviation
    filtered_mix = []
    for soc, pct in occ_mix[:30]:
        occ_demo = get_acs_by_occupation(cur, soc, state_fips, 'race')
        if not occ_demo:
            occ_demo = get_acs_by_occupation(cur, soc, '0', 'race')
        if occ_demo:
            occ_white = occ_demo.get('White', 0)
            deviation = occ_white - baseline_white
            if deviation <= M4_VARIANCE_THRESHOLD:
                filtered_mix.append((soc, pct))
        else:
            # No demographic data -- include by default
            filtered_mix.append((soc, pct))

    # Fallback: if all filtered out, use top-10
    if not filtered_mix:
        filtered_mix = occ_mix[:10]

    # Build weighted estimates from filtered mix
    occ_race = _build_filtered_occ_weighted(cur, filtered_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = _build_filtered_occ_weighted(cur, filtered_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = _build_filtered_occ_weighted(cur, filtered_mix, state_fips, 'gender', GENDER_CATS)

    return {
        'race': _blend_dicts([(occ_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([(occ_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
        'gender': _blend_dicts([(occ_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
    }


def _build_filtered_occ_weighted(cur, occ_mix, state_fips, dimension, categories):
    """Build occupation-weighted estimate from a filtered occupation list."""
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for soc_code, pct_of_industry in occ_mix:
        demo = get_acs_by_occupation(cur, soc_code, state_fips, dimension)
        if not demo:
            demo = get_acs_by_occupation(cur, soc_code, '0', dimension)
        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None

    return {k: round(weighted[k] / total_weight, 2) for k in categories}


# ============================================================
# M2d: Amplified Geographic Tract Layer
# Same as M2c but weights changed: 0.45/0.20/0.35 (more tract weight)
# ============================================================
def method_2d_amp_tract(cur, naics4, state_fips, county_fips, zipcode=''):
    """M2d: Three-Layer with amplified tract weight (45/20/35)."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # ZIP-to-tract crosswalk
    tract_fips = _zip_to_best_tract(cur, zipcode)
    tract_race = get_lodes_tract_race(cur, tract_fips) if tract_fips else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    tract_gender = get_lodes_tract_gender(cur, tract_fips) if tract_fips else None

    # Fallback to residential tract data
    from data_loaders import get_tract_race, get_tract_hispanic, get_tract_gender
    if tract_race is None:
        tract_race = get_tract_race(cur, county_fips)
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)
    if tract_gender is None:
        tract_gender = get_tract_gender(cur, county_fips)

    return {
        'race': _blend_dicts([
            (acs_race, 0.45), (lodes_race, 0.20), (tract_race, 0.35)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (acs_hisp, 0.45), (lodes_hisp, 0.20), (tract_hisp, 0.35)
        ], HISP_CATS),
        'gender': _blend_dicts([
            (acs_gender, 0.45), (lodes_gender, 0.20), (tract_gender, 0.35)
        ], GENDER_CATS),
    }


# ============================================================
# M5e: Industry-Category Routing Dispatcher
# Routes to actual methods instead of weight blending
# ============================================================
def method_5e_ind_dispatch(cur, naics4, state_fips, county_fips, zipcode=''):
    """M5e: Route to best method per industry category.

    occupation category:
        Finance/Insurance or Utilities -> M3 original IPF
        Admin/Staffing -> M4e
        Else -> M3c
    local_labor -> M3d (selective dampening)
    manufacturing:
        Computer/Electrical Mfg -> M1b weights
        Else -> M3c
    default -> M3c
    """
    category = _classify_m5_category(naics4)
    group = classify_naics_group(naics4)

    if category == 'occupation':
        if group in ('Finance/Insurance (52)', 'Utilities (22)'):
            return _run_m3_ipf(cur, naics4, state_fips, county_fips)
        elif group == 'Admin/Staffing (56)':
            return method_4e_var_occ_trim(cur, naics4, state_fips, county_fips)
        else:
            return _run_m3c(cur, naics4, state_fips, county_fips)
    elif category == 'local_labor':
        return _run_m3d(cur, naics4, state_fips, county_fips)
    elif category == 'manufacturing':
        if group == 'Computer/Electrical Mfg (334-335)':
            return _run_m1b(cur, naics4, state_fips, county_fips)
        else:
            return _run_m3c(cur, naics4, state_fips, county_fips)
    else:
        return _run_m3c(cur, naics4, state_fips, county_fips)


# ============================================================
# M8: Adaptive Context Router (meta-method)
# Routes companies to best sub-method based on industry, geography,
# and minority share. Separate routers for race and Hispanic.
# ============================================================
def method_8_adaptive_router(cur, naics4, state_fips, county_fips,
                              naics_group='', county_minority_share=None,
                              urbanicity='', state_abbr='', zipcode='',
                              **kwargs):
    """M8: Adaptive Context Router.

    Race Router (priority order):
    1. Finance/Insurance -> M3 original IPF
    2. Utilities -> M3 original IPF
    3. Admin/Staffing -> M4e
    4. county_minority_share > 0.50 -> M1b
    5. Suburban AND minority < 0.25 -> M3 original IPF
    6. Midwest -> M3d
    7. Default -> M3c

    Hispanic Router:
    - M1B_HISPANIC_INDUSTRIES -> M1b Hispanic
    - All others -> M2c Hispanic (needs zipcode)

    Gender: Always IPF

    Returns dict with extra 'routing_used' key.
    """
    # Classify if not provided
    if not naics_group:
        naics_group = classify_naics_group(naics4)
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if county_minority_share is None:
        county_minority_share = get_lodes_pct_minority(cur, county_fips)

    # Get base data
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # === RACE ROUTER ===
    routing_used = 'M3C'  # default
    min_share = county_minority_share if county_minority_share is not None else 0.0

    if naics_group == 'Finance/Insurance (52)':
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Utilities (22)':
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Admin/Staffing (56)':
        m4e = method_4e_var_occ_trim(cur, naics4, state_fips, county_fips)
        race_result = m4e.get('race')
        routing_used = 'M4E'
    elif min_share > 0.50:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        race_result = _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], RACE_CATS)
        routing_used = 'M1B'
    elif urbanicity == 'Suburban' and min_share < 0.25:
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif region == 'Midwest':
        # M3d: selective dampening
        if min_share > 0.20:
            race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
        else:
            race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3D'
    else:
        # M3c: variable dampened IPF
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50)
        race_result = _variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)
        routing_used = 'M3C'

    # === HISPANIC ROUTER ===
    hispanic_routing = 'M2C'
    if naics_group in M8_M1B_HISPANIC_INDUSTRIES:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        hisp_result = _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], HISP_CATS)
        hispanic_routing = 'M1B'
    else:
        # M2c Hispanic: use ZIP-to-tract crosswalk
        tract_fips = _zip_to_best_tract(cur, zipcode) if zipcode else None
        tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
        if tract_hisp is None:
            from data_loaders import get_tract_hispanic
            tract_hisp = get_tract_hispanic(cur, county_fips)
        hisp_result = _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], HISP_CATS)
        hispanic_routing = 'M2C'

    # === GENDER: Always IPF ===
    gender_result = _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS)

    return {
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        'routing_used': routing_used,
        'hispanic_routing': hispanic_routing,
    }


# ============================================================
# Helper methods used by M5e routing
# ============================================================

def _run_m3_ipf(cur, naics4, state_fips, county_fips):
    """Run M3 original IPF."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    return {
        'race': _ipf_two_marginals(acs_race, lodes_race, RACE_CATS),
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m3c(cur, naics4, state_fips, county_fips):
    """Run M3c variable dampened IPF."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    return {
        'race': _variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha),
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m3d(cur, naics4, state_fips, county_fips):
    """Run M3d selective dampening."""
    pct_min = get_lodes_pct_minority(cur, county_fips)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    if pct_min is not None and pct_min > 0.20:
        race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


def _run_m1b(cur, naics4, state_fips, county_fips):
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


# ============================================================
# Methods that need extra kwargs beyond standard (cur, naics4, state_fips, county_fips)
# ============================================================
V4_METHODS_NEED_EXTRA = {'M2d Amp-Tract', 'M8 Adaptive-Router'}

# Registry of all V4 methods
ALL_V4_METHODS = {
    'M3e Fin-Route-IPF': method_3e_fin_route_ipf,
    'M3f Min-Ind-Thresh': method_3f_min_ind_thresh,
    'M1e Hi-Min-Floor': method_1e_hi_min_floor,
    'M4e Var-Occ-Trim': method_4e_var_occ_trim,
    'M2d Amp-Tract': method_2d_amp_tract,
    'M5e Ind-Dispatch': method_5e_ind_dispatch,
    'M8 Adaptive-Router': method_8_adaptive_router,
}
