"""
Research Agent Auto-Grader (Phase 5.3)

Deterministic quality grading for completed research runs.
Computes 5 dimension scores (each 0-10) and a weighted overall score.

Weights (D16 decision):
  Coverage 20%, Source Quality 35%, Consistency 25%, Freshness 15%, Efficiency 5%

Usage:
  py scripts/research/auto_grader.py            # backfill all unscored runs
  py scripts/research/auto_grader.py --run-id 5  # grade a specific run
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Allow running from project root
sys.path.insert(0, ".")
from db_config import get_connection

_log = logging.getLogger("auto_grader")

# D16 weights
WEIGHTS = {
    "coverage": 0.20,
    "source_quality": 0.35,
    "consistency": 0.25,
    "freshness": 0.15,
    "efficiency": 0.05,
}

TOTAL_SECTIONS = 7  # identity, labor, assessment, workforce, workplace, financial, sources

SOURCE_TYPE_RANK = {
    "database": 1.0,
    "api": 0.9,
    "web_scrape": 0.7,
    "web_search": 0.6,
    "news": 0.5,
}


def _score_coverage(facts_by_section: Dict[str, List[dict]]) -> float:
    """Coverage: how many of the 7 dossier sections have facts."""
    sections_filled = len(facts_by_section)
    base = (sections_filled / TOTAL_SECTIONS) * 8.0

    # Bonus for rich sections (3+ facts)
    bonus = 0.0
    for facts in facts_by_section.values():
        if len(facts) >= 3:
            bonus += 0.4
    bonus = min(bonus, 2.0)

    return min(base + bonus, 10.0)


def _score_source_quality(facts: List[dict]) -> float:
    """Source Quality: based on source types and confidence levels."""
    if not facts:
        return 0.0

    # Average source type score
    source_scores = []
    null_source_count = 0
    for f in facts:
        st = (f.get("source_type") or "").lower()
        source_scores.append(SOURCE_TYPE_RANK.get(st, 0.5))
        if not f.get("source_name"):
            null_source_count += 1

    avg_source = sum(source_scores) / len(source_scores) if source_scores else 0.5

    # Average confidence
    confidences = []
    for f in facts:
        c = f.get("confidence")
        if c is not None:
            confidences.append(float(c))
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

    combined = (0.5 * avg_source + 0.5 * avg_confidence) * 10.0

    # Penalty for missing source names
    if len(facts) > 0 and (null_source_count / len(facts)) > 0.30:
        combined -= 1.0

    return max(min(combined, 10.0), 0.0)


def _extract_numeric(val: Any) -> Optional[float]:
    """Extract a float from various types, including strings with suffixes/commas."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    if isinstance(val, str):
        # Remove commas and common suffixes
        cleaned = re.sub(r'[^\d.]', '', val.split(' ')[0].replace(',', ''))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _score_consistency(facts: List[dict]) -> float:
    """Consistency: penalize contradictions and large numeric divergences."""
    score = 10.0

    # Count contradictions
    contradictions = sum(1 for f in facts if f.get("contradicts_fact_id") is not None)
    score -= contradictions * 2.0

    # Check employee_count divergence
    emp_values = []
    for f in facts:
        if f.get("attribute_name") == "employee_count":
            val = _extract_numeric(f.get("attribute_value"))
            if val:
                emp_values.append(val)
    if len(emp_values) > 1:
        min_val = min(emp_values)
        max_val = max(emp_values)
        if min_val > 0 and (max_val / min_val) > 2.0:
            score -= 2.0

    # Check revenue divergence
    rev_values = []
    for f in facts:
        if f.get("attribute_name") == "revenue":
            val = _extract_numeric(f.get("attribute_value"))
            if val:
                rev_values.append(val)
    if len(rev_values) > 1:
        min_val = min(rev_values)
        max_val = max(rev_values)
        if min_val > 0 and (max_val / min_val) > 2.0:
            score -= 2.0

    return max(score, 0.0)


def _score_freshness(facts: List[dict], today: Optional[date] = None) -> float:
    """Freshness: how recent the fact data is."""
    if not facts:
        return 5.0  # neutral

    today = today or date.today()
    scores = []
    for f in facts:
        as_of = f.get("as_of_date")
        if as_of is None:
            scores.append(5.0)  # neutral for undated facts
            continue

        if isinstance(as_of, str):
            try:
                as_of = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                scores.append(5.0)
                continue
        elif isinstance(as_of, datetime):
            as_of = as_of.date()

        age_days = (today - as_of).days
        if age_days < 183:       # < 6 months
            scores.append(10.0)
        elif age_days < 365:     # 6-12 months
            scores.append(8.0)
        elif age_days < 730:     # 1-2 years
            scores.append(6.0)
        elif age_days < 1095:    # 2-3 years
            scores.append(4.0)
        elif age_days < 1825:    # 3-5 years
            scores.append(2.0)
        else:                    # > 5 years
            scores.append(1.0)

    return sum(scores) / len(scores) if scores else 5.0


def _score_efficiency(total_facts: int, total_tools: int, actions: List[dict]) -> float:
    """Efficiency: facts per tool call and speed."""
    facts_per_tool = total_facts / max(total_tools, 1)

    if facts_per_tool >= 3:
        score = 10.0
    elif facts_per_tool >= 2:
        score = 8.0
    elif facts_per_tool >= 1:
        score = 6.0
    elif facts_per_tool >= 0.5:
        score = 4.0
    else:
        score = 2.0

    # Speed bonus
    latencies = [float(a["latency_ms"]) for a in actions if a.get("latency_ms") is not None]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        if avg_latency < 500:
            score += 1.0

    return min(score, 10.0)


def grade_research_run(run_id: int, conn=None) -> dict:
    """
    Compute 5 dimension scores and weighted overall for a research run.

    Returns dict with keys: coverage, source_quality, consistency, freshness,
    efficiency, overall, and metadata about the computation.
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()

        # Verify run exists and is completed
        cur.execute(
            "SELECT id, total_tools_called, total_facts_found, sections_filled "
            "FROM research_runs WHERE id = %s",
            (run_id,),
        )
        run = cur.fetchone()
        if not run:
            raise ValueError(f"Research run {run_id} not found")
        if run.get("total_facts_found") is None:
            raise ValueError(f"Research run {run_id} has no facts data (likely not completed)")

        total_tools = run["total_tools_called"] or 0
        total_facts = run["total_facts_found"] or 0

        # Get all facts
        cur.execute(
            "SELECT dossier_section, attribute_name, attribute_value, "
            "source_type, source_name, confidence, as_of_date, contradicts_fact_id "
            "FROM research_facts WHERE run_id = %s",
            (run_id,),
        )
        all_facts = [dict(r) for r in cur.fetchall()]

        # Group by section
        facts_by_section: Dict[str, List[dict]] = {}
        for f in all_facts:
            sec = f["dossier_section"]
            if sec not in facts_by_section:
                facts_by_section[sec] = []
            facts_by_section[sec].append(f)

        # Get actions for efficiency scoring
        cur.execute(
            "SELECT latency_ms FROM research_actions WHERE run_id = %s",
            (run_id,),
        )
        actions = [dict(r) for r in cur.fetchall()]

        # Compute each dimension
        coverage = round(_score_coverage(facts_by_section), 2)
        source_quality = round(_score_source_quality(all_facts), 2)
        consistency = round(_score_consistency(all_facts), 2)
        freshness = round(_score_freshness(all_facts), 2)
        efficiency = round(_score_efficiency(total_facts, total_tools, actions), 2)

        overall = round(
            coverage * WEIGHTS["coverage"]
            + source_quality * WEIGHTS["source_quality"]
            + consistency * WEIGHTS["consistency"]
            + freshness * WEIGHTS["freshness"]
            + efficiency * WEIGHTS["efficiency"],
            2,
        )

        return {
            "coverage": coverage,
            "source_quality": source_quality,
            "consistency": consistency,
            "freshness": freshness,
            "efficiency": efficiency,
            "overall": overall,
            "facts_count": len(all_facts),
            "sections_count": len(facts_by_section),
            "actions_count": len(actions),
        }
    finally:
        if close_conn:
            conn.close()


def grade_and_save(run_id: int, conn=None) -> dict:
    """Grade a run and persist scores to research_runs."""
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        result = grade_research_run(run_id, conn=conn)

        dimensions = {
            "coverage": result["coverage"],
            "source_quality": result["source_quality"],
            "consistency": result["consistency"],
            "freshness": result["freshness"],
            "efficiency": result["efficiency"],
        }

        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()
        cur.execute(
            "UPDATE research_runs "
            "SET overall_quality_score = %s, quality_dimensions = %s, updated_at = NOW() "
            "WHERE id = %s",
            (result["overall"], json.dumps(dimensions), run_id),
        )
        conn.commit()

        _log.info("Run %d graded: overall=%.2f (%s)", run_id, result["overall"], dimensions)
        return result
    finally:
        if close_conn:
            conn.close()


def backfill_all_scores() -> int:
    """Grade all completed runs that have no quality score yet."""
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM research_runs "
            "WHERE status = 'completed' AND overall_quality_score IS NULL "
            "ORDER BY id"
        )
        run_ids = [r["id"] for r in cur.fetchall()]

        if not run_ids:
            _log.info("No unscored completed runs found.")
            return 0

        _log.info("Backfilling scores for %d runs...", len(run_ids))
        graded = 0
        for rid in run_ids:
            try:
                result = grade_and_save(rid, conn=conn)
                _log.info("  Run %d: overall=%.2f", rid, result["overall"])
                graded += 1
            except Exception as e:
                _log.warning("  Run %d failed: %s", rid, e)

        _log.info("Backfill complete: %d/%d runs graded.", graded, len(run_ids))

        # Update strategy quality after backfill
        try:
            update_strategy_quality(conn=conn)
        except Exception as e:
            _log.warning("Strategy quality update failed: %s", e)

        return graded
    finally:
        conn.close()


def update_strategy_quality(conn=None) -> int:
    """
    Seed and update research_strategies from completed research runs.

    Uses UPSERT: INSERT rows from research_actions JOIN research_runs grouped
    by (industry 2-digit NAICS, company_type, size_bucket, tool_name), then
    updates avg_quality, hit_rate, avg_latency_ms from graded runs.

    Returns the number of rows upserted.
    """
    close_conn = False
    if conn is None:
        conn = get_connection(cursor_factory=RealDictCursor)
        close_conn = True

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor) if not close_conn else conn.cursor()

        cur.execute("""
            INSERT INTO research_strategies
                (industry_naics_2digit, company_type, company_size_bucket, tool_name,
                 times_tried, times_found_data, hit_rate, avg_quality, avg_latency_ms,
                 last_updated)
            SELECT
                COALESCE(LEFT(rr.industry_naics, 2), ''),
                COALESCE(rr.company_type, ''),
                COALESCE(rr.employee_size_bucket, ''),
                ra.tool_name,
                COUNT(*) AS times_tried,
                COUNT(*) FILTER (WHERE ra.data_found = TRUE) AS times_found_data,
                ROUND(
                    COUNT(*) FILTER (WHERE ra.data_found = TRUE)::numeric
                    / NULLIF(COUNT(*), 0), 4
                ) AS hit_rate,
                ROUND(AVG(rr.overall_quality_score) FILTER (WHERE ra.data_found = TRUE), 2),
                COALESCE(AVG(ra.latency_ms)::integer, 0),
                NOW()
            FROM research_actions ra
            JOIN research_runs rr ON rr.id = ra.run_id
            WHERE rr.status = 'completed'
            GROUP BY LEFT(rr.industry_naics, 2), rr.company_type,
                     rr.employee_size_bucket, ra.tool_name
            ON CONFLICT (industry_naics_2digit, company_type, company_size_bucket, tool_name)
            DO UPDATE SET
                times_tried = EXCLUDED.times_tried,
                times_found_data = EXCLUDED.times_found_data,
                hit_rate = EXCLUDED.hit_rate,
                avg_quality = COALESCE(EXCLUDED.avg_quality, research_strategies.avg_quality),
                avg_latency_ms = EXCLUDED.avg_latency_ms,
                last_updated = NOW()
        """)
        upserted = cur.rowcount
        conn.commit()
        _log.info("Upserted %d strategy rows.", upserted)
        return upserted
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Auto-grade research runs")
    parser.add_argument("--run-id", type=int, help="Grade a specific run")
    args = parser.parse_args()

    if args.run_id:
        result = grade_and_save(args.run_id)
        print(f"Run {args.run_id}: overall={result['overall']}")
        for dim in ["coverage", "source_quality", "consistency", "freshness", "efficiency"]:
            print(f"  {dim}: {result[dim]}")
    else:
        count = backfill_all_scores()
        print(f"Backfilled {count} runs.")
