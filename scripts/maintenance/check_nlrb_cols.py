import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Check nlrb_tallies columns
cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name = 'nlrb_tallies' ORDER BY ordinal_position""")
print('nlrb_tallies columns:')
for r in cur.fetchall():
    print(f'  {r["column_name"]}')

conn.close()
