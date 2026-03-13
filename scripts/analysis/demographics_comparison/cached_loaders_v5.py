"""Extended cached loaders for V5 methods.

Subclasses CachedLoadersV3. Adds:
    - PUMS metro-level demographics accessors (get_pums_race, etc.)
    - County-to-CBSA lookup
    - Cached method wrappers for all V5 methods
    - PUMS-first data source pattern with ACS state fallback
"""
from cached_loaders import RACE_CATS, HISP_CATS, GENDER_CATS
from cached_loaders_v3 import CachedLoadersV3
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf,
    OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import (
    OPTIMAL_DAMPENING_BY_GROUP,
    _classify_m5_category,
    _variable_dampened_ipf,
)
from methodologies_v5 import (
    apply_floor, smoothed_ipf, smoothed_dampened_ipf,
    smoothed_variable_dampened_ipf,
    NATIONAL_EEO1_PRIOR, NAICS_GROUP_COUNTS, PRIOR_WEIGHT,
    _prior_smooth,
)
from config import M8_M1B_HISPANIC_INDUSTRIES
from classifiers import classify_naics_group, classify_region


def _floor_result(result):
    """Apply smoothing floor to race output to prevent zero-collapse from blends."""
    if result and result.get('race'):
        result['race'] = apply_floor(result['race'])
    return result


class CachedLoadersV5(CachedLoadersV3):
    """CachedLoadersV3 extended with PUMS metro-level data accessors."""

    def get_county_cbsa(self, county_fips):
        """Look up CBSA code for a county FIPS via cbsa_counties table."""
        return self._cached(
            ('county_cbsa', county_fips),
            self._query_county_cbsa, county_fips)

    def _query_county_cbsa(self, county_fips):
        if not county_fips:
            return None
        self.cur.execute(
            "SELECT cbsa_code FROM cbsa_counties WHERE fips_full = %s LIMIT 1",
            [county_fips])
        row = self.cur.fetchone()
        return row['cbsa_code'] if row else None

    def get_pums_race(self, cbsa_code, naics_2digit):
        """Get PUMS metro-level race demographics."""
        return self._cached(
            ('pums_race', cbsa_code, naics_2digit),
            self._query_pums_race, cbsa_code, naics_2digit)

    def _query_pums_race(self, cbsa_code, naics_2digit):
        if not cbsa_code or not naics_2digit:
            return None
        self.cur.execute(
            "SELECT race_white, race_black, race_asian, race_aian, "
            "race_nhopi, race_two_plus "
            "FROM pums_metro_demographics "
            "WHERE met2013 = %s AND naics_2digit = %s",
            [cbsa_code, naics_2digit])
        row = self.cur.fetchone()
        if not row:
            return None
        return {
            'White': float(row['race_white']),
            'Black': float(row['race_black']),
            'Asian': float(row['race_asian']),
            'AIAN': float(row['race_aian']),
            'NHOPI': float(row['race_nhopi']),
            'Two+': float(row['race_two_plus']),
        }

    def get_pums_hispanic(self, cbsa_code, naics_2digit):
        """Get PUMS metro-level Hispanic demographics."""
        return self._cached(
            ('pums_hispanic', cbsa_code, naics_2digit),
            self._query_pums_hispanic, cbsa_code, naics_2digit)

    def _query_pums_hispanic(self, cbsa_code, naics_2digit):
        if not cbsa_code or not naics_2digit:
            return None
        self.cur.execute(
            "SELECT hispanic_pct FROM pums_metro_demographics "
            "WHERE met2013 = %s AND naics_2digit = %s",
            [cbsa_code, naics_2digit])
        row = self.cur.fetchone()
        if not row:
            return None
        hisp = float(row['hispanic_pct'])
        return {'Hispanic': hisp, 'Not Hispanic': round(100.0 - hisp, 2)}

    def get_pums_gender(self, cbsa_code, naics_2digit):
        """Get PUMS metro-level gender demographics."""
        return self._cached(
            ('pums_gender', cbsa_code, naics_2digit),
            self._query_pums_gender, cbsa_code, naics_2digit)

    def _query_pums_gender(self, cbsa_code, naics_2digit):
        if not cbsa_code or not naics_2digit:
            return None
        self.cur.execute(
            "SELECT sex_female FROM pums_metro_demographics "
            "WHERE met2013 = %s AND naics_2digit = %s",
            [cbsa_code, naics_2digit])
        row = self.cur.fetchone()
        if not row:
            return None
        female = float(row['sex_female'])
        return {'Male': round(100.0 - female, 2), 'Female': female}

    def get_pums_or_acs_race(self, naics4, state_fips, county_fips):
        """PUMS-first race data with ACS state fallback.

        Returns (race_dict, data_source) tuple.
        """
        cbsa_code = self.get_county_cbsa(county_fips)
        naics_2digit = naics4[:2] if naics4 else None
        pums_race = self.get_pums_race(cbsa_code, naics_2digit) if cbsa_code else None
        if pums_race is not None:
            return pums_race, 'pums_metro'
        return self.get_acs_race(naics4, state_fips), 'acs_state'


# ============================================================
# Cached method wrappers for V5 methods
# ============================================================

def cached_method_3c_v5(cl, naics4, state_fips, county_fips, **kwargs):
    """M3c-V5 Smooth-Var-Damp: Variable dampened IPF with smoothing + PUMS."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def cached_method_3e_v5(cl, naics4, state_fips, county_fips, **kwargs):
    """M3e-V5 Smooth-Fin-Route: Finance/Utilities route + smoothed IPF + PUMS."""
    group = classify_naics_group(naics4)
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    if group in ('Finance/Insurance (52)', 'Utilities (22)'):
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        race_result = smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha)

    return _floor_result({
        'race': race_result,
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def cached_method_2c_v5(cl, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """M2c-V5 PUMS-ZIP-Tract: Three-layer with PUMS + ZIP-tract."""
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    tract_fips = cl.get_zip_to_best_tract(zipcode)
    tract_race = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
    tract_hisp = cl.get_lodes_tract_hispanic(tract_fips) if tract_fips else None
    tract_gender = cl.get_lodes_tract_gender(tract_fips) if tract_fips else None

    if tract_race is None:
        tract_race = cl.get_tract_race(county_fips)
    if tract_hisp is None:
        tract_hisp = cl.get_tract_hispanic(county_fips)
    if tract_gender is None:
        tract_gender = cl.get_tract_gender(county_fips)

    return _floor_result({
        'race': _blend_dicts([
            (race_data, 0.50), (lodes_race, 0.30), (tract_race, 0.20)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.50),
            (cl.get_lodes_hispanic(county_fips), 0.30),
            (tract_hisp, 0.20)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.50),
            (cl.get_lodes_gender(county_fips), 0.30),
            (tract_gender, 0.20)], GENDER_CATS),
        '_data_source': data_source,
    })


def cached_method_5e_v5(cl, naics4, state_fips, county_fips, **kwargs):
    """M5e-V5 Ind-Dispatch: Industry dispatcher with Admin/Staffing -> M1B fix."""
    category = _classify_m5_category(naics4)
    group = classify_naics_group(naics4)

    if category == 'occupation':
        if group in ('Finance/Insurance (52)', 'Utilities (22)'):
            return _cached_m3_ipf_v5(cl, naics4, state_fips, county_fips)
        elif group == 'Admin/Staffing (56)':
            return _cached_m1b_v5(cl, naics4, state_fips, county_fips)
        else:
            return _cached_m3c_v5(cl, naics4, state_fips, county_fips)
    elif category == 'local_labor':
        return _cached_m3d_v5(cl, naics4, state_fips, county_fips)
    elif category == 'manufacturing':
        if group == 'Computer/Electrical Mfg (334-335)':
            return _cached_m1b_v5(cl, naics4, state_fips, county_fips)
        else:
            return _cached_m3c_v5(cl, naics4, state_fips, county_fips)
    else:
        return _cached_m3c_v5(cl, naics4, state_fips, county_fips)


def cached_method_8_v5(cl, naics4, state_fips, county_fips,
                        naics_group='', county_minority_share=None,
                        urbanicity='', state_abbr='', zipcode='', **kwargs):
    """M8-V5 Adaptive-Router: With Admin/Staffing -> M1B fix + smoothed IPF."""
    if not naics_group:
        naics_group = classify_naics_group(naics4)
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if county_minority_share is None:
        county_minority_share = cl.get_lodes_pct_minority(county_fips)

    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    min_share = county_minority_share if county_minority_share is not None else 0.0
    routing_used = 'M3C'

    if naics_group == 'Finance/Insurance (52)':
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Utilities (22)':
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif naics_group == 'Admin/Staffing (56)':
        # FIX: route to M1B instead of M4E
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        race_result = _blend_dicts([(race_data, acs_w), (lodes_race, lodes_w)], RACE_CATS)
        routing_used = 'M1B'
    elif min_share > 0.50:
        acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(naics_group, (0.60, 0.40))
        race_result = _blend_dicts([(race_data, acs_w), (lodes_race, lodes_w)], RACE_CATS)
        routing_used = 'M1B'
    elif urbanicity == 'Suburban' and min_share < 0.25:
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
        routing_used = 'M3_ORIGINAL'
    elif region == 'Midwest':
        if min_share > 0.20:
            race_result = smoothed_dampened_ipf(race_data, lodes_race, RACE_CATS)
        else:
            race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
        routing_used = 'M3D'
    else:
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50)
        race_result = smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha)
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

    # === GENDER: Always smoothed IPF ===
    gender_result = smoothed_ipf(
        cl.get_acs_gender(naics4, state_fips),
        cl.get_lodes_gender(county_fips), GENDER_CATS)

    return _floor_result({
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        'routing_used': routing_used,
        'hispanic_routing': hispanic_routing,
        '_data_source': data_source,
    })


def cached_expert_a(cl, naics4, state_fips, county_fips, **kwargs):
    """Expert-A Smooth-IPF: Smoothed dampened IPF + EEO-1 prior + alpha shrinkage."""
    group = classify_naics_group(naics4)
    alpha_learned = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    n_segment = NAICS_GROUP_COUNTS.get(group, 5)
    alpha_final = (n_segment * alpha_learned + 5 * 0.50) / (n_segment + 5)

    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    acs_smooth = _prior_smooth(race_data, NATIONAL_EEO1_PRIOR)
    lodes_smooth = _prior_smooth(lodes_race, NATIONAL_EEO1_PRIOR)

    race_result = smoothed_variable_dampened_ipf(acs_smooth, lodes_smooth, RACE_CATS, alpha_final)

    return _floor_result({
        'race': race_result,
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def cached_expert_b(cl, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """Expert-B Tract-Heavy: 35/25/40 ACS/LODES/Tract blend."""
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    tract_fips = cl.get_zip_to_best_tract(zipcode)
    tract_race = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
    tract_hisp = cl.get_lodes_tract_hispanic(tract_fips) if tract_fips else None
    tract_gender = cl.get_lodes_tract_gender(tract_fips) if tract_fips else None

    if tract_race is None:
        tract_race = cl.get_tract_race(county_fips)
    if tract_hisp is None:
        tract_hisp = cl.get_tract_hispanic(county_fips)
    if tract_gender is None:
        tract_gender = cl.get_tract_gender(county_fips)

    w1, w2, w3 = 0.35, 0.25, 0.40
    return _floor_result({
        'race': _blend_dicts([
            (race_data, w1), (lodes_race, w2), (tract_race, w3)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), w1),
            (cl.get_lodes_hispanic(county_fips), w2),
            (tract_hisp, w3)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), w1),
            (cl.get_lodes_gender(county_fips), w2),
            (tract_gender, w3)], GENDER_CATS),
        '_data_source': data_source,
    })


# ============================================================
# Helper methods for V5 routing (cached versions with smoothing)
# ============================================================

def _cached_m3_ipf_v5(cl, naics4, state_fips, county_fips):
    """Cached M3 original IPF with smoothing + PUMS."""
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    return _floor_result({
        'race': smoothed_ipf(race_data, cl.get_lodes_race(county_fips), RACE_CATS),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def _cached_m3c_v5(cl, naics4, state_fips, county_fips):
    """Cached M3c variable dampened IPF with smoothing + PUMS."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    return _floor_result({
        'race': smoothed_variable_dampened_ipf(
            race_data, cl.get_lodes_race(county_fips), RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def _cached_m3d_v5(cl, naics4, state_fips, county_fips):
    """Cached M3d selective dampening with smoothing + PUMS."""
    pct_min = cl.get_lodes_pct_minority(county_fips)
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)
    if pct_min is not None and pct_min > 0.20:
        race_result = smoothed_dampened_ipf(race_data, lodes_race, RACE_CATS)
    else:
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
    return _floor_result({
        'race': race_result,
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': data_source,
    })


def _cached_m1b_v5(cl, naics4, state_fips, county_fips):
    """Cached M1b learned weights with PUMS."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))
    race_data, data_source = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    return _floor_result({
        'race': _blend_dicts([
            (race_data, acs_w),
            (cl.get_lodes_race(county_fips), lodes_w)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), acs_w),
            (cl.get_lodes_hispanic(county_fips), lodes_w)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), acs_w),
            (cl.get_lodes_gender(county_fips), lodes_w)], GENDER_CATS),
        '_data_source': data_source,
    })


# Methods that need extra kwargs
V5_METHODS_NEED_EXTRA = {
    'M2c-V5 PUMS-ZIP-Tract',
    'M5e-V5 Ind-Dispatch',
    'M8-V5 Adaptive-Router',
    'Expert-B Tract-Heavy',
}

ALL_V5_CACHED_METHODS = {
    'M3c-V5 Smooth-Var-Damp': cached_method_3c_v5,
    'M3e-V5 Smooth-Fin-Route': cached_method_3e_v5,
    'M2c-V5 PUMS-ZIP-Tract': cached_method_2c_v5,
    'M5e-V5 Ind-Dispatch': cached_method_5e_v5,
    'M8-V5 Adaptive-Router': cached_method_8_v5,
    'Expert-A Smooth-IPF': cached_expert_a,
    'Expert-B Tract-Heavy': cached_expert_b,
}
