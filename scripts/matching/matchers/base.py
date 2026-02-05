"""
Base classes and data structures for matchers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class MatchResult:
    """
    Result of a single employer match attempt.

    Attributes:
        source_id: ID from source table
        source_name: Original name from source
        target_id: ID from target table (None if no match)
        target_name: Matched name from target (None if no match)
        score: Match confidence score 0.0-1.0
        method: Matching method used ("EIN", "NORMALIZED", "AGGRESSIVE", "FUZZY")
        tier: Matching tier (1-4)
        confidence: Confidence level ("HIGH", "MEDIUM", "LOW")
        matched: Whether a match was found
        metadata: Additional match metadata
    """
    source_id: Any
    source_name: str
    target_id: Optional[Any] = None
    target_name: Optional[str] = None
    score: float = 0.0
    method: str = ""
    tier: int = 0
    confidence: str = ""
    matched: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_id": str(self.source_id),
            "source_name": self.source_name,
            "target_id": str(self.target_id) if self.target_id else None,
            "target_name": self.target_name,
            "score": round(self.score, 4),
            "method": self.method,
            "tier": self.tier,
            "confidence": self.confidence,
            "matched": self.matched,
            "metadata": self.metadata,
        }


@dataclass
class MatchRunStats:
    """
    Statistics for a matching run.
    """
    scenario: str
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_source: int = 0
    total_matched: int = 0
    match_rate: float = 0.0
    by_tier: Dict[int, int] = field(default_factory=dict)
    by_method: Dict[str, int] = field(default_factory=dict)
    results: List["MatchResult"] = field(default_factory=list)

    def finalize(self):
        """Calculate final statistics."""
        if self.total_source > 0:
            self.match_rate = (self.total_matched / self.total_source) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_source": self.total_source,
            "total_matched": self.total_matched,
            "match_rate": round(self.match_rate, 2),
            "by_tier": self.by_tier,
            "by_method": self.by_method,
        }


class BaseMatcher(ABC):
    """
    Abstract base class for matchers.

    Each matcher implements a specific matching strategy (EIN, normalized, fuzzy, etc.)
    """

    def __init__(self, conn, config):
        """
        Initialize matcher.

        Args:
            conn: Database connection
            config: MatchConfig instance
        """
        self.conn = conn
        self.config = config
        self.tier: int = 0
        self.method: str = ""

    @abstractmethod
    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """
        Attempt to match a single source record.

        Args:
            source_id: Source record ID
            source_name: Source employer name
            state: Optional state filter
            city: Optional city filter
            ein: Optional EIN for matching
            address: Optional street address for tier 3 matching

        Returns:
            MatchResult if matched, None otherwise
        """
        pass

    @abstractmethod
    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """
        Match multiple source records.

        Args:
            source_records: List of dicts with source record data

        Returns:
            List of MatchResult objects
        """
        pass

    def _create_result(self, source_id: Any, source_name: str,
                       target_id: Any = None, target_name: str = None,
                       score: float = 0.0, metadata: Dict = None) -> MatchResult:
        """
        Helper to create a consistent MatchResult.
        """
        from ..config import TIER_NAMES, CONFIDENCE_LEVELS

        return MatchResult(
            source_id=source_id,
            source_name=source_name,
            target_id=target_id,
            target_name=target_name,
            score=score,
            method=self.method,
            tier=self.tier,
            confidence=CONFIDENCE_LEVELS.get(self.tier, "LOW"),
            matched=target_id is not None,
            metadata=metadata or {},
        )
