# Phase 5 Execution Plan: Scoring Evolution

**Date:** 2026-02-16
**Status:** PLANNING
**Dependencies:** Phase 4 complete, 253/253 tests passing

---

## Execution Timeline

```
WAVE 1 (parallel):
  Claude: 5.1 Temporal Decay (MV rewrite + API + tests)
  Codex:  5.2 Hierarchical NAICS Similarity (algorithm + tests)
  Gemini: 5.5 Propensity Model Design (feature selection + architecture)

WAVE 2 (after Wave 1):
  Codex:  Code review of 5.1 (temporal decay)
  Claude: 5.3 Score Version Tracking (schema + MV + API)
  Gemini: 5.4 Gower Enhancement Review (weight rationale + math)

WAVE 3 (after Wave 2):
  Claude: 5.4 Gower Enhancement Implementation
  Claude: 5.5 Propensity Model Implementation
  Codex:  Code review of 5.3 + 5.4

WAVE 4:
  Claude: Integration testing, MV refresh, full scorecard validation
```

---

## WAVE 1 PROMPTS

### Codex Prompt: 5.2 Hierarchical NAICS Similarity

**When to send:** Immediately when starting Phase 5 (same time Claude starts 5.1)

```
TASK: Implement hierarchical NAICS similarity scoring to replace binary NAICS matching in the organizing scorecard.

CONTEXT:
The platform scores ~24,841 OSHA establishments for union organizing potential. Factor 2 (industry density) currently uses binary matching -- it looks up the employer's 2-digit NAICS code in v_naics_union_density and assigns points based on that single sector's union density rate:
  >20% = 10, >10% = 8, >5% = 5, else = 2

This is crude. Two employers sharing 5 of 6 NAICS digits are treated identically to two sharing only 2 digits.

DELIVERABLE:
1. A SQL function or CTE that computes NAICS similarity as a gradient:
   - 6-digit exact match = 1.0
   - 5-digit match = 0.85
   - 4-digit match = 0.65
   - 3-digit match = 0.45
   - 2-digit match = 0.25
   - No match = 0.0

2. Modify the industry density scoring to use a WEIGHTED BLEND:
   - Primary: the employer's own 2-digit sector density (current behavior)
   - Enhancement: if we have estimated_state_industry_density for the employer's state + industry, use that instead of national-only
   - The similarity gradient multiplies the density contribution when comparing employers

3. Integration point: This needs to work within the MV SQL in create_scorecard_mv.py.

CURRENT MV SQL (Factor 2 -- industry density):
```sql
-- Factor 2: Industry density (10 pts)
CASE
    WHEN COALESCE(id.union_density_pct, 0) > 20 THEN 10
    WHEN COALESCE(id.union_density_pct, 0) > 10 THEN 8
    WHEN COALESCE(id.union_density_pct, 0) > 5 THEN 5
    ELSE 2
END AS score_industry_density,
```

The join:
```sql
LEFT JOIN industry_density id ON id.naics_2digit = LEFT(t.naics_code, 2)
```

AVAILABLE DATA:
- v_naics_union_density: naics_2digit, union_density_pct
- estimated_state_industry_density: year, state, industry_code, industry_name, national_rate, state_multiplier, estimated_density, confidence (459 rows, state x industry estimates from Phase 4)
- Employers have naics_code (up to 6 digits) and site_state

CONSTRAINTS:
- Must remain expressible as a single SQL CTE + CASE block (no PL/pgSQL functions -- the MV is a single CREATE MATERIALIZED VIEW statement)
- Score range must remain 0-10 integer
- Must handle NULL naics_code gracefully (default to 2 pts)
- Must be deterministic (same inputs = same output every time)

TESTS TO WRITE (pytest, using the project's test patterns):
- test_naics_hierarchy_6digit_exact()
- test_naics_hierarchy_partial_matches()
- test_naics_hierarchy_null_naics()
- test_naics_hierarchy_state_density_used_when_available()
- test_naics_hierarchy_falls_back_to_national()

OUTPUT: Return the complete replacement CTE + scoring CASE block, plus the test file. Do NOT modify any files -- return as code blocks for review.
```

---

### Gemini Prompt: 5.5 Propensity Model Design

**When to send:** Immediately when starting Phase 5 (same time as others)

```
TASK: Design the feature engineering, model architecture, and evaluation framework for an NLRB election outcome propensity model.

CONTEXT:
This is an experimental scoring model for a labor relations research platform. The goal: predict P(union_wins_election | employer_features) using logistic regression on historical NLRB election data. The predicted probability becomes an "AI-suggested opportunity score" shown alongside the existing 9-factor heuristic score.

TRAINING DATA:
- nlrb_elections: 33,096 elections, 99.1% have union_won (boolean) outcome
- Base rate: 68% union win (moderately imbalanced toward wins)
- election_type breakdown: Initial=32,168 (67.9% win), Rerun=788 (46.6% win), Runoff=83 (72.3% win)
- Columns: case_number, election_type, election_date, ballot_type, eligible_voters, void_ballots, challenges, runoff_required, total_votes, union_won, vote_margin

JOIN PATH TO EMPLOYER FEATURES:
nlrb_elections.case_number -> nlrb_participants (where participant_type = 'Employer') -> matched_employer_id -> f7_employers_deduped.employer_id -> osha_f7_matches -> mv_organizing_scorecard.establishment_id

CHALLENGE: Not all elections will join successfully. nlrb_participants.matched_employer_id is only set for representation cases (RC/RD/RM). Expect ~30-50% join rate to the full feature set.

AVAILABLE FEATURE SOURCES:

From nlrb_elections directly:
- eligible_voters (int), election_type, ballot_type, election_date (year, month, day-of-week)

From nlrb_participants (via case_number):
- participant_type, participant_name (employer name)
- state (from participant address)

From mv_organizing_scorecard (via join chain above):
- 9 existing score factors (each 0-10 int)
- employee_count, total_violations, total_penalties, osha_industry_ratio
- willful_count, repeat_count, serious_count
- naics_code, site_state

From estimated_state_industry_density (via state + naics_code):
- estimated_density, national_rate, state_multiplier

From bls_industry_occupation_matrix (via naics_code):
- Top occupation mix for the industry

From employer_comparables (269K rows):
- gower_distance to nearest unionized employer
- feature_breakdown (JSONB with per-feature distances)

DESIGN QUESTIONS TO ANSWER:

1. FEATURE ENGINEERING
   - Which raw features become model inputs?
   - How to handle the ~50-70% of elections that WON'T join to the scorecard?
   - Should we train two models (one with full features for joined elections, one with election-only features for all)?
   - How to encode categorical variables (state, NAICS sector, election_type)?
   - Any interaction terms worth including?

2. MODEL ARCHITECTURE
   - Logistic regression is the plan. Should we also benchmark against random forest / gradient boosting as a sanity check?
   - Regularization strategy (L1/L2/ElasticNet)?
   - How to handle the 68/32 class imbalance?

3. EVALUATION FRAMEWORK
   - Train/test split strategy (temporal split by election_date vs random?)
   - Success threshold: AUC > 0.65 to ship as experimental, AUC > 0.55 means features need work
   - What additional metrics beyond AUC? (calibration, precision@k for top-decile targeting)
   - How to validate that the model isn't just learning "state + year" as a proxy?

4. DEPLOYMENT INTEGRATION
   - Output: P(union_win) per employer, stored where?
   - How to handle employers with no NLRB history (the majority)?
   - Versioning: how to track model version alongside score version?
   - Refresh cadence: retrain when new election data arrives?

5. ETHICAL CONSIDERATIONS
   - This predicts organizing success, not whether organizing SHOULD happen
   - Any features that could introduce problematic bias?
   - How to communicate uncertainty to end users?

OUTPUT: A design document with:
- Recommended feature list (with rationale for each)
- Model pipeline architecture (data prep -> train -> evaluate -> deploy)
- Evaluation protocol
- Risk assessment
- Estimated data requirements (minimum N for reliable training)

Do NOT write implementation code. This is architecture + design only.
```

---

## WAVE 2 PROMPTS

### Codex Prompt: Code Review of 5.1 (Temporal Decay)

**When to send:** After Claude completes 5.1 temporal decay implementation

```
TASK: Code review the temporal decay implementation for the organizing scorecard.

CONTEXT:
Phase 5.1 adds time-based decay to three scoring factors: OSHA violations (Factor 5), WHD wage theft (if integrated), and NLRB patterns (Factor 6). Recent events should weigh more than old ones.

REVIEW CHECKLIST:
1. DECAY FORMULA: Is the exponential decay mathematically sound? Expected: weight = exp(-lambda * years_ago), with configurable half-lives per factor.
2. EDGE CASES: What happens when dates are NULL? When all violations are >10 years old? When the decay reduces a score below the minimum?
3. MV REFRESH: Does the decay change mean the MV needs more frequent refreshes? (Scores become stale as time passes even without new data.)
4. SCORE DRIFT: Do list scores still match detail scores? (Both must read from the same MV.)
5. BACKWARD COMPATIBILITY: Does score_version tracking properly distinguish pre-decay and post-decay scores?
6. PERFORMANCE: Is the decay computation in SQL efficient? No sequential scans on large tables?
7. TEST COVERAGE: Are there tests for boundary dates, NULL dates, and score stability?

[PASTE MODIFIED FILES HERE WHEN SENDING]

OUTPUT: Return findings as: CRITICAL (must fix), IMPORTANT (should fix), SUGGESTION (nice to have).
```

---

### Gemini Prompt: 5.4 Gower Enhancement Review

**When to send:** After Wave 1 completes (alongside Codex review of 5.1)

```
TASK: Review the proposed Gower distance enhancement for the organizing scorecard's similarity factor.

CONTEXT:
The platform has an employer_comparables table (269,785 rows) with Gower distances between employers. Currently, Factor 9 (similarity) uses mergent_employers.similarity_score with simple thresholds:
  >=0.80 = 10, >=0.60 = 7, >=0.40 = 4, IS NOT NULL = 1, else = 0

PROPOSED ENHANCEMENTS:
1. Weighted dimensions: industry similarity (3x weight), OSHA violations (2x weight), state (1x), size (1x)
2. New metric: "distance from nearest unionized sibling" as a scoring factor
3. Integration with Phase 4 occupation similarity data (8,731 pairs in occupation_similarity table, cosine similarity on industry co-occurrence vectors)

REVIEW QUESTIONS:
1. WEIGHT RATIONALE: Are the proposed 3x/2x/1x/1x weights defensible? What evidence supports industry being 3x more important than state?
2. MATHEMATICAL SOUNDNESS: Does "distance from nearest unionized sibling" make sense as a scoring signal? What are the failure modes?
3. COLD START: What happens for employers with no comparables? Currently 0 points. Should there be a population-level fallback?
4. OCCUPATION INTEGRATION: The occupation_similarity table uses cosine similarity (different scale than Gower). How should these be combined?
5. SCORE SENSITIVITY: If we change the Gower weights, all 269K comparables need recomputation. Is this a one-time cost or recurring?
6. CIRCULARITY RISK: If the similarity score is based partly on OSHA violations, and OSHA violations is already a separate scoring factor, are we double-counting?

OUTPUT: Architecture review with recommendations for each question. Flag any design issues that should be resolved before implementation.
```

---

## WAVE 3 PROMPTS

### Codex Prompt: Code Review of 5.3 + 5.4

**When to send:** After Claude completes score versioning and Gower enhancement

```
TASK: Code review the score versioning system and Gower enhancement implementation.

REVIEW FOCUS:

SCORE VERSIONING (5.3):
1. Where is the version stored? (MV column? Separate table? API response?)
2. Can you query historical scores for a given employer across versions?
3. Does the version increment automatically on MV rebuild, or manually?
4. Are version identifiers meaningful (semver? sequential int? timestamp?)

GOWER ENHANCEMENT (5.4):
1. Are the weighted dimensions correctly normalized before combining?
2. Does "distance from nearest unionized sibling" handle the case where NO siblings are unionized?
3. Is the recomputation of 269K comparables efficient? Batch vs row-by-row?
4. Does the occupation similarity integration preserve the Gower distance semantics?

[PASTE MODIFIED FILES HERE WHEN SENDING]

OUTPUT: CRITICAL / IMPORTANT / SUGGESTION findings.
```

---

## WHAT CLAUDE DOES (implementation notes for our sessions)

### 5.1 Temporal Decay (Wave 1)
- Add `last_inspection_date` age calculation to OSHA factor
- Exponential decay: `weight = exp(-0.693 * years / half_life)` (half_life = 5 years for OSHA, 3 years for NLRB)
- OSHA: weight violations by recency of inspection
- NLRB: weight predicted win rate by recency of election data (if available)
- Geographic/density/size/contracts/projections: NO DECAY (these are structural, not event-based)
- Update MV SQL, create_scorecard_mv.py, wrapper view, API explanations
- Tests: decay at boundaries (0yr, 1yr, 5yr, 10yr, 20yr), NULL dates, score range preservation

### 5.3 Score Version Tracking (Wave 2)
- New table: `score_versions` (version_id SERIAL, created_at, description, factor_weights JSONB, decay_params JSONB)
- Add `score_version_id` column to MV
- API: include score_version in response, add `GET /api/admin/score-versions` endpoint
- On MV rebuild: auto-insert new version row, stamp all MV rows

### 5.4 Gower Enhancement (Wave 3)
- Recompute employer_comparables with weighted dimensions per Gemini's review
- Add "distance from nearest unionized employer" to MV
- Integrate occupation similarity where available
- Update Factor 9 thresholds based on new distribution

### 5.5 Propensity Model (Wave 3)
- Build per Gemini's design doc
- Logistic regression with scikit-learn
- Store predictions in new table, surface as experimental score in API
- Frontend: show as separate "AI Experimental" score, NOT replacing the 9-factor score

---

## Success Criteria (from roadmap)
- [ ] Temporal decay applied to OSHA, WHD, and NLRB factors
- [ ] Hierarchical NAICS similarity replacing binary matching
- [ ] Score versioning in place
- [ ] Propensity model built and measured (even if experimental)
- [ ] All existing tests still pass + new Phase 5 tests
