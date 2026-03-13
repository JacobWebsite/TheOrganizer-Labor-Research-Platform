"""V3 estimation methodologies: 9 new methods + inherited originals.

Each V3 method makes exactly ONE change from its V2 base method.
Do not modify or delete any existing method.

New methods:
    M1c  -- Cross-Validated Learned Weights (5-fold CV, constrained range)
    M1d  -- Regional Weight Adjustment (West gets 75/25)
    M2c  -- ZIP-to-Tract Workplace Layer
    M3c  -- Variable Dampening IPF (per-group alpha)
    M3d  -- Selective Dampening by County Minority Share
    M4c  -- Top-10 Occupation Trim
    M4d  -- State-Level Top-5 Occupation Mix
    M5c  -- Data-Derived Variable Weights (CV weights by M5 category)
    M5d  -- Corrected Minority-Adaptive Weights (flip direction)
"""
import math

from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_tract_race, get_tract_hispanic, get_tract_gender,
    get_occupation_mix, get_acs_by_occupation,
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_state_occupation_mix, get_lodes_pct_minority,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _normalize,
    _build_occ_weighted, _build_occ_weighted_with_fallback,
    _dampened_ipf,
)
from config import get_industry_weights, RACE_CATEGORIES
from classifiers import classify_naics_group, classify_region

RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']


# ============================================================
# Placeholder weights -- run compute_optimal_weights_v3.py and paste output here.
# Keys are the 18 named NAICS groups from classifiers.py + 'Other'.
# Values are (acs_weight, lodes_weight) tuples.
# ============================================================
OPTIMAL_WEIGHTS_V3_BY_GROUP = {
    'Accommodation/Food Svc (72)': (0.35, 0.65),
    'Admin/Staffing (56)': (0.35, 0.65),
    'Chemical/Material Mfg (325-327)': (0.35, 0.65),
    'Computer/Electrical Mfg (334-335)': (0.35, 0.65),
    'Construction (23)': (0.75, 0.25),
    'Finance/Insurance (52)': (0.35, 0.65),
    'Food/Bev Manufacturing (311,312)': (0.35, 0.65),
    'Healthcare/Social (62)': (0.35, 0.65),
    'Information (51)': (0.35, 0.65),
    'Metal/Machinery Mfg (331-333)': (0.35, 0.65),
    'Other': (0.35, 0.65),
    'Other Manufacturing': (0.35, 0.65),
    'Professional/Technical (54)': (0.35, 0.65),
    'Retail Trade (44-45)': (0.35, 0.65),
    'Transport Equip Mfg (336)': (0.35, 0.65),
    'Transportation/Warehousing (48-49)': (0.35, 0.65),
    'Utilities (22)': (0.35, 0.65),
    'Wholesale Trade (42)': (0.50, 0.50),
}

# Placeholder weights by M5 category -- run compute_optimal_weights_v3.py
OPTIMAL_WEIGHTS_V3_BY_CATEGORY = {
    'local_labor': (0.75, 0.25),
    'occupation': (0.35, 0.65),
    'manufacturing': (0.35, 0.65),
    'default': (0.35, 0.65),
}

# Placeholder dampening factors -- run compute_optimal_dampening.py and paste here.
# Keys are NAICS groups, values are alpha exponents.
OPTIMAL_DAMPENING_BY_GROUP = {
    'Accommodation/Food Svc (72)': 0.35,
    'Admin/Staffing (56)': 0.35,
    'Chemical/Material Mfg (325-327)': 0.35,
    'Computer/Electrical Mfg (334-335)': 0.35,
    'Construction (23)': 0.65,
    'Finance/Insurance (52)': 0.30,
    'Food/Bev Manufacturing (311,312)': 0.35,
    'Healthcare/Social (62)': 0.40,
    'Information (51)': 0.35,
    'Metal/Machinery Mfg (331-333)': 0.35,
    'Other': 0.30,
    'Other Manufacturing': 0.35,
    'Professional/Technical (54)': 0.40,
    'Retail Trade (44-45)': 0.35,
    'Transport Equip Mfg (336)': 0.35,
    'Transportation/Warehousing (48-49)': 0.35,
    'Utilities (22)': 0.35,
    'Wholesale Trade (42)': 0.45,
}

# M5 category classification (matches config.py INDUSTRY_WEIGHTS)
M5_CATEGORY_PREFIXES = {
    'local_labor': ['11', '23', '311', '312', '722'],
    'occupation': ['52', '54', '62'],
    'manufacturing': ['31', '32', '33'],
}


def _classify_m5_category(naics):
    """Classify NAICS into M5 weight category."""
    if not naics:
        return 'default'
    for cat, prefixes in M5_CATEGORY_PREFIXES.items():
        for prefix in sorted(prefixes, key=len, reverse=True):
            if naics.startswith(prefix):
                return cat
    return 'default'


# ============================================================
# M1c: Cross-Validated Learned Weights
# Base: M1b. Change: 5-fold CV weights with [0.35, 0.75] constraints
# ============================================================
def method_1c_cv_learned_weights(cur, naics4, state_fips, county_fips):
    """M1c: M1b with cross-validated, constrained weights."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_GROUP.get(group, (0.55, 0.45))

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
# M1d: Regional Weight Adjustment
# Base: M1. Change: West region gets 75/25 ACS/LODES
# ============================================================
def method_1d_regional_weight(cur, naics4, state_fips, county_fips, state_abbr=''):
    """M1d: M1 with higher ACS weight for West region."""
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if region == 'West':
        acs_w, lodes_w = 0.75, 0.25
    else:
        acs_w, lodes_w = 0.60, 0.40

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
# M2c: ZIP-to-Tract Workplace Layer
# Base: M2/M2b. Change: proper ZIP-to-tract crosswalk lookup
# ============================================================
def _zip_to_best_tract(cur, zipcode):
    """Look up the best business tract for a ZIP code.

    Uses zip_tract_crosswalk table with bus_ratio weighting.
    Returns tract_geoid or None.
    """
    if not zipcode:
        return None
    cur.execute(
        "SELECT tract_geoid FROM zip_tract_crosswalk "
        "WHERE zip_code = %s ORDER BY bus_ratio DESC LIMIT 1",
        [zipcode])
    row = cur.fetchone()
    return row['tract_geoid'] if row else None


def method_2c_zip_tract(cur, naics4, state_fips, county_fips, zipcode=''):
    """M2c: Three-Layer with ZIP-to-tract crosswalk lookup.

    50% ACS + 30% LODES county + 20% LODES tract (from ZIP crosswalk).
    Falls back to residential tract if ZIP not in crosswalk.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # Try ZIP-to-tract crosswalk
    tract_fips = _zip_to_best_tract(cur, zipcode)
    tract_race = get_lodes_tract_race(cur, tract_fips) if tract_fips else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    tract_gender = get_lodes_tract_gender(cur, tract_fips) if tract_fips else None

    # Fallback to residential tract data
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
# M3c: Variable Dampening IPF
# Base: M3b. Change: per-NAICS-group optimized alpha exponent
# ============================================================
def _variable_dampened_ipf(m1, m2, categories, alpha):
    """ACS_k^alpha * LODES_k^(1-alpha), then normalize to 100."""
    if m1 is None or m2 is None:
        return None
    raw = {}
    for k in categories:
        a = max(m1.get(k, 0), 0)
        l = max(m2.get(k, 0), 0)
        if a == 0 or l == 0:
            raw[k] = 0
        else:
            raw[k] = (a ** alpha) * (l ** (1.0 - alpha))
    total = sum(raw.values())
    if total == 0:
        return None
    return {k: round(raw[k] * 100.0 / total, 2) for k in categories}


def method_3c_variable_dampened_ipf(cur, naics4, state_fips, county_fips):
    """M3c: Dampened IPF with per-industry-group alpha exponent.

    Race uses variable alpha dampening; Hispanic and Gender use standard IPF.
    """
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


# ============================================================
# M3d: Selective Dampening by County Minority Share
# Base: M3. Change: dampening only when county minority > 20%
# ============================================================
def method_3d_selective_dampening(cur, naics4, state_fips, county_fips):
    """M3d: IPF product in low-minority areas, dampened IPF in high-minority.

    Threshold: 20% minority share.
    Below 20%: original M3 product (ACS_k * LODES_k)
    Above 20%: dampened geometric mean (sqrt(ACS_k) * sqrt(LODES_k))
    """
    pct_min = get_lodes_pct_minority(cur, county_fips)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if pct_min is not None and pct_min > 0.20:
        # Dampened geometric mean (M3b behavior)
        race_result = _dampened_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        # Original IPF product (M3 behavior)
        race_result = _ipf_two_marginals(acs_race, lodes_race, RACE_CATS)

    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, GENDER_CATS),
    }


# ============================================================
# M4c: Top-10 Occupation Trim
# Base: M4. Change: use top-10 occupations instead of top-30
# ============================================================
def _build_occ_weighted_topn(cur, occ_mix, state_fips, dimension, categories, top_n=10):
    """Build occupation-weighted demographic estimate with configurable top_n."""
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for soc_code, pct_of_industry in occ_mix[:top_n]:
        demo = get_acs_by_occupation(cur, soc_code, state_fips, dimension)
        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None

    return {k: round(weighted[k] / total_weight, 2) for k in categories}


def method_4c_top10_occ(cur, naics4, state_fips, county_fips):
    """M4c: Occupation-weighted ACS with top-10 trim (not top-30).

    70/30 blend with LODES (same as M4).
    """
    occ_mix = get_occupation_mix(cur, naics4)
    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    if not occ_mix:
        # Fallback to M1 style with 70/30
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        return {
            'race': _blend_dicts([(acs_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
            'hispanic': _blend_dicts([(acs_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
            'gender': _blend_dicts([(acs_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
        }

    occ_race = _build_occ_weighted_topn(cur, occ_mix, state_fips, 'race', RACE_CATS, top_n=10)
    occ_hisp = _build_occ_weighted_topn(cur, occ_mix, state_fips, 'hispanic', HISP_CATS, top_n=10)
    occ_gender = _build_occ_weighted_topn(cur, occ_mix, state_fips, 'gender', GENDER_CATS, top_n=10)

    return {
        'race': _blend_dicts([(occ_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([(occ_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
        'gender': _blend_dicts([(occ_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
    }


# ============================================================
# M4d: State-Level Top-5 Occupation Mix
# Base: M4b. Change: state-level for top-5 only, national for rest
# ============================================================
def method_4d_state_top5_occ(cur, naics4, state_fips, county_fips):
    """M4d: State-level ACS for top-5 occupations, national for rest.

    70/30 blend with LODES (same as M4).
    """
    occ_mix = get_occupation_mix(cur, naics4)
    if not occ_mix:
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)
        lodes_hisp = get_lodes_hispanic(cur, county_fips)
        lodes_gender = get_lodes_gender(cur, county_fips)
        return {
            'race': _blend_dicts([(acs_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
            'hispanic': _blend_dicts([(acs_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
            'gender': _blend_dicts([(acs_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
        }

    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # Build split occ-weighted estimate
    occ_race = _build_state_top5_national_rest(cur, occ_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = _build_state_top5_national_rest(cur, occ_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = _build_state_top5_national_rest(cur, occ_mix, state_fips, 'gender', GENDER_CATS)

    return {
        'race': _blend_dicts([(occ_race, 0.70), (lodes_race, 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([(occ_hisp, 0.70), (lodes_hisp, 0.30)], HISP_CATS),
        'gender': _blend_dicts([(occ_gender, 0.70), (lodes_gender, 0.30)], GENDER_CATS),
    }


def _build_state_top5_national_rest(cur, occ_mix, state_fips, dimension, categories):
    """Top 5 occupations: state ACS. Remaining: national ACS."""
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for i, (soc_code, pct_of_industry) in enumerate(occ_mix[:30]):
        if i < 5:
            # Top 5: use state-level ACS
            demo = get_acs_by_occupation(cur, soc_code, state_fips, dimension)
            if not demo:
                # Fall back to national
                demo = get_acs_by_occupation(cur, soc_code, '0', dimension)
        else:
            # Remaining: use national ACS
            demo = get_acs_by_occupation(cur, soc_code, '0', dimension)

        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None

    return {k: round(weighted[k] / total_weight, 2) for k in categories}


# ============================================================
# M5c: Data-Derived Variable Weights
# Base: M5. Change: CV-optimized weights by M5 category (not hand-coded)
# ============================================================
def method_5c_cv_variable_weight(cur, naics4, state_fips, county_fips):
    """M5c: M5 with data-derived weights per M5 industry category.

    Uses OPTIMAL_WEIGHTS_V3_BY_CATEGORY (4 categories) instead of
    hand-coded weights from config.py INDUSTRY_WEIGHTS.
    """
    category = _classify_m5_category(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_CATEGORY.get(category, (0.55, 0.45))

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
# M5d: Corrected Minority-Adaptive Weights
# Base: M5b. Change: flip direction -- increase LODES weight in high-minority
# ============================================================
def method_5d_corrected_minority_adaptive(cur, naics4, state_fips, county_fips):
    """M5d: M5b flipped -- decrease ACS weight in high-minority counties.

    In diverse counties, LODES workplace data is more valuable because
    it captures the actual local labor supply.
    """
    acs_w, lodes_w = get_industry_weights(naics4)
    pct_min = get_lodes_pct_minority(cur, county_fips)

    if pct_min is not None:
        if pct_min > 0.50:
            acs_w = max(0.20, acs_w - 0.20)
            lodes_w = min(0.80, 1.0 - acs_w)
        elif pct_min > 0.30:
            acs_w = max(0.25, acs_w - 0.10)
            lodes_w = min(0.75, 1.0 - acs_w)

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


# Registry of V3 methods
ALL_V3_METHODS = {
    'M1c CV-Learned-Wt': method_1c_cv_learned_weights,
    'M1d Regional-Wt': method_1d_regional_weight,
    'M2c ZIP-Tract': method_2c_zip_tract,
    'M3c Var-Damp-IPF': method_3c_variable_dampened_ipf,
    'M3d Select-Damp': method_3d_selective_dampening,
    'M4c Top10-Occ': method_4c_top10_occ,
    'M4d State-Top5': method_4d_state_top5_occ,
    'M5c CV-Var-Wt': method_5c_cv_variable_weight,
    'M5d Corr-Min-Adapt': method_5d_corrected_minority_adaptive,
}
