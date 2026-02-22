import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT COUNT(*) 
    FROM f7_union_employer_relations r
    LEFT JOIN f7_employers e ON r.employer_id = e.employer_id
    WHERE e.employer_id IS NULL
""")
orphans_raw = cur.fetchone()[0]
print(f"Orphans vs f7_employers: {orphans_raw}")

cur.execute("SELECT employer_id FROM f7_union_employer_relations LIMIT 5")
print("Sample IDs in relations:", cur.fetchall())

cur.execute("SELECT employer_id FROM f7_employers_deduped LIMIT 5")
print("Sample IDs in deduped:", cur.fetchall())

cur.close()
conn.close()
