"""
Fetch USASpending federal contract recipients via paginated search API.

Strategy: For each state, fetch top contract awards sorted by amount desc.
Collect unique recipients (name + state). We don't need ALL 5.9M transactions -
the top awards per state capture the significant federal contractors.
"""
import requests
import time
import re
import psycopg2
from psycopg2.extras import execute_values
from collections import defaultdict
import os

API_BASE = "https://api.usaspending.gov/api/v2"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) labor-research/1.0',
}

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

STATES = [
    'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA',
    'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
    'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
    'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'
]

MAX_PAGES_PER_STATE = 100  # 100 pages x 100/page = 10,000 awards per state


def normalize_name(name):
    if not name:
        return ''
    result = name.lower().strip()
    result = re.sub(r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\b\.?', '', result)
    result = re.sub(r'\bd/?b/?a\b\.?', '', result)
    result = re.sub(r'[^\w\s]', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def fetch_state_awards(state, fiscal_year=2024):
    """Fetch top contract awards for a state."""
    recipients = {}
    total_awards = 0

    for page in range(1, MAX_PAGES_PER_STATE + 1):
        try:
            resp = requests.post(f"{API_BASE}/search/spending_by_award/", json={
                "filters": {
                    "award_type_codes": ["A", "B", "C", "D"],
                    "time_period": [{
                        "start_date": f"{fiscal_year - 1}-10-01",
                        "end_date": f"{fiscal_year}-09-30"
                    }],
                    "recipient_locations": [{"country": "USA", "state": state}]
                },
                "fields": [
                    "Recipient Name", "Recipient UEI",
                    "Award Amount", "NAICS Code", "NAICS Description",
                    "Awarding Agency"
                ],
                "limit": 100,
                "page": page,
                "sort": "Award Amount",
                "order": "desc",
                "subawards": False
            }, headers=HEADERS, timeout=60)

            if resp.status_code == 422:
                # Past last page
                break
            if not resp.ok:
                if page > 1:
                    break
                time.sleep(2)
                continue

            data = resp.json()
            results = data.get("results", [])

            if not results:
                break

            for r in results:
                name = r.get("Recipient Name", "")
                if not name or len(name) < 2 or name.upper() in ('MULTIPLE RECIPIENTS', 'REDACTED DUE TO PII'):
                    continue

                name_norm = normalize_name(name)
                if not name_norm or len(name_norm) < 3:
                    continue

                key = (name_norm, state)
                amount = r.get("Award Amount", 0) or 0

                if key not in recipients:
                    recipients[key] = {
                        'name': name,
                        'name_normalized': name_norm,
                        'uei': None,
                        'state': state,
                        'naics': None,
                        'naics_desc': None,
                        'total_amount': 0,
                        'contract_count': 0,
                        'agencies': set(),
                    }

                rec = recipients[key]
                rec['total_amount'] += float(amount) if amount else 0
                rec['contract_count'] += 1

                uei = r.get("Recipient UEI")
                if uei and len(str(uei)) == 12 and not rec['uei']:
                    rec['uei'] = str(uei)
                if not rec['naics'] and r.get("NAICS Code"):
                    rec['naics'] = str(r["NAICS Code"])
                    rec['naics_desc'] = r.get("NAICS Description", "")
                agency = r.get("Awarding Agency")
                if agency:
                    rec['agencies'].add(agency)

            total_awards += len(results)

            has_next = data.get("page_metadata", {}).get("hasNext", False)
            if not has_next:
                break

            # Rate limit: 1 req/100ms
            time.sleep(0.1)

        except requests.Timeout:
            time.sleep(2)
            continue
        except Exception as e:
            print(f"    Error {state} p{page}: {e}")
            time.sleep(1)
            if page > 3:
                break
            continue

    return recipients, total_awards


def main():
    fiscal_year = 2024
    all_recipients = {}
    total_awards = 0

    print(f"=== Fetching FY{fiscal_year} federal contract recipients ===")
    print(f"  States: {len(STATES)}, max {MAX_PAGES_PER_STATE * 100:,} awards/state")

    for i, state in enumerate(STATES):
        state_recs, state_awards = fetch_state_awards(state, fiscal_year)

        # Merge into global dict
        for key, rec in state_recs.items():
            if key not in all_recipients:
                all_recipients[key] = rec
            else:
                # Shouldn't happen since keyed by (name, state), but just in case
                existing = all_recipients[key]
                existing['total_amount'] += rec['total_amount']
                existing['contract_count'] += rec['contract_count']
                if not existing['uei'] and rec['uei']:
                    existing['uei'] = rec['uei']
                if not existing['naics'] and rec['naics']:
                    existing['naics'] = rec['naics']
                    existing['naics_desc'] = rec['naics_desc']

        total_awards += state_awards
        print(f"  [{i+1}/{len(STATES)}] {state}: {state_awards:,} awards -> {len(state_recs):,} recipients (cumul: {len(all_recipients):,})")

    print(f"\n  TOTAL: {total_awards:,} awards -> {len(all_recipients):,} unique recipients")

    # Load to DB
    print(f"\n=== Loading to PostgreSQL ===")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS federal_contract_recipients (
            id SERIAL PRIMARY KEY,
            recipient_name TEXT,
            recipient_name_normalized TEXT,
            recipient_uei TEXT,
            recipient_state TEXT,
            recipient_city TEXT,
            recipient_zip TEXT,
            naics_code TEXT,
            naics_description TEXT,
            total_obligations NUMERIC,
            contract_count INTEGER,
            fiscal_year INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    cur.execute("DELETE FROM federal_contract_recipients WHERE fiscal_year = %s", (fiscal_year,))
    deleted = cur.rowcount
    if deleted > 0:
        print(f"  Cleared {deleted:,} previous FY{fiscal_year} rows")
    conn.commit()

    batch = []
    for key, r in all_recipients.items():
        batch.append((
            r['name'], r['name_normalized'], r.get('uei'),
            r['state'], None, None,  # city/zip not in search results
            r.get('naics'), r.get('naics_desc'),
            r['total_amount'], r['contract_count'], fiscal_year
        ))

    if batch:
        execute_values(cur, """
            INSERT INTO federal_contract_recipients
                (recipient_name, recipient_name_normalized, recipient_uei,
                 recipient_state, recipient_city, recipient_zip,
                 naics_code, naics_description,
                 total_obligations, contract_count, fiscal_year)
            VALUES %s
        """, batch, page_size=5000)
        conn.commit()
        print(f"  Inserted {len(batch):,} rows")

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_name ON federal_contract_recipients(recipient_name_normalized)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_uei ON federal_contract_recipients(recipient_uei) WHERE recipient_uei IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_state ON federal_contract_recipients(recipient_state)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_naics ON federal_contract_recipients(naics_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fcr_name_state ON federal_contract_recipients(recipient_name_normalized, recipient_state)")
    conn.commit()
    print("  Indexes created")

    # Summary
    print(f"\n=== SUMMARY ===")
    with_uei = sum(1 for r in all_recipients.values() if r.get('uei'))
    with_naics = sum(1 for r in all_recipients.values() if r.get('naics'))
    print(f"  Total recipients: {len(all_recipients):,}")
    print(f"  With UEI: {with_uei:,} ({100*with_uei/max(len(all_recipients),1):.1f}%)")
    print(f"  With NAICS: {with_naics:,} ({100*with_naics/max(len(all_recipients),1):.1f}%)")

    # Top states
    states = defaultdict(int)
    for (_, st), _ in all_recipients.items():
        states[st] += 1
    top = sorted(states.items(), key=lambda x: -x[1])[:10]
    print(f"  Top states: {', '.join(f'{s}:{c:,}' for s,c in top)}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
