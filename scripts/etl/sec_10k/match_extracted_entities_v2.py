"""Less-aggressive ("nonaggressive") fallback tier for the SEC 10-K
relationship matcher.

Background
----------
The full 10-K relationship matcher lives in
``scripts/etl/sec_10k/match_extracted_entities.py`` on the
``ship/2026-05-11-q16-19-rollup`` branch (not yet on master). Its
cascade today is:

    Tier A (exact):    normalize_name_aggressive(entity_text)
                       == master_employers.canonical_name
    Tier B (alias):    config/employer_aliases.json
    Tier C (trigram):  pg_trgm similarity >= 0.85 against canonical_name

The 5/18 corpus audit (Agent 6) measured a 35.8% recall (479 of 1,326
extracted entities matched, 80% precision). The largest miss bucket --
361 of 851 unmatched rows -- is ``real_entity_no_master_match`` cases
where a master row DOES exist but the aggressive normalizer over-strips
the entity_text while ``master_employers.canonical_name`` retains the
suffix/noise tokens. Concrete verified-recoverable cases:

    entity_text "Booking Holdings"            ~  canonical "booking holdings inc"
    entity_text "Marzetti Company"            ~  canonical "marzetti company"
    entity_text "Aerospace Industries Assoc"  ~  canonical "aerospace industries association"
    entity_text "M&T Bank"                    ~  canonical "m t bank corporation"

normalize_name_aggressive() strips "Holdings" / "Industries" / "Company"
/ "Corporation" (they live in LEGAL_SUFFIXES + NOISE_TOKENS) so the
tier-A equality always fails on those pairs; trigram-0.85 catches some
but not all, and the alias dictionary covers only ~120 hand-curated
entities.

This module
-----------
This file ships the less-aggressive fallback tier as a standalone
function ``_match_nonaggressive_exact`` that should slot BETWEEN
tier A (exact) and tier C (trigram) when the q16-19 branch merges.
Integration is a 3-line change in ``match_entity()``::

    norm_agg = normalize_name_aggressive(entity_text)
    # ... tier A: existing exact-match block ...

    # NEW Tier B-nonaggressive: try the less-aggressive variant
    from scripts.etl.sec_10k.match_extracted_entities_v2 import (
        _match_nonaggressive_exact,
    )
    hit = _match_nonaggressive_exact(entity_text, conn=None, cur=cur)
    if hit is not None:
        master_id, score, tier_name = hit
        # alias-collision guard still applies
        ...

    # ... tier C: trigram block ...

Why a separate file?
--------------------
The q16-19 branch isn't on master (Agent 7's collection-error finding
documented why). Shipping the tier-function + unit tests as a
standalone file on master means the q16-19 merge can wire it in with
no merge-conflict risk and we get +40-50 matches as soon as that
merge happens. Until then, the tests are self-contained and exercise
the new function directly.

Normalization design
--------------------
The less-aggressive form strips ONLY corporate legal suffixes
(Inc / LLC / Corp / Ltd / etc.) from both sides of the comparison.
It KEEPS content/noise tokens like Holdings / Industries / Services /
Group / Company / Holding / The / Of -- those are part of the entity
name and disambiguate similar orgs (e.g. ``Apple Holdings`` is a
different entity than ``Apple Inc``).

Symmetry: the same stripper is applied to both ``entity_text`` and
``master_employers.canonical_name`` so that

    entity_text          = "Booking Holdings"
    less_aggr(entity)    = "booking holdings"
    canonical_name       = "booking holdings inc"
    less_aggr(canonical) = "booking holdings"
    -> MATCH

24Q tag: 24Q-16 / 24Q-17 / 24Q-19 (Suppliers / Distribution / Customers)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Less-aggressive stripper
# ---------------------------------------------------------------------------
# Corporate legal-form suffixes only. The full ``LEGAL_SUFFIXES`` set in
# ``src/python/matching/name_normalization.py`` also includes content
# words like ``co``, ``company``, ``trust``, ``fund``, ``foundation``,
# ``cooperative``, ``coop`` -- we KEEP those because removing them
# can over-match ``Apple`` to ``Apple Company`` (a different entity).
#
# Order matters: sorted longest-first inside the regex alternation so
# "corporation" wins over "corp" and "limited" wins over "ltd". The
# misspellings are included so we catch real-world data like
# "Acme Coporation" (one P missing) just like the aggressive path does.
_CORPORATE_SUFFIXES = (
    "limitedliabilitycompany",
    "limitedliability",
    "incorporated",
    "corporations",
    "corporation",
    "corportation",  # common misspelling
    "coropration",   # common misspelling
    "coporation",    # common misspelling
    "incoporated",   # common misspelling
    "incorperated",  # common misspelling
    "limited",
    "gmbh",
    "pllc",
    "ltd",
    "llc",
    "llp",
    "plc",
    "inc",
    "corp",
    "pty",
    "pvt",
    "bv",
    "nv",
    "na",
    "ag",
    "sa",
    "gp",
    "lp",
    "pa",
    "pc",
    "np",
)

# Built once at import time so re-use is cheap.
_SUFFIX_PATTERN = re.compile(
    r"\b(?:" + "|".join(_CORPORATE_SUFFIXES) + r")\b",
    re.IGNORECASE,
)


def normalize_nonaggressive(name: str) -> str:
    """Return the less-aggressive normalized form of a name.

    Steps:
        1. lowercase + collapse internal whitespace
        2. replace ampersand / slash / plus with spaces
        3. strip non-word punctuation
        4. strip corporate legal suffixes (Inc / LLC / Corp / Ltd / ...)
        5. collapse repeated whitespace
        6. trim

    KEEPS content tokens like ``Holdings`` / ``Industries`` / ``Company``
    / ``Group`` / ``The`` / ``Of`` -- those are part of the entity
    name and need to remain in both the query and the master canonical
    for the equality match to succeed.

    Examples
    --------
    >>> normalize_nonaggressive("Booking Holdings")
    'booking holdings'
    >>> normalize_nonaggressive("Booking Holdings Inc")
    'booking holdings'
    >>> normalize_nonaggressive("M&T Bank")
    'm t bank'
    >>> normalize_nonaggressive("M&T Bank Corporation")
    'm t bank'
    >>> normalize_nonaggressive("Marzetti Company")
    'marzetti company'
    >>> normalize_nonaggressive("Aerospace Industries Association")
    'aerospace industries association'
    >>> normalize_nonaggressive("Item 4")
    'item 4'
    >>> normalize_nonaggressive("")
    ''
    """
    if not name:
        return ""
    # Step 1-3: base cleanup (mirrors _base_cleanup in name_normalization)
    s = name.lower().strip()
    s = re.sub(r"[&/+]", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    # Step 4: strip corporate suffixes (word-boundary anchored)
    s = _SUFFIX_PATTERN.sub("", s)
    # Step 5-6: re-collapse whitespace + trim
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Stop-list for obvious junk strings (mirrors _looks_like_company in the
# main matcher). Re-implemented here to keep the v2 file standalone --
# when the q16-19 branch merges, callers can rely on the main matcher's
# guard and skip this one.
# ---------------------------------------------------------------------------
def _looks_like_company(text: str) -> bool:
    """Reject obvious non-company strings before hitting the DB."""
    if not text:
        return False
    t = text.strip()
    if len(t) < 4:
        return False
    if t.isdigit():
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    return True


# ---------------------------------------------------------------------------
# Tier function: less-aggressive exact match
# ---------------------------------------------------------------------------
def _match_nonaggressive_exact(
    entity_text: str,
    conn=None,
    cur=None,
) -> Optional[Tuple[int, float, str]]:
    """Less-aggressive equality match against ``master_employers``.

    Compares the less-aggressive normalized form of ``entity_text``
    against the same less-aggressive form of ``master_employers.canonical_name``
    via a SQL regexp_replace expression. Wins over Tier A's aggressive
    strip when the entity name carries content words (Holdings /
    Industries / Company) that the aggressive normalizer wrongly removes.

    Args:
        entity_text: The raw entity name extracted from the 10-K (e.g.
            ``"Booking Holdings"``).
        conn: Open psycopg2 connection. Optional -- pass ``cur`` instead.
        cur: An open cursor (for testability with the FakeCursor pattern
            used in the existing test suite). Takes precedence over
            ``conn``.

    Returns:
        ``(master_id, 1.0, "nonaggressive_exact")`` if a unique master
        row matches the less-aggressive form. ``None`` if:
          - input fails the ``_looks_like_company`` guard
          - normalization collapses to an empty string
          - no master row matches

    Notes:
        - Confidence is 1.0 (same as Tier A exact) because this IS an
          equality match, just over a different normalization form.
        - If multiple master rows tie (rare for less-aggressive form),
          the lowest master_id wins (stable tie-break consistent with
          Tier A / Tier C in the main matcher).
        - The SQL expression is portable across the master_employers
          DDL revisions in this codebase. It does NOT require the
          ``canonical_name_aggressive`` column added on
          ``ship/2026-05-12-matching-quality-fixes`` -- this matcher
          operates on the lower-aggressivity ``canonical_name``
          which exists on master.
    """
    if not _looks_like_company(entity_text):
        return None
    nonagg_entity = normalize_nonaggressive(entity_text)
    if not nonagg_entity or len(nonagg_entity) < 4:
        return None

    # Open a cursor on `conn` only if the caller didn't supply one.
    own_cur = False
    if cur is None:
        if conn is None:
            # function-local: formatter strips top-level
            from db_config import get_connection
            conn = get_connection()
            own_cur = True
        cur = conn.cursor()
        own_cur = True

    try:
        # Build the SQL regex that mirrors `_SUFFIX_PATTERN` on the
        # canonical_name column. The Python `\b` boundary translates to
        # `\m` / `\M` in PG's POSIX-flavor regex (start / end of word).
        suffix_alt = "|".join(_CORPORATE_SUFFIXES)
        sql = f"""
            SELECT master_id, canonical_name
              FROM master_employers
             WHERE trim(regexp_replace(
                       regexp_replace(canonical_name,
                                      '\\m({suffix_alt})\\M', '', 'gi'),
                       '\\s+', ' ', 'g'
                   )) = %s
             ORDER BY master_id
             LIMIT 2
        """
        cur.execute(sql, (nonagg_entity,))
        rows = cur.fetchall() or []
        if not rows:
            return None
        # If two rows tied, we still take the lowest master_id but log
        # nothing -- ambiguity is rare for less-aggressive equality.
        row = rows[0]
        master_id = row[0] if isinstance(row, tuple) else row["master_id"]
        return (int(master_id), 1.0, "nonaggressive_exact")
    finally:
        if own_cur:
            try:
                cur.close()
            except Exception:
                pass


__all__ = [
    "normalize_nonaggressive",
    "_match_nonaggressive_exact",
    "_CORPORATE_SUFFIXES",
]
