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
