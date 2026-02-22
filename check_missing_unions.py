import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT COUNT(DISTINCT r.f_num) 
    FROM f7_union_employer_relations r
    LEFT JOIN unions_master u ON r.f_num = u.f_num
    WHERE u.f_num IS NULL
""")
missing_count = cur.fetchone()[0]
print(f"Missing unions (f_num in relations but not in master): {missing_count}")

cur.execute("""
    SELECT SUM(COALESCE(r.unit_size, 0))
    FROM f7_union_employer_relations r
    LEFT JOIN unions_master u ON r.f_num = u.f_num
    WHERE u.f_num IS NULL
""")
missing_workers = cur.fetchone()[0]
print(f"Workers affected by missing unions: {missing_workers}")

cur.close()
conn.close()
