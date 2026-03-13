import pytest

from db_config import get_connection


def _find_employer_with_naics():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.employer_id
        FROM f7_employers_deduped e
        WHERE COALESCE(e.naics_detailed, e.naics) IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM bls_industry_occupation_matrix b
              WHERE b.industry_code LIKE regexp_replace(
                  COALESCE(e.naics_detailed, e.naics), '[^0-9]', '', 'g'
              ) || '%%'
          )
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def _find_employer_without_naics():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT employer_id
        FROM f7_employers_deduped
        WHERE NULLIF(TRIM(COALESCE(naics_detailed, naics, '')), '') IS NULL
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def test_occupations_endpoint_returns_200(client):
    employer_id = _find_employer_with_naics()
    if not employer_id:
        pytest.skip("No employer with matching BLS matrix data found")

    r = client.get(f"/api/profile/employers/{employer_id}/occupations")
    assert r.status_code == 200
    data = r.json()
    assert "top_occupations" in data
    assert "similar_industries" in data
    assert isinstance(data["top_occupations"], list)
    assert isinstance(data["similar_industries"], list)


def test_occupations_has_occupation_fields(client):
    employer_id = _find_employer_with_naics()
    if not employer_id:
        pytest.skip("No employer with matching BLS matrix data found")

    r = client.get(f"/api/profile/employers/{employer_id}/occupations")
    assert r.status_code == 200
    data = r.json()
    assert len(data["top_occupations"]) > 0
    occ = data["top_occupations"][0]
    assert "occupation_code" in occ
    assert "occupation_title" in occ
    assert "employment_2024" in occ
    assert "employment_change_pct" in occ


def test_occupations_empty_for_no_naics(client):
    employer_id = _find_employer_without_naics()
    if not employer_id:
        pytest.skip("No employer without NAICS found")

    r = client.get(f"/api/profile/employers/{employer_id}/occupations")
    assert r.status_code == 200
    data = r.json()
    assert data["employer_naics"] is None
    assert data["top_occupations"] == []
    assert data["similar_industries"] == []


def test_occupations_404_for_unknown_employer(client):
    r = client.get("/api/profile/employers/not-a-real-employer-id/occupations")
    assert r.status_code == 404
