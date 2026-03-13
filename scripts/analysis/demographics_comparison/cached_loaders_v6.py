"""Extended cached loaders for V6 methods.

Subclasses CachedLoadersV5. Adds:
    - Industry-specific LODES demographics (CNS-weighted)
    - QCEW concentration lookup
    - Metro ACS demographics
    - Multi-tract ensemble demographics
    - Occupation mix (local OES)
    - CPS occupation gender percentages
    - Cached method wrappers for all V6 methods
"""
from cached_loaders import RACE_CATS, HISP_CATS, GENDER_CATS
from cached_loaders_v5 import CachedLoadersV5, _floor_result
from methodologies import (
    _blend_dicts, OPTIMAL_WEIGHTS_BY_GROUP,
)
from methodologies_v3 import OPTIMAL_DAMPENING_BY_GROUP
from methodologies_v5 import (
    apply_floor, smoothed_ipf, smoothed_variable_dampened_ipf,
)
from methodologies_v6 import _qcew_adaptive_alpha, _occupation_weighted_gender
from data_loaders import (
    get_lodes_industry_race, get_lodes_industry_hispanic,
    get_qcew_concentration,
    get_acs_race_metro, get_multi_tract_demographics,
    get_occupation_mix_local, get_pct_female_by_occupation,
    get_occ_chain_demographics,
)
from classifiers import classify_naics_group
from config import NAICS_TO_CNS
import os as _os
import json as _json

# Load ABS owner density from JSON backup (keyed by county_fips)
_ABS_DENSITY = {}
_abs_path = _os.path.join(_os.path.dirname(__file__), 'abs_owner_density.json')
if _os.path.exists(_abs_path):
    with open(_abs_path, 'r', encoding='utf-8') as _f:
        _ABS_DENSITY = _json.load(_f)

# Load SLD transit scores from JSON backup (keyed by geoid10)
_SLD_TRANSIT = {}
_SLD_TRACT_INDEX = {}  # tract_prefix (11 digits) -> list of bg data dicts
_sld_path = _os.path.join(_os.path.dirname(__file__), 'sld_transit_scores.json')
if _os.path.exists(_sld_path):
    with open(_sld_path, 'r', encoding='utf-8') as _f:
        _SLD_TRANSIT = _json.load(_f)
    # Build tract-level prefix index for fast lookup
    for _bg_geoid, _bg_data in _SLD_TRANSIT.items():
        _tract_key = _bg_geoid[:11]
        if _tract_key not in _SLD_TRACT_INDEX:
            _SLD_TRACT_INDEX[_tract_key] = []
        _SLD_TRACT_INDEX[_tract_key].append(_bg_data)


class CachedLoadersV6(CachedLoadersV5):
    """CachedLoadersV5 extended with V6 data accessors."""

    def get_lodes_industry_race(self, county_fips, naics_2digit):
        """Get industry-specific LODES race demographics."""
        return self._cached(
            ('lodes_industry_race', county_fips, naics_2digit),
            get_lodes_industry_race, self.cur, county_fips, naics_2digit)

    def get_lodes_industry_hispanic(self, county_fips, naics_2digit):
        """Get industry-specific LODES Hispanic demographics."""
        return self._cached(
            ('lodes_industry_hispanic', county_fips, naics_2digit),
            get_lodes_industry_hispanic, self.cur, county_fips, naics_2digit)

    def get_industry_or_county_lodes_hispanic(self, county_fips, naics4):
        """Get industry-specific LODES Hispanic if available, else county.

        Returns (hispanic_dict, data_source) tuple.
        """
        naics_2 = naics4[:2] if naics4 else None
        ind = self.get_lodes_industry_hispanic(county_fips, naics_2)
        if ind is not None:
            return ind, 'lodes_industry'
        return self.get_lodes_hispanic(county_fips), 'lodes_county'

    def get_qcew_concentration(self, county_fips, naics_2digit):
        """Get QCEW concentration (LQ, pay, employment)."""
        return self._cached(
            ('qcew_conc', county_fips, naics_2digit),
            get_qcew_concentration, self.cur, county_fips, naics_2digit)

    def get_occ_chain_demographics(self, naics_group, state_fips):
        """Cached lookup for occupation-chain demographics."""
        return self._cached(
            ('occ_chain', naics_group, state_fips),
            get_occ_chain_demographics, self.cur, naics_group, state_fips)

    def get_acs_race_metro(self, naics_code, cbsa_code):
        """Get ACS race demographics at metro level."""
        return self._cached(
            ('acs_race_metro', naics_code, cbsa_code),
            get_acs_race_metro, self.cur, naics_code, cbsa_code)

    def get_multi_tract_demographics(self, zipcode):
        """Get multi-tract ensemble demographics for ZIP."""
        return self._cached(
            ('multi_tract', zipcode),
            get_multi_tract_demographics, self.cur, zipcode)

    def get_occupation_mix_local(self, naics_code, cbsa_code):
        """Get local OES occupation mix."""
        return self._cached(
            ('occ_mix_local', naics_code, cbsa_code),
            get_occupation_mix_local, self.cur, naics_code, cbsa_code)

    def get_pct_female_by_occupation(self, soc_code):
        """Get CPS Table 11 percent female for occupation."""
        return self._cached(
            ('pct_female_occ', soc_code),
            get_pct_female_by_occupation, self.cur, soc_code)

    def get_industry_or_county_lodes(self, county_fips, naics4):
        """Get industry-specific LODES if available, otherwise county LODES.

        Returns (race_dict, data_source) tuple.
        """
        naics_2 = naics4[:2] if naics4 else None
        ind = self.get_lodes_industry_race(county_fips, naics_2)
        if ind is not None:
            return ind, 'lodes_industry'
        return self.get_lodes_race(county_fips), 'lodes_county'

    def get_qcew_lq(self, county_fips, naics4):
        """Get QCEW location quotient. Returns float or None."""
        naics_2 = naics4[:2] if naics4 else None
        qcew = self.get_qcew_concentration(county_fips, naics_2)
        return qcew['location_quotient'] if qcew else None

    def get_abs_owner_density(self, county_fips):
        """Get ABS minority-owner density for a county.

        Returns dict with 'minority_share' (0-100) or None.
        Uses JSON backup (no DB query needed).
        """
        return _ABS_DENSITY.get(county_fips)

    def get_transit_score(self, zipcode):
        """Get transit score for a ZIP code via zip_tract_crosswalk.

        Joins ZIP -> tract_geoid (11-digit) -> block groups in SLD.
        Averages transit_score weighted by bus_ratio across matching BGs.
        Returns dict with 'transit_score' and 'transit_tier', or None.
        """
        key = ('transit_score', zipcode)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        if not zipcode or not _SLD_TRANSIT:
            self._cache[key] = None
            return None

        # Look up tracts for this ZIP
        try:
            self.cur.execute("""
                SELECT tract, bus_ratio
                FROM zip_tract_crosswalk
                WHERE zip = %s AND bus_ratio > 0
            """, (zipcode,))
            rows = self.cur.fetchall()
        except Exception:
            # Rollback failed transaction to allow further queries
            try:
                self.cur.connection.rollback()
            except Exception:
                pass
            self._cache[key] = None
            return None

        if not rows:
            self._cache[key] = None
            return None

        # Match tracts to SLD block groups (tract = 11 digits, BG = 12 digits)
        total_weight = 0.0
        weighted_score = 0.0
        tier_counts = {}

        for row in rows:
            tract_geoid = str(row.get('tract', row[0]) if isinstance(row, dict) else row[0])
            bus_ratio = float(row.get('bus_ratio', row[1]) if isinstance(row, dict) else row[1])

            # Find all block groups matching this tract (LEFT 11 digits)
            # Use prefix index for O(1) lookup instead of scanning all 220K entries
            tract_prefix = tract_geoid[:11]
            matching_bgs = _SLD_TRACT_INDEX.get(tract_prefix, [])

            if matching_bgs:
                # Average across block groups in this tract
                avg_score = sum(bg['transit_score'] for bg in matching_bgs) / len(matching_bgs)
                weighted_score += avg_score * bus_ratio
                total_weight += bus_ratio

                # Most common tier
                for bg in matching_bgs:
                    t = bg['transit_tier']
                    tier_counts[t] = tier_counts.get(t, 0) + 1

        if total_weight == 0:
            self._cache[key] = None
            return None

        final_score = round(weighted_score / total_weight, 2)
        # Determine tier from score
        if final_score < 10:
            final_tier = 'none'
        elif final_score < 25:
            final_tier = 'minimal'
        elif final_score < 50:
            final_tier = 'moderate'
        else:
            final_tier = 'high'

        result = {'transit_score': final_score, 'transit_tier': final_tier}
        self._cache[key] = result
        return result

    def get_occupation_weighted_gender(self, naics4, cbsa_code):
        """Get occupation-weighted gender estimate.

        Uses BLS industry-occupation matrix (industry-specific) rather than
        OES metro (all-industry) to avoid generic ~50% female estimates.
        """
        key = ('occ_weighted_gender', naics4, cbsa_code)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        # BLS industry-occupation matrix is industry-specific (preferred)
        occ_mix = self.get_occupation_mix(naics4)
        if not occ_mix:
            self._cache[key] = None
            return None

        total_emp = 0.0
        weighted_female = 0.0
        for soc_code, emp in occ_mix[:50]:
            pct_f = self.get_pct_female_by_occupation(soc_code)
            if pct_f is not None:
                total_emp += emp
                weighted_female += emp * pct_f

        if total_emp == 0:
            self._cache[key] = None
            return None

        pct_female = weighted_female / total_emp
        result = {'Male': round(100.0 - pct_female, 2), 'Female': round(pct_female, 2)}
        self._cache[key] = result
        return result


# ============================================================
# Cached method wrappers for V6 methods
# ============================================================

def cached_method_9a(cl, naics4, state_fips, county_fips, **kwargs):
    """M9a Industry-LODES-IPF: ACS x industry-specific LODES."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race, lodes_src = cl.get_industry_or_county_lodes(county_fips, naics4)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': lodes_src,
    })


def cached_method_9b(cl, naics4, state_fips, county_fips, **kwargs):
    """M9b QCEW-Adaptive: Variable dampened IPF with QCEW LQ alpha."""
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    lq = cl.get_qcew_lq(county_fips, naics4)
    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_lq': lq,
        '_alpha_used': alpha,
    })


def cached_method_9c(cl, naics4, state_fips, county_fips, **kwargs):
    """M9c Combined: Industry-LODES + QCEW adaptive alpha."""
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    lq = cl.get_qcew_lq(county_fips, naics4)
    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race, lodes_src = cl.get_industry_or_county_lodes(county_fips, naics4)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_data_source': lodes_src + '+qcew',
        '_lq': lq,
        '_alpha_used': alpha,
    })


def cached_method_3c_ind(cl, naics4, state_fips, county_fips, **kwargs):
    """M3c-IND: Variable dampened IPF with industry LODES."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race, _ = cl.get_industry_or_county_lodes(county_fips, naics4)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    })


def cached_method_1b_qcew(cl, naics4, state_fips, county_fips, **kwargs):
    """M1b-QCEW: Learned weights with QCEW LQ adjustment."""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_BY_GROUP.get(group, (0.60, 0.40))

    lq = cl.get_qcew_lq(county_fips, naics4)
    if lq is not None:
        if lq >= 2.0:
            lodes_w = min(lodes_w + 0.20, 0.85)
        elif lq >= 1.5:
            lodes_w = min(lodes_w + 0.10, 0.75)
        elif lq < 0.5:
            lodes_w = max(lodes_w - 0.15, 0.10)
        acs_w = 1.0 - lodes_w

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    return _floor_result({
        'race': _blend_dicts([(race_data, acs_w), (lodes_race, lodes_w)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), acs_w),
            (cl.get_lodes_hispanic(county_fips), lodes_w)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), acs_w),
            (cl.get_lodes_gender(county_fips), lodes_w)], GENDER_CATS),
    })


def cached_method_2c_multi(cl, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """M2c-Multi: Three-layer with multi-tract ensemble."""
    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    multi = cl.get_multi_tract_demographics(zipcode) if zipcode else None
    tract_race = multi.get('race') if multi else None
    tract_hisp = multi.get('hispanic') if multi else None
    tract_gender = multi.get('gender') if multi else None

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
    })


def cached_method_2c_metro(cl, naics4, state_fips, county_fips,
                            cbsa_code='', **kwargs):
    """M2c-Metro: Metro ACS + LODES + Tract blend."""
    metro_acs = cl.get_acs_race_metro(naics4, cbsa_code) if cbsa_code else None
    race_data = metro_acs if metro_acs is not None else cl.get_acs_race(naics4, state_fips)
    lodes_race = cl.get_lodes_race(county_fips)
    tract_race = cl.get_tract_race(county_fips)

    return _floor_result({
        'race': _blend_dicts([
            (race_data, 0.50), (lodes_race, 0.30), (tract_race, 0.20)
        ], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.50),
            (cl.get_lodes_hispanic(county_fips), 0.30),
            (cl.get_tract_hispanic(county_fips), 0.20)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.50),
            (cl.get_lodes_gender(county_fips), 0.30),
            (cl.get_tract_gender(county_fips), 0.20)], GENDER_CATS),
        '_data_source': 'acs_metro' if metro_acs else 'acs_state',
    })


def cached_method_g1(cl, naics4, state_fips, county_fips,
                      cbsa_code='', **kwargs):
    """G1 Occ-Gender: Occupation-weighted gender blended with IPF."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    occ_gender = cl.get_occupation_weighted_gender(naics4, cbsa_code)
    acs_gender = cl.get_acs_gender(naics4, state_fips)
    lodes_gender = cl.get_lodes_gender(county_fips)
    ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

    if occ_gender is not None and ipf_gender is not None:
        from methodologies_v6 import get_gender_blend_weight
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

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': gender_result,
        '_gender_source': gender_source,
    })


def cached_method_h1(cl, naics4, state_fips, county_fips,
                      zipcode='', cbsa_code='', **kwargs):
    """H1 Geo-Hispanic: Geography-heavy Hispanic method."""
    group = classify_naics_group(naics4)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)

    lodes_hisp = cl.get_lodes_hispanic(county_fips)

    # PUMS Hispanic
    pums_hisp = None
    if cbsa_code:
        naics_2 = naics4[:2] if naics4 else None
        pums_h = cl.get_pums_hispanic(cbsa_code, naics_2) if cbsa_code else None
        if pums_h is not None:
            pums_hisp = pums_h

    # Multi-tract Hispanic
    tract_hisp = None
    if zipcode:
        multi = cl.get_multi_tract_demographics(zipcode)
        if multi:
            tract_hisp = multi.get('hispanic')
    if tract_hisp is None:
        tract_hisp = cl.get_tract_hispanic(county_fips)

    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)

    if pums_hisp is not None:
        hisp_result = _blend_dicts([
            (lodes_hisp, 0.35), (pums_hisp, 0.30),
            (tract_hisp, 0.20), (acs_hisp, 0.15)
        ], HISP_CATS)
    else:
        hisp_result = _blend_dicts([
            (lodes_hisp, 0.45), (tract_hisp, 0.30), (acs_hisp, 0.25)
        ], HISP_CATS)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)

    return _floor_result({
        'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
        'hispanic': hisp_result,
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    })


def cached_method_v6_full(cl, naics4, state_fips, county_fips,
                           cbsa_code='', zipcode='', **kwargs):
    """V6-Full: Dimension-specific (M9b race + Expert-B hisp + G1 gender).

    Optimal combination discovered via ablation study.
    """
    # Race: M9b (QCEW-adaptive, county LODES -- no industry LODES)
    group = classify_naics_group(naics4)
    base_alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
    lq = cl.get_qcew_lq(county_fips, naics4)
    alpha = _qcew_adaptive_alpha(lq, base_alpha)

    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race = cl.get_lodes_race(county_fips)
    race_result = smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha)

    # Hispanic: Expert-B style 35/25/40 tract-heavy blend
    acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
    lodes_hisp = cl.get_lodes_hispanic(county_fips)
    tract_fips = cl.get_zip_to_best_tract(zipcode)
    tract_hisp = cl.get_lodes_tract_hispanic(tract_fips) if tract_fips else None
    if tract_hisp is None:
        tract_hisp = cl.get_tract_hispanic(county_fips)
    hisp_result = _blend_dicts([
        (acs_hisp, 0.35), (lodes_hisp, 0.25), (tract_hisp, 0.40)
    ], HISP_CATS)

    # Gender: G1
    g1_result = cached_method_g1(cl, naics4, state_fips, county_fips,
                                  cbsa_code=cbsa_code)
    gender_result = g1_result.get('gender')

    return _floor_result({
        'race': race_result,
        'hispanic': hisp_result,
        'gender': gender_result,
        '_race_source': 'M9b',
        '_hisp_source': 'expert_b_style',
        '_gender_source': g1_result.get('_gender_source', 'G1'),
        '_lq': lq,
    })


def cached_expert_e(cl, naics4, state_fips, county_fips, **kwargs):
    """Expert-E: Finance/Utilities hard route (smoothed IPF + industry LODES)."""
    race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
    lodes_race, _ = cl.get_industry_or_county_lodes(county_fips, naics4)

    return _floor_result({
        'race': smoothed_ipf(race_data, lodes_race, RACE_CATS),
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': smoothed_ipf(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
        '_expert': 'E',
    })


def cached_expert_f(cl, naics4, state_fips, county_fips,
                     cbsa_code='', **kwargs):
    """Expert-F: Occupation-weighted for Manufacturing/Transport/Admin."""
    occ_mix = cl.get_occupation_mix(naics4)
    lodes_race = cl.get_lodes_race(county_fips)

    if occ_mix:
        occ_race = cl._build_occ_weighted_topn(occ_mix, state_fips, 'race', RACE_CATS, top_n=30)
        if occ_race:
            race_result = smoothed_ipf(occ_race, lodes_race, RACE_CATS)
        else:
            race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
            race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
    else:
        race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
        race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)

    # Gender: G1 occupation-weighted blend
    occ_gender = cl.get_occupation_weighted_gender(naics4, cbsa_code)
    acs_gender = cl.get_acs_gender(naics4, state_fips)
    lodes_gender = cl.get_lodes_gender(county_fips)
    ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

    if occ_gender is not None and ipf_gender is not None:
        from methodologies_v6 import get_gender_blend_weight
        bls_weight = get_gender_blend_weight(naics4[:2])
        ipf_weight = 1.0 - bls_weight
        gender_result = _blend_dicts([
            (occ_gender, bls_weight), (ipf_gender, ipf_weight)
        ], GENDER_CATS)
    else:
        gender_result = ipf_gender

    return _floor_result({
        'race': race_result,
        'hispanic': smoothed_ipf(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': gender_result,
        '_expert': 'F',
    })


def cached_expert_g(cl, naics4, state_fips, county_fips,
                     naics_group=None, **kwargs):
    """Expert G: Occupation-chain local demographics."""
    if not naics_group:
        naics_group = classify_naics_group(naics4)

    occ_chain = cl.get_occ_chain_demographics(naics_group, state_fips)

    if occ_chain and occ_chain.get('_pct_covered', 0) >= 40:
        occ_weight = 0.70

        race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
        lodes_race = cl.get_lodes_race(county_fips)
        group = classify_naics_group(naics4)
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        ipf_race = smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha)

        if ipf_race:
            result_race = {}
            for cat in RACE_CATS:
                result_race[cat] = (occ_weight * occ_chain.get(cat, 0) +
                                   (1 - occ_weight) * ipf_race.get(cat, 0))
            data_source = 'expert_g_occ_chain_blend'
        else:
            result_race = {k: occ_chain.get(k, 0) for k in RACE_CATS}
            data_source = 'expert_g_occ_chain_only'

        # Renormalize race
        race_total = sum(result_race.get(k, 0) for k in RACE_CATS)
        if race_total > 0:
            for k in RACE_CATS:
                result_race[k] = round(result_race[k] * 100 / race_total, 2)

        # Gender
        from methodologies_v6 import get_gender_blend_weight
        bls_w = get_gender_blend_weight(naics4[:2])
        ipf_w = 1.0 - bls_w
        acs_gender = cl.get_acs_gender(naics4, state_fips)
        lodes_gender = cl.get_lodes_gender(county_fips)
        ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)
        occ_gender = {'Female': occ_chain.get('Female', 50.0),
                      'Male': 100.0 - occ_chain.get('Female', 50.0)}
        if ipf_gender:
            gender_result = _blend_dicts([(occ_gender, bls_w), (ipf_gender, ipf_w)], GENDER_CATS)
        else:
            gender_result = occ_gender

        # Hispanic
        acs_hisp = cl.get_acs_hispanic(naics4, state_fips)
        lodes_hisp = cl.get_lodes_hispanic(county_fips)
        ipf_hisp = smoothed_ipf(acs_hisp, lodes_hisp, HISP_CATS)
        occ_hisp = {'Hispanic': occ_chain.get('Hispanic', 0.0),
                     'Not Hispanic': 100.0 - occ_chain.get('Hispanic', 0.0)}
        if ipf_hisp:
            hisp_result = _blend_dicts([(occ_hisp, 0.60), (ipf_hisp, 0.40)], HISP_CATS)
        else:
            hisp_result = occ_hisp

        return _floor_result({
            'race': result_race,
            'hispanic': hisp_result,
            'gender': gender_result,
            '_data_source': data_source,
        })
    else:
        # Fallback to standard IPF
        group = classify_naics_group(naics4)
        alpha = OPTIMAL_DAMPENING_BY_GROUP.get(group, 0.50)
        race_data, _ = cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
        lodes_race = cl.get_lodes_race(county_fips)
        return _floor_result({
            'race': smoothed_variable_dampened_ipf(race_data, lodes_race, RACE_CATS, alpha),
            'hispanic': smoothed_ipf(
                cl.get_acs_hispanic(naics4, state_fips),
                cl.get_lodes_hispanic(county_fips), HISP_CATS),
            'gender': smoothed_ipf(
                cl.get_acs_gender(naics4, state_fips),
                cl.get_lodes_gender(county_fips), GENDER_CATS),
            '_data_source': 'expert_g_fallback_ipf',
        })


# Methods that need extra kwargs
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

ALL_V6_CACHED_METHODS = {
    'M9a Industry-LODES-IPF': cached_method_9a,
    'M9b QCEW-Adaptive': cached_method_9b,
    'M9c Combined': cached_method_9c,
    'M3c-IND Ind-Var-Damp': cached_method_3c_ind,
    'M1b-QCEW LQ-Weights': cached_method_1b_qcew,
    'M2c-Multi Tract-Ensemble': cached_method_2c_multi,
    'M2c-Metro ACS-Metro': cached_method_2c_metro,
    'G1 Occ-Gender': cached_method_g1,
    'H1 Geo-Hispanic': cached_method_h1,
    'Expert-E Finance/Util': cached_expert_e,
    'Expert-F Occ-Weighted': cached_expert_f,
    'Expert-G Occ-Chain': cached_expert_g,
    'V6-Full Pipeline': cached_method_v6_full,
}
