# Building a complete workforce profile from public and commercial data

**No single dataset answers all workforce composition questions, but a layered combination of 12+ federal sources—anchored by BLS OES staffing patterns, Census ACS microdata, and QCEW employment counts—can produce detailed estimates of occupational mix, firm size, and worker demographics for any industry in any U.S. metro area.** The methodology works by stacking national occupation-by-industry ratios onto local employment counts, then overlaying person-level demographic data from the ACS or CPS. Commercial platforms like Lightcast automate this exact pipeline for $5,000–$12,000+/year, but the underlying government data is entirely free. The key challenge is that no single source combines occupation, demographics, industry, firm size, and fine geography simultaneously—each dataset fills a specific gap. Below is a complete inventory of every major source, what it covers, and a step-by-step worked example for a private security firm in Atlanta.

---

## The federal data ecosystem and what each source actually provides

Understanding which dataset answers which question is the critical first step. The table below maps every major federal source against the four dimensions of workforce composition analysis.

| Source | Occupation detail | Industry depth | Finest geography | Firm size | Worker demographics | Revenue data | Cost |
|--------|------------------|---------------|-----------------|-----------|-------------------|-------------|------|
| **BLS OES/OEWS** | ~830 SOC codes | 4-digit NAICS (some 5/6) | MSA (cross-industry); national (by industry) | No | No | No | Free |
| **BLS Industry-Occupation Matrix** | ~830 SOC codes | ~300 industries | National only | No | No | No | Free |
| **BLS QCEW** | None | 6-digit NAICS | County | Establishment size (Q1 annual) | No | Aggregate wages only | Free |
| **BLS CPS** | ~500 occupations | Broad sectors | State; ~12 large MSAs | No | Full (race, sex, age, education) | Self-reported earnings | Free |
| **Census CBP** | None | 6-digit NAICS | ZIP code | Establishment size classes | No | No | Free |
| **Census ACS PUMS** | ~570 occupation codes | NAICS-based industry | PUMA (~100K pop.) | No | Full (race, sex, age, education) | Individual wages | Free |
| **Census SUSB** | None | 6-digit NAICS | County | Enterprise (firm) size | No | Receipts in Economic Census years | Free |
| **Census EEO Tabulations** | 237 occupation groups | Limited | MSA, county, places 50K+ | No | Race, sex, education | No | Free |
| **Census QWI (LEHD)** | None | 4-digit NAICS (state); 2-digit (county) | County | Firm age/size | Age, sex, race, education | Quarterly earnings | Free |
| **Economic Census** | None | 6-digit NAICS | ZIP code | Establishment and firm size | No | Revenue/receipts | Free |

Three sources deserve special attention because they form the backbone of any workforce composition analysis:

**BLS OES staffing patterns** are the only public source showing what percentage of an industry's workforce holds each occupation. Published annually (most recent: May 2024), they cover ~830 SOC occupations across ~410 industry classifications at national level. The critical limitation: industry-specific staffing patterns are **national only**. State- and MSA-level OES data show occupations across all industries combined, not within a specific industry. Data is available at bls.gov/oes/ via bulk downloads, interactive query tools, and the BLS Public Data API.

**ACS PUMS microdata** is the richest source for demographic-by-occupation analysis at sub-national levels. Each person-level record contains occupation (SOC-based), industry (NAICS-based), race, sex, age, education, wages, and geography (down to PUMAs of ~100,000 population). The 5-year file provides approximately a 5% population sample—large enough for reasonably reliable cross-tabulations of specific occupations within large metro areas. Access is free via Census downloads, the IPUMS platform (usa.ipums.org), or the Census Microdata API.

**QCEW** provides the most complete employment counts by detailed industry and geography, covering **95% of U.S. jobs** from unemployment insurance administrative records. It publishes 6-digit NAICS employment at the county level quarterly, though ~60% of detailed county-industry cells are suppressed for confidentiality.

---

## Answering the four core workforce composition questions

### 1. Occupational composition by industry

The primary source is the **BLS OES industry-specific data**, which directly provides the share of each occupation within a given NAICS code. For example, downloading the NAICS 561600 (Investigation and Security Services) file from bls.gov/oes/tables.htm reveals that **security guards (SOC 33-9032) constitute 73% of employment** in that industry nationally, with the remainder split among supervisors, administrative staff, managers, and sales workers.

The **BLS Industry-Occupation Matrix** from the Employment Projections program provides a parallel view with the added benefit of 10-year employment projections. The most recent cycle covers 2024–2034. It uses OES staffing patterns as its primary input but supplements with CPS data for self-employed workers. Both are national-only.

For more granular NAICS codes (e.g., 6-digit 623110 for skilled nursing facilities), OES may publish data at the 4- or 5-digit level. Where 6-digit data is unavailable, the closest parent NAICS code's staffing patterns serve as the best available proxy, with manual adjustment based on industry knowledge.

### 2. Staffing patterns by firm size and revenue-per-employee ratios

This is the hardest question to answer from public data alone, because **no federal source directly cross-tabulates occupation mix by firm size**. However, revenue-per-employee ratios can be estimated from multiple sources:

The **Census SUSB** is the key free source. It tabulates employment, firm count, and (in Economic Census years) receipts by enterprise size class and 6-digit NAICS. From the 2022 SUSB, you can calculate average employees per firm in each size bracket for a specific industry. The **Economic Census** (every 5 years, most recent 2022) provides revenue and employment at the ZIP code level by detailed NAICS, enabling direct revenue-per-employee calculations.

**IBISWorld** explicitly publishes revenue-per-employee as a standard metric in every industry report (~12,000 reports), along with wages as a percentage of revenue, employees per establishment, and cost structure breakdowns. It is widely available through university library subscriptions. For NAICS 561612, commercial benchmarking sources indicate approximately **$47,000–$48,000 revenue per employee**—consistent with an industry where labor costs represent roughly two-thirds of revenue and average pay is ~$30,000.

**County Business Patterns** provides establishment counts by employee-size class (1–4, 5–9, 10–19, 20–49, 50–99, 100–249, 250–499, 500–999, 1,000+) at the ZIP code level by 6-digit NAICS, useful for understanding the size distribution of firms in a geography even without revenue data.

### 3. Demographic composition by occupation and geography

Three sources provide this, each with different tradeoffs:

**ACS PUMS** (via IPUMS) is the most flexible option. By filtering microdata records to a specific occupation and set of PUMAs corresponding to a metro area, you can tabulate race, sex, age, and education distributions. The 5-year file (2019–2023 most recent) is recommended for sub-state analysis. The limitation is that PUMAs don't align perfectly with MSAs, counties, or ZIP codes—crosswalk files from the Census Bureau map PUMAs to other geographies with some approximation error.

**Census EEO Tabulations** provide pre-built tables of occupation × race × sex at the MSA, county, and place level for 237 occupation categories. These are the gold standard for affirmative action plan availability analysis. The major caveat: **the most recent edition reflects 2014–2018 data**, making it 7+ years old. A new edition based on ~2020–2024 ACS data has not yet been announced.

**BLS CPS** publishes annual tables (notably Table 11) showing employed persons by detailed occupation, sex, race, and Hispanic ethnicity—but only at the national level. State-level estimates are available for broad occupation groups, and only **~12 of the largest MSAs** have sufficient sample sizes for any sub-national breakdowns by occupation. CPS data is the most current (monthly releases) but least geographically granular.

**Census Quarterly Workforce Indicators (QWI)** offer a unique angle: they provide employment counts broken down simultaneously by industry, geography (county), and worker demographics (age, sex, race, education). QWI cannot break down by occupation, but it fills the gap of demographic-by-industry-by-county that no other source provides. Lightcast uses QWI as its primary source for demographic breakouts.

### 4. Geographic variation in workforce composition

Geographic variation in occupational mix can be detected by comparing QCEW or CBP industry employment distributions across counties or MSAs, then applying OES staffing patterns. If two metro areas have different industry mixes, their aggregate occupational compositions will differ.

Geographic variation in demographics within the same occupation is best captured through **ACS PUMS** or the **EEO Tabulations**. For example, security guards in New York City are **50.8% Black and 27.8% Latino** (ACS 2021–2023), while nationally the figures are ~32% Black and ~21% Hispanic—a dramatic geographic shift driven by local labor market demographics.

---

## Commercial platforms that automate the combination process

**Lightcast** (formerly EMSI + Burning Glass) is the dominant commercial platform. It integrates QCEW, CBP, OES, ACS, QWI, population estimates, IPEDS, and real-time job postings data into a unified database covering every U.S. county at 6-digit NAICS and 5-digit SOC detail. Its core methodology: start with QCEW employment counts, unsuppress gaps using CBP, add ACS self-employment data, apply regionalized OES staffing patterns (adjusted using metro-level OES occupation totals as constraints), and overlay QWI demographics. Pricing starts at **$5,000/year** for small-area community organizations and scales to $12,000+/year for larger regions, with enterprise/API pricing substantially higher.

**Chmura Economics (JobsEQ)** is a competing platform with similar methodology, adding real-time job postings from 40,000+ websites and geography down to the block/ZIP level. Custom pricing serves 650+ clients including workforce development boards.

**IBISWorld** provides industry-level benchmarks (revenue per employee, cost structure, market share) but not the occupation-by-geography granularity that Lightcast and JobsEQ offer. **Dun & Bradstreet** provides firm-level revenue and employee data for millions of individual businesses, enabling custom revenue-per-employee calculations by NAICS code and geography.

**IPUMS** (free, University of Minnesota) is not a commercial product but deserves mention as the most researcher-friendly way to access Census and CPS microdata, with harmonized variables, enhanced documentation, and a powerful extraction interface.

---

## How to combine datasets into a complete workforce profile

The standard methodology used by both federal agencies (e.g., HRSA's Health Workforce Simulation Model) and commercial platforms follows a four-layer approach:

**Layer 1 — Employment foundation.** Start with QCEW or CBP for total employment in the target industry and geography. QCEW provides county-level employment by 6-digit NAICS for 95% of all jobs. Where QCEW cells are suppressed, CBP establishment counts and size-class distributions can fill gaps through imputation.

**Layer 2 — Occupational decomposition.** Apply BLS OES national staffing patterns for the target NAICS code to the geographic employment total. This produces estimated occupation-level employment counts. For regionalization, Lightcast constrains these estimates so that the sum of all industry-specific occupation estimates in an MSA matches the OES cross-industry occupation totals published for that MSA.

**Layer 3 — Demographic overlay.** Using ACS PUMS (via IPUMS), filter person-level records to each target occupation within the PUMAs corresponding to the metro area. Calculate the demographic distribution (race, sex, age, education) for each occupation in that geography. Apply these proportions to the Layer 2 occupation counts. Cross-validate with QWI industry-by-demographic data where possible.

**Layer 4 — Firm-size calibration.** Use SUSB firm-size distributions and Economic Census revenue data to estimate the firm's likely employee count from its revenue, and to understand how firm size might shift the occupational mix (larger firms typically have proportionally more administrative and management staff).

The BLS publishes critical **crosswalk files** connecting the SOC codes used in OES to Census occupation codes used in ACS/CPS, enabling linkage between Layer 2 and Layer 3. These are available at bls.gov/emp/documentation/crosswalks.htm.

---

## Worked example: a $40M security firm in Atlanta

### Estimating headcount from revenue

For NAICS 561612 (Security Guards and Patrol Services), industry benchmarking data indicates a revenue-per-employee ratio of approximately **$47,900**. This aligns with the industry's labor-intensive structure where wages consume roughly 62–65% of revenue and average pay is ~$30,000. Dividing $40 million by $47,900 yields approximately **835 employees**. At the industry average of $3.8M revenue per location, this firm likely operates 10–11 locations or major contracts—consistent with a mid-to-large regional security company.

### Decomposing the workforce by occupation

BLS OES data for NAICS 561600 shows that security guards (SOC 33-9032) account for **73% of employment** in the broader Investigation and Security Services sector. Because NAICS 561612 is specifically guard and patrol services (excluding investigators, armored car drivers, and alarm technicians present in sibling NAICS codes), the guard share is adjusted upward to approximately **80%**. The remaining 20% distributes across first-line supervisors of protective service workers (~4%), general and operations managers (~3%), office and administrative support (~6%), business and financial operations specialists (~2%), sales representatives (~1%), and miscellaneous other roles (~4%). Applied to 835 employees, this produces approximately **668 security guards, 33 supervisors, 25 managers, 50 administrative staff, 17 finance/HR professionals, 8 sales staff, and 34 others**.

### Overlaying demographic data for Atlanta

National CPS and ACS data show security guards are approximately **75% male and 25% female**, with a racial composition of roughly 44% White, 32% Black, 21% Hispanic, and 5% Asian nationally. However, demographics shift substantially by geography. The Atlanta-Sandy Springs-Roswell MSA has a population that is approximately 34% Black—well above the national 13%. Since Black Americans are already overrepresented in security guard occupations nationally (32% of guards vs. 13% of the total workforce), the Atlanta effect amplifies this further. 

Adjusting national patterns for Atlanta's labor market demographics yields an estimated security guard workforce that is roughly **48–52% Black, 25–30% White, 10–12% Hispanic, and 3–4% Asian** in the Atlanta MSA. The EEO Tabulation 2014–2018 for the Atlanta CBSA would provide the most precise historical figures for this occupation-geography combination, available for download from Census at census.gov/acs/www/data/eeo-data/eeo-tables-2018/. For a more current estimate, ACS 5-year PUMS data (2019–2023) filtered to protective service occupations within Atlanta-area PUMAs would produce updated demographic distributions.

### The complete estimated profile

For this **$40M Atlanta security guard firm**, the composite workforce estimate is:

| Role | Headcount | % Female | % Black | % White | % Hispanic |
|------|-----------|----------|---------|---------|------------|
| Security guards | 668 | 25% | 50% | 28% | 11% |
| Protective service supervisors | 33 | 27% | 45% | 35% | 10% |
| Management | 25 | 35% | 25% | 55% | 10% |
| Administrative support | 50 | 70% | 40% | 40% | 12% |
| Business/finance/HR | 17 | 55% | 30% | 50% | 10% |
| Sales | 8 | 30% | 25% | 55% | 12% |
| Other | 34 | 30% | 35% | 40% | 12% |
| **Total firm** | **835** | **~29%** | **~47%** | **~31%** | **~11%** |

The firmwide demographic profile—approximately 47% Black, 31% White, 11% Hispanic, 71% male—reflects both the national occupational demographics of security work and Atlanta's specific labor market composition.

### Confidence levels and data gaps

The revenue-to-headcount estimate carries the most uncertainty (±25–30%), as individual firms vary widely in service mix, pricing, and subcontracting practices. The occupational mix is moderately reliable, based on national BLS OES data adjusted for the specific NAICS subsector. The demographic estimates are the least precise at the metro level because the best geographic-specific source (EEO Tabulations) is 7+ years old, and ACS PUMS estimates for a single detailed occupation in a single metro area have meaningful margins of error due to sample size. Using 5-year ACS PUMS data and pooling related protective-service occupations would improve reliability.

---

## A practical data access roadmap

For anyone building workforce profiles from scratch, the recommended sequence is:

1. **Start at bls.gov/oes/tables.htm** — download industry-specific OES data for the target NAICS code to get national staffing patterns (free Excel downloads)
2. **Pull QCEW data from bls.gov/cew/opendata.htm** — get employment counts for the target NAICS and geography (free CSV via REST API)
3. **Extract ACS PUMS via usa.ipums.org** — select occupation, industry, demographic variables for the target PUMAs (free with registration)
4. **Download EEO Tabulations from data.census.gov** — get pre-tabulated occupation × race × sex by MSA (free, but 2014–2018 vintage)
5. **Check Census SUSB at census.gov/programs-surveys/susb.html** — get firm-size distributions and receipts data for the target industry (free)
6. **Access QWI via qwiexplorer.ces.census.gov** — get industry × geography × demographic employment flows (free interactive tool and API)
7. **If budget allows, subscribe to Lightcast** — get all of the above pre-integrated, unsuppressed, regionalized, and updated with real-time job postings data ($5,000–$12,000+/year)

Every federal source listed above is free, accessible without special authorization, and available through either downloadable files, interactive web tools, or APIs. The Census Bureau requires a free API key (census.gov/developers/) for programmatic access. The BLS offers a free API with rate limits that can be increased by registering at data.bls.gov/registrationEngine/.

## Conclusion

The U.S. statistical system provides remarkably granular workforce data—but distributed across a dozen siloed sources that were never designed to be combined. The fundamental tradeoff is between **occupational specificity** (OES provides 830 occupations by industry, but only nationally and without demographics), **demographic richness** (ACS PUMS provides individual-level demographics by occupation and geography, but without firm-level context), and **geographic precision** (QCEW and CBP reach the county and ZIP level, but carry no occupational or demographic information). The worked example above demonstrates that by layering these sources—OES for occupational ratios, QCEW/SUSB for employment scaling, ACS/CPS for demographics—a reasonably detailed workforce profile can be constructed for any industry-geography combination, with the caveat that each layer introduces its own margin of error. Commercial platforms like Lightcast exist precisely because this assembly process is laborious, and their primary value is unsuppression, regionalization, and integration rather than proprietary data collection. For organizations building workforce profiles regularly, the time savings justify the subscription cost. For one-off analyses, the free federal data is entirely sufficient given the methodology described here.