# SEC EDGAR data for labor relations research: a complete integration guide

**SEC EDGAR provides a rich but fragmented landscape of labor-relevant data**, combining structured XBRL fields (employee counts, compensation, pension data) with vast unstructured text (human capital narratives, union disclosures, risk factors). The critical finding for entity matching: **EIN is available for every EDGAR filer** via the submissions API and bulk download, making direct joins against your 63,000+ unionized employer database feasible. Roughly 80% of labor-relevant content requires NLP extraction from filing text, while 20% exists as machine-readable XBRL tags. This guide covers every API endpoint, data source, Python library, and schema pattern needed to build a production pipeline.

---

## 1. Labor-relevant data across SEC filing types

### 10-K annual reports: the primary source

The 10-K is the richest single source of workforce data. Six sections contain labor-relevant information:

**Item 1 (Business)** contains employee counts, business segment descriptions, and — since November 9, 2020 — mandatory human capital disclosures under amended Regulation S-K Item 101(c). The SEC rule (Release 33-10825) requires "a description of the registrant's human capital resources, including any human capital measures or objectives that the registrant focuses on in managing the business." The only hard requirement is disclosing **the number of persons employed** (to the extent material). Everything else follows a principles-based approach — companies choose what to disclose based on materiality. Per Gibson Dunn surveys of S&P 100 companies, about **58% include workforce composition data**, with common topics including DEI metrics, turnover rates, training programs, safety data, and labor relations status including union representation and CBA details. Smaller Reporting Companies are exempt from human capital disclosure requirements.

**Item 1A (Risk Factors)** frequently contains labor-specific risk disclosures: union representation, CBA expiration timelines, strike/work stoppage risk, labor shortage concerns, minimum wage exposure, and NLRA compliance risks. This is entirely unstructured text requiring keyword extraction or NLP.

**Item 7 (MD&A)** discusses labor cost trends, wage inflation impacts on margins, pension cost changes, restructuring/severance charges, and headcount changes. Some numeric values overlap with XBRL-tagged financial statement data, but the narrative context is unstructured.

**Item 3 (Legal Proceedings)** may reference NLRB matters, labor lawsuits, or class-action employment litigation.

### DEF 14A proxy statements: compensation data

Proxy statements contain three structured compensation disclosures relevant to labor research:

- **Summary Compensation Table** (Item 402(c) Reg S-K): Salary, bonus, stock awards, option awards, non-equity incentive, pension value changes, and all other compensation for each Named Executive Officer
- **CEO Pay Ratio** (Item 402(u), required since fiscal years beginning after January 1, 2017): Median annual total compensation of all employees, CEO total compensation, and the ratio. Companies have broad methodological flexibility. This data is **mostly unstructured** — it was not originally required to be XBRL-tagged
- **Pay vs Performance** (Item 402(v), effective December 16, 2022): Tables showing compensation actually paid versus financial performance. **This IS required in Inline XBRL** using the Executive Compensation Disclosure (ECD) taxonomy

### Other filing types

**8-K Current Reports** are a real-time signal for labor events. Item 2.05 (Costs Associated with Exit or Disposal Activities) is the primary vehicle for layoff/plant closure disclosures, reporting estimated severance costs and number of affected employees. Items 7.01 and 8.01 sometimes carry strike or labor dispute announcements. Federal Reserve research (FEDS Working Paper 2024-020) confirms 8-Ks as a viable real-time layoff tracking source.

**Form 11-K** (Employee Benefit Plan annual reports) contains employee stock purchase and savings plan data. Starting July 2025, these must be filed in Inline XBRL using the Employee Benefit Plan taxonomy (`us-gaap-ebp`).

**Form S-1** (IPO filings) contains the same Item 101 human capital disclosures as 10-Ks, often with particularly detailed workforce descriptions for labor-intensive businesses.

---

## 2. Every XBRL tag relevant to workforce research

Structured XBRL data is accessible programmatically via three APIs on `data.sec.gov` (detailed in Section 4). Here is the complete inventory of labor-relevant tags across all taxonomies:

### Employee counts and entity information (DEI taxonomy)

| Tag | Description |
|-----|-------------|
| `dei:EntityNumberOfEmployees` | Total employee count (units: "pure") |
| `dei:EntityCommonStockSharesOutstanding` | Shares outstanding |
| `dei:EntityPublicFloat` | Public float value |

### Compensation and labor costs (US-GAAP taxonomy)

| Tag | Description |
|-----|-------------|
| `us-gaap:LaborAndRelatedExpense` | Total labor and related expense |
| `us-gaap:SalariesAndWages` | Salaries and wages expense |
| `us-gaap:SalariesWagesAndOfficersCompensation` | Combined salaries, wages, officers' comp |
| `us-gaap:ShareBasedCompensation` | Stock-based compensation expense |
| `us-gaap:AllocatedShareBasedCompensationExpense` | Allocated SBC expense |
| `us-gaap:EmployeeBenefitsAndShareBasedCompensation` | Combined benefits + SBC |

### Pension and post-retirement benefits (Section 715000)

| Tag | Description |
|-----|-------------|
| `us-gaap:DefinedBenefitPlanNetPeriodicBenefitCost` | Net periodic pension cost |
| `us-gaap:DefinedBenefitPlanBenefitObligation` | Projected benefit obligation |
| `us-gaap:DefinedBenefitPlanFairValueOfPlanAssets` | Plan assets at fair value |
| `us-gaap:DefinedContributionPlanCostRecognized` | 401(k)-type plan expense |
| `us-gaap:MultiemployerPlanPensionSignificantCollectiveBargainingArrangementExpirationDate` | **CBA expiration date for multiemployer pension plans** |

That last tag — `MultiemployerPlanPensionSignificantCollectiveBargainingArrangementExpirationDate` — is especially valuable for labor relations research. It provides **structured, machine-readable CBA expiration dates** directly from XBRL data.

### Restructuring and severance (Section 420000)

| Tag | Description |
|-----|-------------|
| `us-gaap:SeveranceCosts1` | Severance costs |
| `us-gaap:RestructuringCharges` | Total restructuring charges |
| `us-gaap:RestructuringAndRelatedCostNumberOfPositionsEliminated` | **Positions eliminated count** |
| `us-gaap:RestructuringAndRelatedCostNumberOfPositionsEliminatedPeriodPercent` | **Workforce reduction percentage** |

### Employee liabilities

| Tag | Description |
|-----|-------------|
| `us-gaap:EmployeeRelatedLiabilitiesCurrent` | Current employee-related liabilities |
| `us-gaap:AccruedSalariesCurrent` | Accrued salaries |
| `us-gaap:PostemploymentBenefitsLiabilityCurrent` | Post-employment benefits liability |
| `us-gaap:DeferredCompensationLiabilityCurrent` | Deferred compensation |

### Executive compensation (ECD taxonomy, from proxy statements)

| Tag | Description |
|-----|-------------|
| `ecd:PeoTotalCompAmt` | PEO (CEO) total compensation |
| `ecd:PeoActuallyPaidCompAmt` | Compensation actually paid to CEO |
| `ecd:NonPeoNeoAvgTotalCompAmt` | Average non-CEO NEO compensation |
| `ecd:TotalShareholderRtnAmt` | Company TSR |
| `ecd:PvpTableTextBlock` | Full Pay vs Performance table |

**Estimated data coverage**: roughly **20% of labor-relevant data** is available as structured XBRL tags. The remaining 80% — union membership percentages, CBA details, DEI statistics, turnover rates, human capital narratives, risk factor text — requires NLP extraction from unstructured filing text.

---

## 3. Identifier availability and entity matching strategy

### EIN: available and bulk-downloadable

**EIN appears in multiple places across EDGAR**, making it the primary join key for matching against your existing databases:

**Submissions API** — Every filer's JSON at `https://data.sec.gov/submissions/CIK{10-digit}.json` includes an `ein` field at the top level alongside `cik`, `name`, `tickers`, and `sic`. The bulk download at `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` contains all filer JSONs — approximately **800,000 entity records** with EIN where available. This is the single best resource for building a CIK↔EIN mapping.

**SGML Filing Headers** — Every EDGAR filing contains an `<IRS-NUMBER>` field in its header. The Financial Statement Data Sets at `https://www.sec.gov/dera/data/financial-statement-data-sets.html` include quarterly ZIP files with a `sub.txt` table containing `ein`, `cik`, `name`, and `sic` fields.

**EDGAR Full-Text Search** — Per SEC's official FAQ, EIN can be searched directly: `https://www.sec.gov/edgar/search/#/q="74 2099724"&dateRange=all`.

### DUNS: not available in EDGAR

**DUNS numbers do not appear in EDGAR** — they are a proprietary Dun & Bradstreet identifier that the SEC does not collect. Your Mergent data (which contains DUNS) serves as the bridge. The mapping path is: **EDGAR CIK → EIN → your Mergent records → DUNS**. For entities not in Mergent, SAM.gov (Federal contractor registrations) contains both EIN and DUNS and could serve as a supplementary crosswalk for large employers.

### CIK lookup methods

| Method | Endpoint/File | Notes |
|--------|--------------|-------|
| By ticker | `https://www.sec.gov/cgi-bin/browse-edgar?CIK=AAPL&action=getcompany` | CIK field accepts tickers |
| By name | `https://www.sec.gov/cgi-bin/browse-edgar?company=APPLE&action=getcompany` | Prefix/starts-with search; append `&output=atom` for XML |
| By EIN | Parse `submissions.zip` and build your own EIN→CIK index | No direct EIN lookup endpoint exists |
| Bulk ticker mapping | `https://www.sec.gov/files/company_tickers.json` | ~10,000 entries: `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}` |
| Bulk with exchange | `https://www.sec.gov/files/company_tickers_exchange.json` | Adds exchange field |
| All entity names | `https://www.sec.gov/Archives/edgar/cik-lookup-data.txt` | ~13 MB, 500,000+ CIK-to-name records |

### Practical matching pipeline for your databases

Your realistic overlap: of **63,000+ unionized employers**, most are private, government, or nonprofit entities that don't file with the SEC. Expect **500–3,000 direct matches** among large public companies with unionized workforces (automakers, airlines, utilities, telecoms, healthcare, manufacturing, retail). Your **14,000 Mergent employers** will have much higher overlap — potentially **4,000–8,000 matches** since Mergent focuses on public companies.

The recommended four-step matching approach:

1. **Download `submissions.zip`** → parse all JSONs → extract CIK, name, EIN, tickers, SIC, addresses → load into PostgreSQL
2. **Direct EIN join**: Match your unionized employer EINs and Mergent EINs against EDGAR EINs. This is highest confidence
3. **Fuzzy name matching**: For unmatched records, normalize names (uppercase, remove INC/CORP/LLC suffixes, standardize "&" vs "AND") and use Jaro-Winkler or token-set-ratio matching. EDGAR uses "conformed names" in ALL CAPS with standardized abbreviations
4. **Subsidiary resolution**: For matched parent companies, parse Exhibit 21 to extract subsidiary names, then match those against your remaining unmatched unionized employers

---

## 4. SEC EDGAR API endpoints and bulk data access

### Full-Text Search System (EFTS)

**Endpoint**: `https://efts.sec.gov/LATEST/search-index` (POST with JSON body, or GET with URL parameters)

```python
import requests

headers = {"User-Agent": "MyResearchLab admin@mylab.edu"}
payload = {
    "q": "\"collective bargaining\"",
    "forms": ["10-K"],
    "category": "custom",
    "startdt": "2023-01-01",
    "enddt": "2025-12-31"
}
response = requests.post(
    "https://efts.sec.gov/LATEST/search-index",
    json=payload, headers=headers
)
results = response.json()  # hits.hits[] array with accession numbers, CIKs, dates
```

Key parameters: `q` (query text, supports exact phrases, Boolean `AND`/`OR`/`NOT`, `NEAR(n)` proximity), `forms` (array of form types), `startdt`/`enddt` (YYYY-MM-DD), `entityName` (company name or CIK). Covers filings since 2001. Returns up to 100 results per page.

### Company Submissions API

**Endpoint**: `https://data.sec.gov/submissions/CIK{10-digit-CIK}.json`

Returns company metadata (CIK, name, EIN, tickers, exchanges, SIC, addresses, fiscal year end) plus recent filings array (up to 1,000 entries with accession numbers, form types, dates, primary document filenames). Additional filing pages at `CIK{cik}-submissions-001.json`.

### XBRL APIs (three endpoints, all on data.sec.gov)

**Company Concept** — all values for one tag from one company over time:
```
https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/dei/EntityNumberOfEmployees.json
```
Returns array of facts with `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame` per observation.

**Company Facts** — every XBRL fact for one company in a single call:
```
https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
```

**Frames** — cross-company data for one concept at one point in time. **This is the most powerful endpoint for bulk labor research:**
```
https://data.sec.gov/api/xbrl/frames/dei/EntityNumberOfEmployees/pure/CY2024I.json
```
Returns employee counts for **thousands of companies** in a single request. Period formats: `CY2024` (annual duration), `CY2024Q4I` (point-in-time instant). Units: `pure` for counts, `USD` for monetary, `USD-per-shares` for per-share amounts.

### Bulk downloads

| Resource | URL | Size/Content |
|----------|-----|-------------|
| All XBRL company facts | `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` | All structured data, nightly update |
| All submissions metadata | `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` | All filer JSONs with EIN, nightly |
| Quarterly filing indexes | `https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{n}/master.idx` | Pipe-delimited: CIK, name, form, date, URL |
| Financial Statement Data Sets | `https://www.sec.gov/dera/data/financial-statement-data-sets.html` | Quarterly ZIPs with sub.txt (has EIN) |
| 13-F Data Sets | `https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets` | Quarterly institutional holdings |

### Rate limiting

**Hard limit: 10 requests/second** per IP address. Exceeding triggers a 403 block that persists until your rate drops below threshold for 10 minutes. **Required**: a descriptive `User-Agent` header in format `"CompanyName contact@email.com"`. Omitting it may classify you as an unclassified bot. No API keys or registration needed. Best practice: throttle to ~8 req/sec with `time.sleep(0.12)` between requests, enable gzip compression, and **use bulk downloads instead of per-entity API calls** whenever possible.

---

## 5. Corporate hierarchy from Exhibit 21 and 13-F

### Exhibit 21: subsidiary lists

Exhibit 21 ("Subsidiaries of the Registrant") is the primary source for mapping corporate hierarchies. Approximately **7,000 new Exhibit 21 filings per year**, with a historical archive of over **100,000 lists** dating back to 2003. The exhibit contains subsidiary legal names and state/country of incorporation — but **does not include subsidiary EINs, DUNS numbers, or ownership percentages** (some filers voluntarily include ownership percentages).

The critical challenge is format variability. **There is no standardized format** — Exhibit 21 appears as HTML tables, plain text lists, or occasionally PDFs. Column layouts, naming conventions, and hierarchical indentation differ across filers. The data is **not XBRL-tagged** despite lobbying by XBRL US for structured formatting.

**Parsing approaches and existing projects:**

- **CorpWatch API** (`github.com/michalgm/corpwatchapi`): The most comprehensive open-source parser. Built in Perl with MySQL, uses regex-based extraction achieving ~90% accuracy on subsidiary name/jurisdiction extraction. Covers companies from 2003 onward
- **sec-api.io Subsidiary API** (paid, $50–240/month): Uses ML algorithms for <0.1% error rate, provides pre-parsed JSON output searchable by parent or subsidiary name
- **Loughran-McDonald** (`sraf.nd.edu/data`): Free academic resource providing Stage One parsed 10-X filings with exhibits tagged as `<EX-21>...</EX-21>`

### 13-F filings: not useful for corporate hierarchy

**13-F filings show institutional investment manager holdings, not corporate ownership structures.** They document which hedge funds, mutual funds, and pension funds hold shares in publicly traded companies — portfolio positions, not parent-subsidiary relationships. For corporate hierarchy mapping, Exhibit 21 is the correct and only source within EDGAR.

13-F data includes: issuer name, CUSIP, FIGI (since 2023), market value, share count, and voting authority. Quarterly filings from managers with ≥$100M in qualifying assets. The XML Information Table has been mandatory since May 2013.

---

## 6. Python implementation patterns

### Library selection by use case

| Use Case | Best Library | Install |
|----------|-------------|---------|
| Bulk downloading filings | `sec-edgar-downloader` | `pip install sec-edgar-downloader` |
| Parsing 10-K sections + XBRL | `edgartools` | `pip install edgartools` |
| Building filing index databases | `python-edgar` | `pip install python-edgar` |
| Full research infrastructure | OpenEDGAR | Django + PostgreSQL + Celery + S3 |
| Pre-parsed data (paid) | sec-api.io | `pip install sec-api` |

### Bulk downloading filings

```python
from sec_edgar_downloader import Downloader

dl = Downloader("MyResearchLab", "admin@mylab.edu", "/data/sec_filings")

# Download all 10-K filings for a company
dl.get("10-K", "MSFT", after="2020-01-01", before="2025-12-31")

# Download by CIK
dl.get("10-K", "0000320193", limit=5)

# Download proxy statements
dl.get("DEF 14A", "AAPL", after="2022-01-01")
```

### Parsing 10-K sections with edgartools

```python
from edgar import Company, set_identity
set_identity("researcher@university.edu")

company = Company("AAPL")
tenk = company.get_filings(form="10-K").latest().obj()

# Access named sections directly
business = tenk["Item 1"]        # or tenk.business
risk_factors = tenk.risk_factors  # Item 1A
mda = tenk.management_discussion  # Item 7

# Access exhibits (for Exhibit 21)
filing = company.get_filings(form="10-K").latest()
for att in filing.attachments:
    if "21" in att.document or "subsidiar" in (att.description or "").lower():
        content = att.text()
        print(f"Exhibit 21: {att.document}")

# XBRL financial data as DataFrames
financials = company.get_financials()
balance_sheet = financials.balance_sheet()
income_stmt = financials.income_statement
```

### Direct XBRL API access for employee counts

```python
import requests
import time

HEADERS = {"User-Agent": "MyResearchLab admin@mylab.edu"}

def get_all_employee_counts(year=2024):
    """Get employee counts for ALL reporting companies in one API call."""
    url = f"https://data.sec.gov/api/xbrl/frames/dei/EntityNumberOfEmployees/pure/CY{year}I.json"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    print(f"Total companies reporting: {data['pts']}")
    return data['data']  # list of {cik, entityName, val, end, accn, loc}

def get_company_employee_history(cik):
    """Get historical employee counts for one company."""
    padded = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{padded}/dei/EntityNumberOfEmployees.json"
    resp = requests.get(url, headers=HEADERS)
    time.sleep(0.12)  # rate limiting
    return resp.json()['units']['pure']  # list of annual observations

def get_cba_expiration_dates(cik):
    """Get multiemployer plan CBA expiration dates (if reported)."""
    padded = str(cik).zfill(10)
    url = (f"https://data.sec.gov/api/xbrl/companyconcept/CIK{padded}/us-gaap/"
           f"MultiemployerPlanPensionSignificantCollectiveBargaining"
           f"ArrangementExpirationDate.json")
    resp = requests.get(url, headers=HEADERS)
    time.sleep(0.12)
    if resp.status_code == 200:
        return resp.json()
    return None
```

### Regex-based section extraction (for raw HTML 10-Ks)

```python
import re
from bs4 import BeautifulSoup

def extract_10k_sections(filing_url):
    """Extract Item 1, Item 1A, and Human Capital from raw 10-K HTML."""
    page = requests.get(filing_url, headers=HEADERS)
    soup = BeautifulSoup(page.content, "lxml")
    text = re.sub(r'\s+', ' ', soup.get_text())

    def extract_between(text, start_pat, end_pat):
        starts = [m.start() for m in start_pat.finditer(text)]
        ends = [m.start() for m in end_pat.finditer(text)]
        if not starts or not ends:
            return None
        best = None
        for s in starts:
            for e in ends:
                if s < e and (best is None or (e - s) > (best[1] - best[0])):
                    best = (s, e)
        return text[best[0]:best[1]] if best else None

    sections = {}
    sections['business'] = extract_between(
        text,
        re.compile(r"item\s*1\s*[\.;\:\-\_]*\s*\b", re.IGNORECASE),
        re.compile(r"item\s*1a\s*[\.;\:\-\_]*\s*risk|item\s*2\s*[\.;\:\-\_]*\s*(desc|prop)", re.IGNORECASE)
    )
    sections['risk_factors'] = extract_between(
        text,
        re.compile(r"(?<!,\s)item\s*1a[\.;\:\-\_]*\s*risk", re.IGNORECASE),
        re.compile(r"item\s*2\s*[\.;\:\-\_]*\s*(desc|prop)", re.IGNORECASE)
    )
    return sections

def extract_human_capital(business_text):
    """Extract Human Capital subsection from Item 1."""
    if not business_text:
        return None
    pattern = re.compile(
        r"(human\s+capital|our\s+employees|our\s+people|our\s+workforce)",
        re.IGNORECASE
    )
    match = pattern.search(business_text)
    if match:
        start = match.start()
        next_heading = re.search(
            r"\n\s*(item\s*\d|available\s+information|regulation|competition|seasonal)",
            business_text[start+100:], re.IGNORECASE
        )
        end = start + 100 + next_heading.start() if next_heading else len(business_text)
        return business_text[start:end]
    return None
```

### Building the CIK→EIN master table

```python
import json, zipfile, os

def build_cik_ein_mapping(submissions_zip_path):
    """Parse submissions.zip to create CIK→EIN mapping."""
    mapping = {}
    with zipfile.ZipFile(submissions_zip_path) as zf:
        for filename in zf.namelist():
            if filename.endswith('.json'):
                with zf.open(filename) as f:
                    data = json.load(f)
                    cik = data.get('cik')
                    ein = data.get('ein')
                    if cik and ein:
                        mapping[cik] = {
                            'ein': ein,
                            'name': data.get('name'),
                            'tickers': data.get('tickers', []),
                            'sic': data.get('sic'),
                            'state': data.get('stateOfIncorporation')
                        }
    return mapping  # ~800,000 entities
```

---

## 7. PostgreSQL schema for the labor relations platform

```sql
-- Core company table (populated from submissions.zip)
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(500) NOT NULL,
    ticker VARCHAR(20),
    ein VARCHAR(20),                    -- Employer Identification Number
    sic_code VARCHAR(4),
    state_of_incorporation VARCHAR(2),
    fiscal_year_end VARCHAR(4),         -- MMDD format
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_companies_cik ON companies(cik);
CREATE INDEX idx_companies_ein ON companies(ein);
CREATE INDEX idx_companies_ticker ON companies(ticker);

-- Filing metadata
CREATE TABLE filings (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    accession_number VARCHAR(25) UNIQUE NOT NULL,
    form_type VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,
    report_date DATE,
    fiscal_year INTEGER,
    fiscal_period VARCHAR(4),           -- FY, Q1, Q2, Q3, Q4
    primary_document VARCHAR(500),
    filing_url TEXT,
    is_xbrl BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_filings_company ON filings(company_id);
CREATE INDEX idx_filings_form ON filings(form_type);
CREATE INDEX idx_filings_date ON filings(filing_date);

-- Extracted text sections with full-text search
CREATE TABLE filing_sections (
    id SERIAL PRIMARY KEY,
    filing_id INTEGER REFERENCES filings(id),
    section_name VARCHAR(100) NOT NULL,  -- 'item_1', 'item_1a', 'human_capital'
    section_title VARCHAR(500),
    raw_text TEXT,
    word_count INTEGER,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(section_title,'')), 'A') ||
        setweight(to_tsvector('english', coalesce(raw_text,'')), 'B')
    ) STORED,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_sections_search ON filing_sections USING GIN(search_vector);

-- XBRL structured facts
CREATE TABLE xbrl_facts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    filing_id INTEGER REFERENCES filings(id),
    taxonomy VARCHAR(50),               -- us-gaap, dei, ecd
    concept VARCHAR(200) NOT NULL,
    numeric_value DECIMAL(20,4),
    text_value TEXT,
    unit VARCHAR(50),
    period_end DATE,
    instant_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_xbrl_concept ON xbrl_facts(concept);
CREATE INDEX idx_xbrl_company_concept ON xbrl_facts(company_id, concept);

-- Subsidiaries from Exhibit 21
CREATE TABLE subsidiaries (
    id SERIAL PRIMARY KEY,
    parent_company_id INTEGER REFERENCES companies(id),
    filing_id INTEGER REFERENCES filings(id),
    subsidiary_name VARCHAR(500) NOT NULL,
    subsidiary_name_normalized VARCHAR(500),
    jurisdiction VARCHAR(200),
    first_reported DATE,
    last_reported DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_subs_parent ON subsidiaries(parent_company_id);
CREATE INDEX idx_subs_name ON subsidiaries
    USING GIN(to_tsvector('english', subsidiary_name));

-- Labor-specific extracted data (denormalized for analytics)
CREATE TABLE labor_data (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    filing_id INTEGER REFERENCES filings(id),
    fiscal_year INTEGER,
    employee_count INTEGER,
    mentions_union BOOLEAN,
    mentions_cba BOOLEAN,
    mentions_strike BOOLEAN,
    human_capital_text TEXT,
    workforce_keywords JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_labor_keywords ON labor_data USING GIN(workforce_keywords);
```

Key schema design decisions: **EIN gets its own indexed column** on the companies table for direct joins against your unionized employer database. The `filing_sections` table uses PostgreSQL's **generated tsvector column with GIN index** for efficient full-text search across extracted 10-K text. The `labor_data` table is deliberately denormalized — boolean flags for union/CBA/strike mentions enable fast analytical queries, while the JSONB `workforce_keywords` column stores flexible extracted metrics. Use `to_tsvector` GIN indexes on subsidiary names to enable fuzzy text matching against your employer database.

## Conclusion

The most valuable first steps for your platform are: **(1)** download `submissions.zip` to build the CIK↔EIN master mapping and immediately join against your 63,000+ unionized employers; **(2)** use the Frames API endpoint for `EntityNumberOfEmployees` to get employee counts for thousands of companies in a single call; **(3)** use EFTS to search for "collective bargaining", "labor union", and "work stoppage" across all 10-K filings since 2001. The `edgartools` Python library is the strongest choice for parsing 10-K sections and accessing XBRL data programmatically, while `sec-edgar-downloader` handles bulk file retrieval. The biggest gap in EDGAR for labor research is the **lack of structured Exhibit 21 data** — subsidiary parsing remains a regex/NLP challenge with ~90% accuracy using open-source tools like CorpWatch. The `MultiemployerPlanPensionSignificantCollectiveBargainingArrangementExpirationDate` XBRL tag is an underutilized gem that provides structured CBA expiration dates for companies participating in multiemployer pension plans.