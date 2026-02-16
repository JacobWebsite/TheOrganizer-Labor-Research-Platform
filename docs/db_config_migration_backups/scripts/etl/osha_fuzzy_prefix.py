import os
"""
OSHA Phase 6.6: Fuzzy Matching with Prefix Prefilter
Uses first 3 chars to prefilter before applying expensive similarity
"""

import psycopg2
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6: Fuzzy Matching with Prefix Prefilter")
    print("=" * 60)
    
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    # Get count of Union=Y unmatched
    cursor.execute("""
        SELECT COUNT(*) FROM osha_establishments o
        WHERE o.union_status = 'Y'
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
    """)
    remaining_y = cursor.fetchone()[0]
    print(f"Unmatched Union=Y: {remaining_y:,}")
    
    # Process Union=Y with prefix matching
    # Match where first 4 chars are the same, then apply similarity
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fuzzy matching Union=Y with 4-char prefix filter...")
    
    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'FUZZY_PREFIX4',
            ROUND(similarity(o.estab_name_normalized, f.employer_name_aggressive)::numeric, 2),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f 
            ON o.site_state = f.state
            AND LEFT(o.estab_name_normalized, 4) = LEFT(f.employer_name_aggressive, 4)
            AND f.employer_name_aggressive IS NOT NULL
            AND similarity(o.estab_name_normalized, f.employer_name_aggressive) >= 0.55
        WHERE o.union_status = 'Y'
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        ORDER BY o.establishment_id, similarity(o.estab_name_normalized, f.employer_name_aggressive) DESC
    """)
    matched_y = cursor.rowcount
    conn.commit()
    print(f"  Union=Y matches: {matched_y:,}")
    
    # Now try 3-char prefix for remaining
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fuzzy matching Union=Y with 3-char prefix filter...")
    
    cursor.execute("""
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
        SELECT DISTINCT ON (o.establishment_id)
            o.establishment_id,
            f.employer_id,
            'FUZZY_PREFIX3',
            ROUND(similarity(o.estab_name_normalized, f.employer_name_aggressive)::numeric, 2),
            'F7_DIRECT'
        FROM osha_establishments o
        JOIN f7_employers_deduped f 
            ON o.site_state = f.state
            AND LEFT(o.estab_name_normalized, 3) = LEFT(f.employer_name_aggressive, 3)
            AND f.employer_name_aggressive IS NOT NULL
            AND similarity(o.estab_name_normalized, f.employer_name_aggressive) >= 0.6
        WHERE o.union_status = 'Y'
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        ORDER BY o.establishment_id, similarity(o.estab_name_normalized, f.employer_name_aggressive) DESC
    """)
    matched_y2 = cursor.rowcount
    conn.commit()
    print(f"  Additional Union=Y matches: {matched_y2:,}")
    
    # Final stats
    cursor.execute("SELECT COUNT(*) FROM osha_f7_matches")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT match_method, COUNT(*) FROM osha_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC")
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6 Union=Y Complete")
    print(f"Total matches: {total:,}")
    print("\nBy method:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    
    conn.close()

if __name__ == '__main__':
    main()
