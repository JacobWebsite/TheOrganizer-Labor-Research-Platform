"""
Run mergent_to_f7 matching scenario - full run (skip fuzzy).
Matches mergent_employers -> f7_employers_deduped using 4-tier pipeline.
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def main():
    conn = get_connection()

    print("=" * 60)
    print("SCENARIO: mergent_to_f7 (full run, skip fuzzy)")
    print("=" * 60)

    start = time.time()

    def progress(processed, total, matched):
        if processed % 2000 == 0 or processed == total:
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            print("  Processed %d / %d (%d matched) - %.0f rec/s" % (
                processed, total, matched, rate))

    pipeline = MatchPipeline(conn, scenario="mergent_to_f7", skip_fuzzy=True)
    stats = pipeline.run_scenario(batch_size=1000, progress_callback=progress)

    elapsed = time.time() - start

    print("")
    print("=" * 60)
    print("RESULTS: mergent_to_f7")
    print("=" * 60)
    print("  Total source records: %d" % stats.total_source)
    print("  Total matched:        %d" % stats.total_matched)
    print("  Match rate:           %.1f%%" % stats.match_rate)
    print("  Elapsed:              %.1f seconds" % elapsed)
    print("")
    print("  Tier breakdown:")
    for tier_num in sorted(stats.by_tier.keys()):
        method_name = stats.by_method
        # Use by_method dict for labels
        print("    Tier %d: %d matches" % (tier_num, stats.by_tier[tier_num]))
    print("")
    print("  Method breakdown:")
    for method, count in sorted(stats.by_method.items(), key=lambda x: -x[1]):
        print("    %-15s %d" % (method, count))

    # Show a few sample matches from each tier
    print("")
    print("  Sample matches (up to 3 per method):")
    by_method = {}
    for r in stats.results:
        if r.method not in by_method:
            by_method[r.method] = []
        if len(by_method[r.method]) < 3:
            by_method[r.method].append(r)

    for method in ["EIN", "NORMALIZED", "ADDRESS", "AGGRESSIVE"]:
        if method in by_method:
            print("    --- %s ---" % method)
            for r in by_method[method]:
                src = r.source_name[:40] if r.source_name else "?"
                tgt = r.target_name[:40] if r.target_name else "?"
                print("      %s -> %s (score=%.2f)" % (src, tgt, r.score))

    conn.close()
    print("")
    print("Done.")


if __name__ == "__main__":
    main()
