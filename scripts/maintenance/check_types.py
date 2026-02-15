import os
import psycopg2

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'lm_data' AND column_name = 'f_num'
""")
print("lm_data.f_num type:", cur.fetchall())

cur.close()
conn.close()
