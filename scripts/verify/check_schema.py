import os
from db_config import get_connection
"""Check mergent_employers schema"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

# Check schema
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'mergent_employers'
    ORDER BY ordinal_position
""")
print("=== mergent_employers columns ===")
for r in cur.fetchall():
    print(f'{r[0]}: {r[1]}')

# Check existing count
cur.execute("SELECT COUNT(*), COUNT(DISTINCT sector_category) FROM mergent_employers")
count, sectors = cur.fetchone()
print(f"\nExisting records: {count}")
print(f"Existing sectors: {sectors}")

# Check sector breakdown
cur.execute("""
    SELECT sector_category, COUNT(*)
    FROM mergent_employers
    GROUP BY sector_category
    ORDER BY COUNT(*) DESC
""")
print("\n=== By sector ===")
for r in cur.fetchall():
    print(f'{r[0]}: {r[1]}')

cur.close()
conn.close()
