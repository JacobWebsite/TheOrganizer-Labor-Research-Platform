"""Tests for corporate router endpoints (hierarchy, family, multi-employer, SEC)."""
import pytest


class TestMultiEmployerStats:
    """Tests for GET /api/multi-employer/stats"""

    def test_returns_summary(self, client):
        r = client.get("/api/multi-employer/stats")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "by_reason" in data
        assert "top_groups" in data
        assert data["summary"]["total_employers"] > 0


class TestMultiEmployerGroups:
    """Tests for GET /api/multi-employer/groups"""

    def test_default_limit(self, client):
        r = client.get("/api/multi-employer/groups")
        assert r.status_code == 200
        data = r.json()
        assert "groups" in data
        assert isinstance(data["groups"], list)

    def test_custom_limit(self, client):
        r = client.get("/api/multi-employer/groups", params={"limit": 5})
        assert r.status_code == 200
        assert len(r.json()["groups"]) <= 5


class TestEmployerAgreement:
    """Tests for GET /api/employer/{employer_id}/agreement"""

    def test_not_found(self, client):
        r = client.get("/api/employer/nonexistent_id_999/agreement")
        assert r.status_code == 404

    def test_valid_employer(self, client):
        # Get a real employer_id from multi-employer stats
        stats = client.get("/api/multi-employer/stats").json()
        groups = stats.get("top_groups", [])
        if not groups:
            pytest.skip("No multi-employer groups")

        # Search for an employer in the first group
        group_id = groups[0]["multi_employer_group_id"]
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employer_id FROM f7_employers_deduped WHERE multi_employer_group_id = %s LIMIT 1",
                    [group_id],
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers in group")

        r = client.get(f"/api/employer/{row[0]}/agreement")
        assert r.status_code == 200
        data = r.json()
        assert "employer" in data
        assert "group_members" in data
        assert "group_size" in data


class TestEmployerMatches:
    """Tests for GET /api/employers/{employer_id}/matches"""

    def test_not_found(self, client):
        r = client.get("/api/employers/nonexistent_id_999/matches")
        assert r.status_code == 404

    def test_valid_employer(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers in database")

        r = client.get(f"/api/employers/{row[0]}/matches")
        assert r.status_code == 200
        data = r.json()
        assert "employer_id" in data
        assert "matches" in data
        assert isinstance(data["matches"], list)


class TestCorporateFamily:
    """Tests for GET /api/corporate/family/{employer_id}"""

    def test_not_found(self, client):
        r = client.get("/api/corporate/family/nonexistent_id_999")
        assert r.status_code == 404

    def test_valid_employer(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers in database")

        r = client.get(f"/api/corporate/family/{row[0]}")
        assert r.status_code == 200
        data = r.json()
        assert "employer" in data
        assert "root_name" in data
        assert "hierarchy_source" in data
        assert "family_members" in data
        assert "total_family" in data
        assert "total_workers" in data
        assert isinstance(data["family_members"], list)


class TestCorporateHierarchyStats:
    """Tests for GET /api/corporate/hierarchy/stats"""

    def test_returns_stats(self, client):
        r = client.get("/api/corporate/hierarchy/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_hierarchy_links" in data
        assert "by_source" in data
        assert "f7_families" in data
        assert "total_crosswalk_entries" in data


class TestCorporateHierarchySearch:
    """Tests for GET /api/corporate/hierarchy/search"""

    def test_no_params_returns_empty(self, client):
        r = client.get("/api/corporate/hierarchy/search")
        assert r.status_code == 200
        data = r.json()
        assert data["results"] == []
        assert data["total"] == 0

    def test_search_by_name(self, client):
        r = client.get("/api/corporate/hierarchy/search", params={"name": "apple"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "total" in data

    def test_search_by_ticker(self, client):
        r = client.get("/api/corporate/hierarchy/search", params={"ticker": "AAPL"})
        assert r.status_code == 200
        assert isinstance(r.json()["results"], list)


class TestCorporateHierarchy:
    """Tests for GET /api/corporate/hierarchy/{employer_id}"""

    def test_not_found(self, client):
        r = client.get("/api/corporate/hierarchy/nonexistent_id_999")
        assert r.status_code == 404

    def test_valid_employer(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No employers")

        r = client.get(f"/api/corporate/hierarchy/{row[0]}")
        assert r.status_code == 200
        data = r.json()
        assert "employer" in data
        assert "crosswalk" in data
        assert "parent_chain" in data
        assert "siblings" in data
        assert "subsidiaries" in data
        assert "family_union_status" in data


class TestSECCompany:
    """Tests for GET /api/corporate/sec/{cik}"""

    def test_not_found(self, client):
        r = client.get("/api/corporate/sec/999999999")
        assert r.status_code == 404

    def test_valid_cik(self, client):
        from db_config import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT cik FROM sec_companies LIMIT 1")
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            pytest.skip("No SEC companies")

        r = client.get(f"/api/corporate/sec/{row[0]}")
        assert r.status_code == 200
        data = r.json()
        assert "company" in data
        assert "f7_employers" in data
        assert "mergent_employers" in data
