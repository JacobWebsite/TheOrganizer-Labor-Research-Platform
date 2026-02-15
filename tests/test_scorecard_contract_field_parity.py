"""
Contract-field parity tests for scorecard list vs detail payloads.
"""
import pytest


def test_scorecard_list_includes_federal_contract_count(client):
    r = client.get("/api/organizing/scorecard?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    if not data["results"]:
        pytest.skip("No scorecard results")

    first = data["results"][0]
    assert "federal_contract_count" in first
    assert isinstance(first["federal_contract_count"], int)
    assert first["federal_contract_count"] >= 0


def test_scorecard_list_detail_contract_fields_are_compatible(client):
    r = client.get("/api/organizing/scorecard?limit=1")
    assert r.status_code == 200
    results = r.json().get("results", [])
    if not results:
        pytest.skip("No scorecard results")

    row = results[0]
    eid = row["establishment_id"]
    d = client.get(f"/api/organizing/scorecard/{eid}")
    assert d.status_code == 200
    detail = d.json()
    contracts = detail.get("contracts", {})

    assert "federal_contract_count" in row
    assert "federal_contract_count" in contracts
    assert row["federal_contract_count"] == contracts["federal_contract_count"]

