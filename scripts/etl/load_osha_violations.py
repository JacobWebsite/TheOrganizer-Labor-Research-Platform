"""
OSHA Phase 4: Load Violation Details (2012+)
Extracts 2.2M violations from SQLite and loads into PostgreSQL
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import hashlib
from datetime import datetime

# Configuration
SQLITE_DB = r'C:\Users\jakew\Downloads\osha_enforcement.db'
PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}
BATCH_SIZE = 50000
START_DATE = '2012-01-01'

def generate_establishment_id(estab_name, site_address, site_city, site_state):
    """Generate MD5 hash matching the existing establishments"""
    # Normalize: uppercase, strip whitespace
    name = (estab_name or '').upper().strip()
    addr = (site_address or '').upper().strip()
    city = (site_city or '').upper().strip()
    state = (site_state or '').upper().strip()
    
    # Concatenate and hash
    key = f"{name}|{addr}|{city}|{state}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] OSHA Phase 4: Load Violation Details")
    print(f"Start date filter: {START_DATE}")
    print("=" * 60)
    
    # Connect to databases
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cursor = pg_conn.cursor()
    
    # Get count first
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Counting violations from {START_DATE}...")
    sqlite_cursor.execute('''
        SELECT COUNT(*) 
        FROM violation v
        JOIN inspection i ON v.activity_nr = i.activity_nr
        WHERE i.open_date >= ?
    ''', (START_DATE,))
    total_count = sqlite_cursor.fetchone()[0]
    print(f"Total violations to process: {total_count:,}")
    
    # Clear existing data
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Clearing existing violation details...")
    pg_cursor.execute("TRUNCATE TABLE osha_violations_detail RESTART IDENTITY")
    pg_conn.commit()
    
    # Extract and load in batches
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Extracting violations...")
    
    query = '''
        SELECT 
            v.activity_nr,
            v.citation_id,
            v.viol_type,
            v.issuance_date,
            v.current_penalty,
            v.initial_penalty,
            v.standard,
            i.estab_name,
            i.site_address,
            i.site_city,
            i.site_state
        FROM violation v
        JOIN inspection i ON v.activity_nr = i.activity_nr
        WHERE i.open_date >= ?
        ORDER BY v.activity_nr
    '''
    
    sqlite_cursor.execute(query, (START_DATE,))
    
    batch = []
    processed = 0
    matched = 0
    unmatched = 0
    
    # Get all existing establishment_ids for fast lookup
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading establishment IDs for matching...")
    pg_cursor.execute("SELECT establishment_id FROM osha_establishments")
    valid_establishment_ids = set(row[0] for row in pg_cursor.fetchall())
    print(f"Loaded {len(valid_establishment_ids):,} establishment IDs")
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing violations...")
    
    while True:
        rows = sqlite_cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break
            
        for row in rows:
            # Generate establishment_id
            est_id = generate_establishment_id(
                row['estab_name'],
                row['site_address'],
                row['site_city'],
                row['site_state']
            )
            
            # Check if establishment exists
            if est_id in valid_establishment_ids:
                matched += 1
            else:
                unmatched += 1
                est_id = None  # Will be NULL in database
            
            # Parse date
            issuance_date = None
            if row['issuance_date']:
                try:
                    issuance_date = row['issuance_date'][:10]  # YYYY-MM-DD
                except:
                    pass
            
            # Handle empty/null numeric values
            current_penalty = row['current_penalty']
            if current_penalty == '' or current_penalty is None:
                current_penalty = None
            
            initial_penalty = row['initial_penalty']
            if initial_penalty == '' or initial_penalty is None:
                initial_penalty = None
            
            batch.append((
                row['activity_nr'],
                est_id,
                row['viol_type'],
                issuance_date,
                current_penalty,
                initial_penalty,
                row['standard'],
                row['citation_id']
            ))
        
        # Insert batch
        if batch:
            execute_values(
                pg_cursor,
                '''
                INSERT INTO osha_violations_detail 
                (activity_nr, establishment_id, violation_type, issuance_date, 
                 current_penalty, initial_penalty, standard, citation_id)
                VALUES %s
                ''',
                batch,
                page_size=10000
            )
            pg_conn.commit()
            
            processed += len(batch)
            pct = (processed / total_count) * 100
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed: {processed:>10,} / {total_count:,} ({pct:5.1f}%) | Matched: {matched:,} | Unmatched: {unmatched:,}")
            batch = []
    
    # Final stats
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] PHASE 4 COMPLETE")
    print(f"Total violations loaded: {processed:,}")
    print(f"Matched to establishments: {matched:,} ({matched/processed*100:.1f}%)")
    print(f"Unmatched (NULL est_id): {unmatched:,} ({unmatched/processed*100:.1f}%)")
    
    # Verify in PostgreSQL
    pg_cursor.execute("SELECT COUNT(*) FROM osha_violations_detail")
    pg_count = pg_cursor.fetchone()[0]
    print(f"\nPostgreSQL osha_violations_detail: {pg_count:,} records")
    
    pg_cursor.execute("""
        SELECT violation_type, COUNT(*) as cnt, SUM(current_penalty) as penalties
        FROM osha_violations_detail
        GROUP BY violation_type
        ORDER BY cnt DESC
    """)
    print("\nViolation summary:")
    for row in pg_cursor.fetchall():
        print(f"  {row[0] or 'NULL':5} : {row[1]:>10,} violations, ${row[2] or 0:>15,.2f} penalties")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == '__main__':
    main()
