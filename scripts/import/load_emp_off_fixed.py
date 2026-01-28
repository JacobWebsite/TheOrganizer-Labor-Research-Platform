"""
Load Officer/Employee Pay Data Only - Fixed
"""

import os
import psycopg2
import csv
import sys

# Fix CSV field size limit
csv.field_size_limit(10000000)

DB_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!',
    'sslmode': 'disable'
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

def safe_str(val, maxlen):
    """Safely truncate string to max length"""
    if val is None:
        return ''
    return str(val)[:maxlen]

def recreate_table(cursor):
    """Drop and recreate the table with larger fields"""
    print("Recreating table with larger fields...")
    cursor.execute("DROP TABLE IF EXISTS ar_disbursements_emp_off")
    cursor.execute("""
        CREATE TABLE ar_disbursements_emp_off (
            oid VARCHAR(50),
            emp_off_type INTEGER,
            first_name VARCHAR(150),
            middle_name VARCHAR(150),
            last_name VARCHAR(150),
            title VARCHAR(500),
            status_other_payer VARCHAR(100),
            gross_salary NUMERIC,
            allowances NUMERIC,
            official_business NUMERIC,
            other_not_rptd NUMERIC,
            total NUMERIC,
            rep_pct NUMERIC,
            pol_pct NUMERIC,
            cont_pct NUMERIC,
            gen_ovrhd_pct NUMERIC,
            admin_pct NUMERIC,
            rpt_id VARCHAR(50),
            item_num VARCHAR(50),
            load_year INTEGER
        )
    """)
    print("  Done!")

def load_emp_off(cursor, conn, year):
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
                    safe_str(get('OID'), 50),
                    safe_int(get('EMP_OFF_TYPE')),
                    safe_str(get('FIRST_NAME'), 150),
                    safe_str(get('MIDDLE_NAME'), 150),
                    safe_str(get('LAST_NAME'), 150),
                    safe_str(get('TITLE'), 500),
                    safe_str(get('STATUS_OTHER_PAYER'), 100),
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
                    safe_str(get('RPT_ID'), 50),
                    safe_str(get('ITEM_NUM'), 50),
                    year
                ))
                count += 1
                
                # Commit every 5000 records to avoid transaction issues
                if count % 5000 == 0:
                    conn.commit()
                    
            except Exception as e:
                errors += 1
                conn.rollback()  # Reset transaction on error
                if errors <= 3:
                    print(f"    Error: {str(e)[:70]}")
    
    conn.commit()
    
    if errors > 3:
        print(f"    ({errors} total errors)")
    
    return count

def main():
    print("=" * 60)
    print("  LOADING OFFICER/EMPLOYEE PAY DATA (FIXED)")
    print("=" * 60)
    print()
    
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()
    
    recreate_table(cursor)
    conn.commit()
    
    total = 0
    for year in YEARS:
        print(f"Loading {year}...", end=" ", flush=True)
        count = load_emp_off(cursor, conn, year)
        print(f"{count:,} records")
        total += count
    
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
