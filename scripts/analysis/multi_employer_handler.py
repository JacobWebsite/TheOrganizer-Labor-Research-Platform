"""
Multi-Employer Agreement Handler
Strategy: Keep all records for relationships, count only MAX per union group

This creates:
1. Group assignments for multi-employer agreements
2. Primary/secondary flags (only primary counts toward BLS)
3. Views for UI display and BLS reconciliation
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def run_query(conn, query, commit=False):
    cur = conn.cursor()
    try:
        cur.execute(query)
        if commit:
            conn.commit()
        if cur.description:
            return cur.fetchall()
        return []
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: {e}")
        return None

def main():
    print(f"""
================================================================================
        MULTI-EMPLOYER AGREEMENT HANDLER
        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================

Strategy: Keep ALL employer records for relationship tracking.
          Only count the MAX worker count per union group toward BLS totals.
""")
    
    conn = get_connection()
    print("Connected to database.\n")
    
    # =========================================================================
    # STEP 1: Add tracking columns
    # =========================================================================
    print("STEP 1: Adding tracking columns...")
    run_query(conn, """
        ALTER TABLE f7_employers_deduped 
        ADD COLUMN IF NOT EXISTS exclude_from_counts BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS exclude_reason VARCHAR(50),
        ADD COLUMN IF NOT EXISTS data_quality_flag VARCHAR(50),
        ADD COLUMN IF NOT EXISTS multi_employer_group_id INTEGER,
        ADD COLUMN IF NOT EXISTS is_primary_in_group BOOLEAN DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS group_max_workers INTEGER
    """, commit=True)
    print("  Done.\n")
    
    # =========================================================================
    # STEP 2: Reset previous flags (clean slate)
    # =========================================================================
    print("STEP 2: Resetting previous multi-employer flags...")
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET multi_employer_group_id = NULL,
            is_primary_in_group = TRUE,
            group_max_workers = NULL
        WHERE multi_employer_group_id IS NOT NULL
    """, commit=True)
    
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET exclude_from_counts = FALSE,
            exclude_reason = NULL
        WHERE exclude_reason IN ('MULTI_EMPLOYER_SECONDARY', 'SAG_AFTRA_SECONDARY', 
                                  'SAG_AFTRA_DUPLICATE', 'SIGNATORY_SECONDARY')
    """, commit=True)
    print("  Done.\n")
    
    # =========================================================================
    # STEP 3: Identify unions with multiple employers (same f_num)
    # =========================================================================
    print("STEP 3: Finding unions with multiple employer entries...")
    
    # Find unions where same f_num has multiple employers AND sum >> max
    result = run_query(conn, """
        WITH union_stats AS (
            SELECT 
                latest_f_num,
                COUNT(DISTINCT employer_id) as emp_count,
                MAX(latest_unit_size) as max_workers,
                SUM(latest_unit_size) as sum_workers
            FROM f7_employers_deduped
            WHERE latest_f_num IS NOT NULL
              AND exclude_reason IS NULL
            GROUP BY latest_f_num
            HAVING COUNT(DISTINCT employer_id) > 1
               AND SUM(latest_unit_size) > MAX(latest_unit_size) * 1.2
        )
        SELECT COUNT(*) as groups, SUM(emp_count) as employers, 
               SUM(sum_workers) as raw_sum, SUM(max_workers) as deduped_sum
        FROM union_stats
    """)
    if result:
        r = result[0]
        print(f"  Found {r['groups']:,} union groups with {r['employers']:,} employers")
        print(f"  Raw sum: {r['raw_sum']:,} → Deduped: {r['deduped_sum']:,} (saves {r['raw_sum'] - r['deduped_sum']:,})\n")
    
    # Assign group IDs
    run_query(conn, """
        WITH union_groups AS (
            SELECT 
                latest_f_num,
                MAX(latest_unit_size) as max_workers,
                ROW_NUMBER() OVER (ORDER BY SUM(latest_unit_size) DESC) as group_id
            FROM f7_employers_deduped
            WHERE latest_f_num IS NOT NULL
              AND exclude_reason IS NULL
            GROUP BY latest_f_num
            HAVING COUNT(DISTINCT employer_id) > 1
               AND SUM(latest_unit_size) > MAX(latest_unit_size) * 1.2
        )
        UPDATE f7_employers_deduped f
        SET multi_employer_group_id = g.group_id,
            group_max_workers = g.max_workers
        FROM union_groups g
        WHERE f.latest_f_num = g.latest_f_num
          AND f.exclude_reason IS NULL
    """, commit=True)
    
    # Mark primaries (highest worker count in each group)
    run_query(conn, """
        WITH ranked AS (
            SELECT 
                employer_id,
                ROW_NUMBER() OVER (
                    PARTITION BY multi_employer_group_id 
                    ORDER BY latest_unit_size DESC, employer_id
                ) as rn
            FROM f7_employers_deduped
            WHERE multi_employer_group_id IS NOT NULL
              AND multi_employer_group_id < 90000
        )
        UPDATE f7_employers_deduped f
        SET is_primary_in_group = (r.rn = 1)
        FROM ranked r
        WHERE f.employer_id = r.employer_id
    """, commit=True)
    
    # Exclude secondaries from counts
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'MULTI_EMPLOYER_SECONDARY'
        WHERE multi_employer_group_id IS NOT NULL
          AND multi_employer_group_id < 90000
          AND is_primary_in_group = FALSE
    """, commit=True)
    
    result = run_query(conn, """
        SELECT COUNT(*) as excluded, SUM(latest_unit_size) as workers
        FROM f7_employers_deduped
        WHERE exclude_reason = 'MULTI_EMPLOYER_SECONDARY'
    """)
    if result:
        print(f"  Marked {result[0]['excluded']:,} secondary records (not counted)")
        print(f"  Workers removed from count: {result[0]['workers']:,}\n")
    
    # =========================================================================
    # STEP 4: Handle SAG-AFTRA signatories (special case - may have different f_nums)
    # =========================================================================
    print("STEP 4: Handling SAG-AFTRA signatory agreements...")
    
    # Find all SAG-AFTRA signatory entries
    result = run_query(conn, """
        SELECT employer_id, employer_name, latest_unit_size
        FROM f7_employers_deduped
        WHERE (
            employer_name ILIKE '%all signator%'
            OR employer_name ILIKE '%signatories to%'
            OR employer_name ILIKE '%network code%'
        )
        AND (latest_union_name ILIKE '%SAG%' OR latest_union_name ILIKE '%screen actor%')
        AND exclude_reason IS NULL
        ORDER BY latest_unit_size DESC
    """)
    
    if result:
        print(f"  Found {len(result)} SAG-AFTRA signatory entries:")
        for i, r in enumerate(result[:5]):
            marker = "← PRIMARY" if i == 0 else "  (secondary)"
            print(f"    {r['latest_unit_size']:>10,} - {r['employer_name'][:50]} {marker}")
        if len(result) > 5:
            print(f"    ... and {len(result) - 5} more")
        
        # Mark all as group 99999, first one is primary
        run_query(conn, """
            WITH sag_ranked AS (
                SELECT 
                    employer_id,
                    ROW_NUMBER() OVER (ORDER BY latest_unit_size DESC, employer_id) as rn,
                    MAX(latest_unit_size) OVER () as max_workers
                FROM f7_employers_deduped
                WHERE (
                    employer_name ILIKE '%all signator%'
                    OR employer_name ILIKE '%signatories to%'
                    OR employer_name ILIKE '%network code%'
                )
                AND (latest_union_name ILIKE '%SAG%' OR latest_union_name ILIKE '%screen actor%')
                AND exclude_reason IS NULL
            )
            UPDATE f7_employers_deduped f
            SET multi_employer_group_id = 99999,
                is_primary_in_group = (s.rn = 1),
                group_max_workers = s.max_workers
            FROM sag_ranked s
            WHERE f.employer_id = s.employer_id
        """, commit=True)
        
        run_query(conn, """
            UPDATE f7_employers_deduped
            SET exclude_from_counts = TRUE,
                exclude_reason = 'SAG_AFTRA_SECONDARY'
            WHERE multi_employer_group_id = 99999
              AND is_primary_in_group = FALSE
        """, commit=True)
        
        result = run_query(conn, """
            SELECT COUNT(*) as excluded, SUM(latest_unit_size) as workers
            FROM f7_employers_deduped WHERE exclude_reason = 'SAG_AFTRA_SECONDARY'
        """)
        if result:
            print(f"  Excluded {result[0]['excluded']} secondaries ({result[0]['workers']:,} workers)\n")
    
    # =========================================================================
    # STEP 5: Handle other signatory/association patterns
    # =========================================================================
    print("STEP 5: Handling other signatory patterns (building trades, etc.)...")
    
    # Find patterns like "AGC", "Various", "Multiple", association agreements
    run_query(conn, """
        WITH signatory_patterns AS (
            SELECT 
                employer_id,
                COALESCE(latest_f_num::text, 'NOFNUM_' || latest_union_name) as union_key,
                latest_unit_size,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(latest_f_num::text, 'NOFNUM_' || latest_union_name)
                    ORDER BY latest_unit_size DESC, employer_id
                ) as rn,
                COUNT(*) OVER (
                    PARTITION BY COALESCE(latest_f_num::text, 'NOFNUM_' || latest_union_name)
                ) as group_size,
                MAX(latest_unit_size) OVER (
                    PARTITION BY COALESCE(latest_f_num::text, 'NOFNUM_' || latest_union_name)
                ) as max_workers
            FROM f7_employers_deduped
            WHERE (
                employer_name ILIKE '%signator%'
                OR employer_name ILIKE 'AGC%'
                OR employer_name ILIKE '%association%'
                OR employer_name ILIKE 'various%'
                OR employer_name ILIKE 'multiple%'
                OR employer_name ILIKE 'company list%'
                OR employer_name ILIKE 'MBA %'
                OR city IN ('Multiple', 'Various')
            )
            AND multi_employer_group_id IS NULL
            AND exclude_reason IS NULL
        )
        UPDATE f7_employers_deduped f
        SET multi_employer_group_id = 90000 + (
                SELECT DENSE_RANK() OVER (ORDER BY union_key)
                FROM signatory_patterns s2 
                WHERE s2.employer_id = f.employer_id
                LIMIT 1
            ),
            is_primary_in_group = (s.rn = 1),
            group_max_workers = s.max_workers
        FROM signatory_patterns s
        WHERE f.employer_id = s.employer_id
          AND s.group_size > 1
    """, commit=True)
    
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'SIGNATORY_SECONDARY'
        WHERE multi_employer_group_id BETWEEN 90000 AND 99998
          AND is_primary_in_group = FALSE
    """, commit=True)
    
    result = run_query(conn, """
        SELECT COUNT(*) as excluded, SUM(latest_unit_size) as workers
        FROM f7_employers_deduped WHERE exclude_reason = 'SIGNATORY_SECONDARY'
    """)
    if result and result[0]['excluded']:
        print(f"  Excluded {result[0]['excluded']} secondaries ({result[0]['workers']:,} workers)\n")
    else:
        print("  No additional signatory secondaries found.\n")
    
    # =========================================================================
    # STEP 6: Flag federal/public sector (separate from multi-employer)
    # =========================================================================
    print("STEP 6: Flagging federal and public sector employers...")
    
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'FEDERAL_EMPLOYER'
        WHERE (
            employer_name ILIKE '%department of veterans%'
            OR employer_name ILIKE '%veterans affairs%'
            OR employer_name ILIKE '%postal service%'
            OR employer_name ILIKE 'USPS%'
            OR employer_name ILIKE '%u.s. department%'
            OR employer_name ILIKE '%united states department%'
            OR employer_name ILIKE 'HUD/%'
        )
        AND exclude_reason IS NULL
    """, commit=True)
    
    result = run_query(conn, """
        SELECT COUNT(*) as cnt, SUM(latest_unit_size) as workers
        FROM f7_employers_deduped WHERE exclude_reason = 'FEDERAL_EMPLOYER'
    """)
    if result:
        print(f"  Federal: {result[0]['cnt']} employers, {result[0]['workers']:,} workers excluded\n")
    
    # =========================================================================
    # STEP 7: Flag corrupted data
    # =========================================================================
    print("STEP 7: Flagging corrupted records...")
    
    run_query(conn, """
        UPDATE f7_employers_deduped
        SET exclude_from_counts = TRUE,
            exclude_reason = 'DATA_CORRUPTION',
            data_quality_flag = 'CORRUPTED'
        WHERE latest_union_name ILIKE '%higher air and water%'
           OR city ILIKE '%L Enfant plaza%'
    """, commit=True)
    
    result = run_query(conn, """
        SELECT COUNT(*) as cnt FROM f7_employers_deduped WHERE exclude_reason = 'DATA_CORRUPTION'
    """)
    if result:
        print(f"  Corrupted: {result[0]['cnt']} records flagged\n")
    
    # =========================================================================
    # STEP 8: Create views
    # =========================================================================
    print("STEP 8: Creating views...")
    
    # View for BLS counting
    run_query(conn, "DROP VIEW IF EXISTS v_f7_for_bls_counts CASCADE", commit=True)
    run_query(conn, """
        CREATE VIEW v_f7_for_bls_counts AS
        SELECT *
        FROM f7_employers_deduped
        WHERE exclude_from_counts IS NOT TRUE
    """, commit=True)
    print("  Created: v_f7_for_bls_counts (only primaries)")
    
    # View for multi-employer groups (union perspective)
    run_query(conn, "DROP VIEW IF EXISTS v_multi_employer_groups CASCADE", commit=True)
    run_query(conn, """
        CREATE VIEW v_multi_employer_groups AS
        SELECT 
            multi_employer_group_id as group_id,
            latest_f_num,
            MAX(CASE WHEN is_primary_in_group THEN latest_union_name END) as union_name,
            MAX(CASE WHEN is_primary_in_group THEN employer_name END) as primary_employer,
            MAX(CASE WHEN is_primary_in_group THEN employer_id END) as primary_employer_id,
            MAX(group_max_workers) as counted_workers,
            COUNT(*) as employers_in_agreement,
            SUM(latest_unit_size) as raw_total_workers,
            STRING_AGG(employer_name, ' | ' ORDER BY latest_unit_size DESC) as all_employers
        FROM f7_employers_deduped
        WHERE multi_employer_group_id IS NOT NULL
        GROUP BY multi_employer_group_id, latest_f_num
    """, commit=True)
    print("  Created: v_multi_employer_groups (for UI - union view)")
    
    # View for employer details with group context
    run_query(conn, "DROP VIEW IF EXISTS v_employer_with_agreements CASCADE", commit=True)
    run_query(conn, """
        CREATE VIEW v_employer_with_agreements AS
        SELECT 
            e.employer_id,
            e.employer_name,
            e.city,
            e.state,
            e.naics,
            e.latest_unit_size,
            e.latest_union_name,
            e.latest_f_num,
            e.latitude,
            e.longitude,
            e.exclude_from_counts,
            e.exclude_reason,
            e.multi_employer_group_id,
            e.is_primary_in_group,
            e.group_max_workers,
            CASE 
                WHEN e.multi_employer_group_id IS NOT NULL THEN g.employers_in_agreement
                ELSE 1
            END as total_employers_in_agreement,
            CASE 
                WHEN e.multi_employer_group_id IS NOT NULL AND NOT e.is_primary_in_group 
                THEN 'Part of multi-employer agreement. Workers counted under: ' || g.primary_employer
                WHEN e.multi_employer_group_id IS NOT NULL AND e.is_primary_in_group
                THEN 'Primary record for ' || g.employers_in_agreement || ' employers in agreement'
                ELSE NULL
            END as agreement_note
        FROM f7_employers_deduped e
        LEFT JOIN v_multi_employer_groups g ON e.multi_employer_group_id = g.group_id
    """, commit=True)
    print("  Created: v_employer_with_agreements (for UI - employer view)\n")
    
    # =========================================================================
    # STEP 9: Summary Report
    # =========================================================================
    print("="*70)
    print("SUMMARY REPORT")
    print("="*70)
    
    result = run_query(conn, """
        SELECT 
            CASE 
                WHEN exclude_reason IS NOT NULL THEN 'Excluded: ' || exclude_reason
                WHEN multi_employer_group_id IS NOT NULL AND is_primary_in_group THEN 'Multi-employer PRIMARY (counted)'
                ELSE 'Regular employer (counted)'
            END as category,
            COUNT(*) as employers,
            SUM(latest_unit_size) as workers
        FROM f7_employers_deduped
        GROUP BY 1
        ORDER BY 
            CASE WHEN exclude_reason IS NULL THEN 0 ELSE 1 END,
            SUM(latest_unit_size) DESC
    """)
    
    if result:
        print(f"\n  {'Category':<45} {'Employers':>10} {'Workers':>15}")
        print(f"  {'-'*72}")
        counted_emp = 0
        counted_work = 0
        for row in result:
            cat = row['category']
            emp = row['employers']
            work = row['workers'] or 0
            if 'Excluded' not in cat:
                counted_emp += emp
                counted_work += work
            print(f"  {cat:<45} {emp:>10,} {work:>15,}")
        print(f"  {'-'*72}")
        print(f"  {'COUNTED TOWARD BLS':<45} {counted_emp:>10,} {counted_work:>15,}")
    
    # BLS comparison
    result = run_query(conn, """
        SELECT COUNT(*) as employers, SUM(latest_unit_size) as workers
        FROM v_f7_for_bls_counts
    """)
    
    if result:
        emp = result[0]['employers']
        work = result[0]['workers']
        print(f"\n  BLS RECONCILIATION:")
        print(f"    Platform workers: {work:,}")
        print(f"    BLS benchmark:    7,200,000")
        print(f"    Coverage:         {100.0 * work / 7200000:.1f}%")
    
    # Top multi-employer groups
    print(f"\n  TOP MULTI-EMPLOYER GROUPS:")
    result = run_query(conn, """
        SELECT union_name, primary_employer, employers_in_agreement, 
               counted_workers, raw_total_workers
        FROM v_multi_employer_groups
        ORDER BY raw_total_workers DESC
        LIMIT 10
    """)
    
    if result:
        print(f"  {'Union':<30} {'Employers':>10} {'Counted':>12} {'Raw Total':>12}")
        print(f"  {'-'*66}")
        for row in result:
            union = (row['union_name'] or 'Unknown')[:30]
            print(f"  {union:<30} {row['employers_in_agreement']:>10} {row['counted_workers']:>12,} {row['raw_total_workers']:>12,}")
    
    conn.close()
    
    print("\n" + "="*70)
    print("COMPLETE")
    print("="*70)
    print("""
Views created for API/UI:
  - v_f7_for_bls_counts: Use for worker totals (excludes secondaries)
  - v_multi_employer_groups: Show all employers under a union agreement
  - v_employer_with_agreements: Employer details with agreement context
""")
    
    input("Press Enter to exit...")
    return 0

if __name__ == "__main__":
    exit(main())
