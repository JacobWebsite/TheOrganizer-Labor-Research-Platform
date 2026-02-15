"""
Load Officer/Employee Pay Data Only
"""

import os
import psycopg2
import csv
import sys

from db_config import get_connection
# Fix CSV field size limit for large fields
csv.field_size_limit(10000000)

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

OLMS_DIR = r"C:\Users\jakew\Downloads\Claude Ai union project\OLMS"
YEARS = range(2010, 2026)

def safe_int(val):
    if val is None or val == '':
        return None
    try:
        return int(float(val))
    except:
        return None

def safe_numeric(val):
    if val is None or val == '':
        return None
    try:
        return float(val)
    except:
        return None

def load_emp_off(cursor, year):
    """Load officer/employee compensation"""
    filename = f"ar_disbursements_emp_off_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        return 0
    
    count = 0
    errors = 0
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        # Read header
        header = f.readline().strip().split('|')
        header_map = {h: i for i, h in enumerate(header)}
        
        for line in f:
            try:
                fields = line.strip().split('|')
                
                def get(name, default=''):
                    idx = header_map.get(name)
                    if idx is not None and idx < len(fields):
                        return fields[idx]
                    return default
                
                cursor.execute("""
                    INSERT INTO ar_disbursements_emp_off (
                        oid, emp_off_type, first_name, middle_name, last_name,
                        title, status_other_payer, gross_salary, allowances,
                        official_business, other_not_rptd, total, rep_pct,
                        pol_pct, cont_pct, gen_ovrhd_pct, admin_pct, rpt_id,
                        item_num, load_year
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    get('OID'),
                    safe_int(get('EMP_OFF_TYPE')),
                    get('FIRST_NAME')[:100] if get('FIRST_NAME') else '',
                    get('MIDDLE_NAME')[:100] if get('MIDDLE_NAME') else '',
                    get('LAST_NAME')[:100] if get('LAST_NAME') else '',
                    get('TITLE')[:255] if get('TITLE') else '',
                    get('STATUS_OTHER_PAYER'),
                    safe_numeric(get('GROSS_SALARY')),
                    safe_numeric(get('ALLOWANCES')),
                    safe_numeric(get('OFFICIAL_BUSINESS')),
                    safe_numeric(get('OTHER_NOT_RPTD')),
                    safe_numeric(get('TOTAL')),
                    safe_numeric(get('REP_PCT')),
                    safe_numeric(get('POL_PCT')),
                    safe_numeric(get('CONT_PCT')),
                    safe_numeric(get('GEN_OVRHD_PCT')),
                    safe_numeric(get('ADMIN_PCT')),
                    get('RPT_ID'),
                    get('ITEM_NUM'),
                    year
                ))
                count += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"    Error: {str(e)[:60]}")
    
    if errors > 5:
        print(f"    ... and {errors - 5} more errors")
    
    return count

def main():
    print("=" * 60)
    print("  LOADING OFFICER/EMPLOYEE PAY DATA")
    print("=" * 60)
    print()
    
    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()
    
    total = 0
    for year in YEARS:
        print(f"Loading {year}...", end=" ", flush=True)
        count = load_emp_off(cursor, year)
        print(f"{count:,} records")
        total += count
        conn.commit()
    
    print()
    print(f"TOTAL: {total:,} records")
    
    print("\nCreating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_off_rpt ON ar_disbursements_emp_off(rpt_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_off_type ON ar_disbursements_emp_off(emp_off_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emp_off_year ON ar_disbursements_emp_off(load_year)")
    conn.commit()
    print("Done!")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
