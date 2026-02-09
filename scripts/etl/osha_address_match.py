import os
"""
OSHA Phase 6.7: Address-Based Matching
Matches establishments where addresses match even if names differ
"""

import psycopg2
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'os.environ.get('DB_PASSWORD', '')'
}

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.7: Address-Based Matching")
    print("=" * 60)
    
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    # Count unmatched
    cursor.execute("""
        SELECT COUNT(*) FROM osha_establishments o
        WHERE NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
    """)
    remaining = cursor.fetchone()[0]
    print(f"Unmatched establishments: {remaining:,}")
    
    # Create normalized address function inline
    # Match on: normalized street number + city + state
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Matching on normalized address + city + state...")
    
    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'ADDRESS_CITY_STATE',
            0.75,
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f 
            ON o.site_state = f.state
            AND UPPER(TRIM(o.site_city)) = UPPER(TRIM(f.city))
            AND REGEXP_REPLACE(UPPER(o.site_address), '[^0-9A-Z ]', '', 'g') = REGEXP_REPLACE(UPPER(f.street), '[^0-9A-Z ]', '', 'g')
            AND LENGTH(TRIM(o.site_address)) > 5
            AND LENGTH(TRIM(f.street)) > 5
        WHERE NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        ORDER BY o.establishment_id, f.filing_count DESC
    """)
    matched_addr = cursor.rowcount
    conn.commit()
    print(f"  Address matches: {matched_addr:,}")
    
    # Try zip code + partial address match
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Matching on street number + zip...")
    
    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'STREET_NUM_ZIP',
            0.70,
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f 
            ON o.site_state = f.state
            AND LEFT(o.site_zip, 5) = LEFT(f.zip, 5)
            AND SPLIT_PART(UPPER(o.site_address), ' ', 1) = SPLIT_PART(UPPER(f.street), ' ', 1)  -- street number
            AND LENGTH(o.site_zip) >= 5
            AND LENGTH(f.zip) >= 5
            AND SPLIT_PART(UPPER(o.site_address), ' ', 1) ~ '^[0-9]+$'  -- ensure it's a number
        WHERE NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        ORDER BY o.establishment_id, f.filing_count DESC
    """)
    matched_zip = cursor.rowcount
    conn.commit()
    print(f"  Zip+street# matches: {matched_zip:,}")
    
    # Final stats
    cursor.execute("SELECT COUNT(*) FROM osha_f7_matches")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT match_method, COUNT(*) FROM osha_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC")
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.7 Complete")
    print(f"Total matches: {total:,}")
    print("\nBy method:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    
    conn.close()

if __name__ == '__main__':
    main()
