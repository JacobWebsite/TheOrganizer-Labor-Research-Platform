"""
Matcher implementations for the unified matching pipeline.
"""

from .base import MatchResult, BaseMatcher
from .exact import EINMatcher, NormalizedMatcher, AggressiveMatcher
from .fuzzy import TrigramMatcher

__all__ = [
    'MatchResult',
    'BaseMatcher',
    'EINMatcher',
    'NormalizedMatcher',
    'AggressiveMatcher',
    'TrigramMatcher',
]
