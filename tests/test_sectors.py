"""Tests for sectors router endpoints (multi-sector targets overview).

NOTE: Sector target views (v_{sector}_organizing_targets, v_{sector}_target_stats,
v_{sector}_unionized) do not currently exist for most sectors. The /api/sectors/list
endpoint works (queries mergent_employers directly), but per-sector endpoints that
reference these views will return 503. Tests skip gracefully when views are missing.
"""
import pytest


class TestSectorsList:
    """Tests for GET /api/sectors/list"""

    def test_returns_sectors(self, client):
        r = client.get("/api/sectors/list")
        assert r.status_code == 200
        data = r.json()
        assert "sectors" in data
        assert isinstance(data["sectors"], list)
        assert len(data["sectors"]) > 0
        sector = data["sectors"][0]
        assert "sector_category" in sector
        assert "total_employers" in sector
        assert "union_density_pct" in sector


class TestSectorSummary:
    """Tests for GET /api/sectors/{sector}/summary"""

    def test_valid_sector(self, client):
        # Get a real sector from the list
        sectors = client.get("/api/sectors/list").json().get("sectors", [])
        if not sectors:
            pytest.skip("No sectors in mergent_employers")

        sector_name = sectors[0]["sector_category"].lower()
        r = client.get(f"/api/sectors/{sector_name}/summary")
        assert r.status_code == 200
        data = r.json()
        assert "targets" in data
        assert "unionized" in data
        assert "union_density_pct" in data

    def test_invalid_sector_returns_404(self, client):
        r = client.get("/api/sectors/nonexistent_sector/summary")
        assert r.status_code == 404


class TestSectorTargets:
    """Tests for GET /api/sectors/{sector}/targets"""

    def _get_valid_sector_key(self, client):
        """Get a sector key that exists in SECTOR_VIEWS."""
        from api.helpers import SECTOR_VIEWS
        sectors = client.get("/api/sectors/list").json().get("sectors", [])
        for s in sectors:
            key = s["sector_category"].lower()
            if key in SECTOR_VIEWS:
                return key
        return None

    def test_no_filters(self, client):
        sector = self._get_valid_sector_key(client)
        if not sector:
            pytest.skip("No sector keys match SECTOR_VIEWS")

        r = client.get(f"/api/sectors/{sector}/targets", params={"limit": 5})
        # 503 if the view doesn't exist in DB
        if r.status_code == 503:
            pytest.skip(f"View v_{sector}_organizing_targets does not exist")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "targets" in data

    def test_invalid_sector(self, client):
        r = client.get("/api/sectors/nonexistent/targets")
        assert r.status_code == 404


class TestSectorTargetStats:
    """Tests for GET /api/sectors/{sector}/targets/stats"""

    def test_invalid_sector(self, client):
        r = client.get("/api/sectors/nonexistent/targets/stats")
        assert r.status_code == 404


class TestSectorTargetCities:
    """Tests for GET /api/sectors/{sector}/targets/cities"""

    def test_invalid_sector_returns_404(self, client):
        r = client.get("/api/sectors/nonexistent/targets/cities")
        assert r.status_code == 404


class TestSectorUnionized:
    """Tests for GET /api/sectors/{sector}/unionized"""

    def test_invalid_sector(self, client):
        r = client.get("/api/sectors/nonexistent/unionized")
        assert r.status_code == 404
