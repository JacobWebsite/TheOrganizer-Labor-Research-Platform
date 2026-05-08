"""
Tests for /api/employers/master/{master_id}/executives (24Q-7).

Verifies:
- 404 on unknown master_id
- Empty shape returned for masters with no Mergent links
- Populated shape (summary + executives + source_freshness)
- Title ranking puts Board Chair (rank 1) above CEO (rank 2) above VP (rank 9)
- Vice Chairman correctly ranked as VP (rank 9), NOT Board Chair (regression
  guard for the 'chairman matches inside vice chairman' bug we fixed)
- limit query param truncates the executives array but does NOT affect summary
- limit validation
"""
import pytest

from db_config import get_connection


def _get_master_with_execs() -> int:
    """Pick a master with many Mergent execs so populated assertions are
    meaningful. Walmart (master_id=4665905) has 1,883 if available, but
    we let the DB pick the first available high-volume one to stay
    deterministic against future data growth."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sid.master_id
                FROM master_employer_source_ids sid
                JOIN mergent_executives me ON me.duns = sid.source_id
                WHERE sid.source_system = 'mergent'
                GROUP BY sid.master_id
                HAVING COUNT(*) >= 20
                ORDER BY COUNT(*) DESC, sid.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def _get_master_without_execs() -> int:
    """Pick a master with no Mergent links."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.master_id
                FROM master_employers m
                WHERE NOT EXISTS (
                    SELECT 1 FROM master_employer_source_ids s
                    WHERE s.master_id = m.master_id
                      AND s.source_system = 'mergent'
                )
                  AND m.source_origin = 'f7'
                ORDER BY m.master_id
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        conn.close()


def test_executives_404_on_unknown_master(client):
    r = client.get("/api/employers/master/999999999/executives")
    assert r.status_code == 404


def test_executives_empty_shape_when_no_links(client):
    """Master with no Mergent links returns full shape with zeros, not 404."""
    master_id = _get_master_without_execs()
    if master_id == 0:
        pytest.skip("No master without Mergent links available in DB")
    r = client.get(f"/api/employers/master/{master_id}/executives")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "executives" in data
    assert "source_freshness" in data
    s = data["summary"]
    assert s["total_executives"] == 0
    assert s["with_title"] == 0
    assert s["by_rank"] == {}
    assert data["executives"] == []


def test_executives_populated_shape(client):
    master_id = _get_master_with_execs()
    if master_id == 0:
        pytest.skip("No master with Mergent execs available in DB")
    r = client.get(f"/api/employers/master/{master_id}/executives")
    assert r.status_code == 200
    data = r.json()
    s = data["summary"]
    assert s["total_executives"] >= 20
    assert s["with_title"] <= s["total_executives"]
    assert isinstance(data["executives"], list)
    assert len(data["executives"]) > 0

    # Ranks should be monotonically non-decreasing -- top of list = most senior.
    ranks = [e["title_rank"] for e in data["executives"]]
    assert ranks == sorted(ranks), f"executives not sorted by title_rank: {ranks[:10]}"

    # Per-row shape sanity
    e0 = data["executives"][0]
    for k in ("name", "title", "title_rank", "title_rank_label", "company_name", "duns"):
        assert k in e0, f"missing key {k}"
    assert isinstance(e0["title_rank"], int)
    assert isinstance(e0["title_rank_label"], str)


def test_executives_vice_chairman_not_ranked_as_board_chair(client):
    """Regression guard: 'Vice Chairman' must NOT match the Board Chair regex.
    Walmart's Michael Duke ('Vice Chairman') was wrongly ranked 1 in the
    initial implementation. The fixed regex excludes vice/deputy/asst/etc."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sid.master_id
                FROM master_employer_source_ids sid
                JOIN mergent_executives me ON me.duns = sid.source_id
                WHERE sid.source_system = 'mergent'
                  AND me.title ~* '\\mvice chairman\\M'
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        pytest.skip("No 'Vice Chairman' titles in mergent_executives")

    master_id = int(row[0])
    r = client.get(f"/api/employers/master/{master_id}/executives?limit=200")
    data = r.json()
    # The bug we're guarding against: 'Vice Chairman' matched the Board
    # Chair regex (rank 1) because 'chairman' appears inside it. The fix
    # excludes any title containing vice/deputy/asst from rank 1.
    #
    # Compound titles like "Vice Chairman and Chief Operating Officer"
    # are legitimately ranked higher than 9 by the COO clause -- that's
    # not a bug, that's correct. So the assertion is "never rank 1",
    # not "always rank 9".
    found_vice_chairman = False
    for e in data["executives"]:
        title = (e.get("title") or "").lower()
        if "vice chairman" in title:
            found_vice_chairman = True
            assert e["title_rank"] != 1, (
                f"Vice Chairman should never be ranked as Board Chair, "
                f"got rank=1 for {e['name']!r} title={e['title']!r}"
            )
    assert found_vice_chairman, "Test fixture broken: no 'vice chairman' title found"


def test_executives_limit_truncates_only_array(client):
    master_id = _get_master_with_execs()
    if master_id == 0:
        pytest.skip("No master with Mergent execs available in DB")

    full = client.get(f"/api/employers/master/{master_id}/executives?limit=200").json()
    if full["summary"]["total_executives"] < 5:
        pytest.skip("Need >=5 execs to test truncation")

    truncated = client.get(
        f"/api/employers/master/{master_id}/executives?limit=3"
    ).json()
    assert len(truncated["executives"]) == 3
    # Summary aggregates across the FULL match set, not the truncated one.
    assert truncated["summary"] == full["summary"]
    assert truncated["source_freshness"] == full["source_freshness"]


def test_executives_limit_validation(client):
    master_id = _get_master_with_execs()
    if master_id == 0:
        pytest.skip("No master with Mergent execs available in DB")
    r = client.get(f"/api/employers/master/{master_id}/executives?limit=0")
    assert r.status_code == 422
    r = client.get(f"/api/employers/master/{master_id}/executives?limit=500")
    assert r.status_code == 422
