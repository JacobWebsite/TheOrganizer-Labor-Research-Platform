"""
Financial metrics module for union analysis.

Replicates and extends the methodology from "The CWA Fortress" (Wartel, 2025)
across all major international unions using LM-2 bulk data.

Core metrics:
  - Membership trends and change rates
  - Net asset growth (nominal and inflation-adjusted)
  - Revenue composition (dues/tax vs. investment income)
  - Surplus analysis (receipts - disbursements)
  - Asset composition (cash, investments, fixed, receivables)
  - Spending category breakdown
  - Revenue per member
  - All metrics available inflation-adjusted (CPI-U)
"""

import pandas as pd
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# CPI-U annual averages for inflation adjustment (BLS)
# ──────────────────────────────────────────────────────────────────────────────

# Base year = 2024 (CPI-U = 314.069, annual average)
CPI_U = {
    2000: 172.2, 2001: 177.1, 2002: 179.9, 2003: 184.0, 2004: 188.9,
    2005: 195.3, 2006: 201.6, 2007: 207.3, 2008: 215.3, 2009: 214.5,
    2010: 218.1, 2011: 224.9, 2012: 229.6, 2013: 233.0, 2014: 236.7,
    2015: 237.0, 2016: 240.0, 2017: 245.1, 2018: 251.1, 2019: 255.7,
    2020: 258.8, 2021: 271.0, 2022: 292.7, 2023: 304.7, 2024: 314.1,
    2025: 320.0,  # estimated
}

BASE_YEAR = 2024


def _inflation_factor(year: int) -> float:
    """Multiplier to convert nominal dollars in `year` to BASE_YEAR dollars."""
    if year not in CPI_U:
        return 1.0
    return CPI_U[BASE_YEAR] / CPI_U[year]


def adjust_for_inflation(value, year: int):
    """Convert nominal value to real (2024) dollars."""
    return value * _inflation_factor(year)


# ──────────────────────────────────────────────────────────────────────────────
# Union financial profile
# ──────────────────────────────────────────────────────────────────────────────

def compute_union_profile(lm: pd.DataFrame, f_num: str) -> pd.DataFrame:
    """
    Compute a complete financial profile for a single union over time.

    Args:
        lm: full lm_data DataFrame (NHQ filings)
        f_num: the F_NUM identifying the union's national HQ

    Returns:
        DataFrame with one row per year, all key metrics computed
    """
    union = lm[lm['F_NUM'] == str(f_num)].copy()

    if union.empty:
        return pd.DataFrame()

    # Take non-amendment filings where possible
    union = union.sort_values(['year', 'AMENDMENT'])
    union = union.drop_duplicates(subset='year', keep='first')
    union = union.sort_values('year')

    # Core metrics
    union['net_assets'] = union['TTL_ASSETS'] - union['TTL_LIABILITIES']
    union['surplus'] = union['TTL_RECEIPTS'] - union['TTL_DISBURSEMENTS']

    # Year-over-year changes
    union['member_change'] = union['MEMBERS'].diff()
    union['member_change_pct'] = union['MEMBERS'].pct_change() * 100
    union['net_asset_change'] = union['net_assets'].diff()
    union['net_asset_change_pct'] = union['net_assets'].pct_change() * 100

    # Per-member metrics
    union['receipts_per_member'] = union['TTL_RECEIPTS'] / union['MEMBERS']
    union['disbursements_per_member'] = union['TTL_DISBURSEMENTS'] / union['MEMBERS']
    union['assets_per_member'] = union['TTL_ASSETS'] / union['MEMBERS']
    union['net_assets_per_member'] = union['net_assets'] / union['MEMBERS']

    # Surplus rate (surplus as % of receipts)
    union['surplus_rate'] = (union['surplus'] / union['TTL_RECEIPTS']) * 100

    # Spending rate (disbursements as % of assets — how fast are they spending down)
    union['spending_rate'] = (union['TTL_DISBURSEMENTS'] / union['TTL_ASSETS']) * 100

    # Inflation-adjusted columns
    for col in ['TTL_ASSETS', 'TTL_LIABILITIES', 'TTL_RECEIPTS', 'TTL_DISBURSEMENTS',
                'net_assets', 'surplus']:
        union[f'{col}_real'] = union.apply(
            lambda r: adjust_for_inflation(r[col], r['year']), axis=1
        )

    return union


# ──────────────────────────────────────────────────────────────────────────────
# Cross-union comparison metrics
# ──────────────────────────────────────────────────────────────────────────────

def compute_all_profiles(lm: pd.DataFrame, unions: list) -> dict:
    """
    Compute profiles for a list of unions.

    Args:
        lm: full lm_data DataFrame (NHQ filings)
        unions: list of (AFF_ABBR, F_NUM, UNION_NAME) tuples

    Returns:
        dict of {aff_abbr: profile_df}
    """
    profiles = {}
    for aff, fnum, name in unions:
        profile = compute_union_profile(lm, str(fnum))
        if not profile.empty:
            profiles[aff] = profile
    return profiles


def compute_period_summary(profile: pd.DataFrame,
                           start_year: int, end_year: int) -> dict:
    """
    Compute summary metrics for a union over a specific period.

    This replicates the kind of analysis in the CWA paper:
    - Net asset growth (nominal and real)
    - Membership change
    - Total surplus
    - Average surplus rate
    - Revenue trend
    """
    period = profile[(profile['year'] >= start_year) & (profile['year'] <= end_year)]

    if len(period) < 2:
        return {}

    first = period.iloc[0]
    last = period.iloc[-1]

    # Membership
    member_start = first['MEMBERS']
    member_end = last['MEMBERS']
    member_change = member_end - member_start
    member_change_pct = (member_change / member_start * 100) if member_start else None

    # Net assets (nominal)
    na_start = first['net_assets']
    na_end = last['net_assets']
    na_change = na_end - na_start
    na_change_pct = (na_change / na_start * 100) if na_start else None

    # Net assets (real / inflation-adjusted)
    na_start_real = first.get('net_assets_real', na_start)
    na_end_real = last.get('net_assets_real', na_end)
    na_change_real = na_end_real - na_start_real

    # Cumulative surplus
    total_surplus = period['surplus'].sum()
    avg_surplus_rate = period['surplus_rate'].mean()

    # Revenue
    rev_start = first['TTL_RECEIPTS']
    rev_end = last['TTL_RECEIPTS']
    rev_change_pct = ((rev_end - rev_start) / rev_start * 100) if rev_start else None

    return {
        'period': f"{start_year}-{end_year}",
        'years_covered': len(period),
        'member_start': member_start,
        'member_end': member_end,
        'member_change': member_change,
        'member_change_pct': member_change_pct,
        'net_assets_start': na_start,
        'net_assets_end': na_end,
        'net_assets_change': na_change,
        'net_assets_change_pct': na_change_pct,
        'net_assets_change_real': na_change_real,
        'total_surplus': total_surplus,
        'avg_surplus_rate': avg_surplus_rate,
        'revenue_start': rev_start,
        'revenue_end': rev_end,
        'revenue_change_pct': rev_change_pct,
        'avg_receipts_per_member': period['receipts_per_member'].mean(),
        'avg_spending_rate': period['spending_rate'].mean(),
    }


def compute_cross_union_comparison(profiles: dict,
                                    start_year: int = 2010,
                                    end_year: int = 2024) -> pd.DataFrame:
    """
    Build a comparison table across all unions for a given period.

    Returns DataFrame with one row per union, ranked by key metrics.
    """
    rows = []
    for aff, profile in profiles.items():
        summary = compute_period_summary(profile, start_year, end_year)
        if summary:
            summary['union'] = aff
            rows.append(summary)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index('union')
    return df.sort_values('member_change_pct', ascending=True)


# ──────────────────────────────────────────────────────────────────────────────
# Asset composition analysis
# ──────────────────────────────────────────────────────────────────────────────

def compute_asset_composition(assets_df: pd.DataFrame, rpt_ids: set) -> pd.DataFrame:
    """
    Compute asset composition percentages from assets_total table.

    Categories: cash, accounts_receivable, investments,
                fixed_assets, treasury_securities, other_assets, loans_receivable
    """
    filtered = assets_df[assets_df['RPT_ID'].isin(rpt_ids)].copy()

    if filtered.empty:
        return pd.DataFrame()

    # Use end-of-period values
    composition = pd.DataFrame()
    composition['RPT_ID'] = filtered['RPT_ID']
    composition['cash'] = filtered.get('CASH_END', 0)
    composition['accounts_receivable'] = filtered.get('ACCOUNTS_RECEIVABLE_END', 0)
    composition['investments'] = filtered.get('INVESTMENTS_END', 0)
    composition['fixed_assets'] = filtered.get('FIXED_ASSETS_END', 0)
    composition['treasury_securities'] = filtered.get('TREASURY_SECURITIES_END', 0)
    composition['other_assets'] = filtered.get('OTHER_ASSETS_END', 0)
    composition['loans_receivable'] = filtered.get('LOANS_RECEIVABLE_END', 0)

    # Total
    asset_cols = ['cash', 'accounts_receivable', 'investments', 'fixed_assets',
                  'treasury_securities', 'other_assets', 'loans_receivable']
    composition['total'] = composition[asset_cols].sum(axis=1)

    # Percentages
    for col in asset_cols:
        composition[f'{col}_pct'] = (composition[col] / composition['total'] * 100).round(2)

    # Liquidity ratio: (cash + treasury + marketable investments) / total
    composition['liquid_assets'] = (composition['cash'] + composition['treasury_securities']
                                     + composition['investments'])
    composition['liquidity_ratio'] = (composition['liquid_assets'] / composition['total'] * 100).round(2)

    return composition


# ──────────────────────────────────────────────────────────────────────────────
# Disbursement category analysis
# ──────────────────────────────────────────────────────────────────────────────

def compute_spending_breakdown(disb_df: pd.DataFrame, rpt_ids: set) -> pd.DataFrame:
    """
    Break down disbursements into functional categories.

    LM-2 categories:
      - REPRESENTATIONAL: collective bargaining, grievances, organizing
      - POLITICAL: political activities and lobbying
      - CONTRIBUTIONS: contributions, gifts, grants
      - GENERAL_OVERHEAD: rent, utilities, office
      - UNION_ADMINISTRATION: governance, conventions
      - STRIKE_BENEFITS: strike fund disbursements
      - PER_CAPITA_TAX: payments to parent/affiliate bodies
      - BENEFITS: member benefits (non-strike)
    """
    filtered = disb_df[disb_df['RPT_ID'].isin(rpt_ids)].copy()

    if filtered.empty:
        return pd.DataFrame()

    categories = ['REPRESENTATIONAL', 'POLITICAL', 'CONTRIBUTIONS',
                  'GENERAL_OVERHEAD', 'UNION_ADMINISTRATION',
                  'STRIKE_BENEFITS', 'PER_CAPITA_TAX', 'BENEFITS']

    result = filtered[['RPT_ID'] + [c for c in categories if c in filtered.columns]].copy()

    # Compute total of categorized spending
    avail_cats = [c for c in categories if c in result.columns]
    result['categorized_total'] = result[avail_cats].sum(axis=1)

    # Percentages
    for col in avail_cats:
        result[f'{col}_pct'] = (result[col] / result['categorized_total'] * 100).round(2)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Aggregate labor movement metrics (for Boehner-style comparison)
# ──────────────────────────────────────────────────────────────────────────────

def compute_movement_aggregates(lm: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aggregate metrics for the entire labor movement by year.

    This enables the Boehner-style comparison: how does a specific union
    compare to the movement overall?
    """
    nhq = lm[lm['DESIG_NAME'].str.strip().str.upper() == 'NHQ'].copy()

    # Exclude federations (AFL-CIO, SOC, TTD) from aggregates to avoid double-counting
    federations = {'106', '385', '387'}  # AFL-CIO, SOC, TTD
    nhq = nhq[~nhq['F_NUM'].isin(federations)]

    agg = nhq.groupby('year').agg(
        total_members=('MEMBERS', 'sum'),
        total_assets=('TTL_ASSETS', 'sum'),
        total_liabilities=('TTL_LIABILITIES', 'sum'),
        total_receipts=('TTL_RECEIPTS', 'sum'),
        total_disbursements=('TTL_DISBURSEMENTS', 'sum'),
        num_unions=('F_NUM', 'nunique'),
    ).reset_index()

    agg['total_net_assets'] = agg['total_assets'] - agg['total_liabilities']
    agg['total_surplus'] = agg['total_receipts'] - agg['total_disbursements']
    agg['avg_receipts_per_member'] = agg['total_receipts'] / agg['total_members']
    agg['surplus_rate'] = (agg['total_surplus'] / agg['total_receipts'] * 100)

    # Inflation adjust
    agg['total_net_assets_real'] = agg.apply(
        lambda r: adjust_for_inflation(r['total_net_assets'], r['year']), axis=1
    )

    return agg


def compute_union_vs_movement(profile: pd.DataFrame,
                               movement: pd.DataFrame) -> pd.DataFrame:
    """
    Compare a single union's metrics to the movement aggregate.

    Returns merged DataFrame with relative metrics.
    """
    merged = profile.merge(movement[['year', 'total_members', 'total_net_assets',
                                      'total_receipts', 'total_disbursements',
                                      'surplus_rate']],
                           on='year', how='left', suffixes=('', '_mvmt'))

    # Union's share of movement
    merged['member_share_pct'] = (merged['MEMBERS'] / merged['total_members'] * 100)
    merged['asset_share_pct'] = (merged['net_assets'] / merged['total_net_assets'] * 100)
    merged['receipt_share_pct'] = (merged['TTL_RECEIPTS'] / merged['total_receipts'] * 100)

    # Relative surplus rate
    merged['surplus_rate_vs_mvmt'] = merged['surplus_rate'] - merged['surplus_rate_mvmt']

    return merged
