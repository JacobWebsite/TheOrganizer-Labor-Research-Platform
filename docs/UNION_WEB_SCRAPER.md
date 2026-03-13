# Union Web Scraper Documentation

Consolidated reference for the union website scraping pipeline. Covers architecture, database schema, scripts, extraction logic, matching, and expansion plans.

**Status:** AFSCME prototype complete. 295 profiles loaded, 103 websites scraped, 160 employers extracted. Not yet expanded to other unions.

**Roadmap task:** 8-3 (Expand Union Web Scraper)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Database Schema](#2-database-schema)
3. [Pipeline Stages](#3-pipeline-stages)
4. [Crawl4AI Configuration](#4-crawl4ai-configuration)
5. [Extraction Logic](#5-extraction-logic)
6. [Quality Fixes](#6-quality-fixes)
7. [Employer Matching](#7-employer-matching)
8. [AFSCME Prototype Results](#8-afscme-prototype-results)
9. [Research Agent Integration](#9-research-agent-integration)
10. [Known Issues and Limitations](#10-known-issues-and-limitations)
11. [Expansion Plan](#11-expansion-plan)
12. [Commands Reference](#12-commands-reference)
13. [File Inventory](#13-file-inventory)

---

## 1. Architecture Overview

The scraper is a 6-stage sequential pipeline that discovers union local websites, fetches their content, extracts structured data (employers, contracts, membership counts, news), cleans it, and matches extracted employers against existing database records.

```
Stage 1: Setup          Stage 2: Fetch           Stage 3: Extract
CSV directory    -->    Crawl4AI browser    -->   Regex heuristics +
  |                       |                       manual JSON insertion
  v                       v                       |
web_union_profiles      raw_text fields           v
(295 rows)              (homepage, about,       web_union_employers (160)
                         contracts, news)       web_union_contracts (120)
                                                web_union_membership (31)
                                                web_union_news (183)

Stage 4: Fix             Stage 5: Match          Stage 6: Export
Boilerplate filter  -->  5-tier cascade    -->   Interactive HTML
False positive           against F7 + OSHA       dashboard
removal                    |
                           v
                         match_status updated
                         (MATCHED_* or UNMATCHED)
```

**Pipeline manifest entry** (`.claude/specs/pipeline-manifest.md`, line 94-96):
```
Stage 5: Web Scraping
Sequential: setup_afscme_scraper -> fetch_union_sites -> extract_union_data
            -> fix_extraction -> match_web_employers -> export_html
```

---

## 2. Database Schema

Six tables in `olms_multiyear`, all created by `scripts/etl/setup_afscme_scraper.py`.

### web_union_profiles (295 rows)

Primary table. One row per union local website. Stores both directory metadata (from CSV) and scraped content (raw markdown).

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Auto-increment |
| `f_num` | VARCHAR | OLMS file number (linked via OLMS matching) |
| `union_name` | VARCHAR NOT NULL | Full union local name |
| `local_number` | VARCHAR | Extracted local/council number |
| `parent_union` | VARCHAR | Always 'AFSCME' for now |
| `state` | VARCHAR(50) | 2-letter state abbreviation |
| `website_url` | TEXT | Union local website URL |
| `platform` | VARCHAR | Detected CMS ('WordPress' or NULL) |
| `raw_text` | TEXT | Homepage markdown (Crawl4AI output) |
| `raw_text_about` | TEXT | About page markdown |
| `raw_text_contracts` | TEXT | Contracts/CBA page markdown |
| `raw_text_news` | TEXT | News/blog page markdown |
| `extra_data` | JSONB | Reserved for future use |
| `last_scraped` | TIMESTAMP | When the website was last fetched |
| `scrape_status` | VARCHAR | PENDING, FETCHED, EXTRACTED, FAILED, NO_WEBSITE |
| `match_status` | VARCHAR | MATCHED_OLMS, MATCHED_OLMS_CROSS_STATE, UNMATCHED, NO_LOCAL_NUMBER, PENDING_REVIEW |
| `section` | VARCHAR | AFSCME directory section (e.g. 'contracts') |
| `source_directory_url` | TEXT | URL of the AFSCME directory page |
| `officers` | TEXT | Officers from AFSCME directory |
| `address` | TEXT | Address from AFSCME directory |
| `phone` | VARCHAR | Phone from directory |
| `fax` | VARCHAR | Fax from directory |
| `email` | VARCHAR | Email from directory |
| `facebook` | TEXT | Facebook URL from directory |
| `created_at` | TIMESTAMP | Row creation time |

### web_union_employers (160 rows)

Employers extracted from union website text. One row per employer mention per union profile.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `web_profile_id` | INTEGER FK | References `web_union_profiles(id)` |
| `employer_name` | VARCHAR NOT NULL | Raw employer name as found on website |
| `employer_name_clean` | VARCHAR | Cleaned/normalized name |
| `state` | VARCHAR(2) | Employer state (inherited from profile) |
| `sector` | VARCHAR | PUBLIC_LOCAL, PUBLIC_STATE, PUBLIC_EDUCATION, HEALTHCARE, PUBLIC_FEDERAL, NONPROFIT, or NULL |
| `source_url` | TEXT | Website URL the employer was found on |
| `extraction_method` | VARCHAR | 'auto_extract', 'auto_extract_v2', 'manual', 'ai_batch1', etc. |
| `confidence_score` | DECIMAL | 0.0-1.0 extraction confidence |
| `matched_employer_id` | INTEGER | F7 employer_id if matched |
| `match_status` | VARCHAR | MATCHED_F7_EXACT, MATCHED_F7_FUZZY, MATCHED_OSHA_EXACT, MATCHED_OSHA_FUZZY, MATCHED_F7_CROSS_STATE, UNMATCHED, PENDING_REVIEW |
| `created_at` | TIMESTAMP | |

### web_union_contracts (120 rows)

Contracts and CBA references extracted from union websites.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `web_profile_id` | INTEGER FK | References `web_union_profiles(id)` |
| `contract_title` | VARCHAR | Contract name/title (e.g. "2024-2027 Agreement") |
| `employer_name` | VARCHAR | Employer the contract covers (if identifiable) |
| `contract_url` | TEXT | Direct URL to contract PDF (if found) |
| `expiration_date` | DATE | Contract expiration date (if parseable) |
| `source_url` | TEXT | Website URL the contract was found on |
| `created_at` | TIMESTAMP | |

### web_union_news (183 rows)

News items and blog posts extracted from union websites.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `web_profile_id` | INTEGER FK | References `web_union_profiles(id)` |
| `headline` | VARCHAR | News headline |
| `summary` | TEXT | Brief summary (if available) |
| `news_type` | VARCHAR | 'organizing', 'contract', 'action', 'general' |
| `date_published` | DATE | Publication date (if parseable) |
| `source_url` | TEXT | Source website URL |
| `created_at` | TIMESTAMP | |

### web_union_membership (31 rows)

Membership counts extracted from union website text.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `web_profile_id` | INTEGER FK | References `web_union_profiles(id)` |
| `member_count` | INTEGER | Number of members claimed |
| `member_count_source` | VARCHAR | 'website', 'auto_extract', etc. |
| `count_type` | VARCHAR | 'stated' (exact) or 'approximate' ("over", "nearly") |
| `as_of_date` | DATE | Date the count applies to (rarely available) |
| `source_url` | TEXT | |
| `created_at` | TIMESTAMP | |

### scrape_jobs (112 rows)

Job tracking for web scraping operations. One row per fetch attempt.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `tool` | VARCHAR | Default 'UNION_SCRAPER' |
| `target_url` | TEXT NOT NULL | URL being scraped |
| `target_entity_type` | VARCHAR | 'UNION_LOCAL' |
| `web_profile_id` | INTEGER | Profile being scraped |
| `status` | VARCHAR | QUEUED, IN_PROGRESS, COMPLETED, FAILED |
| `error_message` | TEXT | Error detail on failure |
| `retry_count` | INTEGER | Number of retries attempted |
| `pages_scraped` | INTEGER | Pages successfully fetched |
| `pages_found` | TEXT[] | Array of discovered page URLs |
| `started_at` | TIMESTAMP | |
| `completed_at` | TIMESTAMP | |
| `duration_seconds` | DECIMAL | Total scrape time |
| `created_at` | TIMESTAMP | |

---

## 3. Pipeline Stages

### Stage 1: Setup (`scripts/etl/setup_afscme_scraper.py`)

Creates all 6 database tables and loads union profile data from a CSV directory file.

**Input:** `afscme scrape/afscme_national_directory.csv` -- exported from the AFSCME national local directory website. Contains union name, state, website URL, officers, address, phone, email, facebook, and section.

**What it does:**
1. Creates tables (idempotent `CREATE IF NOT EXISTS`)
2. Loads CSV rows into `web_union_profiles` (skips if already loaded)
3. Extracts `local_number` from union name via regex (patterns: "Local 52", "Council 4", "Chapter 97", "District Council 12")
4. Converts full state names to 2-letter abbreviations
5. Sets `scrape_status = 'PENDING'` if website URL exists, else `'NO_WEBSITE'`
6. Matches profiles against `unions_master` (OLMS) by affiliation='AFSCME' + local_number + state
   - Single match: `MATCHED_OLMS`
   - Multiple matches: picks highest membership, `MATCHED_OLMS`
   - No state match but single local-number match: `MATCHED_OLMS_CROSS_STATE`
   - No match: `UNMATCHED`
   - No local number parsed: `NO_LOCAL_NUMBER`

**Command:**
```bash
py scripts/etl/setup_afscme_scraper.py
```

### Stage 2: Fetch (`scripts/scraper/fetch_union_sites.py`)

Crawls union websites using Crawl4AI and stores raw markdown text.

**Input:** Profiles with `scrape_status = 'PENDING'` and `website_url IS NOT NULL`.

**What it does per profile:**
1. Creates a `scrape_jobs` row with `status = 'IN_PROGRESS'`
2. Fetches the homepage (required -- failure here aborts the profile)
3. Checks for WordPress by probing `/wp-json/wp/v2/`
4. Discovers subpages by probing common paths:
   - `/about`, `/about-us` (categorized as 'about')
   - `/contracts`, `/collective-bargaining` (categorized as 'contracts')
   - `/news`, `/blog` (categorized as 'news')
   - `/members`, `/membership` (categorized as 'other')
5. A subpage is kept only if it returns 200+ chars of content, and only the first match per type is saved
6. Updates `web_union_profiles` with raw markdown in `raw_text`, `raw_text_about`, `raw_text_contracts`, `raw_text_news`
7. Sets `scrape_status = 'FETCHED'` on success, `'FAILED'` on error
8. Updates `scrape_jobs` with page counts, URLs found, duration, and status

**Commands:**
```bash
py -u scripts/scraper/fetch_union_sites.py             # fetch all PENDING
py -u scripts/scraper/fetch_union_sites.py --limit 5   # test run (first 5)
py -u scripts/scraper/fetch_union_sites.py --id 42     # fetch specific profile
```

### Stage 3: Extract (`scripts/scraper/extract_union_data.py`)

Extracts structured data from raw markdown text. Supports three modes: manual reading, JSON insertion, and heuristic auto-extraction.

**Modes:**

**Read mode** -- prints raw text for manual analysis:
```bash
py scripts/scraper/extract_union_data.py --read 42          # single profile
py scripts/scraper/extract_union_data.py --read-batch 10    # next 10 summaries
```

**Insert mode** -- inserts structured JSON (from AI or manual analysis):
```bash
py scripts/scraper/extract_union_data.py --insert data.json
```

Expected JSON format:
```json
{
  "profile_id": 42,
  "employers": [
    {"employer_name": "City of New York", "sector": "PUBLIC_LOCAL",
     "confidence": 0.9, "method": "about_page"}
  ],
  "contracts": [
    {"contract_title": "2024-2027 CBA", "employer_name": "City of NY",
     "expiration_date": "2027-03-31", "contract_url": null}
  ],
  "membership": [
    {"member_count": 150000, "source": "homepage", "count_type": "stated"}
  ],
  "news": [
    {"headline": "New Contract Ratified", "news_type": "contract",
     "date_published": "2025-09-15", "summary": "..."}
  ]
}
```

**Auto-extract mode** -- runs regex heuristics on all FETCHED profiles:
```bash
py scripts/scraper/extract_union_data.py --auto-extract
```

Sets `scrape_status = 'EXTRACTED'` after processing each profile (even if nothing found).

**Extraction heuristics (4 types):**

*Employers* -- 6 regex patterns:
- "employees of the [employer]"
- "representing workers at [employer]"
- "bargaining unit at [employer]"
- "contract with [employer]"
- "employed by [employer]"
- "work for [employer]"

*Membership* -- 7 regex patterns:
- "[N] members", "representing [N] workers", "more than [N] members"
- "over [N] members", "approximately [N] members", "nearly [N] members"
- "union of [N]"
- Range filter: 10 <= count <= 5,000,000

*Contracts* -- 3 regex patterns + PDF link extraction:
- "2024-2027 Contract/CBA/Agreement"
- "Contract expires [date/year]"
- "Collective Bargaining Agreement" standalone
- Markdown links to `.pdf` files with contract/agreement/CBA in text

*News* -- heading + date pattern matching:
- Finds markdown headings (`## Headline`) that contain labor keywords (ratify, strike, contract, negotiate, elect, organize, rally, etc.)
- Looks for nearby date patterns ("January 15, 2024")
- Classifies: contract, action, organizing, general
- Caps at 5 items per profile

### Stage 4: Fix (`scripts/scraper/fix_extraction.py`)

Quality filtering to remove false positives from auto-extraction.

**What it does:**

1. **Boilerplate detection:** Counts employer-name mentions across all profiles. Any phrase appearing in 5+ profiles is flagged as shared sidebar/footer text and excluded. Deletes all `extraction_method = 'auto_extract'` rows and re-runs with boilerplate filter as `'auto_extract_v2'`.

2. **Membership false positive removal:**
   - Deletes counts that match the union's own local number (e.g., Local 123 with count=123)
   - Deletes year-like values (2018-2030)
   - Deletes suspiciously small counts (<50, likely page artifacts)

3. **Sector classification** (in `guess_sector()` and `extract_employers_v2()`):
   - "City of X", "County of X" -> `PUBLIC_LOCAL`
   - "State of X", "Department of" -> `PUBLIC_STATE`
   - "University", "School District" -> `PUBLIC_EDUCATION`
   - "Hospital", "Health" -> `HEALTHCARE`
   - "Federal", "U.S." -> `PUBLIC_FEDERAL`

**Command:**
```bash
py scripts/scraper/fix_extraction.py
```

### Stage 5: Match (`scripts/scraper/match_web_employers.py`)

Matches extracted employers against existing F7 and OSHA records using a 5-tier cascade.

| Tier | Method | Target Table | Threshold | Status Value |
|------|--------|-------------|-----------|--------------|
| 1 | Exact name+state | `f7_employers_deduped` | Exact match | `MATCHED_F7_EXACT` |
| 1b | Exact aggressive name+state | `f7_employers_deduped` | Exact on `employer_name_aggressive` | `MATCHED_F7_EXACT` |
| 2 | Exact name+state | `osha_establishments` | Exact match | `MATCHED_OSHA_EXACT` |
| 3 | Fuzzy name+state | `f7_employers_deduped` | pg_trgm >= 0.55 | `MATCHED_F7_FUZZY` |
| 4 | Fuzzy name+state | `osha_establishments` | pg_trgm >= 0.55 | `MATCHED_OSHA_FUZZY` |
| 5 | Fuzzy name only (cross-state) | `f7_employers_deduped` | pg_trgm >= 0.70 | `MATCHED_F7_CROSS_STATE` |

Falls through tiers in order. First match wins. Unmatched employers get `match_status = 'UNMATCHED'`.

**Command:**
```bash
py scripts/scraper/match_web_employers.py
```

**Output:** Prints each match decision and a summary with counts per tier, full data inventory, matched employers with F7 links, and unmatched employers (potential new discoveries).

### Stage 6: Export (`scripts/scraper/export_html.py`)

Generates a single interactive HTML file with 6 tabs (Profiles, Employers, Contracts, Membership, News, Scrape Jobs). Tables are searchable with status color-coding and links to source websites.

**Command:**
```bash
py scripts/scraper/export_html.py
```

---

## 4. Crawl4AI Configuration

### Browser Config
```python
BrowserConfig(
    headless=True,
    user_agent="LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)"
)
```

### Run Config
```python
CrawlerRunConfig(
    page_timeout=30000,          # 30 seconds per page
    wait_until="domcontentloaded",
    cache_mode=CacheMode.BYPASS, # No caching
    check_robots_txt=True,       # Respect robots.txt
    verbose=False
)
```

### Rate Limiting
| Parameter | Value | Purpose |
|-----------|-------|---------|
| `RATE_LIMIT_SECS` | 1.0s | Between requests to same domain |
| `DOMAIN_COOLDOWN_SECS` | 2.0s | Between switching to a different domain |
| `MAX_RETRIES` | 3 | Retry attempts on failure |
| `RETRY_BACKOFF` | [2, 4, 8] seconds | Exponential backoff |

### WordPress Detection
Probes `/wp-json/wp/v2/` after fetching homepage. If response contains "namespace", "wp/v2", or "routes", platform is set to `'WordPress'`.

### Subpage Discovery
Probes these paths (first successful match per category wins):

| Category | Paths Probed |
|----------|-------------|
| about | `/about`, `/about-us` |
| contracts | `/contracts`, `/collective-bargaining` |
| news | `/news`, `/blog` |
| other | `/members`, `/membership` |

A subpage is only saved if it returns >200 chars of content.

### Windows Compatibility

Crawl4AI prints Unicode arrows during browser initialization that crash Windows cp1252 stdout. The research agent's `scrape_employer_website` tool handles this by redirecting stdout/stderr to UTF-8 during `asyncio.run()`:

```python
import io, sys
_orig_stdout, _orig_stderr = sys.stdout, sys.stderr
try:
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="replace")
    result = asyncio.run(...)
finally:
    sys.stdout, sys.stderr = _orig_stdout, _orig_stderr
```

The `fetch_union_sites.py` script uses `py -u` (unbuffered) flag but does NOT apply this redirect -- it works because the scraper itself doesn't trigger the same Unicode output as the research agent's broader Crawl4AI usage. If Unicode errors occur, add the redirect pattern.

---

## 5. Extraction Logic

### Current Approach: Regex + Manual JSON

Extraction uses two complementary approaches:

**Heuristic auto-extraction** (`--auto-extract`): Regex patterns scan raw markdown for employer names, membership counts, contract references, and news headlines. Fast but low precision -- produces false positives that Stage 4 (fix) must clean up.

**Manual/AI JSON insertion** (`--insert data.json`): Human or AI reads the raw text (via `--read` mode), produces structured JSON, and inserts it. Higher quality but doesn't scale.

The AFSCME prototype used both: auto-extraction for a first pass, then manual correction via JSON files (`ai_employers_batch1.json`, `ai_employers_batch2.json`, `manual_employers.json`, `manual_employers_2.json`).

### Extraction Quality

The v2 extractor (`fix_extraction.py`) improves on v1 with:
- Boilerplate phrase filtering (cross-profile frequency analysis)
- Skip words list (union-related terms that aren't employer names)
- Local number filtering (avoids extracting the union's own identifier)
- Confidence scoring by pattern (0.7-0.8 depending on pattern specificity)

### Biggest Bottleneck

Regex extraction is the weakest link. It catches obvious patterns ("employees of the City of Philadelphia") but misses:
- Employer names in unstructured prose without trigger phrases
- Names embedded in lists, tables, or navigation elements
- Employers mentioned only by abbreviation or informal name
- Non-English content (e.g., Puerto Rico council sites in Spanish)

---

## 6. Quality Fixes

Implemented in `fix_extraction.py`, run after extraction:

| Fix | What It Does | Why |
|-----|-------------|-----|
| Boilerplate filter | Deletes employer names appearing in 5+ profiles | Shared sidebar/footer text (e.g., national AFSCME campaign mentions) |
| Local number filter | Skips employer names containing the union's own local number | "Local 123" gets extracted as an employer otherwise |
| Year filter | Deletes membership counts 2018-2030 | Years get parsed as member counts |
| Small count filter | Deletes membership counts <50 | Page numbers, list indices, etc. |
| Article stripping | Removes leading "the", "a", "an" from employer names | "the City of Philadelphia" -> "City of Philadelphia" |

---

## 7. Employer Matching

### Matching vs. Platform's Main Matching Pipeline

The scraper's matching (`match_web_employers.py`) is separate from the platform's main deterministic matcher (`scripts/matching/run_deterministic.py`). Key differences:

| Aspect | Main Pipeline | Scraper Pipeline |
|--------|--------------|-----------------|
| Input | Source tables (OSHA, WHD, SAM, etc.) | `web_union_employers` |
| Output | `unified_match_log` | Updates `web_union_employers.match_status` |
| Tiers | 6-tier cascade (EIN, name+city+state, fuzzy, etc.) | 5-tier cascade (exact name+state, fuzzy) |
| Fuzzy engine | RapidFuzz (Python) | pg_trgm (PostgreSQL) |
| Threshold | 0.75-1.0 | 0.55-0.70 |
| Volume | Millions of records | 160 records |

The lower fuzzy threshold (0.55) is acceptable here because the scraper context provides additional confirmation -- we know the employer is associated with a specific AFSCME local, which constrains the match space.

### pg_trgm Usage Note

The `match_web_employers.py` script uses `%%` escaping for the pg_trgm `%` operator because psycopg2 interprets `%` as parameter placeholders. The script works around this with `.replace('%%s', '%s').replace('%%%%', '%%')` -- ugly but functional.

---

## 8. AFSCME Prototype Results

### Data Source
AFSCME national directory CSV, scraped from `afscme.org`. Contains 295 local/council profiles across all 50 states + DC + PR.

### Pipeline Results

| Metric | Count |
|--------|-------|
| Profiles loaded | 295 |
| With website URL | ~200 |
| Successfully scraped | 103 |
| Failed scrapes | 9 |
| Remaining (not yet attempted) | ~88 |
| Employers extracted | 160 |
| Contracts extracted | 120 |
| Membership counts | 31 |
| News items | 183 |
| Scrape jobs logged | 112 |

### Notable Councils Captured

| Council | State | Employers Found | Key Employers |
|---------|-------|----------------|---------------|
| DC47 | PA | 11 | City of Philadelphia, UPenn, Temple U, Philadelphia Zoo |
| DC37 | NY | 2 | NYC, CUNY |
| Council 28 | WA | 14 | WA State agencies, UW, WSU, Prisons |
| Council 66 | NY | 3 | Erie County, Rochester City, School District |
| Council 95 | PR | 6 | PR government departments |

### Sector Distribution

Most extracted employers are public sector (expected for AFSCME):
- `PUBLIC_LOCAL`: City/county/town governments
- `PUBLIC_STATE`: State agencies
- `PUBLIC_EDUCATION`: Universities, school districts
- `HEALTHCARE`: Hospitals, medical centers
- `PUBLIC_FEDERAL`: Federal agencies (rare for AFSCME)

---

## 9. Research Agent Integration

The research agent (`scripts/research/tools.py`) has a separate but related scraping capability:

### `scrape_employer_website` Tool

Scrapes individual employer websites (not union websites) as part of research dossier generation. Uses the same Crawl4AI framework but with a different page strategy.

**Page types scraped** (with character budgets):
| Page | Paths | Budget |
|------|-------|--------|
| homepage | `/` | 3,000 chars |
| about | `/about`, `/about-us`, `/company`, `/our-story` | 2,500 chars |
| careers | `/careers`, `/jobs`, `/work-with-us` | 1,500 chars |
| news | `/news`, `/press`, `/newsroom`, `/media` | 1,000 chars |
| locations | `/locations`, `/offices`, `/stores`, `/branches` | 1,000 chars |
| contact | `/contact`, `/contact-us` | 1,000 chars |
| investors | `/investors`, `/investor-relations` | 1,500 chars |

**4-tier URL resolution:**
1. URL provided directly
2. Mergent database lookup via `employer_id` -> `unified_match_log` -> `mergent_employers.website`
3. Mergent name+state search
4. Google Search fallback (via Gemini grounding, `RESEARCH_SCRAPER_GOOGLE_FALLBACK=true`)

**Key difference from union scraper:** The research tool scrapes one employer at a time during a research run. The union scraper batch-processes hundreds of union websites in sequence.

---

## 10. Known Issues and Limitations

### Scraper Issues

| Issue | Impact | Workaround |
|-------|--------|-----------|
| Regex extraction misses most employers | ~60% of employer mentions go uncaught | Manual JSON insertion or AI extraction |
| No JavaScript rendering for SPAs | Some modern union sites return empty HTML | Crawl4AI uses browser rendering but some sites still fail |
| No login/authentication handling | Password-protected member areas inaccessible | Only public pages scraped |
| No pagination handling | News/blog archives beyond page 1 missed | Only first page of news captured |
| No PDF content extraction | Contract PDFs linked but not parsed | CBA pipeline (`scripts/cba/`) exists but isn't wired in |
| Puerto Rico sites in Spanish | Regex patterns are English-only | Manual extraction needed |
| 192 profiles not yet scraped | 65% of AFSCME profiles still PENDING | Run `fetch_union_sites.py` to continue |

### Platform Issues

| Issue | Impact | Fix |
|-------|--------|-----|
| `web_union_*` tables not used by API | Scraped data not visible in frontend | Need API endpoints for web-sourced data |
| No scheduled re-scraping | Data goes stale | Need cron/scheduler for quarterly refresh |
| `parent_union` hardcoded to 'AFSCME' | Can't distinguish unions after expansion | Add parent_union parameter to setup script |
| Scraper matching separate from main pipeline | Matched employers don't flow into `unified_match_log` | Need bridge script |

---

## 11. Expansion Plan

### Adding a New Union Federation

To add a new union (e.g., SEIU), the process is:

1. **Source a directory.** Find the union's local/council directory online. Options:
   - National website directory page (scrape or export)
   - OLMS data filtered by `aff_abbr` (has names, states, file numbers -- but no website URLs)
   - Manual compilation from regional/state pages

2. **Prepare CSV.** Format with at minimum: `name`, `state`, `website` columns. Optional: `officers`, `address`, `phone`, `email`, `section`.

3. **Load profiles.** Either:
   - Modify `setup_afscme_scraper.py` to accept a `--union` parameter and `parent_union` value
   - Or INSERT directly into `web_union_profiles` with correct `parent_union`

4. **Run the pipeline.** The remaining stages (fetch, extract, fix, match, export) are union-agnostic -- they operate on any rows in `web_union_profiles` with `scrape_status = 'PENDING'`.

### Priority Unions for Expansion

| Union | Abbr | Members | Local Directory Availability | Notes |
|-------|------|---------|------------------------------|-------|
| SEIU | SEIU | ~2.0M | seiu.org has local pages | Large, diverse sectors (healthcare, property services, public) |
| Teamsters | IBT | ~1.3M | teamster.org has local pages | Complex hierarchy (joint councils) |
| UFCW | UFCW | ~1.3M | ufcw.org has local pages | Retail, food processing, cannabis |
| IBEW | IBEW | ~775K | ibew.org has local pages | Construction, utilities, telecom |
| UAW | UAW | ~400K | uaw.org has regional pages | Auto, academic, gaming |

### Improving Extraction Quality

**Short-term: AI-powered extraction.** Replace regex with Claude API calls:
1. Read `raw_text` + `raw_text_about` for a profile
2. Send to Claude with a structured extraction prompt
3. Parse JSON response into `web_union_employers`, etc.
4. Would dramatically improve precision and recall over regex

**Medium-term: Better matching.** Replace pg_trgm with RapidFuzz (already used in the main matching pipeline). Block on sector + state for faster, more accurate fuzzy matching.

**Long-term: Contract PDF parsing.** Wire the CBA pipeline (`scripts/cba/`) into the scraper to extract provisions from linked contract PDFs.

---

## 12. Commands Reference

```bash
# Full pipeline (run in order)
py scripts/etl/setup_afscme_scraper.py                    # Stage 1: Setup + CSV load + OLMS match
py -u scripts/scraper/fetch_union_sites.py                # Stage 2: Crawl all PENDING sites
py scripts/scraper/extract_union_data.py --auto-extract   # Stage 3: Regex extraction
py scripts/scraper/fix_extraction.py                      # Stage 4: Quality fixes
py scripts/scraper/match_web_employers.py                 # Stage 5: Match against F7/OSHA
py scripts/scraper/export_html.py                         # Stage 6: HTML dashboard

# Targeted operations
py -u scripts/scraper/fetch_union_sites.py --limit 5      # Test run (5 sites)
py -u scripts/scraper/fetch_union_sites.py --id 42        # Single profile
py scripts/scraper/extract_union_data.py --read 42        # View raw text
py scripts/scraper/extract_union_data.py --read-batch 10  # View next 10 summaries
py scripts/scraper/extract_union_data.py --insert data.json  # Insert structured data

# Utilities
py scripts/scraper/read_profiles.py                       # Ad-hoc profile viewer
py scripts/scraper/fetch_summary.py                       # Summary stats
```

---

## 13. File Inventory

### Scripts

| File | Stage | Lines | Purpose |
|------|-------|-------|---------|
| `scripts/etl/setup_afscme_scraper.py` | 1 | 441 | Table creation, CSV load, OLMS matching |
| `scripts/scraper/fetch_union_sites.py` | 2 | 372 | Crawl4AI website fetcher |
| `scripts/scraper/extract_union_data.py` | 3 | 530 | Extraction helper (read/insert/auto-extract) |
| `scripts/scraper/fix_extraction.py` | 4 | 227 | Quality fixes (boilerplate, false positives) |
| `scripts/scraper/match_web_employers.py` | 5 | 248 | 5-tier employer matching |
| `scripts/scraper/export_html.py` | 6 | ~200 | Interactive HTML dashboard export |
| `scripts/scraper/read_profiles.py` | util | ~50 | Ad-hoc profile viewer |
| `scripts/scraper/fetch_summary.py` | util | ~60 | Summary stats |
| `scripts/scraper/extract_ex21.py` | util | ~120 | SEC EX-21 subsidiary extractor (secondary) |

### Data Files

| File | Purpose |
|------|---------|
| `scripts/scraper/ai_employers_batch1.json` | AI-extracted employers (batch 1) |
| `scripts/scraper/ai_employers_batch2.json` | AI-extracted employers (batch 2) |
| `scripts/scraper/manual_employers.json` | Manually reviewed employers |
| `scripts/scraper/manual_employers_2.json` | Additional manual employers |
| `afscme scrape/afscme_national_directory.csv` | Source directory CSV |

### Related Files (not in scripts/scraper/)

| File | Purpose |
|------|---------|
| `scripts/research/tools.py` | `scrape_employer_website` tool (Crawl4AI, lines 1676-2046) |
| `.claude/agents/research.md` | Crawl4AI notes, Windows workaround docs |
| `.claude/specs/pipeline-manifest.md` | Pipeline stage listing (line 94-96) |
| `.claude/specs/database-schema.md` | Table inventory (line 169-171) |
| `.claude/skills/union-research/SKILL.md` | Union discovery pipeline docs |
| `.claude/skills/union-research/references/news-sources.md` | 12 labor news sources for crawling |
