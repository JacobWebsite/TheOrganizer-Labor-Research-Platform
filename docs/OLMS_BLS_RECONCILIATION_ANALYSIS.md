# OLMS-BLS Union Membership Reconciliation Analysis (2024)

## Executive Summary

This analysis reconciles US Department of Labor OLMS (Office of Labor-Management Standards) union membership data with Bureau of Labor Statistics (BLS) Current Population Survey estimates. Starting from 20.2 million members reported on LM forms, systematic adjustments reduce the estimate to **15.9 million US union members**, bringing OLMS data within **11.3%** of the BLS benchmark of 14.3 million.

### Key Findings

| Metric | Value |
|--------|------:|
| Raw OLMS NHQ Filings | 20,241,994 |
| **Final US Estimate** | **15,915,232** |
| BLS Benchmark (2024) | 14,300,000 |
| Remaining Gap | +1,615,232 (+11.3%) |

---

## Methodology

### Step 1: Base Data Selection
- **Source**: NHQ (National Headquarters) filings only from 2024 LM data
- **Exclusions**: Federation umbrella organizations (AFL-CIO, Building Trades Dept, etc.)
- **Result**: 132 national/parent unions with 20,241,994 reported members

### Step 2: Retiree/Inactive Member Exclusion
Using Schedule 13 (ar_membership table) membership categories, excluded:
- Retirees, pensioners, life members
- Honorary, inactive, withdrawn members
- Disabled, emeritus, gold card, superannuated members

**Deduction: 2,094,249 members (10.3%)**

### Step 3: NEA/AFT Merged Affiliate Deduplication
State teacher unions with dual NEA/AFT affiliation were being counted twice:
- NYSUT (New York State United Teachers): 691,867
- FEA (Florida Education Association): 125,121
- Education Minnesota: 86,025

**Deduction: 903,013 members (4.5%)**

### Step 4: Canadian Membership Deduction
US-based international unions report Canadian members to OLMS, but BLS counts only US workers. Research identified Canadian membership for 23 unions.

**Deduction: 1,329,500 members (6.6%)**

---

## Canadian Membership Research

### Major International Unions with Canadian Members

| Union | Canadian Members | % of Total | Confidence | Source |
|-------|----------------:|----------:|:-----------|:-------|
| UFCW | 250,000 | ~20% | HIGH | UFCW Canada Annual Report |
| USW | 225,000 | ~26% | HIGH | usw.ca |
| LIUNA | 160,000 | ~32% | HIGH | Dec 2024 press release |
| IBT (Teamsters) | 125,000 | ~9% | HIGH | teamsters.ca |
| SEIU | 100,000 | ~5% | HIGH | 3 major Canadian locals |
| UBC/Carpenters | 70,000 | ~14% | HIGH | 5 regional councils |
| IBEW | 67,000 | ~8% | HIGH | IBEW First District (Nov 2024) |
| UA (Plumbers) | 62,000 | ~16% | HIGH | UA Canada (33 training centers) |
| IUOE | 52,500 | ~13% | HIGH | 17 Canadian locals |
| IAM | 40,000 | ~7% | HIGH | goiam.org |
| ATU | 35,000 | ~23% | HIGH | 30+ Canadian locals |
| UNITE HERE | 25,000 | ~8% | HIGH | 5 Canadian locals |
| Iron Workers | 23,000 | ~23% | HIGH | 2021 data |
| IATSE | 16,000 | ~10% | MEDIUM | 40 Canadian locals |
| AFM (Musicians) | 15,000 | ~23% | HIGH | Canadian Federation |
| SMART | 13,500 | ~6% | MEDIUM | Estimated |
| Boilermakers | 13,000 | ~29% | MEDIUM | 33 Canadian lodges |
| ALPA | 12,000 | ~16% | HIGH | Grew to 12K+ in 2023 |
| Painters (IUPAT) | 10,000 | ~9% | MEDIUM | 3 district councils |
| BCTGM | 8,411 | ~10% | HIGH | Gov't Canada Aug 2023 |
| ILWU | 7,300 | ~18% | HIGH | 12 BC locals |
| CWA | 6,000 | ~2% | HIGH | CWA Canada media |
| UAW | 2,200 | ~0.5% | HIGH | Local 251 only |
| **TOTAL** | **1,337,911** | | | |

### Historical Context
- In mid-20th century, ~2/3 of Canadian union members belonged to US-based internationals
- Today less than 25% of Canada's 5.3 million unionized workers are in international unions
- Shift driven by: Canadian nationalism, public sector growth (Canadian unions), formation of Unifor/CUPE

### Canada's Building Trades Unions (CBTU)
- Represents 600,000+ skilled trades workers
- 14 international union affiliates
- 197 training centers, $300M annual investment
- Generates 6% of Canada's GDP

---

## Final Reconciliation

### Adjustment Waterfall

```
Raw OLMS NHQ Data:              20,241,994  (100.0%)
  Less: Retirees/Inactive:      (2,094,249) (-10.3%)
  Less: NEA/AFT Dedup:            (903,013) ( -4.5%)
  Less: Canadian Members:       (1,329,500) ( -6.6%)
                                -----------
ESTIMATED US UNION MEMBERS:     15,915,232  ( 78.6%)

BLS BENCHMARK:                  14,300,000
REMAINING GAP:                  +1,615,232  (+11.3%)
```

### Top 10 US-Only Union Membership (2024)

| Rank | Union | US Members |
|-----:|:------|----------:|
| 1 | NEA (National Education Association) | 2,521,111 |
| 2 | SEIU (Service Employees) | 1,817,477 |
| 3 | AFT (American Federation of Teachers) | 1,313,336 |
| 4 | IBT (Teamsters) | 1,126,183 |
| 5 | AFSCME (State/County/Municipal) | 1,098,023 |
| 6 | UFCW (Food & Commercial Workers) | 950,264 |
| 7 | IBEW (Electrical Workers) | 649,942 |
| 8 | NFOP (Fraternal Order of Police) | 373,085 |
| 9 | UAW (Auto Workers) | 372,961 |
| 10 | CWA (Communications Workers) | 357,931 |

---

## Remaining Gap Analysis (~1.6M)

The 11.3% gap between our adjusted estimate and BLS is explained by:

### 1. Methodology Differences (Primary Factor)
- **BLS CPS**: Household survey asking individuals "are you a union member?"
- **OLMS**: Union self-reported membership on financial disclosure forms
- BLS may undercount (survey non-response, worker uncertainty about union status)
- OLMS may overcount (administrative lag in removing lapsed members)

### 2. Remaining Dual Memberships (~200-400K)
- Building trades workers belonging to multiple craft unions
- State/local employees in both AFSCME and independent state associations
- Professional association + union dual membership

### 3. Uncaptured Canadian Members (~50-100K)
- Smaller unions without Canadian-specific data
- Low-confidence estimates excluded from analysis (BAC, OPCMIA, HFIA, IUEC, Roofers, SIU, ILA)

### 4. Associate/Non-Working Members (~100-200K)
- Students maintaining membership
- Unemployed workers keeping union cards active
- Categories not fully captured by retirement exclusions

### 5. Timing & Territory Differences
- BLS uses annual average; OLMS uses fiscal year-end
- Puerto Rico and territory coverage variations

---

## Data Quality Notes

### High-Confidence Canadian Estimates
Sources with specific membership figures:
- Union websites with explicit Canadian membership counts
- Government of Canada Labour Organizations Database
- Recent press releases with membership claims
- Wikipedia with cited sources

### Medium-Confidence Estimates
- Proportional calculations from North American totals
- Estimates based on number of Canadian locals
- Older data (pre-2023)

### Excluded (Low Confidence)
- Unions with no Canadian-specific data: BAC, OPCMIA, HFIA, IUEC, Roofers
- Maritime unions refusing to disclose: SIU Canada, ILA
- No Canadian presence: AFA-CWA, MEBA

---

## Files Generated

| File | Description |
|------|-------------|
| `final_reconciliation_v2.py` | Python script for full analysis |
| `final_us_membership_high_confidence.csv` | All unions with Canadian deductions |
| `union_membership_estimate_2024.csv` | Raw estimates before deduplication |

---

## Conclusions

1. **OLMS data significantly overstates US union membership** due to inclusion of retirees, Canadian members, and dual-affiliated state unions

2. **Canadian membership accounts for ~1.3 million members** (6.6% of raw OLMS total) across 23 international unions, with UFCW, USW, LIUNA, Teamsters, and SEIU having the largest Canadian contingents

3. **After systematic adjustments, OLMS and BLS estimates converge** to within 11.3%, a reasonable gap given fundamental methodology differences between union self-reports and household surveys

4. **The remaining ~1.6M gap** likely reflects a combination of OLMS overcounting (lapsed members) and BLS undercounting (survey limitations), plus residual dual memberships and associate members

---

*Analysis completed: January 2025*
*Data sources: OLMS LM filings (2024), BLS CPS (2024), union websites, Government of Canada*
