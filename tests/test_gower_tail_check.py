"""Tests for the critical-MV tail-check in scripts/scoring/compute_gower_similarity.py.

Background: compute_gower_similarity.py silently drops 3 scorecard MVs
(mv_unified_scorecard, mv_target_scorecard, mv_employer_search) via
CASCADE during its rebuild of mv_employer_features and
employer_comparables. The 2026-05-12 Open Problem "Gower Compute Drops
Scorecard MVs" records the 5th recurrence pattern and chooses adding a
tail-check to compute_gower_similarity itself as the durable answer
(refresh_all.py was already guarded by `ship/2026-05-11-refresh-all-tail-check`
28c55fe, but standalone Gower runs were not).

Unlike refresh_all's tail-check, Gower's tail-check is NON-FATAL: Gower
compute already finished successfully, so we surface the missing MVs as
a WARNING with the exact recovery command, but we never sys.exit nonzero.

We monkeypatch the subprocess.run call inside compute_gower_similarity so
the tests never touch the database or run the gate script.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.scoring.compute_gower_similarity as gower  # noqa: E402


def _fake_completed(returncode: int) -> SimpleNamespace:
    """Stand-in for subprocess.CompletedProcess with just .returncode."""
    return SimpleNamespace(returncode=returncode)


def test_tail_check_happy_path_prints_ok(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When check_critical_mvs.py returns 0, the helper prints OK and
    emit_tail_check_warning prints no warning."""
    import subprocess as _real_subprocess

    monkeypatch.setattr(
        _real_subprocess,
        "run",
        lambda *a, **kw: _fake_completed(0),
    )

    rc = gower.run_critical_mvs_check()
    gower.emit_tail_check_warning(rc)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc == 0
    assert "OK: critical-MV tail-check passed" in combined
    # The non-fatal warning banner must NOT appear on the happy path.
    assert "WARNING: critical-MV tail-check failed" not in combined


def test_tail_check_missing_mv_emits_non_fatal_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When check_critical_mvs.py reports a missing MV (rc=1), the helper
    must emit a clear WARNING with the recommended fix command -- and
    must NOT raise/exit. Gower compute itself succeeded."""
    import subprocess as _real_subprocess

    monkeypatch.setattr(
        _real_subprocess,
        "run",
        lambda *a, **kw: _fake_completed(1),
    )

    # Calling the helper must not raise on the failure path.
    rc = gower.run_critical_mvs_check()
    gower.emit_tail_check_warning(rc)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc == 1
    assert "WARNING: critical-MV tail-check failed" in combined
    assert "refresh_all.py --skip-gower" in combined
    # CASCADE / drop / known recurrence pattern phrasing should be present
    # so the operator understands this is the documented Gower problem.
    assert "CASCADE" in combined or "scorecard MVs" in combined


def test_tail_check_missing_script_is_warned_not_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If check_critical_mvs.py is missing on disk, return -1 sentinel
    and print a WARNING -- never raise."""
    real_isfile = os.path.isfile

    def _fake_isfile(path: str) -> bool:
        if "check_critical_mvs" in str(path):
            return False
        return real_isfile(path)

    monkeypatch.setattr(gower.os.path, "isfile", _fake_isfile)

    rc = gower.run_critical_mvs_check()
    gower.emit_tail_check_warning(rc)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc == -1
    assert "WARNING" in combined
    assert "skipping tail-check" in combined
    # And no "tail-check failed" banner -- script-missing is a separate path.
    assert "critical-MV tail-check failed" not in combined


def test_emit_tail_check_warning_swallows_unknown_rcs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pass an arbitrary non-zero rc directly: emit_tail_check_warning must
    print the WARNING banner and NOT raise. This locks in the contract
    that Gower compute never fails due to the tail-check."""
    gower.emit_tail_check_warning(2)  # e.g., rc=2 from check_critical_mvs (db unreachable)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "WARNING: critical-MV tail-check failed" in combined
    assert "rc=2" in combined
