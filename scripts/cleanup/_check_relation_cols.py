import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'f7_union_employer_relations'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print("  %s (%s)" % (r[0], r[1]))

# Also show a sample row
cur.execute("SELECT * FROM f7_union_employer_relations LIMIT 3")
cols = [d[0] for d in cur.description]
print("\nColumns: %s" % cols)
for r in cur.fetchall():
    print("  %s" % str(r))
conn.close()
