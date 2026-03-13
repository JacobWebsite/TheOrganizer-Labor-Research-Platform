"""Dict-cached wrappers around data_loaders to avoid redundant DB queries.

CachedLoaders holds a cursor internally and caches results keyed by
(function_name, arg1, arg2, ...). Also provides cached method wrappers
that replicate methodology logic using cached data.
"""
from data_loaders import (
    get_acs_race_nonhispanic_v2, get_acs_hispanic, get_acs_gender,
    get_lodes_race, get_lodes_hispanic, get_lodes_gender,
    get_tract_race, get_tract_hispanic, get_tract_gender,
    get_occupation_mix, get_acs_by_occupation,
)
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _normalize, _build_occ_weighted,
)
from config import get_industry_weights


class CachedLoaders:
    def __init__(self, cur):
        self.cur = cur
        self._cache = {}
        self.hits = 0
        self.misses = 0

    def _cached(self, key, fn, *args):
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        result = fn(*args)
        self._cache[key] = result
        return result

    def get_acs_race(self, naics4, state_fips):
        return self._cached(
            ('acs_race', naics4, state_fips),
            get_acs_race_nonhispanic_v2, self.cur, naics4, state_fips)

    def get_acs_hispanic(self, naics4, state_fips):
        return self._cached(
            ('acs_hispanic', naics4, state_fips),
            get_acs_hispanic, self.cur, naics4, state_fips)

    def get_acs_gender(self, naics4, state_fips):
        return self._cached(
            ('acs_gender', naics4, state_fips),
            get_acs_gender, self.cur, naics4, state_fips)

    def get_lodes_race(self, county_fips):
        return self._cached(
            ('lodes_race', county_fips),
            get_lodes_race, self.cur, county_fips)

    def get_lodes_hispanic(self, county_fips):
        return self._cached(
            ('lodes_hispanic', county_fips),
            get_lodes_hispanic, self.cur, county_fips)

    def get_lodes_gender(self, county_fips):
        return self._cached(
            ('lodes_gender', county_fips),
            get_lodes_gender, self.cur, county_fips)

    def get_tract_race(self, county_fips):
        return self._cached(
            ('tract_race', county_fips),
            get_tract_race, self.cur, county_fips)

    def get_tract_hispanic(self, county_fips):
        return self._cached(
            ('tract_hispanic', county_fips),
            get_tract_hispanic, self.cur, county_fips)

    def get_tract_gender(self, county_fips):
        return self._cached(
            ('tract_gender', county_fips),
            get_tract_gender, self.cur, county_fips)

    def get_occupation_mix(self, naics4):
        return self._cached(
            ('occ_mix', naics4),
            get_occupation_mix, self.cur, naics4)

    def get_acs_by_occupation(self, soc_code, state_fips, dimension):
        return self._cached(
            ('acs_occ', soc_code, state_fips, dimension),
            get_acs_by_occupation, self.cur, soc_code, state_fips, dimension)

    def _build_occ_weighted(self, occ_mix, state_fips, dimension, categories):
        """Build occupation-weighted estimate using cached ACS by occupation."""
        key = ('occ_weighted', tuple((s, p) for s, p in occ_mix[:30]),
               state_fips, dimension)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        weighted = {k: 0.0 for k in categories}
        total_weight = 0.0
        for soc_code, pct_of_industry in occ_mix[:30]:
            demo = self.get_acs_by_occupation(soc_code, state_fips, dimension)
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

    def print_stats(self):
        total = self.hits + self.misses
        rate = (100.0 * self.hits / total) if total > 0 else 0
        print('Cache stats: %d hits, %d misses, %.1f%% hit rate (%d unique keys)' % (
            self.hits, self.misses, rate, len(self._cache)))


# ============================================================
# Cached method wrappers (same logic as methodologies.py)
# ============================================================

RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']


def cached_method_1(cl, naics4, state_fips, county_fips):
    """M1 Baseline (60/40)"""
    return {
        'race': _blend_dicts([
            (cl.get_acs_race(naics4, state_fips), 0.60),
            (cl.get_lodes_race(county_fips), 0.40)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.60),
            (cl.get_lodes_hispanic(county_fips), 0.40)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.60),
            (cl.get_lodes_gender(county_fips), 0.40)], GENDER_CATS),
    }


def cached_method_2(cl, naics4, state_fips, county_fips):
    """M2 Three-Layer (50/30/20)"""
    return {
        'race': _blend_dicts([
            (cl.get_acs_race(naics4, state_fips), 0.50),
            (cl.get_lodes_race(county_fips), 0.30),
            (cl.get_tract_race(county_fips), 0.20)], RACE_CATS),
        'hispanic': _blend_dicts([
            (cl.get_acs_hispanic(naics4, state_fips), 0.50),
            (cl.get_lodes_hispanic(county_fips), 0.30),
            (cl.get_tract_hispanic(county_fips), 0.20)], HISP_CATS),
        'gender': _blend_dicts([
            (cl.get_acs_gender(naics4, state_fips), 0.50),
            (cl.get_lodes_gender(county_fips), 0.30),
            (cl.get_tract_gender(county_fips), 0.20)], GENDER_CATS),
    }


def cached_method_3(cl, naics4, state_fips, county_fips):
    """M3 IPF"""
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


def cached_method_4(cl, naics4, state_fips, county_fips):
    """M4 Occ-Weighted"""
    occ_mix = cl.get_occupation_mix(naics4)
    if not occ_mix:
        # Fallback to Method 1 style with 70/30
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
    occ_race = cl._build_occ_weighted(occ_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = cl._build_occ_weighted(occ_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = cl._build_occ_weighted(occ_mix, state_fips, 'gender', GENDER_CATS)
    return {
        'race': _blend_dicts([
            (occ_race, 0.70), (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([
            (occ_hisp, 0.70), (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
        'gender': _blend_dicts([
            (occ_gender, 0.70), (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
    }


def cached_method_5(cl, naics4, state_fips, county_fips):
    """M5 Variable-Weight"""
    acs_w, lodes_w = get_industry_weights(naics4)
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


def cached_method_6(cl, naics4, state_fips, county_fips):
    """M6 IPF+Occ"""
    occ_mix = cl.get_occupation_mix(naics4)
    if not occ_mix:
        # Fallback to plain IPF
        return cached_method_3(cl, naics4, state_fips, county_fips)
    occ_race = cl._build_occ_weighted(occ_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = cl._build_occ_weighted(occ_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = cl._build_occ_weighted(occ_mix, state_fips, 'gender', GENDER_CATS)
    return {
        'race': _ipf_two_marginals(occ_race, cl.get_lodes_race(county_fips), RACE_CATS),
        'hispanic': _ipf_two_marginals(occ_hisp, cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(occ_gender, cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


ALL_CACHED_METHODS = {
    'M1 Baseline (60/40)': cached_method_1,
    'M2 Three-Layer (50/30/20)': cached_method_2,
    'M3 IPF': cached_method_3,
    'M4 Occ-Weighted': cached_method_4,
    'M5 Variable-Weight': cached_method_5,
    'M6 IPF+Occ': cached_method_6,
}
