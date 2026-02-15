import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check v_deduplicated_membership columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'v_deduplicated_membership'
    ORDER BY ordinal_position
""")
print('v_deduplicated_membership columns:')
for r in cur.fetchall():
    print(f'  {r[0]}')

# Check federal_bargaining_units
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'federal_bargaining_units'
    ORDER BY ordinal_position
""")
print('\nfederal_bargaining_units columns:')
for r in cur.fetchall():
    print(f'  {r[0]}')

conn.close()
