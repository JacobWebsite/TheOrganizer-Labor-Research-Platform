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

2026-05-18 Codex follow-up: SQL_FILTER_CLAUSE now mirrors the Python predicate
rule-for-rule, so `summary.director_count` MUST equal `len(directors)` when
`limit >= director_count`. The earlier behaviour -- where Python filtering
happened AFTER LIMIT, so a page of 12 could yield 0 real directors with
`director_count=12` reporting wrong -- is now pinned against by
`test_director_count_equals_array_length_when_within_limit`.

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
def test_director_count_equals_array_length_when_within_limit():
    """`summary.director_count` is the post-filter aggregate AND the SQL
    fetch shares the same WHERE clause. When the response array isn't
    truncated by LIMIT, the two MUST be equal -- no fudge factor for
    Python residue.

    This is the central invariant the 2026-05-18 fix establishes.
    Pre-fix, the BoardCard could render `${director_count} directors`
    over an empty list because Python filtering happened after LIMIT
    and `directors_filtered_count` only counted the page residue.
    """
    mid = _first_master_with_garbage_director()
    r = client.get(f"/api/employers/master/{mid}/board?limit=200")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    # LIMIT=200 is well above the largest known board (Apple/Pfizer at ~17).
    # Therefore len(directors) must exactly equal director_count.
    assert len(data["directors"]) == s["director_count"], (
        f"director_count={s['director_count']} but "
        f"len(directors)={len(data['directors'])} -- aggregate and "
        f"fetch disagree; SQL_FILTER_CLAUSE has drifted from the "
        f"Python predicate. directors_filtered_count="
        f"{s.get('directors_filtered_count')}"
    )
    # The Python residue pass should drop zero rows now that the SQL
    # filter is rule-for-rule identical. Any non-zero value here is a
    # signal that the two paths have diverged.
    assert s.get("directors_filtered_count", 0) == 0, (
        f"SQL/Python predicate divergence: "
        f"directors_filtered_count={s['directors_filtered_count']} > 0 "
        f"means SQL passed rows that Python rejected -- re-align "
        f"SQL_FILTER_CLAUSE with is_likely_real_director_name."
    )


def _first_master_with_year_regex_residue() -> int | None:
    """Find a master whose SQL-survivors (under the OLD clause) contained
    year-bearing strings that the Python year-regex would have killed.
    Under the new clause, the SQL should reject these directly so the
    response should have no such rows AND director_count should reflect
    the post-year-filter total."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Masters with multiple year-bearing director names that would NOT
        # be caught by length/first-word/substring filters -- they pass
        # the OLD SQL clause but fail Python's year-regex.
        cur.execute(
            r"""
            SELECT master_id, COUNT(*) AS n
            FROM employer_directors
            WHERE director_name ~ '[[:<:]](19|20)[0-9]{2}[[:>:]]'
              AND LENGTH(TRIM(director_name)) BETWEEN 4 AND 80
              AND ARRAY_LENGTH(STRING_TO_ARRAY(TRIM(director_name), ' '), 1) >= 2
              AND LOWER(SPLIT_PART(TRIM(director_name), ' ', 1)) NOT IN (
                'def', 'chief', 'vice', 'audit', 'continuing', 'independent',
                'committee', 'class', 'proxy', '2026', '2025'
              )
              AND LOWER(director_name) NOT LIKE '%%proxy statement%%'
              AND LOWER(director_name) NOT LIKE '%%def 14a%%'
            GROUP BY master_id
            ORDER BY n DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


@pytest.mark.skipif(
    _first_master_with_year_regex_residue() is None,
    reason="no master with year-regex residue rows",
)
def test_year_regex_residue_rejected_at_sql_level():
    """Regression for the Codex finding: prior to the fix, a master whose
    parser-garbage rows were year-bearing (e.g. master 4238837 with
    'James A. Bowen 3 1955', 'Thomas J. Driscoll 4 1961', etc.) would
    return `director_count=8` with `directors=[]`. The SQL aggregate
    counted them; the SQL fetch returned them; the Python residue pass
    then dropped them, leaving the array empty AND `director_count`
    overstated.

    Post-fix the SQL clause itself rejects year-bearing names, so
    the aggregate sees the same rows the fetch returns.
    """
    mid = _first_master_with_year_regex_residue()
    r = client.get(f"/api/employers/master/{mid}/board?limit=200")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    # The historical bug: director_count reports rows that don't make
    # it into the array. Pin this against.
    assert len(data["directors"]) == s["director_count"]
    # And the residue counter should be zero (year-regex is now in SQL).
    assert s["directors_filtered_count"] == 0
    # No surviving director name should contain a year.
    import re
    for d in data["directors"]:
        assert not re.search(r"\b(19|20)\d{2}\b", d["name"]), (
            f"year-bearing name survived SQL filter: {d['name']!r}"
        )


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
