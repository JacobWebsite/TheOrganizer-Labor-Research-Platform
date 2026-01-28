import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

# Check what tables exist
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name
""")
print('All tables:')
for r in cur.fetchall():
    print(f'  {r[0]}')

conn.close()
