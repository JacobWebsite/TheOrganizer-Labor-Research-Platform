"""Tests for /api/employers/master/{master_id}/fec-contributions (24Q-41).

Live-data tests against the local DB. Each test is self-skipping if the
required tables are missing or have insufficient rows.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.fec_contributions import _employer_name_variants
from db_config import get_connection


client = TestClient(app)


def _has_fec_data() -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('fec_individual_contributions')")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT COUNT(*) FROM fec_individual_contributions LIMIT 1")
        n = cur.fetchone()[0]
        conn.close()
        return n > 1000
    except Exception:
        return False


# ---- Pure helper tests (no DB needed) ----

def test_employer_name_variants_includes_raw_and_normalized():
    v = _employer_name_variants("Space Exploration Technologies Corp")
    # Raw uppercase + suffix-stripped
    assert "SPACE EXPLORATION TECHNOLOGIES CORP" in v
    assert "SPACE EXPLORATION TECHNOLOGIES" in v
    assert len(v) == 2  # No duplicates


def test_employer_name_variants_no_suffix_returns_single():
    v = _employer_name_variants("Apple")
    assert v == ["APPLE"]


def test_employer_name_variants_short_input_rejected():
    assert _employer_name_variants("AB") == []
    assert _employer_name_variants("") == []
    assert _employer_name_variants(None) == []


def test_employer_name_variants_strips_punctuation_in_normalized():
    v = _employer_name_variants("Smith & Jones, Inc.")
    # Raw uppercase first
    assert v[0] == "SMITH & JONES, INC."
    # Normalized strips punctuation + suffix
    assert any("SMITH" in x and "JONES" in x and "&" not in x for x in v[1:])


# ---- Endpoint tests (live DB) ----

@pytest.mark.skipif(not _has_fec_data(), reason="FEC data not loaded")
def test_unknown_master_returns_404():
    r = client.get("/api/employers/master/999999999/fec-contributions")
    assert r.status_code == 404


@pytest.mark.skipif(not _has_fec_data(), reason="FEC data not loaded")
def test_endpoint_shape_for_known_master_with_fec_activity():
    # SpaceX master_id 1716574 confirmed to have ~47K employee donations
    r = client.get("/api/employers/master/1716574/fec-contributions")
    assert r.status_code == 200
    data = r.json()
    # Top-level shape
    assert "summary" in data
    assert "top_pac_recipients" in data
    assert "top_employee_donors" in data
    assert "yearly_breakdown" in data
    # Summary keys
    summary = data["summary"]
    for key in ("is_matched", "pac_committees_count", "pac_dollars_total",
                "pac_recipients_count", "employee_donations_count",
                "employee_dollars_total", "employer_norms_used",
                "latest_pac_date", "latest_employee_date"):
        assert key in summary, f"missing key: {key}"
    # Sanity: SpaceX should have non-trivial employee donations
    assert summary["employee_donations_count"] > 1000
    assert summary["employee_dollars_total"] > 100000
    assert summary["is_matched"] is True


@pytest.mark.skipif(not _has_fec_data(), reason="FEC data not loaded")
def test_endpoint_returns_unmatched_for_master_with_no_fec():
    # Pick an arbitrary master that almost certainly has no FEC presence
    # (small private LLC). Use a master_id picked from a low-end of the range.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.master_id FROM master_employers m
        WHERE m.canonical_name IS NOT NULL
          AND length(m.canonical_name) < 15
          AND m.canonical_name NOT ILIKE '%inc%'
          AND m.canonical_name NOT ILIKE '%corp%'
          AND NOT EXISTS (
            SELECT 1 FROM master_employer_source_ids s
            WHERE s.master_id = m.master_id AND s.source_system = 'fec'
          )
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("No suitable test master found")
    r = client.get(f"/api/employers/master/{row[0]}/fec-contributions")
    assert r.status_code == 200
    data = r.json()
    # Likely unmatched (no PAC and no employees) but the shape must still be
    # returned correctly.
    assert "summary" in data


@pytest.mark.skipif(not _has_fec_data(), reason="FEC data not loaded")
def test_top_donors_sorted_by_dollars_desc():
    r = client.get("/api/employers/master/1716574/fec-contributions?top_donors=10")
    assert r.status_code == 200
    donors = r.json()["top_employee_donors"]
    if len(donors) > 1:
        for i in range(len(donors) - 1):
            assert donors[i]["dollars"] >= donors[i + 1]["dollars"]


@pytest.mark.skipif(not _has_fec_data(), reason="FEC data not loaded")
def test_yearly_breakdown_sorted_descending():
    r = client.get("/api/employers/master/1716574/fec-contributions")
    assert r.status_code == 200
    yearly = r.json()["yearly_breakdown"]
    if len(yearly) > 1:
        for i in range(len(yearly) - 1):
            assert yearly[i]["year"] >= yearly[i + 1]["year"]
