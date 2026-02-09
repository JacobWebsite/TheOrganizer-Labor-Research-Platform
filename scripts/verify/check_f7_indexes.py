import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
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
