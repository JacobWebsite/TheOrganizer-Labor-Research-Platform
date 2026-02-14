"""
02_industry_exposure.py - Industry Exposure & Decline Analysis

Extends the CWA Fortress analysis: maps each union to its primary industries
and correlates industry employment trends with union membership changes.

Key insight from the paper: CWA's membership decline is partly structural
(telecom industry contraction) rather than purely an organizing failure.
This notebook extends that analysis across all major internationals.

Usage:
    python notebooks/02_industry_exposure.py
    # Or convert: jupytext --to notebook notebooks/02_industry_exposure.py
"""

# %% [markdown]
# # Industry Exposure & Decline Analysis
#
# **Extending the CWA Fortress methodology across all internationals**
#
# The CWA paper demonstrated that telecommunications industry decline was a
# major structural factor behind CWA's membership losses. This notebook
# applies the same logic across all top international unions:
#
# 1. What industries does each union depend on?
# 2. How have those industries changed (employment, union density)?
# 3. How much of each union's membership change is structural vs. organizing?
# 4. Which unions face the biggest industry headwinds?

# %%
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.etl import load_lm_data, identify_nhq_filings, top_internationals
from scripts.metrics import compute_all_profiles, compute_period_summary
from scripts.industry import (load_bls_industry_data, compute_industry_trends,
                               compute_industry_summary, compute_all_exposures,
                               compute_union_industry_exposure,
                               decompose_membership_change,
                               get_union_industry_mapping, UNION_INDUSTRY_MAP)
import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 140)
pd.set_option('display.float_format', lambda x: f'{x:,.1f}')

# %%
# Load data
print("Loading BLS industry data (2000-2024)...")
bls = load_bls_industry_data()
print(f"  BLS industry-year observations: {len(bls):,}")

print("\nLoading LM-2 data (2000-2025)...")
lm = load_lm_data()
nhq = identify_nhq_filings(lm)
print(f"  Total LM-2 filings: {len(lm):,}")
print(f"  NHQ filings: {len(nhq):,}")

# Identify top unions
top30 = top_internationals(lm, n=30)
federations = {'AFLCIO', 'SOC', 'TTD'}
unions = [(a, f, n) for a, f, n in top30 if a not in federations]
print(f"\nAnalyzing {len(unions)} international unions")

# Compute financial profiles
profiles = compute_all_profiles(nhq, unions)

# %% [markdown]
# ## 1. Industry Employment Trends (2000-2024)
#
# Which industries are growing vs. declining, and how has union density changed?

# %%
print("\n" + "="*100)
print("INDUSTRY EMPLOYMENT & UNION MEMBERSHIP TRENDS (2000-2024)")
print("="*100)
print("  Employment and union membership in thousands (BLS CPS data)")

summary = compute_industry_summary(bls)

# Sort by union membership change
summary_display = summary[summary['indy_code'] != '0000'].copy()

print(f"\n{'Industry':38s} {'Emp 2000':>9s} {'Emp 2024':>9s} {'Emp Chg%':>8s} {'Uni 2000':>9s} {'Uni 2024':>9s} {'Uni Chg%':>8s} {'Dens 00':>7s} {'Dens 24':>7s}")
print("-" * 115)
for _, r in summary_display.iterrows():
    print(f"{r['industry']:38s} {r['emp_start']:>8,.0f}K {r['emp_end']:>8,.0f}K {r['emp_change_pct']:>+7.1f}% {r['union_start']:>8,.0f}K {r['union_end']:>8,.0f}K {r['union_change_pct']:>+7.1f}% {r['density_start']:>6.1f}% {r['density_end']:>6.1f}%")

# %% [markdown]
# ## 2. CWA Deep Dive: The Telecom Decline Story
#
# Replicating the paper's core finding: telecom employment collapsed from
# ~1,100K to ~570K (-48%) while union membership fell from 261K to 51K (-80.5%).

# %%
print("\n" + "="*100)
print("CWA CASE STUDY: TELECOMMUNICATIONS INDUSTRY DECLINE")
print("="*100)

# Get telecom trends year-by-year
trends = compute_industry_trends(bls)
telecom = trends[trends['indy_code'] == '6679'].copy()

print(f"\n{'Year':>4s} {'Total Emp':>10s} {'Union Mem':>10s} {'Density':>8s} {'Emp Idx':>8s} {'Union Idx':>9s}")
print("-" * 55)
for _, r in telecom.iterrows():
    print(f"{r['year']:>4.0f} {r['total_employed']:>9,.0f}K {r['union_members']:>9,.0f}K {r['union_density_pct']:>7.1f}% {r['employment_index']:>7.1f} {r['union_index']:>8.1f}")

# CWA exposure breakdown
cwa_exposure = compute_union_industry_exposure('CWA', bls)
print(f"\nCWA Industry Exposure Breakdown:")
print(f"{'Industry':35s} {'Weight':>6s} {'Emp Chg%':>8s} {'Uni Chg%':>9s} {'Dens Chg':>8s} {'Contrib Emp':>11s} {'Contrib Uni':>11s}")
print("-" * 95)
for d in cwa_exposure['industry_detail']:
    print(f"{d['industry']:35s} {d['weight']:>5.0%} {d['emp_change_pct']:>+7.1f}% {d['union_change_pct']:>+8.1f}% {d['density_change']:>+7.2f} {d['contribution_emp']:>+10.1f} {d['contribution_union']:>+10.1f}")

print(f"\n  Weighted employment change:  {cwa_exposure['weighted_emp_change_pct']:>+.1f}%")
print(f"  Weighted union change:       {cwa_exposure['weighted_union_change_pct']:>+.1f}%")
print(f"  Weighted density change:     {cwa_exposure['weighted_density_change']:>+.2f} pp")
print(f"  Headwind score:              {cwa_exposure['headwind_score']:>+.1f}")

# CWA decomposition
cwa_profile = profiles.get('CWA')
if cwa_profile is not None:
    decomp = decompose_membership_change(cwa_profile, cwa_exposure)
    if decomp:
        print(f"\n  CWA Membership Decomposition (2000-2024):")
        print(f"    Starting members:    {decomp['members_start']:>10,.0f}")
        print(f"    Ending members:      {decomp['members_end']:>10,.0f}")
        print(f"    Actual change:       {decomp['actual_change']:>+10,.0f} ({decomp['actual_change_pct']:>+.1f}%)")
        print(f"    Structural effect:   {decomp['structural_effect']:>+10,.0f} ({decomp['structural_effect_pct']:>+.1f}%)")
        print(f"    Density effect:      {decomp['density_effect']:>+10,.0f} ({decomp['density_effect_pct']:>+.1f}%)")
        print(f"    Organizing effect:   {decomp['organizing_effect']:>+10,.0f} ({decomp['organizing_effect_pct']:>+.1f}%)")

# %% [markdown]
# ## 3. Cross-Union Industry Exposure Rankings
#
# Which unions face the strongest headwinds from industry decline?

# %%
print("\n" + "="*100)
print("CROSS-UNION INDUSTRY EXPOSURE RANKINGS (2000-2024)")
print("="*100)
print("  Headwind Score: negative = industries declining, positive = industries growing")
print("  Combines weighted employment change and weighted density change\n")

# Get all union abbreviations that we have profiles for
mapped_unions = [aff for aff, _, _ in unions if aff in UNION_INDUSTRY_MAP]
exposures = compute_all_exposures(bls, unions=mapped_unions)

print(f"{'Rank':>4s} {'Union':12s} {'Headwind':>10s} {'Wtd Emp%':>9s} {'Wtd Uni%':>9s} {'Wtd Dens':>9s}")
print("-" * 60)
for i, (_, r) in enumerate(exposures.iterrows(), 1):
    print(f"{i:>4d} {r['union']:12s} {r['headwind_score']:>+9.1f} {r['weighted_emp_change_pct']:>+8.1f}% {r['weighted_union_change_pct']:>+8.1f}% {r['weighted_density_change']:>+8.2f}")

# %% [markdown]
# ## 4. Membership Decomposition: Structural vs. Organizing
#
# For each union, decompose membership changes into:
# - **Structural effect**: changes due to industry employment trends
# - **Density effect**: changes due to union penetration rates shifting
# - **Organizing effect**: residual (organizing wins/losses net of structure)

# %%
print("\n" + "="*100)
print("MEMBERSHIP CHANGE DECOMPOSITION (2000-2024)")
print("="*100)
print("  Structural = industry employment shifts")
print("  Density = union penetration rate changes")
print("  Organizing = residual (actual minus structural and density)\n")

decomp_rows = []
for aff in mapped_unions:
    profile = profiles.get(aff)
    if profile is None:
        continue

    exposure = compute_union_industry_exposure(aff, bls)
    if not exposure:
        continue

    decomp = decompose_membership_change(profile, exposure)
    if decomp:
        decomp_rows.append(decomp)

decomp_df = pd.DataFrame(decomp_rows)
decomp_df = decomp_df.sort_values('headwind_score')

print(f"{'Union':12s} {'Members 00':>11s} {'Members 24':>11s} {'Actual%':>8s} {'Struct%':>8s} {'Dens%':>8s} {'Org%':>8s} {'Headwind':>10s}")
print("-" * 85)
for _, r in decomp_df.iterrows():
    print(f"{r['union']:12s} {r['members_start']:>10,.0f} {r['members_end']:>10,.0f} {r['actual_change_pct']:>+7.1f}% {r['structural_effect_pct']:>+7.1f}% {r['density_effect_pct']:>+7.1f}% {r['organizing_effect_pct']:>+7.1f}% {r['headwind_score']:>+9.1f}")

# %% [markdown]
# ## 5. Industry Trajectory Dashboard
#
# Key industries classified by employment and union membership trajectory.

# %%
print("\n" + "="*100)
print("INDUSTRY TRAJECTORY CLASSIFICATION (2000-2024)")
print("="*100)

# Classify industries into quadrants
for trajectory in ['DECLINING', 'STABLE', 'GROWING']:
    industries = summary_display[summary_display['emp_trajectory'] == trajectory]
    if len(industries) == 0:
        continue

    print(f"\n  {trajectory} EMPLOYMENT INDUSTRIES:")
    for _, r in industries.sort_values('union_change_pct').iterrows():
        union_traj = "↓" if r['union_change_pct'] < -15 else ("↑" if r['union_change_pct'] > 15 else "→")
        print(f"    {r['industry']:35s}  Emp: {r['emp_change_pct']:>+6.1f}%  Union: {r['union_change_pct']:>+6.1f}% {union_traj}  Density: {r['density_end']:.1f}%")

# %% [markdown]
# ## 6. CWA vs. UAW vs. SEIU: Contrasting Industry Stories
#
# Three different union archetypes:
# - CWA: declining industry (telecom), fortress strategy
# - UAW: recovering industry (auto), recent organizing surge
# - SEIU: growing industry (healthcare), service-sector model

# %%
print("\n" + "="*100)
print("CONTRASTING MODELS: CWA vs UAW vs SEIU")
print("="*100)

for aff in ['CWA', 'UAW', 'SEIU']:
    exposure = compute_union_industry_exposure(aff, bls)
    profile = profiles.get(aff)
    if not exposure or profile is None:
        continue

    decomp = decompose_membership_change(profile, exposure)

    print(f"\n--- {aff} ---")
    print(f"  Headwind score: {exposure['headwind_score']:>+.1f}")
    if decomp:
        print(f"  Members: {decomp['members_start']:,.0f} → {decomp['members_end']:,.0f} ({decomp['actual_change_pct']:>+.1f}%)")
        print(f"  Structural:  {decomp['structural_effect_pct']:>+.1f}%  (industry employment changes)")
        print(f"  Density:     {decomp['density_effect_pct']:>+.1f}%  (union penetration changes)")
        print(f"  Organizing:  {decomp['organizing_effect_pct']:>+.1f}%  (net organizing wins/losses)")

    print(f"\n  Primary industries:")
    for d in exposure['industry_detail'][:3]:
        print(f"    {d['industry']:30s} ({d['weight']:.0%}) → Emp: {d['emp_change_pct']:>+.1f}%, Union: {d['union_change_pct']:>+.1f}%")

# %% [markdown]
# ## 7. Financial Performance vs. Industry Headwinds
#
# Do unions with worse industry headwinds accumulate more wealth (fortress)?
# Or do they face financial pressure from declining dues revenue?

# %%
print("\n" + "="*100)
print("FINANCIAL PERFORMANCE vs. INDUSTRY HEADWINDS")
print("="*100)
print("  Comparing net asset growth to industry exposure\n")

comparison_rows = []
for aff in mapped_unions:
    profile = profiles.get(aff)
    if profile is None:
        continue

    exposure_result = compute_union_industry_exposure(aff, bls)
    if not exposure_result:
        continue

    period = compute_period_summary(profile, 2010, 2024)
    if not period:
        continue

    comparison_rows.append({
        'union': aff,
        'headwind_score': exposure_result['headwind_score'],
        'member_change_pct': period.get('member_change_pct', 0),
        'net_assets_change_pct': period.get('net_assets_change_pct', 0),
        'avg_surplus_rate': period.get('avg_surplus_rate', 0),
        'net_assets_change_real': period.get('net_assets_change_real', 0),
    })

comp = pd.DataFrame(comparison_rows).sort_values('headwind_score')

print(f"{'Union':12s} {'Headwind':>10s} {'Mem Chg%':>9s} {'NA Chg%':>9s} {'Real NA Chg':>14s} {'Surp Rate':>10s}")
print("-" * 70)
for _, r in comp.iterrows():
    print(f"{r['union']:12s} {r['headwind_score']:>+9.1f} {r['member_change_pct']:>+8.1f}% {r['net_assets_change_pct']:>+8.1f}% ${r['net_assets_change_real']:>12,.0f} {r['avg_surplus_rate']:>+9.1f}%")

# Key correlation
if len(comp) > 5:
    corr_headwind_na = comp['headwind_score'].corr(comp['net_assets_change_pct'])
    corr_headwind_mem = comp['headwind_score'].corr(comp['member_change_pct'])
    corr_mem_na = comp['member_change_pct'].corr(comp['net_assets_change_pct'])

    print(f"\n  Correlation: Headwind ↔ Net Asset Growth:  {corr_headwind_na:>+.3f}")
    print(f"  Correlation: Headwind ↔ Membership Change: {corr_headwind_mem:>+.3f}")
    print(f"  Correlation: Membership ↔ Net Asset Growth: {corr_mem_na:>+.3f}")

print("\nAnalysis complete.")
