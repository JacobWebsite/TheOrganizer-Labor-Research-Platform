import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

# Check column names in key NLRB tables
for table in ['nlrb_elections', 'nlrb_tallies', 'nlrb_participants']:
    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
    print(f'{table}:')
    for row in cur.fetchall():
        print(f'  - {row[0]}')
    print()

conn.close()
