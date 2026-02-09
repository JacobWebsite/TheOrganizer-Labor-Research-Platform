import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

for tbl in ['nlrb_participants', 'mv_employer_search']:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (tbl,))
    cols = [r[0] for r in cur.fetchall()]
    print(f"{tbl}: {', '.join(cols)}")

# Check if mv_employer_search is a materialized view
cur.execute("""
    SELECT matviewname FROM pg_matviews WHERE matviewname = 'mv_employer_search'
""")
print(f"\nmv_employer_search is matview: {cur.fetchone() is not None}")

# Try to get its definition
cur.execute("""
    SELECT definition FROM pg_matviews WHERE matviewname = 'mv_employer_search'
""")
row = cur.fetchone()
if row:
    print(f"\nDefinition (first 2000 chars):\n{row[0][:2000]}")

# Sample nlrb_participants
cur.execute("SELECT * FROM nlrb_participants LIMIT 2")
cols = [d[0] for d in cur.description]
print(f"\nnlrb_participants columns from cursor: {cols}")
for row in cur.fetchall():
    print(row[:8])

cur.close()
conn.close()
