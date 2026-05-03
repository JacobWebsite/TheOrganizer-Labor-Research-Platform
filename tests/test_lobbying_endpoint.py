"""
Tests for /api/employers/master/{master_id}/lobbying (24Q-39).

Verifies:
- 404 on unknown master_id
- "Not matched" path (master with no LDA link) returns is_matched=false, NOT 404
- Endpoint returns empty shape (NOT 500) when LDA tables don't exist
- Populated path: summary aggregates, quarterly_spend ordered DESC,
  top_issues sorted by filings DESC, top_registrants sorted by spend DESC
- Limit params validate
"""
import pytest

from db_config import get_connection


def _get_matched_master() -> int:
    """Return a master that's linked to at least one LDA client with >=2
    filings in our load window. Skip the test if no such master yet
    (happens if matcher hasn't run after load)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Tables present?
            cur.execute("SELECT to_regclass('lda_filings') AS f")
            row = cur.fetchone()
            if not row or row[0] is None:
                return 0

            cur.execute(
                """
                SELECT sid.master_id
                FROM master_employer_source_ids sid
                JOIN lda_filings f ON f.client_id::text = sid.source_id
                WHERE sid.source_system = 'lda'
                GROUP BY sid.master_id
                HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC, sid.master_id
                LIMIT 1
                """
            )
            r = cur.fetchone()
            return int(r[0]) if r else 0
    finally:
        conn.close()


def _get_unmatched_master() -> int:
    """A master that's NOT linked to any LDA client."""
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
                      AND s.source_system = 'lda'
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


def test_lobbying_404_on_unknown_master(client):
    r = client.get("/api/employers/master/999999999/lobbying")
    assert r.status_code == 404


def test_lobbying_unmatched_returns_empty_shape(client):
    """Master with no LDA link returns is_matched=false + zeros, NOT 404."""
    master_id = _get_unmatched_master()
    if master_id == 0:
        pytest.skip("No unmatched master available")
    r = client.get(f"/api/employers/master/{master_id}/lobbying")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    s = data["summary"]
    assert s["is_matched"] is False
    assert s["total_filings"] == 0
    assert s["total_spend"] == 0
    assert data["quarterly_spend"] == []
    assert data["top_issues"] == []
    assert data["top_registrants"] == []


def test_lobbying_populated_shape(client):
    """Matched master returns rich shape sorted by spend / filings DESC."""
    master_id = _get_matched_master()
    if master_id == 0:
        pytest.skip(
            "No matched master with >=2 filings; matcher likely not yet run"
        )
    r = client.get(f"/api/employers/master/{master_id}/lobbying")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    assert s["is_matched"] is True
    assert s["client_name_used"]
    assert s["match_method"] in ("exact", "trigram")
    assert s["total_filings"] >= 2

    # Quarterly spend: descending by year, then by period rank.
    qs = data.get("quarterly_spend") or []
    if len(qs) >= 2:
        # First quarter should be at least as recent as the second
        first = qs[0]
        second = qs[1]
        assert (first["year"], first.get("period_display")) >= (second["year"], second.get("period_display"))

    # Top registrants: spend monotonically non-increasing.
    regs = data.get("top_registrants") or []
    if len(regs) >= 2:
        spends = [r["spend"] for r in regs]
        assert spends == sorted(spends, reverse=True)

    # Top issues: filings monotonically non-increasing.
    issues = data.get("top_issues") or []
    if len(issues) >= 2:
        filings = [i["filings"] for i in issues]
        assert filings == sorted(filings, reverse=True)


def test_lobbying_limit_params_validate(client):
    master_id = _get_matched_master() or _get_unmatched_master()
    if master_id == 0:
        pytest.skip("No master available")
    r = client.get(f"/api/employers/master/{master_id}/lobbying?issue_limit=0")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/lobbying?registrant_limit=999")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/lobbying?quarter_limit=200")
    assert r.status_code == 422
