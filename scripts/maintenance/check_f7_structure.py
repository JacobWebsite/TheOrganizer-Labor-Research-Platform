import os
"""
CHECKPOINT 4 FIX: Update unified view with correct column names
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKPOINT 4 FIX: Updating Unified View with Private Sector")
print("=" * 80)

# Check f7_employers_deduped structure
print("\n--- f7_employers_deduped columns ---")
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'f7_employers_deduped'
    ORDER BY ordinal_position;
""")
cols = [r[0] for r in cur.fetchall()]
print(f"Columns: {cols}")

# Get stats - using correct column name
cur.execute("SELECT COUNT(*), SUM(latest_unit_size) FROM f7_employers_deduped;")
row = cur.fetchone()
print(f"\nPrivate sector: {row[0]:,} employers, {row[1] or 0:,} workers (latest_unit_size)")

# Check for aff_abbr or equivalent
cur.execute("SELECT * FROM f7_employers_deduped LIMIT 1;")
sample = cur.fetchone()
col_names = [desc[0] for desc in cur.description]
print(f"\nSample record columns: {col_names}")

# Need to find union affiliation - check f7_union_employer_relations
print("\n--- Checking f7_union_employer_relations ---")
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'f7_union_employer_relations'
    ORDER BY ordinal_position;
""")
rel_cols = [r[0] for r in cur.fetchall()]
print(f"Columns: {rel_cols}")

cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations;")
print(f"Records: {cur.fetchone()[0]:,}")

# Check if there's already a view we should use
print("\n--- Checking existing employer views ---")
cur.execute("""
    SELECT table_name FROM information_schema.views 
    WHERE table_schema = 'public' 
    AND table_name ILIKE '%employer%'
    ORDER BY table_name;
""")
views = [r[0] for r in cur.fetchall()]
print(f"Employer views: {views}")

# Check v_employer_search structure
if 'v_employer_search' in views:
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'v_employer_search'
        ORDER BY ordinal_position;
    """)
    print(f"\nv_employer_search columns: {[r[0] for r in cur.fetchall()]}")
    
    cur.execute("SELECT COUNT(*) FROM v_employer_search;")
    print(f"v_employer_search records: {cur.fetchone()[0]:,}")

conn.close()
