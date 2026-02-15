import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check all tables with 'election' or 'nlrb' in name
print("Tables with election/nlrb:")
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND (table_name LIKE '%election%' OR table_name LIKE '%nlrb%')
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Check if there's a view for elections
print("\nViews with election:")
cur.execute("""
    SELECT table_name FROM information_schema.views 
    WHERE table_schema = 'public' 
    AND table_name LIKE '%election%'
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Sample from nlrb_elections
print("\nSample from nlrb_elections:")
cur.execute("SELECT * FROM nlrb_elections LIMIT 1")
cols = [desc[0] for desc in cur.description]
row = cur.fetchone()
for c, v in zip(cols, row):
    print(f"  {c}: {v}")

cur.close()
conn.close()
