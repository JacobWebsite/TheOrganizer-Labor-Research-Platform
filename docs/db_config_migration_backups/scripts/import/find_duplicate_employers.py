import os
"""
Find potential duplicate employers using fuzzy name matching
Optimized version with GIN indexes and chunked processing
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
from name_normalizer import employer_token_similarity

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("Duplicate Employer Detection Report")
print("=" * 70)

# Create GIN indexes if not exists
print("\nCreating/checking indexes...")
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_f7_emp_trgm ON f7_employers_deduped
    USING gin (employer_name gin_trgm_ops)
""")
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_f7_emp_agg_trgm ON f7_employers_deduped
    USING gin (employer_name_aggressive gin_trgm_ops)
""")
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_vr_emp_trgm ON nlrb_voluntary_recognition
    USING gin (employer_name_normalized gin_trgm_ops)
""")
conn.commit()
print("Indexes ready.")

# =============================================================================
# PART 1: Find duplicates WITHIN f7_employers_deduped
# Use set_limit to filter efficiently with GIN index
# =============================================================================
print("\n" + "=" * 70)
print("PART 1: Potential Duplicates WITHIN f7_employers_deduped")
print("=" * 70)

# Set similarity threshold for GIN index operator
cur.execute("SELECT set_limit(0.5)")

# Get states to process in batches
cur.execute("SELECT DISTINCT state FROM f7_employers_deduped WHERE state IS NOT NULL ORDER BY state")
states = [r['state'] for r in cur.fetchall()]

f7_duplicates = []
print(f"\nProcessing {len(states)} states...")

for i, state in enumerate(states):
    if i % 10 == 0:
        print(f"  Processing state {i+1}/{len(states)}: {state}")

    # Find similar pairs within this state using the % operator (uses GIN index)
    cur.execute("""
        SELECT
            e1.employer_id as id1,
            e1.employer_name as name1,
            e1.city as city1,
            e1.state as state1,
            e1.latest_unit_size as size1,
            e2.employer_id as id2,
            e2.employer_name as name2,
            e2.city as city2,
            e2.state as state2,
            e2.latest_unit_size as size2,
            similarity(e1.employer_name, e2.employer_name) as name_sim
        FROM f7_employers_deduped e1
        JOIN f7_employers_deduped e2
            ON e1.employer_id < e2.employer_id
            AND e1.state = e2.state
            AND e1.employer_name %% e2.employer_name  -- Uses GIN index
        WHERE e1.state = %s
    """, (state,))

    state_dups = cur.fetchall()
    f7_duplicates.extend(state_dups)

print(f"\nFound {len(f7_duplicates)} potential duplicate pairs in f7_employers_deduped")

# Enhance with token similarity
f7_dup_enhanced = []
for row in f7_duplicates:
    token_sim = employer_token_similarity(row['name1'] or '', row['name2'] or '')
    combined_score = max(row['name_sim'], token_sim)
    f7_dup_enhanced.append({
        **dict(row),
        'token_sim': token_sim,
        'combined_score': combined_score
    })

# Sort by combined score
f7_dup_enhanced.sort(key=lambda x: x['combined_score'], reverse=True)

# Filter to high confidence
high_conf_f7 = [x for x in f7_dup_enhanced if x['combined_score'] >= 0.7]

print(f"High confidence (>= 0.7): {len(high_conf_f7)}")

print("\nTop 30 likely duplicates within f7_employers:")
print("-" * 80)
print(f"{'Name 1':<35} {'Name 2':<35} {'St':>3} {'Score':>6}")
print("-" * 80)

for row in f7_dup_enhanced[:30]:
    n1 = (row['name1'] or '')[:33]
    n2 = (row['name2'] or '')[:33]
    st = row['state1'] or ''
    print(f"{n1:<35} {n2:<35} {st:>3} {row['combined_score']:.2f}")

# =============================================================================
# PART 2: Find duplicates WITHIN VR table
# =============================================================================
print("\n" + "=" * 70)
print("PART 2: Potential Duplicates WITHIN nlrb_voluntary_recognition")
print("=" * 70)

# VR table is small enough to use regular similarity without GIN index
cur.execute("""
    SELECT
        v1.id as id1,
        v1.employer_name_normalized as name1,
        v1.unit_city as city1,
        v1.unit_state as state1,
        v1.num_employees as size1,
        v2.id as id2,
        v2.employer_name_normalized as name2,
        v2.unit_city as city2,
        v2.unit_state as state2,
        v2.num_employees as size2,
        similarity(v1.employer_name_normalized::text, v2.employer_name_normalized::text) as name_sim
    FROM nlrb_voluntary_recognition v1
    JOIN nlrb_voluntary_recognition v2
        ON v1.id < v2.id
        AND v1.unit_state = v2.unit_state
    WHERE v1.employer_name_normalized IS NOT NULL
      AND v2.employer_name_normalized IS NOT NULL
      AND similarity(v1.employer_name_normalized::text, v2.employer_name_normalized::text) >= 0.5
    ORDER BY name_sim DESC
    LIMIT 200
""")

vr_duplicates = cur.fetchall()
print(f"\nFound {len(vr_duplicates)} potential duplicate pairs in VR table")

# Enhance with token similarity
vr_dup_enhanced = []
for row in vr_duplicates:
    token_sim = employer_token_similarity(row['name1'] or '', row['name2'] or '')
    combined_score = max(row['name_sim'], token_sim)
    vr_dup_enhanced.append({
        **dict(row),
        'token_sim': token_sim,
        'combined_score': combined_score
    })

vr_dup_enhanced.sort(key=lambda x: x['combined_score'], reverse=True)

print("\nTop 25 likely duplicates within VR table:")
print("-" * 80)
print(f"{'Name 1':<35} {'Name 2':<35} {'St':>3} {'Score':>6}")
print("-" * 80)

for row in vr_dup_enhanced[:25]:
    n1 = (row['name1'] or '')[:33]
    n2 = (row['name2'] or '')[:33]
    st = row['state1'] or ''
    print(f"{n1:<35} {n2:<35} {st:>3} {row['combined_score']:.2f}")

# =============================================================================
# PART 3: Find unmatched VR employers similar to F7 records
# =============================================================================
print("\n" + "=" * 70)
print("PART 3: Unmatched VR Employers with Similar F7 Records")
print("=" * 70)

# Get unmatched VR records with largest employee counts
cur.execute("""
    SELECT id, employer_name_normalized, employer_name_aggressive,
           unit_city, unit_state, num_employees
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NULL
      AND employer_name_normalized IS NOT NULL
    ORDER BY num_employees DESC NULLS LAST
    LIMIT 200
""")
unmatched_vr = cur.fetchall()

print(f"\nAnalyzing top {len(unmatched_vr)} unmatched VR records...")

cross_duplicates = []

for i, vr in enumerate(unmatched_vr):
    if i % 50 == 0 and i > 0:
        print(f"  Processed {i}/{len(unmatched_vr)}...")

    vr_name = vr['employer_name_normalized'] or ''
    vr_state = vr['unit_state']

    # Find similar F7 employers using trigram operator with GIN index
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size,
               similarity(employer_name, %s::text) as name_sim
        FROM f7_employers_deduped
        WHERE employer_name %% %s::text
        ORDER BY similarity(employer_name, %s::text) DESC
        LIMIT 5
    """, (vr_name, vr_name, vr_name))

    similar_f7 = cur.fetchall()

    for f7 in similar_f7:
        token_sim = employer_token_similarity(vr_name, f7['employer_name'] or '')
        combined = max(f7['name_sim'], token_sim)
        same_state = vr_state == f7['state']

        if combined >= 0.5:
            cross_duplicates.append({
                'vr_id': vr['id'],
                'vr_name': vr_name,
                'vr_city': vr['unit_city'],
                'vr_state': vr_state,
                'vr_employees': vr['num_employees'],
                'f7_id': f7['employer_id'],
                'f7_name': f7['employer_name'],
                'f7_city': f7['city'],
                'f7_state': f7['state'],
                'f7_employees': f7['latest_unit_size'],
                'name_sim': f7['name_sim'],
                'token_sim': token_sim,
                'combined_score': combined,
                'same_state': same_state
            })

# Sort by same_state first, then score
cross_duplicates.sort(key=lambda x: (x['same_state'], x['combined_score']), reverse=True)

print(f"\nFound {len(cross_duplicates)} potential cross-table matches")

# High confidence matches
high_conf_cross = [x for x in cross_duplicates if x['combined_score'] >= 0.7 and x['same_state']]
print(f"High confidence same-state (>= 0.7): {len(high_conf_cross)}")

print("\nTop 40 potential matches (VR -> F7):")
print("-" * 95)
print(f"{'VR Name':<30} {'F7 Name':<30} {'VR St':>5} {'F7 St':>5} {'Score':>6} {'Same':>5}")
print("-" * 95)

for row in cross_duplicates[:40]:
    vr_n = (row['vr_name'] or '')[:28]
    f7_n = (row['f7_name'] or '')[:28]
    same = 'Y' if row['same_state'] else 'N'
    print(f"{vr_n:<30} {f7_n:<30} {row['vr_state'] or 'N/A':>5} {row['f7_state'] or 'N/A':>5} {row['combined_score']:.2f}  {same:>5}")

# =============================================================================
# PART 4: Summary Statistics
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY STATISTICS")
print("=" * 70)

def count_by_score(data, score_key='combined_score'):
    ranges = {'0.9+': 0, '0.8-0.9': 0, '0.7-0.8': 0, '0.6-0.7': 0, '0.5-0.6': 0}
    for row in data:
        s = row[score_key]
        if s >= 0.9:
            ranges['0.9+'] += 1
        elif s >= 0.8:
            ranges['0.8-0.9'] += 1
        elif s >= 0.7:
            ranges['0.7-0.8'] += 1
        elif s >= 0.6:
            ranges['0.6-0.7'] += 1
        else:
            ranges['0.5-0.6'] += 1
    return ranges

print("\nF7 internal duplicates by score:")
for range_name, count in count_by_score(f7_dup_enhanced).items():
    if count > 0:
        print(f"  {range_name}: {count}")

print("\nVR internal duplicates by score:")
for range_name, count in count_by_score(vr_dup_enhanced).items():
    if count > 0:
        print(f"  {range_name}: {count}")

print("\nVR -> F7 cross-table matches by score:")
for range_name, count in count_by_score(cross_duplicates).items():
    if count > 0:
        print(f"  {range_name}: {count}")

same_state_count = sum(1 for x in cross_duplicates if x['same_state'])
print(f"\nCross-table same-state matches: {same_state_count}")
print(f"Cross-table different-state: {len(cross_duplicates) - same_state_count}")

# =============================================================================
# Export to CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORTING REPORTS")
print("=" * 70)

# Export F7 duplicates
with open('f7_internal_duplicates.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['ID1', 'Name1', 'City1', 'State1', 'Size1',
                     'ID2', 'Name2', 'City2', 'State2', 'Size2',
                     'Name_Sim', 'Token_Sim', 'Combined_Score'])
    for row in f7_dup_enhanced:
        writer.writerow([
            row['id1'], row['name1'], row['city1'], row['state1'], row['size1'],
            row['id2'], row['name2'], row['city2'], row['state2'], row['size2'],
            f"{row['name_sim']:.3f}", f"{row['token_sim']:.3f}",
            f"{row['combined_score']:.3f}"
        ])
print(f"  Exported {len(f7_dup_enhanced)} F7 duplicate pairs to f7_internal_duplicates.csv")

# Export VR duplicates
with open('vr_internal_duplicates.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['ID1', 'Name1', 'City1', 'State1', 'Size1',
                     'ID2', 'Name2', 'City2', 'State2', 'Size2',
                     'Name_Sim', 'Token_Sim', 'Combined_Score'])
    for row in vr_dup_enhanced:
        writer.writerow([
            row['id1'], row['name1'], row['city1'], row['state1'], row['size1'],
            row['id2'], row['name2'], row['city2'], row['state2'], row['size2'],
            f"{row['name_sim']:.3f}", f"{row['token_sim']:.3f}",
            f"{row['combined_score']:.3f}"
        ])
print(f"  Exported {len(vr_dup_enhanced)} VR duplicate pairs to vr_internal_duplicates.csv")

# Export cross-table matches
with open('vr_f7_potential_matches.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['VR_ID', 'VR_Name', 'VR_City', 'VR_State', 'VR_Employees',
                     'F7_ID', 'F7_Name', 'F7_City', 'F7_State', 'F7_Employees',
                     'Name_Sim', 'Token_Sim', 'Combined_Score', 'Same_State'])
    for row in cross_duplicates:
        writer.writerow([
            row['vr_id'], row['vr_name'], row['vr_city'], row['vr_state'], row['vr_employees'],
            row['f7_id'], row['f7_name'], row['f7_city'], row['f7_state'], row['f7_employees'],
            f"{row['name_sim']:.3f}", f"{row['token_sim']:.3f}",
            f"{row['combined_score']:.3f}",
            'Y' if row['same_state'] else 'N'
        ])
print(f"  Exported {len(cross_duplicates)} cross-table matches to vr_f7_potential_matches.csv")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("REPORT COMPLETE")
print("=" * 70)
