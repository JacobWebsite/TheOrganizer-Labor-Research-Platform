import os
"""
Fix employers with NULL latest_union_fnum by:
1. Auto-fix from f7_union_employer_relations (330 employers)
2. Fuzzy match union names to unions_master (1,943 employers)

PHILOSOPHY: Data quality over external benchmarks. Only apply high-confidence
matches. Ambiguous cases exported for manual review, not force-matched.

Usage:
    py scripts/cleanup/fix_missing_union_linkage.py                # DRY RUN
    py scripts/cleanup/fix_missing_union_linkage.py --apply        # Apply changes
"""
import psycopg2
import sys

DRY_RUN = '--apply' not in sys.argv

conn = psycopg2.connect(
    host='localhost', dbname='olms_multiyear',
    user='postgres', password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

print("=" * 70)
print("FIX MISSING UNION LINKAGE (latest_union_fnum IS NULL)")
print("=" * 70)
print("Mode: %s" % ('DRY RUN' if DRY_RUN else '*** APPLYING ***'))

# Current state
cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
""")
r = cur.fetchone()
print("\nNull-fnum counted employers: %d (%s workers)" % (r[0], '{:,}'.format(r[1] or 0)))

# =========================================================================
# FIX 1: From f7_union_employer_relations
# =========================================================================
print("\n" + "=" * 70)
print("FIX 1: From f7_union_employer_relations (direct lookup)")
print("=" * 70)

# For each null-fnum employer, pick the relation with the largest bargaining unit
cur.execute("""
    WITH ranked AS (
        SELECT e.employer_id, r.union_file_number,
               r.bargaining_unit_size,
               um.union_name,
               ROW_NUMBER() OVER (
                   PARTITION BY e.employer_id
                   ORDER BY r.bargaining_unit_size DESC NULLS LAST
               ) as rn
        FROM f7_employers_deduped e
        JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
        LEFT JOIN unions_master um ON CAST(um.f_num AS INTEGER) = r.union_file_number
        WHERE e.latest_union_fnum IS NULL
    )
    SELECT employer_id, union_file_number, union_name, bargaining_unit_size
    FROM ranked
    WHERE rn = 1
    ORDER BY bargaining_unit_size DESC NULLS LAST
""")
relation_fixes = cur.fetchall()
print("\n  Found %d employers fixable from relations table:" % len(relation_fixes))
for r in relation_fixes[:20]:
    print("    %s -> fnum=%s %-40s (%s workers)" % (
        r[0][:16], r[1], (r[2] or '(unknown)')[:40], '{:,}'.format(r[3] or 0)))
if len(relation_fixes) > 20:
    print("    ... and %d more" % (len(relation_fixes) - 20))

# =========================================================================
# FIX 2: Fuzzy match union names to unions_master
# =========================================================================
print("\n" + "=" * 70)
print("FIX 2: Fuzzy match union names to unions_master")
print("=" * 70)

# Get employers with union names but no relations and no fnum
relation_fixed_ids = set(r[0] for r in relation_fixes)

cur.execute("""
    SELECT employer_id, latest_union_name, latest_unit_size
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
      AND latest_union_name IS NOT NULL AND latest_union_name != ''
    ORDER BY latest_unit_size DESC NULLS LAST
""")
all_null_fnum_with_name = cur.fetchall()

# Filter out those already fixed by relations
need_fuzzy = [(r[0], r[1], r[2]) for r in all_null_fnum_with_name
              if r[0] not in relation_fixed_ids]
print("\n  Employers needing fuzzy match: %d" % len(need_fuzzy))

# Get distinct union names to match
distinct_names = {}
for emp_id, name, size in need_fuzzy:
    key = name.strip().upper()
    if key not in distinct_names:
        distinct_names[key] = {'original': name, 'employers': [], 'total_workers': 0}
    distinct_names[key]['employers'].append(emp_id)
    distinct_names[key]['total_workers'] += size or 0

print("  Distinct union names to match: %d" % len(distinct_names))

# For each distinct name, find best match in unions_master
fuzzy_fixes = []  # (employer_id, fnum, union_name, similarity, emp_union_name)
ambiguous = []    # (name, employers, workers, candidates)

batch_size = 50
name_list = list(distinct_names.items())

print("\n  Matching %d distinct names..." % len(name_list))

for i in range(0, len(name_list), batch_size):
    batch = name_list[i:i + batch_size]
    for key, info in batch:
        name = info['original']
        # Find top match by similarity
        cur.execute("""
            SELECT f_num, union_name, aff_abbr,
                   similarity(%s, union_name) as sim
            FROM unions_master
            WHERE similarity(%s, union_name) > 0.3
            ORDER BY similarity(%s, union_name) DESC
            LIMIT 5
        """, (name, name, name))
        candidates = cur.fetchall()

        if not candidates:
            continue

        best = candidates[0]
        sim = best[3]

        if sim >= 0.7:
            # High confidence - auto-fix
            for emp_id in info['employers']:
                fuzzy_fixes.append((emp_id, int(best[0]), best[1], sim, name))
        elif sim >= 0.4:
            # Medium confidence - export for review
            ambiguous.append((
                name, len(info['employers']), info['total_workers'],
                [(c[0], c[1], c[2], c[3]) for c in candidates[:3]]
            ))

print("\n  High-confidence fuzzy matches (>= 0.7): %d employers" % len(fuzzy_fixes))
print("  Ambiguous matches (0.4-0.7): %d distinct names" % len(ambiguous))

# Show fuzzy fix examples
if fuzzy_fixes:
    # Sort by similarity descending
    fuzzy_fixes.sort(key=lambda x: -x[3])
    print("\n  Top 30 fuzzy fixes:")
    for emp_id, fnum, uname, sim, ename in fuzzy_fixes[:30]:
        print("    %-45s -> fnum=%s %-35s (%.2f)" % (
            ename[:45], fnum, uname[:35], sim))
    if len(fuzzy_fixes) > 30:
        print("    ... and %d more" % (len(fuzzy_fixes) - 30))

# Show ambiguous examples
if ambiguous:
    ambiguous.sort(key=lambda x: -x[2])
    print("\n  Top 20 ambiguous (need review):")
    for name, emp_count, workers, cands in ambiguous[:20]:
        best_cand = cands[0]
        print("    %-45s (%d emps, %s wkrs) -> best: %s (%.2f)" % (
            name[:45], emp_count, '{:,}'.format(workers),
            best_cand[1][:30], best_cand[3]))

# =========================================================================
# COMBINED IMPACT
# =========================================================================
print("\n" + "=" * 70)
print("COMBINED IMPACT")
print("=" * 70)

total_fixes = len(relation_fixes) + len(fuzzy_fixes)
print("\n  From relations table: %d employers" % len(relation_fixes))
print("  From fuzzy matching:  %d employers" % len(fuzzy_fixes))
print("  Total auto-fixable:   %d employers" % total_fixes)
print("  Ambiguous (review):   %d distinct names" % len(ambiguous))

# Remaining unfixed
cur.execute("""
    SELECT COUNT(*)
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
""")
total_null = cur.fetchone()[0]
remaining = total_null - total_fixes
print("\n  Currently null-fnum: %d" % total_null)
print("  After fix: ~%d remaining" % remaining)

# =========================================================================
# APPLY
# =========================================================================
if DRY_RUN:
    print("\n" + "=" * 70)
    print("DRY RUN COMPLETE - No changes made")
    print("=" * 70)
    print("\nTo apply, run:")
    print("  py scripts/cleanup/fix_missing_union_linkage.py --apply")
else:
    print("\n" + "=" * 70)
    print("APPLYING CHANGES")
    print("=" * 70)

    # Fix 1: Relations table
    fix1_count = 0
    for emp_id, fnum, uname, bu_size in relation_fixes:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET latest_union_fnum = %s
            WHERE employer_id = %s AND latest_union_fnum IS NULL
        """, (fnum, emp_id))
        fix1_count += cur.rowcount

    print("\n  Relations fixes applied: %d" % fix1_count)

    # Fix 2: Fuzzy matches
    fix2_count = 0
    for emp_id, fnum, uname, sim, ename in fuzzy_fixes:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET latest_union_fnum = %s
            WHERE employer_id = %s AND latest_union_fnum IS NULL
        """, (fnum, emp_id))
        fix2_count += cur.rowcount

    print("  Fuzzy fixes applied: %d" % fix2_count)

    conn.commit()

    # Export ambiguous for review
    if ambiguous:
        import csv
        outpath = 'data/union_linkage_review.csv'
        with open(outpath, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['union_name', 'employer_count', 'total_workers',
                        'best_fnum', 'best_match_name', 'best_aff', 'best_similarity',
                        'alt_fnum_2', 'alt_name_2', 'alt_sim_2'])
            for name, emp_count, workers, cands in ambiguous:
                row = [name, emp_count, workers]
                for c in cands[:2]:
                    row.extend([c[0], c[1], c[2], '%.3f' % c[3]])
                while len(row) < 10:
                    row.append('')
                w.writerow(row)
        print("\n  Ambiguous cases exported: %s (%d names)" % (outpath, len(ambiguous)))

    # Verify
    cur.execute("""
        SELECT COUNT(*), SUM(latest_unit_size)
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NULL AND exclude_from_counts = FALSE
    """)
    r = cur.fetchone()
    print("\n  Remaining null-fnum (counted): %d (%s workers)" % (r[0], '{:,}'.format(r[1] or 0)))

    # Overall linkage rate
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN latest_union_fnum IS NOT NULL THEN 1 ELSE 0 END) as linked
        FROM f7_employers_deduped
    """)
    r = cur.fetchone()
    print("  Overall linkage: %d / %d (%.1f%%)" % (r[1], r[0], r[1] / r[0] * 100))

    print("\n" + "=" * 70)
    print("CHANGES APPLIED SUCCESSFULLY")
    print("=" * 70)

conn.close()
