# Phase 4: Matching Quality & Research Improvements (2026-03-03)

- **4-4:** Match method naming normalization -- 17,516 lowercase methods in UML normalized to UPPER. Guards added to `_make_result()` and all 4 adapters.
- **4-1:** `score_eligible BOOLEAN` column added to osha/whd/sam/n990_f7_matches. Rules: eligible if confidence >= 0.85 OR method in (EIN_EXACT, CROSSWALK, CIK_BRIDGE). Scoring CTEs (osha_agg, whd_agg, financial_990) filter on `score_eligible = TRUE`. Impact: 23,523 matches (16.2%) initially marked ineligible.
- **4-2/4-3:** Corroboration system joins source tables (city/ZIP/NAICS) to F7 employers. Score: city=+2, ZIP=+3, NAICS-2digit=+2. Threshold >= 2 promotes to eligible. Result: 17,894 of 22,036 quarantine matches promoted; only 4,142 remain truly ineligible (2.9% of all matches).
- **4-6:** `cross_validate_against_db()` in auto_grader.py compares research findings (OSHA violations, NLRB elections, WHD cases, employee count) vs actual DB. Stores `cross_validation_rate` + `cross_validation_discrepancies` on `research_score_enhancements`. Integrated into `grade_and_save()` pipeline. API returns in `/api/research/result/{id}`.
- **4-7:** UML evidence fallback tier in `employer_lookup.py` -- trigram search on `unified_match_log.evidence->>'source_name'`. Auto-linkage in agent.py post-run handler attempts lookup if employer_id is NULL after research completes.
- **4-8:** `GET /api/research/tool-effectiveness` endpoint with overall stats, per-industry strategies, and pruning recommendations. Configurable env vars: `RESEARCH_PRUNE_HIT_RATE` (0.10), `RESEARCH_PRUNE_MIN_TRIES` (5), `RESEARCH_LATENCY_SKIP_MS` (15000), `RESEARCH_LATENCY_SKIP_HIT_RATE` (0.20), `RESEARCH_LATENCY_SKIP_MIN_TRIES` (3). Agent.py uses these instead of hardcoded values + adds latency-based skip.
- **Deferred:** 4-9 (match review UI), 4-5 (confidence recalibration)
- **New scripts:** `normalize_match_methods.py`, `add_score_eligible.py`, `corroborate_matches.py`, `measure_score_eligible_impact.py`
- **New tests:** test_match_method_normalization (10), test_score_eligible (19), test_corroboration (8), test_cross_validation (9), test_employer_linkage_retry (4), test_tool_effectiveness (5) = **55 new tests**
- **New DB columns:** `score_eligible` on 4 legacy match tables; `cross_validation_rate`, `cross_validation_discrepancies` on `research_score_enhancements`
- **Frontend:** "Unverified match" amber badge on low-confidence OSHA establishments; WHD section-level unverified warning banner
- **Key gotcha:** `f7_employers_deduped` size column is `latest_unit_size` NOT `company_size`
- **MV rebuilt (2026-03-03):** All 7 steps passed. Tiers: Priority 2,755 | Strong 15,830 | Promising 40,139 | Moderate 51,367 | Low 36,772. OSHA coverage dropped 22.3% -> 19.7% (ineligible matches excluded from scoring). 681 employers lost all OSHA scoring data; 238 lost all WHD.
- **Impact:** 5,629 total matches excluded (2,702 OSHA + 439 WHD + 1,001 SAM + 1,487 990)
