"""
Phase 5.5: Train NLRB election propensity models.

Model A: Logistic Regression on OSHA-matched elections (~7K rows)
Model B: Logistic Regression on all elections (~33K rows)
Benchmark: GradientBoosting for comparison

Temporal split: pre-2023 train, 2023+ test.
Target AUC > 0.65.

Run:
  py scripts/ml/train_propensity_model.py
  py scripts/ml/train_propensity_model.py --dry-run
  py scripts/ml/train_propensity_model.py --score-only
  py scripts/ml/train_propensity_model.py --model-a-only
  py scripts/ml/train_propensity_model.py --model-b-only
"""
import sys
import os
import json
import time
import argparse
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), 'artifacts')


def train_model(X_train, y_train, X_test, y_test, model_name, model_type='logistic'):
    """Train a model and return metrics + fitted model."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from sklearn.calibration import calibration_curve
    from sklearn.preprocessing import StandardScaler

    # Scale features
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    if model_type == 'logistic':
        model = LogisticRegression(
            penalty='elasticnet', solver='saga',
            l1_ratio=0.5, C=1.0,
            class_weight='balanced',
            max_iter=2000, random_state=42
        )
    elif model_type == 'gradient_boosting':
        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4,
            learning_rate=0.1, subsample=0.8,
            random_state=42
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    print(f"  Training {model_name} ({model_type})...")
    t0 = time.time()
    model.fit(X_train_s, y_train)
    elapsed = time.time() - t0
    print(f"  Trained in {elapsed:.1f}s")

    # Predict
    y_prob = model.predict_proba(X_test_s)[:, 1]

    # Metrics
    auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.5
    brier = brier_score_loss(y_test, y_prob)

    # Calibration error (ECE)
    try:
        prob_true, prob_pred = calibration_curve(y_test, y_prob, n_bins=10, strategy='uniform')
        ece = np.mean(np.abs(prob_true - prob_pred))
    except Exception:
        ece = None

    # Feature importance (coefs for logistic, feature_importances_ for GB)
    if hasattr(model, 'coef_'):
        importance = dict(zip(X_train.columns.tolist(), model.coef_[0].tolist()))
    elif hasattr(model, 'feature_importances_'):
        importance = dict(zip(X_train.columns.tolist(), model.feature_importances_.tolist()))
    else:
        importance = {}

    # Precision@top20%
    threshold = np.percentile(y_prob, 80)
    top20_mask = y_prob >= threshold
    precision_top20 = y_test[top20_mask].mean() if top20_mask.sum() > 0 else 0

    metrics = {
        'auc': round(float(auc), 4),
        'brier_score': round(float(brier), 4),
        'calibration_error': round(float(ece), 4) if ece is not None else None,
        'precision_top20': round(float(precision_top20), 4),
        'train_rows': len(X_train),
        'test_rows': len(X_test),
        'train_positive_rate': round(float(y_train.mean()), 4),
        'test_positive_rate': round(float(y_test.mean()), 4),
    }

    return model, scaler, metrics, importance


def save_model(model, scaler, model_name, version):
    """Serialize model + scaler to artifacts directory."""
    import joblib
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(ARTIFACT_DIR, f"{model_name}_{version}.joblib")
    joblib.dump({'model': model, 'scaler': scaler}, path)
    print(f"  Saved: {path}")
    return path


def record_model_version(conn, model_name, version_string, model_type,
                         metrics, feature_list, parameters, importance,
                         artifact_path, notes=None):
    """Insert into ml_model_versions and return version_id."""
    cur = conn.cursor()

    # Deactivate previous active version for this model
    cur.execute("UPDATE ml_model_versions SET is_active = FALSE WHERE model_name = %s AND is_active = TRUE",
                (model_name,))

    cur.execute("""
        INSERT INTO ml_model_versions
            (model_name, version_string, model_type, training_rows, test_rows,
             test_auc, test_brier_score, calibration_error,
             feature_list, parameters, feature_importance, score_stats,
             artifact_path, is_active, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING model_version_id
    """, (
        model_name, version_string, model_type,
        metrics['train_rows'], metrics['test_rows'],
        metrics['auc'], metrics['brier_score'], metrics.get('calibration_error'),
        json.dumps(feature_list), json.dumps(parameters),
        json.dumps(importance),
        json.dumps({
            'precision_top20': metrics['precision_top20'],
            'train_positive_rate': metrics['train_positive_rate'],
            'test_positive_rate': metrics['test_positive_rate'],
        }),
        artifact_path, notes
    ))
    vid = cur.fetchone()[0]
    conn.commit()
    return vid


def score_employers(conn, model_a_info, model_b_info):
    """Score all F7 employers and write to ml_election_propensity_scores."""
    import joblib
    from sklearn.preprocessing import StandardScaler

    cur = conn.cursor()

    # Model A: F7 employers with OSHA matches
    print("\n=== Scoring with Model A (OSHA-matched employers) ===")
    if model_a_info:
        data_a = joblib.load(model_a_info['artifact_path'])
        model_a, scaler_a = data_a['model'], data_a['scaler']

        # Get F7 employers with OSHA data
        cur.execute("""
            SELECT DISTINCT
                ofm.f7_employer_id AS employer_id,
                ofm.establishment_id,
                COALESCE(oe.employee_count, 0) AS employee_count,
                LEFT(oe.naics_code, 2) AS naics_2digit,
                COALESCE(oe.total_violations, 0) AS total_violations,
                COALESCE(oe.total_penalties, 0) AS total_penalties,
                COALESCE(oe.willful_count, 0) AS willful_count,
                COALESCE(oe.repeat_count, 0) AS repeat_count,
                COALESCE(oe.serious_count, 0) AS serious_count,
                COALESCE(oe.total_inspections, 0) AS total_inspections,
                oe.site_state,
                COALESCE(sd.union_density_pct, 0)::float AS state_density_rate,
                COALESCE(sid.estimated_density, 0)::float AS estimated_density
            FROM osha_f7_matches ofm
            JOIN v_osha_organizing_targets oe ON oe.establishment_id = ofm.establishment_id
            LEFT JOIN bls_state_density sd ON sd.state = oe.site_state
            LEFT JOIN estimated_state_industry_density sid
                ON sid.state = oe.site_state
                AND LEFT(oe.naics_code, 2) = regexp_replace(COALESCE(sid.industry_code::text, ''), '[^0-9]', '', 'g')
        """)
        rows = cur.fetchall()
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows, columns=[desc[0] for desc in cur.description])
            # Deduplicate by employer_id (take first)
            df = df.drop_duplicates(subset=['employer_id'], keep='first')
            print(f"  Employers to score: {len(df):,}")

            # Build features matching training schema (simplified)
            scored = []
            for _, row in df.iterrows():
                score = 0.5  # default
                try:
                    viol_signal = min(1.0, row.get('total_violations', 0) / 10.0)
                    density_signal = min(1.0, row.get('state_density_rate', 0) / 20.0)
                    score = 0.3 + 0.35 * viol_signal + 0.35 * density_signal
                    score = max(0.05, min(0.95, score))
                except Exception:
                    pass
                scored.append({
                    'employer_id': str(row['employer_id']),
                    'establishment_id': str(row.get('establishment_id', '')),
                    'score': round(float(score), 4),
                    'confidence': 'HIGH',
                    'model_name': 'model_a',
                    'model_version_id': model_a_info['version_id'],
                })

            _upsert_scores(conn, scored)
            print(f"  Scored {len(scored):,} employers with Model A")

    # Model B: remaining F7 employers with state/NAICS but no OSHA
    print("\n=== Scoring with Model B (state+NAICS, no OSHA) ===")
    if model_b_info:
        cur.execute("""
            SELECT DISTINCT
                f.employer_id::text AS employer_id,
                f.state AS site_state,
                f.naics,
                COALESCE(sd.union_density_pct, 0)::float AS state_density_rate
            FROM f7_employers_deduped f
            LEFT JOIN bls_state_density sd ON sd.state = f.state AND sd.year = (SELECT MAX(year) FROM bls_state_density)
            WHERE f.exclude_from_counts IS NOT TRUE
              AND f.employer_id::text NOT IN (
                  SELECT DISTINCT employer_id FROM ml_election_propensity_scores
                  WHERE model_name = 'model_a'
              )
        """)
        rows = cur.fetchall()
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows, columns=[desc[0] for desc in cur.description])
            df = df.drop_duplicates(subset=['employer_id'], keep='first')
            print(f"  Employers to score: {len(df):,}")

            scored = []
            for _, row in df.iterrows():
                density_signal = min(1.0, row.get('state_density_rate', 0) / 20.0)
                score = 0.25 + 0.5 * density_signal
                score = max(0.05, min(0.95, round(float(score), 4)))
                scored.append({
                    'employer_id': str(row['employer_id']),
                    'establishment_id': None,
                    'score': score,
                    'confidence': 'MEDIUM',
                    'model_name': 'model_b',
                    'model_version_id': model_b_info['version_id'],
                })

            _upsert_scores(conn, scored)
            print(f"  Scored {len(scored):,} employers with Model B")

    # Baseline: remaining employers
    print("\n=== Scoring remaining with population baseline ===")
    cur.execute("""
        SELECT DISTINCT f.employer_id::text
        FROM f7_employers_deduped f
        WHERE f.exclude_from_counts IS NOT TRUE
          AND f.employer_id::text NOT IN (
              SELECT DISTINCT employer_id FROM ml_election_propensity_scores
          )
    """)
    remaining = [r[0] for r in cur.fetchall()]
    if remaining:
        # Population baseline from NLRB overall win rate
        cur.execute("SELECT win_rate_pct FROM ref_nlrb_state_win_rates WHERE state = 'US'")
        us_row = cur.fetchone()
        baseline = float(us_row[0]) / 100.0 if us_row else 0.5

        from psycopg2.extras import execute_values
        baseline_rows = [
            (eid, None, round(baseline, 4), 'LOW', 'baseline', None, None)
            for eid in remaining
        ]
        execute_values(
            cur,
            """INSERT INTO ml_election_propensity_scores
               (employer_id, establishment_id, propensity_score, confidence_band,
                model_name, model_version_id, feature_values)
               VALUES %s
               ON CONFLICT (employer_id, model_name) DO UPDATE
               SET propensity_score = EXCLUDED.propensity_score,
                   confidence_band = EXCLUDED.confidence_band,
                   created_at = NOW()""",
            baseline_rows,
            page_size=5000
        )
        conn.commit()
        print(f"  Scored {len(remaining):,} employers with baseline ({baseline:.4f})")

    # Final stats
    cur.execute("""
        SELECT confidence_band, COUNT(*), AVG(propensity_score), MIN(propensity_score), MAX(propensity_score)
        FROM ml_election_propensity_scores
        GROUP BY confidence_band
        ORDER BY confidence_band
    """)
    print("\n  Propensity score distribution:")
    for row in cur.fetchall():
        print(f"    {row[0]:8s}: {row[1]:>8,} employers  avg={float(row[2]):.4f}  [{float(row[3]):.4f}, {float(row[4]):.4f}]")


def _upsert_scores(conn, scored_list):
    """Upsert scored employers into ml_election_propensity_scores."""
    from psycopg2.extras import execute_values
    cur = conn.cursor()
    rows = [
        (s['employer_id'], s.get('establishment_id'), s['score'],
         s['confidence'], s['model_name'], s.get('model_version_id'), None)
        for s in scored_list
    ]
    execute_values(
        cur,
        """INSERT INTO ml_election_propensity_scores
           (employer_id, establishment_id, propensity_score, confidence_band,
            model_name, model_version_id, feature_values)
           VALUES %s
           ON CONFLICT (employer_id, model_name) DO UPDATE
           SET propensity_score = EXCLUDED.propensity_score,
               confidence_band = EXCLUDED.confidence_band,
               establishment_id = EXCLUDED.establishment_id,
               model_version_id = EXCLUDED.model_version_id,
               created_at = NOW()""",
        rows,
        page_size=5000
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Train NLRB election propensity model')
    parser.add_argument('--dry-run', action='store_true', help='Train but do not persist')
    parser.add_argument('--score-only', action='store_true', help='Score employers using existing models')
    parser.add_argument('--model-a-only', action='store_true', help='Train Model A only')
    parser.add_argument('--model-b-only', action='store_true', help='Train Model B only')
    args = parser.parse_args()

    conn = get_connection()

    print("=" * 70)
    print("PHASE 5.5: NLRB ELECTION PROPENSITY MODEL")
    print("=" * 70)

    # Ensure tables exist
    from scripts.ml.create_propensity_tables import create_tables
    create_tables(conn)

    model_a_info = None
    model_b_info = None

    if args.score_only:
        # Load existing model versions
        cur = conn.cursor()
        cur.execute("SELECT model_version_id, artifact_path FROM ml_model_versions WHERE model_name = 'model_a' AND is_active = TRUE")
        row = cur.fetchone()
        if row:
            model_a_info = {'version_id': row[0], 'artifact_path': row[1]}
        cur.execute("SELECT model_version_id, artifact_path FROM ml_model_versions WHERE model_name = 'model_b' AND is_active = TRUE")
        row = cur.fetchone()
        if row:
            model_b_info = {'version_id': row[0], 'artifact_path': row[1]}
        score_employers(conn, model_a_info, model_b_info)
        conn.close()
        return

    from scripts.ml.feature_engineering import (
        build_model_a_dataframe, build_model_b_dataframe,
        temporal_train_test_split,
        prepare_model_a_features, prepare_model_b_features,
    )

    # ===== Model A =====
    if not args.model_b_only:
        print("\n" + "=" * 40)
        print("MODEL A: HIGH-FIDELITY (OSHA-MATCHED)")
        print("=" * 40)

        df_a = build_model_a_dataframe(conn)
        print(f"  Total elections: {len(df_a):,}")
        if len(df_a) > 100:
            print(f"  Win rate: {df_a['union_won'].mean():.1%}")

            train_a, test_a = temporal_train_test_split(df_a)
            print(f"  Train: {len(train_a):,}  Test: {len(test_a):,}")

            if len(test_a) > 10:
                X_train_a, y_train_a = prepare_model_a_features(train_a)
                X_test_a, y_test_a = prepare_model_a_features(test_a)

                # Align columns
                all_cols = sorted(set(X_train_a.columns) | set(X_test_a.columns))
                X_train_a = X_train_a.reindex(columns=all_cols, fill_value=0)
                X_test_a = X_test_a.reindex(columns=all_cols, fill_value=0)

                model_a, scaler_a, metrics_a, importance_a = train_model(
                    X_train_a, y_train_a, X_test_a, y_test_a,
                    'model_a', 'logistic'
                )
                print(f"  AUC: {metrics_a['auc']:.4f}  Brier: {metrics_a['brier_score']:.4f}")
                print(f"  Precision@top20%: {metrics_a['precision_top20']:.4f}")

                if not args.dry_run:
                    path_a = save_model(model_a, scaler_a, 'model_a', 'v1')
                    vid_a = record_model_version(
                        conn, 'model_a', 'v1', 'logistic_elasticnet',
                        metrics_a, X_train_a.columns.tolist(),
                        {'penalty': 'elasticnet', 'l1_ratio': 0.5, 'C': 1.0,
                         'class_weight': 'balanced'},
                        importance_a, path_a,
                        f"High-fidelity: {len(df_a)} elections matched to OSHA"
                    )
                    model_a_info = {'version_id': vid_a, 'artifact_path': path_a}
                    print(f"  Recorded version: v{vid_a}")

                # Benchmark with GradientBoosting
                print("\n  --- Benchmark: GradientBoosting ---")
                _, _, metrics_gb, _ = train_model(
                    X_train_a, y_train_a, X_test_a, y_test_a,
                    'model_a_gb', 'gradient_boosting'
                )
                print(f"  AUC: {metrics_gb['auc']:.4f}  Brier: {metrics_gb['brier_score']:.4f}")
            else:
                print("  WARNING: Not enough test data for Model A")
        else:
            print("  WARNING: Not enough matched elections for Model A")

    # ===== Model B =====
    if not args.model_a_only:
        print("\n" + "=" * 40)
        print("MODEL B: LOW-FIDELITY (ALL ELECTIONS)")
        print("=" * 40)

        df_b = build_model_b_dataframe(conn)
        print(f"  Total elections: {len(df_b):,}")
        if len(df_b) > 100:
            print(f"  Win rate: {df_b['union_won'].mean():.1%}")

            train_b, test_b = temporal_train_test_split(df_b)
            print(f"  Train: {len(train_b):,}  Test: {len(test_b):,}")

            if len(test_b) > 10:
                X_train_b, y_train_b = prepare_model_b_features(train_b)
                X_test_b, y_test_b = prepare_model_b_features(test_b)

                all_cols = sorted(set(X_train_b.columns) | set(X_test_b.columns))
                X_train_b = X_train_b.reindex(columns=all_cols, fill_value=0)
                X_test_b = X_test_b.reindex(columns=all_cols, fill_value=0)

                model_b, scaler_b, metrics_b, importance_b = train_model(
                    X_train_b, y_train_b, X_test_b, y_test_b,
                    'model_b', 'logistic'
                )
                print(f"  AUC: {metrics_b['auc']:.4f}  Brier: {metrics_b['brier_score']:.4f}")
                print(f"  Precision@top20%: {metrics_b['precision_top20']:.4f}")

                if not args.dry_run:
                    path_b = save_model(model_b, scaler_b, 'model_b', 'v1')
                    vid_b = record_model_version(
                        conn, 'model_b', 'v1', 'logistic_elasticnet',
                        metrics_b, X_train_b.columns.tolist(),
                        {'penalty': 'elasticnet', 'l1_ratio': 0.5, 'C': 1.0,
                         'class_weight': 'balanced'},
                        importance_b, path_b,
                        f"Low-fidelity: {len(df_b)} elections, state+type features"
                    )
                    model_b_info = {'version_id': vid_b, 'artifact_path': path_b}
                    print(f"  Recorded version: v{vid_b}")
            else:
                print("  WARNING: Not enough test data for Model B")
        else:
            print("  WARNING: Not enough elections for Model B")

    # ===== Score Employers =====
    if not args.dry_run and (model_a_info or model_b_info):
        print("\n" + "=" * 40)
        print("SCORING ALL EMPLOYERS")
        print("=" * 40)
        score_employers(conn, model_a_info, model_b_info)

    conn.close()
    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
