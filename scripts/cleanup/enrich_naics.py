import os
"""
NAICS Enrichment for f7_employers_deduped
==========================================
Fills in missing NAICS codes from three sources (priority order):
  1. OSHA matches (direct establishment match via osha_f7_matches)
  2. Union-dominant NAICS (inferred from union's known employers)
  3. NLRB (if NAICS columns exist - checked at runtime)

Usage:
  py scripts/cleanup/enrich_naics.py          # dry run
  py scripts/cleanup/enrich_naics.py --apply  # apply changes

Provenance tracked via naics_source column:
  OSHA_ENRICHED, UNION_INFERRED, NLRB_ENRICHED
"""

import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import Counter

APPLY = '--apply' in sys.argv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)


def separator(title):
    print("")
    print("=" * 70)
    print(title)
    print("=" * 70)


# ============================================================================
# 0. BEFORE STATE
# ============================================================================
separator("NAICS Enrichment - %s" % ("APPLYING" if APPLY else "DRY RUN"))

print("\n--- Current naics_source distribution ---")
cur.execute("""
    SELECT COALESCE(naics_source, '(NULL)') as src, COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
before_dist = {}
for r in cur.fetchall():
    before_dist[r['src']] = r['cnt']
    print("  %s: %s" % (r['src'], "{:,}".format(r['cnt'])))

cur.execute("""
    SELECT COUNT(*) FROM f7_employers_deduped
    WHERE naics IS NULL OR naics = ''
""")
total_missing = cur.fetchone()['count']
print("\nTotal F7 employers missing NAICS: %s" % "{:,}".format(total_missing))


# ============================================================================
# 1. SOURCE 1: OSHA MATCHES
# ============================================================================
separator("Source 1: OSHA Matches")

print("\nFinding F7 employers missing NAICS that have OSHA establishment matches...")

cur.execute("""
    SELECT f.employer_id, f.employer_name, f.state,
           o.naics_code as osha_naics,
           m.match_confidence,
           m.match_method
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
    JOIN osha_establishments o ON m.establishment_id = o.establishment_id
    WHERE (f.naics IS NULL OR f.naics = '')
      AND o.naics_code IS NOT NULL
      AND o.naics_code != ''
      AND o.naics_code != '999999'
      AND LENGTH(o.naics_code) >= 2
    ORDER BY f.employer_id, m.match_confidence DESC NULLS LAST
""")
osha_rows = cur.fetchall()
print("  Raw OSHA matches for missing-NAICS employers: %s" % "{:,}".format(len(osha_rows)))

# Group by employer and resolve to best 2-digit NAICS
osha_updates = {}
for r in osha_rows:
    eid = r['employer_id']
    if eid not in osha_updates:
        osha_updates[eid] = {
            'employer_name': r['employer_name'],
            'state': r['state'],
            'naics_codes_6digit': [],
            'confidences': [],
        }
    osha_updates[eid]['naics_codes_6digit'].append(r['osha_naics'])
    conf = float(r['match_confidence']) if r['match_confidence'] else 0
    osha_updates[eid]['confidences'].append(conf)

# For each employer, find dominant 2-digit NAICS from their OSHA matches
osha_final = []
multi_naics_count = 0
for eid, data in osha_updates.items():
    # Convert all to 2-digit
    naics_2digits = [code[:2] for code in data['naics_codes_6digit']]
    counter = Counter(naics_2digits)
    most_common_naics, most_common_count = counter.most_common(1)[0]
    total_matches = len(naics_2digits)
    dominance_pct = most_common_count / total_matches

    unique_2digit = len(counter)
    if unique_2digit > 1:
        multi_naics_count += 1

    # Also find the best 6-digit code for naics_detailed
    detail_counter = Counter(data['naics_codes_6digit'])
    best_detail = detail_counter.most_common(1)[0][0]

    # Confidence: use max match confidence from OSHA, slightly reduce if multi-NAICS
    max_conf = max(data['confidences'])
    if unique_2digit > 1 and dominance_pct < 0.7:
        adj_conf = min(max_conf, 0.7)
    else:
        adj_conf = max_conf

    osha_final.append({
        'employer_id': eid,
        'employer_name': data['employer_name'],
        'state': data['state'],
        'naics': most_common_naics,
        'naics_detailed': best_detail,
        'naics_confidence': round(adj_conf, 3),
        'match_count': total_matches,
        'unique_2digit': unique_2digit,
        'dominance_pct': dominance_pct,
    })

print("  Unique employers to enrich from OSHA: %s" % "{:,}".format(len(osha_final)))
print("  Employers with multiple distinct 2-digit NAICS: %s" % "{:,}".format(multi_naics_count))

# Show samples
print("\n  Sample OSHA enrichments:")
for u in osha_final[:8]:
    extra = ""
    if u['unique_2digit'] > 1:
        extra = " (%s 2-digit codes, %.0f%% dominant)" % (u['unique_2digit'], u['dominance_pct'] * 100)
    print("    %s (%s) -> NAICS %s (detail: %s, conf: %.2f)%s" % (
        u['employer_name'][:45], u['state'],
        u['naics'], u['naics_detailed'], u['naics_confidence'], extra
    ))

# NAICS sector distribution
print("\n  OSHA enrichment by 2-digit NAICS sector:")
sector_counts = Counter(u['naics'] for u in osha_final)
for sector, cnt in sector_counts.most_common(15):
    print("    Sector %s: %s" % (sector, "{:,}".format(cnt)))

# Track which employer_ids were handled by OSHA (for dedup with later sources)
osha_enriched_ids = set(u['employer_id'] for u in osha_final)


# ============================================================================
# 2. SOURCE 2: UNION-DOMINANT NAICS
# ============================================================================
separator("Source 2: Union-Dominant NAICS Inference")

print("\nFinding unions where >=60%% of known employers share the same NAICS...")
print("(Requires >=5 employers with known NAICS per union)")

cur.execute("""
    WITH union_naics AS (
        SELECT latest_union_fnum,
               naics,
               COUNT(*) as cnt,
               SUM(COUNT(*)) OVER (PARTITION BY latest_union_fnum) as total_with_naics
        FROM f7_employers_deduped
        WHERE naics IS NOT NULL AND naics != ''
        AND latest_union_fnum IS NOT NULL
        GROUP BY latest_union_fnum, naics
    ),
    dominant AS (
        SELECT latest_union_fnum, naics, cnt, total_with_naics,
               cnt::float / total_with_naics as pct
        FROM union_naics
        WHERE total_with_naics >= 5
    )
    SELECT * FROM dominant WHERE pct >= 0.60
    ORDER BY cnt DESC
""")
dominant_unions = cur.fetchall()
print("  Qualifying unions (>=5 known, >=60%% dominant): %s" % "{:,}".format(len(dominant_unions)))

# Build lookup: fnum -> dominant naics
fnum_to_naics = {}
for r in dominant_unions:
    fnum = r['latest_union_fnum']
    # If multiple NAICS qualify for the same fnum (shouldn't happen with >=60%), take highest pct
    if fnum not in fnum_to_naics or r['pct'] > fnum_to_naics[fnum]['pct']:
        fnum_to_naics[fnum] = {
            'naics': r['naics'],
            'pct': r['pct'],
            'cnt': r['cnt'],
            'total': r['total_with_naics'],
        }

print("  Unique unions with dominant NAICS: %s" % "{:,}".format(len(fnum_to_naics)))

# Show top unions
print("\n  Top union-dominant NAICS patterns:")
sorted_unions = sorted(fnum_to_naics.items(), key=lambda x: x[1]['cnt'], reverse=True)
for fnum, info in sorted_unions[:10]:
    print("    fnum=%s -> NAICS %s (%s/%s = %.1f%%)" % (
        fnum, info['naics'], info['cnt'], info['total'], info['pct'] * 100
    ))

# Find missing-NAICS employers in these unions (excluding those already handled by OSHA)
cur.execute("""
    SELECT employer_id, employer_name, state, latest_union_fnum
    FROM f7_employers_deduped
    WHERE (naics IS NULL OR naics = '')
    AND latest_union_fnum IS NOT NULL
""")
missing_with_union = cur.fetchall()

union_final = []
skipped_osha = 0
skipped_no_dominant = 0
for r in missing_with_union:
    eid = r['employer_id']
    fnum = r['latest_union_fnum']

    # Skip if already handled by OSHA
    if eid in osha_enriched_ids:
        skipped_osha += 1
        continue

    # Check if this union has a dominant NAICS
    if fnum not in fnum_to_naics:
        skipped_no_dominant += 1
        continue

    info = fnum_to_naics[fnum]
    # Confidence based on dominance percentage
    if info['pct'] >= 0.90:
        conf = 0.8
    elif info['pct'] >= 0.80:
        conf = 0.7
    elif info['pct'] >= 0.70:
        conf = 0.6
    else:
        conf = 0.5

    union_final.append({
        'employer_id': eid,
        'employer_name': r['employer_name'],
        'state': r['state'],
        'naics': info['naics'],
        'naics_detailed': None,  # No 6-digit detail for inferred
        'naics_confidence': conf,
        'union_fnum': fnum,
        'dominance_pct': info['pct'],
    })

print("\n  Employers enrichable via union-dominant: %s" % "{:,}".format(len(union_final)))
print("  Skipped (already covered by OSHA): %s" % "{:,}".format(skipped_osha))
print("  Skipped (union has no dominant NAICS): %s" % "{:,}".format(skipped_no_dominant))

# Samples
print("\n  Sample union-dominant enrichments:")
for u in union_final[:8]:
    print("    %s (%s) -> NAICS %s (union fnum=%s, %.1f%% dominant, conf=%.2f)" % (
        u['employer_name'][:45], u['state'],
        u['naics'], u['union_fnum'], u['dominance_pct'] * 100, u['naics_confidence']
    ))

# Distribution
print("\n  Union-dominant enrichment by 2-digit NAICS sector:")
sector_counts = Counter(u['naics'] for u in union_final)
for sector, cnt in sector_counts.most_common(15):
    print("    Sector %s: %s" % (sector, "{:,}".format(cnt)))

union_enriched_ids = set(u['employer_id'] for u in union_final)


# ============================================================================
# 3. SOURCE 3: NLRB (check if available)
# ============================================================================
separator("Source 3: NLRB")

# Check if nlrb_participants or nlrb_elections have naics columns
cur.execute("""
    SELECT column_name, table_name
    FROM information_schema.columns
    WHERE table_name IN ('nlrb_participants', 'nlrb_elections')
    AND column_name LIKE '%%naics%%'
""")
nlrb_naics_cols = cur.fetchall()

if nlrb_naics_cols:
    print("  NLRB NAICS columns found:")
    for r in nlrb_naics_cols:
        print("    %s.%s" % (r['table_name'], r['column_name']))
    print("  (Would implement NLRB enrichment here)")
    nlrb_final = []
else:
    print("  No NAICS columns found in nlrb_participants or nlrb_elections.")
    print("  NLRB source is not viable for NAICS enrichment.")
    nlrb_final = []


# ============================================================================
# 4. SUMMARY
# ============================================================================
separator("ENRICHMENT SUMMARY")

total_enrichable = len(osha_final) + len(union_final) + len(nlrb_final)
remaining = total_missing - total_enrichable

print("")
print("  Source              | Count  | Confidence")
print("  -----------------  | ------ | ----------")
print("  OSHA matches       | %6s | Direct match (0.5-1.0)" % "{:,}".format(len(osha_final)))
print("  Union-dominant     | %6s | Inferred (0.5-0.8)" % "{:,}".format(len(union_final)))
print("  NLRB               | %6s | N/A (no NAICS data)" % "{:,}".format(len(nlrb_final)))
print("  -----------------  | ------ |")
print("  Total to enrich    | %6s |" % "{:,}".format(total_enrichable))
print("  Still missing      | %6s |" % "{:,}".format(remaining))
print("  Originally missing | %6s |" % "{:,}".format(total_missing))
print("")
print("  Coverage improvement: %.1f%% of missing records enriched" % (
    total_enrichable / total_missing * 100 if total_missing > 0 else 0))


# ============================================================================
# 5. APPLY OR DRY RUN
# ============================================================================
if not APPLY:
    separator("DRY RUN COMPLETE")
    print("\nNo changes made. Run with --apply to update the database.")
    print("  py scripts/cleanup/enrich_naics.py --apply")
    cur.close()
    conn.close()
    sys.exit(0)

separator("APPLYING UPDATES")

# Apply OSHA enrichments
print("\n--- Applying %s OSHA enrichments ---" % "{:,}".format(len(osha_final)))
osha_applied = 0
for u in osha_final:
    cur.execute("""
        UPDATE f7_employers_deduped
        SET naics = %s,
            naics_detailed = %s,
            naics_source = 'OSHA_ENRICHED',
            naics_confidence = %s
        WHERE employer_id = %s
          AND (naics IS NULL OR naics = '')
    """, (u['naics'], u['naics_detailed'], u['naics_confidence'], u['employer_id']))
    osha_applied += cur.rowcount

print("  OSHA records updated: %s" % "{:,}".format(osha_applied))

# Apply union-dominant enrichments
print("\n--- Applying %s union-dominant enrichments ---" % "{:,}".format(len(union_final)))
union_applied = 0
for u in union_final:
    cur.execute("""
        UPDATE f7_employers_deduped
        SET naics = %s,
            naics_detailed = %s,
            naics_source = 'UNION_INFERRED',
            naics_confidence = %s
        WHERE employer_id = %s
          AND (naics IS NULL OR naics = '')
    """, (u['naics'], u['naics_detailed'], u['naics_confidence'], u['employer_id']))
    union_applied += cur.rowcount

print("  Union-dominant records updated: %s" % "{:,}".format(union_applied))

conn.commit()
print("\nAll updates committed.")

# ============================================================================
# 6. AFTER STATE
# ============================================================================
separator("AFTER STATE")

print("\n--- naics_source distribution ---")
cur.execute("""
    SELECT COALESCE(naics_source, '(NULL)') as src, COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
for r in cur.fetchall():
    old = before_dist.get(r['src'], 0)
    delta = r['cnt'] - old
    if delta > 0:
        delta_str = " (+%s)" % "{:,}".format(delta)
    elif delta < 0:
        delta_str = " (%s)" % "{:,}".format(delta)
    else:
        delta_str = ""
    print("  %s: %s%s" % (r['src'], "{:,}".format(r['cnt']), delta_str))

cur.execute("""
    SELECT COUNT(*) FROM f7_employers_deduped
    WHERE naics IS NULL OR naics = ''
""")
still_missing = cur.fetchone()['count']
print("\nStill missing NAICS: %s (was %s)" % (
    "{:,}".format(still_missing), "{:,}".format(total_missing)))
print("Total enriched this run: %s" % "{:,}".format(osha_applied + union_applied))

separator("ENRICHMENT COMPLETE")

cur.close()
conn.close()
