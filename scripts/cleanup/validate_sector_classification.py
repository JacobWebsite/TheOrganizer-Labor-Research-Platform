import os
"""
Sector Classification Cross-Validation (Read-Only)
Identifies federal, state, and local government employers in f7_employers_deduped
that are NOT currently flagged with exclude_from_counts.

Checks:
  1. Federal employers by NAICS (92xxxx = Public Administration)
  2. Federal employers by name pattern
  3. State/local government by name pattern
  4. Already-excluded summary
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("SECTOR CLASSIFICATION CROSS-VALIDATION (READ-ONLY)")
print("=" * 70)

cur.execute("SELECT COUNT(*) as total FROM f7_employers_deduped")
total = cur.fetchone()['total']
print(f"Total f7_employers_deduped records: {total:,}")

cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
""")
r = cur.fetchone()
print(f"Currently excluded: {r['cnt']:,} employers, {r['workers']:,} workers")

cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
r = cur.fetchone()
print(f"Currently counted:  {r['cnt']:,} employers, {r['workers']:,} workers")
print(f"BLS private sector benchmark: 7,200,000")
print(f"Current coverage: {r['workers']/7200000*100:.1f}%")

# ============================================================================
# CHECK 1: Federal Employers by NAICS (92xxxx = Public Administration)
# ============================================================================
print("\n" + "=" * 70)
print("CHECK 1: Federal Employers by NAICS (92xxxx = Public Administration)")
print("=" * 70)

cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE naics LIKE '92%%' AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
naics92_count = r['cnt']
naics92_workers = r['workers']
print(f"\nFound: {naics92_count:,} employers with NAICS 92xx NOT excluded")
print(f"Worker impact: {naics92_workers:,}")

if naics92_count > 0:
    print("\nTop 50 by unit size:")
    print(f"  {'Name':<50} {'City':<15} {'ST':<4} {'NAICS':<8} {'Workers':>8}")
    print(f"  {'-'*50} {'-'*15} {'-'*4} {'-'*8} {'-'*8}")
    cur.execute("""
        SELECT employer_name, city, state, naics, latest_unit_size
        FROM f7_employers_deduped
        WHERE naics LIKE '92%%' AND exclude_from_counts = FALSE
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 50
    """)
    for r in cur.fetchall():
        name = (r['employer_name'] or '')[:50]
        city = (r['city'] or '')[:15]
        st = r['state'] or ''
        naics = r['naics'] or ''
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<50} {city:<15} {st:<4} {naics:<8} {workers:>8,}")

# ============================================================================
# CHECK 2: Federal Employers by Name Pattern
# ============================================================================
print("\n" + "=" * 70)
print("CHECK 2: Federal Employers by Name Pattern (not already excluded)")
print("=" * 70)

FEDERAL_PATTERNS = """
    employer_name ILIKE '%%department of%%'
    OR employer_name ILIKE '%%u.s. %%'
    OR employer_name ILIKE '%%united states%%'
    OR employer_name ILIKE '%%federal%%'
    OR employer_name ILIKE '%%veterans affair%%'
    OR employer_name ILIKE '%%army %%'
    OR employer_name ILIKE '%%navy %%'
    OR employer_name ILIKE '%%air force%%'
    OR employer_name ILIKE '%%coast guard%%'
    OR employer_name ILIKE '%%homeland security%%'
    OR employer_name ILIKE '%%bureau of%%'
    OR employer_name ILIKE '%%national guard%%'
    OR employer_name ILIKE '%%social security admin%%'
    OR employer_name ILIKE '%%internal revenue%%'
    OR employer_name ILIKE 'usps%%'
    OR employer_name ILIKE '%%postal service%%'
    OR employer_name ILIKE '%%v.a. %%'
    OR employer_name ILIKE '%%va medical%%'
    OR employer_name ILIKE '%%va hospital%%'
"""

cur.execute(f"""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE AND ({FEDERAL_PATTERNS})
""")
r = cur.fetchone()
fed_name_count = r['cnt']
fed_name_workers = r['workers']
print(f"\nFound: {fed_name_count:,} employers matching federal name patterns")
print(f"Worker impact: {fed_name_workers:,}")

if fed_name_count > 0:
    print("\nTop 50 by unit size:")
    print(f"  {'Name':<55} {'City':<15} {'ST':<4} {'Workers':>8}")
    print(f"  {'-'*55} {'-'*15} {'-'*4} {'-'*8}")
    cur.execute(f"""
        SELECT employer_name, city, state, latest_unit_size, naics
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE AND ({FEDERAL_PATTERNS})
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 50
    """)
    for r in cur.fetchall():
        name = (r['employer_name'] or '')[:55]
        city = (r['city'] or '')[:15]
        st = r['state'] or ''
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<55} {city:<15} {st:<4} {workers:>8,}")

    # Show which patterns matched
    print("\n  Pattern breakdown:")
    pattern_labels = [
        ("department of",    "employer_name ILIKE '%%department of%%'"),
        ("u.s.",             "employer_name ILIKE '%%u.s. %%'"),
        ("united states",    "employer_name ILIKE '%%united states%%'"),
        ("federal",          "employer_name ILIKE '%%federal%%'"),
        ("veterans affair",  "employer_name ILIKE '%%veterans affair%%'"),
        ("army",             "employer_name ILIKE '%%army %%'"),
        ("navy",             "employer_name ILIKE '%%navy %%'"),
        ("air force",        "employer_name ILIKE '%%air force%%'"),
        ("coast guard",      "employer_name ILIKE '%%coast guard%%'"),
        ("homeland security","employer_name ILIKE '%%homeland security%%'"),
        ("bureau of",        "employer_name ILIKE '%%bureau of%%'"),
        ("national guard",   "employer_name ILIKE '%%national guard%%'"),
        ("social security",  "employer_name ILIKE '%%social security admin%%'"),
        ("internal revenue", "employer_name ILIKE '%%internal revenue%%'"),
        ("usps",             "employer_name ILIKE 'usps%%'"),
        ("postal service",   "employer_name ILIKE '%%postal service%%'"),
        ("v.a.",             "employer_name ILIKE '%%v.a. %%'"),
        ("va medical",       "employer_name ILIKE '%%va medical%%'"),
        ("va hospital",      "employer_name ILIKE '%%va hospital%%'"),
    ]
    for label, pattern in pattern_labels:
        cur.execute(f"""
            SELECT COUNT(*) as cnt FROM f7_employers_deduped
            WHERE exclude_from_counts = FALSE AND ({pattern})
        """)
        cnt = cur.fetchone()['cnt']
        if cnt > 0:
            print(f"    {label:<25} -> {cnt:,} matches")

# ============================================================================
# CHECK 3: State/Local Government by Name Pattern
# ============================================================================
print("\n" + "=" * 70)
print("CHECK 3: State/Local Government by Name Pattern")
print("=" * 70)

# Unambiguous government patterns
GOVT_UNAMBIGUOUS = """
    employer_name ILIKE 'county of %%'
    OR employer_name ILIKE '%%school district%%'
    OR employer_name ILIKE '%%board of education%%'
    OR employer_name ILIKE 'state of %%'
    OR employer_name ILIKE '%%township of %%'
    OR employer_name ILIKE '%%municipality of %%'
    OR employer_name ILIKE '%%water authority%%'
    OR employer_name ILIKE '%%transit authority%%'
    OR employer_name ILIKE '%%housing authority%%'
    OR employer_name ILIKE '%%sanitation%%district%%'
    OR employer_name ILIKE '%%fire district%%'
    OR employer_name ILIKE '%%port authority%%'
"""

# "city of" is tricky - "City of Hope" is a hospital, "City Market" is private
# We handle it separately with false-positive filtering
CITY_OF_PATTERN = "employer_name ILIKE 'city of %%'"

# Other ambiguous patterns that need manual review
GOVT_AMBIGUOUS = """
    employer_name ILIKE '%% county'
    OR employer_name ILIKE '%%township%%'
    OR employer_name ILIKE '%%fire department%%'
    OR employer_name ILIKE '%%police department%%'
"""

# --- Unambiguous ---
cur.execute(f"""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE AND ({GOVT_UNAMBIGUOUS})
""")
r = cur.fetchone()
govt_unambig_count = r['cnt']
govt_unambig_workers = r['workers']
print(f"\nUnambiguous govt patterns: {govt_unambig_count:,} employers, {govt_unambig_workers:,} workers")

if govt_unambig_count > 0:
    print("\nTop 30 unambiguous govt employers:")
    print(f"  {'Name':<55} {'City':<15} {'ST':<4} {'Workers':>8}")
    print(f"  {'-'*55} {'-'*15} {'-'*4} {'-'*8}")
    cur.execute(f"""
        SELECT employer_name, city, state, latest_unit_size
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE AND ({GOVT_UNAMBIGUOUS})
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 30
    """)
    for r in cur.fetchall():
        name = (r['employer_name'] or '')[:55]
        city = (r['city'] or '')[:15]
        st = r['state'] or ''
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<55} {city:<15} {st:<4} {workers:>8,}")

# --- "city of" with false-positive filter ---
# Known false positives for "city of" pattern
CITY_OF_FALSE_POSITIVES = [
    'city of hope',
    'city market',
    'city national',
    'city brewing',
    'city carton',
    'city electric',
    'city furniture',
    'city plating',
    'city wide',
    'city line',
    'city club',
    'city press',
    'city forge',
    'city paper',
]

fp_filter = " AND ".join(
    [f"employer_name NOT ILIKE '{fp}%%'" for fp in CITY_OF_FALSE_POSITIVES]
)

cur.execute(f"""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND {CITY_OF_PATTERN}
      AND {fp_filter}
""")
r = cur.fetchone()
city_of_count = r['cnt']
city_of_workers = r['workers']
print(f"\n'City of ...' (filtered): {city_of_count:,} employers, {city_of_workers:,} workers")

if city_of_count > 0:
    print("\nTop 20 'city of' employers:")
    print(f"  {'Name':<55} {'City':<15} {'ST':<4} {'Workers':>8}")
    print(f"  {'-'*55} {'-'*15} {'-'*4} {'-'*8}")
    cur.execute(f"""
        SELECT employer_name, city, state, latest_unit_size
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND {CITY_OF_PATTERN}
          AND {fp_filter}
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 20
    """)
    for r in cur.fetchall():
        name = (r['employer_name'] or '')[:55]
        city = (r['city'] or '')[:15]
        st = r['state'] or ''
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<55} {city:<15} {st:<4} {workers:>8,}")

# Show "city of" false positives caught by filter
cur.execute(f"""
    SELECT employer_name, city, state, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND {CITY_OF_PATTERN}
      AND NOT ({fp_filter})
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
fp_rows = cur.fetchall()
if fp_rows:
    print(f"\nFiltered 'city of' false positives ({len(fp_rows)} shown):")
    for r in fp_rows:
        name = (r['employer_name'] or '')[:55]
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<55} {workers:>8,} workers")

# --- Ambiguous patterns ---
cur.execute(f"""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE AND ({GOVT_AMBIGUOUS})
      AND NOT ({GOVT_UNAMBIGUOUS})
      AND NOT ({CITY_OF_PATTERN})
""")
r = cur.fetchone()
govt_ambig_count = r['cnt']
govt_ambig_workers = r['workers']
print(f"\nAmbiguous govt-like patterns: {govt_ambig_count:,} employers, {govt_ambig_workers:,} workers")
print("  (These need manual review - could be private sector)")

if govt_ambig_count > 0:
    print("\nTop 30 ambiguous employers:")
    print(f"  {'Name':<55} {'City':<15} {'ST':<4} {'Workers':>8}")
    print(f"  {'-'*55} {'-'*15} {'-'*4} {'-'*8}")
    cur.execute(f"""
        SELECT employer_name, city, state, latest_unit_size
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE AND ({GOVT_AMBIGUOUS})
          AND NOT ({GOVT_UNAMBIGUOUS})
          AND NOT ({CITY_OF_PATTERN})
        ORDER BY latest_unit_size DESC NULLS LAST
        LIMIT 30
    """)
    for r in cur.fetchall():
        name = (r['employer_name'] or '')[:55]
        city = (r['city'] or '')[:15]
        st = r['state'] or ''
        workers = r['latest_unit_size'] or 0
        print(f"  {name:<55} {city:<15} {st:<4} {workers:>8,}")

# ============================================================================
# CHECK 4: Already-Excluded Summary
# ============================================================================
print("\n" + "=" * 70)
print("CHECK 4: Already-Excluded Summary")
print("=" * 70)

cur.execute("""
    SELECT COALESCE(exclude_reason, '(none/included)') as reason,
           COUNT(*) as employers,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
    GROUP BY exclude_reason
    ORDER BY COALESCE(SUM(latest_unit_size), 0) DESC
""")
rows = cur.fetchall()
print(f"\n  {'Reason':<30} {'Employers':>10} {'Workers':>12}")
print(f"  {'-'*30} {'-'*10} {'-'*12}")
total_excl_emp = 0
total_excl_wrk = 0
for r in rows:
    print(f"  {r['reason']:<30} {r['employers']:>10,} {r['workers']:>12,}")
    total_excl_emp += r['employers']
    total_excl_wrk += r['workers']
print(f"  {'TOTAL':<30} {total_excl_emp:>10,} {total_excl_wrk:>12,}")

# Check overlap: how many of the already-excluded are federal by name?
cur.execute(f"""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
      AND exclude_reason = 'FEDERAL_EMPLOYER'
""")
r = cur.fetchone()
print(f"\n  Already flagged as FEDERAL_EMPLOYER: {r['cnt']:,}")

# ============================================================================
# SUMMARY TABLE
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Overlap: employers found by multiple checks
cur.execute(f"""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND naics LIKE '92%%'
      AND ({FEDERAL_PATTERNS})
""")
naics_fed_overlap = cur.fetchone()['cnt']

print(f"\n  {'Check':<45} {'Found':>7} {'Workers':>10}")
print(f"  {'-'*45} {'-'*7} {'-'*10}")
print(f"  {'1. NAICS 92 (Public Admin) not excluded':<45} {naics92_count:>7,} {naics92_workers:>10,}")
print(f"  {'2. Federal name patterns not excluded':<45} {fed_name_count:>7,} {fed_name_workers:>10,}")
print(f"  {'   (overlap: NAICS 92 + federal name)':<45} {naics_fed_overlap:>7,} {'':>10}")
print(f"  {'3a. Unambiguous state/local govt':<45} {govt_unambig_count:>7,} {govt_unambig_workers:>10,}")
print(f"  {'3b. City of (filtered)':<45} {city_of_count:>7,} {city_of_workers:>10,}")
print(f"  {'3c. Ambiguous govt-like (needs review)':<45} {govt_ambig_count:>7,} {govt_ambig_workers:>10,}")
print(f"  {'4. Already excluded (all reasons)':<45} {total_excl_emp:>7,} {total_excl_wrk:>10,}")

# Deduplicated new findings (union of checks 1-3, minus already excluded)
cur.execute(f"""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (
        naics LIKE '92%%'
        OR ({FEDERAL_PATTERNS})
        OR ({GOVT_UNAMBIGUOUS})
        OR ({CITY_OF_PATTERN} AND {fp_filter})
      )
""")
r = cur.fetchone()
total_new = r['cnt']
total_new_workers = r['workers']

print(f"\n  Deduplicated new findings (checks 1+2+3a+3b): {total_new:,} employers, {total_new_workers:,} workers")
print(f"  Ambiguous (needs manual review, check 3c):    {govt_ambig_count:,} employers, {govt_ambig_workers:,} workers")

cur.execute("""
    SELECT COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
current_counted = cur.fetchone()['workers']
after_counted = current_counted - total_new_workers

print(f"\n  BLS private sector benchmark:  7,200,000")
print(f"  Currently counted workers:     {current_counted:>10,} ({current_counted/7200000*100:.1f}%)")
print(f"  After excluding new findings:  {after_counted:>10,} ({after_counted/7200000*100:.1f}%)")
print(f"  Worker reduction:              {total_new_workers:>10,}")

print("\n" + "=" * 70)
print("VALIDATION COMPLETE (read-only, no changes made)")
print("=" * 70)

cur.close()
conn.close()
