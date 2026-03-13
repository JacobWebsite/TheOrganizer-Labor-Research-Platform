"""Extended cached loaders for V4 methods (M3e, M3f, M1e, M4e, M2d, M5e, M8).

Subclasses CachedLoadersV3. Provides cached method wrappers for all 7 V4 methods.
No new data accessors needed -- all data functions exist in V3.
"""
from cached_loaders import RACE_CATS, HISP_CATS, GENDER_CATS
from cached_loaders_v3 import CachedLoadersV3
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf,
    OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import (
    OPTIMAL_DAMPENING_BY_GROUP,
    OPTIMAL_WEIGHTS_V3_BY_GROUP,
    _classify_m5_category,
    _variable_dampened_ipf,
)
from config import (
    M4_VARIANCE_THRESHOLD, OPTIMAL_M3F_THRESHOLD, M8_M1B_HISPANIC_INDUSTRIES,
)
from classifiers import classify_naics_group, classify_region


# ============================================================
# Cached method wrappers for V4 methods
# ============================================================

def cached_method_3e(cl, naics4, state_fips, county_fips, **kwargs):
    """M3e Fin-Route-IPF"""
    group = classify_naics_group(naics4)
    acs_race = cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        race_result = _variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def cached_method_3f(cl, naics4, state_fips, county_fips, **kwargs):
    """M3f Min-Ind-Thresh"""
    group = classify_naics_group(naics4)
    acs_race = cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    else:
        pct_min = cl.get_lodes_pct_minority(county_fips)
        if pct_min is not None and pct_min > OPTIMAL_M3F_THRESHOLD:
            race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
        else:
            race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)

    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def cached_method_1e(cl, naics4, state_fips, county_fips, **kwargs):
    """M1e Hi-Min-Floor"""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_GROUP.get(group, (0.55, 0.45))

    pct_min = cl.get_lodes_pct_minority(county_fips)
    if pct_min is not None:
        if pct_min > 0.50:
            lodes_w = max(lodes_w, 0.40)
            acs_w = 1.0 - lodes_w
        elif pct_min > 0.30:
            lodes_w = max(lodes_w, 0.30)
            acs_w = 1.0 - lodes_w

    return {
        'race': _blend_dicts([
            (cl.get_acs_race(naics4, state_fips), acs_w),
            (cl.get_lodes_race(county_fips), lodes_w)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), acs_w),
            (cl.get_lodes_hispanic(county_fips), lodes_w)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), acs_w),
            (cl.get_lodes_gender(county_fips), lodes_w)], GENDER_CATS),
    }


def cached_method_4e(cl, naics4, state_fips, county_fips, **kwargs):
    """M4e Var-Occ-Trim"""
    occ_mix = cl.get_occupation_mix(naics4)
    if not occ_mix:
        return {
            'race': _blend_dicts([
                (cl.get_acs_race(naics4, state_fips), 0.70),
                (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
            'hispanic': _blend_dicts([
                (cl.get_acs_hispanic(naics4, state_fips), 0.70),
                (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
            'gender': _blend_dicts([
                (cl.get_acs_gender(naics4, state_fips), 0.70),
                (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
        }

    # Get industry baseline White share
    baseline = cl.get_acs_race(naics4, state_fips)
    baseline_white = baseline.get('White', 0) if baseline else 0

    # Filter occupations by White deviation
    filtered_mix = []
    for soc, pct in occ_mix[:30]:
        occ_demo = cl.get_acs_by_occupation(soc, state_fips, 'race')
        if not occ_demo:
            occ_demo = cl.get_acs_by_occupation(soc, '0', 'race')
        if occ_demo:
            occ_white = occ_demo.get('White', 0)
            deviation = occ_white - baseline_white
            if deviation <= M4_VARIANCE_THRESHOLD:
                filtered_mix.append((soc, pct))
        else:
            filtered_mix.append((soc, pct))

    if not filtered_mix:
        filtered_mix = occ_mix[:10]

    # Build weighted estimates from filtered mix
    occ_race = _build_filtered_cached(cl, filtered_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = _build_filtered_cached(cl, filtered_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = _build_filtered_cached(cl, filtered_mix, state_fips, 'gender', GENDER_CATS)

    return {
        'race': _blend_dicts([
            (occ_race, 0.70), (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([
            (occ_hisp, 0.70), (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
        'gender': _blend_dicts([
            (occ_gender, 0.70), (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
    }


def _build_filtered_cached(cl, occ_mix, state_fips, dimension, categories):
    """Build occ-weighted estimate from filtered occ list, using cached lookups."""
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for soc_code, pct_of_industry in occ_mix:
        demo = cl.get_acs_by_occupation(soc_code, state_fips, dimension)
        if not demo:
            demo = cl.get_acs_by_occupation(soc_code, '0', dimension)
        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None
    return {k: round(weighted[k] / total_weight, 2) for k in categories}


def cached_method_2d(cl, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """M2d Amp-Tract"""
    tract_fips = cl.get_zip_to_best_tract(zipcode)
    tract_race = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
    tract_hisp = cl.get_lodes_tract_hispanic(tract_fips) if tract_fips else None
    tract_gender = cl.get_lodes_tract_gender(tract_fips) if tract_fips else None

    # Fallback to residential tract data
    if tract_race is None:
        tract_race = cl.get_tract_race(county_fips)
    if tract_hisp is None:
        tract_hisp = cl.get_tract_hispanic(county_fips)
    if tract_gender is None:
        tract_gender = cl.get_tract_gender(county_fips)

    return {
        'race': _blend_dicts([
            (cl.get_acs_race(naics4, state_fips), 0.45),
            (cl.get_lodes_race(county_fips), 0.20),
            (tract_race, 0.35)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.45),
            (cl.get_lodes_hispanic(county_fips), 0.20),
            (tract_hisp, 0.35)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.45),
            (cl.get_lodes_gender(county_fips), 0.20),
            (tract_gender, 0.35)], GENDER_CATS),
    }


def cached_method_5e(cl, naics4, state_fips, county_fips, **kwargs):
    """M5e Ind-Dispatch"""
    category = _classify_m5_category(naics4)
    group = classify_naics_group(naics4)

    if category == 'occupation':
        if group in ('Finance/Insurance (52)', 'Utilities (22)'):
            return _cached_m3_ipf(cl, naics4, state_fips, county_fips)
        elif group == 'Admin/Staffing (56)':
            return cached_method_4e(cl, naics4, state_fips, county_fips)
        else:
            return _cached_m3c(cl, naics4, state_fips, county_fips)
    elif category == 'local_labor':
        return _cached_m3d(cl, naics4, state_fips, county_fips)
    elif category == 'manufacturing':
        if group == 'Computer/Electrical Mfg (334-335)':
            return _cached_m1b(cl, naics4, state_fips, county_fips)
        else:
            return _cached_m3c(cl, naics4, state_fips, county_fips)
    else:
        return _cached_m3c(cl, naics4, state_fips, county_fips)


def cached_method_8(cl, naics4, state_fips, county_fips,
                     naics_group='', county_minority_share=None,
                     urbanicity='', state_abbr='', zipcode='', **kwargs):
    """M8 Adaptive-Router"""
    if not naics_group:
        naics_group = classify_naics_group(naics4)
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if county_minority_share is None:
        county_minority_share = cl.get_lodes_pct_minority(county_fips)

    acs_race = cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    min_share = county_minority_share if county_minority_share is not None else 0.0

    # === RACE ROUTER ===
    routing_used = 'M3C'

    if naics_group == 'Finance/Insurance (52)':
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Utilities (22)':
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Admin/Staffing (56)':
        m4e = cached_method_4e(cl, naics4, state_fips, county_fips)
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
        if min_share > 0.20:
            race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
        else:
            race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
        routing_used = 'M3D'
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50)
        race_result = _variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)
        routing_used = 'M3C'

    # === HISPANIC ROUTER ===
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    lodes_hisp = cl.get_lodes_hispanic(county_fips)
    hispanic_routing = 'M2C'

    if naics_group in M8_M1B_HISPANIC_INDUSTRIES:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        hisp_result = _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], HISP_CATS)
        hispanic_routing = 'M1B'
    else:
        tract_fips = cl.get_zip_to_best_tract(zipcode) if zipcode else None
        tract_hisp = cl.get_lodes_tract_hispanic(tract_fips) if tract_fips else None
        if tract_hisp is None:
            tract_hisp = cl.get_tract_hispanic(county_fips)
        hisp_result = _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], HISP_CATS)
        hispanic_routing = 'M2C'

    # === GENDER: Always IPF ===
    gender_result = _ipf_two_marginals(
        cl.get_acs_gender(naics4, state_fips),
        cl.get_lodes_gender(county_fips), GENDER_CATS)

    return {
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        'routing_used': routing_used,
        'hispanic_routing': hispanic_routing,
    }


# ============================================================
# Helper methods for M5e routing (cached versions)
# ============================================================

def _cached_m3_ipf(cl, naics4, state_fips, county_fips):
    """Cached M3 original IPF."""
    return {
        'race': _ipf_two_marginals(
            cl.get_acs_race(naics4, state_fips),
            cl.get_lodes_race(county_fips), RACE_CATS),
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def _cached_m3c(cl, naics4, state_fips, county_fips):
    """Cached M3c variable dampened IPF."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    return {
        'race': _variable_dampened_ipf(
            cl.get_acs_race(naics4, state_fips),
            cl.get_lodes_race(county_fips), RACE_CATS, alpha),
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def _cached_m3d(cl, naics4, state_fips, county_fips):
    """Cached M3d selective dampening."""
    pct_min = cl.get_lodes_pct_minority(county_fips)
    acs_race = cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)
    if pct_min is not None and pct_min > 0.20:
        race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)
    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def _cached_m1b(cl, naics4, state_fips, county_fips):
    """Cached M1b learned weights."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))
    return {
        'race': _blend_dicts([
            (cl.get_acs_race(naics4, state_fips), acs_w),
            (cl.get_lodes_race(county_fips), lodes_w)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), acs_w),
            (cl.get_lodes_hispanic(county_fips), lodes_w)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), acs_w),
            (cl.get_lodes_gender(county_fips), lodes_w)], GENDER_CATS),
    }


# Methods that need extra kwargs
V4_METHODS_NEED_EXTRA = {'M2d Amp-Tract', 'M8 Adaptive-Router'}

ALL_V4_CACHED_METHODS = {
    'M3e Fin-Route-IPF': cached_method_3e,
    'M3f Min-Ind-Thresh': cached_method_3f,
    'M1e Hi-Min-Floor': cached_method_1e,
    'M4e Var-Occ-Trim': cached_method_4e,
    'M2d Amp-Tract': cached_method_2d,
    'M5e Ind-Dispatch': cached_method_5e,
    'M8 Adaptive-Router': cached_method_8,
}
