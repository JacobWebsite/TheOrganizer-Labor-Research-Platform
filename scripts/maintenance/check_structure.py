"""
Check database structure for union data export
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

# Check union_hierarchy columns
print("union_hierarchy columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'union_hierarchy'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Check lm_data columns
print("\nlm_data columns (first 15):")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'lm_data'
    ORDER BY ordinal_position
    LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Check unions_master
print("\nunions_master columns (first 15):")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'unions_master'
    ORDER BY ordinal_position
    LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Check v_union_members_counted view
print("\nv_union_members_counted columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'v_union_members_counted'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Check v_dedup_summary_by_affiliation
print("\nv_dedup_summary_by_affiliation columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'v_dedup_summary_by_affiliation'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
