#!/usr/bin/env python3
"""
Run Gold Standard Research Dossiers

Runs the research agent on 20 carefully selected companies that are varied
by industry and geography. These will become gold standard dossiers for
quality benchmarking and accuracy validation (roadmap P3-1).

Usage:
    py scripts/research/run_gold_standard_batch.py
    py scripts/research/run_gold_standard_batch.py --start-at 5
    py scripts/research/run_gold_standard_batch.py --resume
    py scripts/research/run_gold_standard_batch.py --dry-run
"""

import argparse
import csv
import os
import sys
import time

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from db_config import get_connection
from scripts.research.tools import get_api_call_stats

# ---------------------------------------------------------------------------
# Gold Standard Company List (ordered by expected data richness)
# ---------------------------------------------------------------------------

GOLD_STANDARD_COMPANIES = [
    {"name": "Amazon.com",            "state": "WA", "naics": "493110", "type": "public"},
    {"name": "Starbucks",             "state": "WA", "naics": "722515", "type": "public"},
    {"name": "Kroger",                "state": "OH", "naics": "445110", "type": "public"},
    {"name": "Tyson Foods",           "state": "AR", "naics": "311615", "type": "public"},
    {"name": "Kaiser Permanente",     "state": "CA", "naics": "622110", "type": "nonprofit"},
    {"name": "United Parcel Service", "state": "GA", "naics": "492110", "type": "public"},
    {"name": "HCA Healthcare",        "state": "TN", "naics": "622110", "type": "public"},
    {"name": "Walmart",               "state": "AR", "naics": "452311", "type": "public"},
    {"name": "Deere & Company",       "state": "IL", "naics": "333111", "type": "public"},
    {"name": "FedEx",                 "state": "TN", "naics": "492110", "type": "public"},
    {"name": "Sodexo",                "state": "MD", "naics": "722310", "type": "public"},
    {"name": "Honeywell",             "state": "NC", "naics": "334512", "type": "public"},
    {"name": "Aramark",               "state": "PA", "naics": "722310", "type": "public"},
    {"name": "Dollar General",        "state": "TN", "naics": "452319", "type": "public"},
    {"name": "University of California", "state": "CA", "naics": "611310", "type": "nonprofit"},
    {"name": "WK Kellogg",            "state": "MI", "naics": "311230", "type": "public"},
    {"name": "Warrior Met Coal",      "state": "AL", "naics": "212112", "type": "public"},
    {"name": "Lumen Technologies",    "state": "LA", "naics": "517311", "type": "public"},
    {"name": "Stericycle",            "state": "IL", "naics": "562112", "type": "public"},
    {"name": "Burgerville",           "state": "OR", "naics": "722513", "type": "private"},
]


def _get_existing_runs(min_quality=6.0):
    """Return set of company names that already have high-quality runs."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT LOWER(company_name) FROM research_runs "
        "WHERE status = 'completed' AND overall_quality_score >= %s",
        (min_quality,)
    )
    names = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return names


def _start_run(company):
    """Start a research run via the agent module and return run details."""
    from scripts.research.agent import run_research

    conn = get_connection()
    cur = conn.cursor()

    # Create the research_runs record
    cur.execute(
        """INSERT INTO research_runs
           (company_name, company_state, industry_naics, company_type, status, created_at)
           VALUES (%s, %s, %s, %s, 'pending', NOW())
           RETURNING id""",
        (company["name"], company["state"], company["naics"], company["type"])
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    start_time = time.time()
    try:
        run_research(run_id)
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"run_id": run_id, "status": "failed", "error": str(e), "duration": time.time() - start_time}

    duration = time.time() - start_time

    # Fetch results
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT status, overall_quality_score, total_tools_called FROM research_runs WHERE id = %s",
        (run_id,)
    )
    row = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM research_facts WHERE run_id = %s", (run_id,))
    fact_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return {
        "run_id": run_id,
        "status": row[0] if row else "unknown",
        "quality": row[1] if row else None,
        "tools_called": row[2] if row else 0,
        "facts": fact_count,
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(description="Run 20 gold standard research dossiers")
    parser.add_argument("--start-at", type=int, default=1, help="Start from company N (1-indexed)")
    parser.add_argument("--resume", action="store_true", help="Skip companies with existing high-quality runs")
    parser.add_argument("--dry-run", action="store_true", help="Print the list without running")
    parser.add_argument("--output", default="gold_standard_results.csv", help="Output CSV filename")
    parser.add_argument("--max-failures", type=int, default=3, help="Halt after N consecutive failures (0=disabled)")
    args = parser.parse_args()

    existing = _get_existing_runs() if args.resume else set()

    print("Gold Standard Research Batch")
    print(f"{'=' * 60}")
    print(f"Companies: {len(GOLD_STANDARD_COMPANIES)}")
    print(f"Starting at: #{args.start_at}")
    if args.resume:
        print(f"Skipping {len(existing)} companies with existing runs")
    print()

    results = []
    api_stats_before = get_api_call_stats()
    consecutive_failures = 0
    max_consecutive_failures = args.max_failures

    for i, company in enumerate(GOLD_STANDARD_COMPANIES, 1):
        if i < args.start_at:
            continue

        name = company["name"]
        if args.resume and name.lower() in existing:
            print(f"[{i:2d}/20] {name} -- SKIP (existing run)")
            continue

        if args.dry_run:
            print(f"[{i:2d}/20] {name} ({company['state']}, {company['naics']}, {company['type']})")
            continue

        print(f"[{i:2d}/20] {name} ({company['state']})...", end=" ", flush=True)

        result = _start_run(company)
        result["company"] = name
        result["state"] = company["state"]
        result["naics"] = company["naics"]
        results.append(result)

        status = result["status"]
        quality = result.get("quality")
        facts = result.get("facts", 0)
        dur = result.get("duration", 0)
        q_str = f"{quality:.1f}" if quality else "N/A"
        print(f"{status} | quality={q_str} | facts={facts} | {dur:.0f}s")

        if status == "completed":
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if max_consecutive_failures > 0 and consecutive_failures >= max_consecutive_failures:
                print(f"\n*** CIRCUIT BREAKER: {consecutive_failures} consecutive failures. Halting. ***")
                break

    if args.dry_run:
        return

    # API call summary
    api_stats_after = get_api_call_stats()
    brave_calls = api_stats_after["brave_search_calls"] - api_stats_before["brave_search_calls"]
    ce_calls = api_stats_after["company_enrich_calls"] - api_stats_before["company_enrich_calls"]

    print()
    print(f"{'=' * 60}")
    print(f"Completed: {len(results)} runs")
    completed = [r for r in results if r["status"] == "completed"]
    if completed:
        avg_q = sum(r["quality"] for r in completed if r["quality"]) / len(completed)
        avg_facts = sum(r["facts"] for r in completed) / len(completed)
        total_dur = sum(r["duration"] for r in completed)
        print(f"Avg quality: {avg_q:.2f}")
        print(f"Avg facts: {avg_facts:.0f}")
        print(f"Total time: {total_dur:.0f}s ({total_dur/60:.1f}m)")
    print(f"API calls -- Brave: {brave_calls}, CompanyEnrich: {ce_calls}")

    # Write CSV
    if results:
        csv_path = os.path.join(_project_root, args.output)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["company", "state", "naics", "run_id", "status", "quality", "tools_called", "facts", "duration"])
            writer.writeheader()
            writer.writerows(results)
        print(f"Results saved to {csv_path}")


if __name__ == "__main__":
    main()
