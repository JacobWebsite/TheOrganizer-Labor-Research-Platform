# Platform Audit — Claude Code (Deep Technical Investigator)
## February 25, 2026

---

## YOUR ROLE

You are auditing a labor relations research platform. You have direct access to the PostgreSQL database (`olms_multiyear`, localhost:5432, user `postgres`) and can run SQL queries to verify everything. Your job is to be the deep technical investigator — the one who actually checks the data, not just the code or docs.

**You are one of three auditors.** Codex is reviewing code quality and architecture. Gemini is assessing strategic value for organizers. Your unique strength is direct database access — you can verify claims that no one else can.

**Critical rules:**
1. **Show SQL and results for every claim.** Don't say "the scores look right." Show the actual query and the actual numbers.
2. **Say "I didn't check this" or "I'm not sure" rather than guess.** An honest gap is infinitely better than a confident wrong answer.
3. **Compare actual values to documented values.** If PROJECT_STATE.md says "97,142 OSHA matches" but the database says something different, that's a finding.
4. **Check for side effects.** When something was "fixed," check whether the fix broke anything else.
5. **Be thorough.** It is much better to check everything and find nothing than to skip something and miss a problem that has to be fixed later.

**Context files you should have:**
- `PROJECT_STATE.md` — current platform state, session handoffs, known issues
- `CLAUDE.md` — database schema and technical reference
- `SCORING_SPECIFICATION.md` — how scoring is supposed to work
- `UNIFIED_ROADMAP_2026_02_19.md` — current roadmap
- `FOUR_AUDIT_SYNTHESIS_v3.md` — previous audit findings to verify

---

## WHAT CHANGED SINCE THE LAST AUDIT (Feb 19, 2026)

Your job is to verify that these changes actually worked and didn't break anything:

1. **Research Agent Built** — Automatically researches companies. 96 runs, 7.93/10 avg quality. Uses Crawl4AI for web scraping plus database lookups.

2. **CorpWatch SEC EDGAR Import** — 14.7 million rows of corporate ownership data imported into 7 new tables. Different from the existing `sec_companies` table.

3. **Data Enrichment** — Geocoding went from 73.8% to 83.3%. NAICS industry codes inferred for employers that didn't have them.

4. **NLRB Participant Cleanup** — 492K junk rows removed from `nlrb_participants`. Previous audit found 83.6% had CSV header text instead of real data.

5. **React Frontend Completed** — All 6 phases. 134 frontend tests. You don't need to deeply review frontend code (that's Codex's job), but verify the API endpoints it depends on return correct data.

6. **Scoring Code Updates** — NLRB 7-year half-life decay. Latest-election dominance. BLS financial inversion fix. `factors_available >= 3` for Priority tier.

7. **Splink Threshold Hardened** — Fuzzy matching minimum raised from 0.65 to 0.70.

8. **Docker Artifacts Added** — Dockerfile, docker-compose.yml, nginx.conf (untested first drafts).

9. **Materialized Views Refreshed** — `mv_unified_scorecard`, `mv_employer_data_sources`, `mv_organizing_scorecard` rebuilt as of Feb 19.

10. **Source Re-runs Partially Complete** — OSHA (4/4 done), SEC (5/5 done), BMF (done). **NOT complete:** 990 (batch 1/5 only), WHD (failed with OOM, never re-run), SAM (failed with OOM, never re-run).

**Key question:** The 990, WHD, and SAM re-runs were never completed. These sources still have matches from the old (pre-Phase-B) matching pipeline. How much does this affect scoring and data quality?

---

# PART 1: SHARED OVERLAP ZONE

**You MUST answer all 10 of these questions.** Two other AI auditors (Codex and Gemini) are answering the same questions independently. Your answers will be compared side by side to find agreements and disagreements. Label each answer clearly (OQ1, OQ2, etc.).

---

### OQ1: Priority Tier Spot Check (5 Employers)

Pick 5 employers that the system currently ranks as "Priority" (highest tier). For each one, report:
- Employer name, state, employer_id
- Final score (0-10)
- How many of the 8 scoring factors have data for this employer
- What factors are driving the high score
- Whether this looks like a real, organizable employer (not a placeholder, federal agency, shell company, or generic name)
- Whether an organizer would find this employer's profile useful and accurate

**Why:** The previous audit found placeholder records ("Employer Name"), 2-character names ("M1"), and federal agencies ranked as Priority with perfect 10.0 scores. The `factors_available >= 3` fix was applied. We need to know if the problem is actually solved or just reduced.

---

### OQ2: Match Accuracy Spot Check (20 Matches)

Pick 20 employer matches from `unified_match_log`:
- 5 from OSHA matches
- 5 from NLRB matches
- 5 from WHD or SAM matches
- 5 from Splink fuzzy matches near the 0.70 threshold (name similarity 0.70-0.75)

For each, report:
- Source name vs. matched employer name
- Match method and confidence score
- Name similarity score (if fuzzy)
- Your judgment: correct match, wrong match, or uncertain
- If wrong: what went wrong

**Why:** Previous audit found 10-40% false positive rates. Threshold was raised to 0.70 but 29,236 OSHA matches from before the fix may still exist.

---

### OQ3: React Frontend ↔ API Contract (5 Features)

Check 5 different features by verifying the API endpoints the frontend depends on:
1. **Employer search** — Does the search endpoint return data the frontend expects?
2. **Employer profile** — Do the profile endpoints return complete data?
3. **Scoring breakdown** — Does the score data include all 8 factors?
4. **Union profile** — Do the financial/membership endpoints exist and work?
5. **Targets page** — Does the tier data endpoint return correct counts?

For each: Does the data shape match what the frontend expects? Are there missing fields? What happens on errors?

---

### OQ4: Data Freshness and View Staleness

- When was `mv_unified_scorecard` last refreshed?
- When was `mv_employer_data_sources` last refreshed?
- When was `mv_employer_search` last refreshed?
- Do the scores reflect the February 19 code changes (NLRB decay, financial fix, factors >= 3)?
- What does the `data_source_freshness` table show? Are the dates accurate or still broken (13/19 NULL, NY showing year 2122)?
- Are there views or materialized views referencing tables/columns that no longer exist?

---

### OQ5: Incomplete Source Re-runs — Impact Assessment

990, WHD, and SAM still have old matches. Assess:
- How many active matches exist for each in `unified_match_log`?
- What match methods were used? (Old pre-Phase-B methods like `NAME_STATE` vs new like `NAME_STATE_EXACT`?)
- Are there matches below the 0.70 threshold that should have been filtered?
- How much does this affect the scores?
- How many employers have potentially wrong scores because of stale matches?

---

### OQ6: The Scoring Factors — Current State (All 8)

For each of the 8 scoring factors, report:
1. **OSHA Safety (1x):** What % of employers have this? Is the calculation correct?
2. **NLRB Activity (3x):** What % have this? Does the 70/30 nearby/own split work? Does proximity use clean or junk participant data?
3. **WHD Wage Theft (1x):** What % have this? Are tiers (0/5/7/10) implemented?
4. **Gov Contracts (2x):** What % have this? Is there tiered scoring or still everyone gets 4.00?
5. **Union Density (1x):** What % have this? State × industry intersection?
6. **Employer Size (3x):** What % have this? Sweet-spot curve?
7. **Statistical Similarity (2x):** What % have this? Still 186/146,863?
8. **Industry Growth (2x):** What % have this? Is `score_financial` still a copy of `score_industry_growth`?

Also: What's the score distribution by tier? Average factors per employer? % with only 1-2 factors?

---

### OQ7: Test Suite Reality Check

- Run the full test suite. How many pass/fail? What fails and why?
- Are there tests that verify actual score VALUES?
- Are there tests that verify match ACCURACY?
- Are there frontend tests? What do they test?
- What's the most important thing with NO test coverage?

---

### OQ8: Database Cleanup Opportunity

- How many tables exist? How many have zero rows?
- How many appear to be abandoned experiments?
- Are there CorpWatch import tables not connected to anything?
- How much disk space could be reclaimed?
- Is the 12 GB GLEIF dump still present?
- How many of the 42 orphaned industry views are still there?

---

### OQ9: Single Biggest Problem

What is the single most important thing to fix before showing this to real organizers?
- What the problem is (plain language)
- Who it affects and how
- Your confidence level
- Rough effort estimate
- What happens if it's NOT fixed

---

### OQ10: Previous Audit Follow-Up

Check which of these from the previous audit have been addressed:

**Investigation questions:**
1. Was name similarity floor tested at 0.75/0.85?
2. Was 14.5M membership validated state-by-state?
3. Were 75,043 orphaned superseded matches investigated?
4. Were 46,627 UML records pointing to missing F7 targets investigated?
5. Was NAICS inference done for the 22,183 lacking codes?
6. Was employer grouping (over-merge of 249 construction companies) addressed?
7. Was comparables→similarity pipeline investigated?
8. Was NLRB proximity data source verified?
9. Were junk/placeholder records cleaned from scoring?
10. Was geocoding gap investigated by tier?

**Decisions:**
1. Name similarity floor — still 0.70 or changed?
2. Priority definition — structural only or requires recent activity?
3. Minimum factors — still 3 for Priority only or extended?
4. Stale OSHA matches — 29,236 dealt with?
5. score_similarity — removed or still weighted 2x?
6. Legacy frontend — archived?
7. User data storage — still localStorage?

---

# PART 2: YOUR SPECIFIC INVESTIGATION AREAS

---

## Area 1: Scoring System Complete Verification

### 1A: Score Factor Status (All 8)

For each factor, run queries to check count, min, max, average, standard deviation, and distribution:

```sql
-- Are score_financial and score_industry_growth still identical?
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE score_financial IS NOT NULL AND score_industry_growth IS NOT NULL 
AND score_financial != score_industry_growth;

-- Contracts score distribution — still flat at 4.00?
SELECT score_contracts, COUNT(*) 
FROM mv_unified_scorecard WHERE score_contracts IS NOT NULL 
GROUP BY score_contracts ORDER BY score_contracts;

-- Similarity coverage
SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_similarity IS NOT NULL;

-- NLRB decay verification
SELECT AVG(score_nlrb) FROM mv_unified_scorecard WHERE score_nlrb IS NOT NULL;
-- Should be ~2.61 after decay fix. Was 6.20 before.

-- Factors distribution
SELECT factors_available, COUNT(*), 
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM mv_unified_scorecard GROUP BY factors_available ORDER BY factors_available;
```

### 1B: Priority Tier Deep Dive

```sql
-- Tier counts
SELECT tier, COUNT(*) FROM mv_unified_scorecard GROUP BY tier;

-- Any Priority with fewer than 3 factors?
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE tier = 'Priority' AND factors_available < 3;

-- Top 20 Priority employers
SELECT employer_name, state, overall_score, factors_available,
       score_osha, score_nlrb, score_whd, score_contracts,
       score_union_density, score_size, score_similarity, score_industry_growth
FROM mv_unified_scorecard WHERE tier = 'Priority' 
ORDER BY overall_score DESC LIMIT 20;

-- Priority employers with zero enforcement activity
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE tier = 'Priority' 
AND score_osha IS NULL AND score_nlrb IS NULL AND score_whd IS NULL;
```

### 1C: Score Distribution

```sql
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
  END as score_bucket, COUNT(*) as count
FROM mv_unified_scorecard GROUP BY 1 ORDER BY 1;
```

### 1D: Junk Record Detection

```sql
SELECT employer_name, state, overall_score, tier, factors_available
FROM mv_unified_scorecard
WHERE employer_name IN ('Employer Name', 'Company Lists', 'M1', 'Test', 'N/A', 'TBD', 'Unknown')
   OR LENGTH(employer_name) <= 2
   OR employer_name ~* '(pension benefit|federal agency|department of|city of|state of|county of|school district)'
ORDER BY overall_score DESC LIMIT 30;

SELECT COUNT(*) FROM mv_unified_scorecard WHERE LENGTH(employer_name) <= 3;
```

---

## Area 2: Match Quality Post-Hardening

### 2A: Stale OSHA Matches

```sql
-- OSHA Splink matches below the 0.70 threshold still active?
SELECT COUNT(*) FROM unified_match_log 
WHERE source_system = 'osha' AND status = 'active' 
AND match_method LIKE '%SPLINK%'
AND (evidence::json->>'name_similarity')::float < 0.70;
```

### 2B: Match Methods by Source

```sql
SELECT source_system, match_method, COUNT(*), 
       AVG(confidence_score) as avg_conf,
       MIN(confidence_score) as min_conf
FROM unified_match_log WHERE status = 'active'
GROUP BY source_system, match_method 
ORDER BY source_system, COUNT(*) DESC;
-- Look for old methods: 'NAME_STATE' vs new 'NAME_STATE_EXACT'
-- Look for 'SPLINK_PROB' (old) vs 'FUZZY_SPLINK_ADAPTIVE' (new)
```

### 2C: Source Match Rates

```sql
SELECT source_system, 
       COUNT(*) FILTER (WHERE status = 'active') as active,
       COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
       COUNT(*) FILTER (WHERE status = 'superseded') as superseded,
       COUNT(*) as total
FROM unified_match_log GROUP BY source_system ORDER BY active DESC;
```

### 2D: Missing Employer Targets

```sql
-- Previous audit found 46,627 active matches pointing to non-existent F7 IDs
SELECT COUNT(*) FROM unified_match_log uml
WHERE uml.status = 'active'
AND NOT EXISTS (
  SELECT 1 FROM f7_employers_deduped f WHERE f.employer_id = uml.f7_employer_id
);
```

### 2E: 20-Match Accuracy Sample

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

For each: judge correct/wrong/uncertain and explain why.

---

## Area 3: Research Agent Verification

### 3A: Where Is the Output?

```sql
SELECT tablename FROM pg_tables 
WHERE schemaname = 'public' AND tablename LIKE '%research%';
```

Also check for files in project directories. Find where 96 runs of output are stored.

### 3B: Quality Assessment

Read 5 research agent outputs. For each:
- Is the information specific and useful, or generic/boilerplate?
- Does the agent cite specific sources?
- Is the 7.93/10 quality score from real evaluation or self-assessment?
- Are results connected to employer profiles?

### 3C: Integration Check

- Can a user access research results from the employer profile?
- Is there an API endpoint for research results?
- Do findings feed into scoring?

---

## Area 4: CorpWatch SEC EDGAR Import

### 4A: Table Inventory

```sql
-- Find CorpWatch/SEC tables and their sizes
SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename)) as size,
       n_live_tup as rows
FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE t.schemaname = 'public' 
AND (tablename LIKE '%corpwatch%' OR tablename LIKE '%cw_%')
ORDER BY pg_total_relation_size('public.'||tablename) DESC;
```

### 4B: Integration Check

- Are these tables linked to the core employer list?
- How many CorpWatch entities match to F7 employers?
- Is any CorpWatch data used in scoring or visible in the frontend?
- What % of the 14.7M rows is actually useful?

---

## Area 5: NLRB Data Quality Post-Cleanup

### 5A: Participant Data Status

```sql
SELECT COUNT(*) FROM nlrb_participants;

-- How many still have junk data?
SELECT COUNT(*) FROM nlrb_participants 
WHERE state = 'Charged Party Address State' OR city LIKE '%Address%';
```

### 5B: Proximity Calculation Source — CRITICAL

Read `scripts/scoring/build_unified_scorecard.py` and trace the NLRB factor calculation. Report exactly which tables it queries. If it uses `nlrb_participants`, does it reference the cleaned data or junk fields?

---

## Area 6: Membership Numbers Paradox

```sql
-- State-by-state totals
SELECT state, SUM(bargaining_unit_size) as total
FROM f7_union_employer_relations r
JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
GROUP BY state ORDER BY total DESC LIMIT 20;

-- Overall total
SELECT SUM(bargaining_unit_size) FROM f7_union_employer_relations;

-- Is the broken view still broken?
SELECT COUNT(*), SUM(members) FROM v_union_members_deduplicated;
```

---

## Area 7: Incomplete Source Re-runs

```sql
-- 990 status
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = '990' 
GROUP BY match_method, status ORDER BY match_method, status;

-- WHD status
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = 'whd' 
GROUP BY match_method, status ORDER BY match_method, status;

-- SAM status
SELECT match_method, status, COUNT(*) 
FROM unified_match_log WHERE source_system = 'sam' 
GROUP BY match_method, status ORDER BY match_method, status;
```

For each: how many employers are affected? Could stale matches produce wrong scores?

---

## Area 8: Over-Merge and Under-Merge

```sql
-- Largest employer name groups
SELECT employer_name, state, COUNT(*) as group_size
FROM f7_employers_deduped
GROUP BY employer_name, state HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC LIMIT 20;

-- Specific problems from previous audit
SELECT employer_name, COUNT(*) FROM f7_employers_deduped
WHERE employer_name ILIKE '%construction%inc%'
   OR employer_name ILIKE '%building service%'
   OR employer_name ILIKE '%pta%congress%'
GROUP BY employer_name HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC;
```

---

## Area 9: Database Health

```sql
-- Empty tables
SELECT tablename FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE t.schemaname = 'public' AND s.n_live_tup = 0;

-- Database size
SELECT pg_size_pretty(pg_database_size('olms_multiyear'));

-- Top 20 largest tables
SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename)) as size,
       n_live_tup as rows
FROM pg_tables t
JOIN pg_stat_user_tables s ON t.tablename = s.relname
WHERE t.schemaname = 'public'
ORDER BY pg_total_relation_size('public.'||tablename) DESC LIMIT 20;

-- Check for nlrb_participants.case_number index
SELECT indexname FROM pg_indexes 
WHERE tablename = 'nlrb_participants' AND indexdef LIKE '%case_number%';

-- Freshness table
SELECT * FROM data_source_freshness ORDER BY source_name;
```

---

## Area 10: API Data Verification

```sql
-- Profile data for a known employer
SELECT * FROM mv_unified_scorecard WHERE employer_name ILIKE '%kaiser%' LIMIT 5;

-- Master stats query (was 4-12 seconds slow)
EXPLAIN ANALYZE SELECT COUNT(*) FROM master_employers;

-- Employer search view status
SELECT COUNT(*) FROM mv_employer_search;
```

---

# OUTPUT FORMAT

Structure your report as:

1. **Executive Summary** (5-10 sentences — honest state of the platform)
2. **Shared Overlap Zone Answers** (all 10, labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-10, with SQL evidence for every claim)
4. **Surprise Findings** (anything discovered that wasn't asked about)
5. **Previous Audit Follow-Up** (which of the 20 investigation questions were addressed)
6. **Recommended Priority List** (top 10 things to fix, with effort estimates)
