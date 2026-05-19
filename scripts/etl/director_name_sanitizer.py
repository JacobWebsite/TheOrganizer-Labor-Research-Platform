"""Sanitize SEC DEF14A director-name extraction artifacts.

Background (2026-05-18): the DEF14A parser
(`scripts/etl/load_def14a_directors.py`) extracts director names from proxy
statements via heuristic title-keyword boundaries. When the HTML layout
puts role text *before* the recognized boundary keyword (e.g. "Cecile B.
Harper, Director Age: 65 ..."), or when company-name / section-header
tokens precede the boundary (e.g. "Robert A. Bradway Boeing Director Age:
65 ..."), the leading slice that becomes the director name keeps those
trailing artifacts.

Round 3 Agent F (`docs/scratch/director_filter_audit_2026_05_18.md`)
flagged 2 of 25 top-N rows have "Cecile B. Harper, Director"-style
suffixes. Round 1 Agent 4's BoardCard audit found 11 Boeing directors all
with `" Boeing"` suffix and 12 Pfizer directors with `" KEY"` title-
bleed.

This module is the **single source of truth** for the post-extraction
artifact-strip regexes. It is used both:
  1. By the live parser (`_norm_director_name` calls
     `sanitize_director_name`) so newly extracted rows are clean.
  2. By the one-shot back-fix script
     (`scripts/maintenance/backfix_def14a_director_artifacts.py`) that
     re-cleans existing `employer_directors.director_name` rows.

The patterns are deliberately conservative -- we only strip when the
suffix is unambiguously *not* a real name component. Negative-test
guards in `tests/etl/test_def14a_director_name_sanitize.py`:
  - "James W. Director" (surname=Director) MUST survive.
  - "Alex Boeing" (surname=Boeing) MUST survive.
  - "Asia Director" (real name w/ Director surname) MUST survive.

Use:
    from scripts.etl.director_name_sanitizer import sanitize_director_name
    clean = sanitize_director_name("Cecile B. Harper, Director")
    # -> "Cecile B. Harper"
"""
from __future__ import annotations

import re

# --- Role tags that bleed into the name via the comma-separator pattern ---
# These are *titles* that follow a name and are joined by a comma in some
# proxy layouts. The comma is the signal that the trailing word is a role
# tag, not a surname. (Real surnames don't sit after a comma in directory
# data unless it's a suffix like "Jr." which is matched separately.)
_ROLE_TAG_KEYWORDS = (
    r"Director|Chairman|Chairwoman|Chairperson|Chair|"
    r"President|CEO|CFO|COO|"
    r"Vice\s+Chair(?:man|woman|person)?|"
    r"Lead\s+Director|Lead\s+Independent\s+Director|"
    r"Independent\s+Director|"
    r"Executive\s+Chair(?:man|woman|person)?|"
    r"Non-Executive\s+Chair(?:man|woman|person)?"
)

# ",\s*<ROLE>\s*$"  -- "Cecile B. Harper, Director" -> "Cecile B. Harper"
# Strip iteratively in case of multiple comma-separated roles.
_COMMA_ROLE_SUFFIX_RE = re.compile(
    rf",\s*(?:{_ROLE_TAG_KEYWORDS})\s*$",
    re.IGNORECASE,
)

# "\s+-+\s+<ROLE>\s*$" -- "John Smith - Director" / "Jane Doe -- Chairman"
# These hyphen-separated layouts bleed when the parser captures past the
# hyphen boundary.
_DASH_ROLE_SUFFIX_RE = re.compile(
    rf"\s+-{{1,3}}\s*(?:{_ROLE_TAG_KEYWORDS})\s*$",
    re.IGNORECASE,
)

# Standalone ALL-CAPS single-token bleed at end of name. Pfizer's proxy
# header reads "KEY EXPERIENCES & EXPERTISE" near the name, and the
# title-boundary regex sometimes lands on "EXPERIENCES" leaving "KEY"
# stuck on the name. We strip an ALL-CAPS token that's 2-12 chars long
# IF AND ONLY IF it is *not* a recognized honorific suffix.
#
# Allowed honorific / credential suffixes (must NOT be stripped):
#   Jr, Sr, II, III, IV, V, VI, MD, PHD, ESQ, CPA, JD, DDS, DVM, RN, MBA,
#   USA, USN (military retirement common in proxy bios).
_ALLOWED_TRAILING_TOKEN = {
    "JR", "SR", "II", "III", "IV", "V", "VI", "VII", "VIII",
    "MD", "PHD", "ESQ", "JD", "CPA", "DDS", "DVM", "RN", "MBA",
    "USN", "USA", "USAF", "USMC", "USCG",  # military retirements
    "DDS", "DSC", "DBA", "DPA", "EDD",
}
_TRAILING_ALLCAPS_RE = re.compile(r"\s+([A-Z]{2,12})\s*$")


# Comma-stripped credentials that should remain ("MD"/"PhD" with comma
# pattern). These appear in the Pfizer data as "Albert Bourla, DVM,
# Ph.D. KEY". The "KEY" is the artifact, NOT the credentials.
def _is_allowed_trailing_caps(token: str) -> bool:
    """ALL-CAPS token that is a known honorific / credential."""
    return token.upper().strip(".") in _ALLOWED_TRAILING_TOKEN


# Mixed-case bleed for the title-keyword "Key" -- Pfizer's mixed-case
# fallback layout has "Key Skills" not "KEY EXPERIENCES" and the parser
# can still strand "Key" on the end. Strict whole-word "Key" at end is
# never a surname, so a strip is safe.
_TRAILING_KEY_RE = re.compile(r"\s+Key\s*$")


# --- Company-name suffix bleed ---
# When the parser's PROFILE_BLOCK strategy extracts the name from text
# like "Robert A. Bradway Boeing Director Age: 65 ..." the title-boundary
# regex lands on "Director", leaving "Robert A. Bradway Boeing".
#
# This is the trickiest pattern: real surnames CAN match company names
# ("Alex Boeing" is a possible legit name). We only strip when the
# trailing token is in a known set of company-name bleed sources that
# have shown up in the live data. Tested via the live DB:
#   Boeing: 11 rows from CIK 12927 (Boeing's own DEF14A proxy).
#   Apple:  1 row from Apple's proxy ("Timothy J. Apple" = Tim Cook).
#
# The list is an explicit hardcoded set, not an open-ended company
# database lookup, to keep behavior predictable and audit-friendly.
_COMPANY_SUFFIX_STOPWORDS = frozenset({
    "Boeing", "Pfizer", "Apple",  # confirmed from 2026-05-18 audit
    # Future entries: only add when a backfill audit confirms multiple
    # rows with this exact suffix on a filing for that company.
})
_TRAILING_COMPANY_RE = re.compile(
    r"\s+(" + "|".join(re.escape(w) for w in _COMPANY_SUFFIX_STOPWORDS) + r")\s*$"
)


def _strip_company_suffix(name: str, filer_company: str | None = None) -> str:
    """Strip a trailing known-company-name token.

    Two strip modes:
      (a) Aggressive mode -- when `filer_company` is provided AND the
          suffix token matches the filer company name. In that case any
          remaining 2+ word name is stripped. This handles the live
          production case: directors of Boeing's DEF14A all have the
          token "Boeing" appended; the filer name is "The Boeing
          Company", so we know with high confidence the strip is safe.
      (b) Conservative mode -- when `filer_company` is None (or doesn't
          match), require 3+ words OR a punctuated initial after strip.
          This protects "Alex Boeing" (2-word real-surname case) when
          there's no contextual signal.

    Why two modes: at the level of the live parser
    (`_norm_director_name`) we don't always have the filer name (the
    function is also called from merge / dedup paths). The conservative
    default keeps `_norm_director_name` safe; the parser's
    `write_directors` path can later wire in the filer name via the
    `sanitize_with_filer_context` helper for stricter cleanup.

    Trade-off acknowledged: conservative mode leaves some 2-word
    bleeds (e.g. "Akhil Johri Boeing") in place when no filer context
    is available. The back-fix script supplies the filer name from
    `employer_directors.filing_cik` -> `sec_companies.company_name`,
    so the one-shot historical cleanup gets the aggressive mode.
    """
    m = _TRAILING_COMPANY_RE.search(name)
    if not m:
        return name
    suffix_token = m.group(1)
    candidate_after_strip = name[: m.start()].strip()
    words_after = candidate_after_strip.split()
    if not words_after:
        return name
    # Aggressive mode: filer company matches the suffix token.
    if filer_company:
        filer_lower = filer_company.lower()
        # "Boeing" matches "The Boeing Company", "Boeing Co." etc.
        if suffix_token.lower() in filer_lower:
            if len(words_after) >= 2:
                return candidate_after_strip
    # Conservative mode: require 3+ words OR punctuated initial.
    # \b[A-Z]\.\b would fail at end-of-string because . isn't a word char
    # and word-boundary won't match between . and EOL; use lookahead for
    # whitespace OR end.
    has_initial = bool(re.search(r"\b[A-Z]\.(?=\s|$)", candidate_after_strip))
    if len(words_after) >= 3 or has_initial:
        return candidate_after_strip
    return name


def sanitize_director_name(name: str, filer_company: str | None = None) -> str:
    """Strip role-tag / company-name / title-bleed suffixes from a
    director name extracted by the DEF14A parser.

    Applied in order:
      1. Comma-separated role-tag suffix (", Director" / ", Chairman").
      2. Dash-separated role suffix (" - Director" / " -- Chairman").
      3. "Key" trailing token (mixed-case Pfizer bleed).
      4. ALL-CAPS trailing token of 2-12 chars (if not an honorific).
      5. Known company-name token (Boeing/Pfizer/Apple). Aggressive
         when `filer_company` is supplied AND matches the suffix;
         conservative (requires 3+ words OR a punctuated initial) when
         no filer context is available.

    `filer_company` is the issuer's name from the DEF14A filing (e.g.
    "The Boeing Company"). When provided, enables a safer cleanup of
    company-name suffix bleeds for the matching filer; when omitted,
    a conservative threshold protects 2-word real-surname cases like
    "Alex Boeing".

    Whitespace/punctuation are normalized at the start and end. Iterates
    until the name is stable (multiple suffixes can be chained).

    Returns the cleaned name. Empty / None inputs return empty string.
    """
    if not name:
        return ""
    s = re.sub(r"\s+", " ", name).strip(" ,;.|")
    prev = None
    while prev != s:
        prev = s
        # 1. Comma-role bleed -- iterate (handles ", Chair, President")
        new_s = _COMMA_ROLE_SUFFIX_RE.sub("", s).strip(" ,;.|")
        if new_s != s:
            s = new_s
            continue
        # 2. Dash-role bleed
        new_s = _DASH_ROLE_SUFFIX_RE.sub("", s).strip(" ,;.-|")
        if new_s != s:
            s = new_s
            continue
        # 3. Trailing "Key" (mixed-case)
        new_s = _TRAILING_KEY_RE.sub("", s).strip(" ,;.|")
        if new_s != s:
            s = new_s
            continue
        # 4. Trailing ALL-CAPS token (if not an honorific). Must check
        # explicitly so we don't strip "Jane Doe, MD" (the comma+MD
        # pattern is the legit honorific case).
        m = _TRAILING_ALLCAPS_RE.search(s)
        if m and not _is_allowed_trailing_caps(m.group(1)):
            # And ALSO check the slice before the strip would still leave
            # a reasonable name (at least 2 tokens with a capitalized lead)
            cand = s[: m.start()].strip(" ,;.|")
            words = cand.split()
            if len(words) >= 2 and cand[0:1].isupper():
                s = cand
                continue
        # 5. Trailing company-name token (Boeing/Pfizer/Apple)
        new_s = _strip_company_suffix(s, filer_company=filer_company)
        if new_s != s:
            s = new_s
            continue
    return s
