import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'f7_employers_deduped'
      AND indexdef LIKE '%employer_name_aggressive%'
""")
rows = cur.fetchall()
if not rows:
    print("No index on employer_name_aggressive!")
else:
    for r in rows:
        print(f"{r[0]}: {r[1]}")

# Also check if the MV has indexes
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'mv_whd_employer_agg'
""")
rows = cur.fetchall()
print("\nMV indexes:")
for r in rows:
    print(f"  {r[0]}: {r[1]}")
conn.close()
