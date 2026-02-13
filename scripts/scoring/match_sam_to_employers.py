"""
Match SAM.gov entities to F7 employers (multi-tier).

Tiers:
  A: Exact normalized name + state (confidence 0.95)
  B: Same city + state + pg_trgm % operator (GIN-indexed, confidence 0.80-0.95)
  C: Same state + NAICS 2-digit + pg_trgm % operator (confidence 0.55-0.80)
  D: DBA name exact + state (confidence 0.80)

CRITICAL: Uses pg_trgm % operator (GIN-indexed) instead of similarity() function
for candidate retrieval. similarity() causes full cross-joins that run 8+ hours
on large states. The % operator uses the GIN index and returns in seconds.

Post-match:
  - Update corporate_identifier_crosswalk (add sam_uei, cage, federal contractor flag)
  - NAICS enrichment (backfill 6-digit onto F7)
  - Summary + spot checks

Usage: py -u scripts/scoring/match_sam_to_employers.py
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection


def ts():
    return datetime.now().strftime('%H:%M:%S')


# ---------------------------------------------------------------------------
# Step 0: Create match table + ensure indexes
# ---------------------------------------------------------------------------

def step0_create_table(cur, conn):
    """Create sam_f7_matches table."""
    print(f"[{ts()}] Step 0: Creating sam_f7_matches table...")

    cur.execute("DROP TABLE IF EXISTS sam_f7_matches CASCADE")
    cur.execute("""
        CREATE TABLE sam_f7_matches (
            uei TEXT NOT NULL,
            f7_employer_id TEXT NOT NULL,
            match_method VARCHAR(50) NOT NULL,
            match_confidence NUMERIC(4,2) DEFAULT 0.50,
            match_source VARCHAR(50) DEFAULT 'SAM_PHASE1',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE UNIQUE INDEX idx_sam_f7_uei ON sam_f7_matches(uei)")
    cur.execute("CREATE INDEX idx_sam_f7_employer ON sam_f7_matches(f7_employer_id)")
    conn.commit()
    print("  sam_f7_matches table created.")

    # Ensure GIN trigram indexes exist on both sides
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sam_name_trgm
        ON sam_entities USING gin (name_aggressive gin_trgm_ops)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_f7_name_agg_trgm
        ON f7_employers_deduped USING gin (employer_name_aggressive gin_trgm_ops)
    """)
    conn.commit()
    print("  GIN trigram indexes verified on both tables.")

    # Set pg_trgm threshold for % operator
    cur.execute("SET pg_trgm.similarity_threshold = 0.55")
    conn.commit()


# ---------------------------------------------------------------------------
# Tier A: Exact normalized name + state
# ---------------------------------------------------------------------------

def tier_a_exact_name_state(cur, conn):
    """Tier A: Exact name match after normalization + same state.

    F7 stores employer_name_aggressive as UPPER with suffixes stripped.
    SAM name_aggressive is the same. But there may be subtle differences
    (e.g. ampersand handling). Use UPPER() on both sides to be safe,
    and also try name_normalized (full UPPER name) matching.
    """
    print(f"\n[{ts()}] Tier A: Exact Name + State")
    print("-" * 60)

    # A1: name_aggressive exact match
    cur.execute("""
        INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (s.uei)
            s.uei,
            f.employer_id,
            'EXACT_NAME_STATE',
            0.95,
            'SAM_PHASE1'
        FROM sam_entities s
        JOIN f7_employers_deduped f
            ON UPPER(TRIM(s.name_aggressive)) = UPPER(TRIM(f.employer_name_aggressive))
            AND s.physical_state = f.state
        WHERE s.name_aggressive IS NOT NULL AND s.name_aggressive != ''
          AND f.employer_name_aggressive IS NOT NULL AND f.employer_name_aggressive != ''
          AND NOT EXISTS (SELECT 1 FROM sam_f7_matches m WHERE m.uei = s.uei)
        ORDER BY s.uei, f.employer_id
    """)
    a1 = cur.rowcount
    conn.commit()
    print(f"  A1 (name_aggressive exact): {a1:,}")

    # A2: name_normalized (full UPPER name with punctuation) exact match
    cur.execute("""
        INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (s.uei)
            s.uei,
            f.employer_id,
            'EXACT_FULLNAME_STATE',
            0.90,
            'SAM_PHASE1'
        FROM sam_entities s
        JOIN f7_employers_deduped f
            ON s.name_normalized = UPPER(TRIM(f.employer_name))
            AND s.physical_state = f.state
        WHERE s.name_normalized IS NOT NULL AND s.name_normalized != ''
          AND f.employer_name IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM sam_f7_matches m WHERE m.uei = s.uei)
        ORDER BY s.uei, f.employer_id
    """)
    a2 = cur.rowcount
    conn.commit()
    print(f"  A2 (full name normalized): {a2:,}")

    total = a1 + a2
    print(f"  Tier A total: {total:,}")
    if total > 0:
        spot_check(cur, 'EXACT_NAME_STATE')
        if a2 > 0:
            spot_check(cur, 'EXACT_FULLNAME_STATE', 5)
    return total


# ---------------------------------------------------------------------------
# Tier B: Same city + state + pg_trgm % operator (GIN-indexed)
# ---------------------------------------------------------------------------

def tier_b_city_state_fuzzy(cur, conn):
    """Tier B: Same city + state + fuzzy name via % operator.

    The % operator uses the GIN trigram index for fast candidate retrieval.
    We set pg_trgm.similarity_threshold = 0.55 and then rank by similarity().
    Processing state-by-state to manage memory.
    """
    print(f"\n[{ts()}] Tier B: City + State + Fuzzy Name (GIN-indexed)")
    print("-" * 60)

    cur.execute("""
        SELECT DISTINCT physical_state FROM sam_entities
        WHERE physical_state IS NOT NULL
        ORDER BY physical_state
    """)
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states...")

    # Use higher threshold for city-constrained matches (good precision)
    cur.execute("SET pg_trgm.similarity_threshold = 0.55")
    conn.commit()

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (s.uei)
                s.uei,
                f.employer_id,
                'CITY_STATE_FUZZY',
                GREATEST(0.55, ROUND(similarity(s.name_aggressive, f.employer_name_aggressive)::numeric, 2)),
                'SAM_PHASE1'
            FROM sam_entities s
            JOIN f7_employers_deduped f
                ON s.physical_state = f.state
                AND UPPER(s.physical_city) = UPPER(f.city)
                AND s.name_aggressive %% f.employer_name_aggressive
            WHERE s.physical_state = %s
              AND s.name_aggressive IS NOT NULL AND s.name_aggressive != ''
              AND s.physical_city IS NOT NULL
              AND f.employer_name_aggressive IS NOT NULL AND f.employer_name_aggressive != ''
              AND NOT EXISTS (SELECT 1 FROM sam_f7_matches m WHERE m.uei = s.uei)
            ORDER BY s.uei,
                similarity(s.name_aggressive, f.employer_name_aggressive) DESC
        """, (state,))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 50:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (running: {total_matched:,})")

    print(f"  Tier B total: {total_matched:,}")
    if total_matched > 0:
        spot_check(cur, 'CITY_STATE_FUZZY')
    return total_matched


# ---------------------------------------------------------------------------
# Tier C: State + NAICS 2-digit + pg_trgm % operator
# ---------------------------------------------------------------------------

def tier_c_naics_fuzzy(cur, conn):
    """Tier C: Same state + NAICS 2-digit + fuzzy name via % operator.

    Wider geographic scope (state, not city) but constrained by industry.
    Uses higher similarity threshold (0.60) since no city constraint.
    """
    print(f"\n[{ts()}] Tier C: State + NAICS + Fuzzy Name (GIN-indexed)")
    print("-" * 60)

    cur.execute("""
        SELECT DISTINCT physical_state FROM sam_entities
        WHERE physical_state IS NOT NULL
          AND naics_primary IS NOT NULL AND LENGTH(naics_primary) >= 2
        ORDER BY physical_state
    """)
    states = [r[0] for r in cur.fetchall()]
    print(f"  Processing {len(states)} states with NAICS data...")

    # Higher threshold since no city constraint
    cur.execute("SET pg_trgm.similarity_threshold = 0.60")
    conn.commit()

    total_matched = 0
    for i, state in enumerate(states):
        cur.execute("""
            INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (s.uei)
                s.uei,
                f.employer_id,
                'STATE_NAICS_FUZZY',
                GREATEST(0.60, ROUND(similarity(s.name_aggressive, f.employer_name_aggressive)::numeric, 2)),
                'SAM_PHASE1'
            FROM sam_entities s
            JOIN f7_employers_deduped f
                ON s.physical_state = f.state
                AND LEFT(s.naics_primary, 2) = f.naics
                AND s.name_aggressive %% f.employer_name_aggressive
            WHERE s.physical_state = %s
              AND s.name_aggressive IS NOT NULL AND s.name_aggressive != ''
              AND s.naics_primary IS NOT NULL
              AND f.naics IS NOT NULL
              AND f.employer_name_aggressive IS NOT NULL AND f.employer_name_aggressive != ''
              AND NOT EXISTS (SELECT 1 FROM sam_f7_matches m WHERE m.uei = s.uei)
            ORDER BY s.uei,
                similarity(s.name_aggressive, f.employer_name_aggressive) DESC
        """, (state,))
        state_matched = cur.rowcount
        conn.commit()
        total_matched += state_matched

        if (i + 1) % 10 == 0 or state_matched > 50:
            print(f"    [{i+1}/{len(states)}] {state}: {state_matched:,} (running: {total_matched:,})")

    print(f"  Tier C total: {total_matched:,}")
    if total_matched > 0:
        spot_check(cur, 'STATE_NAICS_FUZZY')
    return total_matched


# ---------------------------------------------------------------------------
# Tier D: DBA name + state (exact)
# ---------------------------------------------------------------------------

def tier_d_dba_name(cur, conn):
    """Tier D: Match DBA name against F7 employer name + same state."""
    print(f"\n[{ts()}] Tier D: DBA Name + State (exact)")
    print("-" * 60)

    cur.execute("""
        INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (s.uei)
            s.uei,
            f.employer_id,
            'DBA_NAME_STATE',
            0.80,
            'SAM_PHASE1'
        FROM sam_entities s
        JOIN f7_employers_deduped f
            ON s.physical_state = f.state
            AND UPPER(TRIM(s.dba_name)) = UPPER(TRIM(f.employer_name_aggressive))
        WHERE s.dba_name IS NOT NULL AND s.dba_name != ''
          AND s.dba_name != s.name_aggressive
          AND f.employer_name_aggressive IS NOT NULL AND f.employer_name_aggressive != ''
          AND NOT EXISTS (SELECT 1 FROM sam_f7_matches m WHERE m.uei = s.uei)
        ORDER BY s.uei, f.employer_id
    """)
    matched = cur.rowcount
    conn.commit()
    print(f"  Tier D matches: {matched:,}")
    if matched > 0:
        spot_check(cur, 'DBA_NAME_STATE')
    return matched


# ---------------------------------------------------------------------------
# Post-match: Crosswalk update
# ---------------------------------------------------------------------------

def update_crosswalk(cur, conn):
    """Add SAM data to corporate_identifier_crosswalk."""
    print(f"\n[{ts()}] Updating corporate_identifier_crosswalk...")

    # Add columns if missing
    for col_def in [
        "sam_uei TEXT",
        "sam_cage_code VARCHAR(10)",
        "naics_6digit VARCHAR(10)",
    ]:
        col_name = col_def.split()[0]
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'corporate_identifier_crosswalk' AND column_name = %s
        """, (col_name,))
        if cur.fetchone()[0] == 0:
            cur.execute(f"ALTER TABLE corporate_identifier_crosswalk ADD COLUMN {col_def}")
            print(f"  Added column: {col_name}")
    conn.commit()

    # Get crosswalk count before
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    before_count = cur.fetchone()[0]

    # Update existing crosswalk rows (where f7_employer_id already exists)
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET sam_uei = m.uei,
            sam_cage_code = s.cage_code,
            is_federal_contractor = TRUE,
            naics_6digit = COALESCE(c.naics_6digit, s.naics_primary)
        FROM sam_f7_matches m
        JOIN sam_entities s ON s.uei = m.uei
        WHERE c.f7_employer_id = m.f7_employer_id
          AND c.sam_uei IS NULL
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"  Updated existing crosswalk rows: {updated:,}")

    # Insert new crosswalk rows for matches not yet in crosswalk
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk (
            f7_employer_id, sam_uei, sam_cage_code,
            is_federal_contractor, naics_6digit
        )
        SELECT DISTINCT
            m.f7_employer_id,
            m.uei,
            s.cage_code,
            TRUE,
            s.naics_primary
        FROM sam_f7_matches m
        JOIN sam_entities s ON s.uei = m.uei
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.f7_employer_id = m.f7_employer_id
        )
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f"  New crosswalk rows inserted: {inserted:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    after_count = cur.fetchone()[0]
    print(f"  Crosswalk: {before_count:,} -> {after_count:,} (+{after_count - before_count:,})")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE is_federal_contractor = TRUE")
    fed_count = cur.fetchone()[0]
    print(f"  Federal contractors in crosswalk: {fed_count:,}")

    return updated, inserted


# ---------------------------------------------------------------------------
# Post-match: NAICS enrichment
# ---------------------------------------------------------------------------

def enrich_naics(cur, conn):
    """Backfill 6-digit NAICS onto crosswalk from SAM matches."""
    print(f"\n[{ts()}] NAICS enrichment...")

    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET naics_6digit = s.naics_primary
        FROM sam_f7_matches m
        JOIN sam_entities s ON s.uei = m.uei
        WHERE c.f7_employer_id = m.f7_employer_id
          AND c.naics_6digit IS NULL
          AND s.naics_primary IS NOT NULL
    """)
    enriched = cur.rowcount
    conn.commit()
    print(f"  NAICS 6-digit enriched: {enriched:,}")

    cur.execute("""
        SELECT COUNT(DISTINCT f7_employer_id)
        FROM corporate_identifier_crosswalk WHERE naics_6digit IS NOT NULL
    """)
    print(f"  F7 employers with 6-digit NAICS: {cur.fetchone()[0]:,}")
    return enriched


# ---------------------------------------------------------------------------
# Post-match: Flag OSHA federal contractors
# ---------------------------------------------------------------------------

def flag_osha_contractors(cur, conn):
    """Count OSHA establishments linked to federal contractors via SAM->F7->OSHA."""
    print(f"\n[{ts()}] OSHA federal contractor bridge...")

    cur.execute("""
        SELECT COUNT(DISTINCT o.establishment_id)
        FROM osha_f7_matches o
        JOIN sam_f7_matches s ON s.f7_employer_id = o.f7_employer_id
    """)
    direct = cur.fetchone()[0]
    print(f"  OSHA estabs linked via SAM->F7->OSHA: {direct:,}")

    cur.execute("""
        SELECT COUNT(DISTINCT o.establishment_id)
        FROM osha_f7_matches o
        JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = o.f7_employer_id
        WHERE c.is_federal_contractor = TRUE
    """)
    total_fed = cur.fetchone()[0]
    print(f"  OSHA estabs with federal contractor flag (all sources): {total_fed:,}")
    return direct


# ---------------------------------------------------------------------------
# Spot check
# ---------------------------------------------------------------------------

def spot_check(cur, method, n=10):
    """Print sample matches for visual validation."""
    print(f"\n  Spot-check ({method}, {n} samples):")
    cur.execute("""
        SELECT s.legal_business_name, f.employer_name, m.match_confidence, s.physical_state
        FROM sam_f7_matches m
        JOIN sam_entities s ON s.uei = m.uei
        JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
        WHERE m.match_method = %s
        ORDER BY RANDOM()
        LIMIT %s
    """, (method, n))
    for row in cur.fetchall():
        src = (row[0] or '')[:35]
        tgt = (row[1] or '')[:35]
        print(f"    {src:<35s} -> {tgt:<35s} conf={row[2]} st={row[3]}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(cur, tier_counts):
    """Print match rate summary."""
    print(f"\n{'=' * 70}")
    print("SAM -> F7 MATCH SUMMARY")
    print(f"{'=' * 70}")

    cur.execute("SELECT COUNT(*) FROM sam_entities")
    sam_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sam_f7_matches")
    matched_total = cur.fetchone()[0]
    match_rate = 100 * matched_total / sam_total if sam_total > 0 else 0

    print(f"  SAM entities:     {sam_total:,}")
    print(f"  Total matched:    {matched_total:,} ({match_rate:.2f}%)")
    print()
    print(f"  {'Tier':<30s} {'Matches':>10s} {'%':>8s}")
    print(f"  {'-'*30} {'-'*10} {'-'*8}")
    for tier_name, count in tier_counts:
        pct = 100 * count / matched_total if matched_total > 0 else 0
        print(f"  {tier_name:<30s} {count:>10,} {pct:>7.1f}%")
    print()

    cur.execute("""
        SELECT match_method, COUNT(*), ROUND(AVG(match_confidence), 2)
        FROM sam_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC
    """)
    print("  Method breakdown:")
    for row in cur.fetchall():
        print(f"    {row[0]:<25s} {row[1]:>8,} (avg conf: {row[2]})")

    cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM sam_f7_matches")
    unique_f7 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    total_f7 = cur.fetchone()[0]
    print(f"\n  Unique F7 employers matched: {unique_f7:,} / {total_f7:,} ({100*unique_f7/total_f7:.1f}%)")

    print("\n  Top 10 states by match count:")
    cur.execute("""
        SELECT s.physical_state, COUNT(*) as cnt
        FROM sam_f7_matches m JOIN sam_entities s ON s.uei = m.uei
        WHERE s.physical_state IS NOT NULL
        GROUP BY s.physical_state ORDER BY cnt DESC LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    print(f"[{ts()}] SAM.gov -> F7 Matching Pipeline (v2 - GIN-indexed)")
    print("=" * 60)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM sam_entities")
    sam_count = cur.fetchone()[0]
    if sam_count == 0:
        print("ERROR: sam_entities is empty. Run load_sam.py first.")
        return
    print(f"  SAM entities: {sam_count:,}")

    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    f7_count = cur.fetchone()[0]
    print(f"  F7 employers: {f7_count:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    crosswalk_before = cur.fetchone()[0]
    print(f"  Crosswalk before: {crosswalk_before:,}")
    print()

    # Run tiers
    step0_create_table(cur, conn)
    tier_a = tier_a_exact_name_state(cur, conn)
    tier_b = tier_b_city_state_fuzzy(cur, conn)
    tier_c = tier_c_naics_fuzzy(cur, conn)
    tier_d = tier_d_dba_name(cur, conn)

    tier_counts = [
        ('A: Exact Name+State', tier_a),
        ('B: City+State+Fuzzy (GIN)', tier_b),
        ('C: NAICS+State+Fuzzy (GIN)', tier_c),
        ('D: DBA Name+State', tier_d),
    ]

    # Post-match
    update_crosswalk(cur, conn)
    enrich_naics(cur, conn)
    flag_osha_contractors(cur, conn)

    # Summary
    print_summary(cur, tier_counts)

    elapsed = time.time() - start
    print(f"\n[{ts()}] Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
