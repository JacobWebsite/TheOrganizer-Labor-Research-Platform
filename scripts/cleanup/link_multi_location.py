"""
Link multi-location employer groups via corporate_parent_id.

For MULTI_LOCATION groups from the combined dedup evidence CSV: employers with
very similar names but clearly different physical locations. Instead of merging
(which loses per-site granularity), we link them via a shared corporate_parent_id.

The parent is the group member with the largest unit_size.

NO deletes, NO foreign key changes -- preserves per-site data.
Enables UI: "Part of multi-employer group with X other locations"

Input: data/f7_combined_dedup_evidence.csv (classification = MULTI_LOCATION)

Usage:
    py scripts/cleanup/link_multi_location.py                 # DRY RUN
    py scripts/cleanup/link_multi_location.py --apply         # Apply changes
"""
import csv
import os
import sys
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

DRY_RUN = '--apply' not in sys.argv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_CSV = os.path.join(BASE_DIR, 'data', 'f7_combined_dedup_evidence.csv')


def main():
    conn = psycopg2.connect(
        host='localhost',
        database='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("MULTI-LOCATION EMPLOYER LINKING")
    print("=" * 70)
    print("Mode: %s" % ('DRY RUN' if DRY_RUN else '*** APPLYING CHANGES ***'))
    print("Input: %s" % INPUT_CSV)
    print()

    # =========================================================================
    # Step 1: Ensure corporate_parent_id column exists
    # =========================================================================
    print("Step 1: Ensuring corporate_parent_id column exists...")

    try:
        cur.execute("""
            ALTER TABLE f7_employers_deduped
            ADD COLUMN corporate_parent_id TEXT
        """)
        conn.commit()
        print("  Added corporate_parent_id column")
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        print("  Column already exists")

    # Add index for efficient lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_f7_corporate_parent
        ON f7_employers_deduped(corporate_parent_id)
        WHERE corporate_parent_id IS NOT NULL
    """)
    conn.commit()

    # =========================================================================
    # Step 2: Load MULTI_LOCATION pairs
    # =========================================================================
    print("\nStep 2: Loading MULTI_LOCATION pairs from evidence CSV...")

    if not os.path.exists(INPUT_CSV):
        print("  ERROR: %s not found." % INPUT_CSV)
        print("  Run splink_rescore_pairs.py first.")
        cur.close()
        conn.close()
        return

    pairs = []
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Explicit MULTI_LOCATION classification
            if row['classification'] == 'MULTI_LOCATION':
                pairs.append((row['id1'], row['id2']))
                continue
            # Also detect multi-location pattern: high name similarity but
            # different cities (same company, different physical sites)
            pg = float(row['pgtrgm_combined']) if row.get('pgtrgm_combined') else None
            c1 = (row.get('city1') or '').strip().upper()
            c2 = (row.get('city2') or '').strip().upper()
            if pg and pg >= 0.8 and c1 and c2 and c1 != c2:
                pairs.append((row['id1'], row['id2']))

    print("  MULTI_LOCATION pairs: %d" % len(pairs))

    if not pairs:
        print("  No multi-location pairs to process.")
        cur.close()
        conn.close()
        return

    # =========================================================================
    # Step 3: Build groups via union-find
    # =========================================================================
    print("\nStep 3: Building multi-location groups (union-find)...")

    _parent = {}

    def find(x):
        if x not in _parent:
            _parent[x] = x
        if _parent[x] != x:
            _parent[x] = find(_parent[x])
        return _parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            _parent[px] = py

    for id1, id2 in pairs:
        union(id1, id2)

    all_ids = set()
    for id1, id2 in pairs:
        all_ids.add(id1)
        all_ids.add(id2)

    groups = defaultdict(set)
    for emp_id in all_ids:
        root = find(emp_id)
        groups[root].add(emp_id)

    multi_groups = {k: v for k, v in groups.items() if len(v) > 1}

    print("  Total employer IDs: %d" % len(all_ids))
    print("  Multi-location groups: %d" % len(multi_groups))

    size_dist = defaultdict(int)
    for g in multi_groups.values():
        size_dist[len(g)] += 1
    for sz in sorted(size_dist):
        print("    Groups of size %d: %d" % (sz, size_dist[sz]))

    # =========================================================================
    # Step 4: Fetch employer details and select parent (largest unit_size)
    # =========================================================================
    print("\nStep 4: Fetching employer details and selecting group parents...")

    id_list = list(all_ids)
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size
        FROM f7_employers_deduped
        WHERE employer_id = ANY(%s)
    """, (id_list,))
    details = {row['employer_id']: dict(row) for row in cur.fetchall()}

    link_decisions = []  # (employer_id, parent_id, employer_name, parent_name)
    for root, group_ids in multi_groups.items():
        group_employers = [details[eid] for eid in group_ids if eid in details]
        if len(group_employers) < 2:
            continue

        # Parent = largest unit_size
        group_employers.sort(key=lambda x: -(x['latest_unit_size'] or 0))
        parent = group_employers[0]

        for emp in group_employers:
            link_decisions.append({
                'employer_id': emp['employer_id'],
                'parent_id': parent['employer_id'],
                'employer_name': emp['employer_name'],
                'employer_city': emp['city'],
                'parent_name': parent['employer_name'],
                'parent_city': parent['city'],
                'employer_size': emp['latest_unit_size'] or 0,
                'parent_size': parent['latest_unit_size'] or 0,
            })

    print("  Link decisions: %d (including parents pointing to themselves)" % len(link_decisions))

    # =========================================================================
    # Step 5: Preview
    # =========================================================================
    print("\n" + "=" * 70)
    print("PREVIEW (first 20 links)")
    print("=" * 70)

    # Group by parent for display
    by_parent = defaultdict(list)
    for d in link_decisions:
        by_parent[d['parent_id']].append(d)

    shown = 0
    for parent_id, members in list(by_parent.items())[:10]:
        parent = [m for m in members if m['employer_id'] == parent_id]
        children = [m for m in members if m['employer_id'] != parent_id]
        if parent:
            p = parent[0]
            print("\n  PARENT: %s (%s) size=%d" % (p['parent_name'], p['parent_city'], p['parent_size']))
        for c in children:
            print("    CHILD: %s (%s) size=%d" % (c['employer_name'], c['employer_city'], c['employer_size']))
        shown += 1
    if len(by_parent) > 10:
        print("\n  ... and %d more groups" % (len(by_parent) - 10))

    # =========================================================================
    # Step 6: Apply or summarize
    # =========================================================================
    if DRY_RUN:
        print("\n" + "=" * 70)
        print("DRY RUN COMPLETE - No changes made")
        print("=" * 70)
        print("\n  Groups: %d" % len(multi_groups))
        print("  Employers to link: %d" % len(link_decisions))
        print("\nTo apply, run:")
        print("  py scripts/cleanup/link_multi_location.py --apply")
    else:
        print("\n" + "=" * 70)
        print("APPLYING LINKS")
        print("=" * 70)

        updated = 0
        for d in link_decisions:
            cur.execute("""
                UPDATE f7_employers_deduped
                SET corporate_parent_id = %s
                WHERE employer_id = %s
            """, (d['parent_id'], d['employer_id']))
            updated += cur.rowcount

        conn.commit()

        print("  Updated %d employer records with corporate_parent_id" % updated)

        # Verify
        cur.execute("""
            SELECT COUNT(*) as linked,
                   COUNT(DISTINCT corporate_parent_id) as groups
            FROM f7_employers_deduped
            WHERE corporate_parent_id IS NOT NULL
        """)
        row = cur.fetchone()
        print("  Verification: %d employers linked in %d groups" % (row['linked'], row['groups']))

        print("\n" + "=" * 70)
        print("MULTI-LOCATION LINKING COMPLETE")
        print("=" * 70)

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
