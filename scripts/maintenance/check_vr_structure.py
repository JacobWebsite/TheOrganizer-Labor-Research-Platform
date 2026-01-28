import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('VR TABLE STRUCTURE CHECK')
print('='*70)

# Check VR table columns
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'nlrb_voluntary_recognition'
    ORDER BY ordinal_position
""")
print('\nVR Table Columns:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

# Sample VR data
print('\n### Sample VR Data ###')
cur.execute('SELECT * FROM nlrb_voluntary_recognition LIMIT 3')
for row in cur.fetchall():
    for k, v in row.items():
        print(f"  {k}: {v}")
    print('---')

# Check NLRB tallies columns too
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'nlrb_tallies'
    ORDER BY ordinal_position
""")
print('\nNLRB Tallies Columns:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

conn.close()
