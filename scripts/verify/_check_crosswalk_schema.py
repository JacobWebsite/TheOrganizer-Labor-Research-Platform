import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'corporate_identifier_crosswalk'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(r)
cur.close()
conn.close()
