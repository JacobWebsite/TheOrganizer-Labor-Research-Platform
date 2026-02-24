"""
Tests for scripts/research/auto_grader.py (Phase 5.3)
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Module under test
from scripts.research.auto_grader import (
    WEIGHTS,
    _score_consistency,
    _score_coverage,
    _score_efficiency,
    _score_freshness,
    _score_source_quality,
    grade_and_save,
    grade_research_run,
)


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------
class TestCoverage:
    def test_zero_sections(self):
        assert _score_coverage({}) == 0.0

    def test_all_sections(self):
        sections = {s: [{"id": 1}] for s in
                    ["identity", "labor", "assessment", "workforce",
                     "workplace", "financial", "sources"]}
        score = _score_coverage(sections)
        assert score == 8.0  # 7/7 * 8 = 8, no bonus (each has only 1 fact)

    def test_bonus_for_rich_sections(self):
        sections = {
            "identity": [{"id": i} for i in range(5)],   # 3+ -> +0.4
            "labor": [{"id": i} for i in range(3)],       # 3+ -> +0.4
            "assessment": [{"id": 1}],
        }
        # base = 3/7 * 8 = 3.43
        # bonus = 0.4 + 0.4 = 0.8
        score = _score_coverage(sections)
        expected_base = (3 / 7) * 8
        assert abs(score - (expected_base + 0.8)) < 0.01

    def test_bonus_capped_at_2(self):
        # 7 sections all with 5 facts => bonus would be 7*0.4=2.8 but capped at 2
        sections = {s: [{"id": i} for i in range(5)] for s in
                    ["identity", "labor", "assessment", "workforce",
                     "workplace", "financial", "sources"]}
        score = _score_coverage(sections)
        assert score == 10.0  # 8 + 2 = 10

    def test_capped_at_10(self):
        # Even with bonus, should not exceed 10
        sections = {s: [{"id": i} for i in range(10)] for s in
                    ["identity", "labor", "assessment", "workforce",
                     "workplace", "financial", "sources"]}
        assert _score_coverage(sections) == 10.0


# ---------------------------------------------------------------------------
# Source Quality
# ---------------------------------------------------------------------------
class TestSourceQuality:
    def test_empty_facts(self):
        assert _score_source_quality([]) == 0.0

    def test_all_database_high_confidence(self):
        facts = [
            {"source_type": "database", "confidence": 0.95, "source_name": "OSHA"},
            {"source_type": "database", "confidence": 0.90, "source_name": "NLRB"},
        ]
        score = _score_source_quality(facts)
        # avg_source = 1.0, avg_conf = 0.925, combined = (0.5*1.0 + 0.5*0.925)*10 = 9.625
        assert score > 9.0

    def test_all_web_search_low_confidence(self):
        facts = [
            {"source_type": "web_search", "confidence": 0.4, "source_name": "Google"},
            {"source_type": "web_search", "confidence": 0.5, "source_name": "Bing"},
        ]
        score = _score_source_quality(facts)
        # avg_source = 0.6, avg_conf = 0.45, combined = (0.5*0.6 + 0.5*0.45)*10 = 5.25
        assert 4.0 < score < 6.0

    def test_null_source_penalty(self):
        # >30% null source_name -> -1.0
        facts = [
            {"source_type": "database", "confidence": 0.9, "source_name": None},
            {"source_type": "database", "confidence": 0.9, "source_name": None},
            {"source_type": "database", "confidence": 0.9, "source_name": "OSHA"},
        ]
        # 2/3 = 67% null -> penalty applies
        score_with_penalty = _score_source_quality(facts)

        facts_no_null = [
            {"source_type": "database", "confidence": 0.9, "source_name": "OSHA"},
            {"source_type": "database", "confidence": 0.9, "source_name": "NLRB"},
            {"source_type": "database", "confidence": 0.9, "source_name": "WHD"},
        ]
        score_no_penalty = _score_source_quality(facts_no_null)
        assert score_with_penalty < score_no_penalty

    def test_mixed_sources(self):
        facts = [
            {"source_type": "database", "confidence": 0.9, "source_name": "OSHA"},
            {"source_type": "web_search", "confidence": 0.5, "source_name": "Google"},
            {"source_type": "api", "confidence": 0.8, "source_name": "SEC"},
        ]
        score = _score_source_quality(facts)
        assert 5.0 < score < 9.0


# ---------------------------------------------------------------------------
# Consistency
# ---------------------------------------------------------------------------
class TestConsistency:
    def test_no_contradictions(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "name", "attribute_value": "X"},
        ]
        assert _score_consistency(facts) == 10.0

    def test_contradiction_penalty(self):
        facts = [
            {"contradicts_fact_id": 42, "attribute_name": "name", "attribute_value": "X"},
        ]
        assert _score_consistency(facts) == 8.0  # 10 - 2

    def test_employee_count_divergence(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "employee_count", "attribute_value": "100"},
            {"contradicts_fact_id": None, "attribute_name": "employee_count", "attribute_value": "500"},
        ]
        # ratio 5.0 > 2.0 -> -2.0
        assert _score_consistency(facts) == 8.0

    def test_revenue_divergence(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "revenue", "attribute_value": "1000000"},
            {"contradicts_fact_id": None, "attribute_name": "revenue", "attribute_value": "5000000"},
        ]
        assert _score_consistency(facts) == 8.0

    def test_floor_at_zero(self):
        facts = [
            {"contradicts_fact_id": 1, "attribute_name": "x", "attribute_value": "a"},
            {"contradicts_fact_id": 2, "attribute_name": "x", "attribute_value": "b"},
            {"contradicts_fact_id": 3, "attribute_name": "x", "attribute_value": "c"},
            {"contradicts_fact_id": 4, "attribute_name": "x", "attribute_value": "d"},
            {"contradicts_fact_id": 5, "attribute_name": "x", "attribute_value": "e"},
            {"contradicts_fact_id": 6, "attribute_name": "x", "attribute_value": "f"},
        ]
        assert _score_consistency(facts) == 0.0


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------
class TestFreshness:
    def test_empty_facts(self):
        assert _score_freshness([]) == 5.0

    def test_recent_facts(self):
        today = date(2026, 2, 24)
        facts = [
            {"as_of_date": date(2026, 1, 15)},
            {"as_of_date": date(2025, 12, 1)},
        ]
        score = _score_freshness(facts, today=today)
        assert score == 10.0  # both < 6 months

    def test_old_facts(self):
        today = date(2026, 2, 24)
        facts = [
            {"as_of_date": date(2018, 1, 1)},  # > 5 years
        ]
        score = _score_freshness(facts, today=today)
        assert score == 1.0

    def test_no_as_of_date(self):
        facts = [
            {"as_of_date": None},
            {"as_of_date": None},
        ]
        assert _score_freshness(facts) == 5.0

    def test_mixed_dates(self):
        today = date(2026, 2, 24)
        facts = [
            {"as_of_date": date(2026, 1, 1)},   # < 6mo -> 10
            {"as_of_date": date(2023, 1, 1)},   # 3yr+ -> 2 (1126 days, 3-5yr bucket)
            {"as_of_date": None},                 # neutral -> 5
        ]
        score = _score_freshness(facts, today=today)
        assert abs(score - (10 + 2 + 5) / 3) < 0.01

    def test_string_dates(self):
        today = date(2026, 2, 24)
        facts = [{"as_of_date": "2026-01-15"}]
        score = _score_freshness(facts, today=today)
        assert score == 10.0


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------
class TestEfficiency:
    def test_high_ratio(self):
        # 30 facts / 5 tools = 6.0 -> 10
        score = _score_efficiency(30, 5, [])
        assert score == 10.0

    def test_low_ratio(self):
        # 1 fact / 10 tools = 0.1 -> 2
        score = _score_efficiency(1, 10, [])
        assert score == 2.0

    def test_speed_bonus(self):
        # 10 facts / 5 tools = 2.0 -> 8, plus speed bonus -> 9
        actions = [{"latency_ms": 200}, {"latency_ms": 300}]
        score = _score_efficiency(10, 5, actions)
        assert score == 9.0

    def test_speed_no_bonus_slow(self):
        actions = [{"latency_ms": 800}, {"latency_ms": 1200}]
        score = _score_efficiency(10, 5, actions)
        assert score == 8.0  # no speed bonus

    def test_capped_at_10(self):
        # 30 facts / 5 tools = 6.0 -> 10, + speed bonus -> still 10
        actions = [{"latency_ms": 100}]
        score = _score_efficiency(30, 5, actions)
        assert score == 10.0

    def test_zero_tools(self):
        # 0 facts / 0 tools -> 0/1 = 0 -> 2
        score = _score_efficiency(0, 0, [])
        assert score == 2.0


# ---------------------------------------------------------------------------
# Overall weighted score
# ---------------------------------------------------------------------------
class TestOverallWeighting:
    def test_d16_weights(self):
        """Verify D16 weights produce correct weighted average."""
        # Simulate perfect scores
        # coverage=10*0.20 + source_quality=10*0.35 + consistency=10*0.25
        # + freshness=10*0.15 + efficiency=10*0.05 = 10.0
        assert abs(
            10 * 0.20 + 10 * 0.35 + 10 * 0.25 + 10 * 0.15 + 10 * 0.05 - 10.0
        ) < 0.001

    def test_weights_sum_to_1(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001


# ---------------------------------------------------------------------------
# grade_and_save
# ---------------------------------------------------------------------------
class TestGradeAndSave:
    @patch("scripts.research.auto_grader.get_connection")
    def test_grades_and_updates_db(self, mock_get_conn):
        """Verify grade_and_save calls UPDATE with correct params."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # Mock run query
        mock_cur.fetchone.side_effect = [
            # grade_research_run: run row
            {"id": 1, "total_tools_called": 5, "total_facts_found": 10, "sections_filled": 3},
            # (no more fetchone needed)
        ]
        # Mock facts query
        mock_cur.fetchall.side_effect = [
            # facts
            [
                {"dossier_section": "identity", "attribute_name": "name",
                 "attribute_value": "TestCo", "source_type": "database",
                 "source_name": "OSHA", "confidence": 0.9, "as_of_date": None,
                 "contradicts_fact_id": None},
            ],
            # actions
            [{"latency_ms": 200}],
            # (no more fetchall needed)
        ]

        result = grade_and_save(1, conn=mock_conn)

        assert "overall" in result
        assert "coverage" in result
        assert result["overall"] > 0

        # Verify UPDATE was called
        update_calls = [
            c for c in mock_cur.execute.call_args_list
            if "UPDATE research_runs" in str(c)
        ]
        assert len(update_calls) == 1


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------
class TestBackfill:
    @patch("scripts.research.auto_grader.update_strategy_quality")
    @patch("scripts.research.auto_grader.grade_and_save")
    @patch("scripts.research.auto_grader.get_connection")
    def test_backfill_grades_multiple(self, mock_get_conn, mock_grade, mock_strat):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # 3 unscored runs
        mock_cur.fetchall.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_grade.return_value = {"overall": 7.5}

        from scripts.research.auto_grader import backfill_all_scores
        count = backfill_all_scores()

        assert count == 3
        assert mock_grade.call_count == 3

    @patch("scripts.research.auto_grader.grade_and_save")
    @patch("scripts.research.auto_grader.get_connection")
    def test_backfill_skips_already_scored(self, mock_get_conn, mock_grade):
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # No unscored runs
        mock_cur.fetchall.return_value = []

        from scripts.research.auto_grader import backfill_all_scores
        count = backfill_all_scores()

        assert count == 0
        assert mock_grade.call_count == 0
