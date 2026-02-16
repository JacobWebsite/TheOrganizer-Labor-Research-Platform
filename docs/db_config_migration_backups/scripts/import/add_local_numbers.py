"""Add local_number to unions_master from lm_data"""
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

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = conn.cursor()

# Add columns if they don't exist
print("Adding local_number and desig_name columns...")
try:
    cur.execute("ALTER TABLE unions_master ADD COLUMN IF NOT EXISTS local_number VARCHAR(50)")
    cur.execute("ALTER TABLE unions_master ADD COLUMN IF NOT EXISTS desig_name VARCHAR(20)")
    conn.commit()
    print("  Columns added")
except Exception as e:
    print(f"  Error: {e}")
    conn.rollback()

# Update from most recent lm_data
print("Updating local numbers from lm_data...")
cur.execute("""
    WITH latest_lm AS (
        SELECT DISTINCT ON (f_num) 
            f_num, desig_num, desig_name
        FROM lm_data
        WHERE desig_num IS NOT NULL AND desig_num != ''
        ORDER BY f_num, yr_covered DESC
    )
    UPDATE unions_master um
    SET 
        local_number = l.desig_num,
        desig_name = l.desig_name
    FROM latest_lm l
    WHERE um.f_num = l.f_num
""")
updated = cur.rowcount
conn.commit()
print(f"  Updated {updated} rows")

# Verify
print("\n--- Sample results ---")
cur.execute("""
    SELECT f_num, local_number, desig_name, union_name, city, state
    FROM unions_master
    WHERE aff_abbr = 'SEIU' AND local_number IS NOT NULL
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row['f_num']}: Local {row['local_number']} ({row['desig_name']}) - {row['city']}, {row['state']}")

conn.close()
print("\nDone!")
