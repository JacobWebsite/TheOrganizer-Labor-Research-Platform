import os
import psycopg2
conn = psycopg2.connect(host='localhost', database='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

print("NLRB_ELECTIONS columns:")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'nlrb_elections' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(f"  {r[0]}")

print("\nF7_EMPLOYERS_DEDUPED columns:")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'f7_employers_deduped' ORDER BY ordinal_position LIMIT 25")
for r in cur.fetchall():
    print(f"  {r[0]}")

cur.close()
conn.close()
