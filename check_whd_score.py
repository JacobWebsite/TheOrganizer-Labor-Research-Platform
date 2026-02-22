import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT employer_name, score_whd, unified_score, whd_case_count, whd_total_backwages FROM mv_unified_scorecard WHERE has_whd = true LIMIT 5")
rows = cur.fetchall()
for row in rows:
    print(row)

cur.close()
conn.close()
