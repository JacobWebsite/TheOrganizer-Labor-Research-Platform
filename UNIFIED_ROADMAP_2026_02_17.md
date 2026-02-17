# Labor Relations Research Platform — Unified Roadmap

**Date:** February 17, 2026
**Replaces:** All prior roadmaps — UNIFIED_ROADMAP_2026_02_16, TRUE Roadmap, ROADMAP_TO_DEPLOYMENT, v10 through v13, and all others. Those documents should be moved to archive.
**Built from:** Three independent AI reviews (Claude, Codex with live database verification, Gemini synthesis), 22 feedback items reviewed and decided in planning session (Feb 16-17, 2026), plus all strategy and research documents in the project.

---

## How to Read This Document

This is the single source of truth for where the platform stands, what's wrong, and what to do next. Everything is written in plain language. When a technical concept comes up, it's explained right there.

The document has four parts:

1. **Where Things Stand** — an honest inventory of what exists and what works
2. **What's Wrong** — every known problem, ranked by severity
3. **What to Do Next** — a phased plan with clear checkpoints
4. **What Comes Later** — the bigger vision, organized by timeframe

---

## PART 1: WHERE THINGS STAND

### The Big Picture

The platform pulls together data from 18+ government and public databases — which employers have union contracts, which ones have safety violations, which ones have had union elections, who owns whom — and combines all of that into a system that helps organizers figure out where to focus their limited time and resources.

Instead of an organizer separately searching OSHA's website, the NLRB's website, the Department of Labor's website, and the SEC's website to learn about one employer, this platform has already gathered all of that information and linked it together. It then scores employers on how promising they look as organizing targets.

As of today, the core data is loaded, the matching engine works, the scoring system exists, and there are 359 automated checks that verify things are working. But the platform is **not yet ready for other people to use**. There are important accuracy problems, the security isn't production-ready, and the whole thing only runs on one laptop.

### What's in the Database

| What | Count | What This Means |
|------|-------|-----------------|
| Tables | 174+ | Each table holds one specific type of information — employers, unions, OSHA violations, etc. |
| Views | 186 | Saved lookups that combine information from multiple tables. They don't store new data — they just show existing data in useful ways. |
| Materialized views | 4 | Like views, but the computer saves the results so it doesn't have to recalculate every time. The organizing scorecard is one of these. The tradeoff: saved results can go stale if underlying data changes. |
| Employer records | 146,863 | The core list. Roughly 67,552 "current" (active union relationships) and 79,311 "historical" (past relationships that ended). |
| Total records | ~24 million | Plus ~53 million raw corporate ownership records not yet cleaned. |
| Database size | ~20 GB | About 12 GB is raw corporate ownership data that could be archived. |

### Every Connected Data Source

| Source | What It Contains | Records | Match Rate to Employers |
|--------|-----------------|---------|------------------------|
| **OLMS F-7** | Which unions bargain with which employers | 146,863 employers | This IS the core list |
| **OLMS LM** | Union financial reports | 331,238 filings | Connected through union IDs |
| **OSHA** | Workplace safety inspections and violations | 1M workplaces, 2.2M violations | 47.3% of current employers |
| **NLRB** | Union election results and unfair labor practice complaints | 33,096 elections, 1.9M participants | 28.7% of current employers |
| **WHD (Wage & Hour)** | Wage theft enforcement cases | 363,365 cases | 16.0% of current employers |
| **IRS Form 990** | Nonprofit financial filings | 586,767 filers | 11.9% of current employers |
| **SAM.gov** | Federal government contractor registry | 826,042 entities | 7.5% of current employers |
| **SEC EDGAR** | Public company filings | 517,403 companies | 1,743 direct matches |
| **GLEIF** | Global corporate ownership chains | 379,192 US entities | 3,264 linked |
| **Mergent Intellect** | Commercial business intelligence | 56,426 employers | 947 matched |
| **BLS QCEW** | Employment and wage data by industry | 1.9M rows | Via industry codes |
| **BLS Union Density** | Unionization rates by industry and state | 459+ estimates | Via industry/state |
| **BLS OEWS** | Which occupations exist in which industries | 67,699+ linkages | Via industry codes |
| **USASpending** | Federal contract awards | 47,193 recipients | 9,305 matched |
| **NYC Comptroller** | NYC labor violation records | ~9,000 records | Via name matching |
| **NY Open Book / NYC Open Data** | State and city government contracts | ~101,000 contracts | Via vendor name matching |
| **AFSCME Web Scraper** | Data from AFSCME union websites | 295 profiles, 160 employers | 73 matched (46%) |
| **EPI** | Union membership microdata | 1.4M records | Reference/validation only |

**OLMS data not yet being used:** Four annual report tables sitting in the database with valuable information that hasn't been connected to anything yet:
- `ar_disbursements_total` (216,372 records) — union spending by category, including how much they spend on **organizing**
- `ar_membership` (216,508 records) — year-over-year membership counts showing growth/decline
- `ar_assets_investments` (304,816 records) — union financial health (cash, investments, property)
- `ar_disbursements_emp_off` (2,813,248 records) — payments to union officers and employees

### How the Matching System Works

The hardest problem this platform solves is figuring out that "WALMART INC" in OSHA is the same company as "Wal-Mart Stores, Inc." in NLRB and "WAL MART STORES INC" in DOL filings. The platform uses a multi-tier approach — easiest and most reliable methods first, fuzzier methods as fallback:

1. **Exact EIN match** — same tax ID number = definitely the same entity. Gold standard.
2. **Normalized name match** — clean up names (remove "Inc.", "LLC", standardize abbreviations) and check for exact matches.
3. **Address-enhanced match** — same cleaned name AND same city/state? Very likely the same.
4. **Aggressive normalization** — strip even more noise from names and compare.
5. **Fuzzy matching** — algorithms that measure how "similar" two names look, catching typos and abbreviation differences.
6. **Probabilistic matching (Splink)** — a statistical model that weighs multiple pieces of evidence together to estimate the probability two records are the same entity.

Every match goes into a central log (265,526 entries) with a record of which method was used and how confident the system is.

### What's Working Well

- **The BLS benchmark validates the data.** Platform's total membership count (14.5 million workers) matches the Bureau of Labor Statistics' official number within 1.4%.
- **The matching pipeline is auditable.** Every connection between databases has a paper trail.
- **Security went from zero to reasonable.** Login protection, encrypted passwords, rate limiting, zero SQL injection vulnerabilities.
- **The test suite grew 10x.** From 37 to 359 automated checks.
- **The frontend was modularized.** Original 10,500-line monolith split into 21 separate files.

### Key Numbers

| Metric | Value |
|--------|-------|
| NAICS industry code coverage | 84.9% of all employers |
| OSHA match rate (current employers) | 47.3% |
| NLRB match rate (current employers) | 28.7% |
| WHD match rate (current employers) | 16.0% |
| 990 match rate (current employers) | 11.9% |
| Employers with at least one external match | ~61.7% |
| Scorecard rows | 22,389 |
| Automated tests | 359 passing |
| API endpoints | ~160 across 17 routers |

---

## PART 2: WHAT'S WRONG

### CRITICAL — Fix Before Anything Else

**Problem 1: The scorecard is using 10-year-old data.**
The OSHA inspection data goes through 2025, but the scoring system only pulls from inspections dated 2012-2016. An organizer might see "low safety violation activity" when the employer has racked up major violations in 2020-2024. The platform's main output could be actively misleading. Making it worse: the "data freshness" page claims OSHA data was updated recently, which is true for the raw data but not for the scorecard.

**Problem 2: Security is turned off by default.**
The development config has `DISABLE_AUTH=true` which bypasses all login protection. If deployed without changing this one setting, anyone could access everything without logging in.

**Problem 3: Half of all union-employer relationships are invisible.**
The `f7_union_employer_relations` table (119,844 rows) stores the connections between unions and employers. But 60,373 of those relationships (50.4%) point to employer IDs that don't exist in the cleaned employer table — because when employers were deduplicated, the relations table was never updated. This means 7 million workers (44.3% of 15.9M total) are associated with orphaned records. The data isn't lost — it exists in the raw table — but it's silently invisible when anyone queries the database. The same problem exists in the NLRB cross-reference table (14,150 orphaned links, 51%).

### HIGH — Fix Before Letting Others Use It

**Problem 4: The scorecard only covers ~15% of employers.**
22,389 rows out of 146,863 total employers. The scorecard is built around OSHA establishments, so the 85% of employers not matched to OSHA get no score at all. An organizer searching for one of those employers would see nothing.

**Problem 5: Two separate scorecards with different logic.**
The OSHA-based scorecard (22,389 employers) and the Mergent-based scorecard (947 employers) use different factors and different weights. An employer that appears in both could get contradictory assessments.

**Problem 6: The matching pipeline has two bugs.**
First, looser rules sometimes run before stricter rules, meaning the system accepts a weak match without checking if a better one exists. Second, when two different companies normalize to the same name, the system keeps whichever one it saw first and silently drops the other.

**Problem 7: 195 missing unions covering 92,627 workers.**
824 rows in the relations table reference union file numbers that don't exist in the unions master table. The top 2 missing file numbers alone account for 51,811 workers — likely real large unions that merged or reorganized, not data entry errors.

**Problem 8: Corporate hierarchy endpoints are broken.**
The 5 API endpoints for corporate family data reference a column name that doesn't exist in the table. The data is there, the endpoints are there, they just can't talk to each other. Clicking "Corporate Family" shows an error.

**Problem 9: The platform only runs on one laptop.**
No Docker setup, no automatic testing pipeline, no automated maintenance. Everything depends on one machine and one person.

### MEDIUM — Important but Not Blocking

**Problem 10: Match quality dashboard inflates numbers.** Counts total match rows instead of distinct employers, making match rates look higher than reality.

**Problem 11: NLRB time-decay is a dead switch.** Code exists to reduce the weight of old NLRB events, but the decay factor is stuck at 1.0 (no decay) for every record.

**Problem 12: Model B propensity score is basically random.** Accuracy of 0.53 — barely better than a coin flip — but it's scoring 145,000+ employers. Model A (0.72) is decent.

**Problem 13: Documentation keeps falling behind.** CLAUDE.md has 19 known inaccuracies including a startup command that doesn't work. Multiple conflicting roadmap versions exist. This causes AI tools to make wrong assumptions about the project.

**Problem 14: 778 Python files with no manifest.** No clear way to tell which scripts are active pipeline, which are one-time experiments, which are dead. 259 scripts have a broken credential pattern that prevents them from connecting to the database. 9.3 GB of archive data that's already been imported into PostgreSQL is still sitting on disk.

**Problem 15: Database is twice as big as it needs to be.** ~12 GB of raw GLEIF data plus ~1.67 GB of unused indexes. Cleaning up could cut from ~20 GB to ~6 GB.

---

## PART 3: WHAT TO DO NEXT

### How This Plan Is Organized

The key insight from the three-AI review: **fix data correctness before deployment.** It doesn't matter if the platform runs beautifully in a container if the scores it produces are misleading.

The phases below are ordered by dependency — each one builds on what came before. Some can run in parallel where noted.

---

### Phase A: Fix the Foundation (Estimated: 1-2 weeks)

**The goal:** Fix the problems that make the platform's core output untrustworthy.

**Task A1: Fix the F-7 relations orphan problem.**

This is the single most impactful fix. Half of all union-employer relationships are invisible because the relations table points to employer IDs that were retired during deduplication. A merge log exists (21,608 entries) recording which old IDs merged into which new ones — this is the key to reconnecting them.

*How this works:* Think of it like a phone book where half the entries have the wrong phone number. The merge log is a list that says "old number 555-1234 is now 555-5678." We go through every entry with an old number and update it to the new one.

**Checkpoints:**
1. Snapshot "before" numbers — total relationships, connected vs orphaned, workers covered, spot-check 5-10 specific employers
2. Map the merge log — how many orphans can be fixed via the log? Any without log entries? Any cases where one old ID merged into multiple new ones?
3. Dry run on 100 sample relationships — verify the mappings are correct, manually spot-check a few
4. Run the full update inside a database transaction (so it can be rolled back if anything goes wrong)
5. Verify "after" numbers — should see ~100% connected vs the current ~50%
6. Handle leftovers — orphans not in the merge log get matched by name/location, added to the deduped table, or flagged for manual review
7. Apply the same fix to the NLRB cross-reference table (14,150 orphaned links)

*Why this matters:* Until this is fixed, any query about union-employer relationships is silently missing half the data. Every downstream feature — the scorecard, the corporate family view, the search results — is working with an incomplete picture.

**Task A2: Fix the scorecard to use fresh data.**
Update the scoring materialized view to pull from all available OSHA/NLRB data (through 2025), not just the 2012-2016 subset. After rebuilding, the scorecard should clearly show when each piece of data was last updated.

*Why this matters:* This is the platform's primary output. If it's based on decade-old data, it could actively mislead organizers.

**Task A3: Fix the broken corporate hierarchy endpoints.**
Correct the column name reference in the 5 corporate API endpoints. The data exists, the endpoints exist — they just need to point at the right column.

*Why this matters:* Quick win. The corporate family view is one of the most valuable features for organizers, and it's broken by a simple naming error.

**Task A4: Fix the match quality dashboard.**
Change the API to count distinct employers matched, not total match rows. This gives an honest picture of data coverage.

**Task A5: Investigate the F-7 time boundaries.**
The database has 146,863 employer records — 67,552 labeled "current" and 79,311 "historical." But there's no documented definition of what year marks the boundary between current and historical. Figure out: What years does the data actually cover? When does "current" begin? Are there filing gaps (years where an employer appears, disappears, then reappears)?

*Why this matters:* Without understanding the time dimension, we can't tell users whether a relationship is active right now or ended 10 years ago.

**You're done when:**
- Zero orphaned relationships in f7_union_employer_relations
- Zero orphaned links in the NLRB cross-reference
- The scorecard uses the latest available data
- All corporate hierarchy endpoints return valid responses
- The match quality dashboard reports accurate, distinct-employer rates
- The time boundary between "current" and "historical" is documented

---

### Phase B: Fix the Matching Pipeline (Estimated: 1-2 weeks)

**The goal:** Make the connections between databases more accurate, so everything built on top of them is more reliable.

**Task B1: Reorder matching tiers strict-to-broad.**
Right now, some looser matching rules run before stricter ones. This means the system sometimes accepts a weak match when a strong one was available. Reorder so: EIN exact → normalized name+state → address-enhanced → aggressive normalization → fuzzy.

*Why this matters:* Every wrong match cascades — OSHA violations get attributed to the wrong employer, scores become unreliable, and an organizer might get bad information about a target.

**Task B2: Fix the first-hit-wins / name collision bug.**
When two different companies normalize to the same name (like "ABC Services" in New York and "ABC Services" in New Jersey), the system currently keeps whichever it saw first and drops the other. Fix this to use additional information (city, address, industry) to distinguish them, or flag ambiguous cases for review instead of silently picking one.

**Task B3: Bring Splink back into the fuzzy matching tier.**
The current fuzzy tier uses trigram matching — a simple method that only looks at how similar two names are as strings of characters. Splink is a more sophisticated tool already in the project that weighs multiple pieces of evidence (name similarity, state, city, ZIP, industry, address) and calculates an actual probability that two records are the same entity.

*How this is different:* Trigram matching sees "Springfield Hospital" and "Springfield Health Center" and just measures letter-by-letter similarity. Splink sees the names are somewhat similar AND they're in the same city AND the same state AND the same industry, and concludes there's a 94% chance they're the same place. It's smarter because it uses more clues, not just the name.

*Why bring it back now:* Since we're re-running matches anyway after fixing the tier ordering, upgrading the fuzzy tier at the same time means we only do one round of re-matching instead of two. Splink is already installed and configured — it was used for earlier deduplication work.

**Task B4: Re-run affected match tables.**
After the fixes above, re-run the matching pipeline for OSHA (the most affected source — 37% of its matches use a low-confidence fuzzy method) and any other sources with quality issues.

**Task B5: Add confidence flags to the UI.**
Tag every match with a confidence level. Matches above 0.9 confidence get no flag (they're reliable). Matches below 0.7 get flagged as "probable match — verify if critical." This lets organizers know when to trust a connection and when to double-check.

**You're done when:**
- Matching tiers run in strict-to-broad order
- Name collisions are handled (distinguished or flagged, not silently dropped)
- Splink is active as the fuzzy matching tier
- OSHA and other affected match tables have been re-run
- The UI shows confidence indicators on matches

---

### Phase C: Investigate and Clean Up Missing Data (Estimated: 1 week)

**The goal:** Track down the 195 missing unions and understand what's happening with the OLMS data we're not using yet.

*Can run in parallel with Phase B.*

**Task C1: Check the file number crosswalk for the 195 missing unions.**
The `f7_fnum_crosswalk` table (2,693 entries) maps old union file numbers to new ones — like a forwarding address for unions that merged or reorganized. A single database query will show how many of the 195 orphaned file numbers appear in this crosswalk. This could instantly resolve a large portion of the problem.

**Task C2: Manual OLMS lookup for the top 10-20 missing unions by worker count.**
For the biggest missing unions (especially the top 2, which cover 51,811 workers), search the OLMS public disclosure system to find out: Does this union still exist? Did it merge into another union? When was its last filing?

**Task C3: Categorize and resolve.**
For each missing union:
- **Merged** → remap the file number to the surviving union
- **Dissolved** → mark as historical, keep for the record but exclude from active totals
- **Reorganized** → update the crosswalk and remap
- **Data entry error** → correct if obvious, flag if ambiguous
- **Can't determine** → flag for future investigation

**Task C4: Catalog the unused OLMS annual report tables.**
Document what's in the four annual report tables that aren't being used yet. Determine which fields are most valuable for the platform. Priority ranking based on our planning session:
- **Tier 1 (high value, integrate soon):** Organizing spend percentage from disbursements, membership growth/decline trends
- **Tier 2 (useful context, later):** Union financial health from assets/investments
- **Future project:** Officer/leadership data combined with compensation analysis

*Why this matters:* These tables enrich the union side of the platform — helping answer "which union is best positioned to run this campaign?" rather than just "which employer should be targeted?" The platform is currently strong on employer targeting and weaker on union capacity assessment.

**You're done when:**
- The crosswalk has been checked against all 195 missing file numbers
- The top 20 missing unions by worker count have been manually researched
- Each missing union is categorized (merged, dissolved, reorganized, error, or unknown)
- Resolved unions have been remapped in the relations table
- A written catalog exists documenting what's in the unused OLMS tables and what's most valuable

---

### Phase D: Security, Cleanup, and Project Organization (Estimated: 1-2 weeks)

**The goal:** Make the platform secure, shrink the database, and organize the project so that all AI tools (Claude Code, Codex, Gemini) can work with it effectively.

*Can start during Phase B.*

**Task D1: Harden authentication.**
Remove `DISABLE_AUTH=true` from the default configuration. Make the system refuse to start without proper security credentials. Keep a development override, but make it something you actively opt into.

**Task D2: Archive the raw GLEIF data (~12 GB recovery).**
Back up the 53+ million rows of raw global corporate ownership data to a compressed file, then drop those tables. Only 379,192 US entities were extracted, and only 605 actual matches resulted. The raw data can be restored from backup if ever needed.

**Task D3: Drop unused database indexes (~1.67 GB recovery).**
299 confirmed unused indexes. Dropping them reclaims space and speeds up data inserts.

**Task D4: Create a script manifest.**
A single document listing every active script, what it does, and in what order it should run. Organized by pipeline stage: ETL loading → matching → scoring → API. If it's not in the manifest, it's not part of the active system. This is the guide that any AI tool or human developer reads to understand "what runs, and in what order."

**Task D5: Move dead and one-time scripts to archive.**
The 3 dead API monoliths, scripts referencing nonexistent tables, one-time analysis scripts that already ran, and the 259 scripts with broken credential patterns — move all of these out of the active directories into a clearly labeled archive. Not deleted, just out of the way.

**Task D6: Delete redundant data files (~9.3 GB recovery).**
NLRB SQLite databases (4 copies, 3.79 GB), SQL dumps that have been loaded, PostgreSQL installers — all already imported into PostgreSQL and just taking up disk space.

**Task D7: Fix the credential pattern.**
The 259 scripts with the broken `password='os.environ.get(...)'` string literal — either fix them to use the correct `db_config` import (mechanical find-and-replace) or accept they're archive-only and move them.

**Task D8: Create a shared PROJECT_STATE.md for multi-AI workflow.**
A single document that Claude Code, Codex, and Gemini all read at the start of any session. Contains:
- Section 1: Database connection and startup (must be right)
- Section 2: Table inventory (auto-generated from a script that queries the live database)
- Section 3: Active pipeline (pulled from the script manifest)
- Section 4: Current status and known issues (manually updated after each work session)
- Section 5: Recent decisions (last 5-10 sessions worth — the handoff notes between AI sessions)
- Section 6: Design rationale (the "why" behind key choices)

Sections 2 and 3 should be auto-generated so they never go stale. A quick script run before each session regenerates them from the live database and file system.

**Task D9: Full documentation refresh.**
Update CLAUDE.md and README.md to reflect the actual current state. Fix all 19 known inaccuracies in CLAUDE.md, including the wrong startup command. Archive all old roadmap versions (v10, v11, v12, v13, TRUE, previous unified) with clear "superseded by this document" notes.

**Task D10: Fix freshness metadata.**
Correct the entry that says contracts run through "3023" and review all other freshness entries for similar issues.

**You're done when:**
- The platform refuses to start without security credentials
- The database is under 8 GB
- There's a script manifest showing which scripts are active
- Dead/one-time scripts are archived out of active directories
- PROJECT_STATE.md exists with auto-generated sections
- CLAUDE.md, README.md are accurate
- Only one current roadmap exists (this document)

---

### Phase E: Rebuild the Scorecard (Estimated: 2-3 weeks)

**The goal:** Replace the current fragmented scoring system with a single unified pipeline that scores every employer based on whatever data is available for them.

This is the most important design change in the roadmap. Right now there are two separate scorecards (OSHA-based and Mergent-based) covering only ~15% of employers. The new system scores all ~147K employers through one pipeline.

**The core design principle: signal-strength scoring.**

Instead of scoring every employer on all factors (which penalizes employers with missing data), the new system only scores each employer on factors where data actually exists. Missing factors are excluded from the calculation, not treated as zero.

*Example:* If an employer has OSHA violations, NLRB activity, and government contracts — but no wage theft data and no 990 filing — it gets scored on 3 factors out of the possible total. The score reflects "how strong are the available signals?" not "how many boxes did they check?" The platform displays both the score and a coverage percentage (like "scored on 3 of 8 factors, 38% data coverage") so the organizer knows how much information is behind the number.

**The scoring factors:**

| Factor | What It Measures | Source |
|--------|-----------------|--------|
| OSHA Safety Violations | Workplace danger — normalized by industry average, more recent violations weighted more | OSHA |
| NLRB Election Activity Nearby | Real organizing momentum in the area | NLRB |
| Wage Theft Violations | Employers who steal wages create conditions ripe for organizing | WHD + NYC Comptroller |
| Government Contracts | Creates leverage — organizers can pressure the government to enforce labor standards | USASpending + NY/NYC contract data (combined into one factor, not separate tiers) |
| Union Proximity | Are there already unions at this employer or its corporate siblings? Sibling unions (same parent, different location) weighted more heavily than distant corporate hierarchy connections | F-7 + corporate hierarchy |
| Financial Indicators & Industry Viability | Revenue, profitability, BLS 10-year growth projections for the industry | SEC, Mergent, 990, BLS projections |
| Employer Size | Sweet spot of 50-500 employees — large enough for meaningful bargaining unit, small enough to be reachable | All sources with employee counts |

**Factors dropped as standalone score components (with reasoning):**

- **Industry Union Density** — Every employer in the same industry gets the identical score. If you're comparing two hospitals, density tells you nothing about which one is the better target. It's useful context for an organizer to see on the profile page, but it doesn't help distinguish between employers. Kept as informational display, removed from score calculation.
- **Geographic Favorability** — Same problem. State-level data is too broad (every employer in New York gets the same boost). County-level has the same issue within a county. Dropped from the score. Geographic context is still displayed.

**Gower distance for comparables (separate from the score):**
Gower distance is a mathematical method for finding employers that are "similar" to each other across multiple dimensions. It's used to answer: "Show me employers that look like this one — same size, same industry, same region — so I can see how they compare." This is a separate feature from the score — it powers the "comparable employers" display, not the score itself.

**How to build it:**

1. **Create a master employer table** with a platform-assigned ID for each employer, mapped to all source IDs (F-7 employer ID, OSHA establishment ID, NLRB ID, etc.)
2. **Build a "what do we know?" lookup** — for each employer, which sources have data?
3. **Implement the universal scoring formula** — calculate each available factor, exclude missing ones, compute coverage percentage
4. **Add temporal decay** — recent violations and events weighted more than old ones (OSHA, WHD, NLRB all get decay)
5. **Wire up the Gower comparables engine** to the new master table

**Task E1: Design and create the master employer table.**
Each unique real-world employer gets one platform ID. The mapping layer records "platform employer #5678 = F-7 employer #12345 = OSHA establishment #67890." This is the foundation everything else connects through.

**Task E2: Build the "what do we know?" lookup for every employer.**
For each employer, query all matched sources and build the data availability map.

**Task E3: Implement the unified scoring formula.**
One pipeline, all employers, signal-strength approach. Missing factors excluded.

**Task E4: Add temporal decay to OSHA, WHD, and NLRB factors.**
More recent events weighted more heavily. Fix the broken NLRB decay (currently stuck at 1.0).

**Task E5: Rewire the Gower comparables engine.**
Connect it to the new master table instead of the old OSHA-only scorecard.

**Task E6: Add coverage percentage to all score displays.**
Every score shows "scored on X of Y factors" so organizers know how much data is behind the number.

**Task E7: Update the API and frontend to use the new scorecard.**
Replace the old scorecard endpoints with the new unified ones. Display the confidence/coverage information in the UI.

**You're done when:**
- One scorecard pipeline exists (the two old ones are retired)
- Every employer in the database has either a score or a clear "not enough data" indicator
- Every score displays its data coverage percentage
- Temporal decay is working on all applicable factors
- The Gower comparables engine runs on the new master table

---

### Phase F: Deployment and Testing (Estimated: 2-3 weeks)

**The goal:** Make the platform accessible to people beyond just you, and start getting real feedback.

**Task F1: Create a Docker setup.**
Docker packages the entire platform — code, database, web server, settings — into a container that runs identically on any computer. One command (`docker-compose up`) starts everything.

**Task F2: Set up automatic testing (CI/CD).**
Every time code is pushed to GitHub, all 359+ tests run automatically. If anything breaks, you know immediately.

**Task F3: Set up automated maintenance scheduling.**
Materialized view refreshes, database health checks, backups, data freshness checks — all on a weekly schedule instead of manual.

**Task F4: Deploy to a hosted environment.**
Using the Docker setup, deploy to a hosting service (Render, Railway, or similar). Set up HTTPS, monitoring, and alerts.

**Task F5: Recruit 3-5 beta testers.**
Invite organizers from different unions. Give them specific tasks and collect structured feedback.

**You're done when:**
- `docker-compose up` starts the platform from scratch
- Tests run automatically on every code push
- Weekly maintenance runs automatically
- The platform is accessible at a URL
- At least 3 organizers have used it and provided feedback

---

## PART 4: WHAT COMES LATER

These are organized by priority and readiness, not rigid timelines. User feedback from Phase F should heavily influence which of these come first.

### Wave 1: Enrich What's Already There

**Integrate OLMS organizing spend and membership trends (Tier 1 OLMS data).**
Connect the annual report tables to the platform. Show how much each union spends on organizing (as a percentage of total budget) and whether their membership is growing or shrinking. This enriches the union side — helping answer "which union is best positioned to run this campaign?"

**Expose the BLS occupation matrix on employer profiles.**
The `bls_industry_occupation_matrix` table (113,473 rows) is already loaded. Build a simple lookup: given an employer's NAICS code, show the typical workforce composition. "78% security guards, 4% supervisors, 6% admin." This is Phase 1 of the workforce demographics feature — just making existing data visible.

**Improve corporate crosswalk coverage.**
Run the upgraded matching pipeline (from Phase B) against SEC, GLEIF, and Mergent to push crosswalk coverage beyond the current 37%. Add confidence fields to crosswalk links. This makes the corporate family view useful for more employers.

**Complete the IRS Business Master File integration.**
The table, loader script, and matching adapter already exist but aren't connected end-to-end. The IRS BMF has ~1.8 million tax-exempt organizations, which could significantly improve matching for nonprofit employers (currently only 11.9%).

**O*NET working conditions enrichment.**
O*NET publishes their entire database as clean CSV bulk downloads — completely free, no scraping or parsing needed. Load the Work Context and Job Zones tables. Joined to the BLS occupation matrix through standard occupation codes, this tells organizers what daily work life feels like for the people at a target employer: "typically involves standing for 8+ hours, working outdoors, low autonomy." Estimated effort: 2-3 hours.

### Wave 2: Expand Coverage and Intelligence

**ACS PUMS demographic overlay.**
Pre-compute occupation × metro area demographic distributions for the ~50 largest metros using Census data. When showing a workforce profile, combine the industry staffing pattern (from the BLS matrix) with local demographics to estimate the racial, gender, age, and education makeup of a typical workforce at that employer. This is Phase 2 of workforce demographics.

**Revenue-to-headcount estimation.**
When the platform has revenue data for an employer (from SEC, Mergent, or 990), use industry-specific revenue-per-employee ratios to estimate headcount. All three research reports converge on similar formulas. This is Phase 3 of workforce demographics.

**OLMS union financial health (Tier 2 OLMS data).**
Load the assets/investments data to create a financial health indicator for unions. How much cash does the union have? What are their assets? This helps assess which unions have the resources to support a new organizing campaign.

**State PERB data expansion.**
Build scrapers for state Public Employee Relations Board data — starting with NY PERB, CA PERB, and IL ILRB. No open-source tools exist for this. This fills the gap where federal data doesn't cover public-sector employers and would be one of the platform's biggest differentiators.

**Parse SEC Exhibit 21 filings.**
Exhibit 21 is a list of subsidiaries that public companies file with the SEC. ~7,000 new filings per year, 100,000+ historical. The challenge is format variability — some are HTML tables, some are plain text, some are PDFs. Parsing requires either the CorpWatch parser (~90% accuracy) or an LLM approach. This significantly expands the corporate hierarchy data.

**Web scraper pipeline expansion.**
The AFSCME scraper proved the concept. Expand to Teamsters, SEIU, UFCW, UNITE HERE. On-demand deep-dive tool, not an always-running crawler.

**Prevailing wage intelligence.**
Cross-reference government subsidy databases (Davis-Bacon, state prevailing wage laws) with employer records. Employers receiving public money while paying below prevailing wages are prime organizing targets.

### Wave 3: Advanced Analytics and Research

**Union contract database.**
25,000+ downloadable collective bargaining agreements. Use AI-powered extraction to pull structured data: wage rates, benefit levels, contract duration, key provisions. Enables "here's what workers at similar employers negotiated."

**Propensity model refinement.**
With better match rates and real user feedback about which targets were actually promising, rebuild the propensity model. Needs more non-union training data to improve beyond current Model A (0.72 accuracy).

**Union-lost analysis.**
The 52,760 historical employers represent workplaces that once had union contracts but no longer do. Match them against OSHA/WHD/NLRB to research: what happened after the union left? This produces publishable research.

**OLMS officer/leadership combined project.**
The `ar_disbursements_emp_off` table (2.8M records) has every payment to union officers and employees. Combined with leadership succession analysis and compensation benchmarking, this is a substantial research project.

**Occupation-based similarity.**
Use BLS staffing patterns to find employers that employ similar types of workers, even if they're in different industries. A hospital and a university both employ janitorial staff, cafeteria workers, and maintenance crews.

### Wave 4: Platform Maturity

**Major frontend redesign.**
Expand from current layout to: Dashboard (quick snapshot), My Territory (union-specific coverage map), Employer Research (detail + corporate family + workforce profile), Organizing Targets (unified scorecard + comparables), and Data Explorer (density, trends, analytics). Happens after the data foundation is solid.

**Master employer key (full implementation).**
The scorecard rebuild (Phase E) creates a basic master table. The full implementation adds: merge audit log (every merge recorded and reversible), un-merge capability, auto-merge vs review queue based on confidence thresholds, clear distinction between "same entity" merges and "related but different entities" hierarchy links. Build this when matching is mature and confidence is high — premature implementation bakes in errors that are hard to undo.

**Multi-tenant union workspaces.**
Each union gets its own view with territory assignments, saved searches, and campaign tracking.

**Campaign tracking.**
Organizers mark employers as "active campaign" and track progress from research to petition to election to contract. Over time builds a proprietary dataset of organizing outcomes.

**Board report generation.**
One-click PDF/CSV exports for union board presentations: territory overview, top targets with evidence, trend charts, data freshness statement.

**News and media monitoring.**
Automatically scan news for labor-related stories and link them to employers in the database.

---

## APPENDIX A: Timeline Estimates

| Phase | What | Estimated Time | Can Run In Parallel? |
|-------|------|----------------|---------------------|
| A: Fix Foundation | Orphans, scorecard freshness, broken endpoints | 1-2 weeks | Must come first |
| B: Fix Matching | Tier reorder, Splink, re-run matches | 1-2 weeks | After A starts |
| C: Missing Data | 195 unions, OLMS catalog | 1 week | Parallel with B |
| D: Security & Cleanup | Auth, GLEIF archive, manifest, docs, PROJECT_STATE | 1-2 weeks | Parallel with B/C |
| E: Rebuild Scorecard | Unified pipeline, master table, signal-strength scoring | 2-3 weeks | After A and B |
| F: Deploy & Test | Docker, CI/CD, hosting, beta testers | 2-3 weeks | After E |
| **Total to first real users** | | **8-13 weeks** | |

At 10 hours/week: ~22 weeks (5.5 months)
At 15 hours/week: ~15 weeks (3.8 months)
At 20 hours/week: ~12 weeks (3 months)
Full-time: ~9 weeks (2.2 months)

### Dependency Map

```
Phase A (Fix Foundation) ——— MUST COME FIRST
  |
  |——> Phase B (Fix Matching) ——— needs A's orphan fix done
  |       |
  |       |——> Phase E (Rebuild Scorecard) ——— needs good matching
  |               |
  |               |——> Phase F (Deploy & Test) ——— needs working scorecard
  |
  |——> Phase C (Missing Data) ——— can start during B
  |
  |——> Phase D (Security & Cleanup) ——— can start during B/C
```

**Critical path:** A → B → E → F
**Parallel work:** C and D alongside B
**Minimum viable path:** A + B + E (skip C/D for now) gets to a working scorecard faster, but skips important cleanup

---

## APPENDIX B: Decisions Made in Planning Session (Feb 16-17, 2026)

These are the key design decisions made during the roadmap review session. They're documented here so future AI sessions don't re-litigate settled questions.

| # | Topic | Decision |
|---|-------|----------|
| 1 | Stale materialized views | Fine for now, proof of concept first |
| 2 | F-7 orphan problem | Fix first (highest priority), detailed checkpoint procedure defined |
| 3 | OLMS unused data | Tier 1: organizing spend + membership trends. Tier 2: financial health. Future: officer/leadership |
| 4 | Matching bugs | Reorder strict-to-broad, fix first-hit-wins, bring Splink back, re-run matches, add confidence flags |
| 5 | Scorecard design | Unified pipeline, signal-strength scoring (missing=excluded not zero), all employers covered |
| 6 | Gower distance | Comparables display only, separate from score |
| 7 | Industry density | Drop as standalone score factor (not actionable), keep as informational display |
| 8 | Geographic favorability | Drop as standalone score factor (too broad), keep as informational display |
| 9 | Government contracts | Combine federal + state + municipal into one factor |
| 10 | Union proximity | Merge sibling unions + corporate hierarchy into one factor, weight siblings more heavily |
| 11 | BLS projections | Add industry growth/decline as component of financial indicators factor |
| 12 | Propensity model | Needs more non-union training data before improvement |
| 13 | Membership display | Distinguish "covered workers" vs "dues-paying members" in UI |
| 14 | 195 missing unions | Check crosswalk first → manual lookup top 20 → categorize → remap |
| 15 | Corporate hierarchy | Fix broken API, improve crosswalk coverage. Master key deferred to long-term/when confident |
| 16 | FMCS data | Removed from roadmap |
| 17 | Web scraper | On-demand deep-dive tool, not always-running crawler |
| 18 | Workforce demographics | Phase 1: expose existing BLS matrix. Phase 2: ACS PUMS. Phase 3: revenue-to-headcount. Phase 4: O*NET |
| 19 | F-7 time boundaries | Investigate after orphan fix — define current vs historical, analyze filing gaps |
| 20 | Frontend redesign | Major redesign after data foundation is solid |
| 21 | Checkpoints | Built into every work session |
| 22 | Contract database | Lower priority, Wave 3 |
| 23 | Project organization | Script manifest, archive dead files, PROJECT_STATE.md for multi-AI workflow |
| 24 | Multi-AI context | Shared PROJECT_STATE.md with auto-generated sections, session handoff notes |
| 25 | Simpler communication | Explain all technical concepts in plain language, assume limited coding/database familiarity |

---

## APPENDIX C: Key Principle

Every project described in this document is technically feasible and intellectually interesting. But the platform succeeds only if it becomes something organizers reach for when making real decisions about where to invest their limited time and resources.

The most important filter for deciding what to build next: **talk to people who would actually use it, and build the thing they ask for.**
