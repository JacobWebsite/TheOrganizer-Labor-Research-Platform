import pytest

from db_config import get_connection


def _find_union_with_membership_history():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lm.f_num
        FROM ar_membership am
        JOIN lm_data lm ON lm.rpt_id = am.rpt_id
        GROUP BY lm.f_num
        HAVING COUNT(DISTINCT lm.yr_covered) >= 2
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def test_membership_history_returns_series(client):
    file_number = _find_union_with_membership_history()
    if not file_number:
        pytest.skip("No union with membership history found")

    r = client.get(f"/api/unions/{file_number}/membership-history")
    assert r.status_code == 200
    data = r.json()
    assert data["file_number"] == file_number
    assert isinstance(data["history"], list)
    assert len(data["history"]) > 0
    assert len(data["history"]) <= 10


def test_membership_history_sorted_and_structured(client):
    file_number = _find_union_with_membership_history()
    if not file_number:
        pytest.skip("No union with membership history found")

    r = client.get(f"/api/unions/{file_number}/membership-history")
    assert r.status_code == 200
    history = r.json()["history"]
    years = [p["year"] for p in history]
    assert years == sorted(years)
    for point in history:
        assert "year" in point
        assert "members" in point


def test_membership_history_computed_fields(client):
    file_number = _find_union_with_membership_history()
    if not file_number:
        pytest.skip("No union with membership history found")

    r = client.get(f"/api/unions/{file_number}/membership-history")
    assert r.status_code == 200
    data = r.json()
    assert data["trend"] in ("growing", "declining", "stable")
    assert "change_pct" in data
    assert "peak_year" in data
    assert "peak_members" in data


def test_membership_history_404_for_unknown_union(client):
    r = client.get("/api/unions/not-a-real-union/membership-history")
    assert r.status_code == 404
