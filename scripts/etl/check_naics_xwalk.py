import os
"""
Check NAICS crosswalk tables in database
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("="*70)
print("NAICS-RELATED TABLES IN DATABASE")
print("="*70)

# Find all NAICS-related tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    AND (table_name LIKE '%naics%' OR table_name LIKE '%sic%' OR table_name LIKE '%industry%' OR table_name LIKE '%xwalk%' OR table_name LIKE '%crosswalk%')
    ORDER BY table_name
""")
tables = [r['table_name'] for r in cur.fetchall()]

print(f"\nFound {len(tables)} relevant tables:")
for t in tables:
    cur.execute(f'SELECT COUNT(*) as cnt FROM "{t}"')
    cnt = cur.fetchone()['cnt']
    print(f"\n  {t}: {cnt:,} rows")
    
    # Get columns
    cur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (t,))
    cols = [r['column_name'] for r in cur.fetchall()]
    print(f"    Columns: {cols}")
    
    # Sample data
    if cnt > 0:
        cur.execute(f'SELECT * FROM "{t}" LIMIT 3')
        samples = cur.fetchall()
        print(f"    Sample:")
        for s in samples:
            print(f"      {dict(s)}")

# Check specifically for NAICS version crosswalks
print("\n" + "="*70)
print("SEARCHING FOR NAICS VERSION CROSSWALKS (2012/2017/2022)")
print("="*70)

cur.execute("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND (column_name LIKE '%2012%' OR column_name LIKE '%2017%' OR column_name LIKE '%2022%'
         OR column_name LIKE '%naics%')
    ORDER BY table_name, column_name
""")
results = cur.fetchall()
print(f"\nColumns containing year references or 'naics':")
for r in results:
    print(f"  {r['table_name']}.{r['column_name']}")

conn.close()
