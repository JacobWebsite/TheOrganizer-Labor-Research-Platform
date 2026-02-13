"""Kill stuck SAM matching query."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT pid FROM pg_stat_activity
    WHERE datname = 'olms_multiyear' AND state = 'active'
      AND query LIKE '%%sam_f7_matches%%'
""")
rows = cur.fetchall()
for r in rows:
    print(f"Cancelling PID {r[0]}...")
    cur.execute("SELECT pg_cancel_backend(%s)", (r[0],))
    print(f"  Result: {cur.fetchone()[0]}")
conn.commit()
conn.close()
print("Done.")
