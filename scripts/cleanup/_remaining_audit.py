"""
Remaining Data Quality Audit for Labor Data Project
Checks 8 areas of concern in f7_employers_deduped and related tables.
All output is ASCII-safe (no Unicode arrows or special chars).

Usage:
    py scripts/cleanup/_remaining_audit.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import os

from db_config import get_connection
conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

DIVIDER = "=" * 80


def fmt(n):
    """Format number with commas."""
    if n is None:
        return "NULL"
    return "{:,}".format(n)


# ============================================================================
# BASELINE: Current state of f7_employers_deduped
# ============================================================================
print(DIVIDER)
print("REMAINING DATA QUALITY AUDIT")
print(DIVIDER)

cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END) as counted,
           COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded,
           COALESCE(SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END), 0) as counted_workers,
           COALESCE(SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END), 0) as excluded_workers
    FROM f7_employers_deduped
""")
base = cur.fetchone()
print("\nBaseline:")
print("  Total records:    %s" % fmt(base['total']))
print("  Counted:          %s employers, %s workers" % (fmt(base['counted']), fmt(base['counted_workers'])))
print("  Excluded:         %s employers, %s workers" % (fmt(base['excluded']), fmt(base['excluded_workers'])))
print("  BLS benchmark:    7,200,000 private sector")
print("  Coverage:         %.1f%%" % (base['counted_workers'] / 7200000 * 100))


# ============================================================================
# AUDIT 1: Ambiguous Government Employers (sector_review.csv)
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 1: AMBIGUOUS GOVERNMENT EMPLOYERS (sector_review.csv)")
print(DIVIDER)

csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        'data', 'sector_review.csv')

if os.path.exists(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total_csv = len(rows)
    reviewed = sum(1 for r in rows if r.get('review_action', '').strip())
    unreviewed = total_csv - reviewed
    print("  Total in CSV:     %d" % total_csv)
    print("  Reviewed:         %d" % reviewed)
    print("  Unreviewed:       %d" % unreviewed)

    # Check which are still in DB as counted
    csv_ids = [r['employer_id'] for r in rows]

    # Batch check - are they still counted?
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size,
               exclude_from_counts, exclude_reason, naics
        FROM f7_employers_deduped
        WHERE employer_id = ANY(%s)
    """, (csv_ids,))
    db_rows = cur.fetchall()

    still_counted = [r for r in db_rows if not r['exclude_from_counts']]
    already_excluded = [r for r in db_rows if r['exclude_from_counts']]

    print("  Still counted:    %d (workers: %s)" % (
        len(still_counted),
        fmt(sum(r['latest_unit_size'] or 0 for r in still_counted))))
    print("  Already excluded: %d (workers: %s)" % (
        len(already_excluded),
        fmt(sum(r['latest_unit_size'] or 0 for r in already_excluded))))

    # Classify by name patterns
    govt_keywords = [
        'city of', 'county of', 'state of', 'town of', 'village of',
        'borough of', 'township of', 'department of', 'dept of',
        'u.s.', 'united states', 'federal', 'bureau of',
        'navy', 'army', 'air force', 'marine corps',
        'school district', 'board of education', 'public school',
        'fire department', 'police department', 'sheriff',
        'district court', 'water authority', 'housing authority',
        'transit authority', 'port authority'
    ]
    private_keywords = [
        'inc', 'llc', 'corp', 'company', 'co.', 'ltd',
        'hotel', 'restaurant', 'store', 'shop', 'market',
        'hospital', 'medical center', 'clinic',
        'university', 'college'  # private ones
    ]

    clearly_govt = 0
    clearly_private = 0
    ambiguous = 0
    govt_workers = 0
    private_workers = 0
    ambig_workers = 0

    for r in still_counted:
        name_lower = (r['employer_name'] or '').lower()
        is_govt = any(kw in name_lower for kw in govt_keywords)
        is_private = any(kw in name_lower for kw in private_keywords)
        workers = r['latest_unit_size'] or 0

        if is_govt and not is_private:
            clearly_govt += 1
            govt_workers += workers
        elif is_private and not is_govt:
            clearly_private += 1
            private_workers += workers
        else:
            ambiguous += 1
            ambig_workers += workers

    print("\n  Classification of still-counted NAICS-92 employers:")
    print("    Clearly government:  %d (%s workers)" % (clearly_govt, fmt(govt_workers)))
    print("    Clearly private:     %d (%s workers)" % (clearly_private, fmt(private_workers)))
    print("    Ambiguous:           %d (%s workers)" % (ambiguous, fmt(ambig_workers)))

    # Top 15 still-counted by worker count
    still_counted.sort(key=lambda r: r['latest_unit_size'] or 0, reverse=True)
    print("\n  Top 15 still-counted NAICS-92 employers:")
    print("  %-55s %-15s %-4s %10s" % ("Name", "City", "ST", "Workers"))
    print("  " + "-" * 88)
    for r in still_counted[:15]:
        print("  %-55s %-15s %-4s %10s" % (
            (r['employer_name'] or '')[:55],
            (r['city'] or '')[:15],
            r['state'] or '',
            fmt(r['latest_unit_size'])))
else:
    print("  WARNING: sector_review.csv not found at %s" % csv_path)


# ============================================================================
# AUDIT 2: Records Without NAICS Codes - Enrichment Potential
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 2: RECORDS WITHOUT NAICS CODES")
print(DIVIDER)

cur.execute("""
    SELECT naics_source, COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
print("\n  NAICS source distribution (counted only):")
for r in cur.fetchall():
    print("    %-12s %6s employers  %10s workers" % (
        r['naics_source'] or 'NULL', fmt(r['cnt']), fmt(r['workers'])))

# How many have no NAICS?
cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE (naics IS NULL OR naics = '' OR naics_source = 'NONE')
      AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
no_naics = r['cnt']
no_naics_workers = r['workers']
print("\n  No NAICS (counted):  %s employers, %s workers" % (fmt(no_naics), fmt(no_naics_workers)))

# Can any be enriched from OSHA?
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as enrichable
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
    JOIN osha_establishments o ON m.establishment_id = o.establishment_id
    WHERE (f.naics IS NULL OR f.naics = '' OR f.naics_source = 'NONE')
      AND f.exclude_from_counts = FALSE
      AND o.naics_code IS NOT NULL
      AND TRIM(CAST(o.naics_code AS TEXT)) != ''
""")
r = cur.fetchone()
print("  Enrichable from OSHA: %s" % fmt(r['enrichable']))

# Can any be enriched from NLRB participants (matched_employer_id)?
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as enrichable
    FROM f7_employers_deduped f
    JOIN nlrb_participants p ON f.employer_id = p.matched_employer_id
    WHERE (f.naics IS NULL OR f.naics = '' OR f.naics_source = 'NONE')
      AND f.exclude_from_counts = FALSE
      AND p.matched_employer_id IS NOT NULL
""")
r = cur.fetchone()
print("  Enrichable from NLRB (matched employers, no NAICS directly but linkable): %s" % fmt(r['enrichable']))

# Can any be enriched from union's typical NAICS?
cur.execute("""
    WITH union_dominant_naics AS (
        SELECT latest_union_fnum,
               naics,
               COUNT(*) as cnt,
               ROW_NUMBER() OVER (PARTITION BY latest_union_fnum ORDER BY COUNT(*) DESC) as rn
        FROM f7_employers_deduped
        WHERE naics IS NOT NULL AND naics != '' AND naics_source != 'NONE'
          AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, naics
    )
    SELECT COUNT(DISTINCT f.employer_id) as enrichable
    FROM f7_employers_deduped f
    JOIN union_dominant_naics u ON f.latest_union_fnum = u.latest_union_fnum AND u.rn = 1
    WHERE (f.naics IS NULL OR f.naics = '' OR f.naics_source = 'NONE')
      AND f.exclude_from_counts = FALSE
      AND u.cnt >= 5
""")
r = cur.fetchone()
print("  Enrichable from union's dominant NAICS (>=5 examples): %s" % fmt(r['enrichable']))

# Breakdown of no-NAICS by size bucket
cur.execute("""
    SELECT CASE
        WHEN latest_unit_size >= 1000 THEN 'A) >= 1000'
        WHEN latest_unit_size >= 100 THEN 'B) 100-999'
        WHEN latest_unit_size >= 10 THEN 'C) 10-99'
        WHEN latest_unit_size > 0 THEN 'D) 1-9'
        ELSE 'E) 0/NULL'
    END as size_bucket,
    COUNT(*) as cnt,
    COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE (naics IS NULL OR naics = '' OR naics_source = 'NONE')
      AND exclude_from_counts = FALSE
    GROUP BY 1
    ORDER BY 1
""")
print("\n  No-NAICS by size bucket:")
for r in cur.fetchall():
    print("    %-15s %6s employers  %10s workers" % (
        r['size_bucket'], fmt(r['cnt']), fmt(r['workers'])))


# ============================================================================
# AUDIT 3: Missing Union Linkage (latest_union_fnum IS NULL)
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 3: MISSING UNION LINKAGE (latest_union_fnum IS NULL)")
print(DIVIDER)

cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
      AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\n  Missing union fnum (counted): %s employers, %s workers" % (fmt(r['cnt']), fmt(r['workers'])))

# Do they have union names?
cur.execute("""
    SELECT
        COUNT(CASE WHEN latest_union_name IS NOT NULL AND latest_union_name != '' THEN 1 END) as has_name,
        COUNT(CASE WHEN latest_union_name IS NULL OR latest_union_name = '' THEN 1 END) as no_name
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
      AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("  Has union name but no fnum: %s" % fmt(r['has_name']))
print("  No union name and no fnum:  %s" % fmt(r['no_name']))

# What union names appear?
cur.execute("""
    SELECT latest_union_name, COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
      AND exclude_from_counts = FALSE
      AND latest_union_name IS NOT NULL
      AND latest_union_name != ''
    GROUP BY latest_union_name
    ORDER BY COUNT(*) DESC
    LIMIT 20
""")
rows = cur.fetchall()
if rows:
    print("\n  Top 20 union names with no fnum:")
    print("  %-55s %6s %10s" % ("Union Name", "Count", "Workers"))
    print("  " + "-" * 75)
    for r in rows:
        print("  %-55s %6s %10s" % (
            (r['latest_union_name'] or '')[:55],
            fmt(r['cnt']),
            fmt(r['workers'])))

# Are these from specific exclude_reason categories?
cur.execute("""
    SELECT exclude_reason, COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
    GROUP BY exclude_reason
    ORDER BY COUNT(*) DESC
""")
print("\n  All NULL-fnum records by exclude_reason:")
for r in cur.fetchall():
    print("    %-30s %6s employers  %10s workers" % (
        r['exclude_reason'] or 'NOT_EXCLUDED', fmt(r['cnt']), fmt(r['workers'])))


# ============================================================================
# AUDIT 4: Un-Geocoded Records (Missing Lat/Lon)
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 4: UN-GEOCODED RECORDS")
print(DIVIDER)

# Check what geocoding columns exist
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
      AND column_name IN ('latitude', 'longitude', 'lat', 'lon', 'geocoded',
                          'address', 'street', 'street_address')
    ORDER BY column_name
""")
geo_cols = [r['column_name'] for r in cur.fetchall()]
print("\n  Geocoding-related columns found: %s" % (', '.join(geo_cols) if geo_cols else 'NONE'))

# Check address columns
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
      AND (column_name LIKE '%%addr%%' OR column_name LIKE '%%street%%'
         OR column_name LIKE '%%zip%%' OR column_name LIKE '%%city%%'
         OR column_name LIKE '%%state%%')
    ORDER BY column_name
""")
addr_cols = [r['column_name'] for r in cur.fetchall()]
if addr_cols:
    print("  Address-related columns: %s" % ', '.join(addr_cols))
else:
    print("  Address-related columns: NONE")

# Check how many have city/state
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN city IS NOT NULL AND city != '' THEN 1 END) as has_city,
        COUNT(CASE WHEN state IS NOT NULL AND state != '' THEN 1 END) as has_state,
        COUNT(CASE WHEN city IS NOT NULL AND city != '' AND state IS NOT NULL AND state != '' THEN 1 END) as has_both
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\n  Address completeness (counted records):")
print("    Total:         %s" % fmt(r['total']))
print("    Has city:      %s" % fmt(r['has_city']))
print("    Has state:     %s" % fmt(r['has_state']))
print("    Has both:      %s" % fmt(r['has_both']))
print("    Missing city:  %s" % fmt(r['total'] - r['has_city']))
print("    Missing state: %s" % fmt(r['total'] - r['has_state']))

# Check if latitude/longitude exist
if 'latitude' in geo_cols or 'lat' in geo_cols:
    lat_col = 'latitude' if 'latitude' in geo_cols else 'lat'
    lon_col = 'longitude' if 'longitude' in geo_cols else 'lon'
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN %s IS NOT NULL THEN 1 END) as geocoded,
            COUNT(CASE WHEN %s IS NULL THEN 1 END) as not_geocoded
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
    """ % (lat_col, lat_col))
    r = cur.fetchone()
    print("\n  Geocoding status:")
    print("    Geocoded:     %s" % fmt(r['geocoded']))
    print("    Not geocoded: %s" % fmt(r['not_geocoded']))

    # Of the non-geocoded, how many have street addresses?
    cur.execute("""
        SELECT
            COUNT(*) as total_ungeo,
            COUNT(CASE WHEN street IS NOT NULL AND TRIM(street) != '' THEN 1 END) as has_street,
            COUNT(CASE WHEN city IS NOT NULL AND TRIM(city) != '' THEN 1 END) as has_city,
            COUNT(CASE WHEN zip IS NOT NULL AND TRIM(zip) != '' THEN 1 END) as has_zip,
            COUNT(CASE WHEN street IS NOT NULL AND TRIM(street) != ''
                         AND city IS NOT NULL AND TRIM(city) != ''
                         AND state IS NOT NULL AND TRIM(state) != '' THEN 1 END) as has_full_addr
        FROM f7_employers_deduped
        WHERE exclude_from_counts = FALSE
          AND %s IS NULL
    """ % lat_col)
    r2 = cur.fetchone()
    print("\n  Non-geocoded address availability:")
    print("    Total not geocoded: %s" % fmt(r2['total_ungeo']))
    print("    Has street addr:    %s" % fmt(r2['has_street']))
    print("    Has city:           %s" % fmt(r2['has_city']))
    print("    Has ZIP:            %s" % fmt(r2['has_zip']))
    print("    Has full addr:      %s (street+city+state)" % fmt(r2['has_full_addr']))
else:
    print("\n  No lat/lon columns found - checking mv_employer_search for geocoding")
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'mv_employer_search'
          AND (column_name LIKE '%%lat%%' OR column_name LIKE '%%lon%%'
               OR column_name LIKE '%%geocod%%')
    """)
    mv_geo = [r['column_name'] for r in cur.fetchall()]
    print("  mv_employer_search geo columns: %s" % (', '.join(mv_geo) if mv_geo else 'NONE'))

# States with most missing cities
cur.execute("""
    SELECT state, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE (city IS NULL OR city = '')
      AND exclude_from_counts = FALSE
    GROUP BY state
    ORDER BY COUNT(*) DESC
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    print("\n  Top 10 states with missing city:")
    for r in rows:
        print("    %-5s %s records" % (r['state'] or 'NULL', fmt(r['cnt'])))


# ============================================================================
# AUDIT 5: OUTLIER_WORKER_COUNT Exclusions
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 5: OUTLIER_WORKER_COUNT EXCLUSIONS")
print(DIVIDER)

cur.execute("""
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_reason = 'OUTLIER_WORKER_COUNT'
""")
r = cur.fetchone()
print("\n  Total OUTLIER_WORKER_COUNT: %s employers, %s workers" % (fmt(r['cnt']), fmt(r['workers'])))

cur.execute("""
    SELECT employer_name, city, state, latest_unit_size,
           latest_union_name, latest_union_fnum, naics
    FROM f7_employers_deduped
    WHERE exclude_reason = 'OUTLIER_WORKER_COUNT'
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 10
""")
rows = cur.fetchall()
print("\n  Top 10 OUTLIER_WORKER_COUNT by size:")
print("  %-45s %-12s %-4s %10s %-30s %-6s" % ("Employer", "City", "ST", "Workers", "Union", "NAICS"))
print("  " + "-" * 115)
for r in rows:
    print("  %-45s %-12s %-4s %10s %-30s %-6s" % (
        (r['employer_name'] or '')[:45],
        (r['city'] or '')[:12],
        r['state'] or '',
        fmt(r['latest_unit_size']),
        (r['latest_union_name'] or '')[:30],
        r['naics'] or ''))

# Check what threshold was used
cur.execute("""
    SELECT MIN(latest_unit_size) as min_size, MAX(latest_unit_size) as max_size,
           AVG(latest_unit_size) as avg_size,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size) as median_size
    FROM f7_employers_deduped
    WHERE exclude_reason = 'OUTLIER_WORKER_COUNT'
""")
r = cur.fetchone()
print("\n  Size stats for outliers:")
print("    Min:    %s" % fmt(int(r['min_size'] or 0)))
print("    Max:    %s" % fmt(int(r['max_size'] or 0)))
print("    Avg:    %s" % fmt(int(r['avg_size'] or 0)))
print("    Median: %s" % fmt(int(r['median_size'] or 0)))

# Are any of these legitimate large employers (like UPS, USPS)?
cur.execute("""
    SELECT employer_name, latest_unit_size, latest_union_name
    FROM f7_employers_deduped
    WHERE exclude_reason = 'OUTLIER_WORKER_COUNT'
      AND latest_unit_size >= 10000
    ORDER BY latest_unit_size DESC
""")
rows = cur.fetchall()
if rows:
    print("\n  Large outliers (>=10K workers) - potentially legitimate:")
    for r in rows:
        print("    %s (%s workers) - %s" % (
            r['employer_name'], fmt(r['latest_unit_size']), r['latest_union_name']))


# ============================================================================
# AUDIT 6: REPEATED_WORKER_COUNT / DUPLICATE_WORKER_COUNT Exclusions
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 6: REPEATED/DUPLICATE WORKER_COUNT EXCLUSIONS")
print(DIVIDER)

cur.execute("""
    SELECT exclude_reason, COUNT(*) as cnt,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    WHERE exclude_reason LIKE '%%WORKER_COUNT%%'
       OR exclude_reason LIKE '%%DUPLICATE%%'
       OR exclude_reason LIKE '%%SIGNATORY%%'
       OR exclude_reason LIKE '%%REPEATED%%'
    GROUP BY exclude_reason
    ORDER BY COUNT(*) DESC
""")
rows = cur.fetchall()
print("\n  Worker-count related exclusions:")
for r in rows:
    print("    %-35s %6s employers  %12s workers" % (
        r['exclude_reason'], fmt(r['cnt']), fmt(r['workers'])))

# Show the logic: same union + same size = repeated
cur.execute("""
    SELECT exclude_reason, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE exclude_from_counts = TRUE
    GROUP BY exclude_reason
    ORDER BY COUNT(*) DESC
""")
print("\n  All exclusion reasons:")
for r in cur.fetchall():
    print("    %-35s %6s" % (r['exclude_reason'] or 'NO_REASON', fmt(r['cnt'])))

# Show some DUPLICATE_WORKER_COUNT examples
cur.execute("""
    SELECT employer_name, city, state, latest_unit_size,
           latest_union_name, latest_union_fnum
    FROM f7_employers_deduped
    WHERE exclude_reason IN ('DUPLICATE_WORKER_COUNT', 'REPEATED_WORKER_COUNT')
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
rows = cur.fetchall()
if rows:
    print("\n  Top 15 DUPLICATE/REPEATED by size:")
    print("  %-45s %-12s %-4s %8s %-30s" % ("Employer", "City", "ST", "Workers", "Union"))
    print("  " + "-" * 105)
    for r in rows:
        print("  %-45s %-12s %-4s %8s %-30s" % (
            (r['employer_name'] or '')[:45],
            (r['city'] or '')[:12],
            r['state'] or '',
            fmt(r['latest_unit_size']),
            (r['latest_union_name'] or '')[:30]))

# Show a specific group example - same employer counted multiple times by same union
cur.execute("""
    WITH dup_groups AS (
        SELECT latest_union_fnum, employer_name, city, state,
               COUNT(*) as filing_count,
               SUM(latest_unit_size) as total_workers,
               (ARRAY_AGG(DISTINCT exclude_reason))[1:3] as reasons,
               (ARRAY_AGG(DISTINCT CAST(exclude_from_counts AS TEXT)))[1:2] as statuses
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, employer_name, city, state
        HAVING COUNT(*) > 1
    )
    SELECT * FROM dup_groups
    ORDER BY total_workers DESC
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    print("\n  Top 10 duplicate-filing groups (same union + employer + city + state):")
    print("  %-40s %-12s %-4s %5s %10s %s" % ("Employer", "City", "ST", "Files", "Workers", "Reasons"))
    print("  " + "-" * 95)
    for r in rows:
        reasons = [x for x in (r['reasons'] or []) if x]
        print("  %-40s %-12s %-4s %5s %10s %s" % (
            (r['employer_name'] or '')[:40],
            (r['city'] or '')[:12],
            r['state'] or '',
            r['filing_count'],
            fmt(r['total_workers']),
            ', '.join(reasons) if reasons else 'none'))


# ============================================================================
# AUDIT 7: VR Internal Duplicates (79 pairs)
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 7: VR INTERNAL DUPLICATES")
print(DIVIDER)

# Check VR table structure
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'nlrb_voluntary_recognition'
    ORDER BY ordinal_position
""")
vr_cols = [r['column_name'] for r in cur.fetchall()]
print("\n  VR table columns: %s" % ', '.join(vr_cols[:15]))

# Find potential duplicates by employer name + city + state
cur.execute("""
    SELECT LOWER(TRIM(employer_name)) as emp, unit_city, unit_state,
           COUNT(*) as cnt,
           (ARRAY_AGG(vr_case_number))[1:3] as cases,
           (ARRAY_AGG(date_vr_request_received ORDER BY date_vr_request_received))[1:3] as dates,
           (ARRAY_AGG(union_name))[1:2] as unions
    FROM nlrb_voluntary_recognition
    GROUP BY LOWER(TRIM(employer_name)), unit_city, unit_state
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC
    LIMIT 20
""")
rows = cur.fetchall()
total_dup_pairs = 0
cur.execute("""
    SELECT COUNT(*) as pairs FROM (
        SELECT LOWER(TRIM(employer_name)), unit_city, unit_state
        FROM nlrb_voluntary_recognition
        GROUP BY LOWER(TRIM(employer_name)), unit_city, unit_state
        HAVING COUNT(*) > 1
    ) sub
""")
total_dup_pairs = cur.fetchone()['pairs']
print("  Total duplicate groups (same employer+city+state): %d" % total_dup_pairs)

if rows:
    print("\n  Top 20 VR duplicate groups:")
    print("  %-40s %-12s %-4s %5s %-25s" % ("Employer", "City", "ST", "Dupes", "Cases"))
    print("  " + "-" * 90)
    for r in rows:
        cases = [c for c in (r['cases'] or []) if c]
        print("  %-40s %-12s %-4s %5d %-25s" % (
            (r['emp'] or '')[:40],
            (r['unit_city'] or '')[:12],
            r['unit_state'] or '',
            r['cnt'],
            ', '.join(cases[:2]) if cases else ''))

# Are these same-union or different-union duplicates?
cur.execute("""
    WITH dups AS (
        SELECT LOWER(TRIM(employer_name)) as emp, unit_city, unit_state,
               COUNT(DISTINCT union_name) as union_count,
               COUNT(*) as filing_count
        FROM nlrb_voluntary_recognition
        GROUP BY LOWER(TRIM(employer_name)), unit_city, unit_state
        HAVING COUNT(*) > 1
    )
    SELECT
        COUNT(CASE WHEN union_count = 1 THEN 1 END) as same_union,
        COUNT(CASE WHEN union_count > 1 THEN 1 END) as diff_union
    FROM dups
""")
r = cur.fetchone()
print("\n  Same union (true duplicates):     %s" % fmt(r['same_union']))
print("  Different unions (legit multiples): %s" % fmt(r['diff_union']))

# Impact on mv_employer_search
cur.execute("""
    SELECT COUNT(*) as cnt FROM mv_employer_search WHERE source_type = 'VR'
""")
r = cur.fetchone()
print("  VR records in mv_employer_search: %s" % fmt(r['cnt']))


# ============================================================================
# AUDIT 8: Zero/NULL Unit Size Still Counted
# ============================================================================
print("\n" + DIVIDER)
print("AUDIT 8: ZERO OR NULL UNIT SIZE STILL COUNTED")
print(DIVIDER)

cur.execute("""
    SELECT
        COUNT(CASE WHEN latest_unit_size IS NULL THEN 1 END) as null_size,
        COUNT(CASE WHEN latest_unit_size = 0 THEN 1 END) as zero_size,
        COUNT(CASE WHEN latest_unit_size IS NULL OR latest_unit_size = 0 THEN 1 END) as both
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\n  Counted records with no workers:")
print("    NULL unit_size: %s" % fmt(r['null_size']))
print("    Zero unit_size: %s" % fmt(r['zero_size']))
print("    Total:          %s" % fmt(r['both']))

# What are these? Show some examples
cur.execute("""
    SELECT employer_name, city, state, latest_union_name, latest_union_fnum,
           naics, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (latest_unit_size IS NULL OR latest_unit_size = 0)
    ORDER BY employer_name
    LIMIT 20
""")
rows = cur.fetchall()
if rows:
    print("\n  Sample of 0/NULL size counted employers:")
    print("  %-45s %-12s %-4s %8s %-30s" % ("Employer", "City", "ST", "Size", "Union"))
    print("  " + "-" * 105)
    for r in rows:
        print("  %-45s %-12s %-4s %8s %-30s" % (
            (r['employer_name'] or '')[:45],
            (r['city'] or '')[:12],
            r['state'] or '',
            fmt(r['latest_unit_size']),
            (r['latest_union_name'] or '')[:30]))

# Do they have ANY historical filings with non-zero size?
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as recoverable
    FROM f7_employers_deduped f
    WHERE f.exclude_from_counts = FALSE
      AND (f.latest_unit_size IS NULL OR f.latest_unit_size = 0)
      AND f.latest_union_fnum IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM lm_data lm
          WHERE lm.f_num = CAST(f.latest_union_fnum AS VARCHAR)
            AND lm.members > 0
      )
""")
r = cur.fetchone()
print("\n  Have historical lm_data with members > 0: %s (potentially recoverable)" % fmt(r['recoverable']))

# Could these be defunct/expired?
cur.execute("""
    SELECT potentially_defunct, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND (latest_unit_size IS NULL OR latest_unit_size = 0)
    GROUP BY potentially_defunct
    ORDER BY COUNT(*) DESC
""")
print("\n  Defunct status of 0/NULL size records:")
for r in cur.fetchall():
    print("    potentially_defunct=%s: %s" % (r['potentially_defunct'], fmt(r['cnt'])))


# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + DIVIDER)
print("SUMMARY OF ACTIONABLE ITEMS")
print(DIVIDER)

print("""
  1. GOVT EMPLOYERS: Still-counted NAICS-92 records need review
     - Government pattern matches should likely be excluded
     - Private pattern matches (hospitals, hotels) may be miscoded NAICS

  2. NAICS GAPS: Enrichment opportunities exist from OSHA, NLRB, and
     union-dominant-NAICS inference

  3. UNION LINKAGE: NULL fnum records may indicate data entry issues
     or one-off bargaining units not in OLMS master

  4. GEOCODING: Address completeness determines geocoding potential
     - City+State present -> geocodable at city level
     - Full street address -> geocodable at point level

  5. OUTLIER EXCLUSIONS: Review large employers for legitimacy
     - Some may be real (single large employer bargaining units)
     - Others are multi-employer agreements counted as one

  6. DUPLICATE EXCLUSIONS: Same union + same size pattern catches
     repeated filings; spot-check for false positives

  7. VR DUPLICATES: Same-union duplicates are likely true duplicates;
     different-union duplicates are legitimate

  8. ZERO-SIZE RECORDS: May be defunct contracts or data gaps;
     historical filing data could fill some in
""")

print(DIVIDER)
print("AUDIT COMPLETE")
print(DIVIDER)

cur.close()
conn.close()
