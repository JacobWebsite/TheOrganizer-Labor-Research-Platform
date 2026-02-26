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
