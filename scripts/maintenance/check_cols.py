import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='lm_data' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r[0])
conn.close()
