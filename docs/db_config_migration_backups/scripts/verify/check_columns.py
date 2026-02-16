import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

for table in ['ny_990_filers', 'mergent_employers', 'f7_employers_deduped']:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (table,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"\n{table}: {len(cols)} columns")
    print(', '.join(cols))

cur.close()
conn.close()
