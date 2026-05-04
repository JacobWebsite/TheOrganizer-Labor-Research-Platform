"""Tests for scripts/matching/identify_recoverable_orphans.py.

Runs the script via subprocess (mirroring how an operator or release
gate would invoke it) and asserts it stages a plausible candidate set.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "matching" / "identify_recoverable_orphans.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )


def test_default_run_succeeds_and_stages_plausible_count():
    result = _run([])
    assert result.returncode == 0, (
        f"identify_recoverable_orphans returned {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    # Output mentions either "already exists" or "recoverable F7 orphans staged"
    assert (
        "recoverable F7 orphans staged" in result.stdout
        or "already exists" in result.stdout
    ), f"unexpected stdout: {result.stdout}"
    # Should print at least some breakdown
    assert "By NAICS-2 sector" in result.stdout
    assert "By state" in result.stdout


def test_replace_flag_recreates_table():
    # First run: ensure table exists
    _run([])
    # Second run with --replace
    result = _run(["--replace"])
    assert result.returncode == 0
    assert "recoverable F7 orphans staged" in result.stdout, (
        "--replace should always rebuild the table; got: " + result.stdout
    )


def test_dry_run_prints_sql_without_executing():
    result = _run(["--dry-run"])
    assert result.returncode == 0
    assert "CREATE TABLE _recoverable_f7_orphans" in result.stdout
    # Dry-run never produces a row count
    assert "recoverable F7 orphans staged" not in result.stdout


def test_staged_table_has_expected_shape():
    # After running the script, query the staging table directly
    _run([])
    from db_config import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('_recoverable_f7_orphans')")
        row = cur.fetchone()
        regclass = row[0] if isinstance(row, tuple) else row.get("to_regclass")
        assert regclass is not None, "staging table not created"
        cur.execute("SELECT * FROM _recoverable_f7_orphans LIMIT 1")
        cols = {d.name for d in cur.description}
        for required in (
            "employer_id",
            "employer_name",
            "state",
            "naics",
            "naics_2",
            "source_systems_to_retry",
            "source_count_to_retry",
            "staged_at",
        ):
            assert required in cols, f"missing column {required}; got {cols}"
    finally:
        conn.close()
