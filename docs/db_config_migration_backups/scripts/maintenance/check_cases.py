import os
import psycopg2
conn = psycopg2.connect(host='localhost', database='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

# Check nlrb_cases columns
print("NLRB_CASES columns:")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'nlrb_cases' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Check nlrb_participants columns
print("\nNLRB_PARTICIPANTS columns:")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'nlrb_participants' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Sample from nlrb_cases
print("\nSample from nlrb_cases:")
cur.execute("SELECT * FROM nlrb_cases LIMIT 1")
cols = [desc[0] for desc in cur.description]
row = cur.fetchone()
for c, v in zip(cols, row):
    print(f"  {c}: {v}")

cur.close()
conn.close()
