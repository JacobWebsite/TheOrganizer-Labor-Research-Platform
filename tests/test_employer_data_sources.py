"""
Tests for mv_employer_data_sources materialized view and API endpoints.

Validates:
- MV row count matches f7_employers_deduped
- Source flags match known match counts from underlying tables
- Employers with zero matches have source_count=0
- API endpoints return correct format
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection


# ── MV Schema Tests ──────────────────────────────────────────────────────

class TestMVSchema:
    """Verify MV exists and has expected structure."""

    def test_mv_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM pg_matviews
                    WHERE matviewname = 'mv_employer_data_sources'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_has_required_columns(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                required = [
                    'employer_id', 'employer_name', 'state', 'city',
                    'naics', 'naics_detailed', 'latest_unit_size',
                    'latest_union_fnum', 'latest_union_name',
                    'is_historical', 'canonical_group_id', 'is_canonical_rep',
                    'has_osha', 'has_nlrb', 'has_whd', 'has_990',
                    'has_sam', 'has_sec', 'has_gleif', 'has_mergent',
                    'source_count',
                    'corporate_family_id', 'sec_cik', 'gleif_lei',
                    'mergent_duns', 'ein', 'ticker', 'is_public',
                    'is_federal_contractor', 'federal_obligations',
                    'federal_contract_count',
                ]
                # pg_attribute for materialized views (not in information_schema)
                cur.execute("""
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = 'mv_employer_data_sources'::regclass
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
                    WHERE tablename = 'mv_employer_data_sources'
                      AND indexname = 'idx_mv_eds_employer_id'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()


# ── MV Data Integrity Tests ──────────────────────────────────────────────

class TestMVDataIntegrity:
    """Verify data correctness."""

    def test_row_count_matches_f7(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources")
                mv_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
                f7_count = cur.fetchone()[0]
                assert mv_count == f7_count, (
                    f"MV has {mv_count} rows but f7_employers_deduped has {f7_count}"
                )
        finally:
            conn.close()

    def test_osha_count_matches_legacy_table(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE has_osha")
                mv_osha = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches")
                legacy = cur.fetchone()[0]
                assert mv_osha == legacy, (
                    f"MV has_osha={mv_osha} but osha_f7_matches has {legacy} unique employers"
                )
        finally:
            conn.close()

    def test_whd_count_matches_legacy_table(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE has_whd")
                mv_whd = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM whd_f7_matches")
                legacy = cur.fetchone()[0]
                assert mv_whd == legacy, (
                    f"MV has_whd={mv_whd} but whd_f7_matches has {legacy} unique employers"
                )
        finally:
            conn.close()

    def test_nlrb_count_matches_unified(self):
        """NLRB count may differ by a few if unified_match_log has orphan target_ids."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE has_nlrb")
                mv_nlrb = cur.fetchone()[0]
                cur.execute("""
                    SELECT COUNT(DISTINCT target_id) FROM unified_match_log
                    WHERE source_system = 'nlrb' AND status = 'active'
                """)
                uml = cur.fetchone()[0]
                # Allow small tolerance for orphan target_ids not in f7_employers_deduped
                assert abs(mv_nlrb - uml) <= 5, (
                    f"MV has_nlrb={mv_nlrb} vs unified_match_log {uml} (diff > 5)"
                )
        finally:
            conn.close()

    def test_source_count_consistency(self):
        """source_count must equal the number of true flags."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_employer_data_sources
                    WHERE source_count != (
                        has_osha::int + has_nlrb::int + has_whd::int + has_990::int +
                        has_sam::int + has_sec::int + has_gleif::int + has_mergent::int
                    )
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} rows have inconsistent source_count"
        finally:
            conn.close()

    def test_zero_source_employers_have_no_flags(self):
        """Employers with source_count=0 should have all flags false."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM mv_employer_data_sources
                    WHERE source_count = 0
                      AND (has_osha OR has_nlrb OR has_whd OR has_990
                           OR has_sam OR has_sec OR has_gleif OR has_mergent)
                """)
                bad = cur.fetchone()[0]
                assert bad == 0, f"{bad} zero-source employers have true flags"
        finally:
            conn.close()

    def test_source_count_range(self):
        """source_count should be between 0 and 8."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MIN(source_count), MAX(source_count)
                    FROM mv_employer_data_sources
                """)
                mn, mx = cur.fetchone()
                assert mn >= 0, f"Min source_count is {mn}"
                assert mx <= 8, f"Max source_count is {mx}"
        finally:
            conn.close()

    def test_has_employers_with_zero_sources(self):
        """Most employers should have zero external matches."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE source_count = 0")
                zero = cur.fetchone()[0]
                assert zero > 50000, f"Expected >50K zero-source employers, got {zero}"
        finally:
            conn.close()

    def test_has_multi_source_employers(self):
        """Some employers should have 2+ sources."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE source_count >= 2")
                multi = cur.fetchone()[0]
                assert multi > 5000, f"Expected >5K multi-source employers, got {multi}"
        finally:
            conn.close()


# ── API Tests ────────────────────────────────────────────────────────────

class TestDataSourcesAPI:
    """Verify API endpoints return correct format."""

    def test_data_coverage_endpoint(self, client):
        resp = client.get("/api/employers/data-coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_employers" in data
        assert "source_count_distribution" in data
        assert "by_source" in data
        assert data["total_employers"] > 100000

    def test_data_coverage_has_all_sources(self, client):
        resp = client.get("/api/employers/data-coverage")
        data = resp.json()
        by_source = data["by_source"]
        for key in ["osha", "nlrb", "whd", "n990", "sam", "sec", "gleif", "mergent"]:
            assert key in by_source, f"Missing source: {key}"
            assert by_source[key] >= 0

    def test_data_sources_detail_found(self, client):
        # Pick a known employer with matches
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM mv_employer_data_sources
                    WHERE source_count >= 2 LIMIT 1
                """)
                eid = cur.fetchone()[0]
        finally:
            conn.close()

        resp = client.get(f"/api/employers/{eid}/data-sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["employer_id"] == eid
        assert "has_osha" in data
        assert "has_nlrb" in data
        assert "source_count" in data
        assert data["source_count"] >= 2

    def test_data_sources_detail_not_found(self, client):
        resp = client.get("/api/employers/nonexistent_id_12345/data-sources")
        assert resp.status_code == 404

    def test_data_sources_has_crosswalk_fields(self, client):
        # Pick an employer with crosswalk data
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT employer_id FROM mv_employer_data_sources
                    WHERE corporate_family_id IS NOT NULL LIMIT 1
                """)
                eid = cur.fetchone()[0]
        finally:
            conn.close()

        resp = client.get(f"/api/employers/{eid}/data-sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["corporate_family_id"] is not None
        for field in ["sec_cik", "gleif_lei", "mergent_duns", "ein",
                      "ticker", "is_public", "is_federal_contractor"]:
            assert field in data

    def test_data_sources_endpoint_registered(self):
        import importlib
        from api.routers import employers
        importlib.reload(employers)
        routes = [r.path for r in employers.router.routes]
        assert "/api/employers/{employer_id}/data-sources" in routes

    def test_data_coverage_endpoint_registered(self):
        import importlib
        from api.routers import employers
        importlib.reload(employers)
        routes = [r.path for r in employers.router.routes]
        assert "/api/employers/data-coverage" in routes
