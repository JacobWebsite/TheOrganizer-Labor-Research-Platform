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
