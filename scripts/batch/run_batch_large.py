"""
Run large matching scenarios: nlrb_to_f7 and osha_to_f7
Full runs with --skip-fuzzy, no limit.
"""

import os
import sys

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"
import time
import logging
import psycopg2
from datetime import datetime

sys.path.insert(0, r"C:\Users\jakew\Downloads\labor-data-project")
from scripts.matching import MatchPipeline
from scripts.matching.config import TIER_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def connect():
    return psycopg2.connect(
        host="localhost",
        dbname="olms_multiyear",
        user="postgres",
        password="Juniordog33!"
    )


def progress_fn(processed, total, matched):
    if processed % 5000 == 0 and processed > 0:
        rate = (matched / processed * 100) if processed else 0
        elapsed = time.time() - progress_fn.start_time
        rps = processed / elapsed if elapsed > 0 else 0
        remaining = (total - processed) / rps if rps > 0 else 0
        print(
            f"  [{datetime.now().strftime('%H:%M:%S')}] "
            f"{processed:,}/{total:,} processed | "
            f"{matched:,} matched ({rate:.1f}%) | "
            f"{rps:.0f} rec/sec | "
            f"~{remaining/60:.0f} min remaining",
            flush=True
        )


def run_scenario(scenario_name):
    print(f"\n{'='*70}")
    print(f"  SCENARIO: {scenario_name}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    conn = connect()
    try:
        pipeline = MatchPipeline(conn, scenario=scenario_name, skip_fuzzy=True)

        progress_fn.start_time = time.time()
        stats = pipeline.run_scenario(
            batch_size=1000,
            limit=None,
            progress_callback=progress_fn
        )

        elapsed = time.time() - progress_fn.start_time

        print(f"\n  RESULTS for {scenario_name}:")
        print(f"  Total source:  {stats.total_source:,}")
        print(f"  Total matched: {stats.total_matched:,}")
        print(f"  Match rate:    {stats.match_rate:.1f}%")
        print(f"  Elapsed:       {elapsed/60:.1f} minutes ({elapsed:.0f} sec)")
        print(f"  Speed:         {stats.total_source/elapsed:.0f} records/sec")
        print(f"\n  By tier:")
        for tier_num, count in sorted(stats.by_tier.items()):
            tier_name = TIER_NAMES.get(tier_num, f"TIER_{tier_num}")
            pct = count / stats.total_matched * 100 if stats.total_matched else 0
            print(f"    {tier_name:15s}: {count:,} ({pct:.1f}%)")

        print(f"\n  By method:")
        for method, count in sorted(stats.by_method.items()):
            pct = count / stats.total_matched * 100 if stats.total_matched else 0
            print(f"    {method:15s}: {count:,} ({pct:.1f}%)")

        # Show a few sample matches per tier
        print(f"\n  Sample matches:")
        shown_tiers = set()
        for r in stats.results[:200]:
            if r.tier not in shown_tiers:
                shown_tiers.add(r.tier)
                tier_name = TIER_NAMES.get(r.tier, f"TIER_{r.tier}")
                src = (r.source_name or "")[:40]
                tgt = (r.target_name or "")[:40]
                print(f"    [{tier_name}] '{src}' -> '{tgt}' (score={r.score:.3f})")

        return stats

    finally:
        conn.close()


if __name__ == "__main__":
    print("Large Matching Scenario Runner")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_stats = {}

    # Run nlrb_to_f7 first (smaller, ~30K records)
    stats1 = run_scenario("nlrb_to_f7")
    all_stats["nlrb_to_f7"] = stats1

    # Run osha_to_f7 (large, ~1M records)
    stats2 = run_scenario("osha_to_f7")
    all_stats["osha_to_f7"] = stats2

    # Final summary
    print(f"\n{'='*70}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*70}")
    for name, s in all_stats.items():
        print(f"  {name:20s}: {s.total_matched:>8,} / {s.total_source:>10,} ({s.match_rate:.1f}%)")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
