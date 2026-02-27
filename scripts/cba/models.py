"""Shared dataclasses for the CBA rule-engine pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageSpan:
    """Character offset range for a single page."""
    page_number: int
    char_start: int
    char_end: int


@dataclass
class DocumentText:
    """Full text extracted from a PDF with per-page char offsets."""
    text: str
    page_count: int
    spans: list[PageSpan]


@dataclass
class ContractMetadata:
    """Party and date information extracted from the first pages."""
    employer_name: str | None = None
    union_name: str | None = None
    local_number: str | None = None
    effective_date: str | None = None
    expiration_date: str | None = None
    state: str | None = None
    city: str | None = None
    bargaining_unit: str | None = None


@dataclass
class ArticleChunk:
    """A structural chunk (article or section) from the contract."""
    number: str  # "12" or "XII" or "3.4"
    title: str  # heading text
    level: int  # 1=article, 2=section, 3=subsection
    text: str  # full body text of this chunk
    char_start: int
    char_end: int
    page_start: int | None = None
    page_end: int | None = None
    parent_number: str | None = None  # parent article number for sections
    children: list[ArticleChunk] = field(default_factory=list)


@dataclass
class RuleMatch:
    """A single rule-engine match against contract text."""
    provision_class: str
    category: str
    matched_text: str
    char_start: int
    char_end: int
    confidence: float
    modal_verb: str | None = None
    legal_weight: float | None = None
    rule_name: str | None = None
    article_reference: str | None = None
    summary: str | None = None
