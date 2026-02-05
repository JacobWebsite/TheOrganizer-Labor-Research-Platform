"""
Unified Name Normalization

Wraps the existing name_normalizer.py with a simplified, level-based API.
Provides a single entry point for all normalization needs.
"""

import re
import sys
from pathlib import Path
from typing import Optional

# Add parent paths to import existing normalizer
sys.path.insert(0, str(Path(__file__).parent.parent / "import"))

try:
    from name_normalizer import (
        normalize_employer,
        normalize_employer_aggressive,
        EMPLOYER_ABBREVIATIONS,
        LEGAL_SUFFIXES,
        STOPWORDS,
    )
    HAS_NAME_NORMALIZER = True
except ImportError:
    HAS_NAME_NORMALIZER = False
    # Fallback definitions
    EMPLOYER_ABBREVIATIONS = {}
    STOPWORDS = {'the', 'a', 'an', 'of', 'and', '&'}
    LEGAL_SUFFIXES = [
        r'\bincorporated\b', r'\bcorporation\b', r'\bcompany\b', r'\blimited\b',
        r'\bcorp\b\.?', r'\binc\b\.?', r'\bco\b\.?', r'\bltd\b\.?',
        r'\bllc\b\.?', r'\bllp\b\.?', r'\blp\b\.?', r'\bplc\b\.?',
        r'\bpc\b\.?', r'\bpa\b\.?', r'\bpllc\b\.?',
        r'\bd/?b/?a\b\.?', r'\baka\b\.?', r'\bn/?a\b\.?',
    ]


# Extended abbreviations for aggressive matching
EXTENDED_ABBREVIATIONS = {
    **EMPLOYER_ABBREVIATIONS,
    # Healthcare additions
    'mem': 'memorial',
    'meml': 'memorial',
    'reg': 'regional',
    'regl': 'regional',
    'genl': 'general',
    'gen': 'general',
    # Business
    'svs': 'services',
    'srvcs': 'services',
    'mgr': 'manager',
    'mngr': 'manager',
    'asst': 'assistant',
    'dir': 'director',
    'exec': 'executive',
    # Organizations
    'org': 'organization',
    'orgn': 'organization',
    'inst': 'institute',
    'instit': 'institute',
    'acad': 'academy',
    'schl': 'school',
    'sch': 'school',
    'elem': 'elementary',
    'elem': 'elementary',
    'jr': 'junior',
    'sr': 'senior',
    # Common
    'ntwk': 'network',
    'netwrk': 'network',
    'bldg': 'building',
    'bldgs': 'buildings',
    'prop': 'property',
    'props': 'properties',
    'apt': 'apartment',
    'apts': 'apartments',
}


def normalize_employer_name(name: str, level: str = "standard") -> str:
    """
    Unified employer name normalization with three levels.

    Args:
        name: Raw employer name
        level: Normalization level
            - "standard": lowercase, remove punctuation, strip legal suffixes
            - "aggressive": + expand abbreviations, remove stopwords
            - "fuzzy": + additional cleaning for trigram matching

    Returns:
        Normalized name string

    Examples:
        >>> normalize_employer_name("The Kroger Company, Inc.")
        'kroger'

        >>> normalize_employer_name("St. Mary's Hosp. Med. Ctr.", "aggressive")
        'saint marys hospital medical center'

        >>> normalize_employer_name("A.C.M.E. Corp.", "fuzzy")
        'acme'
    """
    if not name:
        return ""

    if level == "standard":
        return _normalize_standard(name)
    elif level == "aggressive":
        return _normalize_aggressive(name)
    elif level == "fuzzy":
        return _normalize_fuzzy(name)
    else:
        raise ValueError(f"Unknown normalization level: {level}. Use 'standard', 'aggressive', or 'fuzzy'")


def _normalize_standard(name: str) -> str:
    """
    Standard normalization: lowercase, remove punctuation, strip legal suffixes.
    """
    if HAS_NAME_NORMALIZER:
        return normalize_employer(name, expand_abbrevs=False, remove_stopwords=False)

    # Fallback implementation
    result = name.lower().strip()

    # Remove punctuation except hyphens
    result = re.sub(r"[^\w\s\-]", " ", result)

    # Strip legal suffixes
    for suffix in LEGAL_SUFFIXES:
        result = re.sub(suffix, '', result, flags=re.IGNORECASE)

    # Collapse whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def _normalize_aggressive(name: str) -> str:
    """
    Aggressive normalization: expand abbreviations, remove stopwords.
    """
    if HAS_NAME_NORMALIZER:
        return normalize_employer_aggressive(name)

    # Fallback implementation
    result = name.lower().strip()

    # Normalize common variations
    replacements = [
        (r"saint\b", "st"),
        (r"mount\b", "mt"),
        (r"fort\b", "ft"),
        (r"\s*&\s*", " and "),
        (r"\s*\+\s*", " and "),
        (r"'s\b", "s"),
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    # Remove punctuation
    result = re.sub(r"[^\w\s]", " ", result)

    # Strip legal suffixes
    for suffix in LEGAL_SUFFIXES:
        result = re.sub(suffix, '', result, flags=re.IGNORECASE)

    # Expand abbreviations
    words = result.split()
    words = [EXTENDED_ABBREVIATIONS.get(w, w) for w in words]
    result = " ".join(words)

    # Remove stopwords
    words = result.split()
    words = [w for w in words if w not in STOPWORDS and len(w) > 1]
    result = " ".join(words)

    # Collapse whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def _normalize_fuzzy(name: str) -> str:
    """
    Fuzzy normalization: additional cleaning for trigram matching.
    Removes numbers, single letters, and normalizes for best fuzzy results.
    """
    # Start with aggressive normalization
    result = _normalize_aggressive(name)

    # Remove standalone numbers (keep numbers in words like "3m")
    result = re.sub(r'\b\d+\b', '', result)

    # Remove single letters
    words = result.split()
    words = [w for w in words if len(w) > 1]
    result = " ".join(words)

    # Remove common prefixes that don't help matching
    prefixes_to_remove = [
        r'^the\s+',
        r'^a\s+',
        r'^an\s+',
    ]
    for prefix in prefixes_to_remove:
        result = re.sub(prefix, '', result, flags=re.IGNORECASE)

    # Collapse whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def normalize_for_sql(name: str, level: str = "standard") -> str:
    """
    Normalize name and escape for SQL LIKE patterns.

    Args:
        name: Raw employer name
        level: Normalization level

    Returns:
        Normalized name safe for SQL LIKE comparison
    """
    normalized = normalize_employer_name(name, level)
    # Escape SQL wildcards
    normalized = normalized.replace('%', r'\%').replace('_', r'\_')
    return normalized


def generate_name_variants(name: str) -> list:
    """
    Generate multiple normalized variants for matching attempts.

    Returns a list of (level, normalized_name) tuples in order of strictness.
    """
    variants = []

    standard = normalize_employer_name(name, "standard")
    if standard:
        variants.append(("standard", standard))

    aggressive = normalize_employer_name(name, "aggressive")
    if aggressive and aggressive != standard:
        variants.append(("aggressive", aggressive))

    fuzzy = normalize_employer_name(name, "fuzzy")
    if fuzzy and fuzzy != aggressive:
        variants.append(("fuzzy", fuzzy))

    return variants


# ============================================================================
# SQL-BASED NORMALIZATION (for batch operations)
# ============================================================================

NORMALIZE_SQL = """
-- Standard normalization SQL
LOWER(TRIM(
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE({column}, E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\\\\b\\\\.?', '', 'gi'),
                E'\\\\bd/?b/?a\\\\b\\\\.?', '', 'gi'
            ),
            E'[^\\\\w\\\\s]', ' ', 'g'
        ),
        E'\\\\s+', ' ', 'g'
    )
))
"""

NORMALIZE_AGGRESSIVE_SQL = """
-- Aggressive normalization SQL
LOWER(TRIM(
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE({column}, E'\\\\bthe\\\\b', '', 'gi'),
                        E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\\\\b\\\\.?', '', 'gi'
                    ),
                    E'\\\\bd/?b/?a\\\\b\\\\.?', '', 'gi'
                ),
                E'[^\\\\w\\\\s]', ' ', 'g'
            ),
            E'\\\\s+', ' ', 'g'
        ),
        E'^\\\\s+|\\\\s+$', '', 'g'
    )
))
"""


def get_normalize_sql(column: str, level: str = "standard") -> str:
    """
    Get SQL expression for normalizing a column.

    Args:
        column: Column name to normalize
        level: "standard" or "aggressive"

    Returns:
        SQL expression string
    """
    if level == "aggressive":
        return NORMALIZE_AGGRESSIVE_SQL.format(column=column)
    return NORMALIZE_SQL.format(column=column)


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    test_names = [
        "The Kroger Company, Inc.",
        "KROGER CO.",
        "Kroger",
        "St. Mary's Hospital, LLC",
        "Saint Mary's Hosp. Med. Ctr.",
        "A.C.M.E. Corporation",
        "ACME Corp",
        "123 Main Street Store #456",
        "D/B/A Quick Mart",
    ]

    print("=" * 70)
    print("NAME NORMALIZATION TEST")
    print("=" * 70)

    for name in test_names:
        print(f"\nOriginal: {name}")
        print(f"  Standard:   {normalize_employer_name(name, 'standard')}")
        print(f"  Aggressive: {normalize_employer_name(name, 'aggressive')}")
        print(f"  Fuzzy:      {normalize_employer_name(name, 'fuzzy')}")
