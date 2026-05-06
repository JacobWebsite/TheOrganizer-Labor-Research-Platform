"""Tests for the F7 orphan rematch executor (dry-run mode).

The executor is gated: --commit is the ONLY path that writes, and it
requires interactive 'yes' confirmation. These tests cover the dry-run
behavior (the read-only path Jacob will use to review thresholds) and
the gate (no writes happen unless --commit is set).
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from db_config import get_connection


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "matching" / "rematch_recoverable_orphans.py"


def _has_staging_table() -> bool:
    """The staging table is created by identify_recoverable_orphans.py.
    These tests skip cleanly if it's not present (CI / fresh DB)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('_recoverable_f7_orphans')")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT COUNT(*) FROM _recoverable_f7_orphans")
        n = cur.fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_staging_table(),
    reason="_recoverable_f7_orphans staging not present",
)


def _uml_count() -> int:
    """Total active rows in unified_match_log targeting f7 system."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM unified_match_log "
        "WHERE target_system = 'f7' AND status = 'active'"
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def test_dry_run_writes_nothing_to_unified_match_log(tmp_path):
    """The default invocation (no --commit) MUST NOT touch UML at all."""
    csv_out = tmp_path / "rematch.csv"
    before = _uml_count()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "200", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=120,
    )
    after = _uml_count()
    assert proc.returncode == 0, f"dry-run failed: {proc.stderr[:500]}"
    assert before == after, (
        f"DRY-RUN WROTE TO unified_match_log!  before={before} after={after}"
    )


def test_dry_run_emits_csv_with_expected_columns(tmp_path):
    """CSV output is the artifact Jacob will review. Lock its columns."""
    csv_out = tmp_path / "rematch.csv"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "500", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert csv_out.exists()
    with open(csv_out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Schema lock — these are the columns the review process will rely on
        assert reader.fieldnames == [
            "f7_employer_id", "f7_name", "f7_state",
            "source", "source_id", "source_name_norm",
            "method", "score",
        ]
        rows = list(reader)
    # At limit=500 we expect at least SOME matches across all 4 sources.
    assert len(rows) > 0, "no matches found at limit=500 — sanity check failed"
    for r in rows:
        assert r["source"] in {"osha", "whd", "990", "sam"}
        assert r["method"] in {
            "NAME_STANDARD_STATE_ZIP_EXACT",
            "NAME_STANDARD_STATE_EXACT",
            "NAME_AGGRESSIVE_STATE_EXACT",
        }
        assert 0.9 <= float(r["score"]) <= 1.0


def test_dry_run_summary_includes_per_source_breakdown(tmp_path):
    """The stdout summary is what surfaces in screen-share / handoff
    docs — make sure it carries the per-source counts."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "300"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    out = proc.stdout
    assert "SUMMARY" in out
    # Each of 4 sources should appear in the breakdown
    for src in ("osha", "whd", "990", "sam"):
        assert src in out, f"summary missing {src}"
    # Score distribution section
    assert "Score distribution" in out


def test_dry_run_matches_are_state_consistent(tmp_path):
    """No match should pair an F7 in one state with a source record in
    another. State-mismatch indicates a regression in the SQL where
    clause."""
    csv_out = tmp_path / "rematch.csv"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "500", "--out-csv", str(csv_out)],
        capture_output=True, text=True, timeout=120,
    )
    # Cross-check: pull the f7 + source rows for each CSV match.
    conn = get_connection()
    cur = conn.cursor()
    state_map = {
        "osha":  ("osha_establishments", "establishment_id", "site_state"),
        "whd":   ("whd_cases",           "case_id",          "state"),
        "990":   ("national_990_filers", "ein",              "state"),
        "sam":   ("sam_entities",        "uei",              "physical_state"),
    }
    with open(csv_out, encoding="utf-8") as f:
        for r in list(csv.DictReader(f))[:50]:
            tbl, idcol, statecol = state_map[r["source"]]
            cur.execute(
                f"SELECT {statecol} FROM {tbl} WHERE {idcol} = %s LIMIT 1",
                [r["source_id"]],
            )
            row = cur.fetchone()
            if row is None:
                continue
            src_state = row[0] if isinstance(row, tuple) else row[statecol]
            assert src_state == r["f7_state"], (
                f"state mismatch: f7={r['f7_state']} src={src_state} "
                f"on {r['source']}/{r['source_id']}"
            )
    conn.close()


def test_commit_flag_does_not_short_circuit_confirmation(tmp_path):
    """--commit alone (no piped 'yes') must not write. The script
    prompts interactively, and an empty stdin returns EOF → script
    aborts. This is the key safety property of the gate."""
    before = _uml_count()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--limit", "100", "--commit", "--min-score", "1.00"],
        capture_output=True, text=True, timeout=120,
        input="",  # empty stdin — confirmation prompt sees EOF
    )
    after = _uml_count()
    assert before == after, "EMPTY-STDIN --commit MUST NOT write to UML"
    # Script should explicitly say "Aborted." when it doesn't get yes
    assert "Aborted" in proc.stdout or "Aborted" in proc.stderr or proc.returncode != 0
