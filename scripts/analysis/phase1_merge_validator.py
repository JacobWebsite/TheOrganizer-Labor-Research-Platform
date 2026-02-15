"""
Run core Phase 1 validation checks and emit a one-page report.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "PHASE1_MERGE_VALIDATION_REPORT.md"


@dataclass
class CheckResult:
    name: str
    command: str
    ok: bool
    output: str


def run_check(name: str, command: str) -> CheckResult:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        shell=True,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return CheckResult(name=name, command=command, ok=(proc.returncode == 0), output=out.strip())


def summarize_output(text: str, max_lines: int = 12) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "(no output)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    head = "\n".join(lines[:max_lines])
    return f"{head}\n... ({len(lines) - max_lines} more lines)"


def main() -> int:
    checks = [
        ("Regression Guards", "python -m pytest tests/test_phase1_regression_guards.py -q"),
        ("Name Normalization Tests", "python -m pytest tests/test_name_normalization.py -q"),
        ("Contract Field Parity Tests", "python -m pytest tests/test_scorecard_contract_field_parity.py -q"),
        ("Frontend/API Audit", "python scripts/analysis/check_frontend_api_alignment.py"),
        ("Password Bug Scanner", "python scripts/analysis/find_literal_password_bug.py"),
        ("InnerHTML Risk Priority", "python scripts/analysis/prioritize_innerhtml_api_risk.py"),
        ("Router Docs Drift", "python scripts/analysis/check_router_docs_drift.py"),
    ]

    results = [run_check(name, cmd) for name, cmd in checks]
    pass_count = sum(1 for r in results if r.ok)

    lines = [
        "# Phase 1 Merge Validation Report",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Passed: {pass_count}/{len(results)}",
        "",
        "## Check Results",
    ]

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        lines.append(f"- **{r.name}**: {status}")
        lines.append(f"  - Command: `{r.command}`")
        lines.append("  - Output:")
        lines.append("```text")
        lines.append(summarize_output(r.output))
        lines.append("```")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {REPORT}")
    print(f"Passed: {pass_count}/{len(results)}")
    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

