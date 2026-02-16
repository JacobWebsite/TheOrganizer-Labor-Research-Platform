# Labor Relations Research Platform — TRUE Roadmap
**Date:** February 15, 2026
**Supersedes:** All prior roadmaps (ROADMAP.md, v12, EXTENDED_ROADMAP, ROADMAP_TO_DEPLOYMENT, Roadmap_2_15v1, Roadmap_2_15v2)
**Built from:** Codex Round 2 Audit, Claude Round 2 Audit, Consolidated Audit Comparison, Matching Improvement Plan, Historical Employer Analysis, and 10+ strategy/research documents
**Resolved by:** Direct owner decisions on 6 key disagreements between V1 and V2

---

## How This Roadmap Was Made

Two AI assistants (Codex and Claude Code) each independently read the same 16 source documents — audits, research notes, case studies, implementation plans — and produced their own roadmaps. Those two roadmaps agreed on most things but disagreed on six important questions about timing, scope, and priorities.

This document is the result of comparing those two roadmaps, identifying every disagreement, and making explicit decisions about each one. Nothing here is a guess or a compromise — every choice was made deliberately.

### The Six Decisions That Shaped This Roadmap

| Question | V1 (Codex) Said | V2 (Claude Code) Said | Decision |
|----------|-----------------|----------------------|----------|
| Timeline | 6 weeks, 4 phases | 14+ weeks, 7 phases | **V2: Be thorough (14 weeks, 7 phases)** |
| When to fix the frontend | Weeks 2-4 (early) | Weeks 6-12 (after data work) | **V1: Early — organizers need a cleaner interface now** |
| When to add new data sources | Only after matching is standardized | In parallel with matching work | **V1: Wait — standardize matching first** |
| How ambitious is the scoring model | Pilot/experiment only | Core deliverable with its own phase | **Middle ground: Plan for it but don't block the release on it** |
| Deployment priority | Not addressed | Full phase with Docker, CI/CD | **Plan for it but it's not urgent (a couple months out)** |
| Frontend screen structure | 4 minimal screens | 5 areas with sub-views | **Start with 4, architect it so the 5-area structure can be added later** |

---

## What the Platform Looks Like Today (Honest Assessment)

### Things That Are Working Well (All Auditors Agree)

The 60,000-orphan fix was the single biggest win — every employer-union relationship in the database now connects properly to a real record. Before this fix, roughly 60,000 employer records were pointing to unions that didn't exist in the system, which made huge chunks of the data unusable.

The 9-factor scoring system is unified in the backend. There's one materialized view (think of it as a pre-calculated results table that the database keeps ready so it doesn't have to re-compute scores every time someone asks) that scores 22,389 employers. The score no longer changes depending on whether you see it in a list versus a detail page.

The frontend was split from one massive 10,500-line file into 21 separate files (1 HTML + 1 CSS + 19 JS). All the connections between the website interface and the backend data system are verified working.

Match rates improved dramatically — the system can now connect 47.3% of current employers to OSHA safety records (up from almost nothing), 16% to wage theft records, 11.9% to nonprofit filings, and 28.7% to NLRB election records.

Security improved significantly — the exposed password was removed, the system has JWT authentication (a way of verifying who's logged in using encrypted tokens), and all database queries are protected against injection attacks (a common hacking technique where someone types malicious code into a search box).

359 automated tests pass across 19 test files, covering matching, scoring, the API, authentication, data integrity, temporal decay, propensity models, and more.

### Things That Were Broken (Status as of Phase 5 Completion, Feb 16 2026)

| What Was Wrong | Status | Resolution |
|---------------|--------|------------|
| 3 density endpoints crash | **FIXED (Phase 1)** | Changed row[N] to row['col'] in all 6 density endpoints. |
| Authentication is disabled by default | **FIXED (Phase 1)** | Auth enforced when JWT_SECRET set. Note: `.env` still has `DISABLE_AUTH=true` for local dev -- must be removed for production. |
| 824 union file number orphans | **IMPROVED** | Reduced to 518 (37% reduction). Remaining are defunct unions not in unions_master. |
| 29 scripts have a password bug | **FIXED (Phase 1)** | All migrated to use `db_config.get_connection()`. |
| GLEIF raw schema is 12 GB | **NOT FIXED** | Still present. Target for Phase 6 cleanup. |
| Only 37.7% of employers have industry codes | **IMPROVED (Phase 1)** | NAICS backfill from OSHA matches. Coverage improved but still partial. |
| 299 unused database indexes wasting 1.67 GB | **NOT FIXED** | Still ~300 unused indexes. Target for Phase 6. |
| Documentation is ~55% accurate | **IMPROVED** | README rewritten (Phase 1), updated again (Phase 5). Some staleness remains. |
| modals.js is 2,598 lines | **FIXED (Phase 2)** | Split into 8 focused modal-*.js files. Largest is now ~400 lines. |
| Frontend has old score label remnants | **FIXED (Phase 2)** | All references unified to 8-factor SCORE_FACTORS system in config.js. |

### Platform by the Numbers

| What | Count |
|------|-------|
| Database size | ~20 GB (12 GB is the GLEIF raw data that should be archived) |
| Tables | 174 total |
| Views | 186 |
| Total rows | ~23.9 million (public) / ~76.7 million (with GLEIF raw data) |
| API endpoints | 160 across 17 route groups |
| Automated tests | 359 (all passing, 19 test files) |
| Current employers tracked | 67,552 |
| Historical employers (no longer active) | 79,311 |
| Python scripts | ~548 |
| Frontend files | 21 (down from 1 monolith) |

---

## Audit Conflicts: What the Auditors Disagreed About and What We Decided

When three different auditors look at the same system, they sometimes measure things differently or interpret the same data differently. Here's every conflict, explained simply, and the resolution.

### OSHA Match Rate: 47.3% or 25.37%?

The auditors got different numbers because they divided by different things. Claude divided the number of successful OSHA matches by the *current* employers (employers with active union contracts right now). Codex divided by *all* employers (including historical ones from expired contracts). As of Phase 5 completion: 67,552 current + 79,311 historical = 146,863 total.

Both numbers are correct — they just answer different questions. The 47.3% answers "how many active employers can I look up safety records for?" The 25.37% answers "what fraction of our entire employer database has OSHA connections?"

**Decision:** Report both. Use the current-employer rate (47.3%) for organizer-facing screens because that reflects what an organizer actually experiences. Use the all-employer rate (25.37%) for internal data quality tracking.

### WHD and 990 Matching: Fixed or Still Broken?

The confusion here came from there being two different paths to get to the same data. Think of it like two roads to the same destination — one road was repaired and works great, the other road is still full of potholes.

The primary path (going from F7 employer records directly to wage theft records) improved 8x, from 2% to 16%. That's the road organizers actually travel. Codex tested a secondary path (going through Mergent commercial data to wage theft records) which was never the main route and is still weak.

Same story with 990 nonprofit matching — the dedicated matching table works well (14,000+ matches). Codex checked an old, unused column on the Mergent table that only had 69 matches.

**Decision:** Mark as IMPROVED (not "fixed" or "broken"). The old Mergent columns that caused confusion should be clearly labeled as outdated or removed entirely so future audits don't get tripped up by them again.

### Scoring: Unified or Dual?

The backend scoring system IS unified — one calculation, one result, consistent everywhere. But the frontend code still has leftover references to old scoring scales from before the unification. These aren't causing visible bugs for users right now, but they're confusing for anyone reading the code, and they could cause problems later.

**Decision:** Backend is correct. Frontend cleanup moves to Phase 2 (the early frontend work) because even though it's not causing user-facing bugs today, inconsistent score references erode trust when organizers start using it seriously.

### GLEIF Storage: 396 MB or 12 GB?

Both auditors were right — they were looking at different parts of the database. The useful, distilled corporate ownership data lives in the main part of the database and takes up 396 MB. But there's a separate area (a different "schema," which is like a folder within the database) holding the raw, unprocessed bulk download that's 12 GB.

**Decision:** Archive (back up and remove) the 12 GB raw schema. Only the 310 MB distilled table is actually used by any part of the platform. This would cut the database size roughly in half.

### NAICS Industry Code Coverage: 37.7% or 94.46%?

Again, different populations. Claude checked the employers that actually matter for scoring. Codex checked all employers including historical ones that got industry codes backfilled from other sources.

**Decision:** For scoring purposes, 37.7% is the real number. The fix: pull NAICS codes from OSHA matches (71.8% of OSHA records include industry codes) and fill in the gaps. This is a quick win that dramatically improves scoring quality.

### NLRB Participant Orphans: Crisis or Expected?

Codex flagged that 92.34% of NLRB participant records don't connect to election records. That sounds catastrophic, but it's actually how the data is structured. The NLRB participants table includes people from ALL types of cases — unfair labor practice complaints, representation petitions, decertification attempts, and more. Only a small fraction of those cases are actual elections.

**Decision:** This is structurally expected, not a bug. However, it IS a real limitation — you can't easily look up "this employer's complete NLRB history" because the data is fragmented across case types. Build a unified NLRB view that bridges these case types and clearly documents what connects to what.

---

## Execution Plan: 7 Phases Over 14 Weeks

### Phase 1: Fix What's Broken (Week 1)
**Goal:** Zero crashes, zero critical security holes, zero data integrity traps
**Effort:** 2-3 focused days

This phase is entirely about trust. Nothing new gets added. Everything that's broken gets fixed. An organizer using the platform after this phase should never hit a crash or see data that doesn't make sense.

**1.1 Fix the 3 crashing density endpoints**
The density pages (which show how concentrated union activity is in geographic areas) crash because of a mismatch in how the code reads data. The code says "give me the first column" but the database returns data labeled by name, not by number. Fix: change the code to ask for columns by name instead of by position.
Time: 2-4 hours including testing.

**1.2 Run ANALYZE on the entire database**
PostgreSQL (the database system) makes guesses about how to find data efficiently. Those guesses are based on statistics it collects about the data. If it's never collected those statistics (which is the case for 150+ tables), it's basically guessing blind, which means slow or wrong query results. Running ANALYZE tells it to look at the actual data and update its statistics.
Time: 2 minutes (literally one command).

**1.3 Fix the 29 scripts with the password bug**
These scripts contain a mistake where the code that's supposed to look up a password is instead sending the literal text of that code as the password. They only work right now because the database doesn't require a password. Once security is enforced, all 29 would break.
Fix: Replace the broken connection code in each script with a call to the shared connection function that already works correctly.
Time: 4-8 hours.

**1.4 Investigate and fix 824 union file number orphans**
824 employer records point to union file numbers that don't exist. Need to figure out: are these defunct unions that should be added to the unions table? Or are these just bad data from the historical import? The answer determines the fix.
Time: 4-8 hours.

**1.5 Backfill NAICS industry codes from OSHA matches**
Only 37.7% of current employers have industry codes, but 71.8% of OSHA records include them. Since we've already matched many employers to OSHA records, we can copy those industry codes over. One database update command, then refresh the scoring.
Time: 2-4 hours.

**1.6 Archive the GLEIF raw schema**
Back up the 12 GB raw corporate ownership data to a compressed file, then remove it from the active database. The 310 MB distilled version stays. This cuts the database nearly in half.
Time: 4-8 hours (mostly being careful nothing breaks).

**1.7 Fix the documentation**
Update the README so it actually matches reality: correct startup command, correct file paths, correct feature descriptions, correct endpoint counts. Add historical banners to outdated documents so no one treats them as current.
Time: 2-4 hours.

**1.8 Enforce authentication**
Make the system require a login when running in anything other than local development mode. Right now, auth is built but turned off by default. Flip that: it should be ON by default and only disabled for local testing.
Time: 2-4 hours.

**Exit criteria (how we know this phase is done):**
- All 160 API endpoints respond without crashing
- Authentication is required unless explicitly running in dev mode
- Documentation matches what the platform actually does
- No scripts with the password bug remain
- NAICS coverage jumps above 50% of current employers

---

### Phase 2: Frontend Cleanup and Quick Wins (Weeks 2-4)
**Goal:** The interface is cleaner, less confusing, and doesn't show contradictory information
**Effort:** 2-3 weeks

This is where the two original roadmaps disagreed the most. V1 said do frontend early; V2 said wait. The decision was to do it early because organizers need to trust what they see on screen, and contradictory scores or confusing navigation undermines that trust immediately.

However, this is NOT the full redesign. This is cleanup and quick structural improvements. The bigger redesign (expanding from 4 screens to 5 areas with sub-views) comes later.

**2.1 Implement 4-screen structure**
Reorganize the interface into four clear pages:
1. **Territory Overview** — Map and big-picture view of a geographic area
2. **Employer Profile** — Everything about one employer on one page
3. **Union Profile** — Everything about one union on one page
4. **Admin / Review Queue** — Internal tools for data quality review

All developer-oriented tools (API testing pages, raw data views) move to a separate "Developer Tools" area that doesn't show up in the regular organizer navigation.

The architecture should be built so that these 4 screens can later split into V2's 5-area structure (Dashboard, My Territory, Employer Research, Organizing Targets, Data Explorer) without having to rebuild from scratch.

**2.2 Remove all dual-score remnants**
Search the entire frontend codebase for references to old scoring scales (0-62 sector score, 0-100 OSHA score, 6-factor references) and remove them. Every score reference should point to the current 9-factor unified system.

**2.3 Split modals.js into feature modules**
Break the 2,598-line modals.js into focused files:
- `modal-employer-detail.js` — employer popup
- `modal-corporate.js` — corporate family tree
- `modal-analytics.js` — charts and analytics
- `modal-comparison.js` — side-by-side comparison
- `modal-elections.js` — NLRB election data
- `modal-shared.js` — shared open/close/overlay utilities

Why this matters: When one giant file handles everything, a small change to the employer popup can accidentally break the analytics charts. Splitting into focused files means each piece can be understood and changed independently.

**2.4 Replace inline event handlers with JavaScript listeners**
Right now, there are 103 places in the HTML where button clicks are handled by code written directly in the HTML (like `onclick="doSomething()"`). This is an older pattern that makes code harder to maintain and test. Replace these with JavaScript event listeners, which keep the logic in the JavaScript files where it belongs.

**2.5 Add confidence and freshness indicators**
When an organizer sees that an employer has OSHA violations, they should also see: How confident is this match? (HIGH/MEDIUM/LOW) and When was this data last updated? This information currently exists in the backend but isn't shown to users.

**2.6 Publish a metrics glossary**
Create one reference document that defines every number the platform shows: what the score means, what scale it uses, what "match rate" means and which denominator is being used, what each confidence level represents. This eliminates the ambiguity that caused auditors to disagree.

**Exit criteria:**
- Zero references to old scoring scales anywhere in the interface code
- No file larger than ~1,200 lines
- Zero hardcoded localhost URLs in user-facing pages
- Confidence and freshness visible on employer detail pages
- Top organizer workflow (find targets → view profile → export) takes under 5 minutes

---

### Phase 3: Matching Pipeline Overhaul (Weeks 3-7)
**Goal:** Every match in the system is standardized, auditable, and has a confidence rating
**Effort:** 4-5 weeks (overlaps with the tail end of Phase 2)

This is the foundation that everything else builds on. Right now, each data source has its own matching approach — the way employers get connected to OSHA records is different from how they get connected to 990 records, which is different from NLRB, and so on. This means you can't easily compare match quality across sources or understand why a particular match was made.

Think of it like this: if five different people are filing documents but each uses their own filing system, nobody can find anything consistently. This phase creates one filing system that everyone uses.

**3.1 Standardize match output format (Week 3)**
Every match — regardless of source — should produce a record with the same fields:
- Where the match came from (source system and ID)
- Where it matched to (target system and ID)
- How the match was made (exact name? fuzzy name? address? EIN?)
- How confident the system is (HIGH / MEDIUM / LOW)
- A numeric score
- When the match was made and which matching run produced it
- The evidence (the specific fields that matched and how closely)

This is the single most important technical decision in the roadmap. Once every match looks the same, you can compare quality across sources, build quality dashboards, and let humans review uncertain matches — all with one set of tools.

**3.2 Normalize all name-matching (Week 3)**
Right now, different matching scripts clean up company names differently before comparing them. One might turn "WALMART INC." into "walmart," while another might turn it into "wal mart inc." This inconsistency means the same comparison can give different results depending on which matcher runs it.

Fix: Create one canonical name-cleaning function with three intensity levels (standard, aggressive, and fuzzy) that every matcher uses.

**3.3 Improve deterministic matching (Weeks 3-4)**
Deterministic matching is the simplest kind — it's when two records match on exact criteria (same EIN, same name + same state, same address). The improvements:
- When one source employer matches to multiple target records, add clear tie-breaker rules (prefer same state > same city > newer record)
- Save ALL match attempts — not just the ones that worked, but also the ones that were rejected and the ones that need human review. This audit trail is essential for understanding why match rates are what they are.

**3.4 Add probabilistic matching for unresolved cases (Week 4)**
For cases where deterministic matching can't find an answer (the names are slightly different, the addresses don't quite match), use Splink — a probabilistic matching tool that calculates the probability that two records refer to the same entity based on multiple fields.

Important: Splink doesn't replace the deterministic matching. It only handles the leftover cases that deterministic matching couldn't resolve. Every Splink result gets tagged so you always know it came from the probabilistic path.

**3.5 Build the match quality dashboard (Weeks 4-5)**
A script that generates a regular report showing:
- Match rate by source, by method, by confidence level
- How many matches are HIGH vs MEDIUM vs LOW confidence
- False-positive sample rate (how often does the system incorrectly say two records match?)
- Trends over time (are match rates improving?)
- State-level variation (matching might work great in New York but poorly in Texas — why?)

**3.6 Surface match evidence in the API (Week 5)**
When the API returns information about an employer's OSHA matches or 990 matches, include the match method and confidence level. Organizers should be able to see: "This employer was matched to this OSHA record based on exact name and state match (HIGH confidence)" rather than just seeing the OSHA data with no explanation of where it came from.

**3.7 Build the NLRB bridge view (Weeks 5-6)**
Create a unified view that brings together all NLRB case types (elections, unfair labor practice complaints, representation petitions) for a given employer. Clearly document which case types are expected to NOT have election records. This makes "show me this employer's complete NLRB history" actually answerable.

**3.8 Resolve historical employers (Weeks 6-7)**
The 79,311 historical employers (ones with expired union contracts) currently create confusion in dashboards because they inflate denominators without being relevant to active organizing. Options decided:
- Merge the ~4,942 that appear to be duplicates of current employers (after manual review)
- Keep the rest flagged as historical with a clear `is_historical` filter
- Run matching against OSHA/WHD for historical trend analysis (answers questions like "what happened to working conditions after the union left?")
- Don't delete anything — archive with full provenance

**Exit criteria:**
- Every match row has: method, tier, confidence band, evidence, and run ID
- One name-normalization function used by all matchers
- Match quality dashboard runs weekly
- NLRB bridge view documented and queryable
- Historical employer denominator confusion eliminated from core dashboards

---

### Phase 4: New Data Sources (Weeks 8-10)
**Goal:** Add the highest-value external data that's currently missing
**Effort:** 3 weeks

This phase was the subject of a key decision: V2 wanted to run data expansion in parallel with matching work; V1 said wait until matching is standardized. The decision was to wait. Here's why that matters:

Adding new data sources before the matching pipeline is standardized means each new source would use its own ad hoc matching approach — exactly the problem Phase 3 was designed to fix. By waiting, every new data source gets integrated through the standardized match contracts, with consistent confidence scoring and evidence tracking from day one.

The order below is based on value per hour of effort:

**4.1 SEC EDGAR Full Index (HIGH priority)**
What it is: The SEC (Securities and Exchange Commission) requires public companies to file financial reports. The EDGAR database contains records for 300,000+ public companies, including their official company identifier (CIK number), and sometimes their tax ID (EIN).

Why it matters: The platform currently has only 4,891 SEC matches. With the full EDGAR index and EIN-based matching (possible because some XBRL filings include the EIN), we could dramatically expand corporate crosswalk coverage. This tells you things like: who owns this company, how many employees do they have, what did they disclose about labor relations in their annual report.

Tool: `edgartools` — an open-source Python library specifically designed for working with EDGAR data.
Time: 8-12 hours.

**4.2 IRS Business Master File (HIGH priority)**
What it is: The IRS keeps a master list of all tax-exempt organizations (~1.8 million). The current 990 matching only covers organizations that actively filed 990 forms (586,000), missing over a million.

Why it matters: Many unions and labor-related nonprofits are in the BMF but haven't filed 990s (or filed older ones that aren't in our dataset). Matching against the BMF could roughly double our 990 match rate from 11.9% to potentially 25%+.

Tool: ProPublica Nonprofit Explorer API or IRS bulk data download.
Time: 10-14 hours.

**4.3 CPS Microdata via IPUMS (MEDIUM priority)**
What it is: The Current Population Survey is a monthly survey that asks Americans about their jobs, including whether they're union members. IPUMS is a free service that makes this microdata accessible for research.

Why it matters: The scoring system currently uses published BLS union density rates, which are broad averages (e.g., "12% of construction workers are unionized nationally"). CPS microdata would let us calculate much more precise estimates — for example, "union density for construction workers in the Chicago metro area specifically." This makes the industry-density scoring factor dramatically more accurate.

Tool: `ipumspy` Python package (free with academic registration).
Time: 15-20 hours.

**4.4 OEWS Staffing Patterns (MEDIUM priority)**
What it is: The Occupational Employment and Wage Statistics survey tells you the mix of occupations in each industry — how many truck drivers, warehouse workers, nurses, etc.

Why it matters: Two employers might have different industry codes (one is "warehouse" and one is "logistics") but employ very similar types of workers. If one is already organized, the other is a natural target. This data enables "workforce composition similarity" — a completely different way of finding comparable employers that doesn't depend on industry codes.

Time: 10-14 hours.

**Exit criteria:**
- All new data sources matched through the Phase 3 standardized pipeline
- Every new match has method, confidence band, and evidence
- No new data source bypasses the confidence policy
- Match rate improvements documented

---

### Phase 5: Scoring Model Evolution (Weeks 10-12)
**Goal:** Move from hand-picked scoring weights toward empirically validated ones
**Effort:** 2-3 weeks

The decision here was "middle ground" — plan for the advanced scoring model but don't block the release on it. That means this phase has a "core" layer that definitely ships and an "advanced" layer that's developed but flagged as experimental.

**Core (ships):**

**5.1 Temporal scoring decay**
A safety violation from last year should matter more than one from 10 years ago. Right now, all violations count the same regardless of age. Add time-based decay so recent violations weigh more heavily. Apply to: OSHA violations (10-year half-life) and NLRB elections (7-year half-life). **Status: DONE.** WHD is not a scoring factor in the MV, so decay does not apply to it.

Why this works: It uses a mathematical formula (exponential decay) where the weight drops off over time. A violation from 1 year ago might count at 90% weight, 5 years ago at 50%, 10 years ago at 15%. The exact rate is tunable per factor.

**5.2 Hierarchical NAICS similarity**
Right now, the scoring system treats industry matching as binary — either two employers have the same industry code or they don't. But NAICS codes have a built-in hierarchy: the first 2 digits are the broad sector, 3 digits is more specific, all the way down to 6 digits being very precise.

Two employers sharing 5 out of 6 digits are much more comparable than two sharing only 2 digits. This change makes the industry-density factor a gradient instead of a yes/no, which is far more useful.

**5.3 Score version tracking**
Add a version identifier to every scored record. When the scoring methodology changes (new factors, new weights, new decay rates), the version increments. This means you can always tell what methodology produced a given score, and compare scores across methodology versions.

**Advanced (experimental, doesn't block release):**

**5.4 Gower distance enhancement**
The platform already has a comparables feature (the `employer_comparables` table with 270,000 rows) that finds employers similar to each other. Enhance it with weighted dimensions — give more importance to industry similarity (3x weight) and OSHA violations (2x weight) compared to state (1x) and size (1x). Also compute "distance from nearest unionized sibling" as a new scoring factor.

**5.5 Propensity score model (experimental)**
This is the most powerful potential enhancement. Use logistic regression (a statistical method that predicts the probability of an outcome based on multiple factors) trained on 33,096 historical NLRB elections to predict: "Given everything we know about this employer, how likely is a successful organizing campaign?"

The predicted probability IS the organizing opportunity score. This replaces hand-picked weights with empirically optimal ones learned from actual outcomes.

Prerequisites: Match rates need to be improved (Phase 3) and NAICS backfilled (Phase 1.5).
Success criteria: If the model's accuracy (measured by AUC) is above 0.65, publish it as an experimental score alongside the current heuristic. If below 0.55, the features need work — go back to improving data quality.

**This ships as experimental** — visible to users as "Experimental: AI-suggested opportunity score" alongside the established 9-factor score. It does NOT replace the current scoring system until it's been validated.

**Exit criteria:**
- Temporal decay applied to OSHA and NLRB factors -- **DONE**
- Hierarchical NAICS similarity replacing binary matching -- **DONE (6-digit gradient blend)**
- Score versioning in place -- **DONE (`score_versions` table, auto-insert on create/refresh)**
- Propensity model built and measured (even if experimental) -- **DONE (Model A AUC=0.72, Model B AUC=0.53, 146K employers scored)**

---

### Phase 6: Deployment Preparation (Weeks 11-14)
**Goal:** Make the platform accessible to other people when the time comes
**Effort:** 2-3 weeks, not blocking other work

This is planned but not urgent — remote access isn't needed for a couple of months. The work here is about making sure that when the time comes, deployment isn't a scramble.

**6.1 Docker setup**
Docker is a tool that packages the entire platform — the code, the database, the web server, all the settings — into a container that can run identically on any computer. Without Docker, getting the platform running on a new machine means hours of installing dependencies and configuring settings. With Docker, it's one command.

Deliverable: A `docker-compose.yml` file that starts the API server, the PostgreSQL database, and a web server together.

**6.2 CI/CD pipeline**
CI/CD (Continuous Integration / Continuous Deployment) means that every time code changes are pushed to GitHub, the 359 automated tests run automatically. If any test fails, you know immediately what broke and when. This prevents the "it worked yesterday, now it doesn't, and nobody knows what changed" problem.

Deliverable: GitHub Actions configuration that runs tests on every push and lints (checks for code style issues) on every pull request.

**6.3 Automated scheduling**
Certain maintenance tasks need to happen regularly: refreshing the materialized views (the pre-calculated score tables), checking data freshness, running ANALYZE on frequently-used tables, and backing up the database. Right now, all of this is manual.

Deliverable: A scheduling configuration (probably cron jobs or a simple task scheduler) for weekly maintenance.

**6.4 Script lifecycle management**
There are ~494 Python scripts. Some are the "official" pipeline for rebuilding data, some are one-off experiments, some are deprecated but never deleted. Create a manifest that documents which scripts are active (part of the real pipeline), which are legacy (kept for reference), and which are experimental. Move deprecated scripts to an archive folder.

**6.5 Drop unused database indexes**
Confirm the 299 unused indexes are genuinely unused (check that zero queries have used them), then drop them to reclaim ~1.67 GB of storage and speed up data inserts and updates.

**Exit criteria:**
- Docker setup works (can start from scratch on a clean machine)
- CI/CD runs tests automatically on code push
- Weekly maintenance automated
- Script manifest published
- Unused indexes removed

---

### Phase 7: Intelligence Layer (Week 14+, Ongoing)
**Goal:** Forward-looking features that transform the platform from a lookup tool into a strategic intelligence system
**Effort:** Ongoing, depends on all earlier phases

These are the high-value ideas from the research documents that depend on earlier phases being complete. They're documented here so they don't get lost, but they're explicitly not blocking the release.

**7.1 Web scraper pipeline expansion**
The AFSCME scraper proved the concept — 295 profiles crawled, 103 sites processed, 160 employers extracted. Expand to Teamsters (338 locals), SEIU, UFCW, and UNITE HERE. Use the two-step architecture: Crawl4AI fetches web pages, then AI extracts structured data from the messy HTML. Match extracted employers against the main database.

**7.2 State PERB data (original contribution)**
No open-source tools exist for scraping state Public Employee Relations Board data. Building scrapers for NY PERB, CA PERB, and IL ILRB would be the first of its kind and directly fills the gap where federal data doesn't cover public-sector employers. This is one of the platform's biggest potential differentiators.

**7.3 "Union-lost" analysis**
The 79,311 historical employers represent workplaces that once had union contracts but no longer do. Matching them against OSHA/WHD/NLRB could answer: "Which employers decertified? What happened to working conditions after the union left?" This is research-grade analysis that would be valuable for academic partners and strategic planning.

**7.4 Board report generation**
One-click PDF/CSV exports for union board presentations: territory overview, top targets with evidence, trend charts, data freshness statement. This is a "last mile" feature that makes the platform useful for the actual meetings where organizing decisions get made.

**7.5 Occupation-based similarity** -- **DONE (completed in Phases 4-5)**
BLS staffing patterns used to compare employers by workforce composition. `occupation_similarity` table (8,731 pairs), `industry_occupation_overlap` table (130,638 rows), integrated into Gower as 14th feature (occupation_overlap, weight 1.5). Two employers with different NAICS codes but similar occupation mixes are now identified as comparable.

**7.6 Expanding frontend to 5-area structure**
When the platform is mature enough, expand from the initial 4-screen structure to V2's 5-area layout:
- Dashboard (quick snapshot / landing)
- My Territory (union-specific coverage map)
- Employer Research (detail + corporate family)
- Organizing Targets (scorecard + comparables + evidence)
- Data Explorer (density, trends, elections, analytics)

This expansion was architecturally planned for in Phase 2 so it can happen incrementally without rebuilding the navigation.

---

## Dependency Map (What Blocks What)

```
Phase 1 (Fix Broken) ─── MUST COMPLETE FIRST
  │
  ├──→ Phase 2 (Frontend Cleanup) ─── can start Week 2
  │       │
  │       └──→ Phase 7.6 (Frontend Expansion) ─── later
  │
  ├──→ Phase 3 (Matching Overhaul) ─── can start Week 3, overlaps with Phase 2
  │       │
  │       ├──→ Phase 4 (New Data Sources) ─── BLOCKED until matching standardized
  │       │       │
  │       │       └──→ Phase 5 Advanced (Propensity Model) ─── needs improved data
  │       │
  │       └──→ Phase 5 Core (Decay, NAICS hierarchy) ─── needs matching quality
  │
  └──→ Phase 6 (Deployment) ─── independent, can overlap with anything after Phase 1
          │
          └──→ Phase 7 (Intelligence) ─── needs stable deployment
```

**Critical path:** Phase 1 → Phase 3 → Phase 4 → Phase 5 Advanced
**Parallel track:** Phase 2 (frontend) runs alongside Phase 3 (matching)
**Can start any time after Phase 1:** Phase 6 (deployment)
**Depends on everything:** Phase 7 (intelligence layer)

---

## Effort Summary

| Phase | What | Weeks | Key Deliverable |
|-------|------|-------|-----------------|
| 1: Fix Broken | Crashes, security, data integrity | Week 1 | Zero critical bugs |
| 2: Frontend Cleanup | Interface trust and usability | Weeks 2-4 | 4 clear screens, no contradictory scores |
| 3: Matching Overhaul | Standardize all matching | Weeks 3-7 | Auditable, confidence-scored matching pipeline |
| 4: New Data Sources | SEC, IRS, CPS, OEWS | Weeks 8-10 | High-value data integrated through standard pipeline |
| 5: Scoring Evolution | Better scoring model | Weeks 10-12 | Temporal decay + experimental propensity model |
| 6: Deployment Prep | Docker, CI/CD, scheduling | Weeks 11-14 | Ready for remote access when needed |
| 7: Intelligence | Scrapers, PERB, reports | Week 14+ | Strategic intelligence features |

**If you have one focused week:** Phase 1 resolves every critical issue.
**If you have one month:** Phase 1 + Phase 2 + most of Phase 3.
**If you have three months:** All of Phases 1-6, start Phase 7.

---

## Governance: How to Keep This on Track

**Weekly check-ins (even if just a quick self-review):**
- Are any API endpoints crashing? (Check the smoke tests)
- What's the match quality dashboard showing? Any drops?
- How's the frontend cleanup burn-down going? (File sizes, remaining old score references)
- Does the documentation still match reality?

**Every two weeks:**
- Re-rank the remaining backlog items by "how much does this help an actual organizer" rather than "what's easiest to build next"

**After each work session:**
- Update the session log with what was done
- If any phase completed, move its items to a "Completed" section rather than deleting them

---

## Outdated Documents

These documents contributed to this roadmap but now contain outdated claims. They should be kept for historical reference but marked clearly:

| Document | What's Outdated |
|----------|----------------|
| MERGENT_SCORECARD_PIPELINE.md | References old API structure, 6-factor scoring, NY-only scope |
| README.md | Wrong startup command, wrong file paths, wrong scoring description |
| AFSCME_NY_CASE_STUDY.md | References 6-factor scoring, nonexistent API endpoints |
| EXTENDED_ROADMAP.md | Lists checkpoints H-O as all pending (several are done) |
| LABOR_PLATFORM_ROADMAP_v12.md | Old score scale (0-62), old factor count (6) |
| AFSCME scraper prompt | Contains hardcoded password (removed from all code) |
| Roadmap_2_15v1.md | Superseded by this document |
| Roadmap_2_15v2.md | Superseded by this document |

Add `[HISTORICAL — See Roadmap_TRUE_02_15.md]` banners to each.

---

*This roadmap is a living document. Update it after each work session. When a phase completes, move its items to a "Completed" section rather than deleting them.*
