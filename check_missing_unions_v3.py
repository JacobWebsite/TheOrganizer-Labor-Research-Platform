import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT COUNT(DISTINCT r.union_file_number) 
    FROM f7_union_employer_relations r
    LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num::text
    WHERE u.f_num IS NULL
""")
missing_count = cur.fetchone()[0]
print(f"Missing unions: {missing_count}")

cur.execute("""
    SELECT SUM(COALESCE(r.bargaining_unit_size, 0))
    FROM f7_union_employer_relations r
    LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num::text
    WHERE u.f_num IS NULL
""")
missing_workers = cur.fetchone()[0]
print(f"Workers affected: {missing_workers}")

cur.close()
conn.close()
