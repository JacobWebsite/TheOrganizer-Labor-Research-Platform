"""
Universal Mergent Intellect Loader
===================================
Loads all 3 sheets from Mergent xlsx-as-csv files into PostgreSQL:
  Sheet 1 (Company Details, 55 cols) -> mergent_employers (UPSERT by DUNS)
  Sheet 2 (Financial Info, 239 cols) -> mergent_financials (UPSERT by DUNS+year)
  Sheet 3 (Executive, 13 cols)       -> mergent_executives (UPSERT by DUNS+name)

Files are Excel .xlsx internally with .csv extensions. Sheet 1 is parsed with
pandas. Sheets 2-3 use raw XML parsing (zipfile + ElementTree) because openpyxl
crashes on whitespace-only cells in the Financial Info sheet.

Usage:
  py scripts/etl/load_mergent_universal.py                    # load all files
  py scripts/etl/load_mergent_universal.py --dry-run           # parse only, no DB writes
  py scripts/etl/load_mergent_universal.py --limit 3           # first 3 files
  py scripts/etl/load_mergent_universal.py --status            # show progress
  py scripts/etl/load_mergent_universal.py --sheet 1           # only Sheet 1
  py scripts/etl/load_mergent_universal.py --force             # reload already-loaded files
"""

import argparse
import glob
import os
import re
import shutil
import tempfile
import time
import traceback
import zipfile
from xml.etree import ElementTree as ET

import pandas as pd
from psycopg2.extras import execute_values

from db_config import get_connection

# ============================================================
# CONSTANTS
# ============================================================

BASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "All Mergent loads",
)

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

SECTOR_MAP = {
    "621": "HEALTHCARE_AMBULATORY",
    "622": "HEALTHCARE_HOSPITALS",
    "623": "HEALTHCARE_NURSING",
    "624": "SOCIAL_SERVICES",
    "611": "EDUCATION",
    "561": "BUILDING_SERVICES",
    "541": "PROFESSIONAL",
    "485": "TRANSIT",
    "488": "TRANSIT",
    "221": "UTILITIES",
    "721": "HOSPITALITY",
    "722": "FOOD_SERVICE",
    "813": "CIVIC_ORGANIZATIONS",
    "921": "GOVERNMENT",
    "922": "GOVERNMENT",
    "923": "GOVERNMENT",
    "924": "GOVERNMENT",
    "925": "GOVERNMENT",
    "926": "GOVERNMENT",
    "513": "BROADCASTING",
    "516": "PUBLISHING",
    "519": "INFORMATION",
    "562": "WASTE_MGMT",
    "811": "REPAIR_SERVICES",
    "711": "ARTS_ENTERTAINMENT",
    "712": "MUSEUMS",
}

STATE_MAP = {
    "NEW YORK": "NY", "CALIFORNIA": "CA", "TEXAS": "TX", "FLORIDA": "FL",
    "ILLINOIS": "IL", "PENNSYLVANIA": "PA", "OHIO": "OH", "GEORGIA": "GA",
    "NORTH CAROLINA": "NC", "MICHIGAN": "MI", "NEW JERSEY": "NJ", "VIRGINIA": "VA",
    "WASHINGTON": "WA", "ARIZONA": "AZ", "MASSACHUSETTS": "MA", "TENNESSEE": "TN",
    "INDIANA": "IN", "MARYLAND": "MD", "MISSOURI": "MO", "WISCONSIN": "WI",
    "COLORADO": "CO", "MINNESOTA": "MN", "SOUTH CAROLINA": "SC", "ALABAMA": "AL",
    "LOUISIANA": "LA", "KENTUCKY": "KY", "OREGON": "OR", "OKLAHOMA": "OK",
    "CONNECTICUT": "CT", "UTAH": "UT", "IOWA": "IA", "NEVADA": "NV",
    "ARKANSAS": "AR", "MISSISSIPPI": "MS", "KANSAS": "KS", "NEW MEXICO": "NM",
    "NEBRASKA": "NE", "WEST VIRGINIA": "WV", "IDAHO": "ID", "HAWAII": "HI",
    "NEW HAMPSHIRE": "NH", "MAINE": "ME", "MONTANA": "MT", "RHODE ISLAND": "RI",
    "DELAWARE": "DE", "SOUTH DAKOTA": "SD", "NORTH DAKOTA": "ND", "ALASKA": "AK",
    "VERMONT": "VT", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC",
    "PUERTO RICO": "PR", "GUAM": "GU", "VIRGIN ISLANDS": "VI",
}

# Year1-5 financial metrics we care about (organizing value)
YEAR_N_METRICS = {
    "Total Revenue": "total_revenue",
    "Net Income": "net_income",
    "Total Assets": "total_assets",
    "Total Liabilities": "total_liabilities",
    "EBITDA": "ebitda",
    "Operating Income": "operating_income",
    "Long Term Debt": "long_term_debt",
    "Stockholders' Equity": "stockholders_equity",
    "Cash & Cash Equivalents, End of Year": "cash_end_of_year",
}


# ============================================================
# CLEANING FUNCTIONS (from load_mergent_al_fl.py)
# ============================================================

def clean_duns(val):
    if pd.isna(val) or val is None:
        return None
    return str(val).replace("-", "").strip()


def clean_ein(val):
    if pd.isna(val) or val is None:
        return None
    try:
        ein = str(int(float(val)))
        if len(ein) == 8:
            ein = "0" + ein
        return ein
    except (ValueError, TypeError):
        return None


def clean_zip(val):
    if pd.isna(val) or val is None:
        return None
    try:
        z = str(int(float(val)))
        if len(z) == 4:
            z = "0" + z
        elif len(z) > 5:
            z = z[:5]
        return z
    except (ValueError, TypeError):
        return str(val)[:5] if val else None


def clean_state(val):
    if pd.isna(val) or val is None:
        return None
    val = str(val).strip().upper()
    if len(val) <= 2:
        return val[:2]
    return STATE_MAP.get(val, val[:2])


def normalize_name(name):
    if not name or pd.isna(name):
        return None
    name = str(name).lower().strip()
    for suffix in [" llc", " inc", " corp", " ltd", " co", " company",
                   " corporation", " incorporated", " limited", ".", ",", '"', "'", " the"]:
        name = name.replace(suffix, "")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def parse_employees(val):
    if pd.isna(val) or val is None:
        return None
    try:
        val = str(val).replace(",", "")
        return int(float(val))
    except (ValueError, TypeError):
        return None


def parse_sales(val):
    if pd.isna(val) or val is None:
        return None, None
    raw = str(val).strip()
    try:
        numeric = float(raw.replace("$", "").replace(",", ""))
        return numeric, raw
    except (ValueError, TypeError):
        return None, raw


def get_sector(naics_code):
    if pd.isna(naics_code) or naics_code is None:
        return "OTHER"
    try:
        naics_str = str(int(float(naics_code)))[:3]
    except (ValueError, TypeError):
        return "OTHER"
    return SECTOR_MAP.get(naics_str, "OTHER")


def safe_str(val, max_len=None):
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    if max_len:
        s = s[:max_len]
    return s


def safe_float(val):
    if val is None or str(val).strip() in ("", " "):
        return None
    try:
        return float(str(val).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def safe_int(val):
    if val is None or str(val).strip() in ("", " "):
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


def clean_naics(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return str(int(float(val)))[:6]
    except (ValueError, TypeError):
        return None


def clean_sic(val):
    if pd.isna(val) or val is None:
        return None
    try:
        return str(int(float(val)))[:8]
    except (ValueError, TypeError):
        return None


# ============================================================
# SHEET 1: COMPANY DETAILS (pandas)
# ============================================================

def parse_sheet1_pandas(filepath):
    """Parse Sheet 1 (Company Details) using pandas. Returns list of tuples."""
    tmp = tempfile.mktemp(suffix=".xlsx")
    shutil.copy2(filepath, tmp)
    try:
        df = pd.read_excel(tmp, sheet_name=0, engine="openpyxl")
    finally:
        os.unlink(tmp)

    records = []
    skipped = 0
    for _, row in df.iterrows():
        company_name = row.get("Company Name")
        if not company_name or pd.isna(company_name):
            skipped += 1
            continue

        duns = clean_duns(row.get("D-U-N-S@ Number"))
        if not duns:
            skipped += 1
            continue

        naics_primary = row.get("Primary NAICS Code")
        sector = get_sector(naics_primary)
        state = clean_state(row.get("Physical State"))
        sales_amount, sales_raw = parse_sales(row.get("Sales"))
        sales_prior, _ = parse_sales(row.get("Sales (Year 1)"))

        records.append((
            duns,
            clean_ein(row.get("Employer ID Number (EIN)")),
            clean_duns(row.get("Global Duns No")),
            clean_duns(row.get("Immediate Parent Duns No")),
            safe_str(row.get("Immediate Parent Name")),
            clean_duns(row.get("Domestic Parent Duns No")),
            safe_str(row.get("Domestic Parent Name")),
            str(company_name).strip(),
            normalize_name(company_name),
            safe_str(row.get("Trade Style")),
            safe_str(row.get("Former Name")),
            safe_str(row.get("Company Type"), 50),
            safe_str(row.get("Subsidiary Status"), 50),
            safe_str(row.get("Location Type"), 50),
            safe_str(row.get("Physical Address"), 500),
            safe_str(row.get("Physical City"), 100),
            state,
            clean_zip(row.get("Physical Zipcode")),
            safe_str(row.get("Physical County"), 100),
            float(row.get("Latitude")) if pd.notna(row.get("Latitude")) else None,
            float(row.get("Longtitude")) if pd.notna(row.get("Longtitude")) else None,
            safe_str(row.get("Mailing Address"), 500),
            safe_str(row.get("Mailing City"), 100),
            clean_state(row.get("Mailing State")),
            clean_zip(row.get("Mailing Zipcode")),
            parse_employees(row.get("Employee this Site")),
            parse_employees(row.get("Employee All Sites")),
            sales_amount,
            sales_raw,
            int(float(row.get("Year of Founding"))) if pd.notna(row.get("Year of Founding")) else None,
            clean_naics(naics_primary),
            safe_str(row.get("Primary NAICS Description")),
            clean_naics(row.get("Secondary NAICS Code")),
            safe_str(row.get("Secondary NAICS Description")),
            clean_sic(row.get("Primary SIC Code")),
            safe_str(row.get("Primary SIC Description")),
            clean_sic(row.get("Secondary SIC Code")),
            safe_str(row.get("Secondary SIC Description")),
            safe_str(row.get("Line of Business")),
            safe_str(row.get("Phone No"), 20),
            safe_str(row.get("Web Address (URL)")),
            sector,
            row.get("Manufacturing Indicator") == "Manufacturer",
            row.get("Minority Owned Indicator") == "Yes",
            safe_str(row.get("Global Name")),
            sales_prior,
            parse_employees(row.get("Employees Total (Year 1)")),
        ))

    return records, skipped


UPSERT_EMPLOYER_SQL = """
    INSERT INTO mergent_employers (
        duns, ein, global_duns, parent_duns, parent_name,
        domestic_parent_duns, domestic_parent_name,
        company_name, company_name_normalized, trade_name, former_name,
        company_type, subsidiary_status, location_type,
        street_address, city, state, zip, county,
        latitude, longitude,
        mailing_address, mailing_city, mailing_state, mailing_zip,
        employees_site, employees_all_sites, sales_amount, sales_raw,
        year_founded, naics_primary, naics_primary_desc,
        naics_secondary, naics_secondary_desc,
        sic_primary, sic_primary_desc, sic_secondary, sic_secondary_desc,
        line_of_business, phone, website,
        sector_category, manufacturing_indicator, minority_owned,
        global_name, sales_prior_year, employees_prior_year,
        source_file, source_batch
    )
    VALUES %s
    ON CONFLICT (duns) DO UPDATE SET
        ein = COALESCE(EXCLUDED.ein, mergent_employers.ein),
        global_duns = COALESCE(EXCLUDED.global_duns, mergent_employers.global_duns),
        parent_duns = COALESCE(EXCLUDED.parent_duns, mergent_employers.parent_duns),
        parent_name = COALESCE(EXCLUDED.parent_name, mergent_employers.parent_name),
        domestic_parent_duns = COALESCE(EXCLUDED.domestic_parent_duns, mergent_employers.domestic_parent_duns),
        domestic_parent_name = COALESCE(EXCLUDED.domestic_parent_name, mergent_employers.domestic_parent_name),
        company_name = COALESCE(EXCLUDED.company_name, mergent_employers.company_name),
        company_name_normalized = COALESCE(EXCLUDED.company_name_normalized, mergent_employers.company_name_normalized),
        trade_name = COALESCE(EXCLUDED.trade_name, mergent_employers.trade_name),
        former_name = COALESCE(EXCLUDED.former_name, mergent_employers.former_name),
        company_type = COALESCE(EXCLUDED.company_type, mergent_employers.company_type),
        subsidiary_status = COALESCE(EXCLUDED.subsidiary_status, mergent_employers.subsidiary_status),
        location_type = COALESCE(EXCLUDED.location_type, mergent_employers.location_type),
        street_address = COALESCE(EXCLUDED.street_address, mergent_employers.street_address),
        city = COALESCE(EXCLUDED.city, mergent_employers.city),
        state = COALESCE(EXCLUDED.state, mergent_employers.state),
        zip = COALESCE(EXCLUDED.zip, mergent_employers.zip),
        county = COALESCE(EXCLUDED.county, mergent_employers.county),
        latitude = COALESCE(EXCLUDED.latitude, mergent_employers.latitude),
        longitude = COALESCE(EXCLUDED.longitude, mergent_employers.longitude),
        mailing_address = COALESCE(EXCLUDED.mailing_address, mergent_employers.mailing_address),
        mailing_city = COALESCE(EXCLUDED.mailing_city, mergent_employers.mailing_city),
        mailing_state = COALESCE(EXCLUDED.mailing_state, mergent_employers.mailing_state),
        mailing_zip = COALESCE(EXCLUDED.mailing_zip, mergent_employers.mailing_zip),
        employees_site = COALESCE(EXCLUDED.employees_site, mergent_employers.employees_site),
        employees_all_sites = COALESCE(EXCLUDED.employees_all_sites, mergent_employers.employees_all_sites),
        sales_amount = COALESCE(EXCLUDED.sales_amount, mergent_employers.sales_amount),
        sales_raw = COALESCE(EXCLUDED.sales_raw, mergent_employers.sales_raw),
        year_founded = COALESCE(EXCLUDED.year_founded, mergent_employers.year_founded),
        naics_primary = COALESCE(EXCLUDED.naics_primary, mergent_employers.naics_primary),
        naics_primary_desc = COALESCE(EXCLUDED.naics_primary_desc, mergent_employers.naics_primary_desc),
        naics_secondary = COALESCE(EXCLUDED.naics_secondary, mergent_employers.naics_secondary),
        naics_secondary_desc = COALESCE(EXCLUDED.naics_secondary_desc, mergent_employers.naics_secondary_desc),
        sic_primary = COALESCE(EXCLUDED.sic_primary, mergent_employers.sic_primary),
        sic_primary_desc = COALESCE(EXCLUDED.sic_primary_desc, mergent_employers.sic_primary_desc),
        sic_secondary = COALESCE(EXCLUDED.sic_secondary, mergent_employers.sic_secondary),
        sic_secondary_desc = COALESCE(EXCLUDED.sic_secondary_desc, mergent_employers.sic_secondary_desc),
        line_of_business = COALESCE(EXCLUDED.line_of_business, mergent_employers.line_of_business),
        phone = COALESCE(EXCLUDED.phone, mergent_employers.phone),
        website = COALESCE(EXCLUDED.website, mergent_employers.website),
        sector_category = COALESCE(EXCLUDED.sector_category, mergent_employers.sector_category),
        manufacturing_indicator = COALESCE(EXCLUDED.manufacturing_indicator, mergent_employers.manufacturing_indicator),
        minority_owned = COALESCE(EXCLUDED.minority_owned, mergent_employers.minority_owned),
        global_name = COALESCE(EXCLUDED.global_name, mergent_employers.global_name),
        sales_prior_year = COALESCE(EXCLUDED.sales_prior_year, mergent_employers.sales_prior_year),
        employees_prior_year = COALESCE(EXCLUDED.employees_prior_year, mergent_employers.employees_prior_year),
        source_file = EXCLUDED.source_file,
        source_batch = EXCLUDED.source_batch,
        updated_at = NOW()
"""


def upsert_employers(cur, records, source_file, source_batch):
    """UPSERT Sheet 1 records into mergent_employers."""
    if not records:
        return 0
    # Append source_file and source_batch to each record tuple
    full_records = [r + (source_file, source_batch) for r in records]
    execute_values(cur, UPSERT_EMPLOYER_SQL, full_records, page_size=500)
    return len(full_records)


# ============================================================
# SHEET 2: FINANCIAL INFO (XML parsing)
# ============================================================

def _parse_xml_sheet(filepath, sheet_num):
    """Parse a sheet from an xlsx-disguised-as-csv via raw XML.
    Returns (headers_list, data_rows) where each data_row is a dict {col_index: value}.
    """
    with zipfile.ZipFile(filepath) as zf:
        sheet_file = f"xl/worksheets/sheet{sheet_num}.xml"
        if sheet_file not in zf.namelist():
            return [], []

        tree = ET.parse(zf.open(sheet_file))

    rows = tree.findall(".//s:sheetData/s:row", NS)
    if not rows:
        return [], []

    def col_to_idx(ref):
        letters = re.match(r"([A-Z]+)", ref).group(1)
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1  # 0-based

    def extract_row(row_el):
        vals = {}
        for c in row_el.findall("s:c", NS):
            ref = c.get("r", "")
            idx = col_to_idx(ref)
            # Try inline string first
            is_el = c.find("s:is", NS)
            if is_el is not None:
                t_el = is_el.find("s:t", NS)
                vals[idx] = t_el.text if t_el is not None else None
            else:
                v_el = c.find("s:v", NS)
                if v_el is not None and v_el.text is not None:
                    vals[idx] = v_el.text
        return vals

    # Headers from first row
    h_vals = extract_row(rows[0])
    max_col = max(h_vals.keys()) if h_vals else 0
    headers = [h_vals.get(i) for i in range(max_col + 1)]

    # Data rows
    data_rows = []
    for row_el in rows[1:]:
        data_rows.append(extract_row(row_el))

    return headers, data_rows


def parse_sheet2_financials(filepath):
    """Parse Sheet 2 (Financial Info). Returns list of (duns, year, metrics_dict) tuples."""
    headers, data_rows = _parse_xml_sheet(filepath, 2)
    if not headers or not data_rows:
        return []

    # Build column mappings
    # Absolute year columns: "YYYY Sales Volume", "YYYY Employee All Sites", "YYYY Employee This Site"
    abs_year_re = re.compile(r"^(\d{4})\s+(.+)$")
    # Relative year columns: "YearN MetricName"
    rel_year_re = re.compile(r"^Year(\d)\s+(.+)$")

    abs_cols = {}  # {col_idx: (year, metric)}
    rel_cols = {}  # {col_idx: (year_offset, metric)}
    duns_col = None

    for i, h in enumerate(headers):
        if not h:
            continue
        h = h.strip()
        if h == "D-U-N-S@ Number":
            duns_col = i
            continue
        m = abs_year_re.match(h)
        if m:
            year = int(m.group(1))
            metric = m.group(2).strip()
            abs_cols[i] = (year, metric)
            continue
        m = rel_year_re.match(h)
        if m:
            offset = int(m.group(1))
            metric = m.group(2).strip()
            rel_cols[i] = (offset, metric)

    if duns_col is None:
        return []

    # Determine max absolute year for Year1-5 anchor
    abs_years = set(yr for yr, _ in abs_cols.values())
    max_year = max(abs_years) if abs_years else 2023

    # Metric name -> DB column mapping for absolute year columns
    abs_metric_map = {
        "Sales Volume": "sales_volume",
        "Employee All Sites": "employees_all_sites",
        "Employee This Site": "employees_site",
    }

    results = []
    for row_data in data_rows:
        duns_raw = row_data.get(duns_col)
        if not duns_raw:
            continue
        duns = str(duns_raw).replace("-", "").strip()
        if not duns:
            continue

        # Collect all (year, metric, value) triples
        year_metrics = {}  # {year: {db_col: value}}

        # Absolute year columns
        for col_idx, (year, metric) in abs_cols.items():
            db_col = abs_metric_map.get(metric)
            if not db_col:
                continue
            val = row_data.get(col_idx)
            if val is None:
                continue
            if db_col in ("employees_all_sites", "employees_site"):
                parsed = safe_int(val)
            else:
                parsed = safe_float(val)
            if parsed is not None:
                year_metrics.setdefault(year, {})[db_col] = parsed

        # Relative year columns (Year1 = max_year, Year2 = max_year-1, etc.)
        for col_idx, (offset, metric) in rel_cols.items():
            db_col = YEAR_N_METRICS.get(metric)
            if not db_col:
                continue
            actual_year = max_year - (offset - 1)
            val = row_data.get(col_idx)
            if val is None:
                continue
            parsed = safe_float(val)
            if parsed is not None:
                year_metrics.setdefault(actual_year, {})[db_col] = parsed

        # Convert to result tuples
        for year, metrics in year_metrics.items():
            results.append((duns, year, metrics))

    return results


UPSERT_FINANCIAL_SQL = """
    INSERT INTO mergent_financials (
        duns, year, sales_volume, employees_all_sites, employees_site,
        total_revenue, net_income, total_assets, total_liabilities,
        ebitda, operating_income, long_term_debt, stockholders_equity,
        cash_end_of_year, source_file
    )
    VALUES %s
    ON CONFLICT (duns, year) DO UPDATE SET
        sales_volume = COALESCE(EXCLUDED.sales_volume, mergent_financials.sales_volume),
        employees_all_sites = COALESCE(EXCLUDED.employees_all_sites, mergent_financials.employees_all_sites),
        employees_site = COALESCE(EXCLUDED.employees_site, mergent_financials.employees_site),
        total_revenue = COALESCE(EXCLUDED.total_revenue, mergent_financials.total_revenue),
        net_income = COALESCE(EXCLUDED.net_income, mergent_financials.net_income),
        total_assets = COALESCE(EXCLUDED.total_assets, mergent_financials.total_assets),
        total_liabilities = COALESCE(EXCLUDED.total_liabilities, mergent_financials.total_liabilities),
        ebitda = COALESCE(EXCLUDED.ebitda, mergent_financials.ebitda),
        operating_income = COALESCE(EXCLUDED.operating_income, mergent_financials.operating_income),
        long_term_debt = COALESCE(EXCLUDED.long_term_debt, mergent_financials.long_term_debt),
        stockholders_equity = COALESCE(EXCLUDED.stockholders_equity, mergent_financials.stockholders_equity),
        cash_end_of_year = COALESCE(EXCLUDED.cash_end_of_year, mergent_financials.cash_end_of_year),
        source_file = EXCLUDED.source_file,
        loaded_at = NOW()
"""


def upsert_financials(cur, fin_records, source_file):
    """UPSERT Sheet 2 financial records."""
    if not fin_records:
        return 0
    all_cols = [
        "sales_volume", "employees_all_sites", "employees_site",
        "total_revenue", "net_income", "total_assets", "total_liabilities",
        "ebitda", "operating_income", "long_term_debt", "stockholders_equity",
        "cash_end_of_year",
    ]
    tuples = []
    for duns, year, metrics in fin_records:
        row = (
            duns, year,
            *[metrics.get(c) for c in all_cols],
            source_file,
        )
        tuples.append(row)
    execute_values(cur, UPSERT_FINANCIAL_SQL, tuples, page_size=500)
    return len(tuples)


# ============================================================
# SHEET 3: EXECUTIVES (XML parsing)
# ============================================================

def parse_sheet3_executives(filepath):
    """Parse Sheet 3 (Executive). Returns list of tuples."""
    headers, data_rows = _parse_xml_sheet(filepath, 3)
    if not headers or not data_rows:
        return []

    # Build column index map
    col_map = {}
    for i, h in enumerate(headers):
        if h:
            col_map[h.strip()] = i

    duns_col = col_map.get("D-U-N-S@ Number")
    if duns_col is None:
        return []

    records = []
    for row_data in data_rows:
        duns_raw = row_data.get(duns_col)
        if not duns_raw:
            continue
        duns = str(duns_raw).replace("-", "").strip()
        if not duns:
            continue

        first_name = row_data.get(col_map.get("First Name", -1))
        last_name = row_data.get(col_map.get("Last Name", -1))
        if not first_name or not last_name:
            continue

        first_name = str(first_name).strip()
        last_name = str(last_name).strip()
        if not first_name or not last_name:
            continue

        records.append((
            duns,
            str(row_data.get(col_map.get("Company Name", -1), "")).strip() or None,
            first_name,
            last_name,
            str(row_data.get(col_map.get("Title", -1), "")).strip() or None,
            str(row_data.get(col_map.get("Gender", -1), "")).strip()[:10] or None,
            str(row_data.get(col_map.get("Phone", -1), "")).strip()[:30] or None,
        ))

    return records


UPSERT_EXECUTIVE_SQL = """
    INSERT INTO mergent_executives (
        duns, company_name, first_name, last_name, title, gender, phone, source_file
    )
    VALUES %s
    ON CONFLICT (duns, first_name, last_name) DO UPDATE SET
        title = COALESCE(EXCLUDED.title, mergent_executives.title),
        gender = COALESCE(EXCLUDED.gender, mergent_executives.gender),
        phone = COALESCE(EXCLUDED.phone, mergent_executives.phone),
        company_name = COALESCE(EXCLUDED.company_name, mergent_executives.company_name),
        source_file = EXCLUDED.source_file,
        loaded_at = NOW()
"""


def upsert_executives(cur, records, source_file):
    """UPSERT Sheet 3 executive records. Dedup by (duns, first_name, last_name) first."""
    if not records:
        return 0
    # Dedup within batch — same person can appear with multiple titles in one file.
    # Keep last occurrence (titles may be semicolon-joined variants).
    seen = {}
    for r in records:
        key = (r[0], r[2], r[3])  # duns, first_name, last_name
        seen[key] = r
    deduped = list(seen.values())
    full_records = [r + (source_file,) for r in deduped]
    execute_values(cur, UPSERT_EXECUTIVE_SQL, full_records, page_size=500)
    return len(full_records)


# ============================================================
# ORCHESTRATION
# ============================================================

def discover_files(base_path):
    """Find all csv files across subfolders, sorted by folder then filename."""
    files = []
    for folder in sorted(os.listdir(base_path)):
        folder_path = os.path.join(base_path, folder)
        if not os.path.isdir(folder_path):
            continue
        for f in sorted(glob.glob(os.path.join(folder_path, "*.csv"))):
            files.append((folder, f))
    return files


def is_file_loaded(cur, file_path):
    cur.execute("SELECT 1 FROM mergent_load_progress WHERE file_path = %s", (file_path,))
    return cur.fetchone() is not None


def record_progress(cur, file_path, folder, stats, duration):
    cur.execute("""
        INSERT INTO mergent_load_progress (file_path, folder, sheet1_rows, sheet2_rows, sheet3_rows, duration_seconds)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_path) DO UPDATE SET
            sheet1_rows = EXCLUDED.sheet1_rows,
            sheet2_rows = EXCLUDED.sheet2_rows,
            sheet3_rows = EXCLUDED.sheet3_rows,
            duration_seconds = EXCLUDED.duration_seconds,
            loaded_at = NOW()
    """, (file_path, folder, stats.get("s1", 0), stats.get("s2", 0), stats.get("s3", 0), duration))


def process_file(conn, filepath, folder, sheets=None, dry_run=False):
    """Process a single file. Returns stats dict."""
    cur = conn.cursor()
    stats = {"s1": 0, "s2": 0, "s3": 0, "s1_skip": 0}
    source_file = os.path.basename(filepath)

    # Sheet 1
    if sheets is None or 1 in sheets:
        records, skipped = parse_sheet1_pandas(filepath)
        stats["s1_skip"] = skipped
        if not dry_run and records:
            stats["s1"] = upsert_employers(cur, records, source_file, folder)
        else:
            stats["s1"] = len(records)

    # Sheet 2
    if sheets is None or 2 in sheets:
        fin_records = parse_sheet2_financials(filepath)
        if not dry_run and fin_records:
            stats["s2"] = upsert_financials(cur, fin_records, source_file)
        else:
            stats["s2"] = len(fin_records)

    # Sheet 3
    if sheets is None or 3 in sheets:
        exec_records = parse_sheet3_executives(filepath)
        if not dry_run and exec_records:
            stats["s3"] = upsert_executives(cur, exec_records, source_file)
        else:
            stats["s3"] = len(exec_records)

    cur.close()
    return stats


def show_status(conn):
    """Show loading progress."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mergent_load_progress")
    loaded = cur.fetchone()[0]
    cur.execute("SELECT SUM(sheet1_rows), SUM(sheet2_rows), SUM(sheet3_rows), SUM(duration_seconds) FROM mergent_load_progress")
    s1, s2, s3, dur = cur.fetchone()
    cur.execute("SELECT folder, COUNT(*), SUM(sheet1_rows), SUM(sheet2_rows), SUM(sheet3_rows) FROM mergent_load_progress GROUP BY folder ORDER BY folder")
    folders = cur.fetchall()

    print("=" * 70)
    print("MERGENT LOAD PROGRESS")
    print("=" * 70)
    print(f"Files loaded: {loaded}")
    print(f"Sheet 1 (employers):  {s1 or 0:>10,} rows")
    print(f"Sheet 2 (financials): {s2 or 0:>10,} rows")
    print(f"Sheet 3 (executives): {s3 or 0:>10,} rows")
    print(f"Total time:           {dur or 0:>10.0f} seconds")
    print()
    print(f"{'Folder':<30} {'Files':>6} {'S1':>8} {'S2':>8} {'S3':>8}")
    print("-" * 70)
    for folder, cnt, fs1, fs2, fs3 in folders:
        print(f"{folder:<30} {cnt:>6} {fs1 or 0:>8,} {fs2 or 0:>8,} {fs3 or 0:>8,}")

    # Current table totals
    cur.execute("SELECT COUNT(*) FROM mergent_employers")
    emp = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mergent_financials")
    fin = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mergent_executives")
    exe = cur.fetchone()[0]
    print()
    print("Current DB totals:")
    print(f"  mergent_employers:  {emp:>10,}")
    print(f"  mergent_financials: {fin:>10,}")
    print(f"  mergent_executives: {exe:>10,}")
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Universal Mergent Intellect Loader")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--status", action="store_true", help="Show progress and exit")
    parser.add_argument("--limit", type=int, help="Process only first N files")
    parser.add_argument("--sheet", type=int, choices=[1, 2, 3], help="Process only this sheet")
    parser.add_argument("--force", action="store_true", help="Reload already-loaded files")
    parser.add_argument("--base-path", default=BASE_PATH, help="Base directory with Mergent files")
    args = parser.parse_args()

    conn = get_connection()

    if args.status:
        show_status(conn)
        conn.close()
        return

    sheets = {args.sheet} if args.sheet else None
    files = discover_files(args.base_path)

    if not files:
        print(f"ERROR: No files found in {args.base_path}")
        conn.close()
        return

    print("=" * 70)
    print(f"MERGENT UNIVERSAL LOADER {'(DRY RUN)' if args.dry_run else ''}")
    print("=" * 70)
    print(f"Base path: {args.base_path}")
    print(f"Files found: {len(files)}")
    print(f"Sheets: {sorted(sheets) if sheets else 'all'}")
    if args.limit:
        print(f"Limit: {args.limit} files")
    print()

    cur = conn.cursor()
    total_s1 = total_s2 = total_s3 = 0
    processed = skipped_loaded = errors = 0
    start_all = time.time()

    for i, (folder, filepath) in enumerate(files):
        if args.limit and processed >= args.limit:
            break

        # Check if already loaded
        if not args.force and is_file_loaded(cur, filepath):
            skipped_loaded += 1
            continue

        fname = os.path.basename(filepath)
        file_start = time.time()

        try:
            stats = process_file(conn, filepath, folder, sheets=sheets, dry_run=args.dry_run)
            duration = time.time() - file_start

            if not args.dry_run:
                record_progress(cur, filepath, folder, stats, duration)
                conn.commit()

            total_s1 += stats["s1"]
            total_s2 += stats["s2"]
            total_s3 += stats["s3"]
            processed += 1

            print(
                f"[{processed:>3}] {folder}/{fname}: "
                f"S1={stats['s1']:>5} S2={stats['s2']:>6} S3={stats['s3']:>5} "
                f"({duration:.1f}s)"
            )

        except Exception:
            conn.rollback()
            errors += 1
            print(f"[ERR] {folder}/{fname}: {traceback.format_exc()}")
            # Record the error
            if not args.dry_run:
                try:
                    record_progress(cur, filepath, folder, {"s1": 0, "s2": 0, "s3": 0}, 0)
                    conn.commit()
                except Exception:
                    conn.rollback()

    elapsed = time.time() - start_all
    cur.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Processed:      {processed} files")
    print(f"Skipped (done): {skipped_loaded} files")
    print(f"Errors:         {errors} files")
    print(f"Sheet 1 rows:   {total_s1:,}")
    print(f"Sheet 2 rows:   {total_s2:,}")
    print(f"Sheet 3 rows:   {total_s3:,}")
    print(f"Total time:     {elapsed:.0f}s ({elapsed/60:.1f}m)")

    if not args.dry_run:
        show_status(conn)

    conn.close()

    if not args.dry_run:
        print()
        print("Next steps:")
        print("  1. PYTHONPATH=. py scripts/etl/build_crosswalk.py")
        print("  2. py scripts/etl/seed_master_from_sources.py --source mergent")
        print("  3. py scripts/scoring/refresh_all.py --skip-gower")


if __name__ == "__main__":
    main()
