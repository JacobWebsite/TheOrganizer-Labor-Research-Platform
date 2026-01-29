"""
Labor Relations Platform - Data Quality Check Runner v2
Runs comprehensive quality checks and generates a formatted report.
Fixed: Error handling and column name verification.

Usage: py quality_check_runner_v2.py
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

def run_query(conn, query, description=""):
    """Run a query and return results - handles errors gracefully"""
    cur = conn.cursor()
    try:
        cur.execute(query)
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return {'success': True, 'columns': columns, 'rows': rows, 'description': description}
        return {'success': True, 'columns': [], 'rows': [], 'description': description}
    except Exception as e:
        conn.rollback()  # Reset transaction so next query can run
        return {'success': False, 'error': str(e), 'description': description}

def format_number(val):
    """Format numbers with commas"""
    if val is None:
        return 'NULL'
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val == int(val):
            return f"{int(val):,}"
        elif isinstance(val, float):
            return f"{val:,.2f}"
        return f"{val:,}"
    return str(val)[:50]  # Truncate long strings

def print_table(result, max_rows=50):
    """Print results as a formatted table"""
    if not result['success']:
        print(f"  ERROR: {result['error'][:100]}")
        return
    
    if not result['rows']:
        print("  No results")
        return
    
    rows = result['rows'][:max_rows]
    columns = result['columns']
    
    # Calculate column widths (cap at 40)
    widths = {col: min(len(col), 40) for col in columns}
    for row in rows:
        for col in columns:
            val_str = format_number(row.get(col, ''))[:40]
            widths[col] = min(max(widths[col], len(val_str)), 40)
    
    # Print header
    header = " | ".join(col[:widths[col]].ljust(widths[col]) for col in columns)
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    
    # Print rows
    for row in rows:
        row_str = " | ".join(format_number(row.get(col, ''))[:widths[col]].ljust(widths[col]) for col in columns)
        print(f"  {row_str}")
    
    if len(result['rows']) > max_rows:
        print(f"  ... and {len(result['rows']) - max_rows} more rows")

def check_table_columns(conn, table_name):
    """Check what columns exist in a table"""
    result = run_query(conn, f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' 
        ORDER BY ordinal_position
    """)
    if result['success']:
        return [r['column_name'] for r in result['rows']]
    return []

def run_employer_checks(conn):
    """Run employer data quality checks"""
    print("\n" + "="*80)
    print("SECTION 1: EMPLOYER DATA QUALITY")
    print("="*80)
    
    # 1.1 Dashboard
    print("\n### 1.1 Employer Quality Dashboard")
    result = run_query(conn, """
        SELECT 
            COUNT(*) as total_employers,
            COUNT(DISTINCT employer_id) as unique_ids,
            SUM(CASE WHEN naics IS NULL OR naics = '' THEN 1 ELSE 0 END) as missing_naics,
            ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL AND naics != '' THEN 1 ELSE 0 END) / COUNT(*), 1) as naics_pct,
            SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) as missing_geocode,
            ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as geocode_pct,
            SUM(CASE WHEN latest_union_name IS NULL THEN 1 ELSE 0 END) as no_union_link,
            COUNT(DISTINCT state) as states,
            SUM(latest_unit_size) as total_workers
        FROM f7_employers_deduped
    """)
    print_table(result)
    
    # 1.2 Duplicates
    print("\n### 1.2 Potential Duplicate Employers (Top 20)")
    result = run_query(conn, """
        SELECT 
            UPPER(TRIM(employer_name)) as name,
            UPPER(TRIM(city)) as city,
            state,
            COUNT(*) as duplicates,
            SUM(latest_unit_size) as workers
        FROM f7_employers_deduped
        WHERE employer_name IS NOT NULL
        GROUP BY UPPER(TRIM(employer_name)), UPPER(TRIM(city)), state
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """)
    print_table(result)
    
    # 1.3 NAICS Distribution
    print("\n### 1.3 NAICS Distribution")
    result = run_query(conn, """
        SELECT 
            COALESCE(naics, 'MISSING') as naics,
            COUNT(*) as employers,
            SUM(latest_unit_size) as workers,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
        FROM f7_employers_deduped
        GROUP BY naics
        ORDER BY COUNT(*) DESC
    """)
    print_table(result)
    
    # 1.4 Large Worker Counts
    print("\n### 1.4 Employers with >50K Workers (Review for Accuracy)")
    result = run_query(conn, """
        SELECT employer_name, city, state, latest_unit_size as workers, latest_union_name
        FROM f7_employers_deduped
        WHERE latest_unit_size > 50000
        ORDER BY latest_unit_size DESC
        LIMIT 15
    """)
    print_table(result)

def run_union_checks(conn):
    """Run union data quality checks"""
    print("\n" + "="*80)
    print("SECTION 2: UNION DATA QUALITY")
    print("="*80)
    
    # First check what columns exist in unions_master
    print("\n### 2.0 Checking unions_master columns...")
    um_cols = check_table_columns(conn, 'unions_master')
    print(f"  Found columns: {', '.join(um_cols[:15])}{'...' if len(um_cols) > 15 else ''}")
    
    # 2.1 Dashboard - adapt based on available columns
    print("\n### 2.1 Union Quality Dashboard")
    result = run_query(conn, """
        SELECT 
            COUNT(*) as total_unions,
            SUM(members) as raw_members,
            SUM(CASE WHEN members < 0 THEN 1 ELSE 0 END) as negative_members,
            SUM(CASE WHEN members > 1000000 THEN 1 ELSE 0 END) as over_1m,
            SUM(CASE WHEN aff_abbr IS NULL OR aff_abbr = '' THEN 1 ELSE 0 END) as no_affiliation,
            COUNT(DISTINCT aff_abbr) as unique_affiliations,
            COUNT(DISTINCT sector) as unique_sectors
        FROM unions_master
    """)
    print_table(result)
    
    # Check union_hierarchy columns
    print("\n### 2.2 Checking union_hierarchy table...")
    uh_cols = check_table_columns(conn, 'union_hierarchy')
    if uh_cols:
        print(f"  Found columns: {', '.join(uh_cols)}")
        
        # Build query based on actual columns
        if 'hierarchy_level' in uh_cols and 'count_members' in uh_cols:
            # Need to find the member count column
            member_col = 'member_count' if 'member_count' in uh_cols else ('total_members' if 'total_members' in uh_cols else None)
            
            if member_col:
                print(f"\n### 2.2b Hierarchy Level Distribution (using {member_col})")
                result = run_query(conn, f"""
                    SELECT 
                        COALESCE(hierarchy_level, 'UNCLASSIFIED') as level,
                        COUNT(*) as unions,
                        SUM({member_col}) as total_members,
                        SUM(CASE WHEN count_members THEN {member_col} ELSE 0 END) as counted
                    FROM union_hierarchy
                    GROUP BY hierarchy_level
                    ORDER BY SUM({member_col}) DESC NULLS LAST
                """)
                print_table(result)
            else:
                print("  Could not find member count column in union_hierarchy")
    else:
        print("  union_hierarchy table not found or empty")
    
    # 2.3 Sector Classification
    print("\n### 2.3 Sector Classification")
    result = run_query(conn, """
        SELECT 
            COALESCE(sector, 'MISSING') as sector,
            COUNT(*) as unions,
            SUM(members) as members
        FROM unions_master
        GROUP BY sector
        ORDER BY SUM(members) DESC
    """)
    print_table(result)
    
    # 2.4 Top Affiliations
    print("\n### 2.4 Top 20 Affiliations by Members")
    
    # Check if f7_employer_count exists
    if 'f7_employer_count' in um_cols:
        result = run_query(conn, """
            SELECT 
                aff_abbr,
                COUNT(*) as locals,
                SUM(members) as members,
                SUM(f7_employer_count) as employers
            FROM unions_master
            WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
            GROUP BY aff_abbr
            ORDER BY SUM(members) DESC
            LIMIT 20
        """)
    else:
        result = run_query(conn, """
            SELECT 
                aff_abbr,
                COUNT(*) as locals,
                SUM(members) as members
            FROM unions_master
            WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
            GROUP BY aff_abbr
            ORDER BY SUM(members) DESC
            LIMIT 20
        """)
    print_table(result)

def run_crossdataset_checks(conn):
    """Run cross-dataset validation checks"""
    print("\n" + "="*80)
    print("SECTION 3: CROSS-DATASET VALIDATION")
    print("="*80)
    
    # 3.1 F-7 to OLMS
    print("\n### 3.1 F-7 to OLMS Match Rate")
    result = run_query(conn, """
        SELECT 
            COUNT(*) as total_employers,
            SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) as matched,
            ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as match_pct,
            SUM(latest_unit_size) as total_workers,
            SUM(CASE WHEN latest_union_name IS NOT NULL THEN latest_unit_size ELSE 0 END) as matched_workers
        FROM f7_employers_deduped
    """)
    print_table(result)
    
    # 3.2 OSHA Match - check if table exists first
    print("\n### 3.2 OSHA to F-7 Match Summary")
    result = run_query(conn, """
        SELECT 
            COUNT(DISTINCT f7_employer_id) as f7_with_osha,
            (SELECT COUNT(*) FROM f7_employers_deduped) as total_f7,
            ROUND(100.0 * COUNT(DISTINCT f7_employer_id) / (SELECT COUNT(*) FROM f7_employers_deduped), 2) as coverage_pct,
            COUNT(*) as total_matches,
            ROUND(AVG(match_confidence), 3) as avg_confidence
        FROM osha_f7_matches
    """)
    print_table(result)
    
    # 3.3 OSHA by Method
    print("\n### 3.3 OSHA Match Quality by Method")
    result = run_query(conn, """
        SELECT 
            match_method,
            COUNT(*) as matches,
            COUNT(DISTINCT f7_employer_id) as unique_f7,
            ROUND(AVG(match_confidence), 3) as avg_conf
        FROM osha_f7_matches
        GROUP BY match_method
        ORDER BY COUNT(*) DESC
    """)
    print_table(result)
    
    # 3.4 NLRB Elections
    print("\n### 3.4 NLRB Election Summary")
    result = run_query(conn, """
        SELECT 
            COUNT(*) as elections,
            SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
            ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
            SUM(eligible_voters) as total_voters,
            MIN(election_date)::date as earliest,
            MAX(election_date)::date as latest
        FROM nlrb_elections
    """)
    print_table(result)
    
    # 3.5 Voluntary Recognition
    print("\n### 3.5 Voluntary Recognition Summary")
    result = run_query(conn, """
        SELECT 
            COUNT(*) as total_cases,
            SUM(num_employees) as workers,
            SUM(CASE WHEN matched_employer_id IS NOT NULL THEN 1 ELSE 0 END) as matched_to_f7,
            ROUND(100.0 * SUM(CASE WHEN matched_employer_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as match_pct
        FROM nlrb_voluntary_recognition
    """)
    print_table(result)

def run_bls_alignment(conn):
    """Run BLS benchmark alignment checks"""
    print("\n" + "="*80)
    print("SECTION 4: BLS BENCHMARK ALIGNMENT")
    print("="*80)
    
    # 4.1 Member Reconciliation
    print("\n### 4.1 Member Count Reconciliation")
    result = run_query(conn, """
        SELECT 'Raw OLMS Total' as category, SUM(members)::bigint as members FROM unions_master
        UNION ALL
        SELECT 'BLS Benchmark 2024', 14300000
        ORDER BY members DESC
    """)
    print_table(result)
    
    # Check if union_hierarchy has the data we need for dedup count
    uh_cols = check_table_columns(conn, 'union_hierarchy')
    if 'count_members' in uh_cols:
        member_col = 'member_count' if 'member_count' in uh_cols else 'total_members'
        if member_col in uh_cols:
            print("\n### 4.1b Deduplicated Member Count")
            result = run_query(conn, f"""
                SELECT 
                    SUM(CASE WHEN count_members THEN {member_col} ELSE 0 END)::bigint as deduplicated_members
                FROM union_hierarchy
            """)
            print_table(result)
    
    # 4.2 Private Sector
    print("\n### 4.2 Private Sector Workers (F-7 Data)")
    result = run_query(conn, """
        SELECT 
            SUM(latest_unit_size)::bigint as platform_workers,
            7200000 as bls_private_benchmark,
            ROUND(100.0 * SUM(latest_unit_size) / 7200000, 1) as coverage_pct
        FROM f7_employers_deduped
    """)
    print_table(result)

def run_data_freshness(conn):
    """Run data freshness checks"""
    print("\n" + "="*80)
    print("SECTION 5: DATA FRESHNESS")
    print("="*80)
    
    print("\n### 5.1 Data Source Freshness")
    result = run_query(conn, """
        SELECT 'OLMS Unions' as source, MAX(yr_covered)::int as latest_year, COUNT(*)::int as records
        FROM unions_master
        UNION ALL
        SELECT 'NLRB Elections', EXTRACT(YEAR FROM MAX(election_date))::int, COUNT(*)::int
        FROM nlrb_elections
        UNION ALL
        SELECT 'OSHA Establishments', EXTRACT(YEAR FROM MAX(last_inspection_date))::int, COUNT(*)::int
        FROM osha_establishments
        UNION ALL
        SELECT 'Voluntary Recognition', EXTRACT(YEAR FROM MAX(date_received))::int, COUNT(*)::int
        FROM nlrb_voluntary_recognition
    """)
    print_table(result)
    
    print("\n### 5.2 Union Filing Year Distribution (Recent)")
    result = run_query(conn, """
        SELECT 
            yr_covered as year,
            COUNT(*) as unions,
            SUM(members)::bigint as members
        FROM unions_master
        WHERE yr_covered >= 2020
        GROUP BY yr_covered
        ORDER BY yr_covered DESC
    """)
    print_table(result)

def run_scorecard(conn):
    """Run final quality scorecard"""
    print("\n" + "="*80)
    print("SECTION 6: QUALITY SCORECARD")
    print("="*80)
    
    print("\n### Overall Quality Metrics\n")
    
    metrics = []
    
    # Employer NAICS
    result = run_query(conn, "SELECT ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as val FROM f7_employers_deduped")
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 80 else ("FAIR" if val >= 60 else "POOR")
        metrics.append(('Employer NAICS Coverage', val, 80, status))
    
    # Geocoding
    result = run_query(conn, "SELECT ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as val FROM f7_employers_deduped")
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 75 else ("FAIR" if val >= 60 else "POOR")
        metrics.append(('Employer Geocoding', val, 75, status))
    
    # Union Match
    result = run_query(conn, "SELECT ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as val FROM f7_employers_deduped")
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 90 else ("FAIR" if val >= 75 else "POOR")
        metrics.append(('Employer-Union Match', val, 90, status))
    
    # Affiliation
    result = run_query(conn, "SELECT ROUND(100.0 * SUM(CASE WHEN aff_abbr IS NOT NULL AND aff_abbr != '' THEN 1 ELSE 0 END) / COUNT(*), 1) as val FROM unions_master")
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 90 else ("FAIR" if val >= 75 else "POOR")
        metrics.append(('Union Affiliation', val, 90, status))
    
    # Sector
    result = run_query(conn, "SELECT ROUND(100.0 * SUM(CASE WHEN sector IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as val FROM unions_master")
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 95 else ("FAIR" if val >= 85 else "POOR")
        metrics.append(('Union Sector Class', val, 95, status))
    
    # OSHA Match
    result = run_query(conn, """
        SELECT ROUND(100.0 * COUNT(DISTINCT f7_employer_id) / (SELECT COUNT(*) FROM f7_employers_deduped), 1) as val
        FROM osha_f7_matches
    """)
    if result['success'] and result['rows']:
        val = float(result['rows'][0]['val'] or 0)
        status = "GOOD" if val >= 40 else ("FAIR" if val >= 25 else "POOR")
        metrics.append(('OSHA-F7 Linkage', val, 40, status))
    
    # Print scorecard
    print(f"  {'Metric':<25} {'Value':>8} {'Target':>8} {'Status':<10}")
    print(f"  {'-'*55}")
    for metric, value, target, status in metrics:
        print(f"  {metric:<25} {value:>7.1f}% {target:>7}% {status:<10}")

def run_issues_check(conn):
    """Check for known data quality issues"""
    print("\n" + "="*80)
    print("SECTION 7: KNOWN ISSUES CHECK")
    print("="*80)
    
    # Check for SAG-AFTRA multi-employer overcounting
    print("\n### 7.1 SAG-AFTRA Multi-Employer (Potential Overcounting)")
    result = run_query(conn, """
        SELECT employer_name, city, state, latest_unit_size as workers
        FROM f7_employers_deduped
        WHERE employer_name ILIKE '%SAG-AFTRA%' 
           OR employer_name ILIKE '%signator%'
           OR employer_name ILIKE '%all signatories%'
        ORDER BY latest_unit_size DESC
        LIMIT 10
    """)
    print_table(result)
    
    # Check for federal employers that shouldn't be in F-7
    print("\n### 7.2 Federal Employers in F-7 (Should Be Excluded)")
    result = run_query(conn, """
        SELECT employer_name, city, state, latest_unit_size as workers
        FROM f7_employers_deduped
        WHERE employer_name ILIKE '%department of%'
           OR employer_name ILIKE '%veterans affairs%'
           OR employer_name ILIKE '%postal service%'
           OR employer_name ILIKE 'USPS%'
           OR employer_name ILIKE '%HUD/%'
        ORDER BY latest_unit_size DESC
        LIMIT 10
    """)
    print_table(result)
    
    # Check top employers missing NAICS
    print("\n### 7.3 Top Employers Missing NAICS")
    result = run_query(conn, """
        SELECT employer_name, city, state, latest_unit_size as workers
        FROM f7_employers_deduped
        WHERE naics IS NULL OR naics = ''
        ORDER BY latest_unit_size DESC
        LIMIT 15
    """)
    print_table(result)

def main():
    print(f"""
================================================================================
        LABOR RELATIONS PLATFORM - DATA QUALITY REPORT
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================
""")
    
    try:
        conn = get_connection()
        print("  Database connected successfully!")
        
        run_employer_checks(conn)
        run_union_checks(conn)
        run_crossdataset_checks(conn)
        run_bls_alignment(conn)
        run_data_freshness(conn)
        run_scorecard(conn)
        run_issues_check(conn)
        
        conn.close()
        
        print("\n" + "="*80)
        print("QUALITY CHECK COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    result = main()
    input("\nPress Enter to exit...")
    exit(result)
