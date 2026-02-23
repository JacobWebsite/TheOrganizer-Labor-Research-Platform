# Session Summary: 2026-02-23d — Phase 2 OSHA Matching + Codex Investigations

## Duration
~6 hours (mostly OSHA batch processing time)

## What Was Done

### 1. RapidFuzz Replaces Splink (Tier 5a Fuzzy Matching)
- **Problem:** Splink's Bayesian model overweighted geography (BF product ~8.5M), producing garbage matches even with name similarity floors.
- **Solution:** New `_fuzzy_batch_rapidfuzz()` method in `deterministic_matcher.py` using 3 blocking indexes (normalized name prefix, state, city) and `rapidfuzz.fuzz.token_sort_ratio >= 0.80`.
- **Performance:** ~2 min for 225K records (vs Splink's DuckDB overhead). Match method still writes `FUZZY_SPLINK_ADAPTIVE` for backward compat.
- **Files:** `scripts/matching/deterministic_matcher.py`, `tests/test_matching_pipeline.py`, `scripts/analysis/compare_splink_vs_rapidfuzz.py`

### 2. Full OSHA 4-Batch Re-run
- **Scale:** 982,717 total OSHA records across 4 batches (~250K each)
- **Duration:** ~6 hours total (trigram fallback phase is the bottleneck — pg_trgm SQL roundtrips)
- **Issues encountered:**
  - tqdm progress bars flooded output buffers, hiding completion summaries
  - `grep -v` pipe caused Python zombie processes on Windows (no SIGPIPE)
  - 3 concurrent batches caused DB contention (all doing pg_trgm queries)
  - `&&` chain broke when batch 3 task wrapper failed (exit 127), batch 4 had to be restarted manually
- **Results:** 53,800 active OSHA matches (up from 50,614 pre-Phase 2)

### 3. Maintenance Cleanup
- **Duplicate matches:** `resolve_duplicate_matches.py --commit` — 283 rows superseded (267 duplicate sets across OSHA/GLEIF/SEC/990)
- **Low-quality trigrams:** `reject_low_trigram.py --commit` — 10,881 rows superseded below 0.75 sim floor (OSHA: 6,792, SAM: 2,301, WHD: 952, SEC: 481, 990: 354)
- **Net effect:** Cleaned 11,164 low-quality matches from the system

### 4. Codex Investigations (I11-I17)
9 scripts created, 7 investigation reports, 1 test file:

| Investigation | Key Finding |
|---|---|
| I11 Trigram Quality | 8.3K matches below 0.75 floor (cleaned) |
| I12 Duplicate Matches | 103 duplicate active matches (resolved) |
| I13 Match Coverage Gaps | 107 files without tests, 2 with tests |
| I14 SAM Quality | 17,687 matches; 53.2% of fuzzy below 0.80 |
| I15 WHD Quality | 12,355 matches audited |
| I16 990 Quality | 13,872 matches audited |
| I17 State Coverage | 61 states, 7 low coverage (<30%), 0 high (>70%) |
| I8 Employer Grouping | 16,647 groups analyzed |
| API Performance | API not running during audit |

### 5. MV Rebuilds (All 4)
| MV | Rows | Key Metric |
|---|---|---|
| mv_unified_scorecard | 146,863 | avg=4.18, Priority=1.5% |
| mv_employer_data_sources | 146,863 | Source flags updated |
| mv_employer_search | 107,025 | Deduped search index |
| mv_organizing_scorecard | 212,072 | v86, avg=32.3 |

### 6. Test Fixes
- `test_most_employers_have_financial_factor`: Changed threshold from 80% to >5,000 (only 990-sourced employers have score_financial)
- `test_weighted_score_formula_consistency`: Replaced `score_similarity` with `score_financial` to match actual MV formula
- **Final:** 497 pass / 1 skip (backend), 156 pass (frontend)

### 7. Frontend Dossier Improvements (Codex)
- Smart type-aware rendering for research dossier (arrays as lists, objects as tables, nested key-value pairs)
- Updated section order to match API structure
- Handle nested dossier JSON properly

## Commits
| Hash | Description | Files |
|---|---|---|
| `ef37d3c` | Codex investigation reports, audit scripts, maintenance tools | 21 |
| `6e1fac8` | Replace Splink with RapidFuzz for tier 5a + session summaries | 9 |
| `748e63d` | Earlier Codex investigations, grouping improvements, misc | 10 |
| `40d2c4e` | Dossier rendering improvements | 3 |
| `fc62abc` | Fix scorecard test expectations for Phase 1 changes | 2 |

## Final Match Counts (Post-Phase 2)
| Source | Active | Change |
|---|---|---|
| OSHA | 53,800 | +3,186 |
| crosswalk | 19,293 | — |
| SAM | 15,386 | -13,429 (trigram cleanup) |
| 990 | 13,488 | -6,727 (trigram cleanup) |
| NLRB | 13,030 | — |
| WHD | 11,403 | -8,059 (trigram cleanup) |
| SEC | 2,924 | -2,415 (trigram cleanup) |
| GLEIF | 1,810 | -30 (duplicate cleanup) |
| mergent | 1,045 | — |
| BMF | 8 | -1 |
| **Total** | **132,187** | |

## Lessons Learned
1. **Never pipe Python through grep on Windows** — no SIGPIPE, Python hangs as zombie
2. **tqdm floods output buffers** — check DB directly for batch results
3. **Max 2 concurrent OSHA batches** — pg_trgm IO contention with 3+ is severe
4. **Verify `&&` chains completed** — Windows background task failures break chains silently
5. **`--rematch-all` vs `--unmatched-only`** — different record sets, different results

## Next Steps
- Phase 2 remaining: Re-run SAM/WHD/990/SEC with RapidFuzz matcher (evaluate quality improvement)
- Phase 2A: NAICS inference, enrichment
- Phase 2B: Master scoring
- Research agent: strategy memory (5.2), employer website scraper
