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
    ("Aerospace Industries Assoc",  "aerospace industries assoc"),
    ("Marzetti Company",            "marzetti company"),

    # Corporate-suffix stripping
    ("Booking Holdings Inc",        "booking holdings"),
    ("Booking Holdings, Inc.",      "booking holdings"),
    ("Apple Corporation",           "apple"),
    ("Apple Corp",                  "apple"),
    ("Acme LLC",                    "acme"),
    # "L.L.C." -> tokens "l l c" which is multi-token. The less-aggressive
    # normalizer strips only word-anchored suffixes, so "l l c" survives.
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
