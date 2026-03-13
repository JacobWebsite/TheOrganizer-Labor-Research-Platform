"""Tests for union hierarchy endpoint and classification (Task 7-1)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_classify_union_level_dc():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('DC') == 'intermediate'


def test_classify_union_level_lu():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('LU') == 'local'


def test_classify_union_level_nhq():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('NHQ') == 'national'


def test_classify_union_level_fed():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('FED') == 'national'


def test_classify_union_level_jc():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('JC') == 'intermediate'


def test_classify_union_level_none():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level(None) == 'local'


def test_classify_union_level_whitespace():
    from api.routers.unions import _classify_union_level
    assert _classify_union_level('  DC  ') == 'intermediate'


def _find_aff_with_intermediates():
    """Find an affiliation that has intermediate bodies (DC, JC, etc.)."""
    from db_config import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT aff_abbr FROM unions_master
            WHERE TRIM(desig_name) IN ('DC', 'JC', 'CONF', 'D', 'C', 'SC', 'SA', 'BCTC')
              AND aff_abbr IS NOT NULL
            GROUP BY aff_abbr
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_hierarchy_returns_intermediates(client):
    """Hierarchy endpoint should return intermediates list for an affiliation with DCs/JCs."""
    aff = _find_aff_with_intermediates()
    if not aff:
        pytest.skip("No affiliation with intermediate bodies found")

    r = client.get(f"/api/unions/hierarchy/{aff}")
    assert r.status_code == 200
    data = r.json()
    assert data["affiliation"] == aff.upper()
    assert isinstance(data["intermediates"], list)
    assert len(data["intermediates"]) > 0
    # Each intermediate should have level_code and locals_count
    inter = data["intermediates"][0]
    assert "level_code" in inter
    assert "locals_count" in inter


def test_hierarchy_has_orphan_locals(client):
    """Hierarchy should include unaffiliated_locals with by_state dict."""
    aff = _find_aff_with_intermediates()
    if not aff:
        pytest.skip("No affiliation with intermediate bodies found")

    r = client.get(f"/api/unions/hierarchy/{aff}")
    assert r.status_code == 200
    data = r.json()
    assert "unaffiliated_locals" in data
    assert "by_state" in data["unaffiliated_locals"]
    assert isinstance(data["unaffiliated_locals"]["by_state"], dict)


def test_hierarchy_404_for_nonexistent(client):
    """Hierarchy endpoint returns 404 for nonexistent affiliation."""
    r = client.get("/api/unions/hierarchy/ZZZNOTREAL")
    assert r.status_code == 404
