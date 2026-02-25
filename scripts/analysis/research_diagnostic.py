"""
Research Agent Diagnostic Report

Comprehensive diagnostic that outputs all key metrics from completed research runs.
Run after any batch of research runs to measure improvement.

Usage:
    py scripts/analysis/research_diagnostic.py
    py scripts/analysis/research_diagnostic.py --recent 10   # only last N runs
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def run_diagnostic(recent: int | None = None) -> dict:
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # ---------- Overall Performance ----------
    where = "WHERE status = 'completed'"
    if recent:
        where += f" ORDER BY id DESC LIMIT {recent}"
        # Wrap to use as subquery
        base_q = f"SELECT * FROM research_runs {where}"
        run_filter = f"id IN (SELECT id FROM ({base_q}) sub)"
    else:
        run_filter = "status = 'completed'"

    cur.execute(f"""
        SELECT COUNT(*) AS cnt,
               ROUND(AVG(overall_quality_score), 2) AS avg_quality,
               ROUND(AVG(total_facts_found), 1) AS avg_facts,
               ROUND(AVG(sections_filled), 1) AS avg_sections,
               ROUND(AVG(duration_seconds) / 60.0, 1) AS avg_minutes,
               ROUND(AVG(total_cost_cents) / 100.0, 4) AS avg_cost_dollars
        FROM research_runs WHERE {run_filter}
    """)
    overall = dict(cur.fetchone())

    cur.execute(f"""
        SELECT COUNT(*) AS total_runs,
               COUNT(*) FILTER (WHERE status = 'completed') AS completed,
               COUNT(*) FILTER (WHERE status = 'failed') AS failed,
               COUNT(*) FILTER (WHERE status = 'running') AS running
        FROM research_runs
    """)
    status_counts = dict(cur.fetchone())

    # ---------- Quality Dimensions ----------
    cur.execute(f"""
        SELECT
            ROUND(AVG((quality_dimensions->>'coverage')::numeric), 2) AS coverage_avg,
            ROUND(MIN((quality_dimensions->>'coverage')::numeric), 2) AS coverage_min,
            ROUND(MAX((quality_dimensions->>'coverage')::numeric), 2) AS coverage_max,
            ROUND(AVG((quality_dimensions->>'source_quality')::numeric), 2) AS source_quality_avg,
            ROUND(MIN((quality_dimensions->>'source_quality')::numeric), 2) AS source_quality_min,
            ROUND(MAX((quality_dimensions->>'source_quality')::numeric), 2) AS source_quality_max,
            ROUND(AVG((quality_dimensions->>'consistency')::numeric), 2) AS consistency_avg,
            ROUND(MIN((quality_dimensions->>'consistency')::numeric), 2) AS consistency_min,
            ROUND(MAX((quality_dimensions->>'consistency')::numeric), 2) AS consistency_max,
            ROUND(AVG((quality_dimensions->>'freshness')::numeric), 2) AS freshness_avg,
            ROUND(MIN((quality_dimensions->>'freshness')::numeric), 2) AS freshness_min,
            ROUND(MAX((quality_dimensions->>'freshness')::numeric), 2) AS freshness_max,
            ROUND(AVG((quality_dimensions->>'efficiency')::numeric), 2) AS efficiency_avg,
            ROUND(MIN((quality_dimensions->>'efficiency')::numeric), 2) AS efficiency_min,
            ROUND(MAX((quality_dimensions->>'efficiency')::numeric), 2) AS efficiency_max
        FROM research_runs
        WHERE {run_filter} AND quality_dimensions IS NOT NULL
    """)
    dims = dict(cur.fetchone())

    # ---------- Tool Hit Rates ----------
    cur.execute(f"""
        SELECT ra.tool_name,
               COUNT(*) AS calls,
               ROUND(AVG(CASE WHEN ra.data_found THEN 1 ELSE 0 END) * 100, 1) AS hit_rate_pct,
               ROUND(AVG(ra.latency_ms)) AS avg_latency_ms
        FROM research_actions ra
        JOIN research_runs rr ON rr.id = ra.run_id
        WHERE rr.{run_filter}
          AND ra.tool_name NOT LIKE '%%(cached)%%'
        GROUP BY ra.tool_name
        ORDER BY calls DESC
    """)
    tool_stats = [dict(r) for r in cur.fetchall()]

    # ---------- Section Fill Rates ----------
    cur.execute(f"""
        SELECT dossier_section,
               COUNT(DISTINCT attribute_name) AS distinct_attrs,
               COUNT(*) AS total_facts,
               COUNT(DISTINCT run_id) AS runs_with_data
        FROM research_facts rf
        JOIN research_runs rr ON rr.id = rf.run_id
        WHERE rr.{run_filter}
        GROUP BY dossier_section
        ORDER BY dossier_section
    """)
    section_stats = [dict(r) for r in cur.fetchall()]

    # ---------- Web Search Gap Effectiveness ----------
    cur.execute("""
        SELECT gap_type, times_used, times_produced_result,
               ROUND(times_produced_result::numeric / NULLIF(times_used, 0) * 100, 1) AS hit_rate_pct
        FROM research_query_effectiveness
        ORDER BY times_used DESC
    """)
    gap_stats = [dict(r) for r in cur.fetchall()]

    # ---------- Dossier Field Coverage ----------
    cur.execute(f"""
        SELECT attribute_name, dossier_section,
               COUNT(*) AS times_filled,
               ROUND(COUNT(*)::numeric / NULLIF(
                   (SELECT COUNT(DISTINCT run_id) FROM research_facts rf2
                    JOIN research_runs rr2 ON rr2.id = rf2.run_id WHERE rr2.{run_filter}),
                   0
               ) * 100, 1) AS fill_rate_pct
        FROM research_facts rf
        JOIN research_runs rr ON rr.id = rf.run_id
        WHERE rr.{run_filter}
        GROUP BY attribute_name, dossier_section
        ORDER BY fill_rate_pct DESC
    """)
    field_coverage = [dict(r) for r in cur.fetchall()]

    # ---------- Vocabulary fields never filled ----------
    cur.execute(f"""
        SELECT v.attribute_name, v.dossier_section
        FROM research_fact_vocabulary v
        LEFT JOIN (
            SELECT DISTINCT attribute_name
            FROM research_facts rf
            JOIN research_runs rr ON rr.id = rf.run_id
            WHERE rr.{run_filter}
        ) filled ON filled.attribute_name = v.attribute_name
        WHERE filled.attribute_name IS NULL
        ORDER BY v.dossier_section, v.attribute_name
    """)
    never_filled = [dict(r) for r in cur.fetchall()]

    conn.close()

    return {
        "overall": overall,
        "status_counts": status_counts,
        "quality_dimensions": dims,
        "tool_stats": tool_stats,
        "section_stats": section_stats,
        "gap_effectiveness": gap_stats,
        "field_coverage": field_coverage,
        "never_filled": never_filled,
    }


def print_report(data: dict):
    print("=" * 70)
    print("  RESEARCH AGENT DIAGNOSTIC REPORT")
    print("=" * 70)

    o = data["overall"]
    s = data["status_counts"]
    print(f"\n## Overall Performance ({s['completed']}/{s['total_runs']} completed)")
    print(f"  Avg quality score:  {o['avg_quality']}/10")
    print(f"  Avg facts per run:  {o['avg_facts']}")
    print(f"  Avg sections filled: {o['avg_sections']}/7")
    print(f"  Avg duration:       {o['avg_minutes']} min")
    print(f"  Avg cost:           ${o['avg_cost_dollars']}")

    d = data["quality_dimensions"]
    print("\n## Quality Dimensions (avg / min / max)")
    for dim in ["coverage", "source_quality", "consistency", "freshness", "efficiency"]:
        avg = d.get(f"{dim}_avg") or "?"
        mn = d.get(f"{dim}_min") or "?"
        mx = d.get(f"{dim}_max") or "?"
        print(f"  {dim:20s}  {str(avg):>6}  {str(mn):>6}  {str(mx):>6}")

    print("\n## Tool Hit Rates")
    print(f"  {'Tool':<30s} {'Calls':>6} {'Hit%':>6} {'Latency':>8}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*8}")
    for t in data["tool_stats"]:
        print(f"  {t['tool_name']:<30s} {t['calls']:>6} {t['hit_rate_pct']:>5.1f}% {t['avg_latency_ms']:>7.0f}ms")

    print("\n## Section Fill Rates")
    for s in data["section_stats"]:
        print(f"  {s['dossier_section']:<15s} {s['distinct_attrs']:>3} attrs, {s['total_facts']:>5} facts, {s['runs_with_data']:>4} runs")

    print("\n## Web Search Gap Effectiveness")
    for g in data["gap_effectiveness"]:
        print(f"  {g['gap_type']:<25s} used={g['times_used']:>3} hits={g['times_produced_result']:>3} rate={g['hit_rate_pct']:>5.1f}%")

    print(f"\n## Never-Filled Vocabulary Fields ({len(data['never_filled'])})")
    for nf in data["never_filled"]:
        print(f"  {nf['dossier_section']}.{nf['attribute_name']}")

    print(f"\n## Field Coverage (top 20)")
    for fc in data["field_coverage"][:20]:
        print(f"  {fc['dossier_section']}.{fc['attribute_name']:<30s} filled={fc['times_filled']:>4} rate={fc['fill_rate_pct']:>5.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research Agent Diagnostic Report")
    parser.add_argument("--recent", type=int, help="Only analyze the last N runs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = run_diagnostic(recent=args.recent)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_report(data)
