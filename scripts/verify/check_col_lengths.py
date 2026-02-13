import os
"""Check column length constraints"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

cur.execute("""
    SELECT column_name, character_maximum_length
    FROM information_schema.columns
    WHERE table_name = 'mergent_employers'
    AND character_maximum_length IS NOT NULL
    ORDER BY column_name
""")

print("=== Columns with length limits ===")
for r in cur.fetchall():
    print(f"{r[0]}: {r[1]}")

cur.close()
conn.close()
