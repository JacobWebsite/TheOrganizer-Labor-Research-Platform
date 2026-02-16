"""
Score version tracking tests (Phase 5.3).

Tests that the score_versions table records algorithm metadata on every
MV create/refresh, and that the API endpoint returns version history.

Run with: py -m pytest tests/test_score_versioning.py -v
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def db():
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


class TestScoreVersionsTable:
    """Verify the score_versions table exists and has correct structure."""

    def test_table_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'score_versions'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_has_required_columns(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'score_versions'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        for required in ["version_id", "created_at", "description",
                         "row_count", "factor_weights", "decay_params", "score_stats"]:
            assert required in cols, f"Missing column: {required}"

    def test_has_at_least_one_version(self, db):
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM score_versions")
        assert cur.fetchone()[0] >= 1


class TestScoreVersionContent:
    """Verify that recorded versions contain meaningful metadata."""

    def test_latest_version_has_row_count(self, db):
        cur = db.cursor()
        cur.execute("SELECT row_count FROM score_versions ORDER BY version_id DESC LIMIT 1")
        row_count = cur.fetchone()[0]
        assert row_count > 0

    def test_factor_weights_is_valid_json(self, db):
        cur = db.cursor()
        cur.execute("SELECT factor_weights FROM score_versions ORDER BY version_id DESC LIMIT 1")
        fw = cur.fetchone()[0]
        assert isinstance(fw, dict)

    def test_canonical_factor_weights_have_core_keys(self, db):
        """Versions with full factor_weights should contain core scoring keys."""
        cur = db.cursor()
        cur.execute("""
            SELECT factor_weights FROM score_versions
            WHERE factor_weights ? 'industry_density'
            ORDER BY version_id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            pytest.skip("No canonical factor_weights version found")
        fw = row[0]
        for key in ["industry_density", "osha", "nlrb", "size", "geographic"]:
            assert key in fw, f"Missing core key: {key}"

    def test_decay_params_is_valid_json(self, db):
        cur = db.cursor()
        cur.execute("SELECT decay_params FROM score_versions ORDER BY version_id DESC LIMIT 1")
        dp = cur.fetchone()[0]
        assert isinstance(dp, dict)

    def test_score_stats_has_expected_keys(self, db):
        cur = db.cursor()
        cur.execute("SELECT score_stats FROM score_versions ORDER BY version_id DESC LIMIT 1")
        stats = cur.fetchone()[0]
        assert isinstance(stats, dict)
        for key in ["min_score", "avg_score", "max_score"]:
            assert key in stats, f"Missing key: {key}"

    def test_score_stats_values_reasonable(self, db):
        cur = db.cursor()
        cur.execute("SELECT score_stats FROM score_versions ORDER BY version_id DESC LIMIT 1")
        stats = cur.fetchone()[0]
        assert stats["min_score"] >= 0
        assert stats["max_score"] <= 90  # 9 factors x 10 max
        assert stats["min_score"] <= stats["avg_score"] <= stats["max_score"]


class TestScoreVersionOrdering:
    """Verify versions are ordered chronologically."""

    def test_version_ids_increase(self, db):
        cur = db.cursor()
        cur.execute("SELECT version_id FROM score_versions ORDER BY version_id")
        ids = [r[0] for r in cur.fetchall()]
        if len(ids) >= 2:
            for i in range(1, len(ids)):
                assert ids[i] > ids[i - 1]

    def test_timestamps_increase(self, db):
        cur = db.cursor()
        cur.execute("SELECT created_at FROM score_versions ORDER BY version_id")
        times = [r[0] for r in cur.fetchall()]
        if len(times) >= 2:
            for i in range(1, len(times)):
                assert times[i] >= times[i - 1]


class TestScoreVersionApi:
    """Test the API endpoint via TestClient."""

    @pytest.fixture(scope="class")
    def client(self):
        os.environ["LABOR_JWT_SECRET"] = ""
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_get_score_versions(self, client):
        resp = client.get("/api/admin/score-versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "versions" in data
        assert "total" in data
        assert data["total"] >= 1
        v = data["versions"][0]
        assert "version_id" in v
        assert "created_at" in v
        assert "row_count" in v

    def test_score_versions_limit(self, client):
        resp = client.get("/api/admin/score-versions?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) <= 1


class TestScoreVersionAuthGuard:
    """Score versions endpoint requires admin auth when JWT is enabled."""

    @pytest.fixture(scope="class")
    def auth_client(self):
        os.environ["LABOR_JWT_SECRET"] = "test-secret-for-auth-guard"
        # Patch JWT_SECRET in all 3 modules
        import api.config
        import api.middleware.auth
        import api.routers.auth as auth_router
        api.config.JWT_SECRET = "test-secret-for-auth-guard"
        api.middleware.auth.JWT_SECRET = "test-secret-for-auth-guard"
        auth_router.JWT_SECRET = "test-secret-for-auth-guard"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        yield client
        # Restore
        os.environ["LABOR_JWT_SECRET"] = ""
        api.config.JWT_SECRET = ""
        api.middleware.auth.JWT_SECRET = ""
        auth_router.JWT_SECRET = ""

    def test_score_versions_requires_auth(self, auth_client):
        resp = auth_client.get("/api/admin/score-versions")
        assert resp.status_code in (401, 403), f"Expected 401 or 403, got {resp.status_code}"
