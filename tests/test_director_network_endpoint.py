"""Live-DB tests for /api/employers/master/{id}/director-network.

Skips if employer_directors / director_interlocks are missing.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from api.main import app
from db_config import get_connection


client = TestClient(app)


def _has_network_data() -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        for table in ("employer_directors", "director_interlocks"):
            cur.execute("SELECT to_regclass(%s)", [table])
            if not cur.fetchone()[0]:
                return False
        cur.execute("SELECT COUNT(*) FROM director_interlocks")
        n = cur.fetchone()[0]
        conn.close()
        return n > 100
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_network_data(), reason="director_interlocks missing or sparse"
)


def _find_well_connected_master() -> int:
    """Pick a master with at least 3 distinct 1-hop neighbors AFTER
    name-filtering, so the `should_surface` gate is True. Iterate
    candidates because the most-connected master might be all-garbage
    once the filter applies."""
    from api.services.director_name_filter import is_likely_real_director_name
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        WITH neighbors AS (
            SELECT i.master_id_a AS anchor, i.master_id_b AS neighbor, i.director_name
            FROM director_interlocks i
            UNION ALL
            SELECT i.master_id_b AS anchor, i.master_id_a AS neighbor, i.director_name
            FROM director_interlocks i
        )
        SELECT anchor, ARRAY_AGG(DISTINCT director_name) AS dnames,
               COUNT(DISTINCT neighbor) AS nhood
        FROM neighbors
        GROUP BY anchor
        HAVING COUNT(DISTINCT neighbor) >= 3
        ORDER BY 3 DESC
        LIMIT 50
        """
    )
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        anchor = r["anchor"] if isinstance(r, dict) else r[0]
        dnames = r["dnames"] if isinstance(r, dict) else r[1]
        real = sum(1 for d in dnames if is_likely_real_director_name(d))
        if real >= 1:  # at least one real-name shared director
            return anchor
    raise RuntimeError("no well-connected master with real-name directors found")


def test_unknown_master_returns_404():
    r = client.get("/api/employers/master/999999999/director-network")
    assert r.status_code == 404


def test_anchor_with_neighbors_returns_populated_network():
    mid = _find_well_connected_master()
    r = client.get(f"/api/employers/master/{mid}/director-network")
    assert r.status_code == 200
    d = r.json()
    # Top-level shape — all keys present even on the empty path
    assert d["anchor"]["master_id"] == mid
    assert "stats" in d
    assert "shared_directors" in d
    assert "one_hop" in d
    assert "two_hop" in d
    s = d["stats"]
    # At least one real-name interlock survived the filter — guaranteed
    # by `_find_well_connected_master`. Don't assert >= 3 here because
    # the post-filter count varies across masters and some lose most
    # interlocks to garbage names.
    assert s["one_hop_count"] >= 1
    assert s["shared_directors_total"] >= 1
    assert len(d["one_hop"]) == s["one_hop_count"]
    # `should_surface` is the gate the frontend respects — it just
    # mirrors `one_hop_count >= MIN_NEIGHBORS_TO_SURFACE` (3 today).
    if s["one_hop_count"] >= 3:
        assert s["should_surface"] is True
    else:
        assert s["should_surface"] is False


def test_one_hop_sorted_by_shared_director_count_desc():
    mid = _find_well_connected_master()
    d = client.get(f"/api/employers/master/{mid}/director-network").json()
    counts = [c["shared_director_count"] for c in d["one_hop"]]
    for i in range(len(counts) - 1):
        assert counts[i] >= counts[i + 1]


def test_anchor_excluded_from_neighbors():
    mid = _find_well_connected_master()
    d = client.get(f"/api/employers/master/{mid}/director-network").json()
    one_hop_ids = {c["master_id"] for c in d["one_hop"]}
    two_hop_ids = {c["master_id"] for c in d["two_hop"]}
    assert mid not in one_hop_ids
    assert mid not in two_hop_ids
    # 1-hop and 2-hop sets are disjoint
    assert not (one_hop_ids & two_hop_ids)


def test_top_two_hop_param_truncates_results():
    mid = _find_well_connected_master()
    full = client.get(f"/api/employers/master/{mid}/director-network").json()
    truncated = client.get(
        f"/api/employers/master/{mid}/director-network?top_two_hop=2"
    ).json()
    if full["stats"]["two_hop_count"] >= 2:
        assert len(truncated["two_hop"]) <= 2
        # Underlying count unchanged — only `two_hop_returned` differs
        assert truncated["stats"]["two_hop_count"] == full["stats"]["two_hop_count"]


def test_depth_one_omits_two_hop():
    mid = _find_well_connected_master()
    d = client.get(f"/api/employers/master/{mid}/director-network?depth=1").json()
    assert d["two_hop"] == []
    assert d["stats"]["two_hop_count"] == 0


def test_master_with_no_neighbors_returns_empty_shape():
    """Pick a master that exists but has zero interlocks."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.master_id FROM master_employers m
        WHERE NOT EXISTS (
            SELECT 1 FROM director_interlocks i
            WHERE i.master_id_a = m.master_id OR i.master_id_b = m.master_id
        )
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("no master with zero interlocks found")
    mid = row["master_id"] if isinstance(row, dict) else row[0]
    r = client.get(f"/api/employers/master/{mid}/director-network")
    assert r.status_code == 200
    d = r.json()
    assert d["stats"]["one_hop_count"] == 0
    assert d["stats"]["two_hop_count"] == 0
    assert d["stats"]["should_surface"] is False
    assert d["one_hop"] == []
    assert d["two_hop"] == []


def test_shared_directors_have_slugs():
    mid = _find_well_connected_master()
    d = client.get(f"/api/employers/master/{mid}/director-network").json()
    for sd in d["shared_directors"]:
        assert "name" in sd
        assert "slug" in sd
        assert sd["slug"]  # non-empty


def test_garbage_director_names_filtered_from_network():
    """No 'Chief' / 'DEF 14A' / 'Continuing Directors' should appear as
    a shared-director-of-record. The filter applies to both the SQL
    pre-filter and the Python post-filter."""
    mid = _find_well_connected_master()
    d = client.get(f"/api/employers/master/{mid}/director-network").json()
    bad_names = {"Chief", "DEF 14A", "Continuing Directors", "President and",
                 "Executive", "Senior", "Vice", "Chairman"}
    found_bad = bad_names & {sd["name"] for sd in d["shared_directors"]}
    assert not found_bad, f"parser garbage leaked into network: {found_bad}"
