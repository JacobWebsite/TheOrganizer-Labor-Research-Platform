import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM osha_f7_matches")
count = cur.fetchone()[0]
print(f"osha_f7_matches: {count}")

cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches")
unique_f7 = cur.fetchone()[0]
print(f"Unique f7_employer_id: {unique_f7}")

cur.close()
conn.close()
