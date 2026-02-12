"""
OSHA Match Phase 5: Improve OSHA->F7 match rate from ~7.9% to >15%.

New tiers (on top of existing ~79,981 matches):
  A: Corporate Parent Bridge (Mergent -> crosswalk -> F7)
  B: Enhanced Address (street+state, normalized address+ZIP3)
  C: Facility Marker Stripping (remove #123, STORE 456, WAREHOUSE, etc.)
  D: State + NAICS Wider Fuzzy (sim >= 0.40, no ZIP constraint)

All INSERT into osha_f7_matches with NOT EXISTS guard on establishment_id.

Usage: py scripts/etl/osha_match_phase5.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection


def ts():
    return datetime.now().strftime('%H:%M:%S')


def get_baseline(cur):
    """Get current OSHA match counts."""
    cur.execute("SELECT COUNT(*) FROM osha_f7_matches")
    matched_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")
    matched_estabs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM osha_establishments")
    total_estabs = cur.fetchone()[0]
    return matched_rows, matched_estabs, total_estabs


def create_strip_facility_function(cur, conn):
    """Create PL/pgSQL function to strip facility markers from names."""
    print(f"[{ts()}] Creating strip_facility_markers() function...")
    cur.execute("""
        CREATE OR REPLACE FUNCTION strip_facility_markers(name TEXT)
        RETURNS TEXT AS $$
        DECLARE
            result TEXT;
        BEGIN
            result := UPPER(COALESCE(name, ''));
            -- Remove unit/store numbers: #123, STORE 456, UNIT 7, etc.
            result := REGEXP_REPLACE(result, E'\\s*#\\d+', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mSTORE\\s+\\d+\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mUNIT\\s+\\d+\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mSHOP\\s+\\d+\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mLOCATION\\s+\\d+\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mSITE\\s+\\d+\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mFACILITY\\s+\\d+\\M', '', 'g');
            -- Remove facility type words
            result := REGEXP_REPLACE(result, E'\\mWAREHOUSE\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mPLANT\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mDIVISION\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mBRANCH\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mDEPOT\\M', '', 'g');
            result := REGEXP_REPLACE(result, E'\\mTERMINAL\\M', '', 'g');
            -- Remove DBA prefix
            result := REGEXP_REPLACE(result, E'\\mD/?B/?A\\s+', '', 'g');
            -- Remove trailing numeric IDs (e.g. "WALMART 1234")
            result := REGEXP_REPLACE(result, E'\\s+\\d{2,}$', '', 'g');
            -- Collapse spaces
            result := REGEXP_REPLACE(result, E'\\s+', ' ', 'g');
            result := TRIM(result);
            RETURN result;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)
    conn.commit()
    print(f"  strip_facility_markers() created.")


def create_mergent_bridge_temp(cur, conn):
    """Build temp table of Mergent employers with F7 links via crosswalk or direct match."""
    print(f"[{ts()}] Building Mergent bridge temp table...")

    cur.execute("DROP TABLE IF EXISTS tmp_mergent_f7_bridge")
    cur.execute("""
        CREATE TEMP TABLE tmp_mergent_f7_bridge AS
        -- Path 1: Mergent -> crosswalk -> F7
        SELECT DISTINCT
            m.company_name_normalized AS mergent_name,
            m.state,
            c.f7_employer_id
        FROM mergent_employers m
        JOIN corporate_identifier_crosswalk c
            ON m.duns = c.mergent_duns
        WHERE c.f7_employer_id IS NOT NULL
          AND m.company_name_normalized IS NOT NULL
          AND m.state IS NOT NULL
          AND m.company_name_normalized != ''

        UNION

        -- Path 2: Mergent -> matched_f7_employer_id (direct link)
        SELECT DISTINCT
            m.company_name_normalized AS mergent_name,
            m.state,
            m.matched_f7_employer_id AS f7_employer_id
        FROM mergent_employers m
        WHERE m.matched_f7_employer_id IS NOT NULL
          AND m.company_name_normalized IS NOT NULL
          AND m.state IS NOT NULL
          AND m.company_name_normalized != ''
    """)
    bridge_count = cur.rowcount
    conn.commit()

    # Create indexes for performance
    cur.execute("CREATE INDEX idx_tmp_bridge_state ON tmp_mergent_f7_bridge(state)")
    cur.execute("CREATE INDEX idx_tmp_bridge_name_trgm ON tmp_mergent_f7_bridge USING gin (mergent_name gin_trgm_ops)")
    conn.commit()

    print(f"  Bridge table: {bridge_count:,} rows (Mergent->F7 links)")
    return bridge_count


def tier_a_mergent_bridge(cur, conn):
    """Tier A: Match OSHA estabs to F7 through Mergent bridge.

    Process state-by-state to keep each query manageable (~20K OSHA x ~200 bridge per state).
    """
    print(f"\n[{ts()}] Tier A: Corporate Parent Bridge (Mergent)")
    print("-" * 60)

    # Get list of states with bridge entries
    cur.execute("SELECT DISTINCT state FROM tmp_mergent_f7_bridge ORDER BY state")
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states...")

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (o.establishment_id)
                o.establishment_id,
                b.f7_employer_id,
                'MERGENT_BRIDGE',
                GREATEST(0.60, ROUND(similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    b.mergent_name
                )::numeric, 2)),
                'MERGENT_BRIDGE'
            FROM osha_establishments o
            JOIN tmp_mergent_f7_bridge b
                ON o.site_state = b.state
                AND b.state = %s
                AND o.site_state = %s
                AND similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    b.mergent_name
                ) >= 0.50
            WHERE NOT EXISTS (
                SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
            )
            ORDER BY o.establishment_id,
                similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    b.mergent_name
                ) DESC
        """, (state, state))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 100:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} matches (running total: {total_matched:,})")

    print(f"  Tier A total: {total_matched:,}")
    return total_matched


def tier_b_address(cur, conn):
    """Tier B: Enhanced address matching."""
    print(f"\n[{ts()}] Tier B: Enhanced Address Matching")
    print("-" * 60)

    # Sub-tier B1: Street number + first street word + state
    print("  B1: Street number + first street word + state...")
    cur.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'STREET_NAME_STATE',
            GREATEST(0.55, ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            )::numeric, 2)),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND LENGTH(TRIM(COALESCE(o.site_address, ''))) > 5
            AND LENGTH(TRIM(COALESCE(f.street, ''))) > 5
            -- Match street number (first token of normalized address)
            AND SPLIT_PART(normalize_address(o.site_address), ' ', 1)
                = SPLIT_PART(normalize_address(f.street), ' ', 1)
            -- Match first street word (second token)
            AND SPLIT_PART(normalize_address(o.site_address), ' ', 2)
                = SPLIT_PART(normalize_address(f.street), ' ', 2)
            AND SPLIT_PART(normalize_address(o.site_address), ' ', 1) ~ '^[0-9]'
            -- Name similarity >= 0.25 as sanity check
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) >= 0.25
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id,
            similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) DESC
    """)
    matched_b1 = cur.rowcount
    conn.commit()
    print(f"    Street+name+state matches: {matched_b1:,}")

    # Sub-tier B2: Normalized address + state + ZIP prefix (3 digits)
    print("  B2: Normalized address + state + ZIP3...")
    cur.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'ADDRESS_STATE_ZIP3',
            0.70,
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND LEFT(o.site_zip, 3) = LEFT(f.zip, 3)
            AND LENGTH(o.site_zip) >= 3
            AND LENGTH(f.zip) >= 3
            AND LENGTH(TRIM(COALESCE(o.site_address, ''))) > 5
            AND LENGTH(TRIM(COALESCE(f.street, ''))) > 5
            AND normalize_address(o.site_address) = normalize_address(f.street)
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id, f.filing_count DESC
    """)
    matched_b2 = cur.rowcount
    conn.commit()
    print(f"    Address+state+ZIP3 matches: {matched_b2:,}")

    total = matched_b1 + matched_b2
    print(f"  Tier B total: {total:,}")
    return total


def tier_c_stripped_facility(cur, conn):
    """Tier C: Match after stripping facility markers from OSHA names."""
    print(f"\n[{ts()}] Tier C: Facility Marker Stripping")
    print("-" * 60)

    cur.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'STRIPPED_FACILITY_MATCH',
            GREATEST(0.60, ROUND(similarity(
                strip_facility_markers(COALESCE(o.estab_name_normalized, o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            )::numeric, 2)),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND UPPER(TRIM(o.site_city)) = UPPER(TRIM(f.city))
            AND similarity(
                strip_facility_markers(COALESCE(o.estab_name_normalized, o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) >= 0.55
            -- Only when stripping changes the name (otherwise prior tiers would have caught it)
            AND strip_facility_markers(COALESCE(o.estab_name_normalized, o.estab_name))
                != COALESCE(o.estab_name_normalized, UPPER(o.estab_name))
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id,
            similarity(
                strip_facility_markers(COALESCE(o.estab_name_normalized, o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) DESC
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  Stripped facility matches: {matched:,}")
    return matched


def tier_d_state_naics_fuzzy(cur, conn):
    """Tier D: State + NAICS + wider fuzzy (no ZIP constraint, sim >= 0.40)."""
    print(f"\n[{ts()}] Tier D: State + NAICS Wider Fuzzy")
    print("-" * 60)

    # Process state-by-state for performance (avoids massive cartesian)
    cur.execute("""
        SELECT DISTINCT site_state FROM osha_establishments
        WHERE site_state IS NOT NULL AND naics_code IS NOT NULL AND LENGTH(naics_code) >= 2
        ORDER BY site_state
    """)
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states...")

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (o.establishment_id)
                o.establishment_id,
                f.employer_id,
                'STATE_NAICS_FUZZY',
                GREATEST(0.55, ROUND(similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
                )::numeric, 2)),
                'F7_DIRECT'
            FROM osha_establishments o
            JOIN f7_employers_deduped f
                ON o.site_state = f.state
                AND f.state = %s
                AND o.site_state = %s
                AND LEFT(o.naics_code, 2) = f.naics
                AND f.naics IS NOT NULL
                AND similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
                ) >= 0.40
            WHERE NOT EXISTS (
                SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
            )
            ORDER BY o.establishment_id,
                similarity(
                    COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                    COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
                ) DESC
        """, (state, state))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 500:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (running total: {total_matched:,})")

    print(f"  Tier D total: {total_matched:,}")
    return total_matched


def spot_check(cur, method, n=10):
    """Print sample matches for visual validation."""
    print(f"\n  Spot-check ({method}, {n} samples):")
    cur.execute("""
        SELECT o.estab_name, f.employer_name, m.match_confidence, o.site_state
        FROM osha_f7_matches m
        JOIN osha_establishments o ON m.establishment_id = o.establishment_id
        JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
        WHERE m.match_method = %s
        ORDER BY RANDOM()
        LIMIT %s
    """, (method, n))
    for row in cur.fetchall():
        src = (row[0] or '')[:35]
        tgt = (row[1] or '')[:35]
        print(f"    {src:<35s} -> {tgt:<35s} conf={row[2]} st={row[3]}")


def print_summary(cur, before_rows, before_estabs, total_estabs):
    """Print final summary statistics."""
    cur.execute("SELECT COUNT(*) FROM osha_f7_matches")
    after_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")
    after_estabs = cur.fetchone()[0]

    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(MIN(match_confidence)::numeric, 2) as min_conf,
               ROUND(AVG(match_confidence)::numeric, 2) as avg_conf,
               ROUND(MAX(match_confidence)::numeric, 2) as max_conf
        FROM osha_f7_matches
        GROUP BY match_method
        ORDER BY cnt DESC
    """)
    methods = cur.fetchall()

    print("\n" + "=" * 70)
    print("OSHA MATCH PHASE 5 - FINAL RESULTS")
    print("=" * 70)
    print(f"Before: {before_estabs:,} estabs / {total_estabs:,} total ({100*before_estabs/total_estabs:.1f}%)")
    print(f"After:  {after_estabs:,} estabs / {total_estabs:,} total ({100*after_estabs/total_estabs:.1f}%)")
    print(f"New match rows: {after_rows - before_rows:,}")
    print(f"New matched estabs: {after_estabs - before_estabs:,}")
    print(f"Improvement: +{100*(after_estabs - before_estabs)/total_estabs:.1f}pp")

    print("\nMatches by method:")
    print(f"  {'Method':<25s} {'Count':>10s} {'Min':>6s} {'Avg':>6s} {'Max':>6s}")
    print(f"  {'-'*25} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")
    for row in methods:
        print(f"  {row[0]:<25s} {row[1]:>10,} {row[2]:>6} {row[3]:>6} {row[4]:>6}")

    # State distribution (new matches only)
    new_methods = ('MERGENT_BRIDGE', 'STREET_NAME_STATE', 'ADDRESS_STATE_ZIP3',
                   'STRIPPED_FACILITY_MATCH', 'STATE_NAICS_FUZZY')
    cur.execute("""
        SELECT o.site_state, COUNT(*) as cnt
        FROM osha_f7_matches m
        JOIN osha_establishments o ON m.establishment_id = o.establishment_id
        WHERE m.match_method = ANY(%s)
        GROUP BY o.site_state
        ORDER BY cnt DESC
        LIMIT 10
    """, (list(new_methods),))
    print("\nTop 10 states (Phase 5 matches):")
    for row in cur.fetchall():
        print(f"  {row[0]:<4s} {row[1]:>8,}")

    # Duplicate check
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT establishment_id, COUNT(*)
            FROM osha_f7_matches
            GROUP BY establishment_id
            HAVING COUNT(*) > 1
        ) d
    """)
    dupes = cur.fetchone()[0]
    print(f"\nDuplicate establishment_ids: {dupes}")
    if dupes > 0:
        print("  WARNING: duplicates found -- investigate!")


def main():
    print("=" * 70)
    print("OSHA MATCH PHASE 5 - MATCH RATE IMPROVEMENT")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    # Baseline
    before_rows, before_estabs, total_estabs = get_baseline(cur)
    print(f"\nBaseline: {before_estabs:,} / {total_estabs:,} ({100*before_estabs/total_estabs:.1f}%)")
    print(f"Target:   {int(total_estabs * 0.15):,} (15%)")
    print(f"Need:     {max(0, int(total_estabs * 0.15) - before_estabs):,} more matches")

    # Create helper functions (normalize_address should already exist)
    create_strip_facility_function(cur, conn)

    # Build Mergent bridge temp table
    create_mergent_bridge_temp(cur, conn)

    # Run tiers
    total_new = 0

    n = tier_a_mergent_bridge(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'MERGENT_BRIDGE')

    n = tier_b_address(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'STREET_NAME_STATE')

    n = tier_c_stripped_facility(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'STRIPPED_FACILITY_MATCH')

    n = tier_d_state_naics_fuzzy(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'STATE_NAICS_FUZZY')

    # Summary
    print_summary(cur, before_rows, before_estabs, total_estabs)

    # Cleanup temp table
    cur.execute("DROP TABLE IF EXISTS tmp_mergent_f7_bridge")
    conn.commit()

    conn.close()
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
