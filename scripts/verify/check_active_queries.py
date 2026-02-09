import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
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
