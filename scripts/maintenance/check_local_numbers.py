"""Check for local number data"""
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

print("--- unions_master columns ---")
cur.execute("""
from db_config import get_connection
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'unions_master' ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

print("\n--- Sample SEIU locals ---")
cur.execute("""
    SELECT f_num, union_name, city, state, members
    FROM unions_master
    WHERE aff_abbr = 'SEIU'
    ORDER BY members DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row['f_num']}: {row['union_name'][:50]} | {row['city']}, {row['state']} | {row['members']}")

print("\n--- Check lm_data for local numbers ---")
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'lm_data' ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row['column_name']}")

print("\n--- Sample lm_data with desig_num ---")
cur.execute("""
    SELECT f_num, union_name, desig_name, desig_num, unit_name
    FROM lm_data
    WHERE aff_abbr = 'SEIU' AND desig_num IS NOT NULL AND desig_num != ''
    ORDER BY members DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row['f_num']}: {row['desig_num']} - {row['desig_name']} | {row['unit_name']}")

conn.close()
