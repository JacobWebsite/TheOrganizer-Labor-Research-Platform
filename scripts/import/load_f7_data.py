import os
"""
Load F-7 Employer Data into PostgreSQL
Migrates data from SQLite (union_lm_f7_crosswalk.db) to PostgreSQL (olms_multiyear)
Handles deduplication of unions_master by keeping most recent record
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import time

# Configuration
SQLITE_DB = r"C:\Users\jakew\Downloads\Claude Ai union project\lm and f7 documents 1_22\union_lm_f7_crosswalk.db"

PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', ''),
    'sslmode': 'disable'
}

BATCH_SIZE = 5000

def load_f7_employers(sqlite_cur, pg_cur):
    """Load f7_employers table"""
    print("\n[1/2] Loading f7_employers...")
    
    # Get count
    sqlite_cur.execute("SELECT COUNT(*) FROM f7_employers")
    total = sqlite_cur.fetchone()[0]
    print(f"  Source records: {total:,}")
    
    # Clear existing data
    pg_cur.execute("TRUNCATE TABLE f7_employers CASCADE")
    
    # Fetch all data
    sqlite_cur.execute("""
        SELECT 
            employer_id,
            employer_name,
            street,
            city,
            state,
            zip,
            latest_notice_date,
            latest_unit_size,
            CAST(union_fnum AS INTEGER) as latest_union_fnum,
            union_name as latest_union_name,
            naics,
            healthcare_related,
            filing_count,
            potentially_defunct,
            latitude,
            longitude,
            geocode_status
        FROM f7_employers
    """)
    
    inserted = 0
    batch = []
    
    for row in sqlite_cur:
        # Convert row to tuple with proper types
        record = (
            row[0],                          # employer_id
            row[1],                          # employer_name
            row[2],                          # street
            row[3],                          # city
            row[4],                          # state
            row[5],                          # zip
            row[6],                          # latest_notice_date
            row[7],                          # latest_unit_size
            int(row[8]) if row[8] else None, # latest_union_fnum
            row[9],                          # latest_union_name
            row[10],                         # naics
            bool(row[11]) if row[11] is not None else False,  # healthcare_related
            row[12] or 1,                    # filing_count
            bool(row[13]) if row[13] is not None else False,  # potentially_defunct
            row[14],                         # latitude
            row[15],                         # longitude
            row[16]                          # geocode_status
        )
        batch.append(record)
        
        if len(batch) >= BATCH_SIZE:
            execute_values(pg_cur, """
                INSERT INTO f7_employers (
                    employer_id, employer_name, street, city, state, zip,
                    latest_notice_date, latest_unit_size, latest_union_fnum, latest_union_name,
                    naics, healthcare_related, filing_count, potentially_defunct,
                    latitude, longitude, geocode_status
                ) VALUES %s
            """, batch)
            inserted += len(batch)
            print(f"  Inserted {inserted:,} / {total:,} ({100*inserted/total:.1f}%)")
            batch = []
    
    # Insert remaining
    if batch:
        execute_values(pg_cur, """
            INSERT INTO f7_employers (
                employer_id, employer_name, street, city, state, zip,
                latest_notice_date, latest_unit_size, latest_union_fnum, latest_union_name,
                naics, healthcare_related, filing_count, potentially_defunct,
                latitude, longitude, geocode_status
            ) VALUES %s
        """, batch)
        inserted += len(batch)
    
    print(f"  Loaded {inserted:,} employers")
    return inserted


def load_unions_master(sqlite_cur, pg_cur):
    """Load unions_master table with deduplication"""
    print("\n[2/2] Loading unions_master...")
    
    # Get counts
    sqlite_cur.execute("SELECT COUNT(*) FROM unions_master")
    total = sqlite_cur.fetchone()[0]
    sqlite_cur.execute("SELECT COUNT(DISTINCT CAST(f_num AS INTEGER)) FROM unions_master")
    unique = sqlite_cur.fetchone()[0]
    print(f"  Source records: {total:,} (unique f_num: {unique:,})")
    
    # Clear existing data
    pg_cur.execute("TRUNCATE TABLE unions_master CASCADE")
    
    # Fetch deduplicated data - keep record with most recent source_year, 
    # then highest f7_employer_count, then highest members
    sqlite_cur.execute("""
        WITH ranked AS (
            SELECT 
                CAST(f_num AS INTEGER) as f_num,
                union_name,
                aff_abbr,
                members,
                yr_covered,
                city,
                state,
                source_year,
                sector,
                f7_union_name,
                f7_employer_count,
                f7_total_workers,
                f7_states,
                has_f7_employers,
                match_status,
                ROW_NUMBER() OVER (
                    PARTITION BY CAST(f_num AS INTEGER) 
                    ORDER BY source_year DESC, f7_employer_count DESC, members DESC
                ) as rn
            FROM unions_master
            WHERE f_num IS NOT NULL
        )
        SELECT 
            f_num, union_name, aff_abbr, members, yr_covered,
            city, state, source_year, sector, f7_union_name,
            f7_employer_count, f7_total_workers, f7_states,
            has_f7_employers, match_status
        FROM ranked
        WHERE rn = 1
    """)
    
    inserted = 0
    batch = []
    
    for row in sqlite_cur:
        # Convert members from string to int if needed
        members = row[3]
        if isinstance(members, str):
            try:
                members = int(float(members)) if members else None
            except:
                members = None
        
        record = (
            str(int(row[0])) if row[0] else None,  # f_num as string (to match lm_data.f_num)
            row[1],                                 # union_name
            row[2],                                 # aff_abbr
            members,                                # members
            int(row[4]) if row[4] else None,       # yr_covered
            row[5],                                 # city
            row[6],                                 # state
            int(row[7]) if row[7] else None,       # source_year
            row[8],                                 # sector
            row[9],                                 # f7_union_name
            int(row[10]) if row[10] else 0,        # f7_employer_count
            int(row[11]) if row[11] else 0,        # f7_total_workers
            row[12],                               # f7_states
            bool(row[13]) if row[13] is not None else False,  # has_f7_employers
            row[14]                                # match_status
        )
        batch.append(record)
        
        if len(batch) >= BATCH_SIZE:
            execute_values(pg_cur, """
                INSERT INTO unions_master (
                    f_num, union_name, aff_abbr, members, yr_covered,
                    city, state, source_year, sector, f7_union_name,
                    f7_employer_count, f7_total_workers, f7_states,
                    has_f7_employers, match_status
                ) VALUES %s
            """, batch)
            inserted += len(batch)
            print(f"  Inserted {inserted:,} / {unique:,} ({100*inserted/unique:.1f}%)")
            batch = []
    
    # Insert remaining
    if batch:
        execute_values(pg_cur, """
            INSERT INTO unions_master (
                f_num, union_name, aff_abbr, members, yr_covered,
                city, state, source_year, sector, f7_union_name,
                f7_employer_count, f7_total_workers, f7_states,
                has_f7_employers, match_status
            ) VALUES %s
        """, batch)
        inserted += len(batch)
    
    print(f"  Loaded {inserted:,} unions (deduplicated from {total:,})")
    return inserted


def verify_data(pg_cur):
    """Verify loaded data"""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    # Table counts
    pg_cur.execute("SELECT COUNT(*) FROM f7_employers")
    emp_count = pg_cur.fetchone()[0]
    
    pg_cur.execute("SELECT COUNT(*) FROM unions_master")
    union_count = pg_cur.fetchone()[0]
    
    print(f"\nTable counts:")
    print(f"  f7_employers:  {emp_count:,}")
    print(f"  unions_master: {union_count:,}")
    
    # Geocoding stats
    pg_cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) as geocoded
        FROM f7_employers
    """)
    row = pg_cur.fetchone()
    print(f"\nGeocoding:")
    print(f"  Total employers: {row[0]:,}")
    print(f"  Geocoded: {row[1]:,} ({100*row[1]/row[0]:.1f}%)")
    
    # State summary (top 5)
    pg_cur.execute("""
        SELECT state, COUNT(*) as cnt, SUM(latest_unit_size) as workers
        FROM f7_employers
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY cnt DESC
        LIMIT 5
    """)
    print(f"\nTop 5 states by employer count:")
    for row in pg_cur.fetchall():
        workers = row[2] or 0
        print(f"  {row[0]}: {row[1]:,} employers, {workers:,} workers")
    
    # Sector summary
    pg_cur.execute("SELECT * FROM v_sector_summary")
    print(f"\nSector summary:")
    for row in pg_cur.fetchall():
        print(f"  {row[0]}: {row[4] or 0:,} unions, {row[5] or 0:,} members")
    
    # Match status summary
    pg_cur.execute("SELECT * FROM v_match_status_summary")
    print(f"\nMatch status summary:")
    for row in pg_cur.fetchall():
        print(f"  {row[0]}: {row[3] or 0:,} unions")
    
    # Test join with lm_data
    pg_cur.execute("""
        SELECT COUNT(*) 
        FROM lm_data l 
        JOIN unions_master um ON l.f_num = um.f_num
        WHERE l.yr_covered = 2024
    """)
    join_count = pg_cur.fetchone()[0]
    print(f"\nJoin test (lm_data 2024 -> unions_master): {join_count:,} matches")
    
    # F7 employers linked to unions_master
    pg_cur.execute("""
        SELECT COUNT(*)
        FROM f7_employers e
        JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
    """)
    emp_link = pg_cur.fetchone()[0]
    print(f"F7 employers linked to unions_master: {emp_link:,} / {emp_count:,}")


def main():
    start_time = time.time()
    
    print("="*60)
    print("F-7 DATA LOADER")
    print("="*60)
    print(f"Source: {SQLITE_DB}")
    print(f"Target: PostgreSQL olms_multiyear")
    
    # Connect to databases
    print("\nConnecting to databases...")
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_cur = sqlite_conn.cursor()
    
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()
    
    try:
        # Load data
        emp_count = load_f7_employers(sqlite_cur, pg_cur)
        union_count = load_unions_master(sqlite_cur, pg_cur)
        
        # Commit
        pg_conn.commit()
        print("\nData committed successfully!")
        
        # Verify
        verify_data(pg_cur)
        
    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        sqlite_cur.close()
        sqlite_conn.close()
        pg_cur.close()
        pg_conn.close()
    
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f} seconds")
    print("="*60)


if __name__ == "__main__":
    main()
