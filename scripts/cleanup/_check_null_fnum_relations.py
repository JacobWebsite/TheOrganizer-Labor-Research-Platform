import os
from db_config import get_connection
"""Show which known unions are linked to null-fnum employers via relations table."""
import psycopg2

conn = get_connection()
cur = conn.cursor()

print('=== Top unions from relations table for null-fnum employers ===')
cur.execute("""
    SELECT r.union_file_number, um.union_name, um.aff_abbr,
           COUNT(DISTINCT e.employer_id) as emp_count,
           SUM(e.latest_unit_size) as workers
    FROM f7_employers_deduped e
    JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
    LEFT JOIN unions_master um ON CAST(um.f_num AS INTEGER) = r.union_file_number
    WHERE e.latest_union_fnum IS NULL AND e.exclude_from_counts = FALSE
    GROUP BY r.union_file_number, um.union_name, um.aff_abbr
    ORDER BY SUM(e.latest_unit_size) DESC
    LIMIT 25
""")
for r in cur.fetchall():
    print("  fnum=%-8s %-45s %-6s | %4d emps | %8s workers" % (
        r[0] or 'NULL', (r[1] or '(unknown)')[:45], r[2] or '', r[3], '{:,}'.format(r[4] or 0)))

# How many could we auto-fix?
print("\n=== Auto-fix potential ===")
cur.execute("""
    WITH fixable AS (
        SELECT e.employer_id, r.union_file_number,
               ROW_NUMBER() OVER (PARTITION BY e.employer_id ORDER BY r.bargaining_unit_size DESC) as rn
        FROM f7_employers_deduped e
        JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
        WHERE e.latest_union_fnum IS NULL
    )
    SELECT COUNT(DISTINCT employer_id) as fixable_employers
    FROM fixable WHERE rn = 1
""")
r = cur.fetchone()
print("  Employers with null fnum that have relations: %d" % r[0])

# And for those without relations, how many have a union name we can match?
cur.execute("""
    WITH unmatched AS (
        SELECT e.employer_id, e.latest_union_name
        FROM f7_employers_deduped e
        WHERE e.latest_union_fnum IS NULL
          AND e.exclude_from_counts = FALSE
          AND e.latest_union_name IS NOT NULL AND e.latest_union_name != ''
          AND NOT EXISTS (
              SELECT 1 FROM f7_union_employer_relations r WHERE r.employer_id = e.employer_id
          )
    )
    SELECT COUNT(*) FROM unmatched
""")
r = cur.fetchone()
print("  Employers with union name but NO relations: %d (need fuzzy match)" % r[0])

# Total null-fnum counted
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\n  Total null-fnum counted: %d employers, %s workers" % (r[0], '{:,}'.format(r[1] or 0)))

conn.close()
