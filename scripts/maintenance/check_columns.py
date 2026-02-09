import os
"""
Fix the unified view with correct column mappings
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("CHECKING TABLE STRUCTURES")
print("=" * 80)

# Check v_f7_private_sector_cleaned columns
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'v_f7_private_sector_cleaned'
    ORDER BY ordinal_position;
""")
print("\nv_f7_private_sector_cleaned:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check public_sector_employers columns
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'public_sector_employers'
    ORDER BY ordinal_position;
""")
print("\npublic_sector_employers:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check f7_employers_deduped
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers_deduped'
    ORDER BY ordinal_position;
""")
print("\nf7_employers_deduped:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check f7_employers
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers'
    ORDER BY ordinal_position
    LIMIT 15;
""")
print("\nf7_employers (first 15):")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
