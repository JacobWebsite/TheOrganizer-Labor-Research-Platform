"""
Regression guard: 4 dead query families must never return to the research agent.

Based on the 2026-04-21 ablation, these site-restricted query patterns have
proven-useless hit rates (22-44% vs 78% for Core 6) and were formally dropped
from the taxonomy. This test keeps them out -- of both the in-repo query
templates AND the DB-backed `research_query_effectiveness` table that the
agent loads learned templates from.

Dead families:
- `site:courtlistener.com`  -- misses most district-court dockets without PACER access
- `site:echo.epa.gov`       -- form-based search misses most facilities
- `reddit.com` site-restricted -- sparse organic coverage for industrial employers
- `site:afscme.org` / `site:aflcio.org` -- redundant with general web search,
  and we have structured `web_union_profiles` data for this purpose now

If this test fails: either remove the offending template (preferred) OR explicitly
add a comment explaining why the particular use is justified and amend this
test to exclude it.

Run: py -m pytest tests/test_research_queries.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_PY = PROJECT_ROOT / "scripts" / "research" / "agent.py"
TOOLS_PY = PROJECT_ROOT / "scripts" / "research" / "tools.py"

# Patterns (case-insensitive) that must NOT appear in agent.py or tools.py
DEAD_PATTERNS = [
    r"site:courtlistener\.com",
    r"site:echo\.epa\.gov",
    r'"site:reddit\.com"',          # allow bare "reddit.com" links in comments, only flag site-restricted queries
    r"site:afscme\.org",
    r"site:aflcio\.org",
    r"site:seiu\.org",
    r"site:uaw\.org",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_agent_py_no_dead_queries():
    """The research agent Python source must not contain site-restricted
    queries for the 4 dead families."""
    text = _read(AGENT_PY)
    offenders = []
    for pattern in DEAD_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            offenders.append((pattern, len(matches)))
    assert not offenders, (
        f"Dead-family site-restricted queries found in agent.py: {offenders}. "
        "Either remove them (see test docstring) or amend DEAD_PATTERNS with "
        "an explicit justification."
    )


def test_tools_py_no_dead_queries():
    """The research agent tool registry must not contain site-restricted
    queries for the 4 dead families."""
    text = _read(TOOLS_PY)
    offenders = []
    for pattern in DEAD_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            offenders.append((pattern, len(matches)))
    assert not offenders, (
        f"Dead-family site-restricted queries found in tools.py: {offenders}. "
        "Either remove them or amend DEAD_PATTERNS with an explicit justification."
    )


def test_db_query_effectiveness_no_dead_queries():
    """The `research_query_effectiveness` table must not contain dead-family
    templates (site-restricted queries for CourtListener / EPA ECHO / Reddit /
    union-site)."""
    try:
        import psycopg2.extras  # noqa: F401
        from db_config import get_connection
    except ImportError:
        pytest.skip("psycopg2 / db_config unavailable")

    try:
        conn = get_connection()
    except Exception as exc:
        pytest.skip(f"DB unreachable: {exc}")

    conn.autocommit = True
    cur = conn.cursor()
    try:
        for pattern in [
            "courtlistener",
            "echo.epa",
            "afscme.org",
            "aflcio.org",
        ]:
            cur.execute(
                "SELECT COUNT(*) FROM research_query_effectiveness "
                "WHERE query_template ILIKE %s",
                (f"%{pattern}%",),
            )
            n = cur.fetchone()[0]
            assert n == 0, (
                f"Dead-family pattern '{pattern}' found in "
                f"research_query_effectiveness ({n} rows). "
                "DELETE those rows or amend this test with a justification."
            )
        # Reddit is a special case: we allow bare reddit.com links but not
        # site-restricted queries.
        cur.execute(
            "SELECT COUNT(*) FROM research_query_effectiveness "
            "WHERE query_template ILIKE %s",
            ("%site:reddit.com%",),
        )
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
