"""
Verify the F7 orphan rate has not regressed beyond the configured threshold.

The F7 orphan rate is the share of f7_employers_deduped rows that have no
active match in unified_match_log. It's the single best leading indicator
that the matching pipeline has decayed -- a regression here cascades into
empty scorecard signals, sparse comparables, and degraded similarity.

Background:
- R6 baseline (2026-03): 64.7% orphan
- R7 audit (2026-04-25): 67.4% orphan (alarming +2.7pp regression)
- 2026-04-30: 68.1% (continued worsening, attributed to Splink retirement)
- 2026-05-03 PM (post 990 + SAM rematch): 65.18% (-2.92pp recovery)
- 2026-05-04: 65.18% (steady)

This check enforces a CEILING (default 67.0%, ~2.3pp slack above the R6
baseline) so a regression that pushes back toward R7-era orphan levels
fails the deploy gate before the data goes live. Per the F7 Orphan Rate
Open Problem (recommendation #5).

Usage:
    py scripts/maintenance/check_orphan_rate.py
    py scripts/maintenance/check_orphan_rate.py --max-orphan-pct 65.5
    py scripts/maintenance/check_orphan_rate.py --json

Exit codes:
    0  Orphan rate at or below threshold.
    1  Orphan rate exceeds threshold (release-blocking).
    2  Could not query the database.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make project root importable so db_config resolves regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from db_config import get_connection
except Exception as exc:  # pragma: no cover - import-time failure
    print(f"ERROR: cannot import db_config: {exc}", file=sys.stderr)
    sys.exit(2)


# Default ceiling: 67.0% — chosen as the R7-era regression number. Pushing
# above this would mean we've slid back to R7 baseline. The R6 baseline is
# 64.7%; the 2.3pp slack accommodates legitimate noise and one-off
# source-driven swings.
DEFAULT_MAX_ORPHAN_PCT = 67.0


def measure_orphan_rate() -> tuple[int, int, float]:
    """Returns (total_f7, matched_count, orphan_pct).

    `matched` counts F7 rows that have an active UML match -- not just
    `COUNT(DISTINCT target_id)` from unified_match_log, which would
    include dangling target_ids (rows pointing at f7_employer_ids that
    no longer exist in f7_employers_deduped). Dangling rows would
    artificially lower the reported orphan rate and could let a real
    regression slip past the deploy gate.
    (Codex finding 2026-05-04, fixed same day.)
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM f7_employers_deduped) AS total,
              (SELECT COUNT(*) FROM f7_employers_deduped f
               WHERE EXISTS (
                 SELECT 1 FROM unified_match_log uml
                 WHERE uml.target_system = 'f7'
                   AND uml.status = 'active'
                   AND uml.target_id = f.employer_id
               )) AS matched
            """
        )
        row = cur.fetchone()
    finally:
        conn.close()
    # Cursor mode varies (dict vs tuple); accept both
    if isinstance(row, dict):
        total, matched = int(row["total"] or 0), int(row["matched"] or 0)
    else:
        total, matched = int(row[0] or 0), int(row[1] or 0)
    if total == 0:
        return 0, 0, 0.0
    orphan = total - matched
    pct = 100.0 * orphan / total
    return total, matched, pct


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--max-orphan-pct",
        type=float,
        default=float(os.environ.get("MAX_ORPHAN_PCT", DEFAULT_MAX_ORPHAN_PCT)),
        help=f"Fail if orphan pct exceeds this (default: {DEFAULT_MAX_ORPHAN_PCT})",
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit a single-line JSON object instead of human text")
    args = parser.parse_args()

    try:
        total, matched, pct = measure_orphan_rate()
    except Exception as exc:
        print(f"ERROR: could not measure orphan rate: {exc}", file=sys.stderr)
        return 2

    orphan_count = total - matched
    is_failure = pct > args.max_orphan_pct
    status = "FAIL" if is_failure else "OK"

    if args.json:
        out = {
            "status": status,
            "total_f7": total,
            "matched": matched,
            "orphans": orphan_count,
            "orphan_pct": round(pct, 2),
            "max_allowed_pct": args.max_orphan_pct,
        }
        print(json.dumps(out))
    else:
        print(f"F7 orphan-rate check (ceiling: {args.max_orphan_pct:.1f}%)")
        print(f"  Total F7: {total:,}")
        print(f"  Matched: {matched:,}")
        print(f"  Orphans: {orphan_count:,} ({pct:.2f}%)")
        print()
        if is_failure:
            print(
                f"  {status}: orphan rate {pct:.2f}% exceeds ceiling "
                f"{args.max_orphan_pct:.1f}%",
                file=sys.stderr,
            )
            print(
                "  Likely causes: a matching method was deactivated without a "
                "replacement, or new F7 rows were loaded without re-running the "
                "deterministic cascade. See: "
                "Open Problems/F7 Orphan Rate Regression.md.",
                file=sys.stderr,
            )
        else:
            slack = args.max_orphan_pct - pct
            print(
                f"  {status}: {slack:.2f}pp of slack below ceiling. "
                f"Reference: R6 baseline 64.7%, 2026-05-04 actual {pct:.2f}%."
            )

    return 1 if is_failure else 0


if __name__ == "__main__":
    sys.exit(main())
