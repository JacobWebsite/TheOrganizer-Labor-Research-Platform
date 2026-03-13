from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _make_conn(fetchone_values=None, fetchall_values=None):
    cur = MagicMock()
    cur.fetchone.side_effect = fetchone_values or []
    cur.fetchall.return_value = fetchall_values or []
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


@patch("api.routers.campaigns.get_db")
def test_post_creates_outcome(mock_get_db):
    mock_get_db.return_value = _make_conn(fetchone_values=[{"id": 12, "created_at": "2026-03-05T12:00:00Z"}])

    resp = client.post("/api/campaigns/outcomes", json={
        "employer_id": "ABC123",
        "employer_name": "Acme Logistics",
        "outcome": "won",
        "notes": "Recognized after neutrality agreement.",
        "reported_by": "Maria",
        "outcome_date": "2026-03-05",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 12
    assert "created_at" in data


@patch("api.routers.campaigns.get_db")
def test_get_returns_outcomes(mock_get_db):
    mock_get_db.return_value = _make_conn(fetchall_values=[{
        "id": 1,
        "employer_id": "ABC123",
        "employer_name": "Acme Logistics",
        "outcome": "in_progress",
        "notes": "Card drive underway",
        "reported_by": "Alex",
        "outcome_date": "2026-03-01",
        "created_at": "2026-03-01T10:00:00Z",
        "updated_at": "2026-03-01T10:00:00Z",
    }])

    resp = client.get("/api/campaigns/outcomes/ABC123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["employer_id"] == "ABC123"
    assert len(data["outcomes"]) == 1
    assert data["outcomes"][0]["outcome"] == "in_progress"


def test_outcome_validation():
    resp = client.post("/api/campaigns/outcomes", json={
        "employer_id": "ABC123",
        "outcome": "maybe",
    })
    assert resp.status_code == 422


def test_employer_id_required():
    resp = client.post("/api/campaigns/outcomes", json={
        "employer_id": "",
        "outcome": "won",
    })
    assert resp.status_code == 422
