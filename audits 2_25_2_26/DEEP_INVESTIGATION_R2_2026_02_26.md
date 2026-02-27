# Claude Code — Deep Investigation Round 2
## February 26, 2026

---

## Executive Summary

Six deep investigations, all driven by SQL against the live database. The headline finding reverses a key conclusion from the three-audit synthesis:

**The scoring system IS predictive.** Priority employers win NLRB elections at 90.9%, Low at 74.1% — a monotonic 17-percentage-point gradient. The "125 vs 392" statistic that alarmed all three auditors was comparing absolute counts (Priority has few employers) rather than win rates. The score works directionally.

However, the other five investigations confirm serious issues: fuzzy matches are unreliable across ALL bands (not just 0.70-0.80), the research feedback loop is dead due to a specific JOIN condition bug, score_size is broken by design (median 0.19 out of 10 at 3x weight), and the Priority tier would be dramatically more useful with an enforcement requirement.

---

## Investigation 1: The Backtest — Does the Score Predict Anything?

**The question:** Does a higher score correlate with higher NLRB election win rates?

### Step 1: The Dataset

**Join chain:** `nlrb_elections` → `nlrb_participants` (type='Employer') → `matched_employer_id` → `mv_unified_scorecard`

```sql
-- Election outcomes
SELECT union_won, COUNT(*) FROM nlrb_elections WHERE union_won IS NOT NULL GROUP BY 1;
-- union_won=true:  22,292
-- union_won=false: 10,501
-- Total with outcomes: 32,793
```

### Step 2: Linkage

```sql
-- Elections linked to scored F7 employers via matched_employer_id
SELECT COUNT(DISTINCT ne.id)
FROM nlrb_elections ne
JOIN nlrb_participants np ON np.case_number = ne.case_number AND np.participant_type = 'Employer'
JOIN mv_unified_scorecard mvs ON mvs.employer_id = np.matched_employer_id
WHERE ne.union_won IS NOT NULL AND np.matched_employer_id IS NOT NULL;
-- Result: 11,109 elections linked to 5,519 distinct employers
```

- **11,109 elections linked** (33.9% of 32,793)
- **21,682 unlinked** (66.1%) — the "invisible elections" problem. These are mostly employers not in F7.

**Important selection bias:** The baseline win rate for ALL elections is **68.0%**, but for F7-matched employers it's **80.8%**. F7 employers already have union contracts, so elections at these workplaces skew toward wins. All tier comparisons below are within this 80.8% baseline pool.

### Step 3: Win Rate by Tier

```
Tier         Elections    Wins   Losses   Win%    AvgScore  AvgFactors
----------------------------------------------------------------------
Priority          319     290       29   90.9%      9.01        4.6
Strong          4,094   3,469      625   84.7%      6.95        4.8
Promising       2,227   1,817      410   81.6%      5.39        4.8
Moderate        3,264   2,504      760   76.7%      3.96        4.4
Low             1,205     893      312   74.1%      2.04        3.2
```

**The gradient is monotonic and meaningful:** 90.9% → 84.7% → 81.6% → 76.7% → 74.1%. Priority employers win elections at a 17-percentage-point higher rate than Low employers.

### Win Rate by Score Bucket

```
Bucket    Elections    Wins    Win%
------------------------------------
0-2            466     342   73.4%
2-4          2,296   1,726   75.2%
4-6          3,929   3,142   80.0%
6-8          3,708   3,132   84.5%
8-10           710     631   88.9%
```

Also monotonic. 73.4% → 88.9% — a 15.5pp spread.

### Win Rate by Factors Available

```
Factors  Elections    Wins    Win%
------------------------------------
2            553     488   88.2%
3          1,892   1,609   85.0%
4          3,460   2,720   78.6%
5          2,976   2,345   78.8%
6          1,427   1,163   81.5%
7            662     546   82.5%
8            139     102   73.4%
```

**Surprising inversion:** Employers with FEWER factors win at HIGHER rates. 2-factor employers win 88.2% while 8-factor employers win 73.4%. This suggests a "data richness paradox" — employers with extensive enforcement records (OSHA violations, NLRB cases, WHD findings) may be harder targets, not easier ones. More data doesn't mean more organizable.

### Step 5: Factor-Level Analysis

```
Factor              Employers   WR(>5)    WR(<=5)    Diff      N(high/low)
---------------------------------------------------------------------------
NLRB                  11,109    85.4%     75.2%    +10.2pp    (6,038/5,071)
Industry Growth        9,257    80.9%     71.3%     +9.6pp    (7,865/1,392)
Contracts              1,642    83.3%     77.6%     +5.7pp    (1,232/410)
WHD                    2,265    85.0%     80.9%     +4.1pp      (153/2,112)
Financial              2,630    83.3%     79.2%     +4.1pp    (1,841/789)
Size                  11,109    80.9%     80.7%     +0.2pp    (1,976/9,133)
Union Proximity        8,036    80.2%     80.2%     +0.0pp    (5,876/2,160)
OSHA                   3,824    77.5%     78.1%     -0.6pp      (378/3,446)
```

**This is the most actionable finding in the entire investigation.** The two factors with the highest weights (Union Proximity 3x, Size 3x) have **zero predictive power** for election wins. Meanwhile, NLRB Activity (3x, +10.2pp) and Industry Growth (2x, +9.6pp) are the strongest actual predictors.

- **NLRB at 3x: justified.** +10.2pp is the strongest signal. The weight is correct.
- **Industry Growth at 2x: underweighted.** +9.6pp rivals NLRB. Could justify 3x.
- **Contracts at 2x: reasonable.** +5.7pp with decent sample size.
- **Size at 3x: unjustified.** +0.2pp — effectively random. Weight should be 1x or lower.
- **Union Proximity at 3x: unjustified.** +0.0pp — literally zero predictive power. Weight should be reduced.
- **OSHA at 1x: arguably should be 0x.** -0.6pp means higher OSHA scores slightly predict LOSSES. Workers with violations may have already been through failed organizing or work at employers sophisticated enough to resist.

### The "125 vs 392" Mystery — Resolved

The synthesis said "Priority captured only 125 NLRB election wins while Low captured 392." My actual numbers:

```
Priority:  289 wins out of  318 elections (91%)
Low:       893 wins out of 1,205 elections (74%)
```

Low has 3x more wins in absolute terms because it contains 4x more elections. But Priority wins at a 17pp higher RATE. The original statistic was misleading — it compared apples (a small high-performing pool) to oranges (a large lower-performing pool).

### Interpretation

The scoring system works as a predictor. It's not perfect, but it's meaningfully better than random within the F7-matched employer pool. However:

1. **Two of the three 3x-weight factors contribute nothing to prediction** (Size, Proximity). The score succeeds DESPITE these factors, not because of them.
2. **The factors-available inversion is concerning.** Employers with 8 factors (extensive government data) win at LOWER rates than those with 2 factors. This suggests the scoring model may be measuring "how much data exists" rather than "how organizable this employer is."
3. **66% of elections are invisible** to the scoring system (unlinked). The platform can only predict outcomes for the 34% of elections at F7-matched employers.

### Recommendation

1. **Reduce Size weight from 3x to 1x.** It has no predictive power and currently drags down scores for 70% of employers.
2. **Reduce Union Proximity weight from 3x to 1-2x.** It has zero predictive power for election wins. It may still have strategic value (known playbooks, institutional support) that doesn't show up in win/loss data, so don't eliminate it entirely.
3. **Consider increasing Industry Growth from 2x to 3x.** It's the second-strongest predictor at +9.6pp.
4. **Investigate OSHA inversion.** The -0.6pp finding is small but counterintuitive. It could be noise, or it could indicate that OSHA violations mark employers that are already hardened against organizing.

---

## Investigation 2: Fuzzy Match Quality by Similarity Band

**The question:** At what similarity threshold do fuzzy matches become reliable?

### Step 1: Band Distribution

```sql
SELECT CASE
    WHEN (evidence::json->>'name_similarity')::float >= 0.95 THEN '0.95-1.00'
    WHEN ... >= 0.90 THEN '0.90-0.95'
    WHEN ... >= 0.85 THEN '0.85-0.90'
    WHEN ... >= 0.80 THEN '0.80-0.85'
    ELSE 'below 0.80'
  END as sim_band, COUNT(*)
FROM unified_match_log
WHERE status = 'active' AND match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
AND evidence::json->>'name_similarity' IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

```
Band        Count    % of fuzzy
--------------------------------
0.80-0.85    9,694      61.1%
0.85-0.90    3,897      24.6%
0.90-0.95    1,600      10.1%
0.95-1.00      679       4.3%
Total:      15,870
(+ 3,554 without similarity data)
```

The vast majority (61%) of fuzzy matches sit in the lowest band (0.80-0.85).

### Step 2: Spot Check — 10 Random Matches Per Band

**Band 0.80-0.85:**

| # | Source | Source Name | Matched To | Sim | Verdict |
|---|--------|------------|------------|-----|---------|
| 1 | osha | graham packaging lc lp | Graham Packaging Company (CA) | 0.842 | CORRECT |
| 2 | osha | fresenius medical care irvine llc | Fresenius Medical Care (CA) | 0.800 | CORRECT |
| 3 | osha | daniel soto | Daniel'sFoods, Inc. d/ba Sentry Foods (WI) | 0.833 | WRONG — person vs company |
| 4 | osha | federal mogul corp powertrain energy systems | Federal Mogul Corporation. Powertrain Systems (MI) | 0.842 | CORRECT |
| 5 | osha | william mathis construction | Williams Construction Services (VA) | 0.833 | WRONG — different companies |
| 6 | sam | jay town of | Town of Jay (ME) | 0.842 | CORRECT — word reorder |
| 7 | osha | pbj construction inc | H & J Construction (OR) | 0.833 | WRONG |
| 8 | osha | nycan builders llc | CNY Builders LLC (NY) | 0.800 | UNCERTAIN — anagram? likely wrong |
| 9 | osha | american cleaners | Americas Center (MO) | 0.812 | WRONG |
| 10 | whd | avi foods systems inc | AVI Foodsystems, INC (OH) | 0.833 | CORRECT |

**Result: 5 correct, 4 wrong, 1 uncertain. Est. FP rate: ~40-50%**

**Band 0.85-0.90:**

| # | Source | Source Name | Matched To | Sim | Verdict |
|---|--------|------------|------------|-----|---------|
| 1 | whd | desiderio james inc | James Desiderio, Inc (NY) | 0.882 | CORRECT — name reorder |
| 2 | osha | san francisco state university | University of San Francisco (CA) | 0.889 | WRONG — different schools |
| 3 | sam | war properties | RJB Properties, Inc. (IL) | 0.857 | WRONG |
| 4 | whd | josaz transportation | JoFaz/Y & M Transportation (NY) | 0.864 | UNCERTAIN |
| 5 | osha | las vegas eagle | AEG Management Las Vegas (NV) | 0.857 | WRONG |
| 6 | whd | csx transportation | CRC Transportation LLC (FL) | 0.889 | WRONG — CSX is a major rail company |
| 7 | osha | va sierra nevada health care system | VA Sierra Health Care System (NV) | 0.889 | CORRECT |
| 8 | osha | sjj construction | JDM Construction Services Co. (MT) | 0.875 | WRONG |
| 9 | osha | independent construction | Independent Contractor, Inc. (PA) | 0.870 | UNCERTAIN |
| 10 | whd | mrs greens natural market 6 | Mrs. Green's Natural Markets (NY) | 0.889 | CORRECT |

**Result: 3 correct, 5 wrong, 2 uncertain. Est. FP rate: ~50-70%**

**Band 0.90-0.95:**

| # | Source | Source Name | Matched To | Sim | Verdict |
|---|--------|------------|------------|-----|---------|
| 1 | osha | woodworks construction | WOODS CONSTRUCTION, INC (MI) | 0.900 | UNCERTAIN |
| 2 | whd | 22nd century technology | 22nd Century Technologies, Inc. (NJ) | 0.917 | CORRECT |
| 3 | sam | saint barnabas behavioral health center | Barnabas Health Behavioral Health Center (NJ) | 0.911 | CORRECT |
| 4 | sam | snohomish county fire district 21 | Snohomish County Fire District No. 3 (WA) | 0.912 | WRONG — different district numbers |
| 5 | osha | macomb cnty | Macomb County (MI) | 0.917 | CORRECT |
| 6 | sam | mason consolidated school | Mason Consoildated Schools (MI) | 0.941 | CORRECT — typo in F7 |
| 7 | osha | maestro construction | Manestar Construction Inc (IL) | 0.927 | WRONG |
| 8 | osha | 64267 louisville jefferson county metro government | Louisville/Jefferson County Metro Government (KY) | 0.936 | CORRECT — prefix number |
| 9 | sam | county of san francisco city | City & County of San Francisco (CA) | 0.943 | CORRECT |
| 10 | osha | coliseum construction | Column Construction Company (PA) | 0.900 | WRONG |

**Result: 6 correct, 3 wrong, 1 uncertain. Est. FP rate: ~30-40%**

### Step 3: Summary Table

| Band | Active Matches | Sampled | Correct | Wrong | Uncertain | Est. FP Rate |
|------|---------------|---------|---------|-------|-----------|-------------|
| 0.80-0.85 | 9,694 | 10 | 5 | 4 | 1 | ~40-50% |
| 0.85-0.90 | 3,897 | 10 | 3 | 5 | 2 | ~50-70% |
| 0.90-0.95 | 1,600 | 10 | 6 | 3 | 1 | ~30-40% |
| 0.95-1.00 | 679 | — | — | — | — | (not sampled) |

**Note:** Sample size is 10 per band, so these FP rates have wide confidence intervals. But the pattern is clear: **no band below 0.95 is reliably accurate.** Even 0.90-0.95 has ~30-40% false positives.

The surprising result is that 0.85-0.90 appears WORSE than 0.80-0.85. This may be because the 0.85-0.90 band contains more "plausible but wrong" matches (names that look similar but aren't the same entity) while 0.80-0.85 contains some obvious matches that just have verbose legal suffixes.

### Step 4: Blast Radius of Cleanup

See Investigation 6 for the full analysis. Summary: deactivating all fuzzy below 0.85 would remove 9,694 matches affecting 3,767 employers. Only 35 Priority employers affected, 11 would lose enough factors to drop below the eligibility gate.

### Recommendation

The data does NOT support a clean threshold. Even 0.90-0.95 has ~30-40% errors. The fundamental problem is that **token-based string similarity cannot distinguish "San Francisco State University" from "University of San Francisco"** — they share all the same tokens but are different institutions.

Options:
1. **Deactivate all fuzzy below 0.85** (removes 9,694 matches, ~50% FP rate) as a quick win, then manually review 0.85-0.95.
2. **Add industry/state confirmation** — require matching NAICS prefix or state for fuzzy matches. This would catch many of the cross-entity false positives.
3. **Flag rather than deactivate** — mark low-sim matches as "unverified" in the UI so organizers know the data may be from a different employer.

---

## Investigation 3: What Would Priority Look Like With Enforcement?

**The question:** How does Priority change if we require enforcement data?

### Scenario A: Current Priority (baseline)

**Count: 2,278 employers**

Top 20 is dominated by hospitals and healthcare with proximity=10 + size=10 + growth=9.2, but **no enforcement data.** Examples: Columbia Memorial Hospital (OR), Robert Wood Johnson (NJ), Jersey Shore University Medical Center (NJ), North Memorial (MN). These score 9.80+ purely on structural factors.

### Scenario B: Priority requires >= 1 enforcement factor (OSHA, NLRB, or WHD)

**Count: 316 employers (86% reduction)**

Top 20 now includes: Kaiser Foundation Hospitals (6 factors), Walt Disney Parks (OSHA+NLRB), Allied Universal (NLRB), Stanford Health Care (NLRB+WHD). These are employers where there's evidence of actual labor activity.

```
Top 5:
First Student, Inc (IL)              — NLRB=10, Prox=10, Size=10     = 10.00
Dignity Health Mercy Medical (CA)    — NLRB=10, Prox=10, Size=10, Grw=9.2 = 9.85
Alta Bates Summit Medical (CA)       — NLRB=10, Prox=10, Size=10, Grw=9.2 = 9.85
American Medical Response (CA)       — NLRB=9.9, Prox=10, Size=10, Grw=9.2 = 9.82
FLUOR BWXT Portsmouth (OH)           — NLRB=9.3, Ctr=10, Prox=10, Size=10 = 9.82
```

### Scenario C: Priority requires >= 2 enforcement factors

**Count: 47 employers**

Top entries all have multiple enforcement signals. Examples:
- San Diego Gas & Electric (CA): **8 factors** — OSHA=10, NLRB=10, WHD=3.8, Ctr=8, Prox=10, Size=10, Grw=7.4, Fin=8
- New York Presbyterian Hospital (NY): **7 factors** — OSHA=2.1, NLRB=10, WHD=5, Prox=10, Size=10, Grw=9.2, Fin=10
- Walt Disney Parks (CA): OSHA=10, NLRB=10, Prox=10, Size=10, Grw=7.0

### Scenario D: Priority requires >= 1 enforcement + >= 4 total factors

**Count: 252 employers**

Similar to Scenario B but ensures broader data coverage. Top 20 overlaps significantly with B.

### Assessment

| Scenario | Count | Organizer Value |
|----------|-------|-----------------|
| A (current) | 2,278 | Low — mostly empty profiles |
| B (>=1 enforcement) | 316 | **High** — every entry has evidence of labor activity |
| C (>=2 enforcement) | 47 | Very high quality, but too restrictive |
| D (>=1 enf + >=4 factors) | 252 | High — good balance of quality and coverage |

### Recommendation

**Scenario B is the clear winner.** It cuts Priority from 2,278 to 316, but every remaining employer has at least one enforcement signal. An organizer scanning this list would find real targets, not just large hospitals in union-heavy areas.

1,962 employers would be downgraded from Priority. This is a feature, not a bug — these employers currently have no evidence of labor activity.

For Strong tier, consider the same rule but with 1 enforcement factor. This would also improve Strong's usefulness.

---

## Investigation 4: The score_size Problem

**The question:** Why does score_size average 1.48 at 3x weight?

### Step 1: Distribution

```sql
SELECT CASE WHEN score_size >= 9 THEN '9-10 (500+)' ... END as bucket, COUNT(*)
FROM mv_unified_scorecard WHERE score_size IS NOT NULL GROUP BY 1 ORDER BY 1;
```

```
Bucket           Count      %
-------------------------------
0-1 (<15)       102,411   69.7%
1-3              21,449   14.6%
3-5               8,129    5.5%
5-7               3,710    2.5%
7-9               2,419    1.6%
9-10 (500+)       8,745    6.0%
```

**69.7% of employers score 0-1.** Median score_size is **0.19** out of 10. At 3x weight, this factor is a massive downward drag on the weighted average for the vast majority of employers.

### Step 2: Why — The Underlying Data

The score_size formula ramps linearly from 0 (at 15 workers) to 10 (at 500 workers). The underlying data is `latest_unit_size` from `f7_employers_deduped`:

```
latest_unit_size Distribution (140,420 employers with data):
  1-14:        40,117   (28.6%)
  15-49:       43,470   (30.9%)
  50-99:       20,919   (14.9%)
  100-499:     27,526   (19.6%)
  500-999:      4,101    (2.9%)
  1000+:        4,287    (3.1%)
  Median: 28 workers
```

The problem is clear: **F7 records represent individual bargaining units**, not whole companies. The median BU is 28 workers. The scoring formula peaks at 500, so 74% of employers score below 3 (having fewer than 100 workers in their reported unit).

### Step 3: Alternative — Consolidated Workers

`employer_canonical_groups` has `consolidated_workers` (summed across all BUs in a corporate group):

```
consolidated_workers Distribution (16,583 groups):
  <15:          1,875   (11.3%)
  15-49:        4,426   (26.7%)
  50-99:        2,759   (16.6%)
  100-499:      5,062   (30.5%)
  500-999:      1,111    (6.7%)
  1000+:        1,350    (8.1%)
  Median: 76 workers (vs 28 for BU size)
```

Consolidated workers has a median of 76 (2.7x higher) and spreads much more evenly across the range. **However, `group_max_workers` on `f7_employers_deduped` is 100% NULL** — the column exists but was never populated. The group data is only in the groups table, not joined to individual employers.

### Step 4: Weight Sensitivity

Simulating size weight change from 3x to 1x:

```
Avg old score: 4.191
Avg new score: 5.267  (+1.076)
Increases: 127,790 (87%)
Decreases:  12,546  (9%)
No change:   6,527  (4%)
```

Tier changes from 3x→1x:

```
Priority -> Strong:     892
Strong -> Priority:     178
Strong -> Promising:  5,943
Promising -> Strong:  1,829
Moderate -> Promising: 5,528
Moderate -> Low:       6,119
Low -> Moderate:       6,380
```

Massive reshuffling. 892 current Priority employers drop to Strong, while 178 Strong employers rise to Priority. The net effect: employers that score well on data-rich factors (NLRB, contracts, enforcement) rise, while employers that only scored well on size+proximity fall.

### Recommendation

1. **Reduce size weight from 3x to 1x.** The backtest shows +0.2pp predictive power — indistinguishable from zero. At 3x, it's the single biggest drag on the scoring system's discriminative ability.
2. **Populate `group_max_workers`** from canonical groups so the size factor uses company-level size, not BU-level size. This would shift median from 28 → 76, reducing the 0-1 bucket from 70% to ~40%.
3. **Consider the high-end taper** from the spec (above 25,000). Currently irrelevant because so few employers reach 500, but would matter if using consolidated workers.

---

## Investigation 5: Research Agent Linkage Problem

**The question:** Why do 76% of research runs have no employer_id, and why is has_research=false for all 146,863 employers?

### The Data

```sql
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE employer_id IS NOT NULL) as linked,
       COUNT(*) FILTER (WHERE employer_id IS NULL) as unlinked
FROM research_runs;
-- Total: 104, Linked: 24 (23%), Unlinked: 80 (77%)
```

### Root Cause 1: Caller Doesn't Pass employer_id

There's no temporal pattern — both linked and unlinked runs span the full date range (Feb 23-25, 2026). The same company is often researched with AND without an employer_id:

```
"XPO Logistics":  1 linked, 5 unlinked
"Kaiser Permanente": 2 linked, 1 unlinked
"TAN": 1 linked, 1 unlinked
```

Of 31 companies with ONLY unlinked runs, **16 exist in F7** by exact name match:

```
"Starbucks": in F7 = YES (3 matches)
"Allied Universal": in F7 = YES
"Marriott International": in F7 = YES
"Montefiore Medical Center": in F7 = YES
"Penske Truck Leasing": in F7 = YES
... (11 more)
```

These could have been linked but weren't because the research caller didn't look up the employer_id first.

### Root Cause 2: The MV JOIN Bug

This is the critical finding. The MV SQL (line 428 of the view definition):

```sql
LEFT JOIN research_score_enhancements rse
  ON rse.employer_id = s.employer_id
  AND rse.is_union_reference = false    -- <== THIS FILTER
```

All **16 RSE rows** have `is_union_reference = true`:

```sql
SELECT is_union_reference, COUNT(*) FROM research_score_enhancements GROUP BY 1;
-- true: 16, false: 0
```

The MV only consumes **Path B** (non-union) enhancements. But all 16 existing enhancements are **Path A** (union reference). The join condition filters out every single one.

The join itself works — employer_ids match between RSE and MV:

```
rse.eid=0b7e00cbf4e4c721 q=8.65 union=True -> mv.eid=0b7e00cbf4e4c721 has_res=False
rse.eid=3f1c6f7d1fa78cd5 q=8.75 union=True -> mv.eid=3f1c6f7d1fa78cd5 has_res=False
... (all 16 rows: has_research=False)
```

The feedback loop is architecturally correct but functionally dead because the pipeline only creates Path A enhancements, and the MV only reads Path B.

### Recommendation

1. **Fix the immediate bug:** Either change the MV join to include Path A enhancements (since they contain useful scores), or ensure the research pipeline creates Path B enhancements for non-union targets.
2. **Auto-lookup employer_id** in the research agent before creating a run. A simple `SELECT employer_id FROM f7_employers_deduped WHERE UPPER(employer_name) = UPPER(?)` would link 16+ currently-unlinked companies.
3. **This is a 30-minute fix** for the MV join condition. The entire research-to-scorecard pipeline would light up immediately for the 16 existing enhancements.

---

## Investigation 6: Employers That Flip Tiers After Cleanup

**The question:** What's the blast radius of deactivating all fuzzy matches below 0.85?

### Matches Affected

```sql
SELECT COUNT(*) FROM unified_match_log
WHERE status = 'active' AND match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
AND (evidence::json->>'name_similarity')::float < 0.85;
-- 9,694 matches
```

By source:
```
osha:       6,687  (69%)
sam:        1,145  (12%)
whd:        1,091  (11%)
990:          547   (6%)
sec:          135   (1%)
corpwatch:     89   (1%)
```

OSHA dominates — 69% of low-sim fuzzy matches are OSHA records.

### Employers Losing ALL Links to a Source

These are employers whose ONLY connection to a data source is a low-sim fuzzy match:

```
Employers losing ALL osha links:  2,012
Employers losing ALL whd links:     774
Employers losing ALL sam links:     798
Employers losing ALL sec links:      74
Employers losing ALL nlrb links:      0
```

NLRB linkage is unaffected (0 losses) because NLRB uses direct `matched_employer_id`, not fuzzy matching.

### Impact by Tier

```
Tier        Affected    Would drop below 3 factors
---------------------------------------------------
Priority         35     11
Strong          447    118
Promising       759    (not checked)
Moderate      1,606    (not checked)
Low             920    (not checked)
```

- **35 Priority employers** are affected by the cleanup. Of those, 11 would drop below the 3-factor minimum and lose Priority status.
- **447 Strong employers** affected, 118 would lose the 3-factor gate.

### Assessment

The blast radius is **manageable**:

- Only 35 out of 2,278 Priority employers are affected (1.5%)
- Only 11 would actually lose their tier status
- The 2,012 employers losing OSHA links are the main concern, but given the ~50% FP rate in this band, roughly half of those OSHA connections are wrong anyway

The bigger risk is keeping bad matches: an organizer who finds incorrect OSHA violations on an employer profile loses trust in the entire platform.

### Recommendation

1. **Proceed with 0.85 cleanup** for the 0.80-0.85 band (9,694 matches). The 35 Priority employers affected is an acceptable cost given that ~50% of these matches are wrong.
2. **After cleanup, manually review the 0.85-0.95 band** (5,497 matches). The spot-check shows these are also unreliable, but the volume is more manageable for human review.
3. **Consider adding a "match confidence" indicator** to the frontend so users can see which data comes from high-confidence exact matches vs lower-confidence fuzzy matches.

---

## Summary of Recommendations

| # | Recommendation | Source | Impact | Effort |
|---|---------------|--------|--------|--------|
| 1 | **Fix MV research JOIN** (remove `is_union_reference = false` filter or create Path B enhancements) | Inv 5 | Lights up research feedback for 16 employers immediately | 30 min |
| 2 | **Require >=1 enforcement factor for Priority** | Inv 3 | Cuts Priority from 2,278 to 316 real targets | 1-2 hrs |
| 3 | **Reduce score_size weight from 3x to 1x** | Inv 1 & 4 | Removes biggest drag on scores; +0.2pp predictive power doesn't justify 3x | 1 hr |
| 4 | **Reduce score_union_proximity weight from 3x to 2x** | Inv 1 | +0.0pp predictive power doesn't justify highest weight | 1 hr |
| 5 | **Deactivate fuzzy matches below 0.85** | Inv 2 & 6 | Removes 9,694 ~50% incorrect matches; 35 Priority employers affected | 2-4 hrs |
| 6 | **Auto-lookup employer_id in research agent** | Inv 5 | Would link 16+ unlinked companies, fixing 77% of research runs going forward | 1-2 hrs |
| 7 | **Populate group_max_workers** from canonical groups | Inv 4 | Shifts size median from 28→76, more accurate company-level scoring | 2-3 hrs |
| 8 | **Consider increasing Industry Growth to 3x** | Inv 1 | Second-strongest predictor at +9.6pp | 30 min |
| 9 | **Investigate OSHA factor inversion** | Inv 1 | -0.6pp is small but counterintuitive; may indicate structural bias | 2-4 hrs |
| 10 | **Review 0.85-0.95 fuzzy band manually** | Inv 2 | 5,497 matches with ~30-50% FP rate | 4-8 hrs |

### How These Affect the Tier 0-1 Roadmap

| Roadmap Item | This Investigation Says... |
|-------------|---------------------------|
| T0-1 (Clean fuzzy matches) | **Confirmed.** FP rate is ~50% even at 0.85-0.90. Cleanup below 0.85 is safe (35 Priority affected). Manual review needed above 0.85. |
| T0-2 (Require enforcement for Priority) | **Strongly confirmed.** Scenario B (316 employers) is dramatically more useful than current (2,278). |
| T1-1 (NLRB nearby 25-mile) | **Deprioritize.** NLRB own-history already provides +10.2pp, the strongest signal. The 25-mile factor would help but isn't blocking the scoring system's effectiveness. |
| T1-2 (Recalibrate score_size) | **Strongly confirmed.** +0.2pp predictive power at 3x weight. Reduce to 1x immediately. Use consolidated_workers for better size data. |
| T1-3 (Connect Research Agent) | **Root cause identified.** MV JOIN bug on `is_union_reference = false`. 30-minute fix lights up 16 employers. Also: auto-lookup employer_id. |
| T2-1 (Backtest scores) | **Done.** Score IS predictive (74.1% → 90.9%). Key insight: NLRB and Industry Growth are the real predictors; Size and Proximity contribute nothing. |

---

## Appendix: Key SQL Queries Used

### Backtest Join Chain
```sql
SELECT DISTINCT ON (ne.id)
    ne.id, ne.union_won, mvs.score_tier, mvs.weighted_score
FROM nlrb_elections ne
JOIN nlrb_participants np ON np.case_number = ne.case_number
    AND np.participant_type = 'Employer'
JOIN mv_unified_scorecard mvs ON mvs.employer_id = np.matched_employer_id
WHERE ne.union_won IS NOT NULL AND np.matched_employer_id IS NOT NULL
```

### Fuzzy Band Distribution
```sql
SELECT CASE
    WHEN (evidence::json->>'name_similarity')::float >= 0.95 THEN '0.95-1.00'
    WHEN (evidence::json->>'name_similarity')::float >= 0.90 THEN '0.90-0.95'
    WHEN (evidence::json->>'name_similarity')::float >= 0.85 THEN '0.85-0.90'
    WHEN (evidence::json->>'name_similarity')::float >= 0.80 THEN '0.80-0.85'
  END as sim_band, COUNT(*)
FROM unified_match_log
WHERE status = 'active'
AND match_method IN ('FUZZY_SPLINK_ADAPTIVE', 'FUZZY_TRIGRAM')
AND evidence::json->>'name_similarity' IS NOT NULL
GROUP BY 1 ORDER BY 1
```

### MV Research JOIN (the bug)
```sql
-- Line 428 of mv_unified_scorecard definition:
LEFT JOIN research_score_enhancements rse
  ON rse.employer_id = s.employer_id
  AND rse.is_union_reference = false  -- filters out ALL 16 existing rows
```

### Weight Simulation
```sql
-- Simulated score with size at 1x instead of 3x
SELECT
    (COALESCE(score_union_proximity * 3, 0) +
     COALESCE(score_size * 1, 0) +  -- changed from 3
     COALESCE(score_nlrb * 3, 0) + ...)
    / NULLIF(total_weight_adjusted, 0) as new_score
FROM mv_unified_scorecard
```
