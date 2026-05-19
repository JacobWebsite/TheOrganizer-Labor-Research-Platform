"""Extract supplier / customer / distribution entity mentions from parsed 10-K sections.

Step 4 of the SEC 10-K text-mining foundation (Q16 Suppliers / Q17 Distribution /
Q19 Customers; Week 4 of the 2026-05-04 launch roadmap). Steps 1-3 picked
candidate filers, downloaded the HTML, and split each filing into named
sections (`sec_10k_sections`). This script reads the rows of
`sec_10k_sections` whose `section` is one of `customers` / `suppliers` /
`distribution`, runs heuristic entity-mention extraction, and writes one
row per mention to a new `sec_10k_extracted_entities` table.

# 24Q-16: Suppliers
# 24Q-17: Distribution
# 24Q-19: Customers

Strategy
--------
The extractor is rule-based on purpose: it has to run cheaply on the entire
~4K-section corpus and produce something a human (or downstream master-id
matcher) can review. The patterns are tuned to the section we're scanning:

* `customers` -- look for "X accounted for N% of", "X represented N% of",
  "principal/major/key/largest customers include X, Y, Z", "customer
  concentration with X".
* `suppliers` -- "key/principal/major suppliers include X, Y, Z", "we
  source X from Y", "single source supplier ... X", "primary supplier
  X".
* `distribution` -- "distributed/sold through X", "distribution partners
  ... X", "third-party distributors such as X".

After the section-specific patterns, we do one extra sweep for **proper
noun phrases** (sequences of capitalized tokens, optionally with a
corporate suffix like Inc. / Corp. / LLC) inside a small list of
introducer phrases ("such as", "including", "include"). This is the same
sentence-pattern approach used in DEF14A director extraction; it catches
e.g. "such as Walmart Inc." or "including Amadeus, Sabre, Travelport".

Stop-list
~~~~~~~~~
A static stop-list filters out obvious false positives ("the Company",
"our subsidiaries", "Fortune 500", section labels like "Major Customers",
common-noun categories like "various retailers" or "government
agencies"). Stop-list is tuned conservatively -- we'd rather over-keep
in this pass and let downstream matching reject; but an obvious
common-noun false positive is worse than missing one real entity.

DB shape
~~~~~~~~
`sec_10k_extracted_entities`:

| column | notes |
|---|---|
| `id` | BIGSERIAL PK. |
| `accession_number` | TEXT (matches `sec_10k_sections.accession`). |
| `cik` | TEXT (we cast from BIGINT in the source). |
| `section_type` | One of `'customers'` / `'suppliers'` / `'distribution'`. |
| `entity_text` | The cleaned mention text. |
| `context` | ~120 chars of surrounding text (60 before, mention, 60 after, clipped). |
| `position_offset` | Byte offset in `sec_10k_sections.text`. |
| `created_at` | TIMESTAMPTZ. |

Idempotent: re-running over the same `(cik, accession)` deletes prior rows
for that filing (per section_type) before inserting fresh ones.

Usage
-----
::

    py scripts/etl/sec_10k/extract_relationship_entities.py --limit 50      # smoke test
    py scripts/etl/sec_10k/extract_relationship_entities.py --report-only   # no DB writes
    py scripts/etl/sec_10k/extract_relationship_entities.py                 # full corpus

The `--limit` smoke test is the default invocation expected during
development. A full-corpus run is the user's call (4K sections at sub-ms
each is fast, but the user is doing parallel Mergent loads so we don't
launch heavy DB writes here).

Verification
------------
::

    SELECT section_type, COUNT(*) FROM sec_10k_extracted_entities
     GROUP BY section_type;
    SELECT entity_text, COUNT(*) FROM sec_10k_extracted_entities
     GROUP BY entity_text ORDER BY 2 DESC LIMIT 30;
"""
from __future__ import annotations

import argparse
import logging
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from db_config import get_connection  # noqa: E402

_log = logging.getLogger("etl.sec_10k.extract_entities")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

DDL_ENTITIES = """
CREATE TABLE IF NOT EXISTS sec_10k_extracted_entities (
    id                BIGSERIAL PRIMARY KEY,
    accession_number  TEXT        NOT NULL,
    cik               TEXT        NOT NULL,
    section_type      TEXT        NOT NULL,
    entity_text       TEXT        NOT NULL,
    context           TEXT,
    position_offset   INT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_sec10ke_accession
    ON sec_10k_extracted_entities (accession_number);
CREATE INDEX IF NOT EXISTS ix_sec10ke_section
    ON sec_10k_extracted_entities (section_type);
CREATE INDEX IF NOT EXISTS ix_sec10ke_cik
    ON sec_10k_extracted_entities (cik);
"""


def ensure_tables(conn) -> None:
    """Create the entities table (and indexes) if missing."""
    prior = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_ENTITIES)
    finally:
        conn.autocommit = prior


# --------------------------------------------------------------------------
# Section types this extractor handles
# --------------------------------------------------------------------------

SECTION_CUSTOMERS = "customers"
SECTION_SUPPLIERS = "suppliers"
SECTION_DISTRIBUTION = "distribution"

EXTRACT_SECTION_TYPES = (
    SECTION_CUSTOMERS,
    SECTION_SUPPLIERS,
    SECTION_DISTRIBUTION,
)


# --------------------------------------------------------------------------
# Stop-list of common false positives
# --------------------------------------------------------------------------

# Lowercased exact-match bad mentions. Most of these are introducer
# fragments, generic categories, or self-references that the regex picks
# up because they're capitalized in 10-K prose.
_STOP_EXACT: frozenset[str] = frozenset(
    {
        # Self-references
        "the company", "our company", "our subsidiaries", "the corporation",
        "our products", "our customers", "our suppliers", "our distributors",
        "our business", "our segments", "our segment",
        "the issuer",
        # Section labels (parser sometimes leaves a heading line in the body)
        "customers", "suppliers", "distribution", "major customers",
        "principal customers", "key customers", "raw materials",
        "sources and availability", "supply chain", "distribution channels",
        "strategic partners", "joint ventures", "concentration of customers",
        "product distribution", "sales and marketing",
        # Generic categories (would-be FPs)
        "various retailers", "various distributors", "various customers",
        "various suppliers", "various government agencies",
        "government agencies", "government", "federal government",
        "state government", "state governments", "local governments",
        "third-party suppliers", "third party suppliers",
        "third-party distributors", "third party distributors",
        "third-party resellers", "third party resellers",
        "fortune 500", "fortune 1000", "fortune 100",
        "small businesses", "large enterprises",
        "general public", "consumers",
        # Country / region names (we want firms, not nations)
        "united states", "united kingdom", "european union", "north america",
        "south america", "asia pacific", "asia-pacific", "latin america",
        "middle east", "the americas",
        # Document fragments
        "annual report", "table of contents", "form 10-k", "item 1",
        "item 1a", "item 7", "part i",
        # 10-K boilerplate that the regex picks up at sentence boundaries
        # ("Item 1A, Risk Factors", "Part II, Item 8", "Form 10-K", etc.).
        # Added 2026-05-10 after 4 of top 10 mentions in first full-corpus
        # run were 10-K cross-references, not real entities.
        "item", "form", "part ii", "part iii", "part iv", "part v",
        "form 10-q", "form 8-k", "risk factors",
        # Tech-industry generic abbreviations (lowercase since _STOP_EXACT
        # compares against `low = entity_text.lower()`). These were 11-20
        # mentions each in first full-corpus run, all unmatched -- e.g.
        # "Our customers include OEMs / VARs / MSPs / ISPs".
        "oem", "oems", "msp", "msps", "isp", "isps", "var", "vars",
        "ems", "odm", "odms", "osat", "osats", "diy",
        "sis",  # systems integrators
        # Sentence-starters / pronouns that the regex captures because
        # they're capitalized at the start of a sentence (7+ mentions each).
        "sales", "net sales", "internet",
        "while", "while the company", "two", "fortune", "canadian",
        "company's",
        # Sentence-boundary bug: parsed-out section headings sometimes
        # adjoin the next paragraph's sentence ("Raw Materials\nThe
        # Company concentrates..." -> "Raw Materials The Company").
        # Real fix is in the regex, but adding the literal phrase here
        # is the cheap interim guard.
        "raw materials the company",
        # ------------------------------------------------------------------
        # Iter 2 (2026-05-11) -- second-pass survey of the post-iter-1 corpus
        # surfaced these still-slipping categories at 2+ mentions each:
        # ------------------------------------------------------------------
        # Geographic noise that trigram-matches to bogus city-/region-named
        # master_employers ("Los Angeles" had 2 spurious matches; same
        # pattern for "New York" and various continent/region fragments).
        "los angeles", "new york", "north american", "western europe",
        "latin america", "asia pacific", "new zealand",
        "china and hong kong",
        # Industry-category acronyms that show up in tech / consumer 10-Ks
        # as generic mentions ("Our customers include IDMs and OEMs...").
        # Unmatched but populating the link table with noise.
        "ai-powered", "dtc", "cpg", "cpas", "iot", "lng", "oled",
        "pcbs", "idms", "hiv",
        # Sentence-boundary captures where the regex spanned across a
        # period. "OEMs. No" snuck through iter 1 because bare "oems"
        # is filtered but the regex captured the trailing "No" as part
        # of the noun phrase.
        "oems. no",
        "national hardware show. our",
        "financial statements and supplementary data",
    }
)

# Single-word terms that are valid English words but not company names.
# We scan tokens with this list; any extracted phrase whose tokens are
# *all* in this set is dropped.
_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "company", "companies", "corporation", "corporations", "subsidiary",
        "subsidiaries", "issuer", "issuers", "entity", "entities",
        "customer", "customers", "supplier", "suppliers", "vendor", "vendors",
        "distributor", "distributors", "reseller", "resellers", "partner",
        "partners", "client", "clients", "provider", "providers",
        "manufacturer", "manufacturers", "retailer", "retailers", "wholesaler",
        "wholesalers", "agent", "agents", "broker", "brokers", "buyer",
        "buyers", "buyers", "operator", "operators", "agency", "agencies",
        "carrier", "carriers", "merchant", "merchants",
        "various", "certain", "many", "several", "few", "all", "some",
        "principal", "primary", "major", "minor", "key", "important",
        "leading", "largest", "single", "multiple", "main",
        "global", "national", "international", "domestic", "foreign",
        "public", "private", "government", "federal", "state", "local",
        "such", "including", "include", "includes", "namely",
        "north", "south", "east", "west", "northern", "southern",
        # Calendar
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        # Generic discussion / pronouns / determiners that get capitalized
        # at sentence start.
        "our", "we", "us", "their", "they", "the", "this", "that", "these",
        "those", "for", "in", "on", "of", "and", "or", "but", "to", "by",
        "with", "as", "from", "at", "into", "during",
        "management", "discussion", "analysis", "financial", "condition",
        "results", "operations", "year", "quarter", "fiscal",
        "exclusive", "non-exclusive", "exclusivity",
        "additionally", "however", "furthermore", "therefore",
        "approximately", "additional", "additionally",
    }
)


# Single-token words that are countries/regions/states. We strip these
# *as full mentions* (not via _STOP_TOKENS) since e.g. "Japan" passes
# the proper-noun-with-uppercase-token check.
_GEO_NAMES: frozenset[str] = frozenset(
    {
        "afghanistan", "albania", "algeria", "andorra", "angola", "argentina",
        "armenia", "australia", "austria", "azerbaijan",
        "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium",
        "belize", "benin", "bhutan", "bolivia", "bosnia", "botswana", "brazil",
        "brunei", "bulgaria", "burkina", "burundi",
        "cambodia", "cameroon", "canada", "chad", "chile", "china",
        "colombia", "comoros", "congo", "croatia", "cuba", "cyprus", "czech",
        "denmark", "djibouti", "dominica", "dominican",
        "ecuador", "egypt", "estonia", "eswatini", "ethiopia",
        "fiji", "finland", "france",
        "gabon", "gambia", "georgia", "germany", "ghana", "greece", "grenada",
        "guatemala", "guinea", "guyana",
        "haiti", "honduras", "hungary",
        "iceland", "india", "indonesia", "iran", "iraq", "ireland", "israel",
        "italy", "ivory",
        "jamaica", "japan", "jordan",
        "kazakhstan", "kenya", "kiribati", "korea", "kosovo", "kuwait",
        "kyrgyzstan",
        "laos", "latvia", "lebanon", "lesotho", "liberia", "libya",
        "liechtenstein", "lithuania", "luxembourg",
        "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
        "marshall", "mauritania", "mauritius", "mexico", "micronesia",
        "moldova", "monaco", "mongolia", "montenegro", "morocco",
        "mozambique", "myanmar",
        "namibia", "nauru", "nepal", "netherlands", "nicaragua", "niger",
        "nigeria", "norway",
        "oman",
        "pakistan", "palau", "palestine", "panama", "paraguay", "peru",
        "philippines", "poland", "portugal",
        "qatar",
        "romania", "russia", "rwanda",
        "samoa", "saudi", "senegal", "serbia", "seychelles", "sierra",
        "singapore", "slovakia", "slovenia", "somalia", "spain", "sudan",
        "suriname", "sweden", "switzerland", "syria",
        "taiwan", "tajikistan", "tanzania", "thailand", "tibet", "togo",
        "tonga", "trinidad", "tunisia", "turkey", "turkmenistan", "tuvalu",
        "uganda", "ukraine",
        "uruguay", "uzbekistan",
        "vanuatu", "venezuela", "vietnam",
        "yemen",
        "zambia", "zimbabwe",
        # Continents and US regions
        "africa", "asia", "europe", "oceania", "antarctica",
        "americas", "midwest", "northeast", "southeast", "southwest",
        "atlantic", "pacific", "mediterranean", "caribbean",
        # US states
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
        "connecticut", "delaware", "florida", "hawaii", "idaho", "illinois",
        "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
        "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
        "missouri", "montana", "nebraska", "nevada", "ohio", "oklahoma",
        "oregon", "pennsylvania", "rhode", "tennessee", "texas", "utah",
        "vermont", "virginia", "washington", "wisconsin", "wyoming",
        # Cities / metros that appear unattributed
        "manhattan", "brooklyn", "boston", "chicago", "houston",
        "philadelphia", "phoenix", "denver", "seattle", "atlanta",
        "dallas", "miami",
    }
)


# Corporate suffixes that always signal "this is a real company name".
# A phrase ending in one of these gets a strong inclusion bias.
_CORP_SUFFIX_RE = re.compile(
    r"\b(Inc|Inc\.|Corp|Corp\.|Corporation|Company|Co|Co\.|LLC|"
    r"L\.L\.C\.|Ltd|Ltd\.|Limited|PLC|P\.L\.C\.|N\.V\.|"
    r"AG|S\.A\.|S\.p\.A\.|Holdings|Group|Bancorp|Trust)\b"
)


# Token-level proper-noun phrase: 1-5 capitalized tokens, where each
# token starts with an uppercase letter. Allows internal apostrophes and
# hyphens; allows trailing comma/period stripping later.
_PROPER_NOUN_RE = re.compile(
    r"\b("
    r"(?:[A-Z][A-Za-z0-9&'\-]*\.?)"
    r"(?:\s+(?:&|and|of|the|de|du|von)\s+[A-Z][A-Za-z0-9&'\-]*\.?"
    r"|\s+[A-Z][A-Za-z0-9&'\-]*\.?){0,4}"
    r")\b"
)


# Introducer phrases that often precede company-name lists in 10-K prose.
# We greedy-scan after these markers for 1-5 proper-noun phrases.
_INTRODUCER_RE = re.compile(
    r"(?:"
    r"such\s+as|"
    r"including(?:,?\s+but\s+not\s+limited\s+to)?|"
    r"include(?:s)?|"
    r"namely|"
    r"like(?:\s+for\s+example)?|"
    r"e\.g\.,?|"
    r"customers?\s+include(?:s)?|"
    r"suppliers?\s+include(?:s)?|"
    r"distributors?\s+include(?:s)?|"
    r"partners?\s+include(?:s)?"
    r")",
    re.IGNORECASE,
)


# Section-type-specific phrasing patterns. Each yields the matched
# subject (an entity span) plus its match.start() offset. Patterns are
# designed to tolerate moderate drift in 10-K prose ("Walmart Inc.,
# represented approximately 16%" / "Walmart accounted for approximately
# 18% of net revenues").
_PCT_AMOUNT = r"(?:\d+(?:\.\d+)?\s*%|approximately\s+\d+(?:\.\d+)?\s*%|"
_PCT_AMOUNT += r"more\s+than\s+\d+(?:\.\d+)?\s*%|over\s+\d+(?:\.\d+)?\s*%)"


# "X accounted for N% / X represented N%". The leading entity is what we want.
_PCT_LEAD_RE = re.compile(
    r"(?P<entity>[A-Z][A-Za-z0-9&'\-\.\s,]{2,80}?)\s+"
    r"(?:accounted\s+for|represented|comprised|generated|"
    r"contributed|made\s+up)\s+"
    r"(?:approximately\s+)?\s*\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)

# "Net sales to / Sales to X were N%" -- entity AFTER "to".
_PCT_TRAIL_RE = re.compile(
    r"(?:net\s+sales\s+to|sales\s+to|revenues?\s+from|purchases?\s+from)\s+"
    r"(?P<entity>[A-Z][A-Za-z0-9&'\-\.\s,]{2,80}?)"
    r"(?:\s+(?:were|was|of|totaled|amounted)|,)",
    re.IGNORECASE,
)

# "primary supplier of X is Y" / "single source X" -- entity after "is".
_SINGLE_SOURCE_RE = re.compile(
    r"(?:primary|principal|main|sole|single)\s+source\s+(?:of\s+\S+\s+)?(?:is|are)\s+"
    r"(?P<entity>[A-Z][A-Za-z0-9&'\-\.\s,]{2,80}?)(?:\s|,|\.|$)"
)


# --------------------------------------------------------------------------
# Extracted entity record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedEntity:
    cik: int
    accession: str
    section_type: str
    entity_text: str
    context: str
    position_offset: int


# --------------------------------------------------------------------------
# Cleanup helpers
# --------------------------------------------------------------------------


def _clean_entity_text(raw: str) -> str:
    """Normalize a raw entity span: trim whitespace + leading/trailing punctuation."""
    s = raw.strip()
    # Strip surrounding quotes / parens.
    while s and s[0] in '"\'(“”':
        s = s[1:]
    while s and s[-1] in '"\'),.;:“”':
        s = s[:-1]
    # Collapse internal whitespace.
    s = re.sub(r"\s+", " ", s)
    # Strip an introductory connector ("and X" / "or X" / "but X").
    s = re.sub(r"^(?:and|or|but|the)\s+", "", s, flags=re.IGNORECASE)
    return s.strip()


# Bare corporate-suffix tokens that should never be standalone entities.
_BARE_SUFFIX_TOKENS: frozenset[str] = frozenset(
    {
        "inc", "inc.", "corp", "corp.", "corporation", "company", "co",
        "co.", "llc", "ltd", "ltd.", "limited", "plc", "holdings", "group",
        "trust", "bancorp",
    }
)


def _is_acceptable_entity(s: str) -> bool:
    """Filter out obvious false positives (stop-list, all-stopword phrases)."""
    if not s:
        return False
    if len(s) < 3:
        return False
    if len(s) > 80:
        return False
    low = s.lower().strip()
    if low in _STOP_EXACT:
        return False
    # Bare corp-suffix word ("Inc", "Corp") -- not a real entity.
    if low in _BARE_SUFFIX_TOKENS:
        return False
    # Must contain at least one alphabetic char.
    if not any(c.isalpha() for c in s):
        return False
    # Must start with an uppercase letter or digit followed by a letter
    # ("3M Company"). Otherwise it's prose noise.
    if not (s[0].isupper() or (len(s) > 1 and s[0].isdigit() and s[1].isalpha())):
        return False
    # All tokens stop-words -> reject.
    tokens = re.split(r"[\s\-]+", low)
    tokens = [t for t in tokens if t]
    if tokens and all(t in _STOP_TOKENS or len(t) < 2 for t in tokens):
        return False
    # If the *entire* mention is a single geo name, reject. We allow geo
    # names as the *first word* of a longer firm name (e.g. "Mexico
    # Telecommunications Corp." -- not stripped).
    if len(tokens) == 1 and tokens[0] in _GEO_NAMES:
        return False
    # Reject "Geo and Geo" / "Geo + filler" -- pure-geo phrases (no
    # corp anchor, all tokens are geos or stop-tokens).
    if all(t in _GEO_NAMES or t in _STOP_TOKENS for t in tokens):
        return False
    # Must have at least one token that is *not* a stop-token AND starts
    # with an uppercase letter (or a digit followed by upper, e.g. "3M")
    # in the original.
    orig_tokens = re.split(r"\s+", s)
    has_real_capital_token = False
    for ot in orig_tokens:
        ot_clean = ot.strip(".,'\"&")
        if not ot_clean:
            continue
        ot_low = ot_clean.lower()
        if ot_low in _STOP_TOKENS:
            continue
        if ot_low in _GEO_NAMES:
            continue
        if ot_low in _BARE_SUFFIX_TOKENS:
            continue
        if len(ot_clean) < 2:
            continue
        # Real-firm tokens: start with uppercase, OR digit + uppercase
        # ("3M Company"), OR all-uppercase acronym ("IBM").
        first = ot_clean[0]
        if first.isupper():
            has_real_capital_token = True
            break
        if first.isdigit() and any(c.isupper() for c in ot_clean):
            has_real_capital_token = True
            break
    return has_real_capital_token


def _context_around(text: str, start: int, end: int, span: int = 60) -> str:
    """Return ~`span` chars before and after, total ~120, ASCII-clean."""
    lo = max(0, start - span)
    hi = min(len(text), end + span)
    snippet = text[lo:hi]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    # Clip at 200 hard so a runaway span (e.g. spans across a paragraph
    # break with no whitespace because of HTML quirks) doesn't blow up.
    if len(snippet) > 240:
        snippet = snippet[:240] + "..."
    return snippet


# --------------------------------------------------------------------------
# Per-section extraction
# --------------------------------------------------------------------------


def _extract_from_introducers(text: str) -> list[tuple[str, int]]:
    """Find proper-noun phrases that follow an introducer ("such as X, Y, Z").

    Captures up to ~250 chars of follow-on prose after the introducer marker
    and grabs the proper-noun runs. Comma- or "and"-separated lists are
    picked up because the proper-noun pattern doesn't span them.
    """
    out: list[tuple[str, int]] = []
    for m in _INTRODUCER_RE.finditer(text):
        scan_start = m.end()
        # Stop at sentence boundary.
        scan_end = scan_start + 250
        # End at the first '.' that's followed by whitespace + uppercase
        # (sentence boundary heuristic). Avoid splitting on "Inc." etc.
        for i in range(scan_start, min(len(text), scan_end)):
            if text[i] == ".":
                if i + 2 < len(text) and text[i+1] == " " and text[i+2].isupper():
                    scan_end = i
                    break
        chunk = text[scan_start:scan_end]
        for pn in _PROPER_NOUN_RE.finditer(chunk):
            phrase = pn.group(1)
            offset = scan_start + pn.start(1)
            out.append((phrase, offset))
    return out


def _last_proper_noun_in(span: str, span_offset: int) -> tuple[str, int] | None:
    """Return the rightmost proper-noun phrase in `span` (with absolute offset).

    Used to tighten greedy regex captures: when a pattern like
    ``X accounted for N%`` captures everything from the previous sentence
    start to the trigger, we only want the last proper-noun-run before the
    trigger ("Walmart Inc.", not "Customers Our largest customer, Walmart
    Inc.").
    """
    last: tuple[str, int] | None = None
    for pn in _PROPER_NOUN_RE.finditer(span):
        last = (pn.group(1), span_offset + pn.start(1))
    return last


def _extract_pattern_matches(text: str) -> list[tuple[str, int]]:
    """Run the section-agnostic phrasing patterns (% accounted for, sales to, single source).

    Each match's `entity` group is run through ``_last_proper_noun_in`` to
    tighten greedy spans down to the actual subject ("Walmart Inc.").
    """
    out: list[tuple[str, int]] = []
    for m in _PCT_LEAD_RE.finditer(text):
        span = m.group("entity")
        offset = m.start("entity")
        tight = _last_proper_noun_in(span, offset)
        if tight:
            out.append(tight)
    for m in _PCT_TRAIL_RE.finditer(text):
        span = m.group("entity")
        offset = m.start("entity")
        tight = _last_proper_noun_in(span, offset)
        if tight:
            out.append(tight)
    for m in _SINGLE_SOURCE_RE.finditer(text):
        span = m.group("entity")
        offset = m.start("entity")
        tight = _last_proper_noun_in(span, offset)
        if tight:
            out.append(tight)
    return out


def _extract_corp_suffixed(text: str) -> list[tuple[str, int]]:
    """Catch phrases ending with a corp suffix anywhere in the text.

    "We sell to Walmart Inc. and target consumers" -> Walmart Inc.
    """
    out: list[tuple[str, int]] = []
    for m in _CORP_SUFFIX_RE.finditer(text):
        # Walk back from m.start() up to 60 chars to find the start of the
        # capitalized phrase.
        end = m.end()
        # Find the start of the proper noun run.
        scan_back = max(0, m.start() - 60)
        backwards_chunk = text[scan_back:end]
        # Match the latest proper-noun-or-corp-suffix phrase that ends at end.
        candidates = list(_PROPER_NOUN_RE.finditer(backwards_chunk))
        if candidates:
            last = candidates[-1]
            phrase = last.group(1)
            offset = scan_back + last.start(1)
            out.append((phrase, offset))
    return out


def extract_entities_from_section(
    cik: int,
    accession: str,
    section_type: str,
    section_text: str,
    *,
    max_entities: int = 100,
) -> list[ExtractedEntity]:
    """Extract entity mentions from one section's text.

    Strategy: union of three rule families:
      1. Introducer-phrase scans ("such as X, Y, Z").
      2. Section-agnostic pattern matches ("X accounted for N%").
      3. Corp-suffix anchor scans ("Walmart Inc.").

    Dedupe by normalized lowercased entity_text (keep the earliest
    position offset). Apply stop-list / shape filters. Cap output at
    `max_entities` per section -- a long Item 1 with 200 mentions of
    "Inc." dotted everywhere is more noise than signal.
    """
    if not section_text:
        return []

    raw_hits: list[tuple[str, int]] = []
    raw_hits.extend(_extract_from_introducers(section_text))
    raw_hits.extend(_extract_pattern_matches(section_text))
    raw_hits.extend(_extract_corp_suffixed(section_text))

    seen_keys: dict[str, int] = {}  # normalized text -> earliest offset
    cleaned: dict[str, tuple[str, int]] = {}  # norm -> (cleaned_text, offset)

    for phrase, offset in raw_hits:
        cleaned_text = _clean_entity_text(phrase)
        if not _is_acceptable_entity(cleaned_text):
            continue
        norm = cleaned_text.lower()
        if norm in seen_keys:
            # Keep earliest occurrence's offset; don't double-count.
            if offset < seen_keys[norm]:
                seen_keys[norm] = offset
                cleaned[norm] = (cleaned_text, offset)
            continue
        seen_keys[norm] = offset
        cleaned[norm] = (cleaned_text, offset)

    # Build result list sorted by offset; cap at max_entities.
    items = sorted(cleaned.values(), key=lambda x: x[1])[:max_entities]
    out: list[ExtractedEntity] = []
    for entity_text, offset in items:
        # Find the actual span of `entity_text` near the recorded offset
        # (the offset may not exactly align after cleaning -- recompute).
        end = offset + len(entity_text)
        ctx = _context_around(section_text, offset, end)
        out.append(
            ExtractedEntity(
                cik=cik,
                accession=accession,
                section_type=section_type,
                entity_text=entity_text,
                context=ctx,
                position_offset=offset,
            )
        )
    return out


# --------------------------------------------------------------------------
# DB I/O
# --------------------------------------------------------------------------


SELECT_SECTIONS_SQL = """
SELECT cik, accession, section, text
FROM sec_10k_sections
WHERE section IN %s
{cik_clause}
ORDER BY cik, accession
{limit_clause}
"""


DELETE_PRIOR_SQL = """
DELETE FROM sec_10k_extracted_entities
WHERE accession_number = %s AND section_type = %s
"""


INSERT_ENTITY_SQL = """
INSERT INTO sec_10k_extracted_entities
    (accession_number, cik, section_type, entity_text, context, position_offset)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def fetch_section_rows(
    conn,
    *,
    section_types: tuple[str, ...],
    cik_filter: int | None,
    limit: int | None,
    sample_seed: int | None,
) -> list[tuple[int, str, str, str]]:
    """Return rows from sec_10k_sections whose section_type matches.

    If `sample_seed` is set and `limit` is set, pick a deterministic
    random sample of size `limit` from the full eligible set instead of
    just the first `limit` rows. This is what the docstring spec calls
    for in the smoke run.
    """
    if sample_seed is not None and limit and limit > 0:
        # Pull more rows than we need (or all if cheap), then sample.
        # Eligible total is small (~1.4K), fetch all and sample.
        cik_clause = f"AND cik = {int(cik_filter)}" if cik_filter is not None else ""
        sql = SELECT_SECTIONS_SQL.format(
            cik_clause=cik_clause,
            limit_clause="",
        )
        with conn.cursor() as cur:
            cur.execute(sql, (section_types,))
            rows = cur.fetchall()
        rng = random.Random(sample_seed)
        rng.shuffle(rows)
        rows = rows[:limit]
        return [(int(r[0]), r[1], r[2], r[3] or "") for r in rows]

    cik_clause = f"AND cik = {int(cik_filter)}" if cik_filter is not None else ""
    limit_clause = f"LIMIT {int(limit)}" if limit and limit > 0 else ""
    sql = SELECT_SECTIONS_SQL.format(
        cik_clause=cik_clause,
        limit_clause=limit_clause,
    )
    with conn.cursor() as cur:
        cur.execute(sql, (section_types,))
        rows = cur.fetchall()
    return [(int(r[0]), r[1], r[2], r[3] or "") for r in rows]


def write_entities(conn, entities: list[ExtractedEntity], *, accession: str, section_type: str) -> int:
    """Idempotent write: delete prior rows for (accession, section_type), then bulk insert."""
    with conn.cursor() as cur:
        cur.execute(DELETE_PRIOR_SQL, (accession, section_type))
        for ent in entities:
            cur.execute(
                INSERT_ENTITY_SQL,
                (
                    ent.accession,
                    str(ent.cik),
                    ent.section_type,
                    ent.entity_text,
                    ent.context,
                    ent.position_offset,
                ),
            )
    conn.commit()
    return len(entities)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _categorize_fps(top_entities: Counter) -> list[tuple[str, list[str]]]:
    """Group likely-FP entities into named categories for the report.

    Buckets:
      * sentence-starter ("Since the Company", "Our")
      * acronym (all-caps 3-5 chars, no corp suffix; e.g. "OEMs", "SMBs")
      * geo-fragment ("Republic of China", "Nevada and New York")
      * heading-like (multi-word capitalized phrase ending without a corp
        suffix, where the leading token is a stop-token, e.g.
        "Repository of Customer-Specific Inspection Data")
      * mid-word-period ("S. Both" -- result of clipping "U.S. Both ...")

    This is purely diagnostic; it doesn't reject anything at extraction time.
    """
    sentence_starts: list[str] = []
    acronyms: list[str] = []
    geo_fragments: list[str] = []
    heading_like: list[str] = []
    mid_word_period: list[str] = []
    for ent, _ in top_entities.most_common():
        # Sentence-starter heuristic: starts with a stop-token like "Since",
        # "Our", "These", "Furthermore".
        first_token = ent.split(None, 1)[0].lower().rstrip(".,")
        if first_token in {
            "since", "our", "we", "these", "those", "this", "that", "their",
            "additionally", "furthermore", "however", "therefore", "for",
        }:
            sentence_starts.append(ent)
            continue
        # Geo fragment: contains a country/state name and a connector.
        tokens_low = re.split(r"[\s,]+", ent.lower())
        geo_count = sum(1 for t in tokens_low if t in _GEO_NAMES)
        if geo_count >= 1 and not _CORP_SUFFIX_RE.search(ent):
            geo_fragments.append(ent)
            continue
        # Mid-word period: starts with a single letter then "." (e.g. "S. Both").
        if re.match(r"^[A-Z]\.\s+\w", ent):
            mid_word_period.append(ent)
            continue
        # Acronym: all-caps tokens, 2-6 chars each, no corp suffix.
        if (
            not _CORP_SUFFIX_RE.search(ent)
            and re.match(r"^[A-Z]{2,6}s?$", ent.replace("-", "").replace(" ", ""))
        ):
            acronyms.append(ent)
            continue
        # Heading-like: 4+ tokens, no corp suffix, contains
        # "Customer"/"Distribution"/"Analysis"/"Operations"/etc.
        toks = ent.split()
        if len(toks) >= 4 and not _CORP_SUFFIX_RE.search(ent):
            joined = ent.lower()
            if any(
                kw in joined
                for kw in (
                    "customer", "operation", "analysis", "discussion",
                    "condition", "results", "repository", "first",
                )
            ):
                heading_like.append(ent)
                continue
    return [
        ("sentence-start FPs", sentence_starts),
        ("industry-acronym FPs", acronyms),
        ("geo-fragment FPs", geo_fragments),
        ("heading-remnant FPs", heading_like),
        ("mid-word-period FPs", mid_word_period),
    ]


def build_summary_report(
    rows_processed: int,
    by_section: Counter,
    top_entities: Counter,
    sample_contexts: dict[str, list[tuple[str, str]]],
    fp_observations: list[str],
) -> str:
    """Build the markdown report body that gets written to docs/scratch."""
    lines: list[str] = []
    lines.append("# SEC 10-K relationship-entity extraction smoke run")
    lines.append("")
    lines.append("Date: 2026-05-09")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Sections processed: {rows_processed}")
    lines.append(f"- Total entities extracted: {sum(by_section.values())}")
    for sec_type in EXTRACT_SECTION_TYPES:
        n = by_section.get(sec_type, 0)
        lines.append(f"  - {sec_type}: {n}")
    lines.append("")
    lines.append("## Top 30 entities by frequency")
    lines.append("")
    lines.append("| Entity | Count |")
    lines.append("|---|---|")
    for ent, n in top_entities.most_common(30):
        # Escape pipes in markdown.
        safe = ent.replace("|", "\\|")
        lines.append(f"| {safe} | {n} |")
    lines.append("")
    lines.append("## Sample contexts (5 per section)")
    lines.append("")
    for sec_type in EXTRACT_SECTION_TYPES:
        lines.append(f"### {sec_type}")
        lines.append("")
        for entity, ctx in sample_contexts.get(sec_type, []):
            safe_ent = entity.replace("|", "\\|")
            safe_ctx = ctx.replace("|", "\\|").replace("\n", " ")
            lines.append(f"- **{safe_ent}**: {safe_ctx}")
        lines.append("")
    lines.append("## Known false-positive patterns observed")
    lines.append("")
    fp_categories = _categorize_fps(top_entities)
    any_fps = False
    for category, items in fp_categories:
        if not items:
            continue
        any_fps = True
        lines.append(f"### {category}")
        for it in items[:8]:
            safe = it.replace("|", "\\|")
            lines.append(f"- `{safe}`")
        lines.append("")
    if fp_observations:
        lines.append("### Frequent low-quality entities (>= 3 occurrences, no corp suffix)")
        for obs in fp_observations:
            lines.append(f"- {obs}")
        lines.append("")
    if not any_fps and not fp_observations:
        lines.append("- (no obvious FP patterns detected in this sample)")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- The extractor is intentionally conservative on common-noun rejection "
        "(see `_STOP_EXACT` and `_STOP_TOKENS` in extract_relationship_entities.py)."
    )
    lines.append(
        "- A name like 'Walmart Inc.' wins on the corp-suffix pass; a name like "
        "'Amadeus' wins on the introducer-phrase pass; '%-accounted-for' wins "
        "the percent-language pass."
    )
    lines.append(
        "- Downstream master-id matching is expected to reject obvious "
        "common-noun misfires that slip through here."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cap on sections to process (0 = no cap). Default 50 = smoke test.",
    )
    ap.add_argument(
        "--cik",
        type=int,
        default=None,
        help="Restrict to a single CIK (debugging).",
    )
    ap.add_argument(
        "--section-type",
        choices=EXTRACT_SECTION_TYPES + ("all",),
        default="all",
        help="Restrict to one section_type, or 'all' (default).",
    )
    ap.add_argument(
        "--report-path",
        default=str(ROOT / "docs" / "scratch" / "sec_10k_extraction_2026_05_09.md"),
        help="Where to write the markdown summary (default docs/scratch).",
    )
    ap.add_argument(
        "--report-only",
        action="store_true",
        help="Run extraction + report but skip DB inserts.",
    )
    ap.add_argument(
        "--no-sample",
        action="store_true",
        help="Don't randomly sample within --limit; just take the first N.",
    )
    ap.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="Random seed for the smoke-run sample (default 42).",
    )
    args = ap.parse_args()

    section_types = (
        EXTRACT_SECTION_TYPES
        if args.section_type == "all"
        else (args.section_type,)
    )

    conn = get_connection()
    if not args.report_only:
        ensure_tables(conn)

    rows = fetch_section_rows(
        conn,
        section_types=section_types,
        cik_filter=args.cik,
        limit=args.limit if args.limit > 0 else None,
        sample_seed=None if args.no_sample else args.sample_seed,
    )
    _log.info("eligible sections fetched: %d", len(rows))

    by_section: Counter = Counter()
    top_entities: Counter = Counter()
    sample_contexts: dict[str, list[tuple[str, str]]] = {st: [] for st in EXTRACT_SECTION_TYPES}
    rows_processed = 0
    sections_with_no_entities = 0

    for cik, accession, section_type, section_text in rows:
        rows_processed += 1
        ents = extract_entities_from_section(
            cik=cik,
            accession=accession,
            section_type=section_type,
            section_text=section_text,
        )
        if not ents:
            sections_with_no_entities += 1
        for e in ents:
            by_section[section_type] += 1
            top_entities[e.entity_text] += 1
            if len(sample_contexts.get(section_type, [])) < 5:
                sample_contexts[section_type].append((e.entity_text, e.context))

        if not args.report_only:
            # Always call write_entities (even on empty list) so the DELETE in
            # write_entities clears stale rows from a prior run that produced
            # entities for this (accession, section_type) but the current run
            # produces zero. Otherwise re-runs leak ghost rows.
            try:
                write_entities(
                    conn,
                    ents,
                    accession=accession,
                    section_type=section_type,
                )
            except Exception as e:  # noqa: BLE001
                _log.warning(
                    "DB write failed for cik=%s accession=%s section=%s: %s",
                    cik, accession, section_type, e,
                )
                conn.rollback()

        if rows_processed <= 5 or rows_processed % 25 == 0:
            _log.info(
                "[%d/%d] cik=%s section=%s entities=%d",
                rows_processed,
                len(rows),
                cik,
                section_type,
                len(ents),
            )

    # Heuristic FP observation: any entity appearing >= 5 times whose
    # cleaned form looks generic (no corp suffix, no proper noun beyond a
    # single common-ish capitalized word). We list these in the report
    # so the user can extend the stop-list later.
    fp_observations: list[str] = []
    for ent, n in top_entities.most_common(50):
        if n < 3:
            break
        if not _CORP_SUFFIX_RE.search(ent):
            tokens = re.split(r"\s+", ent)
            if len(tokens) <= 2 and not any(c.isdigit() for c in ent):
                fp_observations.append(
                    f"`{ent}` appears {n}x without a corp suffix -- likely a "
                    f"section-name remnant or generic category; consider adding "
                    f"to `_STOP_EXACT` if it's not a real firm."
                )
        if len(fp_observations) >= 8:
            break

    # Write summary report.
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    body = build_summary_report(
        rows_processed=rows_processed,
        by_section=by_section,
        top_entities=top_entities,
        sample_contexts=sample_contexts,
        fp_observations=fp_observations,
    )
    report_path.write_text(body, encoding="utf-8")
    _log.info("wrote summary to %s", report_path)

    _log.info(
        "done: %d sections processed; %d empty-result sections; %d total entities; "
        "%d distinct entity_text values",
        rows_processed,
        sections_with_no_entities,
        sum(by_section.values()),
        len(top_entities),
    )
    for st in EXTRACT_SECTION_TYPES:
        _log.info("  %s: %d entities", st, by_section.get(st, 0))

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
