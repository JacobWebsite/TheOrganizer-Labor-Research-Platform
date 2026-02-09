import os
"""
OSHA Violation Aggregation - Phase 3
Aggregates violations by establishment and type, loads summaries
"""
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import hashlib
from datetime import datetime

SQLITE_PATH = r'C:\Users\jakew\Downloads\osha_enforcement.db'
PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'os.environ.get('DB_PASSWORD', '')'
}

def generate_establishment_id(name, address, city, state):
    key = f"{(name or '').upper().strip()}|{(address or '').upper().strip()}|{(city or '').upper().strip()}|{(state or '').upper().strip()}"
    return hashlib.md5(key.encode()).hexdigest()

def process_year(year, sqlite_conn, pg_conn):
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing violations for {year}...")
    
    # Get violations aggregated by establishment + type
    sqlite_cur.execute("""
        SELECT 
            i.estab_name, i.site_address, i.site_city, i.site_state,
            v.viol_type,
            COUNT(*) as violation_count,
            SUM(COALESCE(v.current_penalty, 0)) as total_penalties,
            MIN(v.issuance_date) as first_violation,
            MAX(v.issuance_date) as last_violation
        FROM violation v
        JOIN inspection i ON v.activity_nr = i.activity_nr
        WHERE substr(i.open_date, 1, 4) = ?
        AND i.estab_name IS NOT NULL
        AND v.viol_type IS NOT NULL
        GROUP BY i.estab_name, i.site_address, i.site_city, i.site_state, v.viol_type
    """, (str(year),))
    
    rows = sqlite_cur.fetchall()
    print(f"  Found {len(rows):,} violation aggregates")
    
    if not rows:
        return 0
    
    batch = []
    for row in rows:
        est_id = generate_establishment_id(row[0], row[1], row[2], row[3])
        batch.append((
            est_id,
            row[4],  # viol_type
            row[5],  # violation_count
            row[6],  # total_penalties
            row[7],  # first_violation_date
            row[8]   # last_violation_date
        ))
    
    # Insert with upsert
    insert_sql = """
        INSERT INTO osha_violation_summary 
        (establishment_id, violation_type, violation_count, total_penalties, first_violation_date, last_violation_date)
        VALUES %s
        ON CONFLICT DO NOTHING
    """
    
    chunk_size = 20000
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i+chunk_size]
        execute_values(pg_cur, insert_sql, chunk, page_size=2000)
        pg_conn.commit()
        print(f"    Chunk {i//chunk_size + 1}: {len(chunk):,} records")
    
    return len(batch)

def main():
    print("="*60)
    print("OSHA Violation Aggregation - 2012 to 2026")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(**PG_CONFIG)
    
    # Clear existing data
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE osha_violation_summary RESTART IDENTITY")
    pg_conn.commit()
    print("Cleared existing violation summaries")
    
    years = list(range(2012, 2027))
    total = 0
    
    for year in years:
        total += process_year(year, sqlite_conn, pg_conn)
    
    pg_cur.execute("SELECT COUNT(*) FROM osha_violation_summary")
    final_count = pg_cur.fetchone()[0]
    
    print("\n" + "="*60)
    print(f"COMPLETE: {final_count:,} violation summaries loaded")
    print("="*60)
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    main()
