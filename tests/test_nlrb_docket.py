"""
Tests for NLRB docket integration (Task 3-5).

Validates:
- Docket detail endpoint returns entries for known case
- Docket detail endpoint returns 404 for unknown case
- Profile endpoint includes nlrb_docket key with correct shape
- Profile docket helper returns correct structure
- Research tool registration
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "false")


def test_docket_endpoint_returns_entries(client):
    """GET /api/nlrb/docket/{case_number} returns 200 with entries."""
    from db_config import get_connection
    from psycopg2.extras import RealDictCursor

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT case_number FROM nlrb_docket LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        pytest.skip("No NLRB docket data in database")

    case_num = row["case_number"]
    r = client.get(f"/api/nlrb/docket/{case_num}")
    assert r.status_code == 200
    data = r.json()
    assert data["case_number"] == case_num
    assert "entries" in data
    assert data["entry_count"] > 0
    assert "first_date" in data
    assert "last_date" in data
    assert "duration_days" in data
    entry = data["entries"][0]
    assert "docket_entry" in entry
    assert "docket_date" in entry
    assert "document_id" in entry


def test_docket_endpoint_404_for_missing_case(client):
    """GET /api/nlrb/docket/{case_number} returns 404 for unknown case."""
    r = client.get("/api/nlrb/docket/99-XX-999999")
    assert r.status_code == 404


def test_profile_includes_nlrb_docket(client):
    """Profile endpoint includes nlrb_docket key with correct shape."""
    from db_config import get_connection
    from psycopg2.extras import RealDictCursor

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT employer_id::text AS eid FROM f7_employers_deduped LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        pytest.skip("No F7 employers in database")

    r = client.get(f"/api/profile/employers/{row['eid']}")
    assert r.status_code == 200
    data = r.json()
    assert "nlrb_docket" in data
    docket = data["nlrb_docket"]
    assert "summary" in docket
    assert "cases" in docket
    assert "cases_with_docket" in docket["summary"]
    assert "total_entries" in docket["summary"]
    assert "has_recent_activity" in docket["summary"]
    assert isinstance(docket["summary"]["has_recent_activity"], bool)
    assert isinstance(docket["cases"], list)


def test_docket_helper_empty_for_unknown():
    """Docket helper returns zero counts for unknown employer ID."""
    from db_config import get_connection
    from psycopg2.extras import RealDictCursor

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    from api.routers.profile import _get_nlrb_docket_summary
    result = _get_nlrb_docket_summary(cur, "NONEXISTENT_ID_99999")

    assert result["summary"]["cases_with_docket"] == 0
    assert result["summary"]["total_entries"] == 0
    assert result["summary"]["has_recent_activity"] is False
    assert result["cases"] == []

    conn.close()


class TestDocketToolRegistration:
    """Verify search_nlrb_docket is properly registered."""

    def test_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_nlrb_docket" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_nlrb_docket"])

    def test_in_definitions(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "search_nlrb_docket" in names

    def test_definition_has_schema(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        defn = next(td for td in TOOL_DEFINITIONS if td["name"] == "search_nlrb_docket")
        assert "input_schema" in defn
        assert "company_name" in defn["input_schema"]["properties"]
        assert "company_name" in defn["input_schema"]["required"]
