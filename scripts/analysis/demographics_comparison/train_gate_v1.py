"""Train Gate v1: routing model using OOF predictions from 3 experts.

Reads oof_predictions_v5.csv, trains a logistic regression to route
companies to Expert A, B, or D.

Outputs:
- gate_v1.pkl (model)
- calibration_v1.json (per-expert, per-category bias corrections)

Usage:
    py scripts/analysis/demographics_comparison/train_gate_v1.py
"""
import sys
import os
import csv
import json
import pickle
import warnings
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
sys.path.insert(0, os.path.dirname(__file__))
from classifiers import classify_naics_group, classify_region

SCRIPT_DIR = os.path.dirname(__file__)
RACE_CATS = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']


def load_oof_data():
    """Load oof_predictions_v5.csv."""
    csv_path = os.path.join(SCRIPT_DIR, 'oof_predictions_v5.csv')
    if not os.path.exists(csv_path):
        print('ERROR: %s not found. Run generate_oof_predictions_v5.py first.' % csv_path)
        sys.exit(1)

    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print('Loaded %d OOF rows' % len(rows))
    return rows


def load_companies():
    """Load all_companies_v4.json for features."""
    json_path = os.path.join(SCRIPT_DIR, 'all_companies_v4.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        companies = json.load(f)
    return {c['company_code']: c for c in companies}


def load_gate_training_lodes():
    """Load gate_training_data.csv for LODES-based minority share per company.

    Returns dict: company_code -> lodes_minority_share category string.
    This avoids the ground truth leak from using EEO-1 derived minority_share.
    """
    csv_path = os.path.join(SCRIPT_DIR, 'gate_training_data.csv')
    lookup = {}
    if not os.path.exists(csv_path):
        print('WARNING: gate_training_data.csv not found, using defaults for lodes_minority_share')
        return lookup
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get('company_code', '')
            lms = row.get('lodes_minority_share', '')
            if code and lms:
                lookup[code] = lms
    print('Loaded LODES minority share for %d companies from gate_training_data.csv' % len(lookup))
    return lookup


def compute_expert_mae(row, expert_prefix):
    """Compute race MAE for one expert on one company."""
    errors = []
    for cat in RACE_CATS:
        pred_key = '%s%s' % (expert_prefix, cat)
        actual_key = 'actual_%s' % cat
        p = row.get(pred_key)
        a = row.get(actual_key)
        if p is not None and a is not None and p != '' and a != '':
            errors.append(abs(float(p) - float(a)))
    if errors:
        return sum(errors) / len(errors)
    return None


def main():
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import GroupKFold, cross_val_score
    except ImportError:
        print('ERROR: scikit-learn and numpy required.')
        sys.exit(1)

    print('TRAIN GATE V1')
    print('=' * 60)

    oof_rows = load_oof_data()
    companies = load_companies()
    lodes_minority_lookup = load_gate_training_lodes()

    # Determine best expert per company and build features
    X_cat = []
    X_num = []
    y = []
    groups = []

    expert_wins = defaultdict(int)
    expert_signed_errors = {'A': defaultdict(list), 'B': defaultdict(list), 'D': defaultdict(list)}

    for row in oof_rows:
        code = row['company_code']
        company = companies.get(code)
        if not company:
            continue

        # Compute MAE for each expert
        mae_a = compute_expert_mae(row, 'expert_a_')
        mae_b = compute_expert_mae(row, 'expert_b_')
        mae_d = compute_expert_mae(row, 'expert_d_')

        expert_maes = {}
        if mae_a is not None:
            expert_maes['A'] = mae_a
        if mae_b is not None:
            expert_maes['B'] = mae_b
        if mae_d is not None:
            expert_maes['D'] = mae_d

        if not expert_maes:
            continue

        best_expert = min(expert_maes.keys(), key=lambda e: expert_maes[e])
        expert_wins[best_expert] += 1
        y.append(best_expert)

        # Collect signed errors for calibration
        for expert, prefix in [('A', 'expert_a_'), ('B', 'expert_b_'), ('D', 'expert_d_')]:
            for cat in RACE_CATS:
                p = row.get('%s%s' % (prefix, cat))
                a = row.get('actual_%s' % cat)
                if p is not None and a is not None and p != '' and a != '':
                    expert_signed_errors[expert][cat].append(float(p) - float(a))

        # Features
        cls = company.get('classifications', {})
        naics_group = cls.get('naics_group', 'Other')
        region = cls.get('region', 'Other')
        urbanicity = cls.get('urbanicity', 'Rural')
        size_bucket = cls.get('size', '100-999')
        # Use LODES-derived minority share instead of EEO-1 ground truth
        lodes_minority_share = lodes_minority_lookup.get(code, 'Medium (25-50%)')

        X_cat.append([naics_group, region, urbanicity, size_bucket, lodes_minority_share])

        # Numeric: alpha_used from OOF
        alpha = float(row.get('alpha_used', 0.50) or 0.50)
        X_num.append([alpha])

        groups.append(naics_group)

    print('Training samples: %d' % len(y))
    print('Expert wins: %s' % dict(expert_wins))

    X_cat = np.array(X_cat)
    X_num = np.array(X_num, dtype=float)
    y = np.array(y)
    groups = np.array(groups)

    # Build pipeline
    categorical_features = ['naics_group', 'region', 'urbanicity', 'size_bucket', 'lodes_minority_share']
    numeric_features = ['alpha_used']

    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False),
             list(range(len(categorical_features)))),
            ('num', StandardScaler(),
             list(range(len(categorical_features),
                        len(categorical_features) + len(numeric_features)))),
        ]
    )

    X_all = np.hstack([X_cat, X_num.astype(str)])

    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', LogisticRegression(
            C=0.1, max_iter=1000, solver='lbfgs'
        )),
    ])

    # GroupKFold CV
    gkf = GroupKFold(n_splits=5)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        cv_scores = cross_val_score(pipeline, X_all, y, cv=gkf, groups=groups, scoring='accuracy')

    print('')
    print('GroupKFold CV (5 splits):')
    print('  Per-fold: %s' % ', '.join('%.3f' % s for s in cv_scores))
    print('  Mean: %.3f (+/- %.3f)' % (cv_scores.mean(), cv_scores.std()))

    # Train on all data
    pipeline.fit(X_all, y)

    # Save model
    model_path = os.path.join(SCRIPT_DIR, 'gate_v1.pkl')
    model_data = {
        'pipeline': pipeline,
        'categorical_features': categorical_features,
        'numeric_features': numeric_features,
        'classes': list(pipeline.named_steps['classifier'].classes_),
        'cv_accuracy': float(cv_scores.mean()),
    }
    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
    print('Saved: %s' % model_path)

    # Compute calibration: mean signed error per expert per category
    calibration = {}
    for expert in ['A', 'B', 'D']:
        calibration[expert] = {}
        for cat in RACE_CATS:
            errors = expert_signed_errors[expert].get(cat, [])
            if errors:
                calibration[expert][cat] = round(sum(errors) / len(errors), 4)
            else:
                calibration[expert][cat] = 0.0

    cal_path = os.path.join(SCRIPT_DIR, 'calibration_v1.json')
    with open(cal_path, 'w', encoding='utf-8') as f:
        json.dump(calibration, f, indent=2)
    print('Saved: %s' % cal_path)

    print('')
    print('Calibration (mean signed bias):')
    for expert in ['A', 'B', 'D']:
        biases = calibration[expert]
        print('  Expert %s: %s' % (expert, ', '.join(
            '%s=%.2f' % (k, v) for k, v in biases.items())))

    conn = None  # No DB needed
    print('')
    print('Done.')


if __name__ == '__main__':
    main()
