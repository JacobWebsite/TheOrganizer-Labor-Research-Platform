"""Tests for VR (Voluntary Recognition) router endpoints."""
import pytest


class TestVRSummary:
    """Tests for GET /api/vr/stats/summary"""

    def test_returns_summary(self, client):
        r = client.get("/api/vr/stats/summary")
        assert r.status_code == 200
        data = r.json()
        # v_vr_summary_stats returns a single row with aggregate stats
        assert isinstance(data, dict)


class TestVRByYear:
    """Tests for GET /api/vr/stats/by-year"""

    def test_returns_years(self, client):
        r = client.get("/api/vr/stats/by-year")
        assert r.status_code == 200
        data = r.json()
        assert "years" in data
        assert isinstance(data["years"], list)
        assert len(data["years"]) > 0


class TestVRByState:
    """Tests for GET /api/vr/stats/by-state"""

    def test_returns_states(self, client):
        r = client.get("/api/vr/stats/by-state")
        assert r.status_code == 200
        data = r.json()
        assert "states" in data
        assert len(data["states"]) > 0


class TestVRByAffiliation:
    """Tests for GET /api/vr/stats/by-affiliation"""

    def test_returns_affiliations(self, client):
        r = client.get("/api/vr/stats/by-affiliation")
        assert r.status_code == 200
        data = r.json()
        assert "affiliations" in data
        assert len(data["affiliations"]) > 0


class TestVRMap:
    """Tests for GET /api/vr/map"""

    def test_default(self, client):
        r = client.get("/api/vr/map")
        assert r.status_code == 200
        data = r.json()
        assert "features" in data
        assert isinstance(data["features"], list)

    def test_state_filter(self, client):
        r = client.get("/api/vr/map", params={"state": "NY", "limit": 10})
        assert r.status_code == 200

    def test_year_filter(self, client):
        r = client.get("/api/vr/map", params={"year": 2023, "limit": 10})
        assert r.status_code == 200


class TestVRNewEmployers:
    """Tests for GET /api/vr/new-employers"""

    def test_default(self, client):
        r = client.get("/api/vr/new-employers")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "employers" in data

    def test_state_filter(self, client):
        r = client.get("/api/vr/new-employers", params={"state": "CA", "limit": 10})
        assert r.status_code == 200

    def test_min_employees(self, client):
        r = client.get("/api/vr/new-employers", params={"min_employees": 100, "limit": 10})
        assert r.status_code == 200


class TestVRPipeline:
    """Tests for GET /api/vr/pipeline"""

    def test_default(self, client):
        r = client.get("/api/vr/pipeline")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "records" in data


class TestVRSearch:
    """Tests for GET /api/vr/search"""

    def test_no_filters(self, client):
        r = client.get("/api/vr/search")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_employer_search(self, client):
        r = client.get("/api/vr/search", params={"employer": "hospital", "limit": 5})
        assert r.status_code == 200

    def test_state_filter(self, client):
        r = client.get("/api/vr/search", params={"state": "NY", "limit": 5})
        assert r.status_code == 200

    def test_sort_options(self, client):
        for sort in ["date", "employees", "employer"]:
            r = client.get("/api/vr/search", params={"sort_by": sort, "limit": 3})
            assert r.status_code == 200, f"Sort by {sort} failed"

    def test_matched_filter(self, client):
        r = client.get("/api/vr/search", params={"employer_matched": True, "limit": 5})
        assert r.status_code == 200


class TestVRDetail:
    """Tests for GET /api/vr/{case_number}"""

    def test_not_found(self, client):
        r = client.get("/api/vr/NONEXISTENT-999")
        assert r.status_code == 404

    def test_valid_case(self, client):
        # Get a real case number from search
        search = client.get("/api/vr/search", params={"limit": 1}).json()
        results = search.get("results", [])
        if not results:
            pytest.skip("No VR cases in database")

        case_number = results[0]["vr_case_number"]
        r = client.get(f"/api/vr/{case_number}")
        assert r.status_code == 200
        data = r.json()
        assert "vr_case" in data
        assert data["vr_case"]["vr_case_number"] == case_number
