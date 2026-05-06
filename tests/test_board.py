"""Tests for /api/employers/master/{master_id}/board (24Q-14).

Live-data tests against the local DB. Each test self-skips if the
employer_directors table is empty.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.board import _truncate
from db_config import get_connection


client = TestClient(app)


def _has_director_data() -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('employer_directors')")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT COUNT(*) FROM employer_directors")
        n = cur.fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def _interlock_master_pair():
    """Find a master with at least one interlock for testing."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('director_interlocks')")
        if not cur.fetchone()[0]:
            return None
        cur.execute(
            "SELECT master_id_a, master_id_b FROM director_interlocks LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        return row if row else None
    except Exception:
        return None


# ---- Pure helper tests ----


def test_truncate_short_string_unchanged():
    assert _truncate("hello") == "hello"


def test_truncate_long_string_ellipsised():
    s = "x" * 500
    out = _truncate(s, n=50)
    assert len(out) == 50
    assert out.endswith("…")


def test_truncate_none_returns_none():
    assert _truncate(None) is None
    assert _truncate("") is None


# ---- Endpoint tests ----


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_unknown_master_returns_404():
    r = client.get("/api/employers/master/999999999/board")
    assert r.status_code == 404


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_endpoint_shape_for_known_master_with_directors():
    # Abbott (master 4036186) was confirmed to have 12 directors
    r = client.get("/api/employers/master/4036186/board")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "directors" in data
    assert "interlocks" in data
    summary = data["summary"]
    for key in (
        "is_matched",
        "director_count",
        "independent_count",
        "fiscal_year",
        "parse_strategy",
        "source_url",
        "extracted_at",
    ):
        assert key in summary, f"missing key: {key}"
    # Sanity: Abbott should have a non-trivial roster
    assert summary["director_count"] >= 5
    assert summary["is_matched"] is True


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_director_row_shape_complete():
    r = client.get("/api/employers/master/4036186/board")
    assert r.status_code == 200
    directors = r.json()["directors"]
    assert len(directors) > 0
    d = directors[0]
    for key in (
        "name",
        "age",
        "position",
        "since_year",
        "occupation",
        "is_independent",
        "committees",
        "compensation_total",
        "fiscal_year",
        "parse_strategy",
    ):
        assert key in d, f"missing key: {key}"
    assert isinstance(d["committees"], list)


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_endpoint_returns_unmatched_for_master_without_directors():
    # Find a master that has no director rows
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.master_id FROM master_employers m
        WHERE NOT EXISTS (
          SELECT 1 FROM employer_directors d WHERE d.master_id = m.master_id
        )
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("No master without directors found")
    r = client.get(f"/api/employers/master/{row[0]}/board")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["is_matched"] is False
    assert data["summary"]["director_count"] == 0
    assert data["directors"] == []
    assert data["interlocks"] == []


@pytest.mark.skipif(
    _interlock_master_pair() is None, reason="no director_interlocks rows"
)
def test_interlocks_appear_bidirectionally():
    pair = _interlock_master_pair()
    a, b = pair[0], pair[1]
    r_a = client.get(f"/api/employers/master/{a}/board")
    r_b = client.get(f"/api/employers/master/{b}/board")
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    # Each side should reference the OTHER master
    interlocks_a = r_a.json()["interlocks"]
    interlocks_b = r_b.json()["interlocks"]
    assert len(interlocks_a) > 0
    assert len(interlocks_b) > 0
    other_ids_a = {il["other_master_id"] for il in interlocks_a}
    other_ids_b = {il["other_master_id"] for il in interlocks_b}
    assert b in other_ids_a, f"master {a} should see {b} as interlock"
    assert a in other_ids_b, f"master {b} should see {a} as interlock"


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_limit_respected():
    r = client.get("/api/employers/master/4036186/board?limit=3")
    assert r.status_code == 200
    assert len(r.json()["directors"]) <= 3


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_summary_counts_are_full_roster_not_limit():
    # Codex finding 2026-05-04: summary aggregates were computed from the
    # limited roster query, so a small limit reported a small director_count.
    # Now they're computed from a separate aggregate over ALL rows.
    # Abbott has 12 directors -- with limit=3, summary.director_count must
    # still be 12, not 3.
    r_small = client.get("/api/employers/master/4036186/board?limit=3")
    r_full = client.get("/api/employers/master/4036186/board?limit=50")
    assert r_small.status_code == 200
    assert r_full.status_code == 200
    s_small = r_small.json()["summary"]
    s_full = r_full.json()["summary"]
    # Summary counts must be identical regardless of page size
    assert s_small["director_count"] == s_full["director_count"], (
        f"director_count drifted with limit: small={s_small['director_count']} "
        f"full={s_full['director_count']}"
    )
    assert s_small["independent_count"] == s_full["independent_count"]
    # Directors array DOES respect the limit
    assert len(r_small.json()["directors"]) <= 3
    assert len(r_full.json()["directors"]) == s_full["director_count"]


# ---------------------------------------------------------------------------
# C.4 Enforcement-risk per director (added 2026-05-06)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_each_director_carries_enforcement_risk_or_null():
    """Every director row must carry either an enforcement_risk dict or
    None. None means the director sits on no other tracked boards (no
    overlap signal); a dict means risk score + components were computed."""
    r = client.get("/api/employers/master/4036186/board")
    assert r.status_code == 200
    for d in r.json()["directors"]:
        # Key exists on every row
        assert "enforcement_risk" in d
        er = d["enforcement_risk"]
        if er is None:
            continue
        # Schema check
        assert "other_boards_count" in er
        assert "risk_score" in er
        assert "risk_tier" in er
        assert "components" in er
        assert er["risk_tier"] in {"GREEN", "YELLOW", "RED"}
        assert er["other_boards_count"] >= 1
        assert er["risk_score"] >= 0
        for k in ("osha_violations", "nlrb_ulps", "whd_backwages", "osha_penalties"):
            assert k in er["components"]


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_enforcement_risk_tiers_calibrated():
    """Tier thresholds: GREEN < 20 <= YELLOW < 100 <= RED."""
    r = client.get("/api/employers/master/4036186/board")
    for d in r.json()["directors"]:
        er = d.get("enforcement_risk")
        if er is None:
            continue
        score = er["risk_score"]
        tier = er["risk_tier"]
        if tier == "GREEN":
            assert score < 20, f"GREEN with score {score}"
        elif tier == "YELLOW":
            assert 20 <= score < 100, f"YELLOW with score {score}"
        elif tier == "RED":
            assert score >= 100, f"RED with score {score}"


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_garbage_director_names_get_no_risk_computation():
    """Parser-garbage names ("Chief", "DEF 14A", etc) are filtered out
    of the risk-score query at the Python level. They MAY still appear
    in the directors array (the page-level filter doesn't drop them
    here — that's the directors-permalink filter's job) but their
    enforcement_risk should always be None.

    This is a regression guard: without the filter, "DEF 14A" with 169
    boards would dominate every BoardCard with a fake YELLOW/RED chip.
    """
    # Pick any master that has directors
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT master_id FROM employer_directors
        WHERE director_name IN ('Chief', 'DEF 14A', 'Continuing Directors')
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("no master with garbage-name directors found")
    mid = row["master_id"] if isinstance(row, dict) else row[0]
    r = client.get(f"/api/employers/master/{mid}/board")
    assert r.status_code == 200
    bad_names = {"Chief", "DEF 14A", "Continuing Directors"}
    for d in r.json()["directors"]:
        if d["name"] in bad_names:
            assert d.get("enforcement_risk") is None, (
                f"garbage name {d['name']!r} got risk computed: {d['enforcement_risk']}"
            )
