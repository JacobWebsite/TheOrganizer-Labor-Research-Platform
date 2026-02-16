import os
"""
OSHA Phase 6.6: Fuzzy Trigram Matching - Micro Batches
Processes 200 establishments at a time to avoid timeouts
"""

import psycopg2
from datetime import datetime

PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

BATCH_SIZE = 200  # Very small batches

def process_batch(cursor, conn, union_status, offset):
    """Process a single micro-batch of establishments"""
    
    # Get batch of unmatched establishment IDs
    cursor.execute("""
        SELECT o.establishment_id, o.estab_name_normalized, o.site_state
        FROM osha_establishments o
        WHERE o.union_status = %s
        AND o.site_state IS NOT NULL
        AND o.estab_name_normalized IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        ORDER BY o.establishment_id
        LIMIT %s OFFSET %s
    """, (union_status, BATCH_SIZE, offset))
    
    establishments = cursor.fetchall()
    if not establishments:
        return 0, False  # No more records
    
    matched = 0
    for est_id, est_name, est_state in establishments:
        # Find best fuzzy match for this single establishment
        cursor.execute("""
            SELECT f.employer_id, similarity(f.employer_name_aggressive, %s) as sim
            FROM f7_employers_deduped f
            WHERE f.state = %s
            AND f.employer_name_aggressive IS NOT NULL
            AND similarity(f.employer_name_aggressive, %s) >= 0.6
            ORDER BY sim DESC
            LIMIT 1
        """, (est_name, est_state, est_name))
        
        result = cursor.fetchone()
        if result:
            f7_id, sim = result
            cursor.execute("""
                INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence, match_source)
                VALUES (%s, %s, 'FUZZY_TRIGRAM', %s, 'F7_DIRECT')
                ON CONFLICT DO NOTHING
            """, (est_id, f7_id, round(sim, 2)))
            if cursor.rowcount > 0:
                matched += 1
    
    conn.commit()
    return matched, len(establishments) == BATCH_SIZE

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6: Fuzzy Matching - Micro Batches")
    print(f"Batch size: {BATCH_SIZE}")
    print("=" * 60)
    
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    # Process Union=Y first (higher priority)
    for union_status in ['Y', 'N']:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing union_status = {union_status}")
        
        # Count remaining
        cursor.execute("""
            SELECT COUNT(*) FROM osha_establishments o
            WHERE o.union_status = %s
            AND NOT EXISTS (SELECT 1 FROM osha_f7_matches m WHERE m.establishment_id = o.establishment_id)
        """, (union_status,))
        remaining = cursor.fetchone()[0]
        print(f"Remaining to process: {remaining:,}")
        
        if remaining == 0:
            continue
        
        offset = 0
        total_matched = 0
        batch_num = 0
        
        while True:
            batch_num += 1
            matched, has_more = process_batch(cursor, conn, union_status, offset)
            total_matched += matched
            
            if batch_num % 10 == 0 or not has_more:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Batch {batch_num}: +{matched} (total: {total_matched:,}, processed: {offset + BATCH_SIZE:,})")
            
            if not has_more:
                break
            
            offset += BATCH_SIZE
            
            # Stop after processing all Union=Y, limit Union=N to avoid very long runs
            if union_status == 'N' and offset >= 20000:
                print(f"  Stopping Union=N at {offset:,} to checkpoint progress")
                break
        
        print(f"  Union={union_status} complete: {total_matched:,} matches")
    
    # Final count
    cursor.execute("SELECT COUNT(*) FROM osha_f7_matches")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT match_method, COUNT(*) FROM osha_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC")
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phase 6.6 Checkpoint")
    print(f"Total matches: {total:,}")
    print("\nBy method:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    
    conn.close()

if __name__ == '__main__':
    main()
