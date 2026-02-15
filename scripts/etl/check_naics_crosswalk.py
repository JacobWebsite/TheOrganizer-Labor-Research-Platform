import os
from db_config import get_connection
"""
Check NAICS crosswalk data in database
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("="*70)
print("NAICS-RELATED TABLES IN DATABASE")
print("="*70)

# Find all NAICS-related tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    AND (LOWER(table_name) LIKE '%naics%' 
         OR LOWER(table_name) LIKE '%sic%'
         OR LOWER(table_name) LIKE '%industry%'
         OR LOWER(table_name) LIKE '%crosswalk%'
         OR LOWER(table_name) LIKE '%census%')
    ORDER BY table_name
""")
tables = [r['table_name'] for r in cur.fetchall()]

for t in tables:
    cur.execute(f'SELECT COUNT(*) as cnt FROM "{t}"')
    cnt = cur.fetchone()['cnt']
    print(f"\n{t} ({cnt:,} rows)")
    
    # Get columns
    cur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (t,))
    cols = [r['column_name'] for r in cur.fetchall()]
    print(f"  Columns: {cols}")
    
    # Sample data
    if cnt > 0:
        cur.execute(f'SELECT * FROM "{t}" LIMIT 3')
        samples = cur.fetchall()
        print(f"  Sample:")
        for s in samples:
            print(f"    {dict(s)}")

# Check specifically for NAICS version crosswalks
print("\n" + "="*70)
print("CHECKING FOR NAICS VERSION CROSSWALKS (2012-2017-2022)")
print("="*70)

# Look for any table with multiple NAICS year columns
cur.execute("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND (column_name LIKE '%2012%' 
         OR column_name LIKE '%2017%' 
         OR column_name LIKE '%2022%'
         OR column_name LIKE '%naics%')
    ORDER BY table_name, column_name
""")
results = cur.fetchall()
if results:
    print("\nColumns with year references or NAICS:")
    current_table = None
    for r in results:
        if r['table_name'] != current_table:
            current_table = r['table_name']
            print(f"\n  {current_table}:")
        print(f"    - {r['column_name']}")
else:
    print("No NAICS version crosswalk columns found")

conn.close()
