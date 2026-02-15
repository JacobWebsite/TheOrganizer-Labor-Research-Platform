import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()
# For materialized views, use pg_attribute
cur.execute("""
    SELECT a.attname
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    WHERE c.relname = 'mv_employer_search' AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY a.attnum
""")
print("mv_employer_search columns:", [r[0] for r in cur.fetchall()])
conn.close()
