"""
Tests for api/services/demographics_bounds.py.

Background: R7-1 (2026-04-26 audit) found /api/demographics/NY/6111 returning
total_workers = 145,000,000 -- ~17x the entire NY State workforce.
These tests lock in the plausibility checks that catch that class of bug.
"""
import pytest

from api.services import demographics_bounds


@pytest.fixture(autouse=True)
def _stub_ceilings(monkeypatch):
    """Stub the DB-backed ceiling lookup so tests don't depend on bls_state_density.

    Numbers chosen to mirror the real BLS-CPS 2024 employed counts * 1.30:
        NY: 8.3M employed -> ceiling 10.79M
        CA: 16.3M -> 21.25M
        VA: 4.0M -> 5.25M
    """
    fake_ceilings = {
        "NY": 10_790_000,
        "CA": 21_250_000,
        "VA": 5_255_000,
        "OH": 6_640_000,
        "TX": 16_924_000,
    }
    monkeypatch.setattr(
        demographics_bounds,
        "_state_ceilings_from_db",
        lambda: fake_ceilings,
    )
    demographics_bounds.reset_cache()
    yield
    demographics_bounds.reset_cache()


def _plausible_ny_hospitals_payload() -> dict:
    """Realistic-looking demographics payload for NY hospitals (NAICS 6111).
    Numbers are made up but physically possible."""
    return {
        "total_workers": 250_000,
        "gender": [
            {"code": "1", "label": "Male", "pct": 28.0},
            {"code": "2", "label": "Female", "pct": 72.0},
        ],
        "race": [
            {"code": "1", "label": "White", "pct": 60.0},
            {"code": "2", "label": "Black/African American", "pct": 18.0},
            {"code": "4", "label": "Chinese", "pct": 8.0},
            {"code": "6", "label": "Other Asian/Pacific Islander", "pct": 8.0},
            {"code": "7", "label": "Other race", "pct": 6.0},
        ],
        "hispanic": [
            {"code": "0", "label": "Not Hispanic", "pct": 78.0},
            {"code": "1", "label": "Mexican", "pct": 4.0},
            {"code": "2", "label": "Puerto Rican", "pct": 12.0},
            {"code": "3", "label": "Cuban", "pct": 2.0},
            {"code": "4", "label": "Other Hispanic/Latino", "pct": 4.0},
        ],
        "age_distribution": [
            {"bucket": "u25", "pct": 8.0},
            {"bucket": "25_34", "pct": 22.0},
            {"bucket": "35_44", "pct": 24.0},
            {"bucket": "45_54", "pct": 22.0},
            {"bucket": "55_64", "pct": 18.0},
            {"bucket": "65p", "pct": 6.0},
        ],
        "education": [
            {"group": "No HS diploma", "pct": 4.0},
            {"group": "HS diploma/GED", "pct": 18.0},
            {"group": "Some college/Associate's", "pct": 24.0},
            {"group": "Bachelor's", "pct": 32.0},
            {"group": "Graduate/Professional", "pct": 22.0},
        ],
    }


def test_plausible_payload_no_warnings():
    payload = _plausible_ny_hospitals_payload()
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert warnings == []


def test_r7_1_bug_reproduction_ny_145m():
    """The exact R7-1 bug: 145M total_workers for NY industry slice.
    NY's employed labor force is ~8.3M -- 145M is 17x impossible."""
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = 145_000_000
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert len(warnings) == 1
    assert "total_workers 145,000,000" in warnings[0]
    assert "ceiling" in warnings[0]
    assert "NY" in warnings[0]


def test_total_workers_exceeds_us_ceiling_when_no_state():
    """Fallback to US-wide cap when state isn't known.
    US employed ~144.5M -> ceiling ~187.9M. 200M trips the cap."""
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = 200_000_000
    warnings = demographics_bounds.assert_demographics_plausible(payload)
    assert any("total_workers" in w and "ceiling" in w for w in warnings)


def test_total_workers_just_under_state_ceiling_no_warning():
    payload = _plausible_ny_hospitals_payload()
    # NY ceiling is 10.79M; 10M is fine.
    payload["total_workers"] = 10_000_000
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert warnings == []


def test_total_workers_zero():
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = 0
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert any("> 0" in w for w in warnings)


def test_total_workers_negative():
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = -100
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert any("> 0" in w for w in warnings)


def test_total_workers_non_numeric():
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = "lots"
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert any("not numeric" in w for w in warnings)


def test_pct_sum_too_high():
    payload = _plausible_ny_hospitals_payload()
    # Race sums to 110% (overflow distribution).
    payload["race"] = [
        {"code": "1", "label": "White", "pct": 60.0},
        {"code": "2", "label": "Black", "pct": 50.0},
    ]
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert any("race pct sum 110.0%" in w for w in warnings)


def test_pct_sum_too_low():
    payload = _plausible_ny_hospitals_payload()
    # Gender sums to 80% (missing buckets).
    payload["gender"] = [
        {"code": "1", "label": "Male", "pct": 30.0},
        {"code": "2", "label": "Female", "pct": 50.0},
    ]
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert any("gender pct sum 80.0%" in w for w in warnings)


def test_pct_sum_within_3pp_tolerance_no_warning():
    payload = _plausible_ny_hospitals_payload()
    # Rounding noise: gender 50.5 + 47.5 = 98.0% (within 100 +/- 3)
    payload["gender"] = [
        {"code": "1", "label": "Male", "pct": 50.5},
        {"code": "2", "label": "Female", "pct": 47.5},
    ]
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    assert warnings == []


def test_none_payload_returns_empty():
    assert demographics_bounds.assert_demographics_plausible(None) == []


def test_empty_payload_returns_empty():
    assert demographics_bounds.assert_demographics_plausible({}) == []


def test_missing_pct_keys_handled():
    """A dimension where items lack `pct` shouldn't crash."""
    payload = {
        "total_workers": 100_000,
        "gender": [{"code": "1", "label": "Male"}],  # no pct
    }
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY"
    )
    # Should not raise; should not flag pct-sum (no numeric pcts found).
    assert warnings == []


def test_unknown_state_falls_back_to_us_ceiling():
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = 50_000_000  # under US cap, over fictional state
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="ZZ"  # not in our fake ceilings
    )
    # 50M < 188M US cap, so no warning.
    assert warnings == []


def test_context_prefix_in_warnings():
    payload = _plausible_ny_hospitals_payload()
    payload["total_workers"] = 145_000_000
    warnings = demographics_bounds.assert_demographics_plausible(
        payload, state_abbr="NY", context="GET /api/demographics/NY/6111"
    )
    assert all(w.startswith("[GET /api/demographics/NY/6111]") for w in warnings)


def test_log_warnings_no_warnings_no_calls():
    """Empty list shouldn't touch the logger at all."""
    import logging

    class CountingHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.count = 0

        def emit(self, record):
            self.count += 1

    handler = CountingHandler()
    logger = logging.getLogger("test_bounds_no_warn")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    demographics_bounds.log_warnings([], logger)
    assert handler.count == 0

    logger.removeHandler(handler)
