import os
from db_config import get_connection
"""
OSHA Phase 6.6: Fuzzy Trigram Matching by State
Processes Union=Y and Union=N establishments in small batches
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6: Fuzzy Trigram Matching")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get states with unmatched union establishments
    cursor.execute("""
        SELECT o.site_state, COUNT(*) as cnt
        FROM osha_establishments o
        WHERE o.union_status IN ('Y', 'N')
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        AND o.site_state IS NOT NULL
        GROUP BY o.site_state
        ORDER BY cnt DESC
    """)
    states = cursor.fetchall()
    print(f"States to process: {len(states)}")
    
    total_matched = 0
    
    for state, count in states:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing {state} ({count:,} unmatched)...")
        
        # Fuzzy match within state (similarity >= 0.6)
        cursor.execute("""
            INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
            SELECT DISTINCT ON (o.establishment_id)
                o.establishment_id,
                f.employer_id,
                'FUZZY_TRIGRAM',
                ROUND(similarity(o.estab_name_normalized, f.employer_name_aggressive)::numeric, 2),
                'F7_DIRECT'
            FROM osha_establishments o
            JOIN f7_employers_deduped f 
                ON f.state = %s
                AND f.employer_name_aggressive IS NOT NULL
                AND similarity(o.estab_name_normalized, f.employer_name_aggressive) >= 0.6
            WHERE o.site_state = %s
            AND o.union_status IN ('Y', 'N')
            AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
            ORDER BY o.establishment_id, similarity(o.estab_name_normalized, f.employer_name_aggressive) DESC
        """, (state, state))
        
        matched = cursor.rowcount
        total_matched += matched
        conn.commit()
        
        print(f"  -> Matched: {matched:,} (running total: {total_matched:,})")
    
    # Final count
    cursor.execute("SELECT COUNT(*) FROM osha_f7_matches")
    total = cursor.fetchone()[0]
    
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6 Complete")
    print(f"New fuzzy matches: {total_matched:,}")
    print(f"Total matches: {total:,}")
    
    conn.close()

if __name__ == '__main__':
    main()
