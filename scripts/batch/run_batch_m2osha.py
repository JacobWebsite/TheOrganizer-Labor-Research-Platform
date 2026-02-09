"""
Run mergent_to_osha matching scenario in full (no limit, skip fuzzy).
Matches 14,240 Mergent employers against 1M+ OSHA establishments.
"""

import sys
import os
import time

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from scripts.matching.pipeline import MatchPipeline
from scripts.matching.config import TIER_NAMES


def progress(processed, total, matched):
    if processed % 1000 == 0 or processed == total:
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        pct = (processed / total * 100) if total > 0 else 0
        print(
            "  Processed %d / %d (%.1f%%) - %d matched - %.0f rec/sec"
            % (processed, total, pct, matched, rate),
            flush=True,
        )


if __name__ == "__main__":
    print("=" * 60)
    print("MERGENT -> OSHA MATCHING (FULL RUN, SKIP FUZZY)")
    print("=" * 60)

    conn = psycopg2.connect(
        host="localhost",
        dbname="olms_multiyear",
        user="postgres",
        password="os.environ.get('DB_PASSWORD', '')",
    )

    # Quick count of source and target
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mergent_employers")
    src_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM osha_establishments")
    tgt_count = cur.fetchone()[0]
    cur.close()

    print("Source (mergent_employers): %d" % src_count)
    print("Target (osha_establishments): %d" % tgt_count)
    print("-" * 60)

    pipeline = MatchPipeline(conn, scenario="mergent_to_osha", skip_fuzzy=True)

    start_time = time.time()
    stats = pipeline.run_scenario(batch_size=500, progress_callback=progress)
    elapsed = time.time() - start_time

    print("")
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print("Total source:  %d" % stats.total_source)
    print("Total matched: %d" % stats.total_matched)
    print("Match rate:    %.1f%%" % stats.match_rate)
    print("Elapsed:       %.1f seconds" % elapsed)
    print("")

    print("By Tier:")
    for tier_num in sorted(stats.by_tier.keys()):
        tier_name = TIER_NAMES.get(tier_num, "TIER_%d" % tier_num)
        count = stats.by_tier[tier_num]
        print("  %s (Tier %d): %d" % (tier_name, tier_num, count))

    print("")
    print("By Method:")
    for method, count in sorted(stats.by_method.items(), key=lambda x: -x[1]):
        print("  %s: %d" % (method, count))

    # Show some sample matches
    print("")
    print("Sample matches (first 10):")
    for i, r in enumerate(stats.results[:10]):
        print(
            "  [%s] %s -> %s (score=%.2f)"
            % (r.method, r.source_name, r.target_name, r.score)
        )

    conn.close()
    print("")
    print("Done.")
