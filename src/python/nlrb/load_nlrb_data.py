import os
"""
NLRB Data Loader
Loads NLRB case data from SQLite to PostgreSQL

Usage: python load_nlrb_data.py
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime

# Configuration
NLRB_DB = r'C:\Users\jakew\Downloads\labor-data-project\data\nlrb\nlrb.db'
PG_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}
BATCH_SIZE = 10000

def get_connections():
    sqlite_conn = sqlite3.connect(NLRB_DB)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_conn.autocommit = False
    return sqlite_conn, pg_conn

def load_cases(sqlite_cur, pg_cur):
    """Load nlrb_cases from filing table"""
    print("\nLoading cases...")
    sqlite_cur.execute("""
        SELECT case_number, name, case_type, city, state, 
               date_filed, date_closed, status, reason_closed,
               region_assigned, number_of_eligible_voters,
               number_of_voters_on_petition_or_charge, certified_representative
        FROM filing
    """)
    
    insert_sql = """
        INSERT INTO nlrb_cases 
        (case_number, case_name, case_type, city, state, date_filed, date_closed,
         status, reason_closed, region_assigned, num_eligible_voters,
         num_voters_on_petition, certified_representative)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_number) DO NOTHING
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((
            row['case_number'], row['name'], row['case_type'],
            row['city'], row['state'], row['date_filed'], row['date_closed'],
            row['status'], row['reason_closed'], row['region_assigned'],
            row['number_of_eligible_voters'], row['number_of_voters_on_petition_or_charge'],
            row['certified_representative']
        ))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            print(f"  {count:,} cases...")
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} cases")
    return count


def load_participants(sqlite_cur, pg_cur):
    """Load nlrb_participants - largest table (~1.9M)"""
    print("\nLoading participants...")
    sqlite_cur.execute("""
        SELECT case_number, participant, type, subtype,
               address_1, city, state, zip, phone_number
        FROM participant
        WHERE participant IS NOT NULL
    """)
    
    insert_sql = """
        INSERT INTO nlrb_participants 
        (case_number, participant_name, role_type, subtype, address, city, state, zip, phone)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((
            row['case_number'], row['participant'], row['type'], row['subtype'],
            row['address_1'], row['city'], row['state'], row['zip'], row['phone_number']
        ))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            print(f"  {count:,} participants...")
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} participants")
    return count

def load_elections(sqlite_cur, pg_cur):
    """Load nlrb_elections"""
    print("\nLoading elections...")
    sqlite_cur.execute("""
        SELECT election_id, case_number, voting_unit_id, date,
               tally_type, ballot_type, unit_size
        FROM election
    """)
    
    insert_sql = """
        INSERT INTO nlrb_elections 
        (election_id, case_number, voting_unit_id, election_date, tally_type, ballot_type, unit_size)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (election_id) DO NOTHING
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((
            row['election_id'], row['case_number'], row['voting_unit_id'],
            row['date'], row['tally_type'], row['ballot_type'], row['unit_size']
        ))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} elections")
    return count

def load_tallies(sqlite_cur, pg_cur):
    """Load nlrb_tallies"""
    print("\nLoading tallies...")
    sqlite_cur.execute("SELECT election_id, option, votes FROM tally")
    
    insert_sql = """
        INSERT INTO nlrb_tallies (election_id, option, votes)
        VALUES (%s, %s, %s)
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((row['election_id'], row['option'], row['votes']))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} tallies")
    return count

def load_election_results(sqlite_cur, pg_cur):
    """Load nlrb_election_results"""
    print("\nLoading election results...")
    sqlite_cur.execute("""
        SELECT election_id, total_ballots_counted, void_ballots, challenged_ballots,
               challenges_are_determinative, runoff_required, union_to_certify
        FROM election_result
    """)
    
    insert_sql = """
        INSERT INTO nlrb_election_results 
        (election_id, total_ballots_counted, void_ballots, challenged_ballots,
         challenges_determinative, runoff_required, union_certified)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (election_id) DO NOTHING
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((
            row['election_id'], row['total_ballots_counted'], row['void_ballots'],
            row['challenged_ballots'], row['challenges_are_determinative'],
            row['runoff_required'], row['union_to_certify']
        ))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} election results")
    return count


def load_allegations(sqlite_cur, pg_cur):
    """Load nlrb_allegations"""
    print("\nLoading allegations...")
    sqlite_cur.execute("SELECT case_number, allegation FROM allegation WHERE allegation IS NOT NULL")
    
    insert_sql = """
        INSERT INTO nlrb_allegations (case_number, allegation_text)
        VALUES (%s, %s)
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((row['case_number'], row['allegation']))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            print(f"  {count:,} allegations...")
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} allegations")
    return count

def load_voting_units(sqlite_cur, pg_cur):
    """Load nlrb_voting_units"""
    print("\nLoading voting units...")
    sqlite_cur.execute("SELECT voting_unit_id, case_number, unit_id, description FROM voting_unit")
    
    insert_sql = """
        INSERT INTO nlrb_voting_units (voting_unit_id, case_number, unit_id, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (voting_unit_id) DO NOTHING
    """
    
    batch, count = [], 0
    for row in sqlite_cur:
        batch.append((row['voting_unit_id'], row['case_number'], row['unit_id'], row['description']))
        if len(batch) >= BATCH_SIZE:
            execute_batch(pg_cur, insert_sql, batch)
            count += len(batch)
            batch = []
    if batch:
        execute_batch(pg_cur, insert_sql, batch)
        count += len(batch)
    print(f"  Total: {count:,} voting units")
    return count

def main():
    print("="*60)
    print("NLRB Data Loader")
    print("="*60)
    print(f"Source: {NLRB_DB}")
    print(f"Target: PostgreSQL {PG_CONFIG['database']}")
    print(f"Started: {datetime.now()}")
    
    sqlite_conn, pg_conn = get_connections()
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    
    try:
        # Load in order respecting foreign keys
        cases = load_cases(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        participants = load_participants(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        elections = load_elections(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        tallies = load_tallies(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        results = load_election_results(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        allegations = load_allegations(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        voting_units = load_voting_units(sqlite_cur, pg_cur)
        pg_conn.commit()
        
        print("\n" + "="*60)
        print("LOAD COMPLETE")
        print("="*60)
        print(f"Cases:            {cases:>12,}")
        print(f"Participants:     {participants:>12,}")
        print(f"Elections:        {elections:>12,}")
        print(f"Tallies:          {tallies:>12,}")
        print(f"Election Results: {results:>12,}")
        print(f"Allegations:      {allegations:>12,}")
        print(f"Voting Units:     {voting_units:>12,}")
        print(f"Finished: {datetime.now()}")
        
    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == '__main__':
    main()
