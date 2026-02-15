import os
from db_config import get_connection
"""Check column length constraints"""
import psycopg2

conn = get_connection()
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
