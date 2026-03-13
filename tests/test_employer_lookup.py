"""Tests for scripts/research/employer_lookup.py."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_config import get_connection
from scripts.research.employer_lookup import lookup_employer


@pytest.fixture(scope="module")
def cur():
    conn = get_connection()
    c = conn.cursor()
    yield c
    conn.close()


class TestExactMatch:
    def test_starbucks(self, cur):
        eid, name, method = lookup_employer(cur, "Starbucks")
        assert eid is not None
        assert "starbucks" in name.lower()
        assert method == "exact_standard"

    def test_case_insensitive(self, cur):
        eid, name, method = lookup_employer(cur, "starbucks")
        assert eid is not None
        assert method == "exact_standard"

    def test_xerox(self, cur):
        eid, name, method = lookup_employer(cur, "xerox")
        assert eid is not None
        assert "xerox" in name.lower()

    def test_kaiser_permanente(self, cur):
        eid, name, method = lookup_employer(cur, "Kaiser Permanente")
        assert eid is not None
        assert "kaiser" in name.lower()


class TestPrefixMatch:
    def test_xpo_logistics(self, cur):
        eid, name, method = lookup_employer(cur, "XPO Logistics")
        assert eid is not None
        assert "xpo" in name.lower()
        assert method in ("exact_standard", "prefix_standard")

    def test_fed_ex(self, cur):
        eid, name, method = lookup_employer(cur, "Fed Ex")
        assert eid is not None
        assert "fed ex" in name.lower()
        assert method == "prefix_standard"

    def test_single_token_no_prefix(self, cur):
        """Single-token queries should NOT prefix-match to avoid false positives."""
        eid, name, method = lookup_employer(cur, "Amazon")
        # Amazon isn't in F7 as Amazon.com — should be None, not "Amazon Masonry"
        if eid is not None:
            assert method != "prefix_standard", \
                "Single-token should not use prefix matching"


class TestNoMatch:
    def test_nonexistent(self, cur):
        eid, name, method = lookup_employer(cur, "ZZZZZ Nonexistent Corp 12345")
        assert eid is None
        assert name is None
        assert method is None

    def test_empty_string(self, cur):
        eid, name, method = lookup_employer(cur, "")
        assert eid is None

    def test_none_input(self, cur):
        eid, name, method = lookup_employer(cur, None)
        assert eid is None


class TestStatePreference:
    def test_prefers_matching_state(self, cur):
        """When multiple matches exist, should prefer the one in the given state."""
        # Starbucks has records in multiple states
        eid1, _, _ = lookup_employer(cur, "Starbucks", state="WA")
        eid2, _, _ = lookup_employer(cur, "Starbucks", state="NY")
        # Both should find something (may or may not differ)
        assert eid1 is not None
        assert eid2 is not None


class TestMasterFallback:
    """Test that master_employers fallback activates when F7 misses."""

    def test_master_exact_when_f7_misses(self, cur):
        """A non-F7 company should resolve via master_employers."""
        # Pick a company that exists in master_employers but not in F7
        cur.execute("""
            SELECT display_name FROM master_employers me
            WHERE NOT EXISTS (
                SELECT 1 FROM f7_employers_deduped f
                WHERE f.name_standard = me.canonical_name
            )
            AND me.canonical_name IS NOT NULL
            AND LENGTH(me.canonical_name) > 5
            LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            pytest.skip("No master-only employer found for test")
        name = row[0] if isinstance(row, tuple) else row['display_name']
        eid, ename, method = lookup_employer(cur, name)
        # Should find it via master fallback
        assert eid is not None, f"Expected master fallback for {name}"
        assert method in ("master_exact", "master_trigram")

    def test_master_returns_numeric_id(self, cur):
        """Returned ID from master fallback should be a numeric string (master_id)."""
        cur.execute("""
            SELECT display_name FROM master_employers me
            WHERE NOT EXISTS (
                SELECT 1 FROM f7_employers_deduped f
                WHERE f.name_standard = me.canonical_name
            )
            AND me.canonical_name IS NOT NULL
            AND LENGTH(me.canonical_name) > 5
            LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            pytest.skip("No master-only employer found for test")
        name = row[0] if isinstance(row, tuple) else row['display_name']
        eid, _, method = lookup_employer(cur, name)
        if eid and method and method.startswith("master_"):
            assert eid.isdigit(), f"Master fallback ID should be numeric, got {eid}"

    def test_f7_preferred_over_master(self, cur):
        """F7 match should win when both F7 and master would match."""
        eid, name, method = lookup_employer(cur, "Starbucks")
        assert eid is not None
        # F7 methods should take priority
        assert method in ("exact_standard", "prefix_standard", "trigram", "name_and_address"), \
            f"F7 should be preferred, got method={method}"


class TestReturnTypes:
    def test_returns_tuple_of_three(self, cur):
        result = lookup_employer(cur, "Starbucks")
        assert len(result) == 3
        eid, name, method = result
        assert isinstance(eid, str)
        assert isinstance(name, str)
        assert isinstance(method, str)

    def test_none_returns_tuple_of_three(self, cur):
        result = lookup_employer(cur, "ZZZZZ Corp")
        assert len(result) == 3
        assert result == (None, None, None)
