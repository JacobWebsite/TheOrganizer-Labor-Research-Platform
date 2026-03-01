"""
Tests for _resolve_contradictions() in scripts/research/agent.py (Phase R1).
"""

from unittest.mock import MagicMock, patch, call

import pytest

from scripts.research.agent import _resolve_contradictions


def _make_fact(fact_id, attr_name, attr_value):
    return {"id": fact_id, "attribute_name": attr_name, "attribute_value": attr_value}


class _FakeCursor:
    """Tracks UPDATE calls for verification."""

    def __init__(self, facts):
        self._facts = facts
        self.updates = []

    def execute(self, sql, params=None):
        if "UPDATE" in sql:
            self.updates.append(params)

    def fetchall(self):
        return self._facts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


class TestContradictionDetection:
    """Tests for _resolve_contradictions()."""

    @patch("scripts.research.agent._conn")
    def test_numeric_contradiction_detected(self, mock_conn):
        """Employee count values diverging by >2x should flag contradicts_fact_id."""
        facts = [
            _make_fact(1, "employee_count", "100"),
            _make_fact(2, "employee_count", "500"),
        ]
        # First call: read facts; second call: write updates
        read_cur = _FakeCursor(facts)
        write_cur = _FakeCursor([])
        read_conn = _FakeConn(read_cur)
        write_conn = _FakeConn(write_cur)
        mock_conn.side_effect = [read_conn, write_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 1
        assert len(write_cur.updates) == 1
        # The newer fact (id=2) should point to the older fact (id=1)
        contradicts_id, flagged_id = write_cur.updates[0]
        assert flagged_id == 2
        assert contradicts_id == 1

    @patch("scripts.research.agent._conn")
    def test_no_contradiction_similar_values(self, mock_conn):
        """Values within 2x threshold should NOT be flagged."""
        facts = [
            _make_fact(1, "employee_count", "100"),
            _make_fact(2, "employee_count", "150"),
        ]
        read_cur = _FakeCursor(facts)
        read_conn = _FakeConn(read_cur)
        mock_conn.side_effect = [read_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 0

    @patch("scripts.research.agent._conn")
    def test_string_contradiction_detected(self, mock_conn):
        """Different string values for same attribute should flag contradiction."""
        facts = [
            _make_fact(1, "company_type", "private"),
            _make_fact(2, "company_type", "public"),
        ]
        read_cur = _FakeCursor(facts)
        write_cur = _FakeCursor([])
        read_conn = _FakeConn(read_cur)
        write_conn = _FakeConn(write_cur)
        mock_conn.side_effect = [read_conn, write_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 1

    @patch("scripts.research.agent._conn")
    def test_contradiction_count_returned(self, mock_conn):
        """Function should return the correct count of flagged contradictions."""
        facts = [
            _make_fact(1, "employee_count", "100"),
            _make_fact(2, "employee_count", "500"),
            _make_fact(3, "revenue", "$1M"),
            _make_fact(4, "revenue", "$10M"),
        ]
        read_cur = _FakeCursor(facts)
        write_cur = _FakeCursor([])
        read_conn = _FakeConn(read_cur)
        write_conn = _FakeConn(write_cur)
        mock_conn.side_effect = [read_conn, write_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 2


class TestConsistencyScoreImpact:
    """Verify that flagged contradictions actually lower the consistency dimension."""

    def test_consistency_score_impact(self):
        """Facts with contradicts_fact_id should reduce consistency score."""
        from scripts.research.auto_grader import _score_consistency

        # No contradictions
        clean_facts = [
            {"attribute_name": "employee_count", "attribute_value": "100", "contradicts_fact_id": None},
        ]
        clean_score = _score_consistency(clean_facts)

        # One contradiction
        flagged_facts = [
            {"attribute_name": "employee_count", "attribute_value": "100", "contradicts_fact_id": None},
            {"attribute_name": "employee_count", "attribute_value": "500", "contradicts_fact_id": 1},
        ]
        flagged_score = _score_consistency(flagged_facts)

        assert flagged_score < clean_score
        assert clean_score - flagged_score >= 2.0  # 2.0 per contradiction
