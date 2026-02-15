import os
from db_config import get_connection
"""
Union Discovery 2024 - Verification and Import Script
Verifies discovered 2024 organizing events against the Labor Relations Platform database.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import json
from datetime import datetime

# Database connection
conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

API_BASE = "http://localhost:8000/api"

# Discovered 2024 events from web research
DISCOVERED_EVENTS = [
    {
        "id": 1,
        "employer_name": "The Bazaar by José Andrés",
        "employer_name_normalized": "BAZAAR JOSE ANDRES",
        "city": "Washington",
        "state": "DC",
        "union_name": "UNITE HERE Local 25",
        "affiliation": "UNITEHERE",
        "local_number": "25",
        "num_employees": 140,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-02-02",
        "naics_sector": "72",
        "source_url": "https://unitehere.org/press-releases/workers-at-the-bazaar-by-jose-andres-win-union-recognition/",
        "notes": "Restaurant workers in Waldorf Astoria hotel"
    },
    {
        "id": 2,
        "employer_name": "Activision Central QA (Microsoft)",
        "employer_name_normalized": "ACTIVISION CENTRAL QA MICROSOFT",
        "city": "El Segundo",
        "state": "CA",
        "union_name": "CWA Locals 9400/6215/7250",
        "affiliation": "CWA",
        "local_number": "9400",
        "num_employees": 600,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-03-08",
        "naics_sector": "51",
        "source_url": "https://cwa-union.org/news/releases/quality-assurance-workers-activision-establish-largest-certified-union-us-video-game",
        "notes": "Largest US video game union. Workers in CA, TX, MN under Microsoft neutrality agreement"
    },
    {
        "id": 3,
        "employer_name": "CBS News Digital",
        "employer_name_normalized": "CBS NEWS DIGITAL",
        "city": "New York",
        "state": "NY",
        "union_name": "Writers Guild of America East",
        "affiliation": "WGAE",
        "local_number": None,
        "num_employees": 100,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-02-08",
        "naics_sector": "51",
        "source_url": "https://www.wgaeast.org/",
        "notes": "Digital journalists demanded voluntary recognition"
    },
    {
        "id": 4,
        "employer_name": "Oakland Museum of California",
        "employer_name_normalized": "OAKLAND MUSEUM CALIFORNIA",
        "city": "Oakland",
        "state": "CA",
        "union_name": "AFSCME Council 57",
        "affiliation": "AFSCME",
        "local_number": "57",
        "num_employees": 60,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-03-14",
        "naics_sector": "71",
        "source_url": "https://www.afscme.org/blog/oakland-museum-of-california-recognizes-union-workers-formed-through-afscme",
        "notes": "Cultural workers via AFSCME CWU campaign"
    },
    {
        "id": 5,
        "employer_name": "Brown University (Postdocs)",
        "employer_name_normalized": "BROWN UNIVERSITY POSTDOCS",
        "city": "Providence",
        "state": "RI",
        "union_name": "UAW",
        "affiliation": "UAW",
        "local_number": None,
        "num_employees": 400,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-01-31",
        "naics_sector": "61",
        "source_url": "https://www.browndailyherald.com/article/2024/01/brown-postdoc-union-wins-university-recognition",
        "notes": "Postdoctoral researchers"
    },
    {
        "id": 6,
        "employer_name": "Siemens Mobility (Brightline West)",
        "employer_name_normalized": "SIEMENS MOBILITY BRIGHTLINE WEST",
        "city": "Las Vegas",
        "state": "NV",
        "union_name": "International Association of Machinists",
        "affiliation": "IAM",
        "local_number": None,
        "num_employees": 500,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-05-07",
        "naics_sector": "33",
        "source_url": "https://www.goiam.org/news/iam-union-statement-on-voluntary-recognition-agreement-with-siemens-mobility/",
        "notes": "High-speed rail train set manufacturing agreement"
    },
    {
        "id": 7,
        "employer_name": "Guthrie Theater (Front-of-House)",
        "employer_name_normalized": "GUTHRIE THEATER FOH",
        "city": "Minneapolis",
        "state": "MN",
        "union_name": "IATSE Local 13",
        "affiliation": "IATSE",
        "local_number": "13",
        "num_employees": 80,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-15",
        "naics_sector": "71",
        "source_url": "https://aflcio.org/2024/7/1/worker-wins-when-workers-stand-together-we-win",
        "notes": "70% voted yes. Front-facing staff including box office, guest services"
    },
    {
        "id": 8,
        "employer_name": "National Sawdust",
        "employer_name_normalized": "NATIONAL SAWDUST",
        "city": "Brooklyn",
        "state": "NY",
        "union_name": "IATSE Local 306",
        "affiliation": "IATSE",
        "local_number": "306",
        "num_employees": 25,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-06-20",
        "naics_sector": "71",
        "source_url": "https://aflcio.org/2024/7/1/worker-wins-when-workers-stand-together-we-win",
        "notes": "Nonprofit music venue ushers in Williamsburg"
    },
    {
        "id": 9,
        "employer_name": "South Florida Sun Sentinel",
        "employer_name_normalized": "SOUTH FLORIDA SUN SENTINEL",
        "city": "Fort Lauderdale",
        "state": "FL",
        "union_name": "NewsGuild-CWA",
        "affiliation": "CWA",
        "local_number": None,
        "num_employees": 75,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-08-05",
        "naics_sector": "51",
        "source_url": "https://aflcio.org/2024/8/9/worker-wins-great-win-us-and-our-members",
        "notes": "Alden Global Capital-owned newspaper. Unanimous landslide"
    },
    {
        "id": 10,
        "employer_name": "Prism Reports",
        "employer_name_normalized": "PRISM REPORTS",
        "city": "Remote",
        "state": "NY",
        "union_name": "Prism Workers United",
        "affiliation": "INDEPENDENT",
        "local_number": None,
        "num_employees": 15,
        "recognition_type": "VOLUNTARY",
        "recognition_date": "2024-08-01",
        "naics_sector": "51",
        "source_url": "https://aflcio.org/2024/8/9/worker-wins-great-win-us-and-our-members",
        "notes": "100% card sign. Independent nonprofit newsroom"
    },
    {
        "id": 11,
        "employer_name": "PetSmart Mishawaka",
        "employer_name_normalized": "PETSMART MISHAWAKA",
        "city": "Mishawaka",
        "state": "IN",
        "union_name": "UFCW",
        "affiliation": "UFCW",
        "local_number": None,
        "num_employees": 25,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-10-01",
        "naics_sector": "44",
        "source_url": "https://aflcio.org/2024/10/10/worker-wins-collectively-our-voice-powerful",
        "notes": "First PetSmart union in US. Vote 12-2"
    },
    {
        "id": 12,
        "employer_name": "DreamWorks Animation (Production)",
        "employer_name_normalized": "DREAMWORKS ANIMATION PRODUCTION",
        "city": "Glendale",
        "state": "CA",
        "union_name": "IATSE Local 839 / Local 700",
        "affiliation": "IATSE",
        "local_number": "839",
        "num_employees": 160,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-04-15",
        "naics_sector": "51",
        "source_url": "https://aflcio.org/2024/4/18/worker-wins-new-way-doing-business",
        "notes": "Largest unit to join with AMPTP seat"
    },
    {
        "id": 13,
        "employer_name": "Truetimber Arborists",
        "employer_name_normalized": "TRUETIMBER ARBORISTS",
        "city": "Richmond",
        "state": "VA",
        "union_name": "IAM Local 10",
        "affiliation": "IAM",
        "local_number": "10",
        "num_employees": 30,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-07-20",
        "naics_sector": "56",
        "source_url": "https://aflcio.org/2024/7/29/worker-wins-working-people-are-front-and-center-policymaking",
        "notes": "First residential tree care union in US. 80% signed cards"
    },
    {
        "id": 14,
        "employer_name": "CVS Pharmacy (Rhode Island)",
        "employer_name_normalized": "CVS PHARMACY RHODE ISLAND",
        "city": "Warwick",
        "state": "RI",
        "union_name": "Pharmacy Guild / IAM Healthcare",
        "affiliation": "IAM",
        "local_number": None,
        "num_employees": 20,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-05-25",
        "naics_sector": "44",
        "source_url": "https://aflcio.org/2024/5/31/worker-wins-fighting-better-wages-and-working-conditions",
        "notes": "First CVS unions in company home state. Two stores"
    },
    {
        "id": 15,
        "employer_name": "Shedd Aquarium",
        "employer_name_normalized": "SHEDD AQUARIUM",
        "city": "Chicago",
        "state": "IL",
        "union_name": "AFSCME Council 31",
        "affiliation": "AFSCME",
        "local_number": "31",
        "num_employees": 200,
        "recognition_type": "NLRB_ELECTION",
        "recognition_date": "2024-09-15",
        "naics_sector": "71",
        "source_url": "https://www.afscme.org/blog/shedd-aquarium-employees-win-union-election-despite-managements-misinformation-campaign",
        "notes": "9th Chicago cultural institution to join AFSCME"
    },
    {
        "id": 16,
        "employer_name": "The Venetian Resort",
        "employer_name_normalized": "VENETIAN RESORT LAS VEGAS",
        "city": "Las Vegas",
        "state": "NV",
        "union_name": "Culinary Union UNITE HERE",
        "affiliation": "UNITEHERE",
        "local_number": "226",
        "num_employees": 4000,
        "recognition_type": "FIRST_CONTRACT",
        "recognition_date": "2024-09-30",
        "naics_sector": "72",
        "source_url": "https://aflcio.org/2024/10/3/worker-wins-freedom-intimidation-work",
        "notes": "25-year fight. First contract. 100% Strip now unionized"
    },
    {
        "id": 17,
        "employer_name": "California Child Care Providers",
        "employer_name_normalized": "CALIFORNIA CHILD CARE PROVIDERS",
        "city": "Statewide",
        "state": "CA",
        "union_name": "Child Care Providers United (UDW/AFSCME + SEIU)",
        "affiliation": "AFSCME",
        "local_number": "3930",
        "num_employees": 40000,
        "recognition_type": "STATE_PUBLIC",
        "recognition_date": "2024-12-01",
        "naics_sector": "62",
        "source_url": "https://www.afscme.org/blog/californias-child-care-providers-win-historic-union-election-in-landslide",
        "notes": "Largest union election since 2024. 97% voted yes. 17 years in making"
    },
    {
        "id": 18,
        "employer_name": "Tribune Publications (8 units)",
        "employer_name_normalized": "TRIBUNE PUBLICATIONS ALDEN",
        "city": "Multiple",
        "state": "IL",
        "union_name": "NewsGuild-CWA",
        "affiliation": "CWA",
        "local_number": None,
        "num_employees": 500,
        "recognition_type": "FIRST_CONTRACT",
        "recognition_date": "2024-05-30",
        "naics_sector": "51",
        "source_url": "https://aflcio.org/2024/6/6/worker-wins-priceless-value-having-union-contract",
        "notes": "Historic first contract after 5 years with Alden Global Capital"
    },
    {
        "id": 19,
        "employer_name": "Half Price Books (Minnesota)",
        "employer_name_normalized": "HALF PRICE BOOKS MINNESOTA",
        "city": "Minneapolis",
        "state": "MN",
        "union_name": "UFCW Locals 663/1189",
        "affiliation": "UFCW",
        "local_number": "663",
        "num_employees": 50,
        "recognition_type": "FIRST_CONTRACT",
        "recognition_date": "2024-05-31",
        "naics_sector": "45",
        "source_url": "https://aflcio.org/2024/6/6/worker-wins-priceless-value-having-union-contract",
        "notes": "First in nation at chain. 4 Twin Cities stores. 33% wage increase"
    },
    {
        "id": 20,
        "employer_name": "Pineapple Street Studios",
        "employer_name_normalized": "PINEAPPLE STREET STUDIOS",
        "city": "Brooklyn",
        "state": "NY",
        "union_name": "Writers Guild of America East",
        "affiliation": "WGAE",
        "local_number": None,
        "num_employees": 40,
        "recognition_type": "FIRST_CONTRACT",
        "recognition_date": "2024-07-22",
        "naics_sector": "51",
        "source_url": "https://aflcio.org/2024/7/29/worker-wins-working-people-are-front-and-center-policymaking",
        "notes": "Podcast producers. AI protections. Audacy bankruptcy"
    }
]


def check_f7_employer(name, state):
    """Check if employer exists in f7_employers"""
    # Check exact and fuzzy matches
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size, latest_union_name
        FROM f7_employers
        WHERE (employer_name ILIKE %s OR employer_name ILIKE %s)
          AND state = %s
        LIMIT 5
    """, (f"%{name}%", f"%{name.split()[0]}%", state))
    return cur.fetchall()


def check_vr_employer(name, state):
    """Check if employer exists in voluntary recognition"""
    cur.execute("""
        SELECT id, employer_name, unit_city, unit_state, num_employees, union_name, date_voluntary_recognition
        FROM nlrb_voluntary_recognition
        WHERE (employer_name ILIKE %s OR employer_name ILIKE %s)
          AND unit_state = %s
        LIMIT 5
    """, (f"%{name}%", f"%{name.split()[0]}%", state))
    return cur.fetchall()


def check_unified_employer(name, state):
    """Check unified employers view"""
    cur.execute("""
        SELECT unified_id, employer_name, state, workers_covered, union_acronym, sector_code
        FROM all_employers_unified
        WHERE employer_name ILIKE %s AND state = %s
        LIMIT 5
    """, (f"%{name}%", state))
    return cur.fetchall()


def verify_event(event):
    """Verify a single event against all database sources"""
    name = event['employer_name']
    name_parts = name.replace('(', ' ').replace(')', ' ').split()
    search_term = name_parts[0] if name_parts else name
    state = event['state']

    result = {
        'id': event['id'],
        'employer_name': name,
        'state': state,
        'status': 'NOT_FOUND',
        'matches': [],
        'notes': ''
    }

    # Check F7 employers
    f7_matches = check_f7_employer(search_term, state)
    if f7_matches:
        result['matches'].extend([('F7', m) for m in f7_matches])

    # Check VR records
    vr_matches = check_vr_employer(search_term, state)
    if vr_matches:
        result['matches'].extend([('VR', m) for m in vr_matches])

    # Check unified
    unified_matches = check_unified_employer(search_term, state)
    if unified_matches:
        result['matches'].extend([('UNIFIED', m) for m in unified_matches])

    # Determine status
    if result['matches']:
        # Check for exact or close matches
        for source, match in result['matches']:
            match_name = match.get('employer_name', '')
            if match_name and (
                name.lower() in match_name.lower() or
                match_name.lower() in name.lower() or
                search_term.lower() in match_name.lower()
            ):
                result['status'] = 'PARTIAL_MATCH'
                result['notes'] = f"Possible match in {source}: {match_name}"
                break

    return result


# ============================================================================
# MAIN EXECUTION
# ============================================================================

print("=" * 70)
print("UNION DISCOVERY 2024 - VERIFICATION REPORT")
print("=" * 70)
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Total Events to Verify: {len(DISCOVERED_EVENTS)}")
print()

# Verify all events
results = []
not_found = []
partial_match = []
exact_match = []

for event in DISCOVERED_EVENTS:
    result = verify_event(event)
    results.append(result)

    if result['status'] == 'NOT_FOUND':
        not_found.append(event)
    elif result['status'] == 'PARTIAL_MATCH':
        partial_match.append((event, result))
    else:
        exact_match.append((event, result))

print("-" * 70)
print("VERIFICATION RESULTS")
print("-" * 70)

print(f"\n[NOT_FOUND] - {len(not_found)} records ready for insert:")
for event in not_found:
    print(f"  {event['id']:2}. {event['employer_name'][:45]:<45} ({event['state']}) - {event['num_employees']} workers")

print(f"\n[PARTIAL_MATCH] - {len(partial_match)} records need review:")
for event, result in partial_match:
    print(f"  {event['id']:2}. {event['employer_name'][:45]:<45} ({event['state']})")
    print(f"      -> {result['notes'][:60]}")

print(f"\n[EXACT_MATCH] - {len(exact_match)} records already in database")

# ============================================================================
# CREATE STAGING TABLE AND INSERT NEW RECORDS
# ============================================================================

print("\n" + "=" * 70)
print("INSERTING NEW RECORDS")
print("=" * 70)

# Create staging table
cur.execute("""
    CREATE TABLE IF NOT EXISTS discovered_employers (
        id SERIAL PRIMARY KEY,
        employer_name VARCHAR(255),
        employer_name_normalized VARCHAR(255),
        city VARCHAR(100),
        state VARCHAR(2),
        union_name VARCHAR(255),
        affiliation VARCHAR(50),
        local_number VARCHAR(20),
        num_employees INTEGER,
        recognition_type VARCHAR(50),
        recognition_date DATE,
        naics_sector VARCHAR(2),
        source_url TEXT,
        source_type VARCHAR(50) DEFAULT 'DISCOVERY_2024',
        notes TEXT,
        verification_status VARCHAR(20) DEFAULT 'VERIFIED',
        created_at TIMESTAMP DEFAULT NOW()
    )
""")
conn.commit()

# Insert records that are NOT_FOUND (new) or PARTIAL_MATCH (for review)
inserted = 0
for event in not_found + [e for e, r in partial_match]:
    # Check if already inserted
    cur.execute("""
        SELECT id FROM discovered_employers
        WHERE employer_name_normalized = %s AND state = %s
    """, (event['employer_name_normalized'], event['state']))

    if not cur.fetchone():
        cur.execute("""
            INSERT INTO discovered_employers (
                employer_name, employer_name_normalized, city, state,
                union_name, affiliation, local_number, num_employees,
                recognition_type, recognition_date, naics_sector,
                source_url, notes, verification_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            event['employer_name'],
            event['employer_name_normalized'],
            event['city'],
            event['state'],
            event['union_name'],
            event['affiliation'],
            event['local_number'],
            event['num_employees'],
            event['recognition_type'],
            event['recognition_date'],
            event['naics_sector'],
            event['source_url'],
            event['notes'],
            'VERIFIED' if event in not_found else 'NEEDS_REVIEW'
        ))
        inserted += 1

conn.commit()
print(f"Inserted {inserted} new records into discovered_employers table")

# ============================================================================
# SUMMARY STATISTICS
# ============================================================================

print("\n" + "=" * 70)
print("2024 UNION DISCOVERY SUMMARY")
print("=" * 70)

# By recognition type
print("\n## Records by Recognition Type:")
type_counts = {}
for event in DISCOVERED_EVENTS:
    t = event['recognition_type']
    type_counts[t] = type_counts.get(t, 0) + 1
for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  - {t}: {count}")

# By industry
print("\n## Records by Industry (NAICS):")
naics_map = {
    '51': 'Information/Media',
    '71': 'Arts/Entertainment',
    '72': 'Hospitality',
    '44': 'Retail',
    '45': 'Retail',
    '61': 'Education',
    '62': 'Healthcare/Social',
    '33': 'Manufacturing',
    '56': 'Administrative Services'
}
naics_counts = {}
for event in DISCOVERED_EVENTS:
    n = event['naics_sector']
    label = naics_map.get(n, f'Other ({n})')
    naics_counts[label] = naics_counts.get(label, 0) + 1
for n, count in sorted(naics_counts.items(), key=lambda x: -x[1]):
    print(f"  - {n}: {count}")

# By affiliation
print("\n## Records by Union Affiliation:")
aff_counts = {}
for event in DISCOVERED_EVENTS:
    a = event['affiliation']
    aff_counts[a] = aff_counts.get(a, 0) + 1
for a, count in sorted(aff_counts.items(), key=lambda x: -x[1]):
    print(f"  - {a}: {count}")

# Total workers
total_workers = sum(e['num_employees'] for e in DISCOVERED_EVENTS)
largest = max(DISCOVERED_EVENTS, key=lambda x: x['num_employees'])
print(f"\n## Total Workers Organized: {total_workers:,}")
print(f"   Largest: {largest['employer_name']} ({largest['num_employees']:,} workers)")

# Final counts from database
cur.execute("SELECT COUNT(*) as cnt FROM discovered_employers WHERE source_type = 'DISCOVERY_2024'")
db_count = cur.fetchone()['cnt']
cur.execute("SELECT SUM(num_employees) as total FROM discovered_employers WHERE source_type = 'DISCOVERY_2024'")
db_workers = cur.fetchone()['total'] or 0

print(f"\n## Database Status:")
print(f"   Records in discovered_employers: {db_count}")
print(f"   Total workers in new records: {db_workers:,}")

conn.close()
print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
