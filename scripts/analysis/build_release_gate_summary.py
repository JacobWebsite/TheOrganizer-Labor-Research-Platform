"""
Build a single release-gate summary from key generated reports.
"""
from __future__ import annotations

from pathlib import Path
import re
from datetime import datetime


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "RELEASE_GATE_SUMMARY.md"

SOURCES = {
    "validator": ROOT / "docs" / "PHASE1_MERGE_VALIDATION_REPORT.md",
    "password": ROOT / "docs" / "PARALLEL_PHASE1_PASSWORD_AUDIT.md",
    "xss": ROOT / "docs" / "PARALLEL_INNERHTML_API_RISK_PRIORITY.md",
    "migration": ROOT / "docs" / "PARALLEL_DB_CONFIG_MIGRATION_REPORT.md",
    "drift": ROOT / "docs" / "PARALLEL_ROUTER_DOCS_DRIFT.md",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def extract(pattern: str, text: str, default: str = "unknown") -> str:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1) if m else default


def main() -> int:
    t_validator = read(SOURCES["validator"])
    t_password = read(SOURCES["password"])
    t_xss = read(SOURCES["xss"])
    t_migration = read(SOURCES["migration"])
    t_drift = read(SOURCES["drift"])

    validator_pass = extract(r"Passed:\s*([0-9]+/[0-9]+)", t_validator)
    password_findings = extract(r"- Findings:\s*([0-9]+)", t_password)
    xss_findings = extract(r"- Findings:\s*([0-9]+)", t_xss)
    migration_changed = extract(r"- Files changed:\s*([0-9]+)", t_migration)
    drift_count = len(re.findall(r"\|\s*`[^`]+`\s*\|[^|]*\|[^|]*\|[^|]*\|\s*DRIFT\s*\|", t_drift))

    lines = [
        "# Release Gate Summary",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Status",
        f"- Validator: {validator_pass}",
        f"- Password quoted-literal findings: {password_findings}",
        f"- Prioritized innerHTML findings: {xss_findings}",
        f"- Latest migration report files changed: {migration_changed}",
        f"- Router/docs drift rows: {drift_count}",
        "",
        "## Source Reports",
        f"- `{SOURCES['validator'].relative_to(ROOT)}`",
        f"- `{SOURCES['password'].relative_to(ROOT)}`",
        f"- `{SOURCES['xss'].relative_to(ROOT)}`",
        f"- `{SOURCES['migration'].relative_to(ROOT)}`",
        f"- `{SOURCES['drift'].relative_to(ROOT)}`",
    ]

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

