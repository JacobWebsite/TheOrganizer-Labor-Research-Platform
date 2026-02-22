import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT employer_id, employer_name, naics, has_nlrb, has_osha FROM mv_employer_data_sources WHERE employer_name ILIKE '%Starbucks%' LIMIT 5")
rows = cur.fetchall()
for row in rows:
    print(row)

cur.close()
conn.close()
