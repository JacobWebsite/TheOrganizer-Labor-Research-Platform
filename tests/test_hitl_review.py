"""
Tests for Phase R2: Improved Human-in-the-Loop Review UX.

Covers:
  Feature 1: Run-level usefulness (PATCH /runs/{id}/usefulness)
  Feature 2: Flag-only fact review (POST /facts/{id}/flag)
  Feature 2: Auto-confirm unflagged facts (POST /maintenance/auto-confirm)
  Feature 3: Comparative review (GET/POST /runs/compare)
  Feature 4: Section-level review (POST /runs/{id}/sections/{section}/review)
  Feature 5: Priority facts (GET /runs/{id}/priority-facts)
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

# Prevent real scraper calls
os.environ.setdefault("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "false")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers — mock DB context manager
# ---------------------------------------------------------------------------
def _make_cursor(fetchone_val=None, fetchall_val=None, rowcount=0):
    """Build a mock cursor that returns specified values."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_val
    cur.fetchall.return_value = fetchall_val or []
    cur.rowcount = rowcount
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def _make_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# Feature 1: Run-level usefulness
# ---------------------------------------------------------------------------
class TestRunUsefulness:
    @patch("api.routers.research.get_db")
    def test_set_useful_true(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1, "status": "completed"})
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_run_usefulness", create=True):
            resp = client.patch(
                "/api/research/runs/1/usefulness",
                json={"useful": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["useful"] is True
        assert data["run_id"] == 1

    @patch("api.routers.research.get_db")
    def test_set_useful_false(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1, "status": "completed"})
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_run_usefulness", create=True):
            resp = client.patch(
                "/api/research/runs/1/usefulness",
                json={"useful": False},
            )

        assert resp.status_code == 200
        assert resp.json()["useful"] is False

    @patch("api.routers.research.get_db")
    def test_usefulness_run_not_found(self, mock_get_db):
        cur = _make_cursor(fetchone_val=None)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.patch(
            "/api/research/runs/999/usefulness",
            json={"useful": True},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature 2: Flag fact
# ---------------------------------------------------------------------------
class TestFlagFact:
    @patch("api.routers.research.get_db")
    def test_flag_fact(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1})
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_human_fact_review", create=True):
            resp = client.post("/api/research/facts/1/flag")

        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "rejected"
        assert data["review_source"] == "flag"

    @patch("api.routers.research.get_db")
    def test_flag_fact_not_found(self, mock_get_db):
        cur = _make_cursor(fetchone_val=None)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.post("/api/research/facts/999/flag")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature 2: Auto-confirm unflagged facts
# ---------------------------------------------------------------------------
class TestAutoConfirm:
    @patch("api.routers.research.get_db")
    def test_auto_confirm_after_usefulness(self, mock_get_db):
        cur = _make_cursor(
            fetchone_val={"id": 1, "run_usefulness": True},
            rowcount=10,
        )
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_bulk_fact_reviews", create=True):
            resp = client.post("/api/research/maintenance/auto-confirm?run_id=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["facts_confirmed"] == 10

    @patch("api.routers.research.get_db")
    def test_auto_confirm_before_usefulness_rejected(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1, "run_usefulness": None})
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.post("/api/research/maintenance/auto-confirm?run_id=1")
        assert resp.status_code == 400

    @patch("api.routers.research.get_db")
    def test_auto_confirm_run_not_found(self, mock_get_db):
        cur = _make_cursor(fetchone_val=None)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.post("/api/research/maintenance/auto-confirm?run_id=999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature 3: Comparative review
# ---------------------------------------------------------------------------
class TestComparativeReview:
    @patch("api.routers.research.get_db")
    def test_compare_runs_get(self, mock_get_db):
        """GET /runs/compare returns both runs' data."""
        # fetchone called multiple times: run_a, run_b, existing comparison
        run_a = {
            "id": 1, "company_name": "Acme", "status": "completed",
            "overall_quality_score": 7.5, "quality_dimensions": {"coverage": 8.0},
            "total_facts_found": 30, "sections_filled": 5,
            "duration_seconds": 120, "completed_at": "2026-01-01", "run_usefulness": True,
        }
        run_b = {
            "id": 2, "company_name": "Acme", "status": "completed",
            "overall_quality_score": 6.0, "quality_dimensions": {"coverage": 5.0},
            "total_facts_found": 20, "sections_filled": 4,
            "duration_seconds": 90, "completed_at": "2026-01-02", "run_usefulness": None,
        }

        call_count = {"n": 0}
        fetchone_returns = [run_a, run_b, None]  # run_a, run_b, no existing comparison

        def side_effect_fetchone():
            idx = call_count["n"]
            call_count["n"] += 1
            if idx < len(fetchone_returns):
                return fetchone_returns[idx]
            return None

        fetchall_sections = [
            [{"dossier_section": "identity", "fact_count": 10, "reviewed_count": 5}],
            [{"dossier_section": "identity", "fact_count": 8, "reviewed_count": 0}],
        ]

        fetchall_count = {"n": 0}

        def side_effect_fetchall():
            idx = fetchall_count["n"]
            fetchall_count["n"] += 1
            if idx < len(fetchall_sections):
                return fetchall_sections[idx]
            return []

        cur = MagicMock()
        cur.fetchone.side_effect = side_effect_fetchone
        cur.fetchall.side_effect = side_effect_fetchall
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.get("/api/research/runs/compare?run_a=1&run_b=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "run_a" in data
        assert "run_b" in data
        assert data["run_a"]["id"] == 1
        assert data["run_b"]["id"] == 2

    @patch("api.routers.research.get_db")
    def test_submit_comparison(self, mock_get_db):
        """POST /runs/compare saves the winner."""
        call_count = {"n": 0}

        def side_effect_fetchone():
            idx = call_count["n"]
            call_count["n"] += 1
            if idx < 2:
                return {"id": idx + 1}  # both runs exist
            return {"id": 1}  # RETURNING id

        cur = MagicMock()
        cur.fetchone.side_effect = side_effect_fetchone
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_comparison_verdict", create=True):
            resp = client.post(
                "/api/research/runs/compare",
                json={
                    "run_id_a": 1,
                    "run_id_b": 2,
                    "winner_run_id": 1,
                    "notes": "Better coverage",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["winner_run_id"] == 1

    def test_submit_comparison_invalid_winner(self):
        """winner_run_id must be one of run_id_a or run_id_b."""
        resp = client.post(
            "/api/research/runs/compare",
            json={
                "run_id_a": 1,
                "run_id_b": 2,
                "winner_run_id": 99,
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Feature 4: Section-level review
# ---------------------------------------------------------------------------
class TestSectionReview:
    @patch("api.routers.research.get_db")
    def test_approve_section(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1}, rowcount=8)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_bulk_fact_reviews", create=True):
            resp = client.post(
                "/api/research/runs/1/sections/identity/review",
                json={"verdict": "confirmed"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["section"] == "identity"
        assert data["facts_updated"] == 8
        assert data["verdict"] == "confirmed"

    @patch("api.routers.research.get_db")
    def test_reject_section(self, mock_get_db):
        cur = _make_cursor(fetchone_val={"id": 1}, rowcount=5)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        with patch("api.routers.research.apply_bulk_fact_reviews", create=True):
            resp = client.post(
                "/api/research/runs/1/sections/labor/review",
                json={"verdict": "rejected", "notes": "Outdated info"},
            )

        assert resp.status_code == 200
        assert resp.json()["verdict"] == "rejected"

    def test_invalid_section(self):
        resp = client.post(
            "/api/research/runs/1/sections/invalid_section/review",
            json={"verdict": "confirmed"},
        )
        assert resp.status_code == 400

    @patch("api.routers.research.get_db")
    def test_section_review_run_not_found(self, mock_get_db):
        cur = _make_cursor(fetchone_val=None)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.post(
            "/api/research/runs/999/sections/identity/review",
            json={"verdict": "confirmed"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature 5: Priority facts
# ---------------------------------------------------------------------------
class TestPriorityFacts:
    @patch("api.routers.research.get_db")
    def test_get_priority_facts(self, mock_get_db):
        priority_facts = [
            {
                "fact_id": 1, "dossier_section": "identity",
                "attribute_name": "employee_count", "attribute_value": "500",
                "attribute_value_json": None, "source_type": "web_search",
                "source_name": "Google", "confidence": 0.3,
                "contradicts_fact_id": None, "human_verdict": None,
                "display_name": "Employee Count", "tool_quality": 3.5,
                "priority_rank": 2, "reason": "low_confidence",
            },
            {
                "fact_id": 2, "dossier_section": "labor",
                "attribute_name": "nlrb_election_count", "attribute_value": "2",
                "attribute_value_json": None, "source_type": "web_scrape",
                "source_name": "NLRB", "confidence": 0.8,
                "contradicts_fact_id": 5, "human_verdict": None,
                "display_name": "NLRB Elections", "tool_quality": 5.0,
                "priority_rank": 1, "reason": "contradicted",
            },
        ]

        call_count = {"n": 0}

        def side_effect_fetchone():
            idx = call_count["n"]
            call_count["n"] += 1
            if idx == 0:
                return {"id": 1}  # run exists
            return None

        cur = MagicMock()
        cur.fetchone.side_effect = side_effect_fetchone
        cur.fetchall.return_value = priority_facts
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.get("/api/research/runs/1/priority-facts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["priority_facts"]) == 2

    @patch("api.routers.research.get_db")
    def test_priority_facts_run_not_found(self, mock_get_db):
        cur = _make_cursor(fetchone_val=None)
        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.get("/api/research/runs/999/priority-facts")
        assert resp.status_code == 404

    @patch("api.routers.research.get_db")
    def test_priority_facts_custom_limit(self, mock_get_db):
        cur = MagicMock()
        cur.fetchone.return_value = {"id": 1}
        cur.fetchall.return_value = []
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = _make_conn(cur)
        mock_get_db.return_value = conn

        resp = client.get("/api/research/runs/1/priority-facts?limit=10")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
