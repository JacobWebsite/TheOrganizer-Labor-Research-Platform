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


def _get_master_with_f7_union_name() -> int:
    """A master whose F7 record carries a non-empty latest_union_name."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.master_id
                FROM master_employer_source_ids s
                JOIN f7_employers_deduped fe ON fe.employer_id = s.source_id
                WHERE s.source_system = 'f7'
                  AND NULLIF(TRIM(fe.latest_union_name), '') IS NOT NULL
                ORDER BY s.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def test_master_detail_f7_includes_union_presence(client):
    """A target-track master with an F7 link must surface union presence
    (demo wart: Yale/Montefiore showed 'No Known Union' despite F7 links)."""
    mid = _get_master_with_f7_union_name()
    if not mid:
        pytest.skip("No master with F7 union name found")
    r = client.get(f"/api/master/{mid}")
    assert r.status_code == 200
    up = r.json().get("union_presence")
    assert up is not None
    assert up["latest_union_name"]
    assert up["union_count"] >= 1
    assert isinstance(up["unions"], list) and len(up["unions"]) == up["union_count"]
    assert all(u.get("name") for u in up["unions"])


def test_master_detail_non_f7_union_presence_none(client):
    mid = _get_master_without_f7()
    if not mid:
        pytest.skip("No master record without f7 source found")
    r = client.get(f"/api/master/{mid}")
    assert r.status_code == 200
    assert r.json().get("union_presence") is None


def test_union_presence_dedupes_by_file_number_not_name(client):
    """Review finding (2026-07-18): the F7 filing spelling differs from the
    OLMS spelling for the same union file number on ~63% of F7-linked
    masters. Name-keyed dedup double-counted the union and rendered a false
    '+1 more'. Pick a master with exactly ONE distinct union file number
    whose two spellings differ, and require union_count == 1."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.master_id
                FROM master_employer_source_ids s
                JOIN f7_employers_deduped d ON d.employer_id = s.source_id
                JOIN f7_union_employer_relations r
                    ON r.employer_id = s.source_id
                LEFT JOIN unions_master um
                    ON um.f_num = r.union_file_number::varchar
                WHERE s.source_system = 'f7'
                  AND NULLIF(TRIM(d.latest_union_name), '') IS NOT NULL
                  AND d.latest_union_fnum = r.union_file_number
                  AND UPPER(TRIM(d.latest_union_name))
                      <> UPPER(COALESCE(um.union_name, ''))
                GROUP BY s.master_id
                HAVING COUNT(DISTINCT r.union_file_number) = 1
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No master with single-union name-mismatch found")
    r = client.get(f"/api/master/{row[0]}")
    assert r.status_code == 200
    up = r.json().get("union_presence")
    assert up is not None
    assert up["union_count"] == 1, (
        f"same union double-counted: {[u['name'] for u in up['unions']]}"
    )


def test_union_presence_nameless_f7_link_still_present(client):
    """Review finding (2026-07-18): an F7 link with no union name anywhere
    must still yield a presence block (union_count 0, name None) so the UI
    never claims 'No Known Union' for a master with a unionized unit."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.master_id
                FROM master_employer_source_ids s
                JOIN f7_employers_deduped d ON d.employer_id = s.source_id
                WHERE s.source_system = 'f7'
                  AND NULLIF(TRIM(d.latest_union_name), '') IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_union_employer_relations r
                      WHERE r.employer_id = s.source_id
                  )
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("No name-less F7-linked master found")
    r = client.get(f"/api/master/{row[0]}")
    assert r.status_code == 200
    up = r.json().get("union_presence")
    assert up is not None
    assert up["union_count"] == 0
    assert up["latest_union_name"] is None


def test_non_union_targets_excludes_union_rows(client):
    r = client.get("/api/master/non-union-targets?limit=20")
    assert r.status_code == 200
    for row in r.json().get("results", []):
        assert row.get("is_union") is False

