"""Regression tests for the data source catalog used by data_source_freshness.

The freshness driver (`scripts/maintenance/create_data_freshness.py`) reads from
`api/data_source_catalog.py::DATA_SOURCE_ENTRIES` and executes each entry's
`count_query` + optional `date_query` against the database. If any of those
queries reference a missing table or column, the refresh script silently skips
the entry (see Open Problem: data_source_freshness catalog broken references).

These tests ensure the catalog stays in sync with the live schema by invoking
the new `--validate-only` mode end-to-end against the database.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "create_data_freshness.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


def test_validate_only_returns_zero_when_catalog_is_clean():
    """All catalog entries should execute cleanly against the live DB."""
    result = _run(["--validate-only"])
    assert result.returncode == 0, (
        f"--validate-only failed -- one or more catalog entries reference "
        f"missing tables/columns.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The summary line should report zero broken entries.
    assert "0 broken" in result.stdout, (
        f"expected '0 broken' in stdout, got:\n{result.stdout}"
    )


def test_validate_only_summary_shape():
    """The summary line should report N/M valid, with N == M when clean."""
    result = _run(["--validate-only"])
    assert result.returncode == 0
    # Look for "Summary: N/M entries valid"
    summary_lines = [
        line for line in result.stdout.splitlines() if line.startswith("Summary:")
    ]
    assert len(summary_lines) == 1, (
        f"expected exactly one Summary: line, got {summary_lines}\n"
        f"full stdout:\n{result.stdout}"
    )
    summary = summary_lines[0]
    # Extract "N/M" — should be like "Summary: 44/44 entries valid; 0 broken"
    import re
    m = re.search(r"Summary: (\d+)/(\d+) entries valid; (\d+) broken", summary)
    assert m, f"unexpected summary format: {summary!r}"
    valid, total, broken = (int(x) for x in m.groups())
    assert valid == total, f"only {valid}/{total} catalog entries validate"
    assert broken == 0, f"{broken} catalog entries are broken"


def test_catalog_entries_present():
    """Sanity: at least 40 entries are registered."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from api.data_source_catalog import DATA_SOURCE_ENTRIES  # noqa: E402

    assert len(DATA_SOURCE_ENTRIES) >= 40, (
        f"only {len(DATA_SOURCE_ENTRIES)} catalog entries registered -- "
        "a previous fix may have over-trimmed the catalog"
    )
    # Every entry must have a source_name and count_query.
    for entry in DATA_SOURCE_ENTRIES:
        assert entry.get("source_name"), f"entry missing source_name: {entry}"
        assert entry.get("count_query"), (
            f"entry {entry.get('source_name')} missing count_query"
        )
