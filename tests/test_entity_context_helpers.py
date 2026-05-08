"""
DB-free unit tests for api/services/entity_context.py pure helpers.

Run: py -m pytest tests/test_entity_context_helpers.py -v
"""
import pytest

from api.services.entity_context import (
    CONFLICT_THRESHOLD,
    _compute_spread_and_range,
    _decide_display_mode,
    _format_thousands,
)


# ---------- _format_thousands ----------

@pytest.mark.parametrize("n,expected", [
    (None, None),
    (0, "0"),
    (5, "5"),
    (119, "119"),
    (999, "999"),
    (1_000, "1K"),
    (1_500, "1.5K"),
    (9_999, "10K"),             # 9999 -> 10.0K -> stripped to 10K (cleaner)
    (10_000, "10K"),
    (402_000, "402K"),
    (381_482, "381K"),
    (1_000_000, "1M"),
    (2_100_000, "2.1M"),
])
def test_format_thousands(n, expected):
    assert _format_thousands(n) == expected


# ---------- _compute_spread_and_range ----------

def test_spread_both_none():
    out = _compute_spread_and_range(None, None)
    assert out["primary_count"] is None
    assert out["primary_source"] is None
    assert out["range"] is None
    assert out["conflict"]["present"] is False


def test_spread_only_sec():
    out = _compute_spread_and_range(500_000, None)
    assert out["primary_count"] == 500_000
    assert out["primary_source"] == "sec_10k"
    assert out["range"] is None
    assert out["conflict"]["present"] is False


def test_spread_only_mergent():
    out = _compute_spread_and_range(None, 425_000)
    assert out["primary_count"] == 425_000
    assert out["primary_source"] == "mergent_company"
    assert out["range"] is None
    assert out["conflict"]["present"] is False


def test_spread_zero_diff():
    out = _compute_spread_and_range(100, 100)
    assert out["primary_count"] == 100
    assert out["primary_source"] == "sec_10k"  # SEC wins ties
    assert out["range"]["low"] == 100
    assert out["range"]["high"] == 100
    assert out["conflict"]["present"] is False


def test_spread_starbucks_within_threshold():
    """Starbucks-shape: SEC=381K, Mergent=402K, spread ~5.2% -> range shown, no conflict."""
    out = _compute_spread_and_range(381_000, 402_000)
    assert out["primary_count"] == 381_000
    assert out["primary_source"] == "sec_10k"
    assert out["range"] is not None
    assert out["range"]["low"] == 381_000
    assert out["range"]["high"] == 402_000
    assert out["range"]["display"] == "381K\u2013402K"
    assert out["conflict"]["present"] is False


def test_spread_just_below_threshold():
    """24% spread -> range shown (boundary)."""
    out = _compute_spread_and_range(760, 1_000)  # 24% spread
    assert out["range"] is not None
    assert out["conflict"]["present"] is False


def test_spread_exactly_at_threshold():
    """25.0% spread -> conflict (>= threshold, not <)."""
    sec = 750
    mergent = 1000  # 25% spread
    out = _compute_spread_and_range(sec, mergent)
    assert abs(abs(sec - mergent) / max(sec, mergent) - CONFLICT_THRESHOLD) < 1e-9
    assert out["range"] is None
    assert out["conflict"]["present"] is True


def test_spread_beyond_threshold():
    """50% spread -> conflict, no range."""
    out = _compute_spread_and_range(200_000, 500_000)
    assert out["primary_count"] == 200_000  # SEC still wins as primary
    assert out["primary_source"] == "sec_10k"
    assert out["range"] is None
    assert out["conflict"]["present"] is True
    assert out["conflict"]["spread_pct"] == 60.0
    assert set(out["conflict"]["sources_disagreeing"]) == {"sec_10k", "mergent_company"}


def test_spread_mergent_larger():
    """SEC can be smaller than Mergent (e.g., fiscal year drift)."""
    out = _compute_spread_and_range(50_000, 55_000)
    assert out["primary_count"] == 50_000  # SEC wins regardless of magnitude
    assert out["range"]["low"] == 50_000
    assert out["range"]["high"] == 55_000


# ---------- _decide_display_mode ----------

def test_display_mode_starbucks_shape():
    """Multi-unit group + family data -> family_primary."""
    assert _decide_display_mode(
        group_member_count=87, unit_count=119, family_primary_count=381_000
    ) == "family_primary"


def test_display_mode_single_site_hospital():
    """Single-member group, no family data -> unit_primary."""
    assert _decide_display_mode(
        group_member_count=1, unit_count=120, family_primary_count=None
    ) == "unit_primary"


def test_display_mode_no_group_with_family():
    """No group context at all but family data -> family_primary."""
    assert _decide_display_mode(
        group_member_count=None, unit_count=None, family_primary_count=5_000
    ) == "family_primary"


def test_display_mode_no_group_no_family():
    """No group, no family -> unit_primary (degenerate but valid)."""
    assert _decide_display_mode(
        group_member_count=None, unit_count=50, family_primary_count=None
    ) == "unit_primary"


def test_display_mode_multi_unit_but_no_family_data():
    """Multi-unit group with no family data -> unit_primary (we'd otherwise show a null)."""
    assert _decide_display_mode(
        group_member_count=10, unit_count=50, family_primary_count=None
    ) == "unit_primary"


def test_display_mode_single_unit_with_family():
    """Single-unit group (member_count=1) but family data present -> family_primary (unit doesn't dominate)."""
    # Rule: group_member_count > 1 required for family_primary UNLESS unit_count is None.
    # member_count=1 + unit_count=50 + family=5000 -> unit_primary (kept together)
    assert _decide_display_mode(
        group_member_count=1, unit_count=50, family_primary_count=5_000
    ) == "unit_primary"
