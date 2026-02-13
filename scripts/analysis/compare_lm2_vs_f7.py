"""
Comprehensive comparison: Deduplicated LM2 membership vs F7 employer data by national union.

Uses union_hierarchy.count_members = TRUE as the authoritative dedup system.
- INTERNATIONAL with count_members=TRUE: national union counted directly
- LOCAL with count_members=TRUE (all unaffiliated): grouped by aff_abbr

F7 data (f7_union_employer_relations) mapped up to national via parent_fnum.
"""

import sys
sys.path.insert(0, r'C:\Users\jakew\Downloads\labor-data-project')

from db_config import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()

    # =========================================================================
    # STEP 1: Deduplicated membership by national union
    # =========================================================================

    # Part A: International/national unions with count_members=TRUE
    cur.execute("""
        SELECT
            h.f_num,
            h.aff_abbr,
            h.union_name,
            COALESCE(h.members_2024, 0) as dedup_members,
            'INTERNATIONAL' as source_type
        FROM union_hierarchy h
        WHERE h.count_members = TRUE
          AND h.hierarchy_level = 'INTERNATIONAL'
    """)
    international_rows = cur.fetchall()

    # Part B: Unaffiliated locals (count_members=TRUE, no parent_fnum)
    # These are all locals with count_members=TRUE (confirmed: all have NULL parent_fnum)
    cur.execute("""
        SELECT
            NULL as f_num,
            h.aff_abbr,
            'Unaffiliated ' || h.aff_abbr || ' locals' as union_name,
            SUM(COALESCE(h.members_2024, 0)) as dedup_members,
            'LOCAL_AGGREGATE' as source_type
        FROM union_hierarchy h
        WHERE h.count_members = TRUE
          AND h.hierarchy_level = 'LOCAL'
        GROUP BY h.aff_abbr
    """)
    local_agg_rows = cur.fetchall()

    # Build dedup lookup: key = (f_num or None, aff_abbr)
    # For internationals: key by f_num
    # For local aggregates: key by ('LOCAL_AGG', aff_abbr)
    dedup_data = {}
    for row in international_rows:
        f_num, aff_abbr, union_name, dedup_members, source_type = row
        dedup_data[f_num] = {
            'f_num': f_num,
            'aff_abbr': aff_abbr,
            'union_name': union_name,
            'dedup_members': dedup_members,
            'source_type': source_type,
        }

    local_agg_data = {}
    for row in local_agg_rows:
        _, aff_abbr, union_name, dedup_members, source_type = row
        local_agg_data[aff_abbr] = {
            'f_num': None,
            'aff_abbr': aff_abbr,
            'union_name': union_name,
            'dedup_members': dedup_members,
            'source_type': source_type,
        }

    # =========================================================================
    # STEP 2: F7 employer data mapped to national union
    # =========================================================================

    # Map each F7 union_file_number up to its national/international via parent_fnum
    # If the F7 union IS an international, it maps to itself
    # If the local has a parent_fnum, roll up to the parent
    # If the local has NO parent_fnum, group by aff_abbr as "unaffiliated"

    cur.execute("""
        SELECT
            CASE
                WHEN h.hierarchy_level = 'INTERNATIONAL' THEN h.f_num
                WHEN h.parent_fnum IS NOT NULL THEN h.parent_fnum
                ELSE NULL  -- unaffiliated local
            END as national_fnum,
            CASE
                WHEN h.hierarchy_level = 'INTERNATIONAL' THEN h.aff_abbr
                WHEN h.parent_fnum IS NOT NULL THEN COALESCE(parent_h.aff_abbr, h.aff_abbr)
                ELSE h.aff_abbr  -- unaffiliated local's own aff_abbr
            END as national_aff_abbr,
            CASE
                WHEN h.parent_fnum IS NULL AND h.hierarchy_level = 'LOCAL' THEN TRUE
                ELSE FALSE
            END as is_unaffiliated,
            COUNT(DISTINCT r.employer_id) as employer_count,
            SUM(r.bargaining_unit_size) as f7_total_workers,
            COUNT(DISTINCT r.union_file_number) as local_count
        FROM f7_union_employer_relations r
        JOIN union_hierarchy h ON h.f_num = r.union_file_number::text
        LEFT JOIN union_hierarchy parent_h ON parent_h.f_num = h.parent_fnum
        GROUP BY
            CASE
                WHEN h.hierarchy_level = 'INTERNATIONAL' THEN h.f_num
                WHEN h.parent_fnum IS NOT NULL THEN h.parent_fnum
                ELSE NULL
            END,
            CASE
                WHEN h.hierarchy_level = 'INTERNATIONAL' THEN h.aff_abbr
                WHEN h.parent_fnum IS NOT NULL THEN COALESCE(parent_h.aff_abbr, h.aff_abbr)
                ELSE h.aff_abbr
            END,
            CASE
                WHEN h.parent_fnum IS NULL AND h.hierarchy_level = 'LOCAL' THEN TRUE
                ELSE FALSE
            END
    """)
    f7_rows = cur.fetchall()

    # Build F7 lookup
    # For affiliated (national_fnum is not NULL): key by national_fnum
    # For unaffiliated (is_unaffiliated=TRUE): key by ('LOCAL_AGG', aff_abbr)
    f7_by_national = {}  # keyed by national_fnum
    f7_by_unaff = {}     # keyed by aff_abbr for unaffiliated

    for row in f7_rows:
        national_fnum, national_aff_abbr, is_unaffiliated, emp_count, f7_workers, local_count = row
        entry = {
            'employer_count': emp_count or 0,
            'f7_total_workers': f7_workers or 0,
            'local_count': local_count or 0,
        }
        if is_unaffiliated:
            if national_aff_abbr not in f7_by_unaff:
                f7_by_unaff[national_aff_abbr] = {'employer_count': 0, 'f7_total_workers': 0, 'local_count': 0}
            f7_by_unaff[national_aff_abbr]['employer_count'] += entry['employer_count']
            f7_by_unaff[national_aff_abbr]['f7_total_workers'] += entry['f7_total_workers']
            f7_by_unaff[national_aff_abbr]['local_count'] += entry['local_count']
        else:
            if national_fnum in f7_by_national:
                # Aggregate (shouldn't happen often but be safe)
                f7_by_national[national_fnum]['employer_count'] += entry['employer_count']
                f7_by_national[national_fnum]['f7_total_workers'] += entry['f7_total_workers']
                f7_by_national[national_fnum]['local_count'] += entry['local_count']
            else:
                f7_by_national[national_fnum] = entry

    # =========================================================================
    # STEP 3: Merge dedup + F7 for internationals
    # =========================================================================

    combined = []

    # Internationals
    all_intl_fnums = set(dedup_data.keys()) | set(f7_by_national.keys())
    for fnum in all_intl_fnums:
        dedup = dedup_data.get(fnum, {})
        f7 = f7_by_national.get(fnum, {})

        aff_abbr = dedup.get('aff_abbr', '')
        union_name = dedup.get('union_name', '')
        dedup_members = dedup.get('dedup_members', 0)

        # If we have F7 data but no dedup entry, look up name from hierarchy
        if not aff_abbr and fnum:
            cur.execute("SELECT aff_abbr, union_name FROM union_hierarchy WHERE f_num = %s", (fnum,))
            r = cur.fetchone()
            if r:
                aff_abbr, union_name = r

        combined.append({
            'aff_abbr': aff_abbr or '???',
            'union_name': (union_name or '(unknown)')[:50],
            'dedup_members': dedup_members or 0,
            'f7_total_workers': f7.get('f7_total_workers', 0),
            'employer_count': f7.get('employer_count', 0),
            'local_count': f7.get('local_count', 0),
            'source_type': dedup.get('source_type', 'F7_ONLY'),
            'f_num': fnum,
        })

    # Unaffiliated local aggregates
    all_unaff_abbrs = set(local_agg_data.keys()) | set(f7_by_unaff.keys())
    for abbr in all_unaff_abbrs:
        dedup = local_agg_data.get(abbr, {})
        f7 = f7_by_unaff.get(abbr, {})

        combined.append({
            'aff_abbr': abbr or '???',
            'union_name': dedup.get('union_name', f'Unaffiliated {abbr} locals')[:50],
            'dedup_members': dedup.get('dedup_members', 0),
            'f7_total_workers': f7.get('f7_total_workers', 0),
            'employer_count': f7.get('employer_count', 0),
            'local_count': f7.get('local_count', 0),
            'source_type': dedup.get('source_type', 'F7_ONLY_UNAFF'),
            'f_num': None,
        })

    # Sort by dedup_members descending, then f7_total_workers
    combined.sort(key=lambda x: (-x['dedup_members'], -x['f7_total_workers']))

    # =========================================================================
    # STEP 4: Print comparison table
    # =========================================================================

    header = (
        f"{'#':>3} | {'Abbr':<10} | {'Union Name':<50} | {'Dedup Mbrs':>12} | "
        f"{'F7 Workers':>12} | {'F7 Empls':>10} | {'F7 Locals':>10} | {'Coverage %':>10}"
    )
    sep = '-' * len(header)

    print()
    print("=" * len(header))
    print("  NATIONAL UNION COMPARISON: Deduplicated LM2 Membership vs F7 Employer Data")
    print("=" * len(header))
    print()
    print(header)
    print(sep)

    total_dedup = 0
    total_f7_workers = 0
    total_employers = 0
    total_locals = 0
    rows_with_both = 0
    rows_dedup_only = 0
    rows_f7_only = 0

    for i, row in enumerate(combined, 1):
        dedup = row['dedup_members']
        f7w = row['f7_total_workers']
        emps = row['employer_count']
        locs = row['local_count']

        if dedup > 0 and f7w > 0:
            coverage = f"{f7w / dedup * 100:.1f}%"
            rows_with_both += 1
        elif dedup > 0:
            coverage = "0.0%"
            rows_dedup_only += 1
        elif f7w > 0:
            coverage = "N/A"
            rows_f7_only += 1
        else:
            coverage = "-"

        total_dedup += dedup
        total_f7_workers += f7w
        total_employers += emps
        total_locals += locs

        # Mark source type
        suffix = ""
        if row['source_type'] == 'LOCAL_AGGREGATE' or row['source_type'] == 'F7_ONLY_UNAFF':
            suffix = " *"
        elif row['source_type'] == 'F7_ONLY':
            suffix = " +"

        print(
            f"{i:>3} | {row['aff_abbr']:<10} | {row['union_name']:<50} | "
            f"{dedup:>12,} | {f7w:>12,} | {emps:>10,} | {locs:>10,} | {coverage:>10}{suffix}"
        )

    print(sep)

    # Totals
    if total_dedup > 0:
        total_coverage = f"{total_f7_workers / total_dedup * 100:.1f}%"
    else:
        total_coverage = "N/A"

    print(
        f"{'':>3} | {'TOTAL':<10} | {'':<50} | "
        f"{total_dedup:>12,} | {total_f7_workers:>12,} | {total_employers:>10,} | "
        f"{total_locals:>10,} | {total_coverage:>10}"
    )

    print()
    print("Legend: * = Unaffiliated local aggregate   + = F7 data only (no dedup entry)")
    print()

    # =========================================================================
    # STEP 5: Summary statistics
    # =========================================================================

    print("=" * 70)
    print("  SUMMARY STATISTICS")
    print("=" * 70)
    print(f"  Total national/international unions with dedup data:  {len(dedup_data):>6,}")
    print(f"  Total unaffiliated local groups:                      {len(local_agg_data):>6,}")
    print(f"  Total rows in comparison:                             {len(combined):>6,}")
    print(f"  Rows with both dedup + F7 data:                      {rows_with_both:>6,}")
    print(f"  Rows with dedup only (no F7):                        {rows_dedup_only:>6,}")
    print(f"  Rows with F7 only (no dedup):                        {rows_f7_only:>6,}")
    print()
    print(f"  Total dedup members (LM2):                       {total_dedup:>12,}")
    print(f"  Total F7 workers (bargaining unit):              {total_f7_workers:>12,}")
    print(f"  Overall F7 / Dedup coverage:                     {total_coverage:>12}")
    print(f"  Total F7 employers:                              {total_employers:>12,}")
    print(f"  Total F7 local unions with employer data:        {total_locals:>12,}")
    print()

    # =========================================================================
    # STEP 6: F7 unions NOT in union_hierarchy
    # =========================================================================

    cur.execute("""
        SELECT r.union_file_number,
               um.union_name,
               um.aff_abbr,
               COUNT(DISTINCT r.employer_id) as emp_count,
               SUM(r.bargaining_unit_size) as total_workers
        FROM f7_union_employer_relations r
        LEFT JOIN union_hierarchy h ON h.f_num = r.union_file_number::text
        LEFT JOIN unions_master um ON um.f_num = r.union_file_number::text
        WHERE h.f_num IS NULL
        GROUP BY r.union_file_number, um.union_name, um.aff_abbr
        ORDER BY SUM(r.bargaining_unit_size) DESC NULLS LAST
    """)
    unmatched_rows = cur.fetchall()

    total_unmatched_workers = sum(r[4] or 0 for r in unmatched_rows)
    total_unmatched_employers = sum(r[3] or 0 for r in unmatched_rows)

    print("=" * 90)
    print(f"  F7 UNIONS NOT IN union_hierarchy ({len(unmatched_rows)} unions, "
          f"{total_unmatched_workers:,} workers, {total_unmatched_employers:,} employers)")
    print("=" * 90)

    print(f"  {'F-Num':>10} | {'Abbr':<10} | {'Union Name':<40} | {'Employers':>10} | {'Workers':>10}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*40}-+-{'-'*10}-+-{'-'*10}")

    for row in unmatched_rows:
        fnum, name, abbr, emps, workers = row
        print(f"  {fnum:>10} | {(abbr or '')::<10} | {(name or '(not in unions_master)')[:40]:<40} | {emps or 0:>10,} | {workers or 0:>10,}")

    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*40}-+-{'-'*10}-+-{'-'*10}")
    print(f"  {'TOTAL':>10} | {'':<10} | {'':<40} | {total_unmatched_employers:>10,} | {total_unmatched_workers:>10,}")
    print()

    # =========================================================================
    # STEP 7: Coverage analysis - top unions by gap
    # =========================================================================

    print("=" * 70)
    print("  TOP 15 UNIONS BY ABSOLUTE GAP (Dedup - F7)")
    print("=" * 70)

    gaps = [(r['aff_abbr'], r['union_name'], r['dedup_members'], r['f7_total_workers'],
             r['dedup_members'] - r['f7_total_workers'])
            for r in combined if r['dedup_members'] > 0]
    gaps.sort(key=lambda x: -x[4])

    print(f"  {'Abbr':<10} | {'Union Name':<40} | {'Dedup':>12} | {'F7':>12} | {'Gap':>12} | {'Coverage':>8}")
    print(f"  {'-'*10}-+-{'-'*40}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}-+-{'-'*8}")

    for abbr, name, dedup, f7, gap in gaps[:15]:
        cov = f"{f7/dedup*100:.1f}%" if dedup > 0 else "N/A"
        print(f"  {abbr:<10} | {name[:40]:<40} | {dedup:>12,} | {f7:>12,} | {gap:>12,} | {cov:>8}")

    print()

    # Top unions where F7 EXCEEDS dedup (over-coverage)
    over = [(r['aff_abbr'], r['union_name'], r['dedup_members'], r['f7_total_workers'],
             r['f7_total_workers'] - r['dedup_members'])
            for r in combined if r['f7_total_workers'] > r['dedup_members'] and r['dedup_members'] > 0]
    over.sort(key=lambda x: -x[4])

    if over:
        print("=" * 70)
        print("  UNIONS WHERE F7 EXCEEDS DEDUP MEMBERS (over-coverage)")
        print("=" * 70)
        print(f"  {'Abbr':<10} | {'Union Name':<40} | {'Dedup':>12} | {'F7':>12} | {'Excess':>12} | {'Ratio':>8}")
        print(f"  {'-'*10}-+-{'-'*40}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}-+-{'-'*8}")

        for abbr, name, dedup, f7, excess in over:
            ratio = f"{f7/dedup:.2f}x" if dedup > 0 else "N/A"
            print(f"  {abbr:<10} | {name[:40]:<40} | {dedup:>12,} | {f7:>12,} | {excess:>12,} | {ratio:>8}")
        print()

    conn.close()
    print("Done.")


if __name__ == '__main__':
    main()
