#!/usr/bin/env python3
"""
IRS Business Master File ETL
Extracts ~1.8M tax-exempt organizations from IRS BMF
Loads into irs_bmf table for later matching
"""
import argparse
import requests
import time
import sys
import os
from pathlib import Path

# Add the project root to the sys.path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent # Assumes script is in scripts/etl/
sys.path.insert(0, str(project_root))

from db_config import get_connection
from psycopg2.extras import RealDictCursor


# === OPTION A: ProPublica API ===

def extract_via_propublica(limit=None):
    """
    Fetch organizations via ProPublica Nonprofit Explorer API

    API docs: https://projects.propublica.org/nonprofits/api
    Returns max 250 orgs per page, need to paginate
    """
    API_BASE = 'https://projects.propublica.org/nonprofits/api/v2'

    orgs = []
    page = 0
    total_results = None

    print("Fetching from ProPublica Nonprofit Explorer API...")

    while True:
        # Empty query returns all orgs
        url = f"{API_BASE}/search.json?page={page}"

        try:
            response = requests.get(url)

            if response.status_code != 200:
                print(f"API error: {response.status_code}")
                break

            data = response.json()

            if total_results is None:
                total_results = data.get('total_results')

            if not data.get('organizations'):
                print("No more results on this page")
                break

            orgs.extend(data['organizations'])

            print(f"Page {page}: {len(orgs):,} of {total_results:,} total orgs fetched", end='\r')

            if limit and len(orgs) >= limit:
                print(f"\nLimit of {limit} reached.")
                break

            # ProPublica API returns 25 orgs per page
            # If we fetched less than 25, we're at the last page
            if len(data['organizations']) < 25:
                break

            page += 1
            time.sleep(0.5)  # Rate limit courtesy

        except Exception as e:
            print(f"\nError on page {page}: {e}")
            break

    print(f"\nExtracted {len(orgs):,} organizations")

    return orgs[:limit] if limit else orgs


# === OPTION B: IRS Bulk File ===

def extract_via_irs_bulk():
    """
    Parse IRS bulk data file (fixed-width format)

    Download: https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf
    Format spec: https://www.irs.gov/pub/irs-soi/eo_info.pdf

    This is more complex but gets full dataset.
    If ProPublica works, skip this.
    """
    print("IRS bulk file parsing not implemented yet")
    print("Use ProPublica API instead or implement fixed-width parsing")
    return []


def transform_org(raw_data, source='propublica'):
    """
    Normalize organization data to our schema

    ProPublica fields:
        - ein
        - name
        - state
        - city
        - zipcode
        - ntee_code
        - subsection_code (from 'subseccd')
        - ruling_date
        - deductibility_code
        - foundation_code
        - income_amount
        - asset_amount
    """
    if source == 'propublica':
        return {
            'ein': raw_data.get('ein'),
            'org_name': raw_data.get('name'),
            'state': raw_data.get('state'),
            'city': raw_data.get('city'),
            'zip_code': raw_data.get('zipcode'),
            'ntee_code': raw_data.get('ntee_code'),
            # ProPublica uses 'subseccd' as an integer, convert to string for consistency
            'subsection_code': str(raw_data.get('subseccd')).zfill(2) if raw_data.get('subseccd') is not None else None,
            'ruling_date': raw_data.get('ruling_date'),
            'deductibility_code': raw_data.get('deductibility_code'),
            'foundation_code': raw_data.get('foundation_code'),
            'income_amount': raw_data.get('income_amount'),
            'asset_amount': raw_data.get('asset_amount'),
        }
    else:
        # IRS bulk format (if implemented)
        return {}


def load_to_db(orgs):
    """
    Bulk insert organizations to irs_bmf table
    Uses UPSERT (ON CONFLICT DO UPDATE) for idempotent reloading
    """
    if not orgs:
        print("No organizations to load")
        return 0

    conn = get_connection(cursor_factory=RealDictCursor) # Use RealDictCursor for statistics
    cur = conn.cursor()

    print(f"Loading {len(orgs):,} organizations to database...")

    insert_query = """
        INSERT INTO irs_bmf (
            ein, org_name, state, city, zip_code,
            ntee_code, subsection_code, ruling_date,
            deductibility_code, foundation_code,
            income_amount, asset_amount,
            updated_at
        ) VALUES (
            %(ein)s, %(org_name)s, %(state)s, %(city)s, %(zip_code)s,
            %(ntee_code)s, %(subsection_code)s, %(ruling_date)s,
            %(deductibility_code)s, %(foundation_code)s,
            %(income_amount)s, %(asset_amount)s,
            NOW()
        )
        ON CONFLICT (ein)
        DO UPDATE SET
            org_name = EXCLUDED.org_name,
            state = EXCLUDED.state,
            city = EXCLUDED.city,
            zip_code = EXCLUDED.zip_code,
            ntee_code = EXCLUDED.ntee_code,
            subsection_code = EXCLUDED.subsection_code,
            ruling_date = EXCLUDED.ruling_date,
            deductibility_code = EXCLUDED.deductibility_code,
            foundation_code = EXCLUDED.foundation_code,
            income_amount = EXCLUDED.income_amount,
            asset_amount = EXCLUDED.asset_amount,
            updated_at = NOW()
    """

    # Filter out orgs without EIN
    valid_orgs = [o for o in orgs if o.get('ein')]

    if len(valid_orgs) < len(orgs):
        print(f"Warning: {len(orgs) - len(valid_orgs)} orgs missing EIN, skipping")

    # Ensure financial fields are correctly typed
    for org in valid_orgs:
        if 'income_amount' in org and org['income_amount'] is not None:
            org['income_amount'] = float(org['income_amount'])
        if 'asset_amount' in org and org['asset_amount'] is not None:
            org['asset_amount'] = float(org['asset_amount'])


    # Execute bulk insert
    cur.executemany(insert_query, valid_orgs)
    conn.commit()

    row_count = cur.rowcount
    print(f"Loaded {row_count:,} organizations")

    # Print statistics
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT state) as states,
            COUNT(*) FILTER (WHERE ntee_code LIKE 'J%%') as labor_related,
            COUNT(*) FILTER (WHERE subsection_code = '05') as labor_orgs_501c5,
            COUNT(*) FILTER (WHERE ntee_code = 'J40') as unions,
            COUNT(ntee_code) as with_ntee_code
        FROM irs_bmf
    """)
    stats = cur.fetchone()

    print(f"\nDatabase Statistics:")
    print(f"  Total organizations: {stats['total']:,}")
    print(f"  States covered: {stats['states']}")
    print(f"  Labor-related (NTEE J*): {stats['labor_related']:,}")
    print(f"  501(c)(5) Labor orgs: {stats['labor_orgs_501c5']:,}")
    print(f"  Unions (NTEE J40): {stats['unions']:,}")
    print(f"  Organizations with NTEE Code: {stats['with_ntee_code']:,} ({100 * stats['with_ntee_code'] / stats['total']:.1f}%)")


    return row_count


def main():
    parser = argparse.ArgumentParser(description='Load IRS BMF data')
    parser.add_argument('--source', choices=['propublica', 'irs_bulk'],
                       default='propublica', help='Data source')
    parser.add_argument('--limit', type=int, help='Limit rows for testing')
    parser.add_argument('--refresh', action='store_true',
                       help='Refresh existing records')
    args = parser.parse_args()

    print("=" * 60)
    print("IRS Business Master File ETL")
    print("=" * 60)

    # Extract
    if args.source == 'propublica':
        raw_orgs = extract_via_propublica(limit=args.limit)
    else:
        raw_orgs = extract_via_irs_bulk()

    if not raw_orgs:
        print("ERROR: No organizations extracted")
        return 1

    # Transform
    print(f"Transforming {len(raw_orgs):,} organizations...")
    transformed = [transform_org(org, source=args.source) for org in raw_orgs]

    # Load
    count = load_to_db(transformed)

    print(f"\nETL Complete: {count:,} organizations loaded")
    print(f"Next step: Claude will implement matching logic")

    return 0


if __name__ == '__main__':
    exit(main())
