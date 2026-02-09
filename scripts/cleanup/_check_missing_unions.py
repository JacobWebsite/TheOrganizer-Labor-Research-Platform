import os
"""Check employers with missing union linkage (latest_union_fnum IS NULL)."""
import psycopg2

conn = psycopg2.connect(
    host='localhost', dbname='olms_multiyear',
    user='postgres', password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# Overview
cur.execute("""
    SELECT COUNT(*),
           SUM(latest_unit_size),
           COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END),
           SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END)
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
""")
r = cur.fetchone()
print("=== Employers with NULL latest_union_fnum ===")
print("  Total: %d (%s workers)" % (r[0], '{:,}'.format(r[1] or 0)))
print("  Counted: %d (%s workers)" % (r[2], '{:,}'.format(r[3] or 0)))

# Do they have union names?
cur.execute("""
    SELECT
        COUNT(CASE WHEN latest_union_name IS NOT NULL AND latest_union_name != '' THEN 1 END) as has_name,
        COUNT(CASE WHEN latest_union_name IS NULL OR latest_union_name = '' THEN 1 END) as no_name
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\n  With union name: %d" % r[0])
print("  Without union name: %d" % r[1])

# Top union names for null-fnum employers
print("\n=== Top 30 Union Names (no fnum, still counted) ===")
cur.execute("""
    SELECT latest_union_name, COUNT(*) as emp_count, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
      AND latest_union_name IS NOT NULL AND latest_union_name != ''
    GROUP BY latest_union_name
    ORDER BY SUM(latest_unit_size) DESC
    LIMIT 30
""")
for r in cur.fetchall():
    print("  %-60s | %4d emps | %8s workers" % (
        (r[0] or '')[:60], r[1], '{:,}'.format(r[2] or 0)))

# Can we find these unions in unions_master?
print("\n=== Matching null-fnum union names to unions_master ===")
cur.execute("""
    WITH null_fnum_unions AS (
        SELECT DISTINCT latest_union_name
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
          AND latest_union_name IS NOT NULL AND latest_union_name != ''
    )
    SELECT nfu.latest_union_name,
           um.f_num, um.union_name, um.aff_abbr,
           similarity(nfu.latest_union_name, um.union_name) as sim
    FROM null_fnum_unions nfu
    JOIN unions_master um ON similarity(nfu.latest_union_name, um.union_name) > 0.4
    ORDER BY sim DESC
    LIMIT 30
""")
print("  %-50s | fnum=%-6s | %-50s | sim" % ('F7 union name', '', 'unions_master name'))
print("  " + "-" * 170)
for r in cur.fetchall():
    print("  %-50s | fnum=%-6s | %-50s | %.2f" % (
        (r[0] or '')[:50], r[1], (r[2] or '')[:50], r[4]))

# Show some sample employers
print("\n=== Sample Employers with Largest Worker Counts (no fnum) ===")
cur.execute("""
    SELECT employer_name, city, state, latest_unit_size, latest_union_name,
           employer_id
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
    ORDER BY latest_unit_size DESC
    LIMIT 40
""")
for r in cur.fetchall():
    print("  %-45s | %s, %s | %6s wkrs | union: %s" % (
        (r[0] or '')[:45], r[1] or '', r[2] or '',
        '{:,}'.format(r[3] or 0), (r[4] or '')[:40]))

# Check f7_union_employer_relations for these
print("\n=== Do null-fnum employers have relations with known unions? ===")
cur.execute("""
    SELECT COUNT(DISTINCT e.employer_id) as has_relation,
           (SELECT COUNT(*) FROM f7_employers_deduped
            WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE) - COUNT(DISTINCT e.employer_id) as no_relation
    FROM f7_employers_deduped e
    JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
    WHERE e.latest_union_fnum IS NULL AND e.exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("  With f7_union_employer_relations: %d" % r[0])
print("  Without any relation: %d" % r[1])

# For those with relations, can we get the fnum?
print("\n=== Top unions from relations table for null-fnum employers ===")
cur.execute("""
    SELECT r.f_num, r.union_name, COUNT(DISTINCT e.employer_id) as emp_count,
           SUM(e.latest_unit_size) as workers
    FROM f7_employers_deduped e
    JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
    WHERE e.latest_union_fnum IS NULL AND e.exclude_from_counts = FALSE
    GROUP BY r.f_num, r.union_name
    ORDER BY SUM(e.latest_unit_size) DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print("  fnum=%-8s %-50s | %4d emps | %8s workers" % (
        r[0] or 'NULL', (r[1] or '')[:50], r[2], '{:,}'.format(r[3] or 0)))

conn.close()
