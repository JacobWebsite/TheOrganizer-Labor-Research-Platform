import pytest

from db_config import get_connection


def _find_employer_with_matrix():
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
              WHERE b.industry_code LIKE regexp_replace(COALESCE(e.naics_detailed, e.naics), '[^0-9]', '', 'g') || '%'
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


def test_workforce_profile_returns_occupations(client):
    employer_id = _find_employer_with_matrix()
    if not employer_id:
        pytest.skip("No employer with matching BLS matrix data found")

    r = client.get(f"/api/employers/{employer_id}/workforce-profile")
    assert r.status_code == 200
    data = r.json()
    assert data["employer_id"] == employer_id
    assert data["naics_code"] is not None
    assert isinstance(data["workforce_profile"], list)
    assert len(data["workforce_profile"]) > 0
    top = data["workforce_profile"][0]
    assert "occupation_code" in top
    assert "occupation_title" in top
    assert "employment_share_pct" in top


def test_workforce_profile_sorted_descending_by_share(client):
    employer_id = _find_employer_with_matrix()
    if not employer_id:
        pytest.skip("No employer with matching BLS matrix data found")

    r = client.get(f"/api/employers/{employer_id}/workforce-profile?limit=20")
    assert r.status_code == 200
    shares = [row["employment_share_pct"] for row in r.json()["workforce_profile"] if row["employment_share_pct"] is not None]
    assert shares == sorted(shares, reverse=True)


def test_workforce_profile_handles_missing_naics(client):
    employer_id = _find_employer_without_naics()
    if not employer_id:
        pytest.skip("No employer without NAICS found")

    r = client.get(f"/api/employers/{employer_id}/workforce-profile")
    assert r.status_code == 200
    data = r.json()
    assert data["naics_code"] is None
    assert data["workforce_profile"] == []
    assert data["note"] == "Employer has no NAICS code"


def test_workforce_profile_404_for_unknown_employer(client):
    r = client.get("/api/employers/not-a-real-employer-id/workforce-profile")
    assert r.status_code == 404
