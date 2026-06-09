"""R8-7 (2026-06-07): unified employer search ranking + perf regression tests.

Covers the launch-blocker fix in api/routers/employers.py::unified_employer_search:

  * Famous-acronym recall: 'ge'/'gm'/'p&g'/'kp'/'hcsc'/'nyc hospitals' must
    surface their true canonical in the top results. Before the fix the
    `similarity(search_name, %s) > 0.3` gate filtered these canonicals out
    (acronym->canonical trigram similarity is far below 0.3), so above-gate
    junk (GES / GM-SPO / PSE&G / NYU Langone) won instead.

  * COUNT/SELECT param parity: the endpoint issues a COUNT and a SELECT that
    share the same WHERE clause. The WHERE clause text and its bound params
    MUST be byte-identical between the two queries (same param order), or the
    reported `total` describes a different filter than the returned rows.

These run against the live olms_multiyear DB (like the other tests/ suite).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Query -> a lowercase substring that must appear in the rank-1 result name.
FAMOUS_CASES = [
    ("ge", "general electric"),
    ("gm", "general motors"),
    ("p&g", "procter"),
    ("kp", "kaiser"),
    ("hcsc", "health care service"),
    ("nyc hospitals", "new york city health and hospitals"),
]

# Junk that previously won and must NOT be the rank-1 result for each query.
FORBIDDEN_TOP = {
    "ge": "ges",
    "gm": "gm-spo",
    "p&g": "pse&g",
    "nyc hospitals": "nyu langone",
}


@pytest.mark.parametrize("query,expected_substr", FAMOUS_CASES)
def test_famous_acronym_ranks_canonical_first(client, query, expected_substr):
    """Each famous acronym query returns its true canonical at rank 1."""
    r = client.get("/api/employers/unified-search", params={"name": query, "limit": 5})
    assert r.status_code == 200, r.text
    employers = r.json()["employers"]
    assert employers, f"no results for {query!r}"
    top_name = employers[0]["employer_name"].lower()
    assert expected_substr in top_name, (
        f"{query!r}: expected rank-1 name to contain {expected_substr!r}, "
        f"got {employers[0]['employer_name']!r}. "
        f"Top 5: {[e['employer_name'] for e in employers]}"
    )


@pytest.mark.parametrize("query,forbidden", FORBIDDEN_TOP.items())
def test_famous_acronym_excludes_known_junk_from_top(client, query, forbidden):
    """The previously-winning junk row must not be the rank-1 result."""
    r = client.get("/api/employers/unified-search", params={"name": query, "limit": 5})
    assert r.status_code == 200, r.text
    employers = r.json()["employers"]
    assert employers, f"no results for {query!r}"
    top_name = employers[0]["employer_name"].lower()
    assert forbidden not in top_name, (
        f"{query!r}: junk {forbidden!r} should not rank first, got "
        f"{employers[0]['employer_name']!r}"
    )


def test_count_and_select_share_identical_where_params(client, monkeypatch):
    """COUNT and SELECT must use the same WHERE clause + the same leading params.

    The endpoint runs, in order: cur.execute(COUNT, params) then
    cur.execute(SELECT, params + order_params + [limit, offset]). We intercept
    every execute() on the connection's cursor (via lightweight proxies, since
    psycopg2's connection.cursor is read-only and cannot be monkeypatched
    directly) and assert:
      (1) the COUNT and SELECT WHERE clauses are textually identical, and
      (2) the SELECT's params begin with EXACTLY the COUNT's params (same
          order, same values) -- i.e. the shared WHERE params are byte-identical.
    """
    from contextlib import contextmanager

    from api import database

    captured = []

    orig_get_db = database.get_db

    class _RecordingCursor:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, sql, params=None):
            captured.append((sql, list(params) if params is not None else []))
            return self._cur.execute(sql, params)

        def __getattr__(self, attr):
            return getattr(self._cur, attr)

        def __enter__(self):
            self._cur.__enter__()
            return self

        def __exit__(self, *exc):
            return self._cur.__exit__(*exc)

    class _RecordingConn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self, *a, **k):
            return _RecordingCursor(self._conn.cursor(*a, **k))

        def __getattr__(self, attr):
            return getattr(self._conn, attr)

    @contextmanager
    def recording_get_db():
        with orig_get_db() as conn:
            yield _RecordingConn(conn)

    monkeypatch.setattr("api.routers.employers.get_db", recording_get_db)

    r = client.get("/api/employers/unified-search", params={"name": "p&g", "limit": 5})
    assert r.status_code == 200, r.text

    # Find the COUNT and the main SELECT among captured executes. Match on the
    # leading statement (after stripping whitespace) -- the SELECT's flag-count
    # LEFT JOIN subquery also contains "COUNT(*)", so we cannot key off that.
    def lead(sql):
        return " ".join(sql.split())

    count_calls = [
        (s, p) for (s, p) in captured if lead(s).startswith("SELECT COUNT(*) FROM mv_employer_search")
    ]
    select_calls = [
        (s, p)
        for (s, p) in captured
        if lead(s).startswith("SELECT m.canonical_id") and "ORDER BY" in s
    ]
    assert count_calls, f"no COUNT execute captured; saw {[s[:60] for s, _ in captured]}"
    assert select_calls, f"no SELECT execute captured; saw {[s[:60] for s, _ in captured]}"

    count_sql, count_params = count_calls[-1]
    select_sql, select_params = select_calls[-1]

    # (1) WHERE clause text identical between the two queries. Slice from the
    # last WHERE to the next ORDER BY (if any) and collapse whitespace so the
    # COUNT (single line) and SELECT (multi-line) WHERE compare equal.
    def where_of(sql):
        tail = sql[sql.rindex(" WHERE ") + len(" WHERE "):]
        j = tail.find("ORDER BY")
        if j != -1:
            tail = tail[:j]
        return " ".join(tail.split())

    assert where_of(count_sql) == where_of(select_sql), (
        "COUNT and SELECT WHERE clauses diverge:\n"
        f"  COUNT WHERE : {where_of(count_sql)!r}\n"
        f"  SELECT WHERE: {where_of(select_sql)!r}"
    )

    # (2) SELECT params begin with exactly the COUNT params (same order/values).
    assert select_params[: len(count_params)] == count_params, (
        "Shared WHERE params differ between COUNT and SELECT:\n"
        f"  COUNT params : {count_params!r}\n"
        f"  SELECT params: {select_params[: len(count_params)]!r} (leading slice)"
    )
    # The SELECT carries strictly more params (ORDER BY + LIMIT/OFFSET).
    assert len(select_params) > len(count_params)
