"""
Tests for mv_unified_scorecard materialized view and API endpoints.

Validates:
- MV row count matches f7_employers_deduped
- Weighted scoring columns and compatibility aliases
- Factor ranges are 0-10
- Score tiers are reasonable
- API endpoints return correct format and support filters
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection


# ── MV Schema Tests ──────────────────────────────────────────────────────

class TestUnifiedScorecardSchema:
    """Verify MV exists and has expected structure."""

    def test_mv_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_matviews
                    WHERE matviewname = 'mv_unified_scorecard'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_has_required_columns(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                required = [
                    'employer_id', 'employer_name', 'state', 'city', 'naics',
                    'score_osha', 'score_nlrb', 'score_whd', 'score_contracts',
                    'score_union_proximity', 'score_financial', 'score_size', 'score_similarity',
                    'factors_available', 'factors_total',
                    'total_weight', 'weighted_score', 'unified_score', 'coverage_pct', 'score_tier',
                    'osha_estab_count', 'nlrb_election_count',
                    'whd_case_count', 'bls_growth_pct',
                ]
                cur.execute("""
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = 'mv_unified_scorecard'::regclass
                      AND attnum > 0 AND NOT attisdropped
                """)
                actual_cols = {r[0] for r in cur.fetchall()}
                for col in required:
                    assert col in actual_cols, f"Missing column: {col}"
        finally:
            conn.close()

    def test_unique_index_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE tablename = 'mv_unified_scorecard'
                      AND indexname = 'idx_mv_us_employer_id'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()


# ── MV Data Integrity Tests ──────────────────────────────────────────────

class TestUnifiedScorecardData:
    """Verify data correctness."""

    def test_row_count_matches_f7(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
                mv_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
                f7_count = cur.fetchone()[0]
                assert mv_count == f7_count
        finally:
            conn.close()

    def test_factor_scores_in_range(self):
        """All factor scores must be 0-10 or NULL."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for col in ['score_osha', 'score_nlrb', 'score_whd',
                            'score_contracts', 'score_union_proximity',
                            'score_financial', 'score_size', 'score_similarity']:
                    cur.execute(f"""
                        SELECT COUNT(*) FROM mv_unified_scorecard
                        WHERE {col} IS NOT NULL AND ({col} < 0 OR {col} > 10)
                    """)
                    bad = cur.fetchone()[0]
                    assert bad == 0, f"{col}: {bad} values outside 0-10 range"
        finally:
            conn.close()

    def test_weighted_score_alias_consistency(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM mv_unified_scorecard
                    WHERE ABS(COALESCE(weighted_score, 0) - COALESCE(unified_score, 0)) > 0.001
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} rows have weighted/unified score mismatch"
        finally:
            conn.close()

    def test_osha_score_null_when_no_osha(self):
        """Employers without OSHA data should have NULL score_osha."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE NOT has_osha AND score_osha IS NOT NULL
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} non-OSHA employers have OSHA scores"
        finally:
            conn.close()

    def test_nlrb_score_null_when_no_nlrb(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE NOT has_nlrb AND score_nlrb IS NOT NULL
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} non-NLRB employers have NLRB scores"
        finally:
            conn.close()

    def test_whd_score_null_when_no_whd(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE NOT has_whd AND score_whd IS NOT NULL
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} non-WHD employers have WHD scores"
        finally:
            conn.close()

    def test_unified_score_in_range(self):
        """Unified score should be 0-10."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MIN(weighted_score), MAX(weighted_score)
                    FROM mv_unified_scorecard
                """)
                mn, mx = cur.fetchone()
                assert mn >= 0, f"Min unified_score is {mn}"
                assert mx <= 10, f"Max unified_score is {mx}"
        finally:
            conn.close()

    def test_factors_available_range(self):
        """factors_available should be 0-factors_total."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MIN(factors_available), MAX(factors_available), MAX(factors_total) FROM mv_unified_scorecard")
                mn, mx, ft = cur.fetchone()
                assert mn >= 0, f"Min factors_available is {mn}"
                assert mx <= ft, f"Max factors_available ({mx}) exceeds factors_total ({ft})"
        finally:
            conn.close()

    def test_coverage_pct_consistent(self):
        """coverage_pct should equal factors_available/factors_total * 100."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE ABS(coverage_pct - (factors_available::numeric / factors_total * 100)) > 0.2
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} rows have inconsistent coverage_pct"
        finally:
            conn.close()

    def test_score_tier_values(self):
        """score_tier should be one of Priority/Strong/Promising/Moderate/Low."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE score_tier NOT IN ('Priority', 'Strong', 'Promising', 'Moderate', 'Low')
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} rows have invalid score_tier"
        finally:
            conn.close()

    def test_has_top_tier_employers(self):
        """Should have some priority-tier employers."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_tier = 'Priority'")
                top = cur.fetchone()[0]
                assert top > 0, "No Priority tier employers"
        finally:
            conn.close()

    def test_some_employers_have_financial_factor(self):
        """Some employers should have financial factor (990 revenue data)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_financial IS NOT NULL")
                cnt = cur.fetchone()[0]
                assert cnt > 5000, f"Only {cnt} have financial factor (expected >5000 from 990 data)"
        finally:
            conn.close()

    def test_greatest_null_behavior(self):
        """Regression: PostgreSQL GREATEST(NULL, 5) must return 5."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT GREATEST(NULL, 5), GREATEST(NULL, NULL), GREATEST(3, 5)")
                row = cur.fetchone()
                assert row[0] == 5
                assert row[1] is None
                assert row[2] == 5
        finally:
            conn.close()

    def test_anger_null_when_no_subfactors(self):
        """Anger pillar should be NULL when no OSHA, WHD, or ULP data."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE score_anger IS NOT NULL
                      AND enh_score_osha IS NULL
                      AND enh_score_whd IS NULL
                      AND nlrb_ulp_count = 0
                      AND rse_score_anger IS NULL
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} employers have anger score without any anger sub-factors"
        finally:
            conn.close()

    def test_stability_no_fake_baseline(self):
        """Stability should be NULL (not 5.0) when no turnover/wage data."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_unified_scorecard
                    WHERE score_stability = 5.0
                      AND turnover_rate_found IS NULL
                      AND wage_outlier_score IS NULL
                      AND rse_score_stability IS NULL
                """)
                fake = cur.fetchone()[0]
                assert fake == 0, f"{fake} employers still have fake 5.0 stability baseline"
        finally:
            conn.close()


# ── API Tests ────────────────────────────────────────────────────────────

class TestUnifiedScorecardAPI:
    """Verify API endpoints return correct format."""

    def test_unified_list_returns_data(self, client):
        r = client.get("/api/scorecard/unified?page_size=5")
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert "total" in data
        assert "has_more" in data
        assert data["total"] > 100000
        assert len(data["data"]) == 5

    def test_unified_list_has_score_fields(self, client):
        r = client.get("/api/scorecard/unified?page_size=1")
        item = r.json()["data"][0]
        for field in ['unified_score', 'coverage_pct', 'score_tier',
                      'factors_available', 'factors_total',
                      'score_union_proximity', 'score_size', 'score_similarity', 'weighted_score', 'total_weight']:
            assert field in item, f"Missing field: {field}"

    def test_unified_list_state_filter(self, client):
        r = client.get("/api/scorecard/unified?state=CA&page_size=3")
        assert r.status_code == 200
        data = r.json()
        for item in data["data"]:
            assert item["state"] == "CA"

    def test_unified_list_min_score_filter(self, client):
        r = client.get("/api/scorecard/unified?min_score=7&page_size=5")
        assert r.status_code == 200
        data = r.json()
        for item in data["data"]:
            assert item["weighted_score"] >= 7.0

    def test_unified_list_tier_filter(self, client):
        r = client.get("/api/scorecard/unified?score_tier=TOP&page_size=5")
        assert r.status_code == 200
        for item in r.json()["data"]:
            assert item["legacy_score_tier"] == "TOP"

    def test_unified_list_sort_by_size(self, client):
        r = client.get("/api/scorecard/unified?sort=size&page_size=5")
        assert r.status_code == 200
        sizes = [i["latest_unit_size"] for i in r.json()["data"] if i["latest_unit_size"]]
        assert sizes == sorted(sizes, reverse=True)

    def test_unified_stats_endpoint(self, client):
        r = client.get("/api/scorecard/unified/stats")
        assert r.status_code == 200
        data = r.json()
        assert "overview" in data
        assert "tier_distribution" in data
        assert "factor_coverage" in data
        assert data["overview"]["total_employers"] > 100000

    def test_unified_states_endpoint(self, client):
        r = client.get("/api/scorecard/unified/states")
        assert r.status_code == 200
        states = r.json()
        assert len(states) > 40  # at least 40+ states

    def test_unified_detail_found(self, client):
        # Get a known employer
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT employer_id FROM mv_unified_scorecard WHERE score_tier = 'Priority' LIMIT 1")
                eid = cur.fetchone()[0]
        finally:
            conn.close()

        r = client.get(f"/api/scorecard/unified/{eid}")
        assert r.status_code == 200
        data = r.json()
        assert data["employer_id"] == eid
        assert "unified_score" in data
        assert "explanations" in data
        assert "union_proximity" in data["explanations"]
        assert "size" in data["explanations"]

    def test_unified_detail_not_found(self, client):
        r = client.get("/api/scorecard/unified/nonexistent_id_12345")
        assert r.status_code == 404

    def test_unified_endpoints_registered(self):
        import importlib
        from api.routers import scorecard
        importlib.reload(scorecard)
        routes = [r.path for r in scorecard.router.routes]
        assert "/api/scorecard/unified" in routes
        assert "/api/scorecard/unified/stats" in routes
        assert "/api/scorecard/unified/states" in routes
        assert "/api/scorecard/unified/{employer_id}" in routes
