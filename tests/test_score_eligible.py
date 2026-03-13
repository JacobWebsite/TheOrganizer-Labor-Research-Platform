"""
Tests for score_eligible column and filtering (Task 4-1).

Verifies:
  - Column exists on all legacy match tables
  - HIGH confidence matches are eligible
  - AGGRESSIVE low-confidence matches are ineligible
  - Identity methods (EIN_EXACT, CROSSWALK) always eligible
  - Data source badges unchanged (has_osha still counts ineligible matches)
  - Scoring CTEs filter on score_eligible
  - Adapter inserts include score_eligible
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_config import get_connection


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


LEGACY_TABLES = [
    "osha_f7_matches",
    "whd_f7_matches",
    "sam_f7_matches",
    "national_990_f7_matches",
]


class TestScoreEligibleColumn:
    """Column exists and has correct values."""

    @pytest.mark.parametrize("table", LEGACY_TABLES)
    def test_column_exists(self, conn, table):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = 'score_eligible'",
                (table,),
            )
            assert cur.fetchone() is not None, f"{table} missing score_eligible column"

    @pytest.mark.parametrize("table", LEGACY_TABLES)
    def test_no_nulls(self, conn, table):
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE score_eligible IS NULL")
            nulls = cur.fetchone()[0]
        assert nulls == 0, f"{table} has {nulls} NULL score_eligible values"


class TestEligibilityRules:
    """Verify eligibility rules are correctly applied."""

    def test_high_confidence_eligible(self, conn):
        """Matches with confidence >= 0.85 should be score_eligible."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM osha_f7_matches "
                "WHERE match_confidence >= 0.85 AND score_eligible = FALSE"
            )
            bad = cur.fetchone()[0]
        assert bad == 0, f"{bad} high-confidence OSHA matches incorrectly marked ineligible"

    def test_ein_always_eligible(self, conn):
        """EIN_EXACT matches always eligible regardless of confidence."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM osha_f7_matches "
                "WHERE UPPER(match_method) = 'EIN_EXACT' AND score_eligible = FALSE"
            )
            bad = cur.fetchone()[0]
        assert bad == 0, f"{bad} EIN_EXACT matches incorrectly marked ineligible"

    def test_crosswalk_always_eligible(self, conn):
        """CROSSWALK matches always eligible regardless of confidence."""
        for table in LEGACY_TABLES:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE UPPER(match_method) = 'CROSSWALK' AND score_eligible = FALSE"
                )
                bad = cur.fetchone()[0]
            assert bad == 0, f"{table}: {bad} CROSSWALK matches incorrectly marked ineligible"

    def test_low_confidence_no_corroboration_ineligible(self, conn):
        """Low-confidence matches with NO corroboration should be ineligible.

        Matches promoted by corroboration (city/zip/naics match) are correctly
        eligible even at low confidence, so we check only zero-corroboration ones.
        """
        with conn.cursor() as cur:
            # Check that zero-corroboration low-confidence matches are ineligible
            cur.execute("""
                SELECT COUNT(*) FROM osha_f7_matches m
                JOIN osha_establishments oe ON oe.establishment_id = m.establishment_id
                JOIN f7_employers_deduped f7 ON f7.employer_id = m.f7_employer_id
                WHERE m.match_confidence < 0.85
                  AND UPPER(m.match_method) NOT IN ('EIN_EXACT', 'CROSSWALK', 'CIK_BRIDGE')
                  AND m.score_eligible = TRUE
                  AND (CASE WHEN UPPER(TRIM(oe.site_city)) = UPPER(TRIM(f7.city))
                            AND oe.site_city IS NOT NULL AND f7.city IS NOT NULL THEN 2 ELSE 0 END)
                    + (CASE WHEN LEFT(oe.site_zip, 5) = LEFT(f7.zip, 5)
                            AND oe.site_zip IS NOT NULL AND f7.zip IS NOT NULL THEN 3 ELSE 0 END)
                    + (CASE WHEN LEFT(oe.naics_code, 2) = LEFT(f7.naics, 2)
                            AND oe.naics_code IS NOT NULL AND f7.naics IS NOT NULL THEN 2 ELSE 0 END)
                    < 2
            """)
            bad = cur.fetchone()[0]
        assert bad == 0, (
            f"{bad} low-confidence OSHA matches with no corroboration "
            f"incorrectly marked eligible"
        )


class TestScoringSQL:
    """Verify scoring SQL includes score_eligible filter."""

    def test_osha_agg_filters(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        # Check that osha_agg CTE has score_eligible filter
        osha_section = MV_SQL.split("osha_agg AS")[1].split("),")[0]
        assert "score_eligible" in osha_section, "osha_agg CTE missing score_eligible filter"

    def test_whd_agg_filters(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        whd_section = MV_SQL.split("whd_agg AS")[1].split("),")[0]
        assert "score_eligible" in whd_section, "whd_agg CTE missing score_eligible filter"

    def test_financial_990_filters(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        fin_section = MV_SQL.split("financial_990 AS")[1].split("),")[0]
        assert "score_eligible" in fin_section, "financial_990 CTE missing score_eligible filter"


class TestAdapterInsertsScoreEligible:
    """Verify adapters include score_eligible in INSERT."""

    def test_osha_adapter_sql_has_score_eligible(self):
        import inspect
        from scripts.matching.adapters.osha_adapter import write_legacy
        source = inspect.getsource(write_legacy)
        assert "score_eligible" in source

    def test_whd_adapter_sql_has_score_eligible(self):
        import inspect
        from scripts.matching.adapters.whd_adapter import write_legacy
        source = inspect.getsource(write_legacy)
        assert "score_eligible" in source

    def test_sam_adapter_sql_has_score_eligible(self):
        import inspect
        from scripts.matching.adapters.sam_adapter import write_legacy
        source = inspect.getsource(write_legacy)
        assert "score_eligible" in source

    def test_n990_adapter_sql_has_score_eligible(self):
        import inspect
        from scripts.matching.adapters.n990_adapter import write_legacy
        source = inspect.getsource(write_legacy)
        assert "score_eligible" in source
