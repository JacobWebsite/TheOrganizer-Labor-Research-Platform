"""Tests for museums router endpoints (museum sector targets & unionization).

NOTE: Museum views (v_museum_organizing_targets, v_museum_target_stats,
v_museum_unionized) do not currently exist in the database. Endpoints now
return 404 with a clear message instead of 503 when views are missing.
"""
import pytest


class TestMuseumTargets:
    """Tests for GET /api/museums/targets"""

    def test_no_filters(self, client):
        r = client.get("/api/museums/targets")
        if r.status_code == 404:
            assert "not yet created" in r.json()["detail"]
            return
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "targets" in data

    def test_sort_options(self, client):
        r = client.get("/api/museums/targets")
        if r.status_code == 404:
            pytest.skip("Museum views not created yet")
        for col in ["total_score", "best_employee_count", "revenue_millions", "employer_name"]:
            r = client.get("/api/museums/targets", params={"sort_by": col, "limit": 3})
            assert r.status_code == 200, f"Sort by {col} failed"


class TestMuseumTargetStats:
    """Tests for GET /api/museums/targets/stats"""

    def test_returns_stats(self, client):
        r = client.get("/api/museums/targets/stats")
        if r.status_code == 404:
            assert "not yet created" in r.json()["detail"]
            return
        assert r.status_code == 200
        data = r.json()
        assert "by_tier" in data
        assert "totals" in data


class TestMuseumTargetDetail:
    """Tests for GET /api/museums/targets/{target_id}"""

    def test_not_found(self, client):
        r = client.get("/api/museums/targets/nonexistent_999")
        assert r.status_code == 404


class TestMuseumTargetCities:
    """Tests for GET /api/museums/targets/cities"""

    def test_returns_cities(self, client):
        r = client.get("/api/museums/targets/cities")
        if r.status_code == 404:
            assert "not yet created" in r.json()["detail"]
            return
        assert r.status_code == 200
        assert "cities" in r.json()


class TestMuseumUnionized:
    """Tests for GET /api/museums/unionized"""

    def test_returns_list(self, client):
        r = client.get("/api/museums/unionized")
        if r.status_code == 404:
            assert "not yet created" in r.json()["detail"]
            return
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "museums" in data


class TestMuseumSummary:
    """Tests for GET /api/museums/summary"""

    def test_returns_summary(self, client):
        r = client.get("/api/museums/summary")
        if r.status_code == 404:
            assert "not yet created" in r.json()["detail"]
            return
        assert r.status_code == 200
        data = r.json()
        assert data["sector"] == "MUSEUMS"
        assert "targets" in data
        assert "unionized" in data
