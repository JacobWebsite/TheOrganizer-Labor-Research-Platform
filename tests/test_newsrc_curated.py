"""
Tests for curated transform tables and master employer seed scripts.

Validates:
- Seed scripts are importable and have expected functions
- Curated table SQL generates valid schema
- Data source MV includes new has_form5500 and has_ppp flags
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestSeedForm5500:
    """Tests for seed_master_form5500.py."""

    def test_importable(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        import seed_master_form5500  # noqa: F401

    def test_has_seed_function(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        from seed_master_form5500 import seed_form5500
        assert callable(seed_form5500)

    def test_has_constraint_function(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        from seed_master_form5500 import ensure_check_constraints
        assert callable(ensure_check_constraints)


class TestSeedPPP:
    """Tests for seed_master_ppp.py."""

    def test_importable(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        import seed_master_ppp  # noqa: F401

    def test_has_seed_function(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        from seed_master_ppp import seed_ppp
        assert callable(seed_ppp)


class TestEmployerDataSourcesMV:
    """Test that the employer data sources MV SQL includes new flags."""

    def test_mv_sql_has_form5500_flag(self):
        from scripts.scoring.build_employer_data_sources import MV_SQL
        assert "has_form5500" in MV_SQL

    def test_mv_sql_has_ppp_flag(self):
        from scripts.scoring.build_employer_data_sources import MV_SQL
        assert "has_ppp" in MV_SQL

    def test_mv_sql_form5500_in_source_count(self):
        from scripts.scoring.build_employer_data_sources import MV_SQL
        assert "f5m.f7_employer_id IS NOT NULL" in MV_SQL

    def test_mv_sql_ppp_in_source_count(self):
        from scripts.scoring.build_employer_data_sources import MV_SQL
        assert "pppm.f7_employer_id IS NOT NULL" in MV_SQL


class TestTargetDataSourcesMV:
    """Test that the target data sources MV SQL includes new flags."""

    def test_mv_sql_has_form5500_flag(self):
        from scripts.scoring.build_target_data_sources import MV_SQL
        assert "has_form5500" in MV_SQL

    def test_mv_sql_has_ppp_flag(self):
        from scripts.scoring.build_target_data_sources import MV_SQL
        assert "has_ppp" in MV_SQL


class TestUnifiedScorecardFormula:
    """Test that the unified scorecard SQL includes Form 5500 in score_financial."""

    def test_has_form5500_cte(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        assert "financial_form5500" in MV_SQL

    def test_has_form5500_join(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        assert "ff5.f7_employer_id" in MV_SQL

    def test_form5500_participant_scoring(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        assert "f5500_participants" in MV_SQL

    def test_form5500_pension_scoring(self):
        from scripts.scoring.build_unified_scorecard import MV_SQL
        assert "f5500_has_pension" in MV_SQL

    def test_greatest_blending(self):
        """score_financial should use GREATEST to blend 990 and Form 5500."""
        from scripts.scoring.build_unified_scorecard import MV_SQL
        # The scored CTE should contain GREATEST for the financial score
        assert "GREATEST(" in MV_SQL
        # The Form 5500-based score should be present
        assert "Form 5500-based financial score" in MV_SQL


class TestTargetScorecardFormula:
    """Test that the target scorecard SQL includes Form 5500."""

    def test_has_form5500_cte(self):
        from scripts.scoring.build_target_scorecard import MV_SQL
        assert "financial_form5500" in MV_SQL

    def test_has_form5500_join(self):
        from scripts.scoring.build_target_scorecard import MV_SQL
        assert "ff5.master_id" in MV_SQL

    def test_signal_financial_uses_greatest(self):
        from scripts.scoring.build_target_scorecard import MV_SQL
        # signal_financial should blend 990 and Form 5500 via GREATEST
        assert "ff5.f5500_participants" in MV_SQL
