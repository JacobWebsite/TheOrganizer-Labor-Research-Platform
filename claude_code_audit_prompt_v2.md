# Deep Database & Platform Audit — Claude Code Prompt (v2)

## How This Works

You are going to audit a labor relations research platform. Think of this like a building inspection — you're checking every room, every pipe, every wire to figure out what's solid, what's cracked, and what's a fire hazard.

**The database** is called `olms_multiyear`. It runs on PostgreSQL, locally on this machine. Connect using the credentials in the `.env` file in the project root.

**Be honest and thorough.** Don't assume something works just because it exists. Actually test it. If a table has 60,000 rows but half the important columns are empty, that matters. If an API endpoint claims to show corporate hierarchies but the table it needs doesn't exist, that matters.

**Output:** Create a single report file at `docs/AUDIT_REPORT_2026.md`. Write to it as you go — don't wait until the end. Use plain language. When something is broken, explain what it means in practical terms: "this means when someone searches for an employer, they won't see OSHA violations" is better than "foreign key constraint violated."

**Checkpoints:** After each numbered checkpoint below, **STOP** and show me a brief summary of what you found. Wait for my go-ahead before continuing. This is important — it lets me catch problems early and ask questions before you move on.

---

## PHASE 1: What's Actually In The Database?

### Step 1.1 — Connect and Count Everything

**What you're doing:** Making a complete inventory of every table and view in the database, with real row counts — not what the documentation says, but what's actually there right now.

**Why this matters:** Over months of development, tables get created for experiments, one-time data loads, or features that never got finished. Some might be empty. Some might have millions of rows but nothing actually uses them. We need to know what we're working with before we can evaluate anything else.

**How to do it:**
1. Connect to the `olms_multiyear` database
2. Query `information_schema.tables` to get EVERY table and view — not just the ones you know about from documentation
3. For each table, get:
   - **Actual row count** — use `SELECT count(*) FROM table_name`. For very large tables (over ~2 million rows), you can use the PostgreSQL estimate from `pg_stat_user_tables.n_live_tup` but note it's an estimate. If `n_live_tup` returns 0 for everything, that itself is a finding (it means the database statistics are stale).
   - **Number of columns** — how wide is the table?
   - **Whether it has a primary key** — a primary key is like a serial number; it guarantees every row is unique. A core table without one is a problem.
   - **Physical size on disk** — use `pg_size_pretty(pg_total_relation_size('table_name'))`
4. Sort tables by size so we can see what's taking up the most space
5. Flag any tables with ZERO rows (empty tables that do nothing)
6. Separate tables from views (views are saved queries that look like tables but don't store data independently) and materialized views (which DO store data as a snapshot)

**⏸️ CHECKPOINT 1: Stop here. Show me the full table inventory grouped by size, and list the empty tables. I want to see the total count of tables, views, and materialized views.**

---

### Step 1.2 — Categorize Everything

**What you're doing:** Grouping all those tables into logical categories so we can make sense of what belongs where.

**Why this matters:** Right now we have a flat list of hundreds of objects. Grouping them makes it possible to see "oh, we have 15 NLRB tables, 6 OSHA tables, 28 corporate tables" etc. This also helps identify tables that don't seem to belong anywhere — orphaned experiments.

**Categories to use:**
- **Core (F7/LM/Union)** — The backbone. F7 employer data, LM-2 union financial filings, union master directory
- **OSHA** — Workplace safety inspections, violations, accident reports
- **NLRB** — Union elections, unfair labor practice cases, docket entries
- **Corporate/Financial** — SEC filings, GLEIF entities, SAM.gov contractors, 990 nonprofits
- **Mergent/Scoring** — Business intelligence data, organizing scores, similarity comparisons
- **Matching/Linking** — Tables that connect different data sources (crosswalks, match results)
- **WHD** — Wage and Hour Division enforcement data
- **BLS/Reference** — Bureau of Labor Statistics, industry codes, geographic lookups
- **Public Sector** — Government employers, federal agencies, public bargaining units
- **NYC/NY-Specific** — Local New York data
- **Density/Geographic** — Union density estimates by geography
- **Annual Reports** — Union financial annual report data
- **Unknown/Orphan** — Tables that don't fit anywhere, or were created for experiments

For each category, list the tables with their row counts and sizes.

**⏸️ CHECKPOINT 2: Show me the categorized inventory. Flag anything you couldn't categorize.**

---

### Step 1.3 — Compare Against Documentation

**What you're doing:** Checking whether the documentation (`CLAUDE.md`) accurately describes what's actually in the database.

**Why this matters:** `CLAUDE.md` is the main reference document that Claude Code (and future development sessions) use to understand the platform. If it says a table has 62,000 rows but it actually has 60,000, or if it doesn't mention a table at all that has 800,000 rows, then anyone reading it will make wrong assumptions.

**How to do it:**
1. Read `CLAUDE.md` from the project root
2. For every table name and row count mentioned in `CLAUDE.md`, compare against the actual database
3. List discrepancies: wrong counts, missing tables, tables mentioned that don't exist
4. Note any tables with significant data (over 10,000 rows) that `CLAUDE.md` doesn't mention at all
5. Check the startup command in `CLAUDE.md` — does it reference the correct file? (The API may have been reorganized from a single file into multiple files)

**⏸️ CHECKPOINT 3: Show me all documentation discrepancies found. Flag anything marked CRITICAL.**

---

## PHASE 2: Is The Data Any Good?

### Step 2.1 — Core Table Quality Check

**What you're doing:** Looking inside the most important tables to check if the actual data is healthy. A table can have 60,000 rows, but if half the important columns are blank, it's not as useful as it looks.

**Why this matters:** Quality matters more than quantity. If employer records are missing location data, we can't put them on a map. If union records are missing membership counts, we can't analyze trends. This step tells us the real usable size of our data.

**Tables to check (column by column):**

For each table below, check every important column and report: total rows, null count, empty string count, and percentage that's actually filled in.

1. **`f7_employers_deduped`** — THE core employer table. Check: `employer_name`, `city`, `state`, `naics` (industry code), `latitude`/`longitude` (map coordinates), `latest_unit_size` (how many workers)
2. **`unions_master`** — Master union directory. Check: `union_name`, `aff_abbr` (affiliation), `members`, `city`, `state`
3. **`nlrb_elections`** — Union election records. Check: `case_number`, `election_date`, `eligible_voters`, `union_won`, `vote_margin`
4. **`nlrb_participants`** — People/organizations involved in NLRB cases. Check: `participant_name`, `city`, `state` (geographic data tends to be sparse here)
5. **`osha_establishments`** — Workplaces OSHA has inspected. Check: `estab_name`, `site_city`, `site_state`, `naics_code`
6. **`mergent_employers`** — Business intelligence records. Check: `company_name`, `duns`, `ein`, `employees_site`, `naics_primary`, `organizing_score`, `matched_f7_employer_id` (this tells us how many are connected to our union data)

**⏸️ CHECKPOINT 4: Show me the data quality results. Which tables are in good shape? Which have concerning gaps?**

---

### Step 2.2 — Duplicate Detection

**What you're doing:** Checking whether the same record appears multiple times in tables where it shouldn't.

**Why this matters:** Duplicates inflate counts and can cause double-counting when generating statistics. If the same employer appears twice, anything we calculate about them (total workers, violations, etc.) gets doubled.

**Check these:**
1. **`f7_employers_deduped`** — Look for duplicate `employer_name` + `state` combinations. This table was specifically deduplicated, so duplicates here would mean the dedup process missed something.
2. **`osha_establishments`** — Look for duplicate `estab_name` + `city` + `state`. OSHA creates new records per inspection, so SOME duplication is expected and normal — but note the scale.
3. **`nlrb_elections`** — Look for duplicate `case_number`. Some duplication is expected (runoff elections), but excessive duplication would be a problem.

**⏸️ CHECKPOINT 5: Show me duplicate findings. Distinguish between expected duplication (like OSHA's per-inspection records) and problematic duplication.**

---

### Step 2.3 — Relationship Integrity (The Big One)

**What you're doing:** Checking whether the connections between tables actually work. When Table A says "this record belongs to employer #12345 in Table B," does employer #12345 actually exist in Table B?

**Why this matters:** This is arguably the most important check in the entire audit. The whole platform is built on linking different data sources together. If those links are broken — if records point to employers that don't exist, or to unions that were removed — then any analysis using those connections silently drops data. You could be looking at what you think is a complete picture but you're actually missing half the data, and you'd never know.

**Relationships to test:**

1. **`f7_union_employer_relations.employer_id` → `f7_employers_deduped.employer_id`**
   This is the table that says "Union X represents workers at Employer Y." Check: do ALL the employer IDs in the relations table actually exist in the deduped employer table? If not, how many are orphaned? (Note: orphaned IDs might still exist in the raw `f7_employers` table from before deduplication — check that too.)

2. **`f7_union_employer_relations.union_file_number` → `unions_master.f_num`**
   Same idea but for the union side. Do all union file numbers in the relations table actually exist in the union master directory?

3. **`osha_f7_matches.employer_id` → `f7_employers_deduped.employer_id`**
   Do all OSHA-to-employer matches point to real employers?

4. **`osha_f7_matches.establishment_id` → `osha_establishments.activity_nr`**
   Do all OSHA matches point to real OSHA establishments?

5. **`whd_f7_matches` → `f7_employers_deduped`**
   Same check for Wage & Hour Division matches.

6. **`national_990_f7_matches` → `f7_employers_deduped`**
   Same for nonprofit 990 matches.

7. **`sam_f7_matches` → `f7_employers_deduped`**
   Same for SAM.gov contractor matches.

8. **`nlrb_participants.case_number` → `nlrb_cases.case_number`**
   Do all participant records link to a real case?

9. **`nlrb_employer_xref.f7_employer_id` → `f7_employers_deduped.employer_id`**
   This is the NLRB-to-F7 cross-reference. Check for orphaned IDs.

10. **`ps_union_locals` → `unions_master`**
    Do public sector union locals link back to the master directory?

For any broken relationships, explain clearly:
- How many records are orphaned
- What percentage of the total that represents
- What the practical impact is (e.g., "50% of union-employer bargaining links silently disappear in any query that joins these tables")
- What likely caused it (e.g., "deduplication reduced the employer table but the relations table was never updated to use the new IDs")

**⏸️ CHECKPOINT 6: Show me ALL relationship integrity results. This is the most critical checkpoint — take your time here. If there are orphaned records, explain exactly what data is being lost.**

---

## PHASE 3: Views and Indexes

### Step 3.1 — Materialized Views

**What you're doing:** Checking the "pre-computed summaries" that make the platform faster. A materialized view is like a saved snapshot of a complex query — instead of recalculating from scratch every time, the platform reads from the snapshot.

**Why this matters:** If these snapshots are stale (not refreshed after data changes), they show old numbers. If they depend on tables that have changed, they might give wrong results.

**How to do it:**
1. List all materialized views with: row count, size, what tables they pull from
2. Note that there's no built-in way to check when they were last refreshed — this is a risk to flag
3. Verify each one works: `SELECT count(*) FROM mv_name`

**⏸️ CHECKPOINT 7: Show me the materialized view inventory and any staleness concerns.**

---

### Step 3.2 — Regular Views

**What you're doing:** Testing all regular views (saved queries) to see if they actually work and whether any of them reference wrong tables.

**Why this matters:** If a view was written to reference a table that later got replaced (like pointing to the raw employer table instead of the deduplicated one), it will return inflated or duplicated results — and nobody would know unless they specifically checked.

**How to do it:**
1. List ALL regular views
2. Test each one: `SELECT * FROM view_name LIMIT 1` — does it return data or an error?
3. For each view, check what tables it references (look at the view definition)
4. Specifically flag any views that reference `f7_employers` (the raw table) instead of `f7_employers_deduped` (the cleaned table) — these are likely returning duplicated data
5. Note any patterns — are there groups of similar views that seem auto-generated? (like sector-specific triples)
6. Flag duplicate view sets (e.g., two different versions of the same view for the same sector)

**⏸️ CHECKPOINT 8: Show me view findings. How many work? How many reference the wrong tables? Are there patterns of auto-generated views?**

---

### Step 3.3 — Index Analysis

**What you're doing:** Checking the "speed boosters" on the database — indexes make lookups faster, like the index in the back of a book. But unused indexes waste space and slow down data inserts.

**Why this matters:** Unused indexes are pure overhead — they take up disk space and make every data write slightly slower for zero benefit. Duplicate indexes are doubly wasteful. Missing indexes on heavily-queried tables make the platform slow.

**How to do it:**
1. List ALL indexes with: table, columns covered, size, and usage count (`pg_stat_user_indexes.idx_scan`)
2. Categorize: used vs. unused, primary keys vs. unique constraints vs. regular indexes
3. Find duplicate indexes — two indexes on the same table covering the same columns
4. Calculate total wasted space from unused non-essential indexes
5. Check if any large tables (over 10,000 rows) are missing indexes they should have

**Important caveat:** Index usage statistics reset when PostgreSQL restarts. So "0 scans" might just mean the database was restarted recently, not that the index is truly useless. Primary key and unique constraint indexes serve data integrity even without scans — don't recommend dropping those.

**⏸️ CHECKPOINT 9: Show me index findings. What's the total wasted space? List duplicate indexes that should definitely be dropped.**

---

## PHASE 4: Cross-Reference Coverage

### Step 4.1 — How Well Are Data Sources Connected?

**What you're doing:** Measuring the platform's core value proposition — linking employers across multiple government databases. For each F7 employer (our base employer list), how many have been matched to OSHA, WHD, 990, SAM.gov, and the corporate crosswalk?

**Why this matters:** An employer that's connected to OSHA violations, Wage & Hour cases, and federal contract data is rich with intelligence. An employer with zero external connections is just a name and address. This tells us how deep our intelligence goes.

**How to do it:**
1. Start from `f7_employers_deduped` (the core employer table)
2. For each external source, count how many F7 employers have at least one match:
   - OSHA (via `osha_f7_matches`)
   - WHD (via `whd_f7_matches`)
   - 990 nonprofits (via `national_990_f7_matches`)
   - SAM.gov (via `sam_f7_matches`)
   - Corporate crosswalk (via `corporate_identifier_crosswalk`)
3. Calculate "match depth" — how many employers have 0, 1, 2, 3, 4, or 5 external sources connected
4. Note the overall percentage: what fraction of F7 employers have at least one external connection?

**⏸️ CHECKPOINT 10: Show me the cross-reference coverage. What percentage of employers are "rich" (multiple sources) vs. "bare" (F7-only)?**

---

### Step 4.2 — Match Quality

**What you're doing:** For each matching system, looking at HOW the matches were made and how confident we should be in them.

**Why this matters:** Not all matches are created equal. A match based on exact name + exact address is very reliable. A match based on fuzzy name similarity in the same state is much less certain. Knowing the quality distribution tells us how much to trust the connections.

**How to do it:**
For each match table that has a `match_method` or `confidence` column:
1. **OSHA matches** — Break down by match method. What percentage used high-confidence methods (exact name, address) vs. low-confidence methods (fuzzy name only)?
2. **WHD matches** — Same breakdown
3. **990 matches** — Same breakdown
4. **SAM matches** — Same breakdown
5. **NLRB employer xref** — Break down by match method and confidence score
6. **Corporate crosswalk** — How many entries have multiple external identifiers (stronger confirmation) vs. just one?

Flag any match methods with average confidence below 0.6 — these are approaching coin-flip territory.

**⏸️ CHECKPOINT 11: Show me match quality distribution. What percentage of our connections are high-confidence vs. questionable?**

---

### Step 4.3 — Scoring and Unified Views

**What you're doing:** Checking the organizing score system and the unified employer views that power the search interface.

**Why this matters:** The scoring system ranks employers by organizing potential. If the scores are miscalculated or the tiers are wrong, organizers get bad recommendations. The unified views power the search — if they're incomplete, employers are invisible to users.

**How to do it:**
1. **Mergent scoring:** Distribution of score tiers (TOP/HIGH/MEDIUM/LOW). How many are unscored? What are the actual tier thresholds in the data?
2. **`mv_employer_search`**: Source breakdown (how many from F7, NLRB, VR, MANUAL). What percentage have coordinates? State? NAICS codes?
3. **`unified_employers_osha`** (if it exists): Same analysis
4. **Mergent-to-F7 connection**: How many of the 56K Mergent employers actually link back to our union employer data? (Check `matched_f7_employer_id`)

**⏸️ CHECKPOINT 12: Show me scoring and search coverage results.**

---

## PHASE 5: The API (The Bridge Between Database and Users)

### Step 5.1 — Endpoint Inventory

**What you're doing:** Reading through the API code to catalog every endpoint — every URL that the website can call to get data from the database.

**Why this matters:** The API is the bridge between the database and the user interface. If an endpoint is broken, a feature fails silently. If a table has no endpoint, its data is invisible to users even though it exists.

**How to do it:**
1. First, figure out the API structure. Check `api/main.py` — does it import from a single file or multiple router files?
2. For each router file in `api/routers/`, list every endpoint with:
   - URL path (e.g., `/api/employers/search`)
   - HTTP method (GET, POST, DELETE)
   - What tables it queries
   - Brief description
3. Count total endpoints

**⏸️ CHECKPOINT 13: Show me the endpoint inventory. How many endpoints total? How are they organized?**

---

### Step 5.2 — Broken Endpoints and Security

**What you're doing:** Checking which endpoints reference tables or columns that don't actually exist in the database, and checking for security problems.

**Why this matters:** An endpoint that references a nonexistent table will crash with a 500 error every time someone tries to use that feature. SQL injection vulnerabilities could let someone manipulate or destroy data through the web interface.

**How to do it:**
1. For each endpoint, check: does every table and column it references actually exist in the database? Flag any that don't.
2. Check for SQL injection: look for places where user input (from URL parameters or query strings) gets inserted directly into SQL queries without parameterization. The safe pattern looks like `cur.execute("SELECT * FROM t WHERE col = %s", (value,))`. The dangerous pattern looks like `cur.execute(f"SELECT * FROM t WHERE col = '{value}'")`
3. List tables that have NO API endpoint accessing them — these represent data that exists but can't be reached through the web interface

**⏸️ CHECKPOINT 14: Show me broken endpoints and any security issues. Also list the biggest tables that have NO API access.**

---

### Step 5.3 — Dead Code

**What you're doing:** Finding old API files that aren't actually used anymore but are still sitting in the project.

**Why this matters:** Dead code creates confusion. Someone might look at an old file and think it's the current version. Old `.pyc` bytecode files might interfere with Python imports. It's also just clutter.

**How to do it:**
1. Check `api/` directory for any Python files NOT imported by `api/main.py` — these are dead code
2. Check for `.pyc` files in `__pycache__/` that correspond to dead modules
3. Check for `.bak` files
4. Note their sizes so we know what cleanup saves

**⏸️ CHECKPOINT 15: Show me dead code findings.**

---

## PHASE 6: Scripts and File System

### Step 6.1 — Script Inventory and Credential Security

**What you're doing:** Checking all the Python scripts in the project, and specifically looking for security problems with how they connect to the database.

**Why this matters:** There should be ONE way scripts connect to the database — through a shared configuration file (`db_config.py`). If scripts have the database password written directly in their code (hardcoded), that's a security risk: anyone who sees the code sees the password. If scripts have a BROKEN connection pattern (like a typo in the environment variable call), they'll fail when you try to run them.

**How to do it:**
1. Count total Python files in the project
2. Check `scripts/` specifically — how many scripts are there?
3. Search ALL Python files for:
   - The **correct** pattern: `from db_config import get_connection` (or similar)
   - **Hardcoded passwords**: any line containing the actual database password as a string
   - **Broken patterns**: the string `password='os.environ.get(` — this is a common bug where the environment variable call is accidentally wrapped in quotes, turning it into a useless string literal instead of actual code
4. Count how many scripts use each pattern

**⏸️ CHECKPOINT 16: Show me credential security findings. How many scripts use the correct method vs. broken vs. hardcoded?**

---

### Step 6.2 — Critical Path Scripts and Dead Weight

**What you're doing:** Identifying which scripts are essential (you'd need them to rebuild the database) vs. which are one-time data loaders that already did their job vs. which are dead experiments.

**Why this matters:** If you ever need to recreate a table or reload data, you need to know which script does that. And large files sitting in archive directories (like SQL data dumps that have already been imported) are dead weight taking up disk space.

**How to do it:**
1. Identify the "critical path" scripts — the ones that build or maintain core tables
2. Check `archive/` directory: what's in there? How big is it? Are there large SQL dump files that have already been imported into the database?
3. Check for scripts that reference database tables that no longer exist (dead references)
4. Estimate total disk space that could be recovered by cleaning up archive files and dead code

**⏸️ CHECKPOINT 17: Show me critical scripts, dead weight files, and potential disk space recovery.**

---

## PHASE 7: Documentation Accuracy

### Step 7.1 — CLAUDE.md Audit

**What you're doing:** Going through `CLAUDE.md` line by line and comparing every factual claim against the actual database state.

**Why this matters:** `CLAUDE.md` is the instruction manual for any AI agent working on this platform. If it says the startup command is `api.labor_api_v6:app` but the actual command is `api.main:app`, every new session will fail to start. If it says a table has 62,000 rows but it has 60,000, agents will make wrong assumptions.

**How to do it:**
1. Check the startup command — does it work?
2. Check every row count mentioned — compare to actual
3. Check every table mentioned — does it exist?
4. Check for tables NOT mentioned that have significant data
5. Check feature descriptions — do the described features actually work?
6. Check scoring descriptions — are the tier thresholds correct?
7. Check for any stale roadmap references
8. Count total inaccuracies

**⏸️ CHECKPOINT 18: Show me all CLAUDE.md inaccuracies. List the most critical ones first.**

---

### Step 7.2 — README.md and Roadmap Audit

**What you're doing:** Same fact-checking process for README.md and whatever roadmap document exists.

**How to do it:**
1. Check `README.md` for wrong startup commands, wrong counts, missing features, outdated project structure
2. Find the latest roadmap document (might be in `docs/`)
3. For each roadmap item marked "future" or "planned," check if it's actually already done
4. Check for archived documentation in `archive/` that contains methodology explanations not captured elsewhere

**⏸️ CHECKPOINT 19: Show me README and roadmap findings.**

---

## PHASE 8: LM2 vs F7 Membership Analysis

### Step 8.1 — Membership Comparison

**What you're doing:** Comparing two different ways of counting union members to see if they align, and understanding where they diverge.

**Why this matters:** LM-2 filings report dues-paying members. F7 filings report covered workers (everyone in a bargaining unit, whether they pay dues or not). These should be in the same ballpark, but certain sectors will diverge dramatically — building trades unions will show WAY more F7 covered workers than LM-2 members (because they have open-shop hiring halls), and public sector unions will show near-zero F7 coverage (because F7 only covers private sector).

**How to do it:**
1. Calculate total LM-2 membership using `unions_master` and `union_hierarchy` (use hierarchy to avoid double-counting parent+child unions)
2. Calculate total F7 covered workers from `f7_union_employer_relations`
3. Calculate the ratio (F7 / LM2)
4. Break down by major affiliations — which unions have the biggest divergence?
5. Check for orphaned union file numbers in `f7_union_employer_relations` that don't appear in `union_hierarchy` or `unions_master`

**⏸️ CHECKPOINT 20: Show me the membership comparison findings.**

---

## PHASE 9: Summary and Recommendations

### Step 9.1 — Health Score

**What you're doing:** Pulling everything together into an overall assessment.

**Create a scorecard:**
| Category | Score (0-100) | Weight |
|----------|--------------|--------|
| Data Completeness | ? | 25% |
| Data Integrity | ? | 25% |
| API Reliability | ? | 15% |
| Code Quality | ? | 15% |
| Documentation | ? | 10% |
| Infrastructure | ? | 10% |

Write a brief justification for each score based on what you actually found.

---

### Step 9.2 — Top Issues and Quick Wins

1. **Top 10 Issues** ranked by impact — for each, describe: what the problem is, what it means for users, and estimated effort to fix
2. **Quick Wins** — things fixable in under 30 minutes each
3. **Tables that could be dropped or archived** — empty tables, intermediate data that's already been processed
4. **Duplicate indexes to drop** — with the specific SQL commands
5. **Missing indexes to add** — with specific SQL commands
6. **Documentation updates needed** — organized by document and priority

**⏸️ CHECKPOINT 21 (FINAL): Show me the complete summary. I'll review and we can adjust anything that needs changing.**

---

## Important Notes

- **Save your work as you go.** Write to the report file after completing each phase, not just at the end. If something crashes, we don't want to lose everything.
- **When you find something broken, explain what it means for real people.** "60,373 orphaned records" is data. "Half of all union-employer bargaining relationships silently disappear when looking up employer details" is useful information.
- **Don't skip the hard parts.** If a check is complicated or slow, that's fine — it's usually the complicated checks that find the important problems.
- **If `pg_stat_user_tables` returns stale numbers (zeros everywhere), use actual `count(*)` queries instead.** This is itself a finding worth noting.
- **Track which SQL queries you used for each finding** so the results can be verified later.
