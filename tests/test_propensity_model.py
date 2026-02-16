"""
Propensity model tests (Phase 5.5).

Tests DB schema, feature engineering transforms, model outputs,
and API endpoints.

Run with: py -m pytest tests/test_propensity_model.py -v
"""
import os
import sys
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ========================================
# Unit Tests (no DB required)
# ========================================

class TestFeatureTransforms:
    """Test feature engineering helper functions."""

    def test_log_transform_positive(self):
        from scripts.ml.feature_engineering import _log_transform
        s = pd.Series([0, 1, 10, 100])
        result = _log_transform(s)
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == pytest.approx(np.log(2), abs=0.001)
        assert all(result >= 0)

    def test_log_transform_negative_clipped(self):
        from scripts.ml.feature_engineering import _log_transform
        s = pd.Series([-5, 0, 5])
        result = _log_transform(s)
        assert result.iloc[0] == 0.0  # negative clipped to 0

    def test_log_transform_nan_handled(self):
        from scripts.ml.feature_engineering import _log_transform
        s = pd.Series([np.nan, 5, np.nan])
        result = _log_transform(s)
        assert result.iloc[0] == 0.0  # NaN filled with 0

    def test_cyclical_month_range(self):
        from scripts.ml.feature_engineering import _cyclical_month
        months = pd.Series(range(1, 13))
        sin_vals, cos_vals = _cyclical_month(months)
        assert all(sin_vals.between(-1, 1))
        assert all(cos_vals.between(-1, 1))

    def test_cyclical_month_periodicity(self):
        from scripts.ml.feature_engineering import _cyclical_month
        months = pd.Series([1, 13])  # Jan and "Jan next year"
        sin_vals, cos_vals = _cyclical_month(months)
        # Should have similar values since they're 12 apart
        assert abs(sin_vals.iloc[0] - sin_vals.iloc[1]) < 0.01

    def test_one_hot_top_n(self):
        from scripts.ml.feature_engineering import _one_hot_top_n
        df = pd.DataFrame({'col': ['a', 'a', 'b', 'b', 'c', 'd', 'e']})
        result = _one_hot_top_n(df, 'col', n=2, prefix='test')
        assert 'test_a' in result.columns
        assert 'test_b' in result.columns
        assert 'test_other' in result.columns


class TestTemporalSplit:
    """Test temporal train/test split."""

    def test_no_leakage(self):
        from scripts.ml.feature_engineering import temporal_train_test_split
        df = pd.DataFrame({
            'election_year': [2020, 2021, 2022, 2023, 2024],
            'x': range(5),
        })
        train, test = temporal_train_test_split(df, cutoff_year=2023)
        assert all(train['election_year'] < 2023)
        assert all(test['election_year'] >= 2023)

    def test_split_sizes(self):
        from scripts.ml.feature_engineering import temporal_train_test_split
        df = pd.DataFrame({
            'election_year': [2020, 2021, 2022, 2023, 2024],
            'x': range(5),
        })
        train, test = temporal_train_test_split(df)
        assert len(train) == 3
        assert len(test) == 2

    def test_all_data_preserved(self):
        from scripts.ml.feature_engineering import temporal_train_test_split
        df = pd.DataFrame({'election_year': range(2018, 2026), 'x': range(8)})
        train, test = temporal_train_test_split(df)
        assert len(train) + len(test) == len(df)


class TestModelOutputs:
    """Test that model training produces valid probability outputs."""

    def test_probabilities_in_range(self):
        """Probabilities should be in [0, 1]."""
        from sklearn.linear_model import LogisticRegression
        X = np.random.randn(100, 5)
        y = (X[:, 0] > 0).astype(int)
        model = LogisticRegression(max_iter=1000)
        model.fit(X, y)
        probs = model.predict_proba(X)[:, 1]
        assert all(probs >= 0)
        assert all(probs <= 1)

    def test_balanced_class_weight(self):
        """class_weight='balanced' should handle imbalanced data."""
        from sklearn.linear_model import LogisticRegression
        X = np.random.randn(100, 3)
        y = np.array([0] * 90 + [1] * 10)
        model = LogisticRegression(class_weight='balanced', max_iter=1000)
        model.fit(X, y)
        probs = model.predict_proba(X)[:, 1]
        # Should predict some positives, not all zeros
        assert probs.mean() > 0.05


# ========================================
# Schema Tests (DB required)
# ========================================

@pytest.fixture(scope="module")
def db():
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


class TestPropensitySchema:
    """Verify propensity model tables exist with correct structure."""

    def test_model_versions_table_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'ml_model_versions'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_propensity_scores_table_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'ml_election_propensity_scores'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_model_versions_columns(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ml_model_versions'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        for required in ["model_version_id", "model_name", "version_string",
                         "model_type", "test_auc", "feature_list", "parameters",
                         "is_active"]:
            assert required in cols, f"Missing column: {required}"

    def test_propensity_scores_columns(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ml_election_propensity_scores'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        for required in ["employer_id", "propensity_score", "confidence_band",
                         "model_name", "model_version_id"]:
            assert required in cols, f"Missing column: {required}"

    def test_active_model_unique_constraint(self, db):
        """Only one active model per model_name."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'ml_model_versions'
              AND indexdef LIKE %s
        """, ('%is_active%',))
        assert cur.fetchone()[0] >= 1


# ========================================
# Integration Tests (DB + scores)
# ========================================

class TestPropensityScores:
    """Test propensity scores if they exist."""

    def test_scores_in_valid_range(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM ml_election_propensity_scores
            WHERE propensity_score < 0 OR propensity_score > 1
        """)
        invalid = cur.fetchone()[0]
        assert invalid == 0, f"{invalid} scores outside [0, 1]"

    def test_confidence_bands_valid(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT DISTINCT confidence_band FROM ml_election_propensity_scores
        """)
        bands = {r[0] for r in cur.fetchall()}
        valid_bands = {'HIGH', 'MEDIUM', 'LOW'}
        if bands:
            assert bands.issubset(valid_bands), f"Invalid bands: {bands - valid_bands}"

    def test_model_version_fk_integrity(self, db):
        """model_version_id should reference existing ml_model_versions."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM ml_election_propensity_scores ps
            WHERE ps.model_version_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM ml_model_versions mv
                  WHERE mv.model_version_id = ps.model_version_id
              )
        """)
        orphans = cur.fetchone()[0]
        assert orphans == 0, f"{orphans} scores reference non-existent model versions"


# ========================================
# API Tests
# ========================================

class TestPropensityAPI:
    """Test propensity API endpoints."""

    @pytest.fixture(scope="class")
    def client(self):
        os.environ["LABOR_JWT_SECRET"] = ""
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_propensity_endpoint_exists(self, client):
        """Propensity endpoint should return 200 or 404 (not 500)."""
        resp = client.get("/api/organizing/propensity/999999")
        assert resp.status_code in (200, 404)

    def test_propensity_models_endpoint(self, client):
        resp = client.get("/api/admin/propensity-models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data

    def test_scorecard_detail_has_propensity(self, client):
        """Scorecard detail should include propensity_context (may be null)."""
        # Get first establishment from scorecard
        resp = client.get("/api/organizing/scorecard?limit=1")
        if resp.status_code == 200 and resp.json().get('results'):
            estab_id = resp.json()['results'][0]['establishment_id']
            detail = client.get(f"/api/organizing/scorecard/{estab_id}")
            if detail.status_code == 200:
                data = detail.json()
                assert "propensity_context" in data
