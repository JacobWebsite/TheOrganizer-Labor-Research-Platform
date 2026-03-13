"""Train Gate V2: GradientBoosting routing model on expanded training set.

Runs 6 experts (A, B, D, E, F, V6-Full) on each company, determines which
expert is best for race MAE, trains a GradientBoostingClassifier to route.

New features over V1: QCEW LQ, ACS-vs-LODES divergence, tract diversity
(Shannon entropy), PUMS available flag, 4-digit NAICS prefix, lodes_minority_share.

Outputs:
- gate_v2.pkl (model + metadata)
- calibration_v2.json (per-expert, per-category bias corrections)

Usage:
    py scripts/analysis/demographics_comparison/train_gate_v2.py
"""
import sys
import os
import json
import math
import pickle
import time
import warnings
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from eeo1_parser import load_eeo1_data, load_all_eeo1_data, parse_eeo1_row
from data_loaders import zip_to_county
from classifiers import classify_naics_group, classify_region
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_method_v6_full, cached_expert_e, cached_expert_f, cached_expert_g,
)
from cached_loaders_v5 import cached_expert_a, cached_expert_b, cached_method_3c_v5
from cached_loaders_v2 import cached_method_3b
from methodologies_v5 import RACE_CATS
from config import (
    get_census_region, get_county_minority_tier,
    REGIONAL_CALIBRATION_INDUSTRIES, REGIONAL_CAL_MIN_N,
)

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ['Hispanic', 'Not Hispanic']
GENDER_CATS = ['Male', 'Female']

# Map NAICS groups to broader sectors for calibration fallback
NAICS_SECTOR_MAP = {
    'Metal/Machinery Mfg (331-333)': 'manufacturing',
    'Chemical/Material Mfg (325-327)': 'manufacturing',
    'Food/Bev Manufacturing (311,312)': 'manufacturing',
    'Computer/Electrical Mfg (334-335)': 'manufacturing',
    'Transport Equip Mfg (336)': 'manufacturing',
    'Other Manufacturing': 'manufacturing',
    'Professional/Technical (54)': 'services',
    'Finance/Insurance (52)': 'services',
    'Information (51)': 'services',
    'Admin/Staffing (56)': 'services',
    'Wholesale Trade (42)': 'services',
    'Healthcare/Social (62)': 'healthcare',
    'Retail Trade (44-45)': 'retail_food',
    'Accommodation/Food Svc (72)': 'retail_food',
    'Transportation/Warehousing (48-49)': 'infrastructure',
    'Utilities (22)': 'infrastructure',
    'Construction (23)': 'infrastructure',
    'Agriculture/Mining (11,21)': 'other',
    'Other': 'other',
}

DAMPENING = 0.80  # How much of the measured bias to correct

# Expert roster for Gate V2
EXPERTS = {
    'A': lambda cl, n4, sf, cf, **kw: cached_expert_a(cl, n4, sf, cf),
    'B': lambda cl, n4, sf, cf, **kw: cached_expert_b(cl, n4, sf, cf),
    'D': lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    'E': lambda cl, n4, sf, cf, **kw: cached_expert_e(cl, n4, sf, cf, **kw),
    'F': lambda cl, n4, sf, cf, **kw: cached_expert_f(cl, n4, sf, cf, **kw),
    'G': lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    'V6': lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}


def compute_race_mae(pred, actual, cats):
    """Compute mean absolute error for race categories."""
    if not pred or not actual:
        return None
    errors = []
    for cat in cats:
        if cat in pred and cat in actual:
            errors.append(abs(pred[cat] - actual[cat]))
    return sum(errors) / len(errors) if errors else None


def compute_shannon_entropy(race_dict, cats):
    """Compute Shannon entropy of a race distribution (diversity measure)."""
    if not race_dict:
        return 0.0
    total = sum(race_dict.get(c, 0) for c in cats)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for c in cats:
        p = race_dict.get(c, 0) / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def main():
    try:
        import numpy as np
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import GroupKFold, cross_val_score
    except ImportError:
        print('ERROR: scikit-learn and numpy required.')
        sys.exit(1)

    t0 = time.time()
    print('TRAIN GATE V2')
    print('=' * 60)

    # Load expanded training set
    training_path = os.path.join(SCRIPT_DIR, 'expanded_training_v6.json')
    with open(training_path, 'r', encoding='utf-8') as f:
        training_companies = json.load(f)
    print('Training companies: %d' % len(training_companies))

    # Load EEO-1 ground truth
    print('Loading all EEO-1 files...')
    eeo1_rows = load_all_eeo1_data()
    eeo1_by_code = {}
    for row in eeo1_rows:
        code = (row.get('COMPANY') or '').strip()
        if code:
            eeo1_by_code.setdefault(code, []).append(row)
    print('EEO-1 codes: %d' % len(eeo1_by_code))

    # Connect
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Run all experts on each company, collect MAEs
    X_cat = []
    X_num = []
    y = []
    groups = []
    expert_wins = defaultdict(int)
    expert_signed_errors = {e: defaultdict(list) for e in EXPERTS}
    expert_hisp_errors = {e: defaultdict(list) for e in EXPERTS}
    expert_gender_errors = {e: defaultdict(list) for e in EXPERTS}
    # Per-segment error tracking for segment-level calibration
    expert_segment_race_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    expert_segment_hisp_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    expert_segment_gender_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    # V8: Regional/county-tier sub-segment error tracking
    expert_regional_race_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    expert_regional_hisp_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    expert_regional_gender_errors = {e: defaultdict(lambda: defaultdict(list)) for e in EXPERTS}
    # V8: NAICS4 frequency counter for vocabulary
    naics4_counter = defaultdict(int)
    naics4_codes_for_training = []  # tracks NAICS4 for each training row
    skipped = 0

    for i, company in enumerate(training_companies):
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            print('  %d/%d (%.0fs)...' % (i + 1, len(training_companies), elapsed))

        code = company['company_code']
        naics = company.get('naics', '')
        naics4 = naics[:4]
        state_fips = company.get('state_fips', '')
        county_fips = company.get('county_fips', '')
        zipcode = company.get('zipcode', '')

        if not county_fips or not state_fips:
            skipped += 1
            continue

        # Ground truth
        eeo1_list = eeo1_by_code.get(code, [])
        if not eeo1_list:
            skipped += 1
            continue
        truth = parse_eeo1_row(eeo1_list[0])
        if not truth or not truth.get('race'):
            skipped += 1
            continue

        actual_race = truth['race']
        actual_hisp = truth.get('hispanic')
        actual_gender = truth.get('gender')

        # Classify early so segment errors can be tracked
        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', classify_naics_group(naics4))

        # V8: Track region and county minority tier for regional calibration
        state_abbr = company.get('state', '')
        region_name = get_census_region(state_abbr)
        lodes_race_cal = cl.get_lodes_race(county_fips)
        county_minority_pct = None
        if lodes_race_cal:
            county_minority_pct = 100.0 - lodes_race_cal.get('White', 0)
        county_tier = get_county_minority_tier(county_minority_pct)

        # V8: Build regional/county-tier sub-keys for this company
        regional_sub_keys = []
        if naics_group in REGIONAL_CALIBRATION_INDUSTRIES:
            regional_sub_keys.append('%s|region:%s' % (naics_group, region_name))
            regional_sub_keys.append('%s|county_tier:%s' % (naics_group, county_tier))

        # V8: Count NAICS4 frequency
        naics4_code = naics[:4] if naics else ''
        naics4_counter[naics4_code] += 1

        # CBSA lookup
        cbsa_code = cl.get_county_cbsa(county_fips) or ''

        # Run each expert
        expert_maes = {}
        expert_results = {}
        for exp_name, exp_fn in EXPERTS.items():
            try:
                result = exp_fn(cl, naics4, state_fips, county_fips,
                                cbsa_code=cbsa_code, zipcode=zipcode,
                                naics_group=naics_group)
            except Exception:
                result = None

            if result and result.get('race'):
                race_mae = compute_race_mae(result['race'], actual_race, RACE_CATS)
                if race_mae is not None:
                    expert_maes[exp_name] = race_mae
                    expert_results[exp_name] = result

                    # Collect signed errors for calibration (global + segment)
                    for cat in RACE_CATS:
                        if cat in result['race'] and cat in actual_race:
                            err = result['race'][cat] - actual_race[cat]
                            expert_signed_errors[exp_name][cat].append(err)
                            expert_segment_race_errors[exp_name][naics_group][cat].append(err)
                            # V8: regional/county-tier sub-segment errors
                            for sub_key in regional_sub_keys:
                                expert_regional_race_errors[exp_name][sub_key][cat].append(err)

                    # Hispanic errors
                    if result.get('hispanic') and actual_hisp:
                        for cat in HISP_CATS:
                            if cat in result['hispanic'] and cat in actual_hisp:
                                err = result['hispanic'][cat] - actual_hisp[cat]
                                expert_hisp_errors[exp_name][cat].append(err)
                                expert_segment_hisp_errors[exp_name][naics_group][cat].append(err)
                                for sub_key in regional_sub_keys:
                                    expert_regional_hisp_errors[exp_name][sub_key][cat].append(err)

                    # Gender errors
                    if result.get('gender') and actual_gender:
                        for cat in GENDER_CATS:
                            if cat in result['gender'] and cat in actual_gender:
                                err = result['gender'][cat] - actual_gender[cat]
                                expert_gender_errors[exp_name][cat].append(err)
                                expert_segment_gender_errors[exp_name][naics_group][cat].append(err)
                                for sub_key in regional_sub_keys:
                                    expert_regional_gender_errors[exp_name][sub_key][cat].append(err)

        if not expert_maes:
            skipped += 1
            continue

        best_expert = min(expert_maes.keys(), key=lambda e: expert_maes[e])
        expert_wins[best_expert] += 1
        y.append(best_expert)

        # Build features (naics_group already computed above)
        region = cls.get('region', classify_region(company.get('state', '')))
        size_bucket = cls.get('size', '100-999')

        # LODES minority share
        lodes_race = cl.get_lodes_race(county_fips)
        if lodes_race:
            lodes_white = lodes_race.get('White', 0)
            lodes_minority_pct = 100.0 - lodes_white
            if lodes_minority_pct < 25:
                lodes_minority_share = 'Low (<25%)'
            elif lodes_minority_pct <= 50:
                lodes_minority_share = 'Medium (25-50%)'
            else:
                lodes_minority_share = 'High (>50%)'
        else:
            lodes_minority_share = 'Medium (25-50%)'

        # Categorical features
        naics_2 = naics4[:2] if naics4 else '99'
        X_cat.append([naics_group, region, size_bucket, lodes_minority_share, naics_2])

        # Numeric features
        # 1. QCEW LQ + avg pay
        naics_2d_qcew = naics4[:2] if naics4 else None
        qcew_data = cl.get_qcew_concentration(county_fips, naics_2d_qcew)
        qcew_lq_val = float(qcew_data['location_quotient']) if qcew_data else 1.0
        raw_pay = qcew_data['avg_annual_pay'] if qcew_data and qcew_data['avg_annual_pay'] else 50000
        qcew_pay_val = math.log(max(raw_pay, 1000))

        # 2. ACS-vs-LODES White divergence
        acs_race = cl.get_acs_race(naics4, state_fips)
        acs_white = acs_race.get('White', 0) if acs_race else 0
        lodes_white_val = lodes_race.get('White', 0) if lodes_race else 0
        acs_lodes_div = abs(acs_white - lodes_white_val)

        # 3. Tract diversity (Shannon entropy)
        tract_fips = cl.get_zip_to_best_tract(zipcode)
        tract_race = cl.get_lodes_tract_race(tract_fips) if tract_fips else None
        tract_entropy = compute_shannon_entropy(tract_race, RACE_CATS)

        # 4. PUMS available flag
        naics_2d = naics4[:2] if naics4 else None
        pums_race = cl.get_pums_race(cbsa_code, naics_2d) if cbsa_code else None
        has_pums = 1.0 if pums_race is not None else 0.0

        # 5. Has tract data
        has_tract = 1.0 if tract_race is not None else 0.0

        # 6. Occupation data available
        occ_mix = cl.get_occupation_mix(naics4)
        has_occ = 1.0 if occ_mix else 0.0

        # V8 new numeric features
        # naics4_encoded (placeholder -- will be mapped after vocab is built)
        naics4_code_feat = naics[:4] if naics else ''

        # ABS minority owner share
        abs_data = cl.get_abs_owner_density(county_fips)
        abs_minority_share = abs_data['minority_share'] if abs_data else -1.0

        # Transit score
        transit_data = cl.get_transit_score(zipcode) if zipcode else None
        transit_score_val = transit_data['transit_score'] if transit_data else -1.0

        X_num.append([qcew_lq_val, qcew_pay_val, acs_lodes_div, tract_entropy,
                      has_pums, has_tract, has_occ,
                      0,  # naics4_encoded placeholder -- filled after vocab built
                      abs_minority_share, transit_score_val])

        naics4_codes_for_training.append(naics4_code_feat)
        groups.append(naics_group)

    elapsed = time.time() - t0
    print('')
    print('Processed %d companies in %.0fs (%d skipped)' % (len(y), elapsed, skipped))
    print('Expert wins: %s' % dict(expert_wins))

    if len(y) < 100:
        print('ERROR: Too few training samples (%d). Aborting.' % len(y))
        conn.close()
        return

    # V8: Build NAICS4 vocabulary (top 50 most frequent -> integer indices)
    sorted_naics4 = sorted(naics4_counter.items(), key=lambda x: -x[1])
    naics4_vocab = {}
    for idx, (code, count) in enumerate(sorted_naics4[:50], start=1):
        naics4_vocab[code] = idx
    print('NAICS4 vocab: %d codes (top 50 of %d unique)' % (
        len(naics4_vocab), len(naics4_counter)))
    print('  Top 10: %s' % ', '.join(
        '%s(%d)' % (code, count) for code, count in sorted_naics4[:10]))

    # Save NAICS4 vocab
    naics4_vocab_path = os.path.join(SCRIPT_DIR, 'naics4_vocab.pkl')
    with open(naics4_vocab_path, 'wb') as f:
        pickle.dump(naics4_vocab, f)
    print('Saved: %s' % naics4_vocab_path)

    # Fill in naics4_encoded placeholders in X_num
    # Need to reconstruct naics4 codes from training companies
    # (they were tracked in order via the loop)
    training_naics4_codes = []
    idx_in_training = 0
    for i, company in enumerate(training_companies):
        code = company['company_code']
        naics = company.get('naics', '')
        county_fips = company.get('county_fips', '')
        state_fips = company.get('state_fips', '')
        if not county_fips or not state_fips:
            continue
        eeo1_list = eeo1_by_code.get(code, [])
        if not eeo1_list:
            continue
        truth = parse_eeo1_row(eeo1_list[0])
        if not truth or not truth.get('race'):
            continue
        # This company was processed -- check if it had expert results
        # We can't perfectly reconstruct, but we tracked naics4_counter in order
        # Instead, store naics4 codes during the loop. We'll fix this by
        # re-deriving from the company data.
        training_naics4_codes.append(naics[:4] if naics else '')

    X_cat = np.array(X_cat)
    X_num = np.array(X_num, dtype=float)

    # Fill in naics4_encoded (column index 7) from vocab
    for row_idx, naics4_code in enumerate(naics4_codes_for_training):
        X_num[row_idx, 7] = naics4_vocab.get(naics4_code, 0)

    y = np.array(y)
    groups = np.array(groups)

    cat_feature_names = ['naics_group', 'region', 'size_bucket',
                         'lodes_minority_share', 'naics_2']
    num_feature_names = ['qcew_lq', 'qcew_avg_pay_log', 'acs_lodes_divergence',
                         'tract_entropy', 'has_pums', 'has_tract', 'has_occ',
                         'naics4_encoded', 'abs_minority_owner_share',
                         'transit_score']

    # Build pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False),
             list(range(len(cat_feature_names)))),
            ('num', StandardScaler(),
             list(range(len(cat_feature_names),
                        len(cat_feature_names) + len(num_feature_names)))),
        ]
    )

    X_all = np.hstack([X_cat, X_num.astype(str)])

    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42,
        )),
    ])

    # GroupKFold CV
    gkf = GroupKFold(n_splits=5)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        cv_scores = cross_val_score(pipeline, X_all, y, cv=gkf,
                                    groups=groups, scoring='accuracy')

    print('')
    print('GroupKFold CV (5 splits):')
    print('  Per-fold: %s' % ', '.join('%.3f' % s for s in cv_scores))
    print('  Mean: %.3f (+/- %.3f)' % (cv_scores.mean(), cv_scores.std()))

    # Train on all data
    pipeline.fit(X_all, y)

    # Feature importances
    clf = pipeline.named_steps['classifier']
    ohe = pipeline.named_steps['preprocessor'].named_transformers_['cat']
    cat_names_expanded = list(ohe.get_feature_names_out(cat_feature_names))
    all_feature_names = cat_names_expanded + num_feature_names
    importances = clf.feature_importances_

    print('')
    print('Top 15 feature importances:')
    sorted_idx = np.argsort(importances)[::-1]
    for rank, idx in enumerate(sorted_idx[:15], 1):
        if idx < len(all_feature_names):
            print('  %2d. %-40s %.4f' % (rank, all_feature_names[idx], importances[idx]))

    # Save model
    model_path = os.path.join(SCRIPT_DIR, 'gate_v2.pkl')
    model_data = {
        'pipeline': pipeline,
        'categorical_features': cat_feature_names,
        'numeric_features': num_feature_names,
        'classes': list(clf.classes_),
        'cv_accuracy': float(cv_scores.mean()),
        'n_training': len(y),
        'naics4_vocab': naics4_vocab,
    }
    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
    print('Saved: %s' % model_path)

    # Compute per-segment calibration: bias at NAICS-group level with
    # sector-level fallback (>= 20 examples) and global fallback
    calibration = {}
    all_dims = list(RACE_CATS) + list(HISP_CATS) + list(GENDER_CATS)

    # Collect all unique NAICS groups seen
    all_naics_groups = set()
    for expert in EXPERTS:
        all_naics_groups.update(expert_segment_race_errors[expert].keys())

    for expert in EXPERTS:
        calibration[expert] = {}

        # Global corrections
        calibration[expert]['_global'] = {'race': {}, 'hispanic': {}, 'gender': {}}
        for cat in RACE_CATS:
            errors = expert_signed_errors[expert].get(cat, [])
            global_bias = sum(errors) / len(errors) if errors else 0.0
            calibration[expert]['_global']['race'][cat] = {
                'correction': round(-global_bias * DAMPENING, 4),
                'n': len(errors),
            }
        for cat in HISP_CATS:
            errors = expert_hisp_errors[expert].get(cat, [])
            global_bias = sum(errors) / len(errors) if errors else 0.0
            calibration[expert]['_global']['hispanic'][cat] = {
                'correction': round(-global_bias * DAMPENING, 4),
                'n': len(errors),
            }
        for cat in GENDER_CATS:
            errors = expert_gender_errors[expert].get(cat, [])
            global_bias = sum(errors) / len(errors) if errors else 0.0
            calibration[expert]['_global']['gender'][cat] = {
                'correction': round(-global_bias * DAMPENING, 4),
                'n': len(errors),
            }

        # Per-NAICS-group corrections with sector fallback
        for ng in all_naics_groups:
            calibration[expert][ng] = {'race': {}, 'hispanic': {}, 'gender': {}}
            sector = NAICS_SECTOR_MAP.get(ng, 'other')

            for cat in RACE_CATS:
                seg_errors = expert_segment_race_errors[expert].get(ng, {}).get(cat, [])
                if len(seg_errors) >= 50:
                    seg_bias = sum(seg_errors) / len(seg_errors)
                    used_fallback = False
                elif len(seg_errors) >= 20:
                    # Use broader sector grouping
                    sector_errors = []
                    for ng2, sec2 in NAICS_SECTOR_MAP.items():
                        if sec2 == sector:
                            sector_errors.extend(
                                expert_segment_race_errors[expert].get(ng2, {}).get(cat, []))
                    seg_bias = sum(sector_errors) / len(sector_errors) if sector_errors else 0.0
                    used_fallback = True
                else:
                    # Fall back to global
                    global_errors = expert_signed_errors[expert].get(cat, [])
                    seg_bias = sum(global_errors) / len(global_errors) if global_errors else 0.0
                    used_fallback = True
                calibration[expert][ng]['race'][cat] = {
                    'correction': round(-seg_bias * DAMPENING, 4),
                    'n': len(seg_errors),
                    'used_fallback': used_fallback if len(seg_errors) < 50 else False,
                }

            for cat in HISP_CATS:
                seg_errors = expert_segment_hisp_errors[expert].get(ng, {}).get(cat, [])
                if len(seg_errors) >= 50:
                    seg_bias = sum(seg_errors) / len(seg_errors)
                elif len(seg_errors) >= 20:
                    sector_errors = []
                    for ng2, sec2 in NAICS_SECTOR_MAP.items():
                        if sec2 == sector:
                            sector_errors.extend(
                                expert_segment_hisp_errors[expert].get(ng2, {}).get(cat, []))
                    seg_bias = sum(sector_errors) / len(sector_errors) if sector_errors else 0.0
                else:
                    global_errors = expert_hisp_errors[expert].get(cat, [])
                    seg_bias = sum(global_errors) / len(global_errors) if global_errors else 0.0
                calibration[expert][ng]['hispanic'][cat] = {
                    'correction': round(-seg_bias * DAMPENING, 4),
                    'n': len(seg_errors),
                }

            for cat in GENDER_CATS:
                seg_errors = expert_segment_gender_errors[expert].get(ng, {}).get(cat, [])
                if len(seg_errors) >= 50:
                    seg_bias = sum(seg_errors) / len(seg_errors)
                elif len(seg_errors) >= 20:
                    sector_errors = []
                    for ng2, sec2 in NAICS_SECTOR_MAP.items():
                        if sec2 == sector:
                            sector_errors.extend(
                                expert_segment_gender_errors[expert].get(ng2, {}).get(cat, []))
                    seg_bias = sum(sector_errors) / len(sector_errors) if sector_errors else 0.0
                else:
                    global_errors = expert_gender_errors[expert].get(cat, [])
                    seg_bias = sum(global_errors) / len(global_errors) if global_errors else 0.0
                calibration[expert][ng]['gender'][cat] = {
                    'correction': round(-seg_bias * DAMPENING, 4),
                    'n': len(seg_errors),
                }

        # V8: Regional/county-tier sub-segment calibration
        all_regional_keys = set()
        all_regional_keys.update(expert_regional_race_errors[expert].keys())
        for sub_key in all_regional_keys:
            calibration[expert][sub_key] = {'race': {}, 'hispanic': {}, 'gender': {}}

            for cat in RACE_CATS:
                sub_errors = expert_regional_race_errors[expert].get(sub_key, {}).get(cat, [])
                if len(sub_errors) >= REGIONAL_CAL_MIN_N:
                    sub_bias = sum(sub_errors) / len(sub_errors)
                    calibration[expert][sub_key]['race'][cat] = {
                        'correction': round(-sub_bias * DAMPENING, 4),
                        'n': len(sub_errors),
                    }

            for cat in HISP_CATS:
                sub_errors = expert_regional_hisp_errors[expert].get(sub_key, {}).get(cat, [])
                if len(sub_errors) >= REGIONAL_CAL_MIN_N:
                    sub_bias = sum(sub_errors) / len(sub_errors)
                    calibration[expert][sub_key]['hispanic'][cat] = {
                        'correction': round(-sub_bias * DAMPENING, 4),
                        'n': len(sub_errors),
                    }

            for cat in GENDER_CATS:
                sub_errors = expert_regional_gender_errors[expert].get(sub_key, {}).get(cat, [])
                if len(sub_errors) >= REGIONAL_CAL_MIN_N:
                    sub_bias = sum(sub_errors) / len(sub_errors)
                    calibration[expert][sub_key]['gender'][cat] = {
                        'correction': round(-sub_bias * DAMPENING, 4),
                        'n': len(sub_errors),
                    }

    # Report regional calibration stats
    regional_key_count = 0
    regional_with_data = 0
    for expert in EXPERTS:
        for key in calibration[expert]:
            if '|' in str(key):
                regional_key_count += 1
                race_cal = calibration[expert][key].get('race', {})
                if any(isinstance(v, dict) and v.get('n', 0) >= REGIONAL_CAL_MIN_N
                       for v in race_cal.values()):
                    regional_with_data += 1
    print('')
    print('V8 Regional calibration: %d sub-keys, %d with sufficient data (N>=%d)' % (
        regional_key_count, regional_with_data, REGIONAL_CAL_MIN_N))

    cal_path = os.path.join(SCRIPT_DIR, 'calibration_v2.json')
    with open(cal_path, 'w', encoding='utf-8') as f:
        json.dump(calibration, f, indent=2)
    print('Saved: %s' % cal_path)

    print('')
    print('Race calibration (global mean signed bias):')
    for expert in sorted(EXPERTS.keys()):
        biases = calibration[expert]['_global']['race']
        print('  Expert %s: %s' % (expert, ', '.join(
            '%s=%.2f' % (k, v['correction']) for k, v in biases.items())))

    # Show sample segment-level calibration
    print('')
    print('Sample segment calibration (Asian correction by NAICS group, Expert V6):')
    v6_cal = calibration.get('V6', {})
    for ng in sorted(all_naics_groups):
        ng_cal = v6_cal.get(ng, {}).get('race', {}).get('Asian', {})
        if ng_cal:
            print('  %-45s corr=%.2f  n=%d  fallback=%s' % (
                ng, ng_cal.get('correction', 0), ng_cal.get('n', 0),
                ng_cal.get('used_fallback', '')))

    # V8: Show regional calibration for Healthcare and Admin/Staffing
    print('')
    print('V8 Regional calibration (White correction, Expert V6):')
    for key in sorted(v6_cal.keys()):
        if '|' in str(key):
            white_cal = v6_cal[key].get('race', {}).get('White', {})
            if white_cal and white_cal.get('n', 0) >= REGIONAL_CAL_MIN_N:
                print('  %-55s corr=%+.2f  n=%d' % (
                    key, white_cal.get('correction', 0), white_cal.get('n', 0)))

    total_elapsed = time.time() - t0
    print('')
    print('Done in %.0fs.' % total_elapsed)
    cl.print_stats()
    conn.close()


if __name__ == '__main__':
    main()
