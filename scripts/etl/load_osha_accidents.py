"""
OSHA Phase 5: Load Accidents & Fatalities (2012+)
Extracts accident data from SQLite and loads into PostgreSQL
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
BATCH_SIZE = 10000
START_DATE = '2012-01-01'

def generate_establishment_id(estab_name, site_address, site_city, site_state):
    """Generate MD5 hash matching the existing establishments"""
    name = (estab_name or '').upper().strip()
    addr = (site_address or '').upper().strip()
    city = (site_city or '').upper().strip()
    state = (site_state or '').upper().strip()
    key = f"{name}|{addr}|{city}|{state}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] OSHA Phase 5: Load Accidents & Fatalities")
    print(f"Start date filter: {START_DATE}")
    print("=" * 60)
    
    # Connect to databases
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cursor = pg_conn.cursor()
    
    # Count accidents from 2012+
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Counting accidents from {START_DATE}...")
    sqlite_cursor.execute('''
        SELECT COUNT(*) 
        FROM accident a
        WHERE a.event_date >= ?
    ''', (START_DATE,))
    total_count = sqlite_cursor.fetchone()[0]
    print(f"Total accidents to process: {total_count:,}")
    
    # Check fatality breakdown
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fatality breakdown:")
    sqlite_cursor.execute('''
        SELECT fatality, COUNT(*) as cnt
        FROM accident
        WHERE event_date >= ?
        GROUP BY fatality
    ''', (START_DATE,))
    for row in sqlite_cursor.fetchall():
        label = "Fatality" if row['fatality'] == 'X' else "Non-fatal/Unknown"
        print(f"  {label}: {row['cnt']:,}")
    
    # Clear existing data
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Clearing existing accident data...")
    pg_cursor.execute("TRUNCATE TABLE osha_accidents RESTART IDENTITY")
    pg_conn.commit()
    
    # Load establishment IDs for matching
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading establishment IDs for matching...")
    pg_cursor.execute("SELECT establishment_id FROM osha_establishments")
    valid_establishment_ids = set(row[0] for row in pg_cursor.fetchall())
    print(f"Loaded {len(valid_establishment_ids):,} establishment IDs")
    
    # Extract accidents with inspection data via accident_injury link
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Extracting accidents with establishment data...")
    
    query = '''
        SELECT 
            a.summary_nr,
            a.event_date,
            a.event_desc,
            a.fatality,
            i.estab_name,
            i.site_address,
            i.site_city,
            i.site_state,
            COUNT(DISTINCT ai.injury_line_nr) as injury_count,
            SUM(CASE WHEN ai.degree_of_inj = 1 THEN 1 ELSE 0 END) as fatality_injuries,
            SUM(CASE WHEN ai.degree_of_inj = 2 THEN 1 ELSE 0 END) as hospitalized_count
        FROM accident a
        JOIN accident_injury ai ON a.summary_nr = ai.summary_nr
        JOIN inspection i ON ai.rel_insp_nr = i.activity_nr
        WHERE a.event_date >= ?
        GROUP BY a.summary_nr, a.event_date, a.event_desc, a.fatality, 
                 i.estab_name, i.site_address, i.site_city, i.site_state
        ORDER BY a.summary_nr
    '''
    
    sqlite_cursor.execute(query, (START_DATE,))
    
    batch = []
    processed = 0
    matched = 0
    unmatched = 0
    fatalities = 0
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing accidents...")
    
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
            
            if est_id in valid_establishment_ids:
                matched += 1
            else:
                unmatched += 1
                est_id = None
            
            # Determine if fatality (from accident.fatality column or injury data)
            is_fatality = (row['fatality'] == 'X') or (row['fatality_injuries'] or 0) > 0
            if is_fatality:
                fatalities += 1
            
            # Parse date
            event_date = None
            if row['event_date']:
                try:
                    event_date = row['event_date'][:10]
                except:
                    pass
            
            batch.append((
                row['summary_nr'],
                est_id,
                event_date,
                is_fatality,
                row['injury_count'] or 0,
                row['hospitalized_count'] or 0,
                (row['event_desc'] or '')[:2000]
            ))
        
        # Insert batch
        if batch:
            execute_values(
                pg_cursor,
                '''
                INSERT INTO osha_accidents 
                (summary_nr, establishment_id, event_date, is_fatality, 
                 injury_count, hospitalized, event_description)
                VALUES %s
                ''',
                batch,
                page_size=5000
            )
            pg_conn.commit()
            
            processed += len(batch)
            pct = (processed / total_count) * 100
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed: {processed:>8,} / {total_count:,} ({pct:5.1f}%) | Matched: {matched:,} | Fatalities: {fatalities:,}")
            batch = []
    
    # Final stats
    print("\n" + "=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] PHASE 5 COMPLETE")
    print(f"Total accidents loaded: {processed:,}")
    if processed > 0:
        print(f"Matched to establishments: {matched:,} ({matched/processed*100:.1f}%)")
        print(f"Fatality incidents: {fatalities:,}")
    
    # Verify in PostgreSQL
    pg_cursor.execute("SELECT COUNT(*) FROM osha_accidents")
    pg_count = pg_cursor.fetchone()[0]
    print(f"\nPostgreSQL osha_accidents: {pg_count:,} records")
    
    pg_cursor.execute("""
        SELECT 
            is_fatality,
            COUNT(*) as cnt,
            SUM(injury_count) as total_injuries,
            SUM(hospitalized) as total_hospitalized
        FROM osha_accidents
        GROUP BY is_fatality
    """)
    print("\nAccident summary:")
    for row in pg_cursor.fetchall():
        label = "Fatality" if row[0] else "Non-fatal"
        print(f"  {label:12}: {row[1]:>8,} incidents, {row[2] or 0:>8,} injuries, {row[3] or 0:>6,} hospitalized")
    
    # Year breakdown
    pg_cursor.execute("""
        SELECT 
            EXTRACT(YEAR FROM event_date)::int as year,
            COUNT(*) as accidents,
            SUM(CASE WHEN is_fatality THEN 1 ELSE 0 END) as fatalities
        FROM osha_accidents
        WHERE event_date IS NOT NULL
        GROUP BY EXTRACT(YEAR FROM event_date)
        ORDER BY year
    """)
    print("\nBy year:")
    for row in pg_cursor.fetchall():
        print(f"  {row[0]}: {row[1]:>6,} accidents, {row[2]:>4,} fatalities")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == '__main__':
    main()
