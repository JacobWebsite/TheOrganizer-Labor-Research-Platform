"""
Sector Classification Fix - Flag government employers in f7_employers_deduped
Flags federal, state, and local government employers that should be excluded
from private sector BLS comparison counts.

Usage:
    py scripts/cleanup/fix_sector_classification.py            # dry-run (default)
    py scripts/cleanup/fix_sector_classification.py --apply    # apply changes
"""

import argparse
import csv
import os
import psycopg2
from psycopg2.extras import RealDictCursor

parser = argparse.ArgumentParser(description='Fix sector classification in f7_employers_deduped')
parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry-run)')
args = parser.parse_args()

DRY_RUN = not args.apply

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

mode = "DRY-RUN" if DRY_RUN else "APPLY"
print("=" * 70)
print(f"SECTOR CLASSIFICATION FIX ({mode})")
print("=" * 70)

if DRY_RUN:
    print("  No changes will be made. Use --apply to execute.")
else:
    print("  *** CHANGES WILL BE COMMITTED ***")

# ============================================================================
# Baseline: BLS coverage before changes
# ============================================================================
cur.execute("""
    SELECT COALESCE(SUM(latest_unit_size), 0) as workers,
           COUNT(*) as employers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
before = cur.fetchone()
before_workers = before['workers']
before_employers = before['employers']
print(f"\nBefore: {before_workers:,} counted workers / 7,200,000 BLS = {before_workers/7200000*100:.1f}%")
print(f"        {before_employers:,} counted employers")

# ============================================================================
# FEDERAL PATTERNS - patterns that clearly indicate federal government
# ============================================================================
# We use two criteria combined:
# A) NAICS 92 (Public Administration) + federal name keywords
# B) Strong federal-only name patterns (even without NAICS 92)

# Strong federal patterns - these are unambiguously federal
STRONG_FEDERAL_PATTERNS = """
    employer_name ILIKE '%%department of veteran%%'
    OR employer_name ILIKE '%%veterans affair%%'
    OR employer_name ILIKE '%%va medical%%'
    OR employer_name ILIKE '%%va hospital%%'
    OR employer_name ILIKE '%%v.a. medical%%'
    OR employer_name ILIKE '%%v.a. hospital%%'
    OR employer_name ILIKE 'usps%%'
    OR employer_name ILIKE '%%postal service%%'
    OR employer_name ILIKE '%%u.s. department%%'
    OR employer_name ILIKE '%%u.s. dept%%'
    OR employer_name ILIKE '%%united states department%%'
    OR employer_name ILIKE '%%united states postal%%'
    OR employer_name ILIKE '%%dept of defense%%'
    OR employer_name ILIKE '%%department of defense%%'
    OR employer_name ILIKE '%%department of the army%%'
    OR employer_name ILIKE '%%department of the navy%%'
    OR employer_name ILIKE '%%department of the air force%%'
    OR employer_name ILIKE '%%air force base%%'
    OR employer_name ILIKE '%%coast guard%%'
    OR employer_name ILIKE '%%homeland security%%'
    OR employer_name ILIKE '%%social security admin%%'
    OR employer_name ILIKE '%%internal revenue%%'
    OR employer_name ILIKE '%%national guard%%'
    OR employer_name ILIKE '%%bureau of prisons%%'
    OR employer_name ILIKE '%%bureau of reclamation%%'
    OR employer_name ILIKE '%%bureau of land management%%'
    OR employer_name ILIKE '%%bureau of indian%%'
    OR employer_name ILIKE '%%forest service%%'
    OR employer_name ILIKE '%%u.s. army%%'
    OR employer_name ILIKE '%%u.s. navy%%'
    OR employer_name ILIKE '%%u.s. air force%%'
    OR employer_name ILIKE '%%u.s. marshal%%'
"""

# Moderate federal patterns - federal with NAICS 92 confirmation
MODERATE_FEDERAL_PATTERNS = """
    employer_name ILIKE '%%department of%%'
    OR employer_name ILIKE '%%u.s. %%'
    OR employer_name ILIKE '%%united states%%'
    OR employer_name ILIKE '%%federal%%'
    OR employer_name ILIKE '%%army %%'
    OR employer_name ILIKE '%%navy %%'
    OR employer_name ILIKE '%%air force%%'
    OR employer_name ILIKE '%%bureau of%%'
"""

# ============================================================================
# FIX 1: Flag clearly federal employers (strong patterns)
# ============================================================================
print("\n" + "-" * 70)
print("FIX 1: Flag clearly federal employers (strong name patterns)")
print("-" * 70)

cur.execute(f"""
    SELECT employer_id, employer_name, city, state, latest_unit_size, naics
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND exclude_reason IS NULL
      AND ({STRONG_FEDERAL_PATTERNS})
    ORDER BY latest_unit_size DESC NULLS LAST
""")
strong_federal = cur.fetchall()
strong_fed_workers = sum(r['latest_unit_size'] or 0 for r in strong_federal)
print(f"  Found: {len(strong_federal):,} employers, {strong_fed_workers:,} workers")

if strong_federal:
    print(f"\n  Sample (top 15):")
    for r in strong_federal[:15]:
        name = (r['employer_name'] or '')[:55]
        workers = r['latest_unit_size'] or 0
        print(f"    {name:<55} {r['state'] or '':<4} {workers:>8,}")

if not DRY_RUN and strong_federal:
    ids = [r['employer_id'] for r in strong_federal]
    cur.execute("""
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'FEDERAL_EMPLOYER'
        WHERE employer_id = ANY(%s)
          AND exclude_from_counts = FALSE
          AND exclude_reason IS NULL
    """, (ids,))
    print(f"  -> Updated {cur.rowcount} records")

# ============================================================================
# FIX 2: Flag moderate federal (name pattern + NAICS 92 confirmation)
# ============================================================================
print("\n" + "-" * 70)
print("FIX 2: Flag federal employers (moderate patterns + NAICS 92)")
print("-" * 70)

cur.execute(f"""
    SELECT employer_id, employer_name, city, state, latest_unit_size, naics
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND exclude_reason IS NULL
      AND naics LIKE '92%%'
      AND ({MODERATE_FEDERAL_PATTERNS})
    ORDER BY latest_unit_size DESC NULLS LAST
""")
moderate_federal = cur.fetchall()
# Exclude any already caught by strong patterns
strong_ids = set(r['employer_id'] for r in strong_federal)
moderate_federal = [r for r in moderate_federal if r['employer_id'] not in strong_ids]
mod_fed_workers = sum(r['latest_unit_size'] or 0 for r in moderate_federal)
print(f"  Found: {len(moderate_federal):,} employers (after dedup with Fix 1), {mod_fed_workers:,} workers")

if moderate_federal:
    print(f"\n  Sample (top 15):")
    for r in moderate_federal[:15]:
        name = (r['employer_name'] or '')[:55]
        workers = r['latest_unit_size'] or 0
        print(f"    {name:<55} {r['state'] or '':<4} {workers:>8,}")

if not DRY_RUN and moderate_federal:
    ids = [r['employer_id'] for r in moderate_federal]
    cur.execute("""
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'FEDERAL_EMPLOYER'
        WHERE employer_id = ANY(%s)
          AND exclude_from_counts = FALSE
          AND exclude_reason IS NULL
    """, (ids,))
    print(f"  -> Updated {cur.rowcount} records")

# ============================================================================
# FIX 3: Flag unambiguous state/local government
# ============================================================================
print("\n" + "-" * 70)
print("FIX 3: Flag unambiguous state/local government employers")
print("-" * 70)

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

# "city of" with false-positive filtering
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

# Collect all employer_ids already flagged in fixes 1-2
already_flagged = strong_ids | set(r['employer_id'] for r in moderate_federal)

# Unambiguous patterns
cur.execute(f"""
    SELECT employer_id, employer_name, city, state, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND exclude_reason IS NULL
      AND ({GOVT_UNAMBIGUOUS})
    ORDER BY latest_unit_size DESC NULLS LAST
""")
govt_unambig = [r for r in cur.fetchall() if r['employer_id'] not in already_flagged]

# "City of" filtered
cur.execute(f"""
    SELECT employer_id, employer_name, city, state, latest_unit_size
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND exclude_reason IS NULL
      AND employer_name ILIKE 'city of %%'
      AND {fp_filter}
    ORDER BY latest_unit_size DESC NULLS LAST
""")
city_of_govt = [r for r in cur.fetchall() if r['employer_id'] not in already_flagged]

# Merge and deduplicate
govt_ids_seen = set()
govt_all = []
for r in govt_unambig + city_of_govt:
    if r['employer_id'] not in govt_ids_seen:
        govt_ids_seen.add(r['employer_id'])
        govt_all.append(r)

govt_workers = sum(r['latest_unit_size'] or 0 for r in govt_all)
print(f"  Found: {len(govt_all):,} state/local govt employers, {govt_workers:,} workers")

if govt_all:
    print(f"\n  Sample (top 20):")
    sorted_govt = sorted(govt_all, key=lambda x: x['latest_unit_size'] or 0, reverse=True)
    for r in sorted_govt[:20]:
        name = (r['employer_name'] or '')[:55]
        workers = r['latest_unit_size'] or 0
        print(f"    {name:<55} {r['state'] or '':<4} {workers:>8,}")

if not DRY_RUN and govt_all:
    ids = [r['employer_id'] for r in govt_all]
    cur.execute("""
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'STATE_LOCAL_GOVT'
        WHERE employer_id = ANY(%s)
          AND exclude_from_counts = FALSE
          AND exclude_reason IS NULL
    """, (ids,))
    print(f"  -> Updated {cur.rowcount} records")

# ============================================================================
# FIX 4: Export ambiguous cases to CSV for manual review
# ============================================================================
print("\n" + "-" * 70)
print("FIX 4: Export ambiguous cases to CSV")
print("-" * 70)

GOVT_AMBIGUOUS = """
    employer_name ILIKE '%% county'
    OR employer_name ILIKE '%%township%%'
    OR employer_name ILIKE '%%fire department%%'
    OR employer_name ILIKE '%%police department%%'
"""

# Also include NAICS 92 employers NOT caught by name patterns
all_flagged = already_flagged | govt_ids_seen

cur.execute(f"""
    SELECT employer_id, employer_name, city, state, latest_unit_size, naics
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
      AND exclude_reason IS NULL
      AND (
        ({GOVT_AMBIGUOUS})
        OR (naics LIKE '92%%' AND NOT ({STRONG_FEDERAL_PATTERNS}) AND NOT ({GOVT_UNAMBIGUOUS}))
      )
    ORDER BY latest_unit_size DESC NULLS LAST
""")
ambiguous = [r for r in cur.fetchall() if r['employer_id'] not in all_flagged]
ambig_workers = sum(r['latest_unit_size'] or 0 for r in ambiguous)
print(f"  Found: {len(ambiguous):,} ambiguous employers, {ambig_workers:,} workers")

csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        'data', 'sector_review.csv')
os.makedirs(os.path.dirname(csv_path), exist_ok=True)

with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['employer_id', 'employer_name', 'city', 'state', 'workers', 'naics', 'review_action'])
    for r in ambiguous:
        writer.writerow([
            r['employer_id'],
            r['employer_name'],
            r['city'],
            r['state'],
            r['latest_unit_size'] or 0,
            r['naics'] or '',
            ''  # blank for reviewer to fill in
        ])
print(f"  Wrote {len(ambiguous)} rows to: {csv_path}")

if ambiguous:
    print(f"\n  Top 15 ambiguous employers:")
    for r in ambiguous[:15]:
        name = (r['employer_name'] or '')[:55]
        workers = r['latest_unit_size'] or 0
        print(f"    {name:<55} {r['state'] or '':<4} {workers:>8,}")

# ============================================================================
# COMMIT or ROLLBACK
# ============================================================================
if DRY_RUN:
    conn.rollback()
    print("\n  Rolled back (dry-run mode)")
else:
    conn.commit()
    print("\n  Changes committed")

# ============================================================================
# VERIFICATION: BLS coverage after
# ============================================================================
print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

cur.execute("""
    SELECT COALESCE(SUM(latest_unit_size), 0) as workers,
           COUNT(*) as employers
    FROM f7_employers_deduped
    WHERE exclude_from_counts = FALSE
""")
after = cur.fetchone()
after_workers = after['workers']
after_employers = after['employers']

total_flagged = len(strong_federal) + len(moderate_federal) + len(govt_all)
total_flagged_workers = strong_fed_workers + mod_fed_workers + govt_workers

print(f"\n  {'Metric':<40} {'Before':>12} {'After':>12} {'Change':>12}")
print(f"  {'-'*40} {'-'*12} {'-'*12} {'-'*12}")
print(f"  {'Counted employers':<40} {before_employers:>12,} {after_employers:>12,} {after_employers - before_employers:>+12,}")
print(f"  {'Counted workers':<40} {before_workers:>12,} {after_workers:>12,} {after_workers - before_workers:>+12,}")
print(f"  {'BLS coverage %':<40} {before_workers/7200000*100:>11.1f}% {after_workers/7200000*100:>11.1f}% {(after_workers-before_workers)/7200000*100:>+11.1f}%")

print(f"\n  Flagged in this run:")
print(f"    Federal (strong patterns):   {len(strong_federal):>6,} employers, {strong_fed_workers:>10,} workers")
print(f"    Federal (moderate + NAICS):  {len(moderate_federal):>6,} employers, {mod_fed_workers:>10,} workers")
print(f"    State/local govt:            {len(govt_all):>6,} employers, {govt_workers:>10,} workers")
print(f"    TOTAL flagged:               {total_flagged:>6,} employers, {total_flagged_workers:>10,} workers")
print(f"    Ambiguous (CSV for review):  {len(ambiguous):>6,} employers, {ambig_workers:>10,} workers")

# Exclusion breakdown
print("\n  Current exclusion breakdown:")
cur.execute("""
    SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
           COUNT(*) as employers,
           COALESCE(SUM(latest_unit_size), 0) as workers
    FROM f7_employers_deduped
    GROUP BY exclude_reason
    ORDER BY COALESCE(SUM(latest_unit_size), 0) DESC
""")
for r in cur.fetchall():
    print(f"    {r['reason']:<30} {r['employers']:>7,} emp  {r['workers']:>12,} workers")

print("\n" + "=" * 70)
if DRY_RUN:
    print(f"DRY-RUN COMPLETE - no changes made. Use --apply to execute.")
else:
    print(f"FIX COMPLETE - {total_flagged:,} employers flagged, {len(ambiguous):,} exported for review.")
print("=" * 70)

cur.close()
conn.close()
