"""
Verify 2024 Expanded Organizing Events Against Database
Checks F7 employers, VR records, and discovered_employers table
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import os

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def check_f7_employer(cur, employer_name, city=None, state=None):
    """Check if employer exists in F7 data"""
    # Normalize name for search
    name_parts = employer_name.upper().replace(',', '').replace('.', '').split()[:3]
    search_pattern = '%' + '%'.join(name_parts) + '%'

    query = """
        SELECT employer_name, city, state, latest_union_name as union_name, latest_unit_size as workers
        FROM f7_employers_deduped
        WHERE UPPER(employer_name) LIKE %s
    """
    params = [search_pattern]

    if state and len(state) == 2:
        query += " AND state = %s"
        params.append(state.upper())

    query += " LIMIT 5"
    cur.execute(query, params)
    return cur.fetchall()

def check_vr_employer(cur, employer_name, state=None):
    """Check voluntary recognition records"""
    name_parts = employer_name.upper().replace(',', '').replace('.', '').split()[:2]
    search_pattern = '%' + '%'.join(name_parts) + '%'

    query = """
        SELECT employer_name, unit_city as city, unit_state as state, union_name, num_employees
        FROM nlrb_voluntary_recognition
        WHERE UPPER(employer_name) LIKE %s
    """
    params = [search_pattern]

    if state and len(state) == 2:
        query += " AND unit_state = %s"
        params.append(state.upper())

    query += " LIMIT 5"
    cur.execute(query, params)
    return cur.fetchall()

def check_discovered_employers(cur, employer_name, state=None):
    """Check if already in discovered_employers table"""
    name_parts = employer_name.upper().replace(',', '').replace('.', '').split()[:2]
    search_pattern = '%' + '%'.join(name_parts) + '%'

    query = """
        SELECT employer_name, city, state, union_name, num_employees, recognition_type
        FROM discovered_employers
        WHERE UPPER(employer_name) LIKE %s
    """
    params = [search_pattern]

    if state and len(state) == 2:
        query += " AND state = %s"
        params.append(state.upper())

    query += " LIMIT 5"
    cur.execute(query, params)
    return cur.fetchall()

def verify_events(csv_path):
    """Verify all events from CSV against database"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    results = {
        'found_f7': [],
        'found_vr': [],
        'found_discovered': [],
        'new_events': []
    }

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        events = list(reader)

    print(f"Checking {len(events)} events against database...\n")
    print("=" * 80)

    for event in events:
        event_id = event['event_id']
        employer = event['employer_name']
        state = event['location_state']
        union = event['union_name']
        workers = event.get('worker_count', 'N/A')
        event_type = event['event_type']

        # Check all three sources
        f7_matches = check_f7_employer(cur, employer, state=state if state != 'US' else None)
        vr_matches = check_vr_employer(cur, employer, state=state if state != 'US' else None)
        disc_matches = check_discovered_employers(cur, employer, state=state if state != 'US' else None)

        status = 'NEW'
        match_source = None

        if disc_matches:
            status = 'ALREADY_DISCOVERED'
            match_source = 'discovered_employers'
            results['found_discovered'].append(event)
        elif f7_matches:
            status = 'FOUND_F7'
            match_source = 'f7_employers'
            results['found_f7'].append(event)
        elif vr_matches:
            status = 'FOUND_VR'
            match_source = 'vr_records'
            results['found_vr'].append(event)
        else:
            status = 'NEW - ADD'
            results['new_events'].append(event)

        print(f"{event_id}: {employer[:40]:<40} | {state:>2} | {event_type:<20} | {status}")

        if match_source and (f7_matches or vr_matches or disc_matches):
            matches = disc_matches or f7_matches or vr_matches
            for m in matches[:1]:
                print(f"    -> Match: {m.get('employer_name', 'N/A')[:50]}")

    print("\n" + "=" * 80)
    print(f"\nSUMMARY:")
    print(f"  Already in discovered_employers: {len(results['found_discovered'])}")
    print(f"  Found in F7 employers: {len(results['found_f7'])}")
    print(f"  Found in VR records: {len(results['found_vr'])}")
    print(f"  NEW (to be added): {len(results['new_events'])}")

    cur.close()
    conn.close()

    return results

def insert_new_events(events):
    """Insert new events into discovered_employers table"""
    if not events:
        print("\nNo new events to insert.")
        return

    conn = get_connection()
    cur = conn.cursor()

    # Map event types to recognition types
    type_map = {
        'election_win': 'NLRB_ELECTION',
        'election_loss': 'NLRB_ELECTION_LOSS',
        'voluntary_recognition': 'VOLUNTARY',
        'first_contract': 'FIRST_CONTRACT',
        'affiliation': 'AFFILIATION'
    }

    # Map affiliations
    affiliation_map = {
        'UAW International': 'UAW',
        'CWA CODE-CWA': 'CWA',
        'SEIU': 'SEIU',
        'SEIU-UHW': 'SEIU',
        'USW': 'USW',
        'IATSE': 'IATSE',
        'UE': 'UE',
        'Independent': 'INDEPENDENT',
        'IAM': 'IAM',
        'AFSCME': 'AFSCME',
        'UFCW': 'UFCW',
        'Teamsters': 'IBT',
        'UNITE HERE': 'UNITEHERE',
        'NewsGuild': 'CWA'
    }

    inserted = 0
    for event in events:
        event_type = event.get('event_type', '')
        rec_type = type_map.get(event_type, 'UNKNOWN')

        # Skip election losses for the discovered_employers table
        if event_type == 'election_loss':
            print(f"  Skipping (loss): {event['employer_name']}")
            continue

        affiliation = event.get('union_affiliation', '')
        mapped_aff = affiliation_map.get(affiliation, affiliation.upper()[:10] if affiliation else 'UNKNOWN')

        # Normalize employer name
        employer_name = event['employer_name']
        employer_normalized = employer_name.upper().replace(',', '').replace('.', '').replace("'", '')

        # Get worker count
        try:
            workers = int(event.get('worker_count', 0))
        except:
            workers = 0

        # Build notes
        notes = event.get('notes', '')
        if event.get('data_source'):
            notes = f"{notes}. Source: {event['data_source']}"

        try:
            cur.execute("""
                INSERT INTO discovered_employers (
                    employer_name, employer_name_normalized, city, state,
                    union_name, affiliation, num_employees,
                    recognition_type, recognition_date,
                    source_type, notes, verification_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                employer_name,
                employer_normalized,
                event.get('location_city', ''),
                event.get('location_state', ''),
                event.get('union_name', ''),
                mapped_aff,
                workers,
                rec_type,
                event.get('date', None),
                'DISCOVERY_2024_EXPANDED',
                notes[:500] if notes else None,
                'NEEDS_REVIEW'
            ))
            inserted += 1
            print(f"  Inserted: {employer_name[:50]}")
        except Exception as e:
            print(f"  Error inserting {employer_name}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nInserted {inserted} new records.")

if __name__ == '__main__':
    csv_path = os.path.join(os.path.dirname(__file__), '..', '..', '2024organizing_files', 'discovered_unions_2024_expanded.csv')

    print("=" * 80)
    print("VERIFYING 2024 EXPANDED ORGANIZING EVENTS")
    print("=" * 80 + "\n")

    results = verify_events(csv_path)

    if results['new_events']:
        print("\n" + "=" * 80)
        print("NEW EVENTS TO INSERT:")
        print("=" * 80)
        for e in results['new_events']:
            print(f"  {e['event_id']}: {e['employer_name'][:40]} ({e['location_state']}) - {e['union_name']} - {e.get('worker_count', 'N/A')} workers")

        print("\n" + "=" * 80)
        print("INSERTING NEW EVENTS...")
        print("=" * 80)
        insert_new_events(results['new_events'])
