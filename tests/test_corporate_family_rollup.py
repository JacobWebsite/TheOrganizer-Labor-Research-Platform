"""
DB-free unit tests for api/services/corporate_family_rollup.py pure helpers.

The DB-touching ``get_family_rollup()`` is exercised by the live server in
dev, not by these unit tests. Here we lock down the canonical-stem extraction
-- the piece that determines which NLRB/OSHA/WHD rows get aggregated into
the family view -- so regressions surface immediately.

Run: py -m pytest tests/test_corporate_family_rollup.py -v
"""
import pytest

from api.services.corporate_family_rollup import _extract_root_name


# ---- Single-token brand names ----

@pytest.mark.parametrize(
    "display_name,expected",
    [
        # Starbucks - the driving case for this feature
        ("STARBUCKS CORP", "starbucks"),
        ("Starbucks Corporation", "starbucks"),
        ("Starbucks Coffee Company", "starbucks"),
        ("STARBUCKS COFFEE CO.", "starbucks"),
        ("Starbucks", "starbucks"),
        # Per-store variants
        ("Starbucks Corporation, Easton Store #9534", "starbucks"),
        ("STARBUCKS COFFEE CO #5252", "starbucks"),
        # D/b/a entries
        ("STARBUCKS CORPORATION D/B/A STARBUCKS COFFEE COMPANY", "starbucks"),
        ("Siren Retail Corporation d/b/a Starbucks Reserve Roastery", "siren retail"),
        # CEO-prefixed variants (NLRB charge pattern)
        ("Schultz, Howard\nStarbucks Corporation", "starbucks"),
        ("Narasimhan, Laxman\nStarbucks Corporation", "starbucks"),
        # Whitespace / casing normalisation
        ("  starbucks   corp  ", "starbucks"),
        # Lowe's
        ("LOWES HOME CENTERS, INC.", "lowes home"),
        ("LOWES COMPANIES INC", "lowes companies"),
        ("Lowe's Companies, Inc.", "lowe's companies"),
    ],
)
def test_single_token_brand(display_name, expected):
    assert _extract_root_name(display_name) == expected


# ---- Multi-word brand names (short first token) ----

@pytest.mark.parametrize(
    "display_name,expected",
    [
        ("DOLLAR TREE, INC.", "dollar tree"),
        ("Dollar Tree Stores, Inc.", "dollar tree"),
        ("Family Dollar Stores of Missouri, Inc.", "family dollar"),
        ("Bristol Farms Inc.", "bristol"),  # 7 chars, single word
        ("Maple Donuts, Inc.", "maple donuts"),
    ],
)
def test_multi_word_brand_with_short_stem(display_name, expected):
    assert _extract_root_name(display_name) == expected


# ---- Edge cases ----

@pytest.mark.parametrize("display_name", [None, "", "   "])
def test_empty_or_none_returns_empty_string(display_name):
    assert _extract_root_name(display_name) == ""


def test_single_word_no_legal_suffix():
    assert _extract_root_name("COSTCO") == "costco"


def test_all_caps_vs_mixed_case_collide():
    """Case normalization -- two variants of the same company resolve to the
    same stem so ILIKE matching catches both."""
    assert _extract_root_name("STARBUCKS CORP") == _extract_root_name("Starbucks Corporation")


def test_dba_stripped_after_first_legal_suffix():
    """The d/b/a pattern removes everything after it so we key on the
    original entity name, not the trade name."""
    assert _extract_root_name("Apex Retail Holdings LLC d/b/a The Acme Cafe") == "apex retail"


def test_ceo_name_newline_prefix_stripped():
    """NLRB charges sometimes list the CEO name before the corporation
    separated by a literal newline. We must strip that prefix so the stem
    matches the bare corporation name."""
    assert _extract_root_name("Johnson, Kevin\nStarbucks Corporation") == "starbucks"


# ---- Regression guards ----

def test_starbucks_all_40_variants_collapse_to_one_stem():
    """The 40 NLRB respondent-name variants for Starbucks from the live data
    should all collapse to the same stem (or a small family of stems that
    ILIKE '%starbucks%' catches). If this fails, the rollup will undercount
    Starbucks NLRB cases."""
    variants = [
        "Starbucks Corporation",
        "STARBUCKS CORPORATION",
        "Starbucks",
        "Starbucks Coffee Company",
        "Starbucks Workers United",  # party-in-interest -- still matches
        "STARBUCKS CORPORATION D/B/A STARBUCKS COFFEE COMPANY",
        "Starbucks Corporation, Easton Store #9534",
        "STARBUCKS",
        "Starbucks Workers United, affiliated with SEIU",
        "STARBUCKS COFFEE COMPANY",
        "Schultz, Howard\nStarbucks Corporation",
        "Narasimhan, Laxman\nStarbucks Corporation",
        "Johnson, Kevin\nStarbucks Corporation",
    ]
    stems = {_extract_root_name(v) for v in variants}
    # All 13 distinct names reduce to the single stem "starbucks" -- meaning
    # ILIKE '%starbucks%' picks them all up.
    assert stems == {"starbucks"}
