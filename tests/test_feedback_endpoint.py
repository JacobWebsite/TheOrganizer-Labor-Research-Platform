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


@patch("api.routers.feedback.get_db")
def test_post_creates_feedback(mock_get_db):
    mock_get_db.return_value = _make_conn(
        fetchone_values=[{"id": 7, "created_at": "2026-07-11T00:00:00Z"}]
    )

    resp = client.post(
        "/api/feedback",
        json={
            "category": "bug",
            "message": "The score gauge does not render on Firefox.",
            "page_url": "/employers/M123",
            "employer_id": "M123",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 7
    assert data["status"] == "received"


@patch("api.routers.feedback.get_db")
def test_get_lists_feedback(mock_get_db):
    mock_get_db.return_value = _make_conn(
        fetchall_values=[
            {
                "id": 1,
                "category": "confusing",
                "message": "I could not find the export button.",
                "page_url": "/targets",
                "employer_id": None,
                "submitted_by": None,
                "status": "new",
                "created_at": "2026-07-11T00:00:00Z",
            }
        ]
    )

    resp = client.get("/api/feedback")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["feedback"][0]["category"] == "confusing"


def test_invalid_category_rejected():
    resp = client.post("/api/feedback", json={"category": "spam", "message": "hello"})
    assert resp.status_code == 422


def test_message_required():
    resp = client.post("/api/feedback", json={"category": "bug", "message": ""})
    assert resp.status_code == 422
