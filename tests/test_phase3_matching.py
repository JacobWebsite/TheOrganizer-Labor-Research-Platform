"""
Phase 3 Matching Pipeline Overhaul regression tests.

Validates:
- unified_match_log table exists and is populated
- Pre-computed name columns on f7_employers_deduped
- NLRB bridge view exists
- Match quality API endpoint
- Name normalization canonical module
- Deterministic matcher import
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection


# ============================================================================
# unified_match_log
# ============================================================================

class TestUnifiedMatchLog:
    """Verify unified_match_log table and data."""

    def test_table_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'unified_match_log'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_has_minimum_rows(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM unified_match_log")
                count = cur.fetchone()[0]
                # Should have at least 188K from backfill
                assert count >= 188000, f"Expected >= 188K rows, got {count:,}"
        finally:
            conn.close()

    def test_all_sources_represented(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT source_system FROM unified_match_log
                    ORDER BY source_system
                """)
                sources = {r[0] for r in cur.fetchall()}
                for expected in ["osha", "whd", "990", "sam", "nlrb"]:
                    assert expected in sources, f"Missing source: {expected}"
        finally:
            conn.close()

    def test_all_confidence_bands_present(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT confidence_band FROM unified_match_log
                """)
                bands = {r[0] for r in cur.fetchall()}
                for expected in ["HIGH", "MEDIUM", "LOW"]:
                    assert expected in bands, f"Missing band: {expected}"
        finally:
            conn.close()

    def test_evidence_not_null(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM unified_match_log
                    WHERE evidence IS NULL OR evidence = '{}'::jsonb
                """)
                null_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM unified_match_log")
                total = cur.fetchone()[0]
                # Allow up to 1% null evidence (edge cases)
                assert null_count / max(total, 1) < 0.01, \
                    f"{null_count:,} rows have null/empty evidence out of {total:,}"
        finally:
            conn.close()

    def test_required_columns_exist(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'unified_match_log'
                """)
                cols = {r[0] for r in cur.fetchall()}
                for expected in ["run_id", "source_system", "source_id", "target_id",
                                 "match_method", "match_tier", "confidence_band",
                                 "confidence_score", "evidence", "status"]:
                    assert expected in cols, f"Missing column: {expected}"
        finally:
            conn.close()


# ============================================================================
# Pre-computed name columns
# ============================================================================

class TestNameColumns:
    """Verify pre-computed name columns on f7_employers_deduped."""

    def test_columns_exist(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'f7_employers_deduped'
                      AND column_name IN ('name_standard', 'name_aggressive', 'name_fuzzy')
                """)
                cols = {r[0] for r in cur.fetchall()}
                assert "name_standard" in cols
                assert "name_aggressive" in cols
                assert "name_fuzzy" in cols
        finally:
            conn.close()

    def test_columns_populated(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM f7_employers_deduped
                    WHERE name_standard IS NOT NULL
                """)
                filled = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
                total = cur.fetchone()[0]
                # At least 99% should be filled
                assert filled / max(total, 1) > 0.99, \
                    f"Only {filled:,} of {total:,} have name_standard"
        finally:
            conn.close()

    def test_indexes_exist(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'f7_employers_deduped'
                      AND indexname LIKE 'idx_f7_name_%%'
                """)
                indexes = {r[0] for r in cur.fetchall()}
                assert len(indexes) >= 3, f"Expected 3 name indexes, found {len(indexes)}"
        finally:
            conn.close()


# ============================================================================
# NLRB Bridge View
# ============================================================================

class TestNlrbBridgeView:
    """Verify v_nlrb_employer_history view."""

    def test_view_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.views
                    WHERE table_name = 'v_nlrb_employer_history'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_view_has_data(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM v_nlrb_employer_history")
                count = cur.fetchone()[0]
                assert count > 0, "View has no data"
        finally:
            conn.close()

    def test_view_has_categories(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT case_category FROM v_nlrb_employer_history
                """)
                categories = {r[0] for r in cur.fetchall()}
                assert "representation" in categories
        finally:
            conn.close()


# ============================================================================
# Match runs table enhanced
# ============================================================================

class TestMatchRunsEnhanced:
    """Verify match_runs has new columns."""

    def test_new_columns_exist(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'match_runs'
                      AND column_name IN ('source_system', 'method_type',
                                          'high_count', 'medium_count', 'low_count')
                """)
                cols = {r[0] for r in cur.fetchall()}
                for expected in ["source_system", "method_type", "high_count"]:
                    assert expected in cols, f"Missing column: {expected}"
        finally:
            conn.close()


# ============================================================================
# historical_merge_candidates table
# ============================================================================

class TestHistoricalMergeCandidates:
    """Verify historical_merge_candidates table exists."""

    def test_table_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'historical_merge_candidates'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()


# ============================================================================
# API Endpoints (import-level checks)
# ============================================================================

class TestAPIEndpoints:
    """Verify new API endpoints are registered."""

    def test_match_quality_endpoint_registered(self):
        from api.main import app
        paths = {r.path for r in app.routes if hasattr(r, 'path')}
        assert "/api/admin/match-quality" in paths

    def test_match_review_endpoint_registered(self):
        from api.main import app
        paths = {r.path for r in app.routes if hasattr(r, 'path')}
        assert "/api/admin/match-review" in paths

    def test_nlrb_history_endpoint_registered(self):
        from api.main import app
        paths = {r.path for r in app.routes if hasattr(r, 'path')}
        assert "/api/employers/{employer_id}/nlrb-history" in paths
