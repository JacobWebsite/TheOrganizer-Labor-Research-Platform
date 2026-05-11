"""Tests for the critical-MV tail-check in scripts/scoring/refresh_all.py.

Background: mv_target_scorecard and mv_employer_search silently disappeared
three times in three weeks (2026-04-30, 2026-05-09, 2026-05-10). The
release-checklist gate (scripts/maintenance/check_critical_mvs.py) catches
this at /ship time, but until 2026-05-11 a refresh that silently produced
an empty MV would still exit zero -- the regression sat hidden until
somebody happened to ship.

These tests assert that refresh_all.main():
  * propagates a non-zero exit when the tail-check fails
  * exits cleanly when everything passes
  * still prints the rebuild summary in both paths

We patch the subprocess.run call inside refresh_all so the test never
touches the database or runs any build scripts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.scoring.refresh_all as refresh_all  # noqa: E402


def _fake_completed(returncode: int) -> SimpleNamespace:
    """Stand-in for subprocess.CompletedProcess with just .returncode."""
    return SimpleNamespace(returncode=returncode)


def _make_subprocess_router(tail_rc: int, step_rc: int = 0):
    """Build a fake subprocess.run that returns step_rc for build steps and
    tail_rc when refresh_all invokes check_critical_mvs.py."""

    def _fake_run(cmd, cwd=None, check=False, **kwargs):
        # cmd is [python, script_path]
        script_path = str(cmd[1]) if len(cmd) > 1 else ""
        if "check_critical_mvs" in script_path:
            return _fake_completed(tail_rc)
        return _fake_completed(step_rc)

    return _fake_run


def _patch_pre_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the DB-touching pre-build check."""
    monkeypatch.setattr(refresh_all, "run_pre_checks", lambda: None)


def _patch_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip pytest's argv so argparse doesn't choke on its flags."""
    monkeypatch.setattr(sys, "argv", ["refresh_all.py", "--skip-gower"])


def test_tail_check_failure_propagates_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When check_critical_mvs.py returns 1, refresh_all.main() must sys.exit(1)."""
    _patch_pre_checks(monkeypatch)
    _patch_argv(monkeypatch)
    monkeypatch.setattr(
        refresh_all.subprocess, "run", _make_subprocess_router(tail_rc=1)
    )

    with pytest.raises(SystemExit) as excinfo:
        refresh_all.main()
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "ERROR" in combined
    assert "tail-check" in combined.lower()


def test_tail_check_success_exits_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When every build step and the tail-check return 0, main() returns cleanly."""
    _patch_pre_checks(monkeypatch)
    _patch_argv(monkeypatch)
    monkeypatch.setattr(
        refresh_all.subprocess, "run", _make_subprocess_router(tail_rc=0)
    )

    # No SystemExit should be raised on the happy path.
    refresh_all.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "OK: critical-MV tail-check passed" in combined
    assert "Rebuild chain completed successfully" in combined


def test_tail_check_missing_script_is_warned_not_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If check_critical_mvs.py is missing (rc=-1 sentinel), main() must NOT exit
    nonzero -- we don't want a missing-script edge case to break refresh."""
    _patch_pre_checks(monkeypatch)
    _patch_argv(monkeypatch)

    # Pretend the script isn't on disk.
    real_isfile = os.path.isfile

    def _fake_isfile(path: str) -> bool:
        if "check_critical_mvs" in str(path):
            return False
        return real_isfile(path)

    monkeypatch.setattr(refresh_all.os.path, "isfile", _fake_isfile)
    monkeypatch.setattr(
        refresh_all.subprocess, "run", _make_subprocess_router(tail_rc=99)
    )

    refresh_all.main()  # must not raise

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "WARNING" in combined
    assert "skipping tail-check" in combined


def test_run_critical_mvs_check_returns_subprocess_rc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct unit-test on the helper: it should pass through the subprocess
    return code (so callers can branch on it)."""
    monkeypatch.setattr(
        refresh_all.subprocess, "run", lambda *a, **kw: _fake_completed(2)
    )
    assert refresh_all.run_critical_mvs_check() == 2

    monkeypatch.setattr(
        refresh_all.subprocess, "run", lambda *a, **kw: _fake_completed(0)
    )
    assert refresh_all.run_critical_mvs_check() == 0
