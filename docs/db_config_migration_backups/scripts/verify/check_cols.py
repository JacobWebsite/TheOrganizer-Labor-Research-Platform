import os
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

for table in ['ny_990_filers', 'employers_990', 'nyc_wage_theft_nys']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (table,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{table}: {cols}")

conn.close()
