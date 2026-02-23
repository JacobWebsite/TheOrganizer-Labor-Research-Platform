# PROJECT_STATE.md — Labor Relations Research Platform

> **Document Purpose:** Session handoffs and live status — what just happened, latest numbers, active bugs. For technical details, see `CLAUDE.md`. For the plan, see `MASTER_ROADMAP_2026_02_23.md` (supersedes UNIFIED_ROADMAP_2026_02_19.md). For redesign decisions (scoring, React, UX), see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`. For file locations, see `PROJECT_DIRECTORY.md`.

**Purpose:** Shared context document for all AI tools (Claude Code, Codex, Gemini) and human developers. Read this first before any work session.

**Last manually updated:** 2026-02-23 (Claude Code: Phase 1 Data Trust complete)

---

## Latest Update (2026-02-23 — Phase 1 Data Trust DONE)

**Multi-agent execution:** Claude (scoring fixes), Codex (investigations I1-I5, junk cleanup), Gemini (OSHA cleanup 1.4, data coverage 1.5B, investigations I6-I10).

### Decisions Made (D1-D7)
| Decision | Resolution |
|----------|-----------|
| D1: Name similarity floor | **0.80** (was 0.70). Prioritize quality over quantity. |
| D2: Priority tier meaning | **REJECTED.** Targeting is structural. Recent violations and active contracts are yes/no flags, not scoring requirements. |
| D3: Min factors for Strong | **YES.** Min 3 `factors_available` required for both Priority AND Strong tiers. |
| D4: Stale OSHA handling | **YES.** Bulk-reject OSHA Splink matches with `name_similarity < 0.80`. 46,528 superseded. |
| D5: score_similarity | **Weight 0, keep column.** Pipeline broken (name+state bridge only matches 833/146K, proximity gate kills all). Fix deferred to Phase 2. |
| D7: Empty columns | **Drop 8, keep 6.** Drop DEFERRED due to view/API dependencies (5 of 8 columns used in WHERE/JOIN clauses across 6 API routers). |

### Scoring Fixes (Claude — `build_unified_scorecard.py`)
- **score_financial (NEW):** Real 990 nonprofit financial health (revenue scale 0-6 + asset cushion +0-2 + revenue-per-worker +0-2). Public companies get flat 7. Covers 10,755 employers (7.3%). Was: duplicate of score_industry_growth.
- **score_contracts (FIX):** Federal obligation tiers (1/2/4/6/8/10 based on $100K/$1M/$10M/$100M thresholds). 8,672 employers, 6 distinct values. Was: flat 4.00 for all contractors.
- **score_similarity:** Weight set to 0. Column kept for later pipeline fix.
- **Tier logic:** Min 3 factors for Priority AND Strong. New flag columns: `has_recent_violations` (2yr OSHA/WHD/NLRB, 26,486 employers), `has_active_contracts` (8,672 employers).
- **Post-fix scorecard:** avg=4.16, Priority(2,332/1.6%), Strong(15,350/10.5%), Promising(40,899/27.8%), Moderate(51,460/35.0%), Low(36,822/25.1%).

### OSHA Cleanup (Gemini — `reject_stale_osha.py`)
- 46,528 active OSHA Splink matches with `name_similarity < 0.80` superseded.
- Active OSHA Splink matches: 51,302 -> 4,774. Total active OSHA: 97,142 -> 50,614.
- All remaining active Splink matches have sim >= 0.80.

### Codex Investigations (I1-I5) + Cleanup
- **I1:** No NLRB proximity junk risk (uses canonical groups, not individual matches).
- **I2:** score_similarity pipeline bugs confirmed — name+state bridge ID mismatch + proximity >= 5 gate.
- **I3:** 46,624/46,627 dangling matches already rejected. 1 active dangling row orphaned by `fix_dangling_matches.py`.
- **I4:** 115 junk/placeholder records flagged by `flag_junk_records.py` (includes `*****`, `1`, `3M`, `AD`, etc.).
- **I5:** 0.80 floor confirmed — all current active OSHA matches already >= 0.80.

### Gemini Investigations (I6-I10)
- **I6:** Membership 72M vs 14.5M is hierarchy double-counting (parent unions summing children).
- **I7:** 538K superseded matches in UML — normal from best-match-wins pipeline evolution.
- **I8:** Employer grouping: over-merging on generic names (D. Construction 249 members), under-merging nationals (Healthcare Services Group 7+ fragments).
- **I9:** NAICS inference: ~5,000-6,000 employers can get NAICS from OSHA/WHD matches (25% of 22,183 gap).
- **I10:** 3,000+ association records inflate building trades metrics. Need `is_association` flag.

### Active Match Counts (post-OSHA cleanup)
| Source | Active |
|--------|--------|
| OSHA | 50,614 |
| SAM | 28,815 |
| 990 | 20,215 |
| crosswalk | 19,293 |
| WHD | 19,462 |
| NLRB | 13,030 |
| SEC | 5,339 |
| GLEIF | 1,840 |
| mergent | 1,045 |
| BMF | 9 |

### What's Next: Phase 2 (Matching Quality Overhaul)
- **Track A (Claude):** Splink model retune (2.1), OSHA re-run with new model (2.2), evaluate other sources (2.3), MV rebuild (2.6).
- **Track B (Codex):** Employer grouping fix (2.4, I8 findings), NAICS inference (2A.2, I9 findings), Multi-employer flagging (2A.6, I10 findings).
- **Deferred:** Geocoding (2A.4), NLRB xref rebuild (2A.5), master employer dedup quality.

### Previous: 2026-02-23 (Master Roadmap Created)

- **`MASTER_ROADMAP_2026_02_23.md` created.** Synthesized from 6 source documents (~3,800 lines). 8 phases, 22 decisions, 20 investigations.
- **No code changes.** Planning/documentation only.

### Previous: 2026-02-23 (Codex deep audit execution)

- **Frontend build/test explicitly validated in this environment (outside sandbox restrictions):**
  - `npm.cmd test` -> 21 test files, 134 tests passed
  - `npm.cmd run build` -> success, 1877 modules transformed
- **`frontend/package.json` updated with test script alias:** `"test": "vitest run"`.
- **Backend regression check:** `python -m pytest tests/ -q` -> 492 passed, 1 skipped.
- **Note:** inside sandboxed Node, Vite/esbuild can fail with `spawn EPERM`; use approved `.cmd` commands above.

---

## Previous: 2026-02-22 late night — Spec Gap Closure

- **Spec Gap Closure DONE.** 15 new files + 11 modified. Closes remaining gaps between React frontend and UNIFIED_PLATFORM_REDESIGN_SPEC.
- **Search enhancements:** Employee size filter (min/max workers number inputs), score tier filter (Priority/Strong/Promising/Moderate/Low dropdown), table/card view toggle (persisted to localStorage). SearchResultCard grid for card view. API: 3 new query params on `/api/employers/unified-search` (`min_workers`, `max_workers`, `score_tier`) with SQL filtering on `mv_employer_search` + `mv_unified_scorecard`.
- **Profile cards (7 new CollapsibleCards):** UnionRelationshipsCard (union name, affiliation, unit size), FinancialDataCard (BLS growth, public/nonprofit badges), GovernmentContractsCard (federal obligations, contract count), WhdCard (violations, backwages, cases table), ComparablesCard (top-5 similar employers with similarity %), CorporateHierarchyCard (parent chain, subsidiaries, family stats), ResearchNotesCard (flags list + add form).
- **Profile action buttons:** Flag as Target (opens FlagModal), Export Data (CSV blob download), Something Looks Wrong (FlagModal with DATA_QUALITY preset). FlagModal: 6 flag types, useMutation POST to `/api/employers/flags`.
- **Union explorer enhancements:** ExpansionTargetsSection on union profiles (analyzes employer base, links to Targets page pre-filtered). AffiliationTree on UnionsPage (3-level lazy-loading tree: Affiliation > State > Local with chevron expand/collapse).
- **Union status label on ProfileHeader:** Green "Represented by {union}" badge or gray "No Known Union".
- **6 new API hooks in profile.js:** useEmployerComparables, useEmployerWhd, useEmployerCorporate, useEmployerDataSources, useEmployerFlags, useFlagEmployer. **1 new hook in unions.js:** useNationalUnionDetail.
- **Frontend tests: 134 total (21 files), all passing.** 27 new tests across 3 files (SearchEnhancements, ProfileCards, AffiliationTree).
- **Build clean** (vite build: 1877 modules, 0 errors).
- **Commit:** `a3a9cd5`, pushed to GitHub.

### Previous: 2026-02-22 (late night — Phase 5+6)

- **React Frontend Phase 5 (Union Explorer) DONE.** 16 new files. Union search page with filters (sector, state, affiliation, min members, has employers), debounced search, active filter chips, clickable national union affiliation summary, TanStack Table with pagination (PAGE_SIZE=50). Union profile page with header, 10yr membership CSS horizontal bars, organizing capacity, employer table, NLRB elections, financial trends, sister locals. API hooks: `src/shared/api/unions.js` (8 hooks). URL state sync. PageSkeleton variants added.
- **React Frontend Phase 6 (Admin/Settings) DONE.** 11 new files. Admin dashboard (admin-only access guard) with 7 cards: HealthStatusCard (30s auto-refresh green/red dots), PlatformStatsCard (grid), DataFreshnessCard (table + refresh button), MatchQualityCard (by source/confidence badges), MatchReviewCard (interactive approve/reject per match), UserRegistrationCard (form), RefreshActionsCard (maintenance buttons). API hooks: `src/shared/api/admin.js` (6 queries + 4 mutations). First `useMutation` usage in codebase. Toast notifications via sonner.
- **All frontend phases COMPLETE.** No remaining placeholder components.
- **Frontend tests: 107 total (18 files), all passing.**
- **API response shape fixes applied:** health (db:true not database:'ok'), stats (total_scorecard_rows, match_counts_by_source), freshness (sources array, source_name, stale), match quality (total_match_rows, source_system, confidence_band), match review (evidence.target_name, source_system, confidence_score), union search (display_name, f7_employer_count, f7_total_workers), national unions (national_unions wrapper), employers (employers wrapper), sectors (sector_code), sister locals (union_name + local_number).

### Previous: 2026-02-22 (late evening)

- **NLRB ULP matching DONE.** 234,656 CA charged party records matched to 22,371 distinct F7 employers via `scripts/matching/match_nlrb_ulp.py`. Total NLRB-linked employers: 25,879 (was 5,548, 4.7x increase). Top: USPS (94K), UPS (2K), AT&T (2K), Kaiser (1.6K).
- **ULP integrated into scoring MVs.** `build_employer_data_sources.py` updated: `has_nlrb` 5,547 -> 25,879 (17.6%). `build_unified_scorecard.py` updated: score_nlrb now includes ULP boost (1 charge=2, 2-3=4, 4-9=6, 10+=8 with 7yr decay). New columns: `nlrb_ulp_count`, `nlrb_latest_ulp`.
- **Codex deliverables LIVE.** 8-factor weighted scoring (score_similarity, score_industry_growth, weighted_score, percentile-based tiers: Priority/Strong/Promising/Moderate/Low). Master dedup Phase 1+2+4 done (3,026,290 -> 2,736,890, 289,400 merged). Master API (`api/routers/master.py`) with 4 endpoints verified.
- **All MVs refreshed.** weighted_score avg=4.12. Score tiers: Priority 2.9%, Strong 12.1%, Promising 25.0%, Moderate 35.0%, Low 25.0%.
- **Tests: 492 total, 491 pass, 0 fail, 1 skip.**

### Previous: 2026-02-22 (evening)

- **Misclassification sweep DONE.** 1,843 f7_employers_deduped records flagged `is_labor_org=TRUE` (structural keyword patterns, self-referencing, union name matches, BMF EIN bridge). These are labor orgs that are also legitimate employers -- they remain in search and counts. 194 LOW-confidence (BMF-only) deferred as review. Script: `scripts/analysis/misclass_sweep.py`.
- **master_employers.is_labor_org added and populated.** 6,686 flagged (1,843 from F7, 4,843 from BMF NTEE J40*).
- **Hospital abbreviation test FIXED.** All tests pass (was 478/479 for weeks).

### Previous: 2026-02-22 (earlier)

- **Phase D cleanup batch (D4/D5/D6/D8/D9).**
  - **D6:** Deleted `corpwatch_api_tables_csv/` (8 GB, never imported into DB)
  - **D5:** Archived 35 root-level debug scripts to `archive/old_scripts/root_debug_2026_02_22/`
  - **D4:** Updated PIPELINE_MANIFEST.md with current script counts (134 total, 80 pipeline) and 15 missing scripts from Phase E/G
  - **D8/D9:** Refreshed PROJECT_STATE.md with live DB metrics, Phase G status, problem updates
  - **D9:** Created `scripts/maintenance/generate_project_metrics.py` -- auto-generates `docs/PROJECT_METRICS.md` from live DB
  - Project size: 30 GB -> 22 GB (corpwatch deletion)
  - DB size: 9.5 GB (down from 20 GB after D2 GLEIF archive)
- **Phase G seeding:** master_employers seeded (3,026,290 rows: BMF 2,027,342, SAM 797,226, F7 146,863, Mergent 54,859). master_employer_source_ids: 3,080,492.

### Previous: 2026-02-20c

- **NY employer CSV export v2 (`export_ny_deduped.py` rewrite).**
  - Collapsed canonical groups: 3,642 employers -> 1,641 rows (SUM workers, dedup union names, collect locations)
  - Flagged 78 multi-employer agreements (SAG-AFTRA, Joint Policy, RAB, etc.) via regex pattern detection
  - Public sector (20 entries: NYSUT 467K, CSEA 250K, DC37 150K) placed at top of CSV
  - Fuzzy dedup for 10K+ ungrouped employers (no additional collapses found)
  - Total rows: 18,482 -> 15,509 (16% reduction)
  - New columns: `employer_type`, `union_names`, `union_count`, `location_count`, `locations`
  - Methodology document: `docs/NY_EXPORT_METHODOLOGY.md`

### Previous: 2026-02-20b

- **PHASE B COMPLETE. All B4 source re-runs done (9h 15m total).**
  - OSHA 4/4: 1,007,217 records, 97,142 active (9.6%)
  - SEC 5/5: 517,403 records, 5,339 active (1.0%)
  - 990 5/5: 586,767 records, 20,215 active (3.4%)
  - WHD: 363,365 records, 19,462 active (5.4%)
  - SAM 5/5: 826,042 records, 28,816 active (3.5%)
  - BMF: 2,043,779 loaded (full IRS BMF), 9 matched to F7
- **Legacy match tables rebuilt from UML:** osha(97,142), sam(28,816), 990(20,005), whd(19,462), nlrb_xref(13,031)
- **All 3 MVs refreshed:**
  - `mv_organizing_scorecard`: 212,441 rows
  - `mv_employer_data_sources`: 146,863 rows
  - `mv_unified_scorecard`: 146,863 rows (avg=3.28, WHD coverage 8.2%, score_whd avg=1.18)
- **Fixed 3 frontend bugs:** cross-nav (`loadUnionDetail`, `selectUnionByFnum`), pagination (PAGE_SIZE=15 not 50).
- **Marked 4 dead API endpoints as DEPRECATED** in `employers.py`.
- ~~**Misclassification audit:** 2,776 employer records are likely labor orgs. Only 3 flagged.~~ **DONE (2026-02-22).** 1,843 flagged `is_labor_org=TRUE`. These remain as valid employers (labor orgs employ staff). 194 LOW-confidence deferred.
- **990 adapter bug fixed:** dual unique constraints, changed to `ON CONFLICT DO NOTHING`.
- **Tests:** 456 pass / 1 fail (pre-existing hospital abbreviation only).
- **UML:** 1,738,115 rows.

### Previous: 2026-02-19g

- Fixed `test_union_detail` 503 failure introduced by Codex 2026-02-19f session.
  - Root cause: `ns.naics_sector_name` used in SQL queries but actual column is `ns.sector_name`.
  - Fixed in `api/routers/unions.py` and `api/routers/profile.py`.

### Previous: 2026-02-19f

- Added canonical profile endpoints (`/api/profile/employers/{employer_id}`, `/api/profile/unions/{f_num}`).
- Frontend scorecard UX unified-only. Deep-dive routing collapsed into unified Search detail flow.
- `GET /api/employers/unified-search` now handles `sector`, `naics`, `aff_abbr` filters; rejects unsupported `metro` with 422.

---

## Section 1: Quick Start

### Database Connection
- **Engine:** PostgreSQL 17
- **Database:** `olms_multiyear`
- **Host:** localhost:5432
- **User:** `postgres`
- **Credentials:** Stored in `.env` at project root (never commit this file)
- **Shared module:** `from db_config import get_connection` — used by all scripts and the API

### Start the API Server
```bash
py -m uvicorn api.main:app --reload --port 8001
```
Or use `start-claude.bat` which runs the same command.

The API serves at `http://localhost:8001`. API docs at `http://localhost:8001/docs`.

### Run Tests
```bash
py -m pytest tests/ -q
```
492 backend tests. 491 pass, 1 skip. 134 frontend tests (21 files), all pass.

### Run Frontend Tests
```bash
cd frontend
npm.cmd test
```
Expected current result: 21 files, 134 tests passed.

### Run Frontend Production Build
```bash
cd frontend
npm.cmd run build
```
Expected current result: build success, ~1877 modules transformed.

### Key Files
| File | Purpose |
|------|---------|
| `db_config.py` | Shared database connection — imported by 500+ files |
| `.env` | Database credentials and JWT secret |
| `api/main.py` | FastAPI application entry point |
| `CLAUDE.md` | Detailed project instructions for AI tools |
| `MASTER_ROADMAP_2026_02_23.md` | **Current roadmap** — Phases 0-8, 22 decisions, supersedes UNIFIED_ROADMAP_2026_02_19.md |
| `UNIFIED_PLATFORM_REDESIGN_SPEC.md` | Platform redesign spec — 8-factor weighted scoring, React frontend, UX, page designs |
| `FOUR_AUDIT_SYNTHESIS_v3.md` | Synthesis of 4 independent AI audits — data quality issues, investigation questions |
| `PIPELINE_MANIFEST.md` | Every active script — what it does, when to run it |

---

## Section 2: Database Inventory

*Auto-generated by `scripts/maintenance/generate_project_metrics.py` on 2026-02-22. For full detail see `docs/PROJECT_METRICS.md`.*

| Metric | Value |
|--------|-------|
| Database size | 9.5 GB |
| Tables | 178 |
| Views | 123 |
| Materialized views | 6 |
| Indexes | 270 (total size: 2,865 MB) |

**Materialized Views:**

| View | Rows |
|------|------|
| `mv_whd_employer_agg` | 330,419 |
| `mv_organizing_scorecard` | 212,441 |
| `mv_employer_data_sources` | 146,863 |
| `mv_unified_scorecard` | 146,863 |
| `mv_employer_search` | 107,025 |
| `mv_employer_features` | 54,968 |

**Top 30 Tables by Row Count:**

| Table | Rows |
|-------|------|
| `master_employer_source_ids` | 3,080,492 |
| `master_employers` | 2,736,890 |
| `ar_disbursements_emp_off` | 2,813,076 |
| `osha_violations_detail` | 2,245,012 |
| `nlrb_docket` | 2,046,151 |
| `irs_bmf` | 2,043,779 |
| `qcew_annual` | 1,943,426 |
| `nlrb_participants` | 1,905,912 |
| `unified_match_log` | 1,738,115 |
| `epi_union_membership` | 1,420,064 |
| `employers_990_deduped` | 1,046,167 |
| `osha_establishments` | 1,007,275 |
| `osha_violation_summary` | 872,163 |
| `sam_entities` | 826,042 |
| `nlrb_allegations` | 715,805 |
| `national_990_filers` | 586,767 |
| `sec_companies` | 517,403 |
| `gleif_ownership_links` | 498,963 |
| `nlrb_filings` | 498,749 |
| `nlrb_cases` | 477,688 |
| `gleif_us_entities` | 379,192 |
| `whd_cases` | 362,634 |
| `lm_data` | 331,238 |
| `mv_whd_employer_agg` | 330,419 |
| `ar_assets_investments` | 304,816 |
| `employer_comparables` | 269,785 |
| `ar_membership` | 216,508 |
| `ar_disbursements_total` | 216,372 |
| `mv_organizing_scorecard` | 212,441 |
| `union_names_crosswalk` | 171,481 |

*178 tables total.*

---

## Section 3: Active Pipeline

See **`PIPELINE_MANIFEST.md`** for the complete script inventory.

**Summary:** 80 active pipeline scripts across 5 stages (134 including analysis):
- **Stage 1 -- ETL:** 28 scripts loading data from OSHA, WHD, SAM, SEC, NLRB, BLS, GLEIF, IRS BMF, O*NET, and more
- **Stage 2 -- Matching:** 19 + 7 adapters + 5 matchers = 31 scripts linking records across databases
- **Stage 3 -- Scoring:** 11 scripts (7 scoring + 4 ML) computing scorecards, search MV, and propensity model
- **Stage 4 -- Maintenance:** 7 scripts for periodic refresh, legacy table rebuilds, union resolution, cleanup
- **Stage 5 -- Web Scraping:** 8 scripts for union website data extraction and SEC subsidiary extraction

**Typical full pipeline run order:**
```
1.  ETL: Load/refresh source data
2.  Matching: py scripts/matching/run_deterministic.py all
3.  Matching: py scripts/matching/splink_pipeline.py (optional fuzzy)
4.  Matching: py scripts/matching/build_employer_groups.py
4.5 Scoring: py scripts/scoring/build_employer_data_sources.py --refresh
4.6 Scoring: py scripts/scoring/build_unified_scorecard.py --refresh
5.  Scoring: py scripts/scoring/compute_nlrb_patterns.py
6.  Scoring: py scripts/scoring/create_scorecard_mv.py --refresh
7.  Scoring: py scripts/scoring/compute_gower_similarity.py --refresh-view
8.  ML: py scripts/ml/train_propensity_model.py --score-only
9.  Maintenance: py scripts/maintenance/create_data_freshness.py --refresh
```

---

## Section 4: Current Status and Known Issues

### CRITICAL (fix before anything else)

1. ~~**Scorecard uses 10-year-old OSHA data.**~~ **FIXED (Phase A2).** Root cause: OSHA changed `union_status` codes from N/Y to A/B after 2015. View filter changed from `= 'N'` to `!= 'Y'`. MV expanded from 22,389 to 212,441 rows (after Phase A2 + B4 re-runs).

2. ~~**Security is turned off by default.**~~ **HARDENED (Phase D1).** Auth is now enforced by default -- API refuses to start without `LABOR_JWT_SECRET` unless `DISABLE_AUTH=true` is explicitly set. Admin endpoints require admin role. Write endpoints require authentication. Local dev still uses `DISABLE_AUTH=true` in `.env`.

3. ~~**Half of union-employer relationships are invisible.**~~ **FIXED.** Zero orphaned employer relationships (confirmed 2026-02-19 by all three independent audits). Fix applied during deduplication: 3,531 records repointed, 52,760 historical employers added.

### HIGH (fix before letting others use it)

4. ~~**Scorecard coverage improved but still OSHA-centric.**~~ **FIXED (Phase E3).** Unified scorecard (`mv_unified_scorecard`) scores ALL 146,863 F7 employers using signal-strength approach: 7 factors (each 0-10), missing factors excluded, score = average of available factors. Coverage percentage shows data completeness.

5. ~~**Two separate scorecards with different logic.**~~ **FIXED (Phase E3).** One unified scorecard pipeline replaces both OSHA-based and Mergent-based scoring. Old scorecard (`mv_organizing_scorecard`) kept for backward compatibility.

6. ~~**Matching pipeline has two bugs.**~~ **FIXED (Phase B1-B2).** Tier ordering corrected (strict-to-broad: EIN > name+city+state > name+state > aggressive > Splink fuzzy > trigram). First-hit-wins replaced with best-match-wins (keeps highest-tier match per source record). Splink re-integrated as tier 5a with name similarity floor (token_sort_ratio >= 0.70, raised from 0.65 on 2026-02-19) after discovering Splink model overweights geography.

7. ~~**Missing unions.**~~ **RESOLVED (2026-02-21).** Was 195/92,627 -> 166/61,743 (crosswalk) -> 165/23,551 (CWA) -> 138/19,155 (manual adds). All 27 active (post-2021) orphans identified as locals of known national affiliates and added to `unions_master`. 138 remaining are HISTORICAL (pre-2021 defunct). 0 active orphans. See `docs/MISSING_UNIONS_ANALYSIS.md`.

8. ~~**Corporate hierarchy endpoints are broken.**~~ **FIXED (Phase A3).** 7 RealDictCursor indexing bugs fixed, route shadowing resolved (search before parameterized).

9. **Platform only runs on one laptop.** No Docker, no CI/CD, no automated maintenance.

### MEDIUM

10. ~~Match quality dashboard inflates numbers (counts rows, not distinct employers).~~ **FIXED (Phase A4).** API and report now show both `total_match_rows` and `unique_employers_matched`.
11. ~~NLRB time-decay is a dead switch (always 1.0).~~ **FIXED (2026-02-22 MV refresh).** NLRB 7yr half-life decay now active in `mv_unified_scorecard`. score_nlrb covers 25,879 employers (17.6%) with elections + ULP charges. avg=3.59.
12. Model B propensity score is basically random (AUC 0.53).
13. ~~Documentation keeps falling behind (19 known inaccuracies in CLAUDE.md).~~ **IMPROVED (Phase D8/D9).** PROJECT_STATE.md and PIPELINE_MANIFEST.md refreshed 2026-02-22. Auto-metrics script created for future refreshes.
14. ~~778 Python files with no manifest.~~ **FIXED** -- Pipeline manifest created and updated (134 active scripts, 80 pipeline). 35 root debug scripts archived (2026-02-22). Manifest auto-refreshable via `generate_project_metrics.py`.
15. ~~Database is twice as big as needed (~12 GB raw GLEIF).~~ **FIXED (Phase D2+D3).** GLEIF raw schema dropped (12 GB -> backup dump). 336 unused indexes dropped (3.0 GB). DB now 9.5 GB.

---

## Section 5: Recent Decisions

**New decision register (22 decisions, D1-D22):** See `MASTER_ROADMAP_2026_02_23.md` Decision Register section. **D1-D7 RESOLVED (2026-02-23):** D1=0.80 sim floor, D2=REJECTED (structural targeting), D3=YES (min 3 for Strong), D4=YES (bulk-reject stale OSHA), D5=weight 0 keep column, D6=accept Codex changes, D7=drop 8 DEFERRED. Key remaining: D8-D22 (deferred to later phases), D15 (CBA OCR approach).

From the Feb 16-17, 2026 planning session (full list in `UNIFIED_ROADMAP_2026_02_19.md` Appendix B). For redesign-era decisions (scoring weights, React migration, UX, page designs), see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.

| # | Topic | Decision |
|---|-------|----------|
| 1 | Stale materialized views | Fine for now, proof of concept first |
| 2 | F-7 orphan problem | Fix first (highest priority), detailed checkpoint procedure defined |
| 3 | OLMS unused data | Tier 1: organizing spend + membership trends. Tier 2: financial health. Future: officer/leadership |
| 4 | Matching bugs | Reorder strict-to-broad, fix first-hit-wins, bring Splink back, re-run, add confidence flags |
| 5 | Scorecard design | Unified pipeline, signal-strength scoring (missing=excluded not zero), all employers covered |
| 6 | Gower distance | Comparables display only, separate from score |
| 7 | Industry density | Drop as standalone score factor (not actionable), keep as informational display |
| 8 | Geographic favorability | Drop as standalone score factor (too broad), keep as informational display |
| 9 | Government contracts | Combine federal + state + municipal into one factor |
| 10 | Union proximity | Merge sibling unions + corporate hierarchy into one factor, weight siblings more heavily |
| 11 | BLS projections | Add industry growth/decline as component of financial indicators factor |
| 12 | Propensity model | Needs more non-union training data before improvement |
| 13 | Membership display | Distinguish "covered workers" vs "dues-paying members" in UI |
| 14 | 195 missing unions | Check crosswalk first, manual lookup top 20, categorize, remap |
| 15 | Corporate hierarchy | Fix broken API, improve crosswalk coverage. Master key deferred to long-term |
| 16 | FMCS data | Removed from roadmap |
| 17 | Web scraper | On-demand deep-dive tool, not always-running crawler |
| 18 | Workforce demographics | Phase 1: expose BLS matrix. Phase 2: ACS PUMS. Phase 3: revenue-to-headcount. Phase 4: O*NET |
| 19 | F-7 time boundaries | Investigate after orphan fix |
| 20 | Frontend redesign | Major redesign after data foundation is solid |
| 21 | Checkpoints | Built into every work session |
| 22 | Contract database | Lower priority, Wave 3 |
| 23 | Project organization | Script manifest, archive dead files, PROJECT_STATE.md for multi-AI workflow |
| 24 | Multi-AI context | Shared PROJECT_STATE.md with auto-generated sections, session handoff notes |
| 25 | Simpler communication | Explain all technical concepts in plain language |

---

## Section 6: Key Design Rationale

### Phase B Progress (2026-02-17) — Matching Pipeline Fixes

**Status:** B1-B3 complete, B4 partially complete (OSHA re-run reverted), B5 complete.

| Task | Status | Description |
|------|--------|-------------|
| B1 | DONE | Tier reordering: strict-to-broad cascade (EIN 100 > name+city+state 90 > name+state 80 > aggressive 60 > Splink 45 > trigram 40) |
| B2 | DONE | Name collision fix: best-match-wins replaces first-hit-wins |
| B3 | DONE | Splink re-integrated as tier 5a with name similarity floor. Trigram fallback as tier 5b |
| B4 | DONE | All source re-runs complete. OSHA(97,142), SEC(5,339), 990(20,215), WHD(19,462), SAM(28,816), BMF(9 of 2M+ loaded). Legacy tables rebuilt. All MVs refreshed. 9h15m total. |
| B5 | DONE | Added confidence flags to UI (HIGH hidden, MEDIUM=Probable match, LOW=Verify match) |

**Critical Finding — Splink Model Calibration:**
The pre-trained Splink model (`adaptive_fuzzy_model.json`) overweights geographic features. State (BF~25), city (BF~400), and zip (BF~840) Bayes factors multiply to ~8.5M, overwhelming the 0.0001 prior to give 0.99+ match probability regardless of name similarity. First OSHA re-run produced 835K active matches (81% match rate vs expected ~4%) before being killed and reverted. Fix: added `rapidfuzz.fuzz.token_sort_ratio >= 0.65` post-filter. Dry-run on 5K records showed 3.8% active rate (matches old 4.2% baseline). The model works for disambiguation (2-10 candidates with similar names) but NOT for open-ended batch matching without a name floor.

**Data State After Revert:**
- unified_match_log: 119,747 active + 119,451 rejected (verified matches pre-run state)
- osha_f7_matches: 147,271 (unchanged)
- Bad run entries (860K) deleted, 119,747 superseded entries restored to active

### B4 Batched Re-run (2026-02-18) — OSHA

**Approach:** Added `--batch N/M` flag to `run_deterministic.py`. Processes records in 25% slices with per-batch supersede (only touches current batch's old matches). Checkpoint file at `checkpoints/osha_rerun.json` tracks progress and per-batch stats.

**Command:** `py scripts/matching/run_deterministic.py osha --rematch-all --batch 1/4`

**OSHA Batch 1/4 Interim Quality Check (~252K records, still running):**

| Category | Count | Notes |
|----------|-------|-------|
| Exact tiers 1-4 (HIGH/MED) | ~11,900 | Solid: name+city+state, name+state, aggressive |
| Splink HIGH | ~12,270 | 94% scored 0.95+. Name floor 0.65 working. |
| Splink MEDIUM | ~612 | OK |
| Trigram HIGH+MED | ~1,058 | Marginal |
| Trigram LOW (rejected) | ~29,486 | Garbage -- correctly rejected, not in legacy |
| Ambiguous (rejected) | ~2,459 | Correctly flagged |
| **Active match rate** | **~9%** | Higher than old 4.2% baseline but not the 81% disaster |

**Verdict:** Name similarity floor (token_sort_ratio >= 0.65) is working. The 81% overmatching catastrophe from the first attempt is gone. Active rate of ~9% is higher than old baseline (~4%) mainly from Splink finding ~12K legitimate new matches (Supreme Steel, Teva Pharmaceuticals, etc.).

**Known concern:** A few Splink false positives at the 0.65 name floor -- e.g., "nex transport" matched to "cassens transport" (0.733 name sim but different companies). Splink probability is 1.0 because geography overweights. Could tighten floor to 0.70 for stricter matching, but would lose some good matches.

**To resume:** Run batches 2-4:
```
py scripts/matching/run_deterministic.py osha --rematch-all --batch 2/4
py scripts/matching/run_deterministic.py osha --rematch-all --batch 3/4
py scripts/matching/run_deterministic.py osha --rematch-all --batch 4/4
```
Check progress: `py scripts/matching/run_deterministic.py osha --batch-status`

**Pre-run DB state (for rollback reference):**
- UML osha active: 62,903
- UML osha rejected: 132,430
- UML osha superseded: 147,865
- osha_f7_matches: 147,271

---

## Section 7: Recent Phase A Fixes (2026-02-16)

*Moved from Section 4 inline notes — see Section 4 for current status of each issue.*

---

### Why signal-strength scoring instead of penalizing missing data
Most employers are only matched to 2-3 of the 8+ data sources. If missing data counted as zero, 85% of employers would get artificially low scores. Signal-strength scoring only evaluates factors where data exists, paired with a coverage percentage ("scored on 3 of 8 factors") so users know how much information is behind the number.

### Why Splink over trigram for fuzzy matching
Trigram matching (pg_trgm) only measures string similarity between names. Splink weighs multiple evidence fields (name, state, city, ZIP, industry, address) and calculates a probability that two records are the same entity. "Springfield Hospital" and "Springfield Health Center" score ~0.6 on trigram but ~0.94 on Splink when they share city, state, and industry. Splink is already installed and was used for earlier deduplication work.

### Why F-7 is the foundation (not OSHA or NLRB)
The DOL F-7 filing is the only comprehensive registry of union-employer bargaining relationships. OSHA covers workplaces (not employers), NLRB covers elections (not ongoing relationships), and SEC/990/SAM each cover narrow slices. F-7 provides the most complete list of employers with active union contracts — 146,863 records. Everything else matches against F-7.

### Why the master employer key is deferred
A master employer key (one platform ID per real-world employer, mapped to all source IDs) is the ideal architecture. But building it too early bakes in matching errors that are hard to undo. The current approach uses `f7_employer_id` as the de facto key with match tables linking other sources. The master key will be built during Phase E (scorecard rebuild) when matching quality is higher and confidence thresholds are established.

## Section 8: Session Handoff Notes (2026-02-22 late night, Claude Code — Spec Gap Closure)

### Completed in this session
- **Spec Gap Closure — Search Enhancements, Profile Cards, Affiliation Tree:** 15 new files + 11 modified. Implemented via 5 parallel agents (search, profile header, profile cards, union explorer, tests).
  - **Search:** Employee size filter (min/max workers), score tier filter (5-tier dropdown), table/card view toggle (SearchResultCard grid, localStorage-persisted). API: `min_workers`, `max_workers`, `score_tier` params on `unified-search`.
  - **Profile header:** Union status label (green "Represented by" / gray "No Known Union"), ProfileActionButtons (Flag/Export CSV/Report), FlagModal (6 flag types, POST mutation).
  - **Profile cards (7):** UnionRelationshipsCard, FinancialDataCard, GovernmentContractsCard, WhdCard (self-fetching), ComparablesCard (self-fetching), CorporateHierarchyCard (self-fetching), ResearchNotesCard (self-fetching + add form).
  - **Union explorer:** ExpansionTargetsSection (on union profiles), AffiliationTree (3-level lazy tree on UnionsPage: Affiliation > State > Local).
  - **API hooks:** 6 new in profile.js (useEmployerComparables, useEmployerWhd, useEmployerCorporate, useEmployerDataSources, useEmployerFlags, useFlagEmployer), 1 new in unions.js (useNationalUnionDetail).
  - **Tests:** 27 new (SearchEnhancements 8, ProfileCards 14, AffiliationTree 5). Total: 134 tests, 21 files, all passing.
- **Commit:** `a3a9cd5`, pushed to GitHub.

### What's next (per MASTER_ROADMAP_2026_02_23.md)
- **Phase 0 (Quick Wins):** Backups, indexes, MV fix, search fix, freshness table, ANALYZE, slow endpoints, API key rotation. ~1.5 days.
- **Decisions D1-D7** needed before Phase 1 (name similarity floor, Priority tier meaning, minimum factors, stale OSHA handling, score_similarity, Codex changes, empty columns).
- **Phase 1 (Data Trust):** Fix 3-4 broken scoring factors, clean junk records, tier logic. ~3-4 weeks.
- **Phase 1B (Investigations):** 20 questions from audit synthesis, 5 critical (block later phases). ~35-50 hours.
- **194 LOW-confidence misclassification records:** BMF-only signals, needs manual review.
- **Remaining uncommitted changes:** Codex deliverables (scorecard.py, build_unified_scorecard.py, master.py, CBA extraction) not yet committed.

### File references
- New: 9 profile cards/actions (`frontend/src/features/employer-profile/`), SearchResultCard, AffiliationTree, ExpansionTargetsSection, 3 test files
- Modified: `api/routers/employers.py`, `useSearchState.js`, `employers.js`, `SearchFilters.jsx`, `SearchPage.jsx`, `ProfileHeader.jsx`, `EmployerProfilePage.jsx`, `profile.js`, `unions.js`, `UnionProfilePage.jsx`, `UnionsPage.jsx`
- Commit: `a3a9cd5`

---

## Previous: Session Handoff Notes (2026-02-22 late night, Claude Code — React Frontend Phase 5+6)

### Completed in that session
- **React Frontend Phase 5 (Union Explorer):** 27 new files + 1 modified across both phases.
  - API hooks: `src/shared/api/unions.js` (useUnionSearch, useNationalUnions, useUnionDetail, useUnionEmployers, useUnionOrganizingCapacity, useUnionMembershipHistory, useUnionSectors, useUnionAffiliations)
  - URL state: `useUnionsState.js` (q, aff_abbr, sector, state, min_members, has_employers, page)
  - List page: UnionsPage, UnionFilters, NationalUnionsSummary (clickable affiliation chips), UnionResultsTable (TanStack Table, 6 cols)
  - Profile page: UnionProfilePage, UnionProfileHeader, MembershipSection (CSS bars), OrganizingCapacitySection, UnionEmployersTable, UnionElectionsSection, UnionFinancialsSection, SisterLocalsSection
  - PageSkeleton: added `unions` and `union-profile` variants
- **React Frontend Phase 6 (Admin/Settings):**
  - API hooks: `src/shared/api/admin.js` (6 queries + 4 mutations — first `useMutation` in codebase)
  - Cards: HealthStatusCard (30s auto-refresh), PlatformStatsCard, DataFreshnessCard (refresh button), MatchQualityCard, MatchReviewCard (approve/reject), UserRegistrationCard, RefreshActionsCard
  - SettingsPage: admin guard + dashboard layout with all 7 cards
- **API response shape fixes:** 10 components fixed to match actual API responses (field names, wrapper objects, boolean formats)
- **All frontend phases COMPLETE.** No remaining placeholders. 107 tests, 18 files, all pass.

### What's next
- **Phase F:** Docker, CI/CD, hosting.
- **Master dedup Phase 3 (fuzzy):** Codex rollout plan in `docs/session-summaries/SESSION_SUMMARY_2026-02-22_codex_master_dedup_phase3_plan.md`. Start: `--dry-run --limit 200 --min-name-sim 0.88`.
- **194 LOW-confidence misclassification records:** BMF-only signals, needs manual review.

### File references
- New: `frontend/src/shared/api/unions.js`, `frontend/src/shared/api/admin.js`, 13 union-explorer components, 8 admin components, 4 test files
- Modified: `frontend/src/shared/components/PageSkeleton.jsx` (new variants), `frontend/src/features/union-explorer/UnionsPage.jsx` (replaced placeholder), `frontend/src/features/union-explorer/UnionProfilePage.jsx` (replaced placeholder), `frontend/src/features/admin/SettingsPage.jsx` (replaced placeholder)
- Commits: `b03628c` (Phase 5+6 initial), `bb53e14` (API response shape fixes)

---

## Previous: Session Handoff Notes (2026-02-22 late evening, Claude Code — ULP Scoring + Codex Merge)

### Completed in that session
- **NLRB ULP matching:** 234,656 CA charged party records matched to 22,371 distinct F7 employers. Total NLRB-linked: 25,879 (was 5,548). Script: `scripts/matching/match_nlrb_ulp.py`.
- **ULP integrated into scoring:** `build_employer_data_sources.py` updated (has_nlrb 5,547->25,879). `build_unified_scorecard.py` updated (ULP boost, new columns nlrb_ulp_count/nlrb_latest_ulp).
- **Codex deliverables verified:** 8-factor weighted scoring, master dedup Phase 1+2+4 (3M->2.7M), master API (4 endpoints).
- **Misclassification sweep:** 1,843 flagged `is_labor_org=TRUE` on F7, 6,686 on master_employers.
- **Tests:** 492 total, 491 pass, 0 fail, 1 skip. All 4 MVs refreshed.

---

## Previous: Session Handoff Notes (2026-02-20c, Claude Code — NY Export v2)

### Completed in this session
- **Rewrote `export_ny_deduped.py`** — collapsed, one-row-per-real-employer CSV for NY.
  - 5-step pipeline: canonical group collapse -> multi-employer detection -> fuzzy dedup -> public sector at top -> NLRB append
  - Rows: 18,482 -> 15,509 (16% reduction)
  - Starbucks: 20+ rows -> 3 (1 canonical group, 513 workers, 19 locations)
  - SAG-AFTRA: 6+ rows -> 2 (1 office + 1 flagged multi-employer agreement)
  - 78 multi-employer agreements detected and flagged
  - 20 public-sector entries at top of CSV
- **Created methodology document:** `docs/NY_EXPORT_METHODOLOGY.md` (detailed methodology, problems, alternatives)

### Output file
- `ny_employers_deduped.csv` — 15,509 rows, 23 columns

### What's next
- Consider expanding canonical grouping to catch more duplicates upstream
- Consider address-based or EIN-based dedup as supplementary signals
- Multi-employer agreement member enumeration (list individual employers under each agreement)
- Corporate hierarchy collapsing (SEC/GLEIF parent-subsidiary data)

### File references
- Modified: `export_ny_deduped.py`
- New: `docs/NY_EXPORT_METHODOLOGY.md`, `docs/session-summaries/SESSION_SUMMARY_2026-02-20c_claude_ny_export_v2.md`

---

## Previous: Session Handoff Notes (2026-02-20, Claude Code — Phase B COMPLETE + Frontend Fixes)

### Completed in this session
- **PHASE B COMPLETE.** All B4 source re-runs finished (9h 15m via `run_remaining_reruns.py`):
  - 990 5/5: 586,767 records, 20,215 active (3.4%)
  - WHD: 363,365 records, 19,462 active (5.4%). No OOM (ran solo).
  - SAM 5/5: 826,042 records, 28,816 active (3.5%). No OOM (batched to 165K each).
- **Legacy match tables rebuilt** from UML: osha(97,142), sam(28,816), 990(20,005), whd(19,462), nlrb_xref(13,031).
- **All 3 MVs refreshed:** scorecard(212,441), data_sources(146,863), unified(146,863).
- **Frontend cross-nav bugs fixed.** `loadUnionDetail()` and `selectUnionByFnum()` now call `/api/unions/{fNum}` directly.
- **Pagination fix.** `totalPages` divided by 50 not 15. Extracted `PAGE_SIZE` constant.
- **4 dead API endpoints marked DEPRECATED** in `employers.py`.
- **Misclassification audit.** 2,776 employer records = labor orgs (only 3 flagged). Remediation deferred.
- **990 adapter bug fixed.** Dual unique constraints on legacy table. Changed to `ON CONFLICT DO NOTHING`.
- **UML:** 1,738,115 rows. Tests: 456/457.

### Active match counts (post-B4)
| Source | Active | Rate |
|--------|--------|------|
| OSHA | 97,142 | 9.6% |
| SAM | 28,816 | 3.5% |
| 990 | 20,215 | 3.4% |
| crosswalk | 19,293 | — |
| WHD | 19,462 | 5.4% |
| NLRB | 13,031 | — |
| SEC | 5,339 | 1.0% |
| GLEIF | 1,840 | — |
| mergent | 1,045 | — |
| BMF | 9 | — |

### What's next (per roadmap)
- **Phase C:** 166 missing unions (61,743 workers). CWA District 7 geographic devolution.
- **Phase D remaining:** D2 (GLEIF archive, ~12GB), D6 (redundant files, ~9.3GB), D7 (credential fixes), D9 (docs refresh).
- **Phase F:** Docker, CI/CD, hosting, beta testers. Critical path: A -> B -> E -> **F** (we're here).
- **Misclassification:** 2,776 labor orgs in employer table need bulk flagging.

### File references
- Committed + pushed: `files/js/detail.js`, `files/js/search.js`, `api/routers/employers.py`
- Modified (not committed): `scripts/matching/adapters/n990_adapter.py`, `run_remaining_reruns.py`
- New: `docs/session-summaries/SESSION_SUMMARY_2026-02-20_claude_b4_completion.md`

---

## Previous: Session Handoff Notes (2026-02-18c, Claude Code — Frontend Unified Scorecard + B4 Completion + Source Re-runs)

### Completed in this session
- **B4 OSHA All 4 Batches COMPLETE.** Remarkably consistent results:
  - Batch 1: 251,804 records, 40.3%, 24,349 H+M
  - Batch 2: 251,804 records, 40.4%, 24,178 H+M
  - Batch 3: 251,804 records, 40.4%, 24,252 H+M
  - Batch 4: 251,805 records, 40.3%, 24,363 H+M
  - **Total: 1,007,217 records, 97,142 HIGH+MEDIUM active matches (9.6%)**
- **BMF re-run COMPLETE.** 15/25 matched (60%), 9 H+M. Fixed `bmf_adapter_module.py` ON CONFLICT bug (corporate_identifier_crosswalk has no unique constraint on f7_employer_id due to 2,306 duplicates — switched to UPDATE-then-INSERT pattern).
- **SEC re-run PARTIAL.** Was in final trigram tail when stopped. Active: 6,750, rejected: ~25K. Needs re-run.
- **990 re-run PARTIAL.** Was writing legacy tables when stopped. Active: 34,000, rejected: ~14K. Needs re-run.
- **WHD re-run FAILED (OOM).** PostgreSQL ran out of memory during trigram batch write when running 4 sources in parallel. Needs re-run solo.
- **SAM re-run FAILED (OOM).** numpy OOM on Splink pass — 826K records is too large for parallel. Needs batched re-run (`--batch` flag) or solo run.
- **Frontend unified scorecard DONE.** Wired up `scorecard.js` to use `/api/scorecard/unified` endpoints:
  - `loadUnifiedResults()` — calls unified API, maps data, supports pagination
  - `renderUnifiedDetail()` — 7 factors (0-10) with color bars, explanations, OSHA/NLRB/WHD/contracts context
  - `loadUnifiedStates()` — state filter from unified endpoint with avg scores
  - Dynamic tier labels (TOP 7+, HIGH 5+, MEDIUM 3.5+, LOW <3.5)
  - Dynamic legend using UNIFIED_SCORE_FACTORS
  - Unified-specific badges (OSHA/NLRB/WHD/Fed Contractor), coverage stats
  - 439/441 tests pass (same 2 pre-existing failures)

### To resume
1. **Re-run SEC:** `py scripts/matching/run_deterministic.py sec --rematch-all`
2. **Re-run 990:** `py scripts/matching/run_deterministic.py 990 --rematch-all`
3. **Re-run WHD:** `py scripts/matching/run_deterministic.py whd --rematch-all` (run SOLO, not in parallel — OOM risk)
4. **Re-run SAM:** `py scripts/matching/run_deterministic.py sam --rematch-all` (run SOLO — 826K records, OOM risk. Consider `--batch 1/2` and `--batch 2/2` if still OOM)
5. **After all sources complete:** Refresh MVs:
   ```
   py scripts/scoring/create_scorecard_mv.py --refresh
   py scripts/scoring/build_employer_data_sources.py --refresh
   py scripts/scoring/build_unified_scorecard.py --refresh
   ```
6. **Important:** Run sources ONE AT A TIME to avoid OOM. Do NOT run WHD or SAM in parallel with anything.

---

## Older Sessions (2026-02-18b and earlier)

Full session handoff notes for earlier sessions have been moved to `docs/session-summaries/SESSION_LOG_2026.md`. Summary of key work completed:

- **2026-02-18b (Claude Code):** OSHA batch 1/4 done. 336 unused indexes dropped (3.0 GB). Freshness "3023" bug fixed. 29 crosswalk remaps (orphans 195->166, workers 92K->62K). CWA District 7 deferred.
- **2026-02-18 (Codex):** Missing unions analysis (195 orphans, 30 crosswalk mappings). WHD score backfill (11,297 employers). NLRB ULP matching gap analysis.
- **2026-02-18 (Codex):** Scorecard router, employer match provenance endpoint, API error tests (9 new).
- **2026-02-18 (Gemini):** State PERB research (12 states). BLS OEWS, cosine similarity, revenue-per-employee, ACS PUMS, calibration engine, O*NET research reports.
- **2026-02-18 (Gemini CLI):** Deep dive architecture research. Frontend expansion research (shadcn + TanStack Table). Revenue-per-employee data source confirmed.
- **2026-02-18 (Claude Code):** Batched re-run feature (`--batch N/M`). OSHA batch 1/4 started. Splink name floor 0.65 working (later raised to 0.70).
- **2026-02-17 (Claude Code):** Phase D1 auth hardening. Startup guard, centralized deps, 3 admin + 3 write endpoints protected.

For full details on any session, see `docs/session-summaries/SESSION_LOG_2026.md`.
