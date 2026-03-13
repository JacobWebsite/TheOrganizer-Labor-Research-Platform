"""Train Gate v0: logistic regression routing model.

Reads gate_training_data.csv, trains a multinomial logistic regression
to predict best_method from company features.

Output: gate_v0.pkl

Usage:
    py scripts/analysis/demographics_comparison/train_v5_gate.py
"""
import sys
import os
import csv
import pickle
import warnings

sys.path.insert(0, os.path.dirname(__file__))

SCRIPT_DIR = os.path.dirname(__file__)


def load_training_data():
    """Load gate_training_data.csv."""
    csv_path = os.path.join(SCRIPT_DIR, 'gate_training_data.csv')
    if not os.path.exists(csv_path):
        print('ERROR: %s not found. Run build_gate_training_data.py first.' % csv_path)
        sys.exit(1)

    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    print('Loaded %d training rows' % len(rows))
    return rows


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
        print('  pip install scikit-learn numpy')
        sys.exit(1)

    print('TRAIN GATE V0')
    print('=' * 60)

    rows = load_training_data()

    # Features
    categorical_features = ['naics_group', 'region', 'urbanicity', 'size_bucket']
    numeric_features = ['county_minority_share', 'acs_lodes_disagreement']
    boolean_features = ['has_tract_data', 'is_finance_insurance', 'is_admin_staffing', 'is_healthcare']

    # Build arrays
    X_cat = []
    X_num = []
    X_bool = []
    y = []
    groups = []

    for row in rows:
        X_cat.append([row.get(f, '') for f in categorical_features])
        X_num.append([
            float(row.get(f, 0) or 0) for f in numeric_features
        ])
        X_bool.append([
            int(row.get(f, 0) or 0) for f in boolean_features
        ])
        y.append(row['best_method'])
        groups.append(row.get('naics_group', 'Other'))

    X_cat = np.array(X_cat)
    X_num = np.array(X_num, dtype=float)
    X_bool = np.array(X_bool, dtype=float)
    y = np.array(y)
    groups = np.array(groups)

    # Handle NaN in numeric features
    for j in range(X_num.shape[1]):
        col = X_num[:, j]
        mask = np.isnan(col)
        if mask.any():
            median_val = np.nanmedian(col)
            col[mask] = median_val

    # Build preprocessor
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False),
             list(range(len(categorical_features)))),
            ('num', StandardScaler(),
             list(range(len(categorical_features),
                        len(categorical_features) + len(numeric_features)))),
            ('bool', 'passthrough',
             list(range(len(categorical_features) + len(numeric_features),
                        len(categorical_features) + len(numeric_features) + len(boolean_features)))),
        ]
    )

    # Combine features using DataFrame to preserve dtypes
    import pandas as pd
    df_cat = pd.DataFrame(X_cat, columns=categorical_features)
    df_num = pd.DataFrame(X_num, columns=numeric_features)
    df_bool = pd.DataFrame(X_bool, columns=boolean_features)
    X_all = pd.concat([df_cat, df_num, df_bool], axis=1)

    # Build pipeline
    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', LogisticRegression(
            C=0.1, max_iter=1000, solver='lbfgs'
        )),
    ])

    # GroupKFold CV grouped by naics_group
    gkf = GroupKFold(n_splits=5)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        cv_scores = cross_val_score(pipeline, X_all, y, cv=gkf, groups=groups, scoring='accuracy')

    print('')
    print('GroupKFold CV (5 splits by naics_group):')
    print('  Per-fold accuracy: %s' % ', '.join('%.3f' % s for s in cv_scores))
    print('  Mean accuracy: %.3f (+/- %.3f)' % (cv_scores.mean(), cv_scores.std()))

    # Train on full data
    pipeline.fit(X_all, y)

    # Feature importance (coefficients)
    clf = pipeline.named_steps['classifier']
    print('')
    print('Classes: %s' % list(clf.classes_))

    # Save model
    model_path = os.path.join(SCRIPT_DIR, 'gate_v0.pkl')
    model_data = {
        'pipeline': pipeline,
        'categorical_features': categorical_features,
        'numeric_features': numeric_features,
        'boolean_features': boolean_features,
        'classes': list(clf.classes_),
        'cv_accuracy': float(cv_scores.mean()),
    }
    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
    print('Saved: %s' % model_path)

    # Per-class accuracy
    y_pred = pipeline.predict(X_all)
    from collections import Counter
    correct = Counter()
    total = Counter()
    for true, pred in zip(y, y_pred):
        total[true] += 1
        if true == pred:
            correct[true] += 1

    print('')
    print('Per-class training accuracy:')
    for cls in sorted(total.keys()):
        acc = 100.0 * correct[cls] / total[cls] if total[cls] > 0 else 0
        print('  %-22s  %d/%d (%.1f%%)' % (cls, correct[cls], total[cls], acc))

    overall_acc = sum(correct.values()) / sum(total.values()) * 100
    print('  Overall: %.1f%%' % overall_acc)


if __name__ == '__main__':
    main()
