# Batch Details (2026-03)

## Audit Batch 2 Details (2026-03-01)
- **1-9:** Advisory lock on admin refresh endpoint (`pipeline_lock(conn, 'scorecard_mv')`, 409 on contention)
- **1-3:** OSHA severity weighting (willful x3, repeat x2, serious x1, other x0.5)
- **1-4:** `has_compound_enforcement` flag + API filter (5,197 employers with both OSHA + WHD)
- **1-5:** WHD child labor + repeat violator flags/badges (`has_child_labor`: 287, `is_whd_repeat_violator`: 697)
- **1-6:** NLRB close election flag/badge (`has_close_election`: 1,079, lost by <=5 votes with >10 voters)
- **MV columns added:** `has_compound_enforcement`, `has_child_labor`, `is_whd_repeat_violator`, `whd_child_labor_count`, `has_close_election`, `nlrb_close_election_count`, `nlrb_closest_margin`

## Phase R2 Details
- **DB:** `research_runs.run_usefulness/run_usefulness_at`, `research_facts.review_source`, `research_run_comparisons` table
- **API:** 6 new endpoints in `api/routers/research.py` (usefulness, flag, auto-confirm, section review, priority-facts, compare GET+POST)
- **Learning:** 3 new functions in `auto_grader.py` (apply_run_usefulness, apply_bulk_fact_reviews, apply_comparison_verdict)
- **Frontend:** PriorityReviewCard.jsx, CompareRunsPage.jsx (new); DossierHeader/FactRow/DossierSection/ResearchResultPage (updated); `/research/compare` route
- **Hooks:** useSetRunUsefulness, useFlagFact, useAutoConfirmFacts, useReviewSection, usePriorityFacts, useCompareRuns, useSubmitComparison

## Pillar Weight Validation (2026-03-02)
- Logistic regression on 6,403 NLRB elections linked to scored employers
- Anger strongest predictor (coeff 0.12), stability slightly negative (-0.05), leverage weak (0.03)
- Model accuracy = base win rate (79.9%) -- pillars don't add marginal predictive power
- **Key insight:** Pillars aren't meant to predict election outcomes. They flag structural signals for investigation. Predictive accuracy is not the goal.
- Suggested proportional weights (anger 6.2, stability 2.3, leverage 1.5) noted but NOT applied
- **Decision:** Keep current weights (anger 3, stability 0, leverage 4). Deserves deeper investigation in future.
- Results saved to `docs/pillar_weight_validation.csv`

## Batch 4 Details (2026-03-02)
- **1-11:** UnifiedScorecardPage (`/scorecard` route) -- browse all F7 employers with filters, tier bar, factors badges, flag badges
- **1-12:** DataSourceBadge component -- three-state badges (Present/No Records/Not Matched) on OSHA, NLRB, WHD, SAM, Financial sections
- **1-13:** factors_available display in ProfileHeader -- color-coded badge (green >=5, gold >=3, amber <3)
- **3-1:** Form 5500 already flowing via `financial_form5500` CTE -- 13,414 employers with score_financial, no fix needed
- **3-2:** Tiered contracts VERIFIED already working (scores 2/4/6/8/10 across 9,305 employers)
- **3-3:** PPP size fallback added to `build_unified_scorecard.py` -- `ppp_size` CTE + `size_source` column. Currently 0 F7 employers benefit (all 6,017 PPP-matched already have other size data)
- **3-7:** NAICS inference scripts re-run -- 0 new inferences (low-hanging fruit already picked, 15,659 still null)
- **3-9:** BMF adapter: 8 active matches from 2M rows -- superseded by crosswalk EIN path, archive candidate
- **Stale test fixed:** `test_weighted_score_formula_consistency` had old formula (anger+stability+leverage)/10, updated to dynamic denominator
- **New files:** `scorecard.js` (API hooks), `UnifiedScorecardPage.jsx`, `UnifiedScorecardTable.jsx`, `DataSourceBadge.jsx`, `UnifiedScorecardPage.test.jsx`
- **MV columns added:** `size_source` (company_size/f7_unit_size/ppp_2020/NULL)
