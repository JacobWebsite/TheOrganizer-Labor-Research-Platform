"""
A/B test: iterative critique loop (3 rounds) vs single-pass (1 round).

The iterative critique refactor (Session 2026-04-21) was verified for
correctness + atomicity but not for *quality uplift*. This script picks
5 small employers, runs each one twice (RESEARCH_CRITIQUE_ROUNDS=1 vs
RESEARCH_CRITIQUE_ROUND=3), and writes a comparison report to
`Research/Iterative Critique Loop A-B Test 2026-04.md`.

Cost estimate: ~$5-10 across 10 total Gemini runs. Pre-approved in the
2026-04-24 plan scope.

Safeguards:
- `--dry-run` (default) just prints the plan -- no Gemini calls.
- `--commit` actually fires the 10 runs.
- Each run writes to `research_runs` with a distinctive `triggered_by`
  tag (`ab_test_critique_r1` / `ab_test_critique_r3`) so we can find
  them again without cluttering real runs.
- Re-runs are safe: duplicate tags are OK.

Usage:
    py scripts/research/ab_test_critique_loop.py --dry-run
    py scripts/research/ab_test_critique_loop.py --commit
    py scripts/research/ab_test_critique_loop.py --commit --employers "Acme Inc" "Widget Co"

Verification after a committed run:
    SELECT triggered_by,
           COUNT(*) AS runs,
           AVG(overall_quality_score) AS avg_q,
           AVG(sections_filled) AS avg_sec,
           AVG(total_facts_found) AS avg_facts,
           AVG(total_cost_cents) AS avg_cents,
           AVG(duration_seconds) AS avg_secs
    FROM research_runs
    WHERE triggered_by IN ('ab_test_critique_r1', 'ab_test_critique_r3')
    GROUP BY triggered_by;
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection

_log = logging.getLogger("ab_test_critique")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# 5 default employers spanning archetypes. Small/private preferred so
# Gemini has real gaps to chase via the critique loop.
DEFAULT_EMPLOYERS = [
    ("Cinelease Inc", "NJ"),
    ("Graceland Fruit, Inc.", "MI"),
    ("Wells Nursing Home, Inc.", "NY"),
    ("Country Visions Cooperative", "WI"),
    ("MAPLE SPRINGS LAUNDRY, LLC", "NC"),
]

REPORT_PATH = Path(
    r"C:\Users\jakew\LaborDataTerminal\LaborDataTerminal_real\Research"
    r"\Iterative Critique Loop A-B Test 2026-04.md"
)


def _queue_run(company: str, state: str, triggered_by: str) -> int:
    """Insert a new research_runs row and return its id."""
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO research_runs (company_name, company_state, status, triggered_by)
        VALUES (%s, %s, 'pending', %s)
        RETURNING id
        """,
        (company, state, triggered_by),
    )
    run_id = cur.fetchone()[0]
    conn.close()
    return run_id


def _execute(run_id: int, rounds: int) -> dict:
    """Invoke the research agent on an existing run_id with the specified
    critique-rounds setting. Returns the last-seen row after completion.

    Codex finding #5 (2026-04-24): previously this returned zero-valued
    metrics when the subprocess failed or the row was still pending,
    which silently poisoned the A/B averages. Now we mark failed or
    non-completed runs with `failed=True` and `_summarize()` drops them
    from the per-arm averages + reports the failure count separately.
    """
    env = os.environ.copy()
    env["RESEARCH_CRITIQUE_ROUNDS"] = str(rounds)
    env["PYTHONPATH"] = str(ROOT)

    subprocess_failed = False
    subprocess_rc = None

    # Subprocess the agent so we can swap env per run without interfering
    # with other in-process state.
    try:
        proc = subprocess.run(
            ["py", "-m", "scripts.research.agent", "--run-id", str(run_id)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,  # 20 min cap per run
        )
        subprocess_rc = proc.returncode
        if proc.returncode != 0:
            subprocess_failed = True
            _log.warning("agent subprocess returned %d; stderr head: %s",
                         proc.returncode, (proc.stderr or "")[-500:])
    except subprocess.TimeoutExpired as exc:
        subprocess_failed = True
        subprocess_rc = -1
        _log.warning("agent subprocess timed out for run_id=%d: %s", run_id, exc)

    # Pull the completed row
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, status, overall_quality_score, sections_filled,
               total_facts_found, total_cost_cents, duration_seconds,
               total_tools_called
        FROM research_runs WHERE id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    conn.close()

    status = row[1] if row else None
    # A run is "usable" for A/B stats only if the subprocess exited 0 AND
    # the DB row reached terminal 'completed' state. Anything else gets
    # dropped from the averages.
    usable = (not subprocess_failed) and (status == "completed")

    return {
        "run_id": row[0] if row else run_id,
        "status": status,
        "usable": usable,
        "subprocess_rc": subprocess_rc,
        "quality": float(row[2] or 0) if row else 0.0,
        "sections": row[3] or 0 if row else 0,
        "facts": row[4] or 0 if row else 0,
        "cents": row[5] or 0 if row else 0,
        "duration": row[6] or 0 if row else 0,
        "tools": row[7] or 0 if row else 0,
    }


def _summarize(runs_r1: list[dict], runs_r3: list[dict]) -> dict:
    """Simple per-arm averages + paired deltas. Drops non-usable runs
    (subprocess failures / still-pending / errored DB rows) from the
    averages and reports their counts separately so readers can tell a
    real quality delta from noise caused by half-broken runs."""
    def avg(key, rows):
        usable_rows = [r for r in rows if r.get("usable")]
        vals = [r[key] for r in usable_rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    return {
        "r1_avg": {k: avg(k, runs_r1) for k in ("quality", "sections", "facts", "cents", "duration", "tools")},
        "r3_avg": {k: avg(k, runs_r3) for k in ("quality", "sections", "facts", "cents", "duration", "tools")},
        "r1_count": len(runs_r1),
        "r3_count": len(runs_r3),
        "r1_usable": sum(1 for r in runs_r1 if r.get("usable")),
        "r3_usable": sum(1 for r in runs_r3 if r.get("usable")),
        "r1_failed": sum(1 for r in runs_r1 if not r.get("usable")),
        "r3_failed": sum(1 for r in runs_r3 if not r.get("usable")),
    }


def _write_report(employers: list[tuple[str, str]], runs_r1: list[dict],
                  runs_r3: list[dict], summary: dict, report_path: Path):
    """Emit a Markdown report into the vault Research/ folder."""
    lines = [
        "# Iterative Critique Loop A/B Test (2026-04)",
        "",
        "## Setup",
        "",
        f"- **Employers tested:** {len(employers)}",
        "- **Arm A:** `RESEARCH_CRITIQUE_ROUNDS=1` (single-pass, pre-refactor behavior)",
        "- **Arm B:** `RESEARCH_CRITIQUE_ROUNDS=3` (iterative, post-2026-04-21 refactor)",
        "- **Metric priority:** overall_quality_score > total_facts_found > sections_filled",
        "",
        "## Per-employer runs",
        "",
        "| Employer | State | Arm | run_id | status | quality | sections | facts | cents | duration | tools |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (name, st), r1, r3 in zip(employers, runs_r1, runs_r3):
        lines.append(
            f"| {name} | {st} | R=1 | {r1['run_id']} | {r1['status']} | {r1['quality']} | "
            f"{r1['sections']} | {r1['facts']} | {r1['cents']} | {r1['duration']}s | {r1['tools']} |"
        )
        lines.append(
            f"| {name} | {st} | R=3 | {r3['run_id']} | {r3['status']} | {r3['quality']} | "
            f"{r3['sections']} | {r3['facts']} | {r3['cents']} | {r3['duration']}s | {r3['tools']} |"
        )

    lines += [
        "",
        "## Summary",
        "",
        f"- **Arm A (R=1) usable runs:** {summary['r1_usable']} / {summary['r1_count']} "
        f"({summary['r1_failed']} dropped as failed/pending)",
        f"- **Arm B (R=3) usable runs:** {summary['r3_usable']} / {summary['r3_count']} "
        f"({summary['r3_failed']} dropped as failed/pending)",
        "",
        "Averages below include only usable runs (subprocess exit 0 + DB row `status='completed'`).",
        "",
        "| Metric | Arm A (R=1) | Arm B (R=3) | Delta |",
        "|---|---|---|---|",
    ]
    for k in ("quality", "sections", "facts", "cents", "duration", "tools"):
        a = summary["r1_avg"][k]
        b = summary["r3_avg"][k]
        delta = round(b - a, 3)
        sign = "+" if delta > 0 else ""
        lines.append(f"| {k} | {a} | {b} | {sign}{delta} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "- A positive `quality` delta confirms the iterative loop is earning its keep.",
        "- A `facts` delta > 3 per run suggests the follow-up tools are filling real gaps.",
        "- `cents` and `duration` deltas are the cost of the extra rounds; compare vs the",
        "  quality lift to decide the production default.",
        "- If `quality` delta is near zero but `facts` delta is substantial, the current",
        "  scoring may not be weighting critique-surfaced facts correctly -- worth a",
        "  separate investigation.",
    ]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    _log.info("wrote report -> %s", report_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="Actually run the 10 Gemini calls (~$5-10).")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only (default).")
    ap.add_argument("--employers", nargs="*", help="Override default 5 employers (space-separated names).")
    args = ap.parse_args()

    employers = DEFAULT_EMPLOYERS
    if args.employers:
        # If user passes custom names, we assume state is unknown
        employers = [(n, None) for n in args.employers]

    _log.info("A/B test plan: %d employers x 2 arms = %d Gemini runs", len(employers), len(employers) * 2)
    for name, st in employers:
        _log.info("  - %s (%s)", name, st or "unknown")

    if args.dry_run or not args.commit:
        _log.info("DRY-RUN (no Gemini calls will be made). Use --commit to execute.")
        print(json.dumps({
            "dry_run": True,
            "employer_count": len(employers),
            "arms": ["R=1", "R=3"],
            "expected_runs": len(employers) * 2,
            "report_path": str(REPORT_PATH),
        }, indent=2))
        return

    # Live path: queue + execute each run twice
    runs_r1: list[dict] = []
    runs_r3: list[dict] = []
    for name, st in employers:
        for rounds, tag, out in [
            (1, "ab_test_critique_r1", runs_r1),
            (3, "ab_test_critique_r3", runs_r3),
        ]:
            run_id = _queue_run(name, st or "", tag)
            _log.info("queued run_id=%d for %s (R=%d)", run_id, name, rounds)
            result = _execute(run_id, rounds)
            _log.info("  -> %s", result)
            out.append(result)
            time.sleep(2)  # gentle pacing

    summary = _summarize(runs_r1, runs_r3)
    _log.info("summary: %s", json.dumps(summary, indent=2))
    _write_report(employers, runs_r1, runs_r3, summary, REPORT_PATH)


if __name__ == "__main__":
    main()
