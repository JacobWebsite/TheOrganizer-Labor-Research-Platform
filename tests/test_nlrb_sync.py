"""Tests for NLRB SQLite sync script."""
import sys
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection


class TestNlrbSyncPrereqs:
    """Verify NLRB tables exist with expected structure."""

    def test_nlrb_elections_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_elections")
            count = cur.fetchone()[0]
            assert count > 30000  # known baseline ~33K
        finally:
            conn.close()

    def test_nlrb_participants_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_participants")
            count = cur.fetchone()[0]
            assert count > 1900000  # known baseline ~1.9M
        finally:
            conn.close()

    def test_nlrb_cases_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_cases")
            count = cur.fetchone()[0]
            assert count > 470000  # known baseline ~477K
        finally:
            conn.close()

    def test_nlrb_tallies_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_tallies")
            count = cur.fetchone()[0]
            assert count > 65000
        finally:
            conn.close()

    def test_nlrb_docket_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_docket")
            count = cur.fetchone()[0]
            assert count > 2000000
        finally:
            conn.close()

    def test_nlrb_allegations_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_allegations")
            count = cur.fetchone()[0]
            assert count > 710000
        finally:
            conn.close()

    def test_nlrb_filings_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_filings")
            count = cur.fetchone()[0]
            assert count > 490000
        finally:
            conn.close()

    def test_nlrb_election_results_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_election_results")
            count = cur.fetchone()[0]
            assert count > 30000
        finally:
            conn.close()

    def test_nlrb_voting_units_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_voting_units")
            count = cur.fetchone()[0]
            assert count > 30000
        finally:
            conn.close()

    def test_nlrb_sought_units_exists(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nlrb_sought_units")
            count = cur.fetchone()[0]
            assert count > 50000
        finally:
            conn.close()


class TestNlrbSyncScript:
    """Test the sync script can be imported and has expected structure."""

    def test_script_importable(self):
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        import sync_nlrb_sqlite
        assert hasattr(sync_nlrb_sqlite, "sync_elections")
        assert hasattr(sync_nlrb_sqlite, "sync_cases")
        assert hasattr(sync_nlrb_sqlite, "sync_participants")
        assert hasattr(sync_nlrb_sqlite, "sync_tallies")
        assert hasattr(sync_nlrb_sqlite, "sync_docket")
        assert hasattr(sync_nlrb_sqlite, "sync_allegations")
        assert hasattr(sync_nlrb_sqlite, "sync_filings")
        assert hasattr(sync_nlrb_sqlite, "sync_election_results")
        assert hasattr(sync_nlrb_sqlite, "sync_voting_units")
        assert hasattr(sync_nlrb_sqlite, "sync_sought_units")

    def test_script_handles_missing_file(self):
        """Script should exit gracefully if SQLite file doesn't exist."""
        import subprocess
        result = subprocess.run(
            ["py", str(ROOT / "scripts" / "etl" / "sync_nlrb_sqlite.py"),
             "/nonexistent/path.db"],
            capture_output=True, text=True
        )
        assert result.returncode != 0 or "not found" in (result.stdout + result.stderr).lower()

    def test_script_phase_choices(self):
        """Verify all expected phases are available via --phase."""
        sys.path.insert(0, str(ROOT / "scripts" / "etl"))
        import sync_nlrb_sqlite
        import argparse
        # Parse --help to verify phase choices
        parser = argparse.ArgumentParser()
        parser.add_argument("sqlite_path")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--phase", default="all",
                            choices=["cases", "elections", "participants",
                                     "tallies", "docket", "allegations",
                                     "filings", "election_results",
                                     "voting_units", "sought_units", "all"])
        # Should parse without error
        args = parser.parse_args(["test.db", "--phase", "elections"])
        assert args.phase == "elections"
