import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Check f7_employers_deduped columns
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers_deduped'
    ORDER BY ordinal_position
""")
print('f7_employers_deduped columns:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

# Check unions_master columns
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'unions_master'
    ORDER BY ordinal_position
""")
print('\nunions_master columns:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

conn.close()
