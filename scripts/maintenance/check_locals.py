import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT f_num, union_name, local_number, desig_name, city, state FROM unions_master WHERE aff_abbr = 'SEIU' AND local_number IS NOT NULL LIMIT 15")
for r in cur.fetchall():
    print(r)
conn.close()
