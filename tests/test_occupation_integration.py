"""
Occupation similarity integration tests (Phase 5.4c).

Tests that the industry_occupation_overlap table and naics_to_bls_industry
mapping are properly created and contain valid data.

Run with: py -m pytest tests/test_occupation_integration.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def db():
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


class TestOverlapTableSchema:
    """Verify the industry_occupation_overlap table exists and has correct structure."""

    def test_table_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'industry_occupation_overlap'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_has_required_columns(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'industry_occupation_overlap'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        for required in ["industry_code_a", "industry_code_b", "overlap_score", "shared_occupations"]:
            assert required in cols, f"Missing column: {required}"

    def test_has_rows(self, db):
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM industry_occupation_overlap")
        assert cur.fetchone()[0] > 0


class TestOverlapScores:
    """Verify overlap scores are in valid range and make sense."""

    def test_scores_in_valid_range(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT MIN(overlap_score), MAX(overlap_score)
            FROM industry_occupation_overlap
        """)
        min_s, max_s = cur.fetchone()
        assert float(min_s) >= 0.0, "Overlap score should be >= 0"
        assert float(max_s) <= 1.0, "Overlap score should be <= 1"

    def test_self_overlap_near_one(self, db):
        """Same-industry pairs should have overlap near 1.0."""
        cur = db.cursor()
        cur.execute("""
            SELECT AVG(overlap_score)
            FROM industry_occupation_overlap
            WHERE industry_code_a = industry_code_b
        """)
        avg = cur.fetchone()[0]
        if avg is not None:
            assert float(avg) >= 0.99, f"Self-overlap should be ~1.0, got {avg}"

    def test_shared_occupations_positive(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM industry_occupation_overlap
            WHERE shared_occupations <= 0 AND overlap_score > 0
        """)
        assert cur.fetchone()[0] == 0, "Non-zero overlap should have positive shared_occupations"


class TestMappingTable:
    """Verify naics_to_bls_industry mapping table."""

    def test_mapping_table_exists(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'naics_to_bls_industry'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_mapping_has_rows(self, db):
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM naics_to_bls_industry")
        count = cur.fetchone()[0]
        assert count > 0, "Mapping table should have rows"

    def test_composite_codes_mapped(self, db):
        """BLS composite codes (31-330, 44-450, 48-490) should have NAICS mappings."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(DISTINCT bls_industry_code) FROM naics_to_bls_industry
            WHERE match_type = 'composite'
        """)
        count = cur.fetchone()[0]
        assert count >= 1, "Should have at least one composite code mapping"


class TestGowerIntegration:
    """Verify occupation_overlap is available for Gower computation."""

    def test_employer_comparables_exists(self, db):
        """employer_comparables should exist (computed by Gower)."""
        cur = db.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'employer_comparables'
            )
        """)
        assert cur.fetchone()[0] is True

    def test_comparables_have_feature_breakdown(self, db):
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM employer_comparables
            WHERE feature_breakdown IS NOT NULL
        """)
        count = cur.fetchone()[0]
        assert count > 0, "employer_comparables should have feature_breakdown"
