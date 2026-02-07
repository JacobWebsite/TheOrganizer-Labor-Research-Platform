"""
Load NY State Contract Awards from Excel export
Source: Open Book New York - contracts after 01/01/2023
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'scripts' / 'import'))

import pandas as pd
import psycopg2
from name_normalizer import normalize_employer

# AFSCME-relevant keywords in department/facility or description
AFSCME_KEYWORDS = [
    'HEALTH', 'HOSPITAL', 'MEDICAL', 'NURSING',
    'SOCIAL', 'HUMAN SERVICES', 'CHILD', 'FAMILY',
    'EDUCATION', 'SCHOOL', 'UNIVERSITY', 'SUNY', 'CUNY',
    'MENTAL', 'PSYCHIATRIC', 'BEHAVIORAL',
    'AGING', 'SENIOR', 'ELDERLY',
    'DEVELOPMENTAL', 'DISABILITIES',
    'TRANSIT', 'TRANSPORTATION', 'MTA',
    'CORRECTION', 'PAROLE', 'PROBATION',
]


def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def is_afscme_relevant(row):
    """Check if contract is in AFSCME-relevant category."""
    dept = str(row.get('DEPARTMENT/FACILITY') or '').upper()
    desc = str(row.get('CONTRACT DESCRIPTION') or '').upper()
    contract_type = str(row.get('CONTRACT TYPE') or '').upper()

    text = f"{dept} {desc} {contract_type}"

    for keyword in AFSCME_KEYWORDS:
        if keyword in text:
            return True

    return False


def parse_date(date_val):
    """Parse date value from Excel."""
    if pd.isna(date_val):
        return None
    if isinstance(date_val, str):
        # Try parsing MM/DD/YYYY format
        try:
            from datetime import datetime
            return datetime.strptime(date_val, '%m/%d/%Y').date()
        except:
            return None
    # Pandas Timestamp
    try:
        return date_val.date()
    except:
        return None


def load_contracts_from_excel(excel_path: str):
    """Load NY State contracts from Excel file."""
    print(f"Loading contracts from {excel_path}...")

    # Read Excel with header at row 9
    df = pd.read_excel(excel_path, header=9)
    print(f"Read {len(df)} rows")

    conn = get_db_connection()
    cur = conn.cursor()

    # Clear existing data
    print("Clearing existing NY state contracts...")
    cur.execute("DELETE FROM ny_state_contracts")

    inserted = 0
    afscme_relevant = 0

    for _, row in df.iterrows():
        vendor_name = row.get('VENDOR NAME')
        if pd.isna(vendor_name) or not str(vendor_name).strip():
            continue

        vendor_name = str(vendor_name).strip()
        vendor_normalized = normalize_employer(vendor_name)
        is_relevant = is_afscme_relevant(row)
        if is_relevant:
            afscme_relevant += 1

        # Parse amounts
        current_amt = row.get('CURRENT CONTRACT AMOUNT')
        if pd.isna(current_amt):
            current_amt = None
        else:
            try:
                current_amt = float(current_amt)
            except:
                current_amt = None

        spending = row.get('SPENDING TO DATE')
        if pd.isna(spending):
            spending = None
        else:
            try:
                spending = float(spending)
            except:
                spending = None

        # Parse dates
        start_date = parse_date(row.get('CONTRACT START DATE'))
        end_date = parse_date(row.get('CONTRACT END DATE'))

        # Extract fiscal year from start date
        fiscal_year = None
        if start_date:
            # NY fiscal year starts April 1
            if start_date.month >= 4:
                fiscal_year = start_date.year + 1
            else:
                fiscal_year = start_date.year

        cur.execute("""
            INSERT INTO ny_state_contracts (
                contract_number, contract_title,
                vendor_name, vendor_name_normalized,
                agency_name, contract_type,
                original_amount, current_amount,
                start_date, end_date,
                contract_category, service_description,
                is_afscme_relevant, fiscal_year
            ) VALUES (
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
        """, (
            str(row.get('CONTRACT NUMBER') or ''),
            str(row.get('CONTRACT DESCRIPTION') or ''),
            vendor_name,
            vendor_normalized,
            str(row.get('DEPARTMENT/FACILITY') or ''),
            str(row.get('CONTRACT TYPE') or ''),
            current_amt,  # Use current as original (original not in file)
            current_amt,
            start_date,
            end_date,
            str(row.get('CONTRACT TYPE') or ''),  # Use contract type as category
            str(row.get('CONTRACT DESCRIPTION') or ''),
            is_relevant,
            fiscal_year
        ))

        inserted += 1
        if inserted % 10000 == 0:
            print(f"  Inserted {inserted} contracts...")

    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM ny_state_contracts")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM ny_state_contracts WHERE is_afscme_relevant = TRUE")
    relevant = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"\n=== Load Complete ===")
    print(f"Total contracts inserted: {inserted}")
    print(f"AFSCME-relevant contracts: {afscme_relevant}")
    print(f"Database total: {total}")
    print(f"Database AFSCME-relevant: {relevant}")

    return inserted


def show_contract_summary():
    """Show summary of loaded contracts."""
    conn = get_db_connection()
    cur = conn.cursor()

    # By agency
    cur.execute("""
        SELECT agency_name, COUNT(*) as cnt,
               SUM(current_amount) as total_value,
               COUNT(*) FILTER (WHERE is_afscme_relevant) as afscme_cnt
        FROM ny_state_contracts
        WHERE agency_name IS NOT NULL AND agency_name != ''
        GROUP BY agency_name
        ORDER BY cnt DESC
        LIMIT 20
    """)

    print("\n=== Top 20 Agencies by Contract Count ===")
    for agency, cnt, value, afscme_cnt in cur.fetchall():
        value_str = f"${float(value)/1e6:.1f}M" if value else "$0"
        print(f"  {agency[:50]}: {cnt} contracts ({value_str}) [{afscme_cnt} AFSCME-relevant]")

    # Top vendors in AFSCME-relevant contracts
    cur.execute("""
        SELECT vendor_name, COUNT(*) as cnt, SUM(current_amount) as total
        FROM ny_state_contracts
        WHERE is_afscme_relevant = TRUE
        GROUP BY vendor_name
        ORDER BY total DESC NULLS LAST
        LIMIT 20
    """)

    print("\n=== Top 20 Vendors (AFSCME-relevant contracts) ===")
    for vendor, cnt, total in cur.fetchall():
        total_str = f"${float(total)/1e6:.1f}M" if total else "$0"
        print(f"  {vendor[:50]}: {cnt} contracts ({total_str})")

    cur.close()
    conn.close()


if __name__ == '__main__':
    excel_path = r'C:\Users\jakew\Downloads\contracts_NY STATE after 1_01_23.xlsx'

    print("=" * 60)
    print("Loading NY State Contracts from Excel")
    print("=" * 60)

    load_contracts_from_excel(excel_path)
    show_contract_summary()
