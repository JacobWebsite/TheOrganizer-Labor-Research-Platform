import pytest

from db_config import get_connection


def _get_any_master_id() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT master_id FROM master_employers ORDER BY master_id LIMIT 1")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def _get_master_with_f7() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.master_id
                FROM master_employer_source_ids s
                WHERE s.source_system = 'f7'
                ORDER BY s.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def _get_master_without_f7() -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.master_id
                FROM master_employers m
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM master_employer_source_ids s
                    WHERE s.master_id = m.master_id
                      AND s.source_system = 'f7'
                )
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def test_master_stats_structure(client):
    r = client.get("/api/master/stats")
    assert r.status_code == 200
    data = r.json()
    for k in ["total", "by_source_origin", "top_states", "flags", "quality_distribution", "avg_source_count"]:
        assert k in data
    assert data["total"] > 0


def test_master_search_name_query(client):
    r = client.get("/api/master/search?q=union&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data and "total" in data
    assert len(data["results"]) <= 5


def test_master_search_state_filter(client):
    r = client.get("/api/master/search?state=NY&limit=10")
    assert r.status_code == 200
    for row in r.json().get("results", []):
        assert row.get("state") == "NY"


def test_master_search_pagination(client):
    r1 = client.get("/api/master/search?page=1&limit=5")
    r2 = client.get("/api/master/search?page=2&limit=5")
    assert r1.status_code == 200 and r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()
    assert d1["page"] == 1
    assert d2["page"] == 2


def test_master_detail_f7_includes_scorecard_block(client):
    mid = _get_master_with_f7()
    if not mid:
        pytest.skip("No master record with f7 source found")
    r = client.get(f"/api/master/{mid}")
    assert r.status_code == 200
    data = r.json()
    assert "master" in data and "source_ids" in data and "enrichment" in data
    assert "scorecard" in data["enrichment"]


def test_master_detail_non_f7_has_no_scorecard_block(client):
    mid = _get_master_without_f7()
    if not mid:
        pytest.skip("No master record without f7 source found")
    r = client.get(f"/api/master/{mid}")
    assert r.status_code == 200
    data = r.json()
    assert "enrichment" in data
    assert data["enrichment"].get("scorecard") in (None, {})


def test_master_detail_404_for_bad_id(client):
    r = client.get("/api/master/999999999")
    assert r.status_code == 404


def test_non_union_targets_excludes_union_rows(client):
    r = client.get("/api/master/non-union-targets?limit=20")
    assert r.status_code == 200
    for row in r.json().get("results", []):
        assert row.get("is_union") is False

