"""
Run fast matching scenarios: vr_to_f7, violations_to_mergent, contracts_to_990

These are smaller source tables that run quickly even without fuzzy matching.
"""

import sys
import os
import time
import logging

from db_config import get_connection
# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from scripts.matching import MatchPipeline
from scripts.matching.config import TIER_NAMES

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

SCENARIOS = ["vr_to_f7", "violations_to_mergent", "contracts_to_990"]


def run_all():
    conn = get_connection()

    all_results = {}

    for scenario_name in SCENARIOS:
        print("=" * 60)
        print("SCENARIO: %s" % scenario_name)
        print("=" * 60)

        start = time.time()

        pipeline = MatchPipeline(conn, scenario=scenario_name, skip_fuzzy=True)

        def progress(processed, total, matched):
            if processed % 5000 == 0:
                elapsed = time.time() - start
                print("  Progress: %d / %d (%d matched) - %.1fs" % (
                    processed, total, matched, elapsed))

        stats = pipeline.run_scenario(batch_size=1000, limit=None,
                                      progress_callback=progress)

        elapsed = time.time() - start

        print("")
        print("Results for %s:" % scenario_name)
        print("  Total source records: %d" % stats.total_source)
        print("  Total matched:        %d" % stats.total_matched)
        print("  Match rate:           %.1f%%" % stats.match_rate)
        print("  Time:                 %.1fs" % elapsed)
        print("")
        print("  Matches by tier:")
        for tier_num in sorted(stats.by_tier.keys()):
            tier_name = TIER_NAMES.get(tier_num, "TIER_%d" % tier_num)
            count = stats.by_tier[tier_num]
            print("    %-15s %d" % (tier_name, count))

        print("  Matches by method:")
        for method, count in sorted(stats.by_method.items()):
            print("    %-15s %d" % (method, count))

        print("")
        all_results[scenario_name] = stats

    # Summary
    print("=" * 60)
    print("SUMMARY - ALL FAST SCENARIOS")
    print("=" * 60)
    print("")
    print("%-25s %10s %10s %10s" % ("Scenario", "Source", "Matched", "Rate"))
    print("-" * 60)
    for name, stats in all_results.items():
        print("%-25s %10d %10d %9.1f%%" % (
            name, stats.total_source, stats.total_matched, stats.match_rate))
    print("-" * 60)
    total_src = sum(s.total_source for s in all_results.values())
    total_match = sum(s.total_matched for s in all_results.values())
    overall_rate = (total_match / total_src * 100) if total_src > 0 else 0
    print("%-25s %10d %10d %9.1f%%" % ("TOTAL", total_src, total_match, overall_rate))
    print("")

    conn.close()
    print("Done.")
    return all_results


if __name__ == "__main__":
    run_all()
