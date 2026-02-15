"""
Compare documented router endpoint counts vs current code decorators.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = ROOT / "api" / "routers"
DOC_SOURCE = ROOT / "codex_context_briefing.md"
REPORT = ROOT / "docs" / "PARALLEL_ROUTER_DOCS_DRIFT.md"


TABLE_ROW_RE = re.compile(r"\|\s*`([^`]+\.py)`\s*\|[^|]*\|\s*([0-9]+)\s*\|")


def parse_doc_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in TABLE_ROW_RE.finditer(text):
        file_name = match.group(1).strip()
        count = int(match.group(2))
        counts[file_name] = count
    return counts


def count_router_endpoints() -> dict[str, int]:
    out: dict[str, int] = {}
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        count = len(re.findall(r"@router\.(?:get|post|put|delete|patch)\(", text))
        out[path.name] = count
    return out


def main() -> int:
    doc_counts = parse_doc_counts(DOC_SOURCE.read_text(encoding="utf-8"))
    actual_counts = count_router_endpoints()

    rows = []
    for file_name, doc_count in sorted(doc_counts.items()):
        actual = actual_counts.get(file_name)
        if actual is None:
            status = "MISSING_IN_CODE"
            delta = "n/a"
        else:
            delta_num = actual - doc_count
            delta = f"{delta_num:+d}"
            status = "OK" if delta_num == 0 else "DRIFT"
        rows.append((file_name, doc_count, actual, delta, status))

    undocumented = sorted(set(actual_counts) - set(doc_counts))

    lines = [
        "# Parallel Router Docs Drift",
        "",
        "Compared `codex_context_briefing.md` API table to live `api/routers/*.py` decorators.",
        "",
        "## Documented Routers",
        "| File | Doc Count | Actual Count | Delta | Status |",
        "|------|-----------|--------------|-------|--------|",
    ]

    for file_name, doc_count, actual, delta, status in rows:
        actual_s = str(actual) if actual is not None else "missing"
        lines.append(f"| `{file_name}` | {doc_count} | {actual_s} | {delta} | {status} |")

    lines.extend(["", "## Undocumented Router Files"])
    if undocumented:
        for file_name in undocumented:
            lines.append(f"- `{file_name}` ({actual_counts[file_name]} endpoints)")
    else:
        lines.append("- None")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

