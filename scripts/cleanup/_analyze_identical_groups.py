import os
"""Analyze identical-size groups by address diversity to determine true dups vs distinct employers."""
import psycopg2

conn = psycopg2.connect(
    host='localhost', dbname='olms_multiyear',
    user='postgres', password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# Check how many of the identical-size groups have address/geocode data
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, latest_unit_size,
               COUNT(*) as copies,
               COUNT(CASE WHEN street IS NOT NULL AND street != '' THEN 1 END) as has_street,
               COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as has_geocode,
               COUNT(DISTINCT city) as distinct_cities,
               COUNT(DISTINCT state) as distinct_states
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size
        HAVING COUNT(*) >= 2
    )
    SELECT
        COUNT(*) as total_groups,
        SUM(copies) as total_records,
        SUM(copies - 1) as excess_records,
        AVG(distinct_cities::float / copies) as avg_city_diversity,
        SUM(CASE WHEN distinct_cities = 1 THEN copies - 1 ELSE 0 END) as same_city_excess,
        SUM(CASE WHEN distinct_cities > 1 THEN copies - 1 ELSE 0 END) as diff_city_excess,
        SUM(CASE WHEN distinct_states > 1 THEN copies - 1 ELSE 0 END) as diff_state_excess,
        AVG(has_street::float / copies) as avg_street_coverage,
        AVG(has_geocode::float / copies) as avg_geocode_coverage
    FROM dup_groups
""")
r = cur.fetchone()
print('=== Identical-Size Group Analysis ===')
print('Total groups:          %d' % r[0])
print('Total records:         %d' % r[1])
print('Excess records:        %d' % r[2])
print()
print('Avg city diversity:    %.2f (1.0 = all same city)' % r[3])
print('Same-city excess:      %d (likely true dups)' % r[4])
print('Diff-city excess:      %d (likely distinct employers)' % r[5])
print('Diff-state excess:     %d (almost certainly distinct)' % r[6])
print()
print('Avg street coverage:   %.1f%%' % (r[7] * 100))
print('Avg geocode coverage:  %.1f%%' % (r[8] * 100))

# Breakdown by city diversity
print()
print('=== Breakdown by City Diversity ===')
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, latest_unit_size,
               COUNT(*) as copies,
               COUNT(DISTINCT city) as distinct_cities,
               latest_unit_size * (COUNT(*) - 1) as excess_workers
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size
        HAVING COUNT(*) >= 2
    )
    SELECT
        CASE
            WHEN distinct_cities = 1 THEN 'Same city'
            WHEN distinct_cities = copies THEN 'All different cities'
            ELSE 'Mixed'
        END as category,
        COUNT(*) as groups,
        SUM(copies - 1) as excess_records,
        SUM(excess_workers) as excess_workers
    FROM dup_groups
    GROUP BY 1
    ORDER BY SUM(excess_workers) DESC
""")
for r in cur.fetchall():
    print('  %-25s | %4d groups | %5d excess records | %s excess workers' % (
        r[0], r[1], r[2], '{:,}'.format(r[3])))

# Same-city groups with identical addresses (most likely true duplicates)
print()
print('=== Same-City Groups: Street Address Comparison ===')
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, latest_unit_size, city, state,
               COUNT(*) as copies,
               COUNT(DISTINCT street) as distinct_streets,
               COUNT(DISTINCT COALESCE(street, '')) as distinct_streets_inc_null,
               latest_unit_size * (COUNT(*) - 1) as excess_workers
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size, city, state
        HAVING COUNT(*) >= 2
    )
    SELECT
        CASE
            WHEN distinct_streets <= 1 THEN 'Same/no street'
            WHEN distinct_streets = copies THEN 'All different streets'
            ELSE 'Mixed streets'
        END as category,
        COUNT(*) as groups,
        SUM(copies - 1) as excess_records,
        SUM(excess_workers) as excess_workers
    FROM dup_groups
    GROUP BY 1
    ORDER BY SUM(excess_workers) DESC
""")
for r in cur.fetchall():
    print('  %-25s | %4d groups | %5d excess records | %s excess workers' % (
        r[0], r[1], r[2], '{:,}'.format(r[3])))

# Show some examples of same-city, same-street dups (high confidence)
print()
print('=== Top 20 High-Confidence Duplicates (same city, same/no street) ===')
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, latest_unit_size, city, state,
               (ARRAY_AGG(latest_union_name ORDER BY latest_unit_size DESC))[1] as union_name,
               (ARRAY_AGG(employer_name ORDER BY latest_unit_size DESC))[1:3] as sample_names,
               COUNT(*) as copies,
               COUNT(DISTINCT street) as distinct_streets,
               latest_unit_size * (COUNT(*) - 1) as excess_workers
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size, city, state
        HAVING COUNT(*) >= 2 AND COUNT(DISTINCT street) <= 1
    )
    SELECT union_name, city, state, latest_unit_size, copies, excess_workers, sample_names
    FROM dup_groups
    ORDER BY excess_workers DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print('  %-40s | %s, %s | %s x %d = %s excess | %s' % (
        (r[0] or '')[:40], r[1] or '', r[2] or '',
        '{:,}'.format(r[3]), r[4], '{:,}'.format(r[5]),
        '; '.join((n or '')[:30] for n in (r[6] or [])[:2])))

# Show examples of DIFFERENT city groups (these are likely legitimate)
print()
print('=== Top 15 Multi-City Groups (likely LEGITIMATE distinct employers) ===')
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, latest_unit_size,
               (ARRAY_AGG(latest_union_name))[1] as union_name,
               (ARRAY_AGG(DISTINCT city))[1:5] as sample_cities,
               COUNT(*) as copies,
               COUNT(DISTINCT city) as distinct_cities,
               latest_unit_size * (COUNT(*) - 1) as excess_workers
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size
        HAVING COUNT(*) >= 2 AND COUNT(DISTINCT city) > 1
    )
    SELECT union_name, latest_unit_size, copies, distinct_cities, excess_workers, sample_cities
    FROM dup_groups
    ORDER BY excess_workers DESC
    LIMIT 15
""")
for r in cur.fetchall():
    print('  %-40s | %s x %d (%d cities) = %s excess | %s' % (
        (r[0] or '')[:40], '{:,}'.format(r[1]), r[2], r[3],
        '{:,}'.format(r[4]),
        ', '.join((c or '')[:15] for c in (r[5] or [])[:4])))

# Summary: what's safe to exclude?
print()
print('=== SAFE EXCLUSION SUMMARY ===')
# Same city + same/no street = high confidence duplicates
cur.execute("""
    WITH same_city_same_street AS (
        SELECT latest_union_fnum, latest_unit_size, city, state,
               COUNT(*) as copies,
               latest_unit_size * (COUNT(*) - 1) as excess_workers
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND latest_unit_size >= 100
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, latest_unit_size, city, state
        HAVING COUNT(*) >= 2 AND COUNT(DISTINCT street) <= 1
    )
    SELECT SUM(copies - 1) as excess_records, SUM(excess_workers) as excess_workers
    FROM same_city_same_street
""")
r = cur.fetchone()
print('  Same city + same/no street (HIGH confidence):')
print('    %d excess records, %s excess workers' % (r[0], '{:,}'.format(r[1])))

# Signatory patterns (all thresholds)
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (employer_name ILIKE 'AGC %%'
        OR employer_name ILIKE 'AGC of %%'
        OR employer_name ILIKE '%%all signator%%'
        OR employer_name ILIKE '%%signatories to%%'
        OR employer_name ILIKE 'various %%contractor%%'
        OR employer_name ILIKE 'various employers%%'
        OR employer_name ILIKE '%%multiple employer%%'
        OR employer_name ILIKE '%%company list%%'
        OR city ILIKE 'various'
        OR city ILIKE 'multiple'
        OR employer_name ILIKE '%%& various%%'
        OR employer_name ILIKE '%%various contractor%%'
        OR employer_name ILIKE '%%(various)%%'
        OR employer_name ILIKE '%%signatory contractor%%'
        OR employer_name ILIKE '%%signatory %%employer%%'
        OR employer_name ILIKE '%%signatory %%highway%%'
        OR employer_name ILIKE '%%signatory %%build%%'
        OR employer_name ILIKE '%%signatory %%industr%%')
""")
sig = cur.fetchone()
print()
print('  Signatory patterns (no minimum):')
print('    %d employers, %s workers' % (sig[0], '{:,}'.format(sig[1] or 0)))

# Current BLS numbers
cur.execute("""
    SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END)
    FROM f7_employers_deduped
""")
current = cur.fetchone()[0]

safe_reduction = (r[1] or 0) + (sig[1] or 0)
print()
print('  Combined safe reduction: ~%s workers' % '{:,}'.format(safe_reduction))
print('  Before: %s (%.1f%% BLS)' % ('{:,}'.format(current), current / 7200000 * 100))
print('  After:  ~%s (~%.1f%% BLS)' % ('{:,}'.format(current - safe_reduction), (current - safe_reduction) / 7200000 * 100))

conn.close()
