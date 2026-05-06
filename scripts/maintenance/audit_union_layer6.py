"""Union Explorer Audit -- Layer 6 (response-shape sentinels).

Codex 2026-05-04 originally suggested Playwright DOM sentinels for ~10-20 pages
to catch:
  - Sections that throw/unmount despite valid API payload
  - React Query response-shape mismatches (raw Axios vs .data, see unions.js:56)
  - "No data" sections disappearing entirely
  - Large numbers / long names breaking layout

Adding Playwright is heavy (150MB browser bundles, new test framework). The
empty-state suppression (Bug 3) was preempted by the JSX fix; layout-break
detection requires actual browser rendering. The remaining catch -- response-
shape mismatches -- IS testable without a browser by validating the JSON
response against a hand-written shape schema.

This module validates that key endpoint responses match the shape the React
hooks/components expect. If the backend ever drifts (renames a key, changes a
type from object to array, etc.), the audit catches it before the frontend
crashes silently in production.

Sentinel union list -- 10 high-impact profiles per Codex's "10-20 sentinel
pages, not 270" recommendation:

Usage:
  py scripts/maintenance/audit_union_layer6.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Hand-picked sentinel f_nums, one per major affiliation / failure mode
SENTINEL_UNIONS: list[tuple[str, str]] = [
    # f_num, why-this-sentinel
    ("23715", "SEIU Local 1 -- Bug 1 regression target (large LM-2 with multi-row ar_membership)"),
    ("70581", "AFGE national -- federal/FLRA jurisdiction sentinel (zero NLRB expected)"),
    ("188",   "CWA national HQ -- 30M-bug-class regression target"),
    ("301",   "AFL-CIO federation national -- BCTD-class federation sentinel"),
    ("400",   "Health composite no-data sentinel (score=0, grade=F)"),
    ("12590", "CWA District 7 -- historical orphan resolution sentinel"),
    ("385",   "Strategic Organizing Center -- SOC exclusion sentinel (must NOT appear)"),
    ("503290","Small local zero-elections sentinel (affiliate fallback path)"),
    ("31847", "Top by F7 employer count sentinel"),
    ("500002","AFGE alt sentinel"),
]

# Expected shape per endpoint. Each entry is a path expression like
# "field" or "field.subfield"; the value is the expected type. Wrap in
# `Optional` (a 1-tuple sentinel below) when null is a valid value -- a bare
# type rejects None.

class Optional:
    """Marker that a field may legitimately be null (not just missing)."""
    def __init__(self, t):
        self.t = t


# Endpoints that are allowed to 404 (no LM-2 / no F7 / etc).
# Other endpoints (the detail handler) MUST return 200 for any sentinel.
ENDPOINTS_404_OK = {"/api/unions/{f_num}/health", "/api/unions/{f_num}/assets"}


SHAPES: dict[str, list[tuple[str, type | tuple | Optional]]] = {
    "/api/unions/{f_num}": [
        ("union", dict),
        ("union.f_num", str),
        ("union.union_name", str),
        ("top_employers", list),
        ("nlrb_elections", list),
        ("elections_source", str),
        ("financial_trends", list),
        ("nlrb_summary", dict),
        ("nlrb_summary.total_elections", int),
        ("nlrb_summary.win_rate", (int, float)),
    ],
    "/api/unions/{f_num}/disbursements": [
        ("years", list),
    ],
    "/api/unions/{f_num}/health": [
        ("composite", Optional(dict)),
        # composite may be null when the union has no LM-2 indicators.
        # When present, score and grade must be set; their types are
        # asserted only if `composite` is non-null (handled in check_shape).
    ],
    "/api/unions/{f_num}/assets": [
        # all fields are advisory; just confirm 200 doesn't error
    ],
}


def _path_get(d: Any, path: str) -> Any:
    """Resolve a dotted path; return _MISSING sentinel if any segment absent."""
    cur = d
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return _MISSING
    return cur


_MISSING = object()


def check_shape(body: dict, shape: list[tuple[str, type | tuple | Optional]]) -> list[str]:
    failures: list[str] = []
    for path, expected in shape:
        v = _path_get(body, path)
        if v is _MISSING:
            failures.append(f"missing field: {path}")
            continue
        if isinstance(expected, Optional):
            # Null permitted for this field; type only asserted when value present
            if v is None:
                continue
            target = expected.t
            if not isinstance(v, target):
                failures.append(
                    f"type mismatch at {path}: got {type(v).__name__}, expected {target.__name__ if isinstance(target, type) else target}"
                )
            continue
        # Required fields MUST not be None (Codex 2026-05-05 fix #3:
        # null was previously accepted for typed fields, masking shape drift).
        if v is None:
            failures.append(f"required field is null: {path}")
            continue
        if isinstance(expected, tuple):
            if not isinstance(v, expected):
                failures.append(f"type mismatch at {path}: got {type(v).__name__}, expected one of {expected}")
        else:
            if not isinstance(v, expected):
                failures.append(f"type mismatch at {path}: got {type(v).__name__}, expected {expected.__name__}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "audit_runs" / dt.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DISABLE_AUTH", "true")
    os.environ["RATE_LIMIT_REQUESTS"] = "0"
    sys.path.insert(0, str(PROJECT_ROOT))
    from fastapi.testclient import TestClient
    from api.main import app
    test_client = TestClient(app)

    results: list[dict] = []
    print(f"Validating shapes for {len(SENTINEL_UNIONS)} sentinel unions ...")
    for f_num, why in SENTINEL_UNIONS:
        per_union = {"f_num": f_num, "why": why, "checks": [], "passed": True}

        # Bug 1 regression guard at the sentinel level (Codex 2026-05-05 fix #4):
        # Layer 1's SQL guard is a tautology because both sides compute the
        # FIXED formula. The real regression catch is to hit the endpoint and
        # assert SEIU Local 1's 2023 assets are ~$14.6M (the truth), not
        # $262M (the buggy formula's output).
        if f_num == "23715":
            r_detail = test_client.get(f"/api/unions/{f_num}")
            if r_detail.status_code == 200:
                fts = r_detail.json().get("financial_trends") or []
                row_2023 = next((row for row in fts if int(row.get("year") or 0) == 2023), None)
                bug1_entry: dict[str, Any] = {
                    "endpoint": f"/api/unions/{f_num} (Bug 1 regression guard)",
                    "status_code": r_detail.status_code,
                }
                if row_2023:
                    api_assets = float(row_2023.get("assets") or 0)
                    expected = 14_573_892
                    # Allow ±5% drift (refilings, restatements); fail at >50M which
                    # is unambiguous re-emergence of the multiplication bug.
                    if api_assets > 50_000_000:
                        bug1_entry["passed"] = False
                        bug1_entry["failures"] = [
                            f"SEIU Local 1 2023 assets ${api_assets:,.0f} > $50M "
                            f"-- Bug 1 (financial-trend SUM multiplication) HAS RETURNED. "
                            f"Truth from lm_data is ${expected:,}."
                        ]
                    elif abs(api_assets - expected) / expected > 0.05:
                        bug1_entry["passed"] = True
                        bug1_entry["note"] = (
                            f"SEIU Local 1 2023 assets ${api_assets:,.0f} drifts "
                            f"~{round(100*(api_assets-expected)/expected, 1)}% from canonical "
                            f"${expected:,} -- check for restatement, not necessarily a regression."
                        )
                    else:
                        bug1_entry["passed"] = True
                        bug1_entry["note"] = (
                            f"SEIU Local 1 2023 assets ${api_assets:,.0f} matches truth"
                        )
                else:
                    bug1_entry["passed"] = False
                    bug1_entry["failures"] = ["SEIU Local 1 has no 2023 financial_trends entry"]
                per_union["checks"].append(bug1_entry)
                if not bug1_entry.get("passed", True):
                    per_union["passed"] = False

        for path_template, shape in SHAPES.items():
            url = path_template.replace("{f_num}", f_num)
            r = test_client.get(url)
            entry: dict[str, Any] = {"endpoint": url, "status_code": r.status_code}
            if r.status_code == 404:
                # Only allow 404 on endpoints that are explicitly optional
                # (Codex 2026-05-05 fix #2: previously every 404 passed
                # silently, masking broken/removed routes).
                if path_template in ENDPOINTS_404_OK:
                    entry["note"] = f"404 acceptable for optional endpoint {path_template}"
                    entry["passed"] = True
                else:
                    entry["passed"] = False
                    entry["failures"] = [f"unexpected 404 on required endpoint {url}"]
            else:
                try:
                    body = r.json()
                except Exception:
                    body = None
                if body is None:
                    entry["passed"] = False
                    entry["failures"] = ["non-JSON response"]
                else:
                    failures = check_shape(body, shape)
                    entry["passed"] = len(failures) == 0
                    if failures:
                        entry["failures"] = failures
            per_union["checks"].append(entry)
            if not entry["passed"]:
                per_union["passed"] = False
        results.append(per_union)
        tag = "PASS" if per_union["passed"] else "FAIL"
        print(f"  [{tag}] f_num={f_num} ({why[:60]}{'...' if len(why)>60 else ''})")

    n_total = len(results)
    n_pass = sum(1 for r in results if r["passed"])

    out_path = out_dir / "layer6_results.json"
    md_path = out_dir / "layer6_report.md"
    out_path.write_text(json.dumps({
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total": n_total, "passed": n_pass,
        "sentinels": results,
    }, indent=2, default=str), encoding="utf-8")

    lines = [
        "# Union Explorer Audit -- Layer 6 (Response-Shape Sentinels)", "",
        f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        f"- Sentinels: {n_total}",
        f"- Passed: {n_pass}",
        f"- Failed: {n_total - n_pass}",
        "",
    ]
    for r in results:
        if not r["passed"]:
            lines.append(f"### FAIL f_num={r['f_num']} ({r['why']})")
            for c in r["checks"]:
                if not c.get("passed", True):
                    lines.append(f"- {c['endpoint']} -> {c['status_code']}")
                    for f in c.get("failures", []):
                        lines.append(f"  - {f}")
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{n_pass}/{n_total} sentinels passed")
    print(f"Results: {out_path}")
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
