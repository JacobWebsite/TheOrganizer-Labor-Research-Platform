import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT attname 
    FROM pg_attribute 
    WHERE attrelid = 'mv_organizing_scorecard'::regclass 
      AND attnum > 0 
      AND NOT attisdropped
""")
rows = cur.fetchall()
for row in rows:
    print(row[0])

cur.close()
conn.close()
