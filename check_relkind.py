import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT relname, relkind FROM pg_class WHERE relname = 'mv_organizing_scorecard'")
row = cur.fetchone()
print(row)

cur.close()
conn.close()
