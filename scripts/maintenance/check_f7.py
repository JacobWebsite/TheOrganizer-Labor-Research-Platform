import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check f7_employers columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers'
    ORDER BY ordinal_position
""")
print('f7_employers columns:')
for r in cur.fetchall():
    print(f'  {r[0]}')

conn.close()
