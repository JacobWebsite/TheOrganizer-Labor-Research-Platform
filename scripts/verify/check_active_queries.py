import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT pid, state, query, now()-query_start as duration
    FROM pg_stat_activity
    WHERE datname='olms_multiyear' AND state != 'idle' AND pid != pg_backend_pid()
""")
rows = cur.fetchall()
if not rows:
    print("No active queries found")
else:
    for r in rows:
        print(f"PID={r[0]} state={r[1]} duration={r[3]}")
        print(f"  query={r[2][:300]}")
conn.close()
