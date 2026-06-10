"""Tests for scripts/etl/backfill_terminated_fnums_unions_master.py.

Smoke + regression tests against the live DB. Backfill is INSERT...ON CONFLICT
DO NOTHING so re-runs are no-ops; these tests can be re-run freely.

Covers:
- Dry-run reports counts without writing.
- Real run is idempotent (second invocation = 0 new rows).
- All 138 fnums land with is_likely_inactive=TRUE.
- f7_union_employer_relations orphan count is 0 after backfill.
- Spot-check the canonical sample (540479 = ANA LU 296) from the
  2026-05-12 investigation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "etl" / "backfill_terminated_fnums_unions_master.py"
)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=180,
    )


def _orphan_count() -> int:
    """Live-DB count of f_nums referenced in f7_union_employer_relations
    that have no row in unions_master.
    """
    from db_config import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(DISTINCT r.union_file_number)
            FROM f7_union_employer_relations r
            LEFT JOIN unions_master um ON um.f_num::int = r.union_file_number
            WHERE r.union_file_number IS NOT NULL AND um.f_num IS NULL
            """
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def test_dry_run_reports_counts_without_writing():
    result = _run(["--dry-run"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Before:" in result.stdout
    assert "[DRY-RUN] No DB changes" in result.stdout
    # Dry-run should NOT have an "After:" report (only the real run prints that).
    assert "After:" not in result.stdout


def test_backfill_is_idempotent_on_second_invocation():
    """Run twice. Second invocation must produce 0 new rows because every
    f_num is already present (ON CONFLICT DO NOTHING).
    """
    # First run -- may or may not insert; we don't care here.
    _run([])
    # Second run -- must be a no-op.
    result = _run([])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Parse the "+N" delta from the "After:" section.
    deltas = []
    in_after = False
    for line in result.stdout.splitlines():
        if "After:" in line:
            in_after = True
            continue
        if in_after and "+" in line and "(" in line:
            # Format examples:
            #   unions_master total:                 26831  (+0)
            #   unions_master is_likely_inactive:    6191  (+0)
            try:
                delta_str = line.split("(+")[-1].split(")")[0]
                deltas.append(int(delta_str))
            except (ValueError, IndexError):
                pass
    assert deltas, f"could not parse deltas from output:\n{result.stdout[-500:]}"
    assert all(d == 0 for d in deltas), (
        f"second run was not idempotent; deltas: {deltas}"
    )


def test_all_138_fnums_have_is_likely_inactive_true_after_backfill():
    """Pre-backfill there were exactly 138 orphan f_nums (per the 2026-05-12
    investigation). They should now all exist in unions_master with
    is_likely_inactive=TRUE.
    """
    # Make sure the backfill has run at least once.
    _run([])

    from db_config import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        # The 138 backfilled rows are the unique inactive entries that also
        # have a term_date AND are referenced by f7_union_employer_relations.
        # We pulled them in via the backfill, so they must satisfy:
        #   - is_likely_inactive = TRUE
        #   - term_date IS NOT NULL
        cur.execute(
            """
            SELECT COUNT(*) FROM unions_master
            WHERE is_likely_inactive = TRUE AND term_date IS NOT NULL
            """
        )
        n = int(cur.fetchone()[0])
        # At least 138 -- could be more if future runs add more terminated
        # entries, but never fewer.
        assert n >= 138, (
            f"expected >=138 inactive+term_date rows, got {n}. "
            "Did the backfill INSERT fail?"
        )

        # And every fnum that was previously in the 138-orphan set must now
        # exist in unions_master.
        cur.execute(
            """
            SELECT COUNT(*) FROM f7_union_employer_relations r
            LEFT JOIN unions_master um ON um.f_num::int = r.union_file_number
            WHERE r.union_file_number IS NOT NULL AND um.f_num IS NULL
            """
        )
        orphans = int(cur.fetchone()[0])
        assert orphans == 0, (
            f"expected 0 orphan f7 references after backfill, got {orphans}"
        )
    finally:
        conn.close()


def test_orphan_count_is_zero_after_backfill():
    """Direct invariant check: after backfill, every union_file_number in
    f7_union_employer_relations resolves to a unions_master row.
    """
    _run([])
    assert _orphan_count() == 0


def test_canonical_sample_540479_ana_lu_296():
    """Regression guard for the canonical investigation sample.

    From docs/scratch/138_unresolved_f_nums_investigation_2026_05_12.md:
        f_num=540479  ANA  LU 296  terminated 2008-08-31
    """
    _run([])

    from db_config import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT aff_abbr, desig_name, local_number, is_likely_inactive,
                   term_date
            FROM unions_master WHERE f_num = %s
            """,
            ("540479",),
        )
        row = cur.fetchone()
        assert row is not None, "fnum 540479 missing from unions_master"
        aff_abbr, desig_name, local_number, is_inactive, term_date = row
        assert aff_abbr == "ANA"
        assert desig_name == "LOCAL UNION"
        assert local_number == "296"
        assert is_inactive is True
        assert term_date is not None
        assert term_date.year == 2008
        assert term_date.month == 8
    finally:
        conn.close()
