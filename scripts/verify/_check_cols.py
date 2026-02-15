import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
for tbl in ['ps_union_locals', 'ps_employers', 'ps_parent_unions', 'ps_bargaining_units', 'manual_employers']:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", (tbl,))
    print("%s: %s" % (tbl, [r[0] for r in cur.fetchall()]))
conn.close()
