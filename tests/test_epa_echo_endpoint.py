"""
Tests for /api/employers/master/{master_id}/epa-echo (24Q-31).

Verifies:
- 404 on unknown master_id
- Empty shape returned for masters with no EPA links
- Populated shape (summary + facilities + latest_record_date) for masters
  that DO have EPA links
- facility_limit query param truncates the facilities array but does NOT
  affect the summary aggregates
"""
import pytest

from db_config import get_connection


def _get_master_with_epa_links() -> int:
    """Pick a deterministic master with multiple EPA links + real signal,
    so the populated-shape assertions are meaningful."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sid.master_id
                FROM master_employer_source_ids sid
                JOIN epa_echo_facilities ef ON ef.registry_id = sid.source_id
                WHERE sid.source_system = 'epa_echo'
                GROUP BY sid.master_id
                HAVING COUNT(*) >= 5
                   AND SUM(COALESCE(ef.fac_total_penalties, 0)) > 0
                ORDER BY sid.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def _get_master_without_epa_links() -> int:
    """Pick a master with no EPA links so we can test the empty-shape path."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.master_id
                FROM master_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM master_employer_source_ids s
                    WHERE s.master_id = m.master_id
                      AND s.source_system = 'epa_echo'
                )
                  AND m.source_origin = 'f7'
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def test_epa_echo_404_on_unknown_master(client):
    """Unknown master_id should 404. Use a value far above current max."""
    r = client.get("/api/employers/master/999999999/epa-echo")
    assert r.status_code == 404


def test_epa_echo_empty_shape_when_no_links(client):
    """Master with no EPA links returns the full shape with zeros, not 404.
    The frontend relies on this to render its 'no records matched' panel."""
    master_id = _get_master_without_epa_links()
    if master_id == 0:
        pytest.skip("No master without EPA links available in DB")
    r = client.get(f"/api/employers/master/{master_id}/epa-echo")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "facilities" in data
    assert "latest_record_date" in data
    s = data["summary"]
    assert s["total_facilities"] == 0
    assert s["active_facilities"] == 0
    assert s["total_inspections"] == 0
    assert s["total_formal_actions"] == 0
    assert s["total_informal_actions"] == 0
    assert s["total_penalties"] == 0
    assert s["snc_facilities"] == 0
    assert data["facilities"] == []
    assert data["latest_record_date"] is None


def test_epa_echo_populated_shape(client):
    """Populated path: summary aggregates >0 and facilities sorted by penalty DESC."""
    master_id = _get_master_with_epa_links()
    if master_id == 0:
        pytest.skip("No master with EPA links + signal available in DB")
    r = client.get(f"/api/employers/master/{master_id}/epa-echo")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    assert s["total_facilities"] > 0
    assert s["total_facilities"] >= s["active_facilities"]
    assert s["total_penalties"] >= 0
    assert isinstance(data["facilities"], list)
    assert len(data["facilities"]) > 0

    # Facilities ordered by penalties DESC (with formal_action / inspection
    # tiebreakers). Verify the first row has the largest penalty value.
    pens = [f["total_penalties"] for f in data["facilities"]]
    assert pens == sorted(pens, reverse=True)

    # Per-facility shape sanity
    f0 = data["facilities"][0]
    for k in (
        "registry_id",
        "facility_name",
        "city",
        "state",
        "naics",
        "active",
        "snc_flag",
        "inspection_count",
        "formal_action_count",
        "informal_action_count",
        "total_penalties",
        "last_inspection_date",
        "last_formal_action_date",
        "last_penalty_date",
        "compliance_status",
        "match_confidence",
    ):
        assert k in f0, f"missing key {k} in facility row"
    # Bool typing on the flag fields
    assert isinstance(f0["active"], bool)
    assert isinstance(f0["snc_flag"], bool)


def test_epa_echo_facility_limit_truncates_only_array(client):
    """`facility_limit` should bound facilities[] but NOT change summary
    aggregates -- those always reflect the full match set."""
    master_id = _get_master_with_epa_links()
    if master_id == 0:
        pytest.skip("No master with EPA links + signal available in DB")

    full = client.get(f"/api/employers/master/{master_id}/epa-echo").json()
    if full["summary"]["total_facilities"] < 3:
        pytest.skip("Need a master with >=3 facilities to test truncation")

    truncated = client.get(
        f"/api/employers/master/{master_id}/epa-echo?facility_limit=2"
    ).json()
    assert len(truncated["facilities"]) == 2
    assert truncated["summary"] == full["summary"]
    assert truncated["latest_record_date"] == full["latest_record_date"]


def test_epa_echo_facility_limit_validation(client):
    """Out-of-range facility_limit should return 422 (FastAPI validation)."""
    master_id = _get_master_with_epa_links()
    if master_id == 0:
        pytest.skip("No master with EPA links available in DB")
    r = client.get(f"/api/employers/master/{master_id}/epa-echo?facility_limit=0")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/epa-echo?facility_limit=500")
    assert r.status_code == 422
