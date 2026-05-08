"""
Tests for scripts/research/auto_grader.py (Phase 5.3, updated Phase 5.7)
"""

from datetime import date
from unittest.mock import MagicMock, patch


# Module under test
from scripts.research.auto_grader import (
    WEIGHTS,
    _score_consistency,
    _score_coverage,
    _score_efficiency,
    _score_freshness,
    _score_source_quality,
    _score_actionability,
    grade_and_save,
)


# ---------------------------------------------------------------------------
# Coverage (Phase 5.7: field-level scoring)
# ---------------------------------------------------------------------------
class TestCoverage:
    def test_zero_sections(self):
        assert _score_coverage({}) == 0.0

    def test_all_sections_section_fallback(self):
        """Fallback section-level scoring when no dossier_json."""
        sections = {s: [{"id": 1}] for s in
                    ["identity", "labor", "assessment", "workforce",
                     "workplace", "financial", "sources"]}
        score = _score_coverage(sections)
        assert score == 8.0  # 7/7 * 8 = 8, no bonus (each has only 1 fact)

    def test_bonus_for_rich_sections_fallback(self):
        """Fallback: bonus for 3+ facts per section."""
        sections = {
            "identity": [{"id": i} for i in range(5)],   # 3+ -> +0.4
            "labor": [{"id": i} for i in range(3)],       # 3+ -> +0.4
            "assessment": [{"id": 1}],
        }
        score = _score_coverage(sections)
        expected_base = (3 / 7) * 8
        assert abs(score - (expected_base + 0.8)) < 0.01

    def test_bonus_capped_at_2(self):
        sections = {s: [{"id": i} for i in range(5)] for s in
                    ["identity", "labor", "assessment", "workforce",
                     "workplace", "financial", "sources"]}
        score = _score_coverage(sections)
        assert score == 10.0  # 8 + 2 = 10

    def test_field_level_all_filled(self):
        """Phase 5.7: field-level scoring with dossier_json."""
        dossier = {"dossier": {
            "identity": {"name": "TestCo", "state": "NY"},
            "financial": {"revenue": "$1B", "employee_count": "500"},
            "workforce": {"job_posting_count": "50"},
        }}
        score = _score_coverage({}, dossier_json=dossier)
        # 5 fields, 5 filled -> 100% -> 10.0
        assert score == 10.0

    def test_field_level_half_filled(self):
        """Phase 5.7: half fields null -> ~5.0."""
        dossier = {"dossier": {
            "identity": {"name": "TestCo", "state": None},
            "financial": {"revenue": "$1B", "employee_count": None},
        }}
        score = _score_coverage({}, dossier_json=dossier)
        # 4 fields, 2 filled -> 50% -> 5.0
        assert abs(score - 5.0) < 0.01

    def test_field_level_empty_dossier(self):
        """Phase 5.7: dossier with no sections -> 0."""
        dossier = {"dossier": {}}
        score = _score_coverage({}, dossier_json=dossier)
        assert score == 0.0

    def test_placeholder_penalty(self):
        """Phase 5.7: placeholder values like 'unknown' get penalized."""
        dossier = {"dossier": {
            "identity": {"name": "TestCo", "year_founded": "unknown"},
            "financial": {"revenue": "N/A", "employee_count": "not found"},
        }}
        score = _score_coverage({}, dossier_json=dossier)
        # 4 fields: name filled, 3 are placeholders (don't count as filled)
        # fill_rate = 1/4 = 0.25 -> base 2.5
        # 3 placeholders * 0.5 = 1.5 penalty
        # score = 2.5 - 1.5 = 1.0
        assert abs(score - 1.0) < 0.01

    def test_generic_baseline_penalty(self):
        """Phase 5.7: unlabeled BLS generic baseline is penalized."""
        dossier = {"dossier": {
            "workforce": {
                "demographic_profile": "race_white=76, race_black=12, gender_male=53, avg_age=42",
            },
        }}
        score = _score_coverage({}, dossier_json=dossier)
        # 1 field, but it's generic baseline -> placeholder penalty
        # fill_rate = 0/1 = 0 (treated as placeholder), base = 0
        # penalty = 0.5
        assert score == 0.0  # max(0 - 0.5, 0) = 0

    def test_labeled_baseline_no_penalty(self):
        """Phase 5.7: properly labeled INDUSTRY BASELINE is not penalized."""
        dossier = {"dossier": {
            "workforce": {
                "demographic_profile": "INDUSTRY BASELINE (NAICS 31): race_white=72, race_black=10",
            },
        }}
        score = _score_coverage({}, dossier_json=dossier)
        # 1 field, filled and labeled -> 10.0
        assert score == 10.0


# ---------------------------------------------------------------------------
# Source Quality
# ---------------------------------------------------------------------------
class TestSourceQuality:
    def test_empty_facts(self):
        assert _score_source_quality([]) == 5.0  # neutral when no real facts

    def test_all_database_high_confidence(self):
        facts = [
            {"source_type": "database", "confidence": 0.95, "source_name": "OSHA"},
            {"source_type": "database", "confidence": 0.90, "source_name": "NLRB"},
        ]
        score = _score_source_quality(facts)
        assert score > 9.0

    def test_all_web_search_low_confidence(self):
        facts = [
            {"source_type": "web_search", "confidence": 0.4, "source_name": "Google"},
            {"source_type": "web_search", "confidence": 0.5, "source_name": "Bing"},
        ]
        score = _score_source_quality(facts)
        assert 4.0 < score < 6.0

    def test_null_source_penalty(self):
        facts = [
            {"source_type": "database", "confidence": 0.9, "source_name": None},
            {"source_type": "database", "confidence": 0.9, "source_name": None},
            {"source_type": "database", "confidence": 0.9, "source_name": "OSHA"},
        ]
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
        assert _score_consistency(facts) == 8.0

    def test_revenue_divergence(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "revenue", "attribute_value": "1000000"},
            {"contradicts_fact_id": None, "attribute_name": "revenue", "attribute_value": "5000000"},
        ]
        assert _score_consistency(facts) == 8.0

    def test_floor_at_zero(self):
        facts = [
            {"contradicts_fact_id": i, "attribute_name": "x", "attribute_value": "a"}
            for i in range(1, 7)
        ]
        assert _score_consistency(facts) == 0.0


# ---------------------------------------------------------------------------
# Actionability (Phase 5.7 NEW)
# ---------------------------------------------------------------------------
class TestActionability:
    def test_empty_dossier(self):
        assert _score_actionability(None) == 0.0
        assert _score_actionability({}) == 0.0
        assert _score_actionability({"dossier": {}}) == 0.0

    def test_recommended_approach_long(self):
        """recommended_approach > 50 chars -> +3."""
        dossier = {"dossier": {"assessment": {
            "recommended_approach": "X" * 60,
        }}}
        score = _score_actionability(dossier)
        assert score == 3.0

    def test_recommended_approach_short(self):
        """recommended_approach < 50 chars -> +0."""
        dossier = {"dossier": {"assessment": {
            "recommended_approach": "short",
        }}}
        assert _score_actionability(dossier) == 0.0

    def test_recommended_approach_null(self):
        dossier = {"dossier": {"assessment": {
            "recommended_approach": None,
        }}}
        assert _score_actionability(dossier) == 0.0

    def test_campaign_strengths_3_items(self):
        """3+ campaign_strengths -> +2."""
        dossier = {"dossier": {"assessment": {
            "campaign_strengths": ["a", "b", "c"],
        }}}
        assert _score_actionability(dossier) == 2.0

    def test_campaign_strengths_2_items(self):
        """< 3 campaign_strengths -> +0."""
        dossier = {"dossier": {"assessment": {
            "campaign_strengths": ["a", "b"],
        }}}
        assert _score_actionability(dossier) == 0.0

    def test_campaign_challenges_3_items(self):
        """3+ campaign_challenges -> +2."""
        dossier = {"dossier": {"assessment": {
            "campaign_challenges": ["a", "b", "c", "d"],
        }}}
        assert _score_actionability(dossier) == 2.0

    def test_source_contradictions_present(self):
        """Non-empty source_contradictions -> +1."""
        dossier = {"dossier": {"assessment": {
            "source_contradictions": ["DB says 0 OSHA but web says citations"],
        }}}
        assert _score_actionability(dossier) == 1.0

    def test_source_contradictions_empty(self):
        """Empty source_contradictions -> +0."""
        dossier = {"dossier": {"assessment": {
            "source_contradictions": [],
        }}}
        assert _score_actionability(dossier) == 0.0

    def test_financial_trend_present(self):
        """financial_trend with content -> +1."""
        dossier = {"dossier": {"assessment": {
            "financial_trend": "growing - Revenue increased 15% YoY",
        }}}
        assert _score_actionability(dossier) == 1.0

    def test_exec_compensation_present(self):
        """exec_compensation present -> +1."""
        dossier = {"dossier": {
            "assessment": {},
            "financial": {
                "exec_compensation": [{"name": "CEO", "pay": "$5M"}],
            },
        }}
        assert _score_actionability(dossier) == 1.0

    def test_full_actionability(self):
        """All items present -> max 10."""
        dossier = {"dossier": {
            "assessment": {
                "recommended_approach": "Long recommendation with enough text " * 3,
                "campaign_strengths": ["a", "b", "c"],
                "campaign_challenges": ["a", "b", "c"],
                "source_contradictions": ["contradiction found"],
                "financial_trend": "growing - 15% YoY growth",
            },
            "financial": {
                "exec_compensation": [{"name": "CEO", "pay": "$5M"}],
            },
        }}
        # 3 + 2 + 2 + 1 + 1 + 1 = 10
        assert _score_actionability(dossier) == 10.0

    def test_capped_at_10(self):
        """Score should not exceed 10."""
        dossier = {"dossier": {
            "assessment": {
                "recommended_approach": "X" * 200,
                "campaign_strengths": ["a"] * 10,
                "campaign_challenges": ["a"] * 10,
                "source_contradictions": ["c1", "c2"],
                "financial_trend": "growing strongly",
            },
            "financial": {
                "exec_compensation": [{"name": "CEO"}],
            },
        }}
        assert _score_actionability(dossier) == 10.0


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
        assert score == 10.0

    def test_old_facts(self):
        today = date(2026, 2, 24)
        facts = [
            {"as_of_date": date(2018, 1, 1)},
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
            {"as_of_date": date(2023, 1, 1)},   # 3yr+ -> 2
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
        score = _score_efficiency(30, 5, [])
        assert score == 10.0

    def test_low_ratio(self):
        score = _score_efficiency(1, 10, [])
        assert score == 2.0

    def test_speed_bonus(self):
        actions = [{"latency_ms": 200}, {"latency_ms": 300}]
        score = _score_efficiency(10, 5, actions)
        assert score == 9.0

    def test_speed_no_bonus_slow(self):
        actions = [{"latency_ms": 800}, {"latency_ms": 1200}]
        score = _score_efficiency(10, 5, actions)
        assert score == 8.0

    def test_capped_at_10(self):
        actions = [{"latency_ms": 100}]
        score = _score_efficiency(30, 5, actions)
        assert score == 10.0

    def test_zero_tools(self):
        score = _score_efficiency(0, 0, [])
        assert score == 2.0


# ---------------------------------------------------------------------------
# Overall weighted score
# ---------------------------------------------------------------------------
class TestOverallWeighting:
    def test_weights_sum_to_1(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001

    def test_d16_weights_updated(self):
        """Phase 5.7: verify updated weights."""
        assert WEIGHTS["coverage"] == 0.20
        assert WEIGHTS["source_quality"] == 0.35
        assert WEIGHTS["consistency"] == 0.15
        assert WEIGHTS["actionability"] == 0.15
        assert WEIGHTS["freshness"] == 0.10
        assert WEIGHTS["efficiency"] == 0.05

    def test_perfect_scores(self):
        """Perfect scores across all 6 dimensions = 10.0."""
        total = (
            10 * WEIGHTS["coverage"]
            + 10 * WEIGHTS["source_quality"]
            + 10 * WEIGHTS["consistency"]
            + 10 * WEIGHTS["actionability"]
            + 10 * WEIGHTS["freshness"]
            + 10 * WEIGHTS["efficiency"]
        )
        assert abs(total - 10.0) < 0.001


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

        # Mock run query (now includes dossier_json)
        mock_cur.fetchone.side_effect = [
            {"id": 1, "total_tools_called": 5, "total_facts_found": 10,
             "sections_filled": 3, "dossier_json": None},
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
        ]

        result = grade_and_save(1, conn=mock_conn)

        assert "overall" in result
        assert "coverage" in result
        assert "actionability" in result
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

        mock_cur.fetchall.return_value = []

        from scripts.research.auto_grader import backfill_all_scores
        count = backfill_all_scores()

        assert count == 0
        assert mock_grade.call_count == 0


# ---------------------------------------------------------------------------
# Phase 5.6: DB-vs-web cross-check in consistency scoring
# ---------------------------------------------------------------------------
class TestConsistencyDbVsWeb:
    def test_violation_mismatch_penalty(self):
        """DB says 0 violations but web mentions 'fined' -> -1.0 penalty."""
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "osha_violation_count",
             "attribute_value": "0", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "recent_labor_news",
             "attribute_value": "Company was fined $50,000 for safety violations",
             "source_type": "web_search"},
        ]
        score = _score_consistency(facts)
        assert score == 9.0

    def test_multiple_violation_attrs_penalty(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "osha_violation_count",
             "attribute_value": "0", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "whd_case_count",
             "attribute_value": "0", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "workplace_safety",
             "attribute_value": "OSHA cited the company for a fatal injury",
             "source_type": "web_scrape"},
        ]
        score = _score_consistency(facts)
        assert score == 8.0

    def test_no_false_positive_compliance(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "osha_violation_count",
             "attribute_value": "0", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "safety_record",
             "attribute_value": "The company is OSHA-compliant with a clean safety record",
             "source_type": "web_search"},
        ]
        score = _score_consistency(facts)
        assert score == 10.0

    def test_db_nonzero_no_penalty(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "osha_violation_count",
             "attribute_value": "5", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "recent_labor_news",
             "attribute_value": "Company was fined for violations",
             "source_type": "web_search"},
        ]
        score = _score_consistency(facts)
        assert score == 10.0

    def test_organizing_mismatch_penalty(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "name",
             "attribute_value": "TestCo", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "recent_labor_news",
             "attribute_value": "Workers filed a petition with the NLRB to unionize",
             "source_type": "web_search"},
        ]
        score = _score_consistency(facts)
        assert score == 9.5

    def test_organizing_no_penalty_with_nlrb_data(self):
        facts = [
            {"contradicts_fact_id": None, "attribute_name": "nlrb_election_count",
             "attribute_value": "3", "source_type": "database"},
            {"contradicts_fact_id": None, "attribute_name": "recent_labor_news",
             "attribute_value": "Union organizing campaign ongoing",
             "source_type": "web_search"},
        ]
        score = _score_consistency(facts)
        assert score == 10.0
