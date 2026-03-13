"""Tests for unified scorecard CSV export endpoint."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestCsvExport:
    def test_export_returns_csv(self, client):
        resp = client.get("/api/scorecard/unified/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row
        header = lines[0]
        assert "employer_id" in header
        assert "recommended_action" in header

    def test_export_respects_state_filter(self, client):
        resp = client.get("/api/scorecard/unified/export?state=CA")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        # All data rows should have CA in state column
        if len(lines) > 1:
            import csv as csv_mod
            import io
            reader = csv_mod.reader(io.StringIO(resp.text))
            header = next(reader)
            state_idx = header.index('state')
            for row in reader:
                assert row[state_idx] == 'CA'

    def test_export_respects_tier_filter(self, client):
        resp = client.get("/api/scorecard/unified/export?score_tier=Priority")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        if len(lines) > 1:
            import csv as csv_mod
            import io
            reader = csv_mod.reader(io.StringIO(resp.text))
            header = next(reader)
            tier_idx = header.index('score_tier')
            for row in reader:
                assert row[tier_idx] == 'Priority'

    def test_export_capped_at_10000(self, client):
        resp = client.get("/api/scorecard/unified/export?min_factors=1")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) <= 10001  # header + 10000 max rows

    def test_export_has_recommended_action(self, client):
        resp = client.get("/api/scorecard/unified/export")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        if len(lines) > 1:
            import csv as csv_mod
            import io
            reader = csv_mod.reader(io.StringIO(resp.text))
            header = next(reader)
            action_idx = header.index('recommended_action')
            row = next(reader)
            assert row[action_idx] in ('PURSUE NOW', 'RESEARCH FIRST', 'INSUFFICIENT DATA', 'MONITOR')
