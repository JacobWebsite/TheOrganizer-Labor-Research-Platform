"""V12 Demographics Estimation API Service.

V12 is the production demographics model as of 2026-03-27. It integrates
Census QWI (Quarterly Workforce Indicators) county x NAICS4 data into the
V10 architecture and improves all three dimensions simultaneously.

Sealed holdout results:
  V10:  Race=4.325  Hispanic=6.661  Gender=10.550
  V12:  Race=4.083  Hispanic=6.438  Gender=9.726

Loads three artifacts at startup:
  1. QWI cache   (~77 MB JSON, 255,672 primary county x NAICS4 cells)
  2. Calibration offsets (from export_v12.py)
  3. Hispanic weights    (industry + tier overrides, from export_v12.py)

All three are lazy-loaded on first request so the API starts up fast.
"""
import os
import sys
import json
import logging

logger = logging.getLogger(__name__)

# Add demographics scripts dir to sys.path so we can import the pipeline
DEMO_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts', 'analysis', 'demographics_comparison'))
if DEMO_DIR not in sys.path:
    sys.path.insert(0, DEMO_DIR)

# Calibration / weights JSON files live under api/data/
API_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))

# Lazy-loaded globals
_qwi = None
_calibration = None
_industry_weights = None
_tier_best_weights = None
_models_loaded = False

# V12 dampening parameters (copied from run_v12.py)
D_RACE = 0.85
D_HISP = 0.50
D_GENDER = 0.95


def _deserialize_offsets(serialized_offsets):
    """Turn pipe-delimited string keys back into tuples.

    Input:  {'race|White|dt_reg_ind|Med-High|South|Healthcare/Social (62)':
             {'offset': 1.23, 'n': 45}, ...}
    Output: {('race','White','dt_reg_ind','Med-High','South','Healthcare/Social (62)'):
             (1.23, 45), ...}
    """
    out = {}
    for k_str, v in serialized_offsets.items():
        tup = tuple(k_str.split('|'))
        out[tup] = (v['offset'], v['n'])
    return out


def _load_models():
    """Lazy-load QWI cache, calibration, and Hispanic weights."""
    global _qwi, _calibration, _industry_weights, _tier_best_weights, _models_loaded
    if _models_loaded:
        return

    from run_v12_qwi import QWICache

    logger.info('Loading QWI cache...')
    try:
        _qwi = QWICache()
        logger.info('QWI cache loaded')
    except Exception as e:
        logger.error('Failed to load QWI cache: %s' % str(e))
        _qwi = None

    cal_path = os.path.join(API_DATA_DIR, 'v12_calibration.json')
    try:
        with open(cal_path, 'r', encoding='utf-8') as f:
            cal_raw = json.load(f)
        _calibration = _deserialize_offsets(cal_raw['offsets'])
        logger.info('V12 calibration loaded (%d buckets)' % len(_calibration))
    except Exception as e:
        logger.error('Failed to load v12_calibration.json: %s' % str(e))
        _calibration = {}

    hw_path = os.path.join(API_DATA_DIR, 'v12_hispanic_weights.json')
    try:
        with open(hw_path, 'r', encoding='utf-8') as f:
            hw = json.load(f)
        _industry_weights = hw.get('industry_weights', {})
        _tier_best_weights = hw.get('tier_best_weights', {})
        logger.info('V12 Hispanic weights loaded (%d industries, %d tiers)' % (
            len(_industry_weights), len(_tier_best_weights)))
    except Exception as e:
        logger.error('Failed to load v12_hispanic_weights.json: %s' % str(e))
        _industry_weights = {}
        _tier_best_weights = {}

    _models_loaded = True


def estimate_demographics_v12(cur, naics, state_fips, zipcode, county_fips,
                               state_abbr=None, total_employees=100):
    """Estimate workforce demographics for an employer using the V12 QWI model.

    Args:
        cur: psycopg2 RealDictCursor
        naics: NAICS code (4-6 digits; first 4 used)
        state_fips: 2-digit state FIPS
        zipcode: 5-digit ZIP
        county_fips: 5-digit county FIPS (required for QWI lookups)
        state_abbr: 2-letter state code (for region classification)
        total_employees: headcount (unused by V12, kept for signature parity)

    Returns:
        dict with race, hispanic, gender, metadata; or None on error.
    """
    _load_models()

    if _qwi is None or _calibration is None:
        return None

    # Lazy imports (these depend on DEMO_DIR being on sys.path)
    from classifiers import classify_naics_group
    from config import get_census_region
    from cached_loaders_v6 import CachedLoadersV6
    from cached_loaders_v5 import cached_expert_a
    from run_v9_2 import (
        get_raw_signals, collect_black_signals, apply_calibration_v92,
        get_diversity_tier,
    )
    from run_v12 import v12_scenario
    from estimate_confidence import estimate_confidence

    try:
        naics = (naics or '').strip()
        naics4 = naics[:4]
        county_fips = (county_fips or '').strip()
        zipcode = (zipcode or '').strip()
        state_fips = (state_fips or '').strip()

        cl = CachedLoadersV6(cur)

        # Classifications
        naics_group = classify_naics_group(naics4)
        region = get_census_region(state_abbr) if state_abbr else None

        # Diversity tier (from county LODES minority %)
        lodes_race = cl.get_lodes_race(county_fips) if county_fips else None
        county_minority_pct = None
        if lodes_race and 'White' in lodes_race:
            county_minority_pct = 100.0 - lodes_race['White']
        diversity_tier = get_diversity_tier(county_minority_pct)

        # CBSA for Expert F occupation lookups
        cbsa_code = cl.get_county_cbsa(county_fips) if county_fips else ''
        cbsa_code = cbsa_code or ''

        # Compute Expert A and Expert F predictions (V12 needs A for race blend,
        # F for gender blend; D is only used in the QWI-miss fallback and Black
        # adjustment, which we gracefully skip when D is absent)
        expert_a = cached_expert_a(cl, naics4, state_fips, county_fips)
        from cached_loaders_v6 import cached_expert_f
        expert_f = cached_expert_f(cl, naics4, state_fips, county_fips,
                                    cbsa_code=cbsa_code)

        # Build the record dict the V12 scenario functions expect
        rec = {
            'naics4': naics4,
            'naics_group': naics_group,
            'region': region,
            'state_fips': state_fips,
            'county_fips': county_fips,
            'state': state_abbr,
            'zipcode': zipcode,
            'cbsa_code': cbsa_code,
            'county_minority_pct': county_minority_pct,
            'diversity_tier': diversity_tier,
            'total_employees': total_employees,
            'expert_preds': {
                'A': expert_a,
                'F': expert_f,
                'D': {},  # empty; Black adjustment skips when D race missing
            },
        }
        rec['signals'] = get_raw_signals(cl, rec)

        # black_signals reads rec['expert_preds']['D'] which we left empty;
        # collect_black_signals handles a missing D gracefully (treats as 0)
        rec['black_signals'] = collect_black_signals(rec, cl)

        # Record which QWI level provided the race signal, for metadata
        qwi_level = _detect_qwi_level(county_fips, naics4)

        # Run V12 scenario + calibration
        pred = v12_scenario(rec, _qwi, _industry_weights, _tier_best_weights)
        if not pred or not pred.get('race'):
            return None

        final = apply_calibration_v92(pred, rec, _calibration,
                                       d_race=D_RACE, d_hisp=D_HISP, d_gender=D_GENDER)

        # Confidence tier
        confidence = estimate_confidence(naics_group, diversity_tier, region or 'Midwest')

        return {
            'race': final.get('race'),
            'hispanic': final.get('hispanic'),
            'gender': final.get('gender'),
            'metadata': {
                'model': 'v12_qwi',
                'confidence_tier': confidence,
                'qwi_level': qwi_level,
                'naics_group': naics_group,
                'diversity_tier': diversity_tier,
                'region': region,
            },
        }
    except Exception as e:
        logger.exception('V12 estimation failed: %s' % str(e))
        return None


def _detect_qwi_level(county_fips, naics4):
    """Figure out which QWI cascade level produced the race signal.

    Returns one of: county_naics4, county_naics2, county_all,
    state_naics4, state_naics2, or none.
    """
    if _qwi is None or not county_fips or not naics4:
        return 'none'
    naics2 = naics4[:2]
    state_fips = county_fips[:2]
    for level, key, source in [
        ('county_naics4', county_fips + ':' + naics4, _qwi.primary),
        ('county_naics2', county_fips + ':' + naics2, _qwi.county_n2),
        ('county_all',    county_fips,                _qwi.county_all),
        ('state_naics4',  state_fips + ':' + naics4,  _qwi.state_n4),
        ('state_naics2',  state_fips + ':' + naics2,  _qwi.state_n2),
    ]:
        cell = source.get(key)
        if cell and 'race' in cell:
            return level
    return 'none'
