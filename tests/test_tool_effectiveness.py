"""
Tests for tool effectiveness API and pruning (Task 4-8).

Verifies:
  - GET /api/research/tool-effectiveness endpoint structure
  - Pruning recommendations populated
  - Environment variable overrides
  - Configurable thresholds in agent.py
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "false")
os.environ.setdefault("DISABLE_AUTH", "true")

from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestToolEffectivenessEndpoint:
    """GET /api/research/tool-effectiveness should return correct structure."""

    def test_endpoint_returns_200(self, client):
        resp = client.get("/api/research/tool-effectiveness")
        assert resp.status_code == 200

    def test_response_has_tools_key(self, client):
        resp = client.get("/api/research/tool-effectiveness")
        data = resp.json()
        assert "tools" in data
        assert "strategies" in data
        assert "thresholds" in data

    def test_thresholds_are_populated(self, client):
        resp = client.get("/api/research/tool-effectiveness")
        thresholds = resp.json()["thresholds"]
        assert thresholds["prune_hit_rate"] == 0.10
        assert thresholds["prune_min_tries"] == 5
        assert thresholds["latency_skip_ms"] == 15000

    def test_tools_have_pruning_recommendation(self, client):
        resp = client.get("/api/research/tool-effectiveness")
        tools = resp.json()["tools"]
        if tools:
            for tool in tools:
                assert "pruning_recommendation" in tool
                assert tool["pruning_recommendation"] in ("active", "prune_low_hit_rate", "prune_slow_and_low")


class TestEnvVarOverride:
    """Environment variables should override default thresholds."""

    def test_custom_prune_hit_rate(self, client, monkeypatch):
        monkeypatch.setenv("RESEARCH_PRUNE_HIT_RATE", "0.25")
        resp = client.get("/api/research/tool-effectiveness")
        thresholds = resp.json()["thresholds"]
        assert thresholds["prune_hit_rate"] == 0.25
