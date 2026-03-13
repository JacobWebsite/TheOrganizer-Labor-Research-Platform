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


def test_disbursements_returns_200(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/disbursements")
    assert r.status_code == 200


def test_disbursements_has_years_with_categories(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/disbursements")
    assert r.status_code == 200
    data = r.json()
    assert data["file_number"] == file_number
    assert isinstance(data["years"], list)
    assert len(data["years"]) > 0

    yr = data["years"][0]
    for key in ("organizing", "compensation", "benefits_members",
                "administration", "external", "total"):
        assert key in yr
    assert isinstance(yr["categories"], dict)
    assert "representational" in yr["categories"]
    assert "to_officers" in yr["categories"]


def test_disbursements_has_strike_fund_field(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/disbursements")
    assert r.status_code == 200
    data = r.json()
    assert "has_strike_fund" in data
    assert isinstance(data["has_strike_fund"], bool)


def test_disbursements_totals_add_up(client):
    file_number = _find_union_with_disbursements()
    if not file_number:
        pytest.skip("No union with disbursements found")

    r = client.get(f"/api/unions/{file_number}/disbursements")
    data = r.json()
    for yr in data["years"]:
        expected = (
            yr["organizing"]
            + yr["compensation"]
            + yr["benefits_members"]
            + yr["administration"]
            + yr["external"]
        )
        assert abs(yr["total"] - expected) < 0.01


def test_disbursements_404_for_unknown_union(client):
    r = client.get("/api/unions/not-a-real-union-99999/disbursements")
    assert r.status_code == 404
