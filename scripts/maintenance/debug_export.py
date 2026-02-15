import os
from db_config import get_connection
"""
Debug the query issues
"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

# Check v_union_members_counted data
print("### v_union_members_counted sample ###")
cur.execute("SELECT hierarchy_level, COUNT(*) FROM v_union_members_counted GROUP BY hierarchy_level")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

print("\n### Check hierarchy_level values ###")
cur.execute("""
    SELECT DISTINCT hierarchy_level 
    FROM v_union_members_counted 
    WHERE hierarchy_level IS NOT NULL
""")
for r in cur.fetchall():
    print(f"  '{r[0]}'")

# Check federal_bargaining_units columns
print("\n### federal_bargaining_units columns ###")
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'federal_bargaining_units'
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Try simpler query on v_union_members_counted
print("\n### Simple v_union_members_counted query ###")
cur.execute("""
    SELECT COUNT(*), SUM(members) 
    FROM v_union_members_counted 
    WHERE count_members = TRUE
""")
r = cur.fetchone()
print(f"  Counted unions: {r[0]}, Members: {r[1]}")

# Check if there's data at all
print("\n### Top 5 from v_union_members_counted ###")
cur.execute("""
    SELECT f_num, union_name, hierarchy_level, members, count_members
    FROM v_union_members_counted
    ORDER BY members DESC NULLS LAST
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r}")

conn.close()
