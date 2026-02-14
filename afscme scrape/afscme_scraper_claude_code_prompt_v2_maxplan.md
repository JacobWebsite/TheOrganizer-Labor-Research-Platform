# Claude Code Prompt: Build AFSCME Union Website Scraper (Max Plan Architecture)

## Context

I'm building a labor relations research platform. The database is PostgreSQL (`olms_multiyear`) running locally. I already have a FastAPI backend and 207+ tables with union and employer data.

I need a scraper that visits AFSCME union websites and extracts structured data that doesn't exist in government databases — especially employer names, membership counts, contract info, and organizing news.

## Architecture: Two-Step (Fetch → Extract)

**Important: This scraper does NOT call the Claude API directly.** Instead, it works in two steps:

1. **Crawl4AI fetches pages and saves raw text** — no AI involved, just downloading and cleaning webpages
2. **You (Claude Code) read the raw text and extract structured data** — using your own intelligence, which runs on the user's Max plan subscription at no extra cost

This means the scraper script handles web fetching, rate limiting, and database storage. Claude Code handles the AI extraction by reading saved text and writing structured results to the database.

## Phase 1: Directory Scrape (Already Done)

I already have a CSV file called `afscme_national_directory.csv` with 295 entries scraped from AFSCME's national "Find Your Local" directory (`https://www.afscme.org/local/{state}` for all 52 states/territories). This includes 112 entries with website URLs that we'll follow in Phase 2.

## Phase 2: Deep Scrape and Extract

### Step A: Fetch raw pages (automated script)

Use Crawl4AI to visit each of the 112+ council/local websites found in Phase 1. For each site:
- Visit the homepage, about page, and any contracts/news pages
- Save the full cleaned text (markdown format) to the database
- Log success/failure in the `scrape_jobs` table
- Do NOT attempt any AI extraction — just save raw text

### Step B: AI extraction (Claude Code does this)

After fetching, Claude Code reads the saved raw text from the database and extracts:
- Membership counts
- Employers represented
- Contracts/CBAs mentioned
- Recent organizing news
- Council/district structure
- Contact info (address, phone, email)

Claude Code writes the structured results to the appropriate database tables.

This two-step approach means:
- The fetch script can run unattended (no API key needed)
- AI extraction happens in Claude Code at no extra cost (Max plan)
- If extraction quality is bad, we can re-extract from saved text without re-scraping
- We can adjust extraction prompts and retry without hitting any websites again

## Technical Requirements

### Tool: Crawl4AI
- Install: `pip install crawl4ai && crawl4ai-setup`
- Uses Playwright internally (headless browser)
- Use it ONLY for fetching pages — not for AI extraction
- Save output as clean markdown text

### Database Connection
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

### Database Tables to Create

Create these tables in the `olms_multiyear` database. They store web-sourced data SEPARATELY from government data.

```sql
CREATE TABLE web_union_profiles (
    id SERIAL PRIMARY KEY,
    f_num VARCHAR,
    union_name VARCHAR NOT NULL,
    local_number VARCHAR,
    parent_union VARCHAR DEFAULT 'AFSCME',
    state VARCHAR(50),
    website_url TEXT,
    platform VARCHAR,
    raw_text TEXT,
    raw_text_about TEXT,
    raw_text_contracts TEXT,
    raw_text_news TEXT,
    extra_data JSONB,
    last_scraped TIMESTAMP,
    scrape_status VARCHAR DEFAULT 'PENDING',
    match_status VARCHAR DEFAULT 'PENDING_REVIEW',
    section VARCHAR,
    source_directory_url TEXT,
    officers TEXT,
    address TEXT,
    phone VARCHAR,
    fax VARCHAR,
    email VARCHAR,
    facebook TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE web_union_employers (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    employer_name VARCHAR NOT NULL,
    employer_name_clean VARCHAR,
    state VARCHAR(2),
    sector VARCHAR,
    source_url TEXT,
    extraction_method VARCHAR,
    confidence_score DECIMAL,
    matched_employer_id INTEGER,
    match_status VARCHAR DEFAULT 'PENDING_REVIEW',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE web_union_contracts (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    contract_title VARCHAR,
    employer_name VARCHAR,
    contract_url TEXT,
    expiration_date DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE web_union_news (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    headline VARCHAR,
    summary TEXT,
    news_type VARCHAR,
    date_published DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE web_union_membership (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    member_count INTEGER,
    member_count_source VARCHAR,
    count_type VARCHAR,
    as_of_date DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE scrape_jobs (
    id SERIAL PRIMARY KEY,
    tool VARCHAR DEFAULT 'UNION_SCRAPER',
    target_url TEXT NOT NULL,
    target_entity_type VARCHAR,
    web_profile_id INTEGER,
    status VARCHAR DEFAULT 'QUEUED',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    pages_scraped INTEGER DEFAULT 0,
    pages_found TEXT[],
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds DECIMAL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Matching Against Existing Data

After extraction, match each union against `unions_master` (26,665 records):
- Match on parent union abbreviation (AFSCME) + local_number + state
- `unions_master` columns: `f_num`, `union_name`, `abbr`, `local_number`, `state`
- If matched: set `f_num` and `match_status` = 'MATCHED_OLMS'
- If no match: set `match_status` = 'UNMATCHED'

For employers, match against `unified_employers_osha` (100,768 records) and `mv_employer_search` (120,169 records) using fuzzy name + state matching.

## Build Instructions — Use Checkpoints

### Checkpoint 1: Setup and Data Load
1. Install Crawl4AI: `pip install crawl4ai && crawl4ai-setup`
2. Create all database tables
3. Load `afscme_national_directory.csv` into `web_union_profiles`
4. Run OLMS matching against `unions_master`
5. **STOP and show me:** Match counts, samples, total with website URLs

### Checkpoint 2: Fetch Script (No AI)
Build `fetch_union_sites.py` that:
1. Reads `web_union_profiles` with status='PENDING' and non-null `website_url`
2. Uses Crawl4AI to fetch homepage → save markdown to `raw_text`
3. Discovers common pages: /about, /about-us, /contracts, /news, /blog
4. Checks for WordPress (`/wp-json/wp/v2/`) → note in `platform`
5. Saves page text to appropriate `raw_text_*` columns
6. Rate limiting: 1 req/sec, 2-sec domain cooldown
7. Respects robots.txt, 30-sec timeout, 3 retries with backoff
8. User-Agent: `LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)`
9. Logs in `scrape_jobs`, updates `scrape_status` to 'FETCHED' or 'FAILED'
10. **Test on 5 sites first, STOP and show me results**

### Checkpoint 3: AI Extraction (Claude Code)
Build `extract_union_data.py` helper that:
1. Reads raw_text for a given web_profile_id and prints it
2. Accepts structured JSON input and writes to correct tables
3. Updates `scrape_status` to 'EXTRACTED'

Workflow: Claude Code reads text → extracts data → provides JSON → script inserts into DB

**Process in batches of 10, STOP after each batch for review**

### Checkpoint 4: Match and Summarize
1. Run OLMS matching on extracted data
2. Run employer matching against existing database
3. **STOP and show full summary**

## Configuration Notes

- Rate Limiting: 1 req/sec per domain, 2-sec cooldown between domains
- Retries: 3x with exponential backoff (2s, 4s, 8s)
- Robots.txt: Always respect
- Timeout: 30 seconds per page
- WordPress Detection: Check `/wp-json/wp/v2/` first

## Review Output Format

```
=== AFSCME DC 37 (New York) [id: 42] ===
URL: https://www.dc37.net
OLMS Match: f_num=543210 (MATCHED)
Pages Fetched: 3 (homepage, about, contracts)
Text Saved: 12,450 characters

EMPLOYERS FOUND:
  - City of New York [confidence: 0.95, method: about_page, sector: PUBLIC_LOCAL]
  - NYC Health + Hospitals [confidence: 0.85, method: contract_page, sector: PUBLIC_LOCAL]

CONTRACTS:
  - "2024-2027 Economic Agreement" [employer: City of New York, expires: 2027-03-31]

MEMBERSHIP: ~150,000 (stated on homepage)

NEWS:
  - "DC 37 Ratifies New Contract" [type: contract_ratification, date: 2025-09-15]
```

## Important Notes

- RESEARCH tool for ACADEMIC platform. Be ethical with scraping.
- Store ALL raw text for re-extraction without re-scraping.
- Never mix web data with government data (separate `web_` tables).
- Fetch step = normal script. Extract step = Claude Code (free on Max plan).
- Review-first: show batches before committing to full runs.
- If site is down, log and move on.
