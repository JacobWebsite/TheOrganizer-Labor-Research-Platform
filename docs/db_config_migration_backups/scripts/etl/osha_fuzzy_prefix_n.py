import os
"""
OSHA Phase 6.6b: Fuzzy Matching for Union=N establishments
Uses prefix prefilter approach
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6b: Fuzzy Matching Union=N")
    print("=" * 60)
    
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    # Get count of Union=N unmatched
    cursor.execute("""
        SELECT COUNT(*) FROM osha_establishments o
        WHERE o.union_status = 'N'
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
    """)
    remaining = cursor.fetchone()[0]
    print(f"Unmatched Union=N: {remaining:,}")
    
    # Process in state batches to avoid timeout
    cursor.execute("""
        SELECT site_state, COUNT(*) as cnt
        FROM osha_establishments o
        WHERE o.union_status = 'N'
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        AND site_state IS NOT NULL
        GROUP BY site_state
        ORDER BY cnt DESC
    """)
    states = cursor.fetchall()
    
    total_matched = 0
    for state, count in states:
        cursor.execute("""
            INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (o.establishment_id)
                o.establishment_id,
                f.employer_id,
                'FUZZY_PREFIX4_N',
                ROUND(similarity(o.estab_name_normalized, f.employer_name_aggressive)::numeric, 2),
                'F7_DIRECT'
            FROM osha_establishments o
            JOIN f7_employers_deduped f 
                ON o.site_state = f.state
                AND LEFT(o.estab_name_normalized, 4) = LEFT(f.employer_name_aggressive, 4)
                AND f.employer_name_aggressive IS NOT NULL
                AND similarity(o.estab_name_normalized, f.employer_name_aggressive) >= 0.55
            WHERE o.union_status = 'N'
            AND o.site_state = %s
            AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
            ORDER BY o.establishment_id, similarity(o.estab_name_normalized, f.employer_name_aggressive) DESC
        """, (state,))
        matched = cursor.rowcount
        total_matched += matched
        conn.commit()
        
        if matched > 0:
            print(f"  {state}: +{matched:,}")
    
    print(f"\nTotal Union=N matches: {total_matched:,}")
    
    # Final stats
    cursor.execute("SELECT COUNT(*) FROM osha_f7_matches")
    total = cursor.fetchone()[0]
    print(f"\nGrand total matches: {total:,}")
    
    conn.close()

if __name__ == '__main__':
    main()
