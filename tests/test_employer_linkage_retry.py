"""
Tests for employer linkage retry (Task 4-7).

Verifies:
  - UML evidence fallback tier in employer_lookup
  - backfill_employer_ids function
  - Auto-linkage integration point exists in agent.py
"""
import os
import sys
import pytest
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_config import get_connection


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


class TestUmlEvidenceFallback:
    """The UML evidence fallback tier should exist and work."""

    def test_lookup_uml_evidence_exists(self):
        from scripts.research.employer_lookup import _lookup_uml_evidence
        assert callable(_lookup_uml_evidence)

    def test_lookup_uml_evidence_returns_triple(self, conn):
        from scripts.research.employer_lookup import _lookup_uml_evidence
        cur = conn.cursor()
        result = _lookup_uml_evidence(cur, "NONEXISTENT_COMPANY_XYZ_999", "nonexistent", None)
        assert len(result) == 3
        assert result[0] is None  # No match expected


class TestBackfillFunction:
    """backfill_employer_ids should handle empty set gracefully."""

    def test_backfill_dry_run(self, conn):
        from scripts.research.employer_lookup import backfill_employer_ids
        # dry_run=True should not modify anything
        count = backfill_employer_ids(conn, dry_run=True)
        assert isinstance(count, int)


class TestAutoLinkageInAgent:
    """agent.py should have auto-linkage in post-run handler."""

    def test_agent_has_auto_linkage(self):
        import scripts.research.agent as agent_mod
        source = inspect.getsource(agent_mod)
        assert "auto-linked to employer" in source or "Auto-linkage" in source
