import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(DISTINCT source_id) FROM unified_match_log WHERE source_system = 'osha' AND status = 'active'")
count = cur.fetchone()[0]
print(f"Unique OSHA source_id (active): {count}")

cur.execute("SELECT COUNT(DISTINCT target_id) FROM unified_match_log WHERE source_system = 'osha' AND status = 'active'")
count = cur.fetchone()[0]
print(f"Unique OSHA target_id (active): {count}")

cur.close()
conn.close()
