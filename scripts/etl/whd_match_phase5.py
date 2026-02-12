"""
WHD Match Phase 5: Improve WHD->F7 match rate from ~4.8% to >10%.

Steps:
  0. Create whd_f7_matches audit table
  1. Migrate existing matches (name+city+state, name+state)
  2. Add normalized columns to whd_cases
  3. Tier 3: Trade/Legal name cross-match
  4. Tier 4: Mergent bridge
  5. Tier 5: Address matching
  6. Tier 6: pg_trgm fuzzy (name sim >= 0.55, same state)
  7. Re-aggregate WHD violation data onto F7 and Mergent

Usage: py scripts/etl/whd_match_phase5.py
"""

import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

# Legal suffixes for normalization
LEGAL_SUFFIXES = re.compile(
    r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|'
    r'assoc|association|assn|pllc|pc|pa|dba|group|holdings|enterprises|'
    r'services|international|intl|national|natl)\b\.?',
    re.IGNORECASE
)
STRIP_CHARS = re.compile(r'[^a-z0-9 ]')


def ts():
    return datetime.now().strftime('%H:%M:%S')


def normalize_name(name):
    """Normalize employer name: lowercase, strip legal suffixes, extra spaces."""
    if not name:
        return ''
    name = name.lower().strip()
    name = STRIP_CHARS.sub(' ', name)
    name = LEGAL_SUFFIXES.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def step0_create_table(cur, conn):
    """Create whd_f7_matches audit table."""
    print(f"[{ts()}] Step 0: Creating whd_f7_matches table...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS whd_f7_matches (
            case_id VARCHAR(50) NOT NULL,
            f7_employer_id TEXT NOT NULL,
            match_method VARCHAR(50) NOT NULL,
            match_confidence NUMERIC(4,2) DEFAULT 0.50,
            match_source VARCHAR(50) DEFAULT 'PHASE5',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_whd_f7_matches_case
        ON whd_f7_matches(case_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whd_f7_matches_f7
        ON whd_f7_matches(f7_employer_id)
    """)
    conn.commit()
    print("  whd_f7_matches table created/verified.")


def step1_migrate_existing(cur, conn):
    """Migrate existing name-based matches into whd_f7_matches."""
    print(f"\n[{ts()}] Step 1: Migrating existing matches...")

    # Check if table already has data (idempotent)
    cur.execute("SELECT COUNT(*) FROM whd_f7_matches")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  whd_f7_matches already has {existing:,} rows, skipping migration.")
        return existing

    # Tier 1: name + city + state (HIGH confidence)
    print("  Tier 1: name_normalized + state + city...")
    cur.execute("""
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (w.case_id)
            w.case_id,
            f.employer_id,
            'NAME_CITY_STATE',
            0.90,
            'MIGRATION'
        FROM whd_cases w
        JOIN f7_employers_deduped f
            ON w.name_normalized = f.employer_name_aggressive
            AND w.state = f.state
            AND UPPER(TRIM(w.city)) = UPPER(TRIM(f.city))
        WHERE w.name_normalized IS NOT NULL
          AND w.name_normalized != ''
        ORDER BY w.case_id, f.filing_count DESC
    """)
    tier1 = cur.rowcount
    conn.commit()
    print(f"    NAME_CITY_STATE: {tier1:,}")

    # Tier 2: name + state only (MEDIUM confidence, unmatched only)
    print("  Tier 2: name_normalized + state...")
    cur.execute("""
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (w.case_id)
            w.case_id,
            f.employer_id,
            'NAME_STATE',
            0.80,
            'MIGRATION'
        FROM whd_cases w
        JOIN f7_employers_deduped f
            ON w.name_normalized = f.employer_name_aggressive
            AND w.state = f.state
        WHERE w.name_normalized IS NOT NULL
          AND w.name_normalized != ''
          AND NOT EXISTS (
              SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
          )
        ORDER BY w.case_id, f.filing_count DESC
    """)
    tier2 = cur.rowcount
    conn.commit()
    print(f"    NAME_STATE: {tier2:,}")

    total = tier1 + tier2
    print(f"  Migration total: {total:,}")
    return total


def step2_normalize_columns(cur, conn):
    """Add and populate normalized trade/legal name columns on whd_cases."""
    print(f"\n[{ts()}] Step 2: Adding normalized name columns...")

    cur.execute("ALTER TABLE whd_cases ADD COLUMN IF NOT EXISTS trade_name_normalized TEXT")
    cur.execute("ALTER TABLE whd_cases ADD COLUMN IF NOT EXISTS legal_name_normalized TEXT")
    conn.commit()

    # Check if already populated
    cur.execute("SELECT COUNT(*) FROM whd_cases WHERE trade_name_normalized IS NOT NULL")
    already_done = cur.fetchone()[0]
    if already_done > 100000:
        print(f"  Already populated ({already_done:,} rows), skipping.")
        return

    print("  Populating trade_name_normalized...")
    cur.execute("""
        UPDATE whd_cases SET trade_name_normalized =
            LOWER(TRIM(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(trade_name,
                            E'\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|assoc|association|assn|pllc|pc|pa|dba|group|holdings|enterprises|services|international|intl|national|natl)\\b\\.?',
                            '', 'gi'),
                        E'[^a-z0-9 ]', ' ', 'gi'),
                    E'\\s+', ' ', 'g')
            ))
        WHERE trade_name IS NOT NULL AND trade_name != ''
    """)
    trade_updated = cur.rowcount
    conn.commit()
    print(f"    Updated: {trade_updated:,}")

    print("  Populating legal_name_normalized...")
    cur.execute("""
        UPDATE whd_cases SET legal_name_normalized =
            LOWER(TRIM(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(legal_name,
                            E'\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|assoc|association|assn|pllc|pc|pa|dba|group|holdings|enterprises|services|international|intl|national|natl)\\b\\.?',
                            '', 'gi'),
                        E'[^a-z0-9 ]', ' ', 'gi'),
                    E'\\s+', ' ', 'g')
            ))
        WHERE legal_name IS NOT NULL AND legal_name != ''
    """)
    legal_updated = cur.rowcount
    conn.commit()
    print(f"    Updated: {legal_updated:,}")

    # Create indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_whd_trade_norm ON whd_cases(trade_name_normalized) WHERE trade_name_normalized IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_whd_legal_norm ON whd_cases(legal_name_normalized) WHERE legal_name_normalized IS NOT NULL")
    conn.commit()
    print("  Indexes created.")


def tier3_trade_legal_cross(cur, conn):
    """Tier 3: Match using trade_name and legal_name when they differ from name_normalized."""
    print(f"\n[{ts()}] Tier 3: Trade/Legal Name Cross-Match")
    print("-" * 60)

    # 3a: legal_name_normalized (when different from name_normalized)
    print("  3a: legal_name -> F7...")
    cur.execute("""
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (w.case_id)
            w.case_id,
            f.employer_id,
            'LEGAL_NAME_STATE',
            0.82,
            'PHASE5'
        FROM whd_cases w
        JOIN f7_employers_deduped f
            ON w.legal_name_normalized = f.employer_name_aggressive
            AND w.state = f.state
        WHERE w.legal_name_normalized IS NOT NULL
          AND w.legal_name_normalized != ''
          AND w.legal_name_normalized != w.name_normalized
          AND NOT EXISTS (
              SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
          )
        ORDER BY w.case_id, f.filing_count DESC
    """)
    legal_matches = cur.rowcount
    conn.commit()
    print(f"    LEGAL_NAME_STATE: {legal_matches:,}")

    # 3b: trade_name_normalized (when different from name_normalized)
    print("  3b: trade_name -> F7...")
    cur.execute("""
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (w.case_id)
            w.case_id,
            f.employer_id,
            'TRADE_NAME_STATE',
            0.78,
            'PHASE5'
        FROM whd_cases w
        JOIN f7_employers_deduped f
            ON w.trade_name_normalized = f.employer_name_aggressive
            AND w.state = f.state
        WHERE w.trade_name_normalized IS NOT NULL
          AND w.trade_name_normalized != ''
          AND w.trade_name_normalized != w.name_normalized
          AND NOT EXISTS (
              SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
          )
        ORDER BY w.case_id, f.filing_count DESC
    """)
    trade_matches = cur.rowcount
    conn.commit()
    print(f"    TRADE_NAME_STATE: {trade_matches:,}")

    total = legal_matches + trade_matches
    print(f"  Tier 3 total: {total:,}")
    return total


def tier4_mergent_bridge(cur, conn):
    """Tier 4: WHD -> Mergent (fuzzy name+state) -> crosswalk -> F7."""
    print(f"\n[{ts()}] Tier 4: Mergent Bridge")
    print("-" * 60)

    # Build temp bridge table (same as OSHA script)
    cur.execute("DROP TABLE IF EXISTS tmp_whd_mergent_bridge")
    cur.execute("""
        CREATE TEMP TABLE tmp_whd_mergent_bridge AS
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

    cur.execute("CREATE INDEX idx_tmp_whd_bridge_state ON tmp_whd_mergent_bridge(state)")
    cur.execute("CREATE INDEX idx_tmp_whd_bridge_trgm ON tmp_whd_mergent_bridge USING gin (mergent_name gin_trgm_ops)")
    conn.commit()
    print(f"  Bridge table: {bridge_count:,} rows")

    # Process state-by-state
    cur.execute("SELECT DISTINCT state FROM tmp_whd_mergent_bridge ORDER BY state")
    states = [r[0] for r in cur.fetchall()]

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (w.case_id)
                w.case_id,
                b.f7_employer_id,
                'MERGENT_BRIDGE',
                GREATEST(0.55, ROUND(similarity(w.name_normalized, b.mergent_name)::numeric, 2)),
                'PHASE5'
            FROM whd_cases w
            JOIN tmp_whd_mergent_bridge b
                ON w.state = b.state
                AND b.state = %s
                AND w.state = %s
                AND similarity(w.name_normalized, b.mergent_name) >= 0.50
            WHERE w.name_normalized IS NOT NULL
              AND w.name_normalized != ''
              AND NOT EXISTS (
                  SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
              )
            ORDER BY w.case_id,
                similarity(w.name_normalized, b.mergent_name) DESC
        """, (state, state))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 100:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (total: {total_matched:,})")

    cur.execute("DROP TABLE IF EXISTS tmp_whd_mergent_bridge")
    conn.commit()

    print(f"  Tier 4 total: {total_matched:,}")
    return total_matched


def tier5_address(cur, conn):
    """Tier 5: Address + city + state matching."""
    print(f"\n[{ts()}] Tier 5: Address Matching")
    print("-" * 60)

    cur.execute("""
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (w.case_id)
            w.case_id,
            f.employer_id,
            'ADDRESS_CITY_STATE',
            0.72,
            'PHASE5'
        FROM whd_cases w
        JOIN f7_employers_deduped f
            ON w.state = f.state
            AND UPPER(TRIM(w.city)) = UPPER(TRIM(f.city))
            AND LENGTH(TRIM(COALESCE(w.street_address, ''))) > 5
            AND LENGTH(TRIM(COALESCE(f.street, ''))) > 5
            AND normalize_address(w.street_address) = normalize_address(f.street)
        WHERE w.street_address IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
          )
        ORDER BY w.case_id, f.filing_count DESC
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  ADDRESS_CITY_STATE: {matched:,}")
    return matched


def tier6_fuzzy(cur, conn):
    """Tier 6: pg_trgm fuzzy name + state (sim >= 0.55)."""
    print(f"\n[{ts()}] Tier 6: pg_trgm Fuzzy Name + State")
    print("-" * 60)

    # Process state-by-state for performance
    cur.execute("""
        SELECT DISTINCT state FROM whd_cases
        WHERE state IS NOT NULL AND name_normalized IS NOT NULL AND name_normalized != ''
        ORDER BY state
    """)
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states...")

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (w.case_id)
                w.case_id,
                f.employer_id,
                'FUZZY_NAME_STATE',
                ROUND(similarity(w.name_normalized, f.employer_name_aggressive)::numeric, 2),
                'PHASE5'
            FROM whd_cases w
            JOIN f7_employers_deduped f
                ON w.state = f.state
                AND f.state = %s
                AND w.state = %s
                AND similarity(w.name_normalized, f.employer_name_aggressive) >= 0.55
            WHERE w.name_normalized IS NOT NULL
              AND w.name_normalized != ''
              AND NOT EXISTS (
                  SELECT 1 FROM whd_f7_matches m WHERE m.case_id = w.case_id
              )
            ORDER BY w.case_id,
                similarity(w.name_normalized, f.employer_name_aggressive) DESC
        """, (state, state))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 100:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (total: {total_matched:,})")

    print(f"  Tier 6 total: {total_matched:,}")
    return total_matched


def step3_reaggregate(cur, conn):
    """Re-aggregate WHD violation data onto F7 and Mergent from whd_f7_matches."""
    print(f"\n[{ts()}] Step 3: Re-aggregating WHD data onto employer tables...")

    # Reset F7 WHD columns
    cur.execute("""
        UPDATE f7_employers_deduped SET
            whd_violation_count = NULL,
            whd_backwages = NULL,
            whd_employees_violated = NULL,
            whd_penalties = NULL,
            whd_child_labor = NULL,
            whd_repeat_violator = NULL
    """)
    conn.commit()

    # Aggregate from whd_f7_matches -> whd_cases -> f7
    cur.execute("""
        WITH whd_agg AS (
            SELECT
                m.f7_employer_id,
                COUNT(DISTINCT w.case_id) as case_count,
                SUM(COALESCE(w.total_violations, 0)) as total_violations,
                SUM(COALESCE(w.backwages_amount, 0)) as total_backwages,
                SUM(COALESCE(w.employees_violated, 0)) as total_employees_violated,
                SUM(COALESCE(w.civil_penalties, 0)) as total_penalties,
                SUM(COALESCE(w.flsa_child_labor_violations, 0)) as child_labor,
                BOOL_OR(COALESCE(w.flsa_repeat_violator, FALSE)) as is_repeat
            FROM whd_f7_matches m
            JOIN whd_cases w ON m.case_id = w.case_id
            GROUP BY m.f7_employer_id
        )
        UPDATE f7_employers_deduped f
        SET whd_violation_count = a.case_count,
            whd_backwages = a.total_backwages,
            whd_employees_violated = a.total_employees_violated,
            whd_penalties = a.total_penalties,
            whd_child_labor = a.child_labor,
            whd_repeat_violator = a.is_repeat
        FROM whd_agg a
        WHERE f.employer_id = a.f7_employer_id
    """)
    f7_updated = cur.rowcount
    conn.commit()
    print(f"  F7 employers updated: {f7_updated:,}")

    # Reset and update Mergent WHD columns
    cur.execute("""
        UPDATE mergent_employers SET
            whd_violation_count = NULL,
            whd_backwages = NULL,
            whd_employees_violated = NULL,
            whd_match_method = NULL,
            whd_penalties = NULL,
            whd_child_labor = NULL,
            whd_repeat_violator = NULL
    """)
    conn.commit()

    # Mergent gets WHD data through F7 link
    cur.execute("""
        UPDATE mergent_employers me
        SET whd_violation_count = f.whd_violation_count,
            whd_backwages = f.whd_backwages,
            whd_employees_violated = f.whd_employees_violated,
            whd_penalties = f.whd_penalties,
            whd_child_labor = f.whd_child_labor,
            whd_repeat_violator = f.whd_repeat_violator,
            whd_match_method = 'WHD_PHASE5_VIA_F7'
        FROM f7_employers_deduped f
        WHERE me.matched_f7_employer_id = f.employer_id
          AND f.whd_violation_count IS NOT NULL
    """)
    mergent_via_f7 = cur.rowcount
    conn.commit()
    print(f"  Mergent updated via F7 link: {mergent_via_f7:,}")

    # Also match Mergent directly (name+state)
    cur.execute("""
        WITH whd_state_agg AS (
            SELECT name_normalized, state,
                COUNT(*) as case_count,
                SUM(COALESCE(total_violations, 0)) as total_violations,
                SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                SUM(COALESCE(employees_violated, 0)) as total_employees_violated,
                SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor,
                BOOL_OR(COALESCE(flsa_repeat_violator, FALSE)) as is_repeat
            FROM whd_cases
            WHERE name_normalized IS NOT NULL AND name_normalized != ''
            GROUP BY name_normalized, state
        )
        UPDATE mergent_employers me
        SET whd_violation_count = w.case_count,
            whd_backwages = w.total_backwages,
            whd_employees_violated = w.total_employees_violated,
            whd_penalties = w.total_penalties,
            whd_child_labor = w.child_labor,
            whd_repeat_violator = w.is_repeat,
            whd_match_method = 'WHD_NATIONAL_DIRECT'
        FROM whd_state_agg w
        WHERE me.company_name_normalized = w.name_normalized
          AND me.state = w.state
          AND me.whd_violation_count IS NULL
    """)
    mergent_direct = cur.rowcount
    conn.commit()
    print(f"  Mergent updated via direct name match: {mergent_direct:,}")


def spot_check(cur, method, n=10):
    """Print sample matches for visual validation."""
    print(f"\n  Spot-check ({method}, {n} samples):")
    cur.execute("""
        SELECT w.name_normalized, f.employer_name, m.match_confidence, w.state
        FROM whd_f7_matches m
        JOIN whd_cases w ON m.case_id = w.case_id
        JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
        WHERE m.match_method = %s
        ORDER BY RANDOM()
        LIMIT %s
    """, (method, n))
    for row in cur.fetchall():
        src = (row[0] or '')[:35]
        tgt = (row[1] or '')[:35]
        print(f"    {src:<35s} -> {tgt:<35s} conf={row[2]} st={row[3]}")


def print_summary(cur):
    """Print final summary statistics."""
    cur.execute("SELECT COUNT(*) FROM whd_f7_matches")
    total_matches = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM whd_cases")
    total_cases = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM whd_f7_matches")
    unique_f7 = cur.fetchone()[0]

    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(MIN(match_confidence)::numeric, 2),
               ROUND(AVG(match_confidence)::numeric, 2),
               ROUND(MAX(match_confidence)::numeric, 2)
        FROM whd_f7_matches
        GROUP BY match_method
        ORDER BY cnt DESC
    """)
    methods = cur.fetchall()

    print("\n" + "=" * 70)
    print("WHD MATCH PHASE 5 - FINAL RESULTS")
    print("=" * 70)
    print(f"Total matches: {total_matches:,} / {total_cases:,} cases ({100*total_matches/total_cases:.1f}%)")
    print(f"Unique F7 employers matched: {unique_f7:,}")

    print("\nMatches by method:")
    print(f"  {'Method':<25s} {'Count':>10s} {'Min':>6s} {'Avg':>6s} {'Max':>6s}")
    print(f"  {'-'*25} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")
    for row in methods:
        print(f"  {row[0]:<25s} {row[1]:>10,} {row[2]:>6} {row[3]:>6} {row[4]:>6}")

    # State distribution
    print("\nTop 10 states:")
    cur.execute("""
        SELECT w.state, COUNT(*) as cnt
        FROM whd_f7_matches m
        JOIN whd_cases w ON m.case_id = w.case_id
        GROUP BY w.state
        ORDER BY cnt DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<4s} {row[1]:>8,}")

    # Duplicate check
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT case_id, COUNT(*)
            FROM whd_f7_matches
            GROUP BY case_id
            HAVING COUNT(*) > 1
        ) d
    """)
    dupes = cur.fetchone()[0]
    print(f"\nDuplicate case_ids: {dupes}")
    if dupes > 0:
        print("  WARNING: duplicates found -- investigate!")

    # F7 coverage
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL")
    f7_with_whd = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    f7_total = cur.fetchone()[0]
    print(f"\nF7 employers with WHD data: {f7_with_whd:,} / {f7_total:,} ({100*f7_with_whd/f7_total:.1f}%)")


def main():
    print("=" * 70)
    print("WHD MATCH PHASE 5 - MATCH RATE IMPROVEMENT")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    # Baseline
    cur.execute("SELECT COUNT(*) FROM whd_cases")
    total_cases = cur.fetchone()[0]
    print(f"\nTotal WHD cases: {total_cases:,}")

    # Step 0: Create table
    step0_create_table(cur, conn)

    # Step 1: Migrate existing
    migrated = step1_migrate_existing(cur, conn)

    # Step 2: Normalize columns
    step2_normalize_columns(cur, conn)

    # New tiers
    total_new = 0

    n = tier3_trade_legal_cross(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'LEGAL_NAME_STATE')

    n = tier4_mergent_bridge(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'MERGENT_BRIDGE')

    n = tier5_address(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'ADDRESS_CITY_STATE')

    n = tier6_fuzzy(cur, conn)
    total_new += n
    if n > 0:
        spot_check(cur, 'FUZZY_NAME_STATE')

    print(f"\n  Total new matches (Phase 5): {total_new:,}")

    # Step 3: Re-aggregate
    step3_reaggregate(cur, conn)

    # Summary
    print_summary(cur)

    conn.close()
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
