import os
"""
OSHA Match Improvement Script
Improves F7-OSHA matching from ~32% to 50%+ using:
1. ZIP code + lower similarity threshold (0.4)
2. 2-digit NAICS validation to boost confidence
3. Address abbreviation normalization
"""

import psycopg2
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

# Street abbreviation mappings for normalization
STREET_ABBREVS = {
    'STREET': 'ST',
    'AVENUE': 'AVE',
    'BOULEVARD': 'BLVD',
    'DRIVE': 'DR',
    'ROAD': 'RD',
    'LANE': 'LN',
    'COURT': 'CT',
    'PLACE': 'PL',
    'CIRCLE': 'CIR',
    'HIGHWAY': 'HWY',
    'PARKWAY': 'PKWY',
    'EXPRESSWAY': 'EXPY',
    'TERRACE': 'TER',
    'SUITE': 'STE',
    'APARTMENT': 'APT',
    'BUILDING': 'BLDG',
    'FLOOR': 'FL',
    'NORTH': 'N',
    'SOUTH': 'S',
    'EAST': 'E',
    'WEST': 'W',
    'NORTHEAST': 'NE',
    'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE',
    'SOUTHWEST': 'SW',
}


def get_baseline(cursor):
    """Get current match statistics"""
    cursor.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches")
    matched = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    total = cursor.fetchone()[0]

    return matched, total


def create_address_normalize_function(cursor, conn):
    """Create SQL function for address normalization with abbreviations"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating address normalization function...")

    cursor.execute("""
        CREATE OR REPLACE FUNCTION normalize_address(addr TEXT)
        RETURNS TEXT AS $$
        DECLARE
            result TEXT;
        BEGIN
            result := UPPER(COALESCE(addr, ''));
            -- Remove punctuation except spaces
            result := REGEXP_REPLACE(result, '[^0-9A-Z ]', ' ', 'g');
            -- Normalize common abbreviations (expand to standard form then collapse)
            result := REGEXP_REPLACE(result, '\\mSTREET\\M', 'ST', 'g');
            result := REGEXP_REPLACE(result, '\\mAVENUE\\M', 'AVE', 'g');
            result := REGEXP_REPLACE(result, '\\mBOULEVARD\\M', 'BLVD', 'g');
            result := REGEXP_REPLACE(result, '\\mDRIVE\\M', 'DR', 'g');
            result := REGEXP_REPLACE(result, '\\mROAD\\M', 'RD', 'g');
            result := REGEXP_REPLACE(result, '\\mLANE\\M', 'LN', 'g');
            result := REGEXP_REPLACE(result, '\\mCOURT\\M', 'CT', 'g');
            result := REGEXP_REPLACE(result, '\\mPLACE\\M', 'PL', 'g');
            result := REGEXP_REPLACE(result, '\\mCIRCLE\\M', 'CIR', 'g');
            result := REGEXP_REPLACE(result, '\\mHIGHWAY\\M', 'HWY', 'g');
            result := REGEXP_REPLACE(result, '\\mPARKWAY\\M', 'PKWY', 'g');
            result := REGEXP_REPLACE(result, '\\mTERRACE\\M', 'TER', 'g');
            result := REGEXP_REPLACE(result, '\\mSUITE\\M', 'STE', 'g');
            result := REGEXP_REPLACE(result, '\\mAPARTMENT\\M', 'APT', 'g');
            result := REGEXP_REPLACE(result, '\\mBUILDING\\M', 'BLDG', 'g');
            result := REGEXP_REPLACE(result, '\\mFLOOR\\M', 'FL', 'g');
            result := REGEXP_REPLACE(result, '\\mNORTH\\M', 'N', 'g');
            result := REGEXP_REPLACE(result, '\\mSOUTH\\M', 'S', 'g');
            result := REGEXP_REPLACE(result, '\\mEAST\\M', 'E', 'g');
            result := REGEXP_REPLACE(result, '\\mWEST\\M', 'W', 'g');
            result := REGEXP_REPLACE(result, '\\mNORTHEAST\\M', 'NE', 'g');
            result := REGEXP_REPLACE(result, '\\mNORTHWEST\\M', 'NW', 'g');
            result := REGEXP_REPLACE(result, '\\mSOUTHEAST\\M', 'SE', 'g');
            result := REGEXP_REPLACE(result, '\\mSOUTHWEST\\M', 'SW', 'g');
            -- Collapse multiple spaces
            result := REGEXP_REPLACE(result, '\\s+', ' ', 'g');
            result := TRIM(result);
            RETURN result;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)
    conn.commit()
    print("  Address normalization function created.")


def method_zip_fuzzy_naics(cursor, conn):
    """
    Method 1: ZIP code + fuzzy name matching with NAICS validation
    Uses lower similarity threshold (0.4) when NAICS matches
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Method 1: ZIP + Fuzzy Name + NAICS Validation")
    print("-" * 60)

    # First: Match with NAICS validation (higher confidence)
    print("  Matching with 2-digit NAICS validation (similarity >= 0.35)...")
    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'ZIP_FUZZY_NAICS',
            GREATEST(0.65, ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            )::numeric, 2)),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND LEFT(o.site_zip, 5) = LEFT(f.zip, 5)
            AND LEFT(o.naics_code, 2) = f.naics  -- NAICS 2-digit match
            AND f.naics IS NOT NULL
            AND LENGTH(f.zip) >= 5
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) >= 0.35
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.f7_employer_id = f.employer_id
        )
        ORDER BY o.establishment_id,
            similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) DESC
    """)
    matched_naics = cursor.rowcount
    conn.commit()
    print(f"    ZIP + NAICS matches: {matched_naics:,}")

    return matched_naics


def method_zip_fuzzy_strict(cursor, conn):
    """
    Method 2: ZIP code + stricter fuzzy matching (no NAICS requirement)
    Uses similarity >= 0.5
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Method 2: ZIP + Fuzzy Name (strict, no NAICS)")
    print("-" * 60)

    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'ZIP_FUZZY_STRICT',
            ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            )::numeric, 2),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND LEFT(o.site_zip, 5) = LEFT(f.zip, 5)
            AND LENGTH(f.zip) >= 5
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) >= 0.50
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.f7_employer_id = f.employer_id
        )
        ORDER BY o.establishment_id,
            similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) DESC
    """)
    matched = cursor.rowcount
    conn.commit()
    print(f"    ZIP + strict fuzzy matches: {matched:,}")

    return matched


def method_normalized_address(cursor, conn):
    """
    Method 3: Improved address matching with abbreviation normalization
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Method 3: Normalized Address Matching")
    print("-" * 60)

    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'NORM_ADDRESS_MATCH',
            0.78,
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND UPPER(TRIM(o.site_city)) = UPPER(TRIM(f.city))
            AND normalize_address(o.site_address) = normalize_address(f.street)
            AND LENGTH(TRIM(o.site_address)) > 5
            AND LENGTH(TRIM(f.street)) > 5
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.f7_employer_id = f.employer_id
        )
        ORDER BY o.establishment_id, f.filing_count DESC
    """)
    matched = cursor.rowcount
    conn.commit()
    print(f"    Normalized address matches: {matched:,}")

    return matched


def method_city_naics_fuzzy(cursor, conn):
    """
    Method 4: City + NAICS + moderate fuzzy matching
    For cases where ZIP doesn't match but city and industry do
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Method 4: City + NAICS + Fuzzy Name")
    print("-" * 60)

    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'CITY_NAICS_FUZZY',
            ROUND(similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            )::numeric, 2),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f
            ON o.site_state = f.state
            AND UPPER(TRIM(o.site_city)) = UPPER(TRIM(f.city))
            AND LEFT(o.naics_code, 2) = f.naics
            AND f.naics IS NOT NULL
            AND similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) >= 0.45
        WHERE NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM osha_f7_matches m WHERE m.f7_employer_id = f.employer_id
        )
        ORDER BY o.establishment_id,
            similarity(
                COALESCE(o.estab_name_normalized, UPPER(o.estab_name)),
                COALESCE(f.employer_name_aggressive, UPPER(f.employer_name))
            ) DESC
    """)
    matched = cursor.rowcount
    conn.commit()
    print(f"    City + NAICS + fuzzy matches: {matched:,}")

    return matched


def print_summary(cursor, before_matched, before_total):
    """Print final summary statistics"""
    cursor.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches")
    after_matched = cursor.fetchone()[0]

    cursor.execute("""
        SELECT match_method, COUNT(*) as cnt, ROUND(AVG(match_confidence)::numeric, 2) as avg_conf
        FROM osha_f7_matches
        GROUP BY match_method
        ORDER BY cnt DESC
    """)

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Before: {before_matched:,} / {before_total:,} ({100*before_matched/before_total:.1f}%)")
    print(f"After:  {after_matched:,} / {before_total:,} ({100*after_matched/before_total:.1f}%)")
    print(f"New matches: {after_matched - before_matched:,}")
    print(f"Improvement: +{100*(after_matched - before_matched)/before_total:.1f}%")

    print("\nMatches by method:")
    for row in cursor.fetchall():
        print(f"  {row[0]:<25} {row[1]:>8,}  (avg conf: {row[2]})")


def main():
    print("=" * 60)
    print("OSHA-F7 MATCH IMPROVEMENT")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()

    # Get baseline
    before_matched, before_total = get_baseline(cursor)
    print(f"\nBaseline: {before_matched:,} / {before_total:,} ({100*before_matched/before_total:.1f}%)")
    print(f"Target: {int(before_total * 0.5):,} (50%)")
    print(f"Need: {int(before_total * 0.5) - before_matched:,} more matches")

    # Create helper function
    create_address_normalize_function(cursor, conn)

    # Run improvement methods
    total_new = 0
    total_new += method_zip_fuzzy_naics(cursor, conn)
    total_new += method_zip_fuzzy_strict(cursor, conn)
    total_new += method_normalized_address(cursor, conn)
    total_new += method_city_naics_fuzzy(cursor, conn)

    # Print summary
    print_summary(cursor, before_matched, before_total)

    conn.close()
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
