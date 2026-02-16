"""Verify F-7 schema creation"""
import psycopg2
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Check tables
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('f7_employers', 'unions_master', 'union_sector', 'union_match_status')
    ORDER BY table_name
""")
tables = cursor.fetchall()
print("Tables created:")
for t in tables:
    print(f"  - {t[0]}")

# Check lookup data
cursor.execute("SELECT COUNT(*) FROM union_sector")
print(f"\nunion_sector: {cursor.fetchone()[0]} records")

cursor.execute("SELECT * FROM union_sector")
print("\nSector codes:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} (F7 expected: {row[3]})")

cursor.execute("SELECT COUNT(*) FROM union_match_status")
print(f"\nunion_match_status: {cursor.fetchone()[0]} records")

# Check views
cursor.execute("""
    SELECT table_name 
    FROM information_schema.views 
    WHERE table_schema = 'public' 
    AND (table_name LIKE 'v_f7%' OR table_name LIKE 'v_union%' OR table_name LIKE 'v_sector%' OR table_name LIKE 'v_match%' OR table_name LIKE 'v_lm_with%')
    ORDER BY table_name
""")
views = cursor.fetchall()
print(f"\nViews created:")
for v in views:
    print(f"  - {v[0]}")

# Check f7_employers table structure
cursor.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers'
    ORDER BY ordinal_position
""")
print(f"\nf7_employers columns:")
for col in cursor.fetchall():
    print(f"  {col[0]}: {col[1]}")

cursor.close()
conn.close()

print("\nSchema verification complete!")
