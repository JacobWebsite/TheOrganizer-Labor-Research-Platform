import os
"""
VR Schema Execution Script
Runs the vr_schema.sql file against the PostgreSQL database
"""
import psycopg2

# Database connection
conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = True
cur = conn.cursor()

print("Executing VR Schema...")

# Read and execute the schema SQL
with open('C:/Users/jakew/Downloads/labor-data-project/vr_schema.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

try:
    cur.execute(sql)
    print("Schema executed successfully!")
except Exception as e:
    print(f"Error: {e}")

# Verify tables created
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND (table_name LIKE 'nlrb_voluntary%' 
           OR table_name LIKE 'vr_%'
           OR table_name = 'nlrb_regions')
    ORDER BY table_name
""")
tables = cur.fetchall()
print(f"\nVR Tables created: {len(tables)}")
for t in tables:
    print(f"   - {t[0]}")

# Verify views created
cur.execute("""
    SELECT table_name 
    FROM information_schema.views 
    WHERE table_schema = 'public' AND table_name LIKE 'v_vr_%'
    ORDER BY table_name
""")
views = cur.fetchall()
print(f"\nVR Views created: {len(views)}")
for v in views:
    print(f"   - {v[0]}")

# Check lookup table data
cur.execute("SELECT COUNT(*) FROM nlrb_regions")
region_count = cur.fetchone()[0]
print(f"\nNLRB Regions loaded: {region_count}")

cur.execute("SELECT COUNT(*) FROM vr_affiliation_patterns")
pattern_count = cur.fetchone()[0]
print(f"Affiliation patterns loaded: {pattern_count}")

cur.close()
conn.close()
print("\n=== CHECKPOINT 1 COMPLETE ===")
