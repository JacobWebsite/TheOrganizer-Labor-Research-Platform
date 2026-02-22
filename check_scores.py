import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT score_tier, count(*) FROM mv_unified_scorecard GROUP BY score_tier")
rows = cur.fetchall()
print("| Tier | Count |")
print("|------|-------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.execute("SELECT factors_available, count(*) FROM mv_unified_scorecard GROUP BY factors_available ORDER BY factors_available")
rows = cur.fetchall()
print("\n| Factors Available | Count |")
print("|-------------------|-------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.close()
conn.close()
