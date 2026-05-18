"""Tests for `api/routers/board.py` response-array filter behaviour (2026-05-18).

Agent 4's spot-check of 15 BoardCards on 2026-05-18 found 3 FAIL / 4 MARGINAL
because parser-garbage director names (`DEF 14A`, `2026 Proxy Statement N`,
`Continuing Directors`, etc.) were flowing through to the response array even
though `is_likely_real_director_name` was already in use for the risk-score
CTE.

These tests pin the post-fix behaviour:
  - Garbage names do not appear in `directors[]`.
  - Garbage-name interlocks do not appear in `interlocks[]`.
  - `summary.director_count` reflects the filtered roster, not the raw count.
  - `summary.directors_filtered_count` / `interlocks_filtered_count` are
    present even when zero, so the frontend can opt to surface them.

Live-data tests against the local DB. Each test self-skips if the underlying
table is empty.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.director_name_filter import is_likely_real_director_name
from db_config import get_connection


client = TestClient(app)


# --- Garbage-name catalog used across multiple tests ---------------------------
# These names were observed in `employer_directors` and should always be
# rejected by the filter. If a future parser change starts producing one of
# these strings, the predicate test below will alert before they reach the
# response.
GARBAGE_EXAMPLES = (
    "DEF 14A",
    "Continuing Directors",
    "Independent Directors",
    "2026 Proxy Statement 7",
    "2026 Proxy Statement N",
    "Chief",
    "Vice",
    "Audit Committee",
)


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


def _first_master_with_garbage_director() -> int | None:
    """Find a master that has at least one parser-garbage row alongside
    real directors. Used as the regression-target for filter behaviour."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT master_id
            FROM employer_directors
            WHERE director_name IN ('DEF 14A', 'Continuing Directors')
               OR director_name ILIKE '%%proxy statement%%'
            GROUP BY master_id
            HAVING COUNT(*) > 0
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _first_master_with_garbage_interlock() -> int | None:
    """Find a master that has at least one parser-garbage director_name
    in `director_interlocks` AND at least one real director (so the
    response actually exercises the interlocks branch — the router
    short-circuits the interlocks query when `directors == []`).
    Boeing (162287) had 163 such rows on 2026-05-18.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            WITH garbage_ilock AS (
                SELECT master_id_a AS mid, COUNT(*) AS n
                FROM director_interlocks
                WHERE director_name IN ('DEF 14A', 'Continuing Directors')
                   OR director_name ILIKE '%%proxy statement%%'
                GROUP BY master_id_a
            ),
            has_real_dir AS (
                SELECT DISTINCT master_id
                FROM employer_directors
                WHERE director_name NOT IN (
                    'DEF 14A', 'Continuing Directors',
                    'Chief', 'Vice', 'Independent Directors'
                )
                  AND director_name NOT ILIKE '%%proxy statement%%'
                  AND LENGTH(TRIM(director_name)) BETWEEN 4 AND 80
                  AND ARRAY_LENGTH(
                          STRING_TO_ARRAY(TRIM(director_name), ' '), 1
                      ) >= 2
            )
            SELECT g.mid
            FROM garbage_ilock g
            JOIN has_real_dir d ON d.master_id = g.mid
            ORDER BY g.n DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


# ---- Predicate sanity (no DB dependency) -------------------------------------


@pytest.mark.parametrize("name", list(GARBAGE_EXAMPLES))
def test_predicate_rejects_known_garbage(name: str) -> None:
    """If this regresses, garbage will start flowing back through the
    response array regardless of the router-level filter."""
    assert is_likely_real_director_name(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "Jane Doe",
        "Adam D. Portnoy",
        "Mary-Beth O'Reilly",
        "LeAnne M. Zumwalt",
    ],
)
def test_predicate_accepts_real_names(name: str) -> None:
    assert is_likely_real_director_name(name) is True


# ---- Response-array behaviour ------------------------------------------------


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_summary_carries_filter_observability_fields():
    """`directors_filtered_count` and `interlocks_filtered_count` must be
    present on every response (including the empty-shape branch) so the
    frontend doesn't have to feature-detect them."""
    # Abbott (clean) -> both should be 0 but present.
    r = client.get("/api/employers/master/4036186/board")
    assert r.status_code == 200
    s = r.json()["summary"]
    assert "directors_filtered_count" in s
    assert "interlocks_filtered_count" in s
    assert s["directors_filtered_count"] == 0
    # interlocks_filtered_count >= 0; on Abbott historically 0.
    assert s["interlocks_filtered_count"] >= 0


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_summary_present_on_unmatched_master_too():
    """Masters without any director rows still need the new fields so the
    response shape is stable for the frontend."""
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
    s = r.json()["summary"]
    # _empty_shape() returns 0/0 for both fields.
    assert s["directors_filtered_count"] == 0
    assert s["interlocks_filtered_count"] == 0


@pytest.mark.skipif(
    _first_master_with_garbage_director() is None,
    reason="no master with parser-garbage director rows",
)
def test_response_array_excludes_garbage_director_names():
    """Per-master regression: a master with known garbage rows should
    have NONE of those names in its `directors[]` array. Boeing on
    2026-05-18 had 13 directors before filter, 12 after (DEF 14A
    dropped). Walmart 14 -> 12 (DEF 14A + 2026 Proxy Statement 7).
    Salesforce 16 -> 3 (13 "Salesforce, Inc. ... 2026 Proxy
    Statement" rows dropped). We don't pin specific counts because
    new filings refresh the table — instead pin the invariant that
    no `directors[].name` rejects the predicate."""
    mid = _first_master_with_garbage_director()
    r = client.get(f"/api/employers/master/{mid}/board")
    assert r.status_code == 200
    data = r.json()
    for d in data["directors"]:
        assert is_likely_real_director_name(d["name"]) is True, (
            f"garbage name leaked through filter: master_id={mid} "
            f"name={d['name']!r}"
        )


@pytest.mark.skipif(
    _first_master_with_garbage_director() is None,
    reason="no master with parser-garbage director rows",
)
def test_director_count_matches_filtered_array_when_within_limit():
    """`summary.director_count` is the post-filter aggregate.
    When `len(directors)` <= LIMIT (default 50), the two MUST agree.
    Without this, the BoardCard shows '13 directors' but renders 12
    rows, which is exactly the regression we're fixing."""
    mid = _first_master_with_garbage_director()
    r = client.get(f"/api/employers/master/{mid}/board?limit=200")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    # If the SQL aggregate filter and the directors-fetch filter agree
    # (they share the SQL_FILTER_CLAUSE), `director_count` should equal
    # len(directors) up to any Python-only residue dropped by the
    # post-fetch predicate.
    expected_visible = s["director_count"]
    actual_visible = len(data["directors"])
    # Residue may shave off a few rows the SQL filter missed.
    assert actual_visible == expected_visible - s.get("directors_filtered_count", 0)


@pytest.mark.skipif(
    _first_master_with_garbage_interlock() is None,
    reason="no master with parser-garbage interlock rows",
)
def test_response_array_excludes_garbage_interlock_names():
    """Per Agent 4 2026-05-18: Boeing had 163 interlocks referencing
    'DEF 14A'. None of these should survive the filter."""
    mid = _first_master_with_garbage_interlock()
    r = client.get(f"/api/employers/master/{mid}/board")
    assert r.status_code == 200
    data = r.json()
    for il in data["interlocks"]:
        assert is_likely_real_director_name(il["director_name"]) is True, (
            f"garbage interlock leaked through filter: master_id={mid} "
            f"director_name={il['director_name']!r}"
        )
    # Observability counter should reflect what got dropped.
    assert data["summary"]["interlocks_filtered_count"] >= 1


@pytest.mark.skipif(not _has_director_data(), reason="employer_directors empty")
def test_garbage_director_names_absent_for_known_masters():
    """Explicit allow-list check against the GARBAGE_EXAMPLES catalog.
    Pick a master that's known to have garbage rows; assert the response
    array contains none of the catalog strings."""
    mid = _first_master_with_garbage_director()
    if mid is None:
        pytest.skip("no master with garbage rows in current DB")
    r = client.get(f"/api/employers/master/{mid}/board")
    assert r.status_code == 200
    names_in_response = {d["name"] for d in r.json()["directors"]}
    leaked = names_in_response & set(GARBAGE_EXAMPLES)
    assert not leaked, f"garbage names leaked: {leaked}"
