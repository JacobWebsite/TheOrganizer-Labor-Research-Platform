"""
Tests for /api/employers/master/{master_id}/facilities (Week 3 A.2).

Mirrors test_epa_echo_endpoint.py shape. Verifies:
- 404 on unknown master_id
- Empty shape returned for masters with no geocoded links
- Populated shape (summary + facilities) for masters with geocoded
  facilities across the supported sources (epa, f7, mergent)
- Coordinate validity: every returned facility has a valid lat/lng
- limit query param truncates the facilities array but keeps summary
  totals honest (totals reflect pre-truncation counts)
"""
import pytest

from db_config import get_connection


def _get_master_with_facilities() -> int:
    """Pick a deterministic master with multiple geocoded facilities
    across at least two sources -- gives the populated-shape assertions
    real signal."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH per_master AS (
                  SELECT sid.master_id, COUNT(DISTINCT sid.source_system) AS systems
                  FROM master_employer_source_ids sid
                  WHERE (
                    (sid.source_system = 'epa_echo' AND EXISTS (
                       SELECT 1 FROM epa_echo_facilities ef
                       WHERE ef.registry_id = sid.source_id
                         AND ef.fac_lat IS NOT NULL AND ef.fac_long IS NOT NULL))
                    OR (sid.source_system = 'f7' AND EXISTS (
                       SELECT 1 FROM f7_employers f7
                       WHERE f7.employer_id = sid.source_id
                         AND f7.latitude IS NOT NULL AND f7.longitude IS NOT NULL))
                    OR (sid.source_system = 'mergent' AND EXISTS (
                       SELECT 1 FROM mergent_employers m
                       WHERE m.duns = sid.source_id
                         AND m.latitude IS NOT NULL AND m.longitude IS NOT NULL))
                  )
                  GROUP BY sid.master_id
                  HAVING COUNT(DISTINCT sid.source_system) >= 2
                )
                SELECT master_id FROM per_master ORDER BY master_id LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def _get_master_without_facilities() -> int:
    """Master with zero geocoded facility links -- exercises the empty path."""
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
                      AND s.source_system IN ('epa_echo', 'f7', 'mergent')
                )
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def test_facilities_404_on_unknown_master(client):
    """Unknown master_id should 404."""
    r = client.get("/api/employers/master/999999999/facilities")
    assert r.status_code == 404


def test_facilities_empty_shape_when_no_links(client):
    """Master with zero geocoded sources returns empty shape, not 404.
    Frontend depends on this to render its empty-state panel."""
    master_id = _get_master_without_facilities()
    if master_id == 0:
        pytest.skip("No master without geocoded source links available in DB")
    r = client.get(f"/api/employers/master/{master_id}/facilities")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "facilities" in data
    s = data["summary"]
    assert s["total_facilities"] == 0
    assert s["by_source"] == {"epa": 0, "f7": 0, "mergent": 0}
    assert s["states"] == []
    assert data["facilities"] == []


def test_facilities_populated_shape(client):
    """Populated path: summary counts > 0, every facility has valid coords."""
    master_id = _get_master_with_facilities()
    if master_id == 0:
        pytest.skip("No master with multi-source geocoded facilities in DB")
    r = client.get(f"/api/employers/master/{master_id}/facilities")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    assert s["total_facilities"] > 0

    # by_source dict has all three keys, always.
    assert set(s["by_source"].keys()) == {"epa", "f7", "mergent"}
    sum_by_source = sum(s["by_source"].values())
    assert sum_by_source == s["total_facilities"]

    # At least 2 sources contributed (because that's how we picked the master).
    contributing = sum(1 for v in s["by_source"].values() if v > 0)
    assert contributing >= 2

    # states is sorted unique
    assert s["states"] == sorted(set(s["states"]))

    # Per-facility shape + coord validity
    assert isinstance(data["facilities"], list)
    assert len(data["facilities"]) > 0
    for f in data["facilities"]:
        for k in ("id", "source", "lat", "lng", "label", "extra"):
            assert k in f, f"missing key {k} in facility row"
        assert f["source"] in ("epa", "f7", "mergent")
        assert isinstance(f["lat"], (int, float))
        assert isinstance(f["lng"], (int, float))
        assert -90.0 <= f["lat"] <= 90.0
        assert -180.0 <= f["lng"] <= 180.0
        # Sentinel 0,0 must be filtered upstream.
        assert not (f["lat"] == 0.0 and f["lng"] == 0.0)
        # ID should be source-prefixed for uniqueness.
        assert f["id"].startswith(f["source"] + "-")


def test_facilities_limit_truncates_array_but_keeps_total(client):
    """limit query param truncates the array but `summary.total_facilities`
    must reflect the pre-truncation total. Frontend uses the total to
    label the card header honestly."""
    master_id = _get_master_with_facilities()
    if master_id == 0:
        pytest.skip("No master with multi-source geocoded facilities in DB")

    # First, find the un-truncated count.
    r0 = client.get(f"/api/employers/master/{master_id}/facilities")
    assert r0.status_code == 200
    full = r0.json()
    full_total = full["summary"]["total_facilities"]
    if full_total < 2:
        pytest.skip("Master has fewer than 2 facilities; truncation has no effect")

    # Then call with limit=1.
    r1 = client.get(f"/api/employers/master/{master_id}/facilities?limit=1")
    assert r1.status_code == 200
    truncated = r1.json()
    assert len(truncated["facilities"]) == 1
    # Summary counts must NOT shrink to the truncated array length.
    assert truncated["summary"]["total_facilities"] == full_total


def test_facilities_limit_param_validation(client):
    """Out-of-range limit returns 422 (FastAPI Query validator)."""
    r = client.get("/api/employers/master/1/facilities?limit=0")
    assert r.status_code == 422
    r = client.get("/api/employers/master/1/facilities?limit=99999")
    assert r.status_code == 422
