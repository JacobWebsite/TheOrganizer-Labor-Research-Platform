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
        # Was 22 tools, now should be 28 (22 + 5 new + 1 ACS)
        assert len(TOOL_REGISTRY) >= 28, f"Expected >= 28 tools, got {len(TOOL_REGISTRY)}"


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

    def test_acs_in_agent_prompt(self):
        agent_path = ROOT / "scripts" / "research" / "agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "search_acs_workforce" in content


class TestACSWorkforceTool:
    """Tests for the search_acs_workforce tool."""

    def test_acs_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_acs_workforce" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_acs_workforce"])

    def test_acs_definition(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        td = None
        for d in TOOL_DEFINITIONS:
            if d["name"] == "search_acs_workforce":
                td = d
                break
        assert td is not None
        assert "state" in td["input_schema"]["properties"]
        assert "state" in td["input_schema"]["required"]
        assert "naics" in td["input_schema"]["properties"]
        assert "soc_code" in td["input_schema"]["properties"]
        assert "metro_cbsa" in td["input_schema"]["properties"]

    def test_acs_missing_state(self):
        from scripts.research.tools import search_acs_workforce
        result = search_acs_workforce("TEST_COMPANY")
        assert isinstance(result, dict)
        assert result["found"] is False
        assert "state" in result["summary"].lower()

    def test_acs_invalid_state(self):
        from scripts.research.tools import search_acs_workforce
        result = search_acs_workforce("TEST_COMPANY", state="ZZ")
        assert isinstance(result, dict)
        assert result["found"] is False

    def test_acs_result_format(self):
        from scripts.research.tools import search_acs_workforce
        result = search_acs_workforce("TEST_COMPANY", state="NY")
        assert isinstance(result, dict)
        assert "found" in result
        assert "source" in result
        assert "summary" in result
        assert "data" in result

    def test_acs_data_keys_when_found(self):
        from scripts.research.tools import search_acs_workforce
        result = search_acs_workforce("TEST_COMPANY", state="NY")
        if result["found"]:
            data = result["data"]
            assert "total_weighted_workers" in data
            assert "gender_pct" in data
            assert "race_pct" in data
            assert "age_distribution_pct" in data
            assert "education_pct" in data
            assert "worker_class_pct" in data


class TestGetIndustryProfileBLS:
    """Tests for BLS dataset integration in get_industry_profile (R3-9)."""

    def test_bls_keys_present(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"]:
            assert "oes_area_wages" in result["data"]
            assert "soii_injury_rates" in result["data"]
            assert "jolts_turnover_rates" in result["data"]
            assert "ncs_benefits_access" in result["data"]

    def test_soii_format(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"] and result["data"]["soii_injury_rates"]:
            row = result["data"]["soii_injury_rates"][0]
            assert "year" in row
            assert "industry_name" in row
            assert "case_type_text" in row
            assert "rate" in row

    def test_jolts_format(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"] and result["data"]["jolts_turnover_rates"]:
            row = result["data"]["jolts_turnover_rates"][0]
            assert "year" in row
            assert "period" in row
            assert "dataelement_text" in row
            assert "rate" in row

    def test_ncs_format(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"] and result["data"]["ncs_benefits_access"]:
            row = result["data"]["ncs_benefits_access"][0]
            assert "year" in row
            assert "provision_text" in row
            assert "rate" in row

    def test_oes_only_with_state(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72")
        if result["found"]:
            assert result["data"]["oes_area_wages"] == []

    def test_oes_format_with_state(self):
        from scripts.research.tools import get_industry_profile
        result = get_industry_profile("TEST", naics="72", state="NY")
        if result["found"] and result["data"]["oes_area_wages"]:
            row = result["data"]["oes_area_wages"][0]
            assert "occ_code" in row
            assert "a_median" in row
            assert "tot_emp" in row

    def test_ncs_fallback_to_all_private(self):
        from scripts.research.tools import get_industry_profile
        # Use a rare NAICS that probably has no NCS data
        result = get_industry_profile("TEST", naics="111998")
        if result["found"]:
            # Even with a rare NAICS, NCS should fall back to all-private
            assert isinstance(result["data"]["ncs_benefits_access"], list)


class TestUnionWebProfilesTool:
    """Tests for `search_union_web_profiles` (Session 1d, 2026-04-24).

    Replaces the dropped `site:afscme.org` / `site:seiu.org` site-restricted
    Google queries with deterministic lookups against
    `web_union_employers` (2,241+ rows extracted from union websites by the
    2026-04-19/21 scraper work) joined to `web_union_profiles`.
    """

    def test_union_web_profiles_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_union_web_profiles" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_union_web_profiles"])

    def test_union_web_profiles_definition(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        td = next((t for t in TOOL_DEFINITIONS if t["name"] == "search_union_web_profiles"), None)
        assert td is not None
        props = td["input_schema"]["properties"]
        assert "company_name" in props
        assert "state" in props
        assert "company_name" in td["input_schema"]["required"]

    def test_union_web_profiles_not_found_shape(self):
        from scripts.research.tools import search_union_web_profiles
        result = search_union_web_profiles("NONEXISTENT XYZ COMPANY 12345")
        assert isinstance(result, dict)
        assert result["found"] is False
        assert "source" in result
        assert "summary" in result
        assert "data" in result
        # Even on not-found, data should have the expected shape (empty lists)
        assert result["data"]["mentions"] == []
        assert result["data"]["locals"] == []

    def test_union_web_profiles_found_shape(self):
        """If the DB has the expected scraper data (Republic Services, Rush,
        Sysco), the tool should return the full enriched structure."""
        from scripts.research.tools import search_union_web_profiles
        result = search_union_web_profiles("Republic Services")
        if result["found"]:
            d = result["data"]
            # Required summary fields
            assert d["mention_count"] > 0
            assert d["local_count"] > 0
            assert isinstance(d["parent_unions"], list)
            assert isinstance(d["states_covered"], list)
            # Mention records have the expected keys
            m = d["mentions"][0]
            assert "employer_name" in m
            assert "source_url" in m
            assert "union_local" in m
            # Locals records have the expected keys
            loc = d["locals"][0]
            assert "parent_union" in loc
            assert "local_number" in loc
            assert "website_url" in loc
        else:
            pytest.skip("scraper data not present in DB (expected in dev/CI)")

    def test_union_web_profiles_state_filter(self):
        """State filter restricts results to that state only."""
        from scripts.research.tools import search_union_web_profiles
        result = search_union_web_profiles("Republic Services", state="AZ")
        if result["found"]:
            for mention in result["data"]["mentions"]:
                # Either the mention itself is tagged AZ, OR it has no state
                # (NULL state rows still match because we use COALESCE)
                state = mention.get("state")
                assert state is None or state.upper() == "AZ"


class TestEpaEchoTool:
    """Tests for `search_epa_echo` (Session 3b, 2026-04-24).

    Replaces the dropped `site:echo.epa.gov` Google query with a direct
    JSON API call to EPA ECHO. Returns facility_count + inspection /
    violation / enforcement-action aggregates.
    """

    def test_epa_echo_in_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "search_epa_echo" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["search_epa_echo"])

    def test_epa_echo_definition(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        td = next((t for t in TOOL_DEFINITIONS if t["name"] == "search_epa_echo"), None)
        assert td is not None
        assert "company_name" in td["input_schema"]["properties"]
        assert "state" in td["input_schema"]["properties"]
        assert "company_name" in td["input_schema"]["required"]

    def test_epa_echo_not_found_shape(self):
        """Bogus query returns the not-found shape without raising."""
        from scripts.research.tools import search_epa_echo
        try:
            result = search_epa_echo("ZZ NONEXISTENT FAKE COMPANY 12345")
        except Exception:
            pytest.skip("EPA ECHO endpoint unreachable in this environment")
        assert isinstance(result, dict)
        assert result["found"] is False
        assert "source" in result
        assert "summary" in result
        assert "data" in result

    def test_epa_echo_return_format_when_found(self):
        """If the live API returns matches, the return shape has the
        expected aggregate keys."""
        from scripts.research.tools import search_epa_echo
        try:
            result = search_epa_echo("Exxon", state="TX")
        except Exception:
            pytest.skip("EPA ECHO endpoint unreachable in this environment")
        if result["found"]:
            d = result["data"]
            assert "facility_count" in d
            assert d["facility_count"] > 0
            assert "total_inspections" in d
            assert "significant_violations" in d
            assert "current_violations" in d
            assert "enforcement_actions" in d
            assert "query_id" in d
            # detail_url is a pagination hint for callers who want the full
            # facility list (requires a second API call)
            assert d.get("detail_url", "").startswith("https://echodata.epa.gov/")
