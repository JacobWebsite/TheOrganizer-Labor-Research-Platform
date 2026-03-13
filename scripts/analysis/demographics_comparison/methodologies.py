"""Six estimation methodologies for workforce demographics.

Each method has the same interface:
    method_X(cur, naics4, state_fips, county_fips) ->
        {'race': {cat: pct}, 'hispanic': {cat: pct}, 'gender': {cat: pct}}
        or None if data insufficient.

All race dicts use non-Hispanic categories to match EEO-1:
    White, Black, Asian, AIAN, NHOPI, Two+
"""
from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_tract_race, get_tract_hispanic, get_tract_gender,
    get_occupation_mix, get_acs_by_occupation,
)
from config import get_industry_weights, RACE_CATEGORIES


def _blend_dicts(dicts_and_weights, categories):
    """Blend multiple {category: pct} dicts with given weights.

    dicts_and_weights: list of (dict_or_None, weight)
    categories: list of category keys

    Returns blended dict. Skips None dicts, renormalizes weights.
    """
    active = [(d, w) for d, w in dicts_and_weights if d is not None]
    if not active:
        return None
    total_weight = sum(w for _, w in active)
    if total_weight == 0:
        return None

    result = {}
    for cat in categories:
        val = sum(d.get(cat, 0) * w for d, w in active) / total_weight
        result[cat] = round(val, 2)
    return result


def _normalize(d, categories):
    """Normalize a dict so values sum to 100."""
    if d is None:
        return None
    total = sum(d.get(k, 0) for k in categories)
    if total == 0:
        return d
    return {k: round(d.get(k, 0) * 100.0 / total, 2) for k in categories}


def _ipf_two_marginals(m1, m2, categories):
    """IPF with 2 marginals = normalized product.

    For each category k: raw_k = m1_k * m2_k
    Then normalize so sum = 100.
    """
    if m1 is None or m2 is None:
        return None
    raw = {}
    for k in categories:
        raw[k] = m1.get(k, 0) * m2.get(k, 0)
    total = sum(raw.values())
    if total == 0:
        return None
    return {k: round(raw[k] * 100.0 / total, 2) for k in categories}


def _ipf_three_marginals(marginals, categories, iterations=100):
    """IPF with 3+ marginals via iterative scaling.

    marginals: list of dicts {category: pct}
    """
    active = [m for m in marginals if m is not None]
    if len(active) < 2:
        if len(active) == 1:
            return _normalize(active[0], categories)
        return None

    # If exactly 2, use closed-form normalized product
    if len(active) == 2:
        return _ipf_two_marginals(active[0], active[1], categories)

    # Initialize with uniform seed
    n = len(categories)
    x = {k: 100.0 / n for k in categories}

    for _ in range(iterations):
        for marginal in active:
            for k in categories:
                if x[k] > 0:
                    x[k] *= marginal.get(k, 0.01)
            s = sum(x.values())
            if s > 0:
                x = {k: v * 100.0 / s for k, v in x.items()}

    return {k: round(v, 2) for k, v in x.items()}


# ============================================================
# Method 1: Current Baseline (60% ACS / 40% LODES)
# ============================================================
def method_1_baseline(cur, naics4, state_fips, county_fips):
    """60/40 fixed weight blend of ACS industry+state and LODES county."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _blend_dicts([(acs_race, 0.60), (lodes_race, 0.40)], race_cats),
        'hispanic': _blend_dicts([(acs_hisp, 0.60), (lodes_hisp, 0.40)], hisp_cats),
        'gender': _blend_dicts([(acs_gender, 0.60), (lodes_gender, 0.40)], gender_cats),
    }


# ============================================================
# Method 2: Three-Layer Blend (50% ACS / 30% LODES / 20% Tract)
# ============================================================
def method_2_three_layer(cur, naics4, state_fips, county_fips):
    """50/30/20 blend of ACS, LODES, and tract residential demographics."""
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    tract_race = get_tract_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    tract_hisp = get_tract_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    tract_gender = get_tract_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _blend_dicts([
            (acs_race, 0.50), (lodes_race, 0.30), (tract_race, 0.20)
        ], race_cats),
        'hispanic': _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], hisp_cats),
        'gender': _blend_dicts([
            (acs_gender, 0.50), (lodes_gender, 0.30), (tract_gender, 0.20)
        ], gender_cats),
    }


# ============================================================
# Method 3: IPF (Iterative Proportional Fitting)
# ============================================================
def method_3_ipf(cur, naics4, state_fips, county_fips):
    """IPF: normalized product of ACS and LODES marginals.

    Maximum entropy solution that amplifies agreement, dampens disagreement.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _ipf_two_marginals(acs_race, lodes_race, race_cats),
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, hisp_cats),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, gender_cats),
    }


# ============================================================
# Method 4: Occupation-Weighted Blend
# ============================================================
def method_4_occupation_weighted(cur, naics4, state_fips, county_fips):
    """Occupation-weighted ACS (70%) blended with LODES county (30%).

    Uses BLS occupation matrix to get the occupation mix for the industry,
    then queries ACS demographics per occupation.
    """
    occ_mix = get_occupation_mix(cur, naics4)
    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    # If no occupation data, fall back to method 1
    if not occ_mix:
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        return {
            'race': _blend_dicts([(acs_race, 0.70), (lodes_race, 0.30)], race_cats),
            'hispanic': _blend_dicts([(acs_hisp, 0.70), (lodes_hisp, 0.30)], hisp_cats),
            'gender': _blend_dicts([(acs_gender, 0.70), (lodes_gender, 0.30)], gender_cats),
        }

    # Build occupation-weighted ACS demographics
    occ_race = _build_occ_weighted(cur, occ_mix, state_fips, 'race', race_cats)
    occ_hisp = _build_occ_weighted(cur, occ_mix, state_fips, 'hispanic', hisp_cats)
    occ_gender = _build_occ_weighted(cur, occ_mix, state_fips, 'gender', gender_cats)

    return {
        'race': _blend_dicts([(occ_race, 0.70), (lodes_race, 0.30)], race_cats),
        'hispanic': _blend_dicts([(occ_hisp, 0.70), (lodes_hisp, 0.30)], hisp_cats),
        'gender': _blend_dicts([(occ_gender, 0.70), (lodes_gender, 0.30)], gender_cats),
    }


def _build_occ_weighted(cur, occ_mix, state_fips, dimension, categories):
    """Build occupation-weighted demographic estimate.

    For each occupation in occ_mix, query ACS demographics,
    weight by employment share.
    """
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for soc_code, pct_of_industry in occ_mix[:30]:  # Top 30 occupations
        demo = get_acs_by_occupation(cur, soc_code, state_fips, dimension)
        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None

    return {k: round(weighted[k] / total_weight, 2) for k in categories}


# ============================================================
# Method 5: Variable-Weight by Industry Type
# ============================================================
def method_5_variable_weight(cur, naics4, state_fips, county_fips):
    """Same as Method 1 but with industry-adaptive weights."""
    acs_w, lodes_w = get_industry_weights(naics4)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], race_cats),
        'hispanic': _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], hisp_cats),
        'gender': _blend_dicts([(acs_gender, acs_w), (lodes_gender, lodes_w)], gender_cats),
    }


# ============================================================
# Method 6: IPF + Occupation Layer
# ============================================================
def method_6_ipf_occupation(cur, naics4, state_fips, county_fips):
    """IPF using occupation-weighted ACS as one marginal, LODES as other.

    1. Build occupation-weighted ACS aggregation (Method 4 step)
    2. Use as one marginal in normalized-product IPF
    3. LODES county as other marginal
    """
    occ_mix = get_occupation_mix(cur, naics4)
    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    if not occ_mix:
        # Fall back to plain IPF (Method 3)
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        return {
            'race': _ipf_two_marginals(acs_race, lodes_race, race_cats),
            'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, hisp_cats),
            'gender': _ipf_two_marginals(acs_gender, lodes_gender, gender_cats),
        }

    occ_race = _build_occ_weighted(cur, occ_mix, state_fips, 'race', race_cats)
    occ_hisp = _build_occ_weighted(cur, occ_mix, state_fips, 'hispanic', hisp_cats)
    occ_gender = _build_occ_weighted(cur, occ_mix, state_fips, 'gender', gender_cats)

    return {
        'race': _ipf_two_marginals(occ_race, lodes_race, race_cats),
        'hispanic': _ipf_two_marginals(occ_hisp, lodes_hisp, hisp_cats),
        'gender': _ipf_two_marginals(occ_gender, lodes_gender, gender_cats),
    }


# Registry of all methods
ALL_METHODS = {
    'M1 Baseline (60/40)': method_1_baseline,
    'M2 Three-Layer (50/30/20)': method_2_three_layer,
    'M3 IPF': method_3_ipf,
    'M4 Occ-Weighted': method_4_occupation_weighted,
    'M5 Variable-Weight': method_5_variable_weight,
    'M6 IPF+Occ': method_6_ipf_occupation,
}


# ============================================================
# V2 Methods (M1b-M5b, M7) -- appended, no existing code changed
# ============================================================

import math
from data_loaders import (
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_state_occupation_mix, get_lodes_pct_minority, zip_to_tract,
)

# Placeholder weights -- run compute_optimal_weights.py and paste output here.
# Keys are the 18 named NAICS groups from classifiers.py + 'Other'.
# Values are (acs_weight, lodes_weight) tuples.
OPTIMAL_WEIGHTS_BY_GROUP = {
    'Accommodation/Food Svc (72)': (0.30, 0.70),
    'Admin/Staffing (56)': (0.90, 0.10),
    'Agriculture/Mining (11,21)': (0.65, 0.35),
    'Chemical/Material Mfg (325-327)': (0.30, 0.70),
    'Computer/Electrical Mfg (334-335)': (0.30, 0.70),
    'Construction (23)': (0.90, 0.10),
    'Finance/Insurance (52)': (0.30, 0.70),
    'Food/Bev Manufacturing (311,312)': (0.30, 0.70),
    'Healthcare/Social (62)': (0.35, 0.65),
    'Information (51)': (0.30, 0.70),
    'Metal/Machinery Mfg (331-333)': (0.35, 0.65),
    'Other': (0.30, 0.70),
    'Other Manufacturing': (0.30, 0.70),
    'Professional/Technical (54)': (0.30, 0.70),
    'Retail Trade (44-45)': (0.30, 0.70),
    'Transport Equip Mfg (336)': (0.30, 0.70),
    'Transportation/Warehousing (48-49)': (0.30, 0.70),
    'Utilities (22)': (0.90, 0.10),
    'Wholesale Trade (42)': (0.30, 0.70),
}


# ============================================================
# M1b: Learned Weights by Industry Group
# ============================================================
def method_1b_learned_weights(cur, naics4, state_fips, county_fips):
    """M1 with per-NAICS-group optimized ACS/LODES weights."""
    from classifiers import classify_naics_group
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], race_cats),
        'hispanic': _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], hisp_cats),
        'gender': _blend_dicts([(acs_gender, acs_w), (lodes_gender, lodes_w)], gender_cats),
    }


# ============================================================
# M2b: Workplace Tract LODES
# ============================================================
def method_2b_workplace_tract(cur, naics4, state_fips, county_fips):
    """50% ACS + 30% LODES county + 20% LODES tract (workplace).

    Third layer uses workplace LODES tract instead of residential ACS tract.
    Falls back to M1 behavior if tract data unavailable.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    # Try to get tract-level LODES data
    # Use the largest-employment tract in the county as proxy
    tract_fips = zip_to_tract(cur, None, county_fips)
    tract_race = get_lodes_tract_race(cur, tract_fips) if tract_fips else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    tract_gender = get_lodes_tract_gender(cur, tract_fips) if tract_fips else None

    # If no tract data, fall back to residential tract, then M1
    if tract_race is None:
        tract_race = get_tract_race(cur, county_fips)
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)
    if tract_gender is None:
        tract_gender = get_tract_gender(cur, county_fips)

    return {
        'race': _blend_dicts([
            (acs_race, 0.50), (lodes_race, 0.30), (tract_race, 0.20)
        ], race_cats),
        'hispanic': _blend_dicts([
            (acs_hisp, 0.50), (lodes_hisp, 0.30), (tract_hisp, 0.20)
        ], hisp_cats),
        'gender': _blend_dicts([
            (acs_gender, 0.50), (lodes_gender, 0.30), (tract_gender, 0.20)
        ], gender_cats),
    }


# ============================================================
# M3b: Dampened IPF
# ============================================================
def _dampened_ipf(m1, m2, categories):
    """sqrt(ACS_k) * sqrt(LODES_k), then normalize to 100."""
    if m1 is None or m2 is None:
        return None
    raw = {k: math.sqrt(max(m1.get(k, 0), 0)) * math.sqrt(max(m2.get(k, 0), 0))
           for k in categories}
    total = sum(raw.values())
    if total == 0:
        return None
    return {k: round(raw[k] * 100.0 / total, 2) for k in categories}


def method_3b_dampened_ipf(cur, naics4, state_fips, county_fips):
    """Dampened IPF: geometric mean instead of product.

    Race uses _dampened_ipf; Hispanic and Gender use standard _ipf_two_marginals.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _dampened_ipf(acs_race, lodes_race, race_cats),
        'hispanic': _ipf_two_marginals(acs_hisp, lodes_hisp, hisp_cats),
        'gender': _ipf_two_marginals(acs_gender, lodes_gender, gender_cats),
    }


# ============================================================
# M4b: State-Level Occupation Mix
# ============================================================
def method_4b_state_occ_mix(cur, naics4, state_fips, county_fips):
    """Occupation-weighted ACS using state-level occupation mix.

    Uses state ACS occupation proportions instead of national BLS matrix.
    For SOC codes with <100 state workers, falls back to national ACS.
    70/30 blend with LODES (same as M4).
    """
    state_mix = get_state_occupation_mix(cur, naics4, state_fips)
    if not state_mix:
        state_mix = get_occupation_mix(cur, naics4)  # fall back to national BLS
    if not state_mix:
        # Fall back to M1 with 70/30
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)
        lodes_hisp = get_lodes_hispanic(cur, county_fips)
        lodes_gender = get_lodes_gender(cur, county_fips)
        race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
        hisp_cats = ['Hispanic', 'Not Hispanic']
        gender_cats = ['Male', 'Female']
        return {
            'race': _blend_dicts([(acs_race, 0.70), (lodes_race, 0.30)], race_cats),
            'hispanic': _blend_dicts([(acs_hisp, 0.70), (lodes_hisp, 0.30)], hisp_cats),
            'gender': _blend_dicts([(acs_gender, 0.70), (lodes_gender, 0.30)], gender_cats),
        }

    lodes_race = get_lodes_race(cur, county_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    # Build occupation-weighted ACS with state mix (fallback per-SOC for small samples)
    occ_race = _build_occ_weighted_with_fallback(cur, state_mix, state_fips, 'race', race_cats)
    occ_hisp = _build_occ_weighted_with_fallback(cur, state_mix, state_fips, 'hispanic', hisp_cats)
    occ_gender = _build_occ_weighted_with_fallback(cur, state_mix, state_fips, 'gender', gender_cats)

    return {
        'race': _blend_dicts([(occ_race, 0.70), (lodes_race, 0.30)], race_cats),
        'hispanic': _blend_dicts([(occ_hisp, 0.70), (lodes_hisp, 0.30)], hisp_cats),
        'gender': _blend_dicts([(occ_gender, 0.70), (lodes_gender, 0.30)], gender_cats),
    }


def _build_occ_weighted_with_fallback(cur, occ_mix, state_fips, dimension, categories):
    """Like _build_occ_weighted but falls back to national ACS for small state samples."""
    weighted = {k: 0.0 for k in categories}
    total_weight = 0.0

    for soc_code, pct_of_industry in occ_mix[:30]:
        demo = get_acs_by_occupation(cur, soc_code, state_fips, dimension)
        # If state sample is too small (<100 workers), try national (state_fips='0')
        if demo and demo.get('_workers', 0) < 100:
            national = get_acs_by_occupation(cur, soc_code, '0', dimension)
            if national:
                demo = national
        if not demo:
            # Try national as last resort
            demo = get_acs_by_occupation(cur, soc_code, '0', dimension)
        if demo:
            for k in categories:
                weighted[k] += demo.get(k, 0) * pct_of_industry
            total_weight += pct_of_industry

    if total_weight == 0:
        return None

    return {k: round(weighted[k] / total_weight, 2) for k in categories}


# ============================================================
# M5b: Minority Share Adaptive Weighting
# ============================================================
def method_5b_minority_adaptive(cur, naics4, state_fips, county_fips):
    """M5 Variable-Weight with minority-share adaptive adjustment.

    Increases ACS weight in high-minority areas where LODES geography
    may be less representative of the specific employer.
    """
    acs_w, lodes_w = get_industry_weights(naics4)
    pct_min = get_lodes_pct_minority(cur, county_fips)
    if pct_min is not None:
        if pct_min > 0.50:
            acs_w += 0.20
        elif pct_min > 0.30:
            acs_w += 0.10
        acs_w = min(acs_w, 0.85)
        lodes_w = 1.0 - acs_w

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    race_cats = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    hisp_cats = ['Hispanic', 'Not Hispanic']
    gender_cats = ['Male', 'Female']

    return {
        'race': _blend_dicts([(acs_race, acs_w), (lodes_race, lodes_w)], race_cats),
        'hispanic': _blend_dicts([(acs_hisp, acs_w), (lodes_hisp, lodes_w)], hisp_cats),
        'gender': _blend_dicts([(acs_gender, acs_w), (lodes_gender, lodes_w)], gender_cats),
    }


# ============================================================
# M7: Hybrid (M1b race + M3 gender)
# ============================================================
def method_7_hybrid(cur, naics4, state_fips, county_fips):
    """Hybrid: M1b for race/hispanic, M3 IPF for gender."""
    m1b = method_1b_learned_weights(cur, naics4, state_fips, county_fips)
    m3 = method_3_ipf(cur, naics4, state_fips, county_fips)

    if m1b is None and m3 is None:
        return None

    return {
        'race': m1b['race'] if m1b else (m3['race'] if m3 else None),
        'hispanic': m1b['hispanic'] if m1b else (m3['hispanic'] if m3 else None),
        'gender': m3['gender'] if m3 else (m1b['gender'] if m1b else None),
    }


# Registry of V2 methods
ALL_V2_METHODS = {
    'M1b Learned-Wt': method_1b_learned_weights,
    'M2b Workplace-Tract': method_2b_workplace_tract,
    'M3b Damp-IPF': method_3b_dampened_ipf,
    'M4b State-Occ': method_4b_state_occ_mix,
    'M5b Min-Adapt': method_5b_minority_adaptive,
    'M7 Hybrid': method_7_hybrid,
}
