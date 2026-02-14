"""
Industry exposure/decline analysis module.

Maps each major international union to its primary industries and correlates
industry employment trends with union membership changes.

Replicates and extends the telecom-decline-impacts-CWA analysis from
"The CWA Fortress" (Wartel, 2025) across all top internationals.

Data source: BLS Current Population Survey (CPS) union membership data
from the lu_data_1.AllData file (1983-2024), which provides:
  - Total employed wage/salary workers by industry
  - Members of unions by industry
  - Both at national level, annual frequency

Usage:
    from scripts.industry import (load_bls_industry_data,
                                   get_union_industry_mapping,
                                   compute_industry_trends,
                                   compute_union_industry_exposure)
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# BLS data paths
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_BLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "bls"


# ──────────────────────────────────────────────────────────────────────────────
# BLS industry code mapping
# ──────────────────────────────────────────────────────────────────────────────

# Map from BLS lu.indy codes to readable names
BLS_INDUSTRY_CODES = {
    '0000': 'All Industries',
    '0168': 'Agriculture',
    '0369': 'Mining',
    '0569': 'Utilities',
    '0770': 'Construction',
    '2467': 'Manufacturing',
    '2468': 'Durable Goods Manufacturing',
    '1068': 'Nondurable Goods Manufacturing',
    '4067': 'Wholesale and Retail Trade',
    '4068': 'Wholesale Trade',
    '4669': 'Retail Trade',
    '6068': 'Transportation and Utilities',
    '6069': 'Transportation and Warehousing',
    '6468': 'Information',
    '6469': 'Publishing',
    '6569': 'Motion Pictures',
    '6670': 'Broadcasting',
    '6679': 'Telecommunications',
    '6769': 'Other Information Services',
    '6867': 'Financial Activities',
    '6868': 'Finance and Insurance',
    '7069': 'Real Estate',
    '7268': 'Professional and Business Services',
    '7269': 'Professional and Technical Services',
    '7569': 'Admin and Waste Services',
    '7858': 'Education and Health Services',
    '7859': 'Educational Services',
    '7968': 'Health Care and Social Assistance',
    '8558': 'Leisure and Hospitality',
    '8559': 'Arts and Entertainment',
    '8658': 'Accommodation and Food Services',
    '8767': 'Other Services',
}

# Series IDs for national, private-sector employment and union membership
# Format: (total_employed_series, union_members_series)
# These are: class=17 (private wage/salary), fips=00 (national), no demographics
INDUSTRY_SERIES = {
    '0000': ('LUU0204466700', 'LUU0203182000'),   # All Industries (private)
    '0168': ('LUU0204805500', 'LUU0204794500'),   # Agriculture
    '0369': ('LUU0204805700', 'LUU0204794700'),   # Mining
    '0569': ('LUU0204806700', 'LUU0204795700'),   # Utilities
    '0770': ('LUU0204805800', 'LUU0204794800'),   # Construction
    '2467': ('LUU0204805900', 'LUU0204794900'),   # Manufacturing
    '2468': ('LUU0204806000', 'LUU0204795000'),   # Durable Goods Mfg
    '1068': ('LUU0204921200', 'LUU0204921300'),   # Nondurable Goods Mfg
    '4068': ('LUU0204806300', 'LUU0204795300'),   # Wholesale Trade
    '4669': ('LUU0204806400', 'LUU0204795400'),   # Retail Trade
    '6069': ('LUU0204806600', 'LUU0204795600'),   # Transportation & Warehousing
    '6468': ('LUU0204806800', 'LUU0204795800'),   # Information
    '6469': ('LUU0204806900', 'LUU0204795900'),   # Publishing
    '6569': ('LUU0204807000', 'LUU0204796000'),   # Motion Pictures
    '6670': ('LUU0204807100', 'LUU0204796100'),   # Broadcasting
    '6679': ('LUU0204807300', 'LUU0204796300'),   # Telecommunications
    '6867': ('LUU0204807600', 'LUU0204796600'),   # Financial Activities
    '6868': ('LUU0204807700', 'LUU0204796700'),   # Finance & Insurance
    '7069': ('LUU0204808000', 'LUU0204797000'),   # Real Estate
    '7268': ('LUU0204808100', 'LUU0204797100'),   # Professional & Business Services
    '7858': ('LUU0204808400', 'LUU0204797400'),   # Education & Health
    '7859': ('LUU0204808500', 'LUU0204797500'),   # Educational Services
    '7968': ('LUU0204808600', 'LUU0204797600'),   # Health Care & Social Assistance
    '8558': ('LUU0204808700', 'LUU0204797700'),   # Leisure & Hospitality
    '8559': ('LUU0204808800', 'LUU0204797800'),   # Arts & Entertainment
    '8658': ('LUU0204808900', 'LUU0204797900'),   # Accommodation & Food Services
    '8767': ('LUU0204809200', 'LUU0204798200'),   # Other Services
}

# Also include all-worker (public + private) series for government-heavy unions
ALL_WORKER_SERIES = {
    '0000': ('LUU0204466800', 'LUU0203161800'),   # All Industries (all workers)
}


# ──────────────────────────────────────────────────────────────────────────────
# Union-to-industry mapping
# ──────────────────────────────────────────────────────────────────────────────

# Maps union AFF_ABBR to primary and secondary BLS industry codes
# with estimated exposure weights (should sum to ~1.0 per union)
#
# These are informed by each union's jurisdiction, collective bargaining
# agreements, and historical membership composition.

UNION_INDUSTRY_MAP = {
    'CWA': {
        'primary': [
            ('6679', 0.45),   # Telecommunications (legacy AT&T, Verizon)
            ('6468', 0.15),   # Information (broader tech/media)
            ('6670', 0.10),   # Broadcasting (NBC, ABC)
        ],
        'secondary': [
            ('7858', 0.10),   # Education & Health (public sector workers)
            ('7268', 0.10),   # Professional services (newspaper guild, tech workers)
            ('2467', 0.05),   # Manufacturing (IUE-CWA)
            ('6469', 0.05),   # Publishing (newspaper guild)
        ],
    },
    'IBT': {
        'primary': [
            ('6069', 0.35),   # Transportation & Warehousing
            ('4669', 0.15),   # Retail Trade (grocery delivery, warehouses)
            ('2467', 0.10),   # Manufacturing
        ],
        'secondary': [
            ('0770', 0.10),   # Construction
            ('7968', 0.10),   # Health Care
            ('8658', 0.05),   # Accommodation & Food Services
            ('7569', 0.05),   # Admin/Waste Services
            ('4068', 0.05),   # Wholesale Trade
            ('0000', 0.05),   # Other/general (broad jurisdiction)
        ],
    },
    'SEIU': {
        'primary': [
            ('7968', 0.45),   # Health Care & Social Assistance
            ('7268', 0.15),   # Professional & Business Services (janitors/property svcs)
        ],
        'secondary': [
            ('7859', 0.15),   # Educational Services (some public sector)
            ('7858', 0.15),   # Education & Health (combined)
            ('8767', 0.10),   # Other Services
        ],
    },
    'UAW': {
        'primary': [
            ('2468', 0.50),   # Durable Goods Manufacturing (auto, aerospace)
            ('2467', 0.15),   # Manufacturing (total)
        ],
        'secondary': [
            ('7968', 0.10),   # Health Care (post-merger organizing)
            ('7859', 0.10),   # Educational Services (grad students)
            ('4669', 0.10),   # Retail (auto dealers, casinos)
            ('7268', 0.05),   # Professional services (tech workers)
        ],
    },
    'UFCW': {
        'primary': [
            ('4669', 0.40),   # Retail Trade (grocery, meatpacking retail)
            ('1068', 0.20),   # Nondurable Goods Manufacturing (food processing)
        ],
        'secondary': [
            ('7968', 0.15),   # Health Care
            ('8658', 0.15),   # Accommodation & Food Services
            ('4068', 0.05),   # Wholesale Trade
            ('2467', 0.05),   # Manufacturing
        ],
    },
    'USW': {
        'primary': [
            ('2467', 0.40),   # Manufacturing (steel, aluminum, paper)
            ('0369', 0.15),   # Mining (oil/gas, quarrying)
        ],
        'secondary': [
            ('7968', 0.15),   # Health Care
            ('0569', 0.10),   # Utilities
            ('7268', 0.10),   # Professional services
            ('0770', 0.05),   # Construction
            ('6867', 0.05),   # Financial Activities
        ],
    },
    'IBEW': {
        'primary': [
            ('0770', 0.35),   # Construction (electrical)
            ('0569', 0.25),   # Utilities (power companies)
        ],
        'secondary': [
            ('6679', 0.15),   # Telecommunications
            ('6670', 0.10),   # Broadcasting
            ('2467', 0.10),   # Manufacturing (electrical equipment)
            ('6468', 0.05),   # Information
        ],
    },
    'AFSCME': {
        # AFSCME is predominantly public sector — BLS private series less relevant
        # We use the all-worker Information series as proxy
        'primary': [
            ('7858', 0.40),   # Education & Health (public hospitals, schools)
            ('7968', 0.25),   # Health Care & Social Assistance
        ],
        'secondary': [
            ('7859', 0.15),   # Educational Services
            ('8767', 0.10),   # Other Services
            ('6069', 0.05),   # Transportation (public transit)
            ('7268', 0.05),   # Professional services
        ],
        'note': 'Predominantly public sector; private-sector series are imperfect proxies',
    },
    'NEA': {
        'primary': [
            ('7859', 0.80),   # Educational Services
        ],
        'secondary': [
            ('7858', 0.20),   # Education & Health (combined)
        ],
        'note': 'Almost entirely public K-12 education',
    },
    'AFT': {
        'primary': [
            ('7859', 0.60),   # Educational Services
            ('7968', 0.20),   # Health Care
        ],
        'secondary': [
            ('7858', 0.20),   # Education & Health
        ],
        'note': 'Public education + growing healthcare presence',
    },
    'LIUNA': {
        'primary': [
            ('0770', 0.60),   # Construction
        ],
        'secondary': [
            ('7968', 0.15),   # Health Care
            ('8767', 0.10),   # Other Services
            ('7569', 0.10),   # Admin/Waste Services
            ('2467', 0.05),   # Manufacturing
        ],
    },
    'IUPAT': {
        'primary': [
            ('0770', 0.80),   # Construction (painters, drywall finishers)
        ],
        'secondary': [
            ('2467', 0.10),   # Manufacturing
            ('8767', 0.10),   # Other Services
        ],
    },
    'UNITE HERE': {
        'primary': [
            ('8658', 0.55),   # Accommodation & Food Services (hotels, casinos)
            ('8559', 0.10),   # Arts & Entertainment
        ],
        'secondary': [
            ('8558', 0.15),   # Leisure & Hospitality (broader)
            ('4669', 0.10),   # Retail Trade (laundry, food service)
            ('1068', 0.10),   # Nondurable Manufacturing (textile legacy)
        ],
    },
    'SMART': {
        'primary': [
            ('0770', 0.40),   # Construction (sheet metal)
            ('6069', 0.25),   # Transportation (railroad)
        ],
        'secondary': [
            ('2467', 0.20),   # Manufacturing
            ('0569', 0.10),   # Utilities
            ('7268', 0.05),   # Professional services
        ],
    },
    'IAM': {
        'primary': [
            ('2468', 0.40),   # Durable Goods Manufacturing (aerospace, defense)
            ('6069', 0.20),   # Transportation (airlines)
        ],
        'secondary': [
            ('2467', 0.15),   # Manufacturing (total)
            ('0770', 0.10),   # Construction
            ('7968', 0.10),   # Health Care
            ('7268', 0.05),   # Professional services
        ],
    },
    'BCTGM': {
        'primary': [
            ('1068', 0.70),   # Nondurable Goods Manufacturing (bakery, confectionery, tobacco, grain)
        ],
        'secondary': [
            ('2467', 0.20),   # Manufacturing (total)
            ('4669', 0.10),   # Retail Trade
        ],
    },
    'TWU': {
        'primary': [
            ('6069', 0.70),   # Transportation & Warehousing (transit, airlines)
        ],
        'secondary': [
            ('0569', 0.15),   # Utilities
            ('8767', 0.15),   # Other Services
        ],
    },
    'OPCMIA': {
        'primary': [
            ('0770', 0.85),   # Construction (cement masons, plasterers)
        ],
        'secondary': [
            ('2467', 0.15),   # Manufacturing
        ],
    },
    'GMP': {
        'primary': [
            ('2467', 0.70),   # Manufacturing (glass, molders, pottery)
        ],
        'secondary': [
            ('0770', 0.20),   # Construction
            ('4068', 0.10),   # Wholesale Trade
        ],
    },
    'OPEIU': {
        'primary': [
            ('6867', 0.30),   # Financial Activities
            ('7968', 0.25),   # Health Care
        ],
        'secondary': [
            ('7268', 0.20),   # Professional & Business Services
            ('6868', 0.15),   # Finance & Insurance
            ('8767', 0.10),   # Other Services
        ],
    },
    'IATSE': {
        'primary': [
            ('6569', 0.50),   # Motion Pictures
            ('8559', 0.25),   # Arts & Entertainment
        ],
        'secondary': [
            ('6670', 0.15),   # Broadcasting
            ('6468', 0.10),   # Information
        ],
    },
    'SAG-AFTRA': {
        'primary': [
            ('6569', 0.35),   # Motion Pictures
            ('6670', 0.30),   # Broadcasting
        ],
        'secondary': [
            ('8559', 0.20),   # Arts & Entertainment
            ('6468', 0.15),   # Information
        ],
    },
    'RWDSU': {
        'primary': [
            ('4669', 0.60),   # Retail Trade
        ],
        'secondary': [
            ('4068', 0.15),   # Wholesale Trade
            ('1068', 0.15),   # Nondurable Manufacturing
            ('8658', 0.10),   # Accommodation & Food Services
        ],
    },
    'AFGE': {
        # Federal government workers — private sector series don't apply well
        'primary': [
            ('7858', 0.30),   # Education & Health (VA hospitals)
            ('7268', 0.25),   # Professional services (federal agencies)
        ],
        'secondary': [
            ('6069', 0.15),   # Transportation (TSA, FAA)
            ('8767', 0.15),   # Other Services
            ('0369', 0.10),   # Mining (BLM, etc.)
            ('7968', 0.05),   # Health Care
        ],
        'note': 'Federal government employees; private-sector series are imperfect proxies',
    },
    'NALC': {
        'primary': [
            ('6069', 0.80),   # Transportation & Warehousing (postal)
        ],
        'secondary': [
            ('8767', 0.20),   # Other Services
        ],
        'note': 'Postal workers; federal public sector',
    },
    'APWU': {
        'primary': [
            ('6069', 0.80),   # Transportation & Warehousing (postal)
        ],
        'secondary': [
            ('8767', 0.20),   # Other Services
        ],
        'note': 'Postal workers; federal public sector',
    },
    'NFFE': {
        'primary': [
            ('7268', 0.30),   # Professional services
            ('7858', 0.25),   # Education & Health
        ],
        'secondary': [
            ('8767', 0.20),   # Other Services
            ('6069', 0.15),   # Transportation
            ('0369', 0.10),   # Mining/natural resources
        ],
        'note': 'Federal employees (various agencies)',
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

def load_bls_industry_data(bls_dir=None, years=None) -> pd.DataFrame:
    """
    Load BLS CPS union membership data by industry from lu_data_1.AllData.

    Returns DataFrame with columns:
        year, indy_code, industry, total_employed, union_members, union_density_pct

    All employment figures are in thousands.
    """
    if bls_dir is None:
        bls_dir = DEFAULT_BLS_DIR
    if years is None:
        years = range(2000, 2025)

    data_path = os.path.join(bls_dir, 'lu_data_1.AllData')
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"BLS data file not found: {data_path}")

    # Read the full data file
    df = pd.read_csv(data_path, sep='\t', dtype=str)
    df.columns = df.columns.str.strip()
    for col in df.columns:
        df[col] = df[col].str.strip()

    df['year'] = df['year'].astype(int)
    df['value'] = pd.to_numeric(df['value'], errors='coerce')

    # Filter to requested years
    df = df[df['year'].isin(years)]

    # Build industry dataset from our series mapping
    rows = []
    for indy_code, (total_sid, union_sid) in INDUSTRY_SERIES.items():
        total = df[df['series_id'] == total_sid][['year', 'value']].rename(
            columns={'value': 'total_employed'})
        union = df[df['series_id'] == union_sid][['year', 'value']].rename(
            columns={'value': 'union_members'})

        merged = total.merge(union, on='year', how='outer')
        merged['indy_code'] = indy_code
        merged['industry'] = BLS_INDUSTRY_CODES.get(indy_code, indy_code)
        rows.append(merged)

    result = pd.concat(rows, ignore_index=True)
    result['union_density_pct'] = (result['union_members'] / result['total_employed'] * 100).round(2)

    return result.sort_values(['indy_code', 'year'])


def load_bls_all_workers(bls_dir=None, years=None) -> pd.DataFrame:
    """
    Load BLS all-worker (public + private) aggregate series.
    Useful for public-sector-heavy unions like AFSCME, NEA, AFGE.
    """
    if bls_dir is None:
        bls_dir = DEFAULT_BLS_DIR
    if years is None:
        years = range(2000, 2025)

    data_path = os.path.join(bls_dir, 'lu_data_1.AllData')
    df = pd.read_csv(data_path, sep='\t', dtype=str)
    df.columns = df.columns.str.strip()
    for col in df.columns:
        df[col] = df[col].str.strip()
    df['year'] = df['year'].astype(int)
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df[df['year'].isin(years)]

    rows = []
    for indy_code, (total_sid, union_sid) in ALL_WORKER_SERIES.items():
        total = df[df['series_id'] == total_sid][['year', 'value']].rename(
            columns={'value': 'total_employed'})
        union = df[df['series_id'] == union_sid][['year', 'value']].rename(
            columns={'value': 'union_members'})
        merged = total.merge(union, on='year', how='outer')
        merged['indy_code'] = indy_code
        merged['industry'] = 'All Industries (All Workers)'
        rows.append(merged)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# Industry trend analysis
# ──────────────────────────────────────────────────────────────────────────────

def compute_industry_trends(bls_data: pd.DataFrame) -> pd.DataFrame:
    """
    Compute employment and union membership trends per industry.

    Returns DataFrame with:
        - Year-over-year changes
        - Cumulative change from base year (2000)
        - CAGR (compound annual growth rate)
        - Employment indexing (2000=100)
    """
    result_frames = []

    for indy_code, group in bls_data.groupby('indy_code'):
        g = group.sort_values('year').copy()

        if len(g) < 2:
            continue

        base = g.iloc[0]

        # Index to base year = 100
        g['employment_index'] = (g['total_employed'] / base['total_employed'] * 100).round(1)
        g['union_index'] = (g['union_members'] / base['union_members'] * 100).round(1)

        # Year-over-year changes
        g['employment_change'] = g['total_employed'].diff()
        g['employment_change_pct'] = g['total_employed'].pct_change() * 100
        g['union_change'] = g['union_members'].diff()
        g['union_change_pct'] = g['union_members'].pct_change() * 100
        g['density_change'] = g['union_density_pct'].diff()

        # Cumulative change from base
        g['cum_employment_change'] = g['total_employed'] - base['total_employed']
        g['cum_employment_change_pct'] = ((g['total_employed'] / base['total_employed']) - 1) * 100
        g['cum_union_change'] = g['union_members'] - base['union_members']
        g['cum_union_change_pct'] = ((g['union_members'] / base['union_members']) - 1) * 100

        result_frames.append(g)

    return pd.concat(result_frames, ignore_index=True) if result_frames else pd.DataFrame()


def compute_industry_summary(bls_data: pd.DataFrame,
                              start_year: int = 2000,
                              end_year: int = 2024) -> pd.DataFrame:
    """
    Compute summary statistics for each industry over a period.

    Returns one row per industry with:
        - Start/end employment and union membership
        - Total change and CAGR
        - Density change
        - Classification (growing/declining/stable)
    """
    rows = []
    for indy_code, group in bls_data.groupby('indy_code'):
        g = group.sort_values('year')
        start = g[g['year'] == start_year]
        end = g[g['year'] == end_year]

        if len(start) == 0 or len(end) == 0:
            continue

        s = start.iloc[0]
        e = end.iloc[0]
        n_years = end_year - start_year

        emp_change = e['total_employed'] - s['total_employed']
        emp_change_pct = (emp_change / s['total_employed'] * 100) if s['total_employed'] else 0
        emp_cagr = ((e['total_employed'] / s['total_employed']) ** (1/n_years) - 1) * 100 if s['total_employed'] > 0 else 0

        union_change = e['union_members'] - s['union_members']
        union_change_pct = (union_change / s['union_members'] * 100) if s['union_members'] else 0
        union_cagr = ((e['union_members'] / s['union_members']) ** (1/n_years) - 1) * 100 if s['union_members'] > 0 else 0

        density_change = e['union_density_pct'] - s['union_density_pct']

        # Classify industry trajectory
        if emp_change_pct < -15:
            emp_class = 'DECLINING'
        elif emp_change_pct > 15:
            emp_class = 'GROWING'
        else:
            emp_class = 'STABLE'

        if union_change_pct < -15:
            union_class = 'DECLINING'
        elif union_change_pct > 15:
            union_class = 'GROWING'
        else:
            union_class = 'STABLE'

        rows.append({
            'indy_code': indy_code,
            'industry': BLS_INDUSTRY_CODES.get(indy_code, indy_code),
            'emp_start': s['total_employed'],
            'emp_end': e['total_employed'],
            'emp_change': emp_change,
            'emp_change_pct': round(emp_change_pct, 1),
            'emp_cagr': round(emp_cagr, 2),
            'union_start': s['union_members'],
            'union_end': e['union_members'],
            'union_change': union_change,
            'union_change_pct': round(union_change_pct, 1),
            'union_cagr': round(union_cagr, 2),
            'density_start': s['union_density_pct'],
            'density_end': e['union_density_pct'],
            'density_change': round(density_change, 2),
            'emp_trajectory': emp_class,
            'union_trajectory': union_class,
        })

    return pd.DataFrame(rows).sort_values('union_change_pct')


# ──────────────────────────────────────────────────────────────────────────────
# Union-industry exposure analysis
# ──────────────────────────────────────────────────────────────────────────────

def get_union_industry_mapping() -> dict:
    """Return the union-to-industry mapping dictionary."""
    return UNION_INDUSTRY_MAP


def compute_union_industry_exposure(union_aff: str,
                                     bls_data: pd.DataFrame,
                                     start_year: int = 2000,
                                     end_year: int = 2024) -> dict:
    """
    Compute weighted industry exposure for a single union.

    Returns:
        dict with:
            - weighted_emp_change_pct: employment change weighted by union's exposure
            - weighted_union_change_pct: union membership change weighted by exposure
            - weighted_density_change: density change weighted by exposure
            - industry_detail: list of per-industry metrics
            - headwind_score: negative = industry headwinds, positive = tailwinds
    """
    mapping = UNION_INDUSTRY_MAP.get(union_aff)
    if not mapping:
        return {}

    # Combine primary and secondary industries
    all_industries = mapping.get('primary', []) + mapping.get('secondary', [])

    summary = compute_industry_summary(bls_data, start_year, end_year)
    summary_map = {r['indy_code']: r for _, r in summary.iterrows()}

    weighted_emp_change = 0
    weighted_union_change = 0
    weighted_density_change = 0
    detail = []

    for indy_code, weight in all_industries:
        ind_data = summary_map.get(indy_code)
        if ind_data is None:
            continue

        weighted_emp_change += ind_data['emp_change_pct'] * weight
        weighted_union_change += ind_data['union_change_pct'] * weight
        weighted_density_change += ind_data['density_change'] * weight

        detail.append({
            'indy_code': indy_code,
            'industry': ind_data['industry'],
            'weight': weight,
            'emp_change_pct': ind_data['emp_change_pct'],
            'union_change_pct': ind_data['union_change_pct'],
            'density_start': ind_data['density_start'],
            'density_end': ind_data['density_end'],
            'density_change': ind_data['density_change'],
            'emp_trajectory': ind_data['emp_trajectory'],
            'contribution_emp': round(ind_data['emp_change_pct'] * weight, 1),
            'contribution_union': round(ind_data['union_change_pct'] * weight, 1),
        })

    # Headwind score: negative means the industry environment is working against the union
    # Combines both employment decline and density decline
    headwind_score = round(weighted_emp_change * 0.5 + weighted_density_change * 5, 1)

    return {
        'union': union_aff,
        'weighted_emp_change_pct': round(weighted_emp_change, 1),
        'weighted_union_change_pct': round(weighted_union_change, 1),
        'weighted_density_change': round(weighted_density_change, 2),
        'headwind_score': headwind_score,
        'industry_detail': sorted(detail, key=lambda x: x['weight'], reverse=True),
        'note': mapping.get('note', ''),
    }


def compute_all_exposures(bls_data: pd.DataFrame,
                           unions: list = None,
                           start_year: int = 2000,
                           end_year: int = 2024) -> pd.DataFrame:
    """
    Compute industry exposure for all mapped unions.

    Args:
        bls_data: loaded BLS industry data
        unions: list of AFF_ABBR strings (default: all mapped unions)
        start_year: start of analysis period
        end_year: end of analysis period

    Returns:
        DataFrame with one row per union, ranked by headwind score
    """
    if unions is None:
        unions = list(UNION_INDUSTRY_MAP.keys())

    rows = []
    for aff in unions:
        exposure = compute_union_industry_exposure(aff, bls_data, start_year, end_year)
        if exposure:
            rows.append({
                'union': exposure['union'],
                'weighted_emp_change_pct': exposure['weighted_emp_change_pct'],
                'weighted_union_change_pct': exposure['weighted_union_change_pct'],
                'weighted_density_change': exposure['weighted_density_change'],
                'headwind_score': exposure['headwind_score'],
                'note': exposure.get('note', ''),
            })

    df = pd.DataFrame(rows)
    return df.sort_values('headwind_score') if not df.empty else df


# ──────────────────────────────────────────────────────────────────────────────
# Decomposition: structural vs. organizing effects
# ──────────────────────────────────────────────────────────────────────────────

def decompose_membership_change(union_profile: pd.DataFrame,
                                 exposure: dict,
                                 start_year: int = 2000,
                                 end_year: int = 2024) -> dict:
    """
    Decompose a union's membership change into:
    1. Structural effect (industry employment changes)
    2. Density effect (changes in union penetration within industries)
    3. Organizing effect (residual: actual change minus structural + density)

    This is the core analytical insight from the CWA paper:
    if an industry is shrinking, union membership decline may be structural
    rather than an organizing failure.

    Args:
        union_profile: profile DataFrame from compute_union_profile()
        exposure: result from compute_union_industry_exposure()

    Returns:
        dict with decomposition results
    """
    start = union_profile[union_profile['year'] == start_year]
    end = union_profile[union_profile['year'] == end_year]

    if len(start) == 0 or len(end) == 0:
        return {}

    s = start.iloc[0]
    e = end.iloc[0]

    actual_change = e['MEMBERS'] - s['MEMBERS']
    actual_change_pct = (actual_change / s['MEMBERS'] * 100) if s['MEMBERS'] else 0

    # Structural effect: if the union's industries had maintained their
    # base-year membership but employment changed as observed
    structural_effect_pct = exposure.get('weighted_emp_change_pct', 0)
    structural_effect = s['MEMBERS'] * (structural_effect_pct / 100)

    # Density effect: change in union density within industries
    # weighted_density_change is already in percentage points (e.g., -8.48 pp)
    # We interpret this as: what fraction of the union's membership base is lost
    # due to declining density. Since density is measured as % of industry employment,
    # we scale by the ratio of density change to base density.
    # Simplified: use the weighted union membership change minus the structural part.
    weighted_union_pct = exposure.get('weighted_union_change_pct', 0)
    density_effect_pct = weighted_union_pct - structural_effect_pct
    density_effect = s['MEMBERS'] * (density_effect_pct / 100)

    # Organizing effect: residual
    organizing_effect = actual_change - structural_effect - density_effect
    organizing_effect_pct = (organizing_effect / s['MEMBERS'] * 100) if s['MEMBERS'] else 0

    return {
        'union': exposure.get('union', ''),
        'period': f'{start_year}-{end_year}',
        'members_start': s['MEMBERS'],
        'members_end': e['MEMBERS'],
        'actual_change': actual_change,
        'actual_change_pct': round(actual_change_pct, 1),
        'structural_effect': round(structural_effect),
        'structural_effect_pct': round(structural_effect_pct, 1),
        'density_effect': round(density_effect),
        'density_effect_pct': round(density_effect_pct, 1),
        'organizing_effect': round(organizing_effect),
        'organizing_effect_pct': round(organizing_effect_pct, 1),
        'headwind_score': exposure.get('headwind_score', 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Loading BLS industry data (2000-2024)...")
    bls = load_bls_industry_data()
    print(f"  Loaded {len(bls):,} industry-year observations")

    print("\n" + "="*90)
    print("INDUSTRY EMPLOYMENT & UNION MEMBERSHIP TRENDS (2000-2024)")
    print("="*90)

    summary = compute_industry_summary(bls)
    print(f"\n{'Industry':40s} {'Emp Chg%':>8s} {'Union Chg%':>10s} {'Dens 2000':>9s} {'Dens 2024':>9s} {'Dens Chg':>8s} {'EmpTraj':>10s}")
    print("-" * 95)
    for _, r in summary.iterrows():
        if r['indy_code'] == '0000':
            continue  # Skip aggregate
        print(f"{r['industry']:40s} {r['emp_change_pct']:>+7.1f}% {r['union_change_pct']:>+9.1f}% {r['density_start']:>8.1f}% {r['density_end']:>8.1f}% {r['density_change']:>+7.2f} {r['emp_trajectory']:>10s}")

    print("\n" + "="*90)
    print("UNION INDUSTRY EXPOSURE ANALYSIS")
    print("="*90)

    exposures = compute_all_exposures(bls)
    print(f"\n{'Union':12s} {'Wtd Emp Chg%':>12s} {'Wtd Union Chg%':>14s} {'Wtd Dens Chg':>12s} {'Headwind':>10s} {'Note':30s}")
    print("-" * 95)
    for _, r in exposures.iterrows():
        note = r.get('note', '')[:30] if pd.notna(r.get('note')) else ''
        print(f"{r['union']:12s} {r['weighted_emp_change_pct']:>+11.1f}% {r['weighted_union_change_pct']:>+13.1f}% {r['weighted_density_change']:>+11.2f} {r['headwind_score']:>+9.1f} {note}")

    print("\nDone.")
