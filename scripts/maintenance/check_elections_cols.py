"""Check nlrb_elections columns"""
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = get_connection(cursor_factory=RealDictCursor)
cur = conn.cursor()

print("--- nlrb_elections columns ---")
cur.execute("""
from db_config import get_connection
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'nlrb_elections' ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

conn.close()
