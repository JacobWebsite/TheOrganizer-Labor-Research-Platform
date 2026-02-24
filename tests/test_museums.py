"""Tests for museums router endpoints (museum sector targets & unionization).

NOTE: Museum views (v_museum_organizing_targets, v_museum_target_stats,
v_museum_unionized) do not currently exist in the database. All endpoints
return 503 until the views are created. Tests document expected behavior
and will pass once views are created.
"""
import pytest


@pytest.fixture(scope="module")
def museum_views_exist(client):
    """Check if museum views exist in the database."""
    r = client.get("/api/museums/targets")
    return r.status_code != 503


class TestMuseumTargets:
    """Tests for GET /api/museums/targets"""

    def test_no_filters(self, client, museum_views_exist):
        r = client.get("/api/museums/targets")
        if not museum_views_exist:
            assert r.status_code == 503
            pytest.skip("Museum views not created yet")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "targets" in data

    def test_sort_options(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        for col in ["total_score", "best_employee_count", "revenue_millions", "employer_name"]:
            r = client.get("/api/museums/targets", params={"sort_by": col, "limit": 3})
            assert r.status_code == 200, f"Sort by {col} failed"


class TestMuseumTargetStats:
    """Tests for GET /api/museums/targets/stats"""

    def test_returns_stats(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        r = client.get("/api/museums/targets/stats")
        assert r.status_code == 200
        data = r.json()
        assert "by_tier" in data
        assert "totals" in data


class TestMuseumTargetDetail:
    """Tests for GET /api/museums/targets/{target_id}"""

    def test_not_found(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        r = client.get("/api/museums/targets/nonexistent_999")
        assert r.status_code == 404


class TestMuseumTargetCities:
    """Tests for GET /api/museums/targets/cities"""

    def test_returns_cities(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        r = client.get("/api/museums/targets/cities")
        assert r.status_code == 200
        assert "cities" in r.json()


class TestMuseumUnionized:
    """Tests for GET /api/museums/unionized"""

    def test_returns_list(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        r = client.get("/api/museums/unionized")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "museums" in data


class TestMuseumSummary:
    """Tests for GET /api/museums/summary"""

    def test_returns_summary(self, client, museum_views_exist):
        if not museum_views_exist:
            pytest.skip("Museum views not created yet")
        r = client.get("/api/museums/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["sector"] == "MUSEUMS"
        assert "targets" in data
        assert "unionized" in data
