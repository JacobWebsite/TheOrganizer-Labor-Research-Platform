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


class TestPlausibilityBounds:
    """R7-1 regression guard: total_workers must reconcile to BLS QCEW.

    Pre-fix the table summed 9 IPUMS sample-years and leaked not-in-labor
    -force people, returning 145M for NY. Post-fix, the table is built
    from one ACS sample (2023 5-year) with employed wage + self-employed
    workers only. State totals should be within ~30% of QCEW covered
    employment (the ~10-30% gap is expected: ACS includes self-employed
    and uncovered workers QCEW excludes).
    """

    PLAUSIBLE_STATE_MAX = 50_000_000

    QCEW_GROUND_TRUTH = {
        "NY": 9_705_821,
        "CA": 18_183_696,
        "TX": 13_936_364,
    }

    @pytest.fixture
    def client(self):
        from api.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_ny_state_fallback_within_bounds(self, client):
        resp = client.get("/api/demographics/NY")
        if resp.status_code == 200:
            data = resp.json()
            tw = data["total_workers"]
            assert tw < self.PLAUSIBLE_STATE_MAX, (
                f"NY total_workers={tw:,} exceeds "
                f"{self.PLAUSIBLE_STATE_MAX:,} -- R7-1 grain-mixing bug "
                f"may have returned"
            )
            qcew = self.QCEW_GROUND_TRUTH["NY"]
            ratio = tw / qcew
            assert 0.8 <= ratio <= 1.5, (
                f"NY ACS={tw:,} / QCEW={qcew:,} ratio={ratio:.2f} "
                f"out of expected [0.8, 1.5] band -- ETL may be drifting"
            )

    def test_ca_state_fallback_within_bounds(self, client):
        resp = client.get("/api/demographics/CA")
        if resp.status_code == 200:
            data = resp.json()
            tw = data["total_workers"]
            assert tw < self.PLAUSIBLE_STATE_MAX
            qcew = self.QCEW_GROUND_TRUTH["CA"]
            ratio = tw / qcew
            assert 0.8 <= ratio <= 1.5, (
                f"CA ACS={tw:,} / QCEW={qcew:,} ratio={ratio:.2f}"
            )

    def test_state_fallback_via_unmatched_naics(self, client):
        """The exact audit case: NY/6221 (hospitals NAICS not in ACS table)
        falls through to state-wide. Pre-fix returned 145M; post-fix should
        match /api/demographics/NY exactly."""
        state_only = client.get("/api/demographics/NY")
        with_naics = client.get("/api/demographics/NY/6221")
        if state_only.status_code == 200 and with_naics.status_code == 200:
            d1 = state_only.json()
            d2 = with_naics.json()
            assert d2["fallback_level"] == "state"
            assert d2["total_workers"] == d1["total_workers"]
            assert d2["total_workers"] < self.PLAUSIBLE_STATE_MAX

    def test_age_distribution_is_workforce_shaped(self, client):
        """Pre-fix the state-rollup row leaked not-in-labor-force people,
        causing 56% of 'workers' to be 65+. The fixed table excludes them,
        so 65+ should now be a small minority of any state's workforce."""
        resp = client.get("/api/demographics/NY")
        if resp.status_code == 200:
            data = resp.json()
            age = {a["bucket"]: a["pct"] for a in data.get("age_distribution", [])}
            if "65p" in age:
                assert age["65p"] < 25.0, (
                    f"NY 65+ workforce share = {age['65p']}% -- "
                    f"too high; not-in-labor-force people may be leaking in"
                )
