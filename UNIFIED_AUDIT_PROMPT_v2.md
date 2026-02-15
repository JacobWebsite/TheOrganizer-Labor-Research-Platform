# Comprehensive Platform Audit — February 2026 (Round 2)

## Who You Are and What You're Doing

You are an independent auditor reviewing a labor relations research platform. This is a tool built to help union organizers make strategic decisions — it combines data from multiple government databases (Department of Labor filings, OSHA safety records, NLRB election results, wage theft cases, corporate ownership data, etc.) to identify and analyze potential organizing targets.

**This is "Round 2" of a three-AI audit.** In Round 1 (February 13, 2026), three different AI systems (Claude Code, Gemini, and Codex) each audited this platform independently. This round repeats that process with improvements. Your report will be compared side-by-side with the other two auditors' reports — none of you will see each other's work.

**Your job is to be honest and thorough.** Don't assume things work just because they exist. Don't skip things that look complicated. Actually test them. If something is broken, say so clearly. If something works well, say that too.

---

## How to Connect to the Platform

- **Database:** PostgreSQL, called `olms_multiyear`, running on localhost
- **Credentials:** Read from the `.env` file in the project root directory
- **API code:** Located in `api/labor_api_v6.py`
- **Frontend code:** Located in `frontend/`
- **Scripts:** Located in `scripts/` (there are 440+ Python files and 100+ SQL files)
- **Documentation:** `CLAUDE.md` in the project root is the main reference doc

**Connection approach:** Use the `.env` file for credentials. If direct `psql` doesn't work, write a short Python script using `psycopg2` to connect. Either approach is fine — what matters is getting real data from the live database.

---

## Output Rules (IMPORTANT — Read This)

Your report will be compared directly against two other AI auditors. To make that comparison meaningful, you MUST follow this exact structure. **Do not reorganize, rename, or skip any section.**

### Required Output File
Save your report as: `docs/AUDIT_REPORT_ROUND2_[YOUR_NAME].md`
- Replace `[YOUR_NAME]` with: `CLAUDE`, `GEMINI`, or `CODEX`

### Required Severity Ratings
Every finding must use one of these four labels — no other labels:

| Label | What It Means |
|-------|---------------|
| 🔴 CRITICAL | Broken right now, causing wrong results or security risk |
| 🟡 HIGH | Not broken, but will cause problems soon or blocks deployment |
| 🔵 MEDIUM | Should be fixed but the platform still works without it |
| ⚪ LOW | Nice to have, minor improvement, cosmetic |

### Required Format for Each Finding
```
### [SEVERITY] Finding Title

**What's wrong:** [Plain English description — imagine explaining to someone who doesn't code]
**Evidence:** [The actual query or command you ran, and what it returned]
**Impact:** [What this means for a union organizer using the platform]
**Suggested fix:** [What should be done, with rough time estimate]
**Verified by:** [The specific SQL query, API call, or file you checked]
```

---

## Checkpoints

After completing each section below, **STOP and show me a brief summary** of what you found before moving to the next section. I want to understand what's happening at each step — don't do the whole thing silently and dump a giant report at the end.

---

## SECTION 1: Database Inventory (What's Actually In There?)

**What this does:** Creates a complete, honest count of everything in the database — tables, views, sizes, row counts. Not what the documentation *says* is there, but what's *actually* there right now.

**Why it matters:** Over months of development, tables get created for experiments, one-off analyses, or features that never got finished. Some might be empty. Some might have millions of rows but nothing ever reads from them. We need ground truth.

**Steps:**

1. Connect to the `olms_multiyear` database
2. Get EVERY table, view, and materialized view from `information_schema.tables`
3. For each table, get:
   - Actual row count (use `SELECT count(*)` — don't trust the estimates in `pg_stat_user_tables` because they were stale/zero in Round 1)
   - Size on disk (use `pg_total_relation_size()`)
   - Number of columns
   - Whether it has a primary key
4. Sort tables by size (largest first)
5. Flag any tables with ZERO rows
6. Flag any tables that seem like experiments or one-off imports (look for names like `temp_`, `test_`, `backup_`, `old_`, or tables with very few columns and no relationships)
7. Total everything up: total tables, total views, total database size

**Required output for this section:**

```
| Category | Table Count | Total Rows | Total Size |
|----------|-------------|------------|------------|
| Core (unions, employers, relations) | ? | ? | ? |
| NLRB (elections, cases, participants) | ? | ? | ? |
| OSHA (establishments, violations) | ? | ? | ? |
| Corporate (GLEIF, SEC, crosswalk) | ? | ? | ? |
| Geographic (QCEW, BLS, density) | ? | ? | ? |
| Matching (splink, fuzzy matches) | ? | ? | ? |
| Other/Unknown | ? | ? | ? |
| **TOTAL** | ? | ? | ? |
```

Plus: Top 20 tables by size, and a list of empty/suspicious tables.

**⏸️ CHECKPOINT: Stop here and show me the inventory before continuing.**

---

## SECTION 2: Data Quality (Is the Data Actually Good?)

**What this does:** Looks *inside* the most important tables to check if the data is healthy. Having 60,000 rows means nothing if half the important columns are blank.

**Why it matters:** Union organizers make decisions based on this data. If employer names are missing, or cities are blank, or NAICS codes (industry classifications) aren't filled in, then searches return incomplete results and scores are unreliable.

**Steps:**

1. For each of these core tables, check how complete the important columns are:

   **`f7_employers_deduped`** (the main employer list — ~60,000 employers who have union contracts):
   - employer_name, city, state, naics, lat, lon, latest_unit_size
   
   **`unions_master`** (the main union list):
   - union_name, aff_abbr, members, city, state
   
   **`osha_establishments`** (workplaces inspected by OSHA):
   - estab_name, city, state, sic_code, naics_code
   
   **`nlrb_elections`** (union election results):
   - employer_name, city, state, eligible_voters, votes_for, votes_against, union_won
   
   **`mergent_employers`** (commercial business database):
   - company_name, duns, ein, employees_site, naics_primary

2. For each column above: count total rows, null values, empty strings. Calculate percent filled.

3. Check for duplicates:
   - Same employer_name + state appearing more than once in `f7_employers_deduped`
   - Same establishment name + city + state in `osha_establishments`
   - Same case_number appearing multiple times in `nlrb_elections`

4. Check key relationships (do records that reference other tables actually point to real records?):
   - Every `employer_id` in `f7_union_employer_relations` → does it exist in `f7_employers_deduped`?
   - Every `f_num` in `f7_union_employer_relations` → does it exist in `unions_master`?
   - Every `case_number` in `nlrb_participants` → does it exist in `nlrb_elections`?
   - Every `employer_id` in `osha_f7_matches` → does it exist in `f7_employers_deduped`?
   - Every `establishment_id` in `osha_f7_matches` → does it exist in `osha_establishments`?

5. Report any "orphaned" records — records that point to things that no longer exist. Count them. This was a major finding in Round 1 (about 50% orphaned in some tables).

**Required output:** A completeness table for each checked table showing column-by-column fill rates, plus orphan counts for each relationship checked.

**⏸️ CHECKPOINT: Stop here and show me data quality findings before continuing.**

---

## SECTION 3: Cross-Database Matching (Does the Linking Actually Work?)

**What this does:** The whole point of this platform is connecting data that wasn't designed to go together — linking an employer from DOL filings to their OSHA safety record to their NLRB election history. This section tests whether those connections actually work.

**Why it matters:** If an organizer looks up "Amazon" and the platform can't connect Amazon's DOL filing to Amazon's OSHA violations, the platform has failed at its core purpose. Match rates tell us how much of the data is actually usable in a connected way.

**Steps:**

1. **F7 employer → OSHA establishment matching:**
   - How many F7 employers have at least one OSHA match? (check `osha_f7_matches`)
   - What's the match rate? (matched / total F7 employers)
   - What's the average confidence score of matches (if applicable)?
   - How many OSHA establishments remain unmatched?

2. **F7 employer → NLRB election matching:**
   - How many F7 employers appear in NLRB election records?
   - How many NLRB elections can be linked back to a known F7 employer?

3. **Corporate identifier crosswalk** (`corporate_identifier_crosswalk`):
   - How many F7 employers have entries in the crosswalk?
   - Of those, how many have: a GLEIF identifier? A Mergent DUNS? An SEC CIK? An EIN?
   - What percentage have MORE than one external identifier?

4. **Public sector coverage:**
   - How many public sector union locals link to `unions_master`?
   - How many public sector employers have bargaining unit data?

5. **Unified employer view:**
   - Check whatever unified/combined employer view exists
   - How many total employers from each source?
   - What percentage have geographic coordinates?
   - What percentage have industry codes (NAICS)?

**Required output:** A match rate summary table:

```
| Connection | Matched | Total | Match Rate |
|-----------|---------|-------|------------|
| F7 employers → OSHA | ? | ? | ?% |
| F7 employers → NLRB | ? | ? | ?% |
| F7 employers → Crosswalk | ? | ? | ?% |
| NLRB elections → Known union | ? | ? | ?% |
| Public sector locals → unions_master | ? | ? | ?% |
```

**⏸️ CHECKPOINT: Stop here and show me match rates before continuing.**

---

## SECTION 4: API & Endpoint Audit (Does the Website Backend Work?)

**What this does:** The API is the software that sits between the database and the website. When someone searches for an employer on the website, the API is what actually runs the database query and sends back results. This section checks whether the API endpoints actually work.

**Why it matters:** A broken API endpoint means a feature that looks like it exists on the website but actually fails when someone clicks on it. That's worse than not having the feature at all — it erodes trust.

**Steps:**

1. Read `api/labor_api_v6.py`
2. List EVERY endpoint (URL path) with:
   - What HTTP method it uses (GET, POST, DELETE)
   - What database table(s) it queries
   - One-line description of what it does
3. For each endpoint, check:
   - Does it reference tables/columns that actually exist in the database?
   - Does it use parameterized queries (safe) or string concatenation for SQL (unsafe — means someone could potentially inject malicious commands)?
4. Try to actually call a few key endpoints and verify they return data
5. Flag any endpoints that are dead (reference nonexistent tables)
6. Flag any security concerns (SQL injection, missing authentication, wide-open CORS)
7. Count: total endpoints, working, probably broken, security risks

**Required output:** Endpoint inventory table plus security findings.

**⏸️ CHECKPOINT: Stop here and show me API findings before continuing.**

---

## SECTION 5: Frontend Review (What Does the User Actually See?)

**What this does:** Checks the web interface that organizers would actually use — the search pages, the maps, the scorecards, etc.

**Why it matters:** The frontend is what organizers interact with. If it has bugs, shows wrong data, or has confusing layouts, none of the backend quality matters.

**Steps:**

1. Inventory all frontend files (HTML, JavaScript, CSS)
2. Check what API endpoints the frontend calls — are they all endpoints that actually exist?
3. Look for hardcoded values that would break in deployment (like `localhost:8001` written directly in the code)
4. Check if there are any configuration files for different environments (local vs. deployed)
5. Estimate total lines of code and general complexity
6. Note any obvious usability or accessibility issues

**Required output:** File inventory, hardcoded values found, and any broken connections to the API.

**⏸️ CHECKPOINT: Stop here and show me frontend findings before continuing.**

---

## SECTION 6: Previous Audit Findings — Are They Fixed?

**What this does:** In the Round 1 audit (February 13, 2026), several critical issues were found. This section checks whether those specific issues have been resolved.

**Why it matters:** Finding problems is only half the job. We need to know if the fixes actually happened, or if these issues are still sitting there.

**Check each of these Round 1 findings and report FIXED, PARTIALLY FIXED, or STILL BROKEN:**

| # | Round 1 Finding | What to Check |
|---|----------------|---------------|
| 1 | **Database password in code** — The password `Juniordog33!` appeared directly in at least one script file | Search all `.py` and `.sql` files for this password or any hardcoded credentials |
| 2 | **Authentication disabled** — The API has a login system but it's turned off by default | Check the API code for auth middleware — is it actually enforcing login? |
| 3 | **CORS wide open** — Any website can access the API | Check CORS configuration in the API startup code |
| 4 | **~50% orphaned data in f7_union_employer_relations** — Half the employer_id values pointed to employers that no longer exist | Re-run the orphan check from Section 2 and compare to Round 1 numbers |
| 5 | **Frontend is 9,500+ lines in one file** — Hard to maintain | Check if the frontend has been split into smaller files |
| 6 | **OSHA match rate ~14%** — Most OSHA establishments couldn't be linked to F7 employers | Check current match rate |
| 7 | **WHD (wage theft) match rate ~2%** — Almost no wage theft cases linked to employers | Check current match rate |
| 8 | **No tests for matching pipeline** — The most important code had zero automated tests | Check if tests now exist for matching logic |
| 9 | **README has wrong startup command** — Tells users to run a file that doesn't exist | Check the README |
| 10 | **990 filer data completely unmatched** — IRS nonprofit data imported but never linked to anything | Check if 990 data now connects to other tables |
| 11 | **GLEIF data: 10+ GB for only 605 matches** — Enormous storage for almost no value | Check current GLEIF size and match count |
| 12 | **LIMIT 500 in API silently cuts results** — Some API endpoints cap results at 500 without telling the user | Check if limits are now communicated or removed |
| 13 | **Two separate scoring systems not unified** — OSHA scorecard (0-100) and Mergent scorecard (0-62) use different scales | Check if these have been unified |
| 14 | **195 orphaned F7 union file numbers** — Union records that don't link to any known union | Re-check orphan count |
| 15 | **Stale pg_stat estimates** — `ANALYZE` hadn't been run, making database statistics unreliable | Check if `ANALYZE` has been run recently |

**Required output:** A table with each finding showing FIXED / PARTIALLY FIXED / STILL BROKEN, plus evidence.

**⏸️ CHECKPOINT: Stop here and show me previous findings status before continuing.**

---

## SECTION 7: What Changed Since Round 1? (Delta Analysis)

**What this does:** Identifies anything that's been added, removed, or modified since the last audit on February 13, 2026.

**Why it matters:** Changes since the last audit might have introduced new problems, or they might have fixed old ones. Either way, we need to know what's different.

**Steps:**

1. Compare total table count to Round 1 (was 159 tables, 187 views, 3 materialized views)
2. Compare total database size to Round 1 (was 22 GB)
3. Look for any NEW tables not in the Round 1 inventory
4. Look for any tables that were REMOVED since Round 1
5. Check if row counts in major tables have changed significantly
6. Look for recently modified files (check git log if available, or file modification dates)
7. Note any new scripts, new API endpoints, or new frontend features

**Required output:** A "what changed" summary — new tables, removed tables, major count changes, new files.

**⏸️ CHECKPOINT: Stop here and show me the delta analysis before continuing.**

---

## SECTION 8: Scripts & File System (What Code Exists?)

**What this does:** Catalogs the Python scripts and SQL files to understand which are essential, which are one-time data loaders, and which are dead weight.

**Why it matters:** With 440+ Python files and 100+ SQL files, there's a lot of code. Some of it is critical (if it breaks, the platform breaks). Some of it was used once to load data and never needed again. Some of it references tables that no longer exist. We need to know which is which.

**Steps:**

1. Count files by type and directory
2. Identify "critical path" scripts — the ones that would need to run to rebuild the database from scratch
3. Check for any scripts that reference tables that no longer exist (dead references)
4. Check for hardcoded credentials in any file
5. Check for any scheduled or recurring scripts (cron jobs, task scheduler entries)
6. List the most important/frequently-used scripts with one-line descriptions

**Required output:** Directory summary with file counts, critical scripts list, dead reference list, credential scan results.

---

## SECTION 9: Documentation Accuracy

**What this does:** Compares what `CLAUDE.md` and other documentation says against what's actually true.

**Why it matters:** If future developers (or future-you) read the docs and the numbers are wrong, they'll make bad decisions.

**Steps:**

1. Compare every table name and row count in `CLAUDE.md` against actual database state
2. Flag claims about features that don't actually work
3. Note documentation that's missing for existing tables/features
4. Check if the README accurately describes how to start the system

**Required output:** A list of specific corrections needed in each documentation file.

---

## SECTION 10: Overall Assessment & Recommendations

**What this does:** Pulls everything together into a clear picture and actionable priorities.

**Required output (use this exact structure):**

### 10.1 — Overall Health Score
Rate the platform: CRITICAL / NEEDS WORK / SOLID / EXCELLENT — with a one-paragraph justification.

### 10.2 — Top 10 Issues (Ranked by Impact)
Number them 1-10. Each one gets the severity label (🔴🟡🔵⚪), a plain-English title, and a one-sentence explanation of why it matters for organizers.

### 10.3 — Quick Wins
Things that could be fixed in under 1 hour each. Be specific.

### 10.4 — Tables to Consider Dropping
Any truly orphaned tables with no connections, no API access, and no apparent purpose. Include estimated space savings.

### 10.5 — Missing Indexes
Specific database indexes that should be created to improve speed. Include the SQL command to create each one.

### 10.6 — Strategic Recommendations
Bigger-picture suggestions: new data sources to add, architectural changes, deployment readiness assessment. Separate "should do now" from "should do eventually."

### 10.7 — What's Working Well
Don't just list problems — also call out what's genuinely impressive or well-built. Be specific.

---

## Final Reminders

1. **Be honest.** Don't sugarcoat problems. Don't exaggerate them either.
2. **Show your work.** Include the actual queries you ran so findings can be verified.
3. **Explain in plain English.** When you find something technical, explain what it means in practical terms — "this means when an organizer searches for X, they won't see Y" is better than "foreign key constraint violated."
4. **Follow the section structure exactly.** Your report will be compared side-by-side with two other auditors. If you reorganize or rename sections, the comparison breaks.
5. **Use the severity labels.** Every finding needs a 🔴🟡🔵⚪ rating.
6. **Stop at each checkpoint.** Don't run the whole thing silently.
7. **Note your limitations.** If you can't access something, or if a query fails, say so. Don't pretend you checked something you didn't.
8. **This is YOUR independent assessment.** Don't try to guess what the other auditors will say. Just report what you find.
