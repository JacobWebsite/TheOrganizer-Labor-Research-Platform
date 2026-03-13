"""Script 5: Parse the Table of Contents from a CBA contract.

Detects and parses the contract's own TOC to identify all articles,
sub-sections, and non-article entries (Side Letters, Wage Rates, etc.).

3-tier detection:
  1. Explicit TOC: Find "TABLE OF CONTENTS" header, parse structured entries
  2. Structural inference: Detect dotted-leader clusters in early pages
  3. Fallback: Use find_articles() heuristic from 03_find_articles.py

Usage:
    py scripts/cba/05_parse_toc.py --cba-id 26 [--verbose]
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
from scripts.cba.models import TOCEntry

# Reuse roman numeral support from 03_find_articles
_article_mod = importlib.import_module("scripts.cba.03_find_articles")
ROMAN_MAP = _article_mod.ROMAN_MAP
ROMAN_RE = _article_mod.ROMAN_RE

# ---------------------------------------------------------------------------
# TOC detection patterns
# ---------------------------------------------------------------------------

# Header that marks the start of a TOC block
TOC_HEADER_RE = re.compile(
    r"TABLE\s+OF\s+CONTENTS",
    re.IGNORECASE,
)

# Dotted leader: captures everything before dots and the page number after
# Matches lines like:  "Union Recognition .................1"
DOTTED_LEADER_RE = re.compile(
    r"^(.+?)\s*[.\u00b7\u2026]{3,}\s*(\d+)\s*$"
)

# Article-style TOC line:  "I.   Union Recognition ....... 1"
#   group1 = roman or arabic number, group2 = title, group3 = page
ARTICLE_TOC_RE = re.compile(
    rf"^\s*(?:ARTICLE\s+)?({ROMAN_RE}|\d+)[.\s)]+\s*(.+?)\s*[.\u00b7\u2026]{{2,}}\s*(\d+)\s*$"
)

# Sub-section TOC line:  "  5. Voting Time .............. 77"
SUB_SECTION_TOC_RE = re.compile(
    r"^\s+(\d+)[.\s)]+\s*(.+?)\s*[.\u00b7\u2026]{2,}\s*(\d+)\s*$"
)

# Non-article entry (no number prefix):  "Side Letters .............. 126"
NON_ARTICLE_TOC_RE = re.compile(
    r"^\s*([A-Z][A-Za-z\s,&/()-]+?)\s*[.\u00b7\u2026]{2,}\s*(\d+)\s*$"
)

# Continuation marker: "(cont'd)" or "(continued)"
CONTINUATION_RE = re.compile(r"\(cont['\u2019]?d\)|\(continued\)", re.IGNORECASE)

# Page footer noise: standalone roman numeral page numbers (i, ii, iii, iv)
ROMAN_PAGE_RE = re.compile(r"^\s*(i{1,3}|iv|vi{0,3}|ix|x{0,3})\s*$", re.IGNORECASE)

# Noise lines to skip
NOISE_RE = re.compile(
    r"^\s*$|^\s*page\s*$|^\s*-\s*\d+\s*-\s*$",
    re.IGNORECASE,
)


def parse_toc(text: str, verbose: bool = False) -> list[TOCEntry]:
    """Parse TOC from contract text. Returns list of TOCEntry or empty list.

    Tries 3 tiers:
      1. Explicit TOC header -> parse structured block
      2. Dotted-leader cluster in first 15% of text
      3. Returns empty (caller should use fallback)
    """
    # Tier 1: Look for explicit "TABLE OF CONTENTS"
    search_end = max(len(text) // 4, 2000)  # At least 2000 chars for short texts
    toc_match = TOC_HEADER_RE.search(text[:search_end])
    if toc_match:
        toc_start = toc_match.end()
        entries = _parse_toc_block(text, toc_start, verbose=verbose)
        if entries:
            return entries

    # Tier 2: Structural inference -- dotted-leader cluster in first 15%
    cutoff = len(text) // 7  # ~14%
    early_text = text[:cutoff]
    entries = _find_dotted_leader_toc(early_text, verbose=verbose)
    if entries:
        return entries

    # Tier 3: No TOC found -- return empty (caller handles fallback)
    return []


def _parse_toc_block(text: str, toc_start: int, verbose: bool = False) -> list[TOCEntry]:
    """Parse a structured TOC block starting after the TOC header.

    Scans lines until we hit the end of the TOC region (detected by
    a gap in dotted-leader lines or the start of article body text).
    """
    # Find a reasonable end boundary for the TOC block.
    # TOCs usually end before the first "ARTICLE" heading in the body text.
    # Also stop if we see 5+ consecutive non-TOC lines.
    lines = text[toc_start:].split("\n")

    entries: list[TOCEntry] = []
    current_article_num: str | None = None
    consecutive_non_toc = 0
    max_non_toc = 8  # allow some blank/noise lines within TOC

    for line in lines:
        raw = line.rstrip()

        # Skip noise
        if NOISE_RE.match(raw) or ROMAN_PAGE_RE.match(raw):
            consecutive_non_toc += 1
            if consecutive_non_toc > max_non_toc:
                break
            continue

        # Skip continuation headers -- merge with existing article
        if CONTINUATION_RE.search(raw):
            # Extract the article number from the continuation line
            cont_match = re.match(
                rf"^\s*(?:ARTICLE\s+)?({ROMAN_RE}|\d+)[.\s]+.*\(cont",
                raw, re.IGNORECASE,
            )
            if cont_match:
                num_str = cont_match.group(1)
                current_article_num = _normalize_num(num_str)
            consecutive_non_toc = 0
            continue

        # Try sub-section TOC line FIRST (indented lines with a parent article)
        m = SUB_SECTION_TOC_RE.match(raw)
        if m and current_article_num:
            sub_num, title, page = m.group(1), m.group(2), int(m.group(3))
            title = _clean_toc_title(title)
            parent = current_article_num
            # Compose section number as "PARENT.SUB"
            sec_num = f"{parent}.{sub_num}" if parent else sub_num
            entries.append(TOCEntry(
                number=sec_num, title=title, page_number=page,
                level=2, parent_number=parent,
            ))
            consecutive_non_toc = 0
            if verbose:
                print(f"  [TOC]   {sec_num}: {title} (p.{page})")
            continue

        # Try article-level TOC line
        m = ARTICLE_TOC_RE.match(raw)
        if m:
            num_str, title, page = m.group(1), m.group(2), int(m.group(3))
            num = _normalize_num(num_str)
            title = _clean_toc_title(title)
            current_article_num = num
            entries.append(TOCEntry(
                number=num, title=title, page_number=page,
                level=1, parent_number=None,
            ))
            consecutive_non_toc = 0
            if verbose:
                print(f"  [TOC] Art {num}: {title} (p.{page})")
            continue

        # Try non-article entry (Side Letters, Minimum Wage Rates, Index, etc.)
        m = NON_ARTICLE_TOC_RE.match(raw)
        if m:
            title, page = m.group(1).strip(), int(m.group(2))
            title = _clean_toc_title(title)
            # Skip index/appendix-like entries that are just page references
            if title.lower() in ("index",):
                consecutive_non_toc = 0
                continue
            entries.append(TOCEntry(
                number=title,  # Use title as the "number" for non-article entries
                title=title, page_number=page,
                level=1, parent_number=None,
            ))
            current_article_num = None  # Reset article context
            consecutive_non_toc = 0
            if verbose:
                print(f"  [TOC] {title} (p.{page})")
            continue

        # Try generic dotted-leader line as last resort
        m = DOTTED_LEADER_RE.match(raw)
        if m:
            prefix, page = m.group(1).strip(), int(m.group(2))
            # Try to parse the prefix as an article or sub-section
            entry = _parse_generic_toc_line(prefix, page, current_article_num)
            if entry:
                if entry.level == 1 and entry.number and entry.number != entry.title:
                    current_article_num = entry.number
                entries.append(entry)
                consecutive_non_toc = 0
                if verbose:
                    indent = "  " if entry.level >= 2 else ""
                    print(f"  [TOC] {indent}{entry.number}: {entry.title} (p.{entry.page_number})")
                continue

        # Line is not a TOC entry
        consecutive_non_toc += 1
        if consecutive_non_toc > max_non_toc:
            break

    # Post-processing: merge multi-line titles (rare but possible)
    entries = _merge_multiline_titles(entries)
    return entries


def _find_dotted_leader_toc(early_text: str, verbose: bool = False) -> list[TOCEntry]:
    """Tier 2: Find TOC by detecting a cluster of dotted-leader lines."""
    lines = early_text.split("\n")
    dotted_lines = []
    for i, line in enumerate(lines):
        if DOTTED_LEADER_RE.match(line.rstrip()):
            dotted_lines.append(i)

    # Need at least 5 dotted-leader lines in a cluster to call it a TOC
    if len(dotted_lines) < 5:
        return []

    # Find the densest cluster
    best_start = 0
    best_count = 0
    for i in range(len(dotted_lines)):
        # Count lines within 50-line window
        count = sum(1 for j in range(i, len(dotted_lines))
                    if dotted_lines[j] - dotted_lines[i] <= 60)
        if count > best_count:
            best_count = count
            best_start = i

    if best_count < 5:
        return []

    # Reconstruct the TOC block from the cluster region
    cluster_start_line = max(0, dotted_lines[best_start] - 2)
    cluster_end_line = dotted_lines[best_start + best_count - 1] + 2
    toc_block = "\n".join(lines[cluster_start_line:cluster_end_line + 1])

    return _parse_toc_block(toc_block, 0, verbose=verbose)


def _normalize_num(num_str: str) -> str:
    """Normalize an article number. Roman -> arabic string, arabic stays."""
    upper = num_str.upper().strip()
    if upper in ROMAN_MAP:
        return str(ROMAN_MAP[upper])
    return num_str.strip()


def _clean_toc_title(title: str) -> str:
    """Clean up a TOC title string."""
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    # Strip leading/trailing separators
    title = title.strip("-:. ")
    # Remove trailing dots that weren't caught
    title = re.sub(r"[.\u00b7\u2026]+\s*$", "", title)
    return title.strip()


def _parse_generic_toc_line(prefix: str, page: int, current_article: str | None) -> TOCEntry | None:
    """Try to parse a generic dotted-leader line prefix into a TOCEntry."""
    prefix = prefix.strip()

    # Try: "ARTICLE XII - Title" or "Article 5. Title"
    m = re.match(
        rf"^\s*(?:ARTICLE\s+)?({ROMAN_RE}|\d+)[.\s)-]+\s*(.+)",
        prefix, re.IGNORECASE,
    )
    if m:
        num = _normalize_num(m.group(1))
        title = _clean_toc_title(m.group(2))
        return TOCEntry(number=num, title=title, page_number=page, level=1)

    # Try: "  5. Voting Time" (sub-section, indented or with number prefix)
    m = re.match(r"^\s{2,}(\d+)[.\s)]+\s*(.+)", prefix)
    if m:
        sub_num = m.group(1)
        title = _clean_toc_title(m.group(2))
        sec_num = f"{current_article}.{sub_num}" if current_article else sub_num
        return TOCEntry(
            number=sec_num, title=title, page_number=page,
            level=2, parent_number=current_article,
        )

    # Non-article named entry
    if prefix and prefix[0].isupper() and len(prefix) >= 3:
        title = _clean_toc_title(prefix)
        return TOCEntry(number=title, title=title, page_number=page, level=1)

    return None


def _merge_multiline_titles(entries: list[TOCEntry]) -> list[TOCEntry]:
    """Merge consecutive entries that are actually multi-line titles.

    Detects when an entry has a suspiciously short title followed by
    an entry on the same page with no number -- likely a wrapped title.
    """
    if len(entries) < 2:
        return entries

    merged: list[TOCEntry] = []
    skip_next = False

    for i, entry in enumerate(entries):
        if skip_next:
            skip_next = False
            continue

        if i + 1 < len(entries):
            nxt = entries[i + 1]
            # If same page, next entry's number == its title (non-article),
            # and current title looks incomplete (no period, short)
            if (nxt.page_number == entry.page_number
                    and nxt.number == nxt.title
                    and len(entry.title) < 40
                    and not entry.title.endswith(".")):
                # Merge: append next title to current
                merged_title = f"{entry.title} {nxt.title}"
                merged.append(TOCEntry(
                    number=entry.number,
                    title=_clean_toc_title(merged_title),
                    page_number=entry.page_number,
                    level=entry.level,
                    parent_number=entry.parent_number,
                ))
                skip_next = True
                continue

        merged.append(entry)

    return merged


def toc_entries_to_json(entries: list[TOCEntry]) -> list[dict]:
    """Convert TOCEntry list to JSON-serializable dicts."""
    return [
        {
            "number": e.number,
            "title": e.title,
            "page_number": e.page_number,
            "level": e.level,
            "parent_number": e.parent_number,
        }
        for e in entries
    ]


def save_toc(cba_id: int, entries: list[TOCEntry]) -> None:
    """Save parsed TOC entries to cba_documents.toc_json."""
    toc_data = toc_entries_to_json(entries)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_documents SET toc_json = %s, updated_at = NOW() WHERE cba_id = %s",
                [json.dumps(toc_data), cba_id],
            )
            conn.commit()


def load_toc(cba_id: int) -> list[TOCEntry]:
    """Load previously parsed TOC from cba_documents.toc_json."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT toc_json FROM cba_documents WHERE cba_id = %s",
                [cba_id],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return []
            toc_data = row[0]
            if isinstance(toc_data, str):
                toc_data = json.loads(toc_data)
            return [
                TOCEntry(
                    number=e["number"],
                    title=e["title"],
                    page_number=e["page_number"],
                    level=e.get("level", 1),
                    parent_number=e.get("parent_number"),
                )
                for e in toc_data
            ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse TOC from a CBA contract")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    parser.add_argument("--verbose", action="store_true", help="Print each TOC entry")
    args = parser.parse_args()

    # Load full text
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

    print(f"Parsing TOC for cba_id={args.cba_id} ({len(text):,} chars, {page_count} pages)")

    entries = parse_toc(text, verbose=args.verbose)

    if not entries:
        # Fallback: use find_articles() from 03
        print("  No TOC found. Falling back to heading heuristic...")
        _art_mod = importlib.import_module("scripts.cba.03_find_articles")
        find_articles = _art_mod.find_articles
        get_document_data = _art_mod.get_document_data
        text2, spans = get_document_data(args.cba_id)
        if text2:
            chunks = find_articles(text2, spans)
            entries = [
                TOCEntry(
                    number=c.number,
                    title=c.title,
                    page_number=c.page_start or 0,
                    level=c.level,
                    parent_number=c.parent_number,
                )
                for c in chunks
            ]
            # Mark these as heuristic-based
            for e in entries:
                e._detection_method = "heading_heuristic"
        if not entries:
            print("  WARNING: No articles found even with heuristic.")

    # Count by level
    articles = [e for e in entries if e.level == 1]
    subs = [e for e in entries if e.level >= 2]
    print(f"  Found {len(entries)} TOC entries: {len(articles)} articles + {len(subs)} sub-sections")

    if args.verbose and entries:
        print("\n  TOC:")
        for e in entries:
            indent = "    " if e.level >= 2 else "  "
            parent_info = f" (under {e.parent_number})" if e.parent_number else ""
            print(f"  {indent}{e.number}. {e.title} --> p.{e.page_number}{parent_info}")

    save_toc(args.cba_id, entries)
    print(f"\n  TOC saved to cba_documents.toc_json ({len(entries)} entries)")


if __name__ == "__main__":
    main()
