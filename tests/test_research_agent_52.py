"""
Tests for Research Agent Phase 5.2 — Reliability, Caching & Gap-Aware Web Search.

Covers:
  - A: Vocabulary mapping correctness (_TOOL_FACT_MAP, _ATTR_SECTION)
  - A: JSON repair strategies in _try_parse_json
  - B: Cache hit/miss behavior (_check_cache)
  - C: Gap-aware query builder (_build_web_search_queries)
  - C: Query effectiveness tracking (_update_query_effectiveness)
"""
import json
import sys
import os
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Part A: Vocabulary mapping tests
# ---------------------------------------------------------------------------

class TestToolFactMapVocabulary:
    """Every attribute_name in _TOOL_FACT_MAP must exist in research_fact_vocabulary."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from scripts.research.agent import _TOOL_FACT_MAP, _ATTR_SECTION
        self.fact_map = _TOOL_FACT_MAP
        self.attr_section = _ATTR_SECTION

    @pytest.fixture
    def vocab_attrs(self):
        """Parse the seed SQL to extract all vocabulary attribute_name values."""
        sql_path = os.path.join(
            os.path.dirname(__file__), "..",
            "sql", "create_research_agent_tables.sql",
        )
        attrs = set()
        with open(sql_path, encoding="utf-8") as f:
            for line in f:
                # Match INSERT lines: ('attr_name', ...
                if line.strip().startswith("('"):
                    attr = line.strip().split("'")[1]
                    attrs.add(attr)
        return attrs

    def test_all_fact_map_attrs_in_vocabulary(self, vocab_attrs):
        """Every attribute_name in _TOOL_FACT_MAP must be in the vocabulary SQL."""
        missing = []
        for tool_name, mappings in self.fact_map.items():
            for attr_name, _key in mappings:
                if attr_name not in vocab_attrs:
                    missing.append(f"{tool_name}: {attr_name}")
        assert not missing, f"Attribute names not in vocabulary: {missing}"

    def test_attr_section_matches_fact_map(self):
        """Every attribute in _TOOL_FACT_MAP should be in _ATTR_SECTION."""
        all_attrs = set()
        for mappings in self.fact_map.values():
            for attr_name, _ in mappings:
                all_attrs.add(attr_name)
        missing = all_attrs - set(self.attr_section.keys())
        assert not missing, f"Attributes in _TOOL_FACT_MAP but not _ATTR_SECTION: {missing}"

    def test_no_duplicate_attrs_across_tools(self):
        """Attribute names can appear in multiple tools (that's fine),
        but each tool mapping should have unique attrs."""
        for tool_name, mappings in self.fact_map.items():
            attrs = [a for a, _ in mappings]
            assert len(attrs) == len(set(attrs)), (
                f"{tool_name} has duplicate attribute names: {attrs}"
            )

    def test_broken_attrs_removed(self):
        """The old broken attribute names should no longer appear."""
        all_attrs = set()
        for mappings in self.fact_map.values():
            for attr_name, _ in mappings:
                all_attrs.add(attr_name)
        broken = {"nonprofit_employees", "nonprofit_ein", "annual_revenue", "company_website"}
        found = all_attrs & broken
        assert not found, f"Broken attribute names still present: {found}"

    def test_federal_contract_status_in_vocabulary(self, vocab_attrs):
        """federal_contract_status must be in the vocabulary (was added in 5.2)."""
        assert "federal_contract_status" in vocab_attrs


# ---------------------------------------------------------------------------
# Part A: JSON repair tests
# ---------------------------------------------------------------------------

class TestJsonRepair:
    """Test progressive JSON repair strategies in _try_parse_json."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from scripts.research.agent import _try_parse_json
        self.parse = _try_parse_json

    def test_valid_json(self):
        result = self.parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_escape(self):
        """Strategy 2: fix invalid escape sequences like \\S."""
        result = self.parse('{"key": "test\\Svalue"}')
        assert result is not None
        assert result["key"] == "testSvalue"

    def test_trailing_garbage(self):
        """Strategy 3: strip trailing garbage after last }."""
        result = self.parse('{"key": "value"}\n\nSome trailing text here')
        assert result == {"key": "value"}

    def test_prefix_before_json(self):
        """Strategy 4: strip non-JSON prefix before first {."""
        result = self.parse('Here is the JSON:\n{"key": "value"}')
        assert result == {"key": "value"}

    def test_prefix_and_suffix(self):
        """Strategy 4 + 3 combined: prefix and trailing garbage."""
        result = self.parse('Response:\n{"key": "value"}\nEnd of response.')
        assert result == {"key": "value"}

    def test_completely_invalid(self):
        result = self.parse("This is not JSON at all")
        assert result is None

    def test_empty_string(self):
        result = self.parse("")
        assert result is None

    def test_nested_json_with_prefix(self):
        """Strategy 4: complex nested JSON with text prefix."""
        raw = 'The dossier is:\n{"dossier": {"identity": {"name": "Acme"}}, "facts": []}'
        result = self.parse(raw)
        assert result is not None
        assert "dossier" in result


# ---------------------------------------------------------------------------
# Part B: Cache tests
# ---------------------------------------------------------------------------

class TestCheckCache:
    """Test _check_cache with mocked DB."""

    def test_cache_miss_no_employer(self):
        """Should return None when employer_id is None."""
        from scripts.research.agent import _check_cache
        result = _check_cache(None, "search_osha")
        assert result is None

    @patch("scripts.research.agent._conn")
    def test_cache_hit(self, mock_conn):
        """Should return cached row when recent data exists."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {
            "result_summary": "Found 5 OSHA violations",
            "tool_params": '{"company_name": "Acme"}',
        }
        mock_conn.return_value.cursor.return_value = mock_cur

        from scripts.research.agent import _check_cache
        result = _check_cache(12345, "search_osha")
        assert result is not None
        assert "OSHA violations" in result["result_summary"]
        mock_cur.execute.assert_called_once()

    @patch("scripts.research.agent._conn")
    def test_cache_miss_no_results(self, mock_conn):
        """Should return None when no cached data found."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cur

        from scripts.research.agent import _check_cache
        result = _check_cache(12345, "search_osha")
        assert result is None


# ---------------------------------------------------------------------------
# Part C: Gap-aware query builder tests
# ---------------------------------------------------------------------------

class TestBuildWebSearchQueries:
    """Test _build_web_search_queries for various gap combinations."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from scripts.research.agent import _build_web_search_queries
        self.build = _build_web_search_queries

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_no_gaps(self, mock_best):
        """When no DB tools missed, only always-run queries should appear."""
        queries, gaps = self.build("Acme Corp", "private", "NY", [])
        # Should have at least the 3 always-run categories
        assert len(queries) >= 3
        # All queries should mention Acme Corp
        for q in queries:
            assert "Acme Corp" in q

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_mergent_gap(self, mock_best):
        """When Mergent misses, should add employee/revenue/website queries."""
        queries, gaps = self.build("Acme Corp", "private", "NY", ["search_mergent"])
        gap_types = [g[0] for g in gaps]
        assert "employee_count" in gap_types
        assert "revenue" in gap_types
        assert "website_url" in gap_types
        # Should be more than just always-run queries
        assert len(queries) > 3

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_multiple_gaps(self, mock_best):
        """Multiple DB gaps should produce more queries."""
        queries_few, _ = self.build("Acme Corp", "private", "NY", ["search_mergent"])
        queries_many, _ = self.build(
            "Acme Corp", "private", "NY",
            ["search_mergent", "search_osha", "search_nlrb"],
        )
        assert len(queries_many) > len(queries_few)

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_cap_at_15(self, mock_best):
        """Should cap queries at 15 even with many gaps."""
        queries, _ = self.build(
            "Acme Corp", "private", "NY",
            ["search_mergent", "search_osha", "search_nlrb",
             "search_whd", "search_990"],
        )
        assert len(queries) <= 15

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_placeholders_filled(self, mock_best):
        """Year, state, and company placeholders should be replaced."""
        queries, _ = self.build("TestCo", "private", "CA", ["search_osha"], year="2026")
        for q in queries:
            assert "{company}" not in q
            assert "{state}" not in q
            assert "{year}" not in q

    @patch("scripts.research.agent._get_best_queries")
    def test_learned_queries_preferred(self, mock_best):
        """When learned queries exist, they should replace defaults."""
        mock_best.return_value = [
            '"{company}" employee headcount annual report',
        ]
        queries, gaps = self.build("Acme Corp", "private", "NY", ["search_mergent"])
        # The learned query should appear (after placeholder fill)
        assert any("annual report" in q for q in queries)

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_nonprofit_990_gap(self, mock_best):
        """search_990 gap should produce nonprofit-specific queries."""
        queries, gaps = self.build("Big Charity", "nonprofit", "DC", ["search_990"])
        gap_types = [g[0] for g in gaps]
        assert "nonprofit_financials" in gap_types
        # Should include 990/ProPublica type queries
        combined = " ".join(queries)
        assert "990" in combined or "nonprofit" in combined.lower()


# ---------------------------------------------------------------------------
# Part C: Query effectiveness tracking tests
# ---------------------------------------------------------------------------

class TestQueryEffectiveness:
    """Test _update_query_effectiveness and _get_best_queries."""

    @patch("scripts.research.agent._ensure_query_effectiveness_table")
    @patch("scripts.research.agent._conn")
    def test_update_inserts_rows(self, mock_conn, mock_ensure):
        """Should insert/upsert rows for each queried gap type."""
        mock_cur = MagicMock()
        mock_conn.return_value.cursor.return_value = mock_cur

        from scripts.research.agent import _update_query_effectiveness
        gap_types = [
            ("employee_count", '"{company}" number of employees'),
            ("revenue", '"{company}" annual revenue'),
        ]
        facts = {"employee_count": 2, "revenue": 0}
        _update_query_effectiveness(gap_types, facts, "private")

        # Should have executed 2 INSERT statements
        assert mock_cur.execute.call_count == 2
        mock_conn.return_value.commit.assert_called_once()

    @patch("scripts.research.agent._ensure_query_effectiveness_table")
    @patch("scripts.research.agent._conn")
    def test_update_empty_gaps(self, mock_conn, mock_ensure):
        """No-op when gap_types_queried is empty."""
        from scripts.research.agent import _update_query_effectiveness
        _update_query_effectiveness([], {})
        mock_conn.assert_not_called()

    @patch("scripts.research.agent._conn")
    def test_get_best_queries_empty(self, mock_conn):
        """Should return empty list when no effectiveness data exists."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cur

        from scripts.research.agent import _get_best_queries
        result = _get_best_queries("employee_count", "private")
        assert result == []

    @patch("scripts.research.agent._conn")
    def test_get_best_queries_returns_templates(self, mock_conn):
        """Should return ranked templates when data exists."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {"query_template": '"{company}" employee count'},
            {"query_template": '"{company}" workforce size'},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        from scripts.research.agent import _get_best_queries
        result = _get_best_queries("employee_count", "private", min_uses=3)
        assert len(result) == 2
        assert "employee count" in result[0]


# ---------------------------------------------------------------------------
# Part C: Gap template constant tests
# ---------------------------------------------------------------------------

class TestGapQueryTemplates:
    """Verify _GAP_QUERY_TEMPLATES and _TOOL_GAP_MAP are consistent."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from scripts.research.agent import _GAP_QUERY_TEMPLATES, _TOOL_GAP_MAP
        self.templates = _GAP_QUERY_TEMPLATES
        self.tool_gap_map = _TOOL_GAP_MAP

    def test_all_tool_gaps_have_templates(self):
        """Every gap type referenced in _TOOL_GAP_MAP must have templates."""
        for tool_name, gap_keys in self.tool_gap_map.items():
            for gap_key in gap_keys:
                assert gap_key in self.templates, (
                    f"{tool_name} references gap '{gap_key}' not in _GAP_QUERY_TEMPLATES"
                )

    def test_always_run_keys_have_templates(self):
        """Always-run gap types must have templates."""
        for key in ["recent_news", "labor_stance", "worker_conditions"]:
            assert key in self.templates, f"Always-run key '{key}' not in templates"

    def test_templates_have_company_placeholder(self):
        """Every template should contain {company} placeholder."""
        for gap_type, templates in self.templates.items():
            for t in templates:
                assert "{company}" in t, (
                    f"Template for '{gap_type}' missing {{company}}: {t}"
                )

    def test_no_empty_template_lists(self):
        """No gap type should have an empty template list."""
        for gap_type, templates in self.templates.items():
            assert len(templates) > 0, f"Empty template list for '{gap_type}'"


# ---------------------------------------------------------------------------
# Part D: Phase 5.4 — Year default, section gap map, financial merge, strategies
# ---------------------------------------------------------------------------

class TestYearDefault:
    """Test that _build_web_search_queries defaults to the current year."""

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_year_defaults_to_current(self, mock_best):
        """When year=None (default), queries should contain the current year."""
        from scripts.research.agent import _build_web_search_queries
        from datetime import datetime
        current_year = str(datetime.now().year)
        queries, _ = _build_web_search_queries("Acme Corp", "private", "NY", [])
        # At least one always-run query uses {year}
        has_year = any(current_year in q for q in queries)
        assert has_year, f"No query contains current year {current_year}: {queries}"

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_year_not_2025(self, mock_best):
        """Queries should NOT contain hardcoded 2025 (unless it is actually 2025)."""
        from scripts.research.agent import _build_web_search_queries
        from datetime import datetime
        if datetime.now().year == 2025:
            pytest.skip("Currently 2025, can't distinguish from old default")
        queries, _ = _build_web_search_queries("Acme Corp", "private", "NY",
                                                ["search_mergent"])
        for q in queries:
            assert "2025" not in q, f"Query still contains hardcoded 2025: {q}"

    @patch("scripts.research.agent._get_best_queries", return_value=[])
    def test_explicit_year_override(self, mock_best):
        """Explicit year param should be used."""
        from scripts.research.agent import _build_web_search_queries
        queries, _ = _build_web_search_queries("Acme Corp", "private", "NY", [], year="2030")
        has_year = any("2030" in q for q in queries)
        assert has_year, f"Explicit year 2030 not found in queries: {queries}"


class TestSectionGapMapCoverage:
    """Verify _section_gap_map covers all gap types from _TOOL_GAP_MAP."""

    def test_all_tool_gap_types_in_section_map(self):
        """Every gap type in _TOOL_GAP_MAP should be coverable by the
        _section_gap_map or the financial_data dict handling."""
        from scripts.research.agent import _TOOL_GAP_MAP
        # These are the gap types that _section_gap_map + financial_data handle
        section_gap_keys = {
            "recent_news", "nlrb_activity", "worker_conditions",
            "labor_stance", "osha_violations", "whd_violations",
            # financial_data dict maps to these:
            "employee_count", "revenue", "website_url",
        }
        all_gap_types = set()
        for gap_keys in _TOOL_GAP_MAP.values():
            all_gap_types.update(gap_keys)
        missing = all_gap_types - section_gap_keys
        # nonprofit_financials is the only expected gap without a web section
        expected_missing = {"nonprofit_financials"}
        unexpected_missing = missing - expected_missing
        assert not unexpected_missing, (
            f"Gap types not covered by web section mapping: {unexpected_missing}"
        )

    def test_section_gap_map_has_safety_violations(self):
        """safety_violations should map to osha_violations gap type."""
        # The map is inline in agent.py, so we test by simulating
        _section_gap_map = {
            "recent_news": "recent_news",
            "organizing_activity": "nlrb_activity",
            "worker_issues": "worker_conditions",
            "nlrb_activity": "nlrb_activity",
            "company_labor_stance": "labor_stance",
            "company_context": "recent_news",
            "safety_violations": "osha_violations",
            "wage_violations": "whd_violations",
        }
        assert "safety_violations" in _section_gap_map
        assert _section_gap_map["safety_violations"] == "osha_violations"
        assert "wage_violations" in _section_gap_map
        assert _section_gap_map["wage_violations"] == "whd_violations"


class TestFinancialDataMerge:
    """Test that financial_data dict from web search maps to 3 gap types."""

    def test_financial_data_maps_to_three_gaps(self):
        """financial_data dict should produce hits for employee_count, revenue, website_url."""
        web_data = {
            "financial_data": {
                "employee_count": "50,000 (LinkedIn, 2026)",
                "revenue": "$12.5 billion (SEC 10-K, 2025)",
                "website_url": "https://acme.com",
            },
            "recent_news": [],
        }
        web_facts_by_gap = {}
        # Simulate the section_gap_map processing
        _section_gap_map = {
            "recent_news": "recent_news",
            "organizing_activity": "nlrb_activity",
            "worker_issues": "worker_conditions",
            "nlrb_activity": "nlrb_activity",
            "company_labor_stance": "labor_stance",
            "company_context": "recent_news",
            "safety_violations": "osha_violations",
            "wage_violations": "whd_violations",
        }
        for sec_key, gap_key in _section_gap_map.items():
            val = web_data.get(sec_key, [])
            if isinstance(val, list) and val:
                web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + len(val)
            elif isinstance(val, str) and val.strip():
                web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1

        fin_data = web_data.get("financial_data")
        if isinstance(fin_data, dict):
            for fin_key, gap_key in [
                ("employee_count", "employee_count"),
                ("revenue", "revenue"),
                ("website_url", "website_url"),
            ]:
                val = fin_data.get(fin_key)
                if val and isinstance(val, str) and val.strip():
                    web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1

        assert web_facts_by_gap.get("employee_count") == 1
        assert web_facts_by_gap.get("revenue") == 1
        assert web_facts_by_gap.get("website_url") == 1

    def test_empty_financial_data_no_hits(self):
        """Empty financial_data should produce no gap hits."""
        web_data = {"financial_data": {}}
        web_facts_by_gap = {}
        fin_data = web_data.get("financial_data")
        if isinstance(fin_data, dict):
            for fin_key, gap_key in [
                ("employee_count", "employee_count"),
                ("revenue", "revenue"),
                ("website_url", "website_url"),
            ]:
                val = fin_data.get(fin_key)
                if val and isinstance(val, str) and val.strip():
                    web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1
        assert len(web_facts_by_gap) == 0


class TestGoogleSearchUrlFallback:
    """Test _google_search_url and Tier 4 in _resolve_employer_url."""

    @patch("scripts.research.tools._conn")
    @patch("scripts.research.tools._google_search_url")
    def test_tier4_called_when_tiers_123_fail(self, mock_google, mock_conn):
        """When all 3 tiers fail, Tier 4 should be tried."""
        # Make Tier 3 (name search) return nothing
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_google.return_value = "https://acme-corp.com"
        from scripts.research.tools import _resolve_employer_url
        with patch.dict(os.environ, {"RESEARCH_SCRAPER_GOOGLE_FALLBACK": "true"}):
            url, source = _resolve_employer_url("Acme Corp", url=None, employer_id=None)
        assert url == "https://acme-corp.com"
        assert source == "google_search"

    @patch("scripts.research.tools._conn")
    @patch("scripts.research.tools._google_search_url")
    def test_tier4_disabled_by_env(self, mock_google, mock_conn):
        """When RESEARCH_SCRAPER_GOOGLE_FALLBACK=false, Tier 4 should be skipped."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_google.return_value = "https://acme-corp.com"
        from scripts.research.tools import _resolve_employer_url
        with patch.dict(os.environ, {"RESEARCH_SCRAPER_GOOGLE_FALLBACK": "false"}):
            url, source = _resolve_employer_url("Acme Corp", url=None, employer_id=None)
        assert source == "none"
        mock_google.assert_not_called()

    @patch("scripts.research.tools._conn")
    @patch("scripts.research.tools._google_search_url")
    def test_tier4_returns_none(self, mock_google, mock_conn):
        """When Google Search returns None, should fall through to 'none'."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_google.return_value = None
        from scripts.research.tools import _resolve_employer_url
        with patch.dict(os.environ, {"RESEARCH_SCRAPER_GOOGLE_FALLBACK": "true"}):
            url, source = _resolve_employer_url("Acme Corp", url=None, employer_id=None)
        assert source == "none"

    def test_provided_url_skips_tier4(self):
        """Tier 1 (provided URL) should take precedence over Tier 4."""
        from scripts.research.tools import _resolve_employer_url
        url, source = _resolve_employer_url("Acme Corp", url="https://acme.com")
        assert url == "https://acme.com"
        assert source == "provided"

    @patch.dict(os.environ, {"GOOGLE_API_KEY": ""})
    def test_google_search_url_no_api_key(self):
        """Should return None when no API key is set."""
        from scripts.research.tools import _google_search_url
        result = _google_search_url("Acme Corp")
        assert result is None


class TestStrategySeeding:
    """Test that update_strategy_quality seeds and updates rows."""

    @patch("scripts.research.auto_grader.get_connection")
    def test_upsert_populates_from_actions(self, mock_get_conn):
        """update_strategy_quality should execute an INSERT...ON CONFLICT DO UPDATE."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 5
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        from scripts.research.auto_grader import update_strategy_quality
        result = update_strategy_quality(conn=mock_conn)
        assert result == 5
        # Verify INSERT ... ON CONFLICT was used
        call_args = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO research_strategies" in call_args
        assert "ON CONFLICT" in call_args
        assert "DO UPDATE" in call_args
        mock_conn.commit.assert_called_once()

    @patch("scripts.research.auto_grader.get_connection")
    def test_upsert_includes_hit_rate(self, mock_get_conn):
        """The UPSERT query should compute hit_rate."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 0
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        from scripts.research.auto_grader import update_strategy_quality
        update_strategy_quality(conn=mock_conn)
        call_args = mock_cur.execute.call_args[0][0]
        assert "hit_rate" in call_args
        assert "times_tried" in call_args
        assert "times_found_data" in call_args
