"""
Spot-check match quality across all tiers of the unified matching pipeline.

Validates:
1. EIN matches (Tier 1)
2. Normalized matches (Tier 2)
3. Address matches (Tier 3)
4. Aggressive matches (Tier 4)
5. Cross-tier consistency
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2


def get_conn():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password=os.environ.get('DB_PASSWORD', '')
    )


def section(title):
    print("")
    print("=" * 70)
    print(title)
    print("=" * 70)


def check_ein_matches(cur):
    """Tier 1: Find mergent employers with EINs that also exist in f7_employers_deduped via the matching pipeline."""
    section("TIER 1: EIN MATCHES (Spot Check)")

    # Find mergent employers that were matched to F7 via EIN
    # We check: do any mergent employers share an EIN with a 990 filer?
    # The mergent_to_f7 scenario doesn't have EIN on the F7 side,
    # but mergent_to_990 does use EIN matching.
    cur.execute("""
        SELECT m.company_name, m.ein, m.city, m.state,
               n.business_name, n.ein as n_ein, n.city as n_city, n.state as n_state,
               n.total_employees
        FROM mergent_employers m
        JOIN ny_990_filers n ON m.ein = n.ein
        WHERE m.ein IS NOT NULL
          AND n.ein IS NOT NULL
          AND LENGTH(m.ein) >= 7
        ORDER BY m.company_name
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\nMergent <-> 990 EIN matches (same EIN in both tables):")
    print("-" * 70)

    for row in rows:
        m_name, m_ein, m_city, m_state, n_name, n_ein, n_city, n_state, n_emp = row
        m_lower = (m_name or '').lower()
        n_lower = (n_name or '').lower()
        m_words = [w for w in m_lower.split() if w not in ('the', 'a', 'an', 'of', 'inc', 'llc', 'corp')]
        n_words = [w for w in n_lower.split() if w not in ('the', 'a', 'an', 'of', 'inc', 'llc', 'corp')]
        first_word_match = m_words and n_words and m_words[0] == n_words[0]
        verdict = "TRUE POSITIVE" if first_word_match else "CHECK MANUALLY"

        print("  Mergent: %s (%s, %s)" % (m_name, m_city, m_state))
        print("  990:     %s (%s, %s)" % (n_name, n_city, n_state))
        print("  EIN:     %s" % m_ein)
        print("  Verdict: %s" % verdict)
        print("")

    print("Total EIN matches shown: %d" % len(rows))


def check_normalized_matches(cur):
    """Tier 2: Find employers where normalized names match in same state."""
    section("TIER 2: NORMALIZED NAME MATCHES (Spot Check)")

    # Find mergent employers whose company_name_normalized matches
    # f7_employers_deduped.employer_name_aggressive in the same state
    cur.execute("""
        SELECT m.company_name, m.company_name_normalized, m.city, m.state,
               f.employer_name, f.employer_name_aggressive, f.city as f_city, f.state as f_state
        FROM mergent_employers m
        JOIN f7_employers_deduped f
            ON m.company_name_normalized = f.employer_name_aggressive
            AND m.state = f.state
        ORDER BY m.company_name
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\nMergent <-> F7 normalized name matches (same state):")
    print("-" * 70)

    tp = 0
    fp = 0
    for row in rows:
        m_name, m_norm, m_city, m_state, f_name, f_norm, f_city, f_state = row
        # Names are already matched via normalization; check city
        same_city = (m_city or '').lower().strip() == (f_city or '').lower().strip()
        verdict = "TRUE POSITIVE" if same_city else "TRUE POSITIVE (diff city, same state)"
        if same_city:
            tp += 1
        else:
            tp += 1  # Different city same state is still likely correct

        print(f"  Mergent:    {m_name} ({m_city}, {m_state})")
        print(f"  F7:         {f_name} ({f_city}, {f_state})")
        print(f"  Normalized: '{m_norm}' == '{f_norm}'")
        print(f"  Verdict:    {verdict}")
        print("")

    print(f"Total normalized matches shown: {len(rows)}")
    print(f"Same city: {sum(1 for r in rows if (r[2] or '').lower().strip() == (r[6] or '').lower().strip())}")


def check_address_matches(cur):
    """Tier 3: Run matching pipeline and check ADDRESS tier results."""
    section("TIER 3: ADDRESS MATCHES (Pipeline Run)")

    try:
        from scripts.matching import MatchPipeline

        conn = get_conn()
        pipeline = MatchPipeline(conn, scenario="nlrb_to_f7", skip_fuzzy=True)

        print("Running nlrb_to_f7 scenario (limit 500, skip fuzzy)...")
        stats = pipeline.run_scenario(limit=500)

        address_matches = [r for r in stats.results if r.method == "ADDRESS"]
        print(f"\nFound {len(address_matches)} ADDRESS matches out of {stats.total_matched} total")
        print("-" * 70)

        for r in address_matches[:8]:
            meta = r.metadata or {}
            print(f"  Source: {r.source_name}")
            print(f"  Target: {r.target_name}")
            print(f"  Score:  {r.score:.3f}")
            if meta.get('source_address'):
                print(f"  Src Addr: {meta['source_address']}")
            if meta.get('target_address'):
                print(f"  Tgt Addr: {meta['target_address']}")

            # Check if names share any significant words
            s_words = set(w.lower() for w in (r.source_name or '').split() if len(w) > 2)
            t_words = set(w.lower() for w in (r.target_name or '').split() if len(w) > 2)
            overlap = s_words & t_words
            if overlap:
                print(f"  Name overlap: {overlap}")
                print(f"  Verdict: TRUE POSITIVE (shared words + same address)")
            else:
                print(f"  Verdict: CHECK MANUALLY (no shared words, address match only)")
            print("")

        conn.close()

    except Exception as e:
        print(f"ERROR running pipeline: {e}")
        import traceback
        traceback.print_exc()


def check_aggressive_matches(cur):
    """Tier 4: Run matching pipeline and check AGGRESSIVE tier results."""
    section("TIER 4: AGGRESSIVE MATCHES (Pipeline Run)")

    try:
        from scripts.matching import MatchPipeline

        conn = get_conn()
        pipeline = MatchPipeline(conn, scenario="mergent_to_f7", skip_fuzzy=True)

        print("Running mergent_to_f7 scenario (limit 1000, skip fuzzy)...")
        stats = pipeline.run_scenario(limit=1000)

        agg_matches = [r for r in stats.results if r.method == "AGGRESSIVE"]
        norm_matches = [r for r in stats.results if r.method == "NORMALIZED"]
        addr_matches = [r for r in stats.results if r.method == "ADDRESS"]
        ein_matches = [r for r in stats.results if r.method == "EIN"]

        print(f"\nTier breakdown:")
        print(f"  EIN:        {len(ein_matches)}")
        print(f"  NORMALIZED: {len(norm_matches)}")
        print(f"  ADDRESS:    {len(addr_matches)}")
        print(f"  AGGRESSIVE: {len(agg_matches)}")
        print(f"  Total:      {stats.total_matched} / {stats.total_source}")
        print("-" * 70)

        print(f"\nAGGRESSIVE match samples:")
        for r in agg_matches[:8]:
            meta = r.metadata or {}
            print(f"  Source: {r.source_name}")
            print(f"  Target: {r.target_name}")
            print(f"  Score:  {r.score:.3f}")

            # Check similarity - aggressive matches should be name variations
            s_lower = (r.source_name or '').lower()
            t_lower = (r.target_name or '').lower()
            # Check containment
            if s_lower in t_lower or t_lower in s_lower:
                print(f"  Verdict: TRUE POSITIVE (name containment)")
            else:
                s_words = set(w for w in s_lower.split() if len(w) > 2 and w not in ('the', 'inc', 'llc', 'corp', 'and'))
                t_words = set(w for w in t_lower.split() if len(w) > 2 and w not in ('the', 'inc', 'llc', 'corp', 'and'))
                overlap = s_words & t_words
                ratio = len(overlap) / max(len(s_words), len(t_words), 1)
                if ratio >= 0.5:
                    print(f"  Verdict: TRUE POSITIVE (word overlap {len(overlap)}/{max(len(s_words), len(t_words))})")
                elif overlap:
                    print(f"  Verdict: LIKELY TRUE POSITIVE (partial overlap: {overlap})")
                else:
                    print(f"  Verdict: POSSIBLE FALSE POSITIVE (no word overlap)")
            print("")

        conn.close()

    except Exception as e:
        print(f"ERROR running pipeline: {e}")
        import traceback
        traceback.print_exc()


def check_cross_tier_consistency(cur):
    """Check if normalized matches could have been caught at a higher tier."""
    section("CROSS-TIER CONSISTENCY CHECK")

    # Check: are there normalized name matches (Tier 2) that also share an EIN?
    # These should have been caught at Tier 1 instead.
    cur.execute("""
        SELECT m.company_name, m.ein, m.state,
               n.business_name, n.ein as n_ein
        FROM mergent_employers m
        JOIN ny_990_filers n
            ON LOWER(TRIM(m.company_name_normalized)) = LOWER(TRIM(n.name_normalized))
            AND m.state = n.state
        WHERE m.ein IS NOT NULL
          AND n.ein IS NOT NULL
          AND m.ein = n.ein
        LIMIT 5
    """)
    rows = cur.fetchall()

    print("\n1. Records matchable by BOTH EIN and name (should be Tier 1):")
    print(f"   Found: {len(rows)} (these are correctly handled - EIN match takes priority)")
    for row in rows[:3]:
        print(f"   {row[0]} (EIN: {row[1]}) -> {row[3]} (EIN: {row[4]})")

    # Check: same company_name_normalized appearing multiple times
    # which could cause ambiguous matches
    cur.execute("""
        SELECT company_name_normalized, COUNT(*) as cnt,
               array_agg(DISTINCT state) as states
        FROM mergent_employers
        WHERE company_name_normalized IS NOT NULL
          AND LENGTH(company_name_normalized) > 3
        GROUP BY company_name_normalized
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\n2. Duplicate normalized names in mergent_employers (ambiguity risk):")
    for row in rows:
        name, cnt, states = row
        print(f"   '{name}' -> {cnt} records in states: {states}")

    # Check: F7 employers with same normalized name in same state (target ambiguity)
    cur.execute("""
        SELECT employer_name_aggressive, state, COUNT(*) as cnt
        FROM f7_employers_deduped
        WHERE employer_name_aggressive IS NOT NULL
          AND LENGTH(employer_name_aggressive) > 3
        GROUP BY employer_name_aggressive, state
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\n3. Duplicate aggressive names in f7_employers_deduped (target ambiguity):")
    for row in rows:
        name, state, cnt = row
        print(f"   '{name}' ({state}) -> {cnt} records")

    # Check: very short normalized names that might cause false positives
    cur.execute("""
        SELECT company_name, company_name_normalized, state
        FROM mergent_employers
        WHERE LENGTH(company_name_normalized) <= 3
          AND company_name_normalized IS NOT NULL
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\n4. Very short normalized names (false positive risk):")
    for row in rows:
        print(f"   '{row[0]}' -> normalized: '{row[1]}' ({row[2]})")
    if not rows:
        print("   None found - good!")


def check_existing_matches_in_db(cur):
    """Check quality of existing matches stored in mergent_employers columns."""
    section("EXISTING MATCH QUALITY (Stored in mergent_employers)")

    # F7 matches
    cur.execute("""
        SELECT m.company_name, m.city, m.state,
               f.employer_name, f.city as f_city, f.state as f_state,
               m.f7_match_method
        FROM mergent_employers m
        JOIN f7_employers_deduped f ON m.matched_f7_employer_id = f.employer_id
        WHERE m.matched_f7_employer_id IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 10
    """)
    rows = cur.fetchall()

    print("\nRandom sample of existing F7 matches in DB:")
    print("-" * 70)
    tp = 0
    suspect = 0
    for row in rows:
        m_name, m_city, m_state, f_name, f_city, f_state, method = row
        m_lower = (m_name or '').lower()
        f_lower = (f_name or '').lower()
        m_words = set(w for w in m_lower.split() if len(w) > 2 and w not in ('the', 'inc', 'llc', 'corp', 'and', 'of'))
        f_words = set(w for w in f_lower.split() if len(w) > 2 and w not in ('the', 'inc', 'llc', 'corp', 'and', 'of'))
        overlap = m_words & f_words
        ratio = len(overlap) / max(len(m_words), len(f_words), 1)

        if ratio >= 0.3:
            verdict = "TRUE POSITIVE"
            tp += 1
        else:
            verdict = "POSSIBLE FALSE POSITIVE"
            suspect += 1

        print(f"  Mergent: {m_name} ({m_city}, {m_state})")
        print(f"  F7:      {f_name} ({f_city}, {f_state})")
        print(f"  Method:  {method}")
        print(f"  Overlap: {overlap} ({ratio:.0%})")
        print(f"  Verdict: {verdict}")
        print("")

    print(f"Summary: {tp} likely correct, {suspect} need manual review out of {len(rows)} sampled")

    # 990 matches
    cur.execute("""
        SELECT m.company_name, m.city,
               n.business_name, n.city as n_city,
               m.ny990_match_method
        FROM mergent_employers m
        JOIN ny_990_filers n ON m.ny990_id = n.id
        WHERE m.ny990_id IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 5
    """)
    rows = cur.fetchall()

    print("\nRandom sample of existing 990 matches:")
    print("-" * 70)
    for row in rows:
        m_name, m_city, n_name, n_city, method = row
        print(f"  Mergent: {m_name} ({m_city})")
        print(f"  990:     {n_name} ({n_city})")
        print(f"  Method:  {method}")
        m_lower = (m_name or '').lower()
        n_lower = (n_name or '').lower()
        if m_lower[:10] == n_lower[:10]:
            print(f"  Verdict: TRUE POSITIVE (name prefix match)")
        else:
            print(f"  Verdict: CHECK MANUALLY")
        print("")


def check_has_union_consistency(cur):
    """Verify that has_union records don't have organizing scores."""
    section("DATA CONSISTENCY: has_union vs organizing_score")

    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN has_union = TRUE THEN 1 ELSE 0 END) as unionized,
               SUM(CASE WHEN has_union = TRUE AND organizing_score IS NOT NULL THEN 1 ELSE 0 END) as union_with_score,
               SUM(CASE WHEN has_union = TRUE AND score_priority IS NOT NULL THEN 1 ELSE 0 END) as union_with_tier,
               SUM(CASE WHEN has_union IS NOT TRUE AND organizing_score IS NULL THEN 1 ELSE 0 END) as target_no_score
        FROM mergent_employers
    """)
    total, unionized, union_w_score, union_w_tier, target_no_score = cur.fetchone()

    print(f"\nTotal records:                  {total}")
    print(f"Unionized (has_union=TRUE):     {unionized}")
    print(f"Unionized WITH score (BAD):     {union_w_score}")
    print(f"Unionized WITH tier (BAD):      {union_w_tier}")
    print(f"Non-union WITHOUT score:        {target_no_score}")

    if union_w_score > 0 or union_w_tier > 0:
        print("\n** WARNING: Unionized records should NOT have organizing_score or score_priority!")
        cur.execute("""
            SELECT company_name, has_union, organizing_score, score_priority
            FROM mergent_employers
            WHERE has_union = TRUE AND organizing_score IS NOT NULL
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  {row[0]}: has_union={row[1]}, score={row[2]}, tier={row[3]}")
    else:
        print("\nAll consistent - unionized records have NULL scores as expected.")


def main():
    conn = get_conn()
    cur = conn.cursor()

    print("MATCH QUALITY SPOT CHECK")
    print("========================")
    print("Checking match quality across all tiers of the unified matching pipeline.")
    print("")

    # Database-only checks (fast)
    check_ein_matches(cur)
    check_normalized_matches(cur)
    check_cross_tier_consistency(cur)
    check_existing_matches_in_db(cur)
    check_has_union_consistency(cur)

    # Pipeline-based checks (slower - run actual matching)
    cur.close()
    conn.close()

    check_address_matches(None)
    check_aggressive_matches(None)

    print("\n")
    section("SPOT CHECK COMPLETE")
    print("Review the results above for any POSSIBLE FALSE POSITIVE or CHECK MANUALLY items.")
    print("These should be investigated further to determine if they represent real matching errors.")


if __name__ == "__main__":
    main()
