"""Investigate remaining double-counting patterns in f7_employers_deduped."""
import psycopg2

conn = psycopg2.connect(
    host='localhost', dbname='olms_multiyear',
    user='postgres', password='Juniordog33!'
)
cur = conn.cursor()

# 1. SAG-AFTRA: how many are currently excluded vs still counted?
cur.execute("""
    SELECT exclude_from_counts, exclude_reason, COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE latest_union_fnum = 391
       OR latest_union_name ILIKE '%%SAG%%AFTRA%%'
       OR latest_union_name ILIKE '%%screen actor%%'
    GROUP BY exclude_from_counts, exclude_reason
    ORDER BY SUM(latest_unit_size) DESC
""")
print('=== SAG-AFTRA employers ===')
for r in cur.fetchall():
    print('  excluded=%s reason=%-30s | %5d employers | %s workers' % (
        r[0], r[1], r[2], '{:,}'.format(r[3] or 0)))

# total SAG-AFTRA
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size),
           SUM(CASE WHEN exclude_from_counts THEN latest_unit_size ELSE 0 END),
           SUM(CASE WHEN NOT exclude_from_counts THEN latest_unit_size ELSE 0 END)
    FROM f7_employers_deduped
    WHERE latest_union_fnum = 391
       OR latest_union_name ILIKE '%%SAG%%AFTRA%%'
       OR latest_union_name ILIKE '%%screen actor%%'
""")
r = cur.fetchone()
print('  TOTAL: %d employers, %s workers (%s excluded, %s still counted)' % (
    r[0], '{:,}'.format(r[1] or 0), '{:,}'.format(r[2] or 0), '{:,}'.format(r[3] or 0)))

# 2. Top 25 unions by COUNTED workers
print()
print('=== Top 25 unions by COUNTED workers ===')
cur.execute("""
    SELECT latest_union_fnum,
           (ARRAY_AGG(latest_union_name))[1] as name,
           COUNT(*) as emp_count,
           SUM(latest_unit_size) as total_workers,
           MAX(latest_unit_size) as max_single,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size) as median
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE AND latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum
    ORDER BY SUM(latest_unit_size) DESC
    LIMIT 25
""")
print('  %-6s %-45s | %5s | %10s | %10s | %7s' % ('fnum', 'union_name', 'emps', 'total_wkrs', 'max_single', 'median'))
print('  ' + '-' * 100)
for r in cur.fetchall():
    print('  %-6s %-45s | %5d | %10s | %10s | %7.0f' % (
        r[0], (r[1] or '')[:45], r[2], '{:,}'.format(r[3] or 0), '{:,}'.format(r[4] or 0), r[5] or 0))

# 3. Identical worker count patterns (counted only, size >= 100)
print()
print('=== Identical worker counts still COUNTED (size >= 100, 2+ copies) ===')
cur.execute("""
    SELECT latest_union_fnum,
           (ARRAY_AGG(latest_union_name))[1] as name,
           latest_unit_size,
           COUNT(*) as copies,
           latest_unit_size * (COUNT(*) - 1) as wasted_workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND latest_unit_size >= 100
      AND latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum, latest_unit_size
    HAVING COUNT(*) >= 2
    ORDER BY latest_unit_size * (COUNT(*) - 1) DESC
    LIMIT 30
""")
total_wasted = 0
for r in cur.fetchall():
    total_wasted += r[4]
    print('  fnum=%-6s %-40s | size=%7s x %d = %s wasted' % (
        r[0], (r[1] or '')[:40], '{:,}'.format(r[2]), r[3], '{:,}'.format(r[4])))
print('  TOTAL potential over-count from identical sizes: %s' % '{:,}'.format(total_wasted))

# 4. Employers with very large worker counts that are still counted
print()
print('=== Largest single employer worker counts (still counted) ===')
cur.execute("""
    SELECT employer_id, employer_name, city, state, latest_unit_size,
           latest_union_fnum, latest_union_name
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
    ORDER BY latest_unit_size DESC
    LIMIT 30
""")
for r in cur.fetchall():
    print('  %s | %-40s | %s, %s | %10s wkrs | fnum=%s %s' % (
        r[0][:8], (r[1] or '')[:40], r[2] or '', r[3] or '',
        '{:,}'.format(r[4] or 0), r[5], (r[6] or '')[:30]))

# 5. Check for "signatory" / "various" / "multiple" patterns still counted
print()
print('=== Signatory/various patterns still COUNTED ===')
cur.execute("""
    SELECT employer_name, city, state, latest_unit_size, latest_union_name
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (employer_name ILIKE '%%signator%%'
        OR employer_name ILIKE '%%various%%'
        OR employer_name ILIKE '%%multiple employer%%'
        OR employer_name ILIKE 'AGC %%'
        OR employer_name ILIKE 'AGC of %%')
    ORDER BY latest_unit_size DESC
    LIMIT 20
""")
rows = cur.fetchall()
print('  Found: %d' % len(rows))
for r in rows:
    print('  %-50s | %s, %s | %7s wkrs | %s' % (
        (r[0] or '')[:50], r[1] or '', r[2] or '',
        '{:,}'.format(r[3] or 0), (r[4] or '')[:30]))

# 6. REPEATED_WORKER_COUNT - what threshold was used?
print()
print('=== Current exclusion summary ===')
cur.execute("""
    SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
           COUNT(*) as employers,
           SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    GROUP BY exclude_reason
    ORDER BY SUM(latest_unit_size) DESC
""")
for r in cur.fetchall():
    print('  %-30s | %6d employers | %12s workers' % (r[0], r[1], '{:,}'.format(r[2] or 0)))

conn.close()
