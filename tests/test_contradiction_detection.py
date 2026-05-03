"""
Tests for _resolve_contradictions() and related helpers in scripts/research/agent.py.
"""

from unittest.mock import patch


from scripts.research.agent import _resolve_contradictions, _string_similarity, _find_contradictions


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


class TestStringSimilarity:
    """Tests for _string_similarity() bigram Jaccard helper."""

    def test_identical_strings(self):
        assert _string_similarity("walmart", "walmart") == 1.0

    def test_empty_strings(self):
        assert _string_similarity("", "") == 0.0
        assert _string_similarity("abc", "") == 0.0
        assert _string_similarity("", "abc") == 0.0

    def test_very_similar(self):
        # "walmart inc" vs "walmart inc." should be very similar (> 0.90)
        assert _string_similarity("walmart inc", "walmart inc.") > 0.90

    def test_clearly_different(self):
        # "private" vs "public" should be low similarity
        assert _string_similarity("private", "public") < 0.50

    def test_single_char_strings(self):
        # Single chars produce no bigrams
        assert _string_similarity("a", "b") == 0.0


class TestContradictionDetection:
    """Tests for _resolve_contradictions()."""

    @patch("scripts.research.agent._conn")
    def test_numeric_contradiction_detected(self, mock_conn):
        """Employee count values diverging by >1.5x should flag contradicts_fact_id."""
        facts = [
            _make_fact(1, "employee_count", "100"),
            _make_fact(2, "employee_count", "500"),
        ]
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
    def test_no_contradiction_at_boundary(self, mock_conn):
        """Values at exactly 1.5x ratio should NOT be flagged (strict >)."""
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
    def test_numeric_contradiction_at_1_6x(self, mock_conn):
        """Values at 1.6x ratio SHOULD be flagged with the new 1.5x threshold."""
        facts = [
            _make_fact(1, "employee_count", "100"),
            _make_fact(2, "employee_count", "160"),
        ]
        read_cur = _FakeCursor(facts)
        write_cur = _FakeCursor([])
        read_conn = _FakeConn(read_cur)
        write_conn = _FakeConn(write_cur)
        mock_conn.side_effect = [read_conn, write_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 1

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
    def test_fuzzy_similar_strings_not_flagged(self, mock_conn):
        """Strings that are >90% similar should NOT be flagged as contradictions."""
        facts = [
            _make_fact(1, "legal_name", "Walmart Inc."),
            _make_fact(2, "legal_name", "Walmart Inc"),
        ]
        read_cur = _FakeCursor(facts)
        read_conn = _FakeConn(read_cur)
        mock_conn.side_effect = [read_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 0

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

    @patch("scripts.research.agent._conn")
    def test_skip_values_ignored(self, mock_conn):
        """Exhaustive coverage values should be skipped in comparison."""
        facts = [
            _make_fact(1, "legal_name", "Acme Corp"),
            _make_fact(2, "legal_name", "Not found (searched)"),
        ]
        read_cur = _FakeCursor(facts)
        read_conn = _FakeConn(read_cur)
        mock_conn.side_effect = [read_conn]

        count = _resolve_contradictions(run_id=1)

        assert count == 0


class TestFindContradictions:
    """Tests for the shared _find_contradictions() logic."""

    def test_numeric_1_5x_threshold(self):
        by_attr = {
            "employee_count": [
                {"id": 1, "attribute_value": "100"},
                {"id": 2, "attribute_value": "160"},
            ]
        }
        result = _find_contradictions(by_attr)
        assert len(result) == 1

    def test_fuzzy_string_no_false_positive(self):
        by_attr = {
            "ceo_name": [
                {"id": 1, "attribute_value": "John Smith"},
                {"id": 2, "attribute_value": "John Smith Jr."},
            ]
        }
        result = _find_contradictions(by_attr)
        # These are similar enough (>0.90) to not be contradictions
        sim = _string_similarity("john smith", "john smith jr.")
        if sim > 0.90:
            assert len(result) == 0
        else:
            assert len(result) == 1


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
