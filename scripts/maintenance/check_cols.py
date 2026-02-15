import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'nlrb_tallies' ORDER BY ordinal_position")
print('nlrb_tallies columns:')
for row in cur.fetchall():
    print(f'  - {row[0]}')
conn.close()
