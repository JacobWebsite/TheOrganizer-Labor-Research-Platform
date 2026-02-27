# Platform Audit — Codex (Code Quality & Architecture Reviewer)
## February 25, 2026

---

## YOUR ROLE

You are auditing the code quality, test coverage, architecture, and deployment readiness of a labor relations research platform. Your job is to open files, read actual code, and find bugs, structural problems, and gaps.

**You are one of three auditors.** Claude Code is querying the database directly to verify data accuracy. Gemini is assessing strategic value for organizers. Your unique strength is deep code review — you read the actual source files and find problems the others can't.

**Critical rules:**
1. **Read the actual code.** Don't say "the scoring pipeline appears to work based on file names." Open the file, read the SQL, and verify line by line against the specification.
2. **Show file paths, line numbers, and code snippets.** "There's a problem in scoring" is useless. "Line 340 of `scripts/scoring/build_unified_scorecard.py` contains `s.score_industry_growth AS score_financial`" is useful.
3. **Do NOT fix anything during this audit.** Document only. Fixes will come from the roadmap this audit produces. The previous audit had problems where fixes were made during the audit and it was hard to track what changed.
4. **Say "I didn't check this" when you skip something.** A partial honest audit is far better than a falsely comprehensive one.
5. **Be thorough.** It is much better to check everything and find nothing than to skip something and miss a problem that has to be fixed later.

**Context files you should have:**
- `PROJECT_STATE.md` — current platform state, session handoffs, known issues
- `CLAUDE.md` — database schema and technical reference
- `SCORING_SPECIFICATION.md` — how scoring is supposed to work
- `UNIFIED_ROADMAP_2026_02_19.md` — current roadmap
- `REACT_IMPLEMENTATION_PLAN.md` — frontend architecture decisions
- `PLATFORM_REDESIGN_ADDENDUM.md` — security, OLMS data, deep dive tool decisions

---

## WHAT CHANGED SINCE THE LAST AUDIT (Feb 19, 2026)

Your focus is the CODE side of these changes:

1. **Research Agent Built** — 96 runs, 7.93/10 quality. Check: Is the code well-structured? Error handling? Testable?

2. **CorpWatch SEC EDGAR Import** — 14.7M rows, 7 tables. Check: Are import scripts idempotent (safe to run twice)? Data validation?

3. **Data Enrichment** — Geocoding 73.8%→83.3%, NAICS inference. Check: Edge cases that could produce wrong results?

4. **NLRB Participant Cleanup** — 492K junk rows removed. Check: Done safely with backups/logging?

5. **React Frontend** — All 6 phases complete, 134 tests. Check: Consistent patterns? State management? Error handling?

6. **Scoring Code Updates** — NLRB decay, financial fix, factors >= 3. Check: Do the code changes match the spec?

7. **Splink Threshold** — Raised to 0.70. Check: Is it enforced consistently in all code paths?

8. **Docker Artifacts** — Dockerfile, docker-compose.yml, nginx.conf. Check: Functional or stubs?

9. **Source Re-runs Incomplete** — 990 (1/5 batches), WHD (never re-run), SAM (never re-run). Check: Is there code to resume these? Error handling for the OOM failures?

---

# PART 1: SHARED OVERLAP ZONE

**You MUST answer all 10 of these questions.** Two other AI auditors (Claude Code and Gemini) are answering the same questions independently. Your answers will be compared side by side. Label each answer clearly (OQ1, OQ2, etc.).

---

### OQ1: Priority Tier Spot Check (5 Employers)

Pick 5 employers ranked "Priority" from the scoring data. For each:
- Employer name, state, employer_id
- Final score (0-10)
- How many scoring factors have data
- What factors drive the high score
- Whether this looks like a real organizable employer
- Whether an organizer would find the profile useful

**Why:** Previous audit found placeholders and federal agencies ranked Priority with perfect scores.

---

### OQ2: Match Accuracy Spot Check (20 Matches)

Pick 20 matches from `unified_match_log`:
- 5 OSHA, 5 NLRB, 5 WHD/SAM, 5 Splink fuzzy near 0.70 threshold
- For each: source name vs matched name, method, confidence, your judgment (correct/wrong/uncertain)

**Why:** Previous audit found 10-40% false positive rates.

---

### OQ3: React Frontend ↔ API Contract (5 Features)

Check these 5 features by reading the frontend code AND the API code:
1. **Employer search** — frontend API calls vs actual endpoint response shape
2. **Employer profile** — all data cards vs actual endpoint responses
3. **Scoring breakdown** — factor display vs actual data returned
4. **Union profile** — financial/membership cards vs endpoints
5. **Targets page** — tier cards vs data endpoint

For each: data shape match? Missing fields? Error handling? Loading states?

---

### OQ4: Data Freshness and View Staleness

Check both code and data:
- When were materialized views last refreshed? (Check code for refresh mechanisms)
- Do the views reflect Feb 19 code changes?
- What does the `data_source_freshness` table code look like? Does it populate correctly?
- Are there MV refreshes that block writes (missing `CONCURRENTLY`)?
- Are there views referencing non-existent tables/columns?

---

### OQ5: Incomplete Source Re-runs — Impact Assessment

Check the matching pipeline code:
- What code exists for 990, WHD, SAM re-runs?
- Are there checkpoint/resume mechanisms?
- What caused the WHD and SAM OOM failures? Is there code to handle this?
- How would you complete these re-runs safely?

---

### OQ6: The Scoring Factors — Current State (All 8)

Open `scripts/scoring/build_unified_scorecard.py` and verify each factor against SCORING_SPECIFICATION.md:
1. OSHA (1x): industry normalization, 5-year half-life, severity bonus
2. NLRB (3x): 70/30 nearby/own, 25-mile radius, 7-year half-life, latest-election dominance
3. WHD (1x): 0/5/7/10 tiers, 5-year half-life
4. Contracts (2x): tiered 0/4/6/7/8/10 or still flat 4.00
5. Density (1x): state × industry intersection
6. Size (3x): sweet-spot curve
7. Similarity (2x): active or dead? What connects employer_comparables to score?
8. Growth (2x): is `score_financial` still a copy?

---

### OQ7: Test Suite Reality Check

- Run the full test suite. Pass/fail counts and what fails.
- Tests that verify actual score values?
- Tests that verify match accuracy?
- Frontend tests? What do they test?
- Most important thing with no test coverage?

---

### OQ8: Database Cleanup Opportunity

Check the codebase for:
- Scripts that create tables that are never used
- ETL scripts that load data into tables nothing else reads
- Import scripts for the CorpWatch data — are those tables connected?
- Views that reference non-existent tables (orphaned views)
- Any code that references the 42 industry-specific views

---

### OQ9: Single Biggest Problem

What's the single most important thing to fix before showing this to organizers?
- Plain language description
- Who it affects
- Confidence level
- Effort estimate
- Consequence of not fixing

---

### OQ10: Previous Audit Follow-Up

Check the codebase for evidence that these were addressed:
1. Name similarity tested at 0.75/0.85? (Look for test scripts or analysis files)
2. Membership validation? (Any state-level comparison scripts?)
3. Orphaned match investigation? (Analysis scripts or cleanup scripts?)
4. NAICS inference? (Enrichment scripts?)
5. Employer grouping fixes? (Dedup or merge scripts?)
6. Comparables→similarity pipeline? (Code connecting the two?)
7. NLRB proximity data source? (Which table does the code actually query?)
8. Junk record cleanup? (Filtering scripts?)
9. Geocoding by tier? (Analysis scripts?)
10. Decisions: Check `.env`, scoring code, frontend for evidence of changes

---

# PART 2: YOUR SPECIFIC INVESTIGATION AREAS

---

## Area 1: Scoring Pipeline — Line by Line

Open `scripts/scoring/build_unified_scorecard.py` and read it thoroughly.

### 1A: Factor-by-Factor Code Verification

For EACH of these 8 factors, find the exact lines that calculate it:

**Factor 1 — OSHA Safety (Weight: 1x)**
- Does the code do industry normalization?
- 5-year half-life time decay implemented?
- +1 for willful/repeat (capped at 10)?
- Which table(s) does it query?

**Factor 2 — NLRB Activity (Weight: 3x)**
- 70/30 split (nearby momentum / own history)?
- 25-mile radius for "nearby"?
- 7-year half-life decay (added Feb 19)?
- Latest-election dominance logic?
- **CRITICAL:** Does it JOIN to `nlrb_participants`? If yes, does it use cleaned data or junk fields?

**Factor 3 — WHD Wage Theft (Weight: 1x)**
- Tier system (0/5/7/10)?
- 5-year half-life?
- Which match table? Old `whd_f7_matches` or `unified_match_log`?

**Factor 4 — Government Contracts (Weight: 2x)**
- Tiered scoring (0/4/6/7/8/10) or still flat 4.00?
- Combines federal + state + local?

**Factor 5 — Union Density (Weight: 1x)**
- State × industry intersection?
- What BLS data?

**Factor 6 — Employer Size (Weight: 3x)**
- Sweet-spot curve (15-500 ramp, plateau, taper at 25K+)?
- What column for size?

**Factor 7 — Statistical Similarity (Weight: 2x)**
- Active or commented out?
- What connects `employer_comparables` to the score?
- Why only 186 employers?

**Factor 8 — Industry Growth (Weight: 2x)**
- BLS 10-year projections?
- **Line 340 specifically:** Is `score_financial` still `s.score_industry_growth AS score_financial`?

### 1B: The Weighted Average

- Find the exact code combining factors into final score
- Verify weights match spec (OSHA 1, NLRB 3, WHD 1, Contracts 2, Density 1, Size 3, Similarity 2, Growth 2)
- Divide-by-zero risk when factors_available = 0?
- Where is `factors_available >= 3` for Priority enforced? Scoring code, view, or API?

---

## Area 2: React Frontend Architecture

### 2A: Component Inventory
- Total component files? Feature directories?
- Any components over 500 lines?
- Total frontend LOC?

### 2B: State Management
- Zustand used consistently, or mix of local state/Context/prop drilling?
- List every Zustand store
- Any stores that are too large?

### 2C: API Integration
- Centralized API client, or scattered `fetch` calls?
- Global error boundary?
- List every API endpoint the frontend calls

### 2D: TanStack Query
- Used for all data fetching?
- Consistent cache keys?
- Loading states handled everywhere?
- Background refresh configured?

### 2E: Frontend-API Contract (5 pages)

For each major page, trace the actual code path:

1. **Search page**: What endpoint? What request shape? What response shape? Match?
2. **Employer profile**: What endpoints for score, OSHA, NLRB, hierarchy, etc.? All exist?
3. **Union profile**: Financial and membership endpoints? Data shape match?
4. **Targets page**: Tier data endpoint? Response shape?
5. **Admin panel**: Freshness dashboard? What data does it expect?

### 2F: Error and Edge Cases
- Employer with no score? No matches? No OSHA?
- API returns 500? Empty array? Non-existent ID?
- Is there a 404 page?
- Does the search have the silent failure bug? (Wrong param name returns all records)

---

## Area 3: API Endpoint Complete Audit

### 3A: Endpoint Inventory
List EVERY endpoint in FastAPI. For each:
- Method + path
- Input validation present?
- Auth required?
- What queries it runs

### 3B: Security
- Any raw SQL with string concatenation instead of parameterized queries?
- Which endpoints require auth? Which don't but should?
- CORS configuration?
- Admin endpoints protected?
- `DISABLE_AUTH=true` in `.env`?

### 3C: Performance
- Most expensive queries?
- Full table scans on large tables?
- Is `nlrb_participants.case_number` index present?
- MV usage where queries should be cached?

### 3D: Search Endpoint Bug
Previous audit: using `?q=` instead of `?name=` silently returns all 107,025 records. Still the case?

### 3E: Profile Endpoints
Check `/api/profile/employers/{id}` and `/api/profile/unions/{f_num}`:
- Complete data returned?
- Invalid ID handling?
- Query complexity/speed?
- Include CorpWatch or research agent data?

---

## Area 4: Test Coverage Deep Dive

### 4A: Test Inventory
List every test file. Categorize:
- Unit tests (individual functions)
- Integration tests (API + database)
- Frontend tests (React components)
- Scoring tests (actual calculations)
- Matching tests (accuracy)

### 4B: Coverage Analysis
Run coverage if possible (`pytest --cov`). Report for critical files:
- `build_unified_scorecard.py`
- `run_deterministic.py`
- `splink_pipeline.py`
- `api/main.py`
- `api/routers/employers.py`
- `api/routers/profile.py`

### 4C: Test Quality
Pick 10 tests at random. Do they test meaningful behavior or just "doesn't crash"?
- Any tests asserting specific score values?
- Any tests verifying match accuracy?
- Any regression tests for previously found bugs?

---

## Area 5: Deployment Readiness

### 5A: Docker
Open `Dockerfile`, `docker-compose.yml`, `nginx.conf`:
- Functional or empty stubs?
- Could someone deploy today?
- What environment variables needed?
- Database migration strategy? (How to recreate 174 tables?)
- Data loading strategy?

### 5B: Portability
Previous audit found 19 scripts with hardcoded `C:\Users\jakew\Downloads` paths:
- Still present?
- How many scripts have hardcoded paths?
- Other portability issues?

### 5C: Dependencies
- Complete `requirements.txt` or `pyproject.toml`?
- Python versions pinned?
- npm/Node dependencies pinned?
- Fresh-machine install possible with documented steps?

### 5D: Credentials
- Passwords/tokens in code (not `.env`)?
- "Juniordog33!" in 10 archived files still present?
- `.env` in `.gitignore`?

---

## Area 6: Code Quality and Maintenance

### 6A: Dead Code
- Python scripts never imported/called?
- React components never rendered?
- Versioned duplicates (`analyze_v1.py`, `v2`, `v3`)?
- Previous audit said "55 analysis scripts, 20-30 superseded" — still the case?

### 6B: Error Handling
- ETL scripts: graceful fail or tracebacks?
- Matching scripts: progress logging? Can you tell where a failed run stopped?
- Consistent logging pattern?

### 6C: Documentation in Code
- Critical files have docstrings explaining WHY?
- Is `PIPELINE_MANIFEST.md` up to date? (Check 5 random entries)

### 6D: The Pipeline Run Order
Check the documented pipeline run order in PROJECT_STATE.md Section 3:
```
1. ETL → 2. run_deterministic.py → 3. splink_pipeline.py → 4. build_employer_groups.py
→ 5. build_employer_data_sources.py → 6. build_unified_scorecard.py
→ 7. compute_nlrb_patterns.py → 8. create_scorecard_mv.py
→ 9. compute_gower_similarity.py → 10. train_propensity_model.py
→ 11. create_data_freshness.py
```
- Does this order actually work? Are there hidden dependencies?
- What happens if you run them out of order?
- Are there race conditions if two scripts run simultaneously?

---

# OUTPUT FORMAT

Structure your report as:

1. **Executive Summary** (5-10 sentences)
2. **Shared Overlap Zone Answers** (all 10, labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-6, with file paths and line numbers for every finding)
4. **Bug List** (every bug: file, line, severity [Critical/High/Medium/Low], description)
5. **Architecture Concerns** (structural issues that aren't bugs but will cause problems)
6. **Missing Test Coverage** (10 most important things with no tests)
7. **Deployment Blockers** (things that MUST be fixed before deployment)
8. **Recommended Priority List** (top 10 things to fix, with effort estimates)
