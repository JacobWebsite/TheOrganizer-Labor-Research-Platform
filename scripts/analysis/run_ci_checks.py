"""
Run CI-style checks for the parallel hardening lane.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "CI_CHECK_REPORT.md"


@dataclass
class Step:
    name: str
    cmd: str


STEPS = [
    Step("Phase1 Merge Validator", "python scripts/analysis/phase1_merge_validator.py"),
    Step("Frontend XSS Regressions", "python -m pytest tests/test_frontend_xss_regressions.py -q"),
    Step("Scorecard Contract Parity", "python -m pytest tests/test_scorecard_contract_field_parity.py -q"),
    Step("Normalization Tests", "python -m pytest tests/test_name_normalization.py -q"),
    Step("Migration Guard Test", "python -m pytest tests/test_db_config_migration_guard.py -q"),
    Step("innerHTML Lint Check", "python scripts/analysis/check_js_innerhtml_safety.py"),
]


def run(step: Step) -> tuple[bool, str]:
    proc = subprocess.run(step.cmd, cwd=ROOT, shell=True, capture_output=True, text=True)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, out


def main() -> int:
    results = []
    passed = 0
    for step in STEPS:
        ok, out = run(step)
        results.append((step, ok, out))
        if ok:
            passed += 1

    lines = [
        "# CI Check Report",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Passed: {passed}/{len(STEPS)}",
        "",
        "## Steps",
    ]
    for step, ok, out in results:
        lines.append(f"- **{step.name}**: {'PASS' if ok else 'FAIL'}")
        lines.append(f"  - `{step.cmd}`")
        lines.append("```text")
        lines.append("\n".join(out.splitlines()[:20]) if out else "(no output)")
        lines.append("```")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {REPORT}")
    print(f"Passed: {passed}/{len(STEPS)}")
    return 0 if passed == len(STEPS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

