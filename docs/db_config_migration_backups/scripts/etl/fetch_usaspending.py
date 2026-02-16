"""
Fetch USASpending federal contract data via API.

Uses the bulk_download/awards endpoint to generate CSV files,
then downloads and loads into PostgreSQL.

Strategy: Use the search API to paginate through contract awards
and extract recipient info (name, UEI, state, NAICS, award amount).
"""
import json
import os
import sys
import time
import requests
import psycopg2
import csv
import io
import zipfile
from pathlib import Path

API_BASE = "https://api.usaspending.gov/api/v2"

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def create_table(conn):
    """Create federal_contracts table."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS federal_contracts (
            id SERIAL PRIMARY KEY,
            award_id TEXT,
            recipient_name TEXT,
            recipient_name_normalized TEXT,
            recipient_uei TEXT,
            recipient_duns TEXT,
            recipient_state TEXT,
            recipient_city TEXT,
            recipient_zip TEXT,
            naics_code TEXT,
            naics_description TEXT,
            award_amount NUMERIC,
            total_outlays NUMERIC,
            awarding_agency TEXT,
            awarding_sub_agency TEXT,
            start_date DATE,
            end_date DATE,
            award_type TEXT,
            fiscal_year INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_recipient ON federal_contracts(recipient_name_normalized)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_uei ON federal_contracts(recipient_uei) WHERE recipient_uei IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_duns ON federal_contracts(recipient_duns) WHERE recipient_duns IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_state ON federal_contracts(recipient_state)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_naics ON federal_contracts(naics_code)")
    conn.commit()
    print("  federal_contracts table ready")


def normalize_name(name):
    """Simple name normalization for matching."""
    if not name:
        return ''
    import re
    result = name.lower().strip()
    result = re.sub(r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\b\.?', '', result)
    result = re.sub(r'[^\w\s]', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def fetch_contracts_by_state(state, fiscal_year, page=1, limit=100):
    """Fetch contract awards for a state and fiscal year."""
    url = f"{API_BASE}/search/spending_by_award/"
    payload = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],  # All contract types
            "time_period": [
                {
                    "start_date": f"{fiscal_year - 1}-10-01",
                    "end_date": f"{fiscal_year}-09-30"
                }
            ],
            "recipient_locations": [
                {"country": "USA", "state": state}
            ]
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Recipient UEI",
            "Recipient DUNS Number",
            "Award Amount",
            "Total Outlays",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Contract Award Type",
            "NAICS Code",
            "NAICS Description",
            "recipient_id"
        ],
        "limit": limit,
        "page": page,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False
    }

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_all_contracts_for_state(state, fiscal_year):
    """Paginate through all contracts for a state/year."""
    all_results = []
    page = 1
    limit = 100

    while True:
        try:
            data = fetch_contracts_by_state(state, fiscal_year, page, limit)
        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        all_results.extend(results)

        has_next = data.get("page_metadata", {}).get("hasNext", False)
        if not has_next:
            break

        page += 1

        # Rate limiting
        if page % 10 == 0:
            time.sleep(0.5)

    return all_results


def insert_contracts(conn, contracts, fiscal_year):
    """Insert contract records into database."""
    cur = conn.cursor()
    inserted = 0

    for c in contracts:
        name = c.get("Recipient Name", "")
        cur.execute("""
            INSERT INTO federal_contracts
                (award_id, recipient_name, recipient_name_normalized,
                 recipient_uei, recipient_duns,
                 recipient_state, naics_code, naics_description,
                 award_amount, total_outlays,
                 awarding_agency, awarding_sub_agency,
                 start_date, end_date, award_type, fiscal_year)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            c.get("Award ID"),
            name,
            normalize_name(name),
            c.get("Recipient UEI"),
            c.get("Recipient DUNS Number"),
            None,  # State comes from the query filter
            c.get("NAICS Code"),
            c.get("NAICS Description"),
            c.get("Award Amount"),
            c.get("Total Outlays"),
            c.get("Awarding Agency"),
            c.get("Awarding Sub Agency"),
            c.get("Start Date"),
            c.get("End Date"),
            c.get("Contract Award Type"),
            fiscal_year,
        ))
        inserted += 1

    conn.commit()
    return inserted


def fetch_via_bulk_api(fiscal_year):
    """Use the bulk download API to get all contracts for a fiscal year."""
    url = f"{API_BASE}/bulk_download/awards/"
    payload = {
        "filters": {
            "prime_award_types": ["A", "B", "C", "D"],
            "date_type": "action_date",
            "date_range": {
                "start_date": f"{fiscal_year - 1}-10-01",
                "end_date": f"{fiscal_year}-09-30"
            },
            "agency": "all"
        }
    }

    print(f"  Requesting bulk download for FY{fiscal_year}...")
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    file_url = data.get("file_url")
    status_url = data.get("status_url")

    if not file_url and status_url:
        # Poll for completion
        print(f"  Waiting for generation... (status: {status_url})")
        for i in range(120):  # Wait up to 10 minutes
            time.sleep(5)
            status_resp = requests.get(f"{API_BASE}{status_url}", timeout=30)
            status_data = status_resp.json()
            status = status_data.get("status", "unknown")
            if status == "finished":
                file_url = status_data.get("file_url")
                break
            elif status == "failed":
                print(f"  Bulk download failed: {status_data}")
                return None
            if i % 6 == 0:
                print(f"    Status: {status} ({i*5}s elapsed)")

    if file_url:
        print(f"  Downloading: {file_url}")
        return file_url

    return None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    create_table(conn)

    # Strategy: Use search API to get top contract recipients per state
    # Focus on states with most F7 employers for maximum matching value
    # Get top N contracts per state (by award amount) across FY2020-2024

    # Key states for F7 matching
    states = [
        "NY", "CA", "TX", "FL", "IL", "PA", "OH", "MI", "NJ", "MA",
        "WA", "GA", "NC", "VA", "MN", "WI", "MD", "MO", "IN", "TN",
        "AZ", "CO", "CT", "OR", "SC", "KY", "AL", "LA", "OK", "NV",
        "IA", "KS", "UT", "AR", "MS", "NE", "NM", "WV", "HI", "ID",
        "NH", "ME", "MT", "RI", "DE", "SD", "ND", "AK", "VT", "WY", "DC"
    ]

    fiscal_years = [2024, 2023]  # Start with most recent

    total_inserted = 0

    for fy in fiscal_years:
        print(f"\n=== Fiscal Year {fy} ===")
        for state in states:
            contracts = fetch_all_contracts_for_state(state, fy)
            if contracts:
                # Add state info
                for c in contracts:
                    c['_state'] = state

                inserted = insert_contracts(conn, contracts, fy)
                total_inserted += inserted

                if inserted > 0:
                    print(f"  {state}: {inserted:,} contracts")

            # Rate limiting between states
            time.sleep(0.3)

        print(f"  FY{fy} subtotal: {total_inserted:,}")

    # Update state column from recipient location
    cur = conn.cursor()
    # We'll need to extract state from the API results
    # For now, let's try using the bulk download approach instead

    print(f"\n=== TOTAL LOADED: {total_inserted:,} ===")

    # Create aggregated recipient view
    cur.execute("""
        CREATE OR REPLACE VIEW federal_contract_recipients AS
        SELECT
            recipient_name,
            recipient_name_normalized,
            recipient_uei,
            recipient_duns,
            recipient_state,
            COUNT(DISTINCT award_id) as contract_count,
            SUM(award_amount) as total_obligations,
            MIN(fiscal_year) as first_fy,
            MAX(fiscal_year) as last_fy,
            MODE() WITHIN GROUP (ORDER BY naics_code) as primary_naics
        FROM federal_contracts
        WHERE recipient_name IS NOT NULL
        GROUP BY recipient_name, recipient_name_normalized, recipient_uei, recipient_duns, recipient_state
    """)
    conn.commit()
    print("  Created federal_contract_recipients view")

    conn.close()


if __name__ == "__main__":
    main()
