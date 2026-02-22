import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT o.employer_name, o.score AS old_score, u.unified_score AS new_score, 
           u.coverage_pct, u.factors_available
    FROM mv_organizing_scorecard o
    JOIN mv_unified_scorecard u ON o.employer_id = u.employer_id
    LIMIT 20
""")
rows = cur.fetchall()
print("| Employer | Old Score | New Score | Coverage | Factors |")
print("|----------|-----------|-----------|----------|---------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]}% | {row[4]} |")

cur.close()
conn.close()
