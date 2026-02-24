"""Tests for public_sector router endpoints (public sector union data)."""
import pytest


class TestPublicSectorStats:
    """Tests for GET /api/public-sector/stats"""

    def test_returns_stats(self, client):
        r = client.get("/api/public-sector/stats")
        assert r.status_code == 200
        data = r.json()
        assert "union_locals" in data
        assert "employers" in data
        assert "parent_unions" in data
        assert "bargaining_units" in data
        assert "total_members" in data
        assert "employer_types" in data
        assert "parent_summary" in data


class TestPublicSectorParentUnions:
    """Tests for GET /api/public-sector/parent-unions"""

    def test_returns_list(self, client):
        r = client.get("/api/public-sector/parent-unions")
        assert r.status_code == 200
        data = r.json()
        assert "parent_unions" in data
        assert isinstance(data["parent_unions"], list)


class TestPublicSectorLocals:
    """Tests for GET /api/public-sector/locals"""

    def test_no_filters(self, client):
        r = client.get("/api/public-sector/locals")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "locals" in data

    def test_state_filter(self, client):
        r = client.get("/api/public-sector/locals", params={"state": "NY", "limit": 10})
        assert r.status_code == 200

    def test_name_search(self, client):
        r = client.get("/api/public-sector/locals", params={"name": "teachers", "limit": 10})
        assert r.status_code == 200


class TestPublicSectorEmployers:
    """Tests for GET /api/public-sector/employers"""

    def test_no_filters(self, client):
        r = client.get("/api/public-sector/employers")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "employers" in data

    def test_state_filter(self, client):
        r = client.get("/api/public-sector/employers", params={"state": "CA", "limit": 10})
        assert r.status_code == 200

    def test_name_search(self, client):
        r = client.get("/api/public-sector/employers", params={"name": "school", "limit": 10})
        assert r.status_code == 200


class TestPublicSectorEmployerTypes:
    """Tests for GET /api/public-sector/employer-types"""

    def test_returns_types(self, client):
        r = client.get("/api/public-sector/employer-types")
        assert r.status_code == 200
        data = r.json()
        assert "employer_types" in data
        assert isinstance(data["employer_types"], list)


class TestPublicSectorBenchmarks:
    """Tests for GET /api/public-sector/benchmarks"""

    def test_all_benchmarks(self, client):
        r = client.get("/api/public-sector/benchmarks")
        assert r.status_code == 200
        data = r.json()
        assert "benchmarks" in data
        assert isinstance(data["benchmarks"], list)

    def test_state_benchmark(self, client):
        r = client.get("/api/public-sector/benchmarks", params={"state": "NY"})
        assert r.status_code == 200
        data = r.json()
        assert "benchmark" in data
