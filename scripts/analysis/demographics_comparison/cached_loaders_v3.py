"""Extended cached loaders for V3 methods (M1c-M5d).

Subclasses CachedLoadersV2 with new cache accessors for ZIP-to-tract
crosswalk. Provides cached method wrappers for all 9 new methods.
"""
from cached_loaders import RACE_CATS, HISP_CATS, GENDER_CATS
from cached_loaders_v2 import CachedLoadersV2
from methodologies import (
    _blend_dicts, _ipf_two_marginals, _dampened_ipf,
)
from methodologies_v3 import (
    OPTIMAL_WEIGHTS_V3_BY_GROUP,
    OPTIMAL_WEIGHTS_V3_BY_CATEGORY,
    OPTIMAL_DAMPENING_BY_GROUP,
    _classify_m5_category,
    _variable_dampened_ipf,
)
from config import get_industry_weights
from classifiers import classify_naics_group, classify_region


class CachedLoadersV3(CachedLoadersV2):
    """CachedLoadersV2 extended with V3 data accessors."""

    def get_zip_to_best_tract(self, zipcode):
        """Look up the best business tract for a ZIP code via crosswalk."""
        return self._cached(
            ('zip_best_tract', zipcode),
            self._query_zip_best_tract, zipcode)

    def _query_zip_best_tract(self, zipcode):
        if not zipcode:
            return None
        self.cur.execute(
            "SELECT tract_geoid FROM zip_tract_crosswalk "
            "WHERE zip_code = %s ORDER BY bus_ratio DESC LIMIT 1",
            [zipcode])
        row = self.cur.fetchone()
        return row['tract_geoid'] if row else None

    def _build_occ_weighted_topn(self, occ_mix, state_fips, dimension, categories, top_n=10):
        """Build occ-weighted estimate with top_n limit, using cache."""
        key = ('occ_weighted_topn', tuple((s, p) for s, p in occ_mix[:top_n]),
               state_fips, dimension, top_n)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        weighted = {k: 0.0 for k in categories}
        total_weight = 0.0

        for soc_code, pct_of_industry in occ_mix[:top_n]:
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

    def _build_state_top5_national_rest(self, occ_mix, state_fips, dimension, categories):
        """Top 5: state ACS. Remaining: national ACS. Using cache."""
        key = ('state_top5_rest', tuple((s, p) for s, p in occ_mix[:30]),
               state_fips, dimension)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1

        weighted = {k: 0.0 for k in categories}
        total_weight = 0.0

        for i, (soc_code, pct_of_industry) in enumerate(occ_mix[:30]):
            if i < 5:
                demo = self.get_acs_by_occupation(soc_code, state_fips, dimension)
                if not demo:
                    demo = self.get_acs_by_occupation(soc_code, '0', dimension)
            else:
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
# Cached method wrappers for V3 methods
# ============================================================

def cached_method_1c(cl, naics4, state_fips, county_fips, **kwargs):
    """M1c CV-Learned-Wt"""
    group = classify_naics_group(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_GROUP.get(group, (0.55, 0.45))
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


def cached_method_1d(cl, naics4, state_fips, county_fips, state_abbr='', **kwargs):
    """M1d Regional-Wt"""
    region = classify_region(state_abbr) if state_abbr else 'Other'
    if region == 'West':
        acs_w, lodes_w = 0.75, 0.25
    else:
        acs_w, lodes_w = 0.60, 0.40
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


def cached_method_2c(cl, naics4, state_fips, county_fips, zipcode='', **kwargs):
    """M2c ZIP-Tract"""
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


def cached_method_3c(cl, naics4, state_fips, county_fips, **kwargs):
    """M3c Var-Damp-IPF"""
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


def cached_method_3d(cl, naics4, state_fips, county_fips, **kwargs):
    """M3d Select-Damp"""
    pct_min = cl.get_lodes_pct_minority(county_fips)
    if pct_min is not None and pct_min > 0.20:
        race_result = _dampened_ipf(
            cl.get_acs_race(naics4, state_fips),
            cl.get_lodes_race(county_fips), RACE_CATS)
    else:
        race_result = _ipf_two_marginals(
            cl.get_acs_race(naics4, state_fips),
            cl.get_lodes_race(county_fips), RACE_CATS)
    return {
        'race': race_result,
        'hispanic': _ipf_two_marginals(
            cl.get_acs_hispanic(naics4, state_fips),
            cl.get_lodes_hispanic(county_fips), HISP_CATS),
        'gender': _ipf_two_marginals(
            cl.get_acs_gender(naics4, state_fips),
            cl.get_lodes_gender(county_fips), GENDER_CATS),
    }


def cached_method_4c(cl, naics4, state_fips, county_fips, **kwargs):
    """M4c Top10-Occ"""
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
    occ_race = cl._build_occ_weighted_topn(occ_mix, state_fips, 'race', RACE_CATS, top_n=10)
    occ_hisp = cl._build_occ_weighted_topn(occ_mix, state_fips, 'hispanic', HISP_CATS, top_n=10)
    occ_gender = cl._build_occ_weighted_topn(occ_mix, state_fips, 'gender', GENDER_CATS, top_n=10)
    return {
        'race': _blend_dicts([
            (occ_race, 0.70), (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([
            (occ_hisp, 0.70), (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
        'gender': _blend_dicts([
            (occ_gender, 0.70), (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
    }


def cached_method_4d(cl, naics4, state_fips, county_fips, **kwargs):
    """M4d State-Top5"""
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

    occ_race = cl._build_state_top5_national_rest(occ_mix, state_fips, 'race', RACE_CATS)
    occ_hisp = cl._build_state_top5_national_rest(occ_mix, state_fips, 'hispanic', HISP_CATS)
    occ_gender = cl._build_state_top5_national_rest(occ_mix, state_fips, 'gender', GENDER_CATS)

    return {
        'race': _blend_dicts([
            (occ_race, 0.70), (cl.get_lodes_race(county_fips), 0.30)], RACE_CATS),
        'hispanic': _blend_dicts([
            (occ_hisp, 0.70), (cl.get_lodes_hispanic(county_fips), 0.30)], HISP_CATS),
        'gender': _blend_dicts([
            (occ_gender, 0.70), (cl.get_lodes_gender(county_fips), 0.30)], GENDER_CATS),
    }


def cached_method_5c(cl, naics4, state_fips, county_fips, **kwargs):
    """M5c CV-Var-Wt"""
    category = _classify_m5_category(naics4)
    acs_w, lodes_w = OPTIMAL_WEIGHTS_V3_BY_CATEGORY.get(category, (0.55, 0.45))
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


def cached_method_5d(cl, naics4, state_fips, county_fips, **kwargs):
    """M5d Corr-Min-Adapt"""
    acs_w, lodes_w = get_industry_weights(naics4)
    pct_min = cl.get_lodes_pct_minority(county_fips)

    if pct_min is not None:
        if pct_min > 0.50:
            acs_w = max(0.20, acs_w - 0.20)
            lodes_w = min(0.80, 1.0 - acs_w)
        elif pct_min > 0.30:
            acs_w = max(0.25, acs_w - 0.10)
            lodes_w = min(0.75, 1.0 - acs_w)

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


# Methods that need extra kwargs (state_abbr, zipcode)
V3_METHODS_NEED_EXTRA = {'M1d Regional-Wt', 'M2c ZIP-Tract'}

ALL_V3_CACHED_METHODS = {
    'M1c CV-Learned-Wt': cached_method_1c,
    'M1d Regional-Wt': cached_method_1d,
    'M2c ZIP-Tract': cached_method_2c,
    'M3c Var-Damp-IPF': cached_method_3c,
    'M3d Select-Damp': cached_method_3d,
    'M4c Top10-Occ': cached_method_4c,
    'M4d State-Top5': cached_method_4d,
    'M5c CV-Var-Wt': cached_method_5c,
    'M5d Corr-Min-Adapt': cached_method_5d,
}
