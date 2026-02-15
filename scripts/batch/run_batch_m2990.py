"""
Batch run: mergent_to_990 and mergent_to_nlrb matching scenarios.
Full run (no limit). Uses custom pipeline with only fast tiers (EIN + Normalized + Address).
Skips Aggressive tier for 990 (too slow with 37K target records without trigram index).
"""

import sys
import os
import time
import logging
# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

import builtins
_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _orig_print(*args, **kwargs)

# Add project root to path
sys.path.insert(0, r"C:\Users\jakew\Downloads\labor-data-project")

from db_config import get_connection
from scripts.matching.pipeline import MatchPipeline
from scripts.matching.config import TIER_NAMES, get_scenario
from scripts.matching.matchers.exact import EINMatcher, NormalizedMatcher, AggressiveMatcher
from scripts.matching.matchers.address import AddressMatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_one(conn, scenario_name, skip_aggressive=False):
    print("=" * 60)
    print("Scenario: %s" % scenario_name)
    if skip_aggressive:
        print("  (skipping AGGRESSIVE tier for speed)")
    print("=" * 60)

    t0 = time.time()

    pipeline = MatchPipeline(conn, scenario=scenario_name, skip_fuzzy=True)

    # Optionally remove aggressive matcher for speed
    if skip_aggressive:
        pipeline.matchers = [m for m in pipeline.matchers
                             if not isinstance(m, AggressiveMatcher)]
        print("  Active matchers: %s" % [type(m).__name__ for m in pipeline.matchers])

    def progress(processed, total, matched):
        if processed % 2000 == 0:
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            print("  [%s] %d / %d processed (%d matched) - %.0f rec/s" % (
                scenario_name, processed, total, matched, rate))

    stats = pipeline.run_scenario(batch_size=1000, progress_callback=progress)

    elapsed = time.time() - t0

    print("")
    print("Results for %s:" % scenario_name)
    print("  Total source:  %d" % stats.total_source)
    print("  Total matched: %d" % stats.total_matched)
    print("  Match rate:    %.1f%%" % stats.match_rate)
    print("  Elapsed:       %.1f seconds" % elapsed)
    print("")
    print("  By tier:")
    for tier_num in sorted(stats.by_tier.keys()):
        tier_name = TIER_NAMES.get(tier_num, "TIER_%d" % tier_num)
        count = stats.by_tier[tier_num]
        print("    %-15s %d" % (tier_name, count))
    print("")
    print("  By method:")
    for method, count in sorted(stats.by_method.items(), key=lambda x: -x[1]):
        print("    %-15s %d" % (method, count))
    print("")

    # Show a few sample matches
    print("  Sample matches (first 5):")
    for r in stats.results[:5]:
        tname = r.target_name[:40] if r.target_name else "?"
        sname = r.source_name[:40]
        print("    %s -> %s [%s, %.2f]" % (sname, tname, r.method, r.score))
    print("")

    return stats


def main():
    print("Connecting to database...")
    conn = get_connection()
    print("Connected.")

    # Skip aggressive tier for both: target tables are large (37K for 990, ~16K employers in NLRB)
    # and no trigram index on target. EIN + Normalized capture the vast majority of real matches.
    scenarios = [
        ("mergent_to_990", True),    # skip aggressive
        ("mergent_to_nlrb", True),   # skip aggressive
    ]
    all_stats = {}

    for scenario_name, skip_agg in scenarios:
        try:
            stats = run_one(conn, scenario_name, skip_aggressive=skip_agg)
            all_stats[scenario_name] = stats
        except Exception as e:
            print("ERROR running %s: %s" % (scenario_name, e))
            import traceback
            traceback.print_exc()
            conn.rollback()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, stats in all_stats.items():
        print("  %-25s %d / %d matched (%.1f%%)" % (
            name, stats.total_matched, stats.total_source, stats.match_rate))

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
