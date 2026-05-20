"""Unit tests for src/python/matching/master_dedup.py.

DB-free: every test exercises pure-Python logic. The SQL primitives
(merge_one, bulk_repoint, ensure_dedup_tables) are exercised live via the
backfill_pfizer_canonical_corruption.py --bundled preview against the
local DB; that path is documented in
docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.python.matching.master_dedup import (
    EMP_COUNT_PRIORITY,
    Employer,
    MergeContext,
    REPOINT_TARGETS,
    SOURCE_PRIORITY,
    has_confirming_signal,
    has_id_conflict,
    name_sim,
    pref,
    tnorm,
)
import scripts.maintenance.backfill_pfizer_canonical_corruption as bf  # noqa: E402
from scripts.maintenance.backfill_pfizer_canonical_corruption import (  # noqa: E402
    validate_merge_map,
)


def _emp(mid, *, source_origin="mergent", has_f7=False, ein=None, **kw):
    """Test factory with sensible defaults."""
    defaults = dict(
        canonical_name=None, display_name=None, city=None, state=None,
        zip_code=None, naics=None, employee_count=None,
        employee_count_source=None, is_union=False, is_public=False,
        is_federal_contractor=False, is_nonprofit=False, is_labor_org=None,
    )
    defaults.update(kw)
    return Employer(
        mid=mid, source_origin=source_origin, has_f7=has_f7, ein=ein, **defaults,
    )


# ============================================================================
# Employer.rank() — winner selection
# ============================================================================

class TestEmployerRank:
    def test_f7_wins_over_non_f7(self):
        a = _emp(mid=1, source_origin="mergent", has_f7=True)
        b = _emp(mid=2, source_origin="f7", has_f7=False)
        assert a.rank() < b.rank()

    def test_source_priority_breaks_ties_when_neither_has_f7(self):
        f7 = _emp(mid=99, source_origin="f7", has_f7=False)
        sam = _emp(mid=1, source_origin="sam", has_f7=False)
        mergent = _emp(mid=1, source_origin="mergent", has_f7=False)
        gleif = _emp(mid=1, source_origin="gleif", has_f7=False)
        assert f7.rank() < sam.rank() < mergent.rank() < gleif.rank()

    def test_lower_mid_wins_when_priority_ties(self):
        a = _emp(mid=1, source_origin="sam", has_f7=False)
        b = _emp(mid=2, source_origin="sam", has_f7=False)
        assert a.rank() < b.rank()

    def test_source_priority_ordering(self):
        order = ["f7", "sam", "mergent", "bmf", "sec", "990", "gleif"]
        for lo, hi in zip(order, order[1:]):
            assert SOURCE_PRIORITY[lo] < SOURCE_PRIORITY[hi], f"{lo} should rank before {hi}"

    def test_unknown_source_falls_through_to_99(self):
        a = _emp(mid=1, source_origin="something_unknown", has_f7=False)
        # rank: (1, 99, 1)
        assert a.rank()[1] == 99


# ============================================================================
# pref() / tnorm() — field blending
# ============================================================================

class TestPref:
    def test_longer_string_wins(self):
        assert pref("pfizer", "pfizer products") == "pfizer products"
        assert pref("pfizer products", "pfizer") == "pfizer products"

    def test_equal_length_returns_first(self):
        assert pref("abc", "xyz") == "abc"

    def test_none_handling(self):
        assert pref(None, "x") == "x"
        assert pref("x", None) == "x"
        assert pref(None, None) is None
        assert pref("", "y") == "y"
        assert pref("y", "") == "y"


class TestTnorm:
    def test_strips_whitespace(self):
        assert tnorm("  hello  ") == "hello"

    def test_returns_none_for_empty(self):
        assert tnorm("") is None
        assert tnorm("   ") is None
        assert tnorm(None) is None


# ============================================================================
# name_sim() — fuzz matching
# ============================================================================

class TestNameSim:
    def test_identical_returns_1(self):
        assert name_sim("pfizer products", "pfizer products") == 1.0

    def test_disjoint_returns_low(self):
        assert name_sim("aaaa", "zzzz") < 0.3

    def test_token_order_invariant(self):
        # token_sort_ratio is order-insensitive
        a = name_sim("a b c", "c b a")
        assert a == 1.0

    def test_none_returns_zero(self):
        assert name_sim(None, "x") == 0.0
        assert name_sim("x", None) == 0.0
        assert name_sim(None, None) == 0.0


# ============================================================================
# has_id_conflict() — skip-on-conflict guard
# ============================================================================

class TestHasIdConflict:
    def test_distinct_eins_flagged(self):
        a = _emp(mid=1, ein="12-3456789")
        b = _emp(mid=2, ein="99-0000000")
        assert has_id_conflict(a, b) == "ein"

    def test_matching_eins_safe(self):
        a = _emp(mid=1, ein="12-3456789")
        b = _emp(mid=2, ein="12-3456789")
        assert has_id_conflict(a, b) is None

    def test_one_null_ein_safe(self):
        a = _emp(mid=1, ein="12-3456789")
        b = _emp(mid=2, ein=None)
        assert has_id_conflict(a, b) is None
        assert has_id_conflict(b, a) is None

    def test_both_null_eins_safe(self):
        a = _emp(mid=1, ein=None)
        b = _emp(mid=2, ein=None)
        assert has_id_conflict(a, b) is None

    def test_empty_string_ein_treated_as_null(self):
        a = _emp(mid=1, ein="   ")
        b = _emp(mid=2, ein="12-3456789")
        assert has_id_conflict(a, b) is None


# ============================================================================
# has_confirming_signal() — extra evidence used by dedup
# ============================================================================

class TestHasConfirmingSignal:
    def test_matching_city_returns_true(self):
        a = _emp(mid=1, city="boston")
        b = _emp(mid=2, city="boston")
        assert has_confirming_signal(a, b) is True

    def test_matching_zip_prefix_returns_true(self):
        a = _emp(mid=1, zip_code="02134-1234")
        b = _emp(mid=2, zip_code="02138")
        assert has_confirming_signal(a, b) is True

    def test_no_overlap_returns_false(self):
        a = _emp(mid=1, city="boston", zip_code="02134", naics="551112")
        b = _emp(mid=2, city="san diego", zip_code="92093", naics="722110")
        assert has_confirming_signal(a, b) is False


# ============================================================================
# validate_merge_map — pre-mutation safety checks
# ============================================================================

class TestValidateMergeMap:
    def _mock_cur(self, present_mids):
        cur = MagicMock()
        cur.fetchall.return_value = [(m,) for m in present_mids]
        return cur

    def test_self_merge_raises(self):
        cur = self._mock_cur([1])
        with pytest.raises(RuntimeError, match="self-merge"):
            validate_merge_map(cur, {1: 1})

    def test_chain_winner_also_loser_raises(self):
        cur = self._mock_cur([1, 2, 3])
        # 1 loses to 2; 2 loses to 3 -> winner also loser (chain)
        with pytest.raises(RuntimeError, match="winner and"):
            validate_merge_map(cur, {1: 2, 2: 3})

    def test_missing_master_id_raises(self):
        cur = self._mock_cur([1])  # only 1 exists; 2 is the winner but missing
        with pytest.raises(RuntimeError, match="do not exist"):
            validate_merge_map(cur, {1: 2})

    def test_clean_map_passes(self):
        cur = self._mock_cur([1, 2, 3, 4])
        validate_merge_map(cur, {1: 2, 3: 4})  # no exception

    def test_empty_map_passes(self):
        cur = self._mock_cur([])
        validate_merge_map(cur, {})  # no exception


# ============================================================================
# REPOINT_TARGETS — schema-of-truth
# ============================================================================

class TestRepointTargets:
    def test_employer_directors_present(self):
        names = {t[0] for t in REPOINT_TARGETS}
        assert "employer_directors" in names

    def test_all_modes_valid(self):
        for _table, _cols, mode in REPOINT_TARGETS:
            assert mode in {"simple", "pk_master", "purge"}

    def test_comparables_uses_purge(self):
        for table, _cols, mode in REPOINT_TARGETS:
            if table == "employer_comparables":
                assert mode == "purge"

    def test_pk_master_tables_have_single_column(self):
        for table, cols, mode in REPOINT_TARGETS:
            if mode == "pk_master":
                assert len(cols) == 1, f"{table} has pk_master mode but >1 column"


# ============================================================================
# MergeContext.detect — schema introspection
# ============================================================================

class TestMergeContext:
    def test_explicit_init(self):
        ctx = MergeContext(
            pk_col="master_id",
            include_labor_org=True,
            merge_log_has_reason=False,
            merge_log_has_merged_by=False,
        )
        assert ctx.pk_col == "master_id"
        assert ctx.merged_by_label == "dedup_master_employers.py"

    def test_frozen_dataclass(self):
        ctx = MergeContext(
            pk_col="master_id", include_labor_org=False,
            merge_log_has_reason=False, merge_log_has_merged_by=False,
        )
        with pytest.raises(Exception):  # frozen dataclasses raise FrozenInstanceError
            ctx.pk_col = "id"


# ============================================================================
# EMP_COUNT_PRIORITY — sanity
# ============================================================================

class TestEmpCountPriority:
    def test_f7_wins(self):
        assert EMP_COUNT_PRIORITY["f7"] < EMP_COUNT_PRIORITY["mergent"]
        assert EMP_COUNT_PRIORITY["mergent"] < EMP_COUNT_PRIORITY["sam"]


# ============================================================================
# Pfizer back-fill bundled-mode helpers (Phase C)
# ============================================================================

class TestPfizerBundledPlan:
    """Logic-only checks on the buggy normalizer reproducer + helpers."""

    def test_buggy_reproducer_matches_known_inputs(self):
        # The verbatim buggy fn must produce the exact known-bad outputs.
        assert bf._buggy_normalize_name_for_per_row_check(
            "PFIZER PRODUCTS CORPORATION"
        ) == "pfizer productsoration"
        assert bf._buggy_normalize_name_for_per_row_check(
            "KROGER COMPANY"
        ) == "krogermpany"
        assert bf._buggy_normalize_name_for_per_row_check(
            "PFIZER H.C.P. CORPORATION"
        ) == "pfizer hcporation"

    def test_buggy_reproducer_handles_none(self):
        assert bf._buggy_normalize_name_for_per_row_check(None) is None
        assert bf._buggy_normalize_name_for_per_row_check("") is None

    def test_is_bug_victim_matches_when_buggy_output_equals_canonical(self):
        assert bf._is_bug_victim("PFIZER PRODUCTS CORPORATION", "pfizer productsoration")

    def test_is_bug_victim_false_when_canonical_differs(self):
        assert not bf._is_bug_victim("PFIZER PRODUCTS CORPORATION", "pfizer products")

    def test_is_bug_victim_safe_on_nulls(self):
        assert not bf._is_bug_victim(None, "x")
        assert not bf._is_bug_victim("x", None)

    def test_advisory_lock_id_is_int(self):
        assert isinstance(bf.BUNDLED_ADVISORY_LOCK_ID, int)
        assert bf.BUNDLED_ADVISORY_LOCK_ID > 0
