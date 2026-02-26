"""
Tests for the research-to-scorecard feedback loop.

Covers:
  - research_score_enhancements table existence and schema
  - compute_research_enhancements() quality gate, path detection, scoring
  - UPSERT logic (higher quality replaces, lower is skipped)
  - Unified scorecard MV research columns
  - API endpoints: scorecard has_research filter, research candidates
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection
from scripts.research.auto_grader import (
    _extract_numeric,
    compute_research_enhancements,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dossier(overrides=None):
    """Build a minimal but valid dossier_json dict."""
    base = {
        "dossier": {
            "identity": {
                "company_name": "Test Corp",
                "state": "NY",
                "naics_code": "561320",
                "year_founded": 1990,
                "employee_count": 250,
            },
            "financial": {
                "revenue": "5000000",
                "employee_count": 250,
                "federal_obligations": None,
            },
            "workforce": {},
            "labor": {
                "nlrb_election_count": 2,
                "nlrb_ulp_count": 3,
            },
            "workplace": {
                "osha_violation_count": 5,
                "osha_serious_count": 1,
                "osha_penalty_total": 12000,
                "whd_case_count": 2,
            },
            "assessment": {
                "recommended_approach": "Focus on safety issues as primary organizing leverage given repeat OSHA violations and worker dissatisfaction.",
                "campaign_strengths": ["repeat violations", "worker turnover", "wage gaps"],
                "campaign_challenges": ["anti-union management", "high surveillance"],
                "source_contradictions": [{"field": "employee_count", "db": 200, "web": 300}],
                "financial_trend": "Revenue growing 8% YoY",
            },
            "sources": {},
        }
    }
    if overrides:
        for section, updates in overrides.items():
            if section in base["dossier"]:
                base["dossier"][section].update(updates)
    return base


# ---------------------------------------------------------------------------
# Unit tests: _extract_numeric (already exists but coverage for _extract_int)
# ---------------------------------------------------------------------------

class TestExtractNumeric:
    def test_int(self):
        assert _extract_numeric(42) == 42.0

    def test_float(self):
        assert _extract_numeric(3.14) == 3.14

    def test_string_with_commas(self):
        assert _extract_numeric("1,234,567") == 1234567.0

    def test_none(self):
        assert _extract_numeric(None) is None

    def test_empty_string(self):
        assert _extract_numeric("") is None

    def test_string_with_suffix(self):
        assert _extract_numeric("500 employees") == 500.0


# ---------------------------------------------------------------------------
# Unit tests: compute_research_enhancements scoring logic (mocked DB)
# ---------------------------------------------------------------------------

class TestComputeEnhancementsScoring:
    """Test the scoring formulas in compute_research_enhancements."""

    def _mock_conn(self, employer_id="abc123", quality=8.5, dossier=None,
                   is_f7=False, avg_conf=0.85):
        """Build a mock connection that returns controlled data."""
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur

        dossier = dossier or _make_dossier()

        # First call: load run metadata
        run_row = {
            "id": 1,
            "employer_id": employer_id,
            "dossier_json": dossier,
            "overall_quality_score": quality,
        }
        # Second call: EXISTS check for f7
        exists_row = {"e": is_f7}
        # Third call: AVG confidence
        conf_row = {"avg_conf": avg_conf}
        # Fourth call: UPSERT RETURNING
        upsert_row = {"id": 99}

        cur.fetchone.side_effect = [run_row, exists_row, conf_row, upsert_row]

        return conn

    def test_quality_gate_rejects_low(self):
        conn = self._mock_conn(quality=5.0)
        result = compute_research_enhancements(1, conn=conn)
        assert result is None

    def test_quality_gate_rejects_no_employer_id(self):
        conn = self._mock_conn(employer_id=None)
        result = compute_research_enhancements(1, conn=conn)
        assert result is None

    def test_non_union_path(self):
        conn = self._mock_conn(is_f7=False)
        result = compute_research_enhancements(1, conn=conn)
        assert result == 99  # from UPSERT RETURNING

        # Verify the UPSERT was called
        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        assert len(upsert_call) == 1

        # Check is_union_reference=FALSE was passed
        upsert_args = upsert_call[0][0][1]  # second positional arg (params tuple)
        # is_union_reference is 4th param
        assert upsert_args[3] is False

    def test_union_reference_path(self):
        conn = self._mock_conn(is_f7=True)
        result = compute_research_enhancements(1, conn=conn)
        assert result == 99

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        upsert_args = upsert_call[0][0][1]
        assert upsert_args[3] is True  # is_union_reference=TRUE

    def test_osha_score_formula(self):
        """OSHA: violations / 2.23 industry avg, capped at 10."""
        dossier = _make_dossier({"workplace": {"osha_violation_count": 10, "osha_serious_count": 2}})
        conn = self._mock_conn(dossier=dossier)
        compute_research_enhancements(1, conn=conn)

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        params = upsert_call[0][0][1]
        # s_osha: min(10, 10/2.23 + 1) = min(10, 5.48) = 5.48... rounded
        s_osha = params[4]
        assert s_osha is not None
        assert 4.0 < s_osha <= 10.0

    def test_nlrb_score_formula(self):
        """NLRB: elections*2 + ULP boost."""
        dossier = _make_dossier({"labor": {"nlrb_election_count": 3, "nlrb_ulp_count": 5}})
        conn = self._mock_conn(dossier=dossier)
        compute_research_enhancements(1, conn=conn)

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        params = upsert_call[0][0][1]
        s_nlrb = params[5]  # 3*2 + 6 (ulp 4-9 boost) = 12, capped at 10
        assert s_nlrb == 10.0

    def test_whd_score_tiers(self):
        """WHD: case count tiers (1->5, 2-3->7, 4+->10)."""
        for cases, expected in [(1, 5.0), (3, 7.0), (5, 10.0)]:
            dossier = _make_dossier({"workplace": {
                "whd_case_count": cases,
                "osha_violation_count": 0,
                "osha_serious_count": 0,
            }})
            conn = self._mock_conn(dossier=dossier)
            compute_research_enhancements(1, conn=conn)

            calls = conn.cursor.return_value.execute.call_args_list
            upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
            params = upsert_call[0][0][1]
            s_whd = params[6]
            assert s_whd == expected, f"whd_cases={cases}: expected {expected}, got {s_whd}"

    def test_contracts_score_tiers(self):
        """Contracts: obligation tiers."""
        for amt, expected in [
            (50_000, 2.0),
            (500_000, 4.0),
            (5_000_000, 6.0),
            (50_000_000, 8.0),
            (200_000_000, 10.0),
        ]:
            dossier = _make_dossier({"financial": {"federal_obligations": amt}})
            conn = self._mock_conn(dossier=dossier)
            compute_research_enhancements(1, conn=conn)

            calls = conn.cursor.return_value.execute.call_args_list
            upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
            params = upsert_call[0][0][1]
            s_contracts = params[7]
            assert s_contracts == expected, f"obligations={amt}: expected {expected}, got {s_contracts}"

    def test_size_sweet_spot(self):
        """Size: linear scale 15-500, 0 below 15, 10 at 500+."""
        dossier = _make_dossier({"identity": {"employee_count": 250}})
        conn = self._mock_conn(dossier=dossier)
        compute_research_enhancements(1, conn=conn)

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        params = upsert_call[0][0][1]
        s_size = params[9]
        # (250 - 15) / 485 * 10 = 4.85
        assert 4.0 < s_size < 5.5

    def test_no_score_when_zero(self):
        """Don't set score factors when research found 0 (not missing data)."""
        dossier = _make_dossier({
            "workplace": {"osha_violation_count": 0, "osha_serious_count": 0, "whd_case_count": 0},
            "labor": {"nlrb_election_count": 0, "nlrb_ulp_count": 0},
            "financial": {"revenue": None, "federal_obligations": None},
        })
        conn = self._mock_conn(dossier=dossier)
        compute_research_enhancements(1, conn=conn)

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        params = upsert_call[0][0][1]
        # All factor scores should be None (don't override DB with "not found")
        s_osha, s_nlrb, s_whd, s_contracts, s_financial = params[4:9]
        assert s_osha is None
        assert s_nlrb is None
        assert s_whd is None
        assert s_contracts is None
        assert s_financial is None

    def test_assessment_fields_extracted(self):
        """Assessment fields (approach, strengths, etc.) are extracted."""
        conn = self._mock_conn()
        compute_research_enhancements(1, conn=conn)

        calls = conn.cursor.return_value.execute.call_args_list
        upsert_call = [c for c in calls if "INSERT INTO research_score_enhancements" in str(c)]
        params = upsert_call[0][0][1]
        # recommended_approach is at index 21
        rec_approach = params[21]
        assert rec_approach is not None
        assert "safety" in rec_approach.lower()

    def test_upsert_skips_lower_quality(self):
        """UPSERT WHERE clause: skip if new run has lower quality."""
        conn = self._mock_conn(quality=8.0)
        # Simulate RETURNING returning None (no row updated)
        conn.cursor.return_value.fetchone.side_effect = [
            {"id": 1, "employer_id": "abc", "dossier_json": _make_dossier(),
             "overall_quality_score": 8.0},
            {"e": False},
            {"avg_conf": 0.8},
            None,  # UPSERT returned no row
        ]
        result = compute_research_enhancements(1, conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: table existence and MV columns (require real DB)
# ---------------------------------------------------------------------------

class TestResearchEnhancementsTable:
    """Verify research_score_enhancements table exists with expected schema."""

    def test_table_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'research_score_enhancements'
                    ) AS e
                """)
                assert cur.fetchone()[0], "Table research_score_enhancements does not exist"
        finally:
            conn.close()

    def test_has_required_columns(self):
        required = {
            "id", "employer_id", "run_id", "run_quality", "is_union_reference",
            "score_osha", "score_nlrb", "score_whd", "score_contracts",
            "score_financial", "score_size",
            "osha_violations_found", "nlrb_elections_found", "whd_cases_found",
            "employee_count_found", "revenue_found", "naics_found",
            "recommended_approach", "campaign_strengths", "campaign_challenges",
            "source_contradictions", "financial_trend",
            "confidence_avg", "created_at", "updated_at",
        }
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'research_score_enhancements'
                """)
                actual = {r[0] for r in cur.fetchall()}
                for col in required:
                    assert col in actual, f"Missing column: {col}"
        finally:
            conn.close()

    def test_unique_constraint_on_employer_id(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE tablename = 'research_score_enhancements'
                      AND indexdef LIKE '%%UNIQUE%%employer_id%%'
                """)
                assert cur.fetchone()[0] >= 1, "No UNIQUE constraint on employer_id"
        finally:
            conn.close()


class TestUnifiedScorecardResearchColumns:
    """Verify the MV has the new research columns."""

    def test_mv_has_research_columns(self):
        required = {
            "has_research", "research_run_id", "research_weighted_score",
            "research_quality", "score_delta",
            "research_approach", "research_trend", "research_contradictions",
        }
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = 'mv_unified_scorecard'::regclass
                      AND attnum > 0 AND NOT attisdropped
                """)
                actual = {r[0] for r in cur.fetchall()}
                for col in required:
                    assert col in actual, f"Missing MV column: {col}"
        finally:
            conn.close()

    def test_has_research_index_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE tablename = 'mv_unified_scorecard'
                      AND indexname = 'idx_mv_us_has_research'
                """)
                assert cur.fetchone()[0] == 1, "Missing has_research index"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# API tests (require running test client)
# ---------------------------------------------------------------------------

class TestScorecardAPIResearch:
    """Test scorecard API endpoints include research fields."""

    def test_unified_list_has_research_filter(self, client):
        r = client.get("/api/scorecard/unified?has_research=false&page_size=5")
        assert r.status_code == 200
        data = r.json()
        assert "data" in data

    def test_unified_list_sort_by_delta(self, client):
        r = client.get("/api/scorecard/unified?sort=score_delta&page_size=5")
        assert r.status_code == 200

    def test_unified_stats_has_research_coverage(self, client):
        r = client.get("/api/scorecard/unified/stats")
        assert r.status_code == 200
        data = r.json()
        assert "research_coverage" in data
        rc = data["research_coverage"]
        assert "researched" in rc

    def test_unified_detail_has_research_fields(self, client):
        # Get any employer to test detail
        r = client.get("/api/scorecard/unified?page_size=1")
        assert r.status_code == 200
        rows = r.json().get("data", [])
        if not rows:
            pytest.skip("No employers in unified scorecard")
        eid = rows[0]["employer_id"]
        r2 = client.get(f"/api/scorecard/unified/{eid}")
        assert r2.status_code == 200
        detail = r2.json()
        assert "has_research" in detail


class TestResearchCandidatesAPI:
    """Test GET /api/research/candidates endpoint."""

    def test_non_union_candidates(self, client):
        r = client.get("/api/research/candidates?type=non_union&limit=10")
        assert r.status_code == 200
        data = r.json()
        assert "candidates" in data
        assert data["type"] == "non_union"
        for c in data["candidates"]:
            assert "employer_id" in c
            assert "research_priority" in c

    def test_union_reference_candidates(self, client):
        r = client.get("/api/research/candidates?type=union_reference&limit=10")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "union_reference"

    def test_default_is_non_union(self, client):
        r = client.get("/api/research/candidates?limit=5")
        assert r.status_code == 200
        assert r.json()["type"] == "non_union"

    def test_invalid_type_rejected(self, client):
        r = client.get("/api/research/candidates?type=invalid")
        assert r.status_code == 422  # FastAPI validation error
