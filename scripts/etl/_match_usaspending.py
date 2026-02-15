"""
Match USASpending federal contract recipients to F7 employers
and integrate into the corporate crosswalk.

Matching strategy:
1. Exact name + state match (after normalization)
2. Fuzzy name + exact state match using pg_trgm
3. Use UEI from USASpending to bridge to Mergent (if DUNS->UEI mapping exists)

Also updates the organizing scorecard with federal contract data.
"""
import psycopg2
from psycopg2.extras import execute_values
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def check_data(conn):
    """Check data availability."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM federal_contract_recipients")
    fcr = cur.fetchone()[0]
    print(f"  Federal contract recipients: {fcr:,}")

    cur.execute("SELECT COUNT(*) FROM f7_employers")
    f7 = cur.fetchone()[0]
    print(f"  F7 employers: {f7:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    xw = cur.fetchone()[0]
    print(f"  Crosswalk: {xw:,}")

    return fcr > 0


def match_exact_name_state(conn):
    """Match USASpending recipients to F7 employers by exact normalized name + state."""
    cur = conn.cursor()

    print("\n=== Step 1: Exact name+state match ===")

    # First, we need to normalize F7 names the same way
    # Create a temp table with normalized F7 names
    cur.execute("DROP TABLE IF EXISTS _f7_normalized CASCADE")
    cur.execute("""
        CREATE TEMP TABLE _f7_normalized AS
        SELECT
            employer_id,
            employer_name,
            state,
            city,
            -- Normalize same way as USASpending normalizer
            LOWER(TRIM(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(LOWER(TRIM(employer_name)),
                                '\\m(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\\M\\.?', '', 'g'),
                            '\\md/?b/?a\\M\\.?', '', 'g'),
                        '[^\\w\\s]', ' ', 'g'),
                    '\\s+', ' ', 'g')
            )) as name_normalized
        FROM f7_employers
        WHERE state IS NOT NULL
    """)
    conn.commit()

    cur.execute("CREATE INDEX idx_f7n_name_state ON _f7_normalized(name_normalized, state)")
    conn.commit()

    # Exact match
    cur.execute("""
        SELECT COUNT(DISTINCT fcr.id), COUNT(DISTINCT fn.employer_id)
        FROM federal_contract_recipients fcr
        JOIN _f7_normalized fn
            ON fn.name_normalized = fcr.recipient_name_normalized
            AND fn.state = fcr.recipient_state
    """)
    fcr_matched, f7_matched = cur.fetchone()
    print(f"  Exact matches: {fcr_matched:,} USASpending -> {f7_matched:,} F7 employers")

    # Save matches
    cur.execute("DROP TABLE IF EXISTS usaspending_f7_matches CASCADE")
    cur.execute("""
        CREATE TABLE usaspending_f7_matches AS
        SELECT DISTINCT ON (fn.employer_id)
            fn.employer_id as f7_employer_id,
            fn.employer_name as f7_name,
            fn.state,
            fcr.id as fcr_id,
            fcr.recipient_name as fcr_name,
            fcr.recipient_uei as uei,
            fcr.naics_code as contract_naics,
            fcr.total_obligations,
            fcr.contract_count,
            'EXACT_NAME_STATE' as match_type,
            1.0::numeric as match_confidence
        FROM federal_contract_recipients fcr
        JOIN _f7_normalized fn
            ON fn.name_normalized = fcr.recipient_name_normalized
            AND fn.state = fcr.recipient_state
        ORDER BY fn.employer_id, fcr.total_obligations DESC NULLS LAST
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM usaspending_f7_matches")
    total = cur.fetchone()[0]
    print(f"  Saved {total:,} 1:1 matches (best USASpending match per F7 employer)")

    return total


def match_fuzzy_name_state(conn):
    """Fuzzy match remaining unmatched using pg_trgm."""
    cur = conn.cursor()

    print("\n=== Step 2: Fuzzy name+state match (pg_trgm) ===")

    # Check if pg_trgm extension exists
    cur.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'")
    if cur.fetchone()[0] == 0:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.commit()
        print("  Created pg_trgm extension")

    # Create trigram index on USASpending names
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_name_trgm ON federal_contract_recipients USING gin(recipient_name_normalized gin_trgm_ops)")
    conn.commit()

    # Find unmatched F7 employers
    cur.execute("""
        SELECT COUNT(*)
        FROM _f7_normalized fn
        WHERE NOT EXISTS (
            SELECT 1 FROM usaspending_f7_matches m WHERE m.f7_employer_id = fn.employer_id
        )
        AND fn.name_normalized != '' AND LENGTH(fn.name_normalized) >= 5
    """)
    unmatched = cur.fetchone()[0]
    print(f"  Unmatched F7 employers to try: {unmatched:,}")

    # Fuzzy match: for each unmatched F7 employer, find best USASpending match
    # Using pg_trgm similarity >= 0.55, same state
    # Set similarity threshold for the % operator
    cur.execute("SET pg_trgm.similarity_threshold = 0.55")
    conn.commit()

    # Also create trigram index on F7 names for the join
    cur.execute("CREATE INDEX IF NOT EXISTS idx_f7n_name_trgm ON _f7_normalized USING gin(name_normalized gin_trgm_ops)")
    conn.commit()

    # Use %% which psycopg2 converts to % (the pg_trgm operator) when params are passed
    cur.execute("""
        INSERT INTO usaspending_f7_matches
        SELECT DISTINCT ON (fn.employer_id)
            fn.employer_id as f7_employer_id,
            fn.employer_name as f7_name,
            fn.state,
            fcr.id as fcr_id,
            fcr.recipient_name as fcr_name,
            fcr.recipient_uei as uei,
            fcr.naics_code as contract_naics,
            fcr.total_obligations,
            fcr.contract_count,
            'FUZZY_NAME_STATE' as match_type,
            ROUND(similarity(fn.name_normalized, fcr.recipient_name_normalized)::numeric, 3) as match_confidence
        FROM _f7_normalized fn
        JOIN federal_contract_recipients fcr
            ON fcr.recipient_state = fn.state
            AND fn.name_normalized %% fcr.recipient_name_normalized
        WHERE NOT EXISTS (
            SELECT 1 FROM usaspending_f7_matches m WHERE m.f7_employer_id = fn.employer_id
        )
        AND fn.name_normalized != '' AND LENGTH(fn.name_normalized) >= 5
        ORDER BY fn.employer_id,
                 similarity(fn.name_normalized, fcr.recipient_name_normalized) DESC,
                 fcr.total_obligations DESC NULLS LAST
    """, ())
    conn.commit()

    fuzzy_count = cur.rowcount
    print(f"  Fuzzy matches added: {fuzzy_count:,}")

    cur.execute("SELECT COUNT(*) FROM usaspending_f7_matches")
    total = cur.fetchone()[0]
    print(f"  Total matches: {total:,}")

    return fuzzy_count


def integrate_crosswalk(conn):
    """Add USASpending matches to the crosswalk."""
    cur = conn.cursor()

    print("\n=== Step 3: Crosswalk integration ===")

    # Check how many matched F7 employers are NOT already in crosswalk
    cur.execute("""
        SELECT COUNT(*)
        FROM usaspending_f7_matches m
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.f7_employer_id = m.f7_employer_id
        )
    """)
    new_f7 = cur.fetchone()[0]
    print(f"  New F7 employers not in crosswalk: {new_f7:,}")

    # Check how many already-in-crosswalk F7 employers can get UEI backfilled
    cur.execute("""
        SELECT COUNT(*)
        FROM usaspending_f7_matches m
        JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = m.f7_employer_id
        WHERE m.uei IS NOT NULL
    """)
    backfill = cur.fetchone()[0]
    print(f"  Existing crosswalk rows that can get UEI: {backfill:,}")

    # Add new crosswalk entries for F7 employers identified as federal contractors
    # We'll check if the crosswalk has a UEI column first
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'corporate_identifier_crosswalk'
        ORDER BY ordinal_position
    """)
    xw_cols = [r[0] for r in cur.fetchall()]
    print(f"  Crosswalk columns: {xw_cols}")

    # Add federal_contractor flag column if not exists
    if 'is_federal_contractor' not in xw_cols:
        cur.execute("ALTER TABLE corporate_identifier_crosswalk ADD COLUMN IF NOT EXISTS is_federal_contractor BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE corporate_identifier_crosswalk ADD COLUMN IF NOT EXISTS federal_obligations NUMERIC")
        cur.execute("ALTER TABLE corporate_identifier_crosswalk ADD COLUMN IF NOT EXISTS federal_contract_count INTEGER")
        conn.commit()
        print("  Added federal contractor columns to crosswalk")

    # Update existing crosswalk rows with federal contract info
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET is_federal_contractor = TRUE,
            federal_obligations = m.total_obligations,
            federal_contract_count = m.contract_count
        FROM usaspending_f7_matches m
        WHERE c.f7_employer_id = m.f7_employer_id
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"  Updated {updated:,} existing crosswalk rows with federal contractor info")

    # Insert new crosswalk entries for unmatched F7 employers
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (f7_employer_id, canonical_name, state, match_tier, match_confidence,
             is_federal_contractor, federal_obligations, federal_contract_count)
        SELECT
            m.f7_employer_id,
            m.f7_name,
            m.state,
            'USASPENDING_' || m.match_type,
            m.match_confidence,
            TRUE,
            m.total_obligations,
            m.contract_count
        FROM usaspending_f7_matches m
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.f7_employer_id = m.f7_employer_id
        )
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f"  Inserted {inserted:,} new crosswalk entries")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    total = cur.fetchone()[0]
    print(f"  Crosswalk total: {total:,}")

    return inserted


def create_federal_contractor_scores(conn):
    """Create a scoring table for federal contractor status."""
    cur = conn.cursor()

    print("\n=== Step 4: Federal contractor scores ===")

    cur.execute("DROP TABLE IF EXISTS f7_federal_scores CASCADE")
    cur.execute("""
        CREATE TABLE f7_federal_scores AS
        SELECT
            m.f7_employer_id as employer_id,
            m.f7_name,
            m.state,
            m.uei,
            m.contract_naics,
            m.total_obligations,
            m.contract_count,
            m.match_type,
            m.match_confidence,
            -- Score: 0-15 points based on federal contract status
            CASE
                WHEN m.total_obligations >= 10000000 THEN 15  -- $10M+
                WHEN m.total_obligations >= 1000000 THEN 12   -- $1M-$10M
                WHEN m.total_obligations >= 100000 THEN 9     -- $100K-$1M
                WHEN m.total_obligations >= 10000 THEN 6      -- $10K-$100K
                WHEN m.total_obligations > 0 THEN 3           -- Any federal contract
                ELSE 0
            END as federal_score
        FROM usaspending_f7_matches m
    """)
    conn.commit()

    cur.execute("CREATE INDEX idx_ffs_employer ON f7_federal_scores(employer_id)")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM f7_federal_scores")
    total = cur.fetchone()[0]

    print(f"  Federal contractor scores: {total:,} employers")

    # Score distribution
    cur.execute("""
        SELECT federal_score, COUNT(*)
        FROM f7_federal_scores
        GROUP BY federal_score
        ORDER BY federal_score
    """)
    for row in cur.fetchall():
        print(f"    Score {row[0]:>2}: {row[1]:,}")

    # Top contractors
    print("\n  Top 10 F7 employers by federal obligations:")
    cur.execute("""
        SELECT f7_name, state, total_obligations, contract_count, match_type
        FROM f7_federal_scores
        ORDER BY total_obligations DESC NULLS LAST
        LIMIT 10
    """)
    for row in cur.fetchall():
        obl = row[2] or 0
        print(f"    {row[0][:50]:<50} {row[1]} ${obl:>15,.0f} ({row[3]} contracts) [{row[4]}]")


def summary(conn):
    """Print final summary."""
    cur = conn.cursor()

    print("\n=== FINAL SUMMARY ===")

    cur.execute("""
        SELECT match_type, COUNT(*), ROUND(AVG(match_confidence), 3)
        FROM usaspending_f7_matches
        GROUP BY match_type
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} matches (avg confidence {row[2]})")

    cur.execute("""
        SELECT match_tier, COUNT(*)
        FROM corporate_identifier_crosswalk
        GROUP BY match_tier
        ORDER BY COUNT(*) DESC
    """)
    print("\n  Crosswalk by tier:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    print(f"\n  Crosswalk TOTAL: {cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE is_federal_contractor = TRUE")
    print(f"  Federal contractors in crosswalk: {cur.fetchone()[0]:,}")


def main():
    conn = get_connection()
    conn.autocommit = False

    print("=== Matching USASpending to F7 ===")
    if not check_data(conn):
        print("  No federal contract recipients loaded! Run fetch script first.")
        conn.close()
        return

    match_exact_name_state(conn)
    match_fuzzy_name_state(conn)
    integrate_crosswalk(conn)
    create_federal_contractor_scores(conn)
    summary(conn)

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
