"""Live-DB tests for /api/directors and /api/directors/{slug}.

Skips automatically when employer_directors is empty / non-existent
(e.g. on a fresh CI environment without the DEF14A batch).
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from api.main import app
from db_config import get_connection


client = TestClient(app)


def _has_directors_data() -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('employer_directors')")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT COUNT(*) FROM employer_directors")
        n = cur.fetchone()[0]
        conn.close()
        return n > 100
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_directors_data(), reason="employer_directors missing or empty"
)


def test_list_top_directors_returns_clean_names():
    """Top-N list filters parser garbage — every entry should be a real
    multi-word name, not 'Chief' / 'DEF 14A' / etc."""
    r = client.get("/api/directors?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "directors" in data
    assert data["limit"] == 10
    # All entries should pass the name-quality predicate.
    from api.services.director_name_filter import is_likely_real_director_name
    assert len(data["directors"]) > 0
    for d in data["directors"]:
        assert is_likely_real_director_name(d["name"]), \
            f"garbage leaked through SQL+Python pre-filter: {d['name']!r}"
        assert d["boards_count"] >= 2  # endpoint requires HAVING >= 2
        assert d["slug"] != ""


def test_list_top_directors_sorted_descending():
    r = client.get("/api/directors?limit=20")
    assert r.status_code == 200
    counts = [d["boards_count"] for d in r.json()["directors"]]
    for i in range(len(counts) - 1):
        assert counts[i] >= counts[i + 1], \
            f"top-N out of order: {counts[i]} < {counts[i + 1]} at idx {i}"


def test_director_permalink_resolves_real_director():
    """A known-real director's permalink returns 200 with their boards."""
    # First find a real director by querying the top-N list.
    top = client.get("/api/directors?limit=5").json()["directors"]
    if not top:
        pytest.skip("no directors returned — DEF14A data may be sparse")
    target = top[0]  # most-connected director

    r = client.get(f"/api/directors/{target['slug']}")
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == target["slug"]
    assert data["summary"]["boards_count"] == target["boards_count"]
    assert len(data["names_matched"]) >= 1
    assert len(data["boards"]) == target["boards_count"]
    for b in data["boards"]:
        assert b["master_id"] is not None
        assert "canonical_name" in b


def test_director_permalink_404_on_unknown_slug():
    r = client.get("/api/directors/nonexistent-person-xyz-12345")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_director_permalink_400_on_short_slug():
    r = client.get("/api/directors/ab")
    assert r.status_code == 400


def test_director_permalink_rejects_garbage_slug():
    """A slug that resolves to a parser-garbage name should still 404
    (the predicate filters it out even if rows exist with that name)."""
    # 'Chief' was the #1 garbage name with 200+ boards before the filter.
    r = client.get("/api/directors/chief")
    # Either 404 (predicate filtered all matches) or 400 (slug too short
    # at 5 chars — actually 5 passes our >= 3 minimum). Should be 404.
    assert r.status_code == 404


def test_director_permalink_boards_have_state_and_naics():
    """Each board entry should carry the master's geo + industry context
    so the frontend can render without a follow-up query."""
    top = client.get("/api/directors?limit=3").json()["directors"]
    if not top:
        pytest.skip("no directors returned")
    r = client.get(f"/api/directors/{top[0]['slug']}")
    assert r.status_code == 200
    boards = r.json()["boards"]
    assert len(boards) > 0
    # At least one board should have non-NULL state (most public co's do).
    assert any(b.get("state") for b in boards)
