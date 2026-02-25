"""
Research Web Search Gap Analysis

Analyzes web search effectiveness: which gap types produce results,
which queries work, and which fail.

Usage:
    py scripts/analysis/research_gap_analysis.py
    py scripts/analysis/research_gap_analysis.py --recent 10
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def analyze_gaps(recent: int | None = None) -> dict:
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    # ---------- Query effectiveness from tracking table ----------
    cur.execute("""
        SELECT gap_type, query_template, times_used, times_produced_result,
               ROUND(times_produced_result::numeric / NULLIF(times_used, 0) * 100, 1) AS hit_rate_pct,
               company_type
        FROM research_query_effectiveness
        ORDER BY times_used DESC
    """)
    query_effectiveness = [dict(r) for r in cur.fetchall()]

    # ---------- Google search actions ----------
    run_filter = "rr.status = 'completed'"
    if recent:
        run_filter = f"rr.id IN (SELECT id FROM research_runs WHERE status = 'completed' ORDER BY id DESC LIMIT {recent})"

    cur.execute(f"""
        SELECT ra.run_id, rr.company_name, ra.tool_params, ra.result_summary, ra.data_found
        FROM research_actions ra
        JOIN research_runs rr ON rr.id = ra.run_id
        WHERE {run_filter}
          AND ra.tool_name LIKE '%%google_search%%'
        ORDER BY ra.run_id DESC
    """)
    web_searches = [dict(r) for r in cur.fetchall()]

    # ---------- Tool gaps (tools that returned no data) ----------
    cur.execute(f"""
        SELECT ra.tool_name,
               COUNT(*) AS total_calls,
               COUNT(*) FILTER (WHERE NOT ra.data_found) AS miss_count,
               ROUND(COUNT(*) FILTER (WHERE NOT ra.data_found)::numeric / NULLIF(COUNT(*), 0) * 100, 1) AS miss_rate_pct
        FROM research_actions ra
        JOIN research_runs rr ON rr.id = ra.run_id
        WHERE {run_filter}
          AND ra.tool_name NOT LIKE '%%(cached)%%'
          AND ra.tool_name NOT LIKE '%%google_search%%'
        GROUP BY ra.tool_name
        ORDER BY miss_rate_pct DESC
    """)
    tool_gaps = [dict(r) for r in cur.fetchall()]

    # ---------- Facts source breakdown ----------
    cur.execute(f"""
        SELECT rf.source_type, COUNT(*) AS cnt,
               COUNT(DISTINCT rf.attribute_name) AS distinct_attrs,
               ROUND(AVG(rf.confidence), 2) AS avg_confidence
        FROM research_facts rf
        JOIN research_runs rr ON rr.id = rf.run_id
        WHERE {run_filter}
        GROUP BY rf.source_type
        ORDER BY cnt DESC
    """)
    source_breakdown = [dict(r) for r in cur.fetchall()]

    # ---------- Web-sourced facts detail ----------
    cur.execute(f"""
        SELECT rf.attribute_name, rf.dossier_section, COUNT(*) AS cnt,
               ROUND(AVG(rf.confidence), 2) AS avg_confidence
        FROM research_facts rf
        JOIN research_runs rr ON rr.id = rf.run_id
        WHERE {run_filter} AND rf.source_type = 'web_search'
        GROUP BY rf.attribute_name, rf.dossier_section
        ORDER BY cnt DESC
    """)
    web_facts = [dict(r) for r in cur.fetchall()]

    # ---------- Strategy table summary ----------
    cur.execute("""
        SELECT tool_name,
               ROUND(AVG(hit_rate), 3) AS avg_hit_rate,
               SUM(times_tried) AS total_tries,
               ROUND(AVG(avg_quality), 2) AS avg_quality,
               ROUND(AVG(avg_latency_ms)) AS avg_latency
        FROM research_strategies
        GROUP BY tool_name
        ORDER BY avg_hit_rate DESC
    """)
    strategies = [dict(r) for r in cur.fetchall()]

    conn.close()

    return {
        "query_effectiveness": query_effectiveness,
        "web_searches": web_searches[:20],  # limit for output
        "tool_gaps": tool_gaps,
        "source_breakdown": source_breakdown,
        "web_facts": web_facts,
        "strategies": strategies,
    }


def print_report(data: dict):
    print("=" * 70)
    print("  RESEARCH WEB SEARCH GAP ANALYSIS")
    print("=" * 70)

    print("\n## Query Effectiveness by Gap Type")
    print(f"  {'Gap Type':<25s} {'Uses':>5} {'Hits':>5} {'Rate':>6} {'Company Type':<12s}")
    print(f"  {'-'*25} {'-'*5} {'-'*5} {'-'*6} {'-'*12}")
    for q in data["query_effectiveness"]:
        print(f"  {q['gap_type']:<25s} {q['times_used']:>5} {q['times_produced_result']:>5} {q['hit_rate_pct']:>5.1f}% {q.get('company_type', ''):12s}")

    print("\n## Tool Miss Rates (DB tools that returned no data)")
    print(f"  {'Tool':<30s} {'Calls':>6} {'Misses':>7} {'Miss%':>6}")
    print(f"  {'-'*30} {'-'*6} {'-'*7} {'-'*6}")
    for t in data["tool_gaps"]:
        print(f"  {t['tool_name']:<30s} {t['total_calls']:>6} {t['miss_count']:>7} {t['miss_rate_pct']:>5.1f}%")

    print("\n## Facts Source Breakdown")
    for s in data["source_breakdown"]:
        print(f"  {s['source_type']:<15s} {s['cnt']:>5} facts, {s['distinct_attrs']:>3} attrs, conf={s['avg_confidence']}")

    print("\n## Web-Sourced Facts Detail")
    if data["web_facts"]:
        for wf in data["web_facts"]:
            print(f"  {wf['dossier_section']}.{wf['attribute_name']:<30s} {wf['cnt']:>4} facts, conf={wf['avg_confidence']}")
    else:
        print("  (no web-sourced facts found)")

    print("\n## Strategy Table (learned per tool)")
    print(f"  {'Tool':<30s} {'Tries':>6} {'HitRate':>8} {'Quality':>8} {'Latency':>8}")
    print(f"  {'-'*30} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")
    for s in data["strategies"]:
        print(f"  {s['tool_name']:<30s} {s['total_tries']:>6} {s['avg_hit_rate']:>7.3f} {s['avg_quality'] or 0:>7.2f} {s['avg_latency'] or 0:>7.0f}ms")

    # Recent web searches
    print(f"\n## Recent Web Searches (last {len(data['web_searches'])})")
    for ws in data["web_searches"][:10]:
        params = ws.get("tool_params")
        queries = []
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(params, dict):
            queries = params.get("queries", [])
        found = "HIT" if ws["data_found"] else "MISS"
        print(f"  Run {ws['run_id']:>3} ({ws['company_name']:<25s}) {found}  queries: {queries[:3]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research Web Search Gap Analysis")
    parser.add_argument("--recent", type=int, help="Only analyze the last N runs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    data = analyze_gaps(recent=args.recent)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_report(data)
