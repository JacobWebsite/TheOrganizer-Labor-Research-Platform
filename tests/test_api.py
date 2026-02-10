"""
API integration tests for the Labor Research Platform.

Tests the 20 most critical endpoints for:
- HTTP 200 responses
- Expected response structure (keys present)
- Non-empty data
- Response time < 5 seconds

Requires: running PostgreSQL with olms_multiyear database.
Run with: py -m pytest tests/test_api.py -v
"""
import pytest
import time


# ============================================================================
# SUMMARY & HEALTH
# ============================================================================

def test_summary(client):
    """Platform summary returns union, employer, NLRB, and VR counts."""
    r = client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert "unions" in data
    assert "employers" in data
    assert "nlrb" in data
    # Unions should have substantial counts
    assert data["unions"]["total_unions"] > 20000


def test_stats_breakdown(client):
    """Stats breakdown returns sector-level data."""
    r = client.get("/api/stats/breakdown")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (dict, list))


# ============================================================================
# LOOKUPS
# ============================================================================

def test_lookups_sectors(client):
    """Sectors lookup returns known sector list."""
    r = client.get("/api/lookups/sectors")
    assert r.status_code == 200
    data = r.json()
    assert "sectors" in data
    sector_codes = [s["sector_code"] for s in data["sectors"]]
    assert "PRIVATE" in sector_codes


def test_lookups_states(client):
    """States lookup returns 51 entries (50 states + DC)."""
    r = client.get("/api/lookups/states")
    assert r.status_code == 200
    data = r.json()
    assert "states" in data
    assert len(data["states"]) >= 50


def test_lookups_affiliations(client):
    """Affiliations lookup returns major union abbreviations."""
    r = client.get("/api/lookups/affiliations")
    assert r.status_code == 200
    data = r.json()
    assert "affiliations" in data
    abbrs = [a["aff_abbr"] for a in data["affiliations"]]
    assert "SEIU" in abbrs or "SEI" in abbrs


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

def test_employer_search_walmart(client):
    """Searching for 'walmart' returns results."""
    r = client.get("/api/employers/search?q=walmart&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "employers" in data
    assert "total" in data
    assert data["total"] > 0
    assert len(data["employers"]) > 0


def test_employer_search_empty(client):
    """Searching for gibberish returns 200 (not an error)."""
    r = client.get("/api/employers/search?q=zzzzxxxxxnotreal&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "employers" in data


def test_employer_search_by_state(client):
    """Filtering employers by state returns results."""
    r = client.get("/api/employers/search?state=NY&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 0
    # All results should be in NY
    for emp in data["employers"]:
        assert emp.get("state") == "NY"


def test_employer_cities(client):
    """Employer cities endpoint returns city list with counts."""
    r = client.get("/api/employers/cities?state=NY&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "cities" in data
    assert len(data["cities"]) > 0


# ============================================================================
# UNION SEARCH
# ============================================================================

def test_union_search(client):
    """Searching for 'teamsters' returns results."""
    r = client.get("/api/unions/search?name=teamsters&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "unions" in data
    assert data["total"] > 0
    assert data["total"] < 1000  # Should be filtered, not all 26K


def test_union_detail(client):
    """Getting a union by f_num returns detail."""
    # First search to get a valid f_num
    r = client.get("/api/unions/search?name=seiu&limit=1")
    assert r.status_code == 200
    unions = r.json()["unions"]
    if len(unions) > 0:
        f_num = unions[0]["f_num"]
        r2 = client.get(f"/api/unions/{f_num}")
        assert r2.status_code == 200
        detail = r2.json()
        assert "union" in detail
        assert "union_name" in detail["union"] or "f_num" in detail["union"]


# ============================================================================
# NLRB
# ============================================================================

def test_nlrb_elections_search(client):
    """NLRB election search returns results."""
    r = client.get("/api/nlrb/elections/search?state=NY&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data or "elections" in data or isinstance(data, list)


def test_nlrb_elections_by_year(client):
    """NLRB elections by year returns yearly counts."""
    r = client.get("/api/nlrb/elections/by-year")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (dict, list))


def test_nlrb_elections_by_state(client):
    """NLRB elections by state returns state-level counts."""
    r = client.get("/api/nlrb/elections/by-state")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (dict, list))


# ============================================================================
# DENSITY
# ============================================================================

def test_density_by_state(client):
    """State density returns all 51 states."""
    r = client.get("/api/density/by-state")
    assert r.status_code == 200
    data = r.json()
    assert "states" in data
    assert len(data["states"]) >= 50


# ============================================================================
# OSHA
# ============================================================================

def test_osha_summary(client):
    """OSHA summary returns aggregate statistics."""
    r = client.get("/api/osha/summary")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data


# ============================================================================
# TRENDS
# ============================================================================

def test_trends_national(client):
    """National trends returns multi-year membership data."""
    r = client.get("/api/trends/national")
    assert r.status_code == 200
    data = r.json()
    assert "trends" in data
    assert len(data["trends"]) > 0


# ============================================================================
# PERFORMANCE
# ============================================================================

@pytest.mark.slow
def test_response_times(client):
    """All critical endpoints respond within 5 seconds."""
    endpoints = [
        "/api/summary",
        "/api/lookups/sectors",
        "/api/employers/search?q=hospital&limit=10",
        "/api/unions/search?q=afscme&limit=10",
        "/api/nlrb/elections/search?state=CA&limit=10",
        "/api/density/by-state",
        "/api/osha/summary",
        "/api/trends/national",
    ]
    slow = []
    for ep in endpoints:
        start = time.time()
        r = client.get(ep)
        elapsed = time.time() - start
        if elapsed > 5.0:
            slow.append((ep, elapsed))

    if slow:
        msg = "\n".join(f"  {ep}: {t:.1f}s" for ep, t in slow)
        pytest.fail(f"Slow endpoints (>5s):\n{msg}")


# ============================================================================
# ERROR HANDLING
# ============================================================================

def test_invalid_endpoint_returns_404(client):
    """Non-existent endpoint returns 404."""
    r = client.get("/api/nonexistent/endpoint")
    assert r.status_code in (404, 405)


def test_invalid_sector_returns_404(client):
    """Invalid sector name returns 404."""
    r = client.get("/api/sectors/fakesector/summary")
    assert r.status_code == 404
