"""Analyze research tool effectiveness from research_actions table."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db_config import get_connection


def main():
    parser = argparse.ArgumentParser(description="Analyze research tool effectiveness")
    parser.add_argument("--min-runs", type=int, default=3, help="Minimum calls to include tool (default 3)")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT tool_name,
               COUNT(*) AS total_calls,
               COUNT(*) FILTER (WHERE data_found = true) AS hits,
               COUNT(*) FILTER (WHERE error_message IS NOT NULL AND error_message != '') AS errors,
               ROUND(AVG(latency_ms)) AS avg_latency_ms,
               ROUND(AVG(latency_ms) FILTER (WHERE data_found = true)) AS avg_latency_hit_ms,
               ROUND(AVG(facts_extracted) FILTER (WHERE data_found = true), 1) AS avg_facts_when_hit,
               SUM(latency_ms) AS total_time_ms
        FROM research_actions
        GROUP BY tool_name
        HAVING COUNT(*) >= %s
        ORDER BY COUNT(*) DESC
    """, (args.min_runs,))
    rows = cur.fetchall()

    print(f"{'Tool':<35} {'Calls':>6} {'Hits':>6} {'Hit%':>6} {'Err%':>6} {'AvgMs':>7} {'Facts':>6} {'TotalS':>8}")
    print("-" * 90)

    skip_candidates = []
    for row in rows:
        name, total, hits, errors, avg_lat, _avg_lat_hit, avg_facts, total_time = row
        hit_pct = (hits / total * 100) if total else 0
        err_pct = (errors / total * 100) if total else 0
        avg_facts_str = f"{avg_facts:.1f}" if avg_facts is not None else "-"
        print(f"{name:<35} {total:>6} {hits:>6} {hit_pct:>5.1f}% {err_pct:>5.1f}% {(avg_lat or 0):>6.0f}ms {avg_facts_str:>6} {((total_time or 0) / 1000):>7.1f}s")
        if hit_pct < 10 and (avg_lat or 0) > 500:
            skip_candidates.append((name, hit_pct, avg_lat or 0, total_time or 0))

    print()
    if skip_candidates:
        print("SKIP CANDIDATES (hit rate <10% AND avg latency >500ms):")
        for name, hit_pct, avg_lat, _total_time in skip_candidates:
            print(f"  {name}: {hit_pct:.1f}% hit rate, {avg_lat:.0f}ms avg latency")

        total_skip_time = sum(item[3] for item in skip_candidates)
        print(f"\n  Potential time savings: {total_skip_time / 1000:.1f}s total across all runs")

        cur.execute("SELECT COUNT(DISTINCT run_id) FROM research_actions")
        total_runs = cur.fetchone()[0]
        if total_runs:
            print(f"  Average savings per run: {(total_skip_time / 1000) / total_runs:.1f}s")
    else:
        print("No skip candidates met the configured threshold.")

    conn.close()


if __name__ == "__main__":
    main()
