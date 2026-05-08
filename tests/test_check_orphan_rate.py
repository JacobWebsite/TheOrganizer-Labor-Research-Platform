"""Tests for scripts/maintenance/check_orphan_rate.py.

Smoke + boundary tests against the live DB. The orphan rate has been
between 64.7% (R6 baseline) and 68.1% (worst R7) for the past 2 months,
so the data is stable enough to test against directly.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "check_orphan_rate.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


def test_default_ceiling_passes_today():
    # The 67.0% default ceiling is well above today's actual (~65.2%).
    result = _run([])
    assert result.returncode == 0, (
        f"orphan-rate check failed unexpectedly: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "OK" in result.stdout


def test_low_ceiling_fails():
    # 50% ceiling is impossible for today's data, must fail.
    result = _run(["--max-orphan-pct", "50"])
    assert result.returncode == 1
    assert "FAIL" in result.stderr or "FAIL" in result.stdout


def test_json_output_shape():
    result = _run(["--json"])
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    for key in (
        "status",
        "total_f7",
        "matched",
        "orphans",
        "orphan_pct",
        "max_allowed_pct",
    ):
        assert key in payload, f"missing key: {key}"
    assert payload["status"] == "OK"
    # Sanity: orphans + matched should equal total
    assert payload["orphans"] + payload["matched"] == payload["total_f7"]
    # Sanity: orphan_pct should be within (0, 100)
    assert 0 < payload["orphan_pct"] < 100


def test_orphan_pct_within_known_band():
    # The orphan rate has been 64.7-68.1% across the last 2 months.
    # If today's value falls outside [55, 75], something is very wrong
    # in either the matcher or the f7_employers_deduped table.
    result = _run(["--json"])
    assert result.returncode == 0
    pct = json.loads(result.stdout.strip())["orphan_pct"]
    assert 55.0 <= pct <= 75.0, (
        f"orphan_pct {pct}% is outside the expected [55, 75] band -- "
        "either the matcher pipeline regressed dramatically or "
        "f7_employers_deduped row count changed unexpectedly"
    )
