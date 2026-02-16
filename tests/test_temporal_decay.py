"""
Temporal decay tests for Phase 5.1.

Tests that the OSHA and NLRB scoring factors properly apply time-based
decay, reducing the weight of older data in the organizing scorecard.

OSHA: half-life 10 years (lambda = 0.0693)
NLRB: half-life 7 years (lambda = 0.0990), score-level decay on employer-specific predictions

Run with: py -m pytest tests/test_temporal_decay.py -v
"""
import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routers.organizing import _explain_osha


# ============================================================================
# A. DECAY MATH UNIT TESTS (no DB needed)
# ============================================================================

OSHA_LAMBDA = 0.0693   # ln(2)/10
NLRB_LAMBDA = 0.0990   # ln(2)/7


def osha_decay(years_ago):
    """Expected OSHA decay factor for a given number of years."""
    return math.exp(-OSHA_LAMBDA * max(0, years_ago))


def nlrb_decay(years_ago):
    """Expected NLRB decay factor for a given number of years."""
    return math.exp(-NLRB_LAMBDA * max(0, years_ago))


class TestOshaDecayMath:
    """Verify the exponential decay formula at key time points."""

    def test_zero_years(self):
        assert osha_decay(0) == pytest.approx(1.0)

    def test_one_year(self):
        assert osha_decay(1) == pytest.approx(0.933, abs=0.001)

    def test_five_years(self):
        assert osha_decay(5) == pytest.approx(0.707, abs=0.001)

    def test_ten_years_is_half(self):
        assert osha_decay(10) == pytest.approx(0.5, abs=0.001)

    def test_twenty_years(self):
        assert osha_decay(20) == pytest.approx(0.25, abs=0.001)

    def test_negative_clamped(self):
        assert osha_decay(-5) == pytest.approx(1.0)


class TestNlrbDecayMath:
    """Verify NLRB decay at key time points."""

    def test_zero_years(self):
        assert nlrb_decay(0) == pytest.approx(1.0)

    def test_seven_years_is_half(self):
        assert nlrb_decay(7) == pytest.approx(0.5, abs=0.001)

    def test_fourteen_years_is_quarter(self):
        assert nlrb_decay(14) == pytest.approx(0.25, abs=0.001)


# ============================================================================
# B. EXPLANATION FUNCTION TESTS (no DB needed)
# ============================================================================

class TestExplainOshaWithDecay:
    """_explain_osha should mention decay when factor is significant."""

    def test_no_decay_when_recent(self):
        msg = _explain_osha(5, 2.0, decay_factor=0.97)
        assert "reduced" not in msg
        assert "2.0x industry average" in msg

    def test_decay_mentioned_when_significant(self):
        msg = _explain_osha(10, 1.5, decay_factor=0.45)
        assert "reduced 55%" in msg

    def test_no_violations(self):
        msg = _explain_osha(0, 0.0, decay_factor=0.3)
        assert msg == "No OSHA violations on record"

    def test_none_decay_factor(self):
        msg = _explain_osha(3, 1.2, decay_factor=None)
        assert "reduced" not in msg

    def test_full_decay(self):
        msg = _explain_osha(8, 0.5, decay_factor=0.10)
        assert "reduced 90%" in msg


# ============================================================================
# C. MV INTEGRATION TESTS (require database)
# ============================================================================

@pytest.fixture(scope="module")
def db():
    """Shared database connection for MV tests."""
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


class TestMvDecayColumns:
    """Verify that the MV has the new temporal decay columns."""

    def test_osha_decay_factor_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT osha_decay_factor FROM mv_organizing_scorecard LIMIT 1
        """)
        row = cur.fetchone()
        assert row is not None
        assert 0 < row[0] <= 1.0

    def test_nlrb_decay_factor_always_one_in_mv(self, db):
        """NLRB decay is always 1.0 in MV — no employer-specific NLRB data for unmatched rows."""
        cur = db.cursor()
        cur.execute("""
            SELECT DISTINCT nlrb_decay_factor FROM mv_organizing_scorecard
        """)
        rows = cur.fetchall()
        assert len(rows) == 1
        assert float(rows[0][0]) == pytest.approx(1.0)

    def test_last_election_date_always_null_in_mv(self, db):
        """last_election_date is NULL in MV — NLRB routes through F7 which MV excludes."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM mv_organizing_scorecard WHERE last_election_date IS NOT NULL
        """)
        assert cur.fetchone()[0] == 0


class TestMvDecayBehavior:
    """Verify that decay factors correlate with inspection age."""

    def test_older_inspections_have_lower_decay(self, db):
        """Establishments with older last_inspection_date should have lower osha_decay_factor."""
        cur = db.cursor()
        cur.execute("""
            SELECT osha_decay_factor, last_inspection_date
            FROM mv_organizing_scorecard
            WHERE last_inspection_date IS NOT NULL
            ORDER BY last_inspection_date ASC
            LIMIT 1
        """)
        oldest = cur.fetchone()
        cur.execute("""
            SELECT osha_decay_factor, last_inspection_date
            FROM mv_organizing_scorecard
            WHERE last_inspection_date IS NOT NULL
            ORDER BY last_inspection_date DESC
            LIMIT 1
        """)
        newest = cur.fetchone()
        # Oldest should have lower decay factor than newest
        assert oldest[0] <= newest[0]

    def test_decay_factor_in_expected_range(self, db):
        """All OSHA decay factors should be between 0 and 1."""
        cur = db.cursor()
        cur.execute("""
            SELECT MIN(osha_decay_factor), MAX(osha_decay_factor)
            FROM mv_organizing_scorecard
        """)
        min_val, max_val = cur.fetchone()
        assert min_val > 0, "Decay factor should be > 0"
        assert max_val <= 1.0, "Decay factor should be <= 1.0"

    def test_null_inspection_date_gets_no_decay(self, db):
        """If last_inspection_date is NULL, decay factor should be 1.0."""
        cur = db.cursor()
        cur.execute("""
            SELECT osha_decay_factor
            FROM mv_organizing_scorecard
            WHERE last_inspection_date IS NULL
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:  # Only test if there are NULL rows
            assert float(row[0]) == pytest.approx(1.0)

    def test_osha_score_range_preserved(self, db):
        """Score should still be 0-10 after decay."""
        cur = db.cursor()
        cur.execute("""
            SELECT MIN(score_osha), MAX(score_osha)
            FROM mv_organizing_scorecard
        """)
        min_s, max_s = cur.fetchone()
        assert min_s >= 0, "OSHA score should be >= 0"
        assert max_s <= 10, "OSHA score should be <= 10"

    def test_nlrb_score_range_preserved(self, db):
        """NLRB score should still be 1-10 after decay."""
        cur = db.cursor()
        cur.execute("""
            SELECT MIN(score_nlrb), MAX(score_nlrb)
            FROM mv_organizing_scorecard
        """)
        min_s, max_s = cur.fetchone()
        assert min_s >= 1, "NLRB score should be >= 1"
        assert max_s <= 10, "NLRB score should be <= 10"


class TestMvDecayFormula:
    """Verify the SQL decay matches the Python formula."""

    def test_decay_factor_matches_formula(self, db):
        """Spot-check: SQL decay factor should match Python calculation."""
        cur = db.cursor()
        cur.execute("""
            SELECT osha_decay_factor, last_inspection_date,
                   (CURRENT_DATE - last_inspection_date)::float / 365.25 AS years_ago
            FROM mv_organizing_scorecard
            WHERE last_inspection_date IS NOT NULL
            LIMIT 5
        """)
        for row in cur.fetchall():
            sql_decay = float(row[0])
            years_ago = float(row[2])
            expected = osha_decay(years_ago)
            assert sql_decay == pytest.approx(expected, abs=0.001), \
                f"SQL decay {sql_decay} != expected {expected} for {years_ago:.1f} years"


class TestNlrbDecayArchitecture:
    """Document that NLRB employer-specific decay cannot apply in MV context.

    The MV excludes F7-matched establishments (WHERE fm.establishment_id IS NULL).
    NLRB data routes through osha_f7_matches -> nlrb_participants, which requires
    an F7 match. So Factor 6 always uses the population-average fallback branch.
    Employer-specific NLRB decay is applied in the detail endpoint instead.
    """

    def test_mv_has_no_f7_matches(self, db):
        """All MV rows should have has_f7_match = False."""
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE has_f7_match = TRUE")
        assert cur.fetchone()[0] == 0

    def test_nlrb_predicted_always_null_in_mv(self, db):
        """nlrb_predicted_win_pct should be NULL for all MV rows."""
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE nlrb_predicted_win_pct IS NOT NULL")
        assert cur.fetchone()[0] == 0

    def test_score_nlrb_uses_fallback_only(self, db):
        """NLRB score should use population fallback, not employer-specific."""
        cur = db.cursor()
        cur.execute("""
            SELECT DISTINCT score_nlrb FROM mv_organizing_scorecard ORDER BY 1
        """)
        scores = [r[0] for r in cur.fetchall()]
        # Fallback branch produces 1, 3, 5, 8, or 10 based on blended rate
        for s in scores:
            assert s in (1, 3, 5, 8, 10), f"Unexpected NLRB score {s}"


class TestOshaDecayBoundary:
    """Boundary tests for very old OSHA violations."""

    def test_very_old_violations_floor_behavior(self, db):
        """Establishments with 20+ year old inspections should have low but nonzero OSHA scores."""
        cur = db.cursor()
        cur.execute("""
            SELECT score_osha, osha_decay_factor, total_violations, last_inspection_date
            FROM mv_organizing_scorecard
            WHERE last_inspection_date < CURRENT_DATE - INTERVAL '20 years'
              AND total_violations > 0
            LIMIT 5
        """)
        rows = cur.fetchall()
        for r in rows:
            score, decay, violations, date = r
            assert score >= 1, f"Nonzero violations should get score >= 1 (got {score})"
            assert score <= 5, f"20yr-old violations shouldn't score high (got {score} for {violations} violations on {date})"
            assert float(decay) < 0.30, f"20yr decay should be < 0.30 (got {decay})"


class TestWrapperViewIncludesDecay:
    """Verify the wrapper view v_organizing_scorecard still works."""

    def test_wrapper_view_has_organizing_score(self, db):
        cur = db.cursor()
        cur.execute("SELECT organizing_score FROM v_organizing_scorecard LIMIT 1")
        row = cur.fetchone()
        assert row is not None
        assert row[0] > 0

    def test_wrapper_view_has_decay_columns(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT osha_decay_factor, nlrb_decay_factor
            FROM v_organizing_scorecard LIMIT 1
        """)
        row = cur.fetchone()
        assert row is not None
