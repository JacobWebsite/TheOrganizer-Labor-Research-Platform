"""Check f7 table structure"""
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = conn.cursor()

print("--- f7_employers_deduped columns ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

print("\n--- f7_employers columns ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'f7_employers'
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

print("\n--- Sample from f7_employers ---")
cur.execute("SELECT * FROM f7_employers LIMIT 1")
row = cur.fetchone()
for k, v in row.items():
    print(f"  {k}: {v}")

conn.close()
