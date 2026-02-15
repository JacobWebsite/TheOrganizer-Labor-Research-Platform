"""
Canonical name normalization helpers for matching pipelines.

Levels:
- standard: conservative cleanup
- aggressive: stronger legal/descriptor stripping
- fuzzy: token-centric form for approximate matching
"""
from __future__ import annotations

import re
import unicodedata


LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "llc",
    "l l c",
    "ltd",
    "limited",
    "lp",
    "llp",
    "pllc",
    "pc",
}

NOISE_TOKENS = {
    "the",
    "of",
    "and",
    "services",
    "service",
    "group",
    "holdings",
    "holding",
    "management",
    "international",
    "national",
}

DBA_PATTERNS = [
    r"\bdba\b.*$",
    r"\bdoing business as\b.*$",
    r"\ba k a\b.*$",
    r"\baka\b.*$",
]


def _ascii_fold(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value)
    return norm.encode("ascii", "ignore").decode("ascii")


def _base_cleanup(name: str) -> str:
    s = _ascii_fold(name or "").lower().strip()
    s = re.sub(r"[&/+]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _remove_dba_tail(s: str) -> str:
    out = s
    for pattern in DBA_PATTERNS:
        out = re.sub(pattern, "", out).strip()
    return out


def normalize_name_standard(name: str) -> str:
    """
    Conservative normalization safe for deterministic exact match passes.
    """
    s = _base_cleanup(name)
    s = _remove_dba_tail(s)
    return s


def normalize_name_aggressive(name: str) -> str:
    """
    Aggressive normalization for deterministic + fuzzy bridge passes.
    """
    s = normalize_name_standard(name)
    tokens = [t for t in s.split() if t not in LEGAL_SUFFIXES and t not in NOISE_TOKENS]
    return " ".join(tokens).strip()


def normalize_name_fuzzy(name: str) -> str:
    """
    Token-sorted form for fuzzy matching (order-insensitive).
    """
    s = normalize_name_aggressive(name)
    tokens = [t for t in s.split() if len(t) > 1]
    # Keep duplicates out to reduce token noise impact
    dedup_sorted = sorted(set(tokens))
    return " ".join(dedup_sorted).strip()

