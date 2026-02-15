# Sprint 5 Employer Matching Test Strategy

You should add tests in four layers: unit normalization, candidate generation, ranking/selection, and post-run data quality.

## 1) Edge cases you likely need (and often get missed)

- Common-name collisions: `"American Services Inc"` in same state with multiple real employers; assert high precision and no random tie wins.
- Multi-state employers: same normalized name in many states; assert state constraint blocks cross-state matches unless explicitly allowed.
- Multi-location in same state: same name, different cities; assert geo signal improves ranking but does not override stronger EIN/exact evidence.
- Parent vs subsidiary: `"Acme Holdings"` vs `"Acme Manufacturing LLC"`; assert parent does not absorb subsidiary records without strong evidence.
- DBA/aka variants: `"ABC Logistics"` vs `"ABC Logistics dba Fast Freight"`; assert expected canonicalization behavior.
- Historical renames: `"Facebook"` vs `"Meta Platforms"` style cases; assert alias/history mapping works (or fails safely if no mapping).
- M&A transitions: acquired company names still present in source systems; assert old names map to expected surviving entity when crosswalk exists.
- Legal suffix noise: `Inc`, `LLC`, `LP`, `Co`, `Corp`, pluralization, punctuation, ampersand/and normalization.
- Abbreviation ambiguity: `Intl`, `Svcs`, `Mfg`, `Ctr`, `Univ`; assert controlled abbreviation map and no over-expansion.
- Token-order issues: `"Services American"` vs `"American Services"`; verify trigram threshold behavior.
- EIN quality issues: missing, partial, malformed, reused/test EINs; ensure EIN does not dominate when invalid.
- Non-ASCII/encoding drift: accented chars, smart quotes, bad OCR punctuation.
- Null/empty fields: missing city/state/name fragments; assert deterministic fallback path.
- Ties at threshold boundary: exactly `0.75`, `0.80`, `0.85`; lock expected inclusive/exclusive behavior.
- Very long names and stopword-heavy names: ensure no truncation bugs or over-matching.

## 2) Regression tests to prevent Sprint 5 cross-source damage

- Golden set snapshots per source:
  1. Fixed labeled truth sets for OSHA, WHD, 990 (positive and hard negatives).
  2. Assert precision/recall/F1 per source do not regress beyond tolerance.
- Baseline diff tests:
  1. Compare new run vs previous blessed run.
  2. Fail on unexpected large drops/spikes in match count per source/state/industry.
- Contract tests for shared utilities:
  1. Name normalization output unchanged for a curated corpus unless intentionally updated.
  2. Similarity scoring function monotonicity and weights unchanged unless version-bumped.
- Source-isolation tests:
  1. Run OSHA improvements with WHD/990 fixtures and assert identical outputs for unaffected cases.
  2. Explicit “no cross-source side effects” test on shared ranking code.
- Threshold guardrails:
  1. Parameterized tests over threshold configs.
  2. Ensure config changes are explicit and audited, not accidental defaults.
- Determinism test:
  1. Same input twice yields same best match and score ordering.

## 3) Post-batch validation tests (data-quality gates after job run)

Run these as mandatory checks before publishing results:

- Integrity:
  1. No null `source_id`, `target_employer_id`, or score in accepted matches.
  2. No duplicate `(source_system, source_record_id)` accepted more than once unless business rule allows one-to-many.
  3. No duplicate exact match rows after dedupe.
- Logical consistency:
  1. No self-match (`source` entity mapped to itself when that is invalid in your model).
  2. No contradictory statuses (same pair both `matched` and `rejected`).
  3. No circular parent-child implications if your output constructs linkage graphs.
- Threshold consistency:
  1. All accepted matches `score >= acceptance_threshold`.
  2. All rejected matches below threshold (or explicitly human-overridden with reason).
- Distribution drift:
  1. Match rate by source (OSHA/WHD/990) within expected control limits.
  2. Score distribution drift checks (mean/percentiles) against prior run.
  3. State-level outlier detection (sudden collapse in one state).
- Business sanity:
  1. Top common-name entities manually sampled each run.
  2. EIN-based matches have high confirmation rate.
  3. Geo-only matches capped and reviewed.
- Auditability:
  1. Every accepted match stores rule path (`exact`, `fuzzy+state`, `ein`, `geo`) and version/hash of matcher config.
  2. Batch metadata captured: input snapshot date, code version, thresholds.

## 4) Entity-resolution testing patterns worth adopting

- Labeled benchmark set:
  1. Maintain a versioned truth dataset with hard positives/negatives and ambiguous cases.
  2. Track precision, recall, F1, and precision@k.
- Pairwise + cluster evaluation:
  1. Pairwise metrics for match decisions.
  2. Cluster metrics (B-cubed/CEAF-style) if you form entity groups across multiple records.
- Blocking evaluation:
  1. Test candidate-generation recall separately from final classifier/ranker.
  2. Ensure blocking does not silently drop true matches.
- Calibration checks:
  1. Reliability curve for match scores vs actual correctness.
  2. Threshold chosen by business cost (false match vs missed match), not arbitrary.
- Metamorphic/property tests:
  1. Invariance to punctuation/case/suffix edits.
  2. Monotonic behavior when adding corroborating evidence (valid EIN should not reduce confidence).
- Adversarial test suite:
  1. Synthetic near-duplicates and common-name collisions.
  2. Regression corpus built from past production incidents.
- Human-in-the-loop QA:
  1. Stratified sampling of borderline scores each run.
  2. Feed adjudications back into benchmark and future tests.
