"""
Tests for /api/employers/master/{master_id}/institutional-owners (24Q-9).

Verifies:
- 404 on unknown master_id
- "Not matched" path: master with no SEC 13F issuer-name match returns
  is_matched=false (NOT 404) so the frontend can render its panel
- Populated path: matched master returns owners sorted by value DESC,
  with summary aggregates that span the full match set (not truncated)
- limit truncation
- limit validation
"""
import pytest

from db_config import get_connection


def _get_matched_master() -> int:
    """Pick a master that has a 13F issuer mapping AND >=5 owners in the
    latest period. Tests skip if no such master exists (e.g. before the
    matcher has been run)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # First check the mapping table even exists -- skip otherwise
            cur.execute(
                """
                SELECT to_regclass('sec_13f_issuer_master_map') AS exists
                """
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return 0
            cur.execute(
                """
                SELECT m.master_id
                FROM sec_13f_issuer_master_map m
                JOIN sec_13f_holdings h ON h.name_of_issuer_norm = m.name_of_issuer_norm
                JOIN sec_13f_submissions s ON s.accession_number = h.accession_number
                GROUP BY m.master_id
                HAVING COUNT(DISTINCT s.filer_cik) >= 5
                ORDER BY COUNT(DISTINCT s.filer_cik) DESC, m.master_id
                LIMIT 1
                """
            )
            r = cur.fetchone()
            return int(r[0]) if r else 0
    finally:
        conn.close()


def _get_unmatched_master() -> int:
    """Pick a master with NO 13F issuer mapping. Most masters fall here
    (private companies, name-mismatched public)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT to_regclass('sec_13f_issuer_master_map') AS exists
                """
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                # Map table doesn't exist yet -- pick any master; endpoint
                # should still work (no rows, no_matched=False path).
                cur.execute("SELECT master_id FROM master_employers ORDER BY master_id LIMIT 1")
                r = cur.fetchone()
                return int(r[0]) if r else 0
            cur.execute(
                """
                SELECT m.master_id
                FROM master_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM sec_13f_issuer_master_map mm
                    WHERE mm.master_id = m.master_id
                )
                  AND m.source_origin = 'f7'
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            r = cur.fetchone()
            return int(r[0]) if r else 0
    finally:
        conn.close()


def test_institutional_owners_404_on_unknown_master(client):
    r = client.get("/api/employers/master/999999999/institutional-owners")
    assert r.status_code == 404


def test_institutional_owners_not_matched_returns_empty_shape(client):
    """Master with no 13F issuer mapping returns is_matched=false, NOT 404."""
    master_id = _get_unmatched_master()
    if master_id == 0:
        pytest.skip("No unmatched master available")
    r = client.get(f"/api/employers/master/{master_id}/institutional-owners")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "owners" in data
    s = data["summary"]
    assert s["is_matched"] is False
    assert s["total_owners"] == 0
    assert data["owners"] == []


def test_institutional_owners_populated_shape(client):
    master_id = _get_matched_master()
    if master_id == 0:
        pytest.skip(
            "No matched master with >=5 owners; matcher likely not yet run"
        )
    r = client.get(f"/api/employers/master/{master_id}/institutional-owners")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    assert s["is_matched"] is True
    assert s["issuer_name_used"]
    assert s["match_method"] in ("exact", "trigram")
    assert s["total_owners"] >= 5
    assert s["latest_period"]
    assert isinstance(data["owners"], list)
    assert len(data["owners"]) > 0

    # Owners ordered by value DESC.
    values = [o["value"] for o in data["owners"]]
    assert values == sorted(values, reverse=True)

    # Per-row shape sanity.
    o0 = data["owners"][0]
    for k in ("filer_name", "filer_cik", "filer_state", "value", "shares",
              "share_type", "investment_discretion", "period_of_report"):
        assert k in o0, f"missing key {k}"


def test_institutional_owners_limit_truncates_only_array(client):
    master_id = _get_matched_master()
    if master_id == 0:
        pytest.skip("No matched master available")
    full = client.get(
        f"/api/employers/master/{master_id}/institutional-owners?limit=200"
    ).json()
    if full["summary"]["total_owners"] < 3:
        pytest.skip("Need >=3 owners to test truncation")

    truncated = client.get(
        f"/api/employers/master/{master_id}/institutional-owners?limit=2"
    ).json()
    assert len(truncated["owners"]) == 2
    # Summary aggregates across the FULL match set.
    assert truncated["summary"]["total_owners"] == full["summary"]["total_owners"]
    assert truncated["summary"]["total_value"] == full["summary"]["total_value"]


def test_institutional_owners_limit_validation(client):
    master_id = _get_matched_master()
    if master_id == 0:
        pytest.skip("No matched master available")
    r = client.get(
        f"/api/employers/master/{master_id}/institutional-owners?limit=0"
    )
    assert r.status_code == 422
    r = client.get(
        f"/api/employers/master/{master_id}/institutional-owners?limit=500"
    )
    assert r.status_code == 422
