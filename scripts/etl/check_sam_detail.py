"""Detailed SAM matching diagnostics."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# Current matches
cur.execute("SELECT COUNT(*) FROM sam_f7_matches")
total = cur.fetchone()[0]
print(f"Total matches: {total:,}")

cur.execute("""
    SELECT match_method, COUNT(*), ROUND(AVG(match_confidence), 2)
    FROM sam_f7_matches GROUP BY match_method ORDER BY COUNT(*) DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,} (avg conf: {r[2]})")

# Which states have matches?
cur.execute("""
    SELECT s.physical_state, COUNT(*) as cnt
    FROM sam_f7_matches m
    JOIN sam_entities s ON s.uei = m.uei
    GROUP BY s.physical_state
    ORDER BY s.physical_state
""")
matched_states = cur.fetchall()
print(f"\nStates with matches: {len(matched_states)}")
for r in matched_states:
    print(f"  {r[0]}: {r[1]:,}")

# Active query details
cur.execute("""
    SELECT pid, state, query_start, now() - query_start as duration,
           LEFT(query, 300) as q
    FROM pg_stat_activity
    WHERE datname = 'olms_multiyear'
      AND state = 'active'
      AND query NOT LIKE '%%pg_stat_activity%%'
    ORDER BY query_start
""")
active = cur.fetchall()
print(f"\nActive queries: {len(active)}")
for r in active:
    print(f"  PID {r[0]}: running for {r[3]}")
    print(f"  Query: {r[4][:200]}...")

# Size of states to understand the bottleneck
print("\nSAM entities per state (top 10):")
cur.execute("""
    SELECT physical_state, COUNT(*) as cnt
    FROM sam_entities WHERE physical_state IS NOT NULL
    GROUP BY physical_state ORDER BY cnt DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,}")

print("\nF7 employers per state (top 10):")
cur.execute("""
    SELECT state, COUNT(*) as cnt
    FROM f7_employers_deduped WHERE state IS NOT NULL
    GROUP BY state ORDER BY cnt DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,}")

conn.close()
