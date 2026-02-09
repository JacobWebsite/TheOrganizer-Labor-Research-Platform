import os
"""
Check BLS/EPI data in database
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor(cursor_factory=RealDictCursor)

# List all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
tables = [r['table_name'] for r in cur.fetchall()]

print('ALL TABLES IN DATABASE:')
print('-' * 60)
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) as cnt FROM "{t}"')
        cnt = cur.fetchone()['cnt']
        print(f'  {t:45}: {cnt:>10,}')
    except:
        print(f'  {t:45}: ERROR')

# Check for BLS-related tables specifically
print('\n' + '=' * 60)
print('BLS/EPI/EMPLOYMENT RELATED TABLES (detailed):')
print('=' * 60)

keywords = ['bls', 'union', 'density', 'employment', 'occupation', 'industry', 'state', 'projection', 'epi', 'member']
bls_tables = [t for t in tables if any(k in t.lower() for k in keywords)]

for t in bls_tables:
    try:
        cur.execute(f'SELECT COUNT(*) as cnt FROM "{t}"')
        cnt = cur.fetchone()['cnt']
        print(f'\n{t} ({cnt:,} rows)')
        print('-' * 50)
        
        # Show columns
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (t,))
        cols = [r['column_name'] for r in cur.fetchall()]
        print(f'  Columns: {cols}')
        
        # Show sample data
        cur.execute(f'SELECT * FROM "{t}" LIMIT 3')
        samples = cur.fetchall()
        if samples:
            print(f'  Sample:')
            for s in samples:
                print(f'    {dict(s)}')
    except Exception as e:
        print(f'  ERROR: {e}')

conn.close()
