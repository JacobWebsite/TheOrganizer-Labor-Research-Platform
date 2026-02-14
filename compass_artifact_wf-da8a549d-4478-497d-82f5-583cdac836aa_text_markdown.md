# Every method for classifying businesses as comparable — and how to use them for organizing

**The most powerful approach to ranking non-union employers as organizing targets combines government industry codes, data-driven similarity scoring, and labor-specific metrics into a composite "organizing opportunity score."** Standard NAICS codes are necessary but insufficient — academic research consistently shows that algorithmic similarity measures outperform expert-defined industry codes for identifying truly comparable businesses. The practical breakthrough for a labor organizing scorecard is **Gower Distance**, a similarity metric purpose-built for mixed data types (categorical industry codes + numerical violation counts + binary flags), implementable in a single Python library. Combined with propensity score matching — where the probability of being unionized given observable characteristics becomes the organizing target score itself — this creates a system that identifies non-union employers that statistically *should* be unionized based on how closely they resemble employers that already are.

The scorecard's current foundation (NAICS codes, BLS density, employer size, OSHA violations, NLRB history, government contracts, wage theft) covers the right territory. What follows is a comprehensive map of every classification method available, what each contributes, and exactly how to integrate them into a more powerful system.

---

## Government classification systems form the foundation but have structural blind spots

### NAICS: the backbone of U.S. business classification

The North American Industry Classification System organizes all economic activity into a **six-level hierarchy**: 20 sectors (2-digit) → 99 subsectors (3-digit) → 312 industry groups (4-digit) → 689 NAICS industries (5-digit) → **1,012 national industries (6-digit)**. Three sectors span multiple 2-digit codes: Manufacturing (31–33), Retail Trade (44–45), and Transportation & Warehousing (48–49). The system was last revised in 2022, with the next revision scheduled for 2027.

NAICS classifies **establishments** (single physical locations), not enterprises or companies. A multi-location corporation has separate NAICS codes for each facility based on its primary activity. This is both a strength and a limitation for organizing — it matches the NLRB's typical plant-unit bargaining framework but obscures corporate structure. Codes are assigned through a fragmented process: the SSA assigns codes when businesses file for EINs, the Census Bureau assigns based on survey responses, and BLS assigns based on unemployment insurance applications. The same business may carry different NAICS codes across agencies.

For the scorecard, NAICS is freely available through the Census Data API (api.census.gov) and BLS Public Data API (api.bls.gov). The critical limitation is that NAICS is **production-oriented** — it groups businesses by *how* they produce goods and services, not by labor conditions, workforce composition, or market positioning. Two employers with the same 6-digit NAICS code may have radically different labor practices, while employers with different codes (e.g., an e-commerce warehouse coded as retail vs. a traditional logistics firm coded as transportation) may employ functionally identical workforces.

### SIC persists in critical labor data systems

The Standard Industrial Classification system — 11 divisions, 83 major groups, 416 industry groups, and **1,005 industries** at the 4-digit level — was last revised in **1987** and officially replaced by NAICS in 1997. Yet SIC remains stubbornly embedded in key systems. The **SEC uses SIC codes** in all EDGAR filings to classify companies. **OSHA still maintains the SIC Manual** on its website for enforcement classification. Many state agencies and legacy databases retain SIC coding. Census Bureau crosswalk tables map between SIC and NAICS, but the relationship is many-to-many — no clean one-to-one conversion exists.

For the scorecard, SIC codes matter primarily because OSHA enforcement data references them, and SEC filings for public companies use them. The free SIC-NAICS crosswalk from census.gov/naics enables translation, but imperfect mappings introduce noise.

### SOC captures what NAICS misses: the workforce itself

The Standard Occupational Classification is the occupation-side complement to NAICS's industry focus. It contains **23 major groups → 98 minor groups → 459 broad occupations → 867 detailed occupations**, using 6-digit hyphenated codes (e.g., 29-1141 = Registered Nurses). The 2018 SOC revision added 70 new detailed occupations. SOC connects directly to **O*NET**, which extends to ~1,016 occupation codes with rich data on skills, knowledge, tasks, work context, education requirements, and working conditions — all freely downloadable under Creative Commons license from onetcenter.org.

**SOC classification is arguably more useful than NAICS for organizing purposes** because it describes the actual workforce. BLS publishes the Occupational Employment and Wage Statistics (OEWS) program data cross-tabulating **occupation × industry** at 3–5 digit NAICS levels. This enables a powerful scorecard enhancement: instead of comparing employers only by industry code, compare them by **occupation mix** — the distribution of SOC codes within their workforce. Two employers in different NAICS codes but with similar occupation mixes (e.g., lots of 53-7062 Laborers and Material Movers) are highly comparable for organizing purposes.

### BLS supersectors and union density reporting

BLS reorganizes the 20 NAICS sectors into **11 supersectors** within two domains (Goods-Producing and Service-Providing). The most important groupings for the scorecard include Trade, Transportation & Utilities (combining NAICS 22, 42, 44–45, 48–49) and Education & Health Services (combining NAICS 61, 62). These supersectors drive how BLS reports union membership data.

The **Quarterly Census of Employment and Wages (QCEW)** is the most comprehensive establishment-level dataset — covering ~95% of U.S. jobs from unemployment insurance records — and publishes at **all NAICS levels down to 6-digit** for 3,000+ counties. This is freely available with CSV downloads and a data access API. For the scorecard, QCEW provides the denominator: total employment by industry by geography, against which organizing density can be benchmarked.

Union density reporting from the CPS, however, is published at only the **sector/supersector level** (~50 broad industry categories) due to sample size constraints. This creates the granularity gap: the scorecard assigns NAICS 6-digit codes to employers but can only look up union density at the 2–3 digit level.

---

## Commercial classification systems fill gaps for private employers

Government data covers establishments but often lacks company-level detail for private firms. Commercial databases bridge this gap, though at significant cost.

### D&B and Data Axle cover virtually all U.S. businesses

**Dun & Bradstreet** maintains the most comprehensive commercial business database: **500+ million company records** globally, each identified by a unique 9-digit D-U-N-S number. D&B assigns proprietary **8-digit SIC and 8-digit NAICS codes** (standard codes plus 2–4 proprietary extension digits for finer granularity). They assign multiple codes per business, with the primary code representing the largest revenue source and secondary codes requiring at least 10% of revenue. D&B data comes from 30,000+ sources, supplemented by ~25 million verification calls annually. Access costs $49/month (Essentials) to $25,000+/year (Enterprise).

**Data Axle** (formerly InfoUSA/Infogroup) maintains **24+ million U.S. business records** with 400+ data points per establishment. They use proprietary 6-digit SIC and 8-digit NAICS extensions. Data Axle is particularly strong for small businesses, covering home-based businesses and sole proprietors that other databases miss. It's widely available through academic library subscriptions as "Reference Solutions."

For the scorecard, these databases could provide employer-level NAICS codes, employee counts, revenue estimates, and corporate linkages (parent/subsidiary relationships) for private employers. The cost is the primary barrier. **Data Axle through a library subscription** is the most accessible entry point.

### Financial classification systems serve investors, not organizers

Four major systems classify publicly traded companies for investment analysis:

- **GICS** (S&P/MSCI): 11 sectors → 25 industry groups → 74 industries → **163 sub-industries**. Market-oriented. Public companies only.
- **ICB** (FTSE Russell): 11 industries → 20 supersectors → 45 sectors → **173 subsectors**. 85,000 securities globally. Public companies only.
- **BICS** (Bloomberg): 7 levels of hierarchy, covering **2.6 million legal entities** including private companies. Requires Bloomberg Terminal (~$24,000/year).
- **TRBC** (Refinitiv/LSEG): 10 sectors → 28 business sectors → 54 industry groups → 136 industries → **837 activities**. Most granular. 7.1 million entities.

These systems are **market-oriented** (grouping by investor behavior and revenue source) rather than production-oriented like NAICS. They're useful for classifying public employers and their subsidiaries but irrelevant for the vast majority of non-union private employers. BICS and TRBC are exceptions — both now cover millions of private entities — but require expensive subscriptions.

### Free and low-cost alternatives exist

Several platforms classify businesses at lower or no cost:

- **LinkedIn**: 434 industry codes across 6 levels, self-reported by companies on their profiles. Covers virtually every employer with a web presence. Free to view; the taxonomy loosely mirrors NAICS but with less granularity.
- **Google Business Profile**: ~4,000 categories, self-selected by businesses. Excellent for consumer-facing local businesses, useless for B2B.
- **Yelp**: 1,500+ categories using machine learning (logistic regression + random forest classifiers) plus self-reporting. Consumer-facing only.
- **ZoomInfo**: 100+ million businesses with NAICS/SIC codes, AI-enhanced attribute prediction. Claims 100% fill rate on industry classification. Costs $15,000–$25,000+/year.

For the scorecard, **LinkedIn's industry taxonomy** is the most practical free source for employer-level classification, though its self-reported nature introduces inaccuracy.

---

## Data science approaches outperform standard codes for identifying comparable businesses

Academic research consistently demonstrates that **algorithmic similarity measures identify more operationally comparable businesses** than any single classification code. The most important finding for the scorecard is that these methods are increasingly accessible through open-source tools.

### Text-based classification from company descriptions

The most immediately implementable data science approach uses natural language processing on company descriptions. A 2023 paper by Vamvourellis et al. (arXiv:2308.08031) showed that **Sentence-BERT embeddings of SEC 10-K business descriptions outperform NAICS and SIC codes** for identifying companies with similar profitability, sales growth, and market risk. Companies close in embedding space exhibited correlated financial performance.

The U.S. Census Bureau itself explored generating NAICS codes from web-scraped company websites (Cuffe et al., NBER 2019), achieving useful accuracy using Doc2Vec embeddings fed into Random Forest classifiers on ~120,000 single-unit businesses. An open-source Python package called **naicskit** uses Hugging Face entailment models to assign NAICS codes from company descriptions, claiming **87% accuracy** on known taxonomies.

For the scorecard, the implementation path is straightforward: collect employer descriptions from websites or LinkedIn profiles, embed them using a pre-trained sentence transformer (the `sentence-transformers` Python library is free and open-source), and compute **cosine similarity** between any pair of employers. This produces a continuous similarity score (0.0 to 1.0) far more informative than binary NAICS matching. Using OpenAI's embedding API costs approximately $0.02 per million tokens — essentially free at scorecard scale.

### Job posting analysis reveals workforce composition directly

Analyzing what roles an employer hires for reveals its actual operations regardless of NAICS code. A company hiring warehouse associates, forklift operators, and logistics coordinators operates similarly to other distribution employers whether coded as retail (NAICS 44–45) or transportation (NAICS 48–49). Indeed and LinkedIn job postings are publicly accessible and can be embedded and compared using the same NLP tools. ZipRecruiter uses Prototypical Networks with word2vec for job title classification at scale. **Job posting analysis is uniquely valuable for organizing because it directly reveals workforce composition, pay ranges, and skill requirements** — the exact factors that determine organizing relevance.

### Network-based similarity captures what text misses

A landmark paper by Lee, Ma & Wang (2015, *Journal of Financial Economics*) introduced **Search-Based Peers** by analyzing 3.5 billion SEC EDGAR page views. Companies that investors search in sequence are fundamentally similar — and this co-search signal **explains 81% more variance** in financial metrics than GICS industry codes. A follow-up study introduced "labor market peer firms" using LinkedIn's "also viewed" feature to capture labor-market linkages specifically.

Supply chain similarity offers another powerful signal: companies sharing 70%+ of the same suppliers or customers likely operate in the same or adjacent industries. Graph Neural Networks applied to supply chain networks can classify companies with high accuracy.

### Embedding-based approaches are the most practical advancement

**Company2Vec** (Gerling, 2023) creates 300-dimensional vector representations of companies from corporate website text. After PCA reduction to 100 dimensions, cosine similarity between vectors measures company comparability, and clustering algorithms (hierarchical, DBSCAN) identify peer groups. **Industry2Vec** (open-sourced by ING Bank) creates vector representations of NAICS codes themselves using a Siamese network, so that NAICS codes across different 2-digit sectors but serving similar markets cluster together.

The recommended implementation combines pre-trained sentence transformers with Gower distance (described in the integration section below) for a system that handles both text and structured data.

---

## Labor-specific classification methods define what "comparable" means for organizing

### How unions actually select organizing targets

The AFL-CIO's formal "Organizing Priorities and Strategies" framework establishes that unions should first focus on **core industries and occupations** where they already have presence, then expand to growth industries. The federation coordinates among "lead and major unions" to reduce jurisdictional competition. SEIU focuses on healthcare, building services, and public sector; UNITE HERE on hotels, food service, and laundry; Teamsters on freight, warehousing, and delivery; UFCW on retail food and meatpacking.

Union target selection criteria, synthesized across published frameworks, include:

- Industry and sector history of labor disputes or high turnover
- Workplace size and workforce demographics
- Employer record of anti-union activities or poor labor practices
- Existing employee dissatisfaction (the "hot shop" signal)
- Industry/market union density context
- Geographic union infrastructure
- Competitive position relative to already-unionized firms

The Building and Construction Trades Department has explicitly articulated that "chief competitors in a given market will have to be identified, targeted, and organized in a single unified campaign." This directly validates the scorecard's comparative approach.

### BLS union density data and the granularity problem

The January 2025 BLS release (reporting 2024 data) shows private-sector union density at **5.9%**, with enormous industry variation. **Utilities lead at 18.7%**, followed by transportation & warehousing (15.8%) and educational services (13.2%). At the bottom: finance (0.8%), insurance (1.2%), and professional/technical services (1.2%).

The critical challenge: BLS publishes these rates at roughly the **2–3 digit NAICS level** (~50 industry categories). The scorecard needs density estimates at 6-digit NAICS. Three solutions exist, ordered by complexity:

**Method 1 — Hierarchical mapping (low complexity):** Map each 6-digit NAICS to its parent 3-digit code and apply that broader rate. All sub-industries get the same rate. Free, immediate, imprecise.

**Method 2 — CPS microdata analysis (medium-high complexity):** Download CPS microdata from IPUMS (free) and calculate custom union density at more granular industry × geography × occupation intersections. The `ipumspy` Python package facilitates this. Limitation: CPS sample sizes (~60,000 households/month) require multi-year pooling for detailed cells.

**Method 3 — NLRB election data as proxy (medium complexity):** Calculate election petition frequency and win rates by industry from NLRB data (free at nlrb.gov/advanced-search). This captures "organizing activity density" — a more action-relevant metric than static union membership rates.

**Unionstats.com** (maintained by Barry Hirsch and David Macpherson at Georgia State and Trinity Universities) provides far more granular breakdowns than published BLS tables: detailed industry, detailed occupation, by state, by metropolitan area, from 1983–2025. This is the single most useful free resource for mapping density to specific employer characteristics.

### NLRB bargaining unit definitions shape the "comparable" question

The NLRB determines bargaining units using the **community of interest standard**, which was restored to its more union-friendly form in *American Steel Construction* (December 2022). Under the current standard, a petitioned-for unit is appropriate if workers share an internal community of interest — and an employer challenging the unit must show excluded employees share an **"overwhelming community of interest"** with included workers. Factors include common supervision, shared wages/hours/conditions, functional integration, interchange among employees, and distinct job functions.

The NLRB's election database contains case numbers, employer names, union names, geographic region, **industry classification codes** (NLRB's own coding), bargaining unit descriptions, eligible voter counts, vote totals, and outcomes. This data is searchable at nlrb.gov/advanced-search (up to 100,000 records) and available through academic datasets maintained by JP Ferguson (jpferguson.net/nlrb-representation-case-data) and visualized at unionelections.org. **NLRB election win rates reached 73.8% in 2024** — the highest in recent history.

### Research identifies predictors of organizing success

**Kate Bronfenbrenner** (Cornell ILR School) has produced the most rigorous research on organizing outcomes. Her landmark finding: **union tactic variables explain more variance in election outcomes than employer characteristics**, bargaining unit demographics, or election background. This means the scorecard correctly focuses on identifying targets, but campaign strategy matters even more than target selection.

Among employer/environment characteristics, the most robust predictors are:

- **Unit size**: Unions have always been less likely to win in larger units (Farber 2001, NBER). This finding has strengthened over 45 years. **Smaller units = higher win probability.**
- **Employer opposition intensity**: The single strongest predictor of election loss. Threats of plant closure, interrogation, and discharge dramatically reduce win rates (Bronfenbrenner 2009).
- **Industry sector**: Service, retail, and nonprofit sectors show more recent wins. Healthcare is a growth area.
- **Right-to-work status**: States with RTW laws show lower win rates.
- **Public vs. private**: ~85% public-sector win rate vs. ~48% private sector.

### OSHA benchmarking uses NAICS for peer comparison

OSHA's Site-Specific Targeting (SST) program selects inspection targets based on employer-submitted Form 300A injury data, using the **DART Rate** (Days Away, Restricted, or Transferred) as the primary metric. OSHA sets different DART thresholds for manufacturing (NAICS 31–33) versus non-manufacturing employers. The BLS Survey of Occupational Injuries and Illnesses publishes industry-average incidence rates at **NAICS 2-digit through 6-digit levels**, enabling precise benchmarking. For the scorecard, an employer's OSHA violation rate divided by its NAICS industry average creates a normalized **"excess violation score"** that measures safety performance relative to peers.

---

## Size, structure, and geography create critical classification dimensions beyond industry

### SBA size standards vary dramatically by NAICS code

The SBA maintains **102 different size standard levels** covering 978 NAICS industries. Standards are either revenue-based (496 industries, ranging from $1M to $47M+) or employee-based (478 industries, ranging from 100 to 1,500 employees). A "small" construction firm can have up to 1,500 employees, while a "small" restaurant is capped at $9M in revenue. The full table is freely available at sba.gov/document/support-table-size-standards and can be matched to any employer by NAICS code. For the scorecard, SBA thresholds help normalize "size" across industries — an employer at 2× its SBA threshold is "large for its industry" regardless of absolute employee count.

### Regulatory thresholds create organizing-relevant breakpoints

Key employee-count thresholds trigger compliance obligations that generate shared worker grievances:

- **50 employees**: FMLA (unpaid leave), ACA employer mandate (health insurance). This is the threshold where benefits become a major organizing issue.
- **100 employees**: WARN Act (layoff notification), EEO-1 reporting (workforce demographic disclosure)
- **15 employees**: Title VII and ADA anti-discrimination coverage
- **20 employees**: ADEA (age discrimination), COBRA (health continuation)

The **50-employee threshold** is particularly significant because it simultaneously triggers family leave and health insurance obligations, creating immediate worker-management friction points. Employers just above these thresholds face new compliance costs; those just below may be deliberately suppressing headcount.

### Establishment vs. enterprise data shapes targeting strategy

Census Bureau data distinguishes **establishments** (single physical locations, ~8 million in U.S.) from **enterprises** (entire companies across all locations, ~6 million). County Business Patterns reports at the establishment level by county, industry, and size class. The Statistics of U.S. Businesses uniquely bridges to enterprise-level data, showing how many establishments each firm operates and total enterprise employment.

This distinction matters for organizing because the NLRB's default bargaining unit is the **single worksite**. A 50,000-employee corporation may have 200 separate potential organizing targets. The scorecard should track both establishment-level characteristics (local OSHA violations, local employment) and enterprise-level characteristics (parent company finances, other locations' organizing history, corporate structure).

### Geographic classification defines the comparable labor market

**387 Metropolitan Statistical Areas** cover 94.7% of the U.S. population (317 million people), defined by commuting flows to urbanized cores of 50,000+. **598 Commuting Zones** cover every U.S. county including rural areas, defined by the USDA Economic Research Service through hierarchical cluster analysis of county-level commuting data. For organizing, commuting zones are more comprehensive than MSAs because they include rural labor markets where food processing, agriculture, and manufacturing employers may be prime targets.

The Harvard Business School **Cluster Mapping Project** (clustermapping.us) provides 50+ million open data records on regional industry concentrations, identifying where specific industries cluster geographically. Industries in strong clusters experience higher growth in new business formation — and higher density of comparable employers creates greater pattern bargaining potential.

### Ownership type dramatically affects organizing dynamics

Private equity ownership, identifiable through PitchBook ($20,000–$40,000/year), SEC filings, or press reporting, signals cost-cutting pressure and shorter ownership horizons that both create grievances and complicate long-term bargaining. Government contractor status, freely identifiable through **SAM.gov** and **USAspending.gov**, creates organizing leverage because contractors face additional labor requirements (Davis-Bacon Act, Service Contract Act, Executive Order obligations) and reputational sensitivity. **Nonprofit status** is freely searchable through the IRS Business Master File and ProPublica's Nonprofit Explorer — nonprofits face public accountability for labor practices given their tax-exempt status.

---

## Practical integration: building the composite organizing opportunity score

### Gower Distance solves the core multi-dimensional comparison problem

The scorecard compares employers across mixed data types: categorical (NAICS code, state, ownership type), numerical (employee count, violation rate, union density), and binary (government contractor yes/no). Most distance metrics handle only one data type. **Gower Distance** (Gower, 1971) natively handles all three by computing partial similarity scores for each feature, normalizing them to a 0–1 scale, and averaging with optional weights. It also handles missing data by simply excluding missing features from the calculation rather than requiring imputation.

Implementation requires a single line of Python after data preparation:

```python
import gower
distance_matrix = gower.gower_matrix(employer_df, weight=[3, 2, 2, 1, 1, 1, 1])
```

The `weight` parameter allows domain-expert emphasis — give industry classification triple weight and OSHA violations double weight, for example. The `gower_topn` function returns the N most similar employers to any target. **Complexity: low. Impact: high.** This single addition transforms the scorecard from binary matching (same NAICS yes/no) to continuous similarity scoring.

### Hierarchical NAICS similarity replaces binary matching

Rather than treating NAICS as match/no-match, score similarity by shared prefix length:

| Match level | Similarity score |
|---|---|
| Same 6-digit NAICS | 1.00 |
| Same 5-digit | 0.85 |
| Same 4-digit | 0.65 |
| Same 3-digit | 0.40 |
| Same 2-digit | 0.20 |
| Different sector | 0.00 |

This acknowledges that a general freight trucking firm (NAICS 484121) is closer to a specialized freight firm (484122) than to a school bus operator (485410), but closer to that bus operator than to a software publisher (511210). ING Bank's open-source **Industry2Vec** takes this further by training a Siamese network on the NAICS hierarchy, producing vector embeddings where similar industry codes cluster together regardless of 2-digit sector boundaries.

### Propensity score matching produces the organizing opportunity score directly

The most powerful enhancement is reconceptualizing the scorecard as a **propensity score model**. Fit a logistic regression predicting P(unionized | employer features) using the set of all employers where union status is known (from NLRB election wins, LM-2 reports, and collective bargaining agreement records). Features include NAICS code, employee count, state, metro area, industry union density, government contractor status, and OSHA violation rate.

**The resulting propensity score for non-union employers is itself the organizing opportunity score.** A non-union employer with a predicted probability of 0.85 of being unionized — based on how similar it is to employers that *are* unionized — is a prime target. This approach naturally integrates all classification dimensions into a single score, with weights learned from data rather than guessed.

Implementation uses standard scikit-learn:

```python
from sklearn.linear_model import LogisticRegression
model = LogisticRegression()
model.fit(X_features, y_union_status)
opportunity_scores = model.predict_proba(X_non_union)[:, 1]
```

### The "sibling employer" concept operationalized

The sibling employer concept — same industry, same area, similar size, one union, one not — can be operationalized by computing Gower distance between each non-union target and all known unionized employers. For each target, the **average distance to its 5 nearest unionized peers** becomes the "distance from nearest unionized sibling" score. Inverting this (1 − distance) gives a "similarity to unionized peers" score between 0 and 1.

Data sources for building the unionized employer reference database are all free:

- **NLRB election wins**: nlrb.gov/advanced-search (employer name, location, industry, unit size, outcome)
- **LM-2 reports**: olmsapps.dol.gov/olpdr (union membership counts, local jurisdiction)
- **FMCS work stoppage data**: github.com/labordata/fmcs-work-stoppage (1984–2020)
- **BLS work stoppages**: bls.gov/wsp (stoppages involving 1,000+ workers, classified by NAICS)

### The recommended composite formula

The final organizing opportunity score integrates three dimensions:

**Opportunity Score = 0.35 × Similarity + 0.35 × Vulnerability + 0.30 × Feasibility**

**Similarity Score** (how much does this employer resemble unionized employers?): Gower distance to k-nearest unionized peers, incorporating NAICS hierarchy, employee count, geography, and corporate structure.

**Vulnerability Score** (how exposed is this employer to organizing pressure?): Weighted combination of OSHA violation severity percentile (0.25), wage theft violation percentile (0.25), industry union density (0.20), government contractor flag (0.15), and nearby NLRB election activity (0.15).

**Feasibility Score** (how winnable is a campaign here?): Unit size score where smaller = higher based on Farber's research (0.30), geographic favorability reflecting state labor law environment (0.30), prior election history where close prior elections score high (0.20), and strategic value reflecting parent company and industry importance (0.20).

The 0.35/0.35/0.30 starting weights should be treated as initial estimates. Once the scorecard has accumulated outcome data from actual organizing campaigns, **logistic regression on win/loss outcomes** will produce empirically optimal weights. Cross-validation prevents overfitting to small samples.

### Entity resolution is the unglamorous prerequisite

The same employer appears differently across OSHA ("WALMART INC"), NLRB ("Wal-Mart Stores, Inc."), BLS (aggregate data), DOL wage theft records ("WAL MART STORES INC"), and SAM.gov ("WALMART INC"). Without entity resolution, the scorecard cannot link violation records, election history, and contract data to the same employer.

The recommended tool is **Splink** (open-source, UK Ministry of Justice), which performs probabilistic record linkage using the Fellegi-Sunter model. It runs on DuckDB (fast on laptops) or Spark (for millions of records), handles fuzzy name matching and address comparison, and requires no training data. Block on state + first 4 digits of NAICS to reduce comparison space, then compare on employer name (fuzzy), address, and employee count. **This is the highest-impact infrastructure investment** — without it, all other scoring is unreliable.

---

## How each enhancement improves the current scorecard

The scorecard currently uses NAICS codes, BLS industry density, employer size, OSHA violations, NLRB election history, government contracts, and wage theft violations. Here is each recommended enhancement, prioritized by impact per unit of implementation effort:

**Priority 1 — Immediate, high-impact, free data:**
- Hierarchical NAICS similarity scoring (replace binary match with prefix-length score). Complexity: low. Impact: high.
- Gower distance for mixed-data similarity scoring. Library: Python `gower`. Complexity: low. Impact: high.
- Entity resolution via Splink across data sources. Complexity: medium-high. Impact: very high — enables all other scoring.
- Geographic labor market context: state right-to-work status, metro union density from unionstats.com, local NLRB petition activity. Complexity: low-medium. Impact: high.

**Priority 2 — Moderate effort, significant uplift:**
- Propensity score model as organizing opportunity score. Library: `sklearn.linear_model.LogisticRegression`. Complexity: medium. Impact: very high.
- CPS microdata via IPUMS for granular union density estimates below BLS published levels. Complexity: medium-high. Impact: high.
- NLRB election data integration for "demonstration effect" scoring (how much nearby organizing activity exists). Complexity: medium. Impact: high.

**Priority 3 — Longer-term enhancements:**
- Occupation mix comparison using BLS OEWS staffing patterns and cosine similarity. Complexity: medium. Impact: medium-high.
- Ownership and corporate structure scoring from SEC EDGAR, IRS 990, SAM.gov, and state Secretary of State records. Complexity: medium. Impact: medium.
- LM-2 and OLMS data integration for profiling unionized employers as reference set. Complexity: medium. Impact: medium-high.

**Priority 4 — Future optimization:**
- Data-driven weight optimization from campaign outcomes using logistic regression. Complexity: medium. Impact: very high over time.
- Text-based employer embedding using company descriptions and job postings. Library: `sentence-transformers`. Complexity: medium. Impact: high for nuanced similarity.

The core Python technology stack is: `gower` + `splink` + `sklearn` + `pandas` + `duckdb`. All libraries are free and open-source. All key data sources (BLS, NLRB, OSHA, Census, OLMS, SAM.gov, USAspending.gov, IPUMS) are freely available with APIs or bulk downloads. The primary cost is analyst time for entity resolution tuning and model validation, not data acquisition or software licensing.

---

## Conclusion: classification is solved infrastructure, not a research frontier

The methods for classifying businesses as comparable are well-established across government, commercial, and academic domains. The 1,012 NAICS codes, 867 SOC occupations, and 102 SBA size standards provide structured frameworks. Commercial databases from D&B (500M+ records) and Data Axle (24M+ U.S. establishments) extend coverage to private employers. Academic research has demonstrated that text embeddings and network-based approaches outperform all standard classification codes for identifying truly comparable businesses.

What the organizing scorecard needs is not a new classification system but **intelligent integration** of existing ones. The three highest-leverage improvements are: (1) **Gower distance** replacing binary NAICS matching with continuous multi-dimensional similarity, (2) **propensity score matching** where the probability of being unionized becomes the target score itself, and (3) **entity resolution** via Splink enabling reliable cross-database employer profiles. Together, these transform the scorecard from a list of independent indicators into a unified statistical model that answers the question every organizer needs answered: *which non-union employer most resembles an employer that already has a union?*

The "sibling employer" concept — the non-union twin of a unionized workplace — is no longer just an intuition. With the data sources and methods described here, it is computationally operationalizable at scale using entirely free data and open-source tools.