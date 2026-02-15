"""
OLMS Multi-Year Data Loader
Loads 2010-2025 LM filing data into PostgreSQL
"""

import os
import psycopg2
from psycopg2 import sql
import csv

from db_config import get_connection
# Configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

OLMS_DIR = r"C:\Users\jakew\Downloads\Claude Ai union project\OLMS"

def load_year(cursor, year):
    """Load a single year's data"""
    filename = f"lm_data_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        print(f"  [SKIP] {filename} not found")
        return 0
    
    count = 0
    errors = 0
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='|')
        
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO lm_data (
                        rpt_id, yr_covered, f_num, form_type, union_name,
                        aff_abbr, aff_date, desig_name, desig_num, unit_name,
                        street, city, state, zip, members, members_eo_yr,
                        ttl_receipts, ttl_assets, ttl_disbursements, ttl_liabilities,
                        load_year
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s
                    )
                """, (
                    row.get('RPT_ID', ''),
                    safe_int(row.get('YR_COVERED')),
                    row.get('F_NUM', ''),
                    row.get('FORM_TYPE', ''),
                    row.get('UNION_NAME', '')[:255] if row.get('UNION_NAME') else '',
                    row.get('AFF_ABBR', ''),
                    row.get('EST_DATE', ''),
                    row.get('DESIG_NAME', ''),
                    row.get('DESIG_NUM', ''),
                    row.get('UNIT_NAME', ''),
                    row.get('STREET_ADR', ''),
                    row.get('CITY', ''),
                    row.get('STATE', ''),
                    row.get('ZIP', ''),
                    safe_int(row.get('MEMBERS')),
                    safe_int(row.get('MEMBERS')),  # members_eo_yr same as members
                    safe_numeric(row.get('TTL_RECEIPTS')),
                    safe_numeric(row.get('TTL_ASSETS')),
                    safe_numeric(row.get('TTL_DISBURSEMENTS')),
                    safe_numeric(row.get('TTL_LIABILITIES')),
                    year
                ))
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"    Error: {e}")
    
    return count

def safe_int(val):
    """Convert to int, return None if invalid"""
    if val is None or val == '':
        return None
    try:
        return int(float(val))
    except:
        return None

def safe_numeric(val):
    """Convert to numeric, return None if invalid"""
    if val is None or val == '':
        return None
    try:
        return float(val)
    except:
        return None

def main():
    print("=" * 60)
    print("  OLMS MULTI-YEAR DATA LOADER")
    print("=" * 60)
    print()
    
    # Connect to database
    print("Connecting to PostgreSQL...")
    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor()
        print("  Connected!")
    except Exception as e:
        print(f"  ERROR: Could not connect to database: {e}")
        print()
        print("  Make sure you updated the password in this script!")
        return
    
    print()
    
    # Load each year
    years = list(range(2010, 2026))
    total = 0
    
    for year in years:
        print(f"Loading {year}...", end=" ")
        count = load_year(cursor, year)
        total += count
        print(f"{count:,} records")
        conn.commit()
    
    print()
    print("=" * 60)
    print(f"  TOTAL LOADED: {total:,} records")
    print("=" * 60)
    
    # Create indexes
    print()
    print("Creating indexes...")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lm_fnum ON lm_data(f_num);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lm_year ON lm_data(yr_covered);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lm_state ON lm_data(state);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lm_aff ON lm_data(aff_abbr);")
    conn.commit()
    print("  Done!")
    
    # Show summary
    print()
    print("Verifying data by year:")
    cursor.execute("""
        SELECT yr_covered, COUNT(*) as filings, SUM(members) as total_members
        FROM lm_data
        GROUP BY yr_covered
        ORDER BY yr_covered
    """)
    
    print(f"  {'Year':<6} {'Filings':>10} {'Members':>15}")
    print(f"  {'-'*6} {'-'*10} {'-'*15}")
    for row in cursor.fetchall():
        yr, filings, members = row
        members_str = f"{members:,}" if members else "0"
        print(f"  {yr:<6} {filings:>10,} {members_str:>15}")
    
    cursor.close()
    conn.close()
    
    print()
    print("Done! You can now run trend analysis queries.")

if __name__ == "__main__":
    main()
