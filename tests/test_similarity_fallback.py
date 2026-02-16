"""
Similarity fallback + nearest-unionized tests (Phase 5.4).

Tests that Factor 9 uses industry-average similarity as a fallback
when employer-specific Gower scores are unavailable (all MV rows),
and that the detail endpoint includes nearest-unionized context.

Run with: py -m pytest tests/test_similarity_fallback.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def db():
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


class TestSimilarityFallbackActivation:
    """Verify the industry-average fallback is used for MV rows."""

    def test_no_zero_similarity_scores(self, db):
        """All MV rows should have score_similarity > 0 (via fallback)."""
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE score_similarity = 0")
        assert cur.fetchone()[0] == 0, "No rows should have score_similarity = 0 with fallback"

    def test_all_rows_have_similarity_source(self, db):
        """All MV rows should have a similarity_source."""
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE similarity_source IS NULL")
        null_count = cur.fetchone()[0]
        assert null_count == 0, f"{null_count} rows have NULL similarity_source"

    def test_mv_uses_industry_avg_source(self, db):
        """MV rows should use industry_avg source (not employer-specific)."""
        cur = db.cursor()
        cur.execute("""
            SELECT similarity_source, COUNT(*)
            FROM mv_organizing_scorecard
            GROUP BY similarity_source
        """)
        sources = {r[0]: r[1] for r in cur.fetchall()}
        assert "industry_avg" in sources, "Should have industry_avg source"
        # MV excludes F7-matched, so no employer-specific expected
        assert sources.get("employer", 0) == 0


class TestSimilarityFallbackScoring:
    """Verify the fallback score thresholds are correct."""

    def test_fallback_capped_at_5(self, db):
        """Industry-average fallback should never exceed 5 points."""
        cur = db.cursor()
        cur.execute("""
            SELECT MAX(score_similarity)
            FROM mv_organizing_scorecard
            WHERE similarity_source = 'industry_avg'
        """)
        max_score = cur.fetchone()[0]
        assert max_score <= 5, f"Fallback max should be 5, got {max_score}"

    def test_fallback_score_values(self, db):
        """Fallback scores should be 1, 3, or 5."""
        cur = db.cursor()
        cur.execute("""
            SELECT DISTINCT score_similarity
            FROM mv_organizing_scorecard
            WHERE similarity_source = 'industry_avg'
            ORDER BY 1
        """)
        scores = [r[0] for r in cur.fetchall()]
        for s in scores:
            assert s in (1, 3, 5), f"Unexpected fallback score: {s}"

    def test_similarity_score_populated(self, db):
        """similarity_score column should have the industry average values."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM mv_organizing_scorecard
            WHERE similarity_score IS NOT NULL AND similarity_source = 'industry_avg'
        """)
        count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE similarity_source = 'industry_avg'")
        total = cur.fetchone()[0]
        assert count == total, "All industry_avg rows should have similarity_score populated"


class TestSimilarityFallbackRange:
    """Verify overall score ranges are reasonable with the fallback."""

    def test_overall_score_range_reasonable(self, db):
        """Total organizing_score should be higher with fallback contributing."""
        cur = db.cursor()
        cur.execute("""
            SELECT MIN(organizing_score), AVG(organizing_score)::float, MAX(organizing_score)
            FROM v_organizing_scorecard
        """)
        min_s, avg_s, max_s = cur.fetchone()
        assert min_s >= 10, f"Min score should be >= 10, got {min_s}"
        assert avg_s > 25, f"Avg score should be > 25, got {avg_s:.1f}"
        assert max_s <= 90, f"Max score should be <= 90, got {max_s}"

    def test_score_similarity_range(self, db):
        """Factor 9 should be in valid range."""
        cur = db.cursor()
        cur.execute("SELECT MIN(score_similarity), MAX(score_similarity) FROM mv_organizing_scorecard")
        min_s, max_s = cur.fetchone()
        assert min_s >= 0, f"Min similarity score should be >= 0"
        assert max_s <= 10, f"Max similarity score should be <= 10"


class TestNearestUnionizedAPI:
    """Test the nearest-unionized context in the detail endpoint."""

    @pytest.fixture(scope="class")
    def client(self):
        os.environ["LABOR_JWT_SECRET"] = ""
        from api.main import app
        return TestClient(app)

    @pytest.fixture(scope="class")
    def sample_estab(self):
        """Get a sample establishment with a known NAICS code."""
        import psycopg2, psycopg2.extras
        from db_config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT establishment_id, naics_code, site_state
            FROM mv_organizing_scorecard
            WHERE naics_code IS NOT NULL AND site_state IS NOT NULL
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        return row

    def test_detail_has_similarity_context(self, client, sample_estab):
        """Detail endpoint should include similarity_context."""
        resp = client.get(f"/api/organizing/scorecard/{sample_estab['establishment_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "similarity_context" in data
        ctx = data["similarity_context"]
        assert "similarity_score" in ctx
        assert "similarity_source" in ctx
        assert "siblings_url" in ctx

    def test_detail_similarity_source_populated(self, client, sample_estab):
        """similarity_source should be populated for MV rows."""
        resp = client.get(f"/api/organizing/scorecard/{sample_estab['establishment_id']}")
        data = resp.json()
        assert data["similarity_context"]["similarity_source"] in ("employer", "industry_avg")

    def test_detail_nearest_unionized_structure(self, client, sample_estab):
        """nearest_unionized should be a list or null."""
        resp = client.get(f"/api/organizing/scorecard/{sample_estab['establishment_id']}")
        data = resp.json()
        nu = data["similarity_context"].get("nearest_unionized")
        if nu is not None:
            assert isinstance(nu, list)
            assert len(nu) <= 3
            for item in nu:
                assert "employer_id" in item
                assert "employer_name" in item
                assert "match_score" in item

    def test_siblings_endpoint_exists(self, client, sample_estab):
        """Siblings endpoint should be reachable."""
        resp = client.get(f"/api/organizing/siblings/{sample_estab['establishment_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "siblings" in data
