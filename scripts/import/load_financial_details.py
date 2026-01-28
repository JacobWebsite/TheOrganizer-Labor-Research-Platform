"""
OLMS Financial Detail Loader
Loads investments, disbursements, officer/employee pay, and membership data
"""

import os
import psycopg2
import csv

# Configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!',  # Your password
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

def create_tables(cursor):
    """Create all detail tables"""
    
    # Officer/Employee compensation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ar_disbursements_emp_off (
            oid VARCHAR(20),
            emp_off_type INTEGER,
            first_name VARCHAR(100),
            middle_name VARCHAR(100),
            last_name VARCHAR(100),
            title VARCHAR(255),
            status_other_payer VARCHAR(10),
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
            rpt_id VARCHAR(20),
            item_num VARCHAR(20),
            load_year INTEGER
        )
    """)
    print("  Created: ar_disbursements_emp_off")
    
    # Membership breakdown
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ar_membership (
            oid VARCHAR(20),
            membership_type INTEGER,
            category VARCHAR(255),
            number INTEGER,
            voting_eligibility VARCHAR(10),
            rpt_id VARCHAR(20),
            load_year INTEGER
        )
    """)
    print("  Created: ar_membership")
    
    # Investments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ar_assets_investments (
            oid VARCHAR(20),
            inv_type INTEGER,
            name VARCHAR(255),
            amount NUMERIC,
            rpt_id VARCHAR(20),
            load_year INTEGER
        )
    """)
    print("  Created: ar_assets_investments")
    
    # Disbursements by category
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ar_disbursements_total (
            rpt_id VARCHAR(20),
            representational NUMERIC,
            political NUMERIC,
            contributions NUMERIC,
            general_overhead NUMERIC,
            union_administration NUMERIC,
            withheld NUMERIC,
            members NUMERIC,
            supplies NUMERIC,
            fees NUMERIC,
            administration NUMERIC,
            direct_taxes NUMERIC,
            strike_benefits NUMERIC,
            per_capita_tax NUMERIC,
            to_officers NUMERIC,
            investments NUMERIC,
            benefits NUMERIC,
            loans_made NUMERIC,
            loans_payment NUMERIC,
            affiliates NUMERIC,
            other_disbursements NUMERIC,
            to_employees NUMERIC,
            load_year INTEGER
        )
    """)
    print("  Created: ar_disbursements_total")

def load_emp_off(cursor, year):
    """Load officer/employee compensation"""
    filename = f"ar_disbursements_emp_off_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        return 0
    
    count = 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='|')
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO ar_disbursements_emp_off (
                        oid, emp_off_type, first_name, middle_name, last_name,
                        title, status_other_payer, gross_salary, allowances,
                        official_business, other_not_rptd, total, rep_pct,
                        pol_pct, cont_pct, gen_ovrhd_pct, admin_pct, rpt_id,
                        item_num, load_year
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    row.get('OID'),
                    safe_int(row.get('EMP_OFF_TYPE')),
                    row.get('FIRST_NAME', '')[:100],
                    row.get('MIDDLE_NAME', '')[:100],
                    row.get('LAST_NAME', '')[:100],
                    row.get('TITLE', '')[:255],
                    row.get('STATUS_OTHER_PAYER'),
                    safe_numeric(row.get('GROSS_SALARY')),
                    safe_numeric(row.get('ALLOWANCES')),
                    safe_numeric(row.get('OFFICIAL_BUSINESS')),
                    safe_numeric(row.get('OTHER_NOT_RPTD')),
                    safe_numeric(row.get('TOTAL')),
                    safe_numeric(row.get('REP_PCT')),
                    safe_numeric(row.get('POL_PCT')),
                    safe_numeric(row.get('CONT_PCT')),
                    safe_numeric(row.get('GEN_OVRHD_PCT')),
                    safe_numeric(row.get('ADMIN_PCT')),
                    row.get('RPT_ID'),
                    row.get('ITEM_NUM'),
                    year
                ))
                count += 1
            except Exception as e:
                pass
    return count

def load_membership(cursor, year):
    """Load membership breakdown"""
    filename = f"ar_membership_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        return 0
    
    count = 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='|')
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO ar_membership (
                        oid, membership_type, category, number,
                        voting_eligibility, rpt_id, load_year
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    row.get('OID'),
                    safe_int(row.get('MEMBERSHIP_TYPE')),
                    row.get('CATEGORY', '')[:255],
                    safe_int(row.get('NUMBER')),
                    row.get('VOTING_ELIGIBILITY'),
                    row.get('RPT_ID'),
                    year
                ))
                count += 1
            except:
                pass
    return count

def load_investments(cursor, year):
    """Load investment data"""
    filename = f"ar_assets_investments_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        return 0
    
    count = 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='|')
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO ar_assets_investments (
                        oid, inv_type, name, amount, rpt_id, load_year
                    ) VALUES (%s,%s,%s,%s,%s,%s)
                """, (
                    row.get('OID'),
                    safe_int(row.get('INV_TYPE')),
                    row.get('NAME', '')[:255],
                    safe_numeric(row.get('AMOUNT')),
                    row.get('RPT_ID'),
                    year
                ))
                count += 1
            except:
                pass
    return count

def load_disbursements_total(cursor, year):
    """Load disbursement category totals"""
    filename = f"ar_disbursements_total_data_{year}.txt"
    filepath = os.path.join(OLMS_DIR, filename)
    
    if not os.path.exists(filepath):
        return 0
    
    count = 0
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter='|')
        for row in reader:
            try:
                cursor.execute("""
                    INSERT INTO ar_disbursements_total (
                        rpt_id, representational, political, contributions,
                        general_overhead, union_administration, withheld, members,
                        supplies, fees, administration, direct_taxes, strike_benefits,
                        per_capita_tax, to_officers, investments, benefits,
                        loans_made, loans_payment, affiliates, other_disbursements,
                        to_employees, load_year
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    row.get('RPT_ID'),
                    safe_numeric(row.get('REPRESENTATIONAL')),
                    safe_numeric(row.get('POLITICAL')),
                    safe_numeric(row.get('CONTRIBUTIONS')),
                    safe_numeric(row.get('GENERAL_OVERHEAD')),
                    safe_numeric(row.get('UNION_ADMINISTRATION')),
                    safe_numeric(row.get('WITHHELD')),
                    safe_numeric(row.get('MEMBERS')),
                    safe_numeric(row.get('SUPPLIES')),
                    safe_numeric(row.get('FEES')),
                    safe_numeric(row.get('ADMINISTRATION')),
                    safe_numeric(row.get('DIRECT_TAXES')),
                    safe_numeric(row.get('STRIKE_BENEFITS')),
                    safe_numeric(row.get('PER_CAPITA_TAX')),
                    safe_numeric(row.get('TO_OFFICERS')),
                    safe_numeric(row.get('INVESTMENTS')),
                    safe_numeric(row.get('BENEFITS')),
                    safe_numeric(row.get('LOANS_MADE')),
                    safe_numeric(row.get('LOANS_PAYMENT')),
                    safe_numeric(row.get('AFFILIATES')),
                    safe_numeric(row.get('OTHER_DISBURSEMENTS')),
                    safe_numeric(row.get('TO_EMPLOYEES')),
                    year
                ))
                count += 1
            except:
                pass
    return count

def create_indexes(cursor):
    """Create indexes for faster queries"""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_emp_off_rpt ON ar_disbursements_emp_off(rpt_id)",
        "CREATE INDEX IF NOT EXISTS idx_emp_off_type ON ar_disbursements_emp_off(emp_off_type)",
        "CREATE INDEX IF NOT EXISTS idx_emp_off_year ON ar_disbursements_emp_off(load_year)",
        "CREATE INDEX IF NOT EXISTS idx_membership_rpt ON ar_membership(rpt_id)",
        "CREATE INDEX IF NOT EXISTS idx_membership_cat ON ar_membership(category)",
        "CREATE INDEX IF NOT EXISTS idx_membership_year ON ar_membership(load_year)",
        "CREATE INDEX IF NOT EXISTS idx_invest_rpt ON ar_assets_investments(rpt_id)",
        "CREATE INDEX IF NOT EXISTS idx_invest_year ON ar_assets_investments(load_year)",
        "CREATE INDEX IF NOT EXISTS idx_disb_tot_rpt ON ar_disbursements_total(rpt_id)",
        "CREATE INDEX IF NOT EXISTS idx_disb_tot_year ON ar_disbursements_total(load_year)",
    ]
    for idx in indexes:
        cursor.execute(idx)

def main():
    print("=" * 60)
    print("  OLMS FINANCIAL DETAIL LOADER")
    print("=" * 60)
    print()
    
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()
    
    print("Creating tables...")
    create_tables(cursor)
    conn.commit()
    print()
    
    # Load each data type for each year
    tables = [
        ("Officer/Employee Pay", load_emp_off),
        ("Membership", load_membership),
        ("Investments", load_investments),
        ("Disbursements Total", load_disbursements_total),
    ]
    
    for table_name, load_func in tables:
        print(f"\nLoading {table_name}...")
        total = 0
        for year in YEARS:
            count = load_func(cursor, year)
            if count > 0:
                print(f"  {year}: {count:,} records")
                total += count
            conn.commit()
        print(f"  TOTAL: {total:,} records")
    
    print("\nCreating indexes...")
    create_indexes(cursor)
    conn.commit()
    print("  Done!")
    
    # Summary stats
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    
    cursor.execute("SELECT COUNT(*) FROM ar_disbursements_emp_off")
    print(f"  Officer/Employee records: {cursor.fetchone()[0]:,}")
    
    cursor.execute("SELECT COUNT(*) FROM ar_membership")
    print(f"  Membership records: {cursor.fetchone()[0]:,}")
    
    cursor.execute("SELECT COUNT(*) FROM ar_assets_investments")
    print(f"  Investment records: {cursor.fetchone()[0]:,}")
    
    cursor.execute("SELECT COUNT(*) FROM ar_disbursements_total")
    print(f"  Disbursement records: {cursor.fetchone()[0]:,}")
    
    cursor.close()
    conn.close()
    
    print("\nDone! Run sample queries to explore the data.")

if __name__ == "__main__":
    main()
