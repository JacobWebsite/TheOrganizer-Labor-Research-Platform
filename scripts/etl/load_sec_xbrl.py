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
    py scripts/etl/load_sec_xbrl.py --cleanup-only     # delete bad dates from existing table
"""

import sys
import os
import json
import io
import time
import zipfile
import argparse
from datetime import date


# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

# --- Date validation bounds (P1-3: SEC XBRL erroneous dates) ---
# Lower bound: SEC EDGAR XBRL data realistically starts around 2009, but
# some companies have fiscal years going back further. 1990 is a safe floor.
FISCAL_YEAR_MIN = 1990
# Upper bound: current calendar year. Any fiscal_year_end beyond Dec 31 of
# this year is almost certainly a data-entry error (e.g., 2201-12-31).
FISCAL_YEAR_MAX = date.today().year

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


def extract_annual_facts(company_data, date_reject_counter=None):
    """Extract annual financial facts for a single company.

    Returns list of dicts, one per fiscal year, with financial values
    and the specific tag used for each concept.

    Args:
        company_data: parsed JSON dict from SEC companyfacts
        date_reject_counter: optional dict to accumulate rejected date counts
                             (keys are the rejected end_date strings)
    """
    cik = company_data['cik']
    facts = company_data.get('facts', {})
    gaap = facts.get('us-gaap', {})
    dei = facts.get('dei', {})
    all_tags = {**gaap, **dei}

    # Build dynamic date bounds from module-level constants
    min_date = f'{FISCAL_YEAR_MIN}-01-01'
    max_date = f'{FISCAL_YEAR_MAX}-12-31'

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

                # P1-3 fix: reject dates outside plausible range.
                # Catches erroneous dates like 2201-12-31 (175 years in
                # the future) that break MAX() aggregations and charts.
                if end_date < min_date or end_date > max_date:
                    if date_reject_counter is not None:
                        date_reject_counter[end_date] = date_reject_counter.get(end_date, 0) + 1
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


def cleanup_bad_dates():
    """P1-3: Delete rows with fiscal_year_end outside the plausible range.

    This fixes existing bad data in the table (e.g., 2201-12-31) that was
    loaded before the date validation was added. Safe to run repeatedly --
    if no bad rows exist, it deletes nothing.
    """
    conn = get_connection()
    cur = conn.cursor()

    # First, show what we'd delete
    cur.execute("""
        SELECT fiscal_year_end, COUNT(*) AS cnt
        FROM sec_xbrl_financials
        WHERE fiscal_year_end < %s OR fiscal_year_end > %s
        GROUP BY fiscal_year_end
        ORDER BY fiscal_year_end
    """, (f'{FISCAL_YEAR_MIN}-01-01', f'{FISCAL_YEAR_MAX}-12-31'))
    bad_rows = cur.fetchall()

    if not bad_rows:
        print("No rows with out-of-range fiscal_year_end found. Table is clean.")
        conn.close()
        return 0

    total_bad = sum(r[1] for r in bad_rows)
    print(f"Found {total_bad:,} rows with out-of-range fiscal_year_end:")
    for fy_end, cnt in bad_rows:
        print(f"  {fy_end}: {cnt:,} rows")

    # Delete them
    cur.execute("""
        DELETE FROM sec_xbrl_financials
        WHERE fiscal_year_end < %s OR fiscal_year_end > %s
    """, (f'{FISCAL_YEAR_MIN}-01-01', f'{FISCAL_YEAR_MAX}-12-31'))
    deleted = cur.rowcount
    conn.commit()

    # Verify MAX is now sane
    cur.execute("SELECT MIN(fiscal_year_end), MAX(fiscal_year_end) FROM sec_xbrl_financials")
    min_fy, max_fy = cur.fetchone()
    print(f"Deleted {deleted:,} bad rows.")
    print(f"Fiscal year range is now: {min_fy} to {max_fy}")

    conn.close()
    return deleted


def load_xbrl(limit=None, dry_run=False, cleanup_only=False):
    """Main ETL: parse companyfacts.zip and load into sec_xbrl_financials.

    If cleanup_only=True, only run the bad-date cleanup (no reload)."""

    # P1-3: Always clean up existing bad dates before a full reload
    if cleanup_only:
        cleanup_bad_dates()
        return
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
    date_rejects = {}  # P1-3: track rejected dates for reporting

    print(f"  Date validation: accepting fiscal_year_end in "
          f"{FISCAL_YEAR_MIN}-01-01 .. {FISCAL_YEAR_MAX}-12-31")

    for i, fname in enumerate(filenames):
        try:
            data = json.loads(z.read(fname))
            records = extract_annual_facts(data, date_reject_counter=date_rejects)
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

    # P1-3: report rejected dates
    total_date_rejects = sum(date_rejects.values())
    if total_date_rejects:
        print(f"  Date-rejected entries: {total_date_rejects:,}")
        # Show the worst offenders (up to 10)
        worst = sorted(date_rejects.items(), key=lambda x: -x[1])[:10]
        for bad_date, cnt in worst:
            print(f"    {bad_date}: {cnt:,} entries rejected")
    else:
        print("  Date-rejected entries: 0")

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
    print("\nLoading into sec_xbrl_financials...")
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

    total_time = time.time() - start

    try:
        from etl_log import log_etl_run
        log_etl_run('sec_xbrl', 'sec_xbrl_financials', row_count, 'success',
                     'scripts/etl/load_sec_xbrl.py',
                     duration_seconds=round(total_time, 2))
    except Exception as log_err:
        print(f"WARNING: ETL log failed: {log_err}")

    conn.close()

    print(f"\n=== LOAD COMPLETE ({total_time:.1f}s) ===")
    print(f"  Rows loaded: {row_count:,}")
    print(f"  Unique companies: {company_count:,}")
    print(f"  Fiscal year range: {min_fy} to {max_fy}")
    print(f"\n  Coverage (of {row_count:,} annual records):")
    labels = ['revenue', 'net_income', 'assets', 'liabilities', 'cash', 'debt', 'employees']
    for label, count in zip(labels, cov):
        print(f"    {label:20s}: {count:8,} ({100*count/row_count:5.1f}%)")
    print("\n  Union-linked companies:")
    print(f"    Via match log: {linked_uml:,}")
    print(f"    Via crosswalk: {linked_xwalk:,}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Load SEC XBRL financials from companyfacts.zip')
    parser.add_argument('--limit', type=int, help='Limit to N companies (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no DB write')
    parser.add_argument('--cleanup-only', action='store_true',
                        help='Only delete rows with out-of-range fiscal_year_end (no reload)')
    args = parser.parse_args()

    load_xbrl(limit=args.limit, dry_run=args.dry_run, cleanup_only=args.cleanup_only)
