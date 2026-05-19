"""Tests for scripts/etl/sec_10k/match_extracted_entities_v2.py

The v2 module provides the less-aggressive fallback tier for the 10-K
relationship matcher. These tests exercise its public functions
(`normalize_nonaggressive` and `_match_nonaggressive_exact`) against
both pure-Python and mock-cursor cases.

NO real DB writes are performed -- destructive ops are out of scope
for unit tests, and the production matcher writes to unified_match_log
via `insert_link()` which we are not exercising here.

Run:
    py -m pytest tests/matching/test_nonaggressive_fallback.py -x -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Load the v2 module by path so this test file doesn't require the
# sec_10k package to be a proper Python module (it isn't on master).
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "etl" / "sec_10k" / "match_extracted_entities_v2.py"
)
_spec = importlib.util.spec_from_file_location(
    "match_extracted_entities_v2", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# ============================================================================
# FakeCursor -- a light-weight psycopg2 cursor stand-in driven by a script of
# (sql_keyword, rows) tuples. Mirrors the FakeCursor used in
# tests/etl/sec_10k/test_match_extracted_entities.py.
# ============================================================================
class FakeCursor:
    """Stand-in for a psycopg2 cursor.

    `responses` is a list of return values consumed in order by
    successive execute() calls. Each response is either:
      - a list of rows (returned by fetchall / fetchone)
      - None (no result; e.g. set_limit())
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self._last = None
        self.last_sql = None
        self.last_params = None
        self.description = None
        self.rowcount = 0
        self.executed = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed.append((sql, params))
        if not self._responses:
            self._last = []
        else:
            self._last = self._responses.pop(0)
        if isinstance(self._last, list):
            self.rowcount = len(self._last)
        else:
            self.rowcount = 0
        return self

    def fetchone(self):
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return None

    def fetchall(self):
        if isinstance(self._last, list):
            return list(self._last)
        return []

    def close(self):
        pass


# ============================================================================
# normalize_nonaggressive: pure-Python tests
# ============================================================================

@pytest.mark.parametrize("inp,expected", [
    # Bare names that need NO stripping
    ("booking holdings",            "booking holdings"),
    ("Marzetti Company",            "marzetti company"),

    # Trailing abbreviation expansion (Bug 1 fix, 2026-05-18):
    # `Assoc` at the end expands to `association` so the entity-side
    # form composes with `master_employers.canonical_name` values like
    # "aerospace industries association".
    ("Aerospace Industries Assoc",  "aerospace industries association"),

    # Corporate-suffix stripping (now end-anchored, Bug 2 fix 2026-05-18)
    ("Booking Holdings Inc",        "booking holdings"),
    ("Booking Holdings, Inc.",      "booking holdings"),
    ("Apple Corporation",           "apple"),
    ("Apple Corp",                  "apple"),
    ("Acme LLC",                    "acme"),
    # "L.L.C." -> tokens "l l c" which is multi-token. The less-aggressive
    # normalizer strips only end-anchored suffixes, so "l l c" survives.
    # That's OK because both sides (entity and canonical) go through the
    # same normalizer; symmetry is preserved.
    ("Acme L.L.C.",                 "acme l l c"),
    ("Acme Ltd.",                   "acme"),
    ("Foo PLC",                     "foo"),

    # KEEP content tokens that the aggressive normalizer over-strips.
    # ("Holdings", "Industries", "Services", "Group", "Company",
    # "Holding", "Foundation", "Trust", "Fund" all SURVIVE this step.)
    ("Acme Holdings",       "acme holdings"),
    ("Acme Industries",     "acme industries"),
    ("Acme Services",       "acme services"),
    ("Acme Group",          "acme group"),
    ("Acme Holding",        "acme holding"),
    ("Acme Foundation",     "acme foundation"),

    # Punctuation handling
    ("M&T Bank",                    "m t bank"),
    ("M&T Bank Corporation",        "m t bank"),
    ("AT&T Inc.",                   "at t"),

    # Edge cases: blank, whitespace, all-numeric
    ("",                            ""),
    ("   ",                         ""),

    # Combined suffix removal
    ("Foo Holdings Inc",            "foo holdings"),
    ("Foo Industries Corp",         "foo industries"),
])
def test_normalize_nonaggressive(inp, expected):
    assert mod.normalize_nonaggressive(inp) == expected


def test_normalize_keeps_company_token():
    """`Company` is a content word here -- it must survive the strip.
    Aggressive normalize_name_aggressive() strips it; this less-aggressive
    form does NOT.
    """
    assert mod.normalize_nonaggressive("Marzetti Company") == "marzetti company"
    assert mod.normalize_nonaggressive("Ford Motor Company") == "ford motor company"


def test_normalize_strips_suffix_misspellings():
    """Real-world feeds carry mis-spelled suffixes (Coporation/Coropration).
    The aggressive normalizer's LEGAL_SUFFIXES set includes them so the
    less-aggressive variant should too -- otherwise the same name would
    match at tier-A (aggressive) but not at tier-B (less-aggressive)
    and the cascade would invert.
    """
    assert mod.normalize_nonaggressive("Acme Coporation") == "acme"
    assert mod.normalize_nonaggressive("Acme Coropration") == "acme"
    assert mod.normalize_nonaggressive("Acme Incoporated") == "acme"


# ============================================================================
# Bug 1 (Codex 2026-05-18): trailing abbreviation expansion -- the
# docstring promises `"Aerospace Industries Assoc"` recovers
# `"aerospace industries association"` but the original implementation
# never expanded `assoc -> association`. Tests below verify both the
# happy path AND the "do not over-expand" boundary cases.
# ============================================================================

def test_normalize_expands_trailing_assoc():
    """Brief target: actually uses the abbreviated input form, not the
    full word the original test dodged with.
    """
    assert (
        mod.normalize_nonaggressive("Aerospace Industries Assoc")
        == "aerospace industries association"
    )


def test_normalize_expands_trailing_assoc_with_dot():
    """Real-world Assoc is often written with a trailing dot."""
    assert (
        mod.normalize_nonaggressive("Aerospace Industries Assoc.")
        == "aerospace industries association"
    )


def test_normalize_expands_other_trailing_abbreviations():
    """The expansion table covers the most common 10-K abbreviations."""
    assert mod.normalize_nonaggressive("ABC Intl") == "abc international"
    assert mod.normalize_nonaggressive("Acme Mfg") == "acme manufacturing"
    assert mod.normalize_nonaggressive("Bar Inst") == "bar institute"
    assert mod.normalize_nonaggressive("Baz Assn") == "baz association"


def test_normalize_does_not_over_expand_leading_assoc():
    """Negative test: ``ASSOC Capital`` -- here ``Assoc`` is the company's
    actual name token, not an abbreviation. End-anchored expansion
    prevents over-expansion: only the TRAILING ``assoc`` becomes
    ``association``.
    """
    # Both with and without the suffix to be sure.
    assert mod.normalize_nonaggressive("ASSOC Capital") == "assoc capital"
    assert (
        mod.normalize_nonaggressive("ASSOC Capital Partners LLC")
        == "assoc capital partners"
    )


def test_normalize_does_not_over_expand_mid_name_co():
    """Negative test: ``Co`` mid-name (e.g. ``Coke Co Ltd``). After the
    trailing ``ltd`` strip we have ``coke co`` -- THAT trailing ``co``
    does expand, but a ``co`` in the middle of an unrelated name like
    ``Co Capital LLC`` must NOT expand.
    """
    # Co at end after ltd strip -> "coke company"
    assert mod.normalize_nonaggressive("Coke Co Ltd") == "coke company"
    # Co at start of "Co Capital LLC" -> stripped llc -> "co capital"
    # `co` is not trailing here, so no expansion.
    assert mod.normalize_nonaggressive("Co Capital LLC") == "co capital"


def test_normalize_microsoft_co_does_not_cross_tier_collide():
    """Brief negative: ``Microsoft Co.`` should NOT collide with
    canonical ``Microsoft Corporation`` via this tier.

    Both are normalized via the same function:
        normalize_nonaggressive("Microsoft Co.")        = "microsoft company"
        normalize_nonaggressive("Microsoft Corporation") = "microsoft"
    Different output strings, so the equality match in
    _match_nonaggressive_exact cannot bridge them.

    This regression guards against an over-eager abbreviation table
    that maps ``co -> corporation`` (which WOULD bridge them) -- a
    real risk if someone "fixes" the cross-canonical lookup the wrong
    way.
    """
    entity_form = mod.normalize_nonaggressive("Microsoft Co.")
    canonical_form = mod.normalize_nonaggressive("Microsoft Corporation")
    assert entity_form == "microsoft company"
    assert canonical_form == "microsoft"
    assert entity_form != canonical_form


# ============================================================================
# Bug 2 (Codex 2026-05-18): suffix pattern must be end-anchored.
# Without the `$` anchor, tokens like sa / ag / na / lp / inc / corp
# get stripped from arbitrary positions. Concrete risk: "SA Recycling
# LLC" collapsed to "recycling" and could match unrelated canonicals
# at confidence 1.0.
# ============================================================================

def test_normalize_does_not_strip_sa_at_start():
    """Critical regression: ``SA Recycling LLC`` must keep ``sa`` because
    it sits at the START of the name. Only the trailing ``llc`` strips.
    """
    result = mod.normalize_nonaggressive("SA Recycling LLC")
    assert result == "sa recycling"
    # Belt-and-suspenders: the dangerous collapsed form must NOT appear.
    assert result != "recycling"


def test_normalize_strips_sa_only_when_trailing():
    """Positive trailing-strip case for ``sa``: ``BNP Paribas SA`` ->
    ``bnp paribas``. The same token that survived in
    ``SA Recycling LLC`` IS stripped here because it's trailing.
    """
    assert mod.normalize_nonaggressive("BNP Paribas SA") == "bnp paribas"


def test_normalize_does_not_strip_inc_mid_name():
    """``Inc`` is a corporate suffix, but only at the END. ``Apple Inc
    Holdings`` has ``Inc`` mid-name and ``Holdings`` trailing. Since
    ``Holdings`` is NOT in _CORPORATE_SUFFIXES (kept as a content word
    per design), the trailing strip is a no-op and the result is the
    original cleaned form.
    """
    assert (
        mod.normalize_nonaggressive("Apple Inc Holdings")
        == "apple inc holdings"
    )


def test_normalize_strips_inc_trailing_simple():
    """Positive single-pass case: ``Apple Inc`` -> ``apple``."""
    assert mod.normalize_nonaggressive("Apple Inc") == "apple"


def test_normalize_strips_inc_with_punctuation():
    """``Apple, Inc.`` -> punctuation cleanup leaves ``apple inc``,
    then end-anchored strip drops ``inc``. The final form is ``apple``.
    """
    assert mod.normalize_nonaggressive("Apple, Inc.") == "apple"


def test_normalize_no_strip_short_legal_token_anywhere_but_end():
    """Sweep across the short tokens (sa, ag, na, lp, gp, np, pa, pc,
    bv, nv, pty, pvt) and confirm none get stripped when they appear
    at the START of the name. Without the end-anchor fix, several
    of these would have over-stripped.
    """
    cases = [
        ("SA Recycling LLC", "sa recycling"),
        ("AG Capital LLC",   "ag capital"),
        ("NA Holdings LLC",  "na holdings"),
        ("LP Capital LLC",   "lp capital"),
        ("GP Partners LLC",  "gp partners"),
        ("NP Foundation LLC","np foundation"),
        ("PA Industries LLC","pa industries"),
        ("PC Group LLC",     "pc group"),
        ("BV Holdings LLC",  "bv holdings"),
        ("NV Holdings LLC",  "nv holdings"),
    ]
    for inp, expected in cases:
        actual = mod.normalize_nonaggressive(inp)
        assert actual == expected, (
            f"Over-stripped leading legal token: {inp!r} -> {actual!r} "
            f"(expected {expected!r})"
        )


# ============================================================================
# Bug 2 cross-tier safety: the _match_nonaggressive_exact tier should
# NOT pull through "recycling" as a high-confidence (1.0) match for
# "SA Recycling LLC". The matcher operates on the normalized form,
# so as long as the normalization is correct, the SQL equality match
# is keyed on "sa recycling" -- not the dangerous "recycling".
# ============================================================================

def test_sa_recycling_does_not_collapse_via_tier_match():
    """Regression guard for the matcher itself. Build a FakeCursor
    that WOULD return a master_id IF the SQL was ever called with
    the dangerous form ``"recycling"``. Show that the matcher
    queries with ``"sa recycling"`` instead, so a benign canonical
    that normalizes to ``"recycling"`` cannot tag along.
    """
    cur = FakeCursor([
        # If `_match_nonaggressive_exact` ever queries with "recycling",
        # this row would be returned. The assertion below checks the
        # params actually passed to the cursor.
        [(999, "recycling industries inc")],
    ])
    result = mod._match_nonaggressive_exact("SA Recycling LLC", cur=cur)
    # The actual query is keyed on "sa recycling" -- the FakeCursor
    # is dumb and will still return its row, so we instead assert
    # on `last_params` that the query DID NOT use "recycling".
    assert cur.last_params is not None
    bound_value = cur.last_params[0]
    assert bound_value == "sa recycling", (
        f"matcher bound dangerous form: {bound_value!r}"
    )
    # The function still returns the row (FakeCursor is dumb), but
    # in production the SQL would only return rows whose canonical
    # ALSO normalizes to "sa recycling" -- which "recycling industries
    # inc" does not. Confirm the wire-level safety.
    assert result is not None  # FakeCursor returned a row anyway
    assert result[0] == 999    # the dumb stub


def test_assoc_recovery_via_tier_match():
    """End-to-end: the abbreviated entity_text ``"Aerospace Industries
    Assoc"`` and the canonical ``"aerospace industries association"``
    both normalize to ``"aerospace industries association"`` and the
    equality match succeeds.
    """
    cur = FakeCursor([
        [(505, "aerospace industries association")],
    ])
    result = mod._match_nonaggressive_exact(
        "Aerospace Industries Assoc", cur=cur
    )
    assert result is not None
    master_id, score, tier = result
    assert master_id == 505
    assert score == 1.0
    assert tier == "nonaggressive_exact"
    # And confirm the SQL was keyed on the expanded form.
    assert cur.last_params == ("aerospace industries association",)


# ============================================================================
# _looks_like_company guard
# ============================================================================

@pytest.mark.parametrize("inp,ok", [
    ("Apple Inc",       True),
    ("Booking Holdings",True),
    ("M&T Bank",        True),
    ("",                False),
    ("   ",             False),
    ("12",              False),       # too short
    ("123",             False),       # too short + numeric
    ("12345",           False),       # numeric only
    ("$$$",             False),       # no letters
])
def test_looks_like_company_guard(inp, ok):
    assert mod._looks_like_company(inp) is ok


# ============================================================================
# _match_nonaggressive_exact: the brief's four target cases
# ============================================================================

def test_booking_holdings_matches():
    """Brief target: ``entity_text "Booking Holdings"`` recovers a master
    row whose canonical_name is ``"booking holdings inc"``.

    The cascade applies the less-aggressive normalizer to BOTH sides:
        normalize_nonaggressive("Booking Holdings")     = "booking holdings"
        normalize_nonaggressive("booking holdings inc") = "booking holdings"
        -> equality match
    """
    # FakeCursor returns the master row whose less-aggressive form
    # equals the query's less-aggressive form. The SQL builds the
    # equality on the canonical_name regexp-replace, so the only thing
    # the test needs to provide is a row at the position the query
    # would land.
    cur = FakeCursor([
        [(101, "booking holdings inc")],   # less-aggressive equality hit
    ])
    result = mod._match_nonaggressive_exact("Booking Holdings", cur=cur)
    assert result is not None
    master_id, score, tier = result
    assert master_id == 101
    assert score == 1.0
    assert tier == "nonaggressive_exact"


def test_marzetti_company_matches():
    """Brief target: ``Marzetti Company`` recovers ``master.canonical_name
    = "marzetti company"``. Both sides normalize to "marzetti company"
    (Company is KEPT under the less-aggressive form).
    """
    cur = FakeCursor([
        [(202, "marzetti company")],
    ])
    result = mod._match_nonaggressive_exact("Marzetti Company", cur=cur)
    assert result is not None
    master_id, score, tier = result
    assert master_id == 202
    assert score == 1.0
    assert tier == "nonaggressive_exact"


def test_mt_bank_matches():
    """Brief target: ``M&T Bank`` recovers ``master.canonical_name
    = "m t bank corporation"``. ``&`` becomes space; ``Corporation`` is
    stripped on the canonical side.
    """
    cur = FakeCursor([
        [(303, "m t bank corporation")],
    ])
    result = mod._match_nonaggressive_exact("M&T Bank", cur=cur)
    assert result is not None
    master_id, score, tier = result
    assert master_id == 303
    assert score == 1.0
    assert tier == "nonaggressive_exact"


def test_aerospace_industries_matches():
    """Brief target: ``Aerospace Industries Association`` recovers a
    master row whose canonical_name is the same -- the less-aggressive
    form preserves Industries / Association whereas the aggressive form
    strips Industries.
    """
    cur = FakeCursor([
        [(404, "aerospace industries association")],
    ])
    result = mod._match_nonaggressive_exact(
        "Aerospace Industries Association", cur=cur
    )
    assert result is not None
    master_id, score, tier = result
    assert master_id == 404
    assert tier == "nonaggressive_exact"


# ============================================================================
# Stop-list rejection (don't pull garbage through this tier)
# ============================================================================

def test_rejects_item_4():
    """Inputs like ``"Item 4"`` are 10-K section headers. The upstream
    matcher's ``_STOP_EXACT`` list filters them before this tier runs.
    For this tier in isolation: ``"Item 4"`` passes the
    ``_looks_like_company`` guard (len=6, has letters), but a real DB
    has no master_employer row whose less-aggressive canonical_name
    equals ``"item 4"`` so the function returns None.
    """
    cur = FakeCursor([[]])  # empty result-set response
    result = mod._match_nonaggressive_exact("Item 4", cur=cur)
    assert result is None


def test_rejects_def_14a():
    """SEC filing-type strings should not match. Same as Item 4:
    the upstream stop-list filters them; this tier returns None
    because no master has a matching less-aggressive form.
    """
    cur = FakeCursor([[]])
    result = mod._match_nonaggressive_exact("DEF 14A", cur=cur)
    assert result is None


def test_rejects_empty():
    cur = FakeCursor([])
    assert mod._match_nonaggressive_exact("", cur=cur) is None
    assert cur.executed == []


def test_rejects_short_string():
    """``len(t) < 4`` short-circuits before normalization."""
    cur = FakeCursor([])
    assert mod._match_nonaggressive_exact("ABC", cur=cur) is None
    assert cur.executed == []


def test_rejects_pure_numeric():
    """``isdigit()`` short-circuits."""
    cur = FakeCursor([])
    assert mod._match_nonaggressive_exact("12345", cur=cur) is None
    assert cur.executed == []


def test_rejects_no_db_match():
    """When the SQL returns no rows, the function returns None."""
    cur = FakeCursor([[]])
    result = mod._match_nonaggressive_exact("Some Obscure Co", cur=cur)
    assert result is None


def test_rejects_when_normalization_collapses_to_short():
    """``Inc Inc`` would normalize to empty after suffix stripping; the
    function must reject rather than hit the DB with an empty string.
    """
    cur = FakeCursor([])
    result = mod._match_nonaggressive_exact("Inc Inc", cur=cur)
    assert result is None
    # Length guard fires (post-normalization is "")
    assert cur.executed == []


# ============================================================================
# Cascade-ordering: aggressive tier wins over less-aggressive tier
# ============================================================================

def test_aggressive_form_distinct_from_nonaggressive():
    """Sanity check: for an input where aggressive AND less-aggressive
    both normalize successfully, the two forms are distinct so the
    cascade can prefer the aggressive (Tier A) hit before falling to
    the less-aggressive (new Tier B) form.

    Specifically: ``"Booking Holdings Inc"`` should aggressive-normalize
    to ``"booking"`` but less-aggressive-normalize to ``"booking holdings"``.
    These distinct forms mean Tier A and the new tier are testing
    against genuinely different SQL equality conditions.
    """
    # The less-aggressive form
    assert mod.normalize_nonaggressive("Booking Holdings Inc") == "booking holdings"

    # The aggressive form (imported lazily to keep this test file
    # standalone if the package isn't installed -- on master it IS).
    from src.python.matching.name_normalization import normalize_name_aggressive
    assert normalize_name_aggressive("Booking Holdings Inc") == "booking"

    # The two outputs are not equal -- meaning if the aggressive form
    # already matches a master, the cascade won't get to the new tier.
    assert (
        mod.normalize_nonaggressive("Booking Holdings Inc")
        != normalize_name_aggressive("Booking Holdings Inc")
    )


def test_cascade_ordering_documented_in_module_docstring():
    """Regression guard: keep the module docstring's tier-slot
    explanation in sync with this design. If someone removes the tier
    explanation from the file's __doc__ string we want a test failure.
    """
    doc = mod.__doc__ or ""
    assert "Tier A (exact)" in doc
    assert "Tier C (trigram)" in doc
    # Confirm we tell readers where the new tier slots in.
    assert "BETWEEN" in doc.upper() or "between tier a" in doc.lower()


# ============================================================================
# Return shape contract
# ============================================================================

def test_return_shape_match():
    """When matched, returns a 3-tuple (int, float, str)."""
    cur = FakeCursor([[(7, "any canonical")]])
    result = mod._match_nonaggressive_exact("Apple Holdings", cur=cur)
    assert result is not None
    assert isinstance(result, tuple)
    assert len(result) == 3
    master_id, score, tier = result
    assert isinstance(master_id, int)
    assert isinstance(score, float)
    assert isinstance(tier, str)


def test_return_shape_unmatched():
    """When unmatched, returns plain None (not a tuple of Nones)."""
    cur = FakeCursor([[]])
    result = mod._match_nonaggressive_exact("Some Obscure Co", cur=cur)
    assert result is None


# ============================================================================
# Tie-break: lowest master_id wins
# ============================================================================

def test_tie_break_lowest_master_id():
    """When multiple master rows share the same less-aggressive form,
    return the lowest master_id (matches the main matcher's tier-A and
    tier-C tie-break convention).
    """
    cur = FakeCursor([
        # Two rows tie on the less-aggressive form -- ORDER BY master_id
        # ASC means the LOW id comes first. We return that.
        [(50, "x holdings inc"), (99, "x holdings llc")],
    ])
    result = mod._match_nonaggressive_exact("X Holdings", cur=cur)
    assert result is not None
    master_id, _, _ = result
    assert master_id == 50
