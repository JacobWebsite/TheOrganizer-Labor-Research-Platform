"""Regression tests for scripts/etl/load_fec.py::_norm_date.

Guards against the silent NameError that shipped on 2026-05-03: the loader
imported `from datetime import datetime, timezone` but `_norm_date` calls
`date.today()` at line 230 to enforce a [1980, today+1] year sanity range.
Without `date` imported, every parseable FEC date raised NameError and the
year-range check was effectively dead.

Three call sites were vulnerable to this NameError on next loader run:
  - scripts/etl/load_fec.py::_load_indiv   (line 402)
  - scripts/etl/load_fec.py::_load_pas2    (line 451)
  - scripts/etl/load_fec_extra_cycles.py::load_indiv_from  (line 78)

The fix (cherry-pick of d850d54 from ship/2026-05-12-future-date-cleanup):
add `date` to the top-level `from datetime import ...` line.
"""
from __future__ import annotations

import sys
from datetime import date as _date_type
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.etl.load_fec import _norm_date


class TestNormDateNameErrorRegression:
    """Direct guards against the date.today() NameError."""

    def test_future_year_returns_none_not_nameerror(self):
        """Year too far in the future must return None, not raise NameError.

        FEC bulk data has had keystroke typos like 3312, 2031, 2029. The
        year-range check rejects anything past today+1.
        """
        result = _norm_date("01012099")  # MMDDYYYY format
        assert result is None, (
            f"Expected None for year 2099, got {result!r}. "
            "If this raised NameError, the date import regression is back."
        )

    def test_far_future_year_3312_returns_none(self):
        """Real FEC garbage value: 2099 -> None, not crash."""
        result = _norm_date("01013312")
        assert result is None

    def test_year_before_1980_returns_none(self):
        """FEC bulk only covers 1980-present."""
        result = _norm_date("01011970")
        assert result is None


class TestNormDateValidInputs:
    """Confirm valid dates parse correctly."""

    def test_valid_date_returns_date_object(self):
        result = _norm_date("06152024")
        assert result == _date_type(2024, 6, 15)
        assert isinstance(result, _date_type)

    def test_valid_recent_date(self):
        """A date from the current FEC cycle."""
        result = _norm_date("03152023")
        assert result == _date_type(2023, 3, 15)


class TestNormDateMalformedInputs:
    """Confirm malformed inputs return None without crashing."""

    def test_empty_string_returns_none(self):
        assert _norm_date("") is None

    def test_none_returns_none(self):
        assert _norm_date(None) is None

    def test_wrong_length_returns_none(self):
        assert _norm_date("2024-06-15") is None  # not 8 chars MMDDYYYY
        assert _norm_date("0615") is None

    def test_unparseable_returns_none(self):
        assert _norm_date("13322024") is None  # month 13
        assert _norm_date("XXXXXXXX") is None


class TestDateImportPresent:
    """Static guard: ensure `date` is importable from the loader module.

    If a future refactor strips the import again, this test fails before
    the rest of the suite runs.
    """

    def test_date_is_importable_from_load_fec(self):
        from scripts.etl import load_fec
        assert hasattr(load_fec, "date"), (
            "scripts.etl.load_fec must expose `date` (from datetime). "
            "Without it, _norm_date's date.today() call raises NameError."
        )
        assert load_fec.date is _date_type
