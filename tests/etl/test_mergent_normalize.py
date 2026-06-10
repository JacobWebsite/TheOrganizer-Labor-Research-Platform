"""Regression tests for the Mergent loader normalize_name() str.replace bug.

Bug introduced 2026-05-03 (commit fe0667b). Reproduced bit-exactly:
  "PFIZER PRODUCTS CORPORATION" -> "pfizer productsoration"   (BUG)
  "KROGER COMPANY"              -> "krogermpany"               (BUG)
  "PFIZER H.C.P. CORPORATION"   -> "pfizer hcporation"         (BUG)

Root cause: str.replace() iterating legal suffixes in wrong order with no
word boundaries. " corp" matched the leading-space + "corp" inside
" corporation", leaving "oration" glued to the prior token.

Fixed 2026-05-18 by routing both Mergent loaders through
src.python.matching.name_normalization.normalize_name_legal_suffixes_only,
which is token-based (split + filter LEGAL_SUFFIXES set), so substring
collisions are impossible by construction.

Blast radius: ~19,140 corrupt master_employers.canonical_name rows +
~20,297 mergent_employers.company_name_normalized rows. See
`Open Problems/Pfizer Master Canonical Name Corruption.md` and the
back-fill migration at
`scripts/maintenance/backfill_pfizer_canonical_corruption.py`.
"""
import re
import sys
from pathlib import Path


# Ensure project root is on path before any project import.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from src.python.matching.name_normalization import (  # noqa: E402
    normalize_name_legal_suffixes_only,
)


# ============================================================================
# Loader normalize_name() — the live function callers use
# ============================================================================

def _load_universal_normalize_name():
    """Import normalize_name from load_mergent_universal.

    Safe: load_mergent_universal.py has an `if __name__ == "__main__"` guard.
    """
    from scripts.etl.load_mergent_universal import normalize_name  # noqa: E402
    return normalize_name


def _load_al_fl_normalize_name():
    """Read the normalize_name source from load_mergent_al_fl and exec it.

    Direct import is unsafe -- load_mergent_al_fl.py lacks an
    `if __name__ == "__main__"` guard and would run the full DB-touching
    loader on import. We extract the function via AST so the test stays
    DB-free.
    """
    import ast
    al_fl_path = ROOT / "scripts" / "etl" / "load_mergent_al_fl.py"
    source = al_fl_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "normalize_name":
            # Build a minimal module env containing only what the function needs.
            # The current implementation needs `pd` (pandas) and the function-local
            # import resolves at call time. We also need re, which is imported at
            # module top.
            import pandas as pd
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {"pd": pd}
            exec(  # noqa: S102 — controlled exec of project source for AST isolation
                compile(mod, filename=str(al_fl_path), mode="exec"), ns,
            )
            return ns["normalize_name"]
    raise RuntimeError("normalize_name not found in load_mergent_al_fl.py")


@pytest.fixture(scope="module")
def universal_normalize_name():
    return _load_universal_normalize_name()


@pytest.fixture(scope="module")
def al_fl_normalize_name():
    return _load_al_fl_normalize_name()


# ============================================================================
# Bit-exact bug regressions (must produce the FIXED output, not the buggy one)
# ============================================================================

KNOWN_BAD_INPUTS = [
    # (input, fixed output)
    ("PFIZER PRODUCTS CORPORATION",                       "pfizer products"),
    ("KROGER COMPANY",                                    "kroger"),
    ("PFIZER H.C.P. CORPORATION",                         "pfizer h c p"),
    ("BUFFALO FELT PRODUCTS CORPORATION",                 "buffalo felt products"),
    ("SWISS RE FINANCIAL PRODUCTS CORPORATION",           "swiss re financial products"),
    ("XYZ HOLDINGS CORPORATION",                          "xyz holdings"),
    ("ABC TECHNOLOGIES CORPORATION",                      "abc technologies"),
    ("STEEL INDUSTRIES CORPORATION",                      "steel industries"),
    ("BANANA GROUP CORPORATION",                          "banana group"),
    ("BOEING SYSTEMS CORPORATION",                        "boeing systems"),
    ("SCHAEFER PLUMBING SUPPLY COMPANY, INCORPORATED",    "schaefer plumbing supply"),
    ("TARGET CORPORATION",                                "target"),
    ("CINTAS CORPORATION",                                "cintas"),
    ("APPLE INC",                                         "apple"),
    ("BERKSHIRE HATHAWAY INC",                            "berkshire hathaway"),
]

# The corruption pattern the back-fill migration searches for. Any output
# matching this regex is still corrupt.
CORRUPTION_REGEX = re.compile(
    r"(soration|mpany|orporated|holdingsoration|hcporation)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("raw,expected", KNOWN_BAD_INPUTS)
def test_universal_no_longer_produces_bug(universal_normalize_name, raw, expected):
    """load_mergent_universal.normalize_name produces sane output for known-bad inputs."""
    out = universal_normalize_name(raw)
    assert out == expected, f"got {out!r}, expected {expected!r}"


@pytest.mark.parametrize("raw,expected", KNOWN_BAD_INPUTS)
def test_al_fl_no_longer_produces_bug(al_fl_normalize_name, raw, expected):
    """load_mergent_al_fl.normalize_name produces sane output for known-bad inputs."""
    out = al_fl_normalize_name(raw)
    assert out == expected, f"got {out!r}, expected {expected!r}"


@pytest.mark.parametrize("raw,_expected", KNOWN_BAD_INPUTS)
def test_universal_output_does_not_match_corruption_regex(
    universal_normalize_name, raw, _expected
):
    out = universal_normalize_name(raw)
    assert out is not None
    assert not CORRUPTION_REGEX.search(out), (
        f"output {out!r} still matches corruption regex"
    )


# ============================================================================
# Specific bug demonstrations (the exact named cases from the design doc)
# ============================================================================

def test_pfizer_products_corporation_pfizer_master_157650(universal_normalize_name):
    """master_id=157650, the headline case from the Open Problem note."""
    assert universal_normalize_name("PFIZER PRODUCTS CORPORATION") == "pfizer products"
    # AND should NOT contain the "productsoration" corruption marker.
    assert "oration" not in universal_normalize_name("PFIZER PRODUCTS CORPORATION")


def test_pfizer_hcp_corporation_master_1987063(universal_normalize_name):
    """master_id=1987063, double-period H.C.P. corruption."""
    assert universal_normalize_name("PFIZER H.C.P. CORPORATION") == "pfizer h c p"
    assert "hcporation" not in universal_normalize_name("PFIZER H.C.P. CORPORATION")


def test_kroger_company_18403_row_blast(universal_normalize_name):
    """KROGER COMPANY = canonical example of the 18,403-row `%mpany%` blast."""
    assert universal_normalize_name("KROGER COMPANY") == "kroger"
    assert "mpany" not in universal_normalize_name("KROGER COMPANY")


# ============================================================================
# Overreach guards: legitimate words containing suffix-like substrings stay safe
# ============================================================================

def test_restoration_hardware_token_not_stripped(universal_normalize_name):
    """'restoration' is a real token (not a legal suffix). Must be preserved."""
    out = universal_normalize_name("RESTORATION HARDWARE INC")
    assert "restoration" in out
    assert out == "restoration hardware"


def test_exploration_geosciences_token_not_stripped(universal_normalize_name):
    """'exploration' contains the substring 'oration' but is a real token."""
    out = universal_normalize_name("EXPLORATION GEOSCIENCES INC")
    assert "exploration" in out
    assert out == "exploration geosciences"


def test_celebration_foods_token_not_stripped(universal_normalize_name):
    """'celebration' contains 'oration' substring."""
    out = universal_normalize_name("CELEBRATION FOODS LLC")
    assert out == "celebration foods"


def test_corporate_word_not_stripped(universal_normalize_name):
    """'corporate' is not in LEGAL_SUFFIXES (only 'corp'/'corporation'/'corporations')."""
    out = universal_normalize_name("CORPORATE EXECUTIVE BOARD COMPANY")
    # 'company' IS in LEGAL_SUFFIXES so it should be stripped.
    # 'corporate' should be preserved.
    assert "corporate" in out
    assert out == "corporate executive board"


def test_booking_holdings_distinguishing_token_preserved(universal_normalize_name):
    """'holdings' is a NOISE_TOKEN but distinguishing for some companies.

    normalize_name_aggressive would drop it; the loader normalizer must NOT.
    """
    out = universal_normalize_name("BOOKING HOLDINGS")
    assert out == "booking holdings"


def test_marathon_group_preserved(universal_normalize_name):
    """'group' is a NOISE_TOKEN but we preserve it in loader normalization."""
    out = universal_normalize_name("MARATHON OIL GROUP INC")
    assert "group" in out


# ============================================================================
# Edge cases
# ============================================================================

def test_none_returns_none(universal_normalize_name):
    assert universal_normalize_name(None) is None


def test_empty_returns_none(universal_normalize_name):
    assert universal_normalize_name("") is None


def test_whitespace_only_returns_none_or_empty(universal_normalize_name):
    out = universal_normalize_name("   ")
    # Either None or empty string is acceptable; both indicate "nothing to canonicalize".
    assert out in (None, "")


def test_numpy_nan_returns_none(universal_normalize_name):
    """np.nan is the actual NaN sentinel pandas DataFrame iteration yields."""
    import numpy as np
    assert universal_normalize_name(np.nan) is None


def test_float_nan_returns_none(universal_normalize_name):
    """float('nan') is what `not name` short-circuits on."""
    assert universal_normalize_name(float("nan")) is None


def test_universal_and_al_fl_agree(universal_normalize_name, al_fl_normalize_name):
    """Both loaders must produce IDENTICAL output (they delegate to the same canonical fn)."""
    for raw, _ in KNOWN_BAD_INPUTS:
        u = universal_normalize_name(raw)
        f = al_fl_normalize_name(raw)
        assert u == f, f"divergence for {raw!r}: universal={u!r}, al_fl={f!r}"


# ============================================================================
# Direct test of the canonical normalizer (in case import path changes)
# ============================================================================

@pytest.mark.parametrize("raw,expected", KNOWN_BAD_INPUTS)
def test_canonical_normalizer_directly(raw, expected):
    """normalize_name_legal_suffixes_only must produce the same output as
    the loader delegates to."""
    assert normalize_name_legal_suffixes_only(raw) == expected
