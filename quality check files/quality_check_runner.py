"""
Labor Relations Platform - Data Quality Check Runner
Runs comprehensive quality checks and generates a formatted report.

Usage: py quality_check_runner.py [--output report.md]
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import argparse
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def run_query(cur, query, description=""):
    """Run a query and return results with metadata"""
    try:
        cur.execute(query)
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return {'success': True, 'columns': columns, 'rows': rows, 'description': description}
        return {'success': True, 'columns': [], 'rows': [], 'description': description}
    except Exception as e:
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
    return str(val)

def print_table(result, max_rows=50):
    """Print results as a formatted table"""
    if not result['success']:
        print(f"  ERROR: {result['error']}")
        return
    
    if not result['rows']:
        print("  No results")
        return
    
    rows = result['rows'][:max_rows]
    columns = result['columns']
    
    # Calculate column widths
    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            val_str = format_number(row.get(col, ''))
            widths[col] = max(widths[col], len(val_str))
    
    # Print header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    
    # Print rows
    for row in rows:
        row_str = " | ".join(format_number(row.get(col, '')).ljust(widths[col]) for col in columns)
        print(f"  {row_str}")
    
    if len(result['rows']) > max_rows:
        print(f"  ... and {len(result['rows']) - max_rows} more rows")

def run_employer_checks(cur):
    """Run employer data quality checks"""
    print("\n" + "="*80)
    print("SECTION 1: EMPLOYER DATA QUALITY")
    print("="*80)
    
    # 1.1 Dashboard
    print("\n### 1.1 Employer Quality Dashboard")
    result = run_query(cur, """
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
    result = run_query(cur, """
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
    result = run_query(cur, """
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
    result = run_query(cur, """
        SELECT employer_name, city, state, latest_unit_size as workers, latest_union_name
        FROM f7_employers_deduped
        WHERE latest_unit_size > 50000
        ORDER BY latest_unit_size DESC
        LIMIT 15
    """)
    print_table(result)

def run_union_checks(cur):
    """Run union data quality checks"""
    print("\n" + "="*80)
    print("SECTION 2: UNION DATA QUALITY")
    print("="*80)
    
    # 2.1 Dashboard
    print("\n### 2.1 Union Quality Dashboard")
    result = run_query(cur, """
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
    
    # 2.2 Hierarchy
    print("\n### 2.2 Hierarchy Level Distribution")
    result = run_query(cur, """
        SELECT 
            COALESCE(hierarchy_level, 'UNCLASSIFIED') as level,
            COUNT(*) as unions,
            SUM(members) as raw_members,
            SUM(CASE WHEN count_members THEN members ELSE 0 END) as counted
        FROM union_hierarchy
        GROUP BY hierarchy_level
        ORDER BY SUM(members) DESC
    """)
    print_table(result)
    
    # 2.3 Sector Classification
    print("\n### 2.3 Sector Classification")
    result = run_query(cur, """
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
    result = run_query(cur, """
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
    print_table(result)

def run_crossdataset_checks(cur):
    """Run cross-dataset validation checks"""
    print("\n" + "="*80)
    print("SECTION 3: CROSS-DATASET VALIDATION")
    print("="*80)
    
    # 3.1 F-7 to OLMS
    print("\n### 3.1 F-7 to OLMS Match Rate")
    result = run_query(cur, """
        SELECT 
            COUNT(*) as total_employers,
            SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) as matched,
            ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as match_pct,
            SUM(latest_unit_size) as total_workers,
            SUM(CASE WHEN latest_union_name IS NOT NULL THEN latest_unit_size ELSE 0 END) as matched_workers
        FROM f7_employers_deduped
    """)
    print_table(result)
    
    # 3.2 OSHA Match
    print("\n### 3.2 OSHA to F-7 Match Summary")
    result = run_query(cur, """
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
    result = run_query(cur, """
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
    result = run_query(cur, """
        SELECT 
            COUNT(*) as elections,
            SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
            ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
            SUM(eligible_voters) as total_voters,
            MIN(election_date) as earliest,
            MAX(election_date) as latest
        FROM nlrb_elections
    """)
    print_table(result)

def run_bls_alignment(cur):
    """Run BLS benchmark alignment checks"""
    print("\n" + "="*80)
    print("SECTION 4: BLS BENCHMARK ALIGNMENT")
    print("="*80)
    
    # 4.1 Member Reconciliation
    print("\n### 4.1 Member Count Reconciliation")
    result = run_query(cur, """
        SELECT 'Raw OLMS Total' as category, SUM(members) as members FROM unions_master
        UNION ALL
        SELECT 'Deduplicated (counted)', SUM(members) FROM union_hierarchy WHERE count_members = TRUE
        UNION ALL
        SELECT 'BLS Benchmark 2024', 14300000
    """)
    print_table(result)
    
    # 4.2 Private Sector
    print("\n### 4.2 Private Sector Alignment")
    result = run_query(cur, """
        WITH private AS (
            SELECT SUM(latest_unit_size) as workers FROM f7_employers_deduped
        )
        SELECT 
            workers as platform_workers,
            7200000 as bls_benchmark,
            ROUND(100.0 * workers / 7200000, 1) as coverage_pct
        FROM private
    """)
    print_table(result)

def run_data_freshness(cur):
    """Run data freshness checks"""
    print("\n" + "="*80)
    print("SECTION 5: DATA FRESHNESS")
    print("="*80)
    
    print("\n### 5.1 Data Source Freshness")
    result = run_query(cur, """
        SELECT 'OLMS LM Filings' as source, MAX(yr_covered) as latest, COUNT(*) as records
        FROM unions_master
        UNION ALL
        SELECT 'NLRB Elections', EXTRACT(YEAR FROM MAX(election_date))::int, COUNT(*)
        FROM nlrb_elections
        UNION ALL
        SELECT 'OSHA Establishments', EXTRACT(YEAR FROM MAX(last_inspection_date))::int, COUNT(*)
        FROM osha_establishments
        UNION ALL
        SELECT 'Voluntary Recognition', EXTRACT(YEAR FROM MAX(date_received))::int, COUNT(*)
        FROM nlrb_voluntary_recognition
    """)
    print_table(result)

def run_scorecard(cur):
    """Run final quality scorecard"""
    print("\n" + "="*80)
    print("SECTION 6: QUALITY SCORECARD")
    print("="*80)
    
    print("\n### Overall Quality Metrics")
    
    metrics = []
    
    # Employer NAICS
    cur.execute("SELECT ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) FROM f7_employers_deduped")
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 80 else ("⚠️ FAIR" if val >= 60 else "❌ POOR")
    metrics.append(('Employer NAICS Coverage', val, 80, status))
    
    # Geocoding
    cur.execute("SELECT ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) FROM f7_employers_deduped")
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 75 else ("⚠️ FAIR" if val >= 60 else "❌ POOR")
    metrics.append(('Employer Geocoding', val, 75, status))
    
    # Union Match
    cur.execute("SELECT ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) FROM f7_employers_deduped")
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 90 else ("⚠️ FAIR" if val >= 75 else "❌ POOR")
    metrics.append(('Employer-Union Match', val, 90, status))
    
    # Affiliation
    cur.execute("SELECT ROUND(100.0 * SUM(CASE WHEN aff_abbr IS NOT NULL AND aff_abbr != '' THEN 1 ELSE 0 END) / COUNT(*), 1) FROM unions_master")
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 90 else ("⚠️ FAIR" if val >= 75 else "❌ POOR")
    metrics.append(('Union Affiliation', val, 90, status))
    
    # Sector
    cur.execute("SELECT ROUND(100.0 * SUM(CASE WHEN sector IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) FROM unions_master")
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 95 else ("⚠️ FAIR" if val >= 85 else "❌ POOR")
    metrics.append(('Union Sector Class', val, 95, status))
    
    # OSHA Match
    cur.execute("""
        SELECT ROUND(100.0 * COUNT(DISTINCT f7_employer_id) / (SELECT COUNT(*) FROM f7_employers_deduped), 1)
        FROM osha_f7_matches
    """)
    val = cur.fetchone()[0] or 0
    status = "✅ GOOD" if val >= 40 else ("⚠️ FAIR" if val >= 25 else "❌ POOR")
    metrics.append(('OSHA-F7 Linkage', val, 40, status))
    
    # Print scorecard
    print(f"  {'Metric':<25} {'Value':>8} {'Target':>8} {'Status':<12}")
    print(f"  {'-'*55}")
    for metric, value, target, status in metrics:
        print(f"  {metric:<25} {value:>7.1f}% {target:>7}% {status:<12}")

def main():
    parser = argparse.ArgumentParser(description='Run data quality checks')
    parser.add_argument('--output', '-o', help='Output file (markdown)')
    args = parser.parse_args()
    
    print(f"""
================================================================================
        LABOR RELATIONS PLATFORM - DATA QUALITY REPORT
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================
""")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        run_employer_checks(cur)
        run_union_checks(cur)
        run_crossdataset_checks(cur)
        run_bls_alignment(cur)
        run_data_freshness(cur)
        run_scorecard(cur)
        
        conn.close()
        
        print("\n" + "="*80)
        print("QUALITY CHECK COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
