import os
from db_config import get_connection
"""
Review 173 employers excluded with exclude_reason='OUTLIER_WORKER_COUNT' (1.6M workers).
Some may be legitimately large bargaining units incorrectly excluded.

Classification logic:
  LEGITIMATE  - Real large employer, consistent LM history, OSHA presence -> un-exclude
  MULTI_EMPLOYER - Name suggests multi-employer/association agreement -> keep excluded
  FEDERAL     - Federal/public employer (not private sector BLS count) -> keep excluded
  DATA_ERROR  - Suspicious name, round numbers, unit > union total, no corroboration -> keep excluded
  UNCERTAIN   - No strong evidence either way -> keep excluded

Usage:
  py scripts/cleanup/review_outliers.py          # Dry run - show classifications
  py scripts/cleanup/review_outliers.py --apply  # Apply: un-exclude LEGITIMATE employers
"""
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

DRY_RUN = '--apply' not in sys.argv

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 90)
print("OUTLIER WORKER COUNT REVIEW")
print("Mode: %s" % ("DRY RUN" if DRY_RUN else "*** APPLYING CHANGES ***"))
print("=" * 90)

# ============================================================================
# Step 0: Current state
# ============================================================================
cur.execute("""
    SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted,
           COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END) as counted_emps,
           SUM(CASE WHEN exclude_reason = 'OUTLIER_WORKER_COUNT' THEN latest_unit_size ELSE 0 END) as outlier_workers,
           COUNT(CASE WHEN exclude_reason = 'OUTLIER_WORKER_COUNT' THEN 1 END) as outlier_count
    FROM f7_employers_deduped
""")
state = cur.fetchone()
print("\nCurrent state:")
print("  Counted workers:  %s (%.1f%% of BLS 7.2M)" % (
    '{:,}'.format(state['counted']), state['counted'] / 7200000 * 100))
print("  Counted employers: %s" % '{:,}'.format(state['counted_emps']))
print("  Outlier excluded:  %d employers, %s workers" % (
    state['outlier_count'], '{:,}'.format(state['outlier_workers'])))

# ============================================================================
# Step 1: Load all outliers with enrichment data
# ============================================================================
cur.execute("""
    SELECT
        f.employer_id,
        f.employer_name,
        f.city,
        f.state,
        f.latest_unit_size,
        f.latest_union_name,
        f.latest_union_fnum,
        f.naics,
        -- OSHA presence
        COALESCE(osha.match_count, 0) as osha_match_count,
        COALESCE(osha.total_employees, 0) as osha_total_employees,
        -- Union LM membership (latest year)
        lm_latest.members as union_total_members,
        lm_latest.yr_covered as lm_latest_year,
        -- Union LM history: how many years filed?
        lm_hist.years_filed,
        lm_hist.min_members,
        lm_hist.max_members,
        lm_hist.avg_members,
        -- How many other F7 employers does this union have?
        union_ctx.emp_count as union_employer_count,
        union_ctx.median_size as union_median_employer_size,
        union_ctx.total_workers as union_total_f7_workers
    FROM f7_employers_deduped f
    -- OSHA matches
    LEFT JOIN (
        SELECT m.f7_employer_id,
               COUNT(DISTINCT m.establishment_id) as match_count,
               SUM(e.employee_count) as total_employees
        FROM osha_f7_matches m
        JOIN osha_establishments e ON e.establishment_id = m.establishment_id
        GROUP BY m.f7_employer_id
    ) osha ON osha.f7_employer_id = f.employer_id
    -- Latest LM filing for this union
    LEFT JOIN LATERAL (
        SELECT members, yr_covered
        FROM lm_data
        WHERE f_num = CAST(f.latest_union_fnum AS VARCHAR)
        ORDER BY yr_covered DESC
        LIMIT 1
    ) lm_latest ON TRUE
    -- LM filing history for this union
    LEFT JOIN LATERAL (
        SELECT COUNT(DISTINCT yr_covered) as years_filed,
               MIN(members) as min_members,
               MAX(members) as max_members,
               AVG(members) as avg_members
        FROM lm_data
        WHERE f_num = CAST(f.latest_union_fnum AS VARCHAR)
    ) lm_hist ON TRUE
    -- Union context: how many employers, what's typical size
    LEFT JOIN (
        SELECT latest_union_fnum,
               COUNT(*) as emp_count,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size) as median_size,
               SUM(latest_unit_size) as total_workers
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
          AND latest_unit_size > 0
        GROUP BY latest_union_fnum
    ) union_ctx ON union_ctx.latest_union_fnum = f.latest_union_fnum
    WHERE f.exclude_reason = 'OUTLIER_WORKER_COUNT'
    ORDER BY f.latest_unit_size DESC
""")
outliers = cur.fetchall()
print("  Loaded %d outlier records with enrichment" % len(outliers))

# ============================================================================
# Step 2: Classification rules
# ============================================================================

# Multi-employer / association name patterns
MULTI_EMPLOYER_PATTERNS = [
    'various', 'signator', 'association', 'council', 'alliance',
    'all employer', 'multiple', 'contractors assoc', 'management assoc',
    'employer assoc', 'builders assoc', 'constructors assoc',
    'maritime assoc', 'maritime alliance', 'producers assoc',
    'workforce council', 'trade assoc', 'industry council',
    'benefit corp', 'employee benefit', 'pipe line contractor',
    'fabricators and erectors', 'insulation contractors',
    'building owners and managers', 'produce trade',
    'drywall taping', 'painting contractor', 'finishing contractor',
    'construction-industrial', 'glass management', 'glass & metal',
    'painting / glazing', 'neca ', 'national electrical contractors',
    'fire sprinkler', 'silicon valley contractors',
    'heavy constructors', 'transportation employers',
    'construction industries', 'mechanical contractor',
    'building contractor', 'contracting plumber',
    'agc ', 'agc of', 'associated general contractor',
    'smacna', 'neca chapter', 'n.e.c.a', 'chapter of the neca',
    'chapter, neca', 'chapter of neca',
    'allied employers', 'master painters',
    'line constructors', 'line constructor',
    'boilermaker employer', 'bargaining assoc',
    'associated master',
    'plumbing companies', 'sign and display companies',
    'construction companies', 'symphony opera ballet',
    'league of resident theatres',
    'four county highway',
    'mid-america regional bargaining',
    'fox valley associated',
    'associated general constr',  # AGC typo variant
    'acg of ',  # ACG = Associated General Contractors abbreviation
    'tradeshow convention',
    'international brotherhood of boilermakers',  # union used as employer name
    'international brotherhood of teamsters',  # union used as employer name (DC office)
]

# Federal / public employer patterns
FEDERAL_PATTERNS = [
    'department of vet', "dep't of vet", 'dept of vet',
    'postal service', 'u.s. department', 'u.s. dept',
    'usps ', 'dept of defense', 'state of california',
    'school board', 'board of education',
    'tribal government', 'state of ', 'county of ',
    'city of ', 'board of county',
    'department of correction', 'department of transport',
    'dept of cms', 'dept of correction',
    'honeywell federal',
]

# Known large-bargaining-unit unions (these unions naturally have single employers
# with thousands of workers - auto plants, grocery chains, hospitals, airlines, etc.)
LARGE_UNIT_UNIONS = {
    'ufcw', 'united food', 'food & commercial',
    'teamster', 'ibt',
    'uaw', 'united auto', 'automobile',
    'seiu', 'service employees',
    'unite here', 'hotel',
    'nurses', 'nnu', 'cna',
    'afscme', 'government employees',
    'usw', 'steelworkers',
    'iam', 'machinists',
    'ibew', 'electrical workers',
    'cwa', 'communications workers',
    'bctgm', 'bakery',
    'ilwu', 'longshore',
    'directors guild', 'dga',
    'carpenters',
    'american airlines', 'delta', 'united airlines',
}

# Suspicious name patterns (data garbage)
SUSPICIOUS_PATTERNS = [
    'nasdaq', 'hierarchy', 'test',
    'eeee',  # "Kaiser Permanenteeee"
    'see attached',  # "See attached spreadsheets for employer nam"
]

# Suspicious exact unit sizes (likely data entry placeholders)
SUSPICIOUS_SIZES = {99999, 999999}


def classify_outlier(r):
    """Classify an outlier employer. Returns (classification, reason)."""
    name = (r['employer_name'] or '').lower().strip()
    unit_size = r['latest_unit_size'] or 0
    union_name = (r['latest_union_name'] or '').lower()
    osha_count = r['osha_match_count'] or 0
    union_members = r['union_total_members'] or 0
    union_emp_count = r['union_employer_count'] or 0
    union_median = r['union_median_employer_size'] or 0
    years_filed = r['years_filed'] or 0
    osha_employees = r['osha_total_employees'] or 0

    # ---- DATA_ERROR: Suspicious/garbled names ----
    for pat in SUSPICIOUS_PATTERNS:
        if pat in name:
            return ('DATA_ERROR', 'Suspicious name pattern: %s' % pat)

    # ---- DATA_ERROR: Suspicious placeholder unit sizes ----
    if unit_size in SUSPICIOUS_SIZES:
        return ('DATA_ERROR', 'Suspicious placeholder size: %s' % '{:,}'.format(unit_size))

    # ---- FEDERAL: Government employers ----
    for pat in FEDERAL_PATTERNS:
        if pat in name:
            return ('FEDERAL', 'Government/public employer pattern: %s' % pat)

    # ---- MULTI_EMPLOYER: Association/multi-employer patterns ----
    for pat in MULTI_EMPLOYER_PATTERNS:
        if pat in name:
            return ('MULTI_EMPLOYER', 'Multi-employer pattern: %s' % pat)

    # ---- Now evaluate evidence for LEGITIMATE ----
    evidence_for = 0  # points toward legitimate
    evidence_against = 0  # points toward suspicious
    reasons = []

    # Check 1: OSHA presence (real workplace confirmed)
    if osha_count >= 3:
        evidence_for += 3
        reasons.append('+3 OSHA: %d establishments' % osha_count)
    elif osha_count >= 1:
        evidence_for += 1
        reasons.append('+1 OSHA: %d establishment' % osha_count)
    else:
        evidence_against += 1
        reasons.append('-1 No OSHA match')

    # Check 2: Unit size vs union total membership
    # If employer claims more workers than the union has total members, suspicious
    if union_members > 0:
        ratio = unit_size / union_members
        if ratio > 2.0:
            evidence_against += 3
            reasons.append('-3 Unit(%s) > 2x union members(%s)' % (
                '{:,}'.format(unit_size), '{:,}'.format(union_members)))
        elif ratio > 1.0:
            evidence_against += 1
            reasons.append('-1 Unit(%s) > union members(%s)' % (
                '{:,}'.format(unit_size), '{:,}'.format(union_members)))
        elif ratio >= 0.3:
            evidence_for += 2
            reasons.append('+2 Unit is %.0f%% of union total (plausible major employer)' % (ratio * 100))
        else:
            # Small fraction of union - could be legitimate large employer in big union
            evidence_for += 1
            reasons.append('+1 Unit is %.1f%% of union total' % (ratio * 100))
    else:
        evidence_against += 1
        reasons.append('-1 No union LM data found')

    # Check 3: Union LM filing history (consistency)
    if years_filed >= 5:
        evidence_for += 1
        reasons.append('+1 Union has %d years of LM filings' % years_filed)

    # Check 4: Known large-unit union
    is_large_unit_union = False
    for pat in LARGE_UNIT_UNIONS:
        if pat in union_name:
            is_large_unit_union = True
            break
    if is_large_unit_union:
        evidence_for += 2
        reasons.append('+2 Known large-unit union: %s' % union_name[:40])

    # Check 5: Suspiciously round numbers with no corroboration
    if unit_size % 1000 == 0 and unit_size >= 5000 and osha_count == 0:
        evidence_against += 2
        reasons.append('-2 Suspiciously round number (%s) with no OSHA' % '{:,}'.format(unit_size))

    # Check 6: OSHA employee count corroborates size
    if osha_employees > 0 and osha_employees >= unit_size * 0.1:
        evidence_for += 2
        reasons.append('+2 OSHA employees (%s) corroborate size' % '{:,}'.format(osha_employees))

    # Check 7: Very large (>50K) needs extra evidence
    if unit_size >= 50000:
        evidence_against += 1
        reasons.append('-1 Very large unit (>50K) needs strong evidence')

    # ---- Decision ----
    score = evidence_for - evidence_against
    if score >= 4:
        return ('LEGITIMATE', '; '.join(reasons))
    elif score >= 2:
        # Borderline - legitimate if OSHA or known union
        if osha_count >= 1 and is_large_unit_union:
            return ('LEGITIMATE', '; '.join(reasons))
        else:
            return ('UNCERTAIN', '; '.join(reasons))
    else:
        if evidence_against >= 3:
            return ('DATA_ERROR', '; '.join(reasons))
        else:
            return ('UNCERTAIN', '; '.join(reasons))


# ============================================================================
# Step 3: Classify all outliers
# ============================================================================
classifications = {
    'LEGITIMATE': [],
    'MULTI_EMPLOYER': [],
    'FEDERAL': [],
    'DATA_ERROR': [],
    'UNCERTAIN': [],
}

for r in outliers:
    cls, reason = classify_outlier(r)
    classifications[cls].append({
        'employer_id': r['employer_id'],
        'employer_name': r['employer_name'],
        'city': r['city'],
        'state': r['state'],
        'latest_unit_size': r['latest_unit_size'],
        'latest_union_name': r['latest_union_name'],
        'latest_union_fnum': r['latest_union_fnum'],
        'naics': r['naics'],
        'osha_match_count': r['osha_match_count'],
        'union_total_members': r['union_total_members'],
        'classification': cls,
        'reason': reason,
    })

# ============================================================================
# Step 4: Print results by classification
# ============================================================================

for cls in ['LEGITIMATE', 'MULTI_EMPLOYER', 'FEDERAL', 'DATA_ERROR', 'UNCERTAIN']:
    items = classifications[cls]
    total_workers = sum(i['latest_unit_size'] or 0 for i in items)
    print("\n" + "=" * 90)
    print("%s: %d employers, %s workers" % (cls, len(items), '{:,}'.format(total_workers)))
    print("=" * 90)

    if cls == 'LEGITIMATE':
        action = "-> Will UN-EXCLUDE (restore to counted)"
    elif cls == 'FEDERAL':
        action = "-> Keep excluded (not private sector)"
    elif cls == 'MULTI_EMPLOYER':
        action = "-> Keep excluded (multi-employer agreement)"
    elif cls == 'DATA_ERROR':
        action = "-> Keep excluded (data quality issue)"
    else:
        action = "-> Keep excluded (insufficient evidence)"
    print("  Action: %s" % action)

    # Print header
    print("\n  %-42s %-12s %-4s %10s %4s %10s %-25s" % (
        "Employer", "City", "ST", "Workers", "OSHA", "UnionMbrs", "Union"))
    print("  " + "-" * 115)

    for i in sorted(items, key=lambda x: -(x['latest_unit_size'] or 0)):
        print("  %-42s %-12s %-4s %10s %4d %10s %-25s" % (
            (i['employer_name'] or '')[:42],
            (i['city'] or '')[:12],
            i['state'] or '',
            '{:,}'.format(i['latest_unit_size'] or 0),
            i['osha_match_count'] or 0,
            '{:,}'.format(i['union_total_members'] or 0),
            (i['latest_union_name'] or '')[:25]))
        # Print reason on next line for LEGITIMATE and DATA_ERROR
        if cls in ('LEGITIMATE', 'DATA_ERROR', 'UNCERTAIN'):
            print("    Reason: %s" % i['reason'])

# ============================================================================
# Step 5: Summary
# ============================================================================
print("\n" + "=" * 90)
print("CLASSIFICATION SUMMARY")
print("=" * 90)
print("  %-15s %6s %12s" % ("Classification", "Count", "Workers"))
print("  " + "-" * 40)
total_legit_workers = 0
for cls in ['LEGITIMATE', 'MULTI_EMPLOYER', 'FEDERAL', 'DATA_ERROR', 'UNCERTAIN']:
    items = classifications[cls]
    workers = sum(i['latest_unit_size'] or 0 for i in items)
    print("  %-15s %6d %12s" % (cls, len(items), '{:,}'.format(workers)))
    if cls == 'LEGITIMATE':
        total_legit_workers = workers

print("\n  If LEGITIMATE employers are un-excluded:")
new_counted = state['counted'] + total_legit_workers
new_emps = state['counted_emps'] + len(classifications['LEGITIMATE'])
print("    New counted workers:  %s (was %s)" % (
    '{:,}'.format(new_counted), '{:,}'.format(state['counted'])))
print("    New counted employers: %s (was %s)" % (
    '{:,}'.format(new_emps), '{:,}'.format(state['counted_emps'])))
print("    New BLS coverage:     %.1f%% (was %.1f%%)" % (
    new_counted / 7200000 * 100, state['counted'] / 7200000 * 100))
print("    Workers restored:     %s" % '{:,}'.format(total_legit_workers))

# ============================================================================
# Step 6: Apply changes if --apply
# ============================================================================
if not DRY_RUN:
    legit_ids = [i['employer_id'] for i in classifications['LEGITIMATE']]
    if legit_ids:
        print("\n" + "=" * 90)
        print("APPLYING CHANGES: Un-excluding %d LEGITIMATE employers" % len(legit_ids))
        print("=" * 90)

        cur2 = conn.cursor()
        cur2.execute("""
            UPDATE f7_employers_deduped
            SET exclude_from_counts = FALSE,
                exclude_reason = NULL
            WHERE employer_id = ANY(%s)
              AND exclude_reason = 'OUTLIER_WORKER_COUNT'
        """, (legit_ids,))
        updated = cur2.rowcount
        conn.commit()
        print("  Updated %d records" % updated)

        # Also update FEDERAL ones to proper reason
        federal_ids = [i['employer_id'] for i in classifications['FEDERAL']]
        if federal_ids:
            cur2.execute("""
                UPDATE f7_employers_deduped
                SET exclude_reason = 'FEDERAL_EMPLOYER'
                WHERE employer_id = ANY(%s)
                  AND exclude_reason = 'OUTLIER_WORKER_COUNT'
            """, (federal_ids,))
            print("  Re-classified %d as FEDERAL_EMPLOYER" % cur2.rowcount)
            conn.commit()

        # Update MULTI_EMPLOYER ones to proper reason
        multi_ids = [i['employer_id'] for i in classifications['MULTI_EMPLOYER']]
        if multi_ids:
            cur2.execute("""
                UPDATE f7_employers_deduped
                SET exclude_reason = 'MULTI_EMPLOYER_AGREEMENT'
                WHERE employer_id = ANY(%s)
                  AND exclude_reason = 'OUTLIER_WORKER_COUNT'
            """, (multi_ids,))
            print("  Re-classified %d as MULTI_EMPLOYER_AGREEMENT" % cur2.rowcount)
            conn.commit()

        # Verify final state
        cur.execute("""
            SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted,
                   COUNT(CASE WHEN exclude_from_counts = FALSE THEN 1 END) as counted_emps,
                   SUM(CASE WHEN exclude_reason = 'OUTLIER_WORKER_COUNT' THEN latest_unit_size ELSE 0 END) as remaining_outlier_workers,
                   COUNT(CASE WHEN exclude_reason = 'OUTLIER_WORKER_COUNT' THEN 1 END) as remaining_outlier_count
            FROM f7_employers_deduped
        """)
        final = cur.fetchone()
        print("\n  FINAL STATE:")
        print("    Counted workers:  %s" % '{:,}'.format(final['counted']))
        print("    Counted employers: %d" % final['counted_emps'])
        print("    BLS coverage:     %.1f%%" % (final['counted'] / 7200000 * 100))
        print("    Remaining OUTLIER exclusions: %d employers, %s workers" % (
            final['remaining_outlier_count'],
            '{:,}'.format(final['remaining_outlier_workers'])))

        # Exclusion breakdown
        cur.execute("""
            SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
                   COUNT(*) as cnt, COALESCE(SUM(latest_unit_size), 0) as workers
            FROM f7_employers_deduped
            GROUP BY exclude_reason
            ORDER BY COALESCE(SUM(latest_unit_size), 0) DESC
        """)
        print("\n  Exclusion breakdown:")
        for row in cur.fetchall():
            print("    %-30s %6d employers  %12s workers" % (
                row['reason'], row['cnt'], '{:,}'.format(row['workers'])))
    else:
        print("\nNo LEGITIMATE employers found to un-exclude.")
else:
    print("\n  (Dry run - no changes made. Use --apply to un-exclude LEGITIMATE employers)")

conn.close()
print("\n" + "=" * 90)
print("DONE")
print("=" * 90)
