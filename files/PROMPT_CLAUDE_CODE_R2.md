# Claude Code — Deep Investigation Round 2
## February 26, 2026

---

## CONTEXT

You just completed a thorough audit of this platform (AUDIT_CLAUDE_CODE_2026_02_25.md). This is a follow-up investigation that digs deeper into the most important unresolved questions from that audit and from the three-audit synthesis.

You have direct database access (`olms_multiyear`, localhost:5432, user `postgres`). Your job is the same as before: run actual SQL, show actual numbers, and be honest about what you find.

**Context files you should have:**
- Your own audit report (AUDIT_CLAUDE_CODE_2026_02_25.md)
- THREE_AUDIT_SYNTHESIS_2026_02_26.md — the synthesis of all three audits
- SCORING_SPECIFICATION.md — how scoring is supposed to work
- PROJECT_STATE.md — current platform state

**Rules (same as before):**
1. Show SQL and results for every claim.
2. Say "I didn't check this" rather than guess.
3. Do NOT fix anything — document only.

---

## Investigation 1: The Backtest — Does the Score Predict Anything?

This is the single most important open question in the entire project.

The previous audit found that Priority captured only 125 NLRB election wins while Low captured 392 — three times more. If the scoring system can't predict real organizing activity better than random chance, it needs fundamental changes.

**Step 1: Build the comparison dataset.**

```sql
-- For every NLRB election with a known outcome, find the employer's current score and tier
-- You'll need to join nlrb_elections → nlrb_participants → unified_match_log → mv_unified_scorecard
-- An election "win" = status showing union victory (check what values exist in the status/result columns)
```

First, explore what election outcome data looks like:
- What columns in `nlrb_elections` indicate win/loss?
- How many elections have clear outcomes (win vs loss vs withdrawn vs other)?
- What's the date range?

**Step 2: Match elections to scored employers.**

- How many elections can you link to a scored F7 employer? (Through nlrb_participants → unified_match_log)
- How many elections have NO link to a scored employer? (This is the "invisible wins" problem)

**Step 3: Score vs outcome analysis.**

For elections that DO link to scored employers:
- What's the win rate by tier? (Priority, Strong, Promising, Moderate, Low)
- What's the win rate by score bucket? (0-2, 2-4, 4-6, 6-8, 8-10)
- What's the win rate by number of factors available?
- Which individual factors correlate most with wins? (Run each factor separately)

**Step 4: The critical question.**

Is there ANY positive correlation between score and election win rate? If Priority employers win at 60% and Low employers win at 40%, the system works directionally even if imperfectly. If Priority wins at 35% and Low wins at 50%, the system is actively misleading.

**Step 5: Factor-level analysis.**

For each of the 8 factors, check: do employers with higher values of this factor win elections at higher rates? This tells us which factors actually predict success and which are noise or inversely correlated. Report a simple table:

| Factor | Employers w/ data + elections | Win rate when factor > 5 | Win rate when factor ≤ 5 | Difference |
|--------|-------------------------------|--------------------------|--------------------------|------------|

This is the evidence we need to decide whether to reweight, drop, or redesign factors.

---

## Investigation 2: Fuzzy Match Quality by Similarity Band

Your audit tested the 0.70-0.80 band and found 75% false positives. We need the same analysis at higher thresholds to pick the right cutoff.

**Step 1: Count active fuzzy matches by similarity band.**

```sql
SELECT 
  CASE 
    WHEN (evidence::json->>'name_similarity')::float >= 0.95 THEN '0.95-1.00'
    WHEN (evidence::json->>'name_similarity')::float >= 0.90 THEN '0.90-0.95'
    WHEN (evidence::json->>'name_similarity')::float >= 0.85 THEN '0.85-0.90'
    WHEN (evidence::json->>'name_similarity')::float >= 0.80 THEN '0.80-0.85'
    WHEN (evidence::json->>'name_similarity')::float >= 0.75 THEN '0.75-0.80'
    WHEN (evidence::json->>'name_similarity')::float >= 0.70 THEN '0.70-0.75'
    ELSE 'below 0.70'
  END as sim_band,
  COUNT(*) as match_count
FROM unified_match_log
WHERE status = 'active' 
AND match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
AND evidence::json->>'name_similarity' IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

This tells us how many matches are at risk in each band.

**Step 2: Spot check 10 matches in each of these bands:**
- 0.80-0.85
- 0.85-0.90
- 0.90-0.95

For each match, pull the source name and matched employer name. Judge: correct, wrong, or uncertain. Use the same format as your OQ2 analysis.

```sql
-- Template for each band (adjust the range):
SELECT source_system, match_method,
       evidence::json->>'source_name' as source_name,
       evidence::json->>'name_similarity' as name_sim,
       f.employer_name as matched_to, f.state
FROM unified_match_log uml
JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
WHERE uml.status = 'active'
AND uml.match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
AND (evidence::json->>'name_similarity')::float BETWEEN 0.80 AND 0.85
ORDER BY RANDOM() LIMIT 10;
```

**Step 3: Summary table.**

| Band | Active matches | Sampled | Correct | Wrong | Uncertain | Est. FP rate |
|------|---------------|---------|---------|-------|-----------|-------------|

This gives us the evidence to pick a threshold. If 0.85-0.90 is 90% correct and 0.80-0.85 is 50% correct, we know 0.85 is the right floor.

**Step 4: Blast radius of cleanup.**

If we deactivate all fuzzy matches below 0.85 (or whatever threshold the spot check suggests):
- How many employers lose their only OSHA match?
- How many lose their only WHD match?
- How many lose their only contracts match?
- How many change tiers?
- How many lose enough factors to drop below the Priority/Strong minimum of 3?

This tells us the cost of the cleanup before we do it.

---

## Investigation 3: What Would Priority Look Like With Enforcement?

The synthesis proposes requiring at least 1 enforcement factor (OSHA, NLRB, or WHD) for Priority tier. Before we decide, we need to see what the result looks like.

**Scenario A: Current Priority (baseline)**
```sql
SELECT COUNT(*) FROM mv_unified_scorecard WHERE score_tier = 'Priority';
-- And: top 20 by score
```

**Scenario B: Priority requires ≥ 1 enforcement factor**
```sql
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE score_tier = 'Priority'
AND (score_osha IS NOT NULL OR score_nlrb IS NOT NULL OR score_whd IS NOT NULL);

-- Top 20 under this rule:
SELECT employer_name, state, weighted_score, factors_available,
       score_osha, score_nlrb, score_whd, score_contracts,
       score_union_proximity, score_size, score_industry_growth, score_financial
FROM mv_unified_scorecard
WHERE score_tier = 'Priority'
AND (score_osha IS NOT NULL OR score_nlrb IS NOT NULL OR score_whd IS NOT NULL)
ORDER BY weighted_score DESC LIMIT 20;
```

**Scenario C: Priority requires ≥ 2 enforcement factors**
```sql
SELECT COUNT(*) FROM mv_unified_scorecard 
WHERE score_tier = 'Priority'
AND (CASE WHEN score_osha IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN score_nlrb IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN score_whd IS NOT NULL THEN 1 ELSE 0 END) >= 2;

-- Top 20 under this rule
```

**Scenario D: Priority requires ≥ 1 enforcement AND ≥ 4 total factors**
```sql
-- Same pattern but with both conditions
```

For each scenario, report:
- How many employers qualify
- Top 20 names, states, scores, and factor breakdown
- Your assessment: would an organizer find this list useful?

---

## Investigation 4: The score_size Problem

Average score_size is 1.48 at 3x weight. This investigation figures out why and what alternatives look like.

**Step 1: Understand the current distribution.**
```sql
SELECT 
  CASE 
    WHEN score_size >= 9 THEN '9-10 (500+ workers)'
    WHEN score_size >= 7 THEN '7-9'
    WHEN score_size >= 5 THEN '5-7'
    WHEN score_size >= 3 THEN '3-5'
    WHEN score_size >= 1 THEN '1-3'
    ELSE '0-1 (<15 workers)'
  END as size_bucket, COUNT(*)
FROM mv_unified_scorecard GROUP BY 1 ORDER BY 1;
```

**Step 2: What's the underlying size data?**
```sql
-- What column does score_size actually use?
-- Check: bargaining_unit_size from f7_union_employer_relations?
-- Or: consolidated_workers from employer groups?
-- Or: something else?

-- Distribution of the raw size numbers:
SELECT 
  CASE 
    WHEN raw_size >= 1000 THEN '1000+'
    WHEN raw_size >= 500 THEN '500-999'
    WHEN raw_size >= 100 THEN '100-499'
    WHEN raw_size >= 50 THEN '50-99'
    WHEN raw_size >= 15 THEN '15-49'
    ELSE '<15'
  END as size_range, COUNT(*)
FROM (
  -- Replace with actual column/table used for size
  SELECT bargaining_unit_size as raw_size FROM f7_union_employer_relations
) sub GROUP BY 1 ORDER BY 1;
```

**Step 3: What would consolidated_workers look like as an alternative?**
```sql
-- How many employers have consolidated_workers data?
-- What's the distribution?
-- What would score_size look like if we used consolidated_workers instead?

-- Check if the field exists and what it contains:
SELECT COUNT(*) FILTER (WHERE consolidated_workers IS NOT NULL) as has_data,
       AVG(consolidated_workers) FILTER (WHERE consolidated_workers IS NOT NULL) as avg_size,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY consolidated_workers) 
         FILTER (WHERE consolidated_workers IS NOT NULL) as median_size
FROM mv_unified_scorecard;
```

**Step 4: Weight sensitivity.**

What happens to the score distribution and tier composition if score_size weight changes from 3x to 1x? You can simulate this:

```sql
-- Simulated weighted score with size at 1x instead of 3x
-- Compare to current tier distribution
-- How many employers change tiers?
```

---

## Investigation 5: Research Agent Linkage Problem

76% of research runs have no employer_id. Why?

```sql
-- Runs WITH employer_id
SELECT rr.id, rr.employer_name, rr.employer_id, rr.overall_quality_score,
       f.employer_name as f7_name
FROM research_runs rr
LEFT JOIN f7_employers_deduped f ON f.employer_id = rr.employer_id
WHERE rr.employer_id IS NOT NULL
ORDER BY rr.created_at DESC LIMIT 10;

-- Runs WITHOUT employer_id
SELECT rr.id, rr.employer_name, rr.overall_quality_score, rr.created_at
FROM research_runs rr
WHERE rr.employer_id IS NULL
ORDER BY rr.created_at DESC LIMIT 10;
```

Questions to answer:
- Are the unlinked runs about employers that exist in F7 but just weren't matched? (Check by name)
- Are they about employers NOT in F7 at all?
- Is there a pattern (all early runs unlinked, later ones linked? Or random?)
- For the 16 research_score_enhancements: why don't they show up in the MV? Trace the JOIN.

```sql
-- Check if the MV join condition matches
SELECT rse.employer_id, rse.quality_score,
       mvs.employer_id as mv_employer_id, mvs.has_research
FROM research_score_enhancements rse
LEFT JOIN mv_unified_scorecard mvs ON mvs.employer_id = rse.employer_id
LIMIT 16;
```

---

## Investigation 6: Employers That Flip Tiers After Cleanup

Before we clean fuzzy matches, we need to know the consequences.

**Simulate deactivating all fuzzy matches below 0.85:**

```sql
-- Step 1: Which employers have ONLY fuzzy matches as their link to OSHA/WHD/SAM data?
-- (If we remove fuzzy matches, these employers lose that data entirely)

-- Employers whose only OSHA connection is a fuzzy match below 0.85:
WITH fuzzy_osha AS (
  SELECT DISTINCT target_id as employer_id
  FROM unified_match_log
  WHERE source_system = 'osha' AND status = 'active'
  AND match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
  AND (evidence::json->>'name_similarity')::float < 0.85
),
all_osha AS (
  SELECT DISTINCT target_id as employer_id
  FROM unified_match_log
  WHERE source_system = 'osha' AND status = 'active'
  AND NOT (match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
           AND (evidence::json->>'name_similarity')::float < 0.85)
)
SELECT COUNT(*) as employers_losing_all_osha
FROM fuzzy_osha fo
WHERE NOT EXISTS (SELECT 1 FROM all_osha ao WHERE ao.employer_id = fo.employer_id);
```

Repeat for WHD, SAM, and other sources. Then:

```sql
-- How many of these employers are currently in Priority or Strong?
-- How many would drop below 3 factors?
```

---

## OUTPUT FORMAT

For each investigation:
1. **The question** (one sentence)
2. **The SQL** (actual queries run)
3. **The data** (actual results)
4. **The interpretation** (what this means in plain language)
5. **The recommendation** (what to do based on what you found)

End with a summary table of all recommendations and how they affect the Tier 0-1 roadmap items.
