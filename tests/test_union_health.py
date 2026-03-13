"""Tests for union health composite indicators (Task 7-5)."""
import pytest
from db_config import get_connection


@pytest.fixture
def sample_fnum():
    """Get a union f_num that has LM data."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT um.f_num FROM unions_master um
            JOIN lm_data lm ON um.f_num = lm.f_num
            WHERE um.members > 100
            LIMIT 1
        """)
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No unions with LM data")
    return row[0]


def test_health_endpoint_200(client, sample_fnum):
    """Health endpoint returns 200 for a valid union."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    assert r.status_code == 200


def test_health_endpoint_404(client):
    """Health endpoint returns 404 for nonexistent union."""
    r = client.get("/api/unions/999999999/health")
    assert r.status_code == 404


def test_health_composite_score(client, sample_fnum):
    """Response includes composite with score and grade."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    data = r.json()
    assert "composite" in data
    assert "score" in data["composite"]
    assert "grade" in data["composite"]
    assert data["composite"]["grade"] in ("A", "B", "C", "D", "F")
    assert 0 <= data["composite"]["score"] <= 100


def test_health_has_all_indicators(client, sample_fnum):
    """Response includes all 4 indicator keys."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    data = r.json()
    for key in ("membership_trend", "election_win_rate", "financial_stability", "organizing_activity"):
        assert key in data


def test_health_no_nlrb_handling(client, sample_fnum):
    """Election win rate can be None if < 3 elections."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    data = r.json()
    # Just verify it doesn't crash -- value can be None or dict
    wr = data["election_win_rate"]
    if wr is not None:
        assert "score" in wr
        assert "wins" in wr
        assert "total" in wr


def test_health_financial_ratio(client, sample_fnum):
    """Financial stability includes asset_liability_ratio when data exists."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    data = r.json()
    fs = data["financial_stability"]
    if fs is not None:
        assert "asset_liability_ratio" in fs
        assert fs["asset_liability_ratio"] >= 0


def test_health_grade_boundaries(client, sample_fnum):
    """Grade letter matches score range."""
    r = client.get(f"/api/unions/{sample_fnum}/health")
    data = r.json()
    score = data["composite"]["score"]
    grade = data["composite"]["grade"]
    if score >= 80:
        assert grade == "A"
    elif score >= 60:
        assert grade == "B"
    elif score >= 40:
        assert grade == "C"
    elif score >= 20:
        assert grade == "D"
    else:
        assert grade == "F"
