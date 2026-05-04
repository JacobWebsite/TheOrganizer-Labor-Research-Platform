"""
24Q-12 Board of Directors -- DEF14A proxy parser.

Loads board-of-directors data from SEC DEF14A (proxy statement) filings.
Mirrors the architecture of `load_sec_exhibit21.py`: discover the latest
DEF14A per filer via EDGAR submissions JSON, fetch the document, then
extract director rows via a sequence of parser strategies.

Three parser strategies (`parse_directors`):
  1. per-director mini-table (Starbucks, Abbott patterns) -- per-director
     small table with 'NAME age N director since YYYY' or
     'NAME director since YYYY | age N OCCUPATION' in one cell.
  2. big summary table -- one wide Name/Age/Director Since/Independent/
     Committees table; classical proxy layout.
  3. director-comp table -- catches directors missed by 1 + 2 and merges
     compensation totals into existing rows.

Validated 2026-05-03: Starbucks (12 dirs), Abbott (12 dirs), Worlds Inc
(3 via comp table). Coverage on the first 10-CIK batch was 3/9 (excluding
the 1 with no DEF14A). Remaining filers use one of several other layouts
that future iterations should add (bio-paragraph regex, table-of-contents-
linked director sections).

Usage:
    py scripts/etl/load_def14a_directors.py --cik 829224         # single
    py scripts/etl/load_def14a_directors.py --limit 5 --dry-run
    py scripts/etl/load_def14a_directors.py --limit 100 --commit
    py scripts/etl/load_def14a_directors.py --all --commit       # ~7800 filers, ~3 hr
    py scripts/etl/load_def14a_directors.py --retry-failed       # retry parse_failed CIKs

Verification:
    SELECT COUNT(*) FROM employer_directors;
    SELECT COUNT(*) FROM director_interlocks;  -- shared directors
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection

_log = logging.getLogger("etl.def14a")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "Labor Data Terminal jakewartel@gmail.com",
)
RATE_LIMIT_S = 0.2  # 5 req/sec, polite under SEC's 10/sec limit


class RateLimiter:
    def __init__(self, s: float):
        self.s = s
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.s:
            time.sleep(self.s - elapsed)
        self._last = time.monotonic()


_limiter = RateLimiter(RATE_LIMIT_S)


@dataclass
class Director:
    name: str
    age: int | None = None
    position: str | None = None
    director_since_year: int | None = None
    primary_occupation: str | None = None
    other_directorships: list[str] = field(default_factory=list)
    is_independent: bool | None = None
    committees: list[str] = field(default_factory=list)
    compensation_total: float | None = None
    parse_strategy: str = "unknown"


# --------------------------------------------------------------------------
# EDGAR client (mirrors load_sec_exhibit21.py)
# --------------------------------------------------------------------------


def fetch_latest_def14a_accession(cik: int) -> tuple[str, str] | None:
    """Return (accession_no_no_dashes, primary_doc_filename) or None."""
    cik10 = f"{cik:010d}"
    url = EDGAR_SUBMISSIONS_URL.format(cik10=cik10)
    _limiter.wait()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException as e:
        _log.warning("submissions fetch failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None
    recent = (body.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accession = recent.get("accessionNumber") or []
    primary_doc = recent.get("primaryDocument") or []
    for i, form in enumerate(forms):
        # DEF14A is the standard proxy. DEFM14A = merger proxy, ignore.
        # PRE14A is the preliminary version of DEF14A, also ignored.
        if form == "DEF 14A":
            acc = accession[i]
            return acc.replace("-", ""), primary_doc[i] if i < len(primary_doc) else None
    return None


def fetch_def14a_html(cik: int, accession_no_dashes: str, primary_doc: str | None) -> tuple[str, str] | None:
    """Return (html_text, source_url) or None."""
    if primary_doc:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_doc}"
        _limiter.wait()
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        except requests.RequestException as e:
            _log.warning("DEF14A primary doc fetch failed CIK %s: %s", cik, e)
            return None
        if resp.status_code == 200:
            return resp.text, url
    # Fallback: scan filing index for any .htm document
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/index.json"
    _limiter.wait()
    try:
        resp = requests.get(idx_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None
    items = (body.get("directory") or {}).get("item") or []
    # Prefer files whose name LOOKS like a DEF14A document (def14a/proxy in
    # the name). Excluding obvious exhibits (ex-* / exhibit*) avoids fetching
    # subsidiary lists by mistake. (Codex 2026-05-03: original logic excluded
    # `def14a` strings, the opposite of what we want.)
    candidates: list[str] = []
    for it in items:
        name = (it.get("name") or "")
        lower = name.lower()
        if not lower.endswith((".htm", ".html")):
            continue
        if re.search(r"(^|[\-_])(ex[\-_]?\d|exhibit[\-_]?\d)", lower):
            continue
        score = 0
        if "def14a" in lower or "def_14a" in lower or "def-14a" in lower:
            score += 10
        if "proxy" in lower:
            score += 5
        candidates.append((score, name))
    # Highest-scoring match first; otherwise any non-exhibit .htm.
    for _, name in sorted(candidates, key=lambda x: -x[0]):
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{name}"
        _limiter.wait()
        try:
            doc_resp = requests.get(doc_url, headers={"User-Agent": USER_AGENT}, timeout=20)
            if doc_resp.status_code == 200:
                return doc_resp.text, doc_url
        except requests.RequestException:
            continue
    return None


# --------------------------------------------------------------------------
# Director parsing strategies
# --------------------------------------------------------------------------


# Two orderings observed in real proxies:
#   (A) Starbucks: "NAME age N director since YYYY [title]"
#   (B) Abbott:    "NAME director since YYYY | age N OCCUPATION"
# Match the name once at the start, then locate age and director-since
# anywhere in the text via the helpers below.
_NAME_LEAD_RE = re.compile(
    r"^\s*(?P<name>[A-Z][^|]{2,80}?)(?=\s+(?:age|director\s+since)\b)",
    re.IGNORECASE,
)
_AGE_RE = re.compile(r"\bage[:\s]+(?P<age>\d{2,3})\b", re.IGNORECASE)
_SINCE_RE = re.compile(r"\bdirector\s+since[:\s]+(?P<year>\d{4})\b", re.IGNORECASE)
_BIG_HEADER_NAME_RE = re.compile(r"\bname\b", re.IGNORECASE)
_BIG_HEADER_AGE_RE = re.compile(r"\bage\b", re.IGNORECASE)
# Match the canonical "Director Since" plus the Air-Products-style
# "Year First Elected (or Appointed)" / "Year Elected" variants. Used both
# for table SCORING and for column-INDEX detection.
_BIG_HEADER_SINCE_RE = re.compile(
    r"\b(?:director\s+since|year\s+first\s+elected|first\s+elected|"
    r"year\s+elected|elected\s+or\s+appointed)\b",
    re.IGNORECASE,
)
_INDEPENDENT_RE = re.compile(r"\bindependent\b", re.IGNORECASE)
_COMMITTEE_RE = re.compile(r"\b(audit|compensation|nominating|governance|finance|risk|technology|safety|sustainability)\b", re.IGNORECASE)


_TRAILING_TITLE_RE = re.compile(
    r"\s+(Lead\s+Independent\s+Director|Independent\s+Director|"
    r"Lead\s+Director|Director|Chair(?:man|woman|person)?|"
    r"President|CEO|CFO|COO|Vice\s+Chair(?:man|woman|person)?|"
    r"Founder|Co-Founder|Retired|Senior|Vice|Chief|Executive)\s.*$",
    re.IGNORECASE,
)
_NAME_LEAD_TITLE_BOUNDARY = re.compile(
    r"\s+(Retired|Senior|Vice|Chief|Executive|President|CEO|CFO|COO|"
    r"Chair(?:man|woman|person)?|Lead|Independent|Founder|Co-Founder|"
    r"Skills\b|of\s+the\s+Board)\b",
    re.IGNORECASE,
)


def _is_valid_director_name(s: str) -> bool:
    """A real director name has 2+ alphabetic words, no embedded keywords
    like 'Age:'/'Chairman'/'Director', and no trailing colon. Rejects the
    AAR-pattern false positives where the table layout puts 'Age: 64' and
    'Chairman' into cells that the parser mistakes for names.
    """
    if not s or len(s) < 4 or len(s) > 60:
        return False
    if ":" in s:
        return False
    # Reject when it's all single-word title fragments
    keywords = {"age", "since", "director", "chairman", "chief", "officer",
                "president", "vice", "executive", "board", "committee",
                "independent", "lead", "principal", "founder", "skills",
                "experience", "since", "qualifications", "tenure"}
    # Reject section-heading false positives that the profile-block
    # preceding-heading fallback can pick up (AAR/AEP cases like
    # "Information about our directors", "Proposal 1 Election of Directors",
    # "Professional Highlights", "Class II Directors").
    section_words = {"information", "proposal", "highlights", "election",
                     "about", "following", "below", "page", "section",
                     "chapter", "table", "continued", "item", "professional",
                     "class", "nominees", "summary", "background", "biographies",
                     "biography", "compensation", "overview", "introduction",
                     "election", "elections", "matter", "matters"}
    words = s.split()
    if len(words) < 2:
        return False
    lower_words = [w.lower().rstrip(".,") for w in words]
    if any(lw in section_words for lw in lower_words):
        return False
    # If MORE THAN HALF the words are keywords, reject
    keyword_hits = sum(1 for lw in lower_words if lw in keywords)
    if keyword_hits >= max(1, len(words) // 2):
        return False
    # Reject names ending in stop-word grammar fragments. Real names don't
    # end in "of"/"and"/"the"/"our"/"to" — those are mid-sentence captures.
    stop_endings = {"of", "and", "the", "our", "to", "for", "with",
                    "in", "on", "by", "as", "at"}
    if lower_words[-1] in stop_endings:
        return False
    # Must have at least one word that looks like a real name (capitalized,
    # 3+ chars, alphabetic) AND not a keyword
    for w in words:
        clean = w.rstrip(".,")
        if (clean and clean[0].isupper() and len(clean) >= 3
                and clean.replace("'", "").replace("-", "").isalpha()
                and clean.lower() not in keywords):
            return True
    return False


def _norm_director_name(s: str) -> str:
    """Strip honorifics, suffixes, weird whitespace, and trailing title
    fragments that leak in when a proxy's per-director cell is laid out as
    'NAME President LAS Advisory Services Age 69...' (CECO pattern) or
    'NAME LeadIndependentDirector Director Since YYYY...' (Abbott pattern).

    The strategy:
      1. Trim filler at the boundary words ("Retired"/"Senior"/"President"/
         "Chief"/etc.) — anything from that point on is title/affiliation.
      2. Iteratively strip trailing title fragments (Director / Chair / etc.).
      3. Standard honorific + suffix cleanup.
    """
    s = re.sub(r"\s+", " ", s).strip(" ,;.|")
    # Strip leading filler words that survive the bio_paragraph regex --
    # "Since"/"Former"/"During"/"Effective" are common preface words.
    leading_filler = re.compile(
        r"^(?:Since|Former|During|Effective|Currently|Previously|Recently)\s+",
        re.IGNORECASE,
    )
    while leading_filler.match(s):
        s = leading_filler.sub("", s, count=1).strip()
    # Strip trailing filler words ("Former"/"Retired"/"Current") that come
    # after a name like "Munish Nanda Former" (CECO pattern).
    trailing_status = re.compile(
        r"\s+(?:Former|Retired|Current)\s*$",
        re.IGNORECASE,
    )
    s = trailing_status.sub("", s).strip()
    # Cut at the first title boundary keyword. This prevents "Laurie A. Siegel
    # President LAS Advisory Services" from becoming the full name.
    m = _NAME_LEAD_TITLE_BOUNDARY.search(s)
    if m:
        s = s[:m.start()].strip(" ,;.")
    s = re.sub(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|Sir|Hon\.)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(Jr\.|Sr\.|II|III|IV|Ph\.D\.?|M\.D\.?)\.?$", "", s, flags=re.IGNORECASE)
    # Iterate -- a name might have BOTH "Director" and "Lead Independent" in
    # different orders; strip until stable.
    prev = None
    while prev != s:
        prev = s
        s = _TRAILING_TITLE_RE.sub("", s).strip(" ,;.")
    return s.strip()


def _row_cells(row) -> list[str]:
    return [td.get_text(" ", strip=True) for td in row.find_all(["th", "td"])]


def _strategy_per_director_minitable(soup) -> list[Director]:
    """Each director gets their own small table whose key cell contains the
    name plus 'age N' and 'director since YYYY' in either order. Two real-
    world shapes are caught:
      (A) Starbucks: "NAME age N director since YYYY [title]"
      (B) Abbott:    "NAME director since YYYY | age N OCCUPATION"
    Each table also typically has 'Independent' / 'Professional background'
    cells we mine for context.
    """
    out: list[Director] = []
    seen = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows or len(rows) > 10:
            continue
        # Concatenate ALL cells in the table to find the director's data --
        # Abbott-style hides the key text in a single nested cell while other
        # cells are empty, so first-row-only scanning misses it.
        full_text = " ".join(" ".join(_row_cells(r)) for r in rows)
        # Collapse non-breaking-space and multiple whitespace
        full_text = full_text.replace("\xa0", " ").replace("|", " ")
        full_text = re.sub(r"\s+", " ", full_text).strip()
        if not full_text:
            continue
        # Both age and director-since must be present for us to call this a
        # director profile (avoids false positives on random tables).
        m_age = _AGE_RE.search(full_text)
        m_since = _SINCE_RE.search(full_text)
        if not (m_age and m_since):
            continue
        m_name = _NAME_LEAD_RE.search(full_text)
        if not m_name:
            continue
        name = _norm_director_name(m_name.group("name"))
        # Skip section headers / boilerplate that just happen to mention 'age
        # 50 director since 2018' inside an explanatory paragraph.
        if not name or name.lower() in seen or not _is_valid_director_name(name):
            continue
        independent = bool(_INDEPENDENT_RE.search(full_text))
        committees = sorted({c.group(0).title() for c in _COMMITTEE_RE.finditer(full_text)})
        # Primary occupation: take the slice after director-since YYYY (most
        # proxies put the bio there). Fall back to slice after age N.
        tail_start = max(m_since.end(), m_age.end())
        primary_occupation = full_text[tail_start:tail_start + 400].strip(" ,;.|")[:400] or None
        out.append(Director(
            name=name, age=int(m_age.group("age")),
            director_since_year=int(m_since.group("year")),
            primary_occupation=primary_occupation,
            is_independent=independent or None,
            committees=committees,
            parse_strategy="per_director_minitable",
        ))
        seen.add(name.lower())
    return out


def _strategy_big_summary_table(soup) -> list[Director]:
    """Classic style: one wide table with columns Name | Age | Director Since
    | Independent | Committees. Score every table by header keyword presence;
    extract from the highest-scoring one with >=4 data rows.
    """
    best = None
    best_header_idx = 0
    best_score = 0
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        # Find the first non-empty row -- some proxies (Air Products,
        # CIK 2186) lead with a blank spacer row before the real header.
        header_idx = 0
        header_cells: list[str] = []
        for hi, row in enumerate(rows[:3]):  # cap at first 3 in case of preface
            cells = _row_cells(row)
            if any(c.strip() for c in cells):
                header_idx = hi
                header_cells = [c for c in cells if c.strip()]  # drop spacers
                break
        header_blob = " | ".join(header_cells).lower()
        score = 0
        if _BIG_HEADER_NAME_RE.search(header_blob): score += 1
        if _BIG_HEADER_AGE_RE.search(header_blob): score += 2
        if _BIG_HEADER_SINCE_RE.search(header_blob): score += 3
        if "independent" in header_blob: score += 2
        if "committee" in header_blob: score += 1
        # Avoid director-compensation table (handled elsewhere); detected by a
        # 'compensation' or 'fees earned' header word.
        if "compensation" in header_blob or "fees earned" in header_blob:
            continue
        if score >= 4 and score > best_score:
            best, best_header_idx, best_score = table, header_idx, score
    if not best:
        return []

    rows = best.find_all("tr")
    # Re-derive header at the offset we found during scoring (drop spacers)
    header_cells_raw = _row_cells(rows[best_header_idx])
    header_cells = [c.lower() for c in header_cells_raw if c.strip()]
    # Best-effort column index detection
    def find_idx(predicate) -> int | None:
        for i, h in enumerate(header_cells):
            if predicate(h):
                return i
        return None
    name_idx = find_idx(lambda h: "name" in h)
    age_idx = find_idx(lambda h: h.strip() == "age" or h.startswith("age "))
    # "Director Since" is the canonical label, but Air-Products-style proxies
    # use "Year First Elected or Appointed" and small filers sometimes use
    # "appointed" alone. Accept all of those as the start-year column.
    since_idx = find_idx(
        lambda h: "director since" in h
        or "year first elected" in h
        or "first elected" in h
        or "year elected" in h
        or "elected or appointed" in h
        or h.strip() == "appointed"
        or "since" in h
    )
    indep_idx = find_idx(lambda h: "independent" in h)
    cmte_idx = find_idx(lambda h: "committee" in h)
    if name_idx is None:
        return []

    out: list[Director] = []
    seen = set()
    for tr in rows[best_header_idx + 1:]:
        cells_raw = _row_cells(tr)
        cells = [c for c in cells_raw if c.strip()]  # drop empty spacer cells
        if not cells or name_idx >= len(cells):
            continue
        name = _norm_director_name(cells[name_idx])
        if not name or name.lower() in seen or len(name) < 3:
            continue
        # Reject names that look like bio sentences -- the Adams Diversified
        # Equity Fund proxy embeds full director bios in the name cell, which
        # produces garbage rows like "Kenneth J. Dale, 69, Chair of the
        # Board...". A real director name is short, has no comma followed by
        # an age, and doesn't include 'director' / 'committee' keywords.
        if len(name) > 50:
            continue
        if re.search(r",\s*\d{2,3}\b", name):
            continue
        if re.search(r"\b(director|committee|chair|board|nominee|class\s+[ivx]+)\b", name, re.IGNORECASE):
            continue
        age = None
        if age_idx is not None and age_idx < len(cells):
            m = re.search(r"\b(\d{2,3})\b", cells[age_idx])
            if m: age = int(m.group(1))
        since = None
        if since_idx is not None and since_idx < len(cells):
            m = re.search(r"(\d{4})", cells[since_idx])
            if m: since = int(m.group(1))
        indep = None
        if indep_idx is not None and indep_idx < len(cells):
            indep = "yes" in cells[indep_idx].lower() or "x" == cells[indep_idx].strip().lower()
        cmtes: list[str] = []
        if cmte_idx is not None and cmte_idx < len(cells):
            cmtes = sorted({c.group(0).title() for c in _COMMITTEE_RE.finditer(cells[cmte_idx])})
        out.append(Director(
            name=name, age=age, director_since_year=since,
            is_independent=indep, committees=cmtes,
            parse_strategy="big_summary_table",
        ))
        seen.add(name.lower())
    return out


_BIO_PARAGRAPH_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z][A-Za-z\.\-' ,]{2,60}?)\s*\(\s*[Aa]ge\s+(?P<age>\d{2,3})\s*\)",
)


def _strategy_bio_paragraph(soup) -> list[Director]:
    """Acme-United-style: directors listed in continuous bio paragraphs as
    'NAME (age N) BIO sentences. Director since YYYY...'. Common in smaller
    proxies that don't use per-director tables. Iterates the parenthesised
    age markers in the document text and extracts the name from the 60 chars
    immediately preceding each one.
    """
    out: list[Director] = []
    seen = set()
    text = soup.get_text(" ", strip=True).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    # Match the LAST plausible name in the captured text -- typically 2-4
    # capitalized name-like tokens immediately preceding "(age N)". This
    # rejects leading filler like "Relevant Skills Director Since" / page
    # headers / column titles that the lazy regex captures alongside the
    # actual name.
    rightmost_name_re = re.compile(
        r"((?:[A-Z][a-zA-Z'\.\-]+(?:,)?\s+){1,3}[A-Z][a-zA-Z'\.\-]+(?:,?\s+(?:Jr\.?|Sr\.?|II|III|IV))?)\s*$",
    )
    for m in _BIO_PARAGRAPH_RE.finditer(text):
        raw_name = m.group("name").rstrip(" ,;.")
        rm = rightmost_name_re.search(raw_name)
        candidate = rm.group(1) if rm else raw_name
        name = _norm_director_name(candidate)
        if not name or name.lower() in seen or not _is_valid_director_name(name):
            continue
        # Bio = 300 chars after the (age N) marker
        bio_start = m.end()
        bio = text[bio_start:bio_start + 400].strip(" ,;.")
        # Optional director-since year in the bio (loose pattern)
        since_year = None
        m_since = re.search(r"\b(?:director|board)\s+(?:since|of\s+the\s+Company\s+since)\s+(\d{4})\b", bio, re.IGNORECASE)
        if m_since:
            since_year = int(m_since.group(1))
        out.append(Director(
            name=name, age=int(m.group("age")),
            director_since_year=since_year,
            primary_occupation=bio[:400] or None,
            parse_strategy="bio_paragraph",
        ))
        seen.add(name.lower())
    return out


def _strategy_director_comp_table(soup) -> list[Director]:
    """Director-compensation table almost always lists every non-employee
    director by name (col 1) with total comp (last numeric col). Useful as
    a fallback when no biographical table exists, and as a comp augmenter.
    """
    out: list[Director] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 4:
            continue
        header_blob = " ".join(_row_cells(rows[0])).lower()
        if not (("director" in header_blob and "compensation" in header_blob)
                or ("name" in header_blob and ("total" in header_blob or "fees earned" in header_blob))):
            continue
        seen = set()
        for tr in rows[1:]:
            cells = _row_cells(tr)
            if not cells:
                continue
            name = _norm_director_name(cells[0])
            if not name or len(name) < 3 or name.lower() in seen:
                continue
            # Total = last cell that parses as a dollar amount
            total = None
            for cell in reversed(cells[1:]):
                m = re.search(r"\$?\s*([\d,]{3,})", cell)
                if m:
                    try:
                        total = float(m.group(1).replace(",", ""))
                        break
                    except ValueError:
                        pass
            if total is None:
                continue
            out.append(Director(
                name=name, compensation_total=total,
                parse_strategy="director_comp_table",
            ))
            seen.add(name.lower())
        if out:
            return out  # use the first matching table
    return out


_PROFILE_AGE_RE = re.compile(r"\bAge\s*[:\-]?\s*(\d{2,3})\b", re.IGNORECASE)
_PROFILE_SINCE_RE = re.compile(
    r"\bDirector\s+Since\s*[:\-]?\s*(?:[A-Z][a-z]+\s+)?(\d{4})\b", re.IGNORECASE
)
_PROFILE_INDEP_RE = re.compile(r"\bIndependent\s*[:\-]?\s*(Yes|No)\b", re.IGNORECASE)
_PROFILE_COMMITTEES_RE = re.compile(
    r"(?:[A-Z]{2,4}\s+)?Committees?\s*[:\-]?\s*(.{1,400}?)"
    r"(?=Professional|Other Public|Prior Public|Skills|Qualifications|"
    r"Experience|Independent\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_PROFILE_BULLET_RE = re.compile(r"[•·●\*]\s*([^•·●\*\n]{2,80})")
_PROFILE_TITLE_BOUNDARY = re.compile(
    r"\s+(?:Chair(?:man|woman|person)?|President|CEO|CFO|COO|Director|"
    r"Vice|Senior|Executive|Lead|Independent|Founder|Co-Founder|"
    r"Retired|Former|Other\s+Public|Prior\s+Public|"
    r"Age\s*[:\-]|Director\s+Since|Skills|Qualifications)\b",
    re.IGNORECASE,
)


def _strategy_profile_block(soup) -> list[Director]:
    """AAR / AEP / Avery-style: each director's data lives in a single
    block-level element (div / td / section) that contains both 'Age:' and
    'Director Since:' anchors plus committee bullets, with the director's
    name as the leading text. Independence often spelled 'Independent: Yes'.

    Two name-extraction approaches, tried in order:
      (A) The block's first 2-5 capitalised words preceding any title
          boundary keyword (Chair / President / CEO / etc.). Works for AEP.
      (B) When (A) yields garbage like 'Age: 64' or 'Information about',
          fall back to the immediately preceding heading or strong tag.
          Works for AAR.
    """
    out: list[Director] = []
    seen = set()
    for el in soup.find_all(["div", "td", "section", "article", "p"]):
        text = el.get_text(" ", strip=True)
        if len(text) < 50 or len(text) > 5000:
            continue
        if "age" not in text.lower() or "director since" not in text.lower():
            continue
        text = re.sub(r"\s+", " ", text).strip()
        age_m = _PROFILE_AGE_RE.search(text)
        since_m = _PROFILE_SINCE_RE.search(text)
        if not (age_m and since_m):
            continue
        # (A) leading-name extraction
        name = None
        m = _PROFILE_TITLE_BOUNDARY.search(text)
        if m and m.start() >= 4:
            cand = text[: m.start()].strip(" ,;:.|")
            if 4 <= len(cand) <= 60:
                words = cand.split()
                if 2 <= len(words) <= 5 and _is_valid_director_name(cand):
                    name = cand
        # (B) sibling-cell fallback for AAR-style markup where the profile
        # data is in one <td> and the name is in a sibling <td> of the same
        # <tr>. Try same-row siblings first (cheapest), then fall back to
        # walking preceding headings/strong tags.
        if not name:
            cand = _find_sibling_cell_name(el, text)
            if cand and _is_valid_director_name(cand):
                name = cand
        if not name:
            cand = _find_preceding_name(el)
            if cand and _is_valid_director_name(cand):
                name = cand
        if not name:
            continue
        norm = _norm_director_name(name)
        if not norm or norm.lower() in seen:
            continue
        # Independence
        indep_m = _PROFILE_INDEP_RE.search(text)
        indep = indep_m.group(1).strip().lower() == "yes" if indep_m else None
        # Committees
        cmtes: list[str] = []
        com_m = _PROFILE_COMMITTEES_RE.search(text)
        if com_m:
            for b in _PROFILE_BULLET_RE.findall(com_m.group(1)):
                b = re.sub(r"\(.*?\)", "", b).strip(" ,;.•·●*")
                if 2 <= len(b) <= 50 and b.lower() != "none":
                    cmtes.append(b)
            cmtes = sorted(set(cmtes))
        out.append(Director(
            name=norm,
            age=int(age_m.group(1)),
            director_since_year=int(since_m.group(1)),
            is_independent=indep,
            committees=cmtes,
            parse_strategy="profile_block",
        ))
        seen.add(norm.lower())
    return out


def _find_sibling_cell_name(el, profile_text: str) -> str | None:
    """For AAR-style proxies the profile data sits in one <td> and the
    director's name sits in a SIBLING <td> of the same <tr>. Walk the
    parent <tr> looking for a non-empty cell whose first 2-5 words are
    a valid name (and that doesn't itself contain the profile text).
    """
    tr = el.find_parent("tr") if hasattr(el, "find_parent") else None
    if not tr:
        return None
    for td in tr.find_all(["td", "th"]):
        if td is el:
            continue
        text = td.get_text(" ", strip=True)
        if not text:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        # Skip if this cell IS the profile cell (e.g. nested td)
        if "Age:" in text and "Director since" in text:
            continue
        # Try to extract a leading name like "John M. Holmes ..."
        m = _PROFILE_TITLE_BOUNDARY.search(text)
        if m and m.start() >= 4:
            cand = text[: m.start()].strip(" ,;:.|")
            if 4 <= len(cand) <= 60:
                words = cand.split()
                if 2 <= len(words) <= 5 and _is_valid_director_name(cand):
                    return cand
    return None


def _find_preceding_name(el) -> str | None:
    """Walk previous siblings (and one level up) looking for a heading-like
    element whose text reads like a director's name (2-4 words, capitalised,
    no embedded keywords). Used as fallback when the profile block's leading
    text doesn't contain the name (AAR pattern)."""
    cur = el
    for _ in range(4):  # up to 4 hops upward through parents
        sib = cur.previous_sibling
        for _ in range(15):  # up to 15 prior siblings at this level
            if sib is None:
                break
            if hasattr(sib, "get_text"):
                txt = sib.get_text(" ", strip=True)
                txt = re.sub(r"\s+", " ", txt).strip(" ,;:.")
                if 4 <= len(txt) <= 60 and _is_valid_director_name(txt):
                    return txt
            sib = getattr(sib, "previous_sibling", None) if sib else None
        if not getattr(cur, "parent", None):
            break
        cur = cur.parent
    return None


def _merge_directors(*lists: list[Director]) -> list[Director]:
    """Combine results from multiple strategies. First non-None field wins
    so the strategy order in `parse_directors` is the priority order."""
    merged: dict[str, Director] = {}
    for src in lists:
        for d in src:
            key = _norm_director_name(d.name).lower()
            if not key:
                continue
            if key not in merged:
                merged[key] = d
                continue
            cur = merged[key]
            for field_name in (
                "age", "position", "director_since_year", "primary_occupation",
                "is_independent", "compensation_total",
            ):
                if getattr(cur, field_name) is None:
                    setattr(cur, field_name, getattr(d, field_name))
            # Merge committees
            cur_set = set(cur.committees or [])
            cur_set.update(d.committees or [])
            cur.committees = sorted(cur_set)
            cur_set2 = set(cur.other_directorships or [])
            cur_set2.update(d.other_directorships or [])
            cur.other_directorships = sorted(cur_set2)
    return list(merged.values())


def parse_directors(html: str) -> list[Director]:
    """Extract director rows from a DEF14A HTML document.

    Runs three strategies and merges. The order matters: Strategy 1
    (per-director mini-table) gives the richest data when present; Strategy 2
    (big summary table) is the fallback for traditional proxies; Strategy 3
    (director-comp table) augments with compensation totals and catches
    directors missed by 1+2.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _log.warning("bs4 not installed; cannot parse DEF14A")
        return []
    soup = BeautifulSoup(html, "html.parser")
    s1 = _strategy_per_director_minitable(soup)
    s2 = _strategy_big_summary_table(soup) if not s1 or len(s1) < 4 else []
    s4 = _strategy_bio_paragraph(soup) if (not s1 or len(s1) < 4) and (not s2 or len(s2) < 4) else []
    # Profile-block strategy: each director gets a stand-alone div/td/section
    # with Age + Director Since anchors. Catches AAR/AEP/Avery-style proxies
    # the table-based strategies miss. Run only when earlier strategies
    # didn't produce a complete roster.
    s5 = _strategy_profile_block(soup) if (not s1 or len(s1) < 4) and (not s2 or len(s2) < 4) and (not s4 or len(s4) < 4) else []
    s3 = _strategy_director_comp_table(soup)
    return _merge_directors(s1, s2, s4, s5, s3)


# --------------------------------------------------------------------------
# DB writer
# --------------------------------------------------------------------------


def write_directors(conn, cik: int, filer_name: str, accession: str, source_url: str, directors: list[Director], commit: bool) -> int:
    if not directors:
        return 0

    name_norm_re = re.compile(r"[^a-z0-9\s]")

    def norm(name: str) -> str:
        n = name_norm_re.sub("", name.lower()).strip()
        return re.sub(r"\s+", " ", n)

    # Master ID lookup via SEC -> master bridge plus a name-trigram fallback.
    # The original cut tried to ILIKE the numeric CIK against canonical_name
    # which never matches (Codex 2026-05-03). Two-stage:
    #   1. Try `master_employer_source_ids` where source_system='sec' and the
    #      stored source_id matches the filer's CIK.
    #   2. Otherwise fall back to a name-trigram lookup on the SEC filer name
    #      passed in by process_filer.
    master_id = None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT master_id FROM master_employer_source_ids
            WHERE source_system IN ('sec', 'sec_companies')
              AND source_id::text = %s
            LIMIT 1
            """,
            (str(cik),),
        )
        row = cur.fetchone()
        if row:
            master_id = row[0]
        elif filer_name:
            cur.execute(
                """
                SELECT master_id FROM master_employers
                WHERE canonical_name %% %s
                ORDER BY similarity(canonical_name, %s) DESC
                LIMIT 1
                """,
                (filer_name, filer_name),
            )
            row = cur.fetchone()
            if row:
                master_id = row[0]

    rows = []

    for d in directors:
        rows.append((
            master_id, cik, accession, None,  # fiscal_year inferred later
            d.name, norm(d.name), d.age, d.position,
            d.director_since_year, d.primary_occupation,
            d.other_directorships or None, d.is_independent,
            d.committees or None, d.compensation_total,
            source_url, d.parse_strategy,
        ))

    sql = """
        INSERT INTO employer_directors (
            master_id, filing_cik, filing_accession_number, fiscal_year,
            director_name, name_norm, age, position,
            director_since_year, primary_occupation,
            other_directorships, is_independent,
            committees, compensation_total,
            source_url, parse_strategy
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s
        )
        ON CONFLICT (filing_accession_number, name_norm) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        written = cur.rowcount
    if commit:
        conn.commit()
    else:
        conn.rollback()
    return written


def record_progress(conn, cik: int, status: str, count: int, notes: str = "", commit: bool = True):
    """Upsert a row into load_def14a_progress. When `commit=False` (dry-run),
    rolls back instead so a probe doesn't poison the skip-tracker for the
    next real run. (Codex 2026-05-03)"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO load_def14a_progress (cik, status, directors_found, notes, last_attempted)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (cik) DO UPDATE SET
                status = EXCLUDED.status,
                directors_found = EXCLUDED.directors_found,
                notes = EXCLUDED.notes,
                last_attempted = EXCLUDED.last_attempted
            """,
            (cik, status, count, notes[:500]),
        )
    if commit:
        conn.commit()
    else:
        conn.rollback()


# --------------------------------------------------------------------------
# Per-filer pipeline
# --------------------------------------------------------------------------


def process_filer(conn, cik: int, name: str, commit: bool) -> dict:
    result = {"cik": cik, "name": name, "directors_found": 0, "directors_written": 0, "note": None}
    acc_pair = fetch_latest_def14a_accession(cik)
    if not acc_pair:
        result["note"] = "no DEF14A on file"
        record_progress(conn, cik, "def14a_not_found", 0, result["note"], commit=commit)
        return result

    accession, primary_doc = acc_pair
    fetched = fetch_def14a_html(cik, accession, primary_doc)
    if not fetched:
        result["note"] = "DEF14A document fetch failed"
        record_progress(conn, cik, "http_error", 0, result["note"], commit=commit)
        return result

    html, source_url = fetched
    directors = parse_directors(html)
    result["directors_found"] = len(directors)
    if not directors:
        result["note"] = "parser returned 0 rows -- proxy uses an unrecognized layout"
        record_progress(conn, cik, "parse_failed", 0, result["note"], commit=commit)
        return result

    result["directors_written"] = write_directors(conn, cik, name, accession, source_url, directors, commit=commit)
    record_progress(conn, cik, "ok", result["directors_written"], commit=commit)
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cik", type=int, help="Process a single CIK")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Re-process CIKs whose load_def14a_progress.status is not 'ok'")
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    if args.cik:
        cur.execute("SELECT cik, company_name FROM sec_companies WHERE cik = %s", (args.cik,))
        rows = cur.fetchall()
    elif args.retry_failed:
        cur.execute(
            """
            SELECT s.cik, s.company_name FROM sec_companies s
            JOIN load_def14a_progress p ON p.cik = s.cik
            WHERE p.status <> 'ok' AND s.ticker IS NOT NULL
            ORDER BY p.last_attempted ASC
            """
        )
        rows = cur.fetchall()
    else:
        limit_clause = "" if args.all else f"LIMIT {max(args.limit, 1)}"
        cur.execute(f"""
            SELECT cik, company_name FROM sec_companies
            WHERE ticker IS NOT NULL AND cik IS NOT NULL
            ORDER BY cik
            {limit_clause}
        """)
        rows = cur.fetchall()

    _log.info("processing %d filer(s)", len(rows))
    total_dirs = 0
    total_written = 0
    failures = 0
    for i, (cik, name) in enumerate(rows, 1):
        try:
            result = process_filer(conn, cik, name, commit=args.commit and not args.dry_run)
        except Exception as e:
            _log.warning("CIK %s exception: %s", cik, e)
            failures += 1
            try:
                conn.rollback()
            except Exception:
                pass
            continue
        total_dirs += result["directors_found"]
        total_written += result["directors_written"]
        _log.info("[%d/%d] CIK %s %s -> %d directors (%d written)%s",
                  i, len(rows), cik, name[:40],
                  result["directors_found"], result["directors_written"],
                  f" [{result['note']}]" if result.get("note") else "")

    conn.close()
    _log.info("done: %d filers, %d directors found, %d written, %d failures",
              len(rows), total_dirs, total_written, failures)


if __name__ == "__main__":
    main()
