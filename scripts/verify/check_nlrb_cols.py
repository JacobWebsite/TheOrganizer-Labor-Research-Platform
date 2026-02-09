import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

for tbl in ['nlrb_elections', 'nlrb_voluntary_recognition', 'manual_employers', 'mv_employer_search']:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (tbl,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{tbl}: {', '.join(cols)}")

cur.close()
conn.close()
