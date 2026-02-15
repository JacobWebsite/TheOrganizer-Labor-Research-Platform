import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = 'osha_establishments'
    ORDER BY indexname
""")
for row in cur.fetchall():
    print(row[0])
    print("  ", row[1][:200])
    print()
cur.close()
conn.close()
