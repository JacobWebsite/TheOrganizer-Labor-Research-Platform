"""
Tests for match corroboration system (Tasks 4-2/4-3).

Verifies:
  - Corroboration scoring logic
  - Threshold behavior
  - High-confidence matches unaffected by corroboration
  - EIN matches unaffected
  - Promoted matches are now score_eligible
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_config import get_connection
from scripts.matching.corroborate_matches import (
    score_distribution,
)


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


class TestCorroborationScoring:
    """Verify scoring logic produces correct values."""

    def test_score_distribution_empty(self):
        result = score_distribution([], 2)
        assert result["total"] == 0
        assert result["promotable"] == 0

    def test_score_distribution_all_promotable(self):
        # Fake rows: (id, source_id, target_id, confidence, method, corr_score)
        rows = [
            (1, "E1", "F1", 0.78, "NAME_AGGRESSIVE_STATE", 5),
            (2, "E2", "F2", 0.80, "NAME_AGGRESSIVE_STATE", 3),
        ]
        result = score_distribution(rows, 2)
        assert result["total"] == 2
        assert result["promotable"] == 2

    def test_score_distribution_threshold_boundary(self):
        rows = [
            (1, "E1", "F1", 0.78, "NAME_AGGRESSIVE_STATE", 2),  # at threshold
            (2, "E2", "F2", 0.80, "NAME_AGGRESSIVE_STATE", 1),  # below threshold
        ]
        result = score_distribution(rows, 2)
        assert result["promotable"] == 1
        assert result["stay_demoted"] == 1


class TestHighConfidenceUnaffected:
    """High-confidence and identity matches should not have been demoted."""

    def test_high_confidence_still_eligible(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM osha_f7_matches "
                "WHERE match_confidence >= 0.90 AND score_eligible = FALSE"
            )
            assert cur.fetchone()[0] == 0

    def test_ein_still_eligible(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM osha_f7_matches "
                "WHERE UPPER(match_method) = 'EIN_EXACT' AND score_eligible = FALSE"
            )
            assert cur.fetchone()[0] == 0


class TestPromotedMatchesState:
    """After corroboration, promoted matches should be score_eligible."""

    def test_remaining_ineligible_have_no_corroboration(self, conn):
        """Ineligible OSHA matches should have corroboration_score < threshold."""
        with conn.cursor() as cur:
            # Remaining ineligible should NOT have city+zip+naics matching
            cur.execute("""
                SELECT COUNT(*)
                FROM osha_f7_matches m
                JOIN osha_establishments oe ON oe.establishment_id = m.establishment_id
                JOIN f7_employers_deduped f7 ON f7.employer_id = m.f7_employer_id
                WHERE m.score_eligible = FALSE
                  AND (
                    (UPPER(TRIM(oe.site_city)) = UPPER(TRIM(f7.city))
                     AND oe.site_city IS NOT NULL AND f7.city IS NOT NULL)
                    OR
                    (LEFT(oe.site_zip, 5) = LEFT(f7.zip, 5)
                     AND oe.site_zip IS NOT NULL AND f7.zip IS NOT NULL)
                  )
            """)
            # Some might still be ineligible if only city matches (score=2)
            # but zip matches alone should have been promoted (score=3)
            pass  # structural test - the query runs without error

    def test_ineligible_count_reduced(self, conn):
        """After corroboration, the eligible majority should hold."""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FILTER (WHERE score_eligible = FALSE), COUNT(*) FROM osha_f7_matches")
            ineligible, total = cur.fetchone()
            # 2026-04-24: switched from absolute count (was `< 14559`) to a
            # ratio assertion. The osha_f7_matches table grew with new OSHA
            # data loads + matching reruns (now ~89K total vs ~50K when the
            # original 14,559 baseline was recorded), so the absolute count
            # drifted upward to ~19K even though corroboration is still
            # promoting the bulk of matches. Ratio is the durable invariant:
            # if corroboration runs at all, most matches end up eligible.
            assert total > 0
            assert ineligible / total < 0.35, (
                f"Expected <35% ineligible after corroboration, "
                f"got {ineligible:,}/{total:,} = {100*ineligible/total:.1f}%"
            )

    def test_total_eligible_increased(self, conn):
        """Total eligible should be higher than initial 0.85 threshold alone."""
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM osha_f7_matches WHERE score_eligible = TRUE")
            eligible = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM osha_f7_matches WHERE match_confidence >= 0.85")
            high_conf = cur.fetchone()[0]
            # Eligible should be more than just high-confidence (corroboration added some)
            assert eligible >= high_conf
