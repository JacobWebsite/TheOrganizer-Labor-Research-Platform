"""Tests for lookups router endpoints (reference data for dropdowns)."""
import pytest


class TestLookupSectors:
    """Tests for GET /api/lookups/sectors"""

    def test_returns_sectors(self, client):
        r = client.get("/api/lookups/sectors")
        assert r.status_code == 200
        data = r.json()
        assert "sectors" in data
        assert isinstance(data["sectors"], list)
        assert len(data["sectors"]) > 0
        # Each sector should have expected fields
        sector = data["sectors"][0]
        assert "sector_code" in sector
        assert "sector_name" in sector


class TestLookupAffiliations:
    """Tests for GET /api/lookups/affiliations"""

    def test_all_affiliations(self, client):
        r = client.get("/api/lookups/affiliations")
        assert r.status_code == 200
        data = r.json()
        assert "affiliations" in data
        assert len(data["affiliations"]) > 0
        aff = data["affiliations"][0]
        assert "aff_abbr" in aff
        assert "local_count" in aff

    def test_filter_by_sector(self, client):
        r = client.get("/api/lookups/affiliations", params={"sector": "PVT"})
        assert r.status_code == 200
        assert "affiliations" in r.json()


class TestLookupStates:
    """Tests for GET /api/lookups/states"""

    def test_returns_states(self, client):
        r = client.get("/api/lookups/states")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data
        assert len(data["states"]) > 0
        state = data["states"][0]
        assert "state" in state
        assert "employer_count" in state


class TestLookupNAICSSectors:
    """Tests for GET /api/lookups/naics-sectors"""

    def test_returns_naics(self, client):
        r = client.get("/api/lookups/naics-sectors")
        assert r.status_code == 200
        data = r.json()
        assert "sectors" in data
        assert isinstance(data["sectors"], list)
        assert len(data["sectors"]) > 0


class TestLookupMetros:
    """Tests for GET /api/lookups/metros"""

    def test_returns_metros(self, client):
        r = client.get("/api/lookups/metros")
        assert r.status_code == 200
        data = r.json()
        assert "metros" in data
        assert isinstance(data["metros"], list)
        assert len(data["metros"]) > 0


class TestLookupCities:
    """Tests for GET /api/lookups/cities"""

    def test_all_cities(self, client):
        r = client.get("/api/lookups/cities", params={"limit": 10})
        assert r.status_code == 200
        data = r.json()
        assert "cities" in data
        assert len(data["cities"]) <= 10

    def test_cities_by_state(self, client):
        r = client.get("/api/lookups/cities", params={"state": "NY"})
        assert r.status_code == 200
        assert "cities" in r.json()


class TestMetroStats:
    """Tests for GET /api/metros/{cbsa_code}/stats"""

    def test_valid_metro(self, client):
        # Get a real CBSA code from the metros list
        metros = client.get("/api/lookups/metros").json().get("metros", [])
        if not metros:
            pytest.skip("No metros in database")

        cbsa = metros[0]["cbsa_code"]
        r = client.get(f"/api/metros/{cbsa}/stats")
        assert r.status_code == 200
        data = r.json()
        assert "metro" in data
        assert "union_density" in data
        assert "top_unions" in data
        assert "counties" in data

    def test_invalid_metro(self, client):
        r = client.get("/api/metros/00000/stats")
        assert r.status_code == 200
        # Returns error key rather than 404
        data = r.json()
        assert "error" in data or "metro" in data
