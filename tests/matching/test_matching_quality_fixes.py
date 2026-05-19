"""
Tests for matching-quality fixes shipped on 2026-05-12:

  1. 10-K matcher suffix-stripping asymmetry:
       see Open Problems/10-K Matcher Suffix Stripping Asymmetry.md
       fix: aggressive_form_of_canonical helper + canonical_name_aggressive
       column (DDL in scripts/etl/create_master_employers.sql)

  2. Fuzzy band false-positive defense:
       see Open Problems/Matching FP Rates in Fuzzy Bands.md
       fix: token-overlap gate in scripts/matching/deterministic_matcher
       fuzzy paths (5a RapidFuzz, 5b in-memory trigram, SQL trigram fallback)

These are pure-Python unit tests with no DB dependency. The DB integration
side of the fix is in create_master_employers.sql and is exercised by the
existing master_employers seeding scripts during ETL.

Run with: py -m pytest tests/matching/test_matching_quality_fixes.py -x -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.python.matching.name_normalization import (  # noqa: E402
    aggressive_form_of_canonical,
    canonical_name_aggressive_sql,
    normalize_name_aggressive,
    passes_fuzzy_token_gate,
    token_overlap_ratio,
)


# ============================================================================
# 10-K matcher suffix-stripping asymmetry
# ============================================================================

def test_walmart_inc_and_canonical_form_produce_same_aggressive():
    """
    The Open Problem note's canonical example: "Walmart Inc" is the raw
    entity_text from a 10-K mention; "walmart inc" is what
    master_employers.canonical_name stores (lowercased only). Both must
    produce the same aggressive form so an equality match succeeds.
    """
    raw_entity = "Walmart Inc"
    canonical_db_form = "walmart inc"

    raw_agg = normalize_name_aggressive(raw_entity)
    canonical_agg = aggressive_form_of_canonical(canonical_db_form)

    assert raw_agg == canonical_agg == "walmart", (
        f"Asymmetry not fixed: raw={raw_agg!r}, canonical={canonical_agg!r}"
    )


def test_cleveland_clinic_foundation_canonical_strips_to_cleveland_clinic():
    """Foundation is a legal suffix per LEGAL_SUFFIXES."""
    assert (
        aggressive_form_of_canonical("cleveland clinic foundation")
        == normalize_name_aggressive("Cleveland Clinic Foundation")
        == "cleveland clinic"
    )


def test_noise_token_stripped_consistently():
    """'the' / 'services' / 'group' are NOISE_TOKENS -- removed on both sides."""
    raw = normalize_name_aggressive("The Acme Services Group")
    canonical_form = aggressive_form_of_canonical("the acme services group")
    assert raw == canonical_form == "acme"


@pytest.mark.parametrize("entity_text,canonical_db,expected_agg", [
    # The 5 cases the Open Problem note + 10-K matcher would hit
    ("Walmart Inc",                 "walmart inc",                 "walmart"),
    ("Apple Inc.",                  "apple inc",                   "apple"),
    ("Microsoft Corporation",       "microsoft corporation",       "microsoft"),
    ("ABC Holdings, LLC",           "abc holdings llc",            "abc"),
    ("Cleveland Clinic Foundation", "cleveland clinic foundation", "cleveland clinic"),
])
def test_asymmetric_pairs_now_match(entity_text, canonical_db, expected_agg):
    """Every raw entity_text + DB canonical pair should produce the same
    aggressive output so an equality match succeeds in the 10-K matcher."""
    raw_agg = normalize_name_aggressive(entity_text)
    canonical_agg = aggressive_form_of_canonical(canonical_db)
    assert raw_agg == canonical_agg == expected_agg


def test_empty_input_safe():
    """Helper must not crash on empty/None inputs."""
    assert aggressive_form_of_canonical("") == ""
    assert aggressive_form_of_canonical(None) == ""


def test_aggressive_form_is_idempotent():
    """Calling the helper twice on its own output is a no-op."""
    once = aggressive_form_of_canonical("walmart inc")
    twice = aggressive_form_of_canonical(once)
    assert once == twice == "walmart"


def test_canonical_name_aggressive_sql_emits_pg_expression():
    """SQL helper returns a Postgres expression usable in SELECT/WHERE."""
    sql = canonical_name_aggressive_sql("me.canonical_name")
    # Must reference the input column name
    assert "me.canonical_name" in sql
    # Must use regexp_replace (the suffix/noise stripping primitive)
    assert "regexp_replace" in sql
    # Must use word-boundary anchors (PG-specific \m / \M)
    assert "\\m" in sql and "\\M" in sql
    # Must include common legal suffixes in the alternation
    assert "inc" in sql.lower()
    assert "llc" in sql.lower()
    assert "corp" in sql.lower()


def test_canonical_name_aggressive_sql_default_column_name():
    """Default column reference is just 'canonical_name'."""
    sql = canonical_name_aggressive_sql()
    assert "canonical_name" in sql


def test_canonical_name_aggressive_sql_rejects_injection():
    """SQL injection guard: helper rejects anything that isn't a bare identifier.

    Found-and-fixed by Codex /wrapup crosscheck on 2026-05-18 -- before the
    fix, this helper f-string'd arbitrary input into emitted SQL, which is
    fine for hardcoded literals but unsafe if a future caller ever passed
    request input or config values.
    """
    import pytest
    # Bare column references work
    canonical_name_aggressive_sql("canonical_name")
    canonical_name_aggressive_sql("me.canonical_name")
    canonical_name_aggressive_sql("master_employers.canonical_name")
    # Injection attempts are rejected
    for bad in [
        "canonical_name); DROP TABLE master_employers; --",
        "(SELECT canonical_name FROM master_employers)",
        "canonical_name OR 1=1",
        "canonical_name; SELECT pg_sleep(10)",
        "schema.table.column",  # multi-dot disallowed
        "canonical_name --comment",
        "'canonical_name'",  # quoted identifier
        '"canonical_name"',  # double-quoted
        "",
        " ",
    ]:
        with pytest.raises(ValueError, match="bare column"):
            canonical_name_aggressive_sql(bad)


# ============================================================================
# Fuzzy band false-positive defense (token-overlap gate)
# ============================================================================

def test_token_overlap_perfect():
    """Identical normalized names get overlap 1.0."""
    assert token_overlap_ratio("Walmart Inc", "Walmart Corp") == 1.0


def test_token_overlap_zero_when_disjoint():
    """No shared tokens after normalization -> 0.0."""
    assert token_overlap_ratio("Apple Inc", "Zebra Co") == 0.0


def test_token_overlap_walmart_pharmacy_case():
    """The Open Problem note's flagship example.

    "Walmart" (1 token after normalization) vs "Wal-Mart Pharmacy"
    (3 tokens: wal, mart, pharmacy) shares 0 tokens because the
    aggressive normalizer doesn't merge "Wal-Mart" -> "Walmart". The
    gate's job is to reject this pair when char-trigram similarity is
    suspiciously high.
    """
    overlap = token_overlap_ratio("Walmart", "Wal-Mart Pharmacy")
    assert overlap < 0.5


def test_token_overlap_subset_is_one():
    """When one name's tokens are a strict subset of the other's, the
    ratio is |smaller| / max(|both|) = subset-coverage. We use max() so
    'Cleveland Clinic' vs 'Cleveland Clinic Foundation' returns 1.0
    (the 2-token name is fully inside the 2-token after foundation
    strip).
    """
    # foundation is in LEGAL_SUFFIXES so 'cleveland clinic foundation'
    # -> {cleveland, clinic}. Same as 'cleveland clinic'.
    assert (
        token_overlap_ratio("Cleveland Clinic", "Cleveland Clinic Foundation")
        == 1.0
    )


def test_token_overlap_empty_safe():
    """Empty / None inputs produce 0.0 without raising."""
    assert token_overlap_ratio("", "anything") == 0.0
    assert token_overlap_ratio("anything", "") == 0.0
    assert token_overlap_ratio(None, None) == 0.0


def test_gate_bypasses_above_score_threshold():
    """High-similarity matches (>= 0.90) skip the gate regardless of
    token overlap. Exact-with-typo matches like 'Apple Inc' vs 'Apple
    Inkk' should still be accepted."""
    # Zero token overlap (different tokens) but score is high.
    assert passes_fuzzy_token_gate(
        "Acme Corp", "Acme Holdings", 0.91
    )


def test_gate_rejects_low_score_low_overlap():
    """The Walmart-Pharmacy case: score in the middle band + low token
    overlap = reject."""
    assert not passes_fuzzy_token_gate(
        "Walmart", "Wal-Mart Pharmacy", 0.82
    )


def test_gate_accepts_low_score_high_overlap():
    """Middle-band score with high token overlap is kept (these are the
    matches the gate is NOT trying to filter out -- they're cases like
    'Cleveland Clinic' vs 'Cleveland Clinic Foundation')."""
    assert passes_fuzzy_token_gate(
        "Cleveland Clinic", "Cleveland Clinic Foundation", 0.80
    )


def test_gate_rejects_acme_vs_apex():
    """Realistic FP: 'Acme Corp' vs 'Apex Corp' -- both 4-letter words
    starting with A, ending with -ex/-cme, no shared meaningful tokens
    after suffix-stripping. Score ~0.78 (>= 0.70 floor). Gate rejects."""
    overlap = token_overlap_ratio("Acme Corp", "Apex Corp")
    assert overlap == 0.0
    assert not passes_fuzzy_token_gate("Acme Corp", "Apex Corp", 0.78)


def test_gate_threshold_customizable():
    """Score / overlap thresholds are tunable for experimentation."""
    # Identical pair would pass any reasonable threshold.
    assert passes_fuzzy_token_gate(
        "Walmart Inc", "Walmart Stores", 0.85,
        score_threshold=0.95, overlap_threshold=0.5,
    )


# ============================================================================
# Collapsed-spacing rescue (audit-discovered regression guards)
# ============================================================================
#
# The 2026-05-12 hand-audit found that a naive token-overlap rule
# rejects same-entity pairs with space/hyphen variants. These tests
# guard the collapsed-spacing rescue path that catches them.

def test_collapsed_spacing_amerisource_bergen():
    """'Amerisource Bergen' vs 'AmerisourceBergen Inc' is the same
    company. Token overlap is 0 (different tokens), but the collapsed
    aggressive forms are equal."""
    # Aggressive form drops "Inc"; "amerisourcebergen" == "amerisourcebergen"
    # after space-collapse.
    assert passes_fuzzy_token_gate(
        "Amerisource Bergen", "AmerisourceBergen Inc", 0.76,
    )


def test_collapsed_spacing_hyphenated_corp():
    """'U-NEED-A-ROLL-OFF CORP' vs 'U NEED A ROLLOFF CORP' is the same
    company despite different hyphenation."""
    # Token overlap of these two is partial; the collapsed rescue
    # catches the rest.
    assert passes_fuzzy_token_gate(
        "U-NEED-A-ROLL-OFF CORP", "U NEED A ROLLOFF CORP", 0.75,
    )


def test_collapsed_spacing_does_not_rescue_unrelated():
    """The collapsed-spacing rescue must not over-trigger. 'Acme Corp'
    and 'Apex Corp' have no character-level relation after collapsing
    and must stay rejected."""
    assert not passes_fuzzy_token_gate("Acme Corp", "Apex Corp", 0.78)


def test_collapsed_spacing_prefix_extension_limited():
    """The prefix-extension rescue (one collapsed form is a prefix of
    the other) must reject when the longer one is more than ~1.5x the
    shorter, to avoid accepting things like 'walmart' inside 'walmart
    pharmacy services and a long tail'."""
    short = "walmart"
    # Longer is 4x shorter -> rescue must NOT trigger.
    assert not passes_fuzzy_token_gate(
        short, "walmart very long unrelated supplier mention name", 0.70,
    )


def test_edit_distance_rescue_typo_variant():
    """'Satelite Services' (typo) vs 'Satellite Services' is the same
    company. After noise-stripping 'services', the collapsed forms are
    'satelite' vs 'satellite' -- 1 char of edit distance, length ratio
    8/9 = 0.89. The edit-distance rescue catches this."""
    assert passes_fuzzy_token_gate(
        "Satelite Services Inc", "Satellite Services", 0.73,
    )


def test_edit_distance_rescue_does_not_rescue_short_in_long():
    """The edit-distance rescue must not fire when length ratio is too
    skewed. 'Ford' vs 'Ford Manufacturing Long Tail Inc' would have
    collapsed lengths very different -- rescue stays off."""
    # After stripping noise tokens 'manufacturing'/'tail' aren't in
    # NOISE_TOKENS so they stay; gives us a sufficiently-long target.
    assert not passes_fuzzy_token_gate(
        "Ford", "Ford Manufacturing Heavy Equipment Sector", 0.72,
    )


def test_overlap_threshold_at_0_40_admits_plural_variants():
    """'Lutheran Orphan and Old Folks' vs 'Lutherans Orphans & Old
    Folks Home' shares 2 of 5 tokens after singular/plural stripping
    misses (the normalizer doesn't fold lutheran/lutherans). The
    overlap = 0.40 default lets these plural-variant TPs through."""
    # Both normalize so 'old' and 'folks' are shared.
    assert passes_fuzzy_token_gate(
        "Lutheran Orphan and Old Folks",
        "Lutherans Orphans & Old Folks Home",
        0.74,
    )


# ============================================================================
# Integration with DeterministicMatcher (mocked)
# ============================================================================

def _load_matcher_module():
    """Load deterministic_matcher.py without instantiating the class."""
    path = (
        PROJECT_ROOT / "scripts" / "matching" / "deterministic_matcher.py"
    )
    spec = importlib.util.spec_from_file_location(
        "deterministic_matcher_under_test", path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_matcher_class_exposes_gate_constants():
    """The DeterministicMatcher class must expose the two gate knobs
    so callers / tests can tune them."""
    mod = _load_matcher_module()
    assert hasattr(mod.DeterministicMatcher, "FUZZY_GATE_SCORE_THRESHOLD")
    assert hasattr(mod.DeterministicMatcher, "FUZZY_TOKEN_OVERLAP_MIN")
    assert 0.0 <= mod.DeterministicMatcher.FUZZY_GATE_SCORE_THRESHOLD <= 1.0
    assert 0.0 <= mod.DeterministicMatcher.FUZZY_TOKEN_OVERLAP_MIN <= 1.0


def test_matcher_gate_method_rejects_low_overlap():
    """Use a minimal MagicMock for the conn so we can exercise the
    gate method without touching a real DB."""
    mod = _load_matcher_module()
    matcher = mod.DeterministicMatcher(
        conn=MagicMock(),
        run_id="test_run_2026_05_12",
        source_system="osha",
        dry_run=True,
    )
    # Walmart vs Wal-Mart Pharmacy at 0.82 score is rejected.
    assert not matcher._passes_fuzzy_gate(
        "Walmart", "Wal-Mart Pharmacy", 0.82,
    )
    # Stats counter incremented.
    assert matcher.stats[matcher._GATE_REJECT_KEY] >= 1


def test_matcher_gate_method_accepts_high_score():
    """0.91 score -> bypass gate."""
    mod = _load_matcher_module()
    matcher = mod.DeterministicMatcher(
        conn=MagicMock(),
        run_id="test_run_2026_05_12",
        source_system="osha",
        dry_run=True,
    )
    # Any pair at high enough score passes regardless of token overlap.
    assert matcher._passes_fuzzy_gate("Foo", "Bar Baz Quux", 0.95)
    # Counter should not have been incremented for this call.
    # (Tests run independently so stats start at 0.)
    assert matcher.stats[matcher._GATE_REJECT_KEY] == 0
