import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        relname AS table_name,
        pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
        pg_size_pretty(pg_relation_size(relid)) AS table_size,
        pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size
    FROM pg_catalog.pg_statio_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 20
""")
rows = cur.fetchall()
print("| Table | Total Size | Table Size | Index Size |")
print("|-------|------------|------------|------------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")

cur.close()
conn.close()
