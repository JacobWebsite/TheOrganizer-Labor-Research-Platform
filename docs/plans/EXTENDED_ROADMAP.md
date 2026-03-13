# Extended Roadmap: Labor Relations Research Platform
## Additional Checkpoints for Data Integration

---

## Current State Recap

You have a working unified interface with:
- **26,000+ unions** from OLMS LM filings
- **150,000+ employers** from F-7 bargaining notices
- **5.3M NLRB records** (cases, elections, participants)
- **BLS density data** (1983-present, by industry/state)

The platform answers: *"What unions exist, where are their employers, and what's their NLRB history?"*

---

## New Data Integration Checkpoints

### CHECKPOINT H: Mergent Intellect Integration (Employer Enrichment)
> *"Continue with Checkpoint H"*

**Goal:** Enrich F-7 employers with company financials, size, and industry data

**What Mergent Provides:**
- Company revenue estimates
- Employee counts (company-wide)
- NAICS/SIC industry codes
- Corporate parent/subsidiary relationships
- Headquarters location
- Public/private status

**Sub-tasks:**
- [ ] H1: Design employer enrichment schema (add columns to f7_employers_deduped)
- [ ] H2: Build Mergent lookup workflow (via CUNY library access)
- [ ] H3: Match F-7 employers to Mergent records (fuzzy name + location matching)
- [ ] H4: Create "Employer Profile" view showing union contracts + company financials
- [ ] H5: Add industry-level aggregations (union coverage by NAICS sector)
- [ ] H6: Identify organizing opportunities (large employers without union contracts)

**Enables:**
- "Show me all unionized employers with >$1B revenue"
- "What's the union density at major retail chains?"
- "Which subsidiaries of Company X have union contracts?"

---

### CHECKPOINT I: IRS 990 Integration (Union Financial Deep Dive)
> *"Continue with Checkpoint I"*

**Goal:** Add detailed nonprofit financials for unions (most are 501(c)(5) organizations)

**What 990s Provide:**
- Total revenue and expenses (more detail than LM forms)
- Executive/officer compensation (named individuals)
- Program service accomplishments
- Investment holdings
- Related organizations and transactions
- Lobbying expenditures (Schedule C)

**Data Sources:**
- ProPublica Nonprofit Explorer API (free)
- IRS 990 bulk data (AWS open data)
- Open990.org

**Sub-tasks:**
- [ ] I1: Match unions to their EIN (some are in LM data, others need lookup)
- [ ] I2: Build 990 data pipeline (ProPublica API or bulk download)
- [ ] I3: Create compensation analysis views (top-paid union executives)
- [ ] I4: Track union investment portfolios
- [ ] I5: Identify related organizations (PACs, training funds, etc.)
- [ ] I6: Compare LM vs 990 financials (reconciliation analysis)

**Enables:**
- "What are the highest-paid union executives?"
- "How much do unions spend on lobbying vs organizing?"
- "Which unions have the largest investment portfolios?"

---

### CHECKPOINT J: SEC/Edgar Integration (Public Company Employers)
> *"Continue with Checkpoint J"*

**Goal:** Link unionized employers to SEC filings for public companies

**What SEC Data Provides:**
- 10-K/10-Q financials (audited)
- Labor-related risk disclosures
- Collective bargaining agreement mentions
- Strike/work stoppage disclosures
- Employee counts (Item 1)

**Sub-tasks:**
- [ ] J1: Match F-7 employers to SEC CIK numbers
- [ ] J2: Extract labor-related disclosures from 10-K text
- [ ] J3: Track mentions of unions/CBAs in risk factors
- [ ] J4: Correlate stock performance with labor actions
- [ ] J5: Identify upcoming CBA expirations from filings

**Enables:**
- "Which public companies disclosed union-related risks?"
- "How did Company X's stock react to the strike?"
- "What CBAs are expiring in the next 12 months?"

---

### CHECKPOINT K: OSHA Integration (Workplace Safety)
> *"Continue with Checkpoint K"*

**Goal:** Link employers to workplace safety records

**What OSHA Data Provides:**
- Inspection history
- Violations and penalties
- Injury/illness rates (300A logs)
- Fatalities

**Sub-tasks:**
- [ ] K1: Download OSHA inspection database
- [ ] K2: Match to F-7 employers by name/address
- [ ] K3: Create safety score metrics
- [ ] K4: Correlate safety records with union presence
- [ ] K5: Add safety tab to employer profiles

**Enables:**
- "Do unionized workplaces have fewer OSHA violations?"
- "Which employers in this industry have the worst safety records?"
- "Show me employers with recent fatalities"

---

### CHECKPOINT L: Political Contribution Integration (FEC/OpenSecrets)
> *"Continue with Checkpoint L"*

**Goal:** Track union and employer political spending

**What FEC Data Provides:**
- PAC contributions
- Individual contributions by employer
- Lobbying disclosures
- Independent expenditures

**Sub-tasks:**
- [ ] L1: Match union PACs to parent organizations
- [ ] L2: Download FEC contribution data
- [ ] L3: Aggregate employer employee contributions
- [ ] L4: Track union political spending over time
- [ ] L5: Compare union vs employer political spending

**Enables:**
- "How much did SEIU's PAC spend in 2024?"
- "Which candidates received the most union support?"
- "Compare Amazon's political spending vs union spending"

---

### CHECKPOINT M: Contract Database Integration
> *"Continue with Checkpoint M"*

**Goal:** Collect and analyze actual collective bargaining agreements

**Data Sources:**
- DOL collective bargaining agreements database
- Union contract libraries (some public)
- FOIA requests for public sector contracts
- Bloomberg Law/BNA (if accessible)

**Sub-tasks:**
- [ ] M1: Inventory available CBA sources
- [ ] M2: Build contract metadata schema (employer, union, dates, coverage)
- [ ] M3: Extract key terms (wages, benefits, duration)
- [ ] M4: Track contract expirations
- [ ] M5: Enable contract comparison tools

**Enables:**
- "What's the average wage in UFCW grocery contracts?"
- "Which contracts expire in Q1 2026?"
- "Compare benefits across airline CBAs"

---

### CHECKPOINT N: News & Media Integration
> *"Continue with Checkpoint N"*

**Goal:** Track labor news and correlate with data events

**Data Sources:**
- News APIs (NewsAPI, GDELT)
- Labor-specific sources (Labor Notes, Payday Report)
- Press release monitoring

**Sub-tasks:**
- [ ] N1: Build news ingestion pipeline
- [ ] N2: Entity extraction (identify unions/employers in articles)
- [ ] N3: Sentiment analysis on labor coverage
- [ ] N4: Alert system for organizing activity
- [ ] N5: Timeline view correlating news with NLRB filings

**Enables:**
- "Show me recent news about Starbucks organizing"
- "Alert me when a new NLRB petition is filed at Company X"
- "What's the media sentiment around this strike?"

---

### CHECKPOINT O: Historical Trends & Predictive Analytics
> *"Continue with Checkpoint O"*

**Goal:** Build longitudinal analysis and predictive models

**Sub-tasks:**
- [ ] O1: Create time-series views of union membership by industry
- [ ] O2: Model factors predicting election outcomes
- [ ] O3: Identify industries with growing/declining union density
- [ ] O4: Forecast NLRB case volumes
- [ ] O5: Build "organizing likelihood" scores for non-union employers

**Enables:**
- "Which industries are seeing the most organizing activity?"
- "What factors predict union election wins?"
- "Which non-union employers are likely organizing targets?"

---

## Integration Priority Matrix

| Checkpoint | Data Source | Effort | Value | Dependencies |
|------------|-------------|--------|-------|--------------|
| **H** | Mergent Intellect | Medium | High | CUNY access |
| **I** | IRS 990 | Medium | High | EIN matching |
| **J** | SEC/Edgar | Medium | Medium | Public companies only |
| **K** | OSHA | Low | Medium | None |
| **L** | FEC | Medium | Medium | PAC matching |
| **M** | CBA Database | High | High | Data availability |
| **N** | News APIs | Medium | Medium | API costs |
| **O** | Analytics | High | High | Needs clean data |

---

## Recommended Integration Sequence

### Phase 1: Employer Enrichment (Checkpoints H, K)
Start with Mergent and OSHA - these directly enrich your existing F-7 employer data without requiring new entity types.

### Phase 2: Financial Deep Dive (Checkpoints I, J)
Add 990 data for unions and SEC data for public employers. This creates a complete financial picture on both sides of the bargaining table.

### Phase 3: Political & Contract Context (Checkpoints L, M)
Add political spending and actual contract data. This moves from "who's organized" to "what did they win."

### Phase 4: Intelligence Layer (Checkpoints N, O)
Add news monitoring and predictive analytics. This transforms the platform from retrospective analysis to forward-looking intelligence.

---

## Quick Start Commands

To begin any checkpoint, just say:
- *"Continue with Checkpoint H"* - Mergent employer enrichment
- *"Continue with Checkpoint I"* - IRS 990 union financials
- *"Continue with Checkpoint J"* - SEC public company data
- *"Continue with Checkpoint K"* - OSHA safety records
- *"Continue with Checkpoint L"* - Political contributions
- *"Continue with Checkpoint M"* - Contract database
- *"Continue with Checkpoint N"* - News integration
- *"Continue with Checkpoint O"* - Predictive analytics

Or continue with original checkpoints:
- *"Continue with Checkpoint A"* - Data quality cleanup
- *"Continue with Checkpoint B"* - Geographic features (maps)
- *"Continue with Checkpoint C"* - Charts & visualization
- *"Continue with Checkpoint G"* - BLS density integration
