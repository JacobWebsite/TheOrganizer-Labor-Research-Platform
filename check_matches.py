import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT match_status, count(*) FROM unified_match_log GROUP BY match_status")
rows = cur.fetchall()
print("| Status | Count |")
print("|--------|-------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.execute("SELECT source_system, count(*) FROM unified_match_log GROUP BY source_system")
rows = cur.fetchall()
print("\n| Source | Count |")
print("|--------|-------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.close()
conn.close()
