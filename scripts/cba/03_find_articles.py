"""Script 3: Find article and section headings, break the contract into labeled chunks.

Scans the contract text for structural headings (ARTICLE X, Section Y.Z, etc.)
and builds a hierarchical outline with char offsets and page numbers.

Usage:
    py scripts/cba/03_find_articles.py --cba-id N [--verbose]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import ArticleChunk, PageSpan

# Roman numeral mapping
ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19,
    "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25,
    "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
    "XXXI": 31, "XXXII": 32, "XXXIII": 33, "XXXIV": 34, "XXXV": 35,
    "XXXVI": 36, "XXXVII": 37, "XXXVIII": 38, "XXXIX": 39, "XL": 40,
    "XLI": 41, "XLII": 42, "XLIII": 43, "XLIV": 44, "XLV": 45,
    "XLVI": 46, "XLVII": 47, "XLVIII": 48, "XLIX": 49, "L": 50,
}
ROMAN_RE = "|".join(sorted(ROMAN_MAP.keys(), key=lambda x: -len(x)))

# Heading detection patterns (ordered by priority)
HEADING_PATTERNS = [
    # Priority 1: "ARTICLE 12 - Grievance Procedure" / "ARTICLE XII: WAGES"
    (
        rf"^\s*ARTICLE\s+(?:(\d+)|({ROMAN_RE}))\s*[-:.\s]+\s*(.+?)$",
        1, "article_num_title"
    ),
    # Priority 1b: "ARTICLE 12" alone on a line (title may be on next line)
    (
        rf"^\s*ARTICLE\s+(?:(\d+)|({ROMAN_RE}))\s*$",
        1, "article_num_only"
    ),
    # Priority 2: "Article 12. Grievance Procedure" (mixed case)
    (
        rf"^\s*Article\s+(?:(\d+)|({ROMAN_RE}))\s*[-.:\s]+\s*(.+?)$",
        1, "article_mixed"
    ),
    # Priority 3: "SECTION 3.4" / "Section 3.4 - Overtime"
    (
        r"^\s*[Ss][Ee][Cc][Tt][Ii][Oo][Nn]\s+(\d+(?:\.\d+)?)\s*[-:.\s]*\s*(.*)$",
        2, "section"
    ),
    # Priority 4: "12.3 Overtime Provisions" (numbered heading)
    (
        r"^\s*(\d+\.\d+)\s+([A-Z][A-Za-z\s,&/-]{3,75})$",
        2, "numbered_heading"
    ),
    # Priority 5: Roman numeral headings: "XII. WAGES"
    (
        rf"^\s*({ROMAN_RE})\.\s+([A-Z][A-Z\s,&/-]{{2,75}})$",
        1, "roman_heading"
    ),
]

# Words that indicate a line is NOT a heading (running headers, etc.)
NON_HEADING_WORDS = {
    "page", "continued", "draft", "confidential", "table of contents",
}

# Minimum heading length
MIN_HEADING_LEN = 3
MAX_HEADING_LEN = 120


def find_articles(text: str, spans: list[PageSpan] | None = None) -> list[ArticleChunk]:
    """Find article/section headings and break text into chunks."""
    lines = text.split("\n")
    headings: list[dict] = []
    # Track lines consumed as peeked titles (to avoid double-detecting them)
    consumed_title_lines: set[int] = set()

    line_starts: list[int] = []
    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line) + 1  # +1 for newline

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) < MIN_HEADING_LEN or len(stripped) > MAX_HEADING_LEN:
            continue

        # Skip lines already consumed as titles of preceding ARTICLE headings
        if i in consumed_title_lines:
            continue

        # Skip likely non-headings
        lower = stripped.lower()
        if any(w in lower for w in NON_HEADING_WORDS):
            continue

        heading = _match_heading(stripped, i, lines)
        if heading:
            heading["char_start"] = line_starts[i]
            headings.append(heading)
            # If this was an "article_num_only" pattern, mark the peeked title line
            if heading.get("pattern") == "article_num_only" and heading.get("title"):
                for j in range(i + 1, min(i + 3, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and heading["title"] in candidate:
                        consumed_title_lines.add(j)
                        break
            continue

        # Priority 6: All-caps lines preceded by blank line (5-80 chars)
        if (
            stripped.isupper()
            and 5 <= len(stripped) <= 80
            and not stripped.startswith("(")
            and _preceded_by_blank(i, lines)
            and not _is_running_header(stripped, lines, i)
            and _has_letter(stripped)
        ):
            headings.append({
                "number": str(len(headings) + 1),
                "title": _clean_heading(stripped),
                "level": 1,
                "pattern": "allcaps",
                "line_idx": i,
                "char_start": line_starts[i],
            })

    if not headings:
        return []

    # Build chunks from headings
    chunks = _build_chunks(headings, text, lines, line_starts, spans)
    return chunks


def _match_heading(stripped: str, line_idx: int, lines: list[str]) -> dict | None:
    """Try to match a line against heading patterns."""
    for pattern, level, name in HEADING_PATTERNS:
        m = re.match(pattern, stripped, re.IGNORECASE if "mixed" in name else 0)
        if not m:
            continue

        groups = m.groups()

        if name == "article_num_title":
            num = groups[0] or _roman_to_str(groups[1])
            title = _clean_heading(groups[2])
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

        elif name == "article_num_only":
            num = groups[0] or _roman_to_str(groups[1])
            # Title might be on the next line
            title = _peek_next_line_title(line_idx, lines)
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

        elif name == "article_mixed":
            num = groups[0] or _roman_to_str(groups[1])
            title = _clean_heading(groups[2])
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

        elif name == "section":
            num = groups[0]
            title = _clean_heading(groups[1]) if groups[1] else ""
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

        elif name == "numbered_heading":
            num = groups[0]
            title = _clean_heading(groups[1])
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

        elif name == "roman_heading":
            num = _roman_to_str(groups[0])
            title = _clean_heading(groups[1])
            return {"number": num, "title": title, "level": level, "pattern": name, "line_idx": line_idx}

    return None


def _build_chunks(
    headings: list[dict],
    text: str,
    lines: list[str],
    line_starts: list[int],
    spans: list[PageSpan] | None,
) -> list[ArticleChunk]:
    """Build ArticleChunk objects from heading positions."""
    chunks: list[ArticleChunk] = []
    current_article: str | None = None

    for idx, heading in enumerate(headings):
        # Determine text range: from this heading to the next (or end of text)
        start = heading["char_start"]
        if idx + 1 < len(headings):
            end = headings[idx + 1]["char_start"]
        else:
            end = len(text)

        chunk_text = text[start:end]
        level = heading["level"]

        # Track parent article for sections
        parent = None
        if level == 1:
            current_article = heading["number"]
        elif level >= 2 and current_article:
            parent = current_article

        page_start = _page_for_char(spans, start) if spans else None
        page_end = _page_for_char(spans, max(end - 1, start)) if spans else None

        chunks.append(ArticleChunk(
            number=heading["number"],
            title=heading["title"],
            level=level,
            text=chunk_text,
            char_start=start,
            char_end=end,
            page_start=page_start,
            page_end=page_end,
            parent_number=parent,
        ))

    return chunks


def _roman_to_str(roman: str | None) -> str:
    """Convert Roman numeral to string number."""
    if not roman:
        return "0"
    return str(ROMAN_MAP.get(roman.upper(), 0))


def _clean_heading(title: str) -> str:
    """Clean up heading text."""
    title = title.strip().rstrip("-:.")
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _peek_next_line_title(line_idx: int, lines: list[str]) -> str:
    """If the heading number is alone, check the next non-blank line for the title."""
    for j in range(line_idx + 1, min(line_idx + 3, len(lines))):
        candidate = lines[j].strip()
        if candidate and len(candidate) >= 3:
            # Likely the title if it's not another article heading
            if not re.match(r"^\s*ARTICLE\s+", candidate, re.IGNORECASE):
                return _clean_heading(candidate)
            break
    return ""


def _preceded_by_blank(line_idx: int, lines: list[str]) -> bool:
    """Check if a line is preceded by a blank line (or is near the start)."""
    if line_idx == 0:
        return True
    for j in range(line_idx - 1, max(line_idx - 3, -1), -1):
        if not lines[j].strip():
            return True
    return False


def _is_running_header(text: str, lines: list[str], line_idx: int) -> bool:
    """Detect running headers that repeat on many pages."""
    # If the exact text appears 3+ times in the document, likely a header
    count = sum(1 for line in lines if line.strip() == text)
    return count >= 3


def _has_letter(text: str) -> bool:
    """Check that string contains at least one letter."""
    return any(c.isalpha() for c in text)


def _page_for_char(spans: list[PageSpan] | None, char_pos: int) -> int | None:
    """Binary search for page number."""
    if not spans:
        return None
    lo, hi = 0, len(spans) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        span = spans[mid]
        if char_pos < span.char_start:
            hi = mid - 1
        elif char_pos >= span.char_end:
            lo = mid + 1
        else:
            return span.page_number
    return None


def chunks_to_json(chunks: list[ArticleChunk]) -> list[dict]:
    """Convert chunks to JSON-serializable dicts for storage."""
    return [
        {
            "number": c.number,
            "title": c.title,
            "level": c.level,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "parent_number": c.parent_number,
        }
        for c in chunks
    ]


def get_document_data(cba_id: int) -> tuple[str | None, list[PageSpan]]:
    """Retrieve full_text and reconstruct spans for a document."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT full_text, page_count FROM cba_documents WHERE cba_id = %s", [cba_id])
            row = cur.fetchone()
            if not row or not row[0]:
                return None, []
            text = row[0]
            # Reconstruct approximate spans from page count
            # (exact spans would require re-reading the PDF)
            page_count = row[1] or 1
            chars_per_page = len(text) // max(page_count, 1)
            spans = []
            for i in range(page_count):
                spans.append(PageSpan(
                    page_number=i + 1,
                    char_start=i * chars_per_page,
                    char_end=min((i + 1) * chars_per_page, len(text)),
                ))
            if spans:
                spans[-1] = PageSpan(
                    page_number=page_count,
                    char_start=spans[-1].char_start,
                    char_end=len(text),
                )
            return text, spans


def save_structure(cba_id: int, chunks: list[ArticleChunk]) -> None:
    """Save the article structure to cba_documents.structure_json."""
    structure = chunks_to_json(chunks)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_documents SET structure_json = %s, updated_at = NOW() WHERE cba_id = %s",
                [json.dumps(structure), cba_id],
            )
            conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Find articles and sections in a CBA")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    parser.add_argument("--verbose", action="store_true", help="Print each heading with page")
    args = parser.parse_args()

    text, spans = get_document_data(args.cba_id)
    if not text:
        print(f"ERROR: No full_text found for cba_id={args.cba_id}")
        sys.exit(1)

    print(f"Finding articles in cba_id={args.cba_id} ({len(text):,} chars)")
    chunks = find_articles(text, spans)
    print(f"  Found {len(chunks)} headings")

    if args.verbose:
        print("\n  Outline:")
        for c in chunks:
            indent = "  " * c.level
            page_info = f"p.{c.page_start}" if c.page_start else ""
            parent_info = f" (under Art. {c.parent_number})" if c.parent_number else ""
            print(f"    {indent}{c.number}. {c.title} {page_info}{parent_info}")

    save_structure(args.cba_id, chunks)
    print(f"\n  Structure saved to cba_documents.structure_json")


if __name__ == "__main__":
    main()
