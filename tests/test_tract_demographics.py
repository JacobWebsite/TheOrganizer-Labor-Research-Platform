"""Tests for census tract demographics integration (Task 3-12)."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "false")
from db_config import get_connection
from psycopg2.extras import RealDictCursor


@pytest.fixture(scope="module")
def db():
    conn = get_connection(cursor_factory=RealDictCursor)
    yield conn
    conn.close()


def test_acs_tract_table_exists(db):
    """acs_tract_demographics table must exist."""
    cur = db.cursor()
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM pg_class WHERE relname = 'acs_tract_demographics'
        ) AS e
    """)
    assert cur.fetchone()["e"] is True


def test_acs_tract_has_expected_columns(db):
    """Key columns must be present on acs_tract_demographics."""
    cur = db.cursor()
    cur.execute("""
        SELECT attname FROM pg_attribute
        WHERE attrelid = 'acs_tract_demographics'::regclass
          AND attnum > 0 AND NOT attisdropped
    """)
    cols = {r["attname"] for r in cur.fetchall()}
    expected = {
        "tract_fips", "state_fips", "county_fips", "total_population",
        "pop_white", "pop_black", "pop_hispanic", "pop_female",
        "edu_bachelors", "median_household_income", "unemployment_rate",
        "pct_female", "pct_minority", "pct_bachelors_plus", "acs_year",
    }
    assert expected.issubset(cols), "Missing columns: %s" % (expected - cols)


def test_f7_has_census_tract_column(db):
    """f7_employers_deduped must have census_tract column."""
    cur = db.cursor()
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM pg_attribute
            WHERE attrelid = 'f7_employers_deduped'::regclass
              AND attname = 'census_tract'
              AND NOT attisdropped
        ) AS e
    """)
    assert cur.fetchone()["e"] is True


def test_workforce_profile_includes_tract_key():
    """Workforce profile endpoint response includes 'tract' key."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)

    # Pick an employer that exists
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        pytest.skip("No employers in DB")

    resp = client.get("/api/profile/employers/%s/workforce-profile" % row["employer_id"])
    assert resp.status_code == 200
    data = resp.json()
    assert "tract" in data, "Response must include 'tract' key"


def test_workforce_profile_tract_null_when_missing():
    """Employer without census_tract returns tract: null."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("""
        SELECT employer_id FROM f7_employers_deduped
        WHERE census_tract IS NULL LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if not row:
        pytest.skip("All employers have census_tract (unlikely)")

    resp = client.get("/api/profile/employers/%s/workforce-profile" % row["employer_id"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["tract"] is None
