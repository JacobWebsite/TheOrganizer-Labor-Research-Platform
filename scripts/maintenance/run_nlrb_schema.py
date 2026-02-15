import os
"""Run NLRB schema creation"""
import psycopg2

PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

schema_file = r'C:\Users\jakew\Downloads\labor-data-project\src\sql\nlrb_schema.sql'

with open(schema_file, 'r') as f:
    schema_sql = f.read()

conn = psycopg2.connect(**PG_CONFIG)
conn.autocommit = True
cur = conn.cursor()

print("Creating NLRB schema...")
cur.execute(schema_sql)
print("Schema created successfully!")

# Verify tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name LIKE 'nlrb%'
    ORDER BY table_name
""")
print("\nNLRB tables created:")
for row in cur.fetchall():
    print(f"  - {row[0]}")

conn.close()
