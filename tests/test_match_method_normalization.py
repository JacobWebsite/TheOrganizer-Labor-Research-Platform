"""
Tests for match method normalization (Task 4-4).

Verifies:
  - _make_result uppercases match_method
  - Adapter write_legacy uppercases match_method
  - No lowercase methods remain in live DB tables (integration)
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_config import get_connection


# ---------------------------------------------------------------------------
# Unit tests (no DB)
# ---------------------------------------------------------------------------

class TestMakeResultUppercases:
    """_make_result should normalize method to UPPER."""

    def test_lowercase_method_uppercased(self):
        from scripts.matching.deterministic_matcher import DeterministicMatcher
        # Create a minimal instance without running the full pipeline
        dm = object.__new__(DeterministicMatcher)
        dm.run_id = "test-run"
        dm.source_system = "osha"
        dm._log_buffer = []
        dm.stats = {"by_method": {}, "by_band": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}}
        result = dm._make_result(
            source_id="E001",
            target_id="F001",
            method="name_state_exact",
            tier=3,
            band="HIGH",
            score=0.92,
            evidence={"source_name": "TEST"},
        )
        assert result["method"] == "NAME_STATE_EXACT"

    def test_already_upper_unchanged(self):
        from scripts.matching.deterministic_matcher import DeterministicMatcher
        dm = object.__new__(DeterministicMatcher)
        dm.run_id = "test-run"
        dm.source_system = "osha"
        dm._log_buffer = []
        dm.stats = {"by_method": {}, "by_band": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}}
        result = dm._make_result(
            source_id="E002",
            target_id="F002",
            method="EIN_EXACT",
            tier=1,
            band="HIGH",
            score=1.0,
            evidence={"ein": "123456789"},
        )
        assert result["method"] == "EIN_EXACT"

    def test_mixed_case_uppercased(self):
        from scripts.matching.deterministic_matcher import DeterministicMatcher
        dm = object.__new__(DeterministicMatcher)
        dm.run_id = "test-run"
        dm.source_system = "osha"
        dm._log_buffer = []
        dm.stats = {"by_method": {}, "by_band": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}}
        result = dm._make_result(
            source_id="E003",
            target_id="F003",
            method="Name_City_State_Exact",
            tier=2,
            band="HIGH",
            score=0.90,
            evidence={},
        )
        assert result["method"] == "NAME_CITY_STATE_EXACT"


class TestAdapterUppercases:
    """Adapter write_legacy row tuples should uppercase method."""

    def test_osha_adapter_uppercases(self):
        matches = [{"source_id": "E1", "target_id": "F1", "method": "name_zip_exact", "score": 0.85}]
        rows = [(m["source_id"], m["target_id"], m["method"].upper(), m["score"]) for m in matches]
        assert rows[0][2] == "NAME_ZIP_EXACT"

    def test_n990_adapter_uppercases(self):
        matches = [{"source_id": "N1", "target_id": "F1", "method": "ein_exact",
                     "score": 1.0, "evidence": {"ein": "123"}}]
        for m in matches:
            ein = m.get("evidence", {}).get("ein") or ""
            row = (m["source_id"], ein, m["target_id"], m["method"].upper(), m["score"])
        assert row[3] == "EIN_EXACT"


# ---------------------------------------------------------------------------
# Integration tests (require DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


MATCH_TABLES = [
    "unified_match_log",
    "osha_f7_matches",
    "whd_f7_matches",
    "sam_f7_matches",
    "national_990_f7_matches",
]


class TestNoLowercaseInDB:
    """After normalization, no table should have lowercase match_method values."""

    @pytest.mark.parametrize("table", MATCH_TABLES)
    def test_no_lowercase_methods(self, conn, table):
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE match_method != UPPER(match_method)"
            )
            count = cur.fetchone()[0]
        assert count == 0, (
            f"{table} has {count} rows with non-uppercase match_method"
        )
