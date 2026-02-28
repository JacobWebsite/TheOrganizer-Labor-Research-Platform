"""
Tests for new research tool integrations (Form 5500, PPP, CBP, LODES, ABS).

Validates:
- All 5 new tools are registered in TOOL_REGISTRY
- All 5 new tools have TOOL_DEFINITIONS entries
- Each tool returns the expected result format
- Each tool handles missing data gracefully
- get_industry_profile now returns cbp_local_context
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
    """Verify new tools are properly registered."""

    def test_form5500_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_form5500" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_form5500"])

    def test_ppp_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_ppp_loans" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_ppp_loans"])

    def test_cbp_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_cbp_context" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_cbp_context"])

    def test_lodes_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_lodes_workforce" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_lodes_workforce"])

    def test_abs_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_abs_demographics" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_abs_demographics"])


class TestToolDefinitions:
    """Verify new tools have proper API definitions."""

    def _get_def(self, name):
        from scripts.research.tools import TOOL_DEFINITIONS
        for td in TOOL_DEFINITIONS:
            if td["name"] == name:
                return td
        return None

    def test_form5500_definition(self):
        td = self._get_def("search_form5500")
        assert td is not None
        assert "company_name" in td["input_schema"]["properties"]
        assert "company_name" in td["input_schema"]["required"]

    def test_ppp_definition(self):
        td = self._get_def("search_ppp_loans")
        assert td is not None
        assert "company_name" in td["input_schema"]["properties"]

    def test_cbp_definition(self):
        td = self._get_def("search_cbp_context")
        assert td is not None
        assert "naics" in td["input_schema"]["properties"]
        assert "naics" in td["input_schema"]["required"]

    def test_lodes_definition(self):
        td = self._get_def("search_lodes_workforce")
        assert td is not None
        assert "state" in td["input_schema"]["properties"]

    def test_abs_definition(self):
        td = self._get_def("search_abs_demographics")
        assert td is not None
        assert "naics" in td["input_schema"]["properties"]
        assert "naics" in td["input_schema"]["required"]


class TestToolResultFormat:
    """Test that tools return the expected dict format even for missing data."""

    def test_form5500_not_found(self):
        from scripts.research.tools import search_form5500
        result = search_form5500("ZZZZZ_NONEXISTENT_COMPANY_12345")
        assert isinstance(result, dict)
        assert "found" in result
        assert "source" in result
        assert result["found"] is False

    def test_ppp_not_found(self):
        from scripts.research.tools import search_ppp_loans
        result = search_ppp_loans("ZZZZZ_NONEXISTENT_COMPANY_12345")
        assert isinstance(result, dict)
        assert result["found"] is False

    def test_cbp_missing_naics(self):
        from scripts.research.tools import search_cbp_context
        result = search_cbp_context("TEST_COMPANY")
        assert result["found"] is False
        assert "NAICS" in result["summary"]

    def test_lodes_missing_location(self):
        from scripts.research.tools import search_lodes_workforce
        result = search_lodes_workforce("TEST_COMPANY")
        assert result["found"] is False

    def test_abs_missing_naics(self):
        from scripts.research.tools import search_abs_demographics
        result = search_abs_demographics("TEST_COMPANY")
        assert result["found"] is False
        assert "NAICS" in result["summary"]


class TestGetIndustryProfileExtended:
    """Test that get_industry_profile includes CBP context in its data."""

    def test_return_has_cbp_key(self):
        from scripts.research.tools import get_industry_profile
        # Even if no CBP data, the key should exist
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"]:
            assert "cbp_local_context" in result["data"]

    def test_no_naics_returns_not_found(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST")
        assert result["found"] is False


class TestRegistryCounts:
    """Ensure registry and definitions are in sync."""

    def test_all_registry_tools_have_definitions(self):
        from scripts.research.tools import TOOL_REGISTRY, TOOL_DEFINITIONS
        defined_names = {td["name"] for td in TOOL_DEFINITIONS}
        for name in TOOL_REGISTRY:
            assert name in defined_names, f"Tool '{name}' in REGISTRY but not in DEFINITIONS"

    def test_all_definitions_have_registry_entries(self):
        from scripts.research.tools import TOOL_REGISTRY, TOOL_DEFINITIONS
        for td in TOOL_DEFINITIONS:
            assert td["name"] in TOOL_REGISTRY, f"Tool '{td['name']}' in DEFINITIONS but not in REGISTRY"

    def test_minimum_tool_count(self):
        from scripts.research.tools import TOOL_REGISTRY
        # Was 22 tools, now should be 27 (22 + 5 new)
        assert len(TOOL_REGISTRY) >= 27, f"Expected >= 27 tools, got {len(TOOL_REGISTRY)}"


class TestAgentSystemPrompt:
    """Test that agent.py references the new tools."""

    def test_form5500_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_form5500" in content

    def test_cbp_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_cbp_context" in content

    def test_ppp_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_ppp_loans" in content

    def test_lodes_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_lodes_workforce" in content

    def test_abs_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_abs_demographics" in content
