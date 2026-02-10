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
# ORGANIZING SCORECARD (Phase 2)
# ============================================================================

def test_scorecard_list(client):
    """Scorecard returns scored organizing targets with breakdown."""
    r = client.get("/api/organizing/scorecard?state=NY&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "total" in data
    assert "scored_count" in data
    if data["results"]:
        item = data["results"][0]
        assert "organizing_score" in item
        assert "score_breakdown" in item
        bd = item["score_breakdown"]
        # Phase 2 fields
        assert "geographic" in bd
        assert "size" in bd
        assert "osha" in bd
        assert "industry_density" in bd
        # OSHA normalization produces a ratio
        assert "osha_industry_ratio" in item


def test_scorecard_detail(client):
    """Scorecard detail returns per-establishment scoring with context."""
    # Get a valid establishment ID first
    r = client.get("/api/organizing/scorecard?state=NY&limit=1")
    assert r.status_code == 200
    results = r.json()["results"]
    if results:
        eid = results[0]["establishment_id"]
        r2 = client.get(f"/api/organizing/scorecard/{eid}")
        assert r2.status_code == 200
        d = r2.json()
        assert "organizing_score" in d
        assert "score_breakdown" in d
        # Phase 2 context fields
        assert "osha_context" in d
        assert "industry_ratio" in d["osha_context"]
        assert "geographic_context" in d
        assert "is_rtw_state" in d["geographic_context"]
        assert "nlrb_win_rate" in d["geographic_context"]


def test_scorecard_invalid_id(client):
    """Scorecard detail returns 404 for invalid establishment."""
    r = client.get("/api/organizing/scorecard/nonexistent_id_12345")
    assert r.status_code == 404


def test_siblings(client):
    """Sibling endpoint returns similar unionized employers."""
    # Get a valid establishment ID
    r = client.get("/api/organizing/scorecard?state=NY&limit=1")
    assert r.status_code == 200
    results = r.json()["results"]
    if results:
        eid = results[0]["establishment_id"]
        r2 = client.get(f"/api/organizing/siblings/{eid}?limit=5")
        assert r2.status_code == 200
        d = r2.json()
        assert "target" in d
        assert "siblings" in d
        assert "total_found" in d
        if d["siblings"]:
            sib = d["siblings"][0]
            assert "employer_name" in sib
            assert "match_score" in sib
            assert "match_reasons" in sib


def test_siblings_invalid_id(client):
    """Siblings endpoint returns 404 for invalid establishment."""
    r = client.get("/api/organizing/siblings/nonexistent_id_12345")
    assert r.status_code == 404


# ============================================================================
# EMPLOYER COMPARABLES
# ============================================================================

def test_comparables_endpoint(client):
    """Comparables endpoint returns similar unionized employers."""
    # Find an employer with comparables data
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from db_config import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT employer_id FROM employer_comparables LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        pytest.skip("No comparables data computed yet")

    eid = row[0]
    r = client.get(f"/api/employers/{eid}/comparables")
    assert r.status_code == 200
    data = r.json()
    assert "employer_id" in data
    assert "employer_name" in data
    assert "comparables" in data
    assert len(data["comparables"]) > 0
    comp = data["comparables"][0]
    assert "rank" in comp
    assert "gower_distance" in comp
    assert "similarity_pct" in comp
    assert "match_reasons" in comp
    assert "feature_breakdown" in comp
    assert comp["rank"] == 1
    assert 0 <= comp["gower_distance"] <= 1


def test_comparables_invalid_id(client):
    """Comparables endpoint returns 404 for non-existent employer."""
    r = client.get("/api/employers/999999999/comparables")
    assert r.status_code == 404


# ============================================================================
# NLRB PATTERNS
# ============================================================================

def test_nlrb_patterns_endpoint(client):
    """NLRB patterns endpoint returns industry, size, and state win rates."""
    r = client.get("/api/nlrb/patterns")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert data["summary"]["total_elections"] > 30000
    assert 50 < data["summary"]["overall_win_rate"] < 90
    assert "by_industry" in data
    assert len(data["by_industry"]) >= 20
    assert "by_size" in data
    assert len(data["by_size"]) == 8
    assert "by_state" in data
    assert len(data["by_state"]) >= 50


def test_scorecard_has_nlrb_predicted(client):
    """Scorecard list results include nlrb_predicted_win_pct."""
    r = client.get("/api/organizing/scorecard?limit=5&min_score=20")
    assert r.status_code == 200
    data = r.json()
    assert len(data["results"]) > 0
    result = data["results"][0]
    # Should have nlrb_predicted_win_pct field
    assert "nlrb_predicted_win_pct" in result
    if result["nlrb_predicted_win_pct"] is not None:
        assert 50 <= result["nlrb_predicted_win_pct"] <= 100


def test_scorecard_detail_has_nlrb_context(client):
    """Scorecard detail includes nlrb_context with predicted win pct and factors."""
    # Get an establishment from scorecard list first
    r = client.get("/api/organizing/scorecard?limit=1&min_score=20")
    assert r.status_code == 200
    results = r.json()["results"]
    if not results:
        pytest.skip("No scorecard results")
    estab_id = results[0]["establishment_id"]

    r2 = client.get(f"/api/organizing/scorecard/{estab_id}")
    assert r2.status_code == 200
    detail = r2.json()
    assert "nlrb_context" in detail
    ctx = detail["nlrb_context"]
    assert "predicted_win_pct" in ctx
    assert "state_win_rate" in ctx
    assert "industry_win_rate" in ctx
    assert "direct_case_count" in ctx


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
