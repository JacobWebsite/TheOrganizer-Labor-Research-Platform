import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
total_rels = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(*) 
    FROM f7_union_employer_relations r
    LEFT JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
    WHERE e.employer_id IS NULL
""")
orphaned_rels = cur.fetchone()[0]

cur.execute("""
    SELECT SUM(COALESCE(r.bargaining_unit_size, 0))
    FROM f7_union_employer_relations r
    LEFT JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
    WHERE e.employer_id IS NULL
""")
orphaned_workers = cur.fetchone()[0]

print(f"Total relationships: {total_rels}")
print(f"Orphaned relationships: {orphaned_rels} ({100.0*orphaned_rels/total_rels:.1f}%)")
print(f"Orphaned workers: {orphaned_workers}")

cur.close()
conn.close()
