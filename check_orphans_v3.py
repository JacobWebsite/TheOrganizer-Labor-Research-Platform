import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(DISTINCT employer_id) FROM f7_union_employer_relations")
dist_rel = cur.fetchone()[0]
print(f"Distinct employer_id in relations: {dist_rel}")

cur.execute("SELECT COUNT(DISTINCT e.employer_id) FROM f7_union_employer_relations r JOIN f7_employers_deduped e ON r.employer_id = e.employer_id")
matched_rel = cur.fetchone()[0]
print(f"Distinct employer_id matched in deduped: {matched_rel}")

cur.close()
conn.close()
