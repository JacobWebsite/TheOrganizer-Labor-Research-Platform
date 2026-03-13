# Methodological Review of Using Economic Census 2022 and SUSB for Revenue-Per-Employee Ratios

## Data constructs and what “RPE” actually means in Census programs

Revenue-per-employee (RPE) is typically computed as **(sales/receipts/revenue) ÷ (employees)**. With the 2022 quinquennial business benchmark, the numerator is generally a **calendar-year 2022** concept (sometimes reported by fiscal year if it covers most of 2022), while the denominator is usually a **mid‑March headcount** concept tied to payroll-reporting. In 2022 Economic Census instruments, employment is explicitly asked as “the number of employees for pay period including March 12,” and it is based on payroll filed under the establishment’s EIN (IRS Form 941), including employees working from home but excluding contractors and leased employees. citeturn10view0turn9view0

A key implication is that **RPE computed from these sources is not “annual average revenue divided by annual average employment.”** It is closer to **“annual revenue divided by a point‑in‑time payroll headcount.”** This matters for seasonal industries, rapidly growing/contracting firms, and sectors with high use of contractors or staffing agencies (whose labor is excluded from the employee count). citeturn10view0

For the annual series, SUSB’s core content is described as **number of firms, number of establishments, annual payroll, and employment during the week of March 12**; it additionally includes **receipts data in years ending in 2 and 7**, and those receipts are explicitly described in Census documentation as **estimated receipts** (not necessarily directly reported receipts for the full universe). SUSB also notes a typical **~24‑month lag** after each reference year. citeturn20search0turn20search1

This creates a basic methodological fork:

- If you compute RPE from **Economic Census** tables, you are generally using **survey-collected (with imputation/editing) establishment data** benchmarked to 2022 and disseminated with disclosure controls. citeturn27search0turn27search7  
- If you compute RPE from **SUSB receipts ÷ SUSB employment**, you are combining **estimated receipts** (in 2/7 years) with a **March 12 employment snapshot**, typically at **state/MSA (and national) levels** rather than county-by-6‑digit granularity. citeturn20search0turn20search1

A recurring theme across the critiques below is **unit alignment**—aligning (a) *what* is being summed (establishments vs enterprises), (b) *where* it is being summed (county/state/national), and (c) *when* it is being measured (calendar revenue vs March employment). citeturn27search5turn10view0

## Establishment vs enterprise bias in multi-location enterprises

### Why “place-of-work” establishment data can mis-estimate an enterprise workforce

The Economic Census is fundamentally an **establishment-based program** (a physical operating location), while many policy, finance, and nonprofit reporting concepts are **enterprise/organization-based**. The unit-of-analysis distinction is not cosmetic: the Census “enterprise” concept is described (in labor statistics guidance using Census definitions) as the entire economic unit under common ownership or control (often framed as >50% ownership/control), and it may include “all establishments, subsidiaries, and divisions with the same or different EINs under the same ownership.” citeturn27search5

When an analyst tries to use **location-specific** (county/state) establishment RPE to infer an enterprise’s workforce scale or enterprise-level productivity, several systematic errors become likely:

**Payroll/EIN-driven assignment of workers can differ from physical location of work.** Economic Census instruments define employees as those whose payroll is reported under the establishment’s EIN and explicitly include employees working from home. In practice, remote or centralized workers can be paid under a particular EIN or reporting unit, causing the establishment’s employee count to reflect payroll assignment rather than the worker’s residential geography. citeturn10view0

**Multi-unit allocation introduces modeled, not always directly observed, establishment employment/payroll.** For multi-unit businesses, administrative payroll and employment are filed at EIN levels; public establishment tabulations often require allocating those EIN-level totals to specific establishments. For example, documentation for business-dynamics tabulations notes that in multi-unit firms, IRS-reported payroll/employment are at the aggregate employer level and that establishment-level splits may be modeled (with specific limitations, such as how quarter-specific information is handled). citeturn2search0  
Separately, County Business Patterns methodology explicitly states that EIN-level administrative payroll and employment may be **apportioned to the establishment level** for smaller companies not selected for establishment-level surveys or in cases of nonresponse. citeturn27search12

**Enterprise employment spans multiple industries, not just one (“industry mix” problem).** Because an enterprise can include establishments with different industries, inferring an enterprise’s total workforce from a single NAICS cell (e.g., “the county’s NAICS 62 cell”) risks excluding employees in management offices, shared services, and other supporting units that can be classified outside the operating NAICS. This risk is directly suggested by the enterprise definition as including establishments that may be under different EINs and business divisions. citeturn27search5

### Consolidated reporting as a hidden mechanism for enterprise bias

Some 2022 Economic Census instruments explicitly instruct respondents with multiple locations under one EIN to **report certain items on a consolidated basis** (summing across locations) even though other items are to be reported for the individual location, with a “location list” later used to itemize establishment-level information. This is an explicit acknowledgment that **multi-location reporting can be centralized and then disaggregated**, which can create additional opportunities for reporting/allocative error and for mismatches between “local” and “enterprise” denominators when users compute ratios. citeturn13view0

Methodologically, this means county- or place-based RPE can embed two layers of enterprise bias:

1. **Reporting-unit bias**: data are initially reported (or imputed) at a consolidated reporting unit, then allocated. citeturn13view0turn27search12  
2. **Interpretation bias**: users may treat establishment outputs as enterprise outputs (or vice versa), especially when benchmarking a multi-state enterprise to local RPE. citeturn27search5

## NAICS granularity, disclosure avoidance, and the county-by-6-digit problem

### Noise infusion makes ratios statistically fragile

For county-by-industry work, analysts often reach for CBP-style tabulations for employment (county level) and then try to attach revenue from Economic Census releases or other sources. At fine NAICS (5- or 6-digit) × small geography levels, two disclosure-related issues dominate:

**Noise infusion (multiplicative noise) perturbs establishment values prior to tabulation.** In official documentation describing CBP disclosure methods, the Census Bureau explains that since 2007 it has used **multiplicative noise**: applying a random noise multiplier to establishment magnitude data (employment, payroll), and then producing cell-level flags for the relative distortion: **G (<2%), H (2–<5%), J (≥5%)**. citeturn19view0

If you compute RPE at these granular levels, you are effectively forming a ratio whose denominator (employees) may have been noise-infused (and possibly also numerator if it comes from a noise-infused series). Even if the noise is unbiased in levels, **ratios can be biased and highly volatile** when:
- the denominator is small,
- noise is applied independently to numerator/denominator (or through different mechanisms), or
- the cell is a residual category with heterogeneous establishments.

The methodological takeaway is that **RPE is “noise-amplifying”** at county-by-6-digit granularity, because division magnifies relative error when employment counts are low. citeturn19view0turn27search0

### Suppression flags and the selection bias of “published cells only”

CBP disclosure documentation also notes that some values are suppressed (denoted with “S”) due to data quality concerns, and that starting with reference year 2017, a cell is only published if based on **three or more establishments**; otherwise the corresponding row is dropped from publication. citeturn19view0

This is central to RPE methodology because it creates **non-random missingness**:
- Small counties, niche 6-digit industries, and high-concentration markets are more likely to be unpublished.
- Observed county-by-6-digit RPE is therefore conditioned on *survival through publication rules*, which can bias mean/median RPE upward or downward depending on which establishments remain. citeturn19view0

A common point of confusion is the “D” suppression flag. CBP program documentation explains that the former “D” flag (withheld to avoid disclosure) was replaced by “S” beginning in 2017. So, for 2022 county-by-industry data, “S” is generally the operative suppression mechanism, even if some secondary user guides still define “D” historically. citeturn18search1turn19view0

### Economic Census disclosure avoidance reduces county-by-6-digit reliability even when values exist

Economic Census dissemination explicitly applies disclosure avoidance to protect establishments/companies, including modifying or removing sensitive characteristics. citeturn27search0  
At county and detailed NAICS, Economic Census releases can therefore suffer from:
- **suppressed cells**,  
- **coarsened industry detail**, or  
- **non-publication for certain NAICS-by-geo combinations**, depending on sector and product line.

From an RPE perspective, the key methodological point is that **geographic RPE at 6-digit NAICS is often “statistically under-identified”** in public data: you may not simultaneously observe high-quality, unsuppressed, low-noise (a) revenue and (b) employee counts for the same county-by-6-digit cell. citeturn27search0turn19view0

## Nonprofit vs for-profit variance: are “receipts” comparable to Form 990 total revenue in healthcare and education?

### The Economic Census uses different revenue concepts depending on tax status and instrument

A critical nuance for NAICS 61 (Education) and NAICS 62 (Healthcare) is that Economic Census instruments often distinguish between **taxable** and **tax-exempt** reporting, and the *meaning* of the numerator changes accordingly.

In a 2022 education-sector questionnaire example, respondents are asked whether income is exempt under section 501. If **taxable**, the form asks for “total operating receipts.” If **tax-exempt**, it asks for “total revenue” (and total expenses). citeturn9view2turn9view3

A healthcare-sector questionnaire example (home health care services) follows the same structure: taxable establishments report operating receipts, while tax-exempt establishments report total revenue, and the instrument separately identifies **non-operating revenue** components such as contributions/grants and investment/property income. citeturn33view0turn32view0

Methodological implication: in NAICS 61/62, **“receipts” is not always a single, uniform construct**. Public tabulations may mix taxable operating receipts with tax-exempt total revenue depending on the table definition, the sector’s publication conventions, and how Census harmonizes outputs. citeturn9view2turn9view3turn33view0

### Form 990 total revenue is an organization-level accounting construct

The IRS Form 990 “Total revenue” on the core summary page is defined as the sum of major revenue categories including **contributions and grants, program service revenue, investment income, and other revenue**. citeturn29view0

This provides an immediate conceptual mismatch with many “operating receipts” concepts in establishment surveys:

- “Program service revenue” is typically analogous to tuition/patient-service receipts (operating).  
- “Contributions and grants” and “investment income” can be material for nonprofits (especially large systems and endowed institutions). citeturn29view0turn33view0

### Sector-specific mapping issues: healthcare (NAICS 62) and education (NAICS 61)

In healthcare survey materials, the instrument explicitly separates “Net Patient Care Operating Revenue” from other categories and instructs respondents (in that section) to **exclude non-patient care revenue such as grants, subsidies, contributions, and philanthropy**—placing such items conceptually outside patient-care revenue. citeturn13view0turn32view0  
Meanwhile, the same healthcare instrument for tax-exempt reporting captures **non-operating revenue** including “contributions, gifts, and grants received” and investment/property income, and then defines total revenue as the sum of operating and non-operating components. citeturn33view0turn32view0

In education, the tax-exempt path’s “total revenue” concept is closer in spirit to Form 990’s total revenue than the taxable “operating receipts” concept, but two structural differences remain:

1. **Unit mismatch:** Form 990 is filed for an organization (which may encompass multiple establishments and related entities), whereas Economic Census is fundamentally establishment-based (even when consolidated reporting is used operationally). citeturn27search5turn13view0  
2. **Reporting-period mismatch:** Economic Census reporting is framed to calendar year 2022 (with a fiscal-year exception under conditions), while Form 990 is for a tax year. citeturn9view0turn29view0

**Bottom line for methodological validity:** Census “receipts” can be a reasonable proxy for Form 990 “Total revenue” **only under specific conditions**—primarily when you are using an Economic Census output that corresponds to **tax-exempt total revenue** (not just operating receipts), and when the organization’s reporting boundary roughly aligns with the establishment boundary being analyzed. In multi-facility health systems and multi-campus educational institutions, those conditions often fail, making Form 990-based revenue fundamentally non-comparable to a single-establishment Census receipts figure without a careful crosswalk and consolidation protocol. citeturn9view3turn33view0turn29view0turn27search5

## Lag and volatility: using 2022 baselines for 2025/2026 estimates

### Timing lag is structural, not incidental

The 2022 Economic Census is collected as a quinquennial benchmark; official guidance indicates that the first data releases began in 2024, geographic area statistics were scheduled for 2025, and remaining releases were planned through March 2026. citeturn27search15turn27search7  
SUSB similarly notes a typical ~24‑month lag after each reference year. citeturn20search0

Thus, a 2025/2026 analyst using 2022 Economic Census or SUSB as a baseline is inherently working with:

- an “as of 2022” revenue structure, and  
- an “as of March 2022” workforce snapshot in the denominator. citeturn10view0turn20search0

### Inflation makes nominal RPE drift even if real productivity is unchanged

Because RPE is often calculated in nominal dollars, inflation can cause nominal RPE to rise even without efficiency gains. U.S. price measures and inflation reporting (e.g., CPI and producer price indexes) show ongoing year-to-year price changes in the period relevant to 2022→2025/2026 extrapolation, underscoring the need for deflation or price-index updating when using 2022 nominal receipts as a “baseline revenue.” citeturn22search12turn22search6turn22search1

Methodologically, inflation introduces at least three pathways for “baseline drift”:

- **Output-price inflation** (revenues rise in nominal terms even if volumes don’t). citeturn22search12turn22search6  
- **Input-cost inflation and contracting** (outsourcing may rise; contractor labor is excluded from payroll employee counts). citeturn10view0  
- **Composition effects** (mix shifts toward higher-price services/products, especially in tech-enabled services). citeturn21search16turn21search5

### Workforce volatility and measurement revisions

For fast-shifting industries (including many “information/tech” segments), the employment denominator can change rapidly, and employment series themselves can be subject to benchmark revisions. This is one reason many practitioners incorporate more current administrative or higher-frequency sources (where compatible with the unit definition) when projecting beyond 2022. citeturn21search4turn21search7turn21search0

### Mitigation: use annual and quarterly “bridge” programs rather than pure extrapolation

A methodological best practice is to treat 2022 Economic Census as a benchmark level and then “bridge” forward using more current programs:

- The Census Bureau’s **Annual Integrated Economic Survey (AIES)** is explicitly positioned as an annual source of business revenue and related measures, and its first main releases (e.g., 2023 AIES main release) provide more current post‑2022 information at national and some subnational levels. citeturn21search2turn21search6  
- For services, the **Quarterly Services Survey** is described as a timely indicator source of revenue and expenses for selected service industries. citeturn21search16

These bridge data are not a perfect substitute for the full granularity of the Economic Census, but they reduce the error of carrying a 2022 baseline into 2025/2026, especially in inflationary or rapidly restructuring industries. citeturn21search2turn21search16turn22search12

## Productivity variance and the “long tail” problem inside a single detailed industry

### Public RPE is a mean; firms live in a distribution

Even if all definitional and disclosure issues were solved, there is a fundamental statistical critique: **RPE varies enormously across producers within the same narrowly defined industry**, so an average RPE (even at 6-digit NAICS) can be a weak predictor for any particular firm.

The literature on within-industry productivity dispersion documents very large gaps. A U.S. productivity-dispersion working paper (joint BLS/Census project context) describes results in which, using data from the 1977 Census of Manufactures, the establishment at the 90th percentile of the within‑industry labor productivity distribution was on average **about four times as productive** as the establishment at the 10th percentile within the same (four‑digit SIC) industry. citeturn25view0

While this statistic is for manufacturing establishments and a specific historical benchmark, it is methodologically useful for RPE because it illustrates a general fact: **a single “industry RPE” is often a poor estimator for the extremes of the distribution** (top-decile and bottom-decile firms/establishments), precisely the use case that many benchmarking exercises care about. citeturn25view0

### Why the long tail is especially relevant to revenue-based RPE

RPE often behaves like a revenue-based labor productivity measure. Revenue-based productivity can diverge from physical productivity because it embeds:

- price differences (market power, quality differentiation),  
- product mix, and  
- vertical integration and outsourcing choices (which change revenue and payroll-employee counts asymmetrically). citeturn25view0turn10view0

In practice, this makes the “RPE long tail” potentially **wider** than a pure quantity-based productivity dispersion: firms can have high revenue per employee because they charge higher prices or operate in higher-margin niches, not solely because they use labor more efficiently. citeturn25view0

## Practical methodological safeguards for RPE using Economic Census 2022 and SUSB

RPE can still be useful, but only under guardrails that reflect the critiques above.

At an establishment or small-area benchmarking level, it is methodologically safer to:

Use RPE for broad benchmarking, not firm inference. Treat county-by-6-digit RPE as a descriptive statistic for local industry structure, not a measurement of “firm productivity,” because enterprise boundaries, disclosure avoidance, and selection/suppression can dominate the signal. citeturn19view0turn27search5turn27search0

Prefer aggregation when disclosure controls are material. If the analytic goal tolerates it, aggregate one or more of: geography (county→state), industry (6-digit→3/4-digit), or time (multi-year smoothing using bridge series) to reduce the variance introduced by noise infusion and the bias from suppression rules. citeturn19view0turn27search0

Do not mix units unknowingly. If using SUSB receipts, remember that receipts are described as **estimated receipts** (and only present in 2/7 years), while employment is a March 12 snapshot; mixing establishment-based Economic Census receipts with enterprise-based SUSB employment (or vice versa) can create unit inconsistency unless you explicitly harmonize to the same unit definition. citeturn20search0turn27search5turn10view0

For nonprofit-heavy NAICS 61/62, define the numerator explicitly. If the goal is comparability to Form 990 “Total revenue,” prioritize Census measures that correspond to **tax-exempt total revenue** and recognize that Form 990 totals include multiple revenue categories (contributions, program service revenue, investment income, other). Avoid using “operating receipts” as a proxy for Form 990 total revenue without documenting the expected missing components (e.g., contributions and investment income). citeturn9view2turn9view3turn33view0turn29view0

Bridge forward from 2022 rather than extrapolating naïvely. For 2025/2026 estimation, use 2022 as a benchmark level and update using AIES/QSS and appropriate price indexes rather than assuming nominal receipts and March 2022 headcounts remain representative. citeturn21search2turn21search16turn22search12turn27search15