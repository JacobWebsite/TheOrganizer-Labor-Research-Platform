import os
import psycopg2
conn = psycopg2.connect(host='localhost', database='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()
cur.execute("SELECT f_num, union_name, local_number, desig_name, city, state FROM unions_master WHERE aff_abbr = 'SEIU' AND local_number IS NOT NULL LIMIT 15")
for r in cur.fetchall():
    print(r)
conn.close()
