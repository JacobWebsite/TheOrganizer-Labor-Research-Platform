# Full Platform Audit Report -- Claude Code (Round 4)
## Labor Relations Research Platform
**Auditor:** Claude Code (Opus 4.6)
**Date:** February 22, 2026
**Database:** `olms_multiyear` on localhost

---

## SECTION 1: Database Inventory

### 1.1 Database Size

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Database size | ~9.5 GB | **11 GB** | **MEDIUM** -- 1.5 GB larger than documented |

**What this means:** The database grew ~16% beyond what docs claim. Caused by master employer dedup merge log (289K rows, 90 MB), employer comparables (269K rows, 140 MB), and MV data. The 9.5 GB was post-Phase D; subsequent Phase G seeding and scoring added data.

### 1.2 Schema Summary

| Object Type | Count | Documented |
|-------------|-------|------------|
| Tables | **188** | ~20 named |
| Views | **124** | Unlisted |
| Materialized Views | **6** | 4 |
| API Routers | **22** | 21 |

**Finding 1.1 -- MEDIUM -- Verified:** 2 undocumented MVs with real data:
- `mv_employer_features` (54,968 rows, 8.7 MB)
- `mv_whd_employer_agg` (330,419 rows, 45 MB)

**Finding 1.2 -- LOW -- Verified:** Extra router: `museums.py` (experimental/unused).

### 1.3 Core Table Count Verification

| Table | Expected | Actual | Delta |
|-------|----------|--------|-------|
| `f7_employers_deduped` | 146,863 | 146,863 | 0 |
| `master_employers` | 2,736,890 | 2,736,890 | 0 |
| `master_employer_source_ids` | 3,080,492 | **3,072,689** | **-7,803** |
| `unified_match_log` | 1,738,115 | 1,738,115 | 0 |
| `unions_master` | 26,665 | 26,693 | +28 |
| `osha_establishments` | 1,007,217 | 1,007,217 | 0 |
| `osha_violations_detail` | 2,245,020 | 2,245,020 | 0 |
| `nlrb_elections` | 33,096 | 33,096 | 0 |
| `whd_cases` | 363,365 | 363,365 | 0 |
| `sam_entities` | 826,042 | 826,042 | 0 |
| `sec_companies` | 517,403 | 517,403 | 0 |
| `national_990_filers` | 586,767 | 586,767 | 0 |
| `irs_bmf` | 2,043,779 | 2,043,472 | -307 |

**Finding 1.3 -- MEDIUM -- Verified:** `master_employer_source_ids` is 7,803 rows short. Some master employers may have lost their source linkage during dedup merge.

**Finding 1.4 -- LOW -- Verified:** `unions_master` +28 rows from Phase C manual union additions.

### 1.4 Match Table Consistency

| Source | UML Active | Legacy Table | Delta |
|--------|-----------|-------------|-------|
| osha | 97,142 | 97,142 | 0 |
| sam | 28,815 | 28,816 | **-1** |
| 990 | 20,215 | 20,005 | **+210** |
| whd | 19,462 | 19,462 | 0 |
| nlrb | 13,031 | 13,031 | 0 |
| **TOTAL** | **206,191** | | |

**Finding 1.5 -- MEDIUM -- Verified:** 990 UML vs legacy table off by 210. Known issue: legacy table has dual unique constraints causing INSERT failures.

### 1.5 Zero-Row and Empty Tables

3 truly empty tables: `cba_wage_schedules`, `platform_users`, `splink_match_results`. The `platform_users` being empty confirms auth has never been used by a real user.

### 1.6 NLRB ULP Matching -- Verified

- 234,656 CA charged party records matched (from `nlrb_participants` joined to CA cases): **CONFIRMED**
- Primary type: "Charged Party / Respondent" (671,721 total), 19.4% match rate

---

## SECTION 2: Data Quality Deep Dive

### 2.1 f7_employers_deduped Column Completeness

| Column | Not NULL | Coverage | Status |
|--------|----------|----------|--------|
| employer_name | 146,863 | 100% | OK |
| state | 142,970 | 97.3% | OK |
| city | 143,179 | 97.5% | OK |
| naics | 124,680 | 84.9% | OK |
| latitude/longitude | 108,377 | 73.8% | **26.2% missing geocoding** |
| latest_unit_size | 146,863 | 100% | OK |
| latest_union_fnum | 100,619 | 68.5% | 31.5% lack union linkage |
| canonical_group_id | 66,859 | 45.5% | By design |
| whd_violation_count | 11,297 | 7.7% | Expected |
| naics_detailed | 0 | **0%** | **EMPTY COLUMN** |
| corporate_parent_id | 0 | **0%** | **EMPTY COLUMN** |
| cbsa_code | 0 | **0%** | **EMPTY COLUMN** |
| is_historical | 79,311 | 54.0% | Design split |
| is_labor_org | 1,843 | 1.3% | Reasonable |

**Finding 2.1 -- MEDIUM -- Verified:** Three columns are 100% NULL: `naics_detailed`, `corporate_parent_id`, and `cbsa_code`. These consume schema space and create the illusion of available data. Organizers building reports that reference "detailed NAICS" or "CBSA metro area" will get nothing.

**Finding 2.2 -- MEDIUM -- Verified:** 26.2% of employers (38,486) lack geocoding (lat/lng). This means map-based features will show ~1/4 of employers at a default location or not at all.

### 2.2 master_employers Quality

| Quality Score Bucket | Count | Pct | Avg Score |
|---------------------|-------|-----|-----------|
| 80-100 | 100 | 0.004% | 90.0 |
| 60-79 | 8,855 | 0.3% | 61.7 |
| 40-59 | 34,769 | 1.3% | 45.5 |
| 20-39 | **2,693,166** | **98.4%** | 27.1 |

**Finding 2.3 -- HIGH -- Verified:** **98.4% of master employers have quality scores 20-39.** Only 100 employers (0.004%) score above 80. The master table is dominated by BMF records (1,754,142, 64%) and SAM records (781,778, 29%) -- both tend to have minimal data beyond name+state+EIN.

**What this means for organizers:** The "non-union targets" feature draws from master_employers. Almost all records have very thin data -- just a name and state. An organizer searching for targets will get names with almost no supporting information to assess them.

| Source | Count | Pct |
|--------|-------|-----|
| bmf | 1,754,142 | 64.1% |
| sam | 781,778 | 28.6% |
| f7 | 146,863 | 5.4% |
| mergent | 54,107 | 2.0% |

Master employers with EIN: 1,777,263 (65.0%). Zero duplicate EINs after dedup (good).

### 2.3 Unified Match Log

| Confidence | Active | Superseded | Rejected |
|------------|--------|------------|----------|
| HIGH | 127,160 | 339,342 | 0 |
| MEDIUM | 79,031 | 152,141 | 1 |
| LOW | 0 | 0 | 1,040,440 |

Zero NULL target_ids. All LOW-confidence matches are rejected (correct behavior). **Match method breakdown (active):**

| Method | Count |
|--------|-------|
| FUZZY_SPLINK_ADAPTIVE | 83,087 |
| NAME_AGGRESSIVE_STATE | 19,768 |
| NAME_CITY_STATE_EXACT | 19,048 |
| FUZZY_TRIGRAM | 18,013 |
| NAME_STATE_EXACT | 14,826 |
| EIN_EXACT | 13,760 |
| CROSSWALK | 10,688 |
| name_zip_exact | 8,140 |
| Other methods | 18,861 |

### 2.4 Scoring Factor Coverage (mv_unified_scorecard)

| Factor | Coverage | Avg | Min | Max |
|--------|----------|-----|-----|-----|
| score_size | 146,863 (100%) | 1.48 | 0.00 | 10.00 |
| score_industry_growth | 124,680 (84.9%) | 6.68 | 4.20 | 9.20 |
| **score_financial** | **124,680 (84.9%)** | **6.68** | **4.20** | **9.20** |
| score_union_proximity | 68,827 (46.9%) | 8.80 | 5.00 | 10.00 |
| score_osha | 31,459 (21.4%) | 1.44 | 0.00 | 10.00 |
| score_nlrb | 25,879 (17.6%) | 3.59 | 0.00 | 10.00 |
| score_whd | 12,025 (8.2%) | 1.70 | 0.04 | 9.76 |
| score_contracts | 8,672 (5.9%) | **4.00** | **4.00** | **4.00** |
| score_similarity | **186 (0.1%)** | 8.06 | 0.00 | 10.00 |

**Factor count distribution:**

| Factors | Employers |
|---------|-----------|
| 2 | 7,451 |
| 3 | 9,177 |
| 4 | 44,481 |
| 5 | 55,355 |
| 6 | 21,692 |
| 7 | 6,998 |
| 8 | 1,517 |
| 9 | 192 |

### 2.5 Orphan Records

- F7 employers with orphan fnums (union not in unions_master): **355** (74 current, 281 historical)
- UML active records pointing to missing F7 employer: **1** (nearly perfect)

### 2.6 is_labor_org Flag

- F7: 1,843 flagged (1.3%). Sample names: "Communications Workers of America, Local 1168", "Teamsters 471", "IBEW Local 569", "UAW 4911" -- all clearly labor organizations. **Looks correct.**
- Master: 6,686 flagged.

### 2.7 Member Count Verification

| Measure | Total |
|---------|-------|
| Raw SUM(latest_unit_size), all | 29,675,911 |
| Current only (not historical) | **15,044,103** |
| v_union_members_deduplicated | **71,974,947** |
| BLS benchmark | ~14,300,000 |

**Finding 2.4 -- HIGH -- Verified:** The current-only member count (15.0M) is within ~5% of BLS (14.3M) -- reasonable. **However, `v_union_members_deduplicated` produces 72M** -- 5x the BLS number. This view is fundamentally broken for total membership counting. It likely doesn't properly exclude double-counted members across affiliated locals and national unions.

---

## SECTION 3: Matching Pipeline Integrity

### 3.1 Match Quality Spot Checks

**Finding 3.1 -- CRITICAL -- Verified:** Random sample of 20 HIGH-confidence matches: **8 of 20 (40%) are clearly wrong.** All 8 wrong matches use `FUZZY_SPLINK_ADAPTIVE`. Examples:

| Source Name | F7 Name | State | Name Sim | Verdict |
|-------------|---------|-------|----------|---------|
| RCC INCORPORATED | PCA Corrugated | UT | 0.667 | **WRONG** |
| KWD MANUFACTURING | Markle Manufacturing | TX | 0.703 | **WRONG** |
| RUACH CONSTRUCTION, INC. | Ghilotti Construction Company | CA | 0.651 | **WRONG** |
| PEARSON CONSTRUCTION, LLC. | JPI CONSTRUCTION INC | KS | 0.700 | **WRONG** |
| LA COUNTY SHERIFF'S DEPT | LA County Federation of Labor | CA | 0.676 | **WRONG** |
| SIOUX CITY ENGINEERING CO | Sioux City Journal | IA | 0.651 | **WRONG** |
| EBENEZER CONSTRUCTION | Quad Construction | OK | 0.684 | **WRONG** |
| MARK YOUNG CONSTRUCTION | Mel-Ro Construction | CO | 0.739 | **WRONG** |

Deterministic matches (EIN_EXACT, NAME_STATE_EXACT) in the same sample were all correct. MEDIUM-confidence sample (20 random): 2 of 20 wrong (both FUZZY_TRIGRAM) -- much better than HIGH.

**Root cause:** The Splink model overweights geography (state+city+zip combined Bayes factor ~8.5M) so severely that it assigns 0.99+ match probability even when names are completely different, as long as they share a city/state.

### 3.2 CRITICAL: 29,236 OSHA Matches Below Current Threshold

**Finding 3.2 -- CRITICAL -- Verified:** The name similarity floor was raised from 0.65 to 0.70 on 2026-02-19, but the OSHA re-runs completed on 2026-02-18 (4 batches). Result: **29,236 active OSHA Splink matches have name_similarity between 0.65 and 0.699** -- below the current threshold. Only OSHA is affected; SAM, WHD, 990, and SEC runs used the corrected 0.70.

Name similarity distribution for all 83,087 active FUZZY_SPLINK_ADAPTIVE matches:

| Range | Count | Note |
|-------|-------|------|
| 0.65-0.70 | 29,236 | All OSHA, old threshold |
| 0.70-0.75 | 31,838 | |
| 0.75-0.80 | 11,947 | |
| 0.80-0.85 | 5,681 | |
| 0.85-0.90 | 2,575 | |
| 0.90+ | 1,810 | |

**Remediation:** Re-run OSHA matching with 0.70 threshold, or bulk-reject the 29,236 sub-threshold records.

### 3.3 Many-to-One Analysis

Top F7 employers by OSHA match count (construction companies with many job sites):

| Employer | State | OSHA Matches |
|----------|-------|-------------|
| Marjo Construction Services | MI | 226 |
| DeJean Construction Company | TX | 188 |
| Mel-Ro Construction | CO | 179 |
| Guido Construction Company | TX | 164 |
| CDK Construction Inc | CA | 160 |

**Note:** "Mel-Ro Construction" (179 matches) appeared in the wrong-match sample -- its high count is likely inflated by false Splink matches from unrelated OSHA establishments in Colorado.

### 3.4 Duplicate Match Check

**Finding 3.3 -- POSITIVE -- Verified:** Zero OSHA establishments matched to multiple F7 employers. Best-match-wins working correctly.

### 3.5 Employer Group Quality

**Finding 3.4 -- HIGH -- Verified:** 5 groups with 100+ members are **false groupings** caused by generic normalized names:

| Group | Members | Assessment |
|-------|---------|------------|
| D. CONSTRUCTION, INC. | 249 | FALSE -- unrelated cos (Ceco Concrete, Dunigan, Hesse) |
| International Contractors, Inc. | 188 | FALSE -- unrelated IL contractors |
| Building Service, Inc. | 164 | FALSE -- unrelated building/service/maintenance cos |
| Construction Co. | 140 | FALSE -- any "Construction" company collapsed |
| National Equipment Corp. | 137 | FALSE -- unrelated equipment cos |

Legitimate large groups: Starbucks (234), Aramark (122), MV Transportation (114).

**Finding 3.5 -- MEDIUM -- Verified:** **HealthCare Services Group is fragmented into 18 separate groups** totaling ~900+ records that should be 1 group. The fuzzy post-merge (Phase 4, token_set_ratio>=90) failed on "Health" vs "Healthcare" and "Inc" vs "Inc." variations.

### 3.6 Match Drift

**Finding 3.6 -- HIGH -- Verified:** **75,043 superseded matches have no active replacement.**

| Source | Orphaned | Total Superseded | Orphan Rate |
|--------|----------|-----------------|-------------|
| 990 | 26,256 | 94,531 | 27.8% |
| osha | 14,538 | 236,162 | 6.2% |
| sec | 14,387 | 37,110 | **38.8%** |
| whd | 13,871 | 71,313 | 19.4% |
| sam | 5,991 | 52,358 | 11.4% |

SEC has the highest orphan rate (38.8%) -- many SEC entities are SPVs/subsidiaries that don't match well to F7. This is expected behavior from threshold tightening (`--rematch-all` supersedes before re-run), but represents 75K source records that previously enriched profiles and now don't.

### 3.7 NLRB ULP Matching -- CLEAN

Random sample of 10 CA charged-party ULP matches: **10/10 correct.** USPS dominance in sample (5/10) reflects real-world filing distribution.

### 3.8 NLRB Participant Data Quality

**Finding 3.7 -- MEDIUM -- Verified:** **83.6% of `nlrb_participants`** (1,593,775 of 1,906,542) have literal header text ("Charged Party Address State", "Charged Party Address City") instead of actual values. CSV parsing issue during import. Doesn't affect ULP matching (uses case-level data) but makes participant-level geographic analysis unreliable.

---

## SECTION 4: Scoring System Verification

### 4.1 CRITICAL: score_financial = score_industry_growth (Duplicated Factor)

**Finding 4.1 -- CRITICAL -- Verified:** `score_financial` and `score_industry_growth` are **IDENTICAL** in every single record.

```
Identical values: 124,680
Different values: 0
```

**Root cause (line 340 of `build_unified_scorecard.py`):**
```python
s.score_industry_growth AS score_financial,
```

The code literally copies `score_industry_growth` into `score_financial`. They are the same BLS industry growth data displayed under two different names. The MV has 9 "score_" columns, but only **7 contain distinct data**. The weighted formula correctly uses `score_industry_growth` once with weight 2, so the actual weighted_score calculation is not double-counting -- but the MV presents a misleading picture of "8 diverse factors" when two columns contain duplicate data.

### 4.2 CRITICAL: score_contracts Has Zero Differentiation

**Finding 4.2 -- CRITICAL -- Verified:** ALL 8,672 employers with `score_contracts` have the **exact same value: 4.00**.

The scoring system gives every federal contractor the same score. It does not differentiate between a $100,000 contract and a $10 billion contract. This factor provides zero signal for prioritization.

### 4.3 CRITICAL: score_similarity Is Essentially Empty

**Finding 4.3 -- CRITICAL -- Verified:** Only **186 out of 146,863** employers (0.1%) have a `score_similarity` value. Despite being weighted at 2x, this factor exists for virtually no one. The `employer_comparables` table has 269K rows, but the scoring pipeline apparently fails to translate this into similarity scores for most employers.

### 4.4 CRITICAL: Scoring Rewards Data Sparsity

**Finding 4.4 -- CRITICAL -- Verified:** The "signal-strength" approach (skip NULL factors in the denominator) causes employers with fewer factors to score HIGHER.

Top 25 Priority employers: **ALL have weighted_score = 10.0**

| Factor Count | Priority Employers | Avg Score |
|-------------|-------------------|-----------|
| 1 factor | 231 | 9.96 |
| 2 factors | 1,912 | 9.08 |
| 3 factors | 1,834 | 9.29 |
| 4 factors | 190 | 8.91 |
| 5 factors | 22 | 8.93 |
| 6 factors | 1 | 8.88 |

**231 employers are ranked "Priority" with only 1 factor** -- typically just `score_size=10.0` (large workforce). An employer with 500+ workers and no other data gets a perfect 10, outranking employers with rich multi-source data.

Examples of perfect-10 Priority employers (1 factor only):
- "Company Lists" (workers=10,000, no state listed)
- "Employer Name" (workers=1,100, NY) -- this appears to be a PLACEHOLDER record
- "M1" (AL) -- ambiguous 2-character name
- "Pension Benefit Guaranty Corporation (PBGC)" -- a federal agency, not an organizing target

**Finding 4.5 -- CRITICAL -- Verified:** **92.7% of Priority employers (3,883 of 4,190) have NO OSHA, WHD, or NLRB data.** They're ranked "Priority" purely by employer size and generic industry/proximity factors.

**What this means for organizers:** The "Priority" tier is essentially a list of large employers, not a list of promising organizing targets. An organizer following these recommendations would be sent to employers with zero evidence of labor violations, zero organizing history, and zero external intelligence -- just because they're big.

### 4.5 Weighted Formula Verification

**Finding 4.6 -- POSITIVE -- Verified:** Manual recalculation of weighted_score for 5 random employers with 4+ factors matches stored values within rounding tolerance (max difference: 0.005). The formula `SUM(score * weight) / SUM(active weights)` is implemented correctly. `score_financial` is NOT included in the weighted calculation (it's informational only, a copy of score_industry_growth).

| Employer | Manual Calc | Stored | Diff |
|----------|------------|--------|------|
| GKN AEROSPACE (CA) | 5.976 | 5.98 | 0.004 |
| Richmond Sanitary (CA) | 5.038 | 5.04 | 0.002 |
| Island Movers (HI) | 5.135 | 5.13 | 0.005 |
| Pepsi Americas (PR) | 5.008 | 5.01 | 0.003 |
| Enterprise Car Rental (FL) | 5.453 | 5.45 | 0.003 |

**Bottom line:** The math is correct. The issue is the design (rewarding sparsity), not a calculation bug.

### 4.6 Temporal Decay -- WORKING

**OSHA 10-year half-life confirmed:**

| Era | Employers | Avg score_osha | Avg decay_factor |
|-----|-----------|---------------|-----------------|
| Pre-2020 | 15,414 | 0.48 | 0.25 |
| 2020-2021 | 3,177 | 1.19 | 0.49 |
| 2022-2023 | 5,193 | 1.83 | 0.65 |
| 2024+ | 7,675 | **3.21** | 0.87 |

2024+ employers score **6.7x higher** than pre-2020 on average. Recent violations correctly dominate.

**WHD 5-year half-life confirmed:**

| Cases | Employers | Avg score_whd |
|-------|-----------|--------------|
| 1 case | 8,496 | 1.26 |
| 2-3 cases | 2,783 | 2.30 |
| 4+ cases | 746 | 4.47 |

Top WHD scores (9+) all have 2025 latest findings, confirming recency dominates.

### 4.7 NLRB ULP Boost -- WORKING

| ULP Bucket | Employers | Avg score_nlrb |
|-----------|-----------|---------------|
| No ULP | 3,508 | 2.33 |
| 1 ULP | 8,507 | 1.83 |
| 2-3 ULPs | 6,298 | 3.61 |
| 4-9 ULPs | 4,821 | 5.43 |
| 10+ ULPs | 2,745 | **7.40** |

ULP boost is monotonically increasing as designed.

**Finding 4.7 -- LOW -- Verified:** USPS TX has **38,268 ULPs** -- this is USPS's national ULP aggregation hitting one state record. Score is capped at 7.93, not 10, suggesting proper ceiling behavior.

**Finding 4.8 -- LOW -- Verified:** Laner Muchin (a management-side labor *law firm*) appears with 601 ULPs and a Moderate tier score. It's a charged party/respondent in ULP cases but is not a traditional employer. The system correctly reflects the data but doesn't distinguish between employers and their law firms.

### 4.8 Industry Growth Factor

`score_industry_growth` takes only **16 discrete values** (4.20 to 9.20), confirming it's derived from NAICS sector-level BLS projections, not employer-level data. Coverage is good at 84.9%. The 15.1% without scores likely have NULL/unmappable NAICS codes.

### 4.9 Score Distribution

| Score Range | Employers |
|-------------|-----------|
| 0.00-0.50 | 6,715 |
| 0.50-1.50 | 23,025 |
| 1.50-2.50 | 18,310 |
| 2.50-3.50 | 18,506 |
| 3.50-4.50 | 15,929 |
| 4.50-5.50 | 18,432 |
| 5.50-6.50 | 19,575 |
| 6.50-7.50 | 10,095 |
| 7.50-8.50 | 3,744 |
| 8.50-9.50 | 5,389 |
| 9.50-10.00 | 7,143 |

Employers with weighted_score = 0: **3,389**
Employers with weighted_score > 9: **2,425**

The distribution is bimodal -- a large cluster near 0-1.5 and another cluster near 5-6.5, with spikes at the extremes (0 and 10).

### 4.6 Tier Distribution vs Design Targets

| Tier | Actual | Pct | Target |
|------|--------|-----|--------|
| Priority | 4,190 | 2.9% | 3% |
| Strong | 17,833 | 12.1% | 12% |
| Promising | 36,694 | 25.0% | 25% |
| Moderate | 51,384 | 35.0% | 35% |
| Low | 36,762 | 25.0% | 25% |

Percentile tiers match design targets exactly (they're percentile-based, so this is by construction). The tiers correctly segment the population -- but the underlying scores that determine ordering within tiers are compromised by the issues above.

### 4.7 Amazon and Starbucks

| Employer | State | Score | Tier | Factors |
|----------|-------|-------|------|---------|
| Starbucks | WI | 6.00 | Strong | 6 |
| Starbucks | LA | 6.34 | Strong | 4 |
| Starbucks | FL | 6.42 | Strong | 5 |
| Starbucks | CA | 5.73 | Promising | 5 |
| Starbucks | PA | 5.60 | Promising | 3 |
| Amazon Studios | CA | 4.44 | Moderate | 3 |

Starbucks appears multiple times (partially grouped -- 234 in canonical group, but several remain separate entries). Starbucks scores are in the Promising-Strong range, which seems reasonable given their active organizing history. No "Amazon" warehousing/fulfillment records appear -- the platform mainly picks up Amazon Studios and a construction company named "Amazon."

---

## SECTION 5: API & Endpoint Testing

### 5.1 Live Endpoint Testing

All endpoints tested against running API (`localhost:8001`).

| Endpoint | Status | Response Time |
|----------|--------|--------------|
| `GET /api/health` | **PASS** | 0.21s |
| `GET /api/employers/unified-search?name=walmart` | **PASS** | 0.79s |
| `GET /api/scorecard/unified?limit=5` | **PASS** | 0.22s |
| `GET /api/master/stats` | **FAIL** | **12.55s** |
| `GET /api/master/non-union-targets?limit=5` | **PASS** | 1.96s |
| `GET /api/unions/search?q=teamsters` | **PASS** | 0.51s |
| `GET /api/profile/employers/{id}` | **PASS** | 3.16s |

**Total registered endpoints: 153** (148 GET, 4 POST, 1 DELETE). Four employer search variants exist (`/search`, `/fuzzy-search`, `/normalized-search`, `/unified-search`) -- legacy ones should be deprecated.

**Finding 5.1 -- HIGH -- Verified:** **`/api/master/stats` takes 12.5 seconds** -- full table scan on 2.7M rows. Needs caching, pre-computed aggregation, or a materialized stats table.

**Finding 5.2 -- MEDIUM -- Verified:** **Search parameter naming inconsistency.** Employer search uses `name=`, union search uses `q=`. Using `?q=walmart` on employer search **silently returns all 107,025 records unfiltered** -- no error for unknown params.

### 5.2 Security

**Finding 5.3 -- MEDIUM (downgraded from HIGH) -- Verified:** 82 f-string SQL patterns in API. **Live code inspection confirms all are safe:** f-strings only interpolate internally-built `where_clause` strings (e.g., `"m.state = %s AND m.unit_size >= %s"`) or hardcoded table names from whitelisted dicts. All user input goes through psycopg2 `%s` parameterization. No `.format()` calls found. **No SQL injection vulnerabilities detected.** Still a risky pattern for maintainability.

**Finding 5.4 -- LOW -- Verified:** CORS is properly configured with specific localhost origins (`http://localhost:5173`, `http://localhost:8001`, etc.), NOT `allow_origins=["*"]`. `PUT`/`PATCH` not in `allow_methods` -- will need adding if future endpoints use them.

**Finding 5.5 -- LOW -- Verified:** Auth is enabled by default. Startup guard exits if no JWT_SECRET and auth not disabled. Write endpoints require `require_auth`, admin endpoints require `require_admin`. Properly designed.

### 5.3 Credentials

**Finding 5.6 -- POSITIVE -- Verified:** Zero instances of hardcoded credentials ("Juniordog") found in the codebase. Zero instances of the broken `password='os.environ.get(...)` pattern. The `db_config.py` properly uses environment variables.

### 5.4 Data Quality via API

**Finding 5.7 -- LOW -- Verified:** Some NLRB search results show literal text "Charged Party Address City" instead of actual city values -- raw data leaking through without cleanup.

**Finding 5.8 -- LOW -- Verified:** "LOCAL 580 INSURANCE FUNDS" (NAICS 813930 = Labor Organizations) appears in non-union targets. It's a union insurance fund, not a traditional organizing target.

---

## SECTION 6: Frontend & React App

### 6.1 Structure

| Category | Count |
|----------|-------|
| Frontend source files | **88** (86 JS/JSX + 2 config) |
| Frontend test files | **21** (in `frontend/__tests__/`) |
| Backend test files | **31** (in `tests/`) |
| Backend test functions | **~493** |

Feature directory breakdown:

| Phase | Directory | Files |
|-------|-----------|-------|
| 1 Auth | `features/auth/` | 1 |
| 2 Search | `features/search/` | 8 |
| 3 Profile | `features/employer-profile/` | 16 |
| 4 Targets | `features/scorecard/` | 6 |
| 5 Union Explorer | `features/union-explorer/` | 15 |
| 6 Admin | `features/admin/` | 8 |
| Shared | `shared/` (api, components, hooks, stores) | 21 |
| UI primitives | `components/ui/` | 8 |

### 6.2 Build

**BUILD PASSES** with one warning. Single JS bundle is 522 KB (149 KB gzipped), slightly over Vite's 500 KB threshold. Code-splitting with `React.lazy()` would resolve this. Built in 4.56s.

### 6.3 Tests

**All 134 tests pass across 21 test files** (10.48s runtime). Coverage includes auth, search, profile, targets, union explorer, admin, and shared components. Zero failures, zero skips.

### 6.4 API Architecture

**Finding 6.1 -- POSITIVE -- Verified:** Zero hardcoded URLs in frontend source. All API calls use relative paths (`/api/...`) via a shared fetch wrapper, proxied to `localhost:8001` through Vite dev config. This is production-ready -- will work with any backend origin via reverse proxy.

8 API hook modules reference ~25 distinct backend endpoints. All use TanStack Query for caching/deduplication.

### 6.5 State Management

Clean architecture: 1 Zustand store (auth), TanStack Query for server state, 65 local `useState` calls for UI concerns. No state management anti-patterns detected.

### 6.6 Legacy Frontend

`files/organizer_v5.html` (146 KB monolith) still exists alongside the React app. Loads Tailwind/Leaflet/Chart.js from CDN. Candidate for archival to `archive/` when React app is deployed.

### 6.7 Accessibility

28 `aria-*`/`role` attributes across the codebase. Basic coverage but moderate for a 54-component app. Areas for improvement: keyboard navigation for tables/pagination, screen reader announcements for dynamic content, focus management on page transitions.

**Finding 6.2 -- MEDIUM -- Verified:** Accessibility coverage is thin for a tool intended for broad use. If organizers include users with disabilities, the current state would present barriers for screen reader and keyboard-only users.

---

## SECTION 7: Master Employer Table & Deduplication

### 7.1 Dedup Statistics

| Metric | Value |
|--------|-------|
| Total merges | 289,400 |
| Unique winners | 37,450 |
| Unique losers (merged away) | 289,400 |
| By name+state exact | 288,782 (99.8%) |
| By EIN | 618 (0.2%) |

**Assessment:** Dedup is overwhelmingly name+state based. The EIN-based merges are a tiny fraction. This is expected since BMF and SAM records rarely share EINs with F7 records.

### 7.2 Post-Dedup Quality

- Duplicate EINs remaining: **0** (excellent)
- Masters without source IDs: **0** (excellent)
- Source ID breakdown: bmf (2,043,472), sam (826,042), f7 (146,863), mergent (56,312)

### 7.3 Source ID Integrity

- Masters without source IDs: **0** (every master has at least one link)
- 20/20 random source IDs verified as pointing to real records in their source tables (sam_entities, irs_bmf)
- Source ID total (3,072,689) > master count (2,736,890) because merged losers' source IDs were transferred to winners

### 7.4 Remaining Duplicates

**Finding 7.1 -- MEDIUM -- Verified:** 9,271 groups of same canonical_name + state still exist (22,616 records). Notable:
- "NATIONAL WILD TURKEY FEDERATION INC" (SC): **1,758 records** -- all with unique EINs. These are real separate chapter registrations, not a dedup failure.
- Starbucks Corporation (CA): 25 records -- 25 distinct F7 bargaining units. Expected.
- "first student inc" vs "first student  inc" (double space): ~31 records across IL that the normalizer missed.

**Finding 7.2 -- LOW -- Verified:** `merge_evidence` JSONB is empty (`{}`) for all sampled merges. The loser's original name/state are not preserved, making merge auditing difficult. If a bad merge is suspected, there's no way to see what was merged without querying the merge log separately.

### 7.5 Over-Merge Risk

**Finding 7.3 -- MEDIUM -- Likely:** With 288,782 name+state merges, there's a risk of over-merging common names. "John Smith Construction" in Texas could merge two completely different companies. The 0.2% EIN-based merge rate suggests name matching is doing most of the work, and aggressive normalization can create false positives. No confidence scoring or manual review exists for borderline cases.

---

## SECTION 8: Scripts, Pipeline & Code Quality

### 8.1 Credentials

- Active code (`scripts/`, `api/`): **0 hardcoded passwords** -- all 115 scripts use centralized `db_config.py`
- Broken `password='os.environ.get(...)'` pattern: **0 found**
- `db_config.py`: Clean design -- reads `.env`, falls back to env vars, no hardcoded credentials

**Finding 8.1 -- MEDIUM -- Verified:** **10 archived files contain plaintext password** `Juniordog33!` in `archive/old_api/` and `archive/old_scripts/`. No active risk, but should be scrubbed from archive.

### 8.2 Code Quality

**Finding 8.2 -- MEDIUM -- Verified:** 82 f-string SQL patterns in API, all confirmed safe (user input parameterized). Maintainability risk only.

**Finding 8.3 -- LOW -- Verified:** **19 scripts contain hardcoded `C:\Users\jakew\Downloads` paths.** 10 are ETL loaders (expected for one-time data loads), 8 are analysis scripts, 1 is `update_whd_scores.py`. Would break portability.

### 8.3 Test Suite

- **492 passed, 0 failed, 1 skipped** (5m 41s)
- 33 test files across `tests/`
- Top coverage: `test_matching.py` (53), `test_scoring.py` (39), `test_api.py` (33), `test_name_normalization.py` (32)

**Finding 8.4 -- MEDIUM -- Verified:** **~10 of 23 API routers lack dedicated test files:** `cba`, `corporate`, `density`, `lookups`, `museums`, `projections`, `public_sector`, `sectors`, `trends`, `vr`. Some may be covered indirectly by `test_api.py`.

### 8.4 Pipeline Manifest Accuracy

10/10 randomly sampled scripts from PIPELINE_MANIFEST.md verified on disk. **PASS.**

Zero references to deleted tables (`corpwatch`, `gleif.raw`) in active code. GLEIF references are docstring-only in the loader script. **PASS.**

### 8.5 Analysis Scripts Cleanup

**Finding 8.5 -- LOW -- Verified:** `scripts/analysis/` has 55 scripts, ~20-30 of which are one-off investigations or superseded versions:
- Duplicated: `analyze_geocoding.py` + `analyze_geocoding2.py`, `analyze_deduplication.py` + `_v2.py`
- Migration tools: `migrate_to_db_config_connection.py`, `rollback_db_config_migration.py`, `rollback_password_fix.py`
- Versioned: `sector_analysis_1/2/3.py`, `multi_employer_fix.py` + `_v2.py`

### 8.6 Archive

Archive: **18 GB**, 1,082 Python files. Dominated by `gleif_schema_backup_2026-02-21.dump` (~12 GB). Moving the GLEIF dump to external storage would save 12 GB. Plaintext credentials in archived files should be scrubbed.

---

## SECTION 9: Documentation Accuracy

### 9.1 Phantom File References

**Finding 9.1 -- MEDIUM -- Verified:** `UNIFIED_PLATFORM_REDESIGN_SPEC.md` is referenced in PROJECT_STATE.md but **does not exist**. The actual file is `PLATFORM_REDESIGN_SPEC.md`. One session summary also references the phantom filename.

**Finding 9.2 -- LOW -- Verified:** MEMORY.md references `UNIFIED_ROADMAP_2026_02_17.md` which does not exist. Closest are `_02_16` (archived) and `_02_19` (active in `Start each AI/`).

**Finding 9.3 -- MEDIUM -- Verified:** `PROJECT_STATE.md` is located at `Start each AI/PROJECT_STATE.md`, not `docs/PROJECT_STATE.md` as implied by MEMORY.md references.

### 9.2 Scoring Documentation Inconsistencies

**Finding 9.4 -- HIGH -- Verified:** Documents disagree on factor count:

| Document | Claims | Actual |
|----------|--------|--------|
| SCORING_SPECIFICATION.md | 8 factors | Correct (8 logical factors) |
| PIPELINE_MANIFEST.md | 7 factors | Wrong (missing score_similarity, score_industry_growth) |
| MV_UNIFIED_SCORECARD_GUIDE.md | Header: 8, body: 7 | Self-contradictory |
| MEMORY.md | "8-factor" but lists 9 score columns | Misleading (score_financial is a copy of score_industry_growth) |

### 9.3 Tier Name Inconsistencies

**Finding 9.5 -- HIGH -- Verified:** MV_UNIFIED_SCORECARD_GUIDE.md exclusively uses legacy tiers (TOP/HIGH/MEDIUM/LOW) with old thresholds (>=7.0, >=5.0, >=3.5, <3.5). Does NOT mention the current percentile tiers (Priority/Strong/Promising/Moderate/Low) at all. Significantly out of date.

### 9.4 Missing from Pipeline Manifest

**Finding 9.6 -- MEDIUM -- Verified:** 3 active pipeline scripts missing from PIPELINE_MANIFEST.md:
- `scripts/etl/dedup_master_employers.py` (Phase G master dedup)
- `scripts/matching/match_nlrb_ulp.py` (NLRB ULP matching, used 2026-02-22)
- `scripts/maintenance/generate_project_metrics.py` (auto-metrics generator)

Manifest footer counts are stale: says "6 maintenance scripts" (actually 7), "Total: 134" (actually 137+).

### 9.5 Test Count Discrepancy

**Finding 9.7 -- MEDIUM -- Verified:** MEMORY.md and PROJECT_STATE.md both claim 492 tests. `PROJECT_METRICS.md` (auto-generated by pytest) reports 479 collected. The 13-test gap is likely because the auto-metrics script was run before late-session test additions on 2026-02-22. Neither doc clarifies whether the 134 frontend (Vitest) tests are included in the total.

### 9.6 master_employers Count Confusion

**Finding 9.8 -- MEDIUM -- Verified:** Three different counts appear across docs:
- MEMORY.md: "3,026,290->2,736,890, 289,400 merged" (both pre- and post-dedup)
- PROJECT_METRICS.md: "estimated 2,928,028" (pg_stat) AND "Total: 3,026,290" (pre-dedup `COUNT(*)`)
- Actual post-dedup count: **2,736,890** (not in PROJECT_METRICS.md)

The auto-metrics script reports the pre-dedup count because it runs `COUNT(*)` on the raw table. The post-dedup count (2,736,890) is the real working number.

---

## SECTION 10: Summary & Recommendations

### Health Score: **NEEDS WORK**

The platform has an impressive data foundation -- 2.7M master employers, 1.7M match audit records, 14 integrated data sources. The matching pipeline is technically sound (best-match-wins works, zero duplicate matches). But the scoring system -- the feature that makes the platform useful to organizers -- has fundamental flaws that undermine its primary purpose.

### Top 10 Issues (Ranked by Impact)

| Rank | Finding | Severity | Impact |
|------|---------|----------|--------|
| 1 | **40% of HIGH-confidence Splink matches are wrong** (8/20 sample) | CRITICAL | Wrong OSHA/SAM data linked to wrong employers; scores corrupted |
| 2 | **55.7% of union election wins invisible** to platform | CRITICAL | Platform misses the majority of actual organizing successes |
| 3 | **29,236 OSHA matches below 0.70 threshold** (stale from pre-fix runs) | CRITICAL | Known-bad matches still active; need re-run or bulk rejection |
| 4 | **Scoring rewards data sparsity** -- 1-factor employers get perfect 10s | CRITICAL | Organizers sent to employers with zero evidence |
| 5 | **94.6% of Priority tier has no post-2020 activity** | CRITICAL | "Priority" = ghost employers with no actionable data |
| 6 | **score_financial = score_industry_growth** (duplicated) | CRITICAL | Only 7 distinct signals, not 8 |
| 7 | **score_contracts = 4.00 for all records** (no variation) | CRITICAL | Factor provides zero signal |
| 8 | **No database backup strategy** | HIGH | 9.5 GB of irreproducible work with zero recoverability |
| 9 | **75,043 orphaned superseded matches** | HIGH | Real data no longer linked to employer profiles |
| 10 | **nlrb_participants.case_number missing index** (1.9M rows) | HIGH | Every NLRB JOIN does full table scan |

### Quick Wins (< 1 hour each)

1. **Bulk-reject 29,236 sub-threshold OSHA Splink matches:** `UPDATE unified_match_log SET status='rejected' WHERE source_system='osha' AND match_method='FUZZY_SPLINK_ADAPTIVE' AND confidence_score < 0.70 AND status='active'`. Or re-run OSHA with 0.70 threshold.
2. **Add minimum factor floor to tier assignment:** Require `factors_available >= 3` for Priority tier. This alone fixes the sparsity issue.
3. **Fix score_financial alias:** Change line 340 to compute an actual financial score (e.g., from 990 revenue data or BMF classification) instead of copying industry_growth.
4. **Remove score_similarity from weighted formula** until coverage exceeds 10%. At 0.1%, it distorts scores for the rare employers who have it.
5. **Add contract value tiers** to score_contracts: Small (<$1M)=4, Medium ($1-10M)=6, Large ($10-100M)=8, Mega (>$100M)=10.
6. **Add missing index:** `CREATE INDEX idx_nlrb_participants_case_number ON nlrb_participants(case_number)`. Highest-impact single performance fix.
7. **Set up pg_dump backup:** Even a nightly `pg_dump olms_multiyear | gzip > backup_$(date +%Y%m%d).gz` is better than nothing for a 9.5 GB database.
8. **Fix blocking MV refreshes:** Add `CONCURRENTLY` to `update_whd_scores.py` and `compute_gower_similarity.py`.
9. **Update docs:** Fix phantom file references, tier name inconsistencies, factor count disagreements, 3 missing scripts in manifest.
10. **Drop empty columns:** Remove `naics_detailed`, `corporate_parent_id`, `cbsa_code` from f7_employers_deduped (all 100% NULL).

### Scoring Assessment

The 8-factor weighted system is architecturally sound but has implementation bugs that make its output misleading. The signal-strength approach (skip NULLs) is a good idea in principle -- but without a minimum-factor floor, it produces absurd results (1-factor employers at the top). With the 3 broken/empty factors fixed and a minimum factor requirement added, the system would produce genuinely useful rankings.

**Recommendation:** A "data richness" penalty -- reducing scores for employers with fewer than 3-4 factors -- would immediately improve output quality. Alternatively, weight the score by coverage_pct: `final_score = weighted_score * (0.5 + 0.5 * factors_available / 8)`.

### Master Employer Assessment

The master table is structurally sound (zero duplicate EINs, zero orphaned source IDs, 289K merges completed). But 98.4% of records have quality scores of 20-39. **It's not ready for production use as a "target discovery" tool** -- there's simply not enough data on most records to make useful recommendations. It works well as a lookup/matching reference.

### Frontend Assessment

The React app is well-structured: 88 source files across 6 feature phases, all 134 tests passing, clean build (522 KB bundle), zero hardcoded URLs, and proper state management (Zustand + TanStack Query). **For production readiness:** (1) add code-splitting to get under the 500 KB bundle warning, (2) address the scoring display issues (scores that may mislead organizers), (3) add data freshness indicators, (4) improve accessibility for keyboard/screen reader users, (5) archive the legacy 146 KB monolith frontend.

### Matching Pipeline Assessment

**NOT trustworthy for deployment without OSHA Splink cleanup.** The deterministic tiers (EIN, NAME_STATE, NAME_CITY_STATE, AGGRESSIVE) are reliable. But **40% of randomly sampled HIGH-confidence Splink matches are wrong**, and **29,236 OSHA matches are below the current 0.70 threshold** (stale from pre-fix runs). These bad matches corrupt OSHA violation counts, safety scores, and employer profiles. Best-match-wins is working correctly (zero duplicates), and match drift (75K orphaned superseded) is cleanup, not a quality issue.

**Immediate action:** Re-run OSHA matching with the 0.70 threshold, or bulk-reject the 29,236 sub-threshold records. Then re-evaluate whether 0.70 is sufficient (the 40% error rate in the 0.65-0.739 range suggests 0.75+ may be needed).

### Security Assessment

- Credentials: CLEAN (no hardcoded passwords)
- Auth: Properly designed with JWT + startup guard
- CORS: Appropriately restricted to localhost
- SQL injection: 82 f-string patterns **all confirmed safe** (user input always parameterized). Maintainability risk only.
- **Before real users:** Set up LABOR_JWT_SECRET, create admin account, test auth flow end-to-end, optimize `/api/master/stats` (12.5s)

### Documentation Gaps

1. No documentation of the 2 extra MVs (mv_employer_features, mv_whd_employer_agg)
2. No documentation of the museums.py router
3. Phantom file references (UNIFIED_PLATFORM_REDESIGN_SPEC.md, UNIFIED_ROADMAP_2026_02_17.md)
4. Inconsistent factor counts (7 vs 8 vs 9) across 4 docs
5. Stale tier names (TOP/HIGH/MEDIUM/LOW) in MV guide -- current system not documented there
6. 3 active pipeline scripts missing from PIPELINE_MANIFEST (dedup_master, match_nlrb_ulp, generate_metrics)
7. Test count discrepancy (492 vs 479) with no clarity on frontend test inclusion
8. master_employers count: 3 different numbers across docs (3,026,290 / 2,928,028 / 2,736,890)
9. PROJECT_STATE.md location (`Start each AI/`) differs from implied `docs/` path

---

## SECTION 11: What No One Thought to Ask

### 11.1 Ghost Employers in Priority Tier

**Finding 11.1 -- CRITICAL -- Verified:** Of 4,190 Priority employers:
- **3,894 (92.9%)** have zero external factor scores (OSHA, NLRB, WHD, contracts, similarity all NULL)
- **3,962 (94.6%)** have no activity after 2020 in ANY source
- All 25 top-scoring Priority employers (weighted_score=10.0) have zero external data

Examples of perfect-10 "Priority" employers: "United Football League" (CT), "M1" (AL), "Sheet Metal & AC Contractors" (MD), "Alaskan General Seafoods" (WA) -- all with zero OSHA, NLRB, WHD, or contract records.

Their scores are driven entirely by: `score_union_proximity` (avg 10.0), `score_size` (avg 9.87), `score_industry_growth` (avg 7.56).

### 11.2 False Negatives: Union Wins the Platform Missed

**Finding 11.2 -- CRITICAL -- Verified:** Of **18,452 union election wins since 2023:**
- **10,285 (55.7%) have no F7 link at all** -- the platform cannot see the majority of actual organizing successes
- **392 matched wins were in the "Low" tier** -- pure false negatives

Tier distribution of MATCHED wins:

| Tier | Wins |
|------|------|
| Strong | 6,488 |
| Promising | 583 |
| Moderate | 579 |
| Low | 392 |
| Priority | 125 |

Lowest-scored wins: City World Ford (NY, score 0.99), Wells Fargo Bank (VA, score 1.19), Texas New Mexico Power (NM, score 1.02) -- all successfully organized despite "Low" rating.

The Strong tier captures the most wins (6,488), showing some predictive validity for matched employers, but Priority captures only 125 wins despite being the "highest urgency" tier.

### 11.3 The "No Data" Problem

**Finding 11.3 -- HIGH -- Verified:** 82,864 employers (56.4% of all 146,863) have **zero external source matches**. Of these, **13,698 are rated Priority or Strong** -- high-value targets with zero supporting data.

| Tier | Zero-Source Employers |
|------|----------------------|
| Moderate | 25,806 |
| Promising | 24,095 |
| Low | 19,265 |
| Strong | 10,441 |
| Priority | 3,257 |

The platform cannot distinguish "no problems found" from "no data available."

### 11.4 Industry Coverage Gaps

**Finding 11.4 -- HIGH -- Verified:** Major non-union employers are entirely absent:
- **Amazon.com:** Only 4 entries (Amazon Construction, Amazon Masonry, Amazon Studios, Amazonas Painting). The warehouse/fulfillment giant is invisible.
- **Walmart:** **0 entries** -- completely absent
- **Finance/Insurance (NAICS 52):** Only 418 employers (vs 25,302 Construction)
- **15.1% of employers** (22,183) have NULL NAICS codes

This is structural: F7 data only covers employers with union bargaining relationships. The platform systematically misses the biggest organizing targets.

### 11.5 Geographic Enforcement Bias

**Finding 11.5 -- MEDIUM -- Verified:** OSHA match rate varies 2.6x across major states:
- Highest: NV (37.9%), UT (35.9%), NE (34.5%)
- Lowest among large states: MA (14.6%), NJ (17.5%), MN (16.2%)

Correlation between OSHA match rate and average score: **0.142** (very weak), suggesting the OSHA factor has minimal real influence on overall scores despite being one of 8 factors.

### 11.6 No Database Backup Strategy

**Finding 11.6 -- HIGH -- Verified:** Only one `.dump` file exists (`archive/gleif_schema_backup_2026-02-21.dump`) for an archived schema. There is:
- No `pg_dump` cron job
- No point-in-time recovery configuration
- No backup before destructive operations (289,400 rows deleted during dedup)

A 9.5 GB database with 1.7M+ match records and months of irreproducible ETL work has essentially zero recoverability.

### 11.7 Missing Critical Indexes

**Finding 11.7 -- HIGH -- Verified:** Key missing indexes on large tables:

| Table | Rows | Missing Index | Impact |
|-------|------|---------------|--------|
| `nlrb_participants` | 1.9M | **`case_number`** | Primary JOIN column -- every case lookup does full scan |
| `nlrb_participants` | 1.9M | **`matched_employer_id`** | F7 linkage column |
| `osha_establishments` | 1.0M | Only 3 indexes total | May need compound indexes for common queries |

The `nlrb_participants.case_number` index is the single highest-impact performance fix available.

### 11.8 Blocking MV Refreshes

**Finding 11.8 -- MEDIUM -- Verified:** Two scripts use non-concurrent MV refresh (blocks all reads during refresh):
- `scripts/scoring/update_whd_scores.py` -- refreshes `mv_employer_search` **without CONCURRENTLY**
- `scripts/scoring/compute_gower_similarity.py` -- refreshes `mv_employer_features` **without CONCURRENTLY**

The first is particularly concerning since `mv_employer_search` powers the main search endpoint.

### 11.9 Score Shelf Life

The `data_source_freshness` table has 19 rows, but:
- `date_range_start`/`end` are NULL for 13 of 19 sources
- `last_updated = 2026-02-22` for most sources (reflects when the table was populated, not data freshness)
- **NY State Contracts has `date_range_end` of 2122-09-15** -- 100 years in the future (data quality bug)
- No mechanism to alert when source data goes stale

### 11.10 Union Count Paradox

`unions_master` has 26,693 unions vs BLS estimate of ~16,000 active locals. The 67% surplus includes historical/defunct locals and national affiliations. The "26,693 unions tracked" claim overstates active monitoring.

---

## Findings Index

| ID | Section | Severity | Description | Confidence |
|----|---------|----------|-------------|------------|
| 1.1 | Inventory | MEDIUM | 2 undocumented MVs | Verified |
| 1.2 | Inventory | LOW | 22 routers not 21 | Verified |
| 1.3 | Inventory | MEDIUM | master_employer_source_ids -7,803 | Verified |
| 1.5 | Inventory | MEDIUM | 990 UML/legacy gap of 210 | Verified |
| 2.1 | Quality | MEDIUM | 3 columns 100% NULL on f7 | Verified |
| 2.2 | Quality | MEDIUM | 26.2% missing geocoding | Verified |
| 2.3 | Quality | HIGH | 98.4% master employers quality 20-39 | Verified |
| 2.4 | Quality | HIGH | v_union_members_deduplicated = 72M (5x BLS) | Verified |
| 3.1 | Matching | CRITICAL | 40% of HIGH-confidence Splink matches wrong (8/20 sample) | Verified |
| 3.2 | Matching | CRITICAL | 29,236 OSHA Splink matches below 0.70 threshold | Verified |
| 3.3 | Matching | POSITIVE | Zero duplicate OSHA matches | Verified |
| 3.4 | Matching | HIGH | 5 false canonical groups (878+ employers) | Verified |
| 3.5 | Matching | MEDIUM | HealthCare Services Group fragmented into 18 groups | Verified |
| 3.6 | Matching | HIGH | 75,043 orphaned superseded matches | Verified |
| 3.7 | Matching | MEDIUM | 83.6% nlrb_participants have header text not real data | Verified |
| 4.1 | Scoring | CRITICAL | score_financial = score_industry_growth | Verified |
| 4.2 | Scoring | CRITICAL | score_contracts = 4.00 for all | Verified |
| 4.3 | Scoring | CRITICAL | score_similarity 0.1% coverage | Verified |
| 4.4 | Scoring | CRITICAL | Scoring rewards data sparsity | Verified |
| 4.5 | Scoring | CRITICAL | 92.7% Priority has no enforcement data | Verified |
| 4.6 | Scoring | POSITIVE | Weighted formula verified correct (5/5 match) | Verified |
| 4.7 | Scoring | LOW | USPS TX 38K ULPs aggregation artifact | Verified |
| 4.8 | Scoring | LOW | Law firm (Laner Muchin) scored as employer | Verified |
| 5.1 | API | HIGH | /api/master/stats takes 12.5s | Verified |
| 5.2 | API | MEDIUM | Search param inconsistency (name= vs q=) | Verified |
| 5.3 | API | MEDIUM | 82 f-string SQL (safe but risky pattern) | Verified |
| 5.4 | API | LOW | CORS properly restricted | Verified |
| 5.5 | API | LOW | Auth properly designed | Verified |
| 5.6 | API | POSITIVE | Zero hardcoded credentials | Verified |
| 5.7 | API | LOW | NLRB raw data leaking ("Charged Party Address City") | Verified |
| 5.8 | API | LOW | Union insurance fund in non-union targets | Verified |
| 7.1 | Master | MEDIUM | 9,271 name+state duplicate groups remain | Verified |
| 7.2 | Master | LOW | merge_evidence JSONB empty, no audit trail | Verified |
| 7.3 | Master | MEDIUM | Name+state merge may over-merge | Likely |
| 8.1 | Scripts | MEDIUM | 10 archived files contain plaintext password | Verified |
| 8.2 | Scripts | MEDIUM | 82 f-string SQL (all safe, maintainability risk) | Verified |
| 8.3 | Scripts | LOW | 19 scripts with hardcoded user paths | Verified |
| 8.4 | Scripts | MEDIUM | ~10 of 23 API routers lack dedicated tests | Verified |
| 8.5 | Scripts | LOW | ~20-30 analysis scripts could be archived | Verified |
| 6.1 | Frontend | POSITIVE | Zero hardcoded URLs, clean API proxy | Verified |
| 6.2 | Frontend | MEDIUM | Thin accessibility coverage | Verified |
| 9.1 | Docs | MEDIUM | Phantom file reference (UNIFIED_PLATFORM_REDESIGN_SPEC) | Verified |
| 9.2 | Docs | LOW | Phantom roadmap reference (_02_17) | Verified |
| 9.3 | Docs | MEDIUM | PROJECT_STATE.md location mismatch | Verified |
| 9.4 | Docs | HIGH | Factor count inconsistencies (7 vs 8 vs 9) | Verified |
| 9.5 | Docs | HIGH | Stale tier names in MV guide | Verified |
| 9.6 | Docs | MEDIUM | 3 scripts missing from PIPELINE_MANIFEST | Verified |
| 9.7 | Docs | MEDIUM | Test count discrepancy (492 vs 479) | Verified |
| 9.8 | Docs | MEDIUM | master_employers count confusion (3 different numbers) | Verified |
| 11.1 | Blind Spots | CRITICAL | 94.6% Priority has no post-2020 activity | Verified |
| 11.2 | Blind Spots | CRITICAL | 55.7% of union election wins invisible to platform | Verified |
| 11.3 | Blind Spots | HIGH | 56.4% employers zero external sources; 13,698 rated Priority/Strong | Verified |
| 11.4 | Blind Spots | HIGH | Amazon/Walmart entirely absent from platform | Verified |
| 11.5 | Blind Spots | MEDIUM | 2.6x OSHA match rate disparity across states | Verified |
| 11.6 | Blind Spots | HIGH | No database backup strategy | Verified |
| 11.7 | Blind Spots | HIGH | nlrb_participants.case_number missing index (1.9M rows) | Verified |
| 11.8 | Blind Spots | MEDIUM | 2 scripts use blocking MV refresh | Verified |

**Total findings: 57** (10 CRITICAL, 13 HIGH, 21 MEDIUM, 8 LOW, 5 POSITIVE)

---

*Report generated by Claude Code (Opus 4.6) on February 22, 2026. All findings are based on actual database queries and code inspection against the live `olms_multiyear` database.*
