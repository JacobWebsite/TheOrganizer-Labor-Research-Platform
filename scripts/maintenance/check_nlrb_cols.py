import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check column names in key NLRB tables
for table in ['nlrb_elections', 'nlrb_tallies', 'nlrb_participants']:
    cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
    print(f'{table}:')
    for row in cur.fetchall():
        print(f'  - {row[0]}')
    print()

conn.close()
