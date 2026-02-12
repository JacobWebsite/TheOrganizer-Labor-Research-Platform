"""
990 National Match Phase 5: Match 990 filers to F7 employers (from 0% to >2%).

Steps:
  0. Create national_990_f7_matches table
  1. EIN through crosswalk (990 EIN -> crosswalk EIN -> F7)
  2. EIN through Mergent (990 EIN -> Mergent EIN -> matched_f7_employer_id)
  3. Name + state exact match
  4. Fuzzy name + state (pg_trgm sim >= 0.60)
  5. Address matching
  6. Update crosswalk with new 990 EINs

Usage: py scripts/etl/match_990_national.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection


def ts():
    return datetime.now().strftime('%H:%M:%S')


def step0_create_table(cur, conn):
    """Create national_990_f7_matches audit table."""
    print(f"[{ts()}] Step 0: Creating national_990_f7_matches table...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS national_990_f7_matches (
            n990_id INTEGER NOT NULL,
            ein VARCHAR(20),
            f7_employer_id TEXT NOT NULL,
            match_method VARCHAR(50) NOT NULL,
            match_confidence NUMERIC(4,2) DEFAULT 0.50,
            match_source VARCHAR(50) DEFAULT 'PHASE5',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_n990_f7_matches_n990
        ON national_990_f7_matches(n990_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_n990_f7_matches_f7
        ON national_990_f7_matches(f7_employer_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_n990_f7_matches_ein
        ON national_990_f7_matches(ein)
    """)
    conn.commit()
    print("  national_990_f7_matches table created/verified.")


def normalize_ein(ein_expr):
    """SQL expression to normalize EIN: strip dashes, LPAD to 9 digits."""
    return f"LPAD(REPLACE({ein_expr}, '-', ''), 9, '0')"


def tier1_ein_crosswalk(cur, conn):
    """Tier 1: 990 EIN -> crosswalk EIN -> F7."""
    print(f"\n[{ts()}] Tier 1: EIN through Crosswalk")
    print("-" * 60)

    cur.execute(f"""
        INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (n.id)
            n.id,
            n.ein,
            c.f7_employer_id,
            'EIN_CROSSWALK',
            0.95,
            'PHASE5'
        FROM national_990_filers n
        JOIN corporate_identifier_crosswalk c
            ON {normalize_ein('n.ein')} = {normalize_ein('c.ein')}
        WHERE n.ein IS NOT NULL
          AND n.ein != ''
          AND c.ein IS NOT NULL
          AND c.ein != ''
          AND c.f7_employer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM national_990_f7_matches m WHERE m.n990_id = n.id
          )
        ORDER BY n.id, c.f7_employer_id
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  EIN_CROSSWALK: {matched:,}")
    return matched


def tier2_ein_mergent(cur, conn):
    """Tier 2: 990 EIN -> Mergent EIN -> matched_f7_employer_id."""
    print(f"\n[{ts()}] Tier 2: EIN through Mergent")
    print("-" * 60)

    cur.execute(f"""
        INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (n.id)
            n.id,
            n.ein,
            me.matched_f7_employer_id,
            'EIN_MERGENT',
            0.90,
            'PHASE5'
        FROM national_990_filers n
        JOIN mergent_employers me
            ON {normalize_ein('n.ein')} = {normalize_ein('me.ein')}
        WHERE n.ein IS NOT NULL
          AND n.ein != ''
          AND me.ein IS NOT NULL
          AND me.ein != ''
          AND me.matched_f7_employer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM national_990_f7_matches m WHERE m.n990_id = n.id
          )
        ORDER BY n.id, me.matched_f7_employer_id
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  EIN_MERGENT: {matched:,}")
    return matched


def tier3_name_state_exact(cur, conn):
    """Tier 3: Exact name_normalized + state match."""
    print(f"\n[{ts()}] Tier 3: Name + State Exact")
    print("-" * 60)

    cur.execute("""
        INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (n.id)
            n.id,
            n.ein,
            f.employer_id,
            'NAME_STATE_EXACT',
            0.85,
            'PHASE5'
        FROM national_990_filers n
        JOIN f7_employers_deduped f
            ON n.name_normalized = f.employer_name_aggressive
            AND n.state = f.state
        WHERE n.name_normalized IS NOT NULL
          AND n.name_normalized != ''
          AND NOT EXISTS (
              SELECT 1 FROM national_990_f7_matches m WHERE m.n990_id = n.id
          )
        ORDER BY n.id, f.filing_count DESC
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  NAME_STATE_EXACT: {matched:,}")
    return matched


def tier4_fuzzy_name_state(cur, conn):
    """Tier 4: Fuzzy name + state (pg_trgm sim >= 0.60)."""
    print(f"\n[{ts()}] Tier 4: Fuzzy Name + State")
    print("-" * 60)

    # Process state-by-state for performance
    cur.execute("""
        SELECT DISTINCT state FROM national_990_filers
        WHERE state IS NOT NULL AND name_normalized IS NOT NULL AND name_normalized != ''
        ORDER BY state
    """)
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states...")

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (n.id)
                n.id,
                n.ein,
                f.employer_id,
                'FUZZY_NAME_STATE',
                ROUND(similarity(n.name_normalized, f.employer_name_aggressive)::numeric, 2),
                'PHASE5'
            FROM national_990_filers n
            JOIN f7_employers_deduped f
                ON n.state = f.state
                AND f.state = %s
                AND n.state = %s
                AND similarity(n.name_normalized, f.employer_name_aggressive) >= 0.60
            WHERE n.name_normalized IS NOT NULL
              AND n.name_normalized != ''
              AND NOT EXISTS (
                  SELECT 1 FROM national_990_f7_matches m WHERE m.n990_id = n.id
              )
            ORDER BY n.id,
                similarity(n.name_normalized, f.employer_name_aggressive) DESC
        """, (state, state))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 100:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (total: {total_matched:,})")

    print(f"  Tier 4 total: {total_matched:,}")
    return total_matched


def tier5_address(cur, conn):
    """Tier 5: Normalized address + city + state matching."""
    print(f"\n[{ts()}] Tier 5: Address Matching")
    print("-" * 60)

    cur.execute("""
        INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (n.id)
            n.id,
            n.ein,
            f.employer_id,
            'ADDRESS_CITY_STATE',
            0.75,
            'PHASE5'
        FROM national_990_filers n
        JOIN f7_employers_deduped f
            ON n.state = f.state
            AND n.city = UPPER(TRIM(f.city))
            AND LENGTH(TRIM(COALESCE(n.street_address, ''))) > 5
            AND LENGTH(TRIM(COALESCE(f.street, ''))) > 5
            AND normalize_address(n.street_address) = normalize_address(f.street)
        WHERE n.street_address IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM national_990_f7_matches m WHERE m.n990_id = n.id
          )
        ORDER BY n.id, f.filing_count DESC
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  ADDRESS_CITY_STATE: {matched:,}")
    return matched


def step2_update_crosswalk(cur, conn):
    """Update corporate_identifier_crosswalk with new 990 EINs."""
    print(f"\n[{ts()}] Updating crosswalk with 990 EINs...")

    # Update existing crosswalk rows that lack EIN
    cur.execute(f"""
        UPDATE corporate_identifier_crosswalk c
        SET ein = n.ein
        FROM national_990_f7_matches m
        JOIN national_990_filers n ON m.n990_id = n.id
        WHERE c.f7_employer_id = m.f7_employer_id
          AND (c.ein IS NULL OR c.ein = '')
          AND n.ein IS NOT NULL
          AND n.ein != ''
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"  Existing crosswalk rows updated with EIN: {updated:,}")

    # Insert new crosswalk rows for matched F7 employers not yet in crosswalk
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk (f7_employer_id, ein)
        SELECT DISTINCT m.f7_employer_id, n.ein
        FROM national_990_f7_matches m
        JOIN national_990_filers n ON m.n990_id = n.id
        WHERE n.ein IS NOT NULL
          AND n.ein != ''
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c
              WHERE c.f7_employer_id = m.f7_employer_id
          )
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f"  New crosswalk rows inserted: {inserted:,}")


def spot_check(cur, method, n=10):
    """Print sample matches for visual validation."""
    print(f"\n  Spot-check ({method}, {n} samples):")
    cur.execute("""
        SELECT n.business_name, f.employer_name, m.match_confidence, n.state, n.ein
        FROM national_990_f7_matches m
        JOIN national_990_filers n ON m.n990_id = n.id
        JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
        WHERE m.match_method = %s
        ORDER BY RANDOM()
        LIMIT %s
    """, (method, n))
    for row in cur.fetchall():
        src = (row[0] or '')[:30]
        tgt = (row[1] or '')[:30]
        print(f"    {src:<30s} -> {tgt:<30s} conf={row[2]} st={row[3]} ein={row[4]}")


def print_summary(cur):
    """Print final summary statistics."""
    cur.execute("SELECT COUNT(*) FROM national_990_f7_matches")
    total_matches = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM national_990_filers")
    total_filers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM national_990_f7_matches")
    unique_f7 = cur.fetchone()[0]

    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(MIN(match_confidence)::numeric, 2),
               ROUND(AVG(match_confidence)::numeric, 2),
               ROUND(MAX(match_confidence)::numeric, 2)
        FROM national_990_f7_matches
        GROUP BY match_method
        ORDER BY cnt DESC
    """)
    methods = cur.fetchall()

    print("\n" + "=" * 70)
    print("990 NATIONAL MATCH - FINAL RESULTS")
    print("=" * 70)
    print(f"Total matches: {total_matches:,} / {total_filers:,} filers ({100*total_matches/total_filers:.1f}%)")
    print(f"Unique F7 employers matched: {unique_f7:,}")

    print("\nMatches by method:")
    print(f"  {'Method':<25s} {'Count':>10s} {'Min':>6s} {'Avg':>6s} {'Max':>6s}")
    print(f"  {'-'*25} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")
    for row in methods:
        print(f"  {row[0]:<25s} {row[1]:>10,} {row[2]:>6} {row[3]:>6} {row[4]:>6}")

    # State distribution
    print("\nTop 10 states:")
    cur.execute("""
        SELECT n.state, COUNT(*) as cnt
        FROM national_990_f7_matches m
        JOIN national_990_filers n ON m.n990_id = n.id
        GROUP BY n.state
        ORDER BY cnt DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<4s} {row[1]:>8,}")

    # Duplicate check
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT n990_id, COUNT(*)
            FROM national_990_f7_matches
            GROUP BY n990_id
            HAVING COUNT(*) > 1
        ) d
    """)
    dupes = cur.fetchone()[0]
    print(f"\nDuplicate n990_ids: {dupes}")
    if dupes > 0:
        print("  WARNING: duplicates found -- investigate!")


def main():
    print("=" * 70)
    print("990 NATIONAL MATCH - F7 EMPLOYER MATCHING")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    # Check national_990_filers exists
    cur.execute("SELECT COUNT(*) FROM national_990_filers")
    total_filers = cur.fetchone()[0]
    if total_filers == 0:
        print("ERROR: national_990_filers is empty. Run load_national_990.py first.")
        conn.close()
        return
    print(f"\nTotal 990 filers: {total_filers:,}")

    # Step 0: Create table
    step0_create_table(cur, conn)

    # Check if already populated (idempotent)
    cur.execute("SELECT COUNT(*) FROM national_990_f7_matches")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  national_990_f7_matches already has {existing:,} rows.")
        print("  To re-run, TRUNCATE national_990_f7_matches first.")
        print_summary(cur)
        conn.close()
        return

    # Run tiers
    total = 0

    n = tier1_ein_crosswalk(cur, conn)
    total += n
    if n > 0:
        spot_check(cur, 'EIN_CROSSWALK')

    n = tier2_ein_mergent(cur, conn)
    total += n
    if n > 0:
        spot_check(cur, 'EIN_MERGENT')

    n = tier3_name_state_exact(cur, conn)
    total += n
    if n > 0:
        spot_check(cur, 'NAME_STATE_EXACT')

    n = tier4_fuzzy_name_state(cur, conn)
    total += n
    if n > 0:
        spot_check(cur, 'FUZZY_NAME_STATE')

    n = tier5_address(cur, conn)
    total += n
    if n > 0:
        spot_check(cur, 'ADDRESS_CITY_STATE')

    print(f"\n  Total matches: {total:,}")

    # Update crosswalk
    step2_update_crosswalk(cur, conn)

    # Summary
    print_summary(cur)

    conn.close()
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
