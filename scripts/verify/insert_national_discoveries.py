"""
Insert 11 newly discovered union organizing events into manual_employers.
Source: Union Discovery Research (2015-2025 national scan)
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

# Get current max ID
cur.execute("SELECT COALESCE(MAX(id), 0) FROM manual_employers")
max_id = cur.fetchone()[0]
print("Current max manual_employers ID: %d" % max_id)

# Check existing columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'manual_employers'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print("Columns: %s" % ', '.join(cols))

# New records to insert
records = [
    {
        'employer_name': 'Gawker Media',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 100,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2015 voluntary recognition. Digital media newsroom. Company shut down 2016.',
    },
    {
        'employer_name': 'HuffPost',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 262,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2016 voluntary recognition. Standalone HuffPost before BuzzFeed acquisition.',
    },
    {
        'employer_name': 'Refinery29',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 50,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2019 voluntary recognition. Digital media/lifestyle.',
    },
    {
        'employer_name': 'The Intercept',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 32,
        'recognition_type': 'CARD_CHECK',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2017 card check recognition. Investigative journalism outlet.',
    },
    {
        'employer_name': 'Quartz',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'NewsGuild-CWA',
        'affiliation': 'CWA',
        'num_employees': 60,
        'recognition_type': 'CARD_CHECK',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2019 card check recognition. Business news digital media.',
    },
    {
        'employer_name': 'ThinkProgress',
        'city': 'Washington',
        'state': 'DC',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 20,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2015 voluntary recognition. Progressive news outlet (Center for American Progress). Shut down 2019.',
    },
    {
        'employer_name': 'Thrillist',
        'city': 'New York',
        'state': 'NY',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 60,
        'recognition_type': 'NLRB_ELECTION',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2017 NLRB election (56-3). Digital media/lifestyle.',
    },
    {
        'employer_name': 'Salon Media Group',
        'city': 'San Francisco',
        'state': 'CA',
        'union_name': 'Writers Guild of America East (WGAE)',
        'affiliation': 'WGAE',
        'num_employees': 26,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2015 voluntary recognition. Progressive online magazine.',
    },
    {
        'employer_name': 'Mapbox',
        'city': 'Washington',
        'state': 'DC',
        'union_name': 'Communications Workers of America (CWA)',
        'affiliation': 'CWA',
        'num_employees': 222,
        'recognition_type': 'NLRB_ELECTION',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2021 NLRB election (lost 123-81). Mapping/tech company. Election held but union lost.',
    },
    {
        'employer_name': "EMILY's List",
        'city': 'Washington',
        'state': 'DC',
        'union_name': 'Office and Professional Employees International Union (OPEIU)',
        'affiliation': 'OPEIU',
        'num_employees': 50,
        'recognition_type': 'VOLUNTARY',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': '2020 voluntary recognition. Political organization/nonprofit.',
    },
    {
        'employer_name': 'Amazon ALB1 Warehouse',
        'city': 'Schodack',
        'state': 'NY',
        'union_name': 'Amazon Labor Union / International Brotherhood of Teamsters',
        'affiliation': 'IBT',
        'num_employees': 1000,
        'recognition_type': 'NLRB_ELECTION',
        'source_type': 'RESEARCH_DISCOVERY',
        'sector': 'PRIVATE',
        'notes': 'Amazon fulfillment center ALB1. Organizing attempts ongoing.',
    },
]

# Insert
next_id = max_id + 1
inserted = 0
for rec in records:
    # Check if already exists
    cur.execute("""
        SELECT id FROM manual_employers
        WHERE LOWER(employer_name) = LOWER(%s) AND state = %s
    """, (rec['employer_name'], rec['state']))
    existing = cur.fetchone()
    if existing:
        print("SKIP (already exists ID=%s): %s (%s, %s)" % (
            existing[0], rec['employer_name'], rec['city'], rec['state']))
        continue

    cur.execute("""
        INSERT INTO manual_employers (
            id, employer_name, city, state, union_name, affiliation,
            num_employees, source_type, sector, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        next_id, rec['employer_name'], rec['city'], rec['state'],
        rec['union_name'], rec['affiliation'], rec['num_employees'],
        rec['source_type'], rec['sector'], rec['notes']
    ))
    print("INSERT ID=%d: %s (%s, %s) - %s, %d workers" % (
        next_id, rec['employer_name'], rec['city'], rec['state'],
        rec['affiliation'], rec['num_employees']))
    next_id += 1
    inserted += 1

conn.commit()
print("\nInserted %d new records into manual_employers" % inserted)
print("New max ID: %d" % (next_id - 1))

# Verify
cur.execute("""
    SELECT id, employer_name, city, state, union_name, num_employees
    FROM manual_employers
    WHERE source_type = 'RESEARCH_DISCOVERY'
    ORDER BY id
""")
rows = cur.fetchall()
print("\nAll RESEARCH_DISCOVERY records:")
for r in rows:
    print("  ID=%s | %s | %s, %s | %s | %s workers" % (r[0], r[1], r[2], r[3], r[4], r[5]))

cur.close()
conn.close()
