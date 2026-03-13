"""Tests for O*NET data loading and API enrichment (Task 3-8b)."""
import pytest
from db_config import get_connection


class TestOnetTables:
    """Verify O*NET tables exist and have expected data."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_occupations_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_occupations")
            cnt = cur.fetchone()[0]
            assert cnt > 900, f"Expected >900 occupations, got {cnt}"

    def test_skills_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_skills")
            cnt = cur.fetchone()[0]
            assert cnt > 50000, f"Expected >50K skills rows, got {cnt}"

    def test_knowledge_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_knowledge")
            cnt = cur.fetchone()[0]
            assert cnt > 40000, f"Expected >40K knowledge rows, got {cnt}"

    def test_abilities_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_abilities")
            cnt = cur.fetchone()[0]
            assert cnt > 80000, f"Expected >80K abilities rows, got {cnt}"

    def test_work_context_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_work_context")
            cnt = cur.fetchone()[0]
            assert cnt > 200000, f"Expected >200K work context rows, got {cnt}"

    def test_job_zones_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_job_zones")
            cnt = cur.fetchone()[0]
            assert cnt > 800, f"Expected >800 job zone rows, got {cnt}"

    def test_content_model_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_content_model")
            cnt = cur.fetchone()[0]
            assert cnt > 500, f"Expected >500 content model rows, got {cnt}"

    def test_scales_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_scales")
            cnt = cur.fetchone()[0]
            assert cnt > 20, f"Expected >20 scales, got {cnt}"

    def test_tasks_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_tasks")
            cnt = cur.fetchone()[0]
            assert cnt > 15000, f"Expected >15K tasks, got {cnt}"

    def test_alternate_titles_table(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM onet_alternate_titles")
            cnt = cur.fetchone()[0]
            assert cnt > 50000, f"Expected >50K alternate titles, got {cnt}"


class TestOnetDataIntegrity:
    """Verify O*NET data quality and joins."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_onetsoc_code_format(self):
        """O*NET codes should be 10-char: XX-XXXX.XX"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM onet_occupations
                WHERE onetsoc_code ~ '^[0-9]{2}-[0-9]{4}\\.[0-9]{2}$'
            """)
            valid = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM onet_occupations")
            total = cur.fetchone()[0]
            assert valid == total, f"Invalid SOC codes: {total - valid} of {total}"

    def test_skills_join_to_occupations(self):
        """Skills should join to occupations via onetsoc_code."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT s.onetsoc_code)
                FROM onet_skills s
                JOIN onet_occupations o ON s.onetsoc_code = o.onetsoc_code
            """)
            joined = cur.fetchone()[0]
            assert joined > 800, f"Expected >800 joined SOC codes, got {joined}"

    def test_bls_join_coverage(self):
        """O*NET SOC codes should join to BLS matrix via 7-char prefix."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT LEFT(o.onetsoc_code, 7))
                FROM onet_occupations o
                JOIN bls_industry_occupation_matrix b
                    ON LEFT(o.onetsoc_code, 7) = b.occupation_code
            """)
            joined = cur.fetchone()[0]
            assert joined > 200, f"Expected >200 BLS-joined SOC codes, got {joined}"

    def test_importance_scale_range(self):
        """Importance scale (IM) values should be between 1 and 5."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(data_value), MAX(data_value)
                FROM onet_skills
                WHERE scale_id = 'IM'
            """)
            row = cur.fetchone()
            assert float(row[0]) >= 0, f"Min importance {row[0]} < 0"
            assert float(row[1]) <= 7, f"Max importance {row[1]} > 7"

    def test_job_zone_range(self):
        """Job zones should be 1-5."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(job_zone), MAX(job_zone)
                FROM onet_job_zones
            """)
            row = cur.fetchone()
            assert row[0] >= 1, f"Min job zone {row[0]}"
            assert row[1] <= 5, f"Max job zone {row[1]}"


class TestOnetApiEnrichment:
    """Test the occupations API returns O*NET enrichment."""

    @pytest.fixture
    def client(self):
        from api.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_occupations_include_onet_fields(self, client):
        """Occupations response should include O*NET enrichment fields."""
        # Find an employer with NAICS
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM f7_employers_deduped
                    WHERE naics IS NOT NULL AND naics != ''
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    pytest.skip("No employers with NAICS")
                emp_id = row[0]
        finally:
            conn.close()

        resp = client.get(f"/api/profile/employers/{emp_id}/occupations")
        assert resp.status_code == 200
        data = resp.json()
        occs = data.get("top_occupations", [])
        if occs:
            occ = occs[0]
            assert "top_skills" in occ, "Missing top_skills field"
            assert "top_knowledge" in occ, "Missing top_knowledge field"
            assert "top_work_context" in occ, "Missing top_work_context field"
            assert "job_zone" in occ, "Missing job_zone field"

    def test_skills_have_name_and_importance(self, client):
        """Skill entries should have name and importance."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM f7_employers_deduped
                    WHERE naics IS NOT NULL AND naics != ''
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    pytest.skip("No employers with NAICS")
                emp_id = row[0]
        finally:
            conn.close()

        resp = client.get(f"/api/profile/employers/{emp_id}/occupations")
        data = resp.json()
        for occ in data.get("top_occupations", []):
            for skill in occ.get("top_skills", []):
                assert "name" in skill
                assert "importance" in skill
                if skill["importance"] is not None:
                    assert 0 <= skill["importance"] <= 7
