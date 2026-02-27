"""
Batch research runner for Phase 2.7 backfill sprint.

Submits research runs for candidate employers, tracks progress,
and runs auto-grader + enhancement backfill after completion.

Usage:
  # Run on top 50 non-union targets (Path B)
  py scripts/research/batch_research.py --type non_union --limit 50

  # Run on top 50 union reference employers (Path A)
  py scripts/research/batch_research.py --type union_reference --limit 50

  # Resume from a checkpoint (skip already-submitted)
  py scripts/research/batch_research.py --type non_union --limit 50 --resume

  # Grade and backfill only (no new runs)
  py scripts/research/batch_research.py --backfill-only

  # Dry run (show candidates, don't submit)
  py scripts/research/batch_research.py --type non_union --limit 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from db_config import get_connection
from psycopg2.extras import RealDictCursor

_log = logging.getLogger("batch_research")

CHECKPOINT_DIR = Path("scripts/research")
CHECKPOINT_FILE = CHECKPOINT_DIR / "batch_checkpoint.json"


def _load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"submitted_employer_ids": [], "run_ids": []}


def _save_checkpoint(data: dict):
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def get_candidates(candidate_type: str, limit: int) -> list:
    """Fetch candidate employers from the database."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        if candidate_type == "non_union":
            cur.execute("""
                SELECT
                    s.employer_id, s.employer_name, s.state, s.city, s.naics,
                    s.latest_unit_size, s.weighted_score, s.factors_available,
                    s.score_tier, s.source_count,
                    ROUND((s.weighted_score * (8 - s.factors_available))::numeric, 2)
                        AS research_priority
                FROM mv_unified_scorecard s
                WHERE NOT s.has_research
                  AND s.factors_available < 6
                  AND s.weighted_score IS NOT NULL
                ORDER BY s.weighted_score * (8 - s.factors_available) DESC NULLS LAST
                LIMIT %s
            """, (limit,))
        else:
            cur.execute("""
                SELECT
                    f.employer_id, f.employer_name, f.state, f.city, f.naics,
                    f.latest_unit_size,
                    ds.source_count
                FROM f7_employers_deduped f
                JOIN mv_employer_data_sources ds ON ds.employer_id = f.employer_id
                LEFT JOIN research_score_enhancements rse
                    ON rse.employer_id = f.employer_id
                WHERE rse.id IS NULL
                  AND ds.source_count <= 2
                  AND f.latest_unit_size IS NOT NULL
                ORDER BY ds.source_count ASC,
                         f.latest_unit_size DESC NULLS LAST
                LIMIT %s
            """, (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def submit_research_run(employer_id: str, company_name: str, state: str = None,
                        naics: str = None) -> int:
    """Create a research_runs record and run the agent synchronously."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO research_runs
                (company_name, employer_id, industry_naics, company_state,
                 status, current_step, progress_pct, triggered_by)
            VALUES (%s, %s, %s, %s, 'pending', 'Queued (batch)', 0, 'batch_research')
            RETURNING id
        """, (company_name, employer_id, naics, state))
        run_id = cur.fetchone()["id"]
        conn.commit()
        return run_id
    finally:
        conn.close()


def run_single(run_id: int) -> dict:
    """Execute a single research run synchronously."""
    from scripts.research.agent import run_research
    return run_research(run_id)


def grade_and_enhance(run_id: int):
    """Grade a completed run and compute enhancements."""
    from scripts.research.auto_grader import grade_and_save, compute_research_enhancements
    try:
        result = grade_and_save(run_id)
        _log.info("  Graded: overall=%.2f", result["overall"])
        if result["overall"] >= 7.0:
            enh_id = compute_research_enhancements(run_id)
            if enh_id:
                _log.info("  Enhancement saved (id=%d)", enh_id)
            else:
                _log.info("  Enhancement skipped (no employer_id or lower quality)")
    except Exception as e:
        _log.warning("  Grade/enhance failed for run %d: %s", run_id, e)


def backfill_grades_and_enhancements():
    """Grade all unscored runs and backfill enhancements."""
    from scripts.research.auto_grader import backfill_all_scores, backfill_enhancements

    print("\n=== Grading unscored runs ===")
    graded = backfill_all_scores()
    print(f"Graded {graded} runs.")

    print("\n=== Backfilling enhancements ===")
    saved = backfill_enhancements()
    print(f"Saved {saved} enhancement rows.")

    return graded, saved


def run_batch(candidate_type: str, limit: int, resume: bool = False,
              dry_run: bool = False):
    """Run research on a batch of candidate employers."""
    candidates = get_candidates(candidate_type, limit)
    print(f"\nFound {len(candidates)} candidates ({candidate_type}).")

    if not candidates:
        print("No candidates found.")
        return

    # Load checkpoint if resuming
    checkpoint = _load_checkpoint() if resume else {"submitted_employer_ids": [], "run_ids": []}
    already_done = set(checkpoint["submitted_employer_ids"])

    # Filter out already-submitted
    if resume:
        before = len(candidates)
        candidates = [c for c in candidates if c["employer_id"] not in already_done]
        skipped = before - len(candidates)
        if skipped:
            print(f"Resuming: skipped {skipped} already-submitted employers.")

    if dry_run:
        print(f"\n=== DRY RUN: Would submit {len(candidates)} research runs ===")
        for i, c in enumerate(candidates[:20]):
            name = c["employer_name"]
            state = c.get("state", "?")
            score = c.get("weighted_score") or c.get("source_count", "?")
            tier = c.get("score_tier", "")
            print(f"  {i+1}. {name} ({state}) - score={score} tier={tier}")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
        return

    print(f"\nSubmitting {len(candidates)} research runs...")
    completed = 0
    failed = 0
    start = time.time()

    for i, c in enumerate(candidates):
        emp_id = c["employer_id"]
        name = c["employer_name"]
        state = c.get("state")
        naics = c.get("naics")

        print(f"\n[{i+1}/{len(candidates)}] {name} ({state or '?'})...")

        try:
            run_id = submit_research_run(emp_id, name, state, naics)
            checkpoint["submitted_employer_ids"].append(emp_id)
            checkpoint["run_ids"].append(run_id)
            _save_checkpoint(checkpoint)

            result = run_single(run_id)
            status = result.get("status", "unknown")

            if status == "completed":
                completed += 1
                print(f"  -> Completed (run #{run_id})")
                grade_and_enhance(run_id)
            else:
                failed += 1
                print(f"  -> {status}: {result.get('error', 'unknown error')[:100]}")

        except Exception as e:
            failed += 1
            print(f"  -> ERROR: {str(e)[:100]}")
            _log.exception("Run failed for %s", name)

        # Progress update
        elapsed = time.time() - start
        avg_per_run = elapsed / (i + 1)
        remaining = avg_per_run * (len(candidates) - i - 1)
        print(f"  Progress: {completed} ok, {failed} failed, "
              f"~{remaining/60:.0f}m remaining")

    print(f"\n=== Batch Complete ===")
    print(f"  Completed: {completed}/{len(candidates)}")
    print(f"  Failed: {failed}/{len(candidates)}")
    print(f"  Duration: {(time.time() - start)/60:.1f} minutes")

    # Final stats
    print_stats()


def print_stats():
    """Print current research coverage stats."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS cnt FROM research_runs WHERE status = 'completed'")
        total_runs = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM research_runs WHERE status = 'completed' AND overall_quality_score >= 7.0")
        publishable = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM research_score_enhancements")
        enhancements = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM research_score_enhancements
            WHERE is_union_reference = TRUE
        """)
        union_ref = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM research_score_enhancements
            WHERE is_union_reference = FALSE
        """)
        non_union = cur.fetchone()["cnt"]

        print(f"\n=== Research Coverage Stats ===")
        print(f"  Total completed runs: {total_runs}")
        print(f"  Publishable (>= 7.0): {publishable} ({publishable*100//max(total_runs,1)}%)")
        print(f"  Score enhancements: {enhancements}")
        print(f"    Union reference (Path A): {union_ref}")
        print(f"    Non-union targets (Path B): {non_union}")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Batch research runner for Phase 2.7")
    parser.add_argument("--type", choices=["non_union", "union_reference"],
                        default="non_union", help="Candidate type")
    parser.add_argument("--limit", type=int, default=50,
                        help="Number of candidates to process")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint (skip already-submitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show candidates without submitting")
    parser.add_argument("--backfill-only", action="store_true",
                        help="Only grade and backfill enhancements (no new runs)")
    parser.add_argument("--stats", action="store_true",
                        help="Show current research coverage stats")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.backfill_only:
        backfill_grades_and_enhancements()
        print_stats()
    else:
        run_batch(args.type, args.limit, resume=args.resume, dry_run=args.dry_run)
