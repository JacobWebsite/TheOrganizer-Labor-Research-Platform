import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

# Check lm_data columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'lm_data'
    ORDER BY ordinal_position
    LIMIT 20
""")
print('lm_data columns:')
for r in cur.fetchall():
    print(f'  {r[0]}')

# Check what data exists
cur.execute("SELECT COUNT(*) FROM lm_data")
print(f'\nlm_data rows: {cur.fetchone()[0]}')

conn.close()
