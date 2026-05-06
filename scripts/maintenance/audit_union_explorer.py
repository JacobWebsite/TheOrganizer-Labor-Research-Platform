"""Union Explorer Audit -- Master Orchestrator.

Runs all 5 audit layers in dependency order and emits a single aggregate
report. Layer ordering per Codex review 2026-05-04:

  Layer 1 (truth_queries)     hard gate -- if hard checks fail, layers 2+ may
                              still run for diagnostic purposes but harness
                              exits non-zero.
  Layer 2 (api_db_consistency) per-union API <-> DB diff
  Layer 3 (cross_source)        aggregate linkage metrics (computed inside L2)
  Layer 4 (deepseek_rubric)     advisory; defaults to dry-run; explicit
                                opt-in for paid runs.
  Layer 5 (anomaly_set)         frozen + re-derived + diff vs prior run
  Layer 6 (sentinel_shapes)     response-shape regression for 10 hand-picked
                                union profiles

Output:
  audit_runs/<DATE>/
    layer1_results.json + layer1_report.md
    layer2_per_union.json + layer2_layer3.json + layer2_report.md
    layer4_results.json + layer4_report.md   (only if --include-llm)
    layer5_anomaly_set.json + layer5_unexplained.json + layer5_diff.json + layer5_report.md
    layer6_results.json + layer6_report.md
    audit_summary.md          <-- aggregate of all layers, top-of-funnel
    auto_problems.md          <-- stubs for new Open Problem notes

Usage:
  py scripts/maintenance/audit_union_explorer.py             # all deterministic layers
  py scripts/maintenance/audit_union_explorer.py --include-llm           # add Layer 4 (paid)
  py scripts/maintenance/audit_union_explorer.py --skip-layer 2          # skip a layer
  py scripts/maintenance/audit_union_explorer.py --quick                 # small sample, fast
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

LAYER_SCRIPTS = {
    1: "audit_union_layer1.py",
    2: "audit_union_layer2.py",
    4: "audit_union_layer4.py",
    5: "audit_union_layer5.py",
    6: "audit_union_layer6.py",
}


def run_layer(layer_num: int, extra_args: list[str], output_dir: Path) -> tuple[int, float]:
    script = HERE / LAYER_SCRIPTS[layer_num]
    cmd = [sys.executable, str(script), "--output-dir", str(output_dir)] + extra_args
    print(f"\n{'=' * 60}")
    print(f"Layer {layer_num}: {' '.join(cmd[2:])}")
    print(f"{'=' * 60}")
    started = time.perf_counter()
    rc = subprocess.run(cmd, cwd=PROJECT_ROOT).returncode
    elapsed = time.perf_counter() - started
    return rc, elapsed


def write_aggregate_report(output_dir: Path, layer_results: dict[int, dict]) -> None:
    md = output_dir / "audit_summary.md"
    lines = [
        "# Union Explorer Audit -- Aggregate Summary",
        "",
        f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Layer execution",
        "",
        "| Layer | Status | Elapsed | Output |",
        "|-------|--------|--------:|--------|",
    ]
    for layer_num in sorted(layer_results):
        r = layer_results[layer_num]
        status = "PASS" if r["return_code"] == 0 else f"FAIL (rc={r['return_code']})"
        skipped = r.get("skipped")
        if skipped:
            status = "SKIPPED"
        lines.append(
            f"| {layer_num} | {status} | {r.get('elapsed_sec', 0):.1f}s | {r.get('files', '')} |"
        )
    lines.append("")

    # Pull headline numbers from each layer's JSON output if available
    if (output_dir / "layer1_results.json").is_file():
        d = json.loads((output_dir / "layer1_results.json").read_text(encoding="utf-8"))
        s = d.get("summary", {})
        lines.append("## Layer 1 -- Truth queries")
        lines.append("")
        lines.append(
            f"- {s.get('passed', 0)}/{s.get('total', 0)} pass -- "
            f"{s.get('hard_failures', 0)} hard failure(s), "
            f"{s.get('advisory_failures', 0)} advisory failure(s)"
        )
        lines.append("")

    if (output_dir / "layer2_per_union.json").is_file():
        d = json.loads((output_dir / "layer2_per_union.json").read_text(encoding="utf-8"))
        s = d.get("summary", {})
        lines.append("## Layer 2 -- API <-> DB consistency")
        lines.append("")
        lines.append(
            f"- {s.get('passed', 0)}/{s.get('total_checks', 0)} checks pass "
            f"({round(100*s.get('passed', 0)/max(s.get('total_checks', 1), 1), 1)}%)"
        )
        lines.append(f"- Distinct unions audited: {s.get('distinct_unions_audited', '?')}")
        lines.append(f"- Affiliations audited: {s.get('affiliations_audited', '?')}")
        lines.append(f"- Hard failures: {s.get('hard_failures', '?')}")
        lines.append("")

    if (output_dir / "layer2_layer3.json").is_file():
        l3 = json.loads((output_dir / "layer2_layer3.json").read_text(encoding="utf-8"))
        lines.append("## Layer 3 -- Cross-source linkage")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(l3, indent=2, default=str))
        lines.append("```")
        lines.append("")

    if (output_dir / "layer4_results.json").is_file():
        d = json.loads((output_dir / "layer4_results.json").read_text(encoding="utf-8"))
        s = d.get("summary", {})
        lines.append("## Layer 4 -- DeepSeek advisory rubric")
        lines.append("")
        lines.append(
            f"- {s.get('n_valid_rubrics', 0)}/{s.get('n_calls', 0)} valid rubrics"
        )
        lines.append(
            f"- Avg dimension score: {s.get('average_dimension_score', '?')}"
        )
        lines.append(f"- Cumulative cost: ${s.get('cumulative_cost_usd', 0)}")
        lines.append("")

    if (output_dir / "layer5_anomaly_set.json").is_file():
        d = json.loads((output_dir / "layer5_anomaly_set.json").read_text(encoding="utf-8"))
        lines.append("## Layer 5 -- Anomaly set")
        lines.append("")
        for cat, rows in d.get("anomalies", {}).items():
            n = len([r for r in rows if "_error" not in r])
            lines.append(f"- {cat}: {n}")
        lines.append("")

    if (output_dir / "layer6_results.json").is_file():
        d = json.loads((output_dir / "layer6_results.json").read_text(encoding="utf-8"))
        lines.append("## Layer 6 -- Response-shape sentinels")
        lines.append("")
        lines.append(f"- {d.get('passed', 0)}/{d.get('total', 0)} sentinels pass")
        lines.append("")

    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nAggregate summary written to: {md}")


def write_auto_problems(output_dir: Path) -> None:
    """Generate Open Problem stubs for systematic failures discovered."""
    stubs: list[dict] = []
    if (output_dir / "layer1_results.json").is_file():
        d = json.loads((output_dir / "layer1_results.json").read_text(encoding="utf-8"))
        for c in d.get("checks", []):
            if not c.get("passed") and c.get("gate") == "hard":
                stubs.append({
                    "title": f"Layer 1 hard failure: {c['name']}",
                    "description": c.get("description"),
                    "row_count": c.get("row_count"),
                    "sample": c.get("rows_sample"),
                })
    if (output_dir / "layer2_per_union.json").is_file():
        d = json.loads((output_dir / "layer2_per_union.json").read_text(encoding="utf-8"))
        # Group hard failures by check_name
        by_check: dict[str, int] = {}
        for c in d.get("checks", []):
            if not c.get("passed") and c.get("gate") == "hard":
                by_check[c["check"]] = by_check.get(c["check"], 0) + 1
        for check, n in by_check.items():
            if n >= 3:  # systematic failure threshold
                stubs.append({
                    "title": f"Layer 2 systematic failure: {check}",
                    "description": f"{n} unions failed this hard-gate check",
                })

    if not stubs:
        return
    out = output_dir / "auto_problems.md"
    lines = [
        "# Auto-generated Open Problem candidates",
        "",
        f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "Each entry below is a candidate for an [[Open Problems/]] note in the vault. "
        "Review, write up properly, and link to the audit run.",
        "",
    ]
    for i, stub in enumerate(stubs, 1):
        lines.append(f"## {i}. {stub['title']}")
        if stub.get("description"):
            lines.append(f"- {stub['description']}")
        if stub.get("row_count") is not None:
            lines.append(f"- row_count: {stub['row_count']}")
        if stub.get("sample"):
            lines.append("- sample:")
            for s in stub["sample"][:3]:
                lines.append(f"  - `{json.dumps(s, default=str)}`")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Auto-problem stubs written to: {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-llm", action="store_true",
                    help="Include Layer 4 DeepSeek paid run (default: skipped)")
    ap.add_argument("--llm-max-cost-usd", type=float, default=2.0)
    ap.add_argument("--skip-layer", type=int, action="append", default=[])
    ap.add_argument("--quick", action="store_true",
                    help="Use smaller samples (Layer 2 sample-size=30)")
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "audit_runs" / dt.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    layer_results: dict[int, dict] = {}
    layers_to_run = [1, 2, 4, 5, 6]
    if not args.include_llm:
        if 4 not in args.skip_layer:
            args.skip_layer.append(4)

    for layer_num in layers_to_run:
        if layer_num in args.skip_layer:
            layer_results[layer_num] = {"return_code": 0, "elapsed_sec": 0, "skipped": True}
            print(f"\n--- Skipping Layer {layer_num} ---")
            continue
        extra: list[str] = []
        if layer_num == 2 and args.quick:
            extra += ["--sample-size", "30"]
        if layer_num == 2:
            extra += ["--mode", "asgi", "--no-fail-on-hard"]
        if layer_num == 4:
            extra += ["--max-cost-usd", str(args.llm_max_cost_usd)]
        # Layer 1 must NOT have --no-fail-on-hard; hard checks block release.
        # (Codex review 2026-05-05: contradicts the harness's own contract
        # if Layer 1 reports hard failures but exits 0.)
        rc, elapsed = run_layer(layer_num, extra, out_dir)
        layer_results[layer_num] = {"return_code": rc, "elapsed_sec": elapsed}

    write_aggregate_report(out_dir, layer_results)
    write_auto_problems(out_dir)

    # Hard-fail logic: if any layer with rc!=0 (excluding Layer 4 advisory)
    # the master returns rc=1 to signal release-blocking failures.
    hard_blocking = [n for n, r in layer_results.items()
                     if r["return_code"] != 0 and n in (1, 6)]
    if hard_blocking:
        print(f"\nRELEASE-BLOCKING failures in layers: {hard_blocking}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
