"""
Load SEC XBRL financial data from companyfacts.zip into PostgreSQL.

Parses ~19K company JSON files from SEC bulk XBRL data, extracts core
financial tags (Revenue, NetIncome, Assets, Liabilities, Cash, Debt),
and loads into sec_xbrl_financials table keyed on CIK + fiscal year.

Uses tag variant mapping to normalize across different XBRL tag names
for the same concept (e.g., Revenues vs SalesRevenueNet).

Usage:
    py scripts/etl/load_sec_xbrl.py
    py scripts/etl/load_sec_xbrl.py --limit 100       # test with 100 companies
    py scripts/etl/load_sec_xbrl.py --dry-run          # parse only, no DB write
"""

import sys
import os
import json
import re
import io
import time
import zipfile
import argparse

import psycopg2
import psycopg2.extras

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

COMPANYFACTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'sec', 'companyfacts.zip'
)

# Tag variant mapping: concept -> list of XBRL tags in priority order.
# First match wins. Priority = more standard/common tag first.
TAG_MAP = {
    'revenue': [
        'Revenues',
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'SalesRevenueNet',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        'SalesRevenueGoodsNet',
        'SalesRevenueServicesNet',
    ],
    'net_income': [
        'NetIncomeLoss',
        'ProfitLoss',
        'NetIncomeLossAvailableToCommonStockholdersBasic',
    ],
    'total_assets': [
        'Assets',
    ],
    'total_liabilities': [
        'Liabilities',
        'LiabilitiesAndStockholdersEquity',  # fallback: total L+E
    ],
    'cash': [
        'CashAndCashEquivalentsAtCarryingValue',
        'CashCashEquivalentsAndShortTermInvestments',
        'Cash',
    ],
    'long_term_debt': [
        'LongTermDebt',
        'LongTermDebtNoncurrent',
        'LongTermDebtAndCapitalLeaseObligations',
    ],
    'employee_count': [
        'EntityNumberOfEmployees',
    ],
}

# Forms that contain annual financial data
ANNUAL_FORMS = {'10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A'}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sec_xbrl_financials (
    id SERIAL PRIMARY KEY,
    cik INTEGER NOT NULL,
    fiscal_year_end DATE NOT NULL,
    form_type TEXT,
    filed_date DATE,
    revenue NUMERIC,
    revenue_tag TEXT,
    net_income NUMERIC,
    net_income_tag TEXT,
    total_assets NUMERIC,
    total_assets_tag TEXT,
    total_liabilities NUMERIC,
    total_liabilities_tag TEXT,
    cash NUMERIC,
    cash_tag TEXT,
    long_term_debt NUMERIC,
    long_term_debt_tag TEXT,
    employee_count INTEGER,
    employee_count_tag TEXT,
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (cik, fiscal_year_end)
);

CREATE INDEX IF NOT EXISTS idx_sec_xbrl_cik ON sec_xbrl_financials(cik);
CREATE INDEX IF NOT EXISTS idx_sec_xbrl_fy ON sec_xbrl_financials(fiscal_year_end);
CREATE INDEX IF NOT EXISTS idx_sec_xbrl_cik_fy ON sec_xbrl_financials(cik, fiscal_year_end DESC);

COMMENT ON TABLE sec_xbrl_financials IS
    'SEC XBRL annual financial data from companyfacts.zip (~14K companies with 10-K filings)';
"""


def extract_annual_facts(company_data):
    """Extract annual financial facts for a single company.

    Returns list of dicts, one per fiscal year, with financial values
    and the specific tag used for each concept.
    """
    cik = company_data['cik']
    facts = company_data.get('facts', {})
    gaap = facts.get('us-gaap', {})
    dei = facts.get('dei', {})
    all_tags = {**gaap, **dei}

    # Collect all annual data points: {concept: {fiscal_year_end: (value, tag, form, filed)}}
    concept_data = {}

    for concept, tag_variants in TAG_MAP.items():
        concept_data[concept] = {}

        for tag_name in tag_variants:
            tag_obj = all_tags.get(tag_name)
            if not tag_obj:
                continue

            units = tag_obj.get('units', {})
            # Prefer USD, fall back to pure number (for employee_count)
            entries = units.get('USD', []) or units.get('pure', [])

            for entry in entries:
                form = entry.get('form', '')
                if form not in ANNUAL_FORMS:
                    continue

                end_date = entry.get('end')
                if not end_date:
                    continue

                val = entry.get('val')
                if val is None:
                    continue

                filed = entry.get('filed')
                fp = entry.get('fp', '')

                # For income statement items (revenue, net_income), prefer FY period
                # For balance sheet items (assets, liabilities, cash, debt), any annual filing works
                is_income_stmt = concept in ('revenue', 'net_income')
                if is_income_stmt and fp and fp != 'FY':
                    continue

                # Keep latest filing per fiscal year end (amendments override originals)
                existing = concept_data[concept].get(end_date)
                if existing:
                    # Prefer: same tag with later filed date, or higher-priority tag
                    existing_tag_priority = 999
                    new_tag_priority = 999
                    for i, t in enumerate(tag_variants):
                        if t == existing[1]:
                            existing_tag_priority = i
                        if t == tag_name:
                            new_tag_priority = i

                    if new_tag_priority < existing_tag_priority:
                        concept_data[concept][end_date] = (val, tag_name, form, filed)
                    elif new_tag_priority == existing_tag_priority and filed and filed > (existing[3] or ''):
                        concept_data[concept][end_date] = (val, tag_name, form, filed)
                else:
                    concept_data[concept][end_date] = (val, tag_name, form, filed)

            # If we found data for this concept with this tag variant, don't try lower-priority tags
            # UNLESS we want to fill gaps for fiscal years not covered
            # Actually, continue to fill gaps from lower-priority tags

    # Merge all concepts into per-fiscal-year records
    all_fy_ends = set()
    for concept_vals in concept_data.values():
        all_fy_ends.update(concept_vals.keys())

    records = []
    for fy_end in sorted(all_fy_ends):
        record = {
            'cik': cik,
            'fiscal_year_end': fy_end,
            'form_type': None,
            'filed_date': None,
        }

        has_any_value = False
        for concept in TAG_MAP:
            vals = concept_data[concept].get(fy_end)
            if vals:
                value, tag_name, form, filed = vals
                record[concept] = value
                record[f'{concept}_tag'] = tag_name
                if not record['form_type']:
                    record['form_type'] = form
                if not record['filed_date'] or (filed and filed > record['filed_date']):
                    record['filed_date'] = filed
                has_any_value = True
            else:
                record[concept] = None
                record[f'{concept}_tag'] = None

        if has_any_value:
            records.append(record)

    return records


def load_xbrl(limit=None, dry_run=False):
    """Main ETL: parse companyfacts.zip and load into sec_xbrl_financials."""
    start = time.time()

    if not os.path.exists(COMPANYFACTS_PATH):
        print(f"ERROR: {COMPANYFACTS_PATH} not found")
        print("Download from: https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip")
        sys.exit(1)

    print(f"Opening {COMPANYFACTS_PATH}...")
    z = zipfile.ZipFile(COMPANYFACTS_PATH)
    filenames = [n for n in z.namelist() if n.endswith('.json')]
    total_files = len(filenames)
    print(f"Found {total_files:,} company files")

    if limit:
        filenames = filenames[:limit]
        print(f"Limited to {limit} files")

    # Parse all companies
    all_records = []
    companies_with_data = 0
    parse_errors = 0

    for i, fname in enumerate(filenames):
        try:
            data = json.loads(z.read(fname))
            records = extract_annual_facts(data)
            if records:
                all_records.extend(records)
                companies_with_data += 1
        except Exception as e:
            parse_errors += 1
            if parse_errors <= 5:
                print(f"  Parse error on {fname}: {e}")

        if (i + 1) % 2000 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            print(f"  Parsed {i+1:,}/{len(filenames):,} files "
                  f"({companies_with_data:,} with data, {len(all_records):,} records) "
                  f"[{rate:.0f} files/sec]")

    parse_time = time.time() - start
    print(f"\nParsing complete in {parse_time:.1f}s")
    print(f"  Companies with data: {companies_with_data:,} / {len(filenames):,}")
    print(f"  Total annual records: {len(all_records):,}")
    print(f"  Parse errors: {parse_errors:,}")

    if not all_records:
        print("No records to load.")
        return

    # Coverage stats
    concept_counts = {c: 0 for c in TAG_MAP}
    for r in all_records:
        for c in TAG_MAP:
            if r.get(c) is not None:
                concept_counts[c] += 1

    print(f"\n  Coverage across {len(all_records):,} annual records:")
    for concept, count in concept_counts.items():
        print(f"    {concept:20s}: {count:8,} ({100*count/len(all_records):5.1f}%)")

    if dry_run:
        print("\n--dry-run: skipping database load")
        return

    # Load into PostgreSQL
    print(f"\nLoading into sec_xbrl_financials...")
    conn = get_connection()
    cur = conn.cursor()

    # Create table
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    # Use COPY for fast loading via StringIO
    # First truncate existing data
    cur.execute("TRUNCATE sec_xbrl_financials RESTART IDENTITY")

    columns = [
        'cik', 'fiscal_year_end', 'form_type', 'filed_date',
        'revenue', 'revenue_tag', 'net_income', 'net_income_tag',
        'total_assets', 'total_assets_tag', 'total_liabilities', 'total_liabilities_tag',
        'cash', 'cash_tag', 'long_term_debt', 'long_term_debt_tag',
        'employee_count', 'employee_count_tag', 'currency',
    ]

    buf = io.StringIO()
    for r in all_records:
        vals = []
        for col in columns:
            if col == 'currency':
                vals.append('USD')
            elif col == 'employee_count' and r.get(col) is not None:
                vals.append(str(int(r[col])))
            else:
                v = r.get(col)
                if v is None:
                    vals.append('\\N')
                else:
                    vals.append(str(v))
        buf.write('\t'.join(vals) + '\n')

    buf.seek(0)
    cur.copy_from(buf, 'sec_xbrl_financials', columns=columns, null='\\N')
    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM sec_xbrl_financials")
    row_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT cik) FROM sec_xbrl_financials")
    company_count = cur.fetchone()[0]
    cur.execute("SELECT MIN(fiscal_year_end), MAX(fiscal_year_end) FROM sec_xbrl_financials")
    min_fy, max_fy = cur.fetchone()

    # Coverage by concept
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE revenue IS NOT NULL) AS has_revenue,
            COUNT(*) FILTER (WHERE net_income IS NOT NULL) AS has_net_income,
            COUNT(*) FILTER (WHERE total_assets IS NOT NULL) AS has_assets,
            COUNT(*) FILTER (WHERE total_liabilities IS NOT NULL) AS has_liabilities,
            COUNT(*) FILTER (WHERE cash IS NOT NULL) AS has_cash,
            COUNT(*) FILTER (WHERE long_term_debt IS NOT NULL) AS has_debt,
            COUNT(*) FILTER (WHERE employee_count IS NOT NULL) AS has_employees
        FROM sec_xbrl_financials
    """)
    cov = cur.fetchone()

    # How many link to F7 union employers?
    cur.execute("""
        SELECT COUNT(DISTINCT x.cik)
        FROM sec_xbrl_financials x
        JOIN unified_match_log uml ON uml.source_id::int = x.cik
            AND uml.source_system = 'sec'
            AND uml.status = 'active'
    """)
    linked_uml = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT x.cik)
        FROM sec_xbrl_financials x
        JOIN corporate_identifier_crosswalk xw ON xw.sec_cik = x.cik
        WHERE xw.f7_employer_id IS NOT NULL
    """)
    linked_xwalk = cur.fetchone()[0]

    conn.close()
    total_time = time.time() - start

    print(f"\n=== LOAD COMPLETE ({total_time:.1f}s) ===")
    print(f"  Rows loaded: {row_count:,}")
    print(f"  Unique companies: {company_count:,}")
    print(f"  Fiscal year range: {min_fy} to {max_fy}")
    print(f"\n  Coverage (of {row_count:,} annual records):")
    labels = ['revenue', 'net_income', 'assets', 'liabilities', 'cash', 'debt', 'employees']
    for label, count in zip(labels, cov):
        print(f"    {label:20s}: {count:8,} ({100*count/row_count:5.1f}%)")
    print(f"\n  Union-linked companies:")
    print(f"    Via match log: {linked_uml:,}")
    print(f"    Via crosswalk: {linked_xwalk:,}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Load SEC XBRL financials from companyfacts.zip')
    parser.add_argument('--limit', type=int, help='Limit to N companies (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no DB write')
    args = parser.parse_args()

    load_xbrl(limit=args.limit, dry_run=args.dry_run)
