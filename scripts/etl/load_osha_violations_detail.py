"""
OSHA Detailed Violations - Phase 4
Loads individual violation records with case numbers for external lookup
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
    'password': 'Juniordog33!'
}

def generate_establishment_id(name, address, city, state):
    key = f"{(name or '').upper().strip()}|{(address or '').upper().strip()}|{(city or '').upper().strip()}|{(state or '').upper().strip()}"
    return hashlib.md5(key.encode()).hexdigest()

def process_year(year, sqlite_conn, pg_conn):
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing detailed violations for {year}...")
    
    sqlite_cur.execute("""
        SELECT 
            v.activity_nr,
            i.estab_name, i.site_address, i.site_city, i.site_state,
            v.viol_type,
            v.issuance_date,
            v.current_penalty,
            v.initial_penalty,
            v.standard,
            v.citation_id
        FROM violation v
        JOIN inspection i ON v.activity_nr = i.activity_nr
        WHERE substr(i.open_date, 1, 4) = ?
        AND i.estab_name IS NOT NULL
    """, (str(year),))
    
    rows = sqlite_cur.fetchall()
    print(f"  Found {len(rows):,} violation records")
    
    if not rows:
        return 0
    
    batch = []
    for row in rows:
        est_id = generate_establishment_id(row[1], row[2], row[3], row[4])
        batch.append((
            row[0],   # activity_nr
            est_id,
            row[5],   # viol_type
            row[6],   # issuance_date
            row[7],   # current_penalty
            row[8],   # initial_penalty
            row[9],   # standard
            row[10]   # citation_id
        ))
    
    insert_sql = """
        INSERT INTO osha_violations_detail 
        (activity_nr, establishment_id, violation_type, issuance_date, 
         current_penalty, initial_penalty, standard, citation_id)
        VALUES %s
        ON CONFLICT DO NOTHING
    """
    
    chunk_size = 50000
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i+chunk_size]
        execute_values(pg_cur, insert_sql, chunk, page_size=5000)
        pg_conn.commit()
        print(f"    Chunk {i//chunk_size + 1}: {len(chunk):,} records")
    
    return len(batch)

def main():
    print("="*60)
    print("OSHA Detailed Violations - 2012 to 2026")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(**PG_CONFIG)
    
    pg_cur = pg_conn.cursor()
    pg_cur.execute("TRUNCATE osha_violations_detail RESTART IDENTITY")
    pg_conn.commit()
    print("Cleared existing detail records")
    
    years = list(range(2012, 2027))
    
    for year in years:
        process_year(year, sqlite_conn, pg_conn)
    
    pg_cur.execute("SELECT COUNT(*) FROM osha_violations_detail")
    final_count = pg_cur.fetchone()[0]
    
    print("\n" + "="*60)
    print(f"COMPLETE: {final_count:,} detailed violations loaded")
    print("="*60)
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    main()
