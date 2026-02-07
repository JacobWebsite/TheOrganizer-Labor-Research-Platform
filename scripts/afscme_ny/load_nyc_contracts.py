"""
Load NYC Contract Awards from Checkbook NYC API
Source: https://www.checkbooknyc.com/api
Contracts awarded after 01/01/2023
"""

import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'scripts' / 'import'))

import psycopg2
from name_normalizer import normalize_employer

# AFSCME-relevant keywords
AFSCME_KEYWORDS = [
    'HEALTH', 'HOSPITAL', 'MEDICAL', 'NURSING', 'HHC',
    'SOCIAL', 'HUMAN SERVICES', 'CHILD', 'FAMILY', 'ACS', 'DSS', 'HRA',
    'EDUCATION', 'SCHOOL', 'DOE',
    'MENTAL', 'PSYCHIATRIC', 'BEHAVIORAL',
    'AGING', 'SENIOR', 'ELDERLY', 'DFTA',
    'HOMELESS', 'SHELTER', 'DHS',
    'SANITATION', 'DSNY',
    'PARKS', 'DPR',
    'CORRECTION', 'DOC',
    'TRANSIT', 'TRANSPORTATION', 'DOT',
]


def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def is_afscme_relevant(contract):
    """Check if contract is in AFSCME-relevant category."""
    agency = str(contract.get('agency_name') or '').upper()
    vendor = str(contract.get('vendor_name') or '').upper()
    purpose = str(contract.get('purpose') or '').upper()
    industry = str(contract.get('industry_type') or '').upper()

    text = f"{agency} {vendor} {purpose} {industry}"

    for keyword in AFSCME_KEYWORDS:
        if keyword in text:
            return True

    return False


def fetch_nyc_contracts_xml():
    """
    Fetch NYC contracts from Checkbook NYC API.
    Uses the spending API endpoint.
    """
    # Checkbook NYC API endpoint for contracts
    # Based on their API documentation
    base_url = "https://www.checkbooknyc.com/api"

    # Try the contracts endpoint with XML response
    # The API accepts search parameters
    params = {
        'type_of_data': 'Contracts',
        'startdate': '2023-01-01',
        'records_from': '1',
        'max_records': '10000',
        'response_format': 'json'
    }

    # Build URL
    param_str = '&'.join(f"{k}={v}" for k, v in params.items())
    url = f"{base_url}?{param_str}"

    print(f"Fetching NYC contracts from Checkbook NYC API...")
    print(f"URL: {url}")

    try:
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0 Labor Research Platform')

        with urllib.request.urlopen(req, timeout=120) as response:
            content = response.read().decode('utf-8')
            print(f"Response length: {len(content)} chars")

            # Try to parse as JSON
            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError:
                # May be XML
                print("Response is not JSON, may be XML format")
                return {'raw': content}

    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"Error fetching contracts: {e}")
        return None


def fetch_nyc_contracts_odata():
    """
    Fetch NYC contracts using the Recent Contract Awards endpoint.
    Dataset ID: qyyg-4tf5
    Source: https://data.cityofnewyork.us/City-Government/Recent-Contract-Awards/qyyg-4tf5
    """
    # NYC Open Data - Recent Contract Awards dataset
    base_url = "https://data.cityofnewyork.us/resource/qyyg-4tf5.json"

    all_contracts = []
    offset = 0
    limit = 5000  # Socrata allows up to 50000, but we batch for reliability

    print(f"Fetching NYC contracts from Recent Contract Awards API...")

    while True:
        # URL encode properly - use %27 for quotes, %20 for spaces
        url = f"{base_url}?$limit={limit}&$offset={offset}&$order=start_date%20DESC"

        print(f"  Fetching batch at offset {offset}...")

        try:
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode('utf-8'))

                if not data:
                    print(f"  No more data at offset {offset}")
                    break

                all_contracts.extend(data)
                print(f"  Retrieved {len(data)} contracts (total: {len(all_contracts)})")

                if len(data) < limit:
                    # No more pages
                    break

                offset += limit

                # Safety limit
                if len(all_contracts) > 100000:
                    print("  Reached safety limit of 100,000 contracts")
                    break

        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

    print(f"Total contracts retrieved: {len(all_contracts)}")
    return all_contracts if all_contracts else None


def load_contracts_to_db(contracts):
    """Load NYC contracts into database.

    Field mapping from Recent Contract Awards API (qyyg-4tf5):
    - request_id -> contract_id
    - vendor_name -> vendor_name
    - agency_name -> agency_name
    - contract_amount -> current_amount
    - start_date -> start_date
    - end_date -> end_date
    - type_of_notice_description -> contract_type
    - category_description -> industry_type
    - short_title -> purpose
    - selection_method_description -> award_method
    - pin -> document_id
    """
    if not contracts:
        print("No contracts to load")
        return 0

    conn = get_db_connection()
    cur = conn.cursor()

    # Clear existing data
    print("Clearing existing NYC contracts...")
    cur.execute("DELETE FROM nyc_contracts")

    inserted = 0
    afscme_relevant_count = 0

    for contract in contracts:
        vendor_name = contract.get('vendor_name') or contract.get('vendor')
        if not vendor_name:
            continue

        vendor_normalized = normalize_employer(vendor_name)
        is_relevant = is_afscme_relevant(contract)
        if is_relevant:
            afscme_relevant_count += 1

        # Parse amounts - field is 'contract_amount' in new API
        # Cap at max value for NUMERIC(15,2): 9999999999999.99
        current_amt = None
        try:
            raw_amt = float(contract.get('contract_amount') or
                           contract.get('current_contract_amount') or
                           contract.get('award_amount') or 0)
            # Cap at max PostgreSQL NUMERIC(15,2) value
            current_amt = min(raw_amt, 9999999999999.99)
        except (ValueError, TypeError):
            pass

        # Parse dates - format is ISO like "2026-01-30T00:00:00.000"
        start_date = contract.get('start_date')
        end_date = contract.get('end_date')

        if start_date and isinstance(start_date, str) and len(start_date) >= 10:
            start_date = start_date[:10]
        else:
            start_date = None

        if end_date and isinstance(end_date, str) and len(end_date) >= 10:
            end_date = end_date[:10]
        else:
            end_date = None

        # Extract fiscal year from start_date
        fiscal_year = None
        if start_date:
            try:
                year = int(start_date[:4])
                month = int(start_date[5:7])
                # NYC fiscal year starts July 1
                fiscal_year = year + 1 if month >= 7 else year
            except (ValueError, IndexError):
                pass

        cur.execute("""
            INSERT INTO nyc_contracts (
                contract_id, document_id,
                vendor_name, vendor_name_normalized,
                agency_name, agency_code, contract_type, purpose,
                original_amount, current_amount,
                start_date, end_date,
                industry_type, award_method,
                is_afscme_relevant, fiscal_year
            ) VALUES (
                %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
        """, (
            contract.get('request_id') or contract.get('contract_id'),
            contract.get('pin') or contract.get('document_id'),
            vendor_name,
            vendor_normalized,
            contract.get('agency_name'),
            None,  # agency_code not in this dataset
            contract.get('type_of_notice_description') or contract.get('contract_type'),
            contract.get('short_title') or contract.get('purpose'),
            current_amt,  # Use same for original
            current_amt,
            start_date,
            end_date,
            contract.get('category_description') or contract.get('industry_type'),
            contract.get('selection_method_description') or contract.get('award_method'),
            is_relevant,
            fiscal_year
        ))

        inserted += 1
        if inserted % 5000 == 0:
            print(f"  Inserted {inserted} contracts...")

    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM nyc_contracts")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM nyc_contracts WHERE is_afscme_relevant = TRUE")
    relevant = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"\n=== Load Complete ===")
    print(f"Total contracts inserted: {inserted}")
    print(f"AFSCME-relevant contracts: {afscme_relevant_count}")
    print(f"Database total: {total}")
    print(f"Database AFSCME-relevant: {relevant}")

    return inserted


def show_contract_summary():
    """Show summary of loaded NYC contracts."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM nyc_contracts")
    total = cur.fetchone()[0]

    if total == 0:
        print("No NYC contracts in database")
        cur.close()
        conn.close()
        return

    # By agency
    cur.execute("""
        SELECT agency_name, COUNT(*) as cnt,
               SUM(current_amount) as total_value,
               COUNT(*) FILTER (WHERE is_afscme_relevant) as afscme_cnt
        FROM nyc_contracts
        WHERE agency_name IS NOT NULL
        GROUP BY agency_name
        ORDER BY cnt DESC
        LIMIT 15
    """)

    print("\n=== Top 15 NYC Agencies by Contract Count ===")
    for agency, cnt, value, afscme_cnt in cur.fetchall():
        value_str = f"${float(value)/1e6:.1f}M" if value else "$0"
        print(f"  {agency[:50]}: {cnt} ({value_str}) [{afscme_cnt} AFSCME]")

    # Top vendors in AFSCME-relevant contracts
    cur.execute("""
        SELECT vendor_name, COUNT(*) as cnt, SUM(current_amount) as total
        FROM nyc_contracts
        WHERE is_afscme_relevant = TRUE
        GROUP BY vendor_name
        ORDER BY total DESC NULLS LAST
        LIMIT 15
    """)

    print("\n=== Top 15 Vendors (AFSCME-relevant) ===")
    for vendor, cnt, total in cur.fetchall():
        total_str = f"${float(total)/1e6:.1f}M" if total else "$0"
        print(f"  {vendor[:50]}: {cnt} ({total_str})")

    cur.close()
    conn.close()


def run_load():
    """Main loading process."""
    print("=" * 60)
    print("Loading NYC Contracts from Checkbook NYC / Open Data")
    print("=" * 60)

    # Try NYC Open Data first (more reliable)
    contracts = fetch_nyc_contracts_odata()

    if contracts:
        load_contracts_to_db(contracts)
        show_contract_summary()
        return len(contracts)
    else:
        print("\nCould not fetch from NYC Open Data, trying Checkbook API...")
        data = fetch_nyc_contracts_xml()
        if data and 'raw' not in data:
            load_contracts_to_db(data)
            show_contract_summary()
        else:
            print("Could not load NYC contracts automatically.")
            print("You may need to download manually from https://www.checkbooknyc.com/")

    return 0


if __name__ == '__main__':
    run_load()
