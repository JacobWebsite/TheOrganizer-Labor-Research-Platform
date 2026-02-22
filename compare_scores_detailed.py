import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT o.estab_name, o.score_osha AS old_osha, u.score_osha AS new_osha,
           o.score_nlrb AS old_nlrb, u.score_nlrb AS new_nlrb,
           u.unified_score, u.coverage_pct
    FROM mv_organizing_scorecard o
    JOIN osha_f7_matches m ON o.establishment_id = m.establishment_id
    JOIN mv_unified_scorecard u ON m.f7_employer_id = u.employer_id
    LIMIT 20
""")
rows = cur.fetchall()
print("| Name | Old OSHA | New OSHA | Old NLRB | New NLRB | Unified | Coverage |")
print("|------|----------|----------|----------|----------|---------|----------|")
for row in rows:
    print(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]}% |")

cur.close()
conn.close()
