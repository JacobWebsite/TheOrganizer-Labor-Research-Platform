"""Tests for scripts/etl/sec_10k/match_extracted_entities.py

Mix of unit tests (mocked DB cursor for pure logic + cascade behavior)
and an integration test that exercises the real DB if available.

Run:
  py -m pytest tests/etl/sec_10k/test_match_extracted_entities.py -x -q
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# Import the script as a module (it lives in scripts/etl/sec_10k/)
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "etl" / "sec_10k" / "match_extracted_entities.py"
)
spec = importlib.util.spec_from_file_location("match_extracted_entities", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ----------------------------------------------------------------------------
# FakeCursor: a light-weight psycopg2 cursor stand-in driven by a script of
# (sql_keyword, rows) tuples. Just enough to exercise match_entity()'s cascade
# without touching a real DB.
# ----------------------------------------------------------------------------

class FakeCursor:
    """Stand-in for a psycopg2 cursor.

    Construction takes a `responses` list -- a sequence of return values
    keyed by the order of execute() calls. Each response is either:
      - a list of rows (returned by fetchall / fetchone)
      - None (no result; e.g. set_limit())

    This lets a test specify exact cascade behavior:
      [None,   # set_limit() OR alias-canonical lookup miss
       [],     # exact lookup miss
       None,   # set_limit() before trigram
       [(1234, 'apple', 0.92)]]  # trigram hit
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self._last = None
        self.description = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        if not self._responses:
            self._last = []
        else:
            self._last = self._responses.pop(0)
        if isinstance(self._last, list):
            # Synthesize a description (column names) for dict-style consumers.
            # Our match_entity() consumes by tuple-index, but the production
            # code path via fetchall checks isinstance(row, tuple), which is
            # always True here, so no description object is needed.
            self.description = None
            self.rowcount = len(self._last)
        else:
            self.description = None
            self.rowcount = 0
        return self

    def fetchone(self):
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return None

    def fetchall(self):
        if isinstance(self._last, list):
            return list(self._last)
        return []


# ----------------------------------------------------------------------------
# 1. EXACT MATCH -> confidence 1.0, method 'exact'
# ----------------------------------------------------------------------------

def test_exact_match_returns_confidence_1():
    # Cascade for input "Apple Inc.":
    #   tier B alias: no alias hit (skipped, no DB call)
    #   tier A exact: returns (master_id=1234, canonical='apple')
    cur = FakeCursor([
        [(1234, "apple")],   # exact hit
    ])
    mid, conf, method = mod.match_entity(cur, "Apple Inc.", aliases=[])
    assert method == "exact"
    assert conf == 1.0
    assert mid == 1234


# ----------------------------------------------------------------------------
# 2. TRIGRAM MATCH (>= 0.85) -> method 'trigram', confidence in [0.85, 1.0]
# ----------------------------------------------------------------------------

def test_trigram_match_in_band():
    cur = FakeCursor([
        [],                             # exact miss
        None,                           # set_limit()
        [(5678, "tesla motors", 0.91)], # trigram top hit
    ])
    mid, conf, method = mod.match_entity(cur, "Tesla Motors Inc.", aliases=[])
    assert method == "trigram"
    assert 0.85 <= conf <= 1.0
    assert mid == 5678


# ----------------------------------------------------------------------------
# 3. ALIAS-COLLISION GUARD: Cleveland Clinic must NOT match Cleveland-Cliffs
# ----------------------------------------------------------------------------

def test_alias_collision_blocks_cleveland_cliffs():
    """The alias dict says queries containing 'cleveland clinic' must
    exclude 'cleveland-cliffs'. The matcher should refuse the cliffs
    candidate even if it's the strongest trigram hit, falling through
    to unmatched.
    """
    aliases = [{
        "canonical_name": "Cleveland Clinic Foundation",
        "aliases": ["cleveland clinic"],
        "exclude_terms": ["cleveland-cliffs", "cleveland cliffs"],
    }]
    cur = FakeCursor([
        # tier B alias canonical lookup: NO direct row for the canonical
        # (so we can isolate the guard behavior in tier C)
        [],
        # tier A exact: also no row
        [],
        # tier C set_limit
        None,
        # tier C trigram: returns Cleveland-Cliffs as top hit -- but the
        # guard should reject it. The ONLY candidate is the collision,
        # so the function should return ('unmatched', 0, None).
        [(9999, "cleveland-cliffs", 0.93)],
    ])
    mid, conf, method = mod.match_entity(cur, "Cleveland Clinic", aliases=aliases)
    assert method == "unmatched"
    assert mid is None
    assert conf == 0.0


# ----------------------------------------------------------------------------
# 4. NO MATCH -> child_master_id None, method 'unmatched'
# ----------------------------------------------------------------------------

def test_no_match_returns_unmatched():
    cur = FakeCursor([
        [],   # exact miss
        None, # set_limit
        [],   # trigram miss
    ])
    mid, conf, method = mod.match_entity(
        cur, "Some Obscure Company With No Equivalent", aliases=[]
    )
    assert mid is None
    assert conf == 0.0
    assert method == "unmatched"


# ----------------------------------------------------------------------------
# 5. ALIAS HIT routes to canonical (Cleveland Clinic Foundation)
# ----------------------------------------------------------------------------

def test_alias_hit_routes_to_canonical():
    """When a query matches an alias, we look up the canonical_name as
    the master_employer canonical_name (aggressive form) and return that
    master row with confidence 1.0 and method 'alias'.
    """
    aliases = [{
        "canonical_name": "Cleveland Clinic Foundation",
        "aliases": ["cleveland clinic", "ccf"],
        "exclude_terms": ["cleveland-cliffs"],
    }]
    cur = FakeCursor([
        # tier B alias canonical lookup: returns the legitimate clinic row
        [(7777, "cleveland clinic foundation")],
    ])
    mid, conf, method = mod.match_entity(
        cur, "Cleveland Clinic Foundation", aliases=aliases
    )
    assert method == "alias"
    assert conf == 1.0
    assert mid == 7777


# ----------------------------------------------------------------------------
# 6. _looks_like_company guard: rejects junk strings
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("junk", [
    "",
    "5",
    "12",
    "(see Note 5)",  # has letters but length OK; should pass guard, but
                     # likely return unmatched at trigram tier
])
def test_junk_strings_dont_crash(junk):
    """Short, numeric, or empty strings must not crash. The looks_like_company
    pre-filter rejects most of them; anything that passes goes to a
    trigram pass with empty results.
    """
    cur = FakeCursor([[], None, []])
    mid, conf, method = mod.match_entity(cur, junk, aliases=[])
    # All these should be unmatched -- the guard catches them or the
    # trigram returns empty.
    assert method == "unmatched"
    assert mid is None


# ----------------------------------------------------------------------------
# 7. section_to_relationship mapping
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("section,expected", [
    ("suppliers",          "supplier"),
    ("supply_chain",       "supplier"),
    ("customers",          "customer"),
    ("major_customers",    "customer"),
    ("distribution",       "distribution"),
    ("distributors",       "distribution"),
    ("item_1_business_suppliers", "supplier"),  # substring fallback
    ("",                   "supplier"),         # default
    (None,                 "supplier"),         # None safe
    ("unknown_section",    "supplier"),         # default
])
def test_section_to_relationship(section, expected):
    assert mod.section_to_relationship(section) == expected


# ----------------------------------------------------------------------------
# 8. ON CONFLICT idempotency (DB-backed integration)
# ----------------------------------------------------------------------------

def _has_input_table() -> bool:
    """Skip integration tests when Agent 1 hasn't created the input
    table yet (or the DB isn't reachable)."""
    try:
        from db_config import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.sec_10k_extracted_entities')")
        present = cur.fetchone()[0] is not None
        conn.close()
        return present
    except Exception:
        return False


_skip_no_input = pytest.mark.skipif(
    not _has_input_table(),
    reason="sec_10k_extracted_entities table not present (Agent 1 in parallel)",
)


@_skip_no_input
def test_on_conflict_idempotency():
    """Insert the same (parent, child, type, source_entity) twice; the
    second insert must be a no-op via ON CONFLICT DO NOTHING."""
    from db_config import get_connection
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Make sure the output table exists
        cur.execute(mod.DDL)

        # Pick a real master_id (any will do for the unique-constraint check)
        cur.execute("SELECT master_id FROM master_employers LIMIT 1")
        row = cur.fetchone()
        if row is None:
            pytest.skip("No master_employers rows")
        parent_id = int(row[0])

        # Manufacture a fake source_entity_id at the high end of the
        # BIGSERIAL to avoid colliding with real data. We need a real
        # row in sec_10k_extracted_entities for the FK to hold, so use
        # an actual id. If empty, skip.
        cur.execute("SELECT id FROM sec_10k_extracted_entities ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row is None:
            pytest.skip("sec_10k_extracted_entities has no rows yet")
        source_entity_id = int(row[0])

        # Clean any pre-existing test row first to make this rerunnable
        cur.execute(
            "DELETE FROM sec_10k_relationship_links "
            "WHERE source_entity_id=%s AND child_text=%s",
            (source_entity_id, "_TEST_IDEMPOTENCY_MARKER_"),
        )

        # First insert -> should succeed
        wrote_1 = mod.insert_link(
            cur, parent_id, None, "_TEST_IDEMPOTENCY_MARKER_", "supplier",
            source_entity_id, 0.0, "unmatched", None,
        )
        # Second insert -> ON CONFLICT short-circuits
        wrote_2 = mod.insert_link(
            cur, parent_id, None, "_TEST_IDEMPOTENCY_MARKER_", "supplier",
            source_entity_id, 0.0, "unmatched", None,
        )
        assert wrote_1 is True
        assert wrote_2 is False, "Second insert should hit ON CONFLICT DO NOTHING"
    finally:
        conn.rollback()  # don't leave test row behind
        conn.close()


# ----------------------------------------------------------------------------
# 9. alias_lookup substring matching
# ----------------------------------------------------------------------------

def test_alias_lookup_finds_substring():
    aliases = [{
        "canonical_name": "Walmart Inc",
        "aliases": ["walmart", "wal-mart"],
        "exclude_terms": [],
    }]
    hit = mod.alias_lookup("Walmart Stores Inc.", aliases)
    assert hit is not None
    canonical, exclude_terms = hit
    assert canonical == "Walmart Inc"
    assert exclude_terms == []


def test_alias_lookup_misses_unrelated():
    aliases = [{
        "canonical_name": "Walmart Inc",
        "aliases": ["walmart"],
        "exclude_terms": [],
    }]
    assert mod.alias_lookup("Apple Inc.", aliases) is None


# ----------------------------------------------------------------------------
# 10. alias_collision_guard logic
# ----------------------------------------------------------------------------

def test_alias_collision_guard_blocks_known_collision():
    assert mod.alias_collision_guard(
        "Cleveland Clinic", "cleveland-cliffs",
        ["cleveland-cliffs", "cleveland cliffs"],
    ) is True


def test_alias_collision_guard_allows_legitimate():
    assert mod.alias_collision_guard(
        "Cleveland Clinic", "cleveland clinic foundation",
        ["cleveland-cliffs"],
    ) is False


def test_alias_collision_guard_empty_excludes_pass_through():
    assert mod.alias_collision_guard(
        "anything", "anything else", []
    ) is False
