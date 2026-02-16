# Matching Module Architecture Review (Focused Task 3)

This review covers:
- `scripts/matching/__init__.py`
- `scripts/matching/config.py`
- `scripts/matching/normalizer.py`
- `scripts/matching/pipeline.py`
- `scripts/matching/differ.py`
- `scripts/matching/cli.py`
- `scripts/matching/matchers/base.py`
- `scripts/matching/matchers/exact.py`
- `scripts/matching/matchers/address.py`
- `scripts/matching/matchers/fuzzy.py`

## 1) Is the architecture well-designed? Can new scenarios be added easily?

Short answer: mostly yes, but there are important risks.

What is good:
- New match scenarios are easy to add in one place (`SCENARIOS` in `scripts/matching/config.py`).
- Match logic is split into classes by strategy (`EIN`, normalized, address, aggressive, fuzzy), which is clean.
- Shared output shape (`MatchResult`) is consistent via `BaseMatcher._create_result` in `scripts/matching/matchers/base.py`.

What is weak:
- SQL is built with many f-strings using table/column/filter values from config (example patterns in `scripts/matching/pipeline.py:151`, `scripts/matching/matchers/exact.py:50`, `scripts/matching/matchers/fuzzy.py:125`, `scripts/matching/matchers/address.py:165`).
- If a future scenario is built from user input, this becomes SQL injection risk.
- The pipeline stores all matched results in memory (`self.stats.results.append(...)` in `scripts/matching/pipeline.py:209`). Large runs can use too much memory.

## 2) Code paths that can produce wrong results

### High-risk correctness issues

1) Address batch mode uses hardcoded keys, not scenario keys.
- File: `scripts/matching/matchers/address.py:222`
- It uses `record.get("id")`, `record.get("name")`, `record.get("address")`.
- Many scenarios do not use those field names.
- Result: wrong IDs/names can be sent to matcher, causing missed or wrong matches.

2) City requirement can be ignored in normalized batch path.
- File: `scripts/matching/matchers/exact.py:225`
- Batch key only uses `(normalized_name, state)` and ignores city even when `require_city_match` is true.
- Result: same-name employers in same state but different cities can cross-match incorrectly.

3) Fuzzy matcher ignores city input.
- File: `scripts/matching/matchers/fuzzy.py:76`
- `city` is accepted by function signature but not used in filtering.
- Result: more false positives in multi-city states.

4) Diff report markdown formatter has broken f-strings.
- File: `scripts/matching/differ.py:265`
- Pattern like `{entry.new_score:.3f if entry.new_score else 'N/A'}` is invalid formatting.
- Result: report generation can fail at runtime.

## 3) Confidence scoring consistency across tiers

Not fully consistent:
- Tier confidence labels are static by tier (`HIGH/MEDIUM/LOW`) from `scripts/matching/config.py`.
- But numeric scores are mixed styles:
- `EIN` and normalized return `1.0`.
- Aggressive returns `0.95`.
- Address returns raw similarity score (can be near `0.4` threshold).
- Fuzzy returns composite threshold score (often around threshold).

Impact:
- Two records both labeled `HIGH` can have very different score semantics depending on matcher.
- Harder to compare quality across tiers.

## 4) Unicode and special character handling in fuzzy matching

Partially handled, but not fully safe:
- Good: fallback tests exist for accented text in separate normalization tests.
- Risk: module relies on regex cleanup and external normalizer behavior; no explicit Unicode normalization (`NFKD/NFC`) in `scripts/matching/normalizer.py`.
- Risk: `sys.path` injection import hack (`scripts/matching/normalizer.py:20`) can change behavior by environment.

Also, abbreviation dictionary has duplicate key:
- `scripts/matching/normalizer.py:71` and `scripts/matching/normalizer.py:72` both define `elem`.
- Not a crash, but signals weak config hygiene.

## 5) Race conditions / concurrency issues

If run in parallel, there are risks:
- Same DB connection object is shared across all matchers in pipeline.
- On any matcher exception, code does `rollback` and continues (`scripts/matching/pipeline.py:107`, `scripts/matching/pipeline.py:110`).
- In concurrent usage, one rollback can affect other in-flight work on the same connection.
- Run/result tables have basic keys, but no explicit run-level lock/guard for concurrent writes with same source IDs.

## 6) Error handling behavior

Current behavior hides failures:
- Pipeline catches matcher exceptions and keeps going (`scripts/matching/pipeline.py:107`).
- Address matcher swallows exceptions silently (`scripts/matching/matchers/address.py:211`, `scripts/matching/matchers/address.py:213`).
- This avoids full-run crashes, but can hide large quality regressions.

Operational effect:
- Runs can finish “successfully” while one tier is broken.
- Users see lower match rates without clear root-cause signal.

## Recommended fixes (priority order)

1) Replace dynamic SQL identifier building with safe identifier composition (`psycopg2.sql.Identifier`) and strict allowlists for table/column/filter inputs.
2) Fix address batch key usage to scenario columns instead of hardcoded `id/name/address`.
3) Include city in normalized batch key when `require_city_match` is true.
4) Add optional city filter in fuzzy matcher.
5) Fix broken diff formatter expressions in `scripts/matching/differ.py`.
6) Stop swallowing exceptions without metrics; count per-tier failures and surface in run stats.
7) Add explicit Unicode normalization in `normalizer.py` and remove `sys.path` import hack.
8) Stream results to DB in chunks instead of storing all matches in memory.
