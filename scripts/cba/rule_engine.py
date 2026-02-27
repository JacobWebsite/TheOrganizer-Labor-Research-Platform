"""Core rule-based matching engine for CBA provision categorization.

Loads rule JSON files from config/cba_rules/ and matches them against
contract text chunks. Two-pass matching: heading signals then text patterns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.cba.models import ArticleChunk, RuleMatch

RULES_DIR = Path(__file__).resolve().parents[2] / "config" / "cba_rules"

# Modal verb -> legal weight mapping
MODAL_WEIGHTS = {
    "shall": 0.90,
    "must": 0.90,
    "shall not": 0.95,
    "must not": 0.95,
    "will": 0.80,
    "will not": 0.85,
    "may": 0.40,
    "may not": 0.60,
}
MODAL_RE = re.compile(
    r"\b(shall not|must not|will not|may not|shall|must|will|may)\b",
    re.IGNORECASE,
)

# Fix 1: TOC/Index detection — dotted-line pattern signature
TOC_INDEX_RE = re.compile(r"\.{4,}|·{4,}|\.\s*\.\s*\.\s*\.|\bSubject\s+Page\b")
# Fraction of total pages to skip at start (TOC) and end (Index)
TOC_PAGE_FRACTION = 0.05
INDEX_PAGE_FRACTION = 0.03


@dataclass
class HeadingSignal:
    pattern: str
    weight: float
    _compiled: re.Pattern | None = field(default=None, repr=False, compare=False)

    def compiled(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled


@dataclass
class TextPattern:
    name: str
    pattern: str
    confidence: float
    provision_class: str
    summary: str | None = None
    _compiled: re.Pattern | None = field(default=None, repr=False, compare=False)

    def compiled(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled


@dataclass
class NegativePattern:
    pattern: str
    note: str = ""
    _compiled: re.Pattern | None = field(default=None, repr=False, compare=False)

    def compiled(self) -> re.Pattern:
        if self._compiled is None:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled


@dataclass
class CategoryRules:
    category: str
    provision_classes: list[str]
    heading_signals: list[HeadingSignal]
    text_patterns: list[TextPattern]
    negative_patterns: list[NegativePattern]


def is_toc_or_index_text(text: str) -> bool:
    """Check if a text block looks like a Table of Contents or Index entry."""
    return bool(TOC_INDEX_RE.search(text))


def filter_toc_index_chunks(
    chunks: list[ArticleChunk], total_pages: int | None = None
) -> list[ArticleChunk]:
    """Remove chunks that fall in TOC/Index page ranges or contain TOC signatures.

    Fix 1: Eliminates false positives from Table of Contents and Index pages.
    Uses both page-range heuristic and dotted-line content detection.
    """
    filtered = []
    for chunk in chunks:
        # Page-range filter: skip first ~5% and last ~3% of pages
        if total_pages and chunk.page_start is not None:
            toc_cutoff = max(int(total_pages * TOC_PAGE_FRACTION), 2)
            index_cutoff = total_pages - max(int(total_pages * INDEX_PAGE_FRACTION), 1)
            if chunk.page_start <= toc_cutoff or chunk.page_start >= index_cutoff:
                # Also check content — some early/late pages are real content
                if is_toc_or_index_text(chunk.text):
                    continue
        # Content-based filter: skip any chunk whose text has TOC signatures
        if is_toc_or_index_text(chunk.text):
            continue
        filtered.append(chunk)
    return filtered


def load_category_rules(category: str) -> CategoryRules | None:
    """Load rules for a single category from its JSON file."""
    rule_path = RULES_DIR / f"{category}.json"
    if not rule_path.exists():
        return None
    return _parse_rule_file(rule_path)


def load_all_rules() -> list[CategoryRules]:
    """Load all rule files from config/cba_rules/."""
    rules = []
    if not RULES_DIR.exists():
        return rules
    for path in sorted(RULES_DIR.glob("*.json")):
        parsed = _parse_rule_file(path)
        if parsed:
            rules.append(parsed)
    return rules


def _parse_rule_file(path: Path) -> CategoryRules | None:
    """Parse a single rule JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    return CategoryRules(
        category=data.get("category", path.stem),
        provision_classes=data.get("provision_classes", []),
        heading_signals=[
            HeadingSignal(pattern=s["pattern"], weight=s.get("weight", 0.3))
            for s in data.get("heading_signals", [])
        ],
        text_patterns=[
            TextPattern(
                name=p["name"],
                pattern=p["pattern"],
                confidence=p.get("confidence", 0.75),
                provision_class=p.get("provision_class", data.get("provision_classes", [""])[0]),
                summary=p.get("summary"),
            )
            for p in data.get("text_patterns", [])
        ],
        negative_patterns=[
            NegativePattern(pattern=n["pattern"], note=n.get("note", ""))
            for n in data.get("negative_patterns", [])
        ],
    )


def score_heading(title: str, rules: CategoryRules) -> float:
    """Score a heading title against heading signals. Returns 0-1."""
    if not title:
        return 0.0
    total = 0.0
    for signal in rules.heading_signals:
        if signal.compiled().search(title):
            total += signal.weight
    return min(total, 1.0)


def match_chunk(
    chunk: ArticleChunk,
    rules: CategoryRules,
    *,
    min_confidence: float = 0.50,
) -> list[RuleMatch]:
    """Run a category's rules against a single text chunk.

    Two-pass matching:
    1. Score the heading for topic relevance (heading_boost)
    2. Scan text for pattern matches, boosting confidence if heading matched
    """
    heading_score = score_heading(chunk.title, rules)
    heading_boost = 0.10 if heading_score >= 0.3 else 0.0

    # Split chunk text into paragraphs (double newline or 2+ blank lines)
    paragraphs = _split_paragraphs(chunk.text)
    matches: list[RuleMatch] = []

    for para_text, para_offset in paragraphs:
        # Check negative patterns first
        if _is_negative(para_text, rules):
            continue

        for tp in rules.text_patterns:
            m = tp.compiled().search(para_text)
            if not m:
                continue

            # Extract the matching sentence/context
            matched_text = _extract_sentence_context(para_text, m.start(), m.end())
            if not matched_text or len(matched_text) < 10:
                continue

            abs_start = chunk.char_start + para_offset + m.start()
            abs_end = abs_start + len(matched_text)

            # Compute confidence
            raw_confidence = tp.confidence + heading_boost
            # Extra boost if heading strongly matches
            if heading_score >= 0.5:
                raw_confidence += 0.05
            confidence = min(raw_confidence, 0.99)

            if confidence < min_confidence:
                continue

            # Extract modal verb
            modal_verb, legal_weight = _extract_modal(matched_text)

            article_ref = _build_article_ref(chunk)

            matches.append(RuleMatch(
                provision_class=tp.provision_class,
                category=rules.category,
                matched_text=matched_text,
                char_start=abs_start,
                char_end=abs_end,
                confidence=confidence,
                modal_verb=modal_verb,
                legal_weight=legal_weight,
                rule_name=tp.name,
                article_reference=article_ref,
                summary=tp.summary,
            ))

    return matches


def match_all_chunks(
    chunks: list[ArticleChunk],
    rules: CategoryRules,
    *,
    min_confidence: float = 0.50,
) -> list[RuleMatch]:
    """Run rules against all chunks."""
    all_matches: list[RuleMatch] = []
    for chunk in chunks:
        all_matches.extend(match_chunk(chunk, rules, min_confidence=min_confidence))
    return all_matches


def match_text_all_categories(
    chunks: list[ArticleChunk],
    categories: list[str] | None = None,
    *,
    min_confidence: float = 0.50,
    total_pages: int | None = None,
) -> list[RuleMatch]:
    """Run all (or selected) category rules against all chunks.

    If total_pages is provided, applies Fix 1 (TOC/Index page filter) before matching.
    """
    # Fix 1: Filter out TOC/Index chunks
    working_chunks = filter_toc_index_chunks(chunks, total_pages)

    all_rules = load_all_rules()
    if categories:
        all_rules = [r for r in all_rules if r.category in categories]

    all_matches: list[RuleMatch] = []
    for rules in all_rules:
        all_matches.extend(match_all_chunks(working_chunks, rules, min_confidence=min_confidence))

    # Deduplicate overlapping matches: keep highest confidence for same span
    all_matches = _deduplicate_matches(all_matches)
    return all_matches


def _split_paragraphs(text: str) -> list[tuple[str, int]]:
    """Split text into paragraphs with their offsets within the text."""
    paragraphs: list[tuple[str, int]] = []
    # Split on double newlines or lines that are mostly whitespace
    parts = re.split(r"\n\s*\n", text)
    offset = 0
    for part in parts:
        stripped = part.strip()
        if stripped and len(stripped) >= 15:
            # Find the actual position in the original text
            idx = text.find(part, offset)
            if idx >= 0:
                paragraphs.append((stripped, idx))
                offset = idx + len(part)
    return paragraphs


def _is_negative(text: str, rules: CategoryRules) -> bool:
    """Check if text matches any negative patterns."""
    for np in rules.negative_patterns:
        if np.compiled().search(text):
            return True
    return False


def _extract_sentence_context(text: str, match_start: int, match_end: int) -> str:
    """Extract the sentence containing the match, with some context.

    Fix 7: If the last sentence is incomplete (no terminal punctuation), extend up
    to 200 additional characters to find a sentence boundary.
    """
    # Find sentence boundaries
    sentence_ends = [m.end() for m in re.finditer(r"[.!?;:]\s+", text)]
    sentence_ends.append(len(text))

    # Find start of sentence containing match
    sent_start = 0
    for end in sentence_ends:
        if end > match_start:
            break
        sent_start = end

    # Find end of sentence containing match
    sent_end = len(text)
    for end in sentence_ends:
        if end >= match_end:
            sent_end = end
            break

    result = text[sent_start:sent_end].strip()

    # Fix 7: Check if text ends mid-sentence and extend if possible
    if result and result[-1] not in ".!?;:":
        # Look for a sentence boundary in the next 200 chars beyond sent_end
        continuation = text[sent_end:sent_end + 200]
        boundary = re.search(r"[.!?;:]\s", continuation)
        if boundary:
            result = text[sent_start:sent_end + boundary.end()].strip()

    # Cap at 600 chars
    if len(result) > 600:
        result = result[:597] + "..."
    return result


def extract_context_window(
    full_text: str, char_start: int, char_end: int, window: int = 100
) -> tuple[str, str]:
    """Fix 9: Extract context before and after a matched provision.

    Returns (context_before, context_after) — ~100 chars each, trimmed to
    word boundaries for readability.
    """
    # Context before
    ctx_start = max(0, char_start - window)
    before = full_text[ctx_start:char_start]
    # Trim to word boundary
    space_idx = before.find(" ")
    if space_idx > 0 and ctx_start > 0:
        before = before[space_idx + 1:]

    # Context after
    ctx_end = min(len(full_text), char_end + window)
    after = full_text[char_end:ctx_end]
    # Trim to word boundary
    space_idx = after.rfind(" ")
    if space_idx > 0 and ctx_end < len(full_text):
        after = after[:space_idx]

    return before.strip(), after.strip()


def _extract_modal(text: str) -> tuple[str | None, float | None]:
    """Extract the primary modal verb and its legal weight."""
    m = MODAL_RE.search(text)
    if not m:
        return None, 0.50
    modal = m.group(1).lower()
    weight = MODAL_WEIGHTS.get(modal, 0.50)
    return modal, weight


def _build_article_ref(chunk: ArticleChunk) -> str:
    """Build a human-readable article reference.

    Fix 8: If a section number is > 100, it's almost certainly a statutory reference
    (e.g., Section 1981 of the Civil Rights Act), not a contract section number.
    Prefer the parent article number for the reference in that case.
    """
    number = chunk.number
    # Detect statutory section references (Section 1981, Section 350, etc.)
    try:
        num_val = float(number.split(".")[0])
        if num_val > 100 and chunk.parent_number:
            # This is a statutory reference, use parent article only
            return f"Article {chunk.parent_number}" + (f" - {chunk.title}" if chunk.title else "")
    except (ValueError, IndexError):
        pass

    if chunk.level == 1:
        return f"Article {chunk.number}" + (f" - {chunk.title}" if chunk.title else "")
    elif chunk.parent_number:
        return f"Article {chunk.parent_number}, Section {chunk.number}" + (
            f" - {chunk.title}" if chunk.title else ""
        )
    else:
        return f"Section {chunk.number}" + (f" - {chunk.title}" if chunk.title else "")


def _deduplicate_matches(matches: list[RuleMatch]) -> list[RuleMatch]:
    """Remove duplicate matches for overlapping text spans.

    Fix 6: Enhanced dedup — also catches near-identical text even if char offsets
    differ slightly (>80% text overlap on same page). Keeps highest confidence.
    """
    if not matches:
        return matches

    # Sort by confidence descending so we keep the best matches
    matches.sort(key=lambda m: -m.confidence)

    deduped: list[RuleMatch] = []
    for match in matches:
        is_dup = False
        for existing in deduped:
            # Check 1: Overlapping char spans (>50% overlap)
            overlap_start = max(match.char_start, existing.char_start)
            overlap_end = min(match.char_end, existing.char_end)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                match_len = max(match.char_end - match.char_start, 1)
                if overlap_len / match_len > 0.5:
                    is_dup = True
                    break

            # Check 2 (Fix 6): Near-identical text content (>80% shared)
            # Catches duplicates from different rules matching the same text
            if len(match.matched_text) > 20 and len(existing.matched_text) > 20:
                shorter = min(len(match.matched_text), len(existing.matched_text))
                longer = max(len(match.matched_text), len(existing.matched_text))
                # Quick length check first
                if shorter / longer > 0.7:
                    # Count shared characters (order-independent substring check)
                    common = _text_overlap_ratio(match.matched_text, existing.matched_text)
                    if common > 0.80:
                        is_dup = True
                        break

        if not is_dup:
            deduped.append(match)

    # Re-sort by char_start for output consistency
    deduped.sort(key=lambda m: m.char_start)
    return deduped


def _text_overlap_ratio(a: str, b: str) -> float:
    """Compute character-level overlap ratio between two strings."""
    if not a or not b:
        return 0.0
    # Normalize whitespace for comparison
    a_norm = re.sub(r"\s+", " ", a.strip().lower())
    b_norm = re.sub(r"\s+", " ", b.strip().lower())
    shorter, longer = (a_norm, b_norm) if len(a_norm) <= len(b_norm) else (b_norm, a_norm)
    if shorter in longer:
        return 1.0
    # Sliding window: check how much of shorter appears in longer
    window = min(40, len(shorter))
    if window < 10:
        return 0.0
    matches = 0
    total = max(len(shorter) - window + 1, 1)
    for i in range(0, len(shorter) - window + 1, window):
        chunk = shorter[i:i + window]
        if chunk in longer:
            matches += 1
    return matches / max(total / window, 1)
