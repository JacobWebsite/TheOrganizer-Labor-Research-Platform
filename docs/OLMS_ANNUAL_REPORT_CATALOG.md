# OLMS Annual Report Tables Catalog

Date: 2026-02-18
Database: `olms_multiyear`

## Overview

Four OLMS LM (Labor-Management) annual report tables contain detailed union financial and membership data. All join to `lm_data` via `rpt_id`, which links to `unions_master` via `f_num`. Year coverage: 2010-2025 (2025 partial).

**Join path:** `ar_* -> lm_data (rpt_id) -> unions_master (f_num) -> f7_union_employer_relations (union_file_number)`

- 18,429 distinct union f_nums in annual reports (100% joinable to unions_master)
- 6,561 f_nums joinable to f7_union_employer_relations (employer linkage)

---

## Table 1: ar_disbursements_total (216,372 rows)

Union spending broken down by category per annual report.

### Schema
| Column | Type | Description |
|--------|------|-------------|
| rpt_id | varchar | FK to lm_data |
| representational | numeric | Representational activities spending |
| political | numeric | Political activities spending |
| contributions | numeric | Contributions to other organizations |
| general_overhead | numeric | General overhead |
| union_administration | numeric | Union administration |
| withheld | numeric | Taxes withheld |
| members | numeric | Direct member benefits |
| supplies | numeric | Supplies |
| fees | numeric | Professional fees |
| administration | numeric | Administration |
| direct_taxes | numeric | Direct taxes paid |
| strike_benefits | numeric | Strike fund disbursements |
| per_capita_tax | numeric | Per capita tax to parent org |
| to_officers | numeric | Officer compensation |
| investments | numeric | Investment purchases |
| benefits | numeric | Benefits paid |
| loans_made | numeric | Loans made |
| loans_payment | numeric | Loan payments |
| affiliates | numeric | Payments to affiliates |
| other_disbursements | numeric | Other |
| to_employees | numeric | Employee compensation |
| load_year | integer | Filing year |

### Key Stats
- 65,079 reports with representational spend > 0 (avg $1.1M, max $154M)
- Total representational spend across all years: $71.8 billion
- Total political spend: $11.1 billion
- Total strike benefits: $1.5 billion
- ~14,000 reports/year (declining slightly, from 15,468 in 2010 to 13,190 in 2024)

### Integration Priority: TIER 1
**Organizing capacity signal:** `representational` spend is the single best proxy for how much a union invests in organizing. Combined with `per_capita_tax` (funds flowing up to parent) and `strike_benefits` (willingness to fund action), this gives a financial organizing readiness score per union.

---

## Table 2: ar_membership (216,508 rows)

Membership counts by category per annual report. Each report can have multiple rows (one per membership category).

### Schema
| Column | Type | Description |
|--------|------|-------------|
| oid | varchar | Row ID |
| membership_type | integer | Category code (2101=Full Dues, 2102=Agency Fee, etc.) |
| category | varchar | Free-text category label (WARNING: highly inconsistent) |
| number | integer | Member count |
| voting_eligibility | varchar | T/F - whether this category can vote |
| rpt_id | varchar | FK to lm_data |
| load_year | integer | Filing year |

### Key Stats
- Category names are **extremely messy** -- hundreds of free-text variations for the same concept ("Active Members", "ACTIVE MEMBERS", "Active members", "Active Member", "ACTIVE", etc.)
- 5,511 unions with 2+ years of voting-eligible membership data
- **Growing: 2,577 (47%) | Declining: 2,820 (51%) | Stable: 114 (2%)**
- Use `voting_eligibility = 'T'` to filter to actual members (excludes agency fee payers, retirees)

### Integration Priority: TIER 1
**Membership trend signal:** Year-over-year change in voting-eligible members is a direct measure of union growth/decline. A growing union is more likely to pursue new organizing. Must normalize category labels first (recommend grouping by `membership_type` integer code rather than free-text `category`).

---

## Table 3: ar_assets_investments (304,816 rows)

Union financial assets by type per annual report.

### Schema
| Column | Type | Description |
|--------|------|-------------|
| oid | varchar | Row ID |
| inv_type | integer | Asset type code |
| name | varchar | Asset description (often "N/A") |
| amount | numeric | Dollar amount |
| rpt_id | varchar | FK to lm_data |
| load_year | integer | Filing year |

### Asset Type Codes
| Code | Meaning | Reports | Total |
|------|---------|--------:|------:|
| 704 | US Treasury Securities | 24,565 | $165.0B |
| 703 | Loans Receivable | 23,524 | $157.3B |
| 701 | Cash | 20,913 | $77.8B |
| 706 | Fixed Assets | 8,959 | $33.2B |
| 705 | Investments | 8,397 | $31.7B |
| 702 | Accounts Receivable | 7,056 | $27.9B |

### Integration Priority: TIER 2
**Financial health signal:** Cash + investments indicates a union's ability to fund organizing campaigns and sustain strikes. A union with $10M in cash is more likely to take on a new campaign than one running near zero. Less directly tied to organizing intent than spending or membership trends.

---

## Table 4: ar_disbursements_emp_off (2,813,248 rows)

Individual officer and employee compensation records. Each row is one person's compensation for one reporting year.

### Schema
| Column | Type | Description |
|--------|------|-------------|
| oid | varchar | Row ID |
| emp_off_type | integer | 601=Officer, 602=Employee |
| first_name | varchar | |
| middle_name | varchar | |
| last_name | varchar | |
| title | varchar | Job title |
| status_other_payer | varchar | C=Continuing, N=New |
| gross_salary | numeric | Base salary |
| allowances | numeric | Allowances |
| official_business | numeric | Business expenses |
| other_not_rptd | numeric | Other unreported |
| total | numeric | Total compensation |
| rep_pct | numeric | % time on representational activities |
| pol_pct | numeric | % time on political activities |
| cont_pct | numeric | % time on contributions |
| gen_ovrhd_pct | numeric | % time on general overhead |
| admin_pct | numeric | % time on administration |
| rpt_id | varchar | FK to lm_data |
| item_num | varchar | Line item number |
| load_year | integer | Filing year |

### Key Stats
- 638,473 officer records with >=80% representational time (organizers/reps)
- 287,007 with 20-79% representational time (mixed role)
- Largest table (2.8M rows) -- one row per person per year

### Integration Priority: FUTURE
**Staffing signal:** Count of officers/employees with high `rep_pct` indicates how many full-time organizers a union employs. Useful for advanced modeling but lower priority than spending and membership trends. Privacy considerations for individual compensation data.

---

## Suggested Integration Plan

### Phase 1: Union Organizing Capacity Score (Tier 1)
Build a per-union organizing capacity factor using:
1. **Representational spend** from `ar_disbursements_total` (normalized by union size)
2. **Membership growth trend** from `ar_membership` (voting-eligible YoY change)
3. **Strike fund activity** from `ar_disbursements_total.strike_benefits`

Join to employers via: `lm_data.f_num -> f7_union_employer_relations.union_file_number`

This would create a new scoring factor for `mv_unified_scorecard` measuring "how active/well-resourced is the union representing workers at this employer."

### Phase 2: Financial Health (Tier 2)
Add cash/investment totals from `ar_assets_investments` as a secondary signal.

### Data Quality Notes
- Membership `category` field needs normalization (use `membership_type` integer code instead)
- 3 rpt_ids in ar_disbursements_total don't join to lm_data (negligible)
- 2025 data is partial (3,276 reports vs ~13K typical year)
- `lm_data.f_num` is integer; `unions_master.f_num` is varchar -- cast needed for joins
