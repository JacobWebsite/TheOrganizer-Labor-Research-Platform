"""V5 Demographics Estimation API Service.

Loads Gate v1 model and calibration at import. Provides a single entry point
for workforce demographics estimation with review flags.

Fallback: M3b (dampened IPF) if Gate v1 errors or model not available.
"""
import os
import sys
import json
import pickle
import logging
import re

logger = logging.getLogger(__name__)

# Add demographics comparison scripts to path
DEMO_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts', 'analysis', 'demographics_comparison'))
if DEMO_DIR not in sys.path:
    sys.path.insert(0, DEMO_DIR)

# Lazy-loaded globals
_gate_model = None
_calibration = None
_model_loaded = False

RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']

# Hard segments for review flags
HARD_SEGMENTS = {
    'Healthcare/Social (62)', 'Admin/Staffing (56)',
    'Food/Bev Manufacturing (311,312)', 'Accommodation/Food Svc (72)',
}


def _load_models():
    """Lazy-load Gate v1 model and calibration."""
    global _gate_model, _calibration, _model_loaded
    if _model_loaded:
        return

    model_path = os.path.join(DEMO_DIR, 'gate_v1.pkl')
    cal_path = os.path.join(DEMO_DIR, 'calibration_v1.json')

    try:
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                _gate_model = pickle.load(f)
            logger.info('Loaded gate_v1.pkl')
        else:
            logger.warning('gate_v1.pkl not found, using M3b fallback')
    except Exception as e:
        logger.error('Failed to load gate_v1.pkl: %s' % str(e))

    try:
        if os.path.exists(cal_path):
            with open(cal_path, 'r', encoding='utf-8') as f:
                _calibration = json.load(f)
            logger.info('Loaded calibration_v1.json')
    except Exception as e:
        logger.error('Failed to load calibration_v1.json: %s' % str(e))

    _model_loaded = True


def _apply_calibration(pred_race, expert):
    """Apply bias correction from OOF calibration."""
    if not pred_race or not _calibration or expert not in _calibration:
        return pred_race

    biases = _calibration[expert]
    corrected = {}
    for cat in RACE_CATS:
        val = pred_race.get(cat, 0)
        bias = biases.get(cat, 0)
        corrected[cat] = max(0, val - bias)

    total = sum(corrected.values())
    if total > 0:
        corrected = {k: round(v * 100.0 / total, 2) for k, v in corrected.items()}
    return corrected


def estimate_demographics_v5(cur, naics, state_fips, zipcode, county_fips, total_employees=100):
    """Estimate workforce demographics using V5 Gate v1 pipeline.

    Args:
        cur: psycopg2 RealDictCursor
        naics: 4-6 digit NAICS code
        state_fips: 2-digit state FIPS
        zipcode: 5-digit ZIP code
        county_fips: 5-digit county FIPS
        total_employees: headcount (for size classification)

    Returns:
        dict with:
            race: {White: pct, Black: pct, ...}
            hispanic: {Hispanic: pct, Not Hispanic: pct}
            gender: {Male: pct, Female: pct}
            metadata: {expert_used, confidence_score, data_source,
                      review_flag, review_reasons}
    """
    _load_models()

    naics4 = (naics or '')[:4]

    # Import here to avoid circular imports at module level
    from classifiers import classify_naics_group, classify_region, classify_size
    from cached_loaders_v5 import CachedLoadersV5, cached_expert_a, cached_expert_b
    from cached_loaders_v2 import cached_method_3b
    from methodologies_v3 import OPTIMAL_DAMPENING_BY_GROUP

    cl = CachedLoadersV5(cur)
    naics_group = classify_naics_group(naics)

    # Fallback path
    def _m3b_fallback(reason=''):
        try:
            result = cached_method_3b(cl, naics4, state_fips, county_fips)
            return {
                'race': result.get('race'),
                'hispanic': result.get('hispanic'),
                'gender': result.get('gender'),
                'metadata': {
                    'expert_used': 'M3b_fallback',
                    'confidence_score': 0.0,
                    'data_source': 'acs_state',
                    'review_flag': True,
                    'review_reasons': [reason or 'fallback'],
                },
            }
        except Exception as e:
            logger.error('M3b fallback failed: %s' % str(e))
            return None

    # If no gate model, use fallback
    if _gate_model is None:
        return _m3b_fallback('no_gate_model')

    try:
        import numpy as np

        # Build features
        region = classify_region('')  # Would need state_abbr
        urbanicity = 'Urban'  # Default
        size_bucket = classify_size(total_employees)
        minority_share = 'Medium (25-50%)'  # Default
        alpha_used = str(OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, 0.50))

        cat_features = [naics_group, region, urbanicity, size_bucket, minority_share]
        X = np.array([cat_features + [alpha_used]])

        # Predict
        pipeline = _gate_model['pipeline']
        expert = pipeline.predict(X)[0]
        probs = pipeline.predict_proba(X)[0]
        class_idx = list(pipeline.named_steps['classifier'].classes_).index(expert)
        confidence = float(probs[class_idx])

    except Exception as e:
        logger.error('Gate prediction failed: %s' % str(e))
        return _m3b_fallback('gate_prediction_error')

    # Run chosen expert
    try:
        if expert == 'A':
            result = cached_expert_a(cl, naics4, state_fips, county_fips)
        elif expert == 'B':
            result = cached_expert_b(cl, naics4, state_fips, county_fips, zipcode=zipcode)
        else:
            result = cached_method_3b(cl, naics4, state_fips, county_fips)
    except Exception as e:
        logger.error('Expert %s failed: %s' % (expert, str(e)))
        return _m3b_fallback('expert_%s_error' % expert)

    # Apply calibration
    race = result.get('race')
    if race:
        race = _apply_calibration(race, expert)

    data_source = result.get('_data_source', 'acs_state')

    # Review flags
    review_reasons = []
    if confidence < 0.45:
        review_reasons.append('low_confidence')
    if data_source == 'acs_state':
        review_reasons.append('no_pums_metro')
    if naics_group in HARD_SEGMENTS:
        review_reasons.append('hard_segment')

    return {
        'race': race,
        'hispanic': result.get('hispanic'),
        'gender': result.get('gender'),
        'metadata': {
            'expert_used': expert,
            'confidence_score': round(confidence, 3),
            'data_source': data_source,
            'review_flag': len(review_reasons) > 0,
            'review_reasons': review_reasons,
        },
    }
