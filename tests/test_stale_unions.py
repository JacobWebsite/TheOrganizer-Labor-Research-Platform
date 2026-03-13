"""Tests for stale union flagging (Task 7-4)."""
import pytest
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def test_is_likely_inactive_column_exists():
    """Verify is_likely_inactive column exists in unions_master."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM pg_attribute
            WHERE attrelid = 'unions_master'::regclass
              AND attname = 'is_likely_inactive'
              AND NOT attisdropped
        """)
        assert cur.fetchone() is not None, "is_likely_inactive column missing from unions_master"
    finally:
        conn.close()


def test_search_returns_is_likely_inactive(client):
    """Search endpoint should include is_likely_inactive field."""
    r = client.get("/api/unions/search?limit=1")
    assert r.status_code == 200
    data = r.json()
    if data["unions"]:
        assert "is_likely_inactive" in data["unions"][0]


def test_national_unions_returns_data(client):
    """National unions endpoint should return data (smoke test)."""
    r = client.get("/api/unions/national?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "national_unions" in data
    assert isinstance(data["national_unions"], list)


def test_national_unions_has_deduplicated_members(client):
    """National unions endpoint should include deduplicated_members."""
    r = client.get("/api/unions/national?limit=5")
    assert r.status_code == 200
    data = r.json()
    if data["national_unions"]:
        assert "deduplicated_members" in data["national_unions"][0]


def test_deduplicated_total_within_bls_range(client):
    """Sum of deduplicated_members across affiliations should be roughly near BLS 14.3M."""
    r = client.get("/api/unions/national?limit=200")
    assert r.status_code == 200
    data = r.json()
    total = sum(u.get("deduplicated_members", 0) or 0 for u in data["national_unions"])
    # Should be much less than the overcounted ~71.8M
    assert total < 30_000_000, f"Deduplicated total {total:,} still too high"


def test_summary_has_deduplicated_members(client):
    """Platform summary should include deduplicated_members."""
    r = client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert "deduplicated_members" in data["unions"]


def test_affiliations_lookup_has_deduplicated_members(client):
    """Affiliations lookup should include deduplicated_members."""
    r = client.get("/api/lookups/affiliations")
    assert r.status_code == 200
    data = r.json()
    if data["affiliations"]:
        assert "deduplicated_members" in data["affiliations"][0]


def test_union_detail_includes_is_likely_inactive(client):
    """Union detail endpoint should include is_likely_inactive."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT f_num FROM unions_master LIMIT 1")
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        pytest.skip("No unions in database")

    f_num = row[0]
    r = client.get(f"/api/unions/{f_num}")
    assert r.status_code == 200
    data = r.json()
    assert "is_likely_inactive" in data["union"]
