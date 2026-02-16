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
