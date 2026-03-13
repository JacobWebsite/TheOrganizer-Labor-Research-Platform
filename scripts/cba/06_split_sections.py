"""Script 6: Split full contract text into sections using parsed TOC.

Uses the TOC entries from 05_parse_toc.py to split the document into
complete section texts, then inserts rows into cba_sections.

Algorithm:
  1. Load toc_json from cba_documents
  2. Detect page number offset (printed page vs PDF page)
  3. For each TOC entry, find the heading in the text near the expected offset
  4. Each section's text runs from its heading to the start of the next section
  5. Insert into cba_sections with complete text, char offsets, page ranges

Usage:
    py scripts/cba/06_split_sections.py --cba-id 26 [--verbose]
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import PageSpan, SectionRow, TOCEntry

_toc_mod = importlib.import_module("scripts.cba.05_parse_toc")
load_toc = _toc_mod.load_toc

_article_mod = importlib.import_module("scripts.cba.03_find_articles")
ROMAN_MAP = _article_mod.ROMAN_MAP
_page_for_char = _article_mod._page_for_char

# Width of search window (chars) around expected position for fuzzy heading search
SEARCH_WINDOW = 5000

# Dotted leader pattern -- indicates a TOC line, not a body heading
_DOTTED_LEADER_RE = re.compile(r"[.\u00b7\u2026]{4,}")


def split_sections(
    text: str,
    spans: list[PageSpan],
    toc_entries: list[TOCEntry],
    verbose: bool = False,
) -> list[SectionRow]:
    """Split full_text into sections based on TOC entries.

    Returns a list of SectionRow objects with complete text and offsets.
    """
    if not toc_entries:
        return []

    # Step 1: Compute page offset (printed page 1 -> actual PDF page N)
    page_offset = _detect_page_offset(text, spans, toc_entries)
    if verbose:
        print(f"  Page offset: printed + {page_offset} = PDF page")

    # Step 2: Find char position for each TOC entry
    anchors: list[tuple[TOCEntry, int]] = []  # (entry, char_start)
    for entry in toc_entries:
        char_pos = _find_section_start(text, spans, entry, page_offset, verbose=verbose)
        if char_pos is not None:
            anchors.append((entry, char_pos))
        elif verbose:
            print(f"  WARNING: Could not locate '{entry.title}' (p.{entry.page_number})")

    if not anchors:
        return []

    # Sort by char position
    anchors.sort(key=lambda x: x[1])

    # Step 3: Build sections from anchors
    sections: list[SectionRow] = []
    for i, (entry, char_start) in enumerate(anchors):
        # End is the start of next section, or end of text
        if i + 1 < len(anchors):
            char_end = anchors[i + 1][1]
        else:
            char_end = len(text)

        section_text = text[char_start:char_end]
        page_start = _page_for_char(spans, char_start)
        page_end = _page_for_char(spans, max(char_end - 1, char_start))

        sections.append(SectionRow(
            section_num=entry.number,
            section_title=entry.title,
            section_level=entry.level,
            section_text=section_text,
            char_start=char_start,
            char_end=char_end,
            page_start=page_start,
            page_end=page_end,
            parent_section_num=entry.parent_number,
            detection_method="toc_parsed",
        ))

    if verbose:
        total_chars = sum(s.char_end - s.char_start for s in sections)
        print(f"  Total section chars: {total_chars:,} / {len(text):,} text chars "
              f"({total_chars / len(text) * 100:.1f}% coverage)")

    return sections


def _detect_page_offset(
    text: str,
    spans: list[PageSpan],
    toc_entries: list[TOCEntry],
) -> int:
    """Detect the offset between printed page numbers and PDF page numbers.

    Strategy: Find the first article (level=1) in the TOC, search for its
    heading in the text, determine which PDF page it falls on, compute
    offset = pdf_page - printed_page.
    """
    # Try the first few level-1 entries
    for entry in toc_entries:
        if entry.level != 1:
            continue
        if entry.page_number < 1:
            continue

        # Build a regex to find this article heading in the body text
        pattern = _heading_search_pattern(entry)
        if not pattern:
            continue

        m = pattern.search(text)
        if m:
            found_pos = m.start()
            pdf_page = _page_for_char(spans, found_pos)
            if pdf_page is not None:
                offset = pdf_page - entry.page_number
                return max(offset, 0)  # offset should be non-negative

    # Default: assume small offset (TOC + cover = ~3 pages)
    return 0


def _heading_search_pattern(entry: TOCEntry) -> re.Pattern | None:
    """Build a regex pattern to find a TOC entry's heading in the body text."""
    title = re.escape(entry.title[:60])  # Escape for regex, limit length
    # Allow flexible whitespace in the title
    title = re.sub(r"\\ ", r"\\s+", title)

    num = entry.number

    # If number looks like an article number (pure digits or matches a roman numeral)
    # Try both roman and arabic forms
    roman_form = None
    arabic_form = None
    if num.isdigit():
        arabic_form = num
        # Find the roman equivalent
        for roman, val in ROMAN_MAP.items():
            if val == int(num):
                roman_form = roman
                break
    else:
        # Check if it's already a known roman string (shouldn't happen since we normalize)
        arabic_form = num

    # For section numbers like "19.5", just search for the title near a number
    if "." in num:
        return re.compile(
            rf"(?:^|\n)\s*(?:{re.escape(num)}|{num.split('.')[1]})[.\s)]+\s*{title}",
            re.IGNORECASE,
        )

    # For non-article entries (number == title, like "Side Letters")
    if num == entry.title:
        return re.compile(
            rf"(?:^|\n)\s*{title}",
            re.IGNORECASE,
        )

    # Build alternation for article number
    num_alts = []
    if arabic_form:
        num_alts.append(re.escape(arabic_form))
    if roman_form:
        num_alts.append(re.escape(roman_form))
    if not num_alts:
        num_alts.append(re.escape(num))

    num_pattern = "|".join(num_alts)

    return re.compile(
        rf"(?:^|\n)\s*(?:ARTICLE\s+)?(?:{num_pattern})[.\s:)-]+\s*{title}",
        re.IGNORECASE,
    )


def _find_non_toc_match(
    pattern: re.Pattern,
    search_text: str,
    offset: int,
    full_text: str,
) -> int | None:
    """Find first regex match that is NOT on a TOC line (no dotted leaders).

    Returns absolute char position in full_text, or None.
    """
    for m in pattern.finditer(search_text):
        abs_pos = offset + m.start()
        # Skip leading newline
        if abs_pos < len(full_text) and full_text[abs_pos] == "\n":
            abs_pos += 1
        # Get the full line at this position to check for dotted leaders
        line_start = full_text.rfind("\n", 0, abs_pos)
        line_start = line_start + 1 if line_start >= 0 else 0
        line_end = full_text.find("\n", abs_pos)
        if line_end < 0:
            line_end = len(full_text)
        line = full_text[line_start:line_end]
        if _DOTTED_LEADER_RE.search(line):
            continue  # Skip TOC line
        return abs_pos
    return None


def _find_section_start(
    text: str,
    spans: list[PageSpan],
    entry: TOCEntry,
    page_offset: int,
    verbose: bool = False,
) -> int | None:
    """Find the char offset where a section starts in the full text.

    1. Compute expected char position from TOC page + offset
    2. Search within a window around that position for the heading
    3. Fall back to searching the entire document if not found nearby
    """
    # Convert printed page to approximate char position
    expected_pdf_page = entry.page_number + page_offset
    expected_char = _char_for_page(spans, expected_pdf_page)

    # Search in a window around expected position
    search_start = max(0, expected_char - SEARCH_WINDOW)
    search_end = min(len(text), expected_char + SEARCH_WINDOW * 2)
    window = text[search_start:search_end]

    pattern = _heading_search_pattern(entry)
    if not pattern:
        return None

    abs_pos = _find_non_toc_match(pattern, window, search_start, text)
    if abs_pos is not None:
        if verbose:
            pdf_page = _page_for_char(spans, abs_pos)
            print(f"  Located '{entry.title}' at char {abs_pos:,} (PDF p.{pdf_page})")
        return abs_pos

    # Fallback: search entire document
    abs_pos = _find_non_toc_match(pattern, text, 0, text)
    if abs_pos is not None:
        if verbose:
            pdf_page = _page_for_char(spans, abs_pos)
            print(f"  Located '{entry.title}' at char {abs_pos:,} (PDF p.{pdf_page}) [full search]")
        return abs_pos

    # Last resort: search for just the title text
    title_esc = re.escape(entry.title[:50])
    title_esc = re.sub(r"\\ ", r"\\s+", title_esc)
    title_re = re.compile(rf"(?:^|\n)\s*{title_esc}", re.IGNORECASE)
    abs_pos = _find_non_toc_match(title_re, text, 0, text)
    if abs_pos is not None:
        if verbose:
            pdf_page = _page_for_char(spans, abs_pos)
            print(f"  Located '{entry.title}' at char {abs_pos:,} (PDF p.{pdf_page}) [title-only]")
        return abs_pos

    return None


def _char_for_page(spans: list[PageSpan], page_number: int) -> int:
    """Convert a PDF page number to approximate char offset."""
    if not spans:
        return 0
    for span in spans:
        if span.page_number >= page_number:
            return span.char_start
    # Past the last page -- return end of text
    return spans[-1].char_end if spans else 0


def insert_sections(cba_id: int, sections: list[SectionRow]) -> int:
    """Insert section rows into cba_sections. Returns count inserted."""
    if not sections:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Clear existing sections for this document
            cur.execute("DELETE FROM cba_sections WHERE cba_id = %s", [cba_id])

            # Insert new sections
            # First pass: insert all sections to get IDs, then update parent references
            section_id_map: dict[str, int] = {}  # section_num -> section_id

            for i, s in enumerate(sections):
                cur.execute(
                    """
                    INSERT INTO cba_sections (
                        cba_id, section_num, section_title, section_level,
                        sort_order, section_text, char_start, char_end,
                        page_start, page_end, detection_method
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING section_id
                    """,
                    [
                        cba_id, s.section_num, s.section_title, s.section_level,
                        i + 1, s.section_text, s.char_start, s.char_end,
                        s.page_start, s.page_end, s.detection_method,
                    ],
                )
                section_id = cur.fetchone()[0]
                section_id_map[s.section_num] = section_id

            # Second pass: set parent_section_id references
            for s in sections:
                if s.parent_section_num and s.parent_section_num in section_id_map:
                    child_id = section_id_map.get(s.section_num)
                    parent_id = section_id_map[s.parent_section_num]
                    if child_id:
                        cur.execute(
                            "UPDATE cba_sections SET parent_section_id = %s WHERE section_id = %s",
                            [parent_id, child_id],
                        )

            conn.commit()

    return len(sections)


def reconstruct_spans(text: str, page_count: int) -> list[PageSpan]:
    """Reconstruct approximate page spans from text length and page count."""
    page_count = max(page_count or 1, 1)
    chars_per_page = len(text) // page_count
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
    return spans


def main() -> None:
    parser = argparse.ArgumentParser(description="Split CBA into sections using parsed TOC")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output")
    args = parser.parse_args()

    # Load TOC
    toc_entries = load_toc(args.cba_id)
    if not toc_entries:
        print(f"ERROR: No TOC found for cba_id={args.cba_id}")
        print("  Run 05_parse_toc.py first.")
        sys.exit(1)

    # Load document text and reconstruct spans
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_text, page_count FROM cba_documents WHERE cba_id = %s",
                [args.cba_id],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                print(f"ERROR: No full_text found for cba_id={args.cba_id}")
                sys.exit(1)
            text, page_count = row

    spans = reconstruct_spans(text, page_count)

    print(f"Splitting cba_id={args.cba_id} into sections ({len(toc_entries)} TOC entries)")

    sections = split_sections(text, spans, toc_entries, verbose=args.verbose)
    print(f"  Created {len(sections)} sections")

    if not sections:
        print("  WARNING: No sections created.")
        sys.exit(1)

    # Validate: check for overlaps and coverage
    total_section_chars = sum(s.char_end - s.char_start for s in sections)
    coverage = total_section_chars / len(text) * 100
    print(f"  Coverage: {total_section_chars:,} / {len(text):,} chars ({coverage:.1f}%)")

    # Check for overlaps
    sorted_sections = sorted(sections, key=lambda s: s.char_start)
    overlaps = 0
    for i in range(len(sorted_sections) - 1):
        if sorted_sections[i].char_end > sorted_sections[i + 1].char_start:
            overlaps += 1
    if overlaps:
        print(f"  WARNING: {overlaps} overlapping sections detected")

    # Insert into DB
    inserted = insert_sections(args.cba_id, sections)
    print(f"  Inserted {inserted} sections into cba_sections")

    # Update decomposition status
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_documents SET decomposition_status = 'sections_split', updated_at = NOW() WHERE cba_id = %s",
                [args.cba_id],
            )
            conn.commit()

    if args.verbose:
        print("\n  Sections:")
        for s in sections:
            indent = "    " if s.section_level >= 2 else "  "
            page_info = f"p.{s.page_start}-{s.page_end}" if s.page_start else ""
            chars = s.char_end - s.char_start
            print(f"  {indent}{s.section_num}. {s.section_title} "
                  f"({chars:,} chars) {page_info}")


if __name__ == "__main__":
    main()
