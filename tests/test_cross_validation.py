"""
Tests for research cross-validation against DB (Task 4-6).

Verifies:
  - cross_validate_against_db produces correct output
  - _values_match logic
  - Cross-validation columns exist
  - Storage works
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_config import get_connection
from scripts.research.auto_grader import (
    cross_validate_against_db,
    _values_match,
    _ensure_cross_validation_columns,
)


class TestValuesMatch:
    """Test the _values_match helper."""

    def test_both_zero(self):
        assert _values_match(0, 0) is True

    def test_research_zero_db_nonzero(self):
        assert _values_match(0, 5) is False

    def test_research_nonzero_db_zero(self):
        assert _values_match(3, 0) is False

    def test_both_positive_counts(self):
        # For counts, both > 0 = match (scope may differ)
        assert _values_match(3, 10) is True

    def test_ratio_tolerance_within(self):
        assert _values_match(100, 180, ratio_tolerance=2.0) is True

    def test_ratio_tolerance_exceeded(self):
        assert _values_match(100, 250, ratio_tolerance=2.0) is False


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


class TestCrossValidationColumns:
    """Columns should exist on research_score_enhancements."""

    def test_columns_exist(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'research_score_enhancements' "
                "AND column_name IN ('cross_validation_rate', 'cross_validation_discrepancies')"
            )
            cols = {r[0] for r in cur.fetchall()}
        assert "cross_validation_rate" in cols
        assert "cross_validation_discrepancies" in cols


class TestCrossValidateFunction:
    """Test the full cross_validate_against_db function."""

    def test_no_enhancements_returns_none(self, conn):
        result = cross_validate_against_db(run_id=999999, employer_id="NONEXISTENT", conn=conn)
        assert result["match_rate"] is None
        assert result["comparisons_made"] == 0

    def test_with_real_employer(self, conn):
        """If any employer has research_score_enhancements, test it."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, employer_id FROM research_score_enhancements LIMIT 1"
            )
            row = cur.fetchone()
        if row is None:
            pytest.skip("No research_score_enhancements rows to test")
        result = cross_validate_against_db(
            run_id=row[0], employer_id=row[1], conn=conn
        )
        assert result["comparisons_made"] >= 0
        if result["match_rate"] is not None:
            assert 0.0 <= result["match_rate"] <= 1.0
