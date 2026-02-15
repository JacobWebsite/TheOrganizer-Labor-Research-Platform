import os
from db_config import get_connection
"""
OSHA Establishment Extraction - Phase 2.3 (Resume from 2017)
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
    'password': os.environ.get('DB_PASSWORD', '')
}

def generate_establishment_id(name, address, city, state):
    key = f"{(name or '').upper().strip()}|{(address or '').upper().strip()}|{(city or '').upper().strip()}|{(state or '').upper().strip()}"
    return hashlib.md5(key.encode()).hexdigest()

def safe_int(value, max_val=10000000):
    """Safely convert to int with max cap"""
    if value is None or str(value).strip() == '':
        return None
    try:
        val = int(float(str(value)))
        return min(val, max_val) if val > 0 else None
    except:
        return None

def extract_year(year, sqlite_conn, pg_conn):
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing year {year}...")
    
    sqlite_cur.execute("""
        SELECT 
            estab_name, site_address, site_city, site_state,
            MAX(site_zip), MAX(naics_code), MAX(sic_code), MAX(union_status), MAX(nr_in_estab),
            MIN(open_date), MAX(open_date), COUNT(*)
        FROM inspection
        WHERE substr(open_date, 1, 4) = ? AND estab_name IS NOT NULL
        GROUP BY estab_name, site_address, site_city, site_state
    """, (str(year),))
    
    rows = sqlite_cur.fetchall()
    print(f"  Found {len(rows):,} unique establishments")
    
    if not rows:
        return 0
    
    batch_dict = {}
    for row in rows:
        est_id = generate_establishment_id(row[0], row[1], row[2], row[3])
        if est_id not in batch_dict:
            batch_dict[est_id] = (
                est_id, row[0], row[1], row[2], row[3],
                str(row[4]).strip() if row[4] else None,
                str(row[5]).strip() if row[5] else None,
                str(row[6]).strip() if row[6] else None,
                row[7].strip() if row[7] else None,
                safe_int(row[8]),
                row[9], row[10], row[11]
            )
    
    batch = list(batch_dict.values())
    print(f"  Deduplicated to {len(batch):,} unique IDs")
    
    insert_sql = """
        INSERT INTO osha_establishments 
        (establishment_id, estab_name, site_address, site_city, site_state, 
         site_zip, naics_code, sic_code, union_status, employee_count,
         first_inspection_date, last_inspection_date, total_inspections)
        VALUES %s
        ON CONFLICT (establishment_id) DO UPDATE SET
            last_inspection_date = GREATEST(osha_establishments.last_inspection_date::text, EXCLUDED.last_inspection_date::text)::date,
            total_inspections = osha_establishments.total_inspections + EXCLUDED.total_inspections,
            naics_code = COALESCE(EXCLUDED.naics_code, osha_establishments.naics_code),
            union_status = COALESCE(EXCLUDED.union_status, osha_establishments.union_status),
            employee_count = COALESCE(EXCLUDED.employee_count, osha_establishments.employee_count)
    """
    
    chunk_size = 10000
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i+chunk_size]
        execute_values(pg_cur, insert_sql, chunk, page_size=1000)
        pg_conn.commit()
        print(f"    Chunk {i//chunk_size + 1}: {len(chunk):,} records")
    
    return len(batch)

def main():
    print("="*60)
    print("OSHA Extraction - Resume from 2017")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = get_connection()
    
    # Resume from 2017 onwards
    years = list(range(2017, 2027))
    
    for year in years:
        extract_year(year, sqlite_conn, pg_conn)
    
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT COUNT(*) FROM osha_establishments")
    final_count = pg_cur.fetchone()[0]
    
    print("\n" + "="*60)
    print(f"COMPLETE: {final_count:,} unique establishments")
    print("="*60)
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    main()
