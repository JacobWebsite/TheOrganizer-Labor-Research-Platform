# Improving Matching Implementation (2/15)

## Goal
Strengthen matching quality, coverage, and explainability while keeping the current 5-tier pipeline as the primary engine.

## Scope
- Employer-to-employer matching across F7, OSHA, NLRB, Mergent, WHD, 990, SAM.
- Union linkage consistency (`f_num`, local/state heuristics where needed).
- Crosswalk + hierarchy integration for downstream analytics and API search.

## Phase 1: Standardize Outputs and Policy (Week 1)

- [ ] Create a single match result schema used by all matchers.
  - Files:
    - `scripts/matching/matchers/base.py`
    - `scripts/matching/pipeline.py`
  - Add/standardize fields:
    - `source_system`, `source_id`, `target_system`, `target_id`
    - `method`, `tier`, `score`, `confidence`
    - `confidence_band` (`HIGH`, `MEDIUM`, `LOW`)
    - `run_id`, `matched_at`, `evidence_json`

- [ ] Centralize scenario threshold policy.
  - Files:
    - `scripts/matching/config.py`
  - Actions:
    - Add per-scenario accept/review/reject thresholds.
    - Add a confidence-band policy table/dict by tier and score.

- [ ] Apply policy in pipeline execution and persisted run output.
  - Files:
    - `scripts/matching/pipeline.py`
  - Tables:
    - `match_runs`
    - `match_run_results`
  - Actions:
    - Persist `tier`, `confidence_band`, `metadata/evidence`.
    - Persist rejected and review-required rows (not only matched rows).

- [ ] Expose policy and result format in CLI.
  - Files:
    - `scripts/matching/cli.py`
  - Actions:
    - Add flags to print threshold policy and confidence-band counts.

## Phase 2: Deterministic Hardening (Week 1-2)

- [ ] Tighten normalization consistency across match paths.
  - Files:
    - `scripts/matching/normalizer.py`
    - `scripts/import/name_normalizer.py`
    - `scripts/matching/matchers/exact.py`
    - `scripts/matching/matchers/address.py`
  - Actions:
    - Ensure one canonical normalization path per level (`standard`, `aggressive`, `fuzzy`).
    - Ensure the same state/city normalization in every matcher.

- [ ] Improve conflict resolution for one-to-many candidates.
  - Files:
    - `scripts/matching/pipeline.py`
    - `scripts/matching/matchers/exact.py`
  - Actions:
    - Prefer exact ID matches over name/address/fuzzy.
    - Add deterministic tie-breakers (state exact, city exact, higher score, newest source row).

- [ ] Strengthen address tier evidence for auditability.
  - Files:
    - `scripts/matching/matchers/address.py`
  - Actions:
    - Persist street number extracted, target address snippet, and name similarity in evidence.

## Phase 3: Probabilistic Fallback for Unresolved/Conflicted (Week 2-3)

- [ ] Route only unresolved and conflict cases to Splink.
  - Files:
    - `scripts/matching/pipeline.py`
    - `scripts/matching/splink_pipeline.py`
    - `scripts/matching/splink_config.py`
  - Actions:
    - Add fallback handoff from deterministic to Splink for unresolved records.
    - Track handoff counts per scenario.

- [ ] Integrate accepted Splink outputs with explicit provenance.
  - Files:
    - `scripts/matching/splink_integrate.py`
    - `scripts/etl/build_crosswalk.py`
  - Tables:
    - `corporate_identifier_crosswalk`
  - Actions:
    - Tag records as `source_method = SPLINK`.
    - Persist Splink probability and threshold used.

- [ ] Add scenario-level Splink thresholds (not one global threshold).
  - Files:
    - `scripts/matching/splink_config.py`
  - Actions:
    - Tune thresholds separately for `nlrb_to_f7`, `osha_to_f7`, `mergent_to_f7`, etc.

## Phase 4: Manual Review Queue + Feedback Loop (Week 3)

- [ ] Create review queue for `MEDIUM` confidence and tie cases.
  - Files:
    - `api/` (new router; recommended `api/routers/matching_review.py`)
    - `scripts/matching/pipeline.py`
  - Tables (new):
    - `match_review_queue`
    - `match_review_decisions`
  - Actions:
    - Write review candidates automatically during batch runs.
    - Store reviewer decision and reason code.

- [ ] Feed human decisions back into threshold tuning.
  - Files:
    - `scripts/matching/differ.py`
    - `scripts/matching/splink_pipeline.py`
  - Actions:
    - Build monthly calibration report from accepted/rejected decisions.

## Phase 5: Data Product Integration (Week 3-4)

- [ ] Ensure all downstream views consume canonical accepted links only.
  - Files:
    - `scripts/etl/setup_unified_search.py`
    - relevant views in `sql/` and materialized views used by API
  - Tables/views to verify:
    - `mv_employer_search`
    - `osha_f7_matches`
    - `whd_f7_matches`
    - `nlrb_employer_xref`
    - `corporate_identifier_crosswalk`

- [ ] Add explainability fields to APIs for matched entities.
  - Files:
    - `api/routers/employers.py`
    - `api/routers/corporate.py`
    - `api/routers/osha.py`
    - `api/routers/whd.py`
  - Actions:
    - Return `match_method`, `confidence_band`, and top evidence fields.

## Phase 6: QA, Monitoring, and Drift (Ongoing)

- [ ] Add scenario QA scripts with required metrics.
  - Files:
    - `scripts/maintenance/check_nlrb_matching.py`
    - `scripts/maintenance/check_tallies_matching.py`
    - `scripts/maintenance/check_match_status.py`
    - (new) `scripts/maintenance/matching_quality_dashboard.py`
  - Required metrics:
    - match rate by scenario, by tier, by confidence band
    - false-positive sample rate for fuzzy tiers
    - unresolved rate trend
    - state-level variance alerts

- [ ] Add tests for deterministic tiers + fallback routing.
  - Files:
    - `tests/` (new module recommended: `tests/test_matching_pipeline.py`)
  - Minimum tests:
    - exact EIN precedence
    - state mismatch rejection
    - address tier evidence capture
    - fuzzy threshold boundary behavior
    - unresolved handoff to Splink

## Use Cases and Implementation Mapping

1. Unified employer search and scoring
- Sources: F7 + OSHA + WHD + NLRB + Mergent + 990 + SAM
- Core files: `scripts/matching/pipeline.py`, `scripts/etl/setup_unified_search.py`
- Output: cleaner `mv_employer_search` and scoring inputs.

2. Union-employer relationship quality
- Sources: F7 relations + union master
- Core files/tables: `f7_union_employer_relations`, `unions_master`, `f7_employers_deduped`
- Output: higher quality employer attribution for union strategy.

3. Corporate family expansion
- Sources: SEC + GLEIF + Mergent + USASpending + SAM + 990
- Core files: `scripts/etl/build_crosswalk.py`, `scripts/matching/splink_integrate.py`
- Output: better parent-child rollups and leverage analysis.

4. Web-scraped local union data linking
- Sources: web profile extraction + OLMS + employer match
- Core files: `scripts/etl/setup_afscme_scraper.py`, `scripts/scraper/match_web_employers.py`
- Output: improved local union context and public-sector gap coverage.

## Execution Order (Recommended)

- [ ] Complete Phase 1 before any new source integrations.
- [ ] Complete Phase 2 before tuning fuzzy thresholds.
- [ ] Complete Phase 3 and Phase 4 together (fallback + review queue).
- [ ] Complete Phase 5 after confidence policy is stable for 2 weeks.
- [ ] Run Phase 6 continuously with weekly reports.

## Definition of Done

- [ ] Every match row has method, tier, confidence band, and evidence.
- [ ] Deterministic + Splink fallback is active in batch and reproducible by run ID.
- [ ] Manual review queue is operational with decision capture.
- [ ] APIs expose match explainability fields.
- [ ] QA report shows stable or improved precision/coverage over baseline.
