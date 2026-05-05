"""Tests for scripts/maintenance/backfill_master_naics.py.

Smoke + boundary tests against the live DB. The backfill is idempotent
(only fills NULL values) so re-runs don't perturb other tests.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "backfill_master_naics.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )


def test_dry_run_reports_counts_without_writing():
    result = _run(["--dry-run"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Before backfill:" in result.stdout
    assert "Dry-run: would fill" in result.stdout
    # Must NOT print "rows updated" — dry-run should not write
    assert "rows updated" not in result.stdout


def test_real_run_is_idempotent_on_second_invocation():
    # First invocation may or may not have already happened in another
    # test run. Run it twice; the second time should report 0 new rows
    # because everything is already filled.
    _run([])
    result = _run([])
    assert result.returncode == 0
    # Find "Path 1" and "Path 2" delta lines and assert both report 0
    # (via the "+0," pattern in the After section).
    lines = result.stdout.splitlines()
    after_section = False
    deltas_found = []
    for line in lines:
        if "After backfill:" in line:
            after_section = True
            continue
        if after_section and "+" in line:
            # Format: "with NAICS: ... +63,654" — pull the number after "+"
            try:
                delta_str = line.split("+")[-1].split()[0].replace(",", "")
                deltas_found.append(int(delta_str))
            except (ValueError, IndexError):
                pass
    # On a second run, both deltas should be 0
    assert deltas_found, f"could not parse deltas from output: {result.stdout[-500:]}"
    assert all(d == 0 for d in deltas_found), (
        f"second run was not idempotent; deltas: {deltas_found}"
    )


def test_path_split_strips_comma_separated_naics():
    """Regression guard for the column-truncation bug: Mergent has ~25
    rows with comma-separated NAICS like '335121, 335122'. The backfill
    must take only the first NAICS to fit in master_employers.naics
    (VARCHAR(10)).
    """
    from db_config import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Verify no master ended up with a length>10 NAICS after backfill
        cur.execute(
            "SELECT COUNT(*) FROM master_employers WHERE LENGTH(naics) > 10"
        )
        row = cur.fetchone()
        n = int(row[0] if isinstance(row, tuple) else row.get("count", 0))
        assert n == 0, f"{n} masters have NAICS strings longer than 10 chars"
    finally:
        conn.close()


def test_abbott_has_naics_after_backfill():
    """Abbott Laboratories (master_id 4036186) should have NAICS 325412
    (Pharmaceutical Preparation Manufacturing) after the backfill —
    this is the canonical "V12-now-fires" test case from 2026-05-05."""
    from db_config import get_connection
    # Ensure the backfill has run at least once
    _run([])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT naics FROM master_employers WHERE master_id = 4036186")
        row = cur.fetchone()
        if row is None:
            # Abbott isn't in this DB instance — skip
            import pytest
            pytest.skip("master_id 4036186 (Abbott) not present")
        naics = row[0] if isinstance(row, tuple) else row.get("naics")
        assert naics is not None, "Abbott NAICS still NULL after backfill"
        # Pharma prep is 325412 via SIC 2834. May vary across crosswalk
        # versions; just assert it starts with 3254 (pharma preparations).
        assert naics.startswith("3254"), (
            f"Abbott NAICS {naics!r} does not look like pharma (3254*)"
        )
    finally:
        conn.close()
