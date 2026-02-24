"""Tests for CBA (Collective Bargaining Agreement) router endpoints."""
import pytest


class TestCBAProvisionsSearch:
    """Tests for GET /api/cba/provisions/search"""

    def test_search_no_filters(self, client):
        r = client.get("/api/cba/provisions/search")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_with_text_query(self, client):
        r = client.get("/api/cba/provisions/search", params={"q": "wages"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["total"], int)

    def test_search_pagination(self, client):
        r = client.get("/api/cba/provisions/search", params={"page": 1, "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert len(data["results"]) <= 5

    def test_search_sort_options(self, client):
        for sort_col in ["page_start", "employer_name", "union_name", "provision_class"]:
            r = client.get("/api/cba/provisions/search", params={"sort": sort_col, "order": "asc", "limit": 3})
            assert r.status_code == 200, f"Sort by {sort_col} failed"

    def test_search_invalid_sort_returns_422(self, client):
        r = client.get("/api/cba/provisions/search", params={"sort": "invalid_col"})
        assert r.status_code == 422


class TestCBAProvisionClasses:
    """Tests for GET /api/cba/provisions/classes"""

    def test_list_classes(self, client):
        r = client.get("/api/cba/provisions/classes")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)


class TestCBADocumentDetail:
    """Tests for GET /api/cba/documents/{cba_id}"""

    def test_not_found(self, client):
        r = client.get("/api/cba/documents/999999999")
        assert r.status_code == 404

    def test_valid_document(self, client):
        """Find a real cba_id from the classes endpoint, then fetch its document."""
        search_r = client.get("/api/cba/provisions/search", params={"limit": 1})
        results = search_r.json().get("results", [])
        if not results:
            pytest.skip("No CBA provisions in database")

        cba_id = results[0]["cba_id"]
        r = client.get(f"/api/cba/documents/{cba_id}")
        assert r.status_code == 200
        data = r.json()
        assert "document" in data
        assert "summary" in data
        assert "class_counts" in data
        assert "provisions" in data
        assert data["document"]["cba_id"] == cba_id

    def test_exclude_provisions(self, client):
        search_r = client.get("/api/cba/provisions/search", params={"limit": 1})
        results = search_r.json().get("results", [])
        if not results:
            pytest.skip("No CBA provisions in database")

        cba_id = results[0]["cba_id"]
        r = client.get(f"/api/cba/documents/{cba_id}", params={"include_provisions": False})
        assert r.status_code == 200
        assert r.json()["provisions"] == []
