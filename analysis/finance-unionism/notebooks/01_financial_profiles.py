"""
01_financial_profiles.py - Union Financial Profile Analysis

Runnable as a script or converted to Jupyter notebook.
Replicates and extends the CWA Fortress analysis across top 30 internationals.

Usage:
    python notebooks/01_financial_profiles.py
    # Or convert: jupytext --to notebook notebooks/01_financial_profiles.py
"""

# %% [markdown]
# # Union Financial Profiles: Replicating the CWA Fortress Analysis
#
# This analysis extends the methodology from "The CWA Fortress" (Wartel, 2025)
# across all major international unions using 26 years of LM-2 bulk data (2000-2025).
#
# **Key questions:**
# 1. Which unions are growing vs. shrinking in membership?
# 2. How have net assets changed (nominal and inflation-adjusted)?
# 3. Are unions running surpluses or deficits?
# 4. How does spending break down across categories?
# 5. What is the asset composition (liquidity analysis)?

# %%
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.etl import (load_lm_data, identify_nhq_filings, top_internationals,
                          load_receipts, load_disbursements, load_assets, load_membership)
from scripts.metrics import (compute_union_profile, compute_all_profiles,
                              compute_period_summary, compute_cross_union_comparison,
                              compute_movement_aggregates, compute_union_vs_movement,
                              compute_asset_composition, compute_spending_breakdown)
import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 140)
pd.set_option('display.float_format', lambda x: f'{x:,.1f}')

# %%
# Load all data
print("Loading LM-2 data (2000-2025)...")
lm = load_lm_data()
nhq = identify_nhq_filings(lm)
print(f"Total LM-2 filings: {len(lm):,}")
print(f"NHQ filings: {len(nhq):,}")

# %%
# Identify top 30 internationals (excluding federations)
top30 = top_internationals(lm, n=30)
federations = {'AFLCIO', 'SOC', 'TTD'}
unions = [(a,f,n) for a,f,n in top30 if a not in federations]
print(f"\nAnalyzing {len(unions)} international unions:")
for aff, fnum, name in unions:
    print(f"  {aff:10s}  {name}")

# %%
# Compute all profiles
profiles = compute_all_profiles(nhq, unions)

# %% [markdown]
# ## 1. Membership Trends (2000-2025)

# %%
print("\n" + "="*80)
print("MEMBERSHIP TRENDS: Active Members Where Available")
print("="*80)

# Load membership detail to get active members vs total
mem = load_membership()
print(f"Membership detail records: {len(mem):,}")

# For each union, try to get active members from detail table
for aff in ['CWA', 'SEIU', 'IBT', 'UAW', 'AFSCME', 'NEA', 'AFT', 'UFCW', 'USW', 'IBEW']:
    if aff not in profiles:
        continue
    profile = profiles[aff]
    print(f"\n--- {aff} ---")
    for yr in [2000, 2005, 2010, 2015, 2020, 2024]:
        row = profile[profile['year'] == yr]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        rpt_id = int(r['RPT_ID'])

        # Get membership breakdown
        mem_detail = mem[mem['RPT_ID'] == rpt_id]
        active = mem_detail[mem_detail['MEMBERSHIP_TYPE'] == '2101']
        active_dues = active[~active['CATEGORY'].str.contains('Non Dues|non dues|Non-Dues', case=False, na=False)]
        active_count = active_dues['NUMBER'].sum() if len(active_dues) > 0 else None

        lm2_total = r['MEMBERS']
        active_str = f"{active_count:>10,.0f}" if active_count else "     N/A"
        print(f"  {yr}: LM-2 Total={lm2_total:>10,.0f}  Active/Dues-Paying={active_str}")

# %% [markdown]
# ## 2. Cross-Union Financial Comparison (2010-2024)
#
# Replicating the Boehner period analysis across all unions.

# %%
print("\n" + "="*80)
print("CROSS-UNION COMPARISON: 2010-2024")
print("="*80)

comparison = compute_cross_union_comparison(profiles, 2010, 2024)
print(f"\n{'Union':10s} {'Mem Chg%':>8s} {'NA Start':>14s} {'NA End':>14s} {'NA Chg%':>8s} {'Real NA Chg':>14s} {'Surp%':>6s}")
print("-" * 80)
for idx, row in comparison.iterrows():
    print(f"{idx:10s} {row['member_change_pct']:>+7.1f}% ${row['net_assets_start']:>13,.0f} ${row['net_assets_end']:>13,.0f} {row['net_assets_change_pct']:>+7.1f}% ${row['net_assets_change_real']:>13,.0f} {row['avg_surplus_rate']:>+5.1f}%")

# %% [markdown]
# ## 3. Movement Aggregates (Boehner-Style)
#
# Total net assets, membership, and surplus for the entire labor movement.

# %%
print("\n" + "="*80)
print("LABOR MOVEMENT AGGREGATES (2000-2025)")
print("="*80)

mvmt = compute_movement_aggregates(lm)
print(f"\n{'Year':>4s} {'Unions':>6s} {'Members':>12s} {'Net Assets':>16s} {'Real Net Assets':>16s} {'Surplus%':>8s}")
print("-" * 70)
for _, r in mvmt[mvmt['year'] <= 2024].iterrows():
    print(f"{r['year']:>4.0f} {r['num_unions']:>6.0f} {r['total_members']:>12,.0f} ${r['total_net_assets']:>15,.0f} ${r['total_net_assets_real']:>15,.0f} {r['surplus_rate']:>+7.1f}%")

# Key Boehner stats
m2010 = mvmt[mvmt['year'] == 2010].iloc[0]
m2024 = mvmt[mvmt['year'] == 2024].iloc[0]
print(f"\n  2010->2024 Net Asset Growth: ${m2010['total_net_assets']:,.0f} -> ${m2024['total_net_assets']:,.0f}")
print(f"  Nominal change: ${m2024['total_net_assets'] - m2010['total_net_assets']:,.0f} ({(m2024['total_net_assets']/m2010['total_net_assets']-1)*100:+.1f}%)")
print(f"  Real change: ${m2024['total_net_assets_real'] - m2010['total_net_assets_real']:,.0f}")
print(f"  Membership change: {m2024['total_members'] - m2010['total_members']:+,.0f} ({(m2024['total_members']/m2010['total_members']-1)*100:+.1f}%)")

# %% [markdown]
# ## 4. CWA Deep Dive (Paper Validation)

# %%
print("\n" + "="*80)
print("CWA DEEP DIVE: Validating Against Paper Findings")
print("="*80)

cwa = profiles.get('CWA')
if cwa is not None:
    cwa_mvmt = compute_union_vs_movement(cwa, mvmt)

    print(f"\n{'Year':>4s} {'Members':>10s} {'Net Assets':>14s} {'Receipts':>14s} {'Surplus':>12s} {'Mem Share%':>10s} {'Asset Share%':>12s}")
    print("-" * 90)
    for _, r in cwa_mvmt[cwa_mvmt['year'] <= 2024].iterrows():
        ms = f"{r['member_share_pct']:.2f}%" if pd.notna(r.get('member_share_pct')) else "N/A"
        as_ = f"{r['asset_share_pct']:.2f}%" if pd.notna(r.get('asset_share_pct')) else "N/A"
        print(f"{r['year']:>4.0f} {r['MEMBERS']:>10,.0f} ${r['net_assets']:>13,.0f} ${r['TTL_RECEIPTS']:>13,.0f} ${r['surplus']:>11,.0f} {ms:>10s} {as_:>12s}")

# %% [markdown]
# ## 5. Asset Composition Analysis

# %%
print("\n" + "="*80)
print("ASSET COMPOSITION: Where Is The Money? (2024)")
print("="*80)

assets = load_assets(years=[2024])
print(f"Asset records loaded: {len(assets):,}")

# Get 2024 RPT_IDs for all top unions
rpt_map = {}
for aff, profile in profiles.items():
    row_2024 = profile[profile['year'] == 2024]
    if len(row_2024) > 0:
        rpt_map[aff] = int(row_2024.iloc[0]['RPT_ID'])

rpt_ids = set(rpt_map.values())
composition = compute_asset_composition(assets, rpt_ids)

# Merge with union names
rpt_to_aff = {v: k for k, v in rpt_map.items()}
composition['union'] = composition['RPT_ID'].map(rpt_to_aff)

print(f"\n{'Union':10s} {'Cash':>12s} {'Investments':>14s} {'Fixed':>12s} {'Other':>12s} {'Total':>14s} {'Liquid%':>8s}")
print("-" * 90)
for _, r in composition.sort_values('total', ascending=False).iterrows():
    if pd.isna(r.get('union')):
        continue
    print(f"{r['union']:10s} ${r['cash']:>11,.0f} ${r['investments']:>13,.0f} ${r['fixed_assets']:>11,.0f} ${r['other_assets']:>11,.0f} ${r['total']:>13,.0f} {r['liquidity_ratio']:>7.1f}%")

# %% [markdown]
# ## 6. Disbursement Category Breakdown

# %%
print("\n" + "="*80)
print("SPENDING BREAKDOWN: 2024")
print("="*80)

disb = load_disbursements(years=[2024])
breakdown = compute_spending_breakdown(disb, rpt_ids)
breakdown['union'] = breakdown['RPT_ID'].map(rpt_to_aff)

print(f"\n{'Union':10s} {'Represent%':>10s} {'Political%':>10s} {'Overhead%':>10s} {'Admin%':>10s} {'StrikeBen%':>10s} {'PerCapTax%':>10s}")
print("-" * 80)
for _, r in breakdown.sort_values('union').iterrows():
    if pd.isna(r.get('union')):
        continue
    print(f"{r['union']:10s} {r.get('REPRESENTATIONAL_pct', 0):>9.1f}% {r.get('POLITICAL_pct', 0):>9.1f}% {r.get('GENERAL_OVERHEAD_pct', 0):>9.1f}% {r.get('UNION_ADMINISTRATION_pct', 0):>9.1f}% {r.get('STRIKE_BENEFITS_pct', 0):>9.1f}% {r.get('PER_CAPITA_TAX_pct', 0):>9.1f}%")

print("\nAnalysis complete.")
