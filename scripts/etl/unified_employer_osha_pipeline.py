import os
from db_config import get_connection
"""
Unified Employer-to-OSHA Pipeline

Creates a unified employers table combining all sources:
1. F7 employers (63,118)
2. VR employers not in F7 (824)
3. NLRB employers not in F7 (51,886)
4. Public sector employers (7,987)

Then runs OSHA matching against all unified employers.
"""

import psycopg2
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}


def create_unified_table(cursor, conn):
    """Create the unified employers table"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Creating unified_employers_osha table...")

    cursor.execute("DROP TABLE IF EXISTS unified_employers_osha CASCADE")
    cursor.execute("""
        CREATE TABLE unified_employers_osha (
            unified_id SERIAL PRIMARY KEY,
            source_type VARCHAR(20) NOT NULL,  -- F7, VR, NLRB, PUBLIC_SECTOR
            source_id TEXT,                     -- Original ID from source
            employer_name TEXT NOT NULL,
            employer_name_normalized TEXT,
            city TEXT,
            state VARCHAR(2),
            zip VARCHAR(10),
            street TEXT,
            naics VARCHAR(6),
            union_fnum TEXT,                    -- Link to unions_master if available
            union_name TEXT,
            employee_count INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print("  Table created.")


def populate_f7_employers(cursor, conn):
    """Add F7 employers to unified table"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Adding F7 employers...")

    cursor.execute("""
        INSERT INTO unified_employers_osha
            (source_type, source_id, employer_name, employer_name_normalized,
             city, state, zip, street, naics, union_fnum, union_name, employee_count)
        SELECT
            'F7',
            employer_id,
            employer_name,
            employer_name_aggressive,
            city,
            state,
            zip,
            street,
            COALESCE(naics_detailed, naics),
            latest_union_fnum::text,
            latest_union_name,
            latest_unit_size
        FROM f7_employers_deduped
    """)
    count = cursor.rowcount
    conn.commit()
    print(f"  Added {count:,} F7 employers")
    return count


def populate_vr_employers(cursor, conn):
    """Add VR employers not already in F7"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Adding VR employers (not in F7)...")

    cursor.execute("""
        INSERT INTO unified_employers_osha
            (source_type, source_id, employer_name, employer_name_normalized,
             city, state, union_fnum, union_name, employee_count)
        SELECT
            'VR',
            vr_case_number,
            employer_name,
            employer_name_aggressive,
            unit_city,
            unit_state,
            matched_union_fnum,
            union_name,
            num_employees
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
        AND employer_name IS NOT NULL
    """)
    count = cursor.rowcount
    conn.commit()
    print(f"  Added {count:,} VR employers")
    return count


def populate_nlrb_employers(cursor, conn):
    """Add NLRB employers not already in F7"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Adding NLRB employers (not in F7)...")

    # Get unique employers from participants that aren't matched
    cursor.execute("""
        INSERT INTO unified_employers_osha
            (source_type, source_id, employer_name, employer_name_normalized,
             city, state, zip, street, union_fnum)
        SELECT DISTINCT ON (UPPER(participant_name), LEFT(state, 2))
            'NLRB',
            case_number,
            participant_name,
            UPPER(REGEXP_REPLACE(
                REGEXP_REPLACE(participant_name, '(,? ?(INC|LLC|CORP|CO|LTD)\\.?)+$', '', 'gi'),
                '[^A-Z0-9 ]', '', 'g'
            )),
            city,
            LEFT(state, 2),
            LEFT(zip, 10),
            address_1,
            matched_olms_fnum
        FROM nlrb_participants
        WHERE participant_type IN ('Employer', 'Employer/Charged Party', 'Charged Party/Employer', 'Charged Party')
        AND matched_employer_id IS NULL
        AND participant_name IS NOT NULL
        AND LENGTH(TRIM(participant_name)) > 3
        AND city IS NOT NULL AND state IS NOT NULL
        AND LENGTH(state) = 2
        ORDER BY UPPER(participant_name), LEFT(state, 2), case_number DESC
    """)
    count = cursor.rowcount
    conn.commit()
    print(f"  Added {count:,} NLRB employers")
    return count


def populate_public_sector(cursor, conn):
    """Add public sector employers"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Adding public sector employers...")

    cursor.execute("""
        INSERT INTO unified_employers_osha
            (source_type, source_id, employer_name, employer_name_normalized,
             city, state, naics, employee_count)
        SELECT
            'PUBLIC',
            id::text,
            employer_name,
            UPPER(REGEXP_REPLACE(
                REGEXP_REPLACE(employer_name, '(,? ?(INC|LLC|CORP|CO|LTD)\\.?)+$', '', 'gi'),
                '[^A-Z0-9 ]', '', 'g'
            )),
            city,
            state,
            naics_code,
            total_employees
        FROM ps_employers
        WHERE employer_name IS NOT NULL
    """)
    count = cursor.rowcount
    conn.commit()
    print(f"  Added {count:,} public sector employers")
    return count


def create_indexes(cursor, conn):
    """Create indexes for matching performance"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Creating indexes...")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_unified_emp_state ON unified_employers_osha(state);
        CREATE INDEX IF NOT EXISTS idx_unified_emp_zip ON unified_employers_osha(LEFT(zip, 5));
        CREATE INDEX IF NOT EXISTS idx_unified_emp_city ON unified_employers_osha(UPPER(city));
        CREATE INDEX IF NOT EXISTS idx_unified_emp_name_trgm
            ON unified_employers_osha USING gin (employer_name_normalized gin_trgm_ops);
    """)
    conn.commit()
    print("  Indexes created.")


def create_osha_unified_matches_table(cursor, conn):
    """Create table for unified OSHA matches"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Creating osha_unified_matches table...")

    cursor.execute("DROP TABLE IF EXISTS osha_unified_matches CASCADE")
    cursor.execute("""
        CREATE TABLE osha_unified_matches (
            id SERIAL PRIMARY KEY,
            establishment_id VARCHAR(32) NOT NULL,
            unified_employer_id INTEGER NOT NULL REFERENCES unified_employers_osha(unified_id),
            match_method VARCHAR(30),
            match_confidence NUMERIC(3,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print("  Table created.")


def run_osha_matching(cursor, conn):
    """Run OSHA matching against unified employers"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running OSHA matching...")
    print("=" * 60)

    total_matches = 0

    # Method 1: Exact normalized name + state
    print("\nMethod 1: Exact normalized name + state...")
    cursor.execute("""
        INSERT INTO osha_unified_matches (establishment_id, unified_employer_id, match_method, match_confidence)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            u.unified_id,
            'EXACT_NAME_STATE',
            0.95
        FROM osha_establishments o
        JOIN unified_employers_osha u
            ON o.site_state = u.state
            AND COALESCE(o.estab_name_normalized, UPPER(o.estab_name)) = u.employer_name_normalized
            AND u.employer_name_normalized IS NOT NULL
            AND LENGTH(u.employer_name_normalized) > 5
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_unified_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id, u.unified_id
    """)
    matches = cursor.rowcount
    total_matches += matches
    conn.commit()
    print(f"  Matches: {matches:,}")

    # Method 2: ZIP + fuzzy name (similarity >= 0.6)
    print("\nMethod 2: ZIP + fuzzy name (sim >= 0.6)...")
    cursor.execute("""
        INSERT INTO osha_unified_matches (establishment_id, unified_employer_id, match_method, match_confidence)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            u.unified_id,
            'ZIP_FUZZY_60',
            ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            )::numeric, 2)
        FROM osha_establishments o
        JOIN unified_employers_osha u
            ON o.site_state = u.state
            AND LEFT(o.site_zip, 5) = LEFT(u.zip, 5)
            AND LENGTH(u.zip) >= 5
            AND u.employer_name_normalized IS NOT NULL
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            ) >= 0.60
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_unified_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id,
            similarity(COALESCE(o.estab_name_normalized, UPPER(o.estab_name)), u.employer_name_normalized) DESC
    """)
    matches = cursor.rowcount
    total_matches += matches
    conn.commit()
    print(f"  Matches: {matches:,}")

    # Method 3: City + fuzzy name (similarity >= 0.55)
    print("\nMethod 3: City + fuzzy name (sim >= 0.55)...")
    cursor.execute("""
        INSERT INTO osha_unified_matches (establishment_id, unified_employer_id, match_method, match_confidence)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            u.unified_id,
            'CITY_FUZZY_55',
            ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            )::numeric, 2)
        FROM osha_establishments o
        JOIN unified_employers_osha u
            ON o.site_state = u.state
            AND UPPER(TRIM(o.site_city)) = UPPER(TRIM(u.city))
            AND u.city IS NOT NULL
            AND u.employer_name_normalized IS NOT NULL
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            ) >= 0.55
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_unified_matches m WHERE m.establishment_id = o.establishment_id
        )
        ORDER BY o.establishment_id,
            similarity(COALESCE(o.estab_name_normalized, UPPER(o.estab_name)), u.employer_name_normalized) DESC
    """)
    matches = cursor.rowcount
    total_matches += matches
    conn.commit()
    print(f"  Matches: {matches:,}")

    # Method 4: State + first 5 chars + fuzzy (for F7 we already have this, run for new sources)
    print("\nMethod 4: State + prefix + fuzzy (sim >= 0.45)...")
    cursor.execute("""
        INSERT INTO osha_unified_matches (establishment_id, unified_employer_id, match_method, match_confidence)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            u.unified_id,
            'STATE_PREFIX_FUZZY',
            ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            )::numeric, 2)
        FROM osha_establishments o
        JOIN unified_employers_osha u
            ON o.site_state = u.state
            AND LEFT(COALESCE(o.estab_name_normalized, UPPER(o.estab_name)), 5) = LEFT(u.employer_name_normalized, 5)
            AND u.employer_name_normalized IS NOT NULL
            AND LENGTH(u.employer_name_normalized) >= 8
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                u.employer_name_normalized
            ) >= 0.45
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_unified_matches m WHERE m.establishment_id = o.establishment_id
        )
        AND u.source_type IN ('VR', 'NLRB', 'PUBLIC')  -- Only new sources
        ORDER BY o.establishment_id,
            similarity(COALESCE(o.estab_name_normalized, UPPER(o.estab_name)), u.employer_name_normalized) DESC
    """)
    matches = cursor.rowcount
    total_matches += matches
    conn.commit()
    print(f"  Matches: {matches:,}")

    return total_matches


def print_summary(cursor):
    """Print summary statistics"""
    print("\n" + "=" * 60)
    print("UNIFIED PIPELINE SUMMARY")
    print("=" * 60)

    # Unified employers by source
    cursor.execute("""
        SELECT source_type, COUNT(*) FROM unified_employers_osha GROUP BY source_type ORDER BY 2 DESC
    """)
    print("\nUnified employers by source:")
    total_unified = 0
    for row in cursor.fetchall():
        print(f"  {row[0]:<15} {row[1]:>10,}")
        total_unified += row[1]
    print(f"  {'TOTAL':<15} {total_unified:>10,}")

    # OSHA matches by source
    cursor.execute("""
        SELECT u.source_type, COUNT(DISTINCT m.establishment_id) as estabs,
               COUNT(DISTINCT u.unified_id) as employers
        FROM osha_unified_matches m
        JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
        GROUP BY u.source_type
        ORDER BY estabs DESC
    """)
    print("\nOSHA matches by employer source:")
    for row in cursor.fetchall():
        print(f"  {row[0]:<15} {row[1]:>8,} establishments, {row[2]:>8,} employers")

    # Total unique matches
    cursor.execute("SELECT COUNT(DISTINCT establishment_id) FROM osha_unified_matches")
    total_estabs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT unified_employer_id) FROM osha_unified_matches")
    total_employers = cursor.fetchone()[0]

    # Union-connected matches
    cursor.execute("""
        SELECT COUNT(DISTINCT m.establishment_id)
        FROM osha_unified_matches m
        JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
        WHERE u.union_fnum IS NOT NULL
    """)
    union_connected = cursor.fetchone()[0]

    print(f"\n{'Total OSHA establishments matched:':<40} {total_estabs:>10,}")
    print(f"{'Total unified employers matched:':<40} {total_employers:>10,}")
    print(f"{'Matches with union connection:':<40} {union_connected:>10,}")

    # Matches by method
    cursor.execute("""
        SELECT match_method, COUNT(*) FROM osha_unified_matches GROUP BY match_method ORDER BY 2 DESC
    """)
    print("\nMatches by method:")
    for row in cursor.fetchall():
        print(f"  {row[0]:<25} {row[1]:>10,}")


def main():
    print("=" * 60)
    print("UNIFIED EMPLOYER-TO-OSHA PIPELINE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    # Create table
    create_unified_table(cursor, conn)

    # Populate from all sources
    f7_count = populate_f7_employers(cursor, conn)
    vr_count = populate_vr_employers(cursor, conn)
    nlrb_count = populate_nlrb_employers(cursor, conn)
    ps_count = populate_public_sector(cursor, conn)

    total = f7_count + vr_count + nlrb_count + ps_count
    print(f"\n{'='*60}")
    print(f"Total unified employers: {total:,}")

    # Create indexes
    create_indexes(cursor, conn)

    # Create matches table and run matching
    create_osha_unified_matches_table(cursor, conn)
    total_matches = run_osha_matching(cursor, conn)

    # Print summary
    print_summary(cursor)

    conn.close()
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
