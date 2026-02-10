"""Recalibrate tier thresholds after Phase 2 re-scoring."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection
import psycopg2.extras

conn = get_connection(cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Recalibrate: TOP >= 30, HIGH >= 25, MEDIUM >= 20, LOW < 20
cur.execute("""
    UPDATE mergent_employers
    SET score_priority = CASE
        WHEN organizing_score >= 30 THEN 'TOP'
        WHEN organizing_score >= 25 THEN 'HIGH'
        WHEN organizing_score >= 20 THEN 'MEDIUM'
        ELSE 'LOW'
    END
    WHERE has_union IS NOT TRUE
""")
print(f"Updated {cur.rowcount:,} employers")
conn.commit()

cur.execute("""
    SELECT score_priority, COUNT(*) as cnt,
           ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 1) as pct
    FROM mergent_employers WHERE has_union IS NOT TRUE
    GROUP BY score_priority
    ORDER BY CASE score_priority
        WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END
""")
print("\nRecalibrated tier distribution:")
for r in cur.fetchall():
    print(f"  {r['score_priority']}: {r['cnt']:>7,} ({r['pct']}%)")

cur.close(); conn.close()
