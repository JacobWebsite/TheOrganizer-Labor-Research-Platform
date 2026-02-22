import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_name IN ('entity_statement', 'ooc_statement', 'ooc_annotations', 'entity_annotations', 'person_statement')
""")
rows = cur.fetchall()
for row in rows:
    print(row)

cur.close()
conn.close()
