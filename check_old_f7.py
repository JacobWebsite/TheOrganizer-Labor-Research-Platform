import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard WHERE has_f7_match = true")
count = cur.fetchone()[0]
print(f"Old scorecard with f7 match: {count}")

cur.close()
conn.close()
