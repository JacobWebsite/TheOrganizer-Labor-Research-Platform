"""Extended cached loaders for V2 methods (M1b-M5b, M7).

Subclasses CachedLoaders with new cache accessors for tract-level LODES,
state occupation mix, and minority share. Provides cached method wrappers
for all 6 new methods.
"""
from cached_loaders import CachedLoaders, RACE_CATS, HISP_CATS, GENDER_CATS
from data_loaders import (
    get_lodes_tract_race, get_lodes_tract_hispanic, get_lodes_tract_gender,
    get_state_occupation_mix, get_lodes_pct_minority, zip_to_tract,
    get_acs_by_occupation,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf,
    OPTIMAL_WEIGHTS_BY_GROUP,
    _build_occ_weighted_with_fallback,
)
from config import get_industry_weights


class CachedLoadersV2(CachedLoaders):
    """CachedLoaders extended with V2 data accessors."""

    def get_lodes_tract_race(self, tract_fips):
        return self._cached(
            ('lodes_tract_race', tract_fips),
            get_lodes_tract_race, self.cur, tract_fips)

    def get_lodes_tract_hispanic(self, tract_fips):
        return self._cached(
            ('lodes_tract_hispanic', tract_fips),
            get_lodes_tract_hispanic, self.cur, tract_fips)

    def get_lodes_tract_gender(self, tract_fips):
        return self._cached(
            ('lodes_tract_gender', tract_fips),
            get_lodes_tract_gender, self.cur, tract_fips)

    def get_state_occupation_mix(self, naics4, state_fips):
        return self._cached(
            ('state_occ_mix', naics4, state_fips),
            get_state_occupation_mix, self.cur, naics4, state_fips)

    def get_lodes_pct_minority(self, county_fips):
        return self._cached(
            ('lodes_pct_minority', county_fips),
            get_lodes_pct_minority, self.cur, county_fips)

    def zip_to_tract(self, zipcode, county_fips):
        return self._cached(
            ('zip_to_tract', zipcode, county_fips),
            zip_to_tract, self.cur, zipcode, county_fips)

    def _build_occ_weighted_v2(self, occ_mix, state_fips, dimension, categories):
        """Build occ-weighted estimate with per-SOC fallback, using cache."""
        key = ('occ_weighted_v2', tuple((s, p) for s, p in occ_mix[:30]),
               state_fips, dimension)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        weighted = {k: 0.0 for k in categories}
        total_weight = 0.0

        for soc_code, pct_of_industry in occ_mix[:30]:
            demo = self.get_acs_by_occupation(soc_code, state_fips, dimension)
            # If state sample is too small, try national
            if demo and demo.get('_workers', 0) < 100:
                national = self.get_acs_by_occupation(soc_code, '0', dimension)
                if national:
                    demo = national
            if not demo:
                demo = self.get_acs_by_occupation(soc_code, '0', dimension)
            if demo:
                for k in categories:
                    weighted[k] += demo.get(k, 0) * pct_of_industry
                total_weight += pct_of_industry

        if total_weight == 0:
            self._cache[key] = None
            return None
        result = {k: round(weighted[k] / total_weight, 2) for k in categories}
        self._cache[key] = result
        return result


# ============================================================
# Cached method wrappers for V2 methods
# ============================================================

def cached_method_1b(cl, naics4, state_fips, county_fips):
    """M1b Learned-Wt"""
    from classifiers import classify_naics_group
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


def cached_method_2b(cl, naics4, state_fips, county_fips):
    """M2b Workplace-Tract"""
    # Get largest-employment tract in county
    tract_fips = cl.zip_to_tract(None, county_fips)
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
            (cl.get_acs_race(naics4, state_fips), 0.50),
            (cl.get_lodes_race(county_fips), 0.30),
            (tract_race, 0.20)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.50),
            (cl.get_lodes_hispanic(county_fips), 0.30),
            (tract_hisp, 0.20)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.50),
            (cl.get_lodes_gender(county_fips), 0.30),
            (tract_gender, 0.20)], GENDER_CATS),
    }


def cached_method_3b(cl, naics4, state_fips, county_fips):
    """M3b Damp-IPF"""
    return {
        'race': _dampened_ipf(
            cl.get_acs_race(naics4, state_fips),
            cl.get_lodes_race(county_fips), RACE_CATS),
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def cached_method_4b(cl, naics4, state_fips, county_fips):
    """M4b State-Occ"""
    state_mix = cl.get_state_occupation_mix(naics4, state_fips)
    if not state_mix:
        state_mix = cl.get_occupation_mix(naics4)  # fall back to national BLS
    if not state_mix:
        # Fall back to 70/30 blend
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

    occ_race = cl._build_occ_weighted_v2(state_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = cl._build_occ_weighted_v2(state_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = cl._build_occ_weighted_v2(state_mix, state_fips, 'gender', GENDER_CATS)

    return {
        'race': _blend_dicts([
            (occ_race, 0.70), (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([
            (occ_hisp, 0.70), (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
        'gender': _blend_dicts([
            (occ_gender, 0.70), (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
    }


def cached_method_5b(cl, naics4, state_fips, county_fips):
    """M5b Min-Adapt"""
    acs_w, lodes_w = get_industry_weights(naics4)
    pct_min = cl.get_lodes_pct_minority(county_fips)
    if pct_min is not None:
        if pct_min > 0.50:
            acs_w += 0.20
        elif pct_min > 0.30:
            acs_w += 0.10
        acs_w = min(acs_w, 0.85)
        lodes_w = 1.0 - acs_w

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


def cached_method_7(cl, naics4, state_fips, county_fips):
    """M7 Hybrid (M1b race + M3 gender)"""
    m1b = cached_method_1b(cl, naics4, state_fips, county_fips)
    m3 = {
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

    return {
        'race': m1b['race'] if m1b.get('race') else m3.get('race'),
        'hispanic': m1b['hispanic'] if m1b.get('hispanic') else m3.get('hispanic'),
        'gender': m3['gender'] if m3.get('gender') else m1b.get('gender'),
    }


ALL_V2_CACHED_METHODS = {
    'M1b Learned-Wt': cached_method_1b,
    'M2b Workplace-Tract': cached_method_2b,
    'M3b Damp-IPF': cached_method_3b,
    'M4b State-Occ': cached_method_4b,
    'M5b Min-Adapt': cached_method_5b,
    'M7 Hybrid': cached_method_7,
}
