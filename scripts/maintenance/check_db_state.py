import os
"""
Check current database state and existing tables/views
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
cur = conn.cursor()

print("=" * 80)
print("DATABASE STATE CHECK")
print("=" * 80)

# List all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_type = 'BASE TABLE'
    ORDER BY table_name;
""")
print("\nTables:")
for row in cur.fetchall():
    print(f"  {row[0]}")

# List all views
cur.execute("""
    SELECT table_name 
    FROM information_schema.views
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
print("\nViews:")
for row in cur.fetchall():
    print(f"  {row[0]}")

# Check for private sector tables
print("\n--- Private Sector Data Check ---")
private_tables = [
    'employers_deduped',
    'f7_data', 
    'f7_employers',
    'f7_private_sector',
    'v_f7_private_sector_cleaned'
]

for table in private_tables:
    cur.execute(f"""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = '{table}'
        );
    """)
    exists = cur.fetchone()[0]
    if exists:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            count = cur.fetchone()[0]
            print(f"  {table}: EXISTS ({count:,} rows)")
        except:
            print(f"  {table}: EXISTS (view)")
    else:
        print(f"  {table}: NOT FOUND")

# Check federal sector tables
print("\n--- Federal Sector Data Check ---")
cur.execute("SELECT COUNT(*) FROM federal_bargaining_units;")
print(f"  federal_bargaining_units: {cur.fetchone()[0]:,} rows")
cur.execute("SELECT COUNT(*) FROM federal_agencies;")
print(f"  federal_agencies: {cur.fetchone()[0]:,} rows")

# Check unified views
print("\n--- Unified Views Check ---")
for view in ['public_sector_employers', 'all_employers_unified', 'sector_summary']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {view};")
        count = cur.fetchone()[0]
        print(f"  {view}: {count:,} rows")
    except Exception as e:
        print(f"  {view}: ERROR - {str(e)[:50]}")

conn.close()
