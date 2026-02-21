"""
Canonical name normalization helpers for matching pipelines.

This is the SINGLE SOURCE OF TRUTH for name normalization.
All matchers, adapters, and scripts should import from here.

Levels:
- standard: conservative cleanup (safe for exact match)
- aggressive: stronger legal/descriptor stripping
- fuzzy: token-centric form for approximate matching

Phonetic helpers:
- soundex: 4-char phonetic code
- metaphone: more accurate phonetic code
- phonetic_similarity: combined phonetic score
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


# ============================================================================
# Constants
# ============================================================================

LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "corporations",
    "co", "company",
    "llc", "l l c", "ltd", "limited", "lp", "llp", "pllc", "pc",
    "plc", "pa", "na", "sa", "gmbh", "ag", "pty", "pvt", "nv", "bv",
    "gp", "np",
    "trust", "fund", "foundation", "cooperative", "coop",
    "limitedliabilitycompany", "limitedliability",
    # Common misspellings
    "corportation", "coporation", "coropration",
    "incoporated", "incorperated",
}

NOISE_TOKENS = {
    "the", "of", "and",
    "services", "service", "group", "holdings", "holding",
    "management", "international", "national", "global",
    "usa",
    "enterprises", "enterprise", "associates", "partners",
    "industries", "industry",
    "consulting", "consultants",
    "solutions", "solution",
}

DBA_PATTERNS = [
    r"\bd\s*b\s*a\b.*$",          # dba, d b a, d  b  a (after slash removal)
    r"\bdoing business as\b.*$",
    r"\ba\s*k\s*a\b.*$",          # aka, a k a (after slash removal)
]

# Employer abbreviation expansions for aggressive normalization
ABBREVIATIONS = {
    "hosp": "hospital", "med": "medical", "ctr": "center",
    "cntr": "center", "mgmt": "management", "mfg": "manufacturing",
    "intl": "international", "natl": "national", "assn": "association",
    "assoc": "association", "dept": "department", "govt": "government",
    "univ": "university", "tech": "technology", "sys": "systems",
    "svc": "services", "svcs": "services", "dist": "distribution",
    "mktg": "marketing", "comm": "communications", "engr": "engineering",
    "fin": "financial", "ins": "insurance", "transp": "transportation",
    "rehab": "rehabilitation", "pharm": "pharmaceutical",
    "mem": "memorial", "reg": "regional", "genl": "general",
    "gen": "general", "elem": "elementary", "sch": "school",
    "schl": "school", "bldg": "building", "prop": "property",
    "apt": "apartment", "hwy": "highway", "pkwy": "parkway",
    "st": "saint", "mt": "mount", "ft": "fort",
}


# ============================================================================
# Core normalization functions
# ============================================================================

def _ascii_fold(value: str) -> str:
    """Fold unicode to ASCII equivalents."""
    norm = unicodedata.normalize("NFKD", value)
    return norm.encode("ascii", "ignore").decode("ascii")


def _base_cleanup(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = _ascii_fold(name or "").lower().strip()
    s = re.sub(r"[&/+]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _remove_dba_tail(s: str) -> str:
    """Remove DBA/AKA tails."""
    out = s
    for pattern in DBA_PATTERNS:
        out = re.sub(pattern, "", out).strip()
    return out


def normalize_name_standard(name: str) -> str:
    """
    Conservative normalization safe for deterministic exact match passes.
    Lowercases, strips punctuation, removes DBA tails.
    """
    s = _base_cleanup(name)
    s = _remove_dba_tail(s)
    return s


def normalize_name_aggressive(name: str) -> str:
    """
    Aggressive normalization for deterministic + fuzzy bridge passes.
    Strips legal suffixes, noise tokens, expands abbreviations.
    """
    s = normalize_name_standard(name)
    # Expand abbreviations first
    tokens = s.split()
    tokens = [ABBREVIATIONS.get(t, t) for t in tokens]
    # Then remove legal suffixes and noise
    tokens = [t for t in tokens if t not in LEGAL_SUFFIXES and t not in NOISE_TOKENS]
    return " ".join(tokens).strip()


def normalize_name_fuzzy(name: str) -> str:
    """
    Token-sorted form for fuzzy matching (order-insensitive).
    Removes single-char tokens, deduplicates, sorts alphabetically.
    """
    s = normalize_name_aggressive(name)
    tokens = [t for t in s.split() if len(t) > 1]
    dedup_sorted = sorted(set(tokens))
    return " ".join(dedup_sorted).strip()


# ============================================================================
# Phonetic helpers
# ============================================================================

def soundex(name: str) -> str:
    """
    American Soundex algorithm. Returns 4-character phonetic code.

    >>> soundex("Robert")
    'R163'
    >>> soundex("Rupert")
    'R163'
    """
    if not name:
        return ""
    name = _ascii_fold(name).upper().strip()
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""

    code_map = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2",
        "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }

    first = name[0]
    coded = [first]
    prev_code = code_map.get(first, "0")

    for ch in name[1:]:
        c = code_map.get(ch, "0")
        if c != "0" and c != prev_code:
            coded.append(c)
        prev_code = c if c != "0" else prev_code

    result = "".join(coded)
    return (result + "0000")[:4]


def metaphone(name: str) -> str:
    """
    Simple Metaphone algorithm. Returns phonetic code string.

    >>> metaphone("Smith")
    'SM0'
    >>> metaphone("Schmidt")
    'SXMTT'
    """
    if not name:
        return ""
    name = _ascii_fold(name).upper().strip()
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""

    # Drop initial silent letters
    if name[:2] in ("AE", "GN", "KN", "PN", "WR"):
        name = name[1:]

    result = []
    i = 0
    while i < len(name):
        ch = name[i]
        nxt = name[i + 1] if i + 1 < len(name) else ""

        if ch in "AEIOU":
            if i == 0:
                result.append(ch)
        elif ch == "B":
            if not (i == len(name) - 1 and i > 0 and name[i - 1] == "M"):
                result.append("B")
        elif ch == "C":
            if nxt in "EIY":
                result.append("S")
            else:
                result.append("K")
        elif ch == "D":
            if nxt in "GE" and i + 2 < len(name) and name[i + 2] in "EIY":
                result.append("J")
            else:
                result.append("T")
        elif ch == "F":
            result.append("F")
        elif ch == "G":
            if nxt in "EIY":
                result.append("J")
            elif nxt != "H" or (i + 2 < len(name) and name[i + 2] in "AEIOU"):
                if not (i > 0 and name[i - 1] in "DG"):
                    result.append("K")
        elif ch == "H":
            if nxt in "AEIOU" and (i == 0 or name[i - 1] not in "AEIOU"):
                result.append("H")
        elif ch == "J":
            result.append("J")
        elif ch == "K":
            if i == 0 or name[i - 1] != "C":
                result.append("K")
        elif ch == "L":
            result.append("L")
        elif ch == "M":
            result.append("M")
        elif ch == "N":
            result.append("N")
        elif ch == "P":
            if nxt == "H":
                result.append("F")
                i += 1
            else:
                result.append("P")
        elif ch == "Q":
            result.append("K")
        elif ch == "R":
            result.append("R")
        elif ch == "S":
            if nxt == "H" or (nxt == "I" and i + 2 < len(name) and name[i + 2] in "AO"):
                result.append("X")
                i += 1
            else:
                result.append("S")
        elif ch == "T":
            if nxt == "H":
                result.append("0")
                i += 1
            elif nxt == "I" and i + 2 < len(name) and name[i + 2] in "AO":
                result.append("X")
            else:
                result.append("T")
        elif ch == "V":
            result.append("F")
        elif ch == "W":
            if nxt in "AEIOU":
                result.append("W")
        elif ch == "X":
            result.append("KS")
        elif ch == "Y":
            if nxt in "AEIOU":
                result.append("Y")
        elif ch == "Z":
            result.append("S")

        i += 1

    return "".join(result)


def phonetic_similarity(name1: str, name2: str) -> float:
    """
    Phonetic similarity score between two names (0.0 - 1.0).

    Combines Soundex and Metaphone codes. Returns 1.0 if both
    phonetic codes match, 0.5 if one matches, 0.0 if neither.

    >>> phonetic_similarity("Smith", "Smyth")
    1.0
    >>> phonetic_similarity("Apple", "Zebra")
    0.0
    """
    if not name1 or not name2:
        return 0.0

    # Compare word-by-word for multi-word names
    words1 = normalize_name_standard(name1).split()
    words2 = normalize_name_standard(name2).split()

    if not words1 or not words2:
        return 0.0

    # Simple: compare first significant words
    w1 = words1[0] if words1 else ""
    w2 = words2[0] if words2 else ""

    score = 0.0
    if soundex(w1) == soundex(w2):
        score += 0.5
    if metaphone(w1) == metaphone(w2):
        score += 0.5

    return score
