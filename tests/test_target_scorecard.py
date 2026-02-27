"""
Tests for target scorecard MV (mv_target_scorecard) and API.

Covers:
- MV schema (columns, indexes)
- Data integrity (signal ranges, gold standard tiers, enhanced signals)
- Research integration columns
- API endpoints (list, stats, detail) with filters
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from db_config import get_connection
from psycopg2.extras import RealDictCursor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def conn():
    c = get_connection()
    yield c
    c.close()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def _mv_exists(conn):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_target_scorecard') AS e")
    return cur.fetchone()["e"]


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------
class TestTargetScorecardSchema:
    def test_mv_exists(self, conn):
        assert _mv_exists(conn), "mv_target_scorecard must exist"

    def test_has_required_columns(self, conn):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT attname FROM pg_attribute
            WHERE attrelid = 'mv_target_scorecard'::regclass AND attnum > 0
        """)
        cols = {r["attname"] for r in cur.fetchall()}
        required = {
            # Identity
            "master_id", "display_name", "city", "state", "naics",
            "employee_count", "is_federal_contractor", "is_nonprofit", "source_count",
            # Base signals
            "signal_osha", "signal_whd", "signal_nlrb", "signal_contracts",
            "signal_financial", "signal_industry_growth", "signal_union_density", "signal_size",
            # Inventory
            "signals_present", "has_enforcement", "enforcement_count", "has_recent_violations",
            # Pillars
            "pillar_anger", "pillar_leverage", "pillar_stability",
            # Research integration
            "has_research", "research_run_id", "research_quality",
            "research_approach", "research_trend", "research_contradictions",
            "research_strengths", "research_challenges",
            # Enhanced signals
            "enh_signal_osha", "enh_signal_whd", "enh_signal_nlrb",
            "enh_signal_contracts", "enh_signal_financial", "enh_signal_size",
            # Gold standard
            "gold_standard_tier",
        }
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_unique_index_on_master_id(self, conn):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'mv_target_scorecard' AND indexname = 'idx_mv_ts_master_id'
        """)
        assert cur.fetchone() is not None, "Unique index on master_id must exist"

    def test_research_index_exists(self, conn):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'mv_target_scorecard' AND indexname = 'idx_mv_ts_has_research'
        """)
        assert cur.fetchone() is not None, "Index on has_research must exist"

    def test_gold_tier_index_exists(self, conn):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'mv_target_scorecard' AND indexname = 'idx_mv_ts_gold_tier'
        """)
        assert cur.fetchone() is not None, "Index on gold_standard_tier must exist"


# ---------------------------------------------------------------------------
# Data Integrity Tests
# ---------------------------------------------------------------------------
class TestTargetScorecardData:
    def test_row_count_positive(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_target_scorecard")
        total = cur.fetchone()[0]
        assert total > 100_000, f"Expected 100K+ rows, got {total}"

    def test_signal_scores_in_range(self, conn):
        """All signal scores must be 0-10 or NULL."""
        cur = conn.cursor()
        for col in ["signal_osha", "signal_whd", "signal_nlrb", "signal_contracts",
                     "signal_financial", "signal_industry_growth", "signal_union_density", "signal_size"]:
            cur.execute(f"SELECT COUNT(*) FROM mv_target_scorecard WHERE {col} < 0 OR {col} > 10")
            bad = cur.fetchone()[0]
            assert bad == 0, f"{col} has {bad} out-of-range values"

    def test_enhanced_signals_in_range(self, conn):
        """Enhanced signals must be 0-10 or NULL."""
        cur = conn.cursor()
        for col in ["enh_signal_osha", "enh_signal_whd", "enh_signal_nlrb",
                     "enh_signal_contracts", "enh_signal_financial", "enh_signal_size"]:
            cur.execute(f"SELECT COUNT(*) FROM mv_target_scorecard WHERE {col} < 0 OR {col} > 10")
            bad = cur.fetchone()[0]
            assert bad == 0, f"{col} has {bad} out-of-range values"

    def test_enhanced_signals_gte_base(self, conn):
        """Enhanced signals must be >= base signals (GREATEST logic)."""
        cur = conn.cursor()
        for base, enh in [("signal_osha", "enh_signal_osha"), ("signal_whd", "enh_signal_whd"),
                          ("signal_nlrb", "enh_signal_nlrb"), ("signal_contracts", "enh_signal_contracts"),
                          ("signal_financial", "enh_signal_financial")]:
            cur.execute(f"""
                SELECT COUNT(*) FROM mv_target_scorecard
                WHERE {base} IS NOT NULL AND {enh} IS NOT NULL AND {enh} < {base}
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{enh} < {base} in {bad} rows (GREATEST violated)"

    def test_signals_present_range(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE signals_present < 0 OR signals_present > 8")
        assert cur.fetchone()[0] == 0

    def test_gold_standard_tier_values(self, conn):
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT DISTINCT gold_standard_tier FROM mv_target_scorecard")
        tiers = {r["gold_standard_tier"] for r in cur.fetchall()}
        valid = {"stub", "bronze", "silver", "gold", "platinum"}
        invalid = tiers - valid
        assert not invalid, f"Invalid gold_standard_tier values: {invalid}"

    def test_has_research_boolean(self, conn):
        """has_research must be true/false, not NULL."""
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE has_research IS NULL")
        assert cur.fetchone()[0] == 0, "has_research should never be NULL"

    def test_pillars_in_range(self, conn):
        cur = conn.cursor()
        for col in ["pillar_anger", "pillar_leverage", "pillar_stability"]:
            cur.execute(f"SELECT COUNT(*) FROM mv_target_scorecard WHERE {col} < 0 OR {col} > 10")
            bad = cur.fetchone()[0]
            assert bad == 0, f"{col} has {bad} out-of-range values"

    def test_research_quality_range(self, conn):
        """research_quality must be 0-10 where present."""
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE research_quality < 0 OR research_quality > 10")
        assert cur.fetchone()[0] == 0

    def test_no_research_implies_no_run_id(self, conn):
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM mv_target_scorecard
            WHERE has_research = FALSE AND research_run_id IS NOT NULL
        """)
        assert cur.fetchone()[0] == 0, "has_research=false but research_run_id set"

    def test_enforcement_count_range(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE enforcement_count < 0 OR enforcement_count > 3")
        assert cur.fetchone()[0] == 0

    def test_bronze_tier_has_multiple_signals(self, conn):
        """Bronze tier requires >= 3 non-null enforcement/financial signals or research."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM mv_target_scorecard
            WHERE gold_standard_tier = 'bronze' AND has_research = FALSE
              AND (CASE WHEN signal_osha IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN signal_whd IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN signal_nlrb IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN signal_contracts IS NOT NULL THEN 1 ELSE 0 END
                   + CASE WHEN signal_financial IS NOT NULL THEN 1 ELSE 0 END
              ) < 3
        """)
        assert cur.fetchone()["cnt"] == 0, "Non-researched bronze tier should have >= 3 enforcement/financial signals"


# ---------------------------------------------------------------------------
# API Tests
# ---------------------------------------------------------------------------
class TestTargetScorecardAPI:
    def test_list_endpoint(self, client):
        r = client.get("/api/targets/scorecard?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "results" in data
        assert len(data["results"]) <= 5

    def test_list_has_research_columns(self, client):
        r = client.get("/api/targets/scorecard?limit=1")
        assert r.status_code == 200
        row = r.json()["results"][0]
        assert "has_research" in row
        assert "gold_standard_tier" in row
        assert "enh_signal_osha" in row
        assert "research_quality" in row

    def test_list_filter_has_research(self, client):
        r = client.get("/api/targets/scorecard?has_research=true&limit=5")
        assert r.status_code == 200
        # All results (if any) should have has_research=true
        for row in r.json()["results"]:
            assert row["has_research"] is True

    def test_list_filter_gold_tier(self, client):
        r = client.get("/api/targets/scorecard?gold_standard_tier=bronze&limit=5")
        assert r.status_code == 200
        for row in r.json()["results"]:
            assert row["gold_standard_tier"] == "bronze"

    def test_list_sort_by_research_quality(self, client):
        r = client.get("/api/targets/scorecard?sort=research_quality&order=desc&limit=5")
        assert r.status_code == 200

    def test_list_sort_by_gold_tier(self, client):
        r = client.get("/api/targets/scorecard?sort=gold_tier&order=asc&limit=5")
        assert r.status_code == 200

    def test_stats_has_research_coverage(self, client):
        r = client.get("/api/targets/scorecard/stats")
        assert r.status_code == 200
        data = r.json()
        assert "research_coverage" in data
        assert "researched" in data["research_coverage"]
        assert isinstance(data["research_coverage"]["researched"], int)

    def test_stats_has_gold_tiers(self, client):
        r = client.get("/api/targets/scorecard/stats")
        assert r.status_code == 200
        data = r.json()
        assert "gold_standard_tiers" in data
        tiers = data["gold_standard_tiers"]
        assert len(tiers) > 0
        assert all("tier" in t and "count" in t for t in tiers)

    def test_detail_has_research_section(self, client):
        # Get a real master_id
        r = client.get("/api/targets/scorecard?limit=1")
        master_id = r.json()["results"][0]["master_id"]
        r2 = client.get(f"/api/targets/scorecard/{master_id}")
        assert r2.status_code == 200
        data = r2.json()
        assert "summary" in data
        assert "has_research" in data["summary"]
        assert "gold_standard_tier" in data["summary"]
        # research section is None when no research
        if not data["summary"]["has_research"]:
            assert data.get("research") is None

    def test_detail_summary_keys(self, client):
        r = client.get("/api/targets/scorecard?limit=1")
        master_id = r.json()["results"][0]["master_id"]
        r2 = client.get(f"/api/targets/scorecard/{master_id}")
        summary = r2.json()["summary"]
        required_keys = {
            "signals_present", "has_enforcement", "enforcement_count",
            "has_recent_violations", "has_research", "gold_standard_tier",
            "pillar_anger", "pillar_leverage", "pillar_stability",
        }
        assert required_keys <= set(summary.keys())

    def test_detail_not_found(self, client):
        r = client.get("/api/targets/scorecard/999999999")
        assert r.status_code == 404
