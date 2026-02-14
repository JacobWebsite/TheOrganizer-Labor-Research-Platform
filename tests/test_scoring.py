"""
Scoring engine tests for the Labor Research Platform.

Tests the 9-factor organizing scorecard (scale 10-78):
  1. Company unions    2. Industry density   3. Geographic
  4. Size              5. OSHA               6. NLRB
  7. Contracts         8. Projections        9. Similarity

Covers: scoring helper unit tests, MV validation, and API endpoint tests.

Run with: py -m pytest tests/test_scoring.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routers.organizing import _score_size, _score_osha_normalized, _score_geographic


# ============================================================================
# A. SCORING HELPER UNIT TESTS  (no DB needed)
# ============================================================================

class TestScoreSize:
    """_score_size: sweet spot is 50-250 employees (score 10)."""

    def test_sweet_spot_100(self):
        assert _score_size(100) == 10

    def test_range_251_500(self):
        assert _score_size(300) == 8

    def test_range_25_49(self):
        assert _score_size(40) == 6

    def test_range_501_1000(self):
        assert _score_size(750) == 4

    def test_outside_all_ranges(self):
        assert _score_size(5) == 2

    def test_boundary_50(self):
        assert _score_size(50) == 10

    def test_boundary_250(self):
        assert _score_size(250) == 10

    def test_boundary_25(self):
        assert _score_size(25) == 6

    def test_boundary_500(self):
        assert _score_size(500) == 8

    def test_boundary_1000(self):
        assert _score_size(1000) == 4

    def test_very_large(self):
        assert _score_size(10000) == 2

    def test_zero(self):
        assert _score_size(0) == 2


class TestScoreOshaNormalized:
    """_score_osha_normalized: violations normalized to industry average + severity bonus."""

    def test_high_ratio_returns_7_base(self):
        score, ratio = _score_osha_normalized(10, 0, 0, "3361", {"3361": 3.0})
        # ratio = 10/3.0 = 3.33 -> base 7
        assert score == 7
        assert ratio == pytest.approx(3.33, abs=0.01)

    def test_zero_violations_returns_zero(self):
        score, ratio = _score_osha_normalized(0, 0, 0, "3361", {"3361": 3.0})
        assert score == 0
        assert ratio == 0.0

    def test_fallback_average_with_severity(self):
        # 5 violations / fallback 2.23 = ratio ~2.24 -> base 5
        # severity: willful*2 + repeat = 2*2+1 = 5, capped at 3
        score, ratio = _score_osha_normalized(5, 2, 1, "XX", {})
        assert ratio == pytest.approx(2.24, abs=0.01)
        assert score == min(10, 5 + 3)  # base 5 + severity 3 = 8

    def test_none_violations_treated_as_zero(self):
        score, ratio = _score_osha_normalized(None, None, None, "3361", {"3361": 3.0})
        assert score == 0
        assert ratio == 0.0

    def test_2digit_naics_fallback(self):
        # 4-digit not found, falls back to 2-digit
        score, ratio = _score_osha_normalized(6, 0, 0, "3361", {"33": 2.0})
        # ratio = 6/2.0 = 3.0 -> base 7
        assert score == 7
        assert ratio == pytest.approx(3.0)

    def test_severity_bonus_capped_at_3(self):
        score, _ = _score_osha_normalized(10, 5, 5, "3361", {"3361": 3.0})
        # base 7 + severity min(3, 5*2+5=15) = 7+3 = 10
        assert score == 10

    def test_total_score_capped_at_10(self):
        score, _ = _score_osha_normalized(100, 5, 5, "3361", {"3361": 3.0})
        assert score <= 10


class TestScoreGeographic:
    """_score_geographic: NLRB win rate + density + RTW adjustment."""

    def test_favorable_state(self):
        # Non-RTW (3), high win rate >= 85 (4), high density > 1M (3) = 10
        score = _score_geographic("NY", {"TX", "FL"}, {"NY": 85}, {"NY": 1500000})
        assert score == 10

    def test_rtw_low_stats(self):
        # RTW (0), low win rate 50 (0), low density 100K (0) = 0
        score = _score_geographic("TX", {"TX", "FL"}, {"TX": 50}, {"TX": 100000})
        assert score == 0

    def test_missing_state_uses_defaults(self):
        # Missing state should not crash
        score = _score_geographic("ZZ", {"TX"}, {}, {})
        assert isinstance(score, int)
        assert 0 <= score <= 10

    def test_medium_win_rate(self):
        # Non-RTW (3), win rate 75 (3), medium density 600K (2) = 8
        score = _score_geographic("PA", {"TX"}, {"PA": 75}, {"PA": 600000})
        assert score == 8

    def test_rtw_with_high_win_rate(self):
        # RTW (0), high win rate >= 85 (4), high density > 1M (3) = 7
        score = _score_geographic("TX", {"TX"}, {"TX": 90}, {"TX": 2000000})
        assert score == 7

    def test_score_never_exceeds_10(self):
        score = _score_geographic("NY", set(), {"NY": 100}, {"NY": 50000000})
        assert score <= 10

    def test_fallback_win_rate(self):
        # No state-specific rate -> uses 'US' fallback (75.0 default)
        score = _score_geographic("ZZ", set(), {"US": 75.0}, {"ZZ": 300000})
        # Non-RTW (3), win rate 75 (3), density 300K (1) = 7
        assert score == 7


# ============================================================================
# B. SCORECARD MV VALIDATION  (DB required)
# ============================================================================

@pytest.fixture(scope="module")
def db():
    """Provide a database connection for all tests in this module."""
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


def query_one(db, sql, params=None):
    cur = db.cursor()
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def query_all(db, sql, params=None):
    cur = db.cursor()
    cur.execute(sql, params or ())
    return cur.fetchall()


class TestScorecardMV:
    """Validate the mv_organizing_scorecard materialized view."""

    def test_mv_exists_and_populated(self, db):
        count = query_one(db, "SELECT COUNT(*) FROM mv_organizing_scorecard")
        assert count is not None
        # Should be approximately 24,841 rows (+/- 1000 for data pipeline changes)
        assert count > 20000, f"MV has only {count} rows, expected ~24,841"
        assert count < 30000, f"MV has {count} rows, suspiciously high"

    def test_wrapper_view_exists(self, db):
        exists = query_one(db, """
            SELECT COUNT(*) FROM information_schema.views
            WHERE table_name = 'v_organizing_scorecard' AND table_schema = 'public'
        """)
        assert exists > 0, "v_organizing_scorecard view does not exist"

    def test_wrapper_view_has_organizing_score(self, db):
        col_exists = query_one(db, """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'v_organizing_scorecard' AND column_name = 'organizing_score'
        """)
        assert col_exists > 0, "v_organizing_scorecard missing organizing_score column"

    def test_score_range(self, db):
        min_score = query_one(db, "SELECT MIN(organizing_score) FROM v_organizing_scorecard")
        max_score = query_one(db, "SELECT MAX(organizing_score) FROM v_organizing_scorecard")
        assert min_score >= 0, f"Min score {min_score} is negative"
        assert max_score <= 90, f"Max score {max_score} exceeds theoretical max"

    def test_total_equals_sum_of_factors(self, db):
        """organizing_score should equal the sum of 9 individual factor columns."""
        bad_rows = query_one(db, """
            SELECT COUNT(*) FROM v_organizing_scorecard
            WHERE organizing_score != (
                COALESCE(score_company_unions, 0)
                + COALESCE(score_industry_density, 0)
                + COALESCE(score_geographic, 0)
                + COALESCE(score_size, 0)
                + COALESCE(score_osha, 0)
                + COALESCE(score_nlrb, 0)
                + COALESCE(score_contracts, 0)
                + COALESCE(score_projections, 0)
                + COALESCE(score_similarity, 0)
            )
            LIMIT 100
        """)
        assert bad_rows == 0, f"{bad_rows} rows where total != sum of 9 factors"

    def test_no_null_required_factors(self, db):
        """Core factor columns should not be NULL."""
        factor_cols = [
            'score_size', 'score_osha', 'score_geographic',
            'score_industry_density', 'score_nlrb',
        ]
        for col in factor_cols:
            nulls = query_one(db, f"SELECT COUNT(*) FROM mv_organizing_scorecard WHERE {col} IS NULL")
            assert nulls == 0, f"{col} has {nulls} NULL values"

    def test_unique_index_on_establishment_id(self, db):
        """MV should have a unique index on establishment_id (needed for REFRESH CONCURRENTLY)."""
        idx_count = query_one(db, """
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = 'mv_organizing_scorecard'
              AND indexdef ILIKE '%%unique%%'
        """)
        assert idx_count >= 1, "No UNIQUE index on mv_organizing_scorecard (required for REFRESH CONCURRENTLY)"


# ============================================================================
# C. SCORECARD API TESTS  (TestClient)
# ============================================================================

@pytest.fixture(scope="module")
def client():
    """Create a test client with auth disabled."""
    os.environ.pop("LABOR_JWT_SECRET", None)
    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c


class TestScorecardAPI:
    """API endpoint tests for the organizing scorecard."""

    def test_scorecard_list_returns_score_breakdown(self, client):
        r = client.get("/api/organizing/scorecard?state=NY&limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        if data["results"]:
            item = data["results"][0]
            assert "score_breakdown" in item
            breakdown = item["score_breakdown"]
            expected_factors = {
                "company_unions", "industry_density", "geographic",
                "size", "osha", "nlrb", "contracts", "projections", "similarity"
            }
            assert set(breakdown.keys()) == expected_factors

    def test_scorecard_min_score_filter(self, client):
        r = client.get("/api/organizing/scorecard?min_score=50&limit=20")
        assert r.status_code == 200
        data = r.json()
        for item in data["results"]:
            assert item["organizing_score"] >= 50, (
                f"Score {item['organizing_score']} < 50 for {item['estab_name']}"
            )

    def test_scorecard_limit(self, client):
        r = client.get("/api/organizing/scorecard?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) <= 10

    def test_scorecard_detail_structure(self, client):
        # First get a valid establishment_id
        r = client.get("/api/organizing/scorecard?limit=1")
        assert r.status_code == 200
        results = r.json()["results"]
        if not results:
            pytest.skip("No scorecard results available")
        estab_id = results[0]["establishment_id"]

        # Now get detail
        r2 = client.get(f"/api/organizing/scorecard/{estab_id}")
        assert r2.status_code == 200
        detail = r2.json()
        assert "score_breakdown" in detail
        assert "establishment" in detail
        assert "organizing_score" in detail

    def test_scorecard_score_in_valid_range(self, client):
        r = client.get("/api/organizing/scorecard?limit=50")
        assert r.status_code == 200
        for item in r.json()["results"]:
            score = item["organizing_score"]
            assert 0 <= score <= 90, f"Score {score} out of range [0, 90]"

    def test_scorecard_response_structure(self, client):
        r = client.get("/api/organizing/scorecard?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "total" in data
        if data["results"]:
            item = data["results"][0]
            assert "estab_name" in item or "establishment_name" in item
            assert "organizing_score" in item
            assert "employee_count" in item
