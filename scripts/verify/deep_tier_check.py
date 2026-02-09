"""
Deep analysis of ADDRESS and AGGRESSIVE tier matches across multiple scenarios.
Also checks for the normalized name mismatch issue found in Tier 2.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from scripts.matching import MatchPipeline


def get_conn():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )


def section(title):
    print("")
    print("=" * 70)
    print(title)
    print("=" * 70)


def run_scenario_check(scenario_name, limit=500):
    """Run a scenario and report tier breakdown with samples."""
    section("Scenario: %s (limit %d)" % (scenario_name, limit))

    conn = get_conn()
    pipeline = MatchPipeline(conn, scenario=scenario_name, skip_fuzzy=True)
    stats = pipeline.run_scenario(limit=limit)

    tier_counts = {}
    tier_samples = {}
    for r in stats.results:
        tier_counts[r.method] = tier_counts.get(r.method, 0) + 1
        if r.method not in tier_samples:
            tier_samples[r.method] = []
        if len(tier_samples[r.method]) < 3:
            tier_samples[r.method].append(r)

    print("\nMatch rate: %d / %d (%.1f%%)" % (
        stats.total_matched, stats.total_source,
        100.0 * stats.total_matched / max(stats.total_source, 1)
    ))
    print("\nTier breakdown:")
    for method in ['EIN', 'NORMALIZED', 'ADDRESS', 'AGGRESSIVE']:
        cnt = tier_counts.get(method, 0)
        print("  %-12s: %d" % (method, cnt))

    # Show samples per tier
    for method, samples in sorted(tier_samples.items()):
        print("\n  --- %s samples ---" % method)
        for r in samples:
            meta = r.metadata or {}
            print("    Source: %s" % r.source_name)
            print("    Target: %s" % r.target_name)
            print("    Score:  %.3f" % r.score)
            if meta.get('source_address'):
                print("    Src Addr: %s" % meta['source_address'][:60])
            if meta.get('target_address'):
                print("    Tgt Addr: %s" % meta['target_address'][:60])
            # Quick quality check
            s_words = set(w.lower() for w in (r.source_name or '').split() if len(w) > 2)
            t_words = set(w.lower() for w in (r.target_name or '').split() if len(w) > 2)
            overlap = s_words & t_words
            if overlap:
                print("    Quality: GOOD (shared: %s)" % ', '.join(list(overlap)[:5]))
            else:
                print("    Quality: REVIEW (no word overlap)")
            print("")

    conn.close()
    return stats


def check_normalized_name_gap(cur):
    """Investigate why Tier 2 found 0 matches for mergent->F7."""
    section("INVESTIGATING: Why 0 normalized matches for mergent_to_f7?")

    # Check: what does company_name_normalized look like vs employer_name_aggressive?
    cur.execute("""
        SELECT m.company_name, m.company_name_normalized, m.state
        FROM mergent_employers m
        WHERE m.company_name_normalized IS NOT NULL
        LIMIT 5
    """)
    print("\nSample mergent normalized names:")
    for row in cur.fetchall():
        print("  '%s' -> normalized: '%s' (%s)" % row)

    cur.execute("""
        SELECT f.employer_name, f.employer_name_aggressive, f.state
        FROM f7_employers_deduped f
        WHERE f.state = 'NY' AND f.employer_name_aggressive IS NOT NULL
        LIMIT 5
    """)
    print("\nSample F7 aggressive names:")
    for row in cur.fetchall():
        print("  '%s' -> aggressive: '%s' (%s)" % row)

    # Check: are the normalizations done differently?
    # Try a known match: look for "Brooklyn Friends School" in both
    cur.execute("""
        SELECT company_name, company_name_normalized
        FROM mergent_employers
        WHERE company_name ILIKE '%%brooklyn friends%%'
    """)
    m_rows = cur.fetchall()
    cur.execute("""
        SELECT employer_name, employer_name_aggressive
        FROM f7_employers_deduped
        WHERE employer_name ILIKE '%%brooklyn friends%%'
    """)
    f_rows = cur.fetchall()

    print("\nTest case - 'Brooklyn Friends School':")
    for r in m_rows:
        print("  Mergent: '%s' -> normalized: '%s'" % r)
    for r in f_rows:
        print("  F7:      '%s' -> aggressive: '%s'" % r)

    # Count potential matches if we lowered both sides
    cur.execute("""
        SELECT COUNT(*)
        FROM mergent_employers m
        JOIN f7_employers_deduped f
            ON LOWER(TRIM(m.company_name_normalized)) = LOWER(TRIM(f.employer_name_aggressive))
            AND m.state = f.state
    """)
    count = cur.fetchone()[0]
    print("\nPotential normalized matches (LOWER+TRIM both sides): %d" % count)

    # Check if case difference is the issue
    cur.execute("""
        SELECT m.company_name_normalized, f.employer_name_aggressive
        FROM mergent_employers m
        JOIN f7_employers_deduped f
            ON LOWER(TRIM(m.company_name_normalized)) = LOWER(TRIM(f.employer_name_aggressive))
            AND m.state = f.state
        WHERE m.company_name_normalized != f.employer_name_aggressive
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        print("\nCase/whitespace differences found:")
        for r in rows:
            print("  Mergent: '%s'" % r[0])
            print("  F7:      '%s'" % r[1])
            print("")
    else:
        print("\nNo case differences found - normalization may be truly incompatible")

    # Direct exact match test
    cur.execute("""
        SELECT COUNT(*)
        FROM mergent_employers m
        JOIN f7_employers_deduped f
            ON m.company_name_normalized = f.employer_name_aggressive
            AND m.state = f.state
    """)
    exact_count = cur.fetchone()[0]
    print("Exact string matches (no LOWER/TRIM): %d" % exact_count)


def check_false_positive_patterns(cur):
    """Check for known false positive patterns."""
    section("FALSE POSITIVE PATTERN CHECK")

    # Pattern 1: Very generic names
    cur.execute("""
        SELECT employer_name_aggressive, state, COUNT(*) as cnt
        FROM f7_employers_deduped
        WHERE LENGTH(employer_name_aggressive) <= 5
          AND employer_name_aggressive IS NOT NULL
        GROUP BY employer_name_aggressive, state
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("\nGeneric/short F7 aggressive names with duplicates:")
    for r in rows:
        print("  '%s' (%s) -> %d records" % r)

    # Pattern 2: Common name prefixes
    cur.execute("""
        SELECT employer_name_aggressive, COUNT(*) as cnt
        FROM f7_employers_deduped
        WHERE employer_name_aggressive LIKE 'city %%'
           OR employer_name_aggressive LIKE 'town %%'
           OR employer_name_aggressive LIKE 'county %%'
           OR employer_name_aggressive LIKE 'village %%'
        GROUP BY employer_name_aggressive
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("\nGovernment entity name collisions:")
    for r in rows:
        print("  '%s' -> %d records" % r)


def main():
    # Run pipeline scenarios
    run_scenario_check("nlrb_to_f7", limit=2000)
    run_scenario_check("osha_to_f7", limit=2000)
    run_scenario_check("mergent_to_f7", limit=3000)

    # Database analysis
    conn = get_conn()
    cur = conn.cursor()
    check_normalized_name_gap(cur)
    check_false_positive_patterns(cur)
    cur.close()
    conn.close()

    section("DEEP CHECK COMPLETE")


if __name__ == "__main__":
    main()
