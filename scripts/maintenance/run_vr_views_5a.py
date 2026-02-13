import os
"""
Run VR Views 5A SQL
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("VR Integration Views - Checkpoint 5A")
print("=" * 60)

# Read and execute SQL file
with open('vr_views_5a.sql', 'r') as f:
    sql = f.read()

# Split by semicolons and execute each statement
statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]

for i, stmt in enumerate(statements):
    if stmt and not stmt.startswith('--'):
        try:
            cur.execute(stmt)
            if 'CREATE' in stmt.upper():
                print(f"  Executed statement {i+1}")
        except Exception as e:
            if 'already exists' not in str(e):
                print(f"  Statement {i+1} error: {str(e)[:60]}")

# Verify views
print("\nVerifying views created:")
cur.execute("""
    SELECT table_name
    FROM information_schema.views 
    WHERE table_schema = 'public' 
      AND table_name LIKE 'v_vr_%'
    ORDER BY table_name
""")
views = [r[0] for r in cur.fetchall()]
for v in views:
    cur.execute(f"SELECT COUNT(*) FROM {v}")
    cnt = cur.fetchone()[0]
    print(f"  {v}: {cnt} rows")

cur.close()
conn.close()
print("\nCheckpoint 5A Complete!")
