# ROUND 5 FULL PROJECT AUDIT
## Labor Relations Research Platform — March 2026

---

## BEFORE YOU READ ANYTHING ELSE

This audit is broader than previous rounds. It covers not just code and data, but vision, research questions, the pathway to achieving our goals, and long-term project quality. Read this entire prompt carefully before beginning any investigation.

**Plain-language standard (MANDATORY):** Every finding, recommendation, and answer must be written so someone with very limited coding or database knowledge can understand it. This means:
- Never use a technical term without a plain-English definition immediately following it
- Explain WHY something matters, not just WHAT it is
- Use analogies from everyday life when helpful
- Explain consequences: "If we don't fix this, users will see X, which will cause Y"
- More detail is always better than less

**Bad example:** "Refactor the JOIN logic in the research tool."
**Good example:** "The research tool is combining two data tables the wrong way — imagine looking up a restaurant by its phone number but accidentally reading the area code of the next listing. The result is the tool returns data from the wrong employer. To fix it: go to `api/routers/research.py` around line 340 and change `LEFT JOIN employer_comparables ON comparables.f7_id = results.employer_id` to use `comparables.employer_id` instead. Estimated time: 2-3 hours. Without this fix, every deep-dive research result may show incorrect comparable companies."

---

## WHO YOU ARE AND WHAT YOU'RE DOING

You are auditing the Labor Relations Research Platform. This is a data system that helps workplace organizations (unions) identify the best employers to target for organizing campaigns. It pulls data from 18+ U.S. government databases and combines them into scores, profiles, and research dossiers.

**Your audit role by AI:**
- **Claude Code:** Run actual database queries, test live endpoints, measure real coverage numbers. Your job is empirical — prove or disprove claims with real data.
- **Codex:** Read source code in depth. Your job is to find logic errors, inconsistencies, and disconnects between what the code does and what the documentation says it does.
- **Gemini:** Evaluate strategy, mission alignment, and whether the platform is on the right path. Your job is to ask: "Is all this effort pointed at the right goals? What's missing from the vision? What research questions are we not asking?"

**All three auditors investigate all nine Focus Areas.** Different angles, same questions. Where you agree, we have high confidence. Where you disagree, we investigate further.

---

## PLATFORM CONTEXT AND SCALE

### What It Does
The platform scores ~146,863 employers that already have union activity (the "union scorecard") and ranks ~4.3 million non-union employers (the "target scorecard"). It tracks 26,665 workplace organizations with an estimated 14.5 million members. The goal is to identify ~50,000 viable organizing targets covering ~10 million workers.

### The Core Product Flow
1. Government data (OSHA, NLRB, WHD, SAM, SEC, IRS 990, BLS, Census) is loaded into PostgreSQL
2. A matching system links records from different agencies that refer to the same employer
3. A scoring system converts all that data into a 0-10 score per employer
4. A FastAPI backend serves that data through 140+ endpoints
5. A React frontend lets organizers search, filter, and explore employers and unions
6. A research tool allows on-demand deep dives into specific employers

### Technology
- **Database:** PostgreSQL 17, localhost, database `olms_multiyear` (~19 GB, 174 tables, 25.5M rows)
- **Backend:** Python + FastAPI, runs on localhost:8001
- **Frontend:** React 19 + Vite 7 + Tailwind CSS + shadcn/ui + Zustand + TanStack Query
- **Scraping:** Crawl4AI (primary), Bright Data (secondary)
- **Matching:** RapidFuzz + pg_trgm + deterministic cascade pipeline

---

## CONFIRMED FINDINGS FROM ALL PREVIOUS ROUNDS
### Treat These as Established Facts — Do Not Re-Litigate Them

1. **Employer size has zero predictive power** for organizing success when combined with other factors
2. **Geographic proximity has zero predictive power** when tested against actual NLRB election outcomes
3. **Enforcement signals** (OSHA + WHD + government contracts) are the strongest predictors
4. **50.4% of F-7 notices are orphaned** — no employer link in the database, making half of all union-employer organizing relationships invisible
5. **Score IS directionally predictive**: top-tier employers have 91% enforcement history; second tier 74% — the scoring model is doing something real
6. **The Stability pillar defaults to 5.0 for ~95% of employers** because both component factors are NULL (no data)
7. **The contracts scoring factor shows 0% coverage** in the union scorecard — the data exists (9,305 matched records) but the pipeline is broken
8. **"No data" looks identical to "no violations" in the UI** — one of the most dangerous user-trust problems
9. **False positives exist in all matching confidence bands** — the known example: "Nex Transport" incorrectly matched to "Cassens Transport"
10. **The research tool has a JOIN bug** — it is currently returning incorrect comparable employer data
11. **Demographics estimation is in active development** — four iterations tested; M3c Var-Damp-IPF is current production default (Race MAE ~4.3pp); systematic bias overestimates White workers by ~10pp and underestimates Black workers by ~10pp in high-minority employers
12. **The `.env` file contains live credentials in plain text** including the database password, JWT secret, and Google API key

---

## FOCUS AREA 1: VISION AND MISSION ALIGNMENT
**"Are we building the right thing for the right purpose?"**
Priority: HIGH

This is the strategic layer. Before diving into bugs and data quality, step back and ask whether the platform is truly serving the people who would use it.

### 1A: What Organizers Actually Need
The platform is built to help organizers identify targets. But has anyone asked: what does a good organizing target decision actually look like from an organizer's perspective?

- [ ] **What decisions does an organizer need to make?** They're not just looking for "highest score." They're asking: Is this employer winnable? Is the timing right? Do we have relationships there? Does our union represent workers in this industry? What's the likely campaign length? How does this fit our current bandwidth? **Does the platform answer ANY of these questions? Which ones?**

- [ ] **What is the platform currently good at vs. what it's missing?** The platform is excellent at surfacing employers with enforcement histories. What it cannot tell an organizer: whether workers at this employer are already talking, whether the employer has a history of aggressive union busting, what the turnover rate is, or whether sister locals have tried here before. How big is this gap?

- [ ] **The "high score doesn't mean winnable" problem.** An employer can score a 9/10 because they have OSHA violations, wage theft cases, and federal contracts — and still be an impossible target because management has crushed three previous campaigns. Does the platform have any way to surface this? Should it?

- [ ] **Target audience specificity:** Is this platform meant for local union organizers making day-to-day decisions? National union research staff doing strategic planning? Both? The answer changes what features matter most. Assess who the real user is and whether the current design serves them.

### 1B: The Research Questions We Should Be Asking
The platform has a lot of data. But are we asking the right questions of it?

- [ ] **Current scoring questions vs. unexplored questions.** The current score asks: "How much enforcement history does this employer have?" But we could also ask: "Which employers have the best ratio of worker-to-management power?" or "Which employers are in industries where organizing momentum is accelerating?" or "Which employers have high turnover, suggesting worker dissatisfaction?" List 5 research questions the platform has the data to answer but currently doesn't.

- [ ] **The momentum question.** Organizing follows momentum — wins create more wins in a geography and industry. Does the platform track this? The NLRB factor partially does (nearby wins), but it's a point-in-time snapshot. Could we build a "momentum trajectory" — an employer whose score has been improving over 12 months, suggesting conditions are developing?

- [ ] **The "comparable successful campaigns" question.** We have NLRB election outcomes. We have employer profiles. Could the platform answer: "Find me employers that look like the ones where we won in the last 2 years"? Is the comparables system (Gower distance) capable of this? Is it being used for this purpose?

- [ ] **The industry pipeline question.** If a union wins at McDonald's in Cincinnati, what are the most similar employers in the same metro? The platform could answer this instantly with existing data. Is this a feature? Should it be?

### 1C: What Success Looks Like in 12 Months
- [ ] **What does "done" look like?** The platform has been in development for a long time. What would it look like if it were genuinely ready for regular use by organizers? Define 3-5 concrete milestones that would constitute "usable."

- [ ] **What's the riskiest assumption we're making?** Every platform is built on assumptions. Identify the single biggest assumption baked into the current scoring model that has not been empirically validated. What would it mean for the project if that assumption is wrong?

---

## FOCUS AREA 2: DATA QUALITY AND COVERAGE
**"Is the data we're working with accurate and complete enough to trust?"**
Priority: HIGHEST

Data quality is the foundation. If the data is wrong or missing, every score, every recommendation, every research finding is built on sand.

### 2A: Coverage Reality Check
For each of the 8 scoring factors, run the actual query and report:
- What percentage of 146,863 union employers have data for this factor?
- Is that coverage distributed evenly across industries and states, or is it concentrated in specific sectors?
- If coverage is low, WHY is it low — is data available but not matched, or does the government source genuinely not cover many employers?

```sql
-- Template: replace 'score_osha' with each factor
SELECT 
  COUNT(*) as total,
  COUNT(score_osha) as has_osha_score,
  ROUND(COUNT(score_osha)::numeric / COUNT(*) * 100, 1) as pct_covered
FROM mv_unified_scorecard;
```

Report coverage for all 8 factors: score_osha, score_nlrb, score_whd, score_contracts, score_union_proximity, score_industry_growth, score_size, score_financial.

- [ ] **The "one-factor employer" problem:** How many employers in the union scorecard have data for ONLY one factor? What does a score mean when it's based on a single signal? Should there be a minimum data threshold?

- [ ] **Bias check:** Run coverage by 2-digit NAICS code. Are there entire industries that are essentially invisible to the scoring system? Run coverage by state. Which states are data deserts?

- [ ] **Data freshness:** What is the most recent record date from each source (OSHA, WHD, NLRB, SAM, SEC, IRS)? If OSHA data is from 2023, the 5-year decay means scores are already lower than they would be with current data. Report exact dates for all sources.

### 2B: The Contracts Pipeline Failure
The government contracts factor shows 0% coverage in the union scorecard despite 9,305 matched records existing in the database.

- [ ] **Confirm the break:** Run `SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_contracts IS NOT NULL` — should return 0 if broken.
- [ ] **Trace the pipeline:** Walk through `scripts/scoring/build_unified_scorecard.py` and find exactly where the contracts data fails to flow into the scorecard. Is it a JOIN condition? A missing script run? A crosswalk rebuild that wiped the data?
- [ ] **Quantify the impact:** If contracts data were flowing correctly, approximately how many employers would get a non-null contracts score? How much would this change the ranking of the top 500 employers?

### 2C: Demographics Estimation Quality
The workforce demographics estimation system (V1–V4) represents significant investment. Assess its current state.

- [ ] **Production deployment status:** Is M3c Var-Damp-IPF (the current recommended default) actually deployed in `api/routers/profile.py`? Or is the old M1 60/40 blend still live? Run a test on 5 employers and confirm which method is being called.
- [ ] **The systematic bias:** All methods overestimate White workers (~10pp) and underestimate Black workers (~10pp) for high-minority employers. Has the calibration offset system (per-industry bias correction) been built yet, or is it still planned? What is its current status?
- [ ] **The M8 Adaptive Router:** V4 introduced an adaptive routing system that selects the best method per employer type. Has this been implemented? Is it tested? Is it in production or still in the research pipeline?
- [ ] **UI display:** When a user looks at an employer profile that shows demographic estimates, can they tell whether they're looking at: (a) real EEO-1 data, (b) a high-confidence estimate, or (c) a rough guess with high uncertainty? If not, this is a critical user trust problem.
- [ ] **The unused EEO-1 ground truth:** 16,798 employers have actual EEO-1 data in the database. Are their profiles showing the real data or the estimate? Running an estimate for an employer when you have the actual answer is a fundamental quality failure.

### 2D: The F-7 Orphan Problem
50.4% of F-7 notices (union-employer organizing relationships) cannot be linked to any employer in the database.

- [ ] **Current orphan count:** Run `SELECT COUNT(*) FROM f7_employers WHERE employer_id IS NULL OR employer_id NOT IN (SELECT id FROM f7_employers_deduped)` — or equivalent query — to get the exact orphan count.
- [ ] **Why are they orphaned?** Pick 20 random orphaned F-7 notices and manually look at them. What do they have in common? Are they: (a) employers with unusual name formats, (b) very small employers that don't appear in other government databases, (c) employers that only appear in one source, or (d) data entry problems in the F-7 itself?
- [ ] **The fix potential:** Based on your sample of 20, what proportion could potentially be matched with better fuzzy matching vs. requiring manual intervention vs. genuinely unmatchable?

---

## FOCUS AREA 3: SCORING SYSTEM INTEGRITY
**"Does the score actually mean what we think it means?"**
Priority: HIGHEST

### 3A: Specification vs. Reality
The scoring specification (`SCORING_SPECIFICATION.md`) defines 8 factors with specific weights and formulas. Does the code actually implement what the spec says?

- [ ] **Weight verification:** The spec says NLRB Activity has 3x weight. OSHA, WHD, Financial, Contracts each have 1x weight. Open `scripts/scoring/build_unified_scorecard.py` and find the actual weight values in the code. Do they match the spec?
- [ ] **Signal-strength scoring:** The spec says "missing data = skip, not zero." Find the exact code that implements this. Does it correctly skip NULL factors, or does it include them as 0 in any path?
- [ ] **The NLRB split:** The spec says NLRB is 70% nearby momentum, 30% own history. Verify this split in the SQL.
- [ ] **Time decay:** The spec says OSHA/WHD have 5-year half-life, NLRB has 7-year half-life. Find the actual decay formulas in the code. Run a sanity check: for a violation that occurred exactly 5 years ago, what decay factor does the code produce? It should be approximately 0.5 (half weight).
- [ ] **The Stability pillar default:** The spec says missing data means the factor is skipped. But previous audits found the Stability pillar defaults to 5.0 for ~95% of employers. Is this still true? If so, it directly contradicts the signal-strength spec. Show the exact code line causing this.

### 3B: Score Validation
- [ ] **Top 20 employers by score:** List the top 20 employers in the union scorecard with their scores, factor breakdown, and industry. Do these look like legitimate high-priority organizing targets? Or are any clearly wrong (known already-unionized, very small employers, government entities)?
- [ ] **Score distribution:** What does the full score distribution look like? Is it normally distributed, skewed, or clustered? If 80% of employers score between 4.0 and 6.0, the score is not differentiating well.
- [ ] **Factor correlation:** Are any two scoring factors highly correlated with each other? If OSHA violations and WHD violations tend to occur at the same employers, combining them may effectively double-count the same underlying fact (bad employer behavior). Should they be partially collapsed?
- [ ] **The NULL GREATEST() bug:** Previous audits found a PostgreSQL behavior where `GREATEST(NULL, 5, 3)` returns NULL instead of 5. Has this been fixed? Check for any use of `GREATEST()` in the scoring pipeline that could silently produce NULL scores.

### 3C: The Size and Proximity Factors
These were found to have zero predictive power in Round 2 scoring validation.

- [ ] **Current status:** Are size and proximity still in the scoring model? What weights do they have?
- [ ] **If still present, at what cost?** Run a comparison: for the top 100 employers by score, how many would rank differently if size and proximity were removed entirely? This quantifies the distortion these factors are causing.
- [ ] **Recommendation:** If these factors have been confirmed to have zero predictive power, what is the argument for keeping them? Is there any case for retaining them?

---

## FOCUS AREA 4: THE MATCHING SYSTEM
**"Are the right records being connected to the right employers?"**
Priority: HIGH

Matching is the "plumbing" of the platform. When it fails, employers get wrong scores. When it over-matches, violations from one company get attached to a completely different company.

### 4A: False Positive Assessment
- [ ] **The Nex/Cassens problem:** Confirm this specific false positive is still present: search for "Nex Transport" in the unified match log — does it still incorrectly link to Cassens Transport? Run: `SELECT * FROM unified_match_log WHERE normalized_name ILIKE '%nex transport%'`
- [ ] **False positive rate by confidence band:** The matching system assigns confidence bands (HIGH, MEDIUM, LOW). Previous audits found false positives across all bands. Run a sample of 20 matches from each band and manually verify them. Report the false positive rate per band based on your sample.
- [ ] **Impact of false positives on scores:** Identify the top 10 employers most likely affected by false positive matches (high-confidence matches that may actually be wrong). What happens to their score if those false matches are removed?

### 4B: Matching Coverage Gaps
- [ ] **Source-by-source match rates:** For each government data source (OSHA, WHD, NLRB, SAM, SEC, IRS 990), what percentage of records are successfully matched to an employer in f7_employers_deduped? Run this query for each source and report the match rate.
- [ ] **The 0.65 name similarity floor:** The matching pipeline uses a minimum name similarity score of 0.65. What happens at 0.64? Are there legitimate matches just below the threshold? Run a sample of rejected matches (similarity 0.60-0.64) and manually assess 10 of them.
- [ ] **Unmatched NLRB ULP charges:** NLRB unfair labor practice charges are some of the strongest organizing signals. What percentage of NLRB cases are currently unmatched to any employer in the platform? If a large percentage of ULP charges are floating unconnected, the NLRB score is systematically underestimating employer behavior.

---

## FOCUS AREA 5: THE FRONTEND AND USER EXPERIENCE
**"Can an organizer actually use this effectively?"**
Priority: HIGH

A platform with perfect data and a broken interface is useless. Assess the frontend from the perspective of someone who would actually use it to make organizing decisions.

### 5A: The "No Data" vs. "No Violations" Problem
This is confirmed as a critical bug. When an employer has no OSHA data matched to them, their safety section disappears from the profile page — indistinguishable from an employer with a genuinely clean record.

- [ ] **Confirm the bug is still present:** Load an employer profile where OSHA data is known to be missing. Does the safety section disappear, or does it show an amber warning?
- [ ] **Which sections are affected?** Check: OSHA section, NLRB section, WHD section, Financial section. Which ones silently disappear vs. show a warning?
- [ ] **User trust impact:** Write a plain-English description of how this bug could cause an organizer to make a worse decision than if they had no platform at all.

### 5B: Information Architecture Quality
- [ ] **The employer profile page:** When a user clicks into an employer, what information appears above the fold (visible without scrolling)? Is it the most useful information for making an organizing decision? Or is it metadata (database IDs, match confidence scores) that only matters to a developer?
- [ ] **Score explanation:** Does the platform explain WHY an employer has the score it has? An employer with score 7.8 should show: "This employer scores high because they have 14 OSHA violations (above industry average), 3 wage theft cases, and $2.4M in federal contracts." Does this explanation exist? Is it clear and useful?
- [ ] **Search and filter quality:** What filters are available when searching employers? List them. Then think about what an organizer would actually want to filter by: industry, state, score range, specific violation types, employer size, whether they're already a known target. How many of those are available?
- [ ] **The export problem:** Can an organizer export a list of their top 50 targets as a spreadsheet or PDF to share with colleagues? If not, this is a major workflow gap — researchers work in teams and need to share findings.

### 5C: React Migration Status
The frontend is in the middle of a migration from a legacy HTML file (`organizer_v5.html`) to a React application.

- [ ] **What's been migrated?** List the major UI components/pages and note which are in the new React app vs. still in the legacy HTML file.
- [ ] **What's the current state of each key page?** Check: main search/scorecard list, employer detail/profile, union explorer, research tool interface. For each: is it in React? Does it load correctly? Does it show real data from the API?
- [ ] **Any regressions?** Are there features that worked in the legacy HTML that don't work yet in the React version?

---

## FOCUS AREA 6: THE RESEARCH TOOL
**"Does the on-demand deep dive actually produce useful, accurate results?"**
Priority: HIGH

The research tool is meant to let users trigger a deep investigation of a specific employer — pulling together all available data, running web searches, and producing a structured report. This is a core differentiating feature.

### 6A: The JOIN Bug
Previous audits confirmed the research tool has a JOIN bug producing incorrect results.

- [ ] **Locate the bug:** Open `api/routers/research.py` (or wherever the research endpoint lives). Find the JOIN operation that connects employer records to comparables or to another table. Describe exactly what it's doing wrong.
- [ ] **Demonstrate the problem:** Find an employer where the bug causes wrong output. Show: what the tool returns vs. what it should return.
- [ ] **The fix:** Write the correct SQL or code to fix this. Estimate how long the fix would take.

### 6B: Research Tool Accuracy Benchmark
- [ ] **Pick 5 well-known employers** (ones where you can verify information from public sources). Run the research tool on each. For each output, check: (a) Are the OSHA statistics correct? (b) Are the NLRB cases real and attributed to this employer? (c) Are the comparable employers actually similar? (d) Is the overall assessment reasonable?
- [ ] **Report the accuracy rate** based on your 5-employer test. This is the first empirical benchmark of the research tool's real-world accuracy.
- [ ] **The quality gate threshold:** The system has a research quality gate. What threshold is set in the code? Does the documentation match? Previous audits found a discrepancy (code says < 7.0, docs say < 3.0). Is this fixed?

### 6C: Research Tool Capabilities
- [ ] **What does it actually do?** Trace the full execution path of a research request. Does it: query the internal database only? Run external web searches? Call the Bright Data scraper? Use Indeed MCP? List every data source the tool actually queries.
- [ ] **What does the output look like?** Describe the structure of a research report. Is it useful for making an organizing decision?
- [ ] **Speed:** How long does a complete research run take? Is it fast enough to be usable interactively? The previous audit estimated 45-90 seconds — verify this with actual timing.

---

## FOCUS AREA 7: LONG-TERM PROJECTS — STATUS AND PATHWAY
**"Are the bigger initiatives progressing? Are they designed correctly?"**
Priority: HIGH

The platform has several multi-month initiatives underway. This focus area assesses each one.

### 7A: The CBA Database (Collective Bargaining Agreements)
This initiative aims to build a searchable database of union contracts with extracted provisions.

- [ ] **Current state:** How many contracts are currently loaded? The last audit found 4. Has this grown?
- [ ] **Extraction quality:** The rule-based provision extractor survived 69 provisions after false-positive cleanup from one contract (32BJ). What is the precision of this extractor — how many extracted provisions are genuinely meaningful vs. noise?
- [ ] **The scale question:** Going from 4 contracts to 5,000 contracts requires a sourcing strategy. Where will the contracts come from? PDF collections? Union websites? FMCS? Is there a plan for this?
- [ ] **Usefulness assessment:** What specific questions could an organizer answer with a CBA database that they can't answer now? Is this the right priority given everything else that's incomplete?

### 7B: The Union Web Scraper
The AFSCME prototype scraped 295 profiles, 160 employers, 73 matched. This proves the concept but the pipeline hasn't been expanded.

- [ ] **Current state:** Is the AFSCME scraper still running? When was it last run? What's the data quality like?
- [ ] **Expansion plan:** The goal is to expand to SEIU, Teamsters, UFCW, IBEW. What is blocking this? Is it engineering time, scraper architecture, or something else?
- [ ] **Architecture question:** The scraper was built with a multi-tier architecture (sitemap → WordPress API → HTML parsing → Gemini fallback). Is this architecture holding up in practice? What tier is most used? What are the failure modes?

### 7C: The Demographics Pipeline
Four iterations of workforce demographics estimation have been developed. The pipeline is now fairly sophisticated.

- [ ] **V4 completion:** The V4 iteration has several pending components: `methodologies_v4.py`, `cached_loaders_v4.py`, `run_comparison_all_v4.py`, `generate_report_v4.py`. Which of these are complete? Which are still pending?
- [ ] **Production deployment gap:** There's a significant gap between the research work (which methods are best) and production deployment (what the API actually returns to users). Is the current API serving M3c? M1 baseline? Something else? This gap needs closing.
- [ ] **The calibration offset system:** Industry-specific bias correction was identified as the single highest-leverage improvement. Has it been built? If not, what's the plan and timeline?
- [ ] **User-facing value:** Workforce demographics estimates are interesting research. But when an organizer looks at an employer profile, does demographic information actually help them make better decisions? Is this the right thing to show prominently? Or would other information (turnover rates, recent layoffs, job posting patterns) be more actionable?

### 7D: Public Sector Data
Public sector workers represent roughly half of all union members, but the platform's data comes almost entirely from federal databases covering private sector.

- [ ] **Current public sector coverage:** How many public sector employers are currently in the platform? How many public sector union-employer relationships are trackable? What percentage of total organized workers does the platform cover in the public sector?
- [ ] **The PERB research from Round 3:** Gemini researched State PERB data availability. Ohio and Minnesota were identified as the most accessible sources. Has any action been taken on this? Is there a plan?
- [ ] **The FLRA gap:** Federal workers (covered by FLRA, not NLRB) represent a significant unionized population. Is FLRA data in the database? Is it connected to the scoring system?
- [ ] **Priority question:** Given everything else on the roadmap, should public sector expansion be accelerated or deferred? What's the argument for each?

### 7E: The O*NET Integration
O*NET (the government's occupational data system) was identified as valuable for workforce composition estimation. Eight key files were identified.

- [ ] **Current status:** Has the O*NET ETL script (`scripts/etl/load_onet_data.py`) been run? Is the data loaded?
- [ ] **Is it connected to anything?** The data was loaded — but is it actually feeding into any scoring, estimation, or research output? Or is it sitting in a table that nothing queries?
- [ ] **The value question:** What specifically would O*NET add to the platform's outputs that isn't already provided by BLS OEWS data?

---

## FOCUS AREA 8: INFRASTRUCTURE AND OPERATIONS
**"Can this platform be reliably run, maintained, and deployed?"**
Priority: MEDIUM

### 8A: Security Status
- [ ] **Credential rotation (Task 0-1):** The database password, JWT secret, and Google API key were flagged as exposed. Has any rotation happened? Check the `.env` file for the database password — previous audits found it was `Juniordog33!`. Is this still the case?
- [ ] **JWT fallback default:** The system falls back to `dev-only-change-me` if `.env` is missing. Has this been fixed to hard-fail instead of falling back?
- [ ] **Auth on write endpoints:** Three write endpoints (`POST /api/employers/flags`, `DELETE /api/employers/flags/{id}`, `POST /api/employers/refresh-search`) were unprotected. Are they now protected?

### 8B: Test Suite Health
- [ ] **Current test count and pass rate:** Run `py -m pytest tests/ -q` and report: total tests, passing, failing. What are the failing tests? Are they known pre-existing failures or new regressions?
- [ ] **Coverage gaps:** What major functionality has NO tests? The research tool? The demographics API? The union explorer? Untested code is code that can break silently.

### 8C: The Legacy Cleanup
- [ ] **The `splink_match_results` table:** This 1.6 GB table from old matching experiments is no longer used. Has it been dropped or archived? If not, it's pure wasted storage.
- [ ] **Empty tables (5 confirmed):** `employer_ein_crosswalk`, `sic_naics_xwalk`, `union_affiliation_naics`, `union_employer_history`, `vr_employer_match_staging`, `vr_union_match_staging` — do these still exist empty? Should they be dropped or populated?
- [ ] **The `f7_employers_deduped` primary key gap:** This core employer table has no primary key, meaning duplicate records could accumulate silently. Has this been fixed?

### 8D: Deployment Reality
- [ ] **Is there a staging environment?** Or is all development happening directly on the production database?
- [ ] **Data refresh cadence:** How often is government data refreshed? Who triggers it? Is it manual or automated?
- [ ] **Backup verification:** Has a backup restore ever been tested? If the database was accidentally dropped, how long would recovery take?

---

## FOCUS AREA 9: DATA SOURCE UTILIZATION
**"Are we getting full value from all the data we've collected?"**
Priority: MEDIUM

The platform has loaded a lot of data. Some of it is richly used; some is sitting idle.

### 9A: Underutilized Data Audit
- [ ] **EPI Historical Density Data:** 1.4 million rows covering 51 years of state/industry/demographic union density data (1973-2024). Current use: only state-level density. What additional signals could this data provide? Are there specific queries that would extract value from the historical dimension?
- [ ] **GLEIF Ownership Links (498,963 rows):** This data shows corporate parent-child relationships (which companies own which other companies). Is it being used to identify when a scored employer is a subsidiary of a larger corporate parent? If Walmart violates wage laws through a subsidiary, does the parent's record get surfaced?
- [ ] **QCEW Annual Data (1.9M rows):** Quarterly Census of Employment and Wages — covers employment and wages by industry and county. What is this data currently being used for? What could it be used for that it isn't?
- [ ] **IRS Form 990 (1M+ records):** This contains financial information for nonprofits. What's the current match rate against F-7 employers? Previous audits showed this was a weak link.

### 9B: The Compound Signal Problem
- [ ] **OSHA + WHD overlap:** How many employers appear in BOTH the OSHA database (safety violations) AND the WHD database (wage theft cases)? This overlap is arguably a super-strong organizing signal — employers that are both unsafe AND steal wages. Is this compound signal calculated anywhere?
- [ ] **Federal contractor + violations overlap:** How many employers are BOTH federal contractors AND have enforcement histories? These employers are particularly vulnerable to pressure because their government contracts can be conditioned on labor compliance. Is this combination surfaced anywhere in the platform?
- [ ] **NLRB repeat activity:** How many employers have had NLRB activity (elections or ULP charges) in MULTIPLE distinct time periods? A shop that's been active twice in 10 years is very different from one with a single organizing attempt. Is this pattern detected?

### 9C: New Data Sources Not Yet Integrated
- [ ] **Form 5500 (employee benefit plan data):** Was identified as valuable for employer financial health and employee count verification. Current status: loaded or not? Connected to scoring or not?
- [ ] **LODES commuting data:** Was identified as superior to static county boundaries for demographics estimation (shows who actually commutes to a workplace vs. who lives nearby). Current status?
- [ ] **People Data Labs company dataset:** Was mentioned as an active data source. What is its current status and what does it contribute?
- [ ] **Bright Data Web MCP (5,000 req/month free tier):** Was this connected? Is it being used in the research tool? What has it produced?

---

## FOCUS AREA 10: PATHWAY CLARITY
**"Is the project on a clear path to something usable and valuable?"**
Priority: HIGH

This is the strategic synthesis question. After looking at everything above, assess:

### 10A: The Roadmap Reality Check
- [ ] **Is `COMPLETE_PROJECT_ROADMAP_2026_03.md` still accurate?** It has 58 tasks across Phases 0-8. How many Phase 0 (emergency) tasks are actually done? How many Phase 1 (foundational) tasks are done? What percentage of the roadmap has been completed since it was written?
- [ ] **Task sequencing:** Are there tasks in Phases 2-4 that are blocked because Phase 0-1 work wasn't done? Name them specifically.
- [ ] **The accumulating technical debt:** Each time a new feature is added without fixing underlying problems, technical debt accumulates. List the top 3 pieces of technical debt that, if left unaddressed, will make future development significantly harder or more error-prone.

### 10B: Prioritization Logic
- [ ] **Given limited time, what are the 5 most impactful things to work on?** Not the safest or most interesting — the most impactful for the platform's ability to actually help organizers. Rank them and justify each.
- [ ] **What should be paused or deprioritized?** Not everything can be worked on simultaneously. What is the least impactful active initiative that is consuming attention it shouldn't? Why?
- [ ] **The "minimum viable useful product" question:** If we stripped the platform down to only the features that are genuinely working and reliable, what would remain? Is that stripped-down version actually useful to an organizer?

### 10C: Build vs. Use
- [ ] **Build time vs. value time:** The platform has been built for an extended period. At what point does continued building need to give way to actual use — getting it in front of real organizers who can provide feedback? What is the current barrier to real use?
- [ ] **Feedback loops:** Is there any mechanism for users (organizers) to flag when the platform shows them wrong or misleading information? If not, how would we know when the platform is giving bad guidance?
- [ ] **The validation gap:** Scores are calibrated against enforcement history (do high-scoring employers have violations?). But organizing success is what actually matters. Is there any plan to validate scores against actual organizing outcomes (campaign wins and losses)?

---

## OUTPUT FORMAT

Produce your report as a single markdown document. Save it as `ROUND_5_AUDIT_REPORT_[YOUR_AI_NAME].md` in the project root.

**Structure:**

1. **Executive Summary** (25 lines max)
   - Overall platform health assessment (1 paragraph, plain English)
   - The single most important thing to fix (and why)
   - The single most promising opportunity you found
   - Top 5 actions, in priority order

2. **Focus Area 1: Vision and Mission** — Strategic findings, mission gaps, unexplored research questions

3. **Focus Area 2: Data Quality** — Coverage numbers (actual queries), freshness, contracts pipeline status, demographics deployment status, orphan count

4. **Focus Area 3: Scoring Integrity** — Spec vs. code comparison, distribution analysis, NULL handling confirmation

5. **Focus Area 4: Matching Quality** — False positive rate by band, orphan analysis, coverage gaps

6. **Focus Area 5: Frontend and UX** — No-data bug status, information architecture assessment, React migration status, export capability

7. **Focus Area 6: Research Tool** — JOIN bug location and fix, 5-employer accuracy benchmark, capability map

8. **Focus Area 7: Long-Term Projects** — Status and pathway for CBA database, web scraper, demographics pipeline, public sector, O*NET

9. **Focus Area 8: Infrastructure** — Security status (are credentials still exposed?), test suite health, legacy cleanup status

10. **Focus Area 9: Data Utilization** — Underused data audit, compound signals, new source integration status

11. **Focus Area 10: Pathway Clarity** — Roadmap completion percentage, top 5 priorities, what to deprioritize, minimum viable product definition

12. **Master Recommendation List** — Every recommendation numbered 1–40, sorted by: PRIORITY (1-5, where 1=most critical) × EFFORT (hours/days/weeks). Each recommendation must include:
    - Plain-English description of what to do
    - Why it matters (what breaks or improves)
    - Estimated effort
    - Which skills are needed (SQL, Python, React, manual research, decision-making)
    - How to verify it worked
    - Dependencies (what must happen first)

---

## FINAL ANSWER QUALITY REMINDER

Every answer in this audit must be specific enough to create a real task from. Generic answers are useless.

**Examples of what NOT to write:**
- "Data coverage should be improved." (How? By how much? Which sources?)
- "The frontend needs work." (What specifically? What does it currently do wrong?)
- "This should be investigated further." (By whom? How? What would constitute an answer?)

**Examples of what TO write:**
- "The contracts scoring factor is completely dead — 0 of 146,863 employers have a contracts score — because `scripts/scoring/build_unified_scorecard.py` references `f7_federal_scores.is_federal_contractor` but this field is NULL for all rows after the crosswalk was rebuilt without re-running `scripts/etl/_match_usaspending.py`. Fix: run that ETL script, then rebuild the scorecard. Estimated time: 2-3 hours. Impact: approximately 9,305 employers would receive contracts scores, changing the ranking of an estimated 800-1,000 top employers."
- "The React migration has completed 3 of 5 major pages: the scorecard list, the union explorer, and the search interface. The employer detail profile and the research tool interface still load from the legacy `organizer_v5.html`. The legacy employer detail page is missing the match confidence indicators that were added to the React version."

The person reading your report has limited technical background. Write for them.
