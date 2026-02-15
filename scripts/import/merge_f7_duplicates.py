import os
from db_config import get_connection
"""
Merge duplicate F7 employers based on similarity scores.
Handles updating references in f7_union_employer_relations and nlrb_voluntary_recognition.

IMPORTANT: Only merges employers in the SAME CITY (or city typos).
Different locations of the same company are NOT merged.

Usage:
    python merge_f7_duplicates.py                    # DRY RUN mode (default)
    python merge_f7_duplicates.py --apply            # Actually apply merges
    python merge_f7_duplicates.py --include-diff-cities  # Include different cities (DANGEROUS)
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import sys
from datetime import datetime
from collections import defaultdict

# Configuration
DRY_RUN = '--apply' not in sys.argv
INCLUDE_DIFF_CITIES = '--include-diff-cities' in sys.argv
MIN_SCORE = 0.9
CSV_FILE = 'f7_internal_duplicates.csv'


def normalize_city(city):
    """Normalize city name for comparison."""
    if not city:
        return ''
    return city.strip().upper().replace(',', '').replace('.', '').replace('  ', ' ')


def cities_match(city1, city2):
    """
    Check if two cities are the same or typos of each other.
    Returns True only for same city or very close typos.
    """
    c1 = normalize_city(city1)
    c2 = normalize_city(city2)

    # Exact match after normalization
    if c1 == c2:
        return True

    # Both empty
    if not c1 and not c2:
        return True

    # One is empty, other is not - don't merge
    if not c1 or not c2:
        return False

    # One is substring of other (handles abbreviations like "SF" vs "San Francisco" - but be careful)
    # Only if the shorter one is very short (likely abbreviation)
    if len(c1) <= 4 and c1 in c2:
        return True
    if len(c2) <= 4 and c2 in c1:
        return True

    # Similar length - check for typos (edit distance)
    if abs(len(c1) - len(c2)) <= 2:
        # Count character differences
        shorter, longer = (c1, c2) if len(c1) <= len(c2) else (c2, c1)

        # Simple edit distance approximation for typo detection
        if len(shorter) >= 4:
            # For longer city names, allow 1-2 character differences
            diffs = 0
            for i, char in enumerate(shorter):
                if i < len(longer) and char != longer[i]:
                    diffs += 1
            # Also count extra chars in longer string
            diffs += len(longer) - len(shorter)

            # Allow up to 2 differences for typos
            if diffs <= 2:
                return True

    return False

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("F7 Employer Duplicate Merge Script")
print("=" * 70)
print(f"Mode: {'DRY RUN' if DRY_RUN else 'APPLYING CHANGES'}")
print(f"Minimum score: {MIN_SCORE}")
print(f"City filter: {'DISABLED (including different cities)' if INCLUDE_DIFF_CITIES else 'ENABLED (same city only)'}")
print()

# =============================================================================
# Step 1: Load and filter duplicate pairs
# =============================================================================
print("Step 1: Loading duplicate pairs from CSV...")

all_pairs = []
same_city_pairs = []
diff_city_pairs = []

with open(CSV_FILE, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        score = float(row['Combined_Score'])
        if score >= MIN_SCORE:
            pair = {
                'id1': row['ID1'],
                'name1': row['Name1'],
                'city1': row['City1'],
                'state1': row['State1'],
                'size1': int(row['Size1']) if row['Size1'] else 0,
                'id2': row['ID2'],
                'name2': row['Name2'],
                'city2': row['City2'],
                'state2': row['State2'],
                'size2': int(row['Size2']) if row['Size2'] else 0,
                'score': score
            }
            all_pairs.append(pair)

            if cities_match(row['City1'], row['City2']):
                same_city_pairs.append(pair)
            else:
                diff_city_pairs.append(pair)

print(f"  Total pairs with score >= {MIN_SCORE}: {len(all_pairs)}")
print(f"    - Same city (or typo): {len(same_city_pairs)} (will merge)")
print(f"    - Different cities:    {len(diff_city_pairs)} (skipped)")

# Use only same-city pairs unless override flag is set
if INCLUDE_DIFF_CITIES:
    print("\n  WARNING: --include-diff-cities flag set, merging ALL pairs!")
    duplicate_pairs = all_pairs
else:
    duplicate_pairs = same_city_pairs

print(f"\n  Pairs to process: {len(duplicate_pairs)}")

# =============================================================================
# Step 2: Build merge graph (handle transitive duplicates)
# =============================================================================
print("\nStep 2: Building merge graph to handle transitive duplicates...")

# Use Union-Find to group all connected duplicates
parent = {}

def find(x):
    if x not in parent:
        parent[x] = x
    if parent[x] != x:
        parent[x] = find(parent[x])
    return parent[x]

def union(x, y):
    px, py = find(x), find(y)
    if px != py:
        parent[px] = py

# Connect all duplicate pairs
for pair in duplicate_pairs:
    union(pair['id1'], pair['id2'])

# Group employers by their root
groups = defaultdict(set)
all_ids = set()
for pair in duplicate_pairs:
    all_ids.add(pair['id1'])
    all_ids.add(pair['id2'])

for emp_id in all_ids:
    root = find(emp_id)
    groups[root].add(emp_id)

# Filter to groups with more than one member
merge_groups = {k: v for k, v in groups.items() if len(v) > 1}

print(f"  Unique employer IDs involved: {len(all_ids)}")
print(f"  Merge groups (connected components): {len(merge_groups)}")

# Count total merges (each group of N results in N-1 merges)
total_merges = sum(len(g) - 1 for g in merge_groups.values())
print(f"  Total merges to perform: {total_merges}")

# =============================================================================
# Step 3: For each group, determine which record to keep
# =============================================================================
print("\nStep 3: Determining which records to keep...")

# Get employer details for all involved IDs
id_list = list(all_ids)
cur.execute("""
    SELECT employer_id, employer_name, city, state, latest_unit_size,
           (SELECT COUNT(*) FROM f7_union_employer_relations WHERE employer_id = e.employer_id) as notice_count
    FROM f7_employers e
    WHERE employer_id = ANY(%s)
""", (id_list,))

employer_details = {row['employer_id']: dict(row) for row in cur.fetchall()}

merge_decisions = []

for root, group_ids in merge_groups.items():
    # Get details for all employers in this group
    group_employers = [employer_details.get(eid) for eid in group_ids if eid in employer_details]
    group_employers = [e for e in group_employers if e is not None]

    if len(group_employers) < 2:
        continue

    # Sort by: latest_unit_size DESC, notice_count DESC, employer_name ASC
    group_employers.sort(
        key=lambda x: (-x['latest_unit_size'] or 0, -x['notice_count'], x['employer_name'] or ''),
    )

    # Keep the first one (best), merge others into it
    keeper = group_employers[0]
    for emp in group_employers[1:]:
        # Find the similarity score for this specific pair
        pair_score = MIN_SCORE  # default
        for pair in duplicate_pairs:
            if (pair['id1'] == keeper['employer_id'] and pair['id2'] == emp['employer_id']) or \
               (pair['id2'] == keeper['employer_id'] and pair['id1'] == emp['employer_id']):
                pair_score = pair['score']
                break

        merge_decisions.append({
            'kept_id': keeper['employer_id'],
            'kept_name': keeper['employer_name'],
            'kept_city': keeper['city'],
            'kept_state': keeper['state'],
            'kept_size': keeper['latest_unit_size'],
            'kept_notices': keeper['notice_count'],
            'deleted_id': emp['employer_id'],
            'deleted_name': emp['employer_name'],
            'deleted_city': emp['city'],
            'deleted_state': emp['state'],
            'deleted_size': emp['latest_unit_size'],
            'deleted_notices': emp['notice_count'],
            'score': pair_score
        })

print(f"  Merge decisions prepared: {len(merge_decisions)}")

# =============================================================================
# Step 4: Preview merges
# =============================================================================
print("\n" + "=" * 70)
print("MERGE PREVIEW (first 20)")
print("=" * 70)

for i, m in enumerate(merge_decisions[:20]):
    print(f"\n[{i+1}] KEEP: {m['kept_name']}")
    print(f"       City: {m['kept_city']}, State: {m['kept_state']}, Size: {m['kept_size'] or 0}, Notices: {m['kept_notices']}")
    print(f"    DELETE: {m['deleted_name']}")
    print(f"       City: {m['deleted_city']}, State: {m['deleted_state']}, Size: {m['deleted_size'] or 0}, Notices: {m['deleted_notices']}")
    print(f"    Score: {m['score']:.3f}")

if len(merge_decisions) > 20:
    print(f"\n... and {len(merge_decisions) - 20} more merge operations")

# =============================================================================
# Step 5: Check impact on related tables
# =============================================================================
print("\n" + "=" * 70)
print("IMPACT ANALYSIS")
print("=" * 70)

deleted_ids = [m['deleted_id'] for m in merge_decisions]

# Check f7_union_employer_relations references
cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_union_employer_relations WHERE employer_id = ANY(%s)
""", (deleted_ids,))
f7_union_employer_relations_affected = cur.fetchone()['cnt']
print(f"\nf7_union_employer_relations to update: {f7_union_employer_relations_affected}")

# Check VR references
cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition WHERE matched_employer_id = ANY(%s)
""", (deleted_ids,))
vr_affected = cur.fetchone()['cnt']
print(f"nlrb_voluntary_recognition to update: {vr_affected}")

# =============================================================================
# Step 6: Execute or show summary
# =============================================================================

if DRY_RUN:
    print("\n" + "=" * 70)
    print("DRY RUN COMPLETE - No changes made")
    print("=" * 70)
    print(f"""
Summary:
  - Duplicate pairs with score >= {MIN_SCORE}: {len(duplicate_pairs)}
  - Unique employers involved: {len(all_ids)}
  - Merge groups: {len(merge_groups)}
  - Total merges to perform: {len(merge_decisions)}
  - f7_union_employer_relations to update: {f7_union_employer_relations_affected}
  - VR records to update: {vr_affected}

To apply these merges, run:
  python merge_f7_duplicates.py --apply
""")
else:
    print("\n" + "=" * 70)
    print("APPLYING MERGES")
    print("=" * 70)

    # Create audit log table
    print("\nCreating audit log table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS f7_employer_merge_log (
            id SERIAL PRIMARY KEY,
            merge_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kept_id TEXT NOT NULL,
            deleted_id TEXT NOT NULL,
            kept_name TEXT,
            deleted_name TEXT,
            similarity_score NUMERIC(5,3),
            f7_union_employer_relations_updated INTEGER,
            vr_records_updated INTEGER
        )
    """)
    conn.commit()

    # Process each merge
    successful_merges = 0
    errors = []

    for i, m in enumerate(merge_decisions):
        if i % 100 == 0 and i > 0:
            print(f"  Processed {i}/{len(merge_decisions)}...")

        try:
            # Update f7_union_employer_relations
            cur.execute("""
                UPDATE f7_union_employer_relations
                SET employer_id = %s
                WHERE employer_id = %s
            """, (m['kept_id'], m['deleted_id']))
            notices_updated = cur.rowcount

            # Update VR records
            cur.execute("""
                UPDATE nlrb_voluntary_recognition
                SET matched_employer_id = %s
                WHERE matched_employer_id = %s
            """, (m['kept_id'], m['deleted_id']))
            vr_updated = cur.rowcount

            # Log the merge
            cur.execute("""
                INSERT INTO f7_employer_merge_log
                (kept_id, deleted_id, kept_name, deleted_name, similarity_score,
                 f7_union_employer_relations_updated, vr_records_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (m['kept_id'], m['deleted_id'], m['kept_name'], m['deleted_name'],
                  m['score'], notices_updated, vr_updated))

            # Delete the duplicate employer record
            cur.execute("""
                DELETE FROM f7_employers WHERE employer_id = %s
            """, (m['deleted_id'],))

            successful_merges += 1

        except Exception as e:
            errors.append((m['deleted_id'], str(e)))
            conn.rollback()

    conn.commit()

    print(f"\n  Successful merges: {successful_merges}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for emp_id, error in errors[:5]:
            print(f"    {emp_id}: {error}")

    # Verify
    cur.execute("SELECT COUNT(*) as cnt FROM f7_employer_merge_log")
    log_count = cur.fetchone()['cnt']
    print(f"\n  Merge log entries: {log_count}")

    cur.execute("SELECT COUNT(*) as cnt FROM f7_employers")
    remaining = cur.fetchone()['cnt']
    print(f"  Remaining employers in f7_employers: {remaining}")

    print("\n" + "=" * 70)
    print("MERGE COMPLETE")
    print("=" * 70)

cur.close()
conn.close()
