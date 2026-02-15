"""
Scoped JS safety check for unsafe innerHTML assignment patterns.
"""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "files" / "js"
REPORT = ROOT / "docs" / "JS_INNERHTML_SAFETY_CHECK.md"


BLOCKED_PATTERNS = [
    r"breakdown\.state_density",
]


def main() -> int:
    findings = []
    for path in sorted(JS_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for pat in BLOCKED_PATTERNS:
            for m in re.finditer(pat, text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path.name}:{line}: matches `{pat}`")

    lines = [
        "# JS innerHTML Safety Check",
        "",
        "This check enforces scoped regressions from recent fixes.",
        "",
        f"- Findings: {len(findings)}",
        "",
        "## Matches",
    ]
    if findings:
        lines.extend([f"- `{f}`" for f in findings])
    else:
        lines.append("- None")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {REPORT}")
    print(f"Findings: {len(findings)}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())

