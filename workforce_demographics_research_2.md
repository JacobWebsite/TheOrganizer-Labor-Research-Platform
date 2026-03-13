# Firm-Level Workforce Demographic Estimation: Research Landscape & Methodology Review

> **Research question:** How have academics, government agencies, and commercial providers approached estimating firm-level workforce demographics (race, ethnicity, gender, age, education) using publicly available federal data — specifically ACS, LODES, and occupation data?

---

## How to Think About This Problem

**The core challenge:** No public government dataset tells you directly what a specific employer's workforce looks like demographically. Government data is almost always aggregated — it tells you what workers in a whole industry, county, or occupation look like, but not at the level of a single employer.

The blending approach (ACS industry signal + LODES geography signal) is essentially saying: "The workers at this nursing home in rural Ohio are probably people who (a) look like workers in the nursing home industry generally, AND (b) look like workers who live and work in that specific county." The research below indicates how others have approached this same logic, and where this approach has both support and known weaknesses.

---

## Question 1: Has Academic Research Done This? What Methods Did They Use?

**Short answer:** Yes, but almost entirely at the "small area" level (zip code or census tract), not at the individual employer level. Almost no published research attempts single-employer-level demographic estimation from public data alone. The two dominant academic methods are **IPF (Iterative Proportional Fitting)** and **spatial microsimulation** — both of which are more sophisticated versions of a weighted blend approach.

### What Is IPF and Why Does It Matter?

Think of IPF like a spreadsheet balancing act. Imagine a table where the rows are demographic groups (e.g., Black, White, Hispanic) and the columns are geographic areas (e.g., counties). You know the row totals (from ACS: "X% of healthcare workers nationally are Black") and the column totals (from LODES: "Y% of workers in this county are Black"). IPF repeatedly adjusts the cells back and forth until the rows and columns all add up correctly — finding the most mathematically consistent estimate given all constraints.

IPF is a technique for adjusting a distribution reported in one dataset by totals reported in others. It is used to revise tables of data where the information is incomplete, inaccurate, outdated, or a sample. It has been widely used in population geography and demography for exactly this type of multi-source blending problem.

Population synthesis using IPF has been proposed as a cheaper alternative for forecasting population characteristics when collecting detailed data for the whole population is too expensive or infeasible.

**Why this matters for the 60/40 blend:** A simple weighted average is a fixed assumption. IPF instead takes ACS industry percentages AND LODES county percentages and finds the *internally consistent* set of estimates that satisfies both constraints simultaneously. It's theoretically more defensible than a fixed weight.

### Key Academic Papers

- **Lomax et al. (2013/2015)** — "Estimating Population Attribute Values in a Table: 'Get Me Started in' Iterative Proportional Fitting," *The Professional Geographer*. An accessible how-to guide with R code for IPF applied to demographic estimation problems. [See link section below]

- **Loxton et al. (2015)** — "Evaluating the Performance of Iterative Proportional Fitting for Spatial Microsimulation: New Tests for an Established Technique," *Journal of Artificial Societies and Social Simulation* 18(2). [See link section below]

- **Census Bureau Working Paper (2025)** — "The Composition of Firm Workforces from 2006–2022." This is the closest published government research to the approach described here. Key finding: the labor market is systematically segmented by demographic composition of workers, and across every workforce characteristic considered, employers are more homogeneous than would be expected if workers and employers matched randomly. **This validates the ACS industry signal as the dominant weight** — industry predicts workforce demographics better than chance. [See link section below]

---

## Question 2: How Do Commercial Providers Do This?

Three major companies are doing versions of this problem, and two have published their methodology.

### Lightcast (formerly EMSI/Burning Glass) — Closest Methodological Match

Lightcast's published knowledge base describes an approach very similar to the ACS + LODES blend:

- Uses **Quarterly Workforce Indicators (QWI)** data to create demographic percentage breakouts by age/sex or race/ethnicity for 4-digit NAICS industries
- QWI breakouts are partially suppressed (small cell sizes get hidden), so Lightcast uses **ACS data to fill in the suppressed values**
- The resulting percentages are applied to Lightcast's own industry job counts (derived from QCEW)

**Key difference from the approach described here:** Their industry-side signal is QWI-first, ACS-supplement rather than ACS-only. QWI breaks demographics down by 4-digit NAICS at the county level, meaning it *combines* both industry AND geography signals in one dataset. This is more granular but has significant suppression issues, which is why ACS is needed as a backup.

Lightcast also uses LODES OD data specifically for their "Occupation by Residence" data product — using the three LODES OD file types together to provide information on commuting patterns by 2-digit industry between census tracts.

**Citations:** Lightcast Knowledge Base [see links below]

### Revelio Labs — Fundamentally Different Approach

Revelio scrapes hundreds of millions of individual professional profiles from LinkedIn and similar platforms, then applies statistical weighting to correct for platform bias:

- Uses sampling weights to adjust for occupation and location bias (e.g., if an engineer in the US has a 90% chance of having an online profile, every engineer is considered to represent 1.1 people)
- For race and ethnicity specifically: uses **Bayesian name analysis** — predictive algorithms that compare names and locations with Social Security, Census, and voter data to predict likely race/ethnicity

**Critical limitation for labor organizing research:** Revelio's data skews heavily toward white-collar, LinkedIn-visible workers. Blue-collar, service, and manufacturing workers are dramatically underrepresented — the company acknowledges this explicitly. For organizing-target research where blue-collar industries are often most important, this is a fundamental bias.

**Citations:** Revelio Labs Data Dictionary and academic paper citing their methodology [see links below]

---

## Question 3: Are There Government Efforts to Produce Firm-Level Demographic Estimates?

Yes — and the most important one just launched in April 2025. It is directly relevant as a validation benchmark.

### Business Dynamics Statistics of Human Capital (BDS-HC) — U.S. Census Bureau

Released April 2025. The Census Bureau uses **confidential IRS W-2 records matched to employer IDs** to create summary measures of the demographic characteristics of workers at each firm. This is the gold standard — they literally know which humans worked at which employer.

**What it covers:**
- Nearly all non-farm employer businesses in the US, 2006–2022
- Six demographic characteristics: age, sex, race, ethnicity, nativity, and education
- Cross-tabulated with industry sector, state, firm age, and firm size

**Why it doesn't solve the problem directly:** These are aggregated tables, not employer-level records. You cannot look up "what does Walmart's workforce look like" — you can look up "what do large retail firms' workforces look like." But it is an excellent validation tool. You can compare your estimates for broad industry-state-size combinations against BDS-HC aggregates to check whether your methodology is directionally correct.

**Citation:** U.S. Census Bureau, Experimental BDS [see link below]

### EEO Tabulation — Census Bureau for EEOC

A special ACS tabulation created for the Equal Employment Opportunity Commission, DOJ, and Department of Labor. Covers 488 detailed occupation categories × 15 race/ethnicity combinations × 6,500 geographic entities, including worksite and commuting flows. This is more granular than standard ACS tables and is the government benchmark used for affirmative action and discrimination enforcement.

**Citation:** U.S. Census Bureau, "Measuring Workforce Diversity" [see link below]

---

## Question 4: Is the 60/40 Weight Reasonable? What Does the Literature Say?

**Honest assessment:** No published paper has validated a 60/40 industry-geography split specifically. The literature strongly suggests industry is the more powerful signal for most demographics — supporting ACS as the larger weight. But a fixed weight is a simplification; the principled answer is that the optimal weight varies by situation.

### What the Evidence Suggests

**Industry signal is doing most of the work for occupation-driven demographics.** Things like gender (nursing skews female), race in certain trades, age in manufacturing — these are strongly predicted by industry. The BDS-HC working paper confirms that industry is a strong demographic predictor.

**Geography signal matters more in contexts with extreme local demographic variation.** A warehouse in a county that is 70% Hispanic will likely have a more Hispanic workforce than the national average for warehousing. But if the county demographics are close to national averages, the LODES signal adds less information.

### More Sophisticated Alternatives to a Fixed Weight

| Method | What It Does | Complexity |
|---|---|---|
| **Fixed weight (current)** | Always 60/40, regardless of context | Low |
| **Variable weight by industry** | Increase LODES weight for agriculture/construction; increase ACS weight for professional services | Medium |
| **IPF** | Finds the mathematically consistent estimate satisfying both constraints simultaneously | Medium |
| **Hierarchical Bayesian** | National industry average as prior; update based on local geography; update strength scales with how different the local area is from national | High |

**A practical improvement without replacing the whole system:** For industries where local demographics dominate (agriculture, construction, food processing), increase the LODES weight. For industries where occupational structure dominates (healthcare, finance, professional services), increase the ACS weight. This creates a variable weight by industry type.

---

## Question 5: Known Limitations of LODES WAC for Demographic Estimation

This is critical to understand before relying on LODES WAC counts for demographic signals.

### Problem 1: The "Fuzz Factor" — Intentional Noise Injection

In the QWI, LODES WAC, and J2J files, a multiplicative "fuzz factor" is generated for each employer and each establishment. This factor distorts the true estimates by a confidential percentage range. The fuzz factor is permanent — the same factor is used for the same employer across all years and data releases.

**What this means in practice:** Every number in the WAC file has been secretly multiplied by some unknown value (e.g., between 0.85 and 1.15 — the exact range is classified). You cannot detect or correct for this. At the county level, noise largely cancels out across many employers. At finer geographies (block or tract level for a single employer), noise can be a meaningful share of the true number.

**The OD and RAC files use a more extensive anonymization process than WAC.**

### Problem 2: Worksite Location Errors

The most commonly reported limitation: state workforce agencies ask employers for the physical location of work, but frequently receive the address of the payroll/HR office instead. For multi-establishment companies, this can place all workers at corporate headquarters rather than their actual worksites.

**Worst-affected industries:** Construction (NAICS 23), Administrative/Support Services (NAICS 56), retail chains, large healthcare systems. This directly corrupts the county-level geographic signal for employers in these industries.

### Problem 3: LODES OD Has Very Limited Demographic Detail

The OD file only contains three variable categories: age (three bands), earnings (three bands), and broad industry (goods/services/trade). It contains **no direct information on race, gender, ethnicity, or education** of commuters. To estimate those demographics from OD flows, you must look up the residential tract ACS demographics — which is exactly what the planned labor shed layer does. This introduces an ecological fallacy risk (assuming everyone in a tract has average tract demographics).

### Problem 4: Vintage Lag

The most recently available LODES data typically lags 2–3 years behind the current date. ACS 5-year estimates also have a mid-year about 2.5 years in the past. Estimates inherently reflect the labor market as it was 2–3 years ago.

### Summary of LODES WAC Limitations

| Issue | Impact Level | Mitigation |
|---|---|---|
| Fuzz factor noise | Low at county level; higher at finer geographies | Aggregate to county or higher |
| Worksite location errors | High for NAICS 23, 56, retail chains | Flag these industries; lean more on ACS |
| OD demographic sparseness | Medium | Must infer from residential tract ACS |
| Vintage lag (2–3 years) | Medium | Document uncertainty; note data year |

---

## Question 6: Has Anyone Used LODES OD to Trace Commuter Demographics?

This is a relatively underdeveloped area. No published paper has specifically said "I used LODES OD + residential tract ACS to estimate the demographic composition of a specific employer's labor shed." **This would be a genuinely novel methodological contribution.** The component pieces are well-grounded in prior work.

### Most Relevant Published Work

**Credit & Arnao (2023)** describe an open-source method combining LODES OD and ACS at the census tract scale to derive linked origin-destination commuting flows by transportation mode. The methodology weights LODES flows by ACS commute characteristics — the same logical chain as weighting LODES OD flows by ACS residential tract demographics.

**The DSPG Fairfax County study (2020)** used LODES OD to map origin tracts for commuters into Fairfax County, then overlaid ACS tract-level data to characterize the demographic composition of those commuting origins. This is essentially the labor shed methodology described above, applied at a county rather than employer level.

**Lightcast** uses the three LODES OD files together to form their "Occupation by Residence" data product — though they apply it to occupation composition, not demographic composition.

### Key Limitation to Document

The OD file's limited demographic variables mean race/ethnicity is inferred indirectly through residential tract demographics. This assumes commuters look demographically like their residential neighborhood average — a reasonable first approximation, but not always accurate. Workers in high-paying jobs may commute from demographically different neighborhoods than their workplace community. Document this assumption explicitly as a known limitation.

---

## Summary: How This Methodology Stacks Up

### What the Current Approach Gets Right

- Using ACS industry signal as the dominant weight is supported by the evidence (industry is the strongest demographic predictor)
- County-level LODES aggregation largely cancels out WAC noise
- The planned OD labor shed layer is methodologically novel and valid
- The planned BLS OES occupation layer is the most significant improvement possible — separating RN demographics from CNA demographics moves estimates from "industry average" to something more granular

### The Biggest Gaps Compared to State-of-the-Art

- A fixed 60/40 weight is less defensible than IPF or a variable weight by industry type
- LODES county-level demographics as a "who works in this county" signal doesn't control for industry within the county — a tech company and a meatpacking plant in the same county get the same LODES signal, which is misleading
- The OD labor shed idea is sound, but the OD file's limited demographic variables mean race/ethnicity is inferred indirectly through residential tract ACS (ecological fallacy risk)
- BDS-HC (April 2025) is now available as a validation benchmark that should be compared against

### Most Actionable Next Step

Implement IPF as an alternative to the fixed 60/40 blend. The R package `ipfn` or Python package `ipfn` (via pip) makes this straightforward. You provide ACS industry percentages as row constraints and LODES county percentages as column constraints, and IPF finds the internally consistent cell estimates. This is more mathematically grounded than fixed weights and is the dominant academic standard for this exact problem type.

---

## Full Citations & Links

### Academic Papers

| Paper | Link |
|---|---|
| Lomax et al. (2015) — "Get Me Started in Iterative Proportional Fitting" | https://www.tandfonline.com/doi/full/10.1080/00330124.2015.1099449 |
| Loxton et al. (2015) — "Evaluating IPF for Spatial Microsimulation" | https://www.jasss.org/18/2/21.html |
| Chow et al. (2021) / Census BDS-HC Working Paper (2025) — "Composition of Firm Workforces from 2006–2022" | https://www2.census.gov/library/working-papers/2025/adrm/ces/CES-WP-25-20.pdf |
| Graham, Kutzbach & McKenzie (2014) — "Design Comparison of LODES and ACS Commuting Data Products" | https://www.census.gov/library/working-papers/2014/adrm/ces-wp-14-38.html |
| Green, Kutzbach & Vilhuber (2017) — "Two Perspectives on Commuting: LODES vs ACS" | https://www2.census.gov/ces/wp/2017/CES-WP-17-34.pdf |
| Andrew D. Foote (2025) — "LODES Design and Methodology Report: Version 7" | https://www2.census.gov/library/working-papers/2025/adrm/ces/CES-WP-25-52.pdf |
| Credit & Arnao (2023) — "Deriving Small Area Commuting Trip Estimates from LODES and ACS" | https://journals.sagepub.com/doi/10.1177/23998083221129614 |
| Fienberg (1970) / Wikipedia summary — IPF mathematical foundations | https://en.wikipedia.org/wiki/Iterative_proportional_fitting |
| Peutz (2023) — "Reducing Sampling Bias Through IPF" (accessible explainer) | https://stevenpeutz.com/ipf-survey-weights/ |
| ScienceDirect — "Population Synthesis Using IPF: A Review" | https://www.sciencedirect.com/science/article/pii/S2352146516306925 |
| Academic paper citing Revelio Labs race/ethnicity methodology (Liu 2016; Bursztyn et al.) | https://afajof.org/management/viewp.php?n=63924 |

### Government Data Products & Documentation

| Source | Link |
|---|---|
| U.S. Census Bureau — BDS Human Capital (BDS-HC), released April 2025 | https://www.census.gov/data/experimental-data-products/bds-human-capital.html |
| U.S. Census Bureau — Experimental BDS overview | https://www.census.gov/programs-surveys/ces/data/public-use-data/experimental-bds.html |
| U.S. Census Bureau — LEHD/LODES data hub | https://lehd.ces.census.gov/data/ |
| U.S. Census Bureau — "Measuring Workforce Diversity: The EEO Tabulation" | https://www.census.gov/newsroom/blogs/random-samplings/2012/11/measuring-workforce-diversity.html |
| LODES Technical Documentation v7.2 (file structure, variable definitions) | https://lehd.ces.census.gov/data/lodes/LODES7/LODESTechDoc7.2.pdf |
| Open Journal of Region — "The US Census LEHD Datasets" (LODES overview for researchers) | https://openjournals.wu.ac.at/region/paper_251/251.html |
| Urban Institute — Tract-Level LODES Files (pre-aggregated, analysis-ready) | https://datacatalog.urban.org/dataset/longitudinal-employer-household-dynamics-origin-destination-employment-statistics-lodes |
| Urban Institute — LODES Description PDF | https://datacatalog.urban.org/sites/default/files/data-dictionary-files/Urban-LODES%20Description.pdf |
| Urban Institute — Medium post explaining LODES data | https://urban-institute.medium.com/open-accessible-data-on-jobs-and-workers-tract-level-lodes-data-945fcac9e280 |
| BLS — Guidance for Labor Force Statistics Data Users | https://www.census.gov/topics/employment/labor-force/guidance.html |

### Commercial Provider Documentation

| Source | Link |
|---|---|
| Lightcast — Industry and Occupation Diversity Methodology | https://kb.lightcast.io/en/articles/6957722-industry-and-occupation-diversity-methodology |
| Lightcast — Population Demographics Methodology | https://kb.lightcast.io/en/articles/6957652-population-demographics-methodology |
| Lightcast — LODES OD Data Usage | https://kb.lightcast.io/en/articles/7934021-lehd-origin-destination-employment-statistics-lodes |
| Revelio Labs — Data Dictionary & Methodology | https://www.data-dictionary.reveliolabs.com/methodology.html |
| Revelio Labs — WRDS/Wharton data page | https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/revelio-labs/ |

### Implementation Tools (IPF)

| Tool | Link |
|---|---|
| Python: `ipfn` package | https://datascience.oneoffcoder.com/ipf.html |
| R: `surveysd` package IPF vignette | https://cran.r-project.org/web/packages/surveysd/vignettes/ipf.html |
| R: `lehdr` package for downloading LODES data | https://cran.r-project.org/web/packages/lehdr/vignettes/getting_started.html |

### Community Discussion & Practitioner Notes

| Source | Link |
|---|---|
| TMIP listserv — LODES WAC known limitations (worksite location errors, fuzz factor) | https://groups.google.com/d/msgid/TRBADD30/001101d6392c$5d0cc2f0$172648d0$@gmail.com |
| DSPG Fairfax County — Applied OD + ACS commuter origin methodology example | https://dspg-young-scholars-program.github.io/dspg20fairfax/methods/ |

---

*Research compiled March 2026. LODES data current through 2023. BDS-HC released April 2025.*
