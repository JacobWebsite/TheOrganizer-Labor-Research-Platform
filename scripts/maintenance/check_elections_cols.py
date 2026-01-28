"""Check nlrb_elections columns"""
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

print("--- nlrb_elections columns ---")
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'nlrb_elections' ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

conn.close()
