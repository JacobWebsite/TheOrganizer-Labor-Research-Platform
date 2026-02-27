# Three-Agent Platform Audit — Comprehensive Prompt Pack (v2)
## For: New Roadmap Development (Post Feb 19 Roadmap)
### Created: February 25, 2026

---

## HOW TO USE THIS DOCUMENT

This document contains **three separate audit prompts** — one each for Claude Code, Codex, and Gemini. Each prompt plays to that tool's strengths, but they all share a **Shared Overlap Zone** of questions every agent must answer. The overlap zone is how you compare results and catch disagreements.

**The workflow:**
1. Give each agent its specific prompt (Sections 2, 3, or 4) along with the shared context files
2. Each agent also answers the Shared Overlap Zone questions (Section 1)
3. After all three finish, compare their Overlap Zone answers side by side using the Synthesis Guide (Section 5)
4. Use the combined findings to build the new roadmap

**Files to give every agent:**
- `PROJECT_STATE.md` (the most complete current-state document)
- `CLAUDE.md` (database schema and technical reference)
- `SCORING_SPECIFICATION.md` (how scoring is supposed to work)
- `UNIFIED_ROADMAP_2026_02_19.md` (current roadmap)

**Additional files by agent:**
- Claude Code: Also give `FOUR_AUDIT_SYNTHESIS_v3.md` (previous audit findings to verify)
- Codex: Also give `REACT_IMPLEMENTATION_PLAN.md` and `PLATFORM_REDESIGN_ADDENDUM.md`
- Gemini: Also give `FOUR_AUDIT_SYNTHESIS_v3.md`, `DOCUMENT_RECONCILIATION_ANALYSIS.md`, and `RESEARCH_AGENT_IMPLEMENTATION_PLAN.md`

---

## WHAT CHANGED SINCE THE LAST AUDIT (Feb 19, 2026)

This is critical context. The last three-AI audit was on Feb 18-19, 2026. Since then, significant work has been done. Every agent needs to know what to verify:

1. **Research Agent Built** — A system that automatically researches companies was built and has run 96 times. Average quality score 7.93/10. Uses Crawl4AI for web scraping plus existing database lookups.

2. **CorpWatch SEC EDGAR Import** — 14.7 million rows of corporate ownership data imported into 7 new tables. This is a different SEC data source than the existing `sec_companies` table.

3. **Data Enrichment** — Geocoding coverage went from 73.8% to 83.3%. NAICS industry codes were inferred for employers that didn't have them. This affects multiple scoring factors.

4. **NLRB Participant Cleanup** — 492K junk rows were removed from `nlrb_participants`. The previous audit found 83.6% of participant records had literal CSV header text instead of real data.

5. **React Frontend Completed** — All 6 planned phases built: Search, Employer Profile, Union Profile, Targets, Admin Panel, and Polish. 134 frontend tests passing. Uses React + Vite + Tailwind + shadcn/ui + Zustand + TanStack Query.

6. **Scoring Code Updates** — NLRB 7-year half-life decay implemented. Latest-election dominance logic added. BLS financial factor inversion fixed. `factors_available >= 3` requirement added for Priority tier.

7. **Splink Threshold Hardened** — Fuzzy matching minimum name similarity raised from 0.65 to 0.70.

8. **Docker Artifacts Added** — Dockerfile, docker-compose.yml, nginx.conf created (untested first drafts).

9. **Materialized Views Refreshed** — `mv_unified_scorecard`, `mv_employer_data_sources`, `mv_organizing_scorecard` all rebuilt as of Feb 19.

10. **Source Re-runs Partially Complete** — OSHA (4/4 batches done), SEC (5/5 done), BMF (done). **NOT complete:** 990 (batch 1 of 5 done, batches 2-5 not started), WHD (not started — failed with OOM), SAM (not started — failed with OOM).

**Key question for all agents:** The 990, WHD, and SAM source re-runs were never completed. These sources still have matches from the old (pre-Phase-B) matching pipeline. How much does this affect the current state of scoring and data quality?

---

# SECTION 1: SHARED OVERLAP ZONE (All Agents Must Answer)

Every agent must answer ALL of these questions. Label your answers clearly with the question number (OQ1, OQ2, etc.) so they can be compared side by side.

---

### OQ1: Priority Tier Spot Check (5 Employers)

Pick 5 employers that the system currently ranks as "Priority" (highest tier). For each one, report:
- Employer name, state, employer_id
- Final score (0-10)
- How many of the 8 scoring factors have data for this employer
- What factors are driving the high score
- Whether this looks like a real, organizable employer (not a placeholder, federal agency, shell company, or generic name)
- Whether an organizer would find this employer's profile useful and accurate

**Why:** The previous audit found placeholder records ("Employer Name"), 2-character names ("M1"), and federal agencies ("Pension Benefit Guaranty Corporation") ranked as Priority with perfect 10.0 scores. The `factors_available >= 3` fix was applied. We need to know if the problem is actually solved or just reduced.

---

### OQ2: Match Accuracy Spot Check (20 Matches)

Pick 20 employer matches from `unified_match_log` — specifically:
- 5 from OSHA matches
- 5 from NLRB matches
- 5 from WHD or SAM matches
- 5 from Splink fuzzy matches near the 0.70 threshold (name similarity 0.70-0.75)

For each match, report:
- Source name vs. matched employer name
- Match method and confidence score
- Name similarity score (if fuzzy)
- Your judgment: correct match, wrong match, or uncertain
- If wrong: what went wrong (geography overweight? generic name? different industry?)

**Why:** The previous audit found 10-40% false positive rates depending on the sample. The threshold was raised to 0.70 but 29,236 OSHA matches from before the fix (at 0.65-0.699) may still be in the system. We need a fresh measurement.

---

### OQ3: React Frontend ↔ API Contract (5 Features)

Check 5 different pages/features in the React frontend and verify:
- Does the frontend expect the same data shape that the API actually returns?
- Are there fields the frontend tries to display that don't exist in the API response?
- Are there API endpoints the frontend calls that don't exist or return errors?
- What happens when the API returns an error — does the user see a helpful message, a blank screen, or a crash?
- What happens when data is loading — is there a loading indicator?

Check these 5 specific features:
1. **Employer search** — Does the search page correctly call the API and display results?
2. **Employer profile** — Does the profile page load all data cards correctly?
3. **Scoring breakdown** — Does the score factor display show all 8 factors correctly?
4. **Union profile** — Do the new financial/membership cards load?
5. **Targets page** — Do the tier cards show correct counts?

**Why:** The frontend was built in 6 rapid phases. The API had multiple changes during the same period. Mismatches between frontend expectations and API reality are almost guaranteed.

---

### OQ4: Data Freshness and View Staleness

Answer these specific questions:
- When was `mv_unified_scorecard` last refreshed? (Check `score_versions` table or MV metadata)
- When was `mv_employer_data_sources` last refreshed?
- When was `mv_employer_search` last refreshed?
- Do the scores reflect the February 19 code changes (NLRB decay, financial fix, factors >= 3)?
- What does the `data_source_freshness` table show? Are the dates accurate or are they still broken (13/19 NULL, NY showing year 2122)?
- Have the materialized views been refreshed since the React frontend was built?
- Are there any views or materialized views that reference tables or columns that no longer exist?

**Why:** The previous audit found blocking MV refreshes, stale views, and a broken freshness table. Code changes don't take effect until views are rebuilt. If the MV hasn't been refreshed since the code changes, users are seeing old data.

---

### OQ5: Incomplete Source Re-runs — Impact Assessment

The matching pipeline was upgraded (Phase B), but only OSHA, SEC, and BMF were re-run with the new pipeline. 990, WHD, and SAM still have old matches. Assess:
- How many active matches exist for 990, WHD, and SAM in `unified_match_log`?
- What match methods were used? (Are they old pre-Phase-B methods like `NAME_STATE` vs new methods like `NAME_STATE_EXACT`?)
- Are there matches below the 0.70 name similarity threshold that should have been filtered out?
- How much does this affect the scores in `mv_unified_scorecard`?
- Is there a way to estimate how many employers have wrong scores because of stale matches?

**Why:** Running only half the sources through the improved matching pipeline means the platform has a split-quality problem. Some employer profiles show data matched with the new, better process, while others show data matched with the old, error-prone process. This is invisible to users.

---

### OQ6: The Scoring Factors — Current State (All 8)

For each of the 8 scoring factors, report:
1. **OSHA Safety (1x):** What percentage of employers have this factor? Is the score calculation correct (industry-normalized, 5-year half-life, severity bonus)?
2. **NLRB Activity (3x):** What percentage have this? Does the code implement 70/30 nearby/own split with 7-year half-life? Does the proximity calculation use the cleaned participant data or still the junk data?
3. **WHD Wage Theft (1x):** What percentage have this? Are the tiers (0/5/7/10) implemented correctly?
4. **Gov Contracts (2x):** What percentage have this? Is there now tiered scoring (0/4/6/7/8/10) or does everyone still get 4.00?
5. **Union Density (1x):** What percentage have this? Is it state × industry intersection?
6. **Employer Size (3x):** What percentage have this? Is the sweet-spot curve implemented?
7. **Statistical Similarity (2x):** What percentage have this? Is it still 186/146,863 (0.1%), or has coverage improved?
8. **Industry Growth (2x):** What percentage have this? Is `score_financial` still a copy of `score_industry_growth`, or has it been separated?

Also answer:
- What is the overall score distribution? (How many employers at each tier: Priority, Strong, Promising, Moderate, Low?)
- What is the average number of factors available per employer?
- What percentage of employers have only 1-2 factors?

**Why:** The previous audit found that only 2-3 of 8 factors were fully working. Multiple code fixes were applied. We need a complete status check on all 8 factors to know what's actually functioning.

---

### OQ7: Test Suite Reality Check

- How many test files exist? List them.
- Run the full test suite. How many pass? How many fail? What fails and why?
- Are there tests that verify actual score VALUES (not just that the code doesn't crash)?
- Are there tests that verify match ACCURACY (not just that matches are created)?
- Are there tests that check the API returns correct data (not just status 200)?
- Are there frontend tests? What do they test?
- What's the most important thing that has NO test coverage?

**Why:** The test count has changed with every session (375, 439, 441, 456, 457). We need a definitive current count and an honest assessment of what the tests actually verify.

---

### OQ8: Database Cleanup Opportunity

- How many tables exist? How many have zero rows?
- How many tables appear to be abandoned experiments or duplicates?
- Are there tables from the CorpWatch import (the 14.7M rows) that aren't connected to anything?
- How much disk space could be reclaimed by dropping unused tables?
- Is the 12 GB GLEIF dump still taking up space? Could it be archived?
- Are there any orphaned views that reference tables or columns that no longer exist?
- How many of the 42 industry-specific views identified in the previous audit are still present?

**Why:** The database has grown to 174+ tables across many development sessions. The previous audit found 42 orphaned industry views, 6 empty tables, and 12 GB of archivable GLEIF data. Cleanup now prevents problems during deployment.

---

### OQ9: What's the Single Biggest Problem?

In your judgment, what is the single most important thing that needs to be fixed before this platform can be shown to real organizers? Explain:
- What the problem is, in plain language
- Who it affects and how
- How confident you are this is the biggest issue
- How much work it would take to fix (rough estimate)
- What happens if it's NOT fixed and someone uses the platform anyway

**Why:** Each agent sees the platform from a different angle. Comparing "biggest problem" answers reveals whether there's consensus or whether different perspectives surface different priorities.

---

### OQ10: Previous Audit Follow-Up

The previous audit (FOUR_AUDIT_SYNTHESIS_v3.md) identified 20 investigation questions and 11 decisions. For each of these, check whether it's been addressed:

**Investigation Questions (answer as many as you can):**
1. Was the name similarity floor tested at 0.75 and 0.85?
2. Was the 14.5M membership number validated state-by-state?
3. Were the 75,043 orphaned superseded matches investigated?
4. Were the 46,627 UML records pointing to missing F7 targets investigated?
5. Was NAICS inference done for the 22,183 employers lacking codes?
6. Was the employer grouping problem (over-merge of 249 construction companies, etc.) addressed?
7. Was the comparables→similarity pipeline investigated?
8. Was the NLRB "within 25 miles" data source verified (junk participant data or clean)?
9. Were junk/placeholder records cleaned from the scoring universe?
10. Was the geocoding gap investigated by tier?

**Decisions (check if decided):**
1. Name similarity floor — still at 0.70, or changed?
2. What does "Priority" mean — structural only, or requires recent activity?
3. Minimum factor requirements — still 3 for Priority only, or extended?
4. Stale OSHA matches — were the 29,236 sub-threshold matches dealt with?
5. score_similarity — removed from formula, or still included at 2x weight?
6. Legacy frontend — archived, or still being served?
7. User data storage — still localStorage, or moved to server-side?

**Why:** The previous audit created a comprehensive action list. If none of it was addressed, we're in the same position. If some was addressed, we need to know what's left.

---

# SECTION 2: CLAUDE CODE PROMPT (Deep Technical Investigator)

**Give this prompt to Claude Code. It needs direct database access and the ability to run SQL queries.**

---

## Your Role

You are the deep technical investigator. You have direct access to the PostgreSQL database (`olms_multiyear`, localhost:5432, user `postgres`). Your superpower is that you can actually check the data — not just read documentation claims, but run queries and verify them.

**Critical rules:**
1. **Show SQL and results for every claim.** Don't say "the scores look right." Show `SELECT employer_name, overall_score, factors_available FROM mv_unified_scorecard WHERE tier = 'Priority' ORDER BY overall_score DESC LIMIT 10;` and the results.
2. **Say "I didn't check this" or "I'm not sure" rather than guess.** An honest gap is infinitely better than a confident wrong answer.
3. **Compare actual values to documented values.** If PROJECT_STATE.md says "97,142 OSHA matches" but the database says something different, that's a finding.
4. **Check for side effects.** When something was "fixed," check whether the fix broke anything else.

---

## Investigation Area 1: Scoring System Complete Verification

### 1A: Score Factor Status (All 8)

For each factor, run queries to determine:
- How many employers have a non-null value for this factor
- What the min, max, average, and standard deviation are
- Whether the distribution looks reasonable (not all the same value, not extreme clustering)
- Whether the calculation matches the SCORING_SPECIFICATION.md

Specific checks:

```sql
-- Check if score_financial is still a copy of score_industry_growth
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE score_financial IS NOT NULL AND score_industry_growth IS NOT NULL 
AND score_financial != score_industry_growth;
-- If this returns 0, they're still identical (bug not fixed)

-- Check contracts score distribution
SELECT score_contracts, COUNT(*) 
FROM mv_unified_scorecard 
WHERE score_contracts IS NOT NULL 
GROUP BY score_contracts ORDER BY score_contracts;
-- If there's only one value (4.00), the tiered system isn't implemented

-- Check similarity coverage
SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_similarity IS NOT NULL;
-- Previous audit found 186. What is it now?

-- Check NLRB decay was applied
SELECT AVG(score_nlrb) FROM mv_unified_scorecard WHERE score_nlrb IS NOT NULL;
-- Previous: 6.20 (no decay). After fix: should be around 2.61.

-- Check factors_available distribution
SELECT factors_available, COUNT(*), 
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM mv_unified_scorecard 
GROUP BY factors_available ORDER BY factors_available;
```

### 1B: Priority Tier Deep Dive

```sql
-- How many Priority employers exist?
SELECT tier, COUNT(*) FROM mv_unified_scorecard GROUP BY tier;

-- Do any Priority employers have fewer than 3 factors?
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE tier = 'Priority' AND factors_available < 3;

-- What do the top 20 Priority employers look like?
SELECT employer_name, state, overall_score, factors_available,
       score_osha, score_nlrb, score_whd, score_contracts,
       score_union_density, score_size, score_similarity, score_industry_growth
FROM mv_unified_scorecard 
WHERE tier = 'Priority' 
ORDER BY overall_score DESC LIMIT 20;

-- How many Priority employers have zero enforcement activity?
-- (no OSHA, no NLRB, no WHD data at all)
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE tier = 'Priority' 
AND score_osha IS NULL AND score_nlrb IS NULL AND score_whd IS NULL;
```

### 1C: Score Distribution Analysis

```sql
-- Overall score distribution in buckets
SELECT 
  CASE 
    WHEN overall_score >= 9 THEN '9-10'
    WHEN overall_score >= 8 THEN '8-9'
    WHEN overall_score >= 7 THEN '7-8'
    WHEN overall_score >= 6 THEN '6-7'
    WHEN overall_score >= 5 THEN '5-6'
    WHEN overall_score >= 4 THEN '4-5'
    WHEN overall_score >= 3 THEN '3-4'
    WHEN overall_score >= 2 THEN '2-3'
    WHEN overall_score >= 1 THEN '1-2'
    ELSE '0-1'
  END as score_bucket,
  COUNT(*) as count
FROM mv_unified_scorecard
GROUP BY 1 ORDER BY 1;

-- Is the distribution bimodal (two humps)? The previous audit said yes.
```

### 1D: Junk Record Detection

```sql
-- Generic/placeholder employer names in scored universe
SELECT employer_name, state, overall_score, tier, factors_available
FROM mv_unified_scorecard
WHERE employer_name IN ('Employer Name', 'Company Lists', 'M1', 'Test', 'N/A', 'TBD', 'Unknown')
   OR LENGTH(employer_name) <= 2
   OR employer_name ~* '(pension benefit|federal agency|department of|city of|state of|county of|school district)'
ORDER BY overall_score DESC LIMIT 30;

-- How many short-name employers exist?
SELECT COUNT(*) FROM mv_unified_scorecard WHERE LENGTH(employer_name) <= 3;
```

---

## Investigation Area 2: Match Quality Post-Hardening

### 2A: Stale OSHA Matches

```sql
-- Are there still OSHA Splink matches below the 0.70 threshold?
SELECT COUNT(*) FROM unified_match_log 
WHERE source_system = 'osha' AND status = 'active' 
AND match_method LIKE '%SPLINK%'
AND (evidence::json->>'name_similarity')::float < 0.70;

-- If yes, how many?
-- Were the 29,236 stale matches identified in the previous audit dealt with?
```

### 2B: Match Method Audit Across Sources

```sql
-- What match methods are being used, by source?
SELECT source_system, match_method, COUNT(*), 
       AVG(confidence_score) as avg_conf,
       MIN(confidence_score) as min_conf
FROM unified_match_log 
WHERE status = 'active'
GROUP BY source_system, match_method 
ORDER BY source_system, COUNT(*) DESC;

-- Are there sources still using pre-Phase-B methods?
-- Look for 'NAME_STATE' (old) vs 'NAME_STATE_EXACT' (new)
-- Look for 'SPLINK_PROB' (old) vs 'FUZZY_SPLINK_ADAPTIVE' (new)
```

### 2C: Source-by-Source Match Rates

```sql
-- Current match rates per source
SELECT source_system, 
       COUNT(*) FILTER (WHERE status = 'active') as active,
       COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
       COUNT(*) FILTER (WHERE status = 'superseded') as superseded,
       COUNT(*) as total
FROM unified_match_log 
GROUP BY source_system ORDER BY active DESC;
```

### 2D: Match Records Pointing to Missing Employers

```sql
-- The previous audit found 46,627 match records pointing to non-existent F7 IDs
SELECT COUNT(*) FROM unified_match_log uml
WHERE uml.status = 'active'
AND NOT EXISTS (
  SELECT 1 FROM f7_employers_deduped f 
  WHERE f.employer_id = uml.f7_employer_id
);
-- Is this number the same, better, or worse?
```

### 2E: 20-Match Accuracy Sample

Sample 20 matches near the 0.70 threshold and evaluate each one:
```sql
SELECT source_system, source_id, f7_employer_id, match_method, 
       confidence_score, evidence::json->>'name_similarity' as name_sim,
       evidence::json->>'source_name' as source_name,
       f.employer_name as matched_to
FROM unified_match_log uml
JOIN f7_employers_deduped f ON f.employer_id = uml.f7_employer_id
WHERE uml.status = 'active' 
AND uml.match_method LIKE '%SPLINK%'
AND (evidence::json->>'name_similarity')::float BETWEEN 0.70 AND 0.75
ORDER BY RANDOM() LIMIT 20;
```

---

## Investigation Area 3: Research Agent Verification

### 3A: Where is the output stored?

Find the research agent tables and/or files:
```sql
-- Check for research-related tables
SELECT tablename FROM pg_tables 
WHERE schemaname = 'public' AND tablename LIKE '%research%';

-- Check for any new tables created since Feb 19
SELECT tablename, pg_total_relation_size(schemaname||'.'||tablename) as size
FROM pg_tables WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 30;
```

### 3B: Quality Assessment

- Read 5 research agent outputs in their entirety
- For each: Is the information specific and useful, or generic/boilerplate?
- Does the agent cite specific sources, or just produce general statements?
- Is the 7.93/10 quality score from actual evaluation criteria or self-assessment?
- Are the research results connected to employer profiles?

### 3C: Research Agent → Platform Integration

- Can a user access research agent results from the employer profile page?
- Is there an API endpoint that serves research results?
- Do research findings feed back into scoring in any way?

---

## Investigation Area 4: CorpWatch SEC EDGAR Import

### 4A: Table Inventory
```sql
-- Find the CorpWatch/SEC tables
SELECT tablename, pg_total_relation_size(schemaname||'.'||tablename) as size,
       n_live_tup as est_rows
FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE schemaname = 'public' AND tablename LIKE '%corpwatch%' OR tablename LIKE '%cw_%'
ORDER BY size DESC;
```

### 4B: Integration Check
- Are these tables linked to the core employer list via foreign keys or match tables?
- How many CorpWatch entities match to F7 employers?
- Is any of this data used in scoring?
- Is any of this data visible in the React frontend?
- What percentage of the 14.7M rows is actually queryable/useful?

---

## Investigation Area 5: NLRB Data Quality (Post-Cleanup)

### 5A: Participant Data Status
```sql
-- How many participant records remain after the 492K cleanup?
SELECT COUNT(*) FROM nlrb_participants;

-- How many still have junk data (header text as values)?
SELECT COUNT(*) FROM nlrb_participants 
WHERE state = 'Charged Party Address State' 
   OR city LIKE '%Address%';

-- What percentage is clean now?
```

### 5B: Proximity Calculation Source
This is critical: The NLRB scoring factor uses "within 25 miles" proximity. What data does this calculation actually use?

```sql
-- Check the scoring code for NLRB proximity
-- Look at build_unified_scorecard.py — does it JOIN to nlrb_participants or nlrb_cases?
-- If it uses participants, the proximity data may still be garbage
```

Read the actual code in `scripts/scoring/build_unified_scorecard.py` and trace the NLRB factor calculation. Report exactly which tables it queries and whether it uses the cleaned data or still references junk fields.

---

## Investigation Area 6: Membership Numbers Paradox

### 6A: State-by-State Comparison
```sql
-- Compare platform membership to BLS by state
-- The previous audit found DC at 141,563% and HI at 10.9% of BLS benchmark
-- Has this improved?
SELECT state, SUM(bargaining_unit_size) as platform_total
FROM f7_union_employer_relations r
JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
GROUP BY state ORDER BY platform_total DESC LIMIT 20;
```

### 6B: Is the National 14.5M Number Still Accurate?
```sql
SELECT SUM(bargaining_unit_size) FROM f7_union_employer_relations;
-- Compare to the documented 15,737,807 or 14.5M depending on methodology
```

### 6C: Broken Membership View
```sql
-- The v_union_members_deduplicated view produces 72M instead of 14.5M
-- Is this view still broken?
SELECT COUNT(*), SUM(members) FROM v_union_members_deduplicated;
```

---

## Investigation Area 7: Incomplete Source Re-runs

### 7A: 990 Matches Status
```sql
-- 990 only had batch 1/5 completed. What's the current state?
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = '990' 
GROUP BY match_method, status ORDER BY match_method, status;
```

### 7B: WHD Matches Status
```sql
-- WHD was never re-run (OOM). What methods are in the current matches?
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = 'whd' 
GROUP BY match_method, status ORDER BY match_method, status;
```

### 7C: SAM Matches Status
```sql
-- SAM was never re-run (OOM). Same check.
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = 'sam' 
GROUP BY match_method, status ORDER BY match_method, status;
```

### 7D: Impact Assessment
- For each incomplete source: how many employers are affected?
- Could stale matches be producing wrong scores for some employers?
- Is there a way to flag these employers in the UI as "match quality uncertain"?

---

## Investigation Area 8: Over-Merge and Under-Merge Problems

```sql
-- The previous audit found employer groups that were false merges
-- Check the largest employer groups
SELECT employer_name, state, COUNT(*) as group_size
FROM f7_employers_deduped
GROUP BY employer_name, state
HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC LIMIT 20;

-- Check for the specific problems found before:
-- "D. CONSTRUCTION, INC." with 249 members
-- "Building Service, Inc." with 164 members
-- "PTA ALABAMA CONGRESS" with 239 members
SELECT employer_name, COUNT(*) 
FROM f7_employers_deduped
WHERE employer_name ILIKE '%construction%inc%'
   OR employer_name ILIKE '%building service%'
   OR employer_name ILIKE '%pta%congress%'
GROUP BY employer_name
HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC;
```

---

## Investigation Area 9: Database Health and Cleanup

```sql
-- Empty tables
SELECT tablename FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE t.schemaname = 'public' AND s.n_live_tup = 0;

-- Total database size
SELECT pg_size_pretty(pg_database_size('olms_multiyear'));

-- Largest tables (top 20)
SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename)) as size,
       n_live_tup as rows
FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE t.schemaname = 'public'
ORDER BY pg_total_relation_size('public.'||tablename) DESC LIMIT 20;

-- Missing indexes on frequently-joined columns
-- Specifically check nlrb_participants.case_number (previous audit said no index)
SELECT indexname FROM pg_indexes 
WHERE tablename = 'nlrb_participants' AND indexdef LIKE '%case_number%';

-- Check for orphaned views (views referencing non-existent tables)
-- This requires checking view definitions against actual tables
```

---

## Investigation Area 10: API Endpoint Spot Check

You may not be able to test HTTP endpoints directly, but you can verify the data they would return:

```sql
-- Test the profile endpoint data for a specific employer
-- Pick a well-known employer and check all the data that would appear on their profile
SELECT * FROM mv_unified_scorecard WHERE employer_name ILIKE '%kaiser%' LIMIT 5;

-- Check that the data_source_freshness table is usable
SELECT * FROM data_source_freshness ORDER BY source_name;

-- Check the system stats query (was 4-12 seconds slow)
EXPLAIN ANALYZE SELECT COUNT(*) FROM master_employers;
```

---

## SHARED OVERLAP ZONE

**You MUST also answer all 10 Shared Overlap Zone questions from Section 1.** Label answers OQ1-OQ10.

## Output Format

1. **Executive Summary** (5-10 sentences max — what's the honest state of this platform?)
2. **Shared Overlap Zone Answers** (all 10, clearly labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-10, with SQL evidence for every claim)
4. **Surprise Findings** (anything you discovered that wasn't asked about)
5. **Previous Audit Follow-Up** (which of the 20 investigation questions have been addressed?)
6. **Recommended Priority List** (rank the top 10 things to fix, with effort estimates)

---

# SECTION 3: CODEX PROMPT (Code Quality & Architecture Reviewer)

**Give this prompt to Codex. It needs access to the full codebase.**

---

## Your Role

You are reviewing the code quality, test coverage, architecture, and deployment readiness of a labor relations research platform. Your job is to open files, read actual code, and find bugs, gaps, and structural problems.

**Critical rules:**
1. **Read the actual code.** Don't say "the scoring pipeline appears to work based on file names." Open `scripts/scoring/build_unified_scorecard.py`, read the SQL inside it, and verify line by line.
2. **Show file paths, line numbers, and code snippets.** "There's a problem in scoring" is useless. "Line 340 of `scripts/scoring/build_unified_scorecard.py` contains `s.score_industry_growth AS score_financial`" is useful.
3. **Do NOT fix anything during this audit.** Document what you find. Fixes will come from the roadmap this audit produces.
4. **Say "I didn't check this" when you skip something.** A partial honest audit is better than a falsely comprehensive one.

---

## Investigation Area 1: Scoring Pipeline Code — Line by Line

Open `scripts/scoring/build_unified_scorecard.py` and verify every scoring factor against SCORING_SPECIFICATION.md.

### 1A: Factor-by-Factor Code Verification

For EACH of these 8 factors, find the exact code that calculates it and verify:

**Factor 1 — OSHA Safety (Weight: 1x)**
- Does the code do industry normalization? (Compare violation count to industry peers)
- Does the code implement 5-year half-life time decay?
- Does the code add +1 for willful/repeat violations (capped at 10)?
- What table(s) does it query? Does it use the cleaned OSHA data?

**Factor 2 — NLRB Activity (Weight: 3x)**
- Does the code implement the 70/30 split (nearby momentum / own history)?
- Does the "nearby" calculation use a 25-mile radius?
- Does the code use the 7-year half-life decay that was added in Feb 19?
- Does the latest-election dominance logic work?
- CRITICAL: Does it join to `nlrb_participants` (which had 83.6% junk data)? If yes, does it use the cleaned version or the junk version?

**Factor 3 — WHD Wage Theft (Weight: 1x)**
- Does the code use the tier system (0/5/7/10 based on case count)?
- Does it implement 5-year half-life?
- What match table does it use? Old `whd_f7_matches` or new `unified_match_log`?

**Factor 4 — Government Contracts (Weight: 2x)**
- Does the code implement tiered scoring (0/4/6/7/8/10 based on contract levels)?
- Or does it still give everyone 4.00?
- Does it combine federal + state + local contracts?

**Factor 5 — Union Density (Weight: 1x)**
- Does it use state × industry intersection?
- What BLS data does it reference?

**Factor 6 — Employer Size (Weight: 3x)**
- Does it implement the sweet-spot curve? (15-500 linear ramp, plateau at 500+, taper at 25K+)
- What column does it use for employer size?

**Factor 7 — Statistical Similarity (Weight: 2x)**
- Is this factor active in the code or commented out?
- What connects `employer_comparables` (269K rows) to this score?
- Why do only 186 employers have a value?

**Factor 8 — Industry Growth (Weight: 2x)**
- Does it use BLS 10-year projections?
- Is `score_financial` STILL a copy of `score_industry_growth`? (Check line 340 specifically)
- If they're still identical, this means users see 8 factors in the display but there are really only 7 unique signals.

### 1B: The Weighted Average Calculation
- Find the exact code that combines all 8 factors into the final score
- Verify the weights match the spec (OSHA 1x, NLRB 3x, WHD 1x, Contracts 2x, Density 1x, Size 3x, Similarity 2x, Growth 2x)
- What happens when factors_available = 0? (Divide by zero risk?)
- Is the Priority minimum of 3 factors enforced in the scoring code, the view definition, or the API layer?

---

## Investigation Area 2: React Frontend Architecture

### 2A: Component Inventory
- How many React component files exist? List the top-level feature directories.
- Are there any components over 500 lines? (These probably need splitting)
- What's the total lines of code in the frontend?

### 2B: State Management Audit
- Is Zustand used consistently, or are there components using local state, Context, or prop drilling instead?
- List every Zustand store and what it manages
- Are there any stores that have gotten too large or do too many things?

### 2C: API Integration Patterns
- Is there a centralized API client (like the thin wrapper described in REACT_IMPLEMENTATION_PLAN.md)?
- Or are `fetch` calls scattered throughout components?
- How are API errors handled? Is there a global error boundary?
- List every API endpoint the frontend calls (trace through the code)

### 2D: TanStack Query Usage
- Is TanStack Query used for all data fetching?
- Are cache keys consistent?
- Are loading states handled everywhere, or are there components that show nothing while loading?
- Is there background refresh configured?

### 2E: Frontend-API Contract Verification
For each major page:
1. **Search page**: What endpoint does it call? What does it expect back? Verify the response shape.
2. **Employer profile**: What endpoints does it call? (Score, OSHA violations, NLRB history, corporate hierarchy, etc.) Verify each one.
3. **Union profile**: What endpoints does it call? Do the new financial/membership endpoints exist and work?
4. **Targets page**: What endpoint populates the tier cards? What data shape does it expect?
5. **Admin panel**: What endpoints does it call? Does the data freshness dashboard have data to show?

### 2F: Error and Edge Case Handling
- What happens if an employer has no score? No matches? No OSHA data?
- What happens if the API returns 500?
- What happens if the API returns an empty array?
- What happens if the employer_id doesn't exist?
- Is there a 404 page?

---

## Investigation Area 3: API Endpoint Complete Audit

### 3A: Endpoint Inventory
List EVERY API endpoint defined in the FastAPI code. For each:
- HTTP method and path
- Whether it has input validation
- Whether it has authentication requirements
- What database queries it runs

### 3B: Security Audit
- Are there any endpoints that build SQL using string concatenation instead of parameterized queries?
- Which endpoints require authentication? Which don't?
- Is CORS configured correctly?
- Are there any admin endpoints accessible without admin role?
- Is the `DISABLE_AUTH=true` flag still in `.env`? (It should be for development, but is it documented as a deployment risk?)

### 3C: Performance Audit
- Which endpoints run the most expensive queries?
- Are there any endpoints that do full table scans on large tables?
- Is the `nlrb_participants.case_number` index present? (Previous audit said it was missing)
- Are materialized views used where they should be, or are some queries recomputing things that should be cached?

### 3D: The Search Endpoint Problem
The previous audit found that using the wrong parameter name (`?q=` instead of `?name=`) silently returns all 107,025 records. Is this still the case?

### 3E: Profile Endpoints
Check `/api/profile/employers/{employer_id}` and `/api/profile/unions/{f_num}`:
- Do they return complete data?
- What happens with an invalid ID?
- How fast are they? (Check the query complexity)
- Do they return data from the CorpWatch import? Research agent? Or just the original sources?

---

## Investigation Area 4: Test Coverage Deep Dive

### 4A: Test Inventory
List every test file and categorize what it tests:
- Unit tests (testing individual functions)
- Integration tests (testing API endpoints with database)
- Frontend tests (testing React components)
- Scoring tests (testing actual score calculations)
- Matching tests (testing match accuracy)

### 4B: Coverage Analysis
- Can you run a coverage analysis? (`pytest --cov=scripts --cov=api tests/`)
- What files have 0% coverage?
- What's the coverage percentage for the most critical files?
  - `build_unified_scorecard.py`
  - `run_deterministic.py`
  - `splink_pipeline.py`
  - `api/main.py`
  - `api/routers/employers.py`
  - `api/routers/profile.py`

### 4C: Test Quality Assessment
- Pick 10 tests at random. Do they test meaningful behavior, or just "does this not crash"?
- Are there any tests that assert specific score values?
- Are there any tests that verify match accuracy?
- Are there any tests that check for regression of previously found bugs?

---

## Investigation Area 5: Deployment Readiness

### 5A: Docker Artifacts
Open `Dockerfile`, `docker-compose.yml`, and `nginx.conf`. Answer:
- Are these functional or empty stubs?
- Could someone actually deploy with these files today?
- What environment variables are needed?
- Is there a database migration strategy? (How would you recreate 174 tables on a new server?)
- Is there a data loading strategy? (How would you populate the database from scratch?)

### 5B: Portability Issues
The previous audit found 19 scripts with hardcoded `C:\Users\jakew\Downloads` paths. Check:
- Are these still present?
- How many scripts have hardcoded paths?
- Are there other portability issues? (Windows-specific paths, local file references, etc.)

### 5C: Dependency Management
- Is there a complete `requirements.txt` or `pyproject.toml`?
- Are the Python dependencies pinned to specific versions?
- Are the npm/Node.js dependencies pinned?
- Could someone install this on a fresh machine with just the documented setup steps?

### 5D: Credential Safety
- Are there any passwords, API keys, or tokens in the codebase (not in `.env`)?
- The previous audit found "Juniordog33!" in 10 archived files. Is this still present?
- Is `.env` in `.gitignore`?

---

## Investigation Area 6: Code Quality and Maintenance

### 6A: Dead Code Detection
- Are there Python scripts that are never imported or called by anything?
- Are there React components that are never rendered?
- The previous audit found "55 analysis scripts, 20-30 of which are one-off or superseded." Is this still the case?
- Are there versioned duplicate scripts (e.g., `analyze_v1.py`, `analyze_v2.py`, `analyze_v3.py`)?

### 6B: Error Handling Patterns
- Do ETL scripts fail gracefully with error messages, or crash with tracebacks?
- Do matching scripts log their progress? Can you tell where a failed run stopped?
- Is there a consistent logging pattern across the codebase?

### 6C: Documentation in Code
- Do the most critical files have docstrings and comments explaining WHY, not just WHAT?
- Is the `PIPELINE_MANIFEST.md` up to date? (Check 5 random entries — do the files exist and do the described purposes match?)

---

## SHARED OVERLAP ZONE

**You MUST also answer all 10 Shared Overlap Zone questions from Section 1.** Label answers OQ1-OQ10.

## Output Format

1. **Executive Summary** (5-10 sentences max)
2. **Shared Overlap Zone Answers** (all 10, clearly labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-6, with file paths and line numbers)
4. **Bug List** (every bug found: file, line, severity [Critical/High/Medium/Low], description)
5. **Architecture Concerns** (structural issues that aren't bugs but will cause problems)
6. **Missing Test Coverage** (the 10 most important things with no tests)
7. **Deployment Blockers** (things that MUST be fixed before deployment)
8. **Recommended Priority List** (rank the top 10 things to fix, with effort estimates)

---

# SECTION 4: GEMINI PROMPT (Strategic & Data Coverage Analyst)

**Give this prompt to Gemini. It works primarily from documentation but should also review key code files and data exports when possible.**

---

## Your Role

You are the strategic analyst. While the other auditors check whether the code runs correctly and the data is accurate, your job is to step back and ask: **Does this platform actually serve organizers? Would they trust it? Would it help them make better decisions?**

The platform is built for workplace organizers — people at unions and worker organizations who need to figure out where to focus their limited time and resources for organizing campaigns.

**Critical rules:**
1. **Think like an organizer.** Your questions should be: "Would this help someone decide which employer to target?" "What would make an organizer stop trusting this platform?" "What information is missing that organizers need?"
2. **Cross-reference claims.** The documentation makes many claims. For each major claim, ask whether the evidence supports it. "96.2% matching accuracy" — what does that actually mean? "7.93/10 research agent quality" — who's grading it?
3. **Identify what's NOT being measured.** The platform focuses heavily on government data. What important dimensions of organizing potential does government data miss entirely?
4. **Be honest about what you can't verify.** You don't have direct database access. When working from documentation, say so.

---

## Investigation Area 1: Does the Scoring System Predict Organizing Potential?

### 1A: Factor Selection Critique
The platform scores employers on 8 factors: OSHA violations, NLRB activity, wage theft, government contracts, union density, employer size, statistical similarity, and industry growth.

For EACH factor, assess:
- What's the theory of why this predicts organizing success?
- What research or evidence supports this connection?
- Are there cases where this factor would be misleading? (e.g., a company with no OSHA violations isn't necessarily safe — they might just be in a low-inspection industry)
- Would experienced organizers agree this matters?

### 1B: What's Missing from the Score?
Think about what actually drives successful organizing campaigns. What factors does the platform completely ignore?

Consider:
- **Employer financial vulnerability** — SEC data exists but isn't in scoring. A company in financial trouble may be more vulnerable to pressure.
- **Worker turnover and satisfaction** — High turnover often correlates with organizing interest. No data source for this.
- **Recent media/news** — A company in the news for labor issues is more likely to see organizing activity. Not tracked.
- **Management anti-union history** — Beyond NLRB ULP cases, there's a whole dimension of union-avoidance consulting, captive audience meetings, etc.
- **Community and political support** — Local political climate affects organizing success. Not measured.
- **Workforce demographics** — Younger workers and workers of color are organizing at higher rates. BLS data exists but isn't in scoring.
- **Industry organizing momentum** — Beyond individual NLRB elections, there are sector-wide movements (Starbucks, Amazon, tech) that the platform may not capture well.
- **Contract expiration dates** — When existing contracts expire, it creates organizing opportunities at non-union competitors.
- **Employer growth/contraction** — A growing employer is a different organizing target than a shrinking one.

### 1C: The Signal-Strength Dilemma
When an employer has no data for a factor, it's skipped. This means:
- An employer with 1 factor (size = large) and a perfect size score gets ranked higher than an employer with 6 factors showing moderate scores across safety, wage theft, NLRB activity, etc.
- Is this the right design? What would organizers think?
- How should the platform communicate data completeness to users?

### 1D: Score Validation
Has anyone ever checked whether this scoring system actually predicts real-world organizing outcomes? Specifically:
- Of the employers ranked "Priority," how many have actually seen organizing activity?
- Of employers where organizing succeeded, how were they ranked BEFORE the campaign?
- Is there any backtesting data?

The previous audit found that "Priority" captured only 125 election wins while "Low" captured 392. This means the lowest tier had 3x more real organizing success than the highest tier. Has anyone addressed this?

---

## Investigation Area 2: Data Coverage — Who's Invisible?

### 2A: The Fundamental F7 Limitation
The platform only scores employers in the F7 database — employers that ALREADY have union contracts. But the entire point is to find NEW organizing targets at NON-union employers.

- How many potential non-union targets exist in the `master_employers` table?
- Are any of them scored?
- What's the plan for expanding scoring to non-union employers?
- How urgent is this? (Is the platform useful for organizers if it only covers already-unionized employers?)

### 2B: Industry Gaps
The previous audit found:
- Amazon: Only 4 entries (studios, construction, masonry, painting). Zero warehouse/fulfillment.
- Walmart: Zero entries.
- Cannabis industry: Zero entries.
- Finance/Insurance: Only 418 employers vs 25,302 in Construction.

Have any of these gaps been addressed? What industries are still invisible?

### 2C: Public Sector Gaps
- 7,987 public employers vs ~7 million public sector unionized workers
- What state PERB data exists?
- How big is the gap in practical terms for public sector organizers?

### 2D: Geographic Gaps
- 26.2% of employers have no geocoding (no lat/lng)
- Are some states or regions more affected than others?
- How does this affect the "within 25 miles" NLRB proximity calculation?

### 2E: Temporal Gaps
- How old is the oldest data in each major source?
- How frequently is each source updated?
- If an organizer looks up an employer today, could they be seeing 5-year-old OSHA data? 10-year-old?

---

## Investigation Area 3: Research Agent Strategic Value

### 3A: What Does the Research Agent Actually Do?
Review the RESEARCH_AGENT_IMPLEMENTATION_PLAN.md and assess:
- What questions does it try to answer about an employer?
- What sources does it check?
- How does its output compare to what an organizer could find with 30 minutes of manual research?

### 3B: The "Self-Improving" Claim
The plan describes a self-improving agent that learns from past runs. Assess:
- Is the learning mechanism actually built, or is it planned?
- How would you measure whether the agent is actually getting better?
- What would make this genuinely indispensable vs. just convenient?

### 3C: Integration with Platform
- Can organizers trigger research from the employer profile?
- Are research findings visible in the platform UI?
- Do research findings feed back into scores or flags?
- If not, what would the ideal integration look like?

---

## Investigation Area 4: The Organizer's Experience

### 4A: User Journey Analysis
Walk through 3 realistic scenarios an organizer might have:

**Scenario 1: "I'm an SEIU healthcare organizer in California. Show me my best targets."**
- Can the platform answer this? What would the organizer see?
- Would the results be trustworthy? What could go wrong?

**Scenario 2: "We're considering organizing Amazon warehouse workers in New Jersey. What do we know?"**
- Can the platform help? What data exists?
- What critical information is missing?

**Scenario 3: "We just won an election at a hospital in Ohio. Who else nearby should we target next?"**
- Can the platform find nearby similar employers?
- Does the "within 25 miles" feature work for this use case?
- What would make the organizer's next step clear?

### 4B: Trust Assessment
If an organizer uses this platform and discovers one piece of incorrect information (a wrong OSHA match, a wrong score, a placeholder company ranked as Priority):
- How would this affect their trust in the entire platform?
- Is there any mechanism for users to flag errors?
- How transparent is the platform about data uncertainty?

### 4C: Competitive Context
What tools do organizers currently use?
- NLRB's own search (limited but official)
- OSHA's search (limited but official)
- LaborAction Tracker (public resource)
- Union density data from BLS/EPI
- Commercial databases (Mergent, etc.)
- Manual research (Google, news articles, Glassdoor, LinkedIn)

What does THIS platform offer that the above don't? And what do they offer that this platform doesn't?

---

## Investigation Area 5: Previous Audit Follow-Up

The FOUR_AUDIT_SYNTHESIS_v3.md documented extensive problems. For each major category, assess whether the strategic situation has changed:

### 5A: Scoring System Problems
- Priority tier was "mostly ghost employers" — is this still true?
- The platform "can't see most organizing successes" — is this still true?
- The score distribution was bimodal — has this improved?
- 125 wins in Priority vs 392 in Low — has anyone addressed the prediction problem?

### 5B: Match Accuracy
- 10-40% false positive rates — what's the current estimate?
- The Splink model overweights geography — has the model been retuned?
- Legacy poisoned matches — have they been cleaned up?

### 5C: Data Quality
- Membership numbers don't add up state-by-state — addressed?
- Data freshness tracking was broken — fixed?
- Three empty columns on f7_employers_deduped — removed?

### 5D: Infrastructure
- No backup strategy — implemented?
- 19 scripts with hardcoded paths — fixed?
- Legacy frontend still being served — archived?
- Authentication never tested with real users — tested?

---

## Investigation Area 6: Documentation and Consistency

### 6A: Document Conflicts
The DOCUMENT_RECONCILIATION_ANALYSIS.md found major inconsistencies across 5 documents. Assess:
- Have any of these been resolved?
- How many scoring factors are there according to each document? (7? 8? 9?)
- How many tests pass according to each document?
- Is there a single source of truth, or do documents still contradict each other?

### 6B: Roadmap Reality Check
Review UNIFIED_ROADMAP_2026_02_19.md:
- Are the priorities in the right order for organizers?
- What's the most impactful thing that's NOT in the roadmap?
- How much of the roadmap is fixing existing problems vs. building new features?
- What's a realistic timeline to have something organizers could actually use?

### 6C: Feature Prioritization
If you could only build 3 things before showing this to real organizers, which 3 would have the most impact? Consider:
- What creates the most trust
- What answers the most important question
- What differentiates this from tools organizers already have

---

## SHARED OVERLAP ZONE

**You MUST also answer all 10 Shared Overlap Zone questions from Section 1.** For questions requiring database access, do your best with documentation and note what you verified vs. estimated. Label answers OQ1-OQ10.

## Output Format

1. **Executive Summary** (5-10 sentences — the honest state of this platform from a strategic perspective)
2. **Shared Overlap Zone Answers** (all 10, clearly labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-6)
4. **The Organizer's Verdict** (a paragraph written as if you were an experienced organizer seeing this platform for the first time — what impresses you and what concerns you)
5. **Strategic Blind Spots** (important things nobody seems to be thinking about)
6. **Competitor Gap Analysis** (what this platform offers vs. what organizers already have)
7. **Previous Audit Reality Check** (what was addressed, what wasn't, what got worse)
8. **Recommended Priority List** (top 10 things to fix/build, ordered by impact for organizers, with effort estimates)

---

# SECTION 5: SYNTHESIS GUIDE

After all three agents complete their audits, use this framework to compare and synthesize.

## Step 1: Compare Overlap Zone Answers

Create a comparison table for each overlap question:

| Question | Claude Code Finding | Codex Finding | Gemini Finding | Agreement |
|----------|-------------------|---------------|----------------|-----------|
| OQ1: Priority spot check | | | | ✅/⚠️/❌ |
| OQ2: Match accuracy (20) | | | | ✅/⚠️/❌ |
| OQ3: Frontend-API (5 features) | | | | ✅/⚠️/❌ |
| OQ4: Data freshness | | | | ✅/⚠️/❌ |
| OQ5: Incomplete re-runs impact | | | | ✅/⚠️/❌ |
| OQ6: All 8 factors status | | | | ✅/⚠️/❌ |
| OQ7: Test suite | | | | ✅/⚠️/❌ |
| OQ8: Database cleanup | | | | ✅/⚠️/❌ |
| OQ9: Biggest problem | | | | ✅/⚠️/❌ |
| OQ10: Previous audit follow-up | | | | ✅/⚠️/❌ |

**Agreement key:**
- ✅ All three substantively agree (highest confidence)
- ⚠️ Two agree, one differs (investigate the disagreement)
- ❌ All three give different answers (needs human judgment call)

## Step 2: Cross-Agent Pattern Detection

Look for:
- **Convergent findings** — All three agents flagged the same problem from different angles (most serious)
- **Unique discoveries** — One agent found something critical that the others missed (may be the most valuable)
- **Contradictions** — One says "fixed," another says "still broken" (needs investigation)
- **Scope gaps** — Areas none of the three covered (add to investigation list)

## Step 3: Severity Classification

For every finding across all three reports, classify:

| Severity | Definition | Example |
|----------|-----------|---------|
| **CRITICAL** | Would mislead an organizer into making a wrong decision | Wrong OSHA data attributed to wrong employer |
| **HIGH** | Would reduce organizer trust in the platform | Placeholder company ranked as Priority target |
| **MEDIUM** | Would inconvenience organizers or limit usefulness | Missing geocoding means employer doesn't appear on map |
| **LOW** | Code quality or maintenance issue, no user impact yet | Dead code, duplicate scripts, stale documentation |
| **ENHANCEMENT** | Not broken, but would significantly improve value | Research agent integration with employer profiles |

## Step 4: Build the New Roadmap

Priority tiers for the new roadmap:

**TIER 1: DATA TRUST** — Fix before showing to anyone
- Problems all agents agree on that would mislead organizers
- Score accuracy, match accuracy, junk record removal
- If an organizer would see wrong information, it's Tier 1

**TIER 2: COMPLETE THE FOUNDATION** — Fix before regular use
- Incomplete source re-runs (990, WHD, SAM)
- Missing indexes and performance issues
- Data freshness tracking
- Database backups

**TIER 3: USER EXPERIENCE** — Fix before public launch
- Frontend-API contract mismatches
- Error handling and loading states
- Search parameter problems
- Legacy frontend removal

**TIER 4: STRATEGIC EXPANSION** — Build for maximum impact
- Non-union employer scoring (the targeting paradox)
- Research agent integration
- New data sources (state PERB, etc.)
- Public sector gap closure

**TIER 5: DEPLOYMENT** — Prepare for production
- Docker/containerization
- Hardcoded path cleanup
- Authentication testing with real users
- Credential scrubbing

**PARALLEL TRACKS** (can happen alongside any tier):
- Documentation refresh
- Dead code cleanup
- Test coverage expansion
- Accessibility improvements
