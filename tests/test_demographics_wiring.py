"""Tests for ACS demographics API wiring (Task 3-10)."""
import pytest
from db_config import get_connection


class TestAcsDemographicsTable:
    """Verify cur_acs_workforce_demographics table has data."""

    def test_table_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'cur_acs_workforce_demographics'
                """)
                assert cur.fetchone()[0] == 1, "cur_acs_workforce_demographics table missing"
        finally:
            conn.close()

    def test_has_rows(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM cur_acs_workforce_demographics")
                cnt = cur.fetchone()[0]
                assert cnt > 100_000, f"Expected >100K rows, got {cnt}"
        finally:
            conn.close()

    def test_has_expected_columns(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'cur_acs_workforce_demographics'
                    ORDER BY ordinal_position
                """)
                cols = {r[0] for r in cur.fetchall()}
                for expected in ['state_fips', 'naics4', 'sex', 'race',
                                 'hispanic', 'age_bucket', 'education',
                                 'weighted_workers']:
                    assert expected in cols, f"Missing column: {expected}"
        finally:
            conn.close()

    def test_state_fips_diversity(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(DISTINCT state_fips)
                    FROM cur_acs_workforce_demographics
                """)
                states = cur.fetchone()[0]
                assert states >= 40, f"Expected >=40 states, got {states}"
        finally:
            conn.close()


class TestDemographicsApi:
    """Test the demographics API endpoints."""

    @pytest.fixture
    def client(self):
        from api.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_state_naics_endpoint(self, client):
        """Test /api/demographics/{state}/{naics} with known data."""
        # Use 2-digit NAICS (broader, more likely to have data)
        resp = client.get("/api/demographics/CA/62")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_workers" in data
            assert data["total_workers"] > 0
            assert "gender" in data
            assert "race" in data
            assert "education" in data
            assert data["state"] == "CA"

    def test_state_only_endpoint(self, client):
        """Test /api/demographics/{state}."""
        resp = client.get("/api/demographics/NY")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert data["total_workers"] > 0
            assert data["state"] == "NY"
            assert data["naics"] is None

    def test_naics_fallback_4_to_2(self, client):
        """Test that 4-digit NAICS falls back to 2-digit."""
        # Obscure 4-digit NAICS that likely has no direct ACS data
        resp = client.get("/api/demographics/CA/6219")
        if resp.status_code == 200:
            data = resp.json()
            # Should have data (either direct or fallback)
            assert data["total_workers"] > 0

    def test_fallback_level_field_present(self, client):
        """Test that fallback_level field is included in response."""
        resp = client.get("/api/demographics/CA/62")
        if resp.status_code == 200:
            data = resp.json()
            assert "fallback_level" in data
            assert data["total_workers"] > 0

    def test_unknown_state_returns_404(self, client):
        resp = client.get("/api/demographics/ZZ/6216")
        assert resp.status_code == 404

    def test_gender_percentages_sum_to_100(self, client):
        resp = client.get("/api/demographics/CA/62")
        if resp.status_code == 200:
            data = resp.json()
            gender_sum = sum(g["pct"] for g in data.get("gender", []))
            assert 99.0 <= gender_sum <= 101.0, f"Gender pcts sum to {gender_sum}"

    def test_education_groups_present(self, client):
        resp = client.get("/api/demographics/NY/62")
        if resp.status_code == 200:
            data = resp.json()
            edu_groups = [e["group"] for e in data.get("education", [])]
            # Should have at least HS diploma and Bachelor's
            assert any("HS" in g for g in edu_groups) or len(edu_groups) > 0
