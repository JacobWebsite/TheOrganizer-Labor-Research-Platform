"""Union Explorer Audit -- Layer 1 (deterministic SQL invariants).

Runs every check defined in audit_union_truth_queries.sql. Hard-gate checks
that return any rows cause a non-zero exit code; advisory checks are reported
but do not block. Output is written to:

    audit_runs/<DATE>/layer1_results.json
    audit_runs/<DATE>/layer1_report.md

Usage:
    py scripts/maintenance/audit_union_layer1.py
    py scripts/maintenance/audit_union_layer1.py --output-dir custom/path
    py scripts/maintenance/audit_union_layer1.py --no-fail-on-hard
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

CHECK_HEADER_RE = re.compile(
    r"--\s*@check:\s*(?P<name>[\w_]+)\s*\n"
    r"--\s*@gate:\s*(?P<gate>hard|advisory)\s*\n"
    r"--\s*@description:\s*(?P<description>[^\n]+)\n"
    r"--\s*@expect:\s*(?P<expect>[^\n]+)\n"
    r"--\s*@sql:\s*\n"
    r"(?P<sql>.*?)(?=(?:\n--\s*@check:)|\Z)",
    re.DOTALL,
)


def parse_checks(sql_path: Path) -> list[dict]:
    text = sql_path.read_text(encoding="utf-8")
    checks = []
    for m in CHECK_HEADER_RE.finditer(text):
        sql = m.group("sql").strip()
        if sql.endswith(";"):
            sql = sql[:-1]
        checks.append({
            "name": m.group("name"),
            "gate": m.group("gate"),
            "description": m.group("description").strip(),
            "expect": m.group("expect").strip(),
            "sql": sql,
        })
    return checks


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _evaluate(check: dict, rows: list[dict]) -> tuple[bool, str]:
    """Return (passed, reason). For zero-rows expectation, pass means rows is empty.
    For report_only, always pass (the rows are surface info, not a failure)."""
    expect = check["expect"].lower()
    if expect.startswith("zero rows"):
        return (len(rows) == 0, f"{len(rows)} row(s) returned (expected 0)")
    if expect.startswith("report_only"):
        return (True, "advisory metric; not pass/fail")
    return (len(rows) == 0, f"{len(rows)} row(s); expectation '{check['expect']}' not recognised, defaulting to zero-rows semantics")


def run_check(cur, check: dict) -> dict:
    started = time.perf_counter()
    try:
        cur.execute(check["sql"])
        raw_rows = cur.fetchall()
    except Exception as exc:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return {
            "name": check["name"],
            "gate": check["gate"],
            "description": check["description"],
            "expect": check["expect"],
            "passed": False,
            "row_count": 0,
            "rows_sample": [],
            "reason": f"SQL error: {exc}",
            "error": str(exc),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
    rows = []
    for r in raw_rows:
        if hasattr(r, "_asdict"):
            d = r._asdict()
        elif isinstance(r, dict):
            d = dict(r)
        else:
            cols = [c.name for c in cur.description] if cur.description else []
            d = dict(zip(cols, r))
        rows.append({k: _to_jsonable(v) for k, v in d.items()})
    passed, reason = _evaluate(check, rows)
    return {
        "name": check["name"],
        "gate": check["gate"],
        "description": check["description"],
        "expect": check["expect"],
        "passed": passed,
        "reason": reason,
        "row_count": len(rows),
        "rows_sample": rows[:5],
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }


def write_report(results: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "layer1_results.json"
    md_path = out_dir / "layer1_report.md"

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "hard_failures": sum(1 for r in results if not r["passed"] and r["gate"] == "hard"),
        "advisory_failures": sum(1 for r in results if not r["passed"] and r["gate"] == "advisory"),
        "errored": sum(1 for r in results if r.get("error")),
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    json_path.write_text(
        json.dumps({"summary": summary, "checks": results}, indent=2, default=_to_jsonable),
        encoding="utf-8",
    )

    lines = [
        "# Union Explorer Audit -- Layer 1 Report",
        "",
        f"Run at: {summary['ran_at']}",
        "",
        f"- Total checks: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Hard failures: {summary['hard_failures']}",
        f"- Advisory failures: {summary['advisory_failures']}",
        f"- Errored: {summary['errored']}",
        "",
        "## Checks",
        "",
    ]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        gate = r["gate"].upper()
        lines.append(f"### [{status}] [{gate}] {r['name']}")
        lines.append(f"- {r['description']}")
        lines.append(f"- expect: {r['expect']}")
        if r.get("error"):
            lines.append(f"- ERROR: `{r['error']}`")
        else:
            lines.append(f"- result: {r.get('reason', '')}")
            if r["gate"] == "advisory" and r["expect"].lower().startswith("report_only") and r.get("rows_sample"):
                lines.append(f"- value: `{json.dumps(r['rows_sample'][0], default=_to_jsonable)}`")
            elif r.get("rows_sample") and not r["passed"]:
                lines.append("- sample rows:")
                for sr in r["rows_sample"]:
                    lines.append(f"  - `{json.dumps(sr, default=_to_jsonable)}`")
        lines.append(f"- duration: {r['duration_ms']} ms")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to:\n  {json_path}\n  {md_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sql-file", default=None, help="Path to audit_union_truth_queries.sql")
    ap.add_argument("--output-dir", default=None, help="Override audit_runs/<DATE> output directory")
    ap.add_argument("--no-fail-on-hard", action="store_true",
                    help="Always exit 0 even if hard-gate checks fail (for ad-hoc inspection runs)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    sql_path = Path(args.sql_file) if args.sql_file else (here / "audit_union_truth_queries.sql")
    if not sql_path.is_file():
        print(f"ERROR: SQL file not found: {sql_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir) if args.output_dir else (
        here.parent.parent / "audit_runs" / dt.date.today().isoformat()
    )

    checks = parse_checks(sql_path)
    if not checks:
        print(f"ERROR: no @check blocks parsed from {sql_path}", file=sys.stderr)
        return 2
    print(f"Parsed {len(checks)} checks from {sql_path.name}")

    results: list[dict] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for c in checks:
                print(f"  running: {c['name']:<55s}", end="", flush=True)
                r = run_check(cur, c)
                results.append(r)
                tag = "PASS" if r["passed"] else "FAIL"
                gate = c["gate"].upper()
                err = f"  ERROR: {r['error']}" if r.get("error") else ""
                print(f" [{tag}/{gate}] {r['row_count']} row(s), {r['duration_ms']} ms{err}")

    write_report(results, out_dir)

    hard_failures = [r for r in results if not r["passed"] and r["gate"] == "hard"]
    if hard_failures and not args.no_fail_on_hard:
        print(f"\n{len(hard_failures)} hard-gate failure(s):")
        for r in hard_failures:
            print(f"  - {r['name']}: {r.get('reason', r.get('error', ''))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
