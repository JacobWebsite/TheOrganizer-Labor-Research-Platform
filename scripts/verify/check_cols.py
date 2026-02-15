import os
import psycopg2

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

for table in ['ny_990_filers', 'employers_990', 'nyc_wage_theft_nys']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{table}: {cols}")

conn.close()
