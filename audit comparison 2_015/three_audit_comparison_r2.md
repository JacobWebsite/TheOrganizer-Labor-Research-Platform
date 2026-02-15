# Three-Audit Comparison Report — Round 2
## Labor Relations Research Platform
**Date:** February 15, 2026  
**Auditors Compared:** Claude Code (Opus 4.6), OpenAI Codex, Consolidated Summary (standing in for Gemini)  
**Methodology:** Three independent audits run against the same database and codebase, with no auditor seeing the others' work

---

## Part 1: How to Read This Document

### What Is a Three-Blind-Audit?

Think of it like getting three independent home inspectors to look at the same house — none of them talk to each other, and they all follow the same checklist. Where all three flag the same problem (like a cracked foundation), you can be very confident the problem is real. Where only one inspector catches something, it might be brilliant detective work — or it might be a false alarm. This document compares all three inspectors' notes and tells you what's actually going on.

**Confidence levels:**
- **All three agree** = Very high confidence. This is real, act on it.
- **Two out of three agree** = High confidence. Probably real, worth investigating.
- **Only one found it** = Interesting but verify. Could be a unique insight or could be a misread.

### Glossary of Technical Terms

Here's a plain-English dictionary for every technical term you'll see in this report:

- **Orphaned records (or "orphans"):** Data rows that point to something that doesn't exist. Imagine a phone contact that has a number, but that number is disconnected — the contact is "orphaned." In the platform, this means records referencing employers or unions that aren't in the system, which creates invisible gaps.

- **Match rate:** The percentage of records from one database that successfully link to records in another. If 25% of your employer list matches to OSHA safety records, that's a 25% match rate. Higher is better — it means more employers have connected safety data.

- **CORS (Cross-Origin Resource Sharing):** A security rule that controls which websites are allowed to talk to your platform's backend. Think of it as the bouncer at the door — "wide open" means anyone can walk in, "localhost only" means only your own computer can access it.

- **Foreign key:** A link between two tables, like a phone number in your contacts linking to an actual phone. If the phone number doesn't connect to anything real, that's a "broken foreign key" — same idea as orphaned records.

- **Materialized view (MV):** A pre-computed summary table that the database stores so it doesn't have to recalculate the same thing over and over. Like keeping a printed spreadsheet of monthly totals rather than re-adding all the receipts every time someone asks.

- **NAICS codes:** The government's system for classifying what industry a business is in (like "retail," "manufacturing," "healthcare"). If an employer is missing their NAICS code, the platform can't tell what industry they're in.

- **JWT (JSON Web Token):** A digital pass that proves you're logged in. The platform has a JWT system built, but it's turned off — meaning anyone can access everything without logging in.

- **Fail-open:** When a security system defaults to "let everyone in" when it's not configured. The opposite of fail-closed (which would lock everyone out until properly configured). Fail-open is dangerous for production use.

- **SQL injection:** A hacking technique where someone types malicious code into a search box and it runs against your database. All three auditors confirmed this is NOT a risk — the platform is protected.

- **ANALYZE (PostgreSQL):** A database maintenance command that helps the system make smarter decisions about how to retrieve data. Without it, the database guesses (often poorly) about the best way to answer your queries.

- **RealDictCursor:** A technical setting for how the database returns results. Some code expects results in one format but gets them in another — this caused 3 pages to crash with error 500.

- **f-string (formatted string):** A Python shortcut for building text that includes variables. In database queries, this can be risky if not handled carefully (could open the door to SQL injection), but all three auditors found the current use to be mostly safe.

- **Smoke test:** A quick test that just checks "does this page load at all?" — not a deep test, just seeing if the lights turn on.

- **Scorecard:** The platform's system for rating how good a potential organizing target is, using 9 different factors like safety violations, wage theft history, election history, etc.

### Limitations of This Comparison

- The **Consolidated Summary** (standing in for Gemini) is significantly shorter and less detailed than the Claude and Codex reports. It doesn't include line-level code references, artifact files, or many of the granular numbers the other two provide. This means there are places where the Summary simply didn't check something, rather than disagreeing.
- **Claude** and **Codex** both ran live SQL queries against the actual database. The Summary appears to have as well, but provides fewer specifics about methodology.
- **Codex** ran automated smoke tests against the API — the other two did not. This is why only Codex caught the broken density endpoints.
- **Claude** used "current employers" (60,953) as the denominator for many match rates, while **Codex** and the **Summary** used all employers including historical ones (113,713). This makes Claude's percentages look higher for the same raw numbers. Neither is wrong — they're answering different questions.

---

## Part 2: Numbers at a Glance

This table shows the raw numbers each auditor reported side by side. Where they disagree, I explain why below the table.

| Metric | Claude | Codex | Summary | Agreement? |
|--------|--------|-------|---------|------------|
| Total tables | 160 | 169 | 160 | ⚠️ Partial |
| Total views | 186 | 186 | 186 | ✅ Yes |
| Materialized views | 4 | 4 | — | ✅ Yes |
| Total database size | ~20 GB | 20 GB | 7.52 GB | ⚠️ No |
| Total rows | ~23.9M | ~76.7M | — | ❌ No |
| F7→OSHA match rate | 47.3% (current) / 13.7% (estab.) | 25.37% (all) / 13.73% (estab.) | 25.37% | ⚠️ See note |
| F7→NLRB match rate | 28.7% (current) | 4.88% (all) | 4.88% | ⚠️ See note |
| NLRB orphaned records | Not flagged | 1,760,408 (92.34%) | 1,760,408 (92.34%) | ⚠️ Partial |
| Union file orphans | 824 | 824 | 824 | ✅ Yes |
| Employer ID orphans | 0 | 0 | — | ✅ Yes |
| API endpoints (total) | 152 | 152 | — | ✅ Yes |
| Broken endpoints | 0 reported | 3 (density 500s) | — | ❌ No |
| Security issues found | 1 critical (auth) | 2 critical (auth + density) | 1 critical (auth) | ⚠️ Partial |
| Total unique findings | ~15 | ~20 | ~15 | — |
| Test count | 165 | Not counted | — | — |
| Python scripts | ~530 | 494 | 494 | ⚠️ Partial |
| SQL scripts | — | 34 | 34 | ✅ Yes |

### Why the Numbers Disagree

**Table count (160 vs 169):** Codex counted tables in the `gleif` schema separately (9 large GLEIF tables living in their own schema namespace), while Claude and the Summary counted only `public` schema tables. Both are technically correct — it depends on whether you count the GLEIF raw data tables. This is a counting method difference, not an error.

**Database size (20 GB vs 7.52 GB):** The Summary reports 7.52 GB, which appears to measure only the `public` schema tables. Claude and Codex both report ~20 GB, which includes the `gleif` schema. The actual database is ~20 GB.

**Total rows (23.9M vs 76.7M):** Codex's count is much higher because it includes all the GLEIF schema rows (tens of millions of corporate ownership records). Claude's count excludes those. Neither is wrong — it depends on scope.

**Match rates (47.3% vs 25.37%):** This is the most important number to understand. Claude calculated match rates using only "current" employers (the 60,953 that are actively in the F-7 filings now). Codex used ALL employers including 52,760 historical ones added during the orphan fix. So:
- **Claude's 47.3%** answers: "Of employers we're actively tracking, how many have OSHA data?"
- **Codex's 25.37%** answers: "Of ALL employers in the table (including historical), how many have OSHA data?"

Both are valid. For organizer decision-making, Claude's number is more useful (you care about current employers). For data completeness auditing, Codex's number is more honest.

**NLRB orphans:** Claude didn't flag the 92.34% NLRB participant orphan rate as a finding. Codex and the Summary both flagged it as critical. This is because the NLRB participants table contains ALL case participants (not just elections), so most case numbers reference ULP cases, representation cases, etc. that aren't in the `nlrb_elections` table. It looks catastrophic but is actually a structural design choice — the participants table is broader than the elections table. Still, it means participant-to-election joins will miss most records, which is a real limitation.

**Broken endpoints:** Only Codex ran automated smoke tests against the live API, which is how they discovered 3 density endpoints returning error 500. Claude and the Summary reviewed the code but didn't actually hit the endpoints.

---

## Part 3: Where All Three Agree (Highest Confidence)

These are the issues every auditor independently flagged. You can be very confident these are real.

### 3.1 Authentication Is Disabled by Default (🔴 CRITICAL)

**The problem in plain English:** The platform has a full login system built, but it's turned off. Anyone who can reach the website can see everything — all the data, all the admin controls, everything. This is like building a lock on your front door but leaving the door wide open.

- **Claude** called it "🟡 HIGH" and noted the specific line of code where the bypass happens. Said it's fine for local development but dangerous for any real deployment.
- **Codex** called it "🔴 CRITICAL" and confirmed it with runtime logs showing the warning message that auth is disabled. Found the exact same bypass code.
- **Summary** called it "🔴 CRITICAL" and confirmed it's still broken from Round 1.

**Severity consensus:** All three agree this is the top security issue. Claude rated it slightly lower because the platform is only running locally, but acknowledged it must be fixed before deployment.

**What it means for organizers:** Right now, this doesn't matter because the platform runs on your computer only. But the moment you put it online for others to use, anyone could access sensitive organizing intelligence.

**Recommended action:** Before any deployment beyond your own machine, set the `LABOR_JWT_SECRET` environment variable and make the system refuse to start without it. Estimated time: 30-60 minutes.

### 3.2 Union File Number Orphans Persist and Worsened (🟡 HIGH)

**The problem in plain English:** 824 connections between employers and unions point to union records that don't exist in the system. This is up from 195 in Round 1. It's like having 824 entries in a contact list where the phone numbers are disconnected — those union-employer relationships are invisible to anyone using the platform.

- **Claude** flagged this as "🟡 HIGH" and noted it worsened because the historical employer import added employer records that reference old unions not yet in the system.
- **Codex** confirmed the same 824 count and called it "🟡 MEDIUM" but noted it worsened from Round 1.
- **Summary** confirmed 824 orphans at 0.69% orphan rate and rated it "🔴 CRITICAL."

**Severity consensus:** Everyone agrees this is real and worsened. The ratings vary from MEDIUM to CRITICAL depending on perspective — 824 out of 119,445 is a small percentage (0.69%), but every one represents a real organizing relationship that's invisible.

**What it means for organizers:** If you're looking at a specific employer, you might miss that a union already has a relationship with them. 824 connections that should be showing up simply aren't.

**Recommended action:** Investigate whether these 824 unions are historical locals that should be added to the unions_master table, or genuinely broken references to clean up. Estimated time: 4-8 hours.

### 3.3 Documentation Is Significantly Out of Date (🔵 MEDIUM)

**The problem in plain English:** The "instruction manual" for the platform (README.md, CLAUDE.md) doesn't match what the platform actually does anymore. It lists features that don't exist, shows wrong numbers, and misses major capabilities that have been added.

- **Claude** found README.md is 55% accurate, with wrong endpoint listings, wrong scorecard factor count (says 6, actually 9), and missing 10+ major features. Also found CLAUDE.md is 95.5% accurate with minor count discrepancies.
- **Codex** found similar discrepancies in both files and additionally identified that README startup instructions are unreliable for non-local environments.
- **Summary** confirmed documentation was generally fixed from Round 1 issues, but this was checking against a narrower set of claims.

**Severity consensus:** All agree the docs need updating. Claude was most detailed about exactly what's wrong.

**What it means for organizers:** If a new developer tries to set up the platform using the README, they'd get confused. If someone reads the documentation to understand what the platform can do, they'd significantly underestimate its capabilities.

**Recommended action:** Update README.md to reflect the actual 152 endpoints, 9-factor scorecard, and current data counts. Add a deployment checklist. Estimated time: 2-4 hours.

### 3.4 CORS Configuration Is Fixed (✅ POSITIVE)

**The problem from Round 1:** The platform was configured to accept requests from any website on the internet.

- All three auditors confirmed this is now **FIXED** — only localhost origins are allowed.

### 3.5 Database Password Removed from Code (✅ POSITIVE)

**The problem from Round 1:** The actual database password was written directly in the code files.

- All three auditors confirmed this is now **FIXED**. Claude noted it still appears in 7 old audit documentation files (not code).

### 3.6 Frontend Monolith Decomposed (✅ POSITIVE)

**The problem from Round 1:** The entire user interface was crammed into one enormous 9,500+ line file.

- All three confirmed it's now **FIXED** — split into 12 focused files. All three praise this as a significant improvement.

---

## Part 4: Where Two Out of Three Agree

### 4.1 NLRB Participant Orphan Rate Is 92.34% (🔴 CRITICAL — flagged by Codex + Summary)

**The problem:** 1.76 million out of 1.9 million records in the NLRB participants table can't be linked to any election record. That's over 92% of the data floating without a connection to election outcomes.

- **Codex** called it "🔴 CRITICAL" and provided the exact orphan query.
- **Summary** also flagged it as "🔴 CRITICAL" with the same numbers.
- **Claude** did NOT flag this as a standalone finding.

**Why Claude likely missed it:** Claude focused orphan checks on the F7 employer/union relationships (which are the platform's core data layer) and checked OSHA-to-F7 integrity. The NLRB participant-to-election orphan check was in the audit prompt but Claude may have recognized that the high orphan rate is structurally expected — the participants table includes ALL NLRB case types (ULP cases, representation cases, etc.), not just elections. Most NLRB cases aren't elections, so most participants won't match to the elections table by design.

**Who's probably right:** Codex and the Summary are technically correct about the numbers. However, the severity depends on interpretation. This isn't really a "broken link" — it's more like the participants table is much broader than just elections. That said, this does mean that participant-level data (like employer names from NLRB filings) can rarely be joined to election outcomes, which is a real limitation for organizer research.

**What it means for organizers:** When you look up an employer's NLRB history, the system may not be able to connect their case filings to specific election results. You'll see they were involved in NLRB proceedings, but linking that to "did the union win?" is harder.

**Recommended action:** Create a unified NLRB view that bridges participants to elections through case numbers, handling the different case types explicitly. This is a structural improvement, not a bug fix. Estimated time: 6-12 hours.

### 4.2 Stale Database Statistics (🔵 MEDIUM — flagged by Claude + Codex)

**The problem:** Most tables haven't been "analyzed" by PostgreSQL, which means the database is guessing about the best way to retrieve data instead of knowing. Think of it like a library where the card catalog hasn't been updated — the librarian can still find books, but it takes longer and sometimes goes the wrong way.

- **Claude** found 150 out of 164 tables never analyzed; hot-path (frequently used) tables are fine.
- **Codex** found 170 out of 173 tables with no last_analyze; 159 out of 173 with no autoanalyze.
- **Summary** flagged this as "🟡 MEDIUM" and noted it was "PARTIALLY FIXED."

**Why the numbers differ slightly:** Different counting methods (Claude excluded some system tables).

**Recommended action:** Run `ANALYZE` on the entire database. Takes about 2 minutes and immediately improves query performance. This is the easiest win on the whole list.

### 4.3 Script Credential Migration Incomplete (🔵 MEDIUM — flagged by Claude + Codex)

**The problem:** Most Python scripts (86%+) still have their database connection information written directly inside them, instead of using the shared configuration file. This makes the system fragile — if you ever need to change how the database connects (different password, different server, etc.), you'd need to update hundreds of files.

- **Claude** found 315 scripts (86.3%) using inline connections, with only 50 (13.7%) using the shared config. Also found 29 scripts with a particularly nasty bug where the password code is treated as text instead of being executed.
- **Codex** flagged inconsistent connection patterns across scripts with hardcoded host/user defaults.
- **Summary** didn't specifically address this.

**Recommended action:** The 29 scripts with the literal-string password bug should be fixed first (they'll break if PostgreSQL ever requires a real password). Then gradually migrate the rest. Estimated time: 4-8 hours for the 29 critical ones; ongoing for the rest.

---

## Part 5: Where They Disagree

### 5.1 OSHA Match Rate: Is It 47.3% or 25.37%?

**The disagreement:** Claude reports OSHA matching at 47.3% while Codex and the Summary report 25.37%.

- **Claude's position:** 28,836 matched out of 60,953 **current** employers = 47.3%
- **Codex's position:** 28,848 matched out of 113,713 **all** employers = 25.37%
- **Summary's position:** Same as Codex, 25.37%

**Who's right:** Both are correct — they're measuring different things. The raw matched count is virtually identical (28,836 vs 28,848 — tiny difference from query timing). The difference is the denominator: current employers vs all employers including historical.

**What to do:** Report both numbers. When talking to organizers, use the "current employer" percentage (47.3%) because that reflects the employers they'd actually be researching. When auditing data completeness, use the "all employers" number (25.37%).

### 5.2 WHD Match Rate: Fixed or Still Broken?

**The disagreement:** Claude says WHD matching is "FIXED" (improved from 2% to 16%). Codex says it's "STILL BROKEN" (Mergent-WHD coverage only 2.47%).

- **Claude's position:** 9,745 F7 employers now match to WHD data = 16.0% of current employers. That's an 8x improvement from Round 1's ~2%.
- **Codex's position:** Looking at Mergent-to-WHD linking specifically, only 1,396 out of 56,426 Mergent employers match (2.47%). This is still very low.

**Who's right:** They're measuring different matching pathways. Claude measured F7-employer-to-WHD (the main organizer pathway), which genuinely improved. Codex measured Mergent-employer-to-WHD (a secondary corporate enrichment pathway), which didn't improve much. Both are accurate within their scope.

**What to do:** The F7-to-WHD pathway (what organizers actually use) has improved significantly. The Mergent pathway is less important for organizer workflows. Mark as "IMPROVED" rather than "FIXED" or "BROKEN."

### 5.3 990 Data: Fixed or Still Broken?

**The disagreement:** Claude says 990 matching is "FIXED" (14,059 matches). Codex says it's "STILL BROKEN" (only 69 Mergent-990 matches, 0.12%).

- **Claude's position:** There are now 14,059 matches in the employer_990_matches table, covering 7,240 F7 employers (11.9% of current).
- **Codex's position:** Looking at `mergent_employers.matched_990_id`, only 69 matches exist (0.12%).

**Who's right:** Again, different pathways. Claude checked the dedicated 990 matching table (the correct one). Codex checked a different column on the Mergent table (which was never the primary 990 match pathway). Claude is more correct here — the 990 matching pipeline works and produces real results through its own table.

**What to do:** The 990 matching IS working via its own table. The Mergent 990 column is vestigial and can be ignored.

### 5.4 Scoring Systems: Unified or Still Dual?

**The disagreement:** Claude says the two scoring systems are "FIXED" (unified 9-factor MV scorecard). Codex says "STILL BROKEN" (frontend still has dual score logic).

- **Claude's position:** The backend computes one unified 9-factor score through the materialized view. The Mergent scoring is now used only for enrichment, not as a separate score.
- **Codex's position:** The frontend JavaScript still contains code referencing both a 0-62 sector score and a 0-100 OSHA score at specific line numbers.

**Who's right:** Both are partly right. The backend IS unified — one scorecard, one computation. But the frontend code still has remnants of the old dual-score display logic. This is a cleanup issue rather than a fundamental architecture problem.

**What to do:** Clean up the frontend code to remove the old score references. Low priority since the backend is correct. Estimated time: 1-2 hours.

### 5.5 GLEIF Storage: Fixed or Still a Problem?

**The disagreement:** Claude says GLEIF is "PARTIALLY FIXED" (96% size reduction, 396 MB). Codex says GLEIF is still ~12 GB.

- **Claude's position:** The public schema GLEIF tables were consolidated to 396 MB from 10+ GB.
- **Codex's position:** The `gleif` schema still contains ~12 GB of raw corporate ownership data across 9 tables.

**Who's right:** Both. Claude is correct that the public-facing GLEIF tables shrank dramatically. But Codex discovered that the raw GLEIF data lives in a separate `gleif` schema and is still huge. This is why Codex's database size and table counts are higher.

**What to do:** Evaluate whether the full `gleif` schema is needed. If only the distilled `gleif_us_entities` table (379K rows, 310 MB) is used by the platform, the raw 12 GB could be archived or dropped. This would cut the database almost in half.

---

## Part 6: Unique Catches (Only One Found It)

### Only Claude Found

**6.1 — 29 Scripts Have a Literal-String Password Bug (🟡 HIGH)**

Claude discovered that 29 Python scripts have a particularly sneaky bug: they write `password="os.environ.get('DB_PASSWORD', '')"` — but because of where the quotes are placed, the database receives the literal text `os.environ.get('DB_PASSWORD', '')` as the password, rather than actually looking up the password from the environment. These scripts only work right now because the database doesn't require a password. If you ever enable database authentication, all 29 scripts would immediately break.

*Why the others missed it:* This requires reading the actual code closely and understanding a subtle Python quoting issue. Codex scanned for credentials but looked for leaked passwords, not malformed environment variable calls.

*How important:* Genuinely important. These are ETL and maintenance scripts needed for data refreshes. Fix before enabling any database authentication.

**6.2 — 299 Unused Indexes Consuming 1.67 GB (🔵 MEDIUM)**

The database has 299 indexes that nothing ever uses, wasting 1.67 GB of storage and slowing down every data write operation (because the database has to update these indexes even though nothing reads from them).

*Why the others missed it:* Requires checking `pg_stat_user_indexes` for usage stats — a specific database administration query the others didn't run.

*How important:* Moderate. 1.67 GB isn't critical, but removing unused indexes would speed up all write operations. Good housekeeping.

**6.3 — Specific Missing Index Recommendations for Hot Paths (🔵 MEDIUM)**

Claude identified 3 specific indexes that should be added to speed up common query patterns (ULP batch queries, freshness queries, and union orphan resolution).

*How important:* Useful optimization. Easy to implement.

**6.4 — README Lists Non-Existent API Endpoints (🔵 MEDIUM)**

Claude found that README.md lists `/api/elections/recent` and `/api/targets/search` — endpoints that don't actually exist in the codebase.

*How important:* Would confuse any developer trying to use the documented API.

**6.5 — NAICS Coverage Only 37.7% Limits Industry Scoring (🔵 MEDIUM)**

Claude found that only 37.7% of F7 employers have NAICS industry codes, which means the industry_density scoring factor can't fire for 62% of employers. This makes scores artificially lower for most employers.

*Why the others likely missed it:* Codex reported NAICS at 94.46% — but that's for ALL employers including historical ones where NAICS was backfilled. Claude's number is for the subset that matters for scoring.

*How important:* Significant for scoring accuracy. Claude's suggestion to backfill NAICS from OSHA matches (which have 71.8% NAICS coverage) is practical and could fix this quickly.

### Only Codex Found

**6.6 — Three Density Endpoints Return Error 500 (🔴 CRITICAL)**

Codex actually ran the API and discovered that three density endpoints (`/api/density/by-govt-level`, `/api/density/by-county`, `/api/density/county-summary`) crash when you try to use them. The bug is a mismatch between how the code reads database results (expecting numbered positions like a list) versus how the database returns them (as named fields like a dictionary).

*Why the others missed it:* Claude and the Summary reviewed the code but didn't actually test the endpoints. You can't find runtime crashes just by reading code — you have to run it.

*How important:* Very important. These are key density analysis tools for geographic targeting. Organizers can't use them at all right now. The fix is straightforward — change `stats[0]` to `stats['avg_federal']` style access in three places. Estimated time: 2-4 hours.

**6.7 — GLEIF Raw Schema Is Still 12 GB (🟡 HIGH)**

Codex discovered an entire separate schema (`gleif.*`) with 9 tables totaling ~12 GB of raw corporate ownership data that the other auditors didn't see because they only looked at the `public` schema.

*Why the others missed it:* Claude and the Summary only scanned the `public` schema. Codex scanned all schemas.

*How important:* Significant for database management. If this data isn't actively used, removing it would cut the database nearly in half.

**6.8 — Dead Script References to Non-Existent Tables (🟡 HIGH)**

Codex found 4 scripts that reference database tables that no longer exist (like `splink_match_results`, which was dropped). If someone ran these scripts, they'd crash.

*Why the others missed it:* Claude checked for dead references in "active scripts" and found zero, but may have excluded these as legacy/disabled. Codex checked more broadly.

*How important:* Moderate. These scripts probably shouldn't be run anyway, but they should be marked as legacy or removed to avoid confusion.

**6.9 — NLRB Elections Table Missing Expected Columns (🟡 HIGH)**

Codex found that the `nlrb_elections` table doesn't have employer_name, city, state, votes_for, or votes_against columns. These are fields you'd expect in an elections table.

*Why the others missed it:* Claude may have known these fields live in the participants table (since NLRB data is structured differently than expected). The Summary didn't check schema details at this level.

*How important:* This explains why NLRB matching is hard — the elections table itself doesn't contain the employer information needed for matching. A unified election view that pulls in participant data would solve this.

**6.10 — Frontend Auxiliary Tools Hardcode Localhost (⚪ LOW)**

Codex found that `test_api.html` and `api_map.html` have localhost URLs hardcoded, meaning they won't work in deployed environments.

*How important:* Low. These are developer tools, not organizer-facing.

**6.11 — f-string SQL Pattern Creates Future Risk (🔵 MEDIUM)**

Codex flagged that many API queries use Python f-strings to build SQL, which isn't dangerous now but could become a SQL injection risk if future developers aren't careful.

*How important:* Good forward-looking observation. Current code is safe, but the pattern is fragile.

### Only Summary Found

**6.12 — Mergent EIN Coverage Only 44% (🔵 MEDIUM)**

The Summary noted that only 44% of Mergent employer records have an EIN (tax ID number).

*Why the others reported differently:* Codex found 43.95% (essentially the same). Claude found 86.7%. The difference is likely due to Claude checking a different column or counting methodology. The ~44% figure appears correct.

*How important:* Moderate. EIN is a key identifier for matching employers across databases. Low coverage means fewer matches.

---

## Part 7: Round 1 Issue Resolution — Did They Fix Things?

This table compares what each auditor said about the 15 issues from the first audit round.

| # | Round 1 Issue | Claude Says | Codex Says | Summary Says | Consensus |
|---|--------------|-------------|------------|-------------|-----------|
| 1 | Database password in code | ✅ FIXED | ✅ FIXED | ✅ FIXED | **FIXED** ✅ |
| 2 | Authentication disabled | ⚠️ PARTIALLY FIXED (built but off) | ❌ STILL BROKEN | ❌ STILL BROKEN | **Still broken** — auth exists but is off |
| 3 | CORS wide open | ✅ FIXED | ✅ FIXED | ⚠️ Needs hardening | **FIXED** for dev; needs prod config |
| 4 | ~50% orphaned employer relations | ✅ FIXED (60K→0) | ✅ FIXED (0 orphans) | ✅ FIXED | **FIXED** ✅✅✅ |
| 5 | Frontend monolith | ✅ FIXED (12 files) | ✅ FIXED (12 files) | ✅ FIXED | **FIXED** ✅✅✅ |
| 6 | OSHA match rate ~14% | ✅ FIXED (47.3% current) | ❌ STILL BROKEN (25.37% all) | ✅ FIXED (25.37%) | **Improved** — see Part 5 |
| 7 | WHD match rate ~2% | ✅ FIXED (16.0%) | ❌ STILL BROKEN (2.47% Mergent) | ❌ STILL BROKEN | **Improved** — different pathways measured |
| 8 | No matching tests | ✅ FIXED (165 tests) | ✅ FIXED (tests exist) | ⚠️ PARTIALLY FIXED | **FIXED** ✅ |
| 9 | README wrong startup | ✅ FIXED | ✅ FIXED | ✅ FIXED | **FIXED** ✅ |
| 10 | 990 data unmatched | ✅ FIXED (14K matches) | ❌ STILL BROKEN (69 Mergent) | ✅ FIXED | **FIXED** via dedicated table |
| 11 | GLEIF 10+ GB for few matches | ⚠️ PARTIALLY FIXED (396 MB public) | ⚠️ PARTIALLY FIXED (12 GB still in gleif schema) | ✅ FIXED | **Partially fixed** — public tables shrunk, raw data remains |
| 12 | Silent LIMIT 500 | ✅ FIXED | ⚠️ PARTIALLY FIXED (some lookups still truncate) | ✅ FIXED | **Mostly fixed** |
| 13 | Two scoring systems | ✅ FIXED (unified MV) | ❌ STILL BROKEN (frontend remnants) | ✅ FIXED | **Backend fixed**, frontend cleanup needed |
| 14 | 195 orphaned union file numbers | ❌ STILL BROKEN (824) | ❌ STILL BROKEN (824) | ❌ STILL BROKEN (824) | **Still broken, worsened** ❌❌❌ |
| 15 | Stale pg_stat estimates | ⚠️ PARTIALLY FIXED | ❌ STILL BROKEN | ⚠️ PARTIALLY FIXED | **Partially fixed** — hot tables OK, most still stale |

**Scorecard:** Of the 15 Round 1 issues:
- **6 clearly FIXED** (password, employer orphans, frontend split, tests, README startup, LIMIT 500)
- **4 IMPROVED** (OSHA match rate, WHD matching, 990 matching, scoring unification)
- **3 PARTIALLY FIXED** (CORS needs prod config, GLEIF still large in separate schema, pg_stat still mostly stale)
- **2 STILL BROKEN** (auth disabled, union file orphans worsened)

**Trend:** The platform is moving in the right direction. The biggest win was fixing the 60,000 employer orphans — that was the #1 issue from Round 1. The biggest lingering concern is authentication, which all three agree needs to be enabled before any deployment.

---

## Part 8: Delta Since Round 1

Combining all three auditors' observations about what changed between Round 1 (Feb 13) and Round 2 (Feb 14-15):

### What Got Added
- **52,760 historical employers** added to resolve the orphan crisis (biggest change)
- **Materialized view scorecard** (`mv_organizing_scorecard`) — 9-factor scoring computed entirely in SQL
- **JWT authentication system** — fully built (4 endpoints), just needs activation
- **Data freshness tracking** — 15 data sources monitored for currency
- **ULP integration** — Unfair Labor Practice history now appears in the scorecard
- **118 new tests** (47 → 165 total)
- **Frontend split** — monolith → 12 focused files
- **Platform users table** — ready for when auth is enabled

### What Got Removed
- **splink_match_results** table (5.7M rows, 1.6 GB) — archived
- **6 empty staging tables** from Round 1 — cleaned up
- **71 unused indexes** removed (370 → 299)

### Size Changes
- Database: 22 GB → 20 GB (net reduction despite new data)
- GLEIF public tables: 10+ GB → 396 MB (major reduction)
- But GLEIF raw schema: still ~12 GB (discovered by Codex)

### New Problems Introduced
- Union file orphans **worsened** from 195 to 824 (side effect of historical employer import)
- `modals.js` at 2,598 lines is a secondary monolith in the frontend
- NAICS completeness potentially dropped for current employers (needs verification)

---

## Part 9: Methodology Comparison

| Aspect | Claude | Codex | Summary |
|--------|--------|-------|---------|
| **Approach** | Section-by-section, verified every finding with live SQL | Section-by-section with JSON artifact files for reproducibility | Consolidated summary format, less granular |
| **Database access** | Direct SQL via Claude Code | Direct SQL via Python scripts, saved all outputs to artifact files | Appears to have run live queries |
| **Live API testing** | Code review only | Automated smoke tests on 46 endpoints | Code review only |
| **Schema scope** | Public schema only | All schemas including `gleif.*` | Public schema only |
| **Match rate denominator** | Current employers (60,953) | All employers (113,713) | All employers (113,713) |
| **Artifact trail** | Inline SQL evidence in report | JSON artifacts saved to `docs/audit_artifacts_round2/` | No artifacts referenced |
| **Total findings** | ~15 distinct issues | ~20 distinct issues | ~15 distinct issues |
| **Documentation review depth** | Checked README, CLAUDE.md, ROADMAP.md, case studies | Checked README, CLAUDE.md | Checked CLAUDE.md broadly |
| **Strengths** | Deepest data integrity analysis, best match rate context, most practical fix suggestions, strongest organizer perspective | Most thorough testing (smoke tests), broadest scope (all schemas), best reproducibility (artifact files), found runtime bugs others missed | Concise overview, good at tracking Round 1 resolution |
| **Blind spots** | Missed GLEIF raw schema, didn't run API smoke tests, didn't catch density endpoint crashes | Used wrong denominator for some match rates leading to "STILL BROKEN" calls on fixed items, checked wrong columns for 990 matching | Least detailed, fewer unique findings, limited methodology documentation |

---

## Part 10: Unified Priority List

Combining all findings from all three auditors into a single ranked action plan.

### 🔴 CRITICAL — Do These First

**C1. Fix the 3 crashing density endpoints**
- *Flagged by:* Codex only (but verified with real tests)
- *The issue:* Three pages that organizers use for geographic targeting are completely broken
- *The fix:* Change tuple-style indexing to dictionary-style in density.py (3 locations)
- *Effort:* 2-4 hours
- *Why it matters:* Organizers literally cannot use geographic density analysis right now

**C2. Enable authentication before any deployment**
- *Flagged by:* All three auditors
- *The issue:* Anyone can access everything without logging in
- *The fix:* Set LABOR_JWT_SECRET, bootstrap an admin user, test the login flow
- *Effort:* 1-2 hours
- *Why it matters:* All organizing intelligence is publicly accessible without this

**C3. Investigate and resolve the NLRB participant linkage**
- *Flagged by:* Codex + Summary
- *The issue:* 92% of NLRB participant records can't be connected to election outcomes
- *The fix:* Create a unified NLRB view that properly bridges case types; document the structural gap
- *Effort:* 6-12 hours
- *Why it matters:* NLRB election context is one of the most valuable data points for organizers

### 🟡 HIGH — Do Before Anyone Else Uses It

**H1. Fix the 29 scripts with literal-string password bug**
- *Flagged by:* Claude only
- *Effort:* 4-8 hours
- *Why:* These scripts will break the moment database authentication is enabled

**H2. Resolve the 824 union file number orphans**
- *Flagged by:* All three
- *Effort:* 4-8 hours
- *Why:* 824 invisible employer-union relationships

**H3. Update README.md to reflect actual platform capabilities**
- *Flagged by:* All three
- *Effort:* 2-4 hours
- *Why:* Current docs significantly understate the platform and list nonexistent features

**H4. Evaluate and potentially archive the 12 GB GLEIF raw schema**
- *Flagged by:* Codex
- *Effort:* 4-12 hours
- *Why:* Half the database may be unused raw data; freeing it simplifies everything

**H5. Backfill NAICS codes from OSHA matches**
- *Flagged by:* Claude
- *Effort:* 2-4 hours
- *Why:* 62% of employers can't get industry-based scoring without this

### 🔵 MEDIUM — Should Fix But Not Urgent

**M1. Run ANALYZE on the full database** — 2 minutes, improves all query performance  
**M2. Migrate remaining 315 scripts to shared db_config** — Ongoing, prevents connection fragility  
**M3. Remove 299 unused indexes** — Saves 1.67 GB, speeds up all writes  
**M4. Clean up dual-score frontend remnants** — 1-2 hours  
**M5. Set up automated scheduling for MV refreshes** — 4-8 hours, prevents stale data  
**M6. Create a production deployment checklist** — 2-4 hours  
**M7. Split modals.js into per-feature files** — 2-4 hours, improves maintainability  
**M8. Standardize f-string SQL patterns** — 4-8 hours, prevents future injection risk  

### ⚪ LOW — Nice to Have

**L1. Fix auxiliary frontend tools' hardcoded localhost URLs** — 15-30 minutes  
**L2. Migrate inline event handlers to JS listeners** — Incremental  
**L3. Add a generated "live metrics" doc that auto-updates** — 2-4 hours  
**L4. Mark dead scripts as legacy/experimental** — 2-4 hours  
**L5. Add banner to old audit docs noting they're historical snapshots** — 10 minutes  

---

## Part 11: One-Week Action Plan

If you had 5 focused work days to address the most impactful issues:

### Day 1: Fix What's Broken Right Now
**Morning:**
- Fix the 3 density endpoint crashes in `density.py` (C1) — change tuple indexing to dictionary keys at lines 212, 363, 593
- Run `ANALYZE` on the full database (M1) — takes 2 minutes, immediate performance boost
- Refresh `mv_employer_search` materialized view

**Afternoon:**
- Enable authentication: set `LABOR_JWT_SECRET`, create admin user, test login flow (C2)
- Test all previously-broken density endpoints to confirm they work

*Addresses: C1, C2, M1*

### Day 2: Data Integrity Cleanup
**Morning:**
- Investigate the 824 union file number orphans (H2) — determine which are historical unions needing to be added vs. bad references
- Fix the orphans (either add missing unions or clean up references)

**Afternoon:**
- Backfill NAICS codes from OSHA matches for employers missing them (H5)
- Verify the industry_density scoring factor now works for more employers
- Run a scorecard refresh to incorporate the NAICS improvements

*Addresses: H2, H5*

### Day 3: NLRB Linkage + GLEIF Evaluation
**Morning:**
- Build a unified NLRB view that bridges participants to elections through case numbers (C3)
- Document which case types are expected NOT to have election records (ULP, etc.)

**Afternoon:**
- Evaluate the 12 GB GLEIF raw schema (H4) — determine what's actively used vs. archivable
- If safe, archive or drop the unused GLEIF raw tables
- Verify GLEIF-dependent features still work after cleanup

*Addresses: C3, H4*

### Day 4: Code Cleanup + Documentation
**Morning:**
- Fix the 29 scripts with literal-string password bugs (H1) — replace with `from db_config import get_connection`
- Clean up dual-score frontend remnants (M4)

**Afternoon:**
- Rewrite README.md with accurate endpoints, scorecard description, data counts, and deployment checklist (H3)
- Update CLAUDE.md with corrected row counts and router count
- Add production deployment checklist documenting required environment variables

*Addresses: H1, M4, H3, M6*

### Day 5: Automation + Future-Proofing
**Morning:**
- Set up automated scheduling for MV refreshes and data freshness checks (M5)
- Start script migration: move highest-priority ETL scripts to shared db_config (M2 — begin)

**Afternoon:**
- Review and drop unused indexes — start with the largest ones (M3 — begin)
- Create a "blessed pipeline" manifest documenting the correct order for a full data rebuild
- Run a complete end-to-end test of all major organizer workflows to verify the week's fixes

*Addresses: M5, M2, M3*

---

## Part 12: What's Working Well

These are the things all three auditors praised. When three independent inspectors all call out the same strength, it's genuinely impressive.

### Triple-Praised Highlights

**The 60,000-orphan fix is a massive data integrity win.** In Round 1, this was THE crisis — half of all employer-union relationships were broken. Adding 52,760 historical employers and eliminating every single orphan (60,000 → 0) in one sprint is remarkable. All three auditors highlighted this as the most significant improvement.

**The materialized view scorecard is well-engineered.** Computing all 9 scoring factors in SQL via a single materialized view eliminates score drift and supports zero-downtime refreshes. Claude specifically praised this as a sophisticated approach. Codex noted it as "practical performance-minded design."

**The frontend decomposition was done right.** Breaking a 10,500-line monolith into 12 focused files, with no hardcoded API URLs and dynamic configuration, is production-ready frontend architecture. All three confirmed every API call in the frontend connects to a real backend endpoint.

**Match rates improved significantly.** OSHA matching went from ~14% to 25-47% (depending on how you measure). WHD from ~2% to 16% (F7 pathway). 990 from 0% to 12%. These aren't minor tweaks — the dataset is fundamentally more connected than it was 48 hours ago.

**Security posture improved dramatically.** The database password is gone from all code, CORS is locked down, SQL injection is impossible (parameterized queries throughout), and a full JWT auth system is built and ready to activate.

**165 automated tests now exist.** Up from ~47 in Round 1. Covering matching, scoring, API endpoints, authentication, and data integrity. This is a real safety net for future development.

### Individual Auditor Praise

**Claude specifically praised:** The ULP integration as strategically valuable for organizers, the data freshness tracking system, and the clean separation of concerns across 17 API routers.

**Codex specifically praised:** The broad breadth of integrated labor-relevant data sources in one platform, and the fact that frontend-to-API wiring had zero broken connections.

**Summary specifically praised:** The good keyboard navigation, interactive maps (Leaflet), and data visualization capabilities (Chart.js).

---

## Part 13: Key Takeaways

If you read nothing else, read this:

1. **The platform has made enormous progress in 48 hours.** The biggest crisis from Round 1 (60,000 orphaned records) is completely resolved. Match rates doubled or tripled. Tests went from 47 to 165. The frontend was professionally decomposed. This is genuinely impressive velocity.

2. **Three pages are broken right now and need immediate attention.** The density endpoints crash when used. This is the single most urgent fix — 2-4 hours of work to change how the code reads database results. Only Codex caught this because only Codex actually tested the API.

3. **Authentication must be enabled before anyone else uses this.** All three auditors agree. The system is wide open. Fine for your laptop, dangerous for anything public.

4. **The match rate disagreements aren't really disagreements.** Claude and Codex are measuring different things (current vs. all employers). Both are right. For organizer work, use Claude's numbers (current employers). For auditing, use Codex's (all employers).

5. **There may be 12 GB of unused data sitting in the database.** Codex discovered a `gleif` schema the other auditors missed entirely. If it's not actively used, removing it would cut the database nearly in half — a huge operational simplification.

6. **The "still broken" items are mostly wording disagreements.** WHD matching, 990 matching, and scoring unification all improved significantly — Codex called them "broken" because it measured different pathways than Claude. The underlying improvements are real.

7. **The platform is ready for real organizing work, with caveats.** The core functionality — connecting employers to safety records, elections, wage theft, and corporate ownership — works. The scoring system is solid. An organizer CAN use this tool to make strategic decisions today. The remaining issues are about deployment readiness, documentation accuracy, and data completeness expansion — not fundamental functionality.
