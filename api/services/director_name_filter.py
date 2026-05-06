"""Filter parser-garbage director names from `employer_directors`.

The DEF14A parsers (per_director_minitable, big_summary_table,
director_comp_table, profile_block, bio_paragraph) admitted false-
positives for a few category-shaped strings:
  - Single-word title fragments  ("Chief", "Senior", "Vice")
  - Title phrases                ("Chief Financial Officer", "President and")
  - Section headers              ("Continuing Directors", "DEF 14A")
  - Bio-paragraph lead-ins       ("Planner. Michael A. Wheeler")
  - Investor entities            ("Khosla Ventures, LLC (6)")

This module provides:
  - `is_likely_real_director_name(name)` — pure-Python predicate; use
    when post-processing an already-fetched list.
  - `SQL_FILTER_CLAUSE` — string fragment for `WHERE` clauses; use when
    pushing the filter into Postgres for set-level performance.

Discovered 2026-05-05 while building the director permalink endpoint.
Top "directors" by board count were all parser garbage (Chief = 202
boards, DEF 14A = 169 boards). Filter at SELECT time so future parser
improvements just lower the noise level rather than requiring a one-time
cleanup pass.
"""
from __future__ import annotations

# First-word lowercased blacklist. If the first whitespace-delimited
# token of a director name (lowercased, comma-stripped) appears here,
# reject. Mirrors the section-headings-as-names false-positive class.
_BAD_FIRST_WORDS: frozenset[str] = frozenset({
    "chief", "president", "executive", "chairman", "director", "directors",
    "officer", "vice", "senior", "audit", "continuing", "independent",
    "outside", "new", "other", "principal", "lead", "committee",
    "committees", "def", "planner", "treasurer", "corporate", "class",
    "professional", "qualifications", "experience", "background",
    "managing", "founder", "co-founder",
    # 2026-05-05: catch proxy-statement page-header text. Top hits before
    # this addition: "All directors and" 15, "2026 Proxy Statement 15" 15,
    # "CEO and" 9. Adding "all", "ceo", and the year-prefix patterns.
    "all", "ceo", "an", "a", "the",
    # Additional 2026-05-05: page-nav and section-header text
    "our", "back", "general", "deputy", "assistant",
    "as", "with", "to", "for", "from", "on", "in", "by",
})

# Substring blacklist (lowercased, partial match). Catches multi-word
# phrases that aren't covered by the first-word filter alone.
_BAD_SUBSTRINGS: tuple[str, ...] = (
    "def 14a",
    "continuing directors",
    "independent directors",
    "outside directors",
    "class i directors",
    "class ii directors",
    "class iii directors",
    "audit committee",
    "directors are",
    "venture",          # "Khosla Ventures, LLC"
    "ltd. (",           # entity wrappers
    "llc (",
    "inc. (",
    "lp (",
    "and his ",         # bio-paragraph lead-ins
    "and her ",
    "proxy statement",  # 2026-05-05: page-header text leaking through
    "page ",
    "table of contents",
)


def is_likely_real_director_name(name: str | None) -> bool:
    """Return True if `name` looks like a real person's name (not parser
    garbage). Conservative: false negatives possible (some real names
    rejected) but false positives kept low.

    Rules:
      1. Must be a non-empty string.
      2. Must have >= 2 whitespace-delimited tokens.
      3. First token (lowercased, comma-stripped) must NOT be in
         `_BAD_FIRST_WORDS`.
      4. Lowercased name must NOT contain any `_BAD_SUBSTRINGS`.
      5. Length 4-80 chars (filters single chars + bio paragraphs that
         leaked through).
    """
    if not name:
        return False
    s = name.strip()
    if not (4 <= len(s) <= 80):
        return False
    tokens = s.split()
    if len(tokens) < 2:
        return False
    first_word = tokens[0].lower().rstrip(".,;:")
    if first_word in _BAD_FIRST_WORDS:
        return False
    # 2026-05-05: Reject anything containing a 4-digit year-like number.
    # Real names don't have years embedded; page-header artifacts like
    # "2026 Proxy Statement 15" do. Year range chosen broadly (1900-2099)
    # to allow for any future proxy that might include "since 1995" etc.
    # — but those would be malformed anyway.
    import re
    if re.search(r"\b(19|20)\d{2}\b", s):
        return False
    # Reject if first token is purely a number (e.g. "12 2026 Proxy...")
    if first_word.isdigit():
        return False
    lname = s.lower()
    if any(bad in lname for bad in _BAD_SUBSTRINGS):
        return False
    return True


# SQL filter clause for use in WHERE conditions. Mirrors the Python
# predicate but skips the year-regex check (regex isn't easily
# parameterizable here; callers needing the year-filter should run
# `is_likely_real_director_name()` post-fetch instead — see
# `api/routers/directors.py` for the canonical pattern). For most
# practical filtering this still removes 90%+ of the parser garbage
# at the DB layer, leaving a small Python pass to clean the residue.
SQL_FILTER_CLAUSE = """
    director_name IS NOT NULL
    AND LENGTH(TRIM(director_name)) BETWEEN 4 AND 80
    AND ARRAY_LENGTH(STRING_TO_ARRAY(TRIM(director_name), ' '), 1) >= 2
    AND LOWER(SPLIT_PART(TRIM(director_name), ' ', 1)) NOT IN %(bad_first)s
    AND NOT EXISTS (
        SELECT 1 FROM UNNEST(%(bad_subs)s::text[]) AS sub
        WHERE LOWER(director_name) LIKE '%%' || sub || '%%'
    )
""".strip()


def sql_filter_params() -> dict:
    """Return the params dict matching `SQL_FILTER_CLAUSE`."""
    return {
        "bad_first": tuple(_BAD_FIRST_WORDS),
        "bad_subs": list(_BAD_SUBSTRINGS),
    }


# --------------------------------------------------------------------------
# Slug helpers (URL-friendly forms of director names)
# --------------------------------------------------------------------------


def name_to_slug(name: str) -> str:
    """Convert a director name to a URL slug.

    'Adam D. Portnoy (3)' -> 'adam-d-portnoy-3'
    'Nancy Yao'           -> 'nancy-yao'
    'LeAnne M. Zumwalt'   -> 'leanne-m-zumwalt'

    Slug is reversible only by going through the DB lookup
    (`SELECT director_name WHERE LOWER(...) = slug` won't work because
    the slug normalizes punctuation and case). The endpoint must
    accept the slug and resolve it via case-insensitive prefix +
    Python predicate.
    """
    import re
    if not name:
        return ""
    s = name.lower()
    # Replace any non-alphanumeric run with a single hyphen.
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
