"""
Tests for fact review API endpoints (Phase R1).

POST /api/research/facts/{fact_id}/review
GET  /api/research/runs/{run_id}/review-summary
PATCH /api/research/runs/{run_id}/human-score
GET  /api/research/result/{run_id} (review fields)
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: mock DB rows
# ---------------------------------------------------------------------------

def _mock_fact_row(fact_id=1, run_id=1, human_verdict=None, human_notes=None):
    return {"id": fact_id, "run_id": run_id, "human_verdict": human_verdict, "human_notes": human_notes}


def _mock_run_row(run_id=1, status="completed", **extras):
    base = {
        "id": run_id, "company_name": "TestCo", "company_address": None,
        "employer_id": "abc123", "industry_naics": "31", "company_type": "private",
        "status": status, "current_step": "Done", "progress_pct": 100,
        "started_at": None, "completed_at": None, "duration_seconds": 10,
        "total_tools_called": 5, "total_facts_found": 3, "sections_filled": 2,
        "total_cost_cents": 0, "overall_quality_score": 7.5,
        "quality_dimensions": {"coverage": 8.0}, "dossier_json": '{"dossier":{}}',
        "human_quality_score": None, "created_at": None, "updated_at": None,
        "company_state": None, "employee_size_bucket": "medium",
    }
    base.update(extras)
    return base


class _FakeCursor:
    """Minimal cursor mock that supports fetchone/fetchall with scripted returns."""
    def __init__(self, results=None):
        self._results = list(results or [])
        self._idx = 0
        self.rowcount = 0

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        if self._idx < len(self._results):
            row = self._results[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        rows = self._results[self._idx:]
        self._idx = len(self._results)
        return rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReviewFactEndpoint:
    """POST /api/research/facts/{fact_id}/review"""

    def test_review_fact_confirmed(self, client):
        fake_cur = _FakeCursor([{"id": 1}])  # fact exists
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            with patch("scripts.research.auto_grader.apply_human_fact_review"):
                resp = client.post("/api/research/facts/1/review",
                                   json={"verdict": "confirmed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "confirmed"
        assert data["fact_id"] == 1

    def test_review_fact_rejected(self, client):
        fake_cur = _FakeCursor([{"id": 1}])
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            with patch("scripts.research.auto_grader.apply_human_fact_review"):
                resp = client.post("/api/research/facts/1/review",
                                   json={"verdict": "rejected", "notes": "Wrong number"})
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "rejected"

    def test_review_fact_irrelevant(self, client):
        fake_cur = _FakeCursor([{"id": 1}])
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            with patch("scripts.research.auto_grader.apply_human_fact_review"):
                resp = client.post("/api/research/facts/1/review",
                                   json={"verdict": "irrelevant"})
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "irrelevant"

    def test_review_fact_not_found(self, client):
        fake_cur = _FakeCursor([None])  # fetchone returns None
        fake_cur.fetchone = lambda: None
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            resp = client.post("/api/research/facts/9999/review",
                               json={"verdict": "confirmed"})
        assert resp.status_code == 404

    def test_review_fact_invalid_verdict(self, client):
        """Invalid verdict value should return 422."""
        resp = client.post("/api/research/facts/1/review",
                           json={"verdict": "maybe"})
        assert resp.status_code == 422


class TestReviewSummary:
    """GET /api/research/runs/{run_id}/review-summary"""

    def test_review_summary_counts(self, client):
        results = [
            {"id": 1},  # run exists
            {"total_facts": 10, "reviewed": 4, "unreviewed": 6,
             "confirmed": 2, "rejected": 1, "irrelevant": 1},
        ]
        fake_cur = _FakeCursor(results)
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            resp = client.get("/api/research/runs/1/review-summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == 1
        assert data["total_facts"] == 10
        assert data["confirmed"] == 2
        assert data["rejected"] == 1
        assert data["irrelevant"] == 1
        assert data["reviewed"] == 4
        assert data["unreviewed"] == 6


class TestHumanScore:
    """PATCH /api/research/runs/{run_id}/human-score"""

    def test_human_score_set(self, client):
        results = [{"id": 1}]  # run exists
        fake_cur = _FakeCursor(results)
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            resp = client.patch("/api/research/runs/1/human-score",
                                json={"human_quality_score": 8.5})

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == 1
        assert data["human_quality_score"] == 8.5

    def test_human_score_out_of_range(self, client):
        results = [{"id": 1}]
        fake_cur = _FakeCursor(results)
        fake_conn = _FakeConn(fake_cur)

        with patch("api.routers.research.get_db", return_value=fake_conn):
            resp = client.patch("/api/research/runs/1/human-score",
                                json={"human_quality_score": 15.0})

        assert resp.status_code == 422


class TestResultIncludesReviewFields:
    """GET /api/research/result/{run_id} should include fact_id and human_verdict."""

    def test_result_includes_review_fields(self, client):
        run = _mock_run_row()
        facts = [
            {"fact_id": 42, "dossier_section": "identity", "attribute_name": "legal_name",
             "attribute_value": "TestCo", "attribute_value_json": None,
             "source_type": "database", "source_name": "f7", "source_url": None,
             "confidence": 0.9, "as_of_date": None, "contradicts_fact_id": None,
             "human_verdict": "confirmed", "human_notes": "Looks good",
             "reviewed_at": "2026-03-01T00:00:00", "display_name": "Legal Name",
             "data_type": "string"},
        ]
        actions = []

        fake_cur = MagicMock()
        call_count = [0]

        def fake_fetchone():
            call_count[0] += 1
            if call_count[0] == 1:
                return run
            return None

        def fake_fetchall():
            call_count[0] += 1
            if call_count[0] == 2:
                return facts
            return actions

        fake_cur.fetchone = fake_fetchone
        fake_cur.fetchall = fake_fetchall
        fake_cur.__enter__ = lambda s: s
        fake_cur.__exit__ = lambda s, *a: None

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        fake_conn.__enter__ = lambda s: s
        fake_conn.__exit__ = lambda s, *a: None

        with patch("api.routers.research.get_db", return_value=fake_conn):
            resp = client.get("/api/research/result/1")

        assert resp.status_code == 200
        data = resp.json()
        identity_facts = data["facts_by_section"].get("identity", [])
        assert len(identity_facts) == 1
        f = identity_facts[0]
        assert f["fact_id"] == 42
        assert f["human_verdict"] == "confirmed"
