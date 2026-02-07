import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="Juniordog33!",
)
cur = conn.cursor()
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'osha_establishments'
    ORDER BY indexname
""")
for row in cur.fetchall():
    print(row[0])
    print("  ", row[1][:200])
    print()
cur.close()
conn.close()
