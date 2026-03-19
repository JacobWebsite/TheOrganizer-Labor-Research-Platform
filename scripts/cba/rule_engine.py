"""Core rule-based matching engine for CBA provision categorization.

Loads rule JSON files from config/cba_rules/ and matches them against
contract text chunks. Two-pass matching: heading signals then text patterns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

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

# Fix 1: TOC/Index detection — dotted-line pattern + index-style entries
TOC_INDEX_RE = re.compile(
    r"\.{4,}|·{4,}|\.\s*\.\s*\.\s*\."       # dotted leaders
    r"|\bSubject\s+Page\b"                     # explicit TOC header
    r"|(?:\w[\w\s]{2,30}\s+\d{1,3}(?:,\s*\d{1,3}){2,})"  # "Topic 12, 34, 56" index entries
)
# Fraction of total pages to skip at start (TOC) and end (Index)
TOC_PAGE_FRACTION = 0.05
INDEX_PAGE_FRACTION = 0.05  # increased from 0.03 — last 5% is almost always index


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
class HeadingExclusion:
    """When a chunk's heading (or parent article heading) matches, block this category entirely."""
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
    heading_exclusions: list[HeadingExclusion] = field(default_factory=list)


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
        if total_pages and chunk.page_start is not None:
            toc_cutoff = max(int(total_pages * TOC_PAGE_FRACTION), 2)
            index_cutoff = total_pages - max(int(total_pages * INDEX_PAGE_FRACTION), 1)
            # Last 2 pages are almost always index — drop unconditionally
            if chunk.page_start >= total_pages - 1:
                continue
            # Pages in TOC/index range: drop if any index-like content detected
            if chunk.page_start <= toc_cutoff or chunk.page_start >= index_cutoff:
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
        heading_exclusions=[
            HeadingExclusion(pattern=h["pattern"], note=h.get("note", ""))
            for h in data.get("heading_exclusions", [])
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


def _heading_excluded(
    title: str | None,
    parent_title: str | None,
    rules: CategoryRules,
) -> bool:
    """Check if a chunk's heading (or parent article heading) triggers an exclusion.

    When excluded, the entire category is blocked from matching in this chunk.
    """
    if not rules.heading_exclusions:
        return False
    for excl in rules.heading_exclusions:
        compiled = excl.compiled()
        if title and compiled.search(title):
            return True
        if parent_title and compiled.search(parent_title):
            return True
    return False


def match_chunk(
    chunk: ArticleChunk,
    rules: CategoryRules,
    *,
    min_confidence: float = 0.50,
) -> list[RuleMatch]:
    """Run a category's rules against a single text chunk.

    Three-pass matching:
    1. Check heading exclusions -- if excluded, return [] immediately
    2. Score the heading for topic relevance (affinity adjustment)
    3. Scan text for pattern matches, adjusting confidence based on heading affinity
    """
    # Pass 1: Heading exclusion gate
    if _heading_excluded(chunk.title, getattr(chunk, 'parent_title', None), rules):
        return []

    # Pass 2: Heading affinity scoring
    heading_score = score_heading(chunk.title, rules)
    # Also check parent title for heading affinity
    parent_title = getattr(chunk, 'parent_title', None)
    if parent_title:
        parent_heading_score = score_heading(parent_title, rules)
        heading_score = max(heading_score, parent_heading_score)

    # Heading affinity adjustment (replaces flat +0.10 boost)
    if heading_score >= 0.5:
        heading_adjust = 0.05   # Strong heading match confirms topic
    elif heading_score >= 0.3:
        heading_adjust = 0.0    # Weak match -- neutral
    else:
        heading_adjust = -0.15  # Zero affinity -- likely cross-category FP

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

            # Use the full paragraph as the matched text
            matched_text = para_text.strip()
            if not matched_text or len(matched_text) < 80:
                continue

            # Cap at 3000 chars
            if len(matched_text) > 3000:
                matched_text = matched_text[:2997] + "..."

            abs_start = chunk.char_start + para_offset
            abs_end = abs_start + len(para_text)

            # Compute confidence with heading affinity
            confidence = min(tp.confidence + heading_adjust, 0.99)

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


_MERGE_CONJUNCTIONS = re.compile(
    r"^(?:and|or|but|provided|except|however|furthermore|moreover|additionally|including)\b",
    re.IGNORECASE,
)


def _should_merge(prev_text: str, curr_text: str) -> bool:
    """Decide whether curr_text is a fragment that should merge into prev_text.

    Merge when:
    - Current starts with lowercase (continuation of prior sentence)
    - Current starts with a conjunction (and, or, but, provided, except, however)
    - Previous ends without sentence-terminal punctuation and current starts with
      non-heading text (no Article/Section prefix)
    """
    if not prev_text or not curr_text:
        return False
    first_char = curr_text[0]
    # Starts lowercase -> continuation fragment
    if first_char.islower():
        return True
    # Starts with a conjunction
    if _MERGE_CONJUNCTIONS.match(curr_text):
        return True
    # Previous lacks terminal punctuation and current isn't a heading
    if prev_text[-1] not in ".!?;:" and not re.match(
        r"^(?:ARTICLE|SECTION|Art\.|Sec\.)\s", curr_text
    ):
        if first_char.isupper() and not curr_text[:1].isnumeric():
            # Could be a real new paragraph -- only merge if short
            return len(curr_text) < 120
    return False


def _split_paragraphs(text: str) -> list[tuple[str, int]]:
    """Split text into paragraphs with their offsets, merging fragments.

    Fragments (mid-sentence breaks from PDF soft wraps) are merged into the
    preceding paragraph to avoid returning incomplete provisions.
    """
    # Step 1: split on double newlines
    parts = re.split(r"\n\s*\n", text)

    # Step 2: locate each part and collect raw segments
    raw: list[tuple[str, int]] = []
    offset = 0
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        idx = text.find(part, offset)
        if idx >= 0:
            raw.append((stripped, idx))
            offset = idx + len(part)

    # Step 3: merge fragments into previous paragraph
    merged: list[tuple[str, int]] = []
    for seg_text, seg_offset in raw:
        if merged and _should_merge(merged[-1][0], seg_text):
            prev_text, prev_offset = merged[-1]
            merged[-1] = (prev_text + " " + seg_text, prev_offset)
        else:
            merged.append((seg_text, seg_offset))

    # Step 4: filter by minimum length (80 chars -- match_chunk already rejects <80)
    return [(t, o) for t, o in merged if len(t) >= 80]


def _is_negative(text: str, rules: CategoryRules) -> bool:
    """Check if text matches any negative patterns."""
    for np in rules.negative_patterns:
        if np.compiled().search(text):
            return True
    return False


def _extract_sentence_context(text: str, match_start: int, match_end: int) -> str:
    """Extract the provision text containing the match with enough context.

    Strategy: capture the sentence containing the match, then expand in both
    directions until we have at least MIN_PROVISION_CHARS of text. This prevents
    returning useless fragments like "There shall be paid the following:"
    without the actual details that follow.
    """
    MIN_PROVISION_CHARS = 150

    # Find sentence boundaries (periods, colons, semicolons followed by whitespace)
    boundaries = [0]
    for m in re.finditer(r"[.!?;]\s+", text):
        boundaries.append(m.end())
    # Colons that introduce lists/details should NOT be boundaries -- they start
    # the substantive content we want to capture. Only treat colon as boundary
    # if followed by a capital letter (new sentence) not a list/number.
    for m in re.finditer(r":\s+(?=[A-Z])", text):
        boundaries.append(m.end())
    boundaries.append(len(text))
    boundaries = sorted(set(boundaries))

    # Find which boundary segment contains the match
    seg_start_idx = 0
    for i, b in enumerate(boundaries):
        if b > match_start:
            break
        seg_start_idx = i
    seg_end_idx = len(boundaries) - 1
    for i, b in enumerate(boundaries):
        if b >= match_end:
            seg_end_idx = i
            break

    sent_start = boundaries[seg_start_idx]
    sent_end = boundaries[seg_end_idx]
    result = text[sent_start:sent_end].strip()

    # Expand forward if too short -- the details usually follow the match
    while len(result) < MIN_PROVISION_CHARS and seg_end_idx < len(boundaries) - 1:
        seg_end_idx += 1
        sent_end = boundaries[seg_end_idx]
        result = text[sent_start:sent_end].strip()

    # Expand backward if still too short
    while len(result) < MIN_PROVISION_CHARS and seg_start_idx > 0:
        seg_start_idx -= 1
        sent_start = boundaries[seg_start_idx]
        result = text[sent_start:sent_end].strip()

    # If text ends mid-sentence, extend to find a boundary
    if result and result[-1] not in ".!?;:":
        continuation = text[sent_end:sent_end + 300]
        boundary = re.search(r"[.!?;]\s", continuation)
        if boundary:
            result = text[sent_start:sent_end + boundary.end()].strip()

    # Cap at 2000 chars
    if len(result) > 2000:
        result = result[:1997] + "..."
    return result


def extract_context_window(
    full_text: str, char_start: int, char_end: int, window: int = 500
) -> tuple[str, str]:
    """Fix 9: Extract context before and after a matched provision.

    Returns (context_before, context_after) — ~500 chars each, trimmed to
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


def populate_context(matches: list[RuleMatch], full_text: str, window: int = 500) -> None:
    """Populate context_before and context_after on each RuleMatch."""
    for m in matches:
        before, after = extract_context_window(full_text, m.char_start, m.char_end, window)
        m.context_before = before
        m.context_after = after


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
