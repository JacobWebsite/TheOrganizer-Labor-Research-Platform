import pytest

from db_config import get_connection


def _find_union_with_disbursements():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lm.f_num
        FROM ar_disbursements_total adt
        JOIN lm_data lm ON lm.rpt_id = adt.rpt_id
        WHERE lm.f_num IS NOT NULL
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def test_organizing_capacity_returns_expected_fields(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/organizing-capacity")
    assert r.status_code == 200
    data = r.json()
    assert data["file_number"] == file_number
    assert "organizing_spend_pct" in data
    assert "total_disbursements" in data
    assert "organizing_disbursements" in data
    assert "reporting_year" in data
    assert data["membership_trend"] in ("growing", "declining", "stable")


def test_organizing_capacity_pct_range(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/organizing-capacity")
    assert r.status_code == 200
    pct = r.json()["organizing_spend_pct"]
    if pct is not None:
        assert 0 <= pct <= 100


def test_organizing_capacity_includes_categories(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/organizing-capacity")
    assert r.status_code == 200
    cats = r.json()["organizing_categories"]
    assert "representational" in cats
    assert "strike_benefits" in cats


def test_organizing_capacity_404_for_unknown_union(client):
    r = client.get("/api/unions/not-a-real-union/organizing-capacity")
    assert r.status_code == 404
