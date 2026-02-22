import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'f7_union_employer_relations'")
rows = cur.fetchall()
for row in rows:
    print(row[0])

cur.close()
conn.close()
