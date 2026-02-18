import psycopg2


def test_scorecard_detail_bogus_id_returns_404(client):
    r = client.get("/api/scorecard/nonexistent_id_12345")
    assert r.status_code == 404


def test_corporate_family_bogus_id_returns_404(client):
    r = client.get("/api/corporate/family/nonexistent_id_12345")
    assert r.status_code == 404


def test_employer_agreement_bogus_id_returns_404(client):
    r = client.get("/api/employer/nonexistent_id_12345/agreement")
    assert r.status_code == 404


def test_employer_matches_bogus_id_returns_404(client):
    r = client.get("/api/employers/nonexistent_id_12345/matches")
    assert r.status_code == 404


def test_employer_detail_bogus_id_returns_404(client):
    r = client.get("/api/employers/nonexistent_id_12345")
    assert r.status_code == 404


def test_related_filings_bogus_id_returns_404(client):
    r = client.get("/api/employers/nonexistent_id_12345/related-filings")
    assert r.status_code == 404


def test_similar_employers_bogus_id_returns_404(client):
    r = client.get("/api/employers/nonexistent_id_12345/similar")
    assert r.status_code == 404


def test_invalid_page_size_returns_422(client):
    r = client.get("/api/scorecard/?page_size=not_a_number")
    assert r.status_code == 422


def test_db_connection_error_returns_503(client, monkeypatch):
    from api.routers import scorecard as scorecard_router

    class BrokenConnection:
        def __enter__(self):
            raise psycopg2.OperationalError("db unavailable")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(scorecard_router, "get_db", lambda: BrokenConnection())
    r = client.get("/api/scorecard/states")
    assert r.status_code == 503

