import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check for projection-related tables
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='public'
    AND (table_name LIKE '%projection%' OR table_name LIKE '%occupation%' OR table_name LIKE '%bls%')
    ORDER BY table_name
""")
tables = cur.fetchall()
print("Tables matching projection/occupation/bls:")
for t in tables:
    print(f"  {t[0]}")

# Check for views
cur.execute("""
    SELECT table_name FROM information_schema.views
    WHERE table_schema='public'
    AND (table_name LIKE '%projection%' OR table_name LIKE '%naics%')
    ORDER BY table_name
""")
views = cur.fetchall()
print("\nViews matching projection/naics:")
for v in views:
    print(f"  {v[0]}")

# Check if industry_projections table exists
cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'industry_projections'
    )
""")
exists = cur.fetchone()[0]
print(f"\nindustry_projections table exists: {exists}")

if exists:
    cur.execute("SELECT COUNT(*) FROM industry_projections")
    print(f"industry_projections count: {cur.fetchone()[0]}")
    cur.execute("SELECT * FROM industry_projections LIMIT 3")
    print("Sample rows:", cur.fetchall())

# Check for occupation_projections
cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'occupation_projections'
    )
""")
occ_exists = cur.fetchone()[0]
print(f"\noccupation_projections table exists: {occ_exists}")

if occ_exists:
    cur.execute("SELECT COUNT(*) FROM occupation_projections")
    print(f"occupation_projections count: {cur.fetchone()[0]}")

conn.close()
