"""V6 estimation methodologies: industry-LODES IPF, QCEW-adaptive,
occupation-weighted gender, geography-heavy Hispanic.

New methods:
    M9a  -- Industry-LODES IPF (ACS x industry-weighted LODES)
    M9b  -- QCEW LQ-adaptive weighting (trust LODES more when LQ high)
    M9c  -- Combined M9a + M9b
    M3c-IND -- V5 M3c with industry-LODES replacing all-county LODES
    M1b-QCEW -- M1b with QCEW-adjusted weights
    M2c-Multi -- M2c with multi-tract ensemble
    G1   -- Occupation-weighted gender (CPS Table 11 + OES)
    H1   -- Geography-heavy Hispanic (multi-source blend)

All methods return: {'race': {}, 'hispanic': {}, 'gender': {}}
"""
from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_lodes_pct_minority,
    get_tract_race, get_tract_hispanic, get_tract_gender,
    get_lodes_industry_race, get_qcew_concentration,
    get_acs_race_metro, get_multi_tract_demographics,
    get_occupation_mix_local, get_pct_female_by_occupation,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _normalize,
    OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import (
    OPTIMAL_DAMPENING_BY_GROUP, _variable_dampened_ipf,
)
from methodologies_v5 import (
    apply_floor, smoothed_ipf, smoothed_variable_dampened_ipf,
    RACE_CATS, HISP_CATS, GENDER_CATS,
)
from classifiers import classify_naics_group
from config import NAICS_TO_CNS


# ============================================================
# M9a: Industry-LODES IPF
# ACS x industry-weighted LODES (CNS columns)
# ============================================================

def method_9a_industry_lodes_ipf(cur, naics4, state_fips, county_fips, **kwargs):
    """M9a: ACS x LODES_industry via smoothed variable dampened IPF.

    Uses industry-specific LODES demographics (from lodes_county_industry_demographics)
    instead of all-industry county LODES. Falls back to all-county LODES if
    industry-specific data unavailable.
    """
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)

    # Try industry-specific LODES first
    naics_2 = naics4[:2] if naics4 else None
    ind_lodes = get_lodes_industry_race(cur, county_fips, naics_2)
    if ind_lodes is not None:
        lodes_race = ind_lodes
        data_source = 'lodes_industry'
    else:
        lodes_race = get_lodes_race(cur, county_fips)
        data_source = 'lodes_county'

    race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
        '_data_source': data_source,
    }


# ============================================================
# M9b: QCEW LQ-Adaptive Weighting
# ============================================================

def _qcew_adaptive_alpha(lq, base_alpha=0.50):
    """Adjust alpha based on QCEW location quotient.

    High LQ (industry concentrated locally) -> trust LODES more (lower alpha).
    Low LQ (industry rare locally) -> trust ACS more (higher alpha).

    alpha controls ACS/LODES balance in dampened IPF:
    alpha=1.0 -> pure ACS, alpha=0.0 -> pure LODES.
    """
    if lq is None:
        return base_alpha
    if lq >= 2.0:
        # Industry is 2x+ concentrated -- LODES very reliable
        return max(base_alpha - 0.20, 0.15)
    elif lq >= 1.5:
        return max(base_alpha - 0.15, 0.20)
    elif lq >= 1.0:
        return max(base_alpha - 0.05, 0.30)
    elif lq >= 0.5:
        return base_alpha
    else:
        # Industry is rare locally -- LODES less representative
        return min(base_alpha + 0.15, 0.85)


def method_9b_qcew_adaptive(cur, naics4, state_fips, county_fips, **kwargs):
    """M9b: QCEW LQ-adaptive weighting between ACS and LODES.

    Uses location quotient to decide how much to trust LODES geography
    vs ACS industry signal. High LQ -> more LODES weight.
    """
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    naics_2 = naics4[:2] if naics4 else None
    qcew = get_qcew_concentration(cur, county_fips, naics_2)
    lq = qcew['location_quotient'] if qcew else None

    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)

    race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
        '_lq': lq,
        '_alpha_used': alpha,
    }


# ============================================================
# M9c: Combined Industry-LODES + QCEW Adaptive
# ============================================================

def method_9c_combined(cur, naics4, state_fips, county_fips, **kwargs):
    """M9c: Industry-LODES + QCEW adaptive alpha.

    Best of both: uses industry-specific LODES demographics AND adjusts
    dampening based on QCEW location quotient.
    """
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    naics_2 = naics4[:2] if naics4 else None

    # QCEW adjustment
    qcew = get_qcew_concentration(cur, county_fips, naics_2)
    lq = qcew['location_quotient'] if qcew else None
    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    # Industry-specific LODES
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    ind_lodes = get_lodes_industry_race(cur, county_fips, naics_2)
    if ind_lodes is not None:
        lodes_race = ind_lodes
        data_source = 'lodes_industry+qcew'
    else:
        lodes_race = get_lodes_race(cur, county_fips)
        data_source = 'lodes_county+qcew'

    race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
        '_data_source': data_source,
        '_lq': lq,
        '_alpha_used': alpha,
    }


# ============================================================
# M3c-IND: Variable dampened IPF with industry-LODES
# ============================================================

def method_3c_ind(cur, naics4, state_fips, county_fips, **kwargs):
    """M3c-IND: V5 M3c but with industry-specific LODES replacing all-county."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    naics_2 = naics4[:2] if naics4 else None
    ind_lodes = get_lodes_industry_race(cur, county_fips, naics_2)
    lodes_race = ind_lodes if ind_lodes is not None else get_lodes_race(cur, county_fips)

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
# M1b-QCEW: Learned weights with QCEW LQ adjustment
# ============================================================

def method_1b_qcew(cur, naics4, state_fips, county_fips, **kwargs):
    """M1b-QCEW: Learned-weight blend with QCEW LQ adjustment.

    High LQ -> more LODES weight. Low LQ -> more ACS weight.
    """
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))

    naics_2 = naics4[:2] if naics4 else None
    qcew = get_qcew_concentration(cur, county_fips, naics_2)
    if qcew and qcew['location_quotient'] is not None:
        lq = qcew['location_quotient']
        if lq >= 2.0:
            lodes_w = min(lodes_w + 0.20, 0.85)
        elif lq >= 1.5:
            lodes_w = min(lodes_w + 0.10, 0.75)
        elif lq < 0.5:
            lodes_w = max(lodes_w - 0.15, 0.10)
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
# M2c-Multi: Three-layer with multi-tract ensemble
# ============================================================

def method_2c_multi(cur, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """M2c-Multi: Uses multi-tract ensemble instead of single best tract.

    Multi-tract averages demographics across ALL tracts in ZIP weighted
    by LODES employment counts, providing more representative geography.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    # Multi-tract ensemble
    multi = get_multi_tract_demographics(cur, zipcode) if zipcode else None
    tract_race = multi.get('race') if multi else None
    tract_hisp = multi.get('hispanic') if multi else None
    tract_gender = multi.get('gender') if multi else None

    # Fallback to county-level tract data
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
# M2c-Metro: Three-layer with metro ACS instead of state ACS
# ============================================================

def method_2c_metro(cur, naics4, state_fips, county_fips, cbsa_code='', **kwargs):
    """M2c-Metro: Metro ACS + LODES + Tract blend.

    Uses metro-level ACS (more precise than state) when available.
    Falls back to state ACS.
    """
    metro_acs = get_acs_race_metro(cur, naics4, cbsa_code) if cbsa_code else None
    acs_race = metro_acs if metro_acs is not None else get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    tract_race = get_tract_race(cur, county_fips)
    tract_hisp = get_tract_hispanic(cur, county_fips)
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
        '_data_source': 'acs_metro' if metro_acs else 'acs_state',
    }


# ============================================================
# G1: Occupation-Weighted Gender (CPS Table 11 + OES)
# ============================================================

def get_gender_blend_weight(naics_2digit):
    """Return BLS occupation weight for gender blend (remainder goes to IPF).

    Industries far from 50% female should trust occupation data more heavily.
    Uses NAICS_GENDER_BENCHMARKS from config.py for industry benchmarks.
    """
    try:
        from config import NAICS_GENDER_BENCHMARKS
        benchmark = NAICS_GENDER_BENCHMARKS.get(str(naics_2digit), 45.0)
    except (ImportError, KeyError):
        benchmark = 45.0

    distance_from_50 = abs(float(benchmark) - 50.0)

    if distance_from_50 > 25:
        # e.g. Construction (11%), Healthcare (77%), Mining (15%)
        return 0.75  # 75% BLS occupation, 25% IPF
    elif distance_from_50 > 15:
        # e.g. Transportation (25%), Education (66%), Manufacturing (29%)
        return 0.65  # 65% BLS occupation, 35% IPF
    else:
        # e.g. Retail (50%), Finance (53%), Information (40%)
        return 0.50  # Keep current 50/50 blend


def _occupation_weighted_gender(cur, naics4, cbsa_code):
    """Build occupation-weighted gender estimate from CPS Table 11 + BLS industry matrix.

    1. Get industry-specific occupation mix from BLS (national, NAICS-specific)
    2. For each occupation, look up CPS Table 11 % female
    3. Weight by employment share

    Uses BLS industry-occupation matrix (industry-specific) rather than OES metro
    (all-industry), which would produce generic ~50% female estimates.
    """
    from data_loaders import get_occupation_mix

    # BLS industry-occupation matrix is industry-specific (preferred)
    occ_mix = get_occupation_mix(cur, naics4)
    if not occ_mix:
        return None

    total_emp = 0.0
    weighted_female = 0.0

    for soc_code, emp in occ_mix[:50]:  # Top 50 occupations
        pct_f = get_pct_female_by_occupation(cur, soc_code)
        if pct_f is not None:
            total_emp += emp
            weighted_female += emp * pct_f

    if total_emp == 0:
        return None

    pct_female = weighted_female / total_emp
    return {'Male': round(100.0 - pct_female, 2), 'Female': round(pct_female, 2)}


def method_g1_occupation_gender(cur, naics4, state_fips, county_fips,
                                cbsa_code='', zipcode='', **kwargs):
    """G1: Occupation-weighted gender blended with geographic IPF.

    When occupation data available: blend occupation signal with smoothed IPF.
    40% occupation-weighted (BLS industry matrix + CPS), 60% smoothed IPF.
    The occupation signal provides industry-specific prior; IPF provides
    geographic adjustment. Neither alone is sufficient.
    Fallback: pure smoothed IPF.
    """
    occ_gender = _occupation_weighted_gender(cur, naics4, cbsa_code)

    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

    if occ_gender is not None and ipf_gender is not None:
        bls_weight = get_gender_blend_weight(naics4[:2])
        ipf_weight = 1.0 - bls_weight
        gender_result = _blend_dicts([
            (occ_gender, bls_weight), (ipf_gender, ipf_weight)
        ], GENDER_CATS)
        gender_source = 'occ_weighted+ipf(%.0f/%.0f)' % (bls_weight * 100, ipf_weight * 100)
    elif ipf_gender is not None:
        gender_result = ipf_gender
        gender_source = 'smoothed_ipf_fallback'
    else:
        gender_result = occ_gender
        gender_source = 'occ_only_fallback'

    # Race and Hispanic use standard M3c
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)

    return {
        'race': smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': gender_result,
        '_gender_source': gender_source,
    }


# ============================================================
# H1: Geography-Heavy Hispanic
# ============================================================

def method_h1_geographic_hispanic(cur, naics4, state_fips, county_fips,
                                   zipcode='', cbsa_code='', **kwargs):
    """H1: Geography-heavy Hispanic method.

    Multi-source geographic blend:
      LODES Hispanic (35%) + PUMS Hispanic (30%) + Tract Hispanic (20%) + ACS Hispanic (15%)

    The key insight: Hispanic concentration is highly geographic, so
    geographic sources should dominate over industry-based ACS.
    """
    # LODES county Hispanic
    lodes_hisp = get_lodes_hispanic(cur, county_fips)

    # PUMS metro Hispanic (via ACS metro query for Hispanic dimension)
    pums_hisp = None
    if cbsa_code:
        # Use PUMS metro data if available
        from cached_loaders_v5 import CachedLoadersV5
        try:
            # Direct query for PUMS Hispanic
            cur.execute(
                "SELECT hispanic_pct FROM pums_metro_demographics "
                "WHERE met2013 = %s AND naics_2digit = %s",
                [cbsa_code, naics4[:2] if naics4 else ''])
            row = cur.fetchone()
            if row and row['hispanic_pct'] is not None:
                hisp_pct = float(row['hispanic_pct'])
                pums_hisp = {'Hispanic': hisp_pct, 'Not Hispanic': round(100.0 - hisp_pct, 2)}
        except Exception:
            pass

    # Multi-tract Hispanic
    tract_hisp = None
    if zipcode:
        multi = get_multi_tract_demographics(cur, zipcode)
        if multi:
            tract_hisp = multi.get('hispanic')
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)

    # ACS state Hispanic
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)

    # Build weighted blend
    # When PUMS available: 35/30/20/15
    # When PUMS missing: redistribute 30% -> 45/0/30/25
    if pums_hisp is not None:
        hisp_result = _blend_dicts([
            (lodes_hisp, 0.35), (pums_hisp, 0.30),
            (tract_hisp, 0.20), (acs_hisp, 0.15)
        ], HISP_CATS)
        hisp_source = 'geo_heavy_4src'
    else:
        hisp_result = _blend_dicts([
            (lodes_hisp, 0.45), (tract_hisp, 0.30), (acs_hisp, 0.25)
        ], HISP_CATS)
        hisp_source = 'geo_heavy_3src'

    # Race and Gender use standard M3c
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha),
        'hispanic': hisp_result,
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
        '_hisp_source': hisp_source,
    }


# ============================================================
# Full V6 Pipeline: Independent tracks for race/hispanic/gender
# ============================================================

def method_v6_full(cur, naics4, state_fips, county_fips,
                   cbsa_code='', zipcode='', **kwargs):
    """Full V6 method: dimension-specific estimation.

    Race: M9b (QCEW adaptive alpha -- best race MAE on holdout)
    Hispanic: Expert-B style tract-heavy blend (best Hispanic MAE)
    Gender: G1 (occupation-weighted + IPF -- biggest V6 improvement)

    Optimal combination discovered via V6 ablation study.
    """
    # Race: M9b (QCEW-adaptive, no industry-LODES -- ablation showed it hurts)
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    naics_2 = naics4[:2] if naics4 else None

    qcew = get_qcew_concentration(cur, county_fips, naics_2)
    lq = qcew['location_quotient'] if qcew else None
    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    lodes_race = get_lodes_race(cur, county_fips)
    race_result = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

    # Hispanic: Expert-B style 35/25/40 tract-heavy blend
    from methodologies_v3 import _zip_to_best_tract
    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    tract_fips = _zip_to_best_tract(cur, zipcode) if zipcode else None
    tract_hisp = get_lodes_tract_hispanic(cur, tract_fips) if tract_fips else None
    if tract_hisp is None:
        tract_hisp = get_tract_hispanic(cur, county_fips)
    hisp_result = _blend_dicts([
        (acs_hisp, 0.35), (lodes_hisp, 0.25), (tract_hisp, 0.40)
    ], HISP_CATS)

    # Gender: G1 (occupation-weighted + IPF blend)
    gender_data = method_g1_occupation_gender(
        cur, naics4, state_fips, county_fips,
        cbsa_code=cbsa_code, zipcode=zipcode)
    gender_result = gender_data['gender']

    return {
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        '_race_source': 'M9b',
        '_hisp_source': 'expert_b_style',
        '_gender_source': gender_data.get('_gender_source', 'G1'),
        '_lq': lq,
    }


# ============================================================
# Expert E: Finance/Utilities Hard Route (Step 11)
# ============================================================

def expert_e_finance_utilities(cur, naics4, state_fips, county_fips, **kwargs):
    """Expert E: Hard route for Finance (52) and Utilities (22).

    These industries have strong ACS signal but weak LODES geographic signal.
    Uses smoothed IPF (not dampened) with industry-specific LODES when available.
    Bypasses gate -- directly routed based on NAICS.
    """
    acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
    naics_2 = naics4[:2] if naics4 else None
    ind_lodes = get_lodes_industry_race(cur, county_fips, naics_2)
    lodes_race = ind_lodes if ind_lodes is not None else get_lodes_race(cur, county_fips)

    race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS),
        '_expert': 'E',
    }


# ============================================================
# Expert F: Occupation-Weighted for Manufacturing/Transportation (Step 12)
# ============================================================

def expert_f_occupation_weighted(cur, naics4, state_fips, county_fips,
                                  cbsa_code='', **kwargs):
    """Expert F: Occupation-weighted for Manufacturing/Transportation/Admin.

    For NAICS 31-33, 48-49, 56: occupation mix is highly predictive of
    demographics. Uses BLS industry-occupation matrix fed into IPF.
    Gender uses G1 occupation-weighted method.
    """
    from data_loaders import get_occupation_mix

    occ_mix = get_occupation_mix(cur, naics4)
    lodes_race = get_lodes_race(cur, county_fips)

    if occ_mix:
        # Build occupation-weighted ACS race
        from methodologies import _build_occ_weighted
        occ_race = _build_occ_weighted(cur, occ_mix, state_fips, 'race', RACE_CATS)
        if occ_race:
            # IPF: occupation-weighted ACS x LODES
            race_result = smoothed_ipf(occ_race, lodes_race, RACE_CATS)
        else:
            # Fallback to standard ACS x LODES
            acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
            race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)
    else:
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        race_result = smoothed_ipf(acs_race, lodes_race, RACE_CATS)

    acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
    lodes_hisp = get_lodes_hispanic(cur, county_fips)

    # Gender: G1 occupation-weighted
    occ_gender = _occupation_weighted_gender(cur, naics4, cbsa_code)
    acs_gender = get_acs_gender(cur, naics4, state_fips)
    lodes_gender = get_lodes_gender(cur, county_fips)
    ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

    if occ_gender is not None and ipf_gender is not None:
        bls_weight = get_gender_blend_weight(naics4[:2])
        ipf_weight = 1.0 - bls_weight
        gender_result = _blend_dicts([
            (occ_gender, bls_weight), (ipf_gender, ipf_weight)
        ], GENDER_CATS)
    else:
        gender_result = ipf_gender

    return {
        'race': race_result,
        'hispanic': smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS),
        'gender': gender_result,
        '_expert': 'F',
    }


# ============================================================
# Gender bounds enforcement (Step 24)
# ============================================================

def apply_gender_bounds(gender_result, naics4):
    """Apply industry-specific gender bounds to prevent extreme estimates.

    Soft bounds: flag for review.
    Hard bounds: cap estimate at bound value.
    """
    if gender_result is None:
        return gender_result, []

    from config import GENDER_BOUNDS
    naics_2 = naics4[:2] if naics4 else ''
    bounds = GENDER_BOUNDS.get(naics_2)
    if not bounds:
        return gender_result, []

    flags = []
    pct_female = gender_result.get('Female', 50.0)

    hard_min = bounds.get('hard_min')
    hard_max = bounds.get('hard_max')
    soft_min = bounds.get('soft_min')
    soft_max = bounds.get('soft_max')

    # Hard bounds: clamp
    if hard_min is not None and pct_female < hard_min:
        pct_female = hard_min
        flags.append('gender_hard_min_%.0f' % hard_min)
    if hard_max is not None and pct_female > hard_max:
        pct_female = hard_max
        flags.append('gender_hard_max_%.0f' % hard_max)

    # Soft bounds: flag only
    if soft_min is not None and pct_female < soft_min:
        flags.append('gender_soft_min_%.0f' % soft_min)
    if soft_max is not None and pct_female > soft_max:
        flags.append('gender_soft_max_%.0f' % soft_max)

    corrected = {
        'Male': round(100.0 - pct_female, 2),
        'Female': round(pct_female, 2),
    }
    return corrected, flags


# ============================================================
# Expert G: Occupation-Chain Local Demographics
# ============================================================

def method_expert_g_occ_chain(cur, naics4, state_fips, county_fips,
                               naics_group=None, **kwargs):
    """Expert G: Occupation-chain local demographics.

    Uses precomputed occupation-chain table (BLS industry mix x ACS state
    occupation demographics) as primary signal, blended with standard IPF
    as a fallback when coverage is low.

    Best for: Healthcare, Finance, Information, Professional services --
    industries with well-defined occupation mixes and geographic demographic
    variation in those occupations (especially Asian workers in coastal metros).

    Returns dict matching standard expert output format.
    """
    from data_loaders import get_occ_chain_demographics
    from methodologies_v3 import _variable_dampened_ipf

    if not naics_group:
        naics_group = classify_naics_group(naics4)

    occ_chain = get_occ_chain_demographics(cur, naics_group, state_fips)

    if occ_chain and occ_chain['_pct_covered'] >= 40:
        # High confidence: primarily trust occupation chain
        occ_weight = 0.70

        # Get standard IPF estimate as secondary signal
        acs_race = get_acs_race_nonhispanic_v2(cur, naics4, state_fips)
        lodes_race = get_lodes_race(cur, county_fips)
        group = classify_naics_group(naics4)
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        ipf_race = smoothed_variable_dampened_ipf(acs_race, lodes_race, RACE_CATS, alpha)

        if ipf_race:
            # Blend: 70% occupation chain, 30% IPF
            result_race = {}
            for cat in RACE_CATS:
                result_race[cat] = (occ_weight * occ_chain.get(cat, 0) +
                               (1 - occ_weight) * ipf_race.get(cat, 0))
            data_source = 'expert_g_occ_chain_blend'
        else:
            result_race = {k: occ_chain.get(k, 0) for k in RACE_CATS}
            data_source = 'expert_g_occ_chain_only'

        # Renormalize race to 100%
        race_total = sum(result_race.get(k, 0) for k in RACE_CATS)
        if race_total > 0:
            for k in RACE_CATS:
                result_race[k] = round(result_race[k] * 100 / race_total, 2)

        # Gender from occupation chain with adaptive blend
        bls_weight = get_gender_blend_weight(naics4[:2])
        ipf_weight_g = 1.0 - bls_weight
        acs_gender = get_acs_gender(cur, naics4, state_fips)
        lodes_gender = get_lodes_gender(cur, county_fips)
        ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)
        occ_gender_est = {'Female': occ_chain.get('Female', 50.0),
                          'Male': 100.0 - occ_chain.get('Female', 50.0)}
        if ipf_gender:
            gender_result = _blend_dicts([
                (occ_gender_est, bls_weight), (ipf_gender, ipf_weight_g)
            ], GENDER_CATS)
        else:
            gender_result = occ_gender_est

        # Hispanic from occupation chain blended with IPF
        acs_hisp = get_acs_hispanic(cur, naics4, state_fips)
        lodes_hisp = get_lodes_hispanic(cur, county_fips)
        ipf_hisp = smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS)
        occ_hisp = {'Hispanic': occ_chain.get('Hispanic', 0.0),
                     'Not Hispanic': 100.0 - occ_chain.get('Hispanic', 0.0)}
        if ipf_hisp:
            hisp_result = _blend_dicts([
                (occ_hisp, 0.60), (ipf_hisp, 0.40)
            ], HISP_CATS)
        else:
            hisp_result = occ_hisp

        return {
            'race': result_race,
            'hispanic': hisp_result,
            'gender': gender_result,
            '_data_source': data_source,
        }

    else:
        # Low coverage: fall back to standard variable dampened IPF
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
            '_data_source': 'expert_g_fallback_ipf',
        }


# ============================================================
# Method registries
# ============================================================

# Methods that need extra kwargs (cbsa_code, zipcode, etc.)
V6_METHODS_NEED_EXTRA = {
    'M2c-Multi Tract-Ensemble',
    'M2c-Metro ACS-Metro',
    'G1 Occ-Gender',
    'H1 Geo-Hispanic',
    'V6-Full Pipeline',
    'Expert-E Finance/Util',
    'Expert-F Occ-Weighted',
    'Expert-G Occ-Chain',
}

ALL_V6_METHODS = {
    'M9a Industry-LODES-IPF': method_9a_industry_lodes_ipf,
    'M9b QCEW-Adaptive': method_9b_qcew_adaptive,
    'M9c Combined': method_9c_combined,
    'M3c-IND Ind-Var-Damp': method_3c_ind,
    'M1b-QCEW LQ-Weights': method_1b_qcew,
    'M2c-Multi Tract-Ensemble': method_2c_multi,
    'M2c-Metro ACS-Metro': method_2c_metro,
    'G1 Occ-Gender': method_g1_occupation_gender,
    'H1 Geo-Hispanic': method_h1_geographic_hispanic,
    'Expert-E Finance/Util': expert_e_finance_utilities,
    'Expert-F Occ-Weighted': expert_f_occupation_weighted,
    'Expert-G Occ-Chain': method_expert_g_occ_chain,
    'V6-Full Pipeline': method_v6_full,
}
