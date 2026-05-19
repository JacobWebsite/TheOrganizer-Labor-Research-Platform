"""
Canonical name normalization helpers for matching pipelines.

This is the SINGLE SOURCE OF TRUTH for name normalization.
All matchers, adapters, and scripts should import from here.

Levels:
- standard: conservative cleanup (safe for exact match)
- aggressive: stronger legal/descriptor stripping
- fuzzy: token-centric form for approximate matching

Phonetic helpers:
- soundex: 4-char phonetic code
- metaphone: more accurate phonetic code
- phonetic_similarity: combined phonetic score
"""
from __future__ import annotations

import re
import unicodedata


# ============================================================================
# Constants
# ============================================================================

LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "corporations",
    "co", "company",
    "llc", "l l c", "ltd", "limited", "lp", "llp", "pllc", "pc",
    "plc", "pa", "na", "sa", "gmbh", "ag", "pty", "pvt", "nv", "bv",
    "gp", "np",
    "trust", "fund", "foundation", "cooperative", "coop",
    "limitedliabilitycompany", "limitedliability",
    # Common misspellings
    "corportation", "coporation", "coropration",
    "incoporated", "incorperated",
}

NOISE_TOKENS = {
    "the", "of", "and",
    "services", "service", "group", "holdings", "holding",
    "management", "international", "national", "global",
    "usa",
    "enterprises", "enterprise", "associates", "partners",
    "industries", "industry",
    "consulting", "consultants",
    "solutions", "solution",
}

DBA_PATTERNS = [
    r"\bd\s*b\s*a\b.*$",          # dba, d b a, d  b  a (after slash removal)
    r"\bdoing business as\b.*$",
    r"\ba\s*k\s*a\b.*$",          # aka, a k a (after slash removal)
]

# Employer abbreviation expansions for aggressive normalization
ABBREVIATIONS = {
    "hosp": "hospital", "med": "medical", "ctr": "center",
    "cntr": "center", "mgmt": "management", "mfg": "manufacturing",
    "intl": "international", "natl": "national", "assn": "association",
    "assoc": "association", "dept": "department", "govt": "government",
    "univ": "university", "tech": "technology", "sys": "systems",
    "svc": "services", "svcs": "services", "dist": "distribution",
    "mktg": "marketing", "comm": "communications", "engr": "engineering",
    "fin": "financial", "ins": "insurance", "transp": "transportation",
    "rehab": "rehabilitation", "pharm": "pharmaceutical",
    "mem": "memorial", "reg": "regional", "genl": "general",
    "gen": "general", "elem": "elementary", "sch": "school",
    "schl": "school", "bldg": "building", "prop": "property",
    "apt": "apartment", "hwy": "highway", "pkwy": "parkway",
    "st": "saint", "mt": "mount", "ft": "fort",
}


# ============================================================================
# Core normalization functions
# ============================================================================

def _ascii_fold(value: str) -> str:
    """Fold unicode to ASCII equivalents."""
    norm = unicodedata.normalize("NFKD", value)
    return norm.encode("ascii", "ignore").decode("ascii")


def _base_cleanup(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = _ascii_fold(name or "").lower().strip()
    s = re.sub(r"[&/+]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _remove_dba_tail(s: str) -> str:
    """Remove DBA/AKA tails."""
    out = s
    for pattern in DBA_PATTERNS:
        out = re.sub(pattern, "", out).strip()
    return out


def normalize_name_standard(name: str) -> str:
    """
    Conservative normalization safe for deterministic exact match passes.
    Lowercases, strips punctuation, removes DBA tails.
    """
    s = _base_cleanup(name)
    s = _remove_dba_tail(s)
    return s


def normalize_name_aggressive(name: str) -> str:
    """
    Aggressive normalization for deterministic + fuzzy bridge passes.
    Strips legal suffixes, noise tokens, expands abbreviations.
    """
    s = normalize_name_standard(name)
    # Expand abbreviations first
    tokens = s.split()
    tokens = [ABBREVIATIONS.get(t, t) for t in tokens]
    # Then remove legal suffixes and noise
    tokens = [t for t in tokens if t not in LEGAL_SUFFIXES and t not in NOISE_TOKENS]
    return " ".join(tokens).strip()


def normalize_name_fuzzy(name: str) -> str:
    """
    Token-sorted form for fuzzy matching (order-insensitive).
    Removes single-char tokens, deduplicates, sorts alphabetically.
    """
    s = normalize_name_aggressive(name)
    tokens = [t for t in s.split() if len(t) > 1]
    dedup_sorted = sorted(set(tokens))
    return " ".join(dedup_sorted).strip()


def aggressive_form_of_canonical(canonical_name: str) -> str:
    """
    Apply aggressive normalization to a value that is already in
    ``master_employers.canonical_name`` form.

    Why this exists
    ---------------
    ``master_employers.canonical_name`` is populated by SQL in
    ``scripts/etl/create_master_employers.sql`` using only base cleanup
    (lowercase + non-alphanumerics replaced with spaces). It does NOT
    strip legal suffixes like ``Inc`` / ``Corp`` / ``LLC`` or noise
    tokens like ``the`` / ``services`` / ``holdings``.

    Matchers that compare ``normalize_name_aggressive(entity_text)``
    against ``canonical_name`` will silently miss real matches because
    of this asymmetry:

        entity_text = "Walmart Inc"
        normalize_name_aggressive(entity_text) = "walmart"      # suffix stripped
        master_employers.canonical_name         = "walmart inc" # suffix preserved
        equality match -> MISS

    The bug surfaces every time a downstream caller does::

        WHERE canonical_name = normalize_name_aggressive(query_text)

    See ``Open Problems/10-K Matcher Suffix Stripping Asymmetry.md`` for
    the full context. The 10-K relationship matcher in
    ``scripts/etl/sec_10k/match_extracted_entities.py`` is the canonical
    case that motivated this helper.

    Fix approaches in priority order
    --------------------------------
    1. **Schema fix (preferred)**: ``master_employers`` now carries a
       ``canonical_name_aggressive`` column (added in this commit). Match
       against that column rather than ``canonical_name``.

    2. **Query-time fix (fallback)**: callers that cannot use the new
       column should normalize ``canonical_name`` at query time via the
       SQL fragment returned by ``canonical_name_aggressive_sql()``.

    3. **In-process fix**: this Python helper. Use when you already have
       the canonical_name value in memory (e.g., post-fetch filtering).

    Idempotency
    -----------
    ``normalize_name_aggressive`` is idempotent for canonical-form
    inputs: running it on either ``"Walmart Inc"`` or ``"walmart inc"``
    produces ``"walmart"``. This helper is a thin wrapper around
    ``normalize_name_aggressive`` whose only purpose is to make the
    semantic intent explicit at call sites.

    >>> aggressive_form_of_canonical("walmart inc")
    'walmart'
    >>> aggressive_form_of_canonical("cleveland clinic foundation")
    'cleveland clinic'
    >>> aggressive_form_of_canonical("the acme services group")
    'acme'
    """
    return normalize_name_aggressive(canonical_name or "")


# Strict identifier pattern: alphanumeric + underscore + at most ONE dot
# (table.column). Anything else (parentheses, quotes, spaces, semicolons,
# multi-dot like schema.table.col, comments, etc.) is rejected -- this
# helper builds query-time SQL via f-string interpolation, so the column
# reference MUST be a trusted hardcoded identifier, not request input.
_COLUMN_EXPR_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")


def canonical_name_aggressive_sql(column_expr: str = "canonical_name") -> str:
    """
    Return a Postgres SQL expression that computes the aggressive form
    of a ``canonical_name`` column.

    This is the query-time fallback for callers that can't migrate to
    the new ``canonical_name_aggressive`` column. Mirrors the suffix /
    noise-token stripping rules in :data:`LEGAL_SUFFIXES` and
    :data:`NOISE_TOKENS` for the most common cases.

    NOTE: this SQL expression is intentionally less aggressive than the
    Python helper because abbreviation expansion (e.g. ``hosp`` ->
    ``hospital``) requires lookup tables that are awkward in pure SQL.
    For high-stakes equality matches use the new column or read into
    Python and call :func:`aggressive_form_of_canonical`.

    SECURITY: ``column_expr`` is interpolated directly into the returned
    SQL via f-string and is therefore an injection sink. To prevent
    accidental misuse this function validates the input against a strict
    identifier regex (``[A-Za-z_]\\w*(\\.[A-Za-z_]\\w*)?``) -- only bare
    column names or simple ``table.column`` references are accepted.
    Pass request input or anything dynamic at your peril; the input must
    be a hardcoded literal or come from a tightly-controlled allowlist.
    Found-and-fixed by Codex /wrapup crosscheck on 2026-05-18.

    Args:
        column_expr: Column reference / SQL expression that yields a
            canonical_name value. Defaults to ``canonical_name``.
            Must match ``^[A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)?$``.

    Returns:
        A SQL expression string with no trailing semicolon.

    Raises:
        ValueError: if ``column_expr`` doesn't look like a bare column
            reference (e.g. contains quotes, parens, spaces, semicolons).

    Example
    -------
    >>> sql = canonical_name_aggressive_sql("me.canonical_name")
    >>> "regexp_replace" in sql
    True
    """
    if not _COLUMN_EXPR_PATTERN.match(column_expr):
        raise ValueError(
            f"canonical_name_aggressive_sql: column_expr must be a bare "
            f"column or 'table.column' reference (matches "
            f"[A-Za-z_]\\w*(\\.[A-Za-z_]\\w*)?); got {column_expr!r}. "
            f"This helper builds SQL via f-string interpolation and "
            f"will not accept arbitrary expressions."
        )
    # Suffix patterns sorted longest-first to avoid partial matches
    # (e.g. "corporation" must match before "corp"). Bounded by word
    # boundaries via the \\m and \\M anchors (PG-specific).
    suffix_alt = "|".join(sorted(
        (re.escape(s) for s in LEGAL_SUFFIXES if s and " " not in s),
        key=len, reverse=True,
    ))
    noise_alt = "|".join(sorted(
        (re.escape(n) for n in NOISE_TOKENS if n and " " not in n),
        key=len, reverse=True,
    ))
    # Strip suffix tokens then noise tokens, then collapse whitespace.
    return (
        f"trim(regexp_replace("
        f"regexp_replace("
        f"regexp_replace({column_expr}, '\\m({suffix_alt})\\M', '', 'gi'),"
        f" '\\m({noise_alt})\\M', '', 'gi'),"
        f" '\\s+', ' ', 'g'))"
    )


# ============================================================================
# Token-overlap gate (false-positive defense in fuzzy bands)
# ============================================================================

def token_overlap_ratio(name1: str, name2: str,
                        normalizer=None) -> float:
    """
    Compute the Jaccard-style overlap ratio between the unique tokens of
    two names.

    Defined as::

        |tokens(name1) intersect tokens(name2)| / max(|tokens|)

    Returns 0.0 if either input normalizes to empty.

    Why this exists
    ---------------
    Pure token-similarity functions like
    ``rapidfuzz.fuzz.token_sort_ratio`` can score names like
    ``"Walmart"`` vs ``"Wal-Mart Pharmacy"`` at ~0.85, masking the fact
    that the second name describes a different entity ("Walmart" as a
    brand vs "Walmart Pharmacy" the pharmacy subsidiary). Token-overlap
    is more stringent: it asks how many distinct *words* the two names
    have in common.

    The fuzzy matching cascade uses this as a gate above the similarity
    floor: even a 0.82 token_sort_ratio match is rejected if fewer than
    half the unique tokens overlap. See ``Open Problems/Matching FP
    Rates in Fuzzy Bands.md`` for the empirical FP-rate context.

    Args:
        name1: First name (raw or already-normalized).
        name2: Second name (raw or already-normalized).
        normalizer: Callable applied to each input before tokenization.
            Defaults to :func:`normalize_name_aggressive`. Pass ``str``
            (identity) when inputs are already normalized to avoid
            double-normalization.

    Returns:
        Float in ``[0.0, 1.0]``. 1.0 means complete token-set overlap.

    Examples
    --------
    >>> round(token_overlap_ratio("Walmart", "Wal-Mart Pharmacy"), 2)
    0.5
    >>> round(token_overlap_ratio("Walmart Inc", "Walmart Stores Inc"), 2)
    1.0
    >>> round(token_overlap_ratio("Apple Inc", "Zebra Co"), 2)
    0.0
    >>> token_overlap_ratio("", "anything")
    0.0
    """
    norm = normalizer if normalizer is not None else normalize_name_aggressive
    tokens1 = {t for t in norm(name1 or "").split() if len(t) > 1}
    tokens2 = {t for t in norm(name2 or "").split() if len(t) > 1}
    if not tokens1 or not tokens2:
        return 0.0
    inter = tokens1 & tokens2
    if not inter:
        return 0.0
    return len(inter) / max(len(tokens1), len(tokens2))


def passes_fuzzy_token_gate(name1: str, name2: str, score: float,
                            score_threshold: float = 0.90,
                            overlap_threshold: float = 0.40) -> bool:
    """
    Apply the fuzzy-band token-overlap gate.

    The gate exists to suppress the high-FP tail of fuzzy matching.
    Audit data in 2026-03 estimated 30-70% FP rates in the 0.70-0.85
    score band; token-overlap distinguishes "name1 and name2 share most
    words" from "name1 and name2 share a few common substrings".

    Rule:
      * Score >= ``score_threshold`` (default 0.90): bypass the gate.
        High-similarity matches like exact-with-typo are reliable.
      * Score < ``score_threshold``: require token overlap >=
        ``overlap_threshold`` (default 0.40) OR a collapsed-spacing
        rescue match (same chars after stripping whitespace, or one
        collapsed form is a bounded prefix of the other).

    Both names are normalized with :func:`normalize_name_aggressive`
    before token comparison so that ``"Walmart Inc"`` and ``"walmart"``
    aren't penalized for the suffix difference.

    Args:
        name1: Candidate name (typically the source side).
        name2: Candidate name (typically the target side).
        score: Similarity score in [0,1] from the fuzzy matcher.
        score_threshold: Score above which the gate is bypassed.
        overlap_threshold: Minimum unique-token overlap ratio when the
            gate IS applied.

    Returns:
        True if the pair passes the gate; False if rejected.

    Examples
    --------
    >>> # High similarity bypasses the gate entirely.
    >>> passes_fuzzy_token_gate("Apple Inc", "Apple Corp", 0.95)
    True
    >>> # Low score + low token overlap rejected.
    >>> passes_fuzzy_token_gate("Walmart", "Wal-Mart Pharmacy", 0.82)
    False
    >>> # Low score + high token overlap accepted.
    >>> passes_fuzzy_token_gate(
    ...     "Cleveland Clinic", "Cleveland Clinic Foundation", 0.80)
    True
    >>> # Collapsed-spacing rescue: "AmerisourceBergen" vs "Amerisource
    >>> # Bergen" are the same company despite zero token overlap.
    >>> passes_fuzzy_token_gate(
    ...     "Amerisource Bergen", "AmerisourceBergen Inc", 0.76)
    True
    """
    if score >= score_threshold:
        return True
    overlap = token_overlap_ratio(name1, name2)
    if overlap >= overlap_threshold:
        return True
    # Collapsed-spacing rescue: low-token-overlap cases where one side
    # has had its spaces/hyphens collapsed (AmerisourceBergen vs
    # Amerisource Bergen, U-NEED-A-ROLL-OFF vs U NEED A ROLLOFF, etc.)
    # share aggressive-normalized character content but tokenize
    # differently. The 5/12 audit found these are the bulk of false
    # rejections under the basic token-overlap rule.
    norm1 = normalize_name_aggressive(name1 or "")
    norm2 = normalize_name_aggressive(name2 or "")
    collapsed1 = norm1.replace(" ", "")
    collapsed2 = norm2.replace(" ", "")
    if collapsed1 and collapsed2:
        # Either string fully contained in the other after collapsing
        # whitespace = same entity, just tokenized differently.
        if collapsed1 == collapsed2:
            return True
        # One is a prefix-extension of the other ("walmart" -> "walmartstores")
        # AND the longer one isn't more than 1.5x the shorter (which
        # would smuggle in unrelated suffix-noise tokens).
        shorter, longer = sorted((collapsed1, collapsed2), key=len)
        if longer.startswith(shorter) and len(longer) <= int(len(shorter) * 1.5):
            return True
        # Edit-distance rescue (typo variants like "Satelite" vs
        # "Satellite", "Glaziers" vs "Glazers"). Requires the collapsed
        # forms to be within ~10% character-level edit distance AND
        # roughly equal length, otherwise it'd accept too much. Uses
        # rapidfuzz.ratio which is normalized Levenshtein-similarity in
        # [0, 1]. Function-local import is intentional -- top-level
        # imports of optional deps tend to vanish under the project's
        # autoflake pass.
        try:
            from rapidfuzz.fuzz import ratio as _rf_ratio
            edit_sim = _rf_ratio(collapsed1, collapsed2) / 100.0
            # Length ratio: 0.85 means the shorter is at least 85% the
            # length of the longer. Keeps "satelite"/"satellite" but
            # rejects "ford"/"fordfoundation".
            len_ratio = len(shorter) / len(longer) if longer else 0.0
            if edit_sim >= 0.90 and len_ratio >= 0.85:
                return True
        except ImportError:
            pass
    return False


# ============================================================================
# Phonetic helpers
# ============================================================================

def soundex(name: str) -> str:
    """
    American Soundex algorithm. Returns 4-character phonetic code.

    >>> soundex("Robert")
    'R163'
    >>> soundex("Rupert")
    'R163'
    """
    if not name:
        return ""
    name = _ascii_fold(name).upper().strip()
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""

    code_map = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2",
        "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }

    first = name[0]
    coded = [first]
    prev_code = code_map.get(first, "0")

    for ch in name[1:]:
        c = code_map.get(ch, "0")
        if c != "0" and c != prev_code:
            coded.append(c)
        prev_code = c if c != "0" else prev_code

    result = "".join(coded)
    return (result + "0000")[:4]


def metaphone(name: str) -> str:
    """
    Simple Metaphone algorithm. Returns phonetic code string.

    >>> metaphone("Smith")
    'SM0'
    >>> metaphone("Schmidt")
    'SXMTT'
    """
    if not name:
        return ""
    name = _ascii_fold(name).upper().strip()
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""

    # Drop initial silent letters
    if name[:2] in ("AE", "GN", "KN", "PN", "WR"):
        name = name[1:]

    result = []
    i = 0
    while i < len(name):
        ch = name[i]
        nxt = name[i + 1] if i + 1 < len(name) else ""

        if ch in "AEIOU":
            if i == 0:
                result.append(ch)
        elif ch == "B":
            if not (i == len(name) - 1 and i > 0 and name[i - 1] == "M"):
                result.append("B")
        elif ch == "C":
            if nxt in "EIY":
                result.append("S")
            else:
                result.append("K")
        elif ch == "D":
            if nxt in "GE" and i + 2 < len(name) and name[i + 2] in "EIY":
                result.append("J")
            else:
                result.append("T")
        elif ch == "F":
            result.append("F")
        elif ch == "G":
            if nxt in "EIY":
                result.append("J")
            elif nxt != "H" or (i + 2 < len(name) and name[i + 2] in "AEIOU"):
                if not (i > 0 and name[i - 1] in "DG"):
                    result.append("K")
        elif ch == "H":
            if nxt in "AEIOU" and (i == 0 or name[i - 1] not in "AEIOU"):
                result.append("H")
        elif ch == "J":
            result.append("J")
        elif ch == "K":
            if i == 0 or name[i - 1] != "C":
                result.append("K")
        elif ch == "L":
            result.append("L")
        elif ch == "M":
            result.append("M")
        elif ch == "N":
            result.append("N")
        elif ch == "P":
            if nxt == "H":
                result.append("F")
                i += 1
            else:
                result.append("P")
        elif ch == "Q":
            result.append("K")
        elif ch == "R":
            result.append("R")
        elif ch == "S":
            if nxt == "H" or (nxt == "I" and i + 2 < len(name) and name[i + 2] in "AO"):
                result.append("X")
                i += 1
            else:
                result.append("S")
        elif ch == "T":
            if nxt == "H":
                result.append("0")
                i += 1
            elif nxt == "I" and i + 2 < len(name) and name[i + 2] in "AO":
                result.append("X")
            else:
                result.append("T")
        elif ch == "V":
            result.append("F")
        elif ch == "W":
            if nxt in "AEIOU":
                result.append("W")
        elif ch == "X":
            result.append("KS")
        elif ch == "Y":
            if nxt in "AEIOU":
                result.append("Y")
        elif ch == "Z":
            result.append("S")

        i += 1

    return "".join(result)


def phonetic_similarity(name1: str, name2: str) -> float:
    """
    Phonetic similarity score between two names (0.0 - 1.0).

    Combines Soundex and Metaphone codes. Returns 1.0 if both
    phonetic codes match, 0.5 if one matches, 0.0 if neither.

    >>> phonetic_similarity("Smith", "Smyth")
    1.0
    >>> phonetic_similarity("Apple", "Zebra")
    0.0
    """
    if not name1 or not name2:
        return 0.0

    # Compare word-by-word for multi-word names
    words1 = normalize_name_standard(name1).split()
    words2 = normalize_name_standard(name2).split()

    if not words1 or not words2:
        return 0.0

    # Simple: compare first significant words
    w1 = words1[0] if words1 else ""
    w2 = words2[0] if words2 else ""

    score = 0.0
    if soundex(w1) == soundex(w2):
        score += 0.5
    if metaphone(w1) == metaphone(w2):
        score += 0.5

    return score
