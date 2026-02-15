"""
Integration stubs for adopting canonical name normalization in match pipelines.

These stubs are intentionally non-invasive and can be imported by existing scripts
without changing matching behavior until wiring is complete.
"""
from __future__ import annotations

from dataclasses import dataclass

from .name_normalization import (
    normalize_name_aggressive,
    normalize_name_fuzzy,
    normalize_name_standard,
)


@dataclass(frozen=True)
class NormalizedNameBundle:
    raw: str
    standard: str
    aggressive: str
    fuzzy: str


def build_normalized_bundle(raw_name: str) -> NormalizedNameBundle:
    """
    Return all three normalization levels for downstream deterministic/fuzzy passes.
    """
    return NormalizedNameBundle(
        raw=raw_name or "",
        standard=normalize_name_standard(raw_name or ""),
        aggressive=normalize_name_aggressive(raw_name or ""),
        fuzzy=normalize_name_fuzzy(raw_name or ""),
    )


def choose_name_for_method(bundle: NormalizedNameBundle, method: str) -> str:
    """
    Stub mapping: which normalized string each matcher should consume.
    """
    method_l = (method or "").lower()
    if method_l in {"exact", "deterministic", "geo_exact"}:
        return bundle.standard
    if method_l in {"aggressive_exact", "deterministic_aggressive"}:
        return bundle.aggressive
    if method_l in {"fuzzy", "trigram", "splink"}:
        return bundle.fuzzy
    return bundle.standard

