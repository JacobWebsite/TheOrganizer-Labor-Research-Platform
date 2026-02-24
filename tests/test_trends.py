"""Tests for trends router endpoints (historical membership & election trends)."""
import pytest


class TestNationalTrends:
    """Tests for GET /api/trends/national"""

    def test_returns_trends(self, client):
        r = client.get("/api/trends/national")
        assert r.status_code == 200
        data = r.json()
        assert "trends" in data
        assert "dedup_ratio" in data
        assert isinstance(data["trends"], list)
        assert len(data["trends"]) > 0
        # Each year should have raw + deduped
        trend = data["trends"][0]
        assert "year" in trend
        assert "total_members_raw" in trend
        assert "total_members_dedup" in trend


class TestAffiliationTrendsSummary:
    """Tests for GET /api/trends/affiliations/summary"""

    def test_returns_affiliations(self, client):
        r = client.get("/api/trends/affiliations/summary")
        assert r.status_code == 200
        data = r.json()
        assert "affiliations" in data
        assert len(data["affiliations"]) > 0
        aff = data["affiliations"][0]
        assert "aff_abbr" in aff
        assert "members_2024" in aff


class TestAffiliationTrends:
    """Tests for GET /api/trends/by-affiliation/{aff_abbr}"""

    def test_valid_affiliation(self, client):
        r = client.get("/api/trends/by-affiliation/SEIU")
        assert r.status_code == 200
        data = r.json()
        assert data["affiliation"] == "SEIU"
        assert "trends" in data
        assert len(data["trends"]) > 0

    def test_unknown_affiliation(self, client):
        r = client.get("/api/trends/by-affiliation/ZZZZZ")
        assert r.status_code == 200
        assert r.json()["trends"] == []


class TestStateTrendsSummary:
    """Tests for GET /api/trends/states/summary"""

    def test_returns_states(self, client):
        r = client.get("/api/trends/states/summary")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data
        assert len(data["states"]) > 0


class TestStateTrends:
    """Tests for GET /api/trends/by-state/{state}"""

    def test_valid_state(self, client):
        r = client.get("/api/trends/by-state/NY")
        assert r.status_code == 200
        data = r.json()
        assert data["state"] == "NY"
        assert "trends" in data
        assert len(data["trends"]) > 0

    def test_unknown_state(self, client):
        r = client.get("/api/trends/by-state/QQ")
        assert r.status_code == 200
        data = r.json()
        assert data["state"] == "QQ"
        assert len(data["trends"]) == 0


class TestElectionTrends:
    """Tests for GET /api/trends/elections"""

    def test_returns_trends(self, client):
        r = client.get("/api/trends/elections")
        assert r.status_code == 200
        data = r.json()
        assert "election_trends" in data
        assert len(data["election_trends"]) > 0
        year_data = data["election_trends"][0]
        assert "year" in year_data
        assert "total_elections" in year_data
        assert "union_wins" in year_data
        assert "win_rate" in year_data


class TestElectionTrendsByAffiliation:
    """Tests for GET /api/trends/elections/by-affiliation/{aff_abbr}"""

    def test_valid_affiliation(self, client):
        r = client.get("/api/trends/elections/by-affiliation/SEIU")
        assert r.status_code == 200
        data = r.json()
        assert data["affiliation"] == "SEIU"
        assert "election_trends" in data

    def test_unknown_affiliation(self, client):
        r = client.get("/api/trends/elections/by-affiliation/ZZZZZ")
        assert r.status_code == 200
        assert r.json()["election_trends"] == []


class TestSectorTrends:
    """Tests for GET /api/trends/sectors"""

    def test_returns_sectors(self, client):
        r = client.get("/api/trends/sectors")
        assert r.status_code == 200
        data = r.json()
        assert "sectors" in data
        assert len(data["sectors"]) > 0
        sec = data["sectors"][0]
        assert "naics_2digit" in sec
        assert "employer_count" in sec
