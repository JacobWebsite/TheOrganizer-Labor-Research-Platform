"""
OSHA Establishment Extraction - Phase 2.3 (Fixed)
Extracts unique establishments from SQLite by year and loads to PostgreSQL
"""
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import hashlib
from datetime import datetime

# Configuration
SQLITE_PATH = r'C:\Users\jakew\Downloads\osha_enforcement.db'
PG_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

def generate_establishment_id(name, address, city, state):
    """Generate consistent hash ID for establishment"""
    key = f"{(name or '').upper().strip()}|{(address or '').upper().strip()}|{(city or '').upper().strip()}|{(state or '').upper().strip()}"
    return hashlib.md5(key.encode()).hexdigest()

def extract_year(year, sqlite_conn, pg_conn):
    """Extract establishments for a single year"""
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing year {year}...")
    
    # Get establishments aggregated by unique key
    sqlite_cur.execute("""
        SELECT 
            estab_name,
            site_address,
            site_city,
            site_state,
            MAX(site_zip) as site_zip,
            MAX(naics_code) as naics_code,
            MAX(sic_code) as sic_code,
            MAX(union_status) as union_status,
            MAX(nr_in_estab) as nr_in_estab,
            MIN(open_date) as first_inspection,
            MAX(open_date) as last_inspection,
            COUNT(*) as total_inspections
        FROM inspection
        WHERE substr(open_date, 1, 4) = ?
        AND estab_name IS NOT NULL
        GROUP BY estab_name, site_address, site_city, site_state
    """, (str(year),))
    
    rows = sqlite_cur.fetchall()
    print(f"  Found {len(rows):,} unique establishments for {year}")
    
    if not rows:
        return 0
    
    # Build deduplicated batch using dict
    batch_dict = {}
    for row in rows:
        est_id = generate_establishment_id(row[0], row[1], row[2], row[3])
        
        # Handle empty/None values
        site_zip = str(row[4]).strip() if row[4] else None
        site_zip = site_zip if site_zip else None
        
        naics_code = str(row[5]).strip() if row[5] else None
        naics_code = naics_code if naics_code else None
        
        sic_code = str(row[6]).strip() if row[6] else None
        sic_code = sic_code if sic_code else None
        
        union_status = row[7].strip() if row[7] else None
        union_status = union_status if union_status else None
        
        employee_count = row[8] if row[8] and str(row[8]).strip() else None
        
        # Only keep first occurrence (or merge if needed)
        if est_id not in batch_dict:
            batch_dict[est_id] = (
                est_id,
                row[0],  # estab_name
                row[1],  # site_address
                row[2],  # site_city
                row[3],  # site_state
                site_zip,
                naics_code,
                sic_code,
                union_status,
                employee_count,
                row[9],  # first_inspection_date
                row[10], # last_inspection_date
                row[11]  # total_inspections
            )
    
    batch = list(batch_dict.values())
    print(f"  Deduplicated to {len(batch):,} unique establishment IDs")
    
    # Insert with ON CONFLICT UPDATE
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
    
    # Insert in smaller chunks
    chunk_size = 10000
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i+chunk_size]
        execute_values(pg_cur, insert_sql, chunk, page_size=1000)
        pg_conn.commit()
        print(f"    Inserted chunk {i//chunk_size + 1} ({len(chunk):,} records)")
    
    return len(batch)

def main():
    print("="*60)
    print("OSHA Establishment Extraction - 2012 to 2026")
    print("="*60)
    
    # Connect to databases
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(**PG_CONFIG)
    
    years = list(range(2012, 2027))
    total_loaded = 0
    
    for year in years:
        loaded = extract_year(year, sqlite_conn, pg_conn)
        total_loaded += loaded
    
    # Final count
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT COUNT(*) FROM osha_establishments")
    final_count = pg_cur.fetchone()[0]
    
    print("\n" + "="*60)
    print(f"COMPLETE: {final_count:,} unique establishments in PostgreSQL")
    print("="*60)
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    main()
