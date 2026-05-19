"""
list_dossiers_needing_review.py
================================

Emit a CSV (or TSV) of research dossiers that need a human review pass, sorted
so the highest-impact reviews float to the top. Designed for a weekly manual
sweep when the frontend review UI is not being used.

Why this exists
---------------
As of 2026-05-12 the research agent has produced 192 completed runs with 6,348
extracted facts, but only 1 fact has been human-reviewed. All technical
infrastructure for review is in place (DB columns, API endpoints, frontend
components), but adoption has stalled. The smallest fix that makes review
possible in a manual end-of-week pass is this script -- it surfaces the
specific dossiers that would benefit most from human attention, with the
information needed to act on them.

Usage
-----
    # Default: top 20 highest-quality unreviewed runs, CSV to stdout
    py scripts/research/list_dossiers_needing_review.py

    # Write to a file
    py scripts/research/list_dossiers_needing_review.py \\
        --out files/review_queue_2026_05_12.csv

    # Wider net: include medium-quality runs (5.0-6.9)
    py scripts/research/list_dossiers_needing_review.py --min-quality 5.0

    # Focus on a section
    py scripts/research/list_dossiers_needing_review.py --priority contradictions

    # Limit to 50 rows, tab-separated for spreadsheet paste
    py scripts/research/list_dossiers_needing_review.py --limit 50 --tsv

Priority modes
--------------
- highest_quality (default): runs with the strongest auto-grade score first;
  these are the dossiers where review yields the best ROI on score enhancement.
- contradictions: runs with the most internal contradictions; review unlocks
  the consistency-score deductions.
- gold_standard: runs already flagged is_gold_standard = TRUE; canonical
  starting point for a calibration pass.
- most_facts: runs with the most extracted facts but lowest review coverage.
- recent: most recent runs first.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Make the project root importable when invoked as a script.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection
from psycopg2.extras import RealDictCursor

_log = logging.getLogger("list_dossiers_needing_review")

# Columns emitted in the CSV. Tuned for a spreadsheet review workflow:
# the first columns identify the run, the middle columns convey priority,
# and the last column is a deep link to the frontend review page.
CSV_COLUMNS = [
    "run_id",
    "employer_id",
    "company_name",
    "company_state",
    "company_type",
    "industry_naics",
    "completed_at",
    "overall_quality_score",
    "is_gold_standard",
    "total_facts_found",
    "facts_reviewed",
    "facts_unreviewed",
    "contradiction_count",
    "low_confidence_count",
    "web_numeric_count",
    "priority_facts_url",
    "frontend_review_url",
]

# The frontend mounts research review at this path (see
# frontend/src/features/research/). Adjust here if that ever changes.
FRONTEND_BASE = "http://localhost:5173"


def _build_query(
    min_quality: float,
    priority: str,
    limit: int,
    gold_only: bool,
) -> tuple[str, tuple]:
    """Compose the SQL based on the requested priority ordering.

    Returns (sql, params).
    """
    # Common projection: per-run rollups computed once via LEFT JOIN LATERAL
    # subqueries. We avoid a self-join on research_facts so the per-row
    # counts stay accurate even when a run has zero facts.
    base = """
        WITH run_facts AS (
            SELECT
                f.run_id,
                COUNT(*) AS total_facts,
                COUNT(*) FILTER (WHERE f.human_verdict IS NOT NULL) AS reviewed,
                COUNT(*) FILTER (WHERE f.human_verdict IS NULL) AS unreviewed,
                COUNT(*) FILTER (WHERE f.contradicts_fact_id IS NOT NULL) AS contradictions,
                COUNT(*) FILTER (WHERE f.confidence IS NOT NULL AND f.confidence < 0.5) AS low_conf,
                COUNT(*) FILTER (
                    WHERE f.source_type IN ('web_scrape', 'web_search')
                      AND f.attribute_value ~ '^[0-9]'
                ) AS web_numeric
            FROM research_facts f
            GROUP BY f.run_id
        )
        SELECT
            r.id AS run_id,
            r.employer_id,
            r.company_name,
            r.company_state,
            r.company_type,
            r.industry_naics,
            r.completed_at,
            r.overall_quality_score,
            COALESCE(r.is_gold_standard, FALSE) AS is_gold_standard,
            r.total_facts_found,
            COALESCE(rf.reviewed, 0) AS facts_reviewed,
            COALESCE(rf.unreviewed, 0) AS facts_unreviewed,
            COALESCE(rf.contradictions, 0) AS contradiction_count,
            COALESCE(rf.low_conf, 0) AS low_confidence_count,
            COALESCE(rf.web_numeric, 0) AS web_numeric_count
        FROM research_runs r
        LEFT JOIN run_facts rf ON rf.run_id = r.id
        WHERE r.status = 'completed'
          AND r.overall_quality_score >= %s
          AND COALESCE(rf.unreviewed, 0) > 0
    """

    params: list = [min_quality]

    if gold_only:
        base += " AND r.is_gold_standard = TRUE"

    # Order clauses tuned to put the most review-worthy runs on top.
    order_map = {
        "highest_quality": (
            "r.overall_quality_score DESC NULLS LAST, "
            "COALESCE(rf.unreviewed, 0) DESC, "
            "r.completed_at DESC"
        ),
        "contradictions": (
            "COALESCE(rf.contradictions, 0) DESC, "
            "r.overall_quality_score DESC NULLS LAST, "
            "r.completed_at DESC"
        ),
        "gold_standard": (
            # is_gold_standard already filtered above when gold_only; this
            # ordering still works for the non-filtered "prefer gold" case.
            "COALESCE(r.is_gold_standard, FALSE) DESC, "
            "r.overall_quality_score DESC NULLS LAST, "
            "r.completed_at DESC"
        ),
        "most_facts": (
            "COALESCE(rf.unreviewed, 0) DESC, "
            "r.overall_quality_score DESC NULLS LAST"
        ),
        "recent": "r.completed_at DESC NULLS LAST",
    }
    order_clause = order_map.get(priority, order_map["highest_quality"])

    sql = base + f" ORDER BY {order_clause} LIMIT %s"
    params.append(limit)
    return sql, tuple(params)


def query_dossiers_needing_review(
    min_quality: float = 6.0,
    priority: str = "highest_quality",
    limit: int = 20,
    gold_only: bool = False,
    conn=None,
) -> list[dict]:
    """Return a list of dossier rows in priority order.

    Each row is a dict with the CSV_COLUMNS keys (frontend URLs added).
    Tests can pass a mock connection to avoid touching the real DB.
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor()
        sql, params = _build_query(min_quality, priority, limit, gold_only)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            # Prepend the deep links so reviewers can click straight into the UI
            # or query the API for priority facts.
            run_id = row["run_id"]
            row["priority_facts_url"] = (
                f"{FRONTEND_BASE}/api/research/runs/{run_id}/priority-facts"
            )
            row["frontend_review_url"] = (
                f"{FRONTEND_BASE}/research/runs/{run_id}"
            )
        return rows
    finally:
        if close_conn:
            conn.close()


def write_csv(rows: list[dict], out_path: Optional[Path], tsv: bool = False) -> None:
    """Emit the rows as CSV (or TSV) either to out_path or stdout."""
    delimiter = "\t" if tsv else ","

    stream = open(out_path, "w", newline="", encoding="utf-8") if out_path else sys.stdout
    try:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, delimiter=delimiter)
        writer.writeheader()
        for row in rows:
            # csv.DictWriter expects every key in fieldnames to exist
            # (missing keys would raise). Fill any absent ones with "".
            clean = {col: row.get(col, "") for col in CSV_COLUMNS}
            # Format datetimes/booleans as plain strings.
            if isinstance(clean.get("completed_at"), datetime):
                clean["completed_at"] = clean["completed_at"].isoformat(timespec="seconds")
            writer.writerow(clean)
    finally:
        if out_path and stream is not sys.stdout:
            stream.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-quality",
        type=float,
        default=6.0,
        help="Minimum overall_quality_score to include (default 6.0 = dual-gate cutoff)",
    )
    parser.add_argument(
        "--priority",
        choices=["highest_quality", "contradictions", "gold_standard", "most_facts", "recent"],
        default="highest_quality",
        help="How to sort the review queue (default highest_quality)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum rows to emit (default 20)",
    )
    parser.add_argument(
        "--gold-only",
        action="store_true",
        help="Only include runs flagged is_gold_standard = TRUE",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output file path (default stdout)",
    )
    parser.add_argument(
        "--tsv",
        action="store_true",
        help="Emit tab-separated rather than comma-separated",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log progress to stderr",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    rows = query_dossiers_needing_review(
        min_quality=args.min_quality,
        priority=args.priority,
        limit=args.limit,
        gold_only=args.gold_only,
    )

    if args.verbose:
        _log.info(
            "Found %d dossiers (min_quality=%.1f, priority=%s, gold_only=%s)",
            len(rows), args.min_quality, args.priority, args.gold_only,
        )

    write_csv(rows, args.out, tsv=args.tsv)

    if args.verbose and args.out:
        _log.info("Wrote %d rows to %s", len(rows), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
