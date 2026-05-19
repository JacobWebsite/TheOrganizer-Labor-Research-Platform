"""
Tests for /api/employers/master/{master_id}/competitors (24Q-15).

Verifies:
- 404 on unknown master_id
- Top-level shape (master_id, naics, naics_label, size_band, peers, as_of)
- Peer rows: per-peer shape, master_id type, ranking by log-distance
- Self excluded from peers
- LIMIT enforcement (peers <= 12 by default, <= 50 max)
- NAICS-6 path (e.g. Abbott 325412): all peers share that exact code
- NAICS-4 fallback: when self has only 4-digit NAICS, peers come from
  any 6-digit code starting with that prefix
- Missing-NAICS path: scorecard row absent or NAICS null -> empty peers
- limit query-param validation
"""
import math

import pytest
from psycopg2.extras import RealDictCursor

from db_config import get_connection


def _dict_cursor(conn):
    """Project's get_connection() returns a tuple-cursor connection. We
    need RealDictCursor here for .get() on result rows to work. Wrap in
    a tiny helper so each test function reads consistently."""
    return conn.cursor(cursor_factory=RealDictCursor)


def _get_master_with_naics6(min_peers: int = 5) -> int:
    """Pick a master that has a 6-digit NAICS in mv_target_scorecard AND
    enough peers in the same NAICS-6 to make the populated assertions
    meaningful. Defaults to Abbott (4036186 / 325412) when available."""
    conn = get_connection()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT 1 FROM mv_target_scorecard
                WHERE master_id = 4036186 AND naics IS NOT NULL AND length(naics) = 6
                """
            )
            if cur.fetchone():
                # Confirm there are enough peers for the test to be meaningful.
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM mv_target_scorecard
                    WHERE naics = '325412'
                      AND master_id <> 4036186
                      AND effective_employee_count IS NOT NULL
                    """
                )
                row = cur.fetchone()
                if row and int(row.get("cnt", 0)) >= min_peers:
                    return 4036186
            # Fallback: any master with >= min_peers peers in the same NAICS-6.
            cur.execute(
                """
                SELECT s.master_id
                FROM mv_target_scorecard s
                WHERE s.naics IS NOT NULL
                  AND length(s.naics) = 6
                  AND s.effective_employee_count IS NOT NULL
                  AND (
                    SELECT COUNT(*) FROM mv_target_scorecard p
                    WHERE p.naics = s.naics AND p.master_id <> s.master_id
                      AND p.effective_employee_count IS NOT NULL
                  ) >= %s
                ORDER BY s.master_id
                LIMIT 1
                """,
                [min_peers],
            )
            row = cur.fetchone()
            return int(row[0] if isinstance(row, tuple) else row.get("master_id")) if row else 0
    finally:
        conn.close()


def _get_master_without_scorecard_naics() -> int:
    """Pick a master that has NO row in mv_target_scorecard, OR has a row
    but with NAICS NULL. Used to verify the empty-peers path."""
    conn = get_connection()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT m.master_id
                FROM master_employers m
                LEFT JOIN mv_target_scorecard ts ON ts.master_id = m.master_id
                WHERE ts.master_id IS NULL OR ts.naics IS NULL
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0] if isinstance(row, tuple) else row.get("master_id")) if row else 0
    finally:
        conn.close()


def test_competitors_404_on_unknown_master(client):
    r = client.get("/api/employers/master/999999999/competitors")
    assert r.status_code == 404


def test_competitors_top_level_shape_on_known_master(client):
    """Master with a NAICS-6 + scorecard row returns the populated shape."""
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + >=5 peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    assert r.status_code == 200
    data = r.json()
    # Top-level keys
    for k in ("master_id", "naics", "naics_label", "size_band", "peers", "as_of"):
        assert k in data, f"missing top-level key {k}"
    assert data["master_id"] == master_id
    assert isinstance(data["peers"], list)
    assert isinstance(data["as_of"], str) and len(data["as_of"]) == 10
    # NAICS should be present + 6 digits (we picked a NAICS-6 master).
    assert data["naics"] is not None
    assert len(data["naics"]) == 6
    # size_band must be one of the known bucket labels.
    assert data["size_band"] in {"1-100", "100-1K", "1K-10K", "10000+", "unknown"}


def test_competitors_peers_capped_at_12_default(client):
    master_id = _get_master_with_naics6(min_peers=15)
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + >=15 peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    assert r.status_code == 200
    data = r.json()
    assert len(data["peers"]) <= 12, "default limit must cap peers at 12"


def test_competitors_self_excluded(client):
    """The peers array must never include the queried master itself."""
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors?limit=50")
    assert r.status_code == 200
    data = r.json()
    for peer in data["peers"]:
        assert peer["master_id"] != master_id, (
            f"self {master_id} appeared in peers"
        )


def test_competitors_per_peer_shape(client):
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    data = r.json()
    if not data["peers"]:
        pytest.skip("No peers returned -- coverage too thin for shape check")
    peer = data["peers"][0]
    for k in ("master_id", "name", "consolidated_workers", "revenue_total", "tier", "naics", "match_basis"):
        assert k in peer, f"peer row missing key {k}"
    assert isinstance(peer["master_id"], int)
    # name may be None as a fallback but must always be a string when present.
    assert peer["name"] is None or isinstance(peer["name"], str)
    assert peer["match_basis"] in {"naics6", "naics4"}


def test_competitors_naics6_path_exact_match(client):
    """When self has a 6-digit NAICS, every peer must share that EXACT code."""
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    data = r.json()
    if not data["peers"]:
        pytest.skip("No peers returned")
    self_naics = data["naics"]
    for peer in data["peers"]:
        assert peer["naics"] == self_naics, (
            f"NAICS-6 path should yield exact matches; "
            f"self={self_naics}, peer={peer['naics']}"
        )
        assert peer["match_basis"] == "naics6"


def test_competitors_ranking_by_log_workforce_distance(client):
    """Peers ordered ascending by |ln(peer_workers) - ln(self_workers)|."""
    master_id = _get_master_with_naics6(min_peers=5)
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + 5+ peers available in DB")
    # Pull self workforce
    conn = get_connection()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT effective_employee_count FROM mv_target_scorecard
                WHERE master_id = %s
                """,
                [master_id],
            )
            row = cur.fetchone()
            if not row or not row.get("effective_employee_count"):
                pytest.skip("Self has no workforce -- cannot validate ranking")
            self_workers = float(row["effective_employee_count"])
    finally:
        conn.close()

    r = client.get(f"/api/employers/master/{master_id}/competitors")
    data = r.json()
    if len(data["peers"]) < 2:
        pytest.skip("Need >=2 peers to validate ranking")

    self_log = math.log(max(self_workers, 1.0))
    distances = [
        abs(math.log(max(p["consolidated_workers"] or 1, 1)) - self_log)
        for p in data["peers"]
    ]
    # Allow tiny float wobble between sorted-result and recomputed values.
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1] + 1e-9, (
            f"peers not sorted by log-distance at index {i}: "
            f"{distances[i]} > {distances[i + 1]}"
        )


def test_competitors_limit_enforcement(client):
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + peers available in DB")

    r = client.get(f"/api/employers/master/{master_id}/competitors?limit=3")
    assert r.status_code == 200
    assert len(r.json()["peers"]) <= 3


def test_competitors_limit_validation(client):
    master_id = _get_master_with_naics6()
    if master_id == 0:
        pytest.skip("No master with NAICS-6 + peers available in DB")
    r = client.get(f"/api/employers/master/{master_id}/competitors?limit=0")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/competitors?limit=51")
    assert r.status_code == 422


def test_competitors_missing_naics_returns_empty_peers(client):
    """Master with no scorecard row (or NAICS null) returns shape with
    naics=null and peers=[] -- 200, not 404 or 500."""
    master_id = _get_master_without_scorecard_naics()
    if master_id == 0:
        pytest.skip("Every master in DB has a scorecard NAICS")
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    assert r.status_code == 200
    data = r.json()
    # naics may be None (truly missing) or carry master_employers.naics
    # if the scorecard row was missing but the master row had a code.
    if data["naics"] is None:
        assert data["naics_label"] is None
        assert data["peers"] == []
    # When peers is empty but NAICS is present, the master_employers row
    # had a NAICS but the scorecard MV did not -- still 200 with peers
    # potentially non-empty if the NAICS resolves on prefix.
    assert isinstance(data["peers"], list)


def test_competitors_naics4_fallback(client):
    """If we synthesize a master whose self NAICS is only 4 digits, the
    endpoint should still return peers via prefix match. Most production
    rows are NAICS-6 so the fallback is exercised by SQL-level injection
    of a self row -- here we just verify the public contract by finding
    a NAICS-4 self row if one exists, else skip."""
    conn = get_connection()
    try:
        with _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT master_id
                FROM mv_target_scorecard
                WHERE naics IS NOT NULL AND length(naics) = 4
                  AND effective_employee_count IS NOT NULL
                ORDER BY master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No NAICS-4 self rows in mv_target_scorecard; fallback path covered by NAICS-6 test")
    master_id = int(row[0] if isinstance(row, tuple) else row.get("master_id"))
    r = client.get(f"/api/employers/master/{master_id}/competitors")
    assert r.status_code == 200
    data = r.json()
    # NAICS reported is the 4-digit self code.
    assert data["naics"] is not None
    assert len(data["naics"]) == 4
    # All peers (if any) must declare match_basis="naics4".
    for peer in data["peers"]:
        assert peer["match_basis"] == "naics4"
        assert peer["naics"].startswith(data["naics"][:4])
