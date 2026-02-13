"""
Agent B: Duplicate/Ambiguous Records - Phase 1 (Read-Only)
Finds duplicate and near-duplicate employers in f7_employers_deduped
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import os

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 1: Duplicate/Ambiguous Records Audit - f7_employers_deduped")
print("=" * 70)

# ============================================================================
# 1. Exact same aggressive name + same state
# ============================================================================
print("\n--- 1. Same Aggressive Name + Same State Groups ---")

cur.execute("""
    SELECT employer_name_aggressive, state, COUNT(*) as cnt,
           ARRAY_AGG(employer_id ORDER BY employer_id) as ids,
           ARRAY_AGG(employer_name ORDER BY employer_id) as names,
           ARRAY_AGG(city ORDER BY employer_id) as cities,
           ARRAY_AGG(COALESCE(street, '') ORDER BY employer_id) as streets
    FROM f7_employers_deduped
    WHERE employer_name_aggressive IS NOT NULL
      AND TRIM(employer_name_aggressive) != ''
    GROUP BY employer_name_aggressive, state
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC
""")
dup_groups = cur.fetchall()
print(f"Total duplicate groups (same aggressive name + state): {len(dup_groups)}")
total_dup_records = sum(g['cnt'] for g in dup_groups)
print(f"Total records in duplicate groups: {total_dup_records:,}")

# Categorize
generic_words = {'hauling', 'city', 'construction', 'transport', 'security',
                 'maintenance', 'services', 'management', 'cleaning',
                 'trucking', 'plumbing', 'electric', 'painting', 'roofing',
                 'paving', 'concrete', 'masonry', 'drywall', 'landscaping',
                 'janitorial', 'staffing', 'moving', 'delivery', 'towing',
                 'disposal', 'recycling', 'demolition', 'excavating',
                 'grading', 'welding', 'auto', 'taxi', 'cab'}

generic_groups = []
true_dup_groups = []
multi_location_groups = []

for g in dup_groups:
    name = g['employer_name_aggressive']
    words = set(name.split())
    cities = [c for c in g['cities'] if c]
    unique_cities = set(c.lower() for c in cities if c)

    # Generic name: single common word or very short
    if len(words) == 1 and (words & generic_words or len(name) <= 5):
        generic_groups.append(g)
    elif len(unique_cities) > 1:
        multi_location_groups.append(g)
    else:
        true_dup_groups.append(g)

print(f"\nCategories:")
print(f"  Generic names (likely different orgs): {len(generic_groups)}")
print(f"  Multi-location (different cities): {len(multi_location_groups)}")
print(f"  Potential true duplicates (same city): {len(true_dup_groups)}")

# Show top generic names
print(f"\n  Top 15 generic name groups:")
for g in sorted(generic_groups, key=lambda x: x['cnt'], reverse=True)[:15]:
    cities_str = ', '.join(list(set(c for c in g['cities'] if c))[:5])
    print(f"    '{g['employer_name_aggressive']}' x{g['cnt']} in {g['state']} -- cities: {cities_str}")

# Show potential true duplicates
print(f"\n  Top 20 potential true duplicates (same name+state+city):")
for g in sorted(true_dup_groups, key=lambda x: x['cnt'], reverse=True)[:20]:
    ids_str = ', '.join(str(i) for i in g['ids'][:5])
    names_str = ' | '.join(n for n in g['names'][:3])
    city = g['cities'][0] if g['cities'] else 'N/A'
    print(f"    '{g['employer_name_aggressive']}' x{g['cnt']} in {city}, {g['state']}")
    print(f"      IDs: {ids_str}")
    print(f"      Names: {names_str}")

# Show multi-location
print(f"\n  Top 15 multi-location groups:")
for g in sorted(multi_location_groups, key=lambda x: x['cnt'], reverse=True)[:15]:
    cities_str = ', '.join(list(set(c for c in g['cities'] if c))[:5])
    print(f"    '{g['employer_name_aggressive']}' x{g['cnt']} in {g['state']} -- cities: {cities_str}")

# ============================================================================
# 2. Downstream references for duplicate groups
# ============================================================================
print("\n--- 2. Downstream References for Top Duplicate Groups ---")

# Check which duplicate IDs are referenced in nlrb_participants or osha_f7_matches
all_dup_ids = []
for g in true_dup_groups[:50]:
    all_dup_ids.extend(g['ids'])

if all_dup_ids:
    # NLRB references
    cur.execute("""
        SELECT matched_employer_id, COUNT(*) as cnt
        FROM nlrb_participants
        WHERE matched_employer_id = ANY(%s)
        GROUP BY matched_employer_id
    """, (all_dup_ids,))
    nlrb_refs = {r['matched_employer_id']: r['cnt'] for r in cur.fetchall()}

    # OSHA references
    cur.execute("""
        SELECT f7_employer_id, COUNT(*) as cnt
        FROM osha_f7_matches
        WHERE f7_employer_id = ANY(%s)
        GROUP BY f7_employer_id
    """, (all_dup_ids,))
    osha_refs = {r['f7_employer_id']: r['cnt'] for r in cur.fetchall()}

    print(f"  Duplicate IDs referenced by NLRB: {len(nlrb_refs)}")
    print(f"  Duplicate IDs referenced by OSHA: {len(osha_refs)}")

    # Show examples of referenced duplicates
    print(f"\n  Duplicates with downstream references:")
    shown = 0
    for g in true_dup_groups:
        has_ref = False
        for eid in g['ids']:
            if eid in nlrb_refs or eid in osha_refs:
                has_ref = True
                break
        if has_ref and shown < 10:
            shown += 1
            print(f"    '{g['employer_name_aggressive']}' in {g['state']}:")
            for i, eid in enumerate(g['ids'][:5]):
                nlrb = nlrb_refs.get(eid, 0)
                osha = osha_refs.get(eid, 0)
                print(f"      ID={eid} '{g['names'][i]}' -- NLRB refs: {nlrb}, OSHA refs: {osha}")

# ============================================================================
# 3. Near-duplicate trigram scan (top states only for speed)
# ============================================================================
print("\n--- 3. Near-Duplicate Trigram Scan (>=0.7 similarity) ---")

# Ensure index exists
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_f7_emp_agg_trgm ON f7_employers_deduped
    USING gin (employer_name_aggressive gin_trgm_ops)
""")
conn.commit()

# Only scan top 5 states by employer count for speed
cur.execute("""
    SELECT state, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE state IS NOT NULL
    GROUP BY state ORDER BY COUNT(*) DESC LIMIT 5
""")
top_states = cur.fetchall()

cur.execute("SELECT set_limit(0.7)")

near_dups = []
for st in top_states:
    state = st['state']
    print(f"  Scanning {state} ({st['cnt']:,} employers)...")
    cur.execute("""
        SELECT e1.employer_id as id1, e1.employer_name as name1, e1.employer_name_aggressive as agg1,
               e1.city as city1,
               e2.employer_id as id2, e2.employer_name as name2, e2.employer_name_aggressive as agg2,
               e2.city as city2,
               similarity(e1.employer_name_aggressive, e2.employer_name_aggressive) as sim
        FROM f7_employers_deduped e1
        JOIN f7_employers_deduped e2
            ON e1.employer_id < e2.employer_id
            AND e1.state = e2.state
            AND e1.employer_name_aggressive %% e2.employer_name_aggressive
        WHERE e1.state = %s
          AND e1.employer_name_aggressive != e2.employer_name_aggressive
        ORDER BY similarity(e1.employer_name_aggressive, e2.employer_name_aggressive) DESC
        LIMIT 50
    """, (state,))
    state_near = cur.fetchall()
    near_dups.extend(state_near)
    print(f"    Found {len(state_near)} near-duplicate pairs")

print(f"\nTotal near-duplicate pairs across top 5 states: {len(near_dups)}")
print(f"\nTop 25 near-duplicates:")
for nd in sorted(near_dups, key=lambda x: x['sim'], reverse=True)[:25]:
    print(f"  sim={nd['sim']:.3f}: '{nd['agg1']}' ({nd['city1']}) vs '{nd['agg2']}' ({nd['city2']})")
    print(f"    Original: '{nd['name1']}' vs '{nd['name2']}'")

# ============================================================================
# 4. Duplicate stats by state
# ============================================================================
print("\n--- 4. Duplicate Groups by State ---")
state_dup_counts = {}
for g in dup_groups:
    st = g['state']
    state_dup_counts[st] = state_dup_counts.get(st, 0) + 1

print(f"States with most duplicate groups (top 15):")
for st, cnt in sorted(state_dup_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
    print(f"  {st}: {cnt} groups")

# ============================================================================
# Export to CSV
# ============================================================================
print("\n--- Exporting duplicate groups to CSV ---")

csv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'f7_duplicate_groups.csv')
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['aggressive_name', 'state', 'count', 'category', 'ids', 'original_names', 'cities'])
    for g in sorted(dup_groups, key=lambda x: x['cnt'], reverse=True):
        name = g['employer_name_aggressive']
        words = set(name.split())
        cities = [c for c in g['cities'] if c]
        unique_cities = set(c.lower() for c in cities if c)

        if len(words) == 1 and (words & generic_words or len(name) <= 5):
            cat = 'GENERIC'
        elif len(unique_cities) > 1:
            cat = 'MULTI_LOCATION'
        else:
            cat = 'TRUE_DUPLICATE'

        writer.writerow([
            g['employer_name_aggressive'],
            g['state'],
            g['cnt'],
            cat,
            ';'.join(str(i) for i in g['ids']),
            ';'.join(g['names']),
            ';'.join(c for c in g['cities'] if c)
        ])

print(f"Exported {len(dup_groups)} groups to {csv_path}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total duplicate groups (same aggressive+state): {len(dup_groups)}")
print(f"  Generic names: {len(generic_groups)}")
print(f"  Multi-location: {len(multi_location_groups)}")
print(f"  Potential true duplicates: {len(true_dup_groups)}")
print(f"Near-duplicates (>=0.7 sim, top 5 states): {len(near_dups)}")
print(f"CSV exported to: {csv_path}")
print("=" * 70)

cur.close()
conn.close()
print("\nPhase 1 audit complete (read-only, no changes made)")
