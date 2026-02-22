import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count > 0")
count = cur.fetchone()[0]
print(f"Employers with whd_violation_count > 0: {count}")

cur.execute("SELECT SUM(whd_backwages) FROM f7_employers_deduped")
total_bw = cur.fetchone()[0]
print(f"Total whd_backwages: {total_bw}")

cur.close()
conn.close()
