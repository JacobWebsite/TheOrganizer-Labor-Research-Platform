"""Tests for LODES workplace demographics (Task 3-12)."""
import pytest
from db_config import get_connection


class TestLodesGeoMetrics:
    """Verify LODES demographic columns exist and have data."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_demographic_columns_exist(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'cur_lodes_geo_metrics'
                ORDER BY ordinal_position
            """)
            cols = {r[0] for r in cur.fetchall()}
            for expected in ['jobs_white', 'jobs_black', 'jobs_native', 'jobs_asian',
                             'jobs_pacific', 'jobs_two_plus_races',
                             'jobs_not_hispanic', 'jobs_hispanic',
                             'jobs_male', 'jobs_female',
                             'jobs_edu_less_than_hs', 'jobs_edu_hs',
                             'jobs_edu_some_college', 'jobs_edu_bachelors_plus',
                             'pct_female', 'pct_hispanic', 'pct_minority', 'pct_bachelors_plus']:
                assert expected in cols, f"Missing column: {expected}"

    def test_all_counties_have_demographics(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cur_lodes_geo_metrics WHERE jobs_white IS NOT NULL")
            with_demo = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM cur_lodes_geo_metrics")
            total = cur.fetchone()[0]
            assert with_demo == total, f"{total - with_demo} counties missing demographics"

    def test_race_sums_match_total(self):
        """Race columns should sum close to demo_total_jobs."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT county_fips,
                    demo_total_jobs,
                    (COALESCE(jobs_white,0) + COALESCE(jobs_black,0)
                        + COALESCE(jobs_native,0) + COALESCE(jobs_asian,0)
                        + COALESCE(jobs_pacific,0) + COALESCE(jobs_two_plus_races,0)) AS race_sum
                FROM cur_lodes_geo_metrics
                WHERE demo_total_jobs > 1000
                LIMIT 10
            """)
            for row in cur.fetchall():
                total = row[1]
                race = row[2]
                assert abs(total - race) < total * 0.01, (
                    f"County {row[0]}: race sum {race} vs total {total}"
                )

    def test_sex_sums_match_total(self):
        """Male + Female should equal demo_total_jobs."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT county_fips, demo_total_jobs,
                    (COALESCE(jobs_male,0) + COALESCE(jobs_female,0)) AS sex_sum
                FROM cur_lodes_geo_metrics
                WHERE demo_total_jobs > 1000
                LIMIT 10
            """)
            for row in cur.fetchall():
                assert row[1] == row[2], f"County {row[0]}: sex sum {row[2]} vs total {row[1]}"

    def test_pct_female_reasonable(self):
        """pct_female should be between 0.30 and 0.70 for most counties."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(pct_female)
                FROM cur_lodes_geo_metrics
                WHERE pct_female IS NOT NULL
            """)
            avg_pct = float(cur.fetchone()[0])
            assert 0.40 < avg_pct < 0.60, f"Average pct_female = {avg_pct}"

    def test_pct_bachelors_reasonable(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(pct_bachelors_plus)
                FROM cur_lodes_geo_metrics
                WHERE pct_bachelors_plus IS NOT NULL
            """)
            avg_pct = float(cur.fetchone()[0])
            assert 0.05 < avg_pct < 0.50, f"Average pct_bachelors_plus = {avg_pct}"


class TestZipCountyCrosswalk:
    """Verify ZIP-county crosswalk table."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_crosswalk_exists(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM zip_county_crosswalk")
            cnt = cur.fetchone()[0]
            assert cnt > 30000, f"Expected >30K ZIP codes, got {cnt}"

    def test_county_fips_format(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM zip_county_crosswalk
                WHERE LENGTH(county_fips) = 5
            """)
            valid = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM zip_county_crosswalk")
            total = cur.fetchone()[0]
            assert valid == total, f"{total - valid} invalid county FIPS codes"


class TestLodesApi:
    """Test the workplace demographics API endpoint."""

    @pytest.fixture
    def client(self):
        from api.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_workplace_demographics_endpoint(self, client):
        """Test the workplace demographics endpoint with a real employer."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM f7_employers_deduped
                    WHERE zip IS NOT NULL AND LENGTH(TRIM(zip)) >= 5
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    pytest.skip("No employers with ZIP codes")
                emp_id = row[0]
        finally:
            conn.close()

        resp = client.get(f"/api/profile/employers/{emp_id}/workplace-demographics")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        if data["available"]:
            assert "county_fips" in data
            assert "gender" in data
            assert "race" in data
            assert "education" in data
            assert data["total_jobs"] > 0

    def test_workplace_demographics_no_zip(self, client):
        """Test endpoint returns graceful message when no ZIP."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM f7_employers_deduped
                    WHERE zip IS NULL OR TRIM(zip) = ''
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    pytest.skip("No employers without ZIP codes")
                emp_id = row[0]
        finally:
            conn.close()

        resp = client.get(f"/api/profile/employers/{emp_id}/workplace-demographics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
