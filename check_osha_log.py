import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT status, count(*) FROM unified_match_log WHERE source_system = 'osha' GROUP BY status")
rows = cur.fetchall()
print("| Status | Count |")
print("|--------|-------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.execute("SELECT confidence_band, count(*) FROM unified_match_log WHERE source_system = 'osha' AND status = 'active' GROUP BY confidence_band")
rows = cur.fetchall()
print("\nActive OSHA by Confidence Band:")
for row in rows:
    print(f"| {row[0]} | {row[1]} |")

cur.close()
conn.close()
