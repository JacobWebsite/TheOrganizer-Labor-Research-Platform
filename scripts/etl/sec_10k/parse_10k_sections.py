"""Parse named sections out of locally-mirrored SEC 10-K HTML filings.

Step 3 of the 10-K text-mining foundation (24Q-16/17/19, Week 2/3 of the
2026-05-04 launch roadmap). Step 1 (`identify_recent_10k`) and step 2
(`download_10k_batch`) populated `files/sec_10k/{cik}/{accession}.html`;
this script reads those HTML files and extracts six text sections:

  * `business`        -- Item 1. Business (full text)
  * `risk_factors`    -- Item 1A. Risk Factors (full text)
  * `customers`       -- "Customers" / "Major Customers" / "Concentration of
                          Customers" subsection inside Item 1
  * `suppliers`       -- "Suppliers" / "Raw Materials" subsection
  * `distribution`    -- "Distribution" / "Sales and Marketing" subsection
  * `partners`        -- "Strategic Partners" / "Partnerships" subsection

Output goes to a new `sec_10k_sections` table. PK is
`(cik, accession, section)`. Resumable: re-running skips (cik, accession)
pairs whose all-six rows already exist.

This is a *scaffold* -- it produces clean text. Entity matching ("which
master_id does this 'Walmart' mention map to?") is a separate Week 4
concern.

Strategy
--------
1. Read HTML, strip `<script>` and `<style>`, extract text via BeautifulSoup
   `.get_text(separator='\n')`. Collapse blank lines.
2. Locate body section headers using a "biggest-gap" heuristic: among all
   lines beginning with `Item N.`, pick the one whose distance to the next
   item-marker is biggest. This robustly distinguishes the body section
   from table-of-contents references (which are short, tightly packed).
3. Extract sub-sections from inside Item 1 by scanning for short heading
   lines that match known sub-section keywords.

Usage
-----
::

    py scripts/etl/sec_10k/parse_10k_sections.py --limit 10        # smoke test
    py scripts/etl/sec_10k/parse_10k_sections.py                   # full corpus
    py scripts/etl/sec_10k/parse_10k_sections.py --reparse         # ignore existing rows
    py scripts/etl/sec_10k/parse_10k_sections.py --cik 51143       # single filer

Verification
------------
::

    SELECT section, COUNT(*) FROM sec_10k_sections GROUP BY section;
    -- A healthy run should show roughly equal counts of `business` /
    -- `risk_factors` and somewhat smaller counts for the sub-section types.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from db_config import get_connection  # noqa: E402

# bs4 emits this when it sees inline-XBRL 10-Ks; the lxml HTML parser still
# extracts the text we need, so the warning is noise.
try:
    from bs4 import XMLParsedAsHTMLWarning  # type: ignore
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    pass

_log = logging.getLogger("etl.sec_10k.parse")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

DDL_SECTIONS = """
CREATE TABLE IF NOT EXISTS sec_10k_sections (
    cik         BIGINT      NOT NULL,
    accession   VARCHAR(32) NOT NULL,
    section     VARCHAR(32) NOT NULL,
    text        TEXT        NOT NULL,
    char_count  INTEGER     NOT NULL,
    parsed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cik, accession, section)
);
CREATE INDEX IF NOT EXISTS ix_sec_10k_sections_section
    ON sec_10k_sections (section);
CREATE INDEX IF NOT EXISTS ix_sec_10k_sections_cik
    ON sec_10k_sections (cik);
"""


def ensure_tables(conn) -> None:
    """Create the sections table if missing. DDL needs autocommit per CLAUDE.md."""
    prior = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_SECTIONS)
    finally:
        conn.autocommit = prior


# --------------------------------------------------------------------------
# Section types
# --------------------------------------------------------------------------

# All six section keys we write to the table.
SECTION_BUSINESS = "business"
SECTION_RISK_FACTORS = "risk_factors"
SECTION_CUSTOMERS = "customers"
SECTION_SUPPLIERS = "suppliers"
SECTION_DISTRIBUTION = "distribution"
SECTION_PARTNERS = "partners"

ALL_SECTIONS = (
    SECTION_BUSINESS,
    SECTION_RISK_FACTORS,
    SECTION_CUSTOMERS,
    SECTION_SUPPLIERS,
    SECTION_DISTRIBUTION,
    SECTION_PARTNERS,
)

# Sub-section keyword groups. The keys here are the canonical section name
# we store in the DB; the values are regex fragments matching heading-line
# variants we've observed in real 10-K filings.
#
# The matcher is forgiving: any heading line whose lowercased text contains
# one of these substrings (after stripping a trailing colon) is accepted.
# Real 10-Ks vary widely -- e.g. American Express uses "Diverse Customer
# Base and Global Footprint", Howmet uses "Sales by Market and Significant
# Customer Revenue", Abbott uses "Seasonal Aspects, Customers, and
# Renegotiation". We don't try to exactly match "Customers" alone.
SUBSECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    SECTION_CUSTOMERS: (
        "customer",          # singular or plural; covers most variants
        "concentration of",  # "concentration of customers" / "of credit"
    ),
    SECTION_SUPPLIERS: (
        "supplier",
        "raw material",
        "sources and availability",
        "supply chain",
        "key vendor",
    ),
    SECTION_DISTRIBUTION: (
        "distribution",
        "sales and marketing",
        "sales, marketing",
        "sales and distribution",
        "marketing and distribution",
        "distribution channel",
    ),
    SECTION_PARTNERS: (
        "strategic partner",
        "strategic alliance",
        "joint venture",
        "collaboration",
        "partnership",
    ),
}


# --------------------------------------------------------------------------
# HTML -> clean text
# --------------------------------------------------------------------------


def html_to_clean_text(html: str) -> str:
    """Convert raw 10-K HTML into newline-separated clean prose.

    Strips `<script>` and `<style>` first; uses ``BeautifulSoup`` with the
    `lxml` HTML parser; collapses blank lines so subsequent regexes can rely
    on `^...$` semantics for short header lines.

    Returns an empty string on parse errors.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:  # noqa: BLE001
        _log.debug("BeautifulSoup parse failed: %s", e)
        return ""
    for tag in soup(["script", "style"]):
        tag.decompose()
    raw = soup.get_text(separator="\n")
    # Normalize: strip each line, drop empties, collapse runs of whitespace.
    lines = []
    for ln in raw.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        # Collapse internal whitespace runs to single spaces.
        ln = re.sub(r"[ \t]+", " ", ln)
        lines.append(ln)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Section header location
# --------------------------------------------------------------------------


# Pattern element: "Item N." possibly followed by a section title, on a line.
# Letter portion is `[A-C]?` (most 10-Ks go up to Item 1C cybersecurity).
_ITEM_LINE_PATTERN = re.compile(
    r"(?:^|\n)([ \t]*item\s+\d+[a-c]?\b\.?[^\n]{0,160})",
    re.IGNORECASE,
)


def _all_item_header_positions(text: str, max_header_line_chars: int = 120) -> list[int]:
    """Return positions of every line that looks like an SEC Item N header."""
    positions: list[int] = []
    for m in _ITEM_LINE_PATTERN.finditer(text):
        line = m.group(1)
        if len(line) <= max_header_line_chars:
            positions.append(m.start(1))
    return sorted(set(positions))


def find_section_body(
    text: str,
    item_num: str,
    *,
    min_body_chars: int = 1500,
    max_header_line_chars: int = 120,
) -> tuple[int, int] | None:
    """Locate the body of an SEC 10-K Item N section.

    Strategy
    --------
    Among all lines that look like ``Item {item_num}.`` headers, return the
    one whose distance to the *next* item-header (any number) is biggest.
    Real body sections have thousands of characters of prose; TOC entries
    are tightly packed (~20-50 chars per item). Returns ``None`` when no
    candidate exceeds ``min_body_chars``.

    Returns
    -------
    ``(start, end)`` byte positions in ``text``, or ``None`` if no body
    section was located.
    """
    pat = re.compile(
        rf"(?:^|\n)([ \t]*item\s+{re.escape(item_num)}\b\.?[^\n]{{0,160}})",
        re.IGNORECASE,
    )
    candidates: list[int] = []
    for m in pat.finditer(text):
        line = m.group(1)
        if len(line) <= max_header_line_chars:
            candidates.append(m.start(1))

    all_positions = _all_item_header_positions(text, max_header_line_chars)

    best: tuple[int, int] | None = None
    best_gap = 0
    for s in candidates:
        next_pos = None
        for p in all_positions:
            if p > s + 5:  # past this header line itself
                next_pos = p
                break
        if next_pos is None:
            next_pos = len(text)
        gap = next_pos - s
        if gap >= min_body_chars and gap > best_gap:
            best = (s, next_pos)
            best_gap = gap
    return best


# --------------------------------------------------------------------------
# Sub-section detection (Customers / Suppliers / Distribution / Partners)
# --------------------------------------------------------------------------


def _looks_like_heading(line: str, max_header_line_chars: int = 90) -> bool:
    """Heuristic: does this line look like a section heading rather than prose?

    Heading characteristics:
      * Short (<= max_header_line_chars)
      * Doesn't end in a sentence period (a trailing colon is fine)
      * Starts with an uppercase letter (or is fully uppercase)
      * Has reasonable letter density (not "$1,234,567")
    """
    s = line.strip()
    if not s or len(s) > max_header_line_chars or len(s) < 2:
        return False
    # Skip lines that are clearly sentences (end with a period that isn't
    # the final period of an abbreviation).
    if s.endswith(".") and not re.search(r"\b[A-Z]\.\s*$", s):
        return False
    # Mostly letters, not numbers / punctuation.
    if sum(c.isalpha() for c in s) < max(3, len(s) * 0.5):
        return False
    # Must start with uppercase or digit (some 10-Ks use "1. Customers").
    if not (s[0].isupper() or s[0].isdigit()):
        return False
    return True


def find_subsection(
    item1_text: str,
    keywords: tuple[str, ...],
    *,
    max_chars: int = 12_000,
    max_header_line_chars: int = 90,
) -> str | None:
    """Find a sub-section inside Item 1 prose by short-heading detection.

    Strategy
    --------
    1. Walk line-by-line through ``item1_text``.
    2. A line qualifies as a heading if ``_looks_like_heading`` says yes.
    3. A heading matches our subsection if its lowercased form contains any
       of the ``keywords`` substrings.
    4. Capture the heading and everything up to the next heading-like line
       OR ``max_chars`` ahead, whichever is first.

    Real 10-K headings are highly variable -- "Diverse Customer Base and
    Global Footprint" / "Sources and Availability of Raw Materials" /
    "Seasonal Aspects, Customers, and Renegotiation". The substring match
    is forgiving by design.

    Returns the captured text or ``None`` if no heading was found.
    """
    if not item1_text:
        return None

    # Walk through the text line by line. Track byte offsets.
    lines = item1_text.split("\n")
    line_starts: list[int] = []
    pos = 0
    for ln in lines:
        line_starts.append(pos)
        pos += len(ln) + 1  # +1 for the newline

    # First pass: pick the first heading-line whose lowercased text contains
    # any keyword. Avoid matching "Item 1." style item-headers themselves.
    matched_idx = -1
    for i, ln in enumerate(lines):
        if not _looks_like_heading(ln, max_header_line_chars):
            continue
        s = ln.strip()
        # Skip if this looks like an item-header line ("Item 1.", "ITEM 1A").
        if re.match(r"^item\s+\d+[a-c]?\b", s, re.IGNORECASE):
            continue
        # Skip if this is the Item 1 title line ("Business" alone).
        if s.lower() in ("business", "general"):
            continue
        s_low = s.lower().rstrip(":").strip()
        if any(kw in s_low for kw in keywords):
            matched_idx = i
            break

    if matched_idx < 0:
        return None

    start_offset = line_starts[matched_idx]

    # Find the next heading-like line. End the section there.
    end_offset = min(start_offset + max_chars, len(item1_text))
    for j in range(matched_idx + 1, len(lines)):
        candidate = lines[j]
        # Skip: itself the same keyword (e.g. repeated word in a sub-bullet).
        if not _looks_like_heading(candidate, max_header_line_chars):
            continue
        s = candidate.strip()
        s_low = s.lower().rstrip(":").strip()
        # If this heading also matches our keywords, treat it as a continuation
        # (subsections like "Customers in EMEA" / "Customers in Asia").
        if any(kw in s_low for kw in keywords):
            continue
        # Found the next non-related heading.
        end_offset = line_starts[j]
        break

    if end_offset - start_offset < 50:
        return None

    return item1_text[start_offset:end_offset].strip()


# --------------------------------------------------------------------------
# Top-level: parse one filing
# --------------------------------------------------------------------------


@dataclass
class ParsedFiling:
    cik: int
    accession: str
    sections: dict[str, str]   # section_name -> text
    error: str | None = None


def parse_filing(
    cik: int,
    accession: str,
    html: str,
    *,
    min_body_chars: int = 1500,
) -> ParsedFiling:
    """Parse a single 10-K HTML body into named sections.

    The result's ``sections`` dict will only contain entries for sections
    we actually found. Empty / missing sections are not stored.

    Errors during HTML cleanup are caught and recorded in ``error`` so that
    the caller can mark the filing as ``parse_error`` rather than crash the
    whole batch.
    """
    out = ParsedFiling(cik=cik, accession=accession, sections={})
    try:
        text = html_to_clean_text(html)
    except Exception as e:  # noqa: BLE001
        out.error = f"html_to_clean_text exception: {e!r}"
        return out

    if not text or len(text) < 1000:
        out.error = f"text too short ({len(text)} chars after HTML strip)"
        return out

    # ---- Item 1 (Business) and Item 1A (Risk Factors) ----
    item1_loc = find_section_body(text, "1", min_body_chars=min_body_chars)
    item1a_loc = find_section_body(text, "1A", min_body_chars=min_body_chars)

    if item1_loc is not None:
        out.sections[SECTION_BUSINESS] = text[item1_loc[0] : item1_loc[1]].strip()
    if item1a_loc is not None:
        out.sections[SECTION_RISK_FACTORS] = text[item1a_loc[0] : item1a_loc[1]].strip()

    # ---- Sub-sections inside Item 1 ----
    item1_text = out.sections.get(SECTION_BUSINESS, "")
    if item1_text:
        for sub_name, kw in SUBSECTION_KEYWORDS.items():
            captured = find_subsection(item1_text, kw)
            if captured:
                out.sections[sub_name] = captured

    return out


# --------------------------------------------------------------------------
# DB I/O
# --------------------------------------------------------------------------

UPSERT_SECTION = """
INSERT INTO sec_10k_sections (cik, accession, section, text, char_count, parsed_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (cik, accession, section) DO UPDATE SET
    text       = EXCLUDED.text,
    char_count = EXCLUDED.char_count,
    parsed_at  = EXCLUDED.parsed_at
"""


def write_sections(conn, parsed: ParsedFiling) -> int:
    """Upsert all parsed sections for one filing. Returns rows written."""
    if not parsed.sections:
        return 0
    rows_written = 0
    with conn.cursor() as cur:
        for section, body in parsed.sections.items():
            body = body or ""
            cur.execute(
                UPSERT_SECTION,
                (parsed.cik, parsed.accession, section, body, len(body)),
            )
            rows_written += 1
    conn.commit()
    return rows_written


SELECT_DOWNLOADED = """
SELECT p.cik, p.accession, p.file_path, f.company_name
FROM load_sec_10k_progress p
LEFT JOIN sec_10k_filings_to_download f
       ON f.cik = p.cik AND f.accession = p.accession
WHERE p.status IN ('downloaded', 'cached')
  AND p.file_path IS NOT NULL
  {extra_clause}
{cik_clause}
ORDER BY p.cik
{limit_clause}
"""

EXISTING_PARSED_CIKS = """
SELECT DISTINCT cik, accession
FROM sec_10k_sections
"""


def fetch_targets(
    conn,
    *,
    limit: int | None,
    reparse: bool,
    cik_filter: int | None,
) -> list[tuple[int, str, str, str | None]]:
    """Read the list of (cik, accession, file_path, company_name) to parse.

    Skips rows already in ``sec_10k_sections`` unless ``reparse`` is True.
    ``cik_filter`` narrows to a single CIK for debugging.
    """
    extra_clause = ""
    cik_clause = ""
    limit_clause = ""
    if cik_filter is not None:
        cik_clause = f"AND p.cik = {int(cik_filter)}"
    if limit and limit > 0:
        limit_clause = f"LIMIT {int(limit)}"
    sql = SELECT_DOWNLOADED.format(
        extra_clause=extra_clause,
        cik_clause=cik_clause,
        limit_clause=limit_clause,
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    if reparse or not rows:
        return [(int(r[0]), r[1], r[2], r[3]) for r in rows]

    with conn.cursor() as cur:
        cur.execute(EXISTING_PARSED_CIKS)
        already = {(int(r[0]), r[1]) for r in cur.fetchall()}
    return [
        (int(r[0]), r[1], r[2], r[3])
        for r in rows
        if (int(r[0]), r[1]) not in already
    ]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap on filings to parse (0 = no cap).",
    )
    ap.add_argument(
        "--reparse",
        action="store_true",
        help="Ignore existing rows in sec_10k_sections and re-parse.",
    )
    ap.add_argument(
        "--cik",
        type=int,
        default=None,
        help="Only parse a single CIK (debugging).",
    )
    ap.add_argument(
        "--min-body-chars",
        type=int,
        default=1500,
        help="Minimum body length for a candidate to qualify as the body section.",
    )
    args = ap.parse_args()

    conn = get_connection()
    ensure_tables(conn)

    targets = fetch_targets(
        conn,
        limit=args.limit if args.limit > 0 else None,
        reparse=args.reparse,
        cik_filter=args.cik,
    )
    _log.info("parsing targets: %d filings", len(targets))

    n_ok = 0
    n_partial = 0
    n_errored = 0
    n_full_coverage = 0  # all 3 of business/risk_factors/customers found
    sections_total = 0

    for i, (cik, accession, file_path, company_name) in enumerate(targets, start=1):
        path = Path(file_path)
        if not path.exists():
            _log.warning(
                "[%d/%d] CIK %s file missing: %s",
                i,
                len(targets),
                cik,
                file_path,
            )
            n_errored += 1
            continue
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            _log.warning("[%d/%d] CIK %s read failed: %s", i, len(targets), cik, e)
            n_errored += 1
            continue

        try:
            parsed = parse_filing(
                cik, accession, html, min_body_chars=args.min_body_chars
            )
        except Exception as e:  # noqa: BLE001
            _log.warning(
                "[%d/%d] CIK %s parse_filing exception: %s",
                i, len(targets), cik, e,
            )
            n_errored += 1
            continue

        if parsed.error:
            _log.warning(
                "[%d/%d] CIK %s parse error: %s",
                i, len(targets), cik, parsed.error,
            )
            n_errored += 1
            continue

        try:
            written = write_sections(conn, parsed)
        except Exception as e:  # noqa: BLE001
            _log.warning(
                "[%d/%d] CIK %s db write failed: %s",
                i, len(targets), cik, e,
            )
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            n_errored += 1
            continue

        sections_total += written
        if written == 0:
            n_errored += 1
        elif {SECTION_BUSINESS, SECTION_RISK_FACTORS}.issubset(parsed.sections):
            n_ok += 1
            if SECTION_CUSTOMERS in parsed.sections:
                n_full_coverage += 1
        else:
            n_partial += 1

        if i <= 5 or i % 50 == 0:
            sec_keys = sorted(parsed.sections.keys())
            _log.info(
                "[%d/%d] CIK %s %s -> %d sections %s",
                i,
                len(targets),
                cik,
                (company_name or "?")[:40],
                written,
                sec_keys,
            )

    conn.close()
    _log.info(
        "done: %d ok, %d partial, %d errored; %d full-coverage (all of "
        "business/risk_factors/customers); %d total section rows written",
        n_ok,
        n_partial,
        n_errored,
        n_full_coverage,
        sections_total,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
