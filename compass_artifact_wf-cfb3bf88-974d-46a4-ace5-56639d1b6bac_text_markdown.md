# Estimating workforce size from the outside: a complete methodological guide

**The most accurate external workforce estimates come not from any single data source but from layered Bayesian approaches that combine government administrative records, SEC filings, professional profiles, and job postings — achieving ±5–15% accuracy for total headcount at well-documented companies.** For a labor relations research platform, NLRB bargaining unit sizes provide uniquely valuable ground-truth calibration points that most commercial workforce intelligence providers lack. The open-source ecosystem for this work is maturing but fragmented: strong tools exist for entity resolution, government data access, and job posting analysis, yet no single project ties them together into an end-to-end workforce estimation pipeline.

---

## Traditional methods range from near-census accuracy to rough approximation

Six established methods form the backbone of external workforce estimation, spanning an accuracy spectrum from **±1–3%** (QCEW administrative records) to **±25–50%** (revenue-per-employee ratios).

**QCEW (Quarterly Census of Employment and Wages)** is the most comprehensive U.S. employment data source, covering **95%+ of wage and salary civilian employment** through unemployment insurance tax filings from roughly 11.5 million employer accounts. It provides monthly employment, quarterly wages, and establishment counts at the county × 6-digit NAICS level. Because this data derives from administrative records rather than surveys, it carries virtually no sampling error. The critical limitation is **~60% suppression** at detailed county-industry levels to protect employer confidentiality, plus a 5–6 month publication lag. When a target company dominates a specific county-industry cell with few other employers, the QCEW figure closely approximates that company's actual employment.

**Census County Business Patterns (CBP)** and **Statistics of U.S. Businesses (SUSB)** complement QCEW with establishment-level granularity. CBP publishes establishment counts by employment size class (1–4, 5–9, 10–19, 20–49, 50–99, 100–249, 250–499, 500–999, 1,000+) at the county × 6-digit NAICS level. Since 2007, Census applies **balanced multiplicative noise infusion** rather than cell suppression, meaning published employment and payroll values are perturbed by ±2–10% for large cells. SUSB adds enterprise-level data, distinguishing firm size from establishment size. Together, these datasets constrain an establishment's employment to a known range — narrower when few establishments share that industry-geography cell.

**BLS Staffing Patterns (OEWS Industry-Occupation Matrix)** is the only systematic source for estimating occupational composition without internal data. The Occupational Employment and Wage Statistics program surveys ~1.1 million establishments over a three-year rolling cycle, producing cross-tabulations of **~830 SOC occupations across ~410 NAICS industry aggregations**. Once you know a company's total headcount and primary NAICS code, multiplying by each occupation's staffing share yields estimated counts — for example, if NAICS 622 (hospitals) shows 26% registered nurses, a 2,000-employee hospital has an estimated 520 RNs. Accuracy is **±10–20%** for dominant occupations but widens considerably for rare ones or companies whose operations diverge from industry norms.

**Payroll triangulation** reverses the compensation equation: divide total reported compensation expense by average compensation per employee to derive headcount. For public companies, SEC filings contain compensation line items, and Dodd-Frank's **CEO pay ratio** disclosure directly reveals median employee compensation. A company reporting $500M in total compensation expense with $80K average total comp per employee implies ~6,250 employees. Accuracy runs **±10–25%** with clean data but degrades when stock-based compensation, international workforces, or contractor costs muddy the denominator.

**Revenue-per-employee ratios** offer the simplest estimation: divide company revenue by industry-average RPE. Industry benchmarks vary enormously — from ~$150K in retail to $400K+ in software to over $1M in energy and finance. **NVIDIA's RPE exceeds $4.4M/employee** while labor-intensive service companies may run below $100K. This method achieves only **±25–50%** accuracy because within-industry variation is massive, though it narrows to ±15–25% within tightly defined sub-industries.

**Operational coverage math** applies industry-specific ratios: hospitals average **5.0–6.0 FTEs per occupied bed**, schools run ~1 employee per 8–10 students, and modern offices average 150–175 square feet per employee. For facility-based industries where operational metrics are publicly reported, this yields **±10–30%** accuracy — strongest for hospitals (bed counts are strong predictors) and schools (enrollment data is public).

---

## Emerging methods add real-time signals but introduce new biases

Advanced approaches bring timeliness and coverage advantages at the cost of systematic biases that require careful correction.

**LinkedIn profile counting** leverages over 1 billion global profiles but suffers from severe industry-dependent penetration gaps. Tech and professional services workers maintain profiles at **60–90% rates**, while manufacturing, retail, and agricultural workers may show just **2–5%** penetration. People Data Labs found ~15% of profiles at well-known companies are "relatively incomplete and generally irrelevant," while entity-matching errors can be extreme — Railway, a cloud company with 11–50 actual employees, showed ~4,000 on LinkedIn due to railroad workers being incorrectly mapped. Raw LinkedIn accuracy runs ±15–30% for tech companies but can undercount blue-collar workforces by 50–95%.

**Job posting analysis** provides the strongest leading indicator of workforce changes. A 2020 *Management Science* study confirmed that increases in online job postings significantly predict future headcount gains, revenue growth, and earnings, typically 1–3 quarters ahead. Revelio Labs' COSMOS dataset processes **2B+ postings from 5.25M companies** in 100+ languages, weighting each posting by expected hires — a critical refinement since only ~0.5 people are hired per U.S. posting as of 2023. NLP extraction maps job titles to standardized taxonomies, revealing occupational composition with ±5–10% accuracy for large companies with many postings. The primary contamination is "ghost postings" — **~73%** of job seekers report encountering them.

**SEC filing analysis** yields the highest-accuracy headcount data for public companies. The November 2020 SEC human capital disclosure rule expanded Item 101(c) to require descriptions of "human capital resources, including the number of persons employed." Gibson Dunn surveys of S&P 100 companies show nearly universal total headcount disclosure, though only **14–16% report full-time/part-time splits**, ~37% disclose unionization rates, and just 19–20% provide quantitative turnover data. These are audited, legally mandated numbers — accuracy is **±1–5%** for total headcount, making 10-K filings the gold standard anchor for public company estimation.

**Machine learning models** trained on observable company features can predict headcount from revenue, web traffic, job postings, industry, and funding history. A 2024 ScienceDirect study using 1.3M+ firms found XGBoost achieved **ROC AUC of 0.87** for classifying employee-high-growth firms, with growth opportunity as the most predictive feature. However, no production-ready open-source headcount prediction model exists — this remains largely the domain of proprietary providers.

**Satellite imagery** works for physical-footprint businesses: computer vision counting vehicles in parking lots correlates at **r=0.74** with retailer production figures per Feng & Fay (2022) in the *Journal of Retailing*. Orbital Insight pioneered this approach across 60+ retail chains. The method is objective and ungameable but limited to brick-and-mortar operations, expensive for commercial imagery, and increasingly irrelevant as remote work grows.

**Glassdoor/Indeed review volume** correlates with company size directionally but lacks calibration for absolute headcount estimation. Tech companies generate roughly 1 review per 5–15 employees while non-tech companies run 1 per 20–50. No authoritative calibration study exists. Review volume is better as a relative signal or sentiment indicator than a headcount proxy — Green, Huang & Wen (2019, *Journal of Financial Economics*) showed employer rating changes predict stock returns, but this measures satisfaction rather than size.

---

## The alternative data industry reveals the state of the art

Commercial workforce intelligence providers demonstrate what's achievable with multi-source fusion. **Revelio Labs** (founded 2018 by NYU labor economist Ben Zweig) applies the most methodologically rigorous approach: they collect hundreds of millions of professional profiles, then apply **occupation × location sampling weights** comparing observed profile rates against BLS occupational employment data. If a U.S. engineer has a 90% profile probability, each observed profile represents 1.1 workers; if a German nurse has 25% probability, each represents 4. They also apply **nowcasting models** to correct for lag in profile updates, predicting currently unreported changes from historical patterns.

**People Data Labs** maintains 3B+ person profiles and 60M+ company records with strict quality filtering and proprietary entity resolution that separates parent companies from subsidiaries. **Lightcast** (formerly Burning Glass + Emsi) processes 1B+ job postings across 30+ countries. **Diffbot** takes a different approach, using AI-powered web crawling across 1.2B+ websites to build a knowledge graph of 10B+ entities. All these providers achieve **±15–30%** accuracy for large/medium companies in well-represented industries, with directional trends more reliable than absolute numbers.

---

## Open source tools exist for every component but no integrated solution

The open-source landscape provides strong building blocks across seven categories, though no project assembles them into an end-to-end workforce estimation pipeline.

**Entity resolution is the most mature category.** Splink (`moj-analytical-services/splink`, ~4,400+ stars) implements the Fellegi-Sunter probabilistic model with PostgreSQL backend support, linking a million records on a laptop in ~1 minute. It's used by the Australian Bureau of Statistics, UK MOJ, and NHS. Dedupe (`dedupeio/dedupe`, ~4,200+ stars) uses active learning to train company-specific matching rules. Entity-embed (`vintasoftware/entity-embed`) applies PyTorch contrastive learning for embedding-based blocking. For your platform, **Splink is the highest-priority integration** — it directly supports matching company names across OSHA, SEC EDGAR, NLRB, and DOL/OLMS datasets with your existing PostgreSQL database.

**Job posting scraping centers on JobSpy** (`speedyapply/JobSpy`, ~10,000+ stars), which scrapes LinkedIn, Indeed, Glassdoor, Google, and ZipRecruiter into structured Pandas DataFrames with fields including company size. It's actively maintained and directly outputs the company_employees_label field. The Workforce Data Initiative's **skills-ml** library (`workforce-data-initiative/skills-ml`, ~171 stars) performs SOC occupation classification, skill extraction, and job title normalization using O*NET and ESCO ontologies — directly mapping to your BLS industry-occupation matrix.

**Company embedding research has produced several implementations.** ING Bank's Industry2Vec (`ing-bank/industry2vec`) generates vector representations of NAICS codes using Siamese neural networks, capturing semantic similarity between industries that hierarchical codes miss — "Automobile Dealers" clusters near "Automotive Repair and Maintenance" despite distant NAICS codes. Eddiepease's Company2Vec (`eddiepease/company2vec`) generates company embeddings from web-scraped text using GloVe. Itomoki430's Company2Vec creates embeddings from SEC annual report text for fine-grained industry characterization. Since your platform uses NAICS codes extensively, **Industry2Vec embeddings could replace one-hot encoding** in any ML models, enabling similarity-aware industry matching.

**BLS and Census data access is well-served in both Python and R.** Key tools:

| Tool | Language | Install | Key capability | Status |
|------|----------|---------|---------------|--------|
| `ipumspy` | Python | `pip install ipumspy` | IPUMS microdata (CPS, ACS PUMS) | Active, official |
| `census` (DataMade) | Python | `pip install census` | Census API wrapper (ACS, Decennial) | Active |
| `censusdis` | Python | `pip install censusdis` | All Census datasets + PUMS + mapping | Active |
| `edgartools` | Python | `pip install edgartools` | SEC EDGAR parsing, XBRL extraction | Very active |
| `tidycensus` | R | `install.packages("tidycensus")` | ACS, PUMS, Census with sf geometry | Active |
| `censusapi` | R | `install.packages("censusapi")` | All Census APIs including CBP, QWI | Active |
| `blscrapeR` | R | `install.packages("blscrapeR")` | BLS API with QCEW support, 75K+ series | Active |
| `lehdr` | R | `install.packages("lehdr")` | LODES employment data by census block | Active |

For the BLS API directly, the recommended Python approach is using `requests` against the v2 endpoint (`api.bls.gov/publicAPI/v2/timeseries/data/`) rather than thin wrappers, as existing Python BLS packages are less actively maintained than R equivalents.

---

## Government data infrastructure provides the estimation foundation

The federal statistical system offers several underutilized datasets for workforce estimation beyond the well-known BLS and Census products.

**LEHD/LODES (Longitudinal Employer-Household Dynamics)** from Census provides block-level employment counts by 2-digit NAICS, covering 2002–2022. The Workplace Area Characteristics (WAC) files contain employment counts at the census block level — fine enough to isolate specific facilities. **Quarterly Workforce Indicators (QWI)** add 32 economic indicators including employment, job creation, earnings, hires, and separations by firm characteristics and worker demographics, updated quarterly. The `lehdr` R package and `pygris` Python package both provide programmatic access.

**EEO-1 data** is becoming increasingly accessible. While individual company reports were historically confidential, a February 2025 legal settlement mandates public release of federal contractors' EEO-1 Component 1 data (2016–2020). The Census Bureau's EEO Tabulation provides workforce demographics by occupation, industry, and geography from ACS 5-Year data. EEO-1 reports break the workforce into **10 job categories** (Executive/Senior Officials through Service Workers) that can be crosswalked to SOC codes.

**Classification crosswalks** are essential infrastructure. BLS publishes official crosswalks between SOC and ACS occupation codes, O*NET-SOC codes, and Census industry codes. The `naicskit` Python package applies ML-based industry classification from text descriptions with **87% accuracy** using HuggingFace models — useful for classifying company descriptions when NAICS codes are missing or suspect. O*NET provides SOC-linked occupational data including tasks, skills, and abilities as bulk downloads.

---

## Combining methods: layered estimation recipes for different scenarios

The optimal estimation strategy depends on what data is available. Here are concrete recipes for common scenarios, following the Bayesian triangulation principle of weighting each source inversely by its error variance.

**For public companies**, start with the **SEC 10-K employee count** as the anchor (±2–5%), apply **BLS staffing patterns** by NAICS to estimate occupational composition (±15–25% per occupation), validate with **NLRB bargaining unit sizes** where available (near ground-truth for specific units), and cross-reference **OSHA establishment records** for establishment-level detail. Combined accuracy: **±2–5% total headcount, ±15–25% occupational composition.**

**For private companies**, the estimation challenge is fundamentally harder. Begin with **QCEW county × NAICS data** as the industry benchmark, apply **revenue-per-employee ratios** if revenue is known or estimable (using industry medians, not means), layer in **LinkedIn profile counts with sampling weight corrections** (comparing observed profiles against BLS occupational rates to correct for industry-specific penetration), and validate with **OSHA and NLRB records** when available. Combined accuracy: **±15–30% total headcount, ±25–40% occupational composition.**

**For specific establishments**, **OSHA inspection records** (which often note establishment size), **NLRB bargaining unit records**, **CBP establishment size class data**, and **physical capacity estimation** (square footage, bed counts, enrollment) provide the tightest constraints. If the target is the dominant employer in a small county-industry QCEW cell, the aggregate figure closely approximates its employment.

**The single largest source of downstream error is industry classification.** A misassigned NAICS code cascades through every method — wrong RPE benchmarks, wrong staffing patterns, wrong wage assumptions. Investing in accurate NAICS assignment (potentially using ML-based classification from company descriptions via `naicskit` or Industry2Vec) pays disproportionate dividends.

---

## Practical integration with your existing platform

Your platform's existing data assets — BLS industry-occupation matrix (113,473 rows), OSHA establishments, NLRB elections, SEC EDGAR filings, and DOL/OLMS union filings in PostgreSQL — provide an unusually strong foundation. NLRB bargaining unit sizes are particularly valuable: they represent **ground-truth headcounts for specific occupational subgroups at specific establishments**, enabling calibration of statistical estimates against observed reality. Most commercial workforce intelligence providers lack this data entirely.

The highest-impact additions, in priority order: **(1)** Implement Splink for cross-dataset entity resolution, unifying company identities across all five data sources. **(2)** Ingest QCEW and CBP data via Census/BLS APIs to establish industry-geography employment benchmarks. **(3)** Add LEHD/LODES WAC data for block-level employment validation near known establishments. **(4)** Deploy JobSpy for ongoing job posting collection, feeding skills-ml for SOC classification against your staffing pattern matrix. **(5)** Apply Industry2Vec embeddings to your NAICS codes for similarity-aware industry matching and ML feature engineering.

The critical gap in the open-source ecosystem is a tool that combines BLS staffing patterns with establishment-level data to produce company-specific occupational composition estimates. Building this — a system that takes a company name, resolves it across OSHA/SEC/NLRB datasets, determines its NAICS code(s) and headcount, applies weighted staffing patterns, and calibrates against any available ground-truth data (NLRB unit sizes, SEC disclosures) — would be a genuinely novel contribution to the labor market analytics ecosystem. Every piece of the pipeline exists as an open-source component; no one has assembled them.