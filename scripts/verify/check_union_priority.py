import os
from db_config import get_connection
"""Check unionized records that still have score_priority set."""
import psycopg2

conn = get_connection()
cur = conn.cursor()

# Check which unionized records have score_priority
cur.execute("""
    SELECT company_name, has_union, organizing_score, score_priority, f7_match_method
    FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
    ORDER BY company_name
""")
rows = cur.fetchall()

print("Unionized records with score_priority still set:")
print("-" * 70)
for row in rows:
    print("  %s | union=%s | score=%s | tier=%s | method=%s" % row)

print("\nTotal: %d records" % len(rows))
print("")

# Also check: do all of these have NULL organizing_score?
cur.execute("""
    SELECT
        SUM(CASE WHEN organizing_score IS NOT NULL THEN 1 ELSE 0 END) as has_score,
        SUM(CASE WHEN organizing_score IS NULL THEN 1 ELSE 0 END) as no_score
    FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
""")
has_score, no_score = cur.fetchone()
print("Of those %d: %s have organizing_score, %s have NULL score" % (len(rows), has_score, no_score))

# Check the broader unionized population
cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN f7_match_method = 'SIBLING_FIX' THEN 1 ELSE 0 END) as sibling_fix,
        SUM(CASE WHEN f7_match_method = 'NAME_CITY' THEN 1 ELSE 0 END) as name_city,
        SUM(CASE WHEN f7_match_method IS NULL THEN 1 ELSE 0 END) as no_method,
        SUM(CASE WHEN score_priority IS NOT NULL THEN 1 ELSE 0 END) as has_tier,
        SUM(CASE WHEN organizing_score IS NOT NULL THEN 1 ELSE 0 END) as has_score
    FROM mergent_employers
    WHERE has_union = TRUE
""")
row = cur.fetchone()
print("\nAll unionized records: %d total" % row[0])
print("  SIBLING_FIX: %s" % row[1])
print("  NAME_CITY: %s" % row[2])
print("  No method: %s" % row[3])
print("  Has tier: %s" % row[4])
print("  Has score: %s" % row[5])

# Run a bigger sample of NLRB matches for address tier
cur.close()
conn.close()
