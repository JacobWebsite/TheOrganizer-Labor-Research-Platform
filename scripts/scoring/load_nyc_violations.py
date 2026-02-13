import os
"""
Load NYC Comptroller Employer Violations Dashboard data into PostgreSQL
Source: https://comptroller.nyc.gov/services/for-the-public/employer-violations-dashboard/
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import numpy as np

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

# Load Excel file
xlsx = pd.ExcelFile('data/nyc_employer_violations.xlsx')

def clean_df(df):
    """Clean dataframe for database insertion"""
    # Replace NaN with None
    df = df.replace({np.nan: None})
    # Replace whitespace-only strings with None
    df = df.replace(r'^\s*$', None, regex=True)
    # Clean column names
    df.columns = [c.split('(')[0].strip().lower().replace(' ', '_').replace('-', '_').replace('/', '_').replace('#', 'num').replace('\xa0', '_') for c in df.columns]
    return df

def safe_int(val):
    """Safely convert to int"""
    if val is None or val == '' or (isinstance(val, str) and val.strip() == ''):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def safe_float(val):
    """Safely convert to float"""
    if val is None or val == '' or (isinstance(val, str) and val.strip() == ''):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ============================================================
# 1. WAGE THEFT - NYS DOL
# ============================================================
print("Loading Wage Theft - NYS DOL...")

cur.execute("""
DROP TABLE IF EXISTS nyc_wage_theft_nys CASCADE;
CREATE TABLE nyc_wage_theft_nys (
    id SERIAL PRIMARY KEY,
    year_of_case INTEGER,
    employer_name TEXT,
    address TEXT,
    street TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    wages_owed NUMERIC,
    num_claimants INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Wage Theft - NYS DOL')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        safe_int(row['year_of_case']),
        row['employer_name'],
        row['address'],
        row['street'],
        row['city'],
        row['state'],
        str(safe_int(row['zip_code'])) if safe_int(row['zip_code']) else None,
        safe_float(row['wages_owed']),
        safe_int(row['number_of_claimants_on_case'])
    ))

execute_values(cur, """
    INSERT INTO nyc_wage_theft_nys (year_of_case, employer_name, address, street, city, state, zip_code, wages_owed, num_claimants)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} NYS DOL wage theft records")


# ============================================================
# 2. WAGE THEFT - US DOL
# ============================================================
print("Loading Wage Theft - US DOL...")

cur.execute("""
DROP TABLE IF EXISTS nyc_wage_theft_usdol CASCADE;
CREATE TABLE nyc_wage_theft_usdol (
    id SERIAL PRIMARY KEY,
    case_id TEXT,
    trade_name TEXT,
    legal_name TEXT,
    street_address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    naics_code TEXT,
    naics_description TEXT,
    backwages_amount NUMERIC,
    employees_violated INTEGER,
    violation_count INTEGER,
    civil_penalties NUMERIC,
    employees_agreed INTEGER,
    findings_start_date DATE,
    findings_end_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Wage Theft - US DOL')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        str(safe_int(row['case_id'])) if safe_int(row['case_id']) else None,
        row['trade_nm'],
        row['legal_name'],
        row['street_addr_1_txt'],
        row['cty_nm'],
        row['st_cd'],
        str(safe_int(row['zip_cd'])) if safe_int(row['zip_cd']) else None,
        str(safe_int(row['naic_cd'])) if safe_int(row['naic_cd']) else None,
        row['naics_code_description'],
        safe_float(row['bw_atp_amt']),
        safe_int(row['ee_violtd_cnt']),
        safe_int(row['case_violtn_cnt']),
        safe_float(row['cmp_assd_cnt']),
        safe_int(row['ee_atp_cnt']),
        row['findings_start_date'],
        row['findings_end_date']
    ))

execute_values(cur, """
    INSERT INTO nyc_wage_theft_usdol (case_id, trade_name, legal_name, street_address, city, state, zip_code,
        naics_code, naics_description, backwages_amount, employees_violated, violation_count, civil_penalties,
        employees_agreed, findings_start_date, findings_end_date)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} US DOL wage theft records")


# ============================================================
# 3. WAGE THEFT - LITIGATION
# ============================================================
print("Loading Wage Theft - Litigation...")

cur.execute("""
DROP TABLE IF EXISTS nyc_wage_theft_litigation CASCADE;
CREATE TABLE nyc_wage_theft_litigation (
    id SERIAL PRIMARY KEY,
    employer TEXT,
    settlement_amount NUMERIC,
    settlement_year INTEGER,
    enforcement_entity TEXT,
    case_title TEXT,
    notes TEXT,
    press_release_link TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Wage Theft - Litigation')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['employer'],
        safe_float(row['settlement_amount']),
        safe_int(row['settlement_year']),
        row['enforcement_entity'],
        row['private_litigation_case_title'],
        row['notes'],
        row['press_release_link']
    ))

execute_values(cur, """
    INSERT INTO nyc_wage_theft_litigation (employer, settlement_amount, settlement_year, enforcement_entity, case_title, notes, press_release_link)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} wage theft litigation records")


# ============================================================
# 4. UNFAIR LABOR PRACTICES - CLOSED
# ============================================================
print("Loading Unfair Labor Practices - Closed...")

cur.execute("""
DROP TABLE IF EXISTS nyc_ulp_closed CASCADE;
CREATE TABLE nyc_ulp_closed (
    id SERIAL PRIMARY KEY,
    region TEXT,
    case_number TEXT,
    employer TEXT,
    case_name TEXT,
    union_filing TEXT,
    date_filed DATE,
    date_closed DATE,
    reason_closed TEXT,
    city TEXT,
    state TEXT,
    employees_in_unit INTEGER,
    allegations TEXT,
    violations_8a1 INTEGER,
    violations_8a2 INTEGER,
    violations_8a3 INTEGER,
    violations_8a4 INTEGER,
    violations_8a5 INTEGER,
    violation_count_total INTEGER,
    participants TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Unfair Labor Practice - Closed')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['region'],
        row['case_number'],
        row['employer'],
        row['case_name'],
        row['union'],
        row['date_filed'],
        row['date_closed'],
        row['reason_closed'],
        row['city'],
        row['states_&_territories'],
        safe_int(row['employees_on_charge_petition']),
        row['allegations'],
        safe_int(row.iloc[12]) or 0,  # 8(a)(1)
        safe_int(row.iloc[13]) or 0,  # 8(a)(2)
        safe_int(row.iloc[14]) or 0,  # 8(a)(3)
        safe_int(row.iloc[15]) or 0,  # 8(a)(4)
        safe_int(row.iloc[16]) or 0,  # 8(a)(5)
        safe_int(row['violation_count_total']) or 0,
        row['participants']
    ))

execute_values(cur, """
    INSERT INTO nyc_ulp_closed (region, case_number, employer, case_name, union_filing, date_filed, date_closed,
        reason_closed, city, state, employees_in_unit, allegations, violations_8a1, violations_8a2, violations_8a3,
        violations_8a4, violations_8a5, violation_count_total, participants)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} closed ULP records")


# ============================================================
# 5. UNFAIR LABOR PRACTICES - OPEN
# ============================================================
print("Loading Unfair Labor Practices - Open...")

cur.execute("""
DROP TABLE IF EXISTS nyc_ulp_open CASCADE;
CREATE TABLE nyc_ulp_open (
    id SERIAL PRIMARY KEY,
    region TEXT,
    case_number TEXT,
    employer TEXT,
    case_name TEXT,
    union_filing TEXT,
    date_filed DATE,
    city TEXT,
    state TEXT,
    employees_in_unit INTEGER,
    allegations TEXT,
    violations_8a1 INTEGER,
    violations_8a2 INTEGER,
    violations_8a3 INTEGER,
    violations_8a4 INTEGER,
    violations_8a5 INTEGER,
    violation_count_total INTEGER,
    participants TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Unfair Labor Practice - Open')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['region'],
        row['case_number'],
        row['employer'],
        row['case_name'],
        row['union'],
        row['date_filed'],
        row['city'],
        row['states_&_territories'],
        safe_int(row['employees_on_charge_petition']),
        row['allegations'],
        safe_int(row.iloc[10]) or 0,  # 8(a)(1)
        safe_int(row.iloc[11]) or 0,  # 8(a)(2)
        safe_int(row.iloc[12]) or 0,  # 8(a)(3)
        safe_int(row.iloc[13]) or 0,  # 8(a)(4)
        safe_int(row.iloc[14]) or 0,  # 8(a)(5)
        safe_int(row['violation_count_total']) or 0,
        row['participants']
    ))

execute_values(cur, """
    INSERT INTO nyc_ulp_open (region, case_number, employer, case_name, union_filing, date_filed,
        city, state, employees_in_unit, allegations, violations_8a1, violations_8a2, violations_8a3,
        violations_8a4, violations_8a5, violation_count_total, participants)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} open ULP records")


# ============================================================
# 6. LOCAL NYC LABOR LAWS
# ============================================================
print("Loading Local NYC Labor Laws...")

cur.execute("""
DROP TABLE IF EXISTS nyc_local_labor_laws CASCADE;
CREATE TABLE nyc_local_labor_laws (
    id SERIAL PRIMARY KEY,
    enforcement_id TEXT,
    employer_name TEXT,
    dba TEXT,
    street_address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    pssl_flag BOOLEAN,
    fww_flag BOOLEAN,
    ff_wrongful_discharge BOOLEAN,
    delivery_worker_flag BOOLEAN,
    grocery_worker_flag BOOLEAN,
    closed_date DATE,
    closed_year INTEGER,
    covered_workers INTEGER,
    restitution_amount NUMERIC,
    penalty_amount NUMERIC,
    total_recovered NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Local NYC Labor Laws')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['enf'],
        row['employer_or_hiring_party_name'],
        row['dba'],
        row['street_address'],
        row['city'],
        row['state'],
        str(safe_int(row['zip'])) if safe_int(row['zip']) else None,
        bool(safe_int(row['pssl'])) if safe_int(row['pssl']) else False,
        bool(safe_int(row['fww'])) if safe_int(row['fww']) else False,
        bool(safe_int(row['fast_food_wrongful_discharge'])) if safe_int(row['fast_food_wrongful_discharge']) else False,
        bool(safe_int(row['dw'])) if safe_int(row['dw']) else False,
        bool(safe_int(row['gwr'])) if safe_int(row['gwr']) else False,
        row['closed_date'],
        safe_int(row['closed_date_cy']),
        safe_int(row['covered_workers']),
        safe_float(row['restitution_amount']),
        safe_float(row['penalty_amount']),
        safe_float(row['amount_recovered'])
    ))

execute_values(cur, """
    INSERT INTO nyc_local_labor_laws (enforcement_id, employer_name, dba, street_address, city, state, zip_code,
        pssl_flag, fww_flag, ff_wrongful_discharge, delivery_worker_flag, grocery_worker_flag, closed_date,
        closed_year, covered_workers, restitution_amount, penalty_amount, total_recovered)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} local labor law violations")


# ============================================================
# 7. DISCRIMINATION AND HARASSMENT
# ============================================================
print("Loading Discrimination and Harassment...")

cur.execute("""
DROP TABLE IF EXISTS nyc_discrimination CASCADE;
CREATE TABLE nyc_discrimination (
    id SERIAL PRIMARY KEY,
    employer TEXT,
    enforcement_entity TEXT,
    hiring_or_work_env TEXT,
    discrimination_type TEXT,
    settlement_year INTEGER,
    settlement_amount NUMERIC,
    payment_type TEXT,
    press_release_link TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Discrimination and Harassment')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['employer'],
        row['enforcement_entity'],
        row['hiring_or_work_environment'],
        row['type_of_discrimination'],
        safe_int(row['settlement_penalty_year']),
        safe_float(row['settlement__penalty_amount']),
        row['type_of_payment'],
        row['press_release_link']
    ))

execute_values(cur, """
    INSERT INTO nyc_discrimination (employer, enforcement_entity, hiring_or_work_env, discrimination_type,
        settlement_year, settlement_amount, payment_type, press_release_link)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} discrimination records")


# ============================================================
# 8. PREVAILING WAGE VIOLATIONS
# ============================================================
print("Loading Prevailing Wage Violations...")

cur.execute("""
DROP TABLE IF EXISTS nyc_prevailing_wage CASCADE;
CREATE TABLE nyc_prevailing_wage (
    id SERIAL PRIMARY KEY,
    contractor TEXT,
    settlement_ruling TEXT,
    result TEXT,
    action TEXT,
    city_agency TEXT,
    amount_recovered NUMERIC,
    underpayment NUMERIC,
    civil_penalties NUMERIC,
    press_release TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Prevailing Wage Violations')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['contractor'],
        row['settlement_ruling'],
        row['result'],
        row['action'],
        row['city_agency'],
        safe_float(row['amount_recovered']),
        safe_float(row['underpayment']),
        safe_float(row['civil_penalties']),
        row['press_release']
    ))

execute_values(cur, """
    INSERT INTO nyc_prevailing_wage (contractor, settlement_ruling, result, action, city_agency,
        amount_recovered, underpayment, civil_penalties, press_release)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} prevailing wage violations")


# ============================================================
# 9. NYS DEBARMENT LIST
# ============================================================
print("Loading NYS Debarment List...")

cur.execute("""
DROP TABLE IF EXISTS nyc_debarment_list CASCADE;
CREATE TABLE nyc_debarment_list (
    id SERIAL PRIMARY KEY,
    prosecuting_agency TEXT,
    fein TEXT,
    employer_name TEXT,
    employer_dba TEXT,
    address TEXT,
    debarment_start_date DATE,
    debarment_end_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='NYS Debarment List')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['prosecuting_agency'],
        row['fein'],
        row['employer_name'],
        row['employer_dba_name'],
        row['address'],
        row['debarment_start_date'],
        row['debarment_end_date']
    ))

execute_values(cur, """
    INSERT INTO nyc_debarment_list (prosecuting_agency, fein, employer_name, employer_dba, address,
        debarment_start_date, debarment_end_date)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} debarment records")


# ============================================================
# 10. WORKPLACE SAFETY - OSHA (NYC specific)
# ============================================================
print("Loading Workplace Safety - OSHA...")

cur.execute("""
DROP TABLE IF EXISTS nyc_osha_violations CASCADE;
CREATE TABLE nyc_osha_violations (
    id SERIAL PRIMARY KEY,
    estab_name TEXT,
    site_address TEXT,
    site_city TEXT,
    site_state TEXT,
    site_zip TEXT,
    naics_code TEXT,
    sector TEXT,
    inspection_number TEXT,
    citation_id TEXT,
    violation_type TEXT,
    final_order_date DATE,
    num_exposed INTEGER,
    osha_standard TEXT,
    part_number_title TEXT,
    subpart TEXT,
    subpart_title TEXT,
    union_status TEXT,
    penalty_amount NUMERIC,
    fatality BOOLEAN,
    event_description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

df = pd.read_excel(xlsx, sheet_name='Workplace Safety - OSHA')
df = clean_df(df)

records = []
for _, row in df.iterrows():
    records.append((
        row['estab_name'],
        row['site_address'],
        row['site_city'],
        row['site_state'],
        str(row['site_zip']) if row['site_zip'] else None,
        str(safe_int(row['naics_code'])) if safe_int(row['naics_code']) else None,
        row['sector'],
        str(row['activity_nr']) if row['activity_nr'] else None,
        row['citation_id'],
        row['viol_type'],
        row['final_order_date'],
        safe_int(row['nr_exposed']),
        row['osha_standard_number'],
        row['part_number_title'],
        row['subpart'],
        row['subpart_title'],
        row['union_status'],
        safe_float(row['current_penalty']),
        row['fatality'] == 'Yes' if row['fatality'] else False,
        row['event_desc']
    ))

execute_values(cur, """
    INSERT INTO nyc_osha_violations (estab_name, site_address, site_city, site_state, site_zip, naics_code,
        sector, inspection_number, citation_id, violation_type, final_order_date, num_exposed, osha_standard,
        part_number_title, subpart, subpart_title, union_status, penalty_amount, fatality, event_description)
    VALUES %s
""", records)
print(f"  Loaded {len(records)} OSHA violations")


# ============================================================
# CREATE SUMMARY VIEW
# ============================================================
print("\nCreating summary view...")

cur.execute("""
DROP VIEW IF EXISTS v_nyc_employer_violations_summary CASCADE;
CREATE VIEW v_nyc_employer_violations_summary AS
WITH wage_theft AS (
    SELECT employer_name AS employer, 'NYS DOL Wage Theft' AS violation_type,
           wages_owed AS amount, year_of_case AS year, city
    FROM nyc_wage_theft_nys
    UNION ALL
    SELECT trade_name, 'US DOL Wage Theft', backwages_amount,
           EXTRACT(YEAR FROM findings_end_date)::int, city
    FROM nyc_wage_theft_usdol
    UNION ALL
    SELECT employer, 'Wage Theft Litigation', settlement_amount, settlement_year, NULL
    FROM nyc_wage_theft_litigation
),
ulp AS (
    SELECT employer, 'ULP (Closed)' AS violation_type,
           violation_count_total::numeric AS amount,
           EXTRACT(YEAR FROM date_closed)::int AS year, city
    FROM nyc_ulp_closed
    UNION ALL
    SELECT employer, 'ULP (Open)', violation_count_total::numeric,
           EXTRACT(YEAR FROM date_filed)::int, city
    FROM nyc_ulp_open
),
local_laws AS (
    SELECT employer_name, 'Local NYC Labor Law', total_recovered, closed_year, city
    FROM nyc_local_labor_laws
),
all_violations AS (
    SELECT * FROM wage_theft
    UNION ALL SELECT * FROM ulp
    UNION ALL SELECT * FROM local_laws
)
SELECT
    employer,
    COUNT(*) AS violation_count,
    array_agg(DISTINCT violation_type) AS violation_types,
    SUM(amount) AS total_amount,
    MIN(year) AS earliest_year,
    MAX(year) AS latest_year
FROM all_violations
WHERE employer IS NOT NULL
GROUP BY employer
ORDER BY violation_count DESC, total_amount DESC NULLS LAST;
""")

# Create indexes
print("Creating indexes...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_wage_nys_employer ON nyc_wage_theft_nys(employer_name);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_wage_usdol_trade ON nyc_wage_theft_usdol(trade_name);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_ulp_closed_employer ON nyc_ulp_closed(employer);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_ulp_open_employer ON nyc_ulp_open(employer);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_local_employer ON nyc_local_labor_laws(employer_name);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_nyc_osha_estab ON nyc_osha_violations(estab_name);")

conn.commit()

# Print summary
print("\n" + "="*60)
print("NYC EMPLOYER VIOLATIONS DATA LOADED SUCCESSFULLY")
print("="*60)

cur.execute("""
SELECT
    'Wage Theft - NYS DOL' as source, COUNT(*) as records,
    SUM(wages_owed) as total_amount
FROM nyc_wage_theft_nys
UNION ALL
SELECT 'Wage Theft - US DOL', COUNT(*), SUM(backwages_amount) FROM nyc_wage_theft_usdol
UNION ALL
SELECT 'Wage Theft - Litigation', COUNT(*), SUM(settlement_amount) FROM nyc_wage_theft_litigation
UNION ALL
SELECT 'ULP - Closed', COUNT(*), NULL FROM nyc_ulp_closed
UNION ALL
SELECT 'ULP - Open', COUNT(*), NULL FROM nyc_ulp_open
UNION ALL
SELECT 'Local NYC Labor Laws', COUNT(*), SUM(total_recovered) FROM nyc_local_labor_laws
UNION ALL
SELECT 'Discrimination', COUNT(*), SUM(settlement_amount) FROM nyc_discrimination
UNION ALL
SELECT 'Prevailing Wage', COUNT(*), SUM(amount_recovered) FROM nyc_prevailing_wage
UNION ALL
SELECT 'Debarment List', COUNT(*), NULL FROM nyc_debarment_list
UNION ALL
SELECT 'OSHA Violations', COUNT(*), SUM(penalty_amount) FROM nyc_osha_violations
ORDER BY records DESC;
""")

print(f"\n{'Source':<30} {'Records':>10} {'Total Amount':>20}")
print("-" * 62)
for row in cur.fetchall():
    amt = f"${row[2]:,.2f}" if row[2] else "N/A"
    print(f"{row[0]:<30} {row[1]:>10,} {amt:>20}")

cur.close()
conn.close()
print("\nDone!")
