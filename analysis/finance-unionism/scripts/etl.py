"""
ETL module for parsing OLMS LM-2 bulk data (2000-2025) into unified DataFrames.

Reads pipe-delimited text files from the OLMS annual disclosure archives and
produces clean, typed DataFrames suitable for financial analysis.

Usage:
    from scripts.etl import load_lm_data, load_financial_tables, load_membership

    lm = load_lm_data(years=range(2000, 2026))
    fin = load_financial_tables(years=range(2000, 2026))
    mem = load_membership(years=range(2000, 2026))
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path

# Default path to the LM-2 bulk data directory
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lm-2 2000_2025"


def _read_pipe_file(path: str, dtype=str) -> pd.DataFrame:
    """Read a pipe-delimited OLMS text file, handling encoding and quoting issues."""
    import csv
    try:
        return pd.read_csv(path, sep='|', dtype=dtype, low_memory=False,
                           encoding='utf-8', on_bad_lines='skip',
                           quoting=csv.QUOTE_NONE)
    except UnicodeDecodeError:
        return pd.read_csv(path, sep='|', dtype=dtype, low_memory=False,
                           encoding='latin-1', on_bad_lines='skip',
                           quoting=csv.QUOTE_NONE)


def _to_numeric(series: pd.Series) -> pd.Series:
    """Convert a string series to numeric, coercing errors to NaN."""
    return pd.to_numeric(series.str.strip() if series.dtype == object else series,
                         errors='coerce')


# ──────────────────────────────────────────────────────────────────────────────
# Core lm_data loader
# ──────────────────────────────────────────────────────────────────────────────

# Columns we actually need from lm_data
LM_DATA_COLS = [
    'UNION_NAME', 'AFF_ABBR', 'F_NUM', 'FYE', 'UNIT_NAME',
    'PD_COVERED_FROM', 'PD_COVERED_TO', 'TERMINATE',
    'TTL_ASSETS', 'TTL_LIABILITIES', 'TTL_RECEIPTS', 'TTL_DISBURSEMENTS',
    'MEMBERS', 'DESIG_NUM', 'DESIG_NAME', 'RPT_ID',
    'YR_COVERED', 'AMENDMENT', 'FORM_TYPE', 'CITY', 'STATE',
]

NUMERIC_LM_COLS = [
    'TTL_ASSETS', 'TTL_LIABILITIES', 'TTL_RECEIPTS', 'TTL_DISBURSEMENTS',
    'MEMBERS', 'RPT_ID', 'AMENDMENT',
]


def load_lm_data(years=None, data_dir=None, lm2_only=True) -> pd.DataFrame:
    """
    Load lm_data files across multiple years into a single DataFrame.

    Args:
        years: iterable of year ints (default: 2000-2025)
        data_dir: path to the LM-2 bulk data directory
        lm2_only: if True, filter to LM-2 form type only (excludes LM-3/4/5)

    Returns:
        DataFrame with all filings, with a 'year' column added
    """
    if years is None:
        years = range(2000, 2026)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    frames = []
    for year in years:
        path = os.path.join(data_dir, str(year), f"lm_data_data_{year}.txt")
        if not os.path.exists(path):
            print(f"  Warning: {path} not found, skipping {year}")
            continue

        df = _read_pipe_file(path)

        # Select and clean columns
        available = [c for c in LM_DATA_COLS if c in df.columns]
        df = df[available].copy()

        # Convert numeric columns
        for col in NUMERIC_LM_COLS:
            if col in df.columns:
                df[col] = _to_numeric(df[col])

        # Clean string columns
        for col in ['UNION_NAME', 'AFF_ABBR', 'F_NUM', 'DESIG_NAME', 'FORM_TYPE']:
            if col in df.columns:
                df[col] = df[col].str.strip()

        # Add year
        df['year'] = year

        # Filter to LM-2 if requested
        if lm2_only:
            df = df[df['FORM_TYPE'] == 'LM-2']

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Compute derived columns
    result['net_assets'] = result['TTL_ASSETS'] - result['TTL_LIABILITIES']
    result['surplus'] = result['TTL_RECEIPTS'] - result['TTL_DISBURSEMENTS']

    # Clean F_NUM to string without decimals
    result['F_NUM'] = result['F_NUM'].astype(str).str.replace('.0', '', regex=False)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Financial detail tables
# ──────────────────────────────────────────────────────────────────────────────

RECEIPTS_COLS = [
    'RPT_ID', 'DUES', 'TAX', 'INVESTMENTS', 'SUPPLIES', 'LOANS_MADE',
    'INTEREST', 'DIVIDENDS', 'RENTS', 'FEES', 'LOANS_OBTAINED',
    'OTHER_RECEIPTS', 'AFFILIATES', 'MEMBERS',
    'INV_SALE_REINVESTMENTS', 'ALL_OTHER_RECEIPTS',
]

DISBURSEMENTS_COLS = [
    'RPT_ID', 'REPRESENTATIONAL', 'POLITICAL', 'CONTRIBUTIONS',
    'GENERAL_OVERHEAD', 'UNION_ADMINISTRATION', 'STRIKE_BENEFITS',
    'PER_CAPITA_TAX', 'TO_OFFICERS', 'BENEFITS', 'TO_EMPLOYEES',
    'AFFILIATES', 'OTHER_DISBURSEMENTS',
    'INV_PURCH_REINVESTMENTS', 'ALL_OTHER_REP_ACTIVITIES',
    'ALL_OTHER_POL_ACTIVITIES', 'ALL_OTHER_CONTRIBUTIONS',
    'ALL_OTHER_GEN_OVERHEAD', 'ALL_OTHER_UNION_ADMIN',
    'OFF_ADMIN_EXPENSE', 'EDU_PUB_EXPENSE', 'PRO_FEES',
]

ASSETS_COLS = [
    'RPT_ID', 'CASH_START', 'CASH_END',
    'ACCOUNTS_RECEIVABLE_START', 'ACCOUNTS_RECEIVABLE_END',
    'INVESTMENTS_START', 'INVESTMENTS_END',
    'FIXED_ASSETS_START', 'FIXED_ASSETS_END',
    'TREASURY_SECURITIES_START', 'TREASURY_SECURITIES_END',
    'OTHER_ASSETS_START', 'OTHER_ASSETS_END',
    'LOANS_RECEIVABLE_START', 'LOANS_RECEIVABLE_END',
    'TOTAL_START',
]

LIABILITIES_COLS = [
    'RPT_ID', 'ACCOUNTS_PAYABLE_START', 'ACCOUNTS_PAYABLE_END',
    'LOANS_PAYABLE_START', 'LOANS_PAYABLE_END',
    'MORTGAGE_PAYABLE_START', 'MORTGAGE_PAYABLE_END',
    'OTHER_LIABILITIES_START', 'OTHER_LIABILITIES_END',
    'TOTAL_START',
]


def _load_table(table_name: str, cols: list, years, data_dir) -> pd.DataFrame:
    """Generic loader for a specific OLMS table across years."""
    if years is None:
        years = range(2000, 2026)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    frames = []
    for year in years:
        path = os.path.join(data_dir, str(year), f"ar_{table_name}_data_{year}.txt")
        if not os.path.exists(path):
            continue

        df = _read_pipe_file(path)
        available = [c for c in cols if c in df.columns]
        df = df[available].copy()

        # Convert all non-RPT_ID columns to numeric
        for col in df.columns:
            if col != 'RPT_ID':
                df[col] = _to_numeric(df[col])

        df['RPT_ID'] = _to_numeric(df['RPT_ID'])
        df['year'] = year
        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_receipts(years=None, data_dir=None) -> pd.DataFrame:
    """Load receipts_total across years. Join to lm_data via RPT_ID."""
    return _load_table('receipts_total', RECEIPTS_COLS, years, data_dir)


def load_disbursements(years=None, data_dir=None) -> pd.DataFrame:
    """Load disbursements_total across years. Join to lm_data via RPT_ID."""
    return _load_table('disbursements_total', DISBURSEMENTS_COLS, years, data_dir)


def load_assets(years=None, data_dir=None) -> pd.DataFrame:
    """Load assets_total across years. Join to lm_data via RPT_ID."""
    return _load_table('assets_total', ASSETS_COLS, years, data_dir)


def load_liabilities(years=None, data_dir=None) -> pd.DataFrame:
    """Load liabilities_total across years. Join to lm_data via RPT_ID."""
    return _load_table('liabilities_total', LIABILITIES_COLS, years, data_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Membership detail
# ──────────────────────────────────────────────────────────────────────────────

def load_membership(years=None, data_dir=None) -> pd.DataFrame:
    """
    Load membership detail (categories like full dues, agency fee, etc.)
    Join to lm_data via RPT_ID.
    """
    if years is None:
        years = range(2000, 2026)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    frames = []
    for year in years:
        path = os.path.join(data_dir, str(year), f"ar_membership_data_{year}.txt")
        if not os.path.exists(path):
            continue

        df = _read_pipe_file(path)
        df['RPT_ID'] = _to_numeric(df['RPT_ID'])
        df['NUMBER'] = _to_numeric(df['NUMBER'])
        df['year'] = year

        # Clean string columns
        for col in ['MEMBERSHIP_TYPE', 'CATEGORY', 'VOTING_ELIGIBILITY']:
            if col in df.columns:
                df[col] = df[col].str.strip()

        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# Strike fund / benefits detail
# ──────────────────────────────────────────────────────────────────────────────

def load_benefits_detail(years=None, data_dir=None) -> pd.DataFrame:
    """
    Load disbursements_benefits detail (individual strike fund payouts, etc.)
    Join to lm_data via RPT_ID.
    """
    return _load_table('disbursements_benefits',
                       ['OID', 'DESCRIPTION', 'PAID_TO', 'AMOUNT', 'RPT_ID'],
                       years, data_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Payer/Payee schedules
# ──────────────────────────────────────────────────────────────────────────────

def load_payer_payee(years=None, data_dir=None) -> pd.DataFrame:
    """Load payer/payee schedule data for fund flow analysis."""
    if years is None:
        years = range(2000, 2026)
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    frames = []
    for year in years:
        path = os.path.join(data_dir, str(year), f"ar_payer_payee_data_{year}.txt")
        if not os.path.exists(path):
            continue

        df = _read_pipe_file(path)
        df['RPT_ID'] = _to_numeric(df['RPT_ID'])
        df['year'] = year

        # Convert amount columns to numeric
        for col in df.columns:
            if 'AMOUNT' in col.upper() or 'TOTAL' in col.upper():
                df[col] = _to_numeric(df[col])

        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: build full financial dataset for a set of unions
# ──────────────────────────────────────────────────────────────────────────────

def build_union_financials(lm: pd.DataFrame, years=None, data_dir=None) -> pd.DataFrame:
    """
    Given a filtered lm_data DataFrame (e.g. NHQ filings only),
    join receipts, disbursements, and assets detail.

    Returns merged DataFrame with all financial detail columns.
    """
    rpt_ids = set(lm['RPT_ID'].dropna().astype(int))

    # Load detail tables
    receipts = load_receipts(years, data_dir)
    disbursements = load_disbursements(years, data_dir)

    # Filter to relevant RPT_IDs
    receipts = receipts[receipts['RPT_ID'].isin(rpt_ids)]
    disbursements = disbursements[disbursements['RPT_ID'].isin(rpt_ids)]

    # Merge
    result = lm.merge(receipts.drop(columns=['year'], errors='ignore'),
                      on='RPT_ID', how='left', suffixes=('', '_rcpt'))
    result = result.merge(disbursements.drop(columns=['year'], errors='ignore'),
                          on='RPT_ID', how='left', suffixes=('', '_disb'))

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Top internationals filter
# ──────────────────────────────────────────────────────────────────────────────

def identify_nhq_filings(lm: pd.DataFrame) -> pd.DataFrame:
    """Filter to National HQ filings only (DESIG_NAME == 'NHQ')."""
    return lm[lm['DESIG_NAME'].str.strip().str.upper() == 'NHQ'].copy()


def top_internationals(lm: pd.DataFrame, n: int = 30,
                       reference_year: int = 2024) -> list:
    """
    Identify the top N international unions by membership in a reference year.

    Returns list of (AFF_ABBR, F_NUM, UNION_NAME) tuples.
    """
    nhq = identify_nhq_filings(lm)
    ref = nhq[nhq['year'] == reference_year].nlargest(n, 'MEMBERS')

    return list(ref[['AFF_ABBR', 'F_NUM', 'UNION_NAME']].itertuples(index=False, name=None))


if __name__ == '__main__':
    print("Loading all LM-2 data (2000-2025)...")
    lm = load_lm_data()
    print(f"  Total LM-2 filings: {len(lm):,}")

    nhq = identify_nhq_filings(lm)
    print(f"  NHQ filings: {len(nhq):,}")

    top = top_internationals(lm, n=30)
    print(f"\nTop 30 internationals (by 2024 membership):")
    for aff, fnum, name in top:
        print(f"  {aff:10s}  F#{fnum:>7s}  {name}")
