"""Tests for the dossier-review queue CSV generator.

Covers:
- query SQL builder (priority modes, gold filter, min quality filter)
- the deep-link URL composition
- CSV serialization (header, missing columns, datetimes)
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock


# The script lives at scripts/research/list_dossiers_needing_review.py
_PROJECT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT))

import importlib.util

_SCRIPT = _PROJECT / "scripts" / "research" / "list_dossiers_needing_review.py"
spec = importlib.util.spec_from_file_location("list_dossiers_needing_review", _SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------
# _build_query
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_default_uses_highest_quality_order(self):
        sql, params = mod._build_query(
            min_quality=6.0, priority="highest_quality", limit=20, gold_only=False
        )
        assert "r.overall_quality_score DESC NULLS LAST" in sql
        assert "LIMIT %s" in sql
        assert params == (6.0, 20)

    def test_contradictions_priority_orders_by_contradiction_count(self):
        sql, _ = mod._build_query(
            min_quality=6.0, priority="contradictions", limit=10, gold_only=False
        )
        # contradictions sort first, then quality, then date
        assert "ORDER BY COALESCE(rf.contradictions, 0) DESC" in sql

    def test_gold_only_adds_filter(self):
        sql, _ = mod._build_query(
            min_quality=6.0, priority="highest_quality", limit=20, gold_only=True
        )
        assert "r.is_gold_standard = TRUE" in sql

    def test_gold_only_off_omits_filter(self):
        sql, _ = mod._build_query(
            min_quality=6.0, priority="highest_quality", limit=20, gold_only=False
        )
        assert "r.is_gold_standard = TRUE" not in sql

    def test_min_quality_propagates_to_params(self):
        sql, params = mod._build_query(
            min_quality=5.0, priority="highest_quality", limit=10, gold_only=False
        )
        assert params[0] == 5.0
        # min_quality is bound to overall_quality_score >= %s
        assert "r.overall_quality_score >= %s" in sql

    def test_unknown_priority_falls_back_to_default(self):
        # Defensive: the CLI restricts choices, but the function should still
        # behave sanely if a programmatic caller passes garbage.
        sql, _ = mod._build_query(
            min_quality=6.0, priority="nonsense", limit=20, gold_only=False
        )
        # Falls back to the highest_quality order
        assert "r.overall_quality_score DESC NULLS LAST" in sql

    def test_filters_to_completed_runs_with_unreviewed_facts(self):
        sql, _ = mod._build_query(
            min_quality=6.0, priority="highest_quality", limit=20, gold_only=False
        )
        assert "r.status = 'completed'" in sql
        # Must filter to runs that have at least one unreviewed fact -- otherwise
        # the queue would surface already-fully-reviewed runs.
        assert "COALESCE(rf.unreviewed, 0) > 0" in sql

    def test_rollup_uses_filter_clauses_not_self_join(self):
        # The aggregate uses COUNT FILTER WHERE, not a CASE-with-OUTER-JOIN
        # pattern -- that pattern would silently drop runs with zero facts.
        sql, _ = mod._build_query(
            min_quality=6.0, priority="highest_quality", limit=20, gold_only=False
        )
        assert "COUNT(*) FILTER (WHERE f.human_verdict IS NOT NULL)" in sql
        assert "COUNT(*) FILTER (WHERE f.contradicts_fact_id IS NOT NULL)" in sql


# ---------------------------------------------------------------------------
# query_dossiers_needing_review (with mocked DB connection)
# ---------------------------------------------------------------------------

class TestQueryDossiersNeedingReview:
    def _make_conn(self, rows):
        """Mock connection that returns the given rows from fetchall()."""
        cur = MagicMock()
        cur.fetchall.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn

    def test_returns_rows_with_deep_links_appended(self):
        rows = [
            {
                "run_id": 42,
                "employer_id": "abc123",
                "company_name": "Acme Corp",
                "company_state": "NY",
                "company_type": "private",
                "industry_naics": "561320",
                "completed_at": datetime(2026, 5, 10, 12, 0),
                "overall_quality_score": 8.5,
                "is_gold_standard": False,
                "total_facts_found": 30,
                "facts_reviewed": 0,
                "facts_unreviewed": 30,
                "contradiction_count": 2,
                "low_confidence_count": 5,
                "web_numeric_count": 3,
            }
        ]
        conn = self._make_conn(rows)
        result = mod.query_dossiers_needing_review(conn=conn)
        assert len(result) == 1
        # Deep links should be appended after the SQL fetch
        assert "priority_facts_url" in result[0]
        assert "frontend_review_url" in result[0]
        assert "/research/runs/42" in result[0]["frontend_review_url"]
        assert "/runs/42/priority-facts" in result[0]["priority_facts_url"]

    def test_empty_result_returns_empty_list(self):
        conn = self._make_conn([])
        result = mod.query_dossiers_needing_review(conn=conn)
        assert result == []


# ---------------------------------------------------------------------------
# write_csv
# ---------------------------------------------------------------------------

class TestWriteCsv:
    def _read_csv(self, text, delimiter=","):
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return list(reader)

    def test_header_matches_csv_columns(self, tmp_path):
        out = tmp_path / "out.csv"
        mod.write_csv([], out, tsv=False)
        content = out.read_text(encoding="utf-8")
        rows = self._read_csv(content)
        # Header is written even with zero data rows
        assert content.startswith(",".join(mod.CSV_COLUMNS)) or content.startswith(
            mod.CSV_COLUMNS[0]
        )
        assert rows == []

    def test_missing_columns_filled_with_empty_string(self, tmp_path):
        out = tmp_path / "out.csv"
        # Row missing several CSV columns; writer must not raise.
        mod.write_csv(
            [{"run_id": 7, "company_name": "Foo Inc"}],
            out,
            tsv=False,
        )
        rows = self._read_csv(out.read_text(encoding="utf-8"))
        assert len(rows) == 1
        assert rows[0]["run_id"] == "7"
        assert rows[0]["company_name"] == "Foo Inc"
        # Missing keys are empty, not "None"
        assert rows[0]["employer_id"] == ""
        assert rows[0]["overall_quality_score"] == ""

    def test_datetime_serialized_as_iso(self, tmp_path):
        out = tmp_path / "out.csv"
        mod.write_csv(
            [{"run_id": 1, "completed_at": datetime(2026, 5, 12, 14, 30, 0)}],
            out,
            tsv=False,
        )
        rows = self._read_csv(out.read_text(encoding="utf-8"))
        assert rows[0]["completed_at"] == "2026-05-12T14:30:00"

    def test_tsv_uses_tab_delimiter(self, tmp_path):
        out = tmp_path / "out.tsv"
        mod.write_csv(
            [{"run_id": 1, "company_name": "Foo, with comma"}],
            out,
            tsv=True,
        )
        text = out.read_text(encoding="utf-8")
        # The header row should be tab-delimited
        first_line = text.split("\n", 1)[0]
        assert "\t" in first_line
        # Commas inside fields should not split into new columns when TSV
        rows = self._read_csv(text, delimiter="\t")
        assert rows[0]["company_name"] == "Foo, with comma"


# ---------------------------------------------------------------------------
# CSV_COLUMNS schema
# ---------------------------------------------------------------------------

class TestCsvColumns:
    def test_includes_identifying_columns(self):
        # Reviewer needs at minimum the run id, the company name, and a URL
        # to click into the UI.
        for col in ("run_id", "company_name", "frontend_review_url"):
            assert col in mod.CSV_COLUMNS

    def test_includes_priority_signal_columns(self):
        # The whole point of the queue is to surface the priority signals
        # without making the reviewer write SQL.
        for col in ("contradiction_count", "low_confidence_count", "web_numeric_count"):
            assert col in mod.CSV_COLUMNS

    def test_includes_quality_score(self):
        assert "overall_quality_score" in mod.CSV_COLUMNS
