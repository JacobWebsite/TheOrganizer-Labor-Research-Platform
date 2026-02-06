"""Scope out the impact of lowering signatory + identical-size thresholds."""
import psycopg2

conn = psycopg2.connect(
    host='localhost', dbname='olms_multiyear',
    user='postgres', password='Juniordog33!'
)
cur = conn.cursor()

print("=" * 70)
print("SCOPE: Lowered Thresholds for Signatory + Identical-Size Exclusions")
print("=" * 70)

# Current state
cur.execute("""
    SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END)
    FROM f7_employers_deduped
""")
current_counted = cur.fetchone()[0]
print("\nCurrent counted workers: %s" % '{:,}'.format(current_counted))

# ========================================================================
# 1. SIGNATORY PATTERNS - remove size threshold entirely
# ========================================================================
print("\n" + "=" * 70)
print("1. SIGNATORY PATTERNS (currently >= 1000, proposed: no minimum)")
print("=" * 70)

# What the current filter catches (already excluded)
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE exclude_reason = 'SIGNATORY_PATTERN'
""")
r = cur.fetchone()
print("\nAlready excluded: %d employers, %s workers" % (r[0], '{:,}'.format(r[1] or 0)))

# NEW catches at various thresholds
for threshold in [0, 100, 200, 500]:
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
            OR city ILIKE 'multiple')
          AND latest_unit_size >= %s
    """, (threshold,))
    r = cur.fetchone()
    print("  threshold >= %4d: %3d new employers, %7s new workers" % (
        threshold, r[0], '{:,}'.format(r[1] or 0)))

# Also check broader patterns
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (employer_name ILIKE '%%& various%%'
        OR employer_name ILIKE '%%various contractor%%'
        OR employer_name ILIKE '%%(various)%%'
        OR employer_name ILIKE '%%signatory contractor%%'
        OR employer_name ILIKE '%%signatory %%employer%%'
        OR employer_name ILIKE '%%signatory %%highway%%'
        OR employer_name ILIKE '%%signatory %%build%%'
        OR employer_name ILIKE '%%signatory %%industr%%')
      AND NOT (employer_name ILIKE 'AGC %%'
            OR employer_name ILIKE 'AGC of %%'
            OR employer_name ILIKE '%%all signator%%'
            OR employer_name ILIKE '%%signatories to%%'
            OR employer_name ILIKE 'various %%contractor%%'
            OR employer_name ILIKE 'various employers%%'
            OR employer_name ILIKE '%%multiple employer%%'
            OR employer_name ILIKE '%%company list%%'
            OR city ILIKE 'various'
            OR city ILIKE 'multiple')
""")
r = cur.fetchone()
print("\n  Additional broader patterns: %d employers, %s workers" % (r[0], '{:,}'.format(r[1] or 0)))

# Show them
cur.execute("""
    SELECT employer_name, city, state, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (employer_name ILIKE '%%& various%%'
        OR employer_name ILIKE '%%various contractor%%'
        OR employer_name ILIKE '%%(various)%%'
        OR employer_name ILIKE '%%signatory contractor%%'
        OR employer_name ILIKE '%%signatory %%employer%%'
        OR employer_name ILIKE '%%signatory %%highway%%'
        OR employer_name ILIKE '%%signatory %%build%%'
        OR employer_name ILIKE '%%signatory %%industr%%')
    ORDER BY latest_unit_size DESC
    LIMIT 15
""")
for r in cur.fetchall():
    print("    %-55s | %s, %s | %s wkrs" % (
        (r[0] or '')[:55], r[1] or '', r[2] or '', '{:,}'.format(r[3] or 0)))

# ========================================================================
# 2. IDENTICAL WORKER COUNTS - lower threshold from 1000 to 100
# ========================================================================
print("\n" + "=" * 70)
print("2. IDENTICAL WORKER COUNTS (currently >= 1000, proposed: >= 100)")
print("=" * 70)

cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE exclude_reason = 'DUPLICATE_WORKER_COUNT'
""")
r = cur.fetchone()
print("\nAlready excluded (>= 1000): %d employers, %s workers" % (r[0], '{:,}'.format(r[1] or 0)))

for threshold in [100, 200, 500]:
    cur.execute("""
        WITH duplicates AS (
            SELECT employer_id, latest_union_fnum, latest_unit_size,
                   ROW_NUMBER() OVER (
                       PARTITION BY latest_union_fnum, latest_unit_size
                       ORDER BY employer_id
                   ) as rn,
                   COUNT(*) OVER (PARTITION BY latest_union_fnum, latest_unit_size) as cnt
            FROM f7_employers_deduped
            WHERE latest_union_fnum IS NOT NULL
              AND latest_unit_size >= %s
              AND exclude_from_counts = FALSE
        )
        SELECT COUNT(*), SUM(latest_unit_size)
        FROM duplicates
        WHERE rn > 1 AND cnt > 1
    """, (threshold,))
    r = cur.fetchone()
    print("  threshold >= %4d: %4d new employers, %8s workers to exclude" % (
        threshold, r[0], '{:,}'.format(r[1] or 0)))

# Show the biggest groups at >= 100
print("\n  Top 20 identical-count groups (>= 100, still counted):")
cur.execute("""
    SELECT latest_union_fnum,
           (ARRAY_AGG(latest_union_name ORDER BY latest_unit_size DESC))[1] as name,
           latest_unit_size, COUNT(*) as copies,
           latest_unit_size * (COUNT(*) - 1) as excess
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND latest_unit_size >= 100
      AND latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum, latest_unit_size
    HAVING COUNT(*) >= 3
    ORDER BY latest_unit_size * (COUNT(*) - 1) DESC
    LIMIT 20
""")
for r in cur.fetchall():
    print("    fnum=%-6s %-40s | %5s x %2d copies = %7s excess" % (
        r[0], (r[1] or '')[:40], '{:,}'.format(r[2]), r[3], '{:,}'.format(r[4])))

# ========================================================================
# Combined impact
# ========================================================================
print("\n" + "=" * 70)
print("COMBINED IMPACT ESTIMATE")
print("=" * 70)

# Signatory at >= 0
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

# Identical at >= 100
cur.execute("""
    WITH duplicates AS (
        SELECT employer_id, latest_union_fnum, latest_unit_size,
               ROW_NUMBER() OVER (
                   PARTITION BY latest_union_fnum, latest_unit_size
                   ORDER BY employer_id
               ) as rn,
               COUNT(*) OVER (PARTITION BY latest_union_fnum, latest_unit_size) as cnt
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND latest_unit_size >= 100
          AND exclude_from_counts = FALSE
    )
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM duplicates
    WHERE rn > 1 AND cnt > 1
""")
dup = cur.fetchone()

print("\n  Signatory pattern (no min): %d employers, %s workers" % (sig[0], '{:,}'.format(sig[1] or 0)))
print("  Identical count (>= 100):   %d employers, %s workers" % (dup[0], '{:,}'.format(dup[1] or 0)))
total_workers = (sig[1] or 0) + (dup[1] or 0)
print("  Combined (with overlap):    up to %s workers" % '{:,}'.format(total_workers))
print("\n  Before: %s counted" % '{:,}'.format(current_counted))
print("  After:  ~%s counted" % '{:,}'.format(current_counted - total_workers))
print("  BLS:    %s (%.1f%% -> ~%.1f%%)" % (
    '{:,}'.format(7200000),
    current_counted / 7200000 * 100,
    (current_counted - total_workers) / 7200000 * 100))

conn.close()
