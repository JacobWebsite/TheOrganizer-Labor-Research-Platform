"""Check SAM matching progress."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM sam_f7_matches")
total = cur.fetchone()[0]
print(f"Current SAM->F7 matches: {total:,}")

cur.execute("SELECT match_method, COUNT(*), ROUND(AVG(match_confidence), 2) FROM sam_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r[0]}: {r[1]:,} (avg conf: {r[2]})")

# Check if matching is still running by looking at pg_stat_activity
cur.execute("""
    SELECT pid, state, query_start, LEFT(query, 120) as q
    FROM pg_stat_activity
    WHERE datname = 'olms_multiyear'
      AND state = 'active'
      AND query NOT LIKE '%pg_stat_activity%'
    ORDER BY query_start
""")
active = cur.fetchall()
if active:
    print(f"\nActive queries ({len(active)}):")
    for r in active:
        print(f"  PID {r[0]} ({r[1]}, started {r[2]}): {r[3]}")
else:
    print("\nNo active matching queries running.")

conn.close()
