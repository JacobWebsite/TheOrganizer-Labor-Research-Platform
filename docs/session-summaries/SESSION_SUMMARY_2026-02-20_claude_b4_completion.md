# Session Summary: 2026-02-20 — Claude Code — Phase B COMPLETE + Frontend Fixes

## Overview
**Phase B is fully complete.** Finished all B4 source re-runs (990 5/5, WHD solo, SAM 5/5) in 9h 15m. Rebuilt legacy tables, refreshed all MVs. Fixed 3 frontend bugs, audited dead API endpoints, ran employer/union misclassification audit.

## Frontend Bug Fixes (Committed + Pushed)

### Cross-Navigation Bugs (HIGH)
- **`loadUnionDetail(fNum)`** (`detail.js:636`): Was setting search box to file number and running text search — union search matches on name/local_number, never file number. Fix: call `/api/unions/{fNum}` directly (same pattern as `switchToEmployerAndSelect`).
- **`selectUnionByFnum(fNum)`** (`detail.js:1575`): Was calling `/api/unions/search?f_num=...` but `f_num` is not a search parameter — silently ignored, returning unfiltered results. Fix: call `/api/unions/{fNum}` directly.

### Pagination Math (MEDIUM)
- **`search.js:769`**: `totalPages = Math.ceil(total / 50)` but page size is 15. Users saw ~3.3x too few pages. Fix: extracted `const PAGE_SIZE = 15` used in both limit param and totalPages calculation.

### API Endpoint Audit (LOW)
- Added `DEPRECATED` docstrings to 4 dead employer search endpoints in `employers.py`:
  - `/api/employers/search` (superseded by unified-search)
  - `/api/employers/fuzzy-search` (same)
  - `/api/employers/normalized-search` (same)
  - `/api/employers/unified/search` (legacy, queries old `unified_employers_osha`)
- Annotated unused `has_nlrb` parameter on `/api/employers/search`.

### Tests
- 456/457 pass (1 pre-existing hospital abbreviation failure). No regressions.

## Misclassification Audit (Read-Only)

| Metric | Count |
|--------|-------|
| Employer names matching union keywords | 3,452 |
| Exact name cross-matches (employer = union) | 2,776 |
| Already flagged as `LABOR_ORG_NOT_EMPLOYER` | 3 |
| `unions_master` misclassifications | 0 (clean) |

~2,776 employer records are near-certain labor organizations with only 3 flagged. Remediation deferred — flag system exists but barely used.

## B4 Re-Runs

### 990 — ALL 5 BATCHES COMPLETE
| Batch | Records | Matched | Rate | H+M | Time |
|-------|---------|---------|------|-----|------|
| 1/5 | 117,353 | 21,211 | 18.1% | 4,587 | ~60m |
| 2/5 | 117,353 | 21,148 | 18.0% | 4,345 | 64m |
| 3/5 | 117,353 | 20,899 | 17.8% | 4,385 | 61m |
| 4/5 | 117,353 | 21,136 | 18.0% | 4,510 | 58m |
| 5/5 | 117,355 | 21,205 | 18.1% | 4,529 | 58m |
| **Total** | **586,767** | **105,599** | **18.0%** | **~22,356** | **~5hrs** |

Remarkably consistent across batches. H+M rate ~3.8%.

**990 adapter bug fixed**: `national_990_f7_matches` has two overlapping unique constraints — PK on `(f7_employer_id, ein)` and unique index on `n990_id`. Changed legacy write to `ON CONFLICT DO NOTHING` since `rebuild_legacy_tables.py` produces correct final state from UML.

### WHD — COMPLETE
| Records | Matched | Rate | H+M | Time |
|---------|---------|------|-----|------|
| 363,365 | 87,842 | 24.2% | 19,462 | 2h 8m |

No OOM — ran solo as planned. Splink found 9,309 matches, trigram found 68,889.

### SAM — ALL 5 BATCHES COMPLETE
| Batch | Records | Matched | Rate | H+M | Time |
|-------|---------|---------|------|-----|------|
| 1/5 | 165,208 | ~33K | ~20% | ~5,400 | ~75m |
| 2/5 | 165,209 | ~33K | ~20% | ~5,400 | ~75m |
| 3/5 | 165,209 | ~33K | ~20% | ~5,400 | ~75m |
| 4/5 | 165,208 | ~33K | ~20% | ~5,400 | ~75m |
| 5/5 | 165,208 | ~33K | ~20% | ~5,200 | ~75m |
| **Total** | **826,042** | — | — | **28,816 active** | **~6hrs** |

No OOM — batching to 165K per batch worked perfectly.

## Bug Fixes During Re-Runs
- **990 adapter `ON CONFLICT`**: Changed from targeting `(n990_id)` to `DO NOTHING` to handle dual unique constraints.
- **Runner script**: Fixed batch skip check (`completed_at` instead of `status == 'done'`).
- **Runner script**: Added `rebuild_legacy_tables.py` step before MV refreshes.

## Final UML State
| Source | Active | Rejected | Superseded |
|--------|--------|----------|------------|
| osha | 97,142 | 461,453 | 236,162 |
| sam | 28,816 | 219,175 | 52,358 |
| 990 | 20,215 | 131,294 | 94,531 |
| crosswalk | 19,293 | — | — |
| whd | 19,462 | 106,727 | 71,313 |
| nlrb | 13,031 | 4,485 | — |
| sec | 5,339 | 117,294 | 37,110 |
| gleif | 1,840 | — | — |
| mergent | 1,045 | — | — |
| bmf | 9 | 12 | 9 |
| **Total** | **1,738,115** | | |

## Legacy Match Tables (rebuilt from UML)
| Table | Rows |
|-------|------|
| osha_f7_matches | 97,142 |
| sam_f7_matches | 28,816 |
| national_990_f7_matches | 20,005 |
| whd_f7_matches | 19,462 |
| nlrb_employer_xref | 13,031 |

## Materialized Views (all refreshed)
| MV | Rows |
|----|------|
| mv_organizing_scorecard | 212,441 |
| mv_employer_data_sources | 146,863 |
| mv_unified_scorecard | 146,863 |

## Files Modified
| File | Change |
|------|--------|
| `files/js/detail.js` | Fix `loadUnionDetail()` and `selectUnionByFnum()` cross-nav |
| `files/js/search.js` | Fix pagination PAGE_SIZE constant |
| `api/routers/employers.py` | DEPRECATED comments on 4 dead endpoints |
| `scripts/matching/adapters/n990_adapter.py` | Fix ON CONFLICT for dual unique constraints |
| `run_remaining_reruns.py` | New sequential runner script for B4 completion |

## To Resume
1. **Phase B is DONE.** No more re-runs needed.
2. Run tests to verify: `py -m pytest tests/ -q` (expect 456/457)
3. Next: Phase C (missing unions), Phase D cleanup, or Phase F (deployment).

## Commit
`0390b5a` — "Fix cross-navigation bugs, pagination math, and mark dead API endpoints"
