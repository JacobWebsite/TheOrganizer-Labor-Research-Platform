import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT relname, n_live_tup 
    FROM pg_stat_user_tables 
    ORDER BY n_live_tup DESC
""")
rows = cur.fetchall()
print("| Table | Rows |")
print("|-------|------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.close()
conn.close()
