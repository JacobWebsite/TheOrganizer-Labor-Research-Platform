import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.python.matching.name_normalization import (  # noqa: E402
    normalize_name_aggressive,
    normalize_name_fuzzy,
    normalize_name_standard,
    soundex,
    metaphone,
    phonetic_similarity,
    ABBREVIATIONS,
    LEGAL_SUFFIXES,
)


# ============================================================================
# Standard normalization
# ============================================================================

def test_standard_keeps_core_tokens():
    assert normalize_name_standard("WAL-MART STORES, INC.") == "wal mart stores inc"


def test_standard_removes_dba_tail():
    assert normalize_name_standard("Acme LLC DBA Midtown Labs") == "acme llc"


def test_standard_handles_empty():
    assert normalize_name_standard("") == ""
    assert normalize_name_standard(None) == ""


def test_standard_strips_punctuation():
    assert normalize_name_standard("O'Brien & Sons, Ltd.") == "o brien sons ltd"


# ============================================================================
# Aggressive normalization
# ============================================================================

def test_aggressive_removes_legal_suffixes():
    result = normalize_name_aggressive("Acme Corporation, LLC")
    assert "corporation" not in result
    assert "llc" not in result
    assert "acme" in result


def test_aggressive_removes_common_noise_tokens():
    result = normalize_name_aggressive("The Acme Services Group")
    assert result == "acme"


def test_aggressive_expands_abbreviations():
    result = normalize_name_aggressive("St. Mary's Hosp. Med. Ctr.")
    assert "hospital" in result
    assert "medical" in result
    assert "center" in result


def test_aggressive_expands_mfg():
    result = normalize_name_aggressive("ABC Mfg. Co.")
    assert "manufacturing" in result
    assert "co" not in result.split()


# ============================================================================
# Fuzzy normalization
# ============================================================================

def test_fuzzy_is_order_insensitive():
    a = normalize_name_fuzzy("Global Logistics Partners")
    b = normalize_name_fuzzy("Partners Global Logistics")
    assert a == b


def test_fuzzy_ascii_folds():
    # "internacional" is not in NOISE_TOKENS (only "international" is)
    assert normalize_name_fuzzy("Caf\u00e9 Internacional, Inc.") == "cafe internacional"


def test_fuzzy_removes_single_char_tokens():
    result = normalize_name_fuzzy("A B C Manufacturing")
    assert "a" not in result.split()
    assert "manufacturing" in result


# ============================================================================
# Soundex
# ============================================================================

def test_soundex_basic():
    assert soundex("Robert") == "R163"
    assert soundex("Rupert") == "R163"


def test_soundex_similar_names():
    assert soundex("Smith") == soundex("Smyth")


def test_soundex_empty():
    assert soundex("") == ""
    assert soundex("   ") == ""


def test_soundex_different_names():
    assert soundex("Apple") != soundex("Zebra")


# ============================================================================
# Metaphone
# ============================================================================

def test_metaphone_basic():
    code = metaphone("Smith")
    assert len(code) > 0


def test_metaphone_silent_prefix():
    # KN -> N
    assert metaphone("Knight")[0] == "N"


def test_metaphone_ph():
    # PH -> F
    code = metaphone("Phone")
    assert "F" in code


def test_metaphone_empty():
    assert metaphone("") == ""


# ============================================================================
# Phonetic similarity
# ============================================================================

def test_phonetic_similar_names():
    score = phonetic_similarity("Smith", "Smyth")
    assert score >= 0.5


def test_phonetic_different_names():
    score = phonetic_similarity("Apple", "Zebra")
    assert score == 0.0


def test_phonetic_empty():
    assert phonetic_similarity("", "test") == 0.0
    assert phonetic_similarity("test", "") == 0.0


# ============================================================================
# Constants validation
# ============================================================================

def test_abbreviations_has_common_entries():
    assert "hosp" in ABBREVIATIONS
    assert "med" in ABBREVIATIONS
    assert "mfg" in ABBREVIATIONS
    assert "intl" in ABBREVIATIONS


def test_legal_suffixes_has_common_entries():
    assert "inc" in LEGAL_SUFFIXES
    assert "llc" in LEGAL_SUFFIXES
    assert "corp" in LEGAL_SUFFIXES


# ============================================================================
# Expanded normalization tests (Layer 1 improvements)
# ============================================================================

def test_plural_suffixes():
    """'ABC Corporations' normalizes same as 'ABC Corporation'."""
    assert normalize_name_aggressive("ABC Corporations") == normalize_name_aggressive("ABC Corporation")


def test_misspellings():
    """Common corporate misspellings normalize to same result."""
    base = normalize_name_aggressive("ABC Corporation")
    assert normalize_name_aggressive("ABC Corportation") == base
    assert normalize_name_aggressive("ABC Coporation") == base
    assert normalize_name_aggressive("ABC Coropration") == base


def test_dba_space_separated():
    """'d/b/a' (which becomes 'd b a' after cleanup) strips DBA portion."""
    result = normalize_name_standard("Acme Corp d/b/a Midtown Labs")
    assert "midtown" not in result
    assert "acme" in result


def test_aka_space_separated():
    """'a/k/a' (which becomes 'a k a' after cleanup) strips AKA portion."""
    result = normalize_name_standard("Acme Corp a/k/a Midtown Labs")
    assert "midtown" not in result
    assert "acme" in result


def test_noise_tokens_expanded():
    """Expanded noise tokens are properly stripped."""
    result = normalize_name_aggressive("ABC Holdings USA")
    assert result == "abc"

    result = normalize_name_aggressive("XYZ Enterprises International")
    assert result == "xyz"


def test_abbreviation_expansions():
    """Abbreviations expand, then noise tokens strip the expansions."""
    # "svcs" expands to "services", then "services" is a noise token -> removed
    result = normalize_name_aggressive("ABC Svcs")
    assert result == "abc"

    # "mgmt" -> "management" (noise), "group" (noise) -> just "xyz"
    result = normalize_name_aggressive("XYZ Mgmt Group")
    assert result == "xyz"


def test_cooperative_suffix():
    """'cooperative' and 'coop' are treated as legal suffixes."""
    result = normalize_name_aggressive("Workers Cooperative")
    assert "cooperative" not in result
    assert "workers" in result

    result = normalize_name_aggressive("Food Coop Inc")
    assert "coop" not in result
    assert "food" in result


def test_trust_foundation_suffixes():
    """'trust' and 'foundation' are treated as legal suffixes."""
    result = normalize_name_aggressive("Smith Family Trust")
    assert "trust" not in result

    result = normalize_name_aggressive("Gates Foundation")
    assert "foundation" not in result
