import os
"""
Load F-7 Employers and Crosswalk data from SQLite into PostgreSQL
Database: olms_multiyear
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import time

# Configuration
PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

F7_DB = r'C:\Users\jakew\Downloads\labor-data-project\data\f7\employers_deduped.db'
CROSSWALK_DB = r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db'

BATCH_SIZE = 5000

def get_pg_connection():
    return psycopg2.connect(**PG_CONFIG)

def load_f7_employers():
    """Load F-7 employers table"""
    print("\n" + "="*60)
    print("Loading F-7 Employers...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(F7_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    # Get data from SQLite
    cursor.execute("SELECT * FROM employers")
    rows = cursor.fetchall()
    total = len(rows)
    print(f"Found {total:,} employers to load")
    
    # Insert into PostgreSQL
    insert_sql = """
        INSERT INTO f7_employers (
            employer_id, employer_name, city, state, street, zip,
            latest_notice_date, latest_unit_size, latest_union_fnum,
            latest_union_name, naics, healthcare_related, filing_count,
            potentially_defunct, latitude, longitude, geocode_status,
            data_quality_flag
        ) VALUES %s
        ON CONFLICT (employer_id) DO NOTHING
    """
    
    data = []
    for row in rows:
        data.append((
            row['employer_id'], row['employer_name'], row['city'],
            row['state'], row['street'], row['zip'],
            row['latest_notice_date'], row['latest_unit_size'],
            row['latest_union_fnum'], row['latest_union_name'],
            row['naics'], row['healthcare_related'], row['filing_count'],
            row['potentially_defunct'], row['latitude'], row['longitude'],
            row['geocode_status'], row['data_quality_flag']
        ))
    
    # Batch insert
    start = time.time()
    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i:i+BATCH_SIZE]
        execute_values(pg_cursor, insert_sql, batch)
        pg_conn.commit()
        print(f"  Loaded {min(i+BATCH_SIZE, len(data)):,} / {total:,}")
    
    elapsed = time.time() - start
    print(f"✓ F-7 Employers loaded in {elapsed:.1f}s")
    
    sqlite_conn.close()
    pg_conn.close()

def load_f7_relations():
    """Load F-7 union-employer relations"""
    print("\n" + "="*60)
    print("Loading F-7 Union-Employer Relations...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(F7_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    cursor.execute("SELECT * FROM union_employer_relations")
    rows = cursor.fetchall()
    total = len(rows)
    print(f"Found {total:,} relations to load")
    
    insert_sql = """
        INSERT INTO f7_union_employer_relations (
            employer_id, union_file_number, bargaining_unit_size, notice_date
        ) VALUES %s
    """
    
    data = []
    for row in rows:
        data.append((
            row['employer_id'], row['union_file_number'],
            row['bargaining_unit_size'], row['notice_date']
        ))
    
    start = time.time()
    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i:i+BATCH_SIZE]
        execute_values(pg_cursor, insert_sql, batch)
        pg_conn.commit()
        print(f"  Loaded {min(i+BATCH_SIZE, len(data)):,} / {total:,}")
    
    elapsed = time.time() - start
    print(f"✓ Relations loaded in {elapsed:.1f}s")
    
    sqlite_conn.close()
    pg_conn.close()

def load_crosswalk_sectors():
    """Load sector lookup table"""
    print("\n" + "="*60)
    print("Loading Crosswalk Sector Lookup...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(CROSSWALK_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    cursor.execute("SELECT * FROM sector_lookup")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} sectors")
    
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO crosswalk_sector_lookup 
            (sector_code, sector_name, description, f7_expected, governing_law)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sector_code) DO NOTHING
        """, (row['sector_code'], row['sector_name'], row['description'],
              row['f7_expected'], row['governing_law']))
    
    pg_conn.commit()
    print(f"✓ Sectors loaded")
    
    sqlite_conn.close()
    pg_conn.close()

def load_crosswalk_affiliations():
    """Load affiliation-sector map"""
    print("\n" + "="*60)
    print("Loading Crosswalk Affiliation-Sector Map...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(CROSSWALK_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    cursor.execute("SELECT * FROM affiliation_sector_map")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} affiliations")
    
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO crosswalk_affiliation_sector_map 
            (aff_abbr, aff_name, sector_code, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (aff_abbr) DO NOTHING
        """, (row['aff_abbr'], row['aff_name'], row['sector_code'], row['notes']))
    
    pg_conn.commit()
    print(f"✓ Affiliations loaded")
    
    sqlite_conn.close()
    pg_conn.close()

def load_crosswalk_unions_master():
    """Load unions master table"""
    print("\n" + "="*60)
    print("Loading Crosswalk Unions Master...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(CROSSWALK_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    cursor.execute("SELECT * FROM unions_master")
    rows = cursor.fetchall()
    total = len(rows)
    print(f"Found {total:,} union records")
    
    insert_sql = """
        INSERT INTO crosswalk_unions_master (
            union_name, aff_abbr, f_num, members, yr_covered, city, state,
            source_year, sector, f7_union_name, f7_employer_count,
            f7_total_workers, f7_states, has_f7_employers, match_status
        ) VALUES %s
    """
    
    data = []
    for row in rows:
        data.append((
            row['union_name'], row['aff_abbr'], row['f_num'], row['members'],
            row['yr_covered'], row['city'], row['state'], row['source_year'],
            row['sector'], row['f7_union_name'], row['f7_employer_count'],
            row['f7_total_workers'], row['f7_states'], row['has_f7_employers'],
            row['match_status']
        ))
    
    start = time.time()
    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i:i+BATCH_SIZE]
        execute_values(pg_cursor, insert_sql, batch)
        pg_conn.commit()
        print(f"  Loaded {min(i+BATCH_SIZE, len(data)):,} / {total:,}")
    
    elapsed = time.time() - start
    print(f"✓ Unions master loaded in {elapsed:.1f}s")
    
    sqlite_conn.close()
    pg_conn.close()

def load_crosswalk_f7_only():
    """Load F-7 only unions (unions not in LM filings)"""
    print("\n" + "="*60)
    print("Loading Crosswalk F-7 Only Unions...")
    print("="*60)
    
    sqlite_conn = sqlite3.connect(CROSSWALK_DB)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    cursor.execute("SELECT * FROM f7_only_unions")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} F-7 only unions")
    
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO crosswalk_f7_only_unions 
            (f_num, union_name, employer_count, total_workers, likely_reason)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (f_num) DO NOTHING
        """, (row['f_num'], row['union_name'], row['employer_count'],
              row['total_workers'], row['likely_reason']))
    
    pg_conn.commit()
    print(f"✓ F-7 only unions loaded")
    
    sqlite_conn.close()
    pg_conn.close()

def verify_load():
    """Verify data was loaded correctly"""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    tables = [
        'f7_employers',
        'f7_union_employer_relations',
        'crosswalk_sector_lookup',
        'crosswalk_affiliation_sector_map',
        'crosswalk_unions_master',
        'crosswalk_f7_only_unions'
    ]
    
    for table in tables:
        pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = pg_cursor.fetchone()[0]
        print(f"  {table}: {count:,} rows")
    
    pg_conn.close()

if __name__ == "__main__":
    print("="*60)
    print("F-7 AND CROSSWALK DATA LOADER")
    print("="*60)
    print(f"Target database: {PG_CONFIG['database']}")
    print(f"F-7 source: {F7_DB}")
    print(f"Crosswalk source: {CROSSWALK_DB}")
    
    try:
        load_f7_employers()
        load_f7_relations()
        load_crosswalk_sectors()
        load_crosswalk_affiliations()
        load_crosswalk_unions_master()
        load_crosswalk_f7_only()
        verify_load()
        
        print("\n" + "="*60)
        print("✓ ALL DATA LOADED SUCCESSFULLY")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
