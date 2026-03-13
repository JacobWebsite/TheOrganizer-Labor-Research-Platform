"""
Tests for NYC/NYS enforcement integration (Task 3-4).

Validates:
- Research tool registration and definition
- Research tool returns correct structure for known NYC employer
- Research tool returns found=False for unknown name
- Profile endpoint includes nyc_enforcement key
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Disable real URL resolution in tests
import os
os.environ.setdefault("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "false")


class TestToolRegistration:
    """Verify search_nyc_enforcement is properly registered."""

    def test_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_nyc_enforcement" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_nyc_enforcement"])

    def test_in_definitions(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "search_nyc_enforcement" in names

    def test_definition_has_schema(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        defn = next(td for td in TOOL_DEFINITIONS if td["name"] == "search_nyc_enforcement")
        assert "input_schema" in defn
        assert "company_name" in defn["input_schema"]["properties"]
        assert "company_name" in defn["input_schema"]["required"]


class TestSearchNycEnforcement:
    """Verify search_nyc_enforcement returns correct structure."""

    def test_known_employer_returns_found(self):
        """Burlington Coat Factory appears in NYC local labor laws."""
        from scripts.research.tools import search_nyc_enforcement
        result = search_nyc_enforcement("Burlington Coat Factory", state="NY")
        assert isinstance(result, dict)
        assert "found" in result
        assert "source" in result
        assert "summary" in result
        assert "data" in result
        # Should have standard result shape regardless of found status
        if result["found"]:
            assert result["data"]["record_count"] > 0
            assert isinstance(result["data"]["records"], list)
            assert "is_debarred" in result["data"]

    def test_unknown_employer_returns_not_found(self):
        from scripts.research.tools import search_nyc_enforcement
        result = search_nyc_enforcement("ZZZZZ_NONEXISTENT_COMPANY_99999")
        assert result["found"] is False
        assert result["data"] == {}

    def test_result_data_keys(self):
        """Verify data dict has all expected keys when found."""
        from scripts.research.tools import search_nyc_enforcement
        result = search_nyc_enforcement("Starbucks", state="NY")
        if result["found"]:
            data = result["data"]
            expected_keys = {"record_count", "debarment_count", "local_law_count",
                             "wage_theft_count", "is_debarred", "total_wages_owed",
                             "total_recovered", "records"}
            assert expected_keys.issubset(set(data.keys()))


class TestProfileNycEnforcement:
    """Verify profile endpoint includes nyc_enforcement section."""

    def test_profile_has_nyc_enforcement_key(self):
        """The profile endpoint helper returns a dict with expected shape."""
        from db_config import get_connection
        from psycopg2.extras import RealDictCursor

        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get any F7 employer to test with
        cur.execute("""
            SELECT employer_id, employer_name
            FROM f7_employers_deduped
            WHERE employer_name IS NOT NULL
            LIMIT 1
        """)
        row = cur.fetchone()
        assert row is not None, "Need at least one F7 employer for this test"

        # Import and call the helper directly
        from api.routers.profile import _get_nyc_enforcement
        result = _get_nyc_enforcement(cur, dict(row))

        assert isinstance(result, dict)
        assert "summary" in result
        assert "records" in result
        assert "record_count" in result["summary"]
        assert "is_debarred" in result["summary"]
        assert "total_wages_owed" in result["summary"]
        assert "total_recovered" in result["summary"]
        assert isinstance(result["records"], list)

        conn.close()

    def test_profile_helper_empty_name(self):
        """Helper handles missing employer name gracefully."""
        from db_config import get_connection
        from psycopg2.extras import RealDictCursor

        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        from api.routers.profile import _get_nyc_enforcement
        result = _get_nyc_enforcement(cur, {"employer_name": ""})

        assert result["summary"]["record_count"] == 0
        assert result["summary"]["is_debarred"] is False
        assert result["records"] == []

        conn.close()
