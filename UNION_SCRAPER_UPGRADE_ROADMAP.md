# Union Web Scraper — Tiered Extraction Upgrade
## Implementation Roadmap for Claude Code

**Project:** `C:\Users\jakew\Downloads\labor-data-project`  
**Database:** `olms_multiyear` on localhost, user `postgres`  
**Goal:** Replace/supplement the current regex-only extraction with a 4-tier no-cost extraction system, then add Gemini API as a fallback for hard cases. Do not break existing functionality — all new code adds to or wraps existing behavior.

---

## Context: What Exists Today and What's Wrong

The union web scraper currently has 6 stages:
1. Setup (load union directory CSVs into DB)
2. Fetch (visit each union website, save raw text)
3. Extract (scan text with regex patterns — **THIS IS THE PROBLEM**)
4. Clean (remove boilerplate, fix_extraction.py)
5. Match (link found employers to main platform tables)
6. Export (HTML report)

**The core problem:** Stage 3 uses 6 rigid regex patterns that only fire on specific phrases like "employees of the X" or "contract with X." This catches roughly 40% of employer mentions. The other 60% appear in HTML tables, bullet lists, PDF links, WordPress page data, or casual prose — all of which regex ignores entirely.

**The fix:** Add 4 new extraction methods that run BEFORE regex, each targeting a different data format. Regex becomes the last-resort fallback, not the primary method. Add Gemini API as a final fallback for anything that still yields nothing.

---

## Relevant Existing Files

```
scripts/scraper/
  fetch_union_sites.py        ← Stage 2: fetches websites, saves raw_text to DB
  extract_union_data.py       ← Stage 3: CURRENT REGEX EXTRACTION — modify this
  fix_extraction.py           ← Stage 4: boilerplate cleanup — leave alone
  match_web_employers.py      ← Stage 5: matching — leave alone for now

scripts/etl/
  setup_afscme_scraper.py     ← Stage 1: loads AFSCME data — leave alone for now

scripts/matching/             ← Main platform matching pipeline — do not modify
  pipeline.py
  config.py
```

**Key database tables (scraper-specific):**
```sql
web_union_profiles            -- one row per union local (id, union_name, website_url, 
                              --   raw_text, raw_text_about, raw_text_contracts, 
                              --   raw_text_news, scrape_status, last_scraped,
                              --   is_wordpress, wp_api_base)

web_union_employers           -- extracted employer names
                              -- (web_profile_id, employer_name, employer_name_clean,
                              --   source, confidence, extraction_method)

web_union_contracts           -- extracted contract references
web_union_membership          -- extracted membership counts
web_union_news               -- extracted news items
```

---

## What to Build: The 4-Tier Extraction System

### Overview

Every union profile goes through tiers in order. Each tier writes results tagged with its method name. If a tier finds data, later tiers still run (they are cumulative, not exclusive), EXCEPT Gemini which only runs when all other tiers found nothing.

```
Tier 1: WordPress REST API     → structured JSON directly from WP database
Tier 2: HTML Table/List Parser → structured data from <table>, <ul>, <ol> in raw HTML  
Tier 3: PDF Link Cataloger     → finds contract PDFs by page context
Tier 4: Sitemap + Nav Parser   → improves PAGE DISCOVERY (feeds better data into tiers 1-3)
Fallback: Gemini API           → only fires when tiers 1-3 found zero employers
```

The existing regex extractor becomes **Tier 5 (legacy)** and runs last.

---

## PHASE 1: Database Schema Updates

Run these SQL changes first before touching any Python. These add columns and tables needed by the new system. Use psycopg2 with the standard connection.

### 1a. Add tracking columns to web_union_profiles

```sql
ALTER TABLE web_union_profiles
  ADD COLUMN IF NOT EXISTS wp_api_available BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS wp_api_base TEXT,
  ADD COLUMN IF NOT EXISTS sitemap_url TEXT,
  ADD COLUMN IF NOT EXISTS sitemap_parsed BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS nav_links_parsed BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS extraction_tier_reached INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gemini_used BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS page_inventory JSONB DEFAULT '[]'::jsonb;
  -- page_inventory stores: [{"url": "...", "title": "...", "page_type": "contracts|about|news|unknown"}]
```

### 1b. Add extraction_method column to web_union_employers

```sql
ALTER TABLE web_union_employers
  ADD COLUMN IF NOT EXISTS extraction_method TEXT DEFAULT 'regex',
  ADD COLUMN IF NOT EXISTS source_page_url TEXT,
  ADD COLUMN IF NOT EXISTS source_element TEXT;
  -- source_element: 'table_row', 'list_item', 'wp_api', 'pdf_link', 'regex', 'gemini'
```

### 1c. Add unique constraint to prevent duplicate inserts on re-runs

```sql
-- Only add if it doesn't already exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conname = 'uq_web_employer_profile_name'
  ) THEN
    ALTER TABLE web_union_employers
      ADD CONSTRAINT uq_web_employer_profile_name 
      UNIQUE (web_profile_id, employer_name_clean);
  END IF;
END $$;
```

### 1d. Create web_union_pages table (replaces storing all text in one row)

This is a new table. The existing raw_text columns on web_union_profiles stay intact — do not remove them. This new table stores individual pages discovered during crawling.

```sql
CREATE TABLE IF NOT EXISTS web_union_pages (
  id SERIAL PRIMARY KEY,
  profile_id INTEGER REFERENCES web_union_profiles(id),
  page_url TEXT NOT NULL,
  final_url TEXT,                    -- after redirects
  page_type TEXT DEFAULT 'unknown',  -- 'about', 'contracts', 'news', 'home', 'unknown'
  http_status INTEGER,
  content_hash TEXT,                 -- MD5 of content, for change detection
  language TEXT DEFAULT 'en',
  markdown_text TEXT,
  html_raw TEXT,
  discovered_from TEXT,             -- 'sitemap', 'nav_link', 'wp_api', 'hardcoded_probe'
  last_scraped TIMESTAMP DEFAULT NOW(),
  UNIQUE(profile_id, page_url)
);

CREATE INDEX IF NOT EXISTS idx_web_union_pages_profile ON web_union_pages(profile_id);
CREATE INDEX IF NOT EXISTS idx_web_union_pages_type ON web_union_pages(page_type);
```

### 1e. Create pdf_links table

```sql
CREATE TABLE IF NOT EXISTS web_union_pdf_links (
  id SERIAL PRIMARY KEY,
  profile_id INTEGER REFERENCES web_union_profiles(id),
  page_id INTEGER REFERENCES web_union_pages(id),
  pdf_url TEXT NOT NULL,
  link_text TEXT,
  page_context TEXT,                 -- surrounding text snippet (200 chars)
  pdf_type TEXT DEFAULT 'unknown',   -- 'contract', 'mou', 'agreement', 'other'
  sent_to_cba_parser BOOLEAN DEFAULT FALSE,
  discovered_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(profile_id, pdf_url)
);
```

---

## PHASE 2: Tier 4 — Sitemap + Nav Link Discovery

**Build this first** because it improves what data the other tiers have to work with. Better page discovery → better extraction in every downstream tier.

### Create file: `scripts/scraper/discover_pages.py`

This script runs on all profiles with `scrape_status = 'FETCHED'` or `'EXTRACTED'`. It does three things in order:

**Step 1 — Try sitemap.xml**

For each union profile, attempt to fetch `{website_url}/sitemap.xml` and `{website_url}/sitemap_index.xml`. Parse the XML. For each URL found, classify its `page_type` using this keyword logic:

```python
def classify_page_type(url: str, title: str = "") -> str:
    text = (url + " " + title).lower()
    if any(k in text for k in ['contract', 'cba', 'agreement', 'bargain', 'negotiat']):
        return 'contracts'
    if any(k in text for k in ['about', 'who-we-are', 'history', 'mission', 'represent']):
        return 'about'
    if any(k in text for k in ['news', 'blog', 'update', 'press', 'announcement']):
        return 'news'
    if any(k in text for k in ['member', 'benefit', 'resource', 'document', 'form']):
        return 'members'
    return 'unknown'
```

Insert all discovered URLs into `web_union_pages` with `discovered_from = 'sitemap'`.

**Step 2 — Parse homepage navigation links**

The profile's `raw_text` column already contains the homepage markdown (fetched in Stage 2). Parse all internal links from the markdown (links starting with the same domain or with `/`). Apply the same `classify_page_type` function. Insert into `web_union_pages` with `discovered_from = 'nav_link'`.

**Step 3 — Hardcoded path probes (fallback only)**

If steps 1 and 2 found zero contract-type pages, fall back to probing the existing hardcoded path list. This preserves current behavior as a last resort.

**Update `web_union_profiles`:**
- Set `sitemap_parsed = TRUE` if sitemap was found
- Set `nav_links_parsed = TRUE` after nav parsing
- Update `page_inventory` JSONB column with summary of what was found

**CLI interface:**
```bash
python scripts/scraper/discover_pages.py
python scripts/scraper/discover_pages.py --profile-id 42
python scripts/scraper/discover_pages.py --status FETCHED
python scripts/scraper/discover_pages.py --union AFSCME
```

---

## PHASE 3: Tier 1 — WordPress REST API Extractor

WordPress powers approximately 40% of union websites. WordPress sites expose a REST API at `/wp-json/wp/v2/` that returns clean JSON — no HTML parsing needed. This is the highest-value tier.

### Create file: `scripts/scraper/extract_wordpress.py`

**Step 1 — Detect WordPress**

The existing `web_union_profiles` table has an `is_wordpress` boolean already populated during fetch. For any profile where `is_wordpress = TRUE`, attempt to locate the API base URL:

Try in order:
1. `{website_url}/wp-json/wp/v2/`  
2. Check if `wp_api_base` is already set in the profile

If the API responds with HTTP 200 and valid JSON containing a `namespace` field, set `wp_api_available = TRUE` and store the base URL in `wp_api_base`.

**Step 2 — Pull pages list**

```
GET {wp_api_base}/pages?per_page=100&_fields=id,title,slug,link,content
```

For each page returned:
- Run `classify_page_type(slug, title)` to determine page type
- Insert into `web_union_pages` with `discovered_from = 'wp_api'`
- Store the rendered content in `markdown_text` (strip HTML tags)

**Step 3 — Extract employers from page content**

For pages classified as `contracts` or `about`:
- Parse the rendered HTML content for `<table>` elements and `<ul>`/`<ol>` lists (see Tier 2 for the shared parsing function)
- Any employer names found get inserted into `web_union_employers` with `extraction_method = 'wp_api'`

**Step 4 — Pull recent posts (news)**

```
GET {wp_api_base}/posts?per_page=10&_fields=id,title,date,link,excerpt
```

Insert into `web_union_news` table.

**What to do with errors:**
- HTTP 403 or 404: API not available, set `wp_api_available = FALSE`, continue to next tier
- HTTP 429: Rate limited, wait 5 seconds, retry once
- Connection error: Log and skip, do not crash

**CLI interface:**
```bash
python scripts/scraper/extract_wordpress.py
python scripts/scraper/extract_wordpress.py --profile-id 42
python scripts/scraper/extract_wordpress.py --wp-only          # skip non-WP profiles
```

---

## PHASE 4: Tier 2 — HTML Table and List Parser

This is a shared utility that all tiers call. It takes HTML or markdown text as input and returns a list of candidate employer names. It does NOT connect to the database directly — it returns data that the calling tier inserts.

### Create file: `scripts/scraper/parse_structured.py`

**Function 1: `extract_from_tables(html: str) -> list[dict]`**

Parse HTML using BeautifulSoup. Find all `<table>` elements. For each table:
1. Skip tables with fewer than 2 rows (likely layout tables, not data tables)
2. Read the header row to identify column names
3. Look for columns whose header contains keywords: `employer`, `company`, `agency`, `department`, `employer name`, `represented`, `bargaining unit`, `employer/agency`
4. If a matching column is found, extract all cell values from that column
5. If no header match but the table has 2-5 columns and 3+ rows, treat the first column as potential employer names (heuristic)

Each result dict: `{"name": str, "source_element": "table_row", "context": str}`

**Function 2: `extract_from_lists(html: str) -> list[dict]`**

Parse HTML using BeautifulSoup. Find all `<ul>` and `<ol>` elements. For each list:
1. Skip navigation lists (check if parent element has class `nav`, `menu`, `header`, `footer`)
2. Skip lists with fewer than 3 items
3. Skip lists where most items are short (< 3 words) — these are usually nav menus
4. For remaining lists, check if items look like employer/organization names:
   - Contains keywords: `city of`, `county of`, `university`, `school`, `hospital`, `district`, `authority`, `department`, `inc`, `corp`, `llc`
   - OR: appears on a page classified as `contracts` or `about`
5. Extract qualifying list items as employer name candidates

Each result dict: `{"name": str, "source_element": "list_item", "context": str}`

**Function 3: `extract_pdf_links(html: str, base_url: str) -> list[dict]`**

Find all `<a>` tags where href ends in `.pdf` or contains `/pdf/`. For each:
1. Classify PDF type using link text and surrounding context:
   - `contract`: link text contains `contract`, `cba`, `agreement`, `mou`, `memorandum`
   - `contract`: PDF is on a page of type `contracts`
   - Otherwise: `other`
2. Extract 200 characters of surrounding text as `page_context`

Each result dict: `{"url": str, "link_text": str, "page_context": str, "pdf_type": str}`

**Cleaning function: `clean_employer_name(name: str) -> str`**

Apply to all extracted names before inserting:
```python
import re
def clean_employer_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)          # normalize whitespace
    name = re.sub(r'^[\-\•\*\>\|]+\s*', '', name)  # remove leading bullets/dashes
    name = re.sub(r'\s*[\-\•\*]+$', '', name)  # remove trailing bullets
    # Skip if too short, too long, or looks like boilerplate
    if len(name) < 4 or len(name) > 120:
        return None
    skip_phrases = ['click here', 'read more', 'learn more', 'contact us', 
                    'home', 'about', 'news', 'events', 'member login']
    if name.lower() in skip_phrases:
        return None
    return name
```

---

## PHASE 5: Wire Tier 2 Into the Main Extraction Flow

### Modify: `scripts/scraper/extract_union_data.py`

Do NOT delete the existing regex logic. Wrap it and add the new tiers around it.

**New execution order inside extract_union_data.py:**

```python
def extract_profile(profile_id: int, conn):
    profile = fetch_profile(profile_id, conn)
    results = {
        'employers': [],
        'contracts': [],
        'membership': None,
        'news': []
    }
    
    # --- TIER 1: WordPress API (already handled by extract_wordpress.py) ---
    # If wp_api_available = TRUE for this profile, its data is already in DB.
    # Check how many employers were already inserted by wp_api method.
    wp_count = count_existing_by_method(profile_id, 'wp_api', conn)
    
    # --- TIER 2: HTML Table + List Parser ---
    # Run on ALL pages in web_union_pages for this profile
    pages = fetch_profile_pages(profile_id, conn)
    for page in pages:
        if page['html_raw']:
            table_results = extract_from_tables(page['html_raw'])
            list_results = extract_from_lists(page['html_raw'])
            pdf_results = extract_pdf_links(page['html_raw'], page['page_url'])
            
            for emp in table_results + list_results:
                clean = clean_employer_name(emp['name'])
                if clean:
                    results['employers'].append({
                        'name': clean,
                        'extraction_method': emp['source_element'],
                        'source_page_url': page['page_url']
                    })
            
            for pdf in pdf_results:
                insert_pdf_link(profile_id, page['id'], pdf, conn)
    
    # Also run on the existing raw_text columns for backward compatibility
    for text_field in ['raw_text', 'raw_text_about', 'raw_text_contracts']:
        if profile.get(text_field):
            # Convert markdown back to basic HTML for parsing
            # (or extract from markdown directly using regex for links/tables)
            pass
    
    # --- TIER 5 (Legacy): Existing regex extraction ---
    # Always run regex too — it may catch things structured parsing misses
    regex_results = existing_regex_extract(profile)  # existing function, unchanged
    for emp in regex_results:
        results['employers'].append({
            'name': emp['name'],
            'extraction_method': 'regex',
            'source_page_url': profile['website_url']
        })
    
    # --- INSERT ALL RESULTS ---
    # Use ON CONFLICT DO UPDATE to avoid duplicates
    insert_employers(profile_id, results['employers'], conn)
    
    # Update extraction_tier_reached on the profile
    tier = determine_highest_tier_used(results)
    update_profile_tier(profile_id, tier, conn)
```

**INSERT with ON CONFLICT:**
```sql
INSERT INTO web_union_employers 
  (web_profile_id, employer_name, employer_name_clean, source, confidence, 
   extraction_method, source_page_url, source_element)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (web_profile_id, employer_name_clean) 
DO UPDATE SET
  extraction_method = EXCLUDED.extraction_method,
  source_page_url = EXCLUDED.source_page_url,
  updated_at = NOW()
```

---

## PHASE 6: Gemini API Fallback

This runs ONLY for profiles where all other tiers found zero employers. It is a separate script that runs after the main extraction pass.

### Create file: `scripts/scraper/extract_gemini_fallback.py`

**Setup:**
```python
import google.generativeai as genai
# API key from environment variable — never hardcode
# Set: GEMINI_API_KEY environment variable
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
model = genai.GenerativeModel('gemini-1.5-flash')  # cheapest/fastest model
```

**Which profiles qualify:**
```sql
SELECT p.id, p.union_name, p.website_url, p.raw_text, 
       p.raw_text_about, p.raw_text_contracts
FROM web_union_profiles p
LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
WHERE p.scrape_status IN ('FETCHED', 'EXTRACTED')
  AND p.gemini_used = FALSE
  AND p.raw_text IS NOT NULL
GROUP BY p.id
HAVING COUNT(e.id) = 0
```

**Prompt to send to Gemini:**

```python
EXTRACTION_PROMPT = """
You are analyzing text from a union local's website. Extract structured information.

Union name: {union_name}
Website: {website_url}

Website text:
{text}

Return ONLY valid JSON in this exact format, with no other text:
{{
  "employers": [
    {{
      "name": "exact employer name as it appears in the text",
      "confidence": "high|medium|low",
      "evidence": "brief quote showing why you identified this as an employer"
    }}
  ],
  "membership_count": null or integer,
  "has_contracts_page": true or false
}}

Rules:
- Only include employers where the union REPRESENTS workers there
- Do not include the union's own name
- Do not include vendors, sponsors, or advertisers
- If you find no employers, return an empty employers array
- Confidence is "high" if explicitly stated, "medium" if implied, "low" if uncertain
"""
```

**Text to send:** Combine `raw_text_contracts` + `raw_text_about` (contracts first, prioritized). Truncate to 6000 characters if longer.

**After Gemini responds:**
- Parse JSON response
- Insert each employer with `extraction_method = 'gemini'`
- Set `gemini_used = TRUE` on the profile
- Log token usage for cost tracking

**CLI interface:**
```bash
python scripts/scraper/extract_gemini_fallback.py
python scripts/scraper/extract_gemini_fallback.py --dry-run   # show what would be sent, don't call API
python scripts/scraper/extract_gemini_fallback.py --limit 10  # test on 10 profiles first
python scripts/scraper/extract_gemini_fallback.py --profile-id 42
```

**Cost tracking — print at end of each run:**
```
Gemini fallback summary:
  Profiles processed: 47
  New employers found: 83
  Estimated tokens used: ~94,000
  Estimated cost: ~$0.02
```

---

## PHASE 7: Run Order and Master Script

### Create file: `scripts/scraper/run_extraction_pipeline.py`

A single script that runs all tiers in the correct order for a complete extraction pass.

```bash
# Full pipeline for all profiles
python scripts/scraper/run_extraction_pipeline.py

# Full pipeline for specific union
python scripts/scraper/run_extraction_pipeline.py --union AFSCME

# Skip stages you've already run
python scripts/scraper/run_extraction_pipeline.py --skip-discovery --skip-wordpress

# Dry run (show what would happen, don't write to DB)
python scripts/scraper/run_extraction_pipeline.py --dry-run
```

**Internal run order:**
```
1. discover_pages.py          (Tier 4: sitemap + nav)
2. extract_wordpress.py       (Tier 1: WP REST API)
3. extract_union_data.py      (Tier 2: tables/lists + Tier 5: legacy regex)
4. fix_extraction.py          (existing cleanup — unchanged)
5. extract_gemini_fallback.py (Gemini: only zero-result profiles)
6. match_web_employers.py     (existing matching — unchanged)
```

---

## PHASE 8: Validation and Reporting

After each full pipeline run, generate a quality report so we can see whether the new tiers are actually improving coverage.

### Create file: `scripts/scraper/extraction_report.py`

Query and print (or save to CSV) the following:

```sql
-- Coverage by extraction method
SELECT 
  extraction_method,
  COUNT(DISTINCT web_profile_id) as profiles_with_data,
  COUNT(*) as total_employers,
  ROUND(AVG(CASE WHEN confidence = 'high' THEN 1.0 
                 WHEN confidence = 'medium' THEN 0.5 
                 ELSE 0.2 END), 2) as avg_confidence
FROM web_union_employers
GROUP BY extraction_method
ORDER BY total_employers DESC;

-- Profile-level summary
SELECT
  p.union_name,
  p.website_url,
  p.is_wordpress,
  p.wp_api_available,
  p.sitemap_parsed,
  p.extraction_tier_reached,
  p.gemini_used,
  COUNT(e.id) as employers_found,
  COUNT(CASE WHEN e.extraction_method = 'wp_api' THEN 1 END) as from_wp_api,
  COUNT(CASE WHEN e.extraction_method IN ('table_row','list_item') THEN 1 END) as from_html,
  COUNT(CASE WHEN e.extraction_method = 'regex' THEN 1 END) as from_regex,
  COUNT(CASE WHEN e.extraction_method = 'gemini' THEN 1 END) as from_gemini
FROM web_union_profiles p
LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
GROUP BY p.id
ORDER BY employers_found DESC;

-- PDF catalog
SELECT 
  p.union_name,
  pdf.pdf_url,
  pdf.link_text,
  pdf.pdf_type,
  pdf.page_context
FROM web_union_pdf_links pdf
JOIN web_union_profiles p ON p.id = pdf.profile_id
WHERE pdf.pdf_type = 'contract'
ORDER BY p.union_name;
```

CLI: `python scripts/scraper/extraction_report.py` — prints summary to terminal and saves full CSV to `files/scraper_report_{date}.csv`

---

## PHASE 9: Critical Fixes (Do These Alongside the Above)

These are bugs from the audit that should be fixed as you touch the relevant files.

### Fix 1: URL Provenance (in fetch_union_sites.py)

**Current problem:** When saving fetched page content to the database, it stores a synthetic URL like `{base_url}/about` even if the actual page was at a different URL after redirects.

**Fix:** After `httpx` follows redirects, store `response.url` (the final URL after redirects) as `final_url` in `web_union_pages`. Never store a guessed URL — always store what the server actually responded from.

### Fix 2: Boilerplate Filter (in fix_extraction.py)

**Current problem:** Running fix_extraction.py twice creates duplicate `auto_extract_v2` rows.

**Fix:** Add this check at the start of fix_extraction.py:
```python
# Delete any existing v2 rows for these profiles before re-inserting
cursor.execute("""
  DELETE FROM web_union_employers 
  WHERE source = 'auto_extract_v2' 
  AND web_profile_id = ANY(%s)
""", (profile_ids,))
```

### Fix 3: Add `updated_at` tracking

Add `updated_at TIMESTAMP DEFAULT NOW()` to `web_union_employers` if it doesn't exist. Use a trigger or manual update to keep it current.

---

## Dependencies to Install

```bash
pip install beautifulsoup4 lxml google-generativeai --break-system-packages
```

BeautifulSoup + lxml: HTML parsing for Tier 2  
google-generativeai: Gemini API for fallback  

All other dependencies (httpx, psycopg2, etc.) are already in the project.

---

## Environment Variables Needed

```bash
# Add to your .env or system environment (NOT hardcoded in code)
GEMINI_API_KEY=your_key_here
```

The Gemini key goes in `.env` in the project root. Load it with `python-dotenv` (already used in the project) or `os.environ`.

**IMPORTANT:** Do not put the API key directly in any Python file. If the project already has a `.env` file, add to it. If not, create one and add it to `.gitignore`.

---

## Testing Checkpoints

After each phase, run these quick checks before moving on:

**After Phase 1 (schema):**
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'web_union_profiles' 
AND column_name IN ('wp_api_available', 'sitemap_parsed', 'page_inventory');
-- Should return 3 rows
```

**After Phase 2 (page discovery):**
```sql
SELECT discovered_from, COUNT(*) FROM web_union_pages GROUP BY discovered_from;
-- Should show sitemap, nav_link, and/or hardcoded_probe rows
```

**After Phase 3 (WordPress):**
```sql
SELECT COUNT(*) FROM web_union_profiles WHERE wp_api_available = TRUE;
-- Should be > 0 for AFSCME data
SELECT COUNT(*) FROM web_union_employers WHERE extraction_method = 'wp_api';
-- Should be > 0 if any AFSCME locals run WordPress
```

**After Phase 5 (full extraction):**
```sql
SELECT extraction_method, COUNT(*) 
FROM web_union_employers 
GROUP BY extraction_method;
-- Should show multiple methods, not just 'regex'
```

**After Phase 6 (Gemini fallback):**
```sql
SELECT COUNT(*) FROM web_union_profiles WHERE gemini_used = TRUE;
-- Should be > 0 but much less than total profiles (Gemini is last resort)
```

---

## What NOT to Change

- `setup_afscme_scraper.py` — leave AFSCME-specific setup alone for now. Multi-union generalization is a separate future phase.
- `match_web_employers.py` — leave matching logic alone for now.
- `fix_extraction.py` — only apply Fix 2 from Phase 9 above.
- `scripts/matching/` — the main platform matching pipeline. Do not touch.
- Any table not prefixed with `web_union_` — this scraper should only write to its own tables.
- `CLAUDE.md` — update this file when done to reflect the new scripts and schema changes.

---

## Success Criteria

The upgrade is complete when:

1. `python scripts/scraper/run_extraction_pipeline.py` runs end-to-end without errors on the existing 295 AFSCME profiles
2. The extraction report shows at least 3 distinct `extraction_method` values in results
3. Total employers found is higher than the pre-upgrade baseline (check `SELECT COUNT(*) FROM web_union_employers` before starting)
4. No duplicate rows exist in `web_union_employers` (verified by checking the unique constraint)
5. At least one profile has `source_page_url` populated with a real URL (not a guessed path)
6. The PDF catalog table has at least some rows for AFSCME profiles that have contract pages

---

*This roadmap was generated March 2026. Refer to `CLAUDE.md` for database connection details and project conventions.*
