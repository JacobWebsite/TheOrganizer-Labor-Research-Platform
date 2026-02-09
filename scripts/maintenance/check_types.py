import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'lm_data' AND column_name = 'f_num'
""")
print("lm_data.f_num type:", cur.fetchall())

cur.close()
conn.close()
