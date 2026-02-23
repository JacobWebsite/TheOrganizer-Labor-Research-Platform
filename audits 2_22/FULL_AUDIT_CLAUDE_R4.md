# Full Platform Audit — Claude Code (Round 4)
## Labor Relations Research Platform
**Date:** February 22, 2026
**Version:** Round 4 — Post-Codex merge, post-React frontend, post-ULP integration

---

## READ THIS FIRST — What This Project Is (Plain Language)

This is a research platform that helps labor union organizers figure out where to focus their efforts. Think of it like a detective tool — it pulls information from over a dozen government databases (workplace safety records, union election results, wage theft cases, government contracts, corporate filings, nonprofit records) and connects them all together so you can see the full picture of any employer in the country.

The core question the platform answers: **"If we only have time and money to organize 50 employers this year, which 50 should we pick?"**

It does this by scoring every employer on 8 different factors — things like "does this employer have safety violations?", "are nearby employers already unionized?", "has this employer been caught stealing wages?" — and combining those into a single 0-to-10 score. Higher score = more promising organizing target.

The platform runs on PostgreSQL (a database), has a Python backend using FastAPI (which serves data to the website), and a React frontend (the screens organizers interact with). It currently tracks about 147,000 employers with union contracts, plus ~2.7 million employers in a broader "master" table. It accounts for 14.5 million union members — matching federal benchmarks within 1.5%.

---

## YOUR ROLE AS AUDITOR

**You are Claude Code — the primary auditor.** You have direct access to the database and codebase. Run actual queries. Test actual endpoints. Read actual code. Your audit should be the most detailed and data-backed of the three AI auditors.

Create your report at `docs/AUDIT_REPORT_CLAUDE_2026_R4.md`.

**Three other AI tools are doing their own audits of the same system using this same prompt (with small tweaks).** After all audits are done, the results will be compared side by side. So be thorough — if you miss something another auditor catches, that's a problem.

**Communication style:** Explain everything in plain, simple language. When you find a problem, explain what it means for an actual organizer trying to use this tool. Don't just say "foreign key constraint violated" — say "this means 824 employer records are pointing to unions that don't exist in the system, so when someone looks up those employers, the union information will be wrong or missing."

**Checkpoints:** After completing each section below, STOP and show a brief summary of findings before moving to the next section. Don't rush through everything at once.

---

## DATABASE CONNECTION

```python
from db_config import get_connection
conn = get_connection()
```

Credentials are in `.env` at project root. Never hardcode the password — always use `db_config.py`.

---

## WHAT THE PLATFORM LOOKS LIKE TODAY

### Platform by the Numbers (Verify All of These)

| What | Expected Count | Source |
|------|----------------|--------|
| Database size | ~9.5 GB | After GLEIF archive + corpwatch deletion |
| F7 employers (union contracts) | 146,863 | `f7_employers_deduped` |
| Master employers (all sources) | ~2,736,890 | `master_employers` (after dedup) |
| Master source ID mappings | 3,080,492 | `master_employer_source_ids` |
| Unified Match Log rows | 1,738,115 | `unified_match_log` |
| Unions tracked | 26,665 | `unions_master` |
| Members accounted for | 14.5M | Should be within ~1.5% of BLS 14.3M |
| OSHA establishments | 1,007,217 | `osha_establishments` |
| OSHA violations | 2,245,020 | `osha_violations_detail` |
| NLRB elections | 33,096 | `nlrb_elections` |
| WHD wage theft cases | 363,365 | `whd_cases` |
| SAM federal contractors | 826,042 | `sam_entities` |
| SEC companies | 517,403 | `sec_companies` |
| 990 nonprofit filers | 586,767 | `national_990_filers` |
| IRS BMF records | ~2,043,779 | `irs_bmf` |
| API routers | 21 | In `api/routers/` (20 original + master.py) |
| Automated tests | 492 | 491 pass, 0 fail, 1 skip |
| Active pipeline scripts | 134 | Per PIPELINE_MANIFEST.md |
| Frontend React components | All 6 phases complete | src/ directory |
| Materialized views | 4 key MVs | organizing_scorecard, employer_data_sources, unified_scorecard, employer_search |

### Core Tables and What They Hold

| Table | Expected Rows | What It Is |
|-------|---------------|------------|
| `unions_master` | 26,665 | Every union local/affiliate that files with the Department of Labor |
| `f7_employers_deduped` | 146,863 | Employers that have active or historical union contracts |
| `master_employers` | ~2,736,890 | ALL employers from ALL sources combined (F7 + SAM + Mergent + BMF) |
| `master_employer_source_ids` | 3,080,492 | Links each master employer back to its original source records |
| `unified_match_log` | 1,738,115 | Audit trail of every cross-database match ever made |
| `nlrb_elections` | 33,096 | Union election records — who petitioned, who voted, who won |
| `nlrb_ca_charged_parties` | ~234,656 | ULP (Unfair Labor Practice) charged party records |
| `osha_establishments` | 1,007,217 | Every workplace OSHA has visited |
| `osha_violations_detail` | 2,245,020 | Individual safety violations ($3.52B in penalties total) |
| `whd_cases` | 363,365 | Wage theft enforcement cases |
| `sam_entities` | 826,042 | Federal contractor entities from SAM.gov |
| `sec_companies` | 517,403 | SEC-registered companies |
| `national_990_filers` | 586,767 | IRS 990 nonprofit filers |
| `irs_bmf` | ~2,043,779 | IRS Business Master File (tax-exempt orgs) |
| `employer_comparables` | ~269,000 | Top-5 comparable employers per employer (Gower distance) |
| `employer_groups` | ~66,859 | Canonical employer groupings (same company, different records) |
| `mv_organizing_scorecard` | 212,441 | Pre-calculated organizing scores (legacy OSHA-based) |
| `mv_employer_data_sources` | 146,863 | Which data sources exist per F7 employer |
| `mv_unified_scorecard` | 146,863 | The NEW 8-factor weighted scores |
| `mv_employer_search` | ~107,025 | Pre-built search index |

### How the Scoring System Works (8 Factors)

Every employer gets a score from 0 to 10. The score is a **weighted average** of up to 8 factors. If a factor has no data for an employer, it gets **skipped entirely** — not counted as zero. This is called "signal-strength scoring."

| Factor | Weight | What It Measures | Key Detail |
|--------|--------|-----------------|------------|
| **Union Proximity** | 3x | Are there already unions at this employer or corporate siblings? | 2+ siblings=10, 1=5, none=0 |
| **Employer Size** | 3x | How many workers? Bigger = more impact per campaign | Under 15=0, 15-500 ramp, 500+=10 |
| **NLRB Activity** | 3x | Real organizing momentum nearby + own history + ULP charges | 70% nearby, 30% own. Losses = negative. 7yr half-life |
| **Gov Contracts** | 2x | Government leverage — federal/state/city | Federal=4, State=6, City=7, combo=8-10 |
| **Industry Growth** | 2x | BLS 10-year employment projections | Growing industries = more leverage |
| **Statistical Similarity** | 2x | How similar is this employer to already-unionized ones? | Gower distance comparables engine |
| **OSHA Safety** | 1x | Workplace danger normalized by industry | 5yr half-life. Willful/repeat bonus |
| **WHD Wage Theft** | 1x | Has this employer been caught stealing wages? | 0=0, 1 case=5, 2-3=7, 4+=10. 5yr half-life |

**Weighted formula:** `SUM(score × weight) / SUM(weights of factors that have data)`

**Tier system (percentile-based):**

| Tier | Percentile | Approx Count |
|------|-----------|-------------|
| Priority | Top 3% | ~4,400 |
| Strong | Next 12% | ~17,600 |
| Promising | Next 25% | ~36,700 |
| Moderate | Next 35% | ~51,400 |
| Low | Bottom 25% | ~36,700 |

### What "Matching" Means (The Core Technical Challenge)

Different government agencies don't use the same ID system for employers. OSHA knows "Walmart" by one ID, the Department of Labor knows it by another, the NLRB has its own case numbers, etc. Even the names are different across databases — "WALMART INC" vs "Wal-Mart Stores, Inc." vs "WAL MART STORES INC."

The platform uses a **6-tier matching pipeline** to connect these records:

| Tier | Method | What It Does | Confidence |
|------|--------|--------------|------------|
| 1 | EIN exact match | Same tax ID number = same entity. Most reliable. | HIGH |
| 2 | Normalized name + full address | Clean up names, match on cleaned name + full address | HIGH |
| 3 | Normalized name + state | Cleaned name + same state | HIGH |
| 4 | Aggressive normalization + state | Extra-aggressive name cleaning + state | MEDIUM |
| 5a | Splink probabilistic | Statistical model that calculates probability two records are the same | MEDIUM |
| 5b | Trigram fuzzy | Compares how many 3-letter chunks overlap between names | MEDIUM |
| 6 | Relaxed fuzzy | Lower thresholds for last-resort matching | LOW |

**Key design principle:** "Best match wins" — if an employer matches multiple records, only the highest-confidence match is kept.

**Current match rates to verify:**

| Source | Expected Active Matches | Rate |
|--------|------------------------|------|
| OSHA → F7 | 97,142 | 9.6% of 1M OSHA records |
| SAM → F7 | 28,816 | 3.5% of 826K SAM records |
| 990 → F7 | 20,215 | 3.4% of 587K 990 records |
| WHD → F7 | 19,462 | 5.4% of 363K WHD records |
| NLRB → F7 | ~25,879 | Post-ULP integration (was 5,548) |
| SEC → F7 | 5,339 | 1.0% of 517K SEC records |
| BMF → F7 | 9 | Extremely low — expected, BMF is nonprofits |

### The Frontend

The platform now has a **React frontend** built with Vite, Tailwind, shadcn/ui components, Zustand for state management, and TanStack Query for data fetching. All 6 build phases are complete:

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | Core layout, routing, auth, theme | DONE |
| Phase 2 | Employer search + profiles | DONE |
| Phase 3 | Scorecard/targets explorer | DONE |
| Phase 4 | Data Explorer (OSHA, NLRB, WHD, maps) | DONE |
| Phase 5 | Union Explorer + profiles | DONE |
| Phase 6 | Admin dashboard + settings | DONE |

107 frontend tests across 18 files, all passing.

The legacy vanilla JS frontend (`files/organizer_v5.html`) still exists alongside the React app.

### The API

FastAPI backend with 21 routers. Key endpoint groups:

| Router | What | Key Endpoints |
|--------|------|---------------|
| `employers.py` | Employer search and details | `/api/employers/search`, `/api/employers/{id}` |
| `scorecard.py` | Unified scorecard data | `/api/scorecard/`, `/api/scorecard/{id}` |
| `master.py` | Master employer table (NEW) | `/api/master/search`, `/api/master/{id}`, `/api/master/stats`, `/api/master/non-union-targets` |
| `profile.py` | Canonical employer/union profiles | `/api/profile/employers/{id}`, `/api/profile/unions/{fnum}` |
| `unions.py` | Union search and details | `/api/unions/search`, `/api/unions/{fnum}` |
| `osha.py` | OSHA violation data | `/api/osha/violations/{id}` |
| `nlrb.py` | NLRB election data | `/api/nlrb/elections` |
| `corporate.py` | Corporate hierarchy | `/api/corporate/family/{id}` |
| `health.py` | Platform health check | `/api/health` |
| `admin.py` | Admin actions (refresh MVs, etc.) | `/api/admin/refresh-scorecard` |

---

## SECTION 1: Database Inventory

**What this does:** Creates a complete list of every table, view, and materialized view in the database with real, current row counts.

**Why it matters:** Over time, tables get created for experiments or features that never got finished. Some might be empty, some might have millions of rows but nothing uses them. We need to know what's actually there.

**Steps:**
1. Connect to `olms_multiyear` database
2. Get EVERY table and view (not just the documented ones)
3. For each: actual row count, column count, whether it has a primary key, disk size
4. Compare actual counts against the numbers in this prompt — flag discrepancies
5. Flag any tables with ZERO rows
6. Flag any tables NOT mentioned in documentation ("undocumented" tables)
7. Group tables: Core, OSHA, NLRB, WHD, Corporate/Financial, Public Sector, Scoring, Master Employer, Legacy/Orphan
8. List all 4 materialized views with row counts and check when they were last refreshed

**CHECKPOINT: Stop here and show me the table inventory before continuing.**

---

## SECTION 2: Data Quality Deep Dive

**What this does:** Looks INSIDE the most important tables to check if the data itself is healthy.

**Why it matters:** A table can have 100,000 rows, but if half the important columns are empty, it's not as useful as it looks.

**Steps:**
1. For the top 15 tables by row count: check what percentage of key columns have actual data vs NULL/empty
2. Check `f7_employers_deduped`: How many employers have names? States? EINs? NAICS codes? Lat/lng coordinates?
3. Check `master_employers`: data quality score distribution (how many are above 40? 60? 80?), source_origin breakdown, how many have EINs?
4. Check `unified_match_log`: breakdown by source_system, confidence level distribution, how many are "active" vs "superseded"
5. Check `mv_unified_scorecard`: How many employers have scores for each factor? What's the average score per factor? How many have data for 1 factor? 2? 3? 4+?
6. Check for orphaned records: employers pointing to unions that don't exist, match records pointing to deleted employers
7. Check the `is_labor_org` flag: How many F7 employers are flagged as labor organizations? Does this look reasonable?
8. Verify member count deduplication: total members should be ~14.5M, not 70M

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 3: Matching Pipeline Integrity

**What this does:** Verifies that the matching system — which connects records across databases — is working correctly and producing trustworthy results.

**Why it matters:** If matching is broken, scores are wrong. If an employer's OSHA violations don't get connected to the right employer record, the platform will either miss important safety data or show the wrong employer's violations. This is the foundation everything else depends on.

**Steps:**
1. Pull a random sample of 20 HIGH-confidence matches from unified_match_log and manually verify: do the names, addresses, and states make sense together?
2. Pull a random sample of 20 MEDIUM-confidence matches and verify the same way
3. Pull 10 LOW-confidence matches — are any of these clearly wrong?
4. Check for "many-to-one" problems: are there F7 employers matched to an unreasonable number of OSHA establishments? (Flag any with 50+ matches)
5. Check for "duplicate match" problems: are there OSHA establishments matched to multiple F7 employers? There shouldn't be (best-match-wins should prevent this)
6. Verify the legacy match tables are consistent with unified_match_log: compare row counts of `osha_f7_matches`, `sam_f7_matches`, `whd_f7_matches`, `national_990_f7_matches` against counts from UML with `status='active'`
7. Check the Splink name similarity floor: is it 0.70 as documented?
8. Check the NLRB ULP matching: 234,656 CA records matched to 22,371 employers — sample 10 and verify they're reasonable
9. Check `employer_groups`: How many groups have more than 20 members? Any with 100+? (These might be over-merged — different companies incorrectly grouped together)
10. Check for match "drift": are there superseded matches in UML that have no active replacement? How many?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 4: Scoring System Verification

**What this does:** Checks whether the scoring system is producing sensible, useful results.

**Why it matters:** The whole point of the platform is to help organizers prioritize. If the scores are wrong — or if they don't meaningfully distinguish between good and bad targets — the platform isn't doing its job.

**Steps:**
1. Pull the top 25 "Priority" tier employers. Do the names make sense? Are they real companies that organizers would actually want to target?
2. Pull 25 random "Low" tier employers. Do these look like genuinely less promising targets?
3. Check score distribution: is there a reasonable spread, or are most employers clustered around the same score?
4. Verify the weighted formula: pick 5 employers, manually calculate their weighted score from the component factor scores, and compare against what the MV says
5. Verify percentile tiers: are the actual percentile breakpoints close to the design targets (3% Priority, 12% Strong, 25% Promising, 35% Moderate, 25% Low)?
6. Check the `score_similarity` factor (new): How many employers have this score? Does it add useful differentiation, or is it mostly NULL?
7. Check the `score_industry_growth` factor: How many employers have this? Is the BLS projection data correctly mapped?
8. Check OSHA scoring freshness: the old system was using decade-old data despite having current data through 2025. Verify the 5-year half-life is working — recent violations should count much more than old ones
9. Check WHD scoring: verify 5-year half-life (was 7yr before), and the case-count-based approach (0=0, 1=5, 2-3=7, 4+=10)
10. Check NLRB scoring with ULP integration: verify the ULP boost is working (1 charge=2, 2-3=4, 4-9=6, 10+=8 with 7yr decay)
11. Look for scoring anomalies: any employers with score=10 on every factor? Any with implausible combinations?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 5: API & Endpoint Testing

**What this does:** Tests whether the API endpoints actually return correct data when called.

**Why it matters:** The frontend gets ALL its data through the API. If an endpoint returns wrong data, stale data, or crashes — organizers see wrong information or a broken page.

**Steps:**
1. Start the API if not running: `cd C:\Users\jakew\Downloads\labor-data-project && python -m uvicorn api.main:app --port 8001`
2. Test `GET /api/health` — does it return healthy status with all components?
3. Test `GET /api/employers/search?q=walmart` — does it return results? Are they reasonable?
4. Test `GET /api/scorecard/` — does it return the scorecard list with the new tier names (Priority/Strong/Promising/Moderate/Low)?
5. Test `GET /api/master/stats` — does it return the expected counts?
6. Test `GET /api/master/non-union-targets` — does it correctly exclude union employers?
7. Test `GET /api/corporate/family/{employer_id}` for a known employer — does it return corporate hierarchy?
8. Test `GET /api/profile/employers/{employer_id}` for a known employer — does it return the full profile with all available data?
9. Test `GET /api/unions/search?q=teamsters` — does it return results?
10. Check for deprecated endpoints: are there endpoints that return stale data from old materialized views?
11. Check response times: any endpoints taking more than 3 seconds?
12. Check for SQL injection protection: are all query parameters properly parameterized?
13. Check authentication: is `require_auth` enabled or disabled by default? Can anonymous users access admin endpoints?
14. Check CORS settings: is it still `allow_origins=["*"]` (wide open)?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 6: Frontend & React App

**What this does:** Checks whether the new React frontend is working correctly and connected to real data.

**Why it matters:** This is what organizers actually see and interact with. If pages are broken, data doesn't load, or the UI is confusing — organizers won't trust or use the tool.

**Steps:**
1. Check the React app structure: `src/` directory — are all 6 phases present with the expected file counts?
2. Check the build: does `npm run build` succeed without errors?
3. Run frontend tests: `npm test` — do all 107 tests pass?
4. Check API hooks: are the hooks in `src/shared/api/` correctly pointing to the right backend endpoints?
5. Check for hardcoded URLs: search the React codebase for `localhost:8001` or hardcoded API URLs that would break in production
6. Check state management: is Zustand being used consistently, or are there places where state is managed inconsistently?
7. Check the legacy frontend: does `files/organizer_v5.html` still work? Are there conflicts between old and new?
8. Check the admin dashboard: does the health check auto-refresh work? Does the MV refresh button work?
9. Check for accessibility basics: do buttons have labels? Do forms have proper labels?
10. Check the employer profile page: does it display all 8 scoring factors with explanations?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 7: Master Employer Table & Deduplication

**What this does:** Audits the new master employer table — the biggest structural addition since the last audit.

**Why it matters:** The master table is supposed to be the single source of truth for ALL employers — union and non-union. If it has duplicates, bad data, or broken links, the whole "non-union target discovery" feature won't work.

**Steps:**
1. Check `master_employers` row count and breakdown by `source_origin` (F7, SAM, Mergent, BMF)
2. Check dedup quality: how many records were merged (expected: 289,400 merged from 3,026,290 → 2,736,890)?
3. Sample 20 merged records: did the dedup correctly identify these as the same employer?
4. Check for remaining duplicates: are there employers that appear multiple times with slightly different names?
5. Check the `data_quality_score` distribution: how many employers have a score above 60? Below 20?
6. Check `is_labor_org` flag on master_employers: 6,686 expected flagged. Does this look right?
7. Check `master_employer_source_ids`: does every master employer have at least one source ID?
8. Check links back to source tables: pick 10 random master employers and verify their source_ids correctly point to real records in f7, SAM, irs_bmf, etc.
9. Check the master API endpoints: do `/api/master/search`, `/api/master/stats`, `/api/master/non-union-targets` return consistent data?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 8: Scripts, Pipeline & Code Quality

**What this does:** Checks the codebase for broken scripts, dead code, security issues, and technical debt.

**Why it matters:** Broken scripts mean data can't be updated. Dead code makes everything harder to understand and maintain. Security issues could expose sensitive data.

**Steps:**
1. Verify the PIPELINE_MANIFEST.md is accurate: pick 10 random scripts listed as "active" and confirm they exist and are functional
2. Check for scripts that reference old table names or deleted tables
3. Check for hardcoded credentials: `grep -r "Juniordog33" scripts/` — should find ZERO results (was a known problem, supposedly fixed)
4. Check for hardcoded file paths: how many scripts still use `C:\Users\jakew\Downloads\` hardcoded paths instead of relative paths or config?
5. Check the broken password pattern: `password='os.environ.get(...)` — was this actually fixed in all 347 scripts?
6. Check `db_config.py`: is it properly using environment variables?
7. Run the test suite: `pytest tests/ -v` — do all tests pass? Which tests are new since the last audit?
8. Check test coverage: are there major features with NO tests?
9. Check for abandoned experiments: are there scripts in active directories (not archive/) that do nothing useful?
10. Check the archive: was the cleanup actually done (expected: ~400 dead scripts moved to `archive/old_scripts/`)?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 9: Documentation Accuracy

**What this does:** Checks whether the documentation matches reality.

**Why it matters:** Three AI tools use these documents to understand the project. If the docs are wrong, the AIs will make wrong decisions. This was a major problem identified in the Document Reconciliation Analysis.

**Steps:**
1. Check every number in CLAUDE.md against the actual database — flag discrepancies
2. Check every number in PROJECT_STATE.md against the actual database — flag discrepancies
3. Verify that all 5 core documents reference the UNIFIED_PLATFORM_REDESIGN_SPEC.md
4. Verify the roadmap filename is consistent everywhere (should be `UNIFIED_ROADMAP_2026_02_19.md`, not `_02_17`)
5. Check the scoring section in CLAUDE.md: does it reflect the new 8-factor weighted system or the old 7-factor equal-weight system?
6. Check the tier names: are all documents using Priority/Strong/Promising/Moderate/Low (new) rather than TOP/HIGH/MEDIUM/LOW (old)?
7. Check the test count: all documents should say 492 tests (491 pass, 0 fail, 1 skip)
8. Check the API router count: should be 21
9. Check the PIPELINE_MANIFEST.md against actual files on disk

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 10: Summary & Recommendations

Pull everything together:

1. **Health Score:** Rate overall platform health: Critical / Needs Work / Solid / Excellent — with justification
2. **Top 10 Issues:** Most important problems, ranked by impact on organizers
3. **Quick Wins:** Things fixable in under an hour each
4. **Data Quality Priorities:** Which tables need the most cleanup
5. **Scoring Assessment:** Is the 8-factor weighted system producing useful results? What would make it more accurate?
6. **Master Employer Assessment:** Is the master table ready for production use, or does it need more dedup/cleanup?
7. **Frontend Assessment:** Is the React app production-ready? What's missing?
8. **Matching Pipeline Assessment:** Is matching trustworthy enough to deploy?
9. **Security Assessment:** What's the current security posture? What must be fixed before any real users?
10. **Documentation Gaps:** What's missing from the docs that a new developer would need?

---

## SECTION 11: What No One Thought to Ask

**This is the most important section.** The previous 10 sections check things we KNOW to look at. This section is about finding problems nobody anticipated — the blind spots, the silent failures, the assumptions that might be wrong.

**Think about these questions and investigate any that seem relevant:**

### Data Integrity Questions Nobody Asked

1. **Are there employers in the scorecard that don't exist anymore?** If a company went bankrupt, got acquired, or changed names — is the platform still scoring a ghost? Check if any high-scoring "Priority" employers have no recent activity across ANY data source (no OSHA inspections, no NLRB cases, no WHD cases, no SAM contracts in the last 5 years).

2. **Is the matching pipeline creating false connections?** Not just "are individual matches wrong" — but could a systematic error be linking thousands of records incorrectly? For example: if two companies at the same address get merged, and one is unionized and one isn't, the non-union company might disappear from the "targets" list. How many potential targets are being hidden by incorrect matches?

3. **Are there entire industries being missed?** The platform is built around F7 filings, which are for private-sector unions. Are there large industries where organizing is happening but the platform shows almost nothing? Check: tech, gig economy, cannabis, warehousing/logistics. What does the platform say about Amazon? About Starbucks?

4. **Is the deduplication OVER-counting or UNDER-counting?** The 14.5M member count is close to BLS — but is that because the methodology is correct, or because over-counting in some areas cancels out under-counting in others? Check: are there specific states or sectors where the platform's count diverges wildly from BLS?

5. **What happens to the scores when data is stale?** The half-life decay system means old violations count less. But what about employers with NO data? An employer with zero OSHA violations could be perfectly safe — or it could be that OSHA has never inspected them. Does the platform distinguish between "clean record" and "no record"?

### Architectural Questions Nobody Asked

6. **What's the performance cliff?** The system works with ~3M master employers. What happens at 5M? 10M? Are there queries that will become unusably slow? Check the largest table scans and joins — which ones don't have indexes?

7. **Is the materialized view refresh safe?** If someone refreshes the scorecard MV while the API is serving requests, do users see broken/partial data? Is `REFRESH MATERIALIZED VIEW CONCURRENTLY` being used everywhere?

8. **What happens when the database connection dies mid-operation?** Are there scripts that could leave the database in an inconsistent state if they crash halfway through?

9. **Is there a way to roll back a bad data update?** If someone runs the wrong ETL script and corrupts a table, is there a backup? Can you restore to yesterday's state?

### Strategic Questions Nobody Asked

10. **Is the platform scoring the RIGHT things?** The 8 factors measure conditions that make organizing more likely to succeed. But are there important factors being completely ignored? For example: employer turnover rate, local unemployment, political environment, presence of right-to-work laws, employer's legal counsel spending?

11. **Could the scoring system be gamed?** If an employer found out they were being scored, could they manipulate their public records to lower their score? (Settle OSHA violations quickly, avoid NLRB elections by voluntary recognition, etc.)

12. **What's the shelf life of a score?** If an organizer looks at a score today, how long is it valid? A week? A month? A year? Is there any indicator of when the underlying data was last updated?

13. **Are there unions that should be in the system but aren't?** The platform tracks 26,665 unions. The BLS says there are roughly 16,000 union locals in the US. Why does the platform have more? Are some of these defunct? Double-counted? National affiliates vs. locals?

14. **What's the false negative rate?** Of employers that actually got organized in the last 2 years (check NLRB election wins), how many were flagged as "Priority" or "Strong" by the platform BEFORE the election? If the platform consistently fails to predict successful organizing, the scoring model needs work.

15. **Is there geographic bias in the data?** Government enforcement varies hugely by region. OSHA inspects more in some states than others. WHD enforcement is concentrated in certain areas. Does this mean the platform systematically underscores employers in states with weak enforcement?

---

## OUTPUT FORMAT

Write your report in clear, plain language with actual numbers and evidence. When something is broken, explain what it means practically.

Include the actual queries or code you used, so findings can be independently verified.

Organize findings by severity:
- **CRITICAL** — Blocks basic use or produces wrong results organizers would act on
- **HIGH** — Significant gap that reduces platform value
- **MEDIUM** — Should be fixed soon but doesn't break core functionality
- **LOW** — Nice to have / cleanup

Number your findings (e.g., Finding 1.1, Finding 1.2) so they can be cross-referenced with the other auditors.

State your confidence in each finding:
- **Verified** — You tested it and confirmed
- **Likely** — Strong evidence but not fully tested
- **Possible** — Inferred from indirect evidence

---

## CROSS-AUDIT COMPARISON

Three AI tools are auditing the same system. To make comparison easier:

1. Use the severity labels above consistently
2. Number all findings
3. Note your confidence level
4. If you encounter ambiguous metrics (like match rates that can be measured different ways), explain BOTH interpretations
5. If you disagree with something in the documentation, explain why

---

*This prompt was built from: CLAUDE.md, PROJECT_STATE.md, UNIFIED_ROADMAP_2026_02_19.md, UNIFIED_PLATFORM_REDESIGN_SPEC.md, PROJECT_DIRECTORY.md, PIPELINE_MANIFEST.md, CODEX_TASKS_2026_02_22.md, DOCUMENT_RECONCILIATION_ANALYSIS.md, AUDIT_2026_FILE_INVENTORY.md, SCORING_SPECIFICATION.md, and actual current database state.*
