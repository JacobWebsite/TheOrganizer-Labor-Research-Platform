"""
NAICS Enrichment from OSHA Matches
Fills in missing NAICS codes for f7_employers_deduped using osha_f7_matches -> osha_establishments
"""

import sys
import os
from psycopg2.extras import RealDictCursor
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection(cursor_factory=RealDictCursor)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NAICS Enrichment from OSHA Matches")
print("=" * 70)

# ============================================================================
# 1. Before counts
# ============================================================================
print("\n--- Before: naics_source distribution ---")
cur.execute("""
    SELECT naics_source, COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
before = {}
for r in cur.fetchall():
    before[r['naics_source']] = r['cnt']
    print(f"  {r['naics_source']}: {r['cnt']:,}")

# ============================================================================
# 2. Find enrichable records with best OSHA NAICS per f7 employer
# ============================================================================
print("\n--- Finding enrichable records ---")

cur.execute("""
    SELECT f.employer_id, f.employer_name, f.naics as old_naics,
           o.naics_code as osha_naics,
           m.match_confidence,
           m.match_method,
           o.estab_name as osha_name
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
    JOIN osha_establishments o ON m.establishment_id = o.establishment_id
    WHERE f.naics_source = 'NONE'
      AND o.naics_code IS NOT NULL
      AND TRIM(CAST(o.naics_code AS TEXT)) != ''
    ORDER BY f.employer_id, m.match_confidence DESC NULLS LAST
""")
rows = cur.fetchall()
print(f"Total OSHA matches for enrichable employers: {len(rows):,}")

# Group by employer_id and pick best NAICS
employer_naics = {}
for r in rows:
    eid = r['employer_id']
    if eid not in employer_naics:
        employer_naics[eid] = {
            'employer_name': r['employer_name'],
            'old_naics': r['old_naics'],
            'matches': []
        }
    employer_naics[eid]['matches'].append({
        'naics': r['osha_naics'],
        'confidence': float(r['match_confidence']) if r['match_confidence'] else 0,
        'method': r['match_method'],
        'osha_name': r['osha_name']
    })

print(f"Unique F7 employers to enrich: {len(employer_naics):,}")

# Resolve conflicts: highest confidence first, then mode
updates = []
conflict_count = 0
for eid, data in employer_naics.items():
    matches = data['matches']
    naics_codes = [m['naics'] for m in matches]
    unique_naics = set(naics_codes)

    if len(unique_naics) == 1:
        # All matches agree
        best_naics = naics_codes[0]
        best_conf = max(m['confidence'] for m in matches)
    else:
        # Conflict: pick highest confidence match's NAICS
        conflict_count += 1
        best_match = max(matches, key=lambda m: m['confidence'])
        best_naics = best_match['naics']
        best_conf = best_match['confidence']

    # Extract 2-digit sector
    naics_2digit = best_naics[:2] if len(best_naics) >= 2 else best_naics

    updates.append({
        'employer_id': eid,
        'employer_name': data['employer_name'],
        'old_naics': data['old_naics'],
        'naics': naics_2digit,
        'naics_detailed': best_naics,
        'naics_confidence': best_conf,
        'match_count': len(matches),
        'unique_naics_count': len(unique_naics)
    })

print(f"NAICS conflicts (multi-match, different codes): {conflict_count}")

# ============================================================================
# 3. Apply updates
# ============================================================================
print(f"\n--- Applying {len(updates):,} updates ---")

for u in updates:
    cur.execute("""
        UPDATE f7_employers_deduped
        SET naics = %s,
            naics_detailed = %s,
            naics_source = 'OSHA',
            naics_confidence = %s
        WHERE employer_id = %s
    """, (u['naics'], u['naics_detailed'], u['naics_confidence'], u['employer_id']))

conn.commit()
print(f"Updated {len(updates):,} records")

# ============================================================================
# 4. After counts
# ============================================================================
print("\n--- After: naics_source distribution ---")
cur.execute("""
    SELECT naics_source, COUNT(*) as cnt
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
for r in cur.fetchall():
    old = before.get(r['naics_source'], 0)
    delta = r['cnt'] - old
    delta_str = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
    print(f"  {r['naics_source']}: {r['cnt']:,}{delta_str}")

# ============================================================================
# 5. Verify: any remaining enrichable?
# ============================================================================
print("\n--- Verification ---")
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) as remaining
    FROM f7_employers_deduped f
    JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
    JOIN osha_establishments o ON m.establishment_id = o.establishment_id
    WHERE f.naics_source = 'NONE'
      AND o.naics_code IS NOT NULL
      AND TRIM(CAST(o.naics_code AS TEXT)) != ''
""")
r = cur.fetchone()
print(f"Remaining enrichable (should be 0): {r['remaining']}")

# ============================================================================
# 6. Spot check
# ============================================================================
print("\n--- Spot Check (10 enriched records) ---")
sample = updates[:10]
for u in sample:
    print(f"  {u['employer_name'][:50]}")
    print(f"    NAICS: {u['old_naics'] or 'NULL'} -> {u['naics_detailed']} (sector {u['naics']})")
    print(f"    Confidence: {u['naics_confidence']:.2f}, OSHA matches: {u['match_count']}, unique NAICS: {u['unique_naics_count']}")

# ============================================================================
# 7. NAICS sector distribution of enriched records
# ============================================================================
print("\n--- Enriched Records by NAICS Sector ---")
sector_counts = Counter(u['naics'] for u in updates)
for sector, cnt in sector_counts.most_common(20):
    print(f"  Sector {sector}: {cnt:,}")

# ============================================================================
# 8. Confidence distribution
# ============================================================================
print("\n--- Confidence Distribution ---")
conf_counts = Counter(u['naics_confidence'] for u in updates)
for conf, cnt in conf_counts.most_common():
    print(f"  {conf}: {cnt:,}")

print("\n" + "=" * 70)
print(f"NAICS enrichment complete: {len(updates):,} records updated")
print("=" * 70)

cur.close()
conn.close()
