# Full Platform Audit - Codex (Round 4, Deep Pass)
## Labor Relations Research Platform
Date: 2026-02-23
Auditor: Codex

## Scope
- Live DB audit on `olms_multiyear` via `db_config.get_connection()`.
- API testing against `http://127.0.0.1:8001`.
- Backend tests: `python -m pytest tests/ -v`.
- Static frontend/code review in `frontend/` and `api/`.
- Section-by-section execution of the prompt with deeper samples and cross-checks.

## Section 1 - Database Inventory (Checkpoint)
### Verified inventory
- Objects: `312` (`182` tables/partitioned tables, `124` views, `6` materialized views).
- Total DB object footprint measured from relation sizes: `11.166 GB` (expected in prompt ~`9.5 GB`).
- Inventory artifact: `docs/session-summaries/db_inventory_codex_r4_section1.csv`.

### Count discrepancies vs prompt baseline
- `master_employer_source_ids`: expected `3,080,492`; actual `3,072,689` (delta `-7,803`).
- `unions_master`: expected `26,665`; actual `26,693` (delta `+28`).
- `irs_bmf`: expected `2,043,779`; actual `2,043,472` (delta `-307`).

### Zero-row objects
- `cba_wage_schedules` (table)
- `platform_users` (table)
- `splink_match_results` (table)
- `v_multi_employer_groups` (view)

### Materialized views present (6, not 4)
- `mv_organizing_scorecard` (`212,441`)
- `mv_employer_data_sources` (`146,863`)
- `mv_unified_scorecard` (`146,863`)
- `mv_employer_search` (`107,025`)
- `mv_whd_employer_agg` (`330,419`)
- `mv_employer_features` (`54,968`)

### Finding 1.1
- **Severity:** MEDIUM
- **Confidence:** Verified
- **Issue:** Prompt/documented baseline says “4 key MVs,” but system has 6 active MVs and docs only partially reflect this.
- **Practical impact:** Refresh/operational runbooks can miss data dependencies.

### Finding 1.2
- **Severity:** MEDIUM
- **Confidence:** Verified
- **Issue:** Database size and key table counts drift from expected baseline.
- **Practical impact:** Status dashboards and benchmark checks can hide regressions.

## Section 2 - Data Quality Deep Dive (Checkpoint)
### Top-table quality checks (expanded)
- F7 completeness (`146,863` rows):
  - employer name: `100%`
  - state: `97.35%`
  - NAICS: `84.89%`
  - lat/lng pair: `73.79%`
  - EIN column: **not present** in `f7_employers_deduped`
- Master quality (`2,736,890` rows):
  - `data_quality_score >= 40`: `43,724` (`1.60%`)
  - `>= 60`: `8,955` (`0.33%`)
  - `>= 80`: `100` (`0.004%`)
  - EIN present: `1,777,263` (`64.94%`)
- `unified_match_log` (`1,738,115`):
  - active `206,191`
  - superseded `491,483`
  - rejected `1,040,441`

### Scorecard factor availability (`mv_unified_scorecard`)
- coverage counts:
  - `score_union_proximity`: `68,827`
  - `score_size`: `146,863`
  - `score_nlrb`: `25,879`
  - `score_contracts`: `8,672`
  - `score_industry_growth`: `124,680`
  - `score_similarity`: `186`
  - `score_osha`: `31,459`
  - `score_whd`: `12,025`
- `factors_available` distribution:
  - 1 factor: `7,451`
  - 2 factors: `49,770`
  - 3 factors: `57,957`
  - 4+ factors: `31,685`

### Orphans and linkage health
- F7 employer -> union missing target (`latest_union_fnum` unmatched): `355`.
- UML records pointing to missing F7 target IDs: `46,627`.

### Member dedup check
- `SUM(unions_master.members) = 73,334,761`.
- `v_union_members_deduplicated` exists; `SUM(members)=71,974,947`.

### Finding 2.1
- **Severity:** CRITICAL
- **Confidence:** Verified
- **Issue:** Deduplicated membership narrative (~14.5M) does not match live aggregate member totals (>71M).
- **Practical impact:** Benchmark claims and strategy confidence are materially unreliable.

### Finding 2.2
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** Significant share of records are scored with very sparse factor coverage (1-2 factors for `57,221` employers).
- **Practical impact:** Organizer ranking can overfit to thin signals.

## Section 3 - Matching Pipeline Integrity (Checkpoint)
### Deep sample verification
- Sampled `20` HIGH active, `20` MEDIUM active, `10` LOW (all rejected in practice).
- Heuristic record-level adjudication (source name/state/city vs target):
  - HIGH likely-bad: `2/20`
  - MEDIUM likely-bad: `4/20` (mostly crosswalk/mergent entries with thin evidence context)
  - LOW likely-bad: `3/10` (appropriately rejected)

### Confirmed problematic HIGH examples
- `HOME ASSOCIATES OF VIRGINIA` -> `Virginia Association of Contractors` (name similarity ~0.357).
- `DIEDE CONSTRUCTION` -> `J F SHEA CONSTRUCTION ...` (name similarity ~0.475).

### Structural checks
- OSHA source matched to multiple active F7 targets: `0` (best-match-wins behavior holds).
- F7 employers with `>=50` active OSHA matches: many (`top=226`).
- Legacy table parity with UML-active:
  - OSHA: `97,142` vs `97,142` (match)
  - WHD: `19,462` vs `19,462` (match)
  - SAM: `28,816` vs `28,815` (off by 1)
  - 990: `20,005` vs `20,215` (off by 210)

### Splink floor
- Observed min `name_similarity` in Splink-marked records: `0.65` (not 0.70 documented threshold).

### Grouping checks
- Canonical groups with `>20` members: `221`.
- Canonical groups with `>=100` members: `13`.

### Match drift
- Superseded source IDs without active replacement: `46,484`.
- By source (top): `990 (15,452)`, `OSHA (12,952)`, `WHD (11,074)`.

### Finding 3.1
- **Severity:** CRITICAL
- **Confidence:** Verified
- **Issue:** HIGH-confidence set still contains clear false positives.
- **Practical impact:** Misattributed violations/contracts can mis-rank real targets.

### Finding 3.2
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** Superseded-without-replacement match drift is substantial.
- **Practical impact:** Reruns can silently remove usable linkages.

## Section 4 - Scoring System Verification (Checkpoint)
### Formula and distribution
- Weighted formula manually recomputed on random sample; MV values match within rounding tolerance.
- Tier distribution (after guardrail patch + full MV rebuild):
  - Priority `1.39%`
  - Strong `13.60%`
  - Promising `24.99%`
  - Moderate `34.99%`
  - Low `25.03%`
- Score range: `0.00` to `10.00`.

### Priority quality checks
- Priority total: `2,047`.
- Priority with `factors_available <= 2`: `0` (`0.0%`).
- Priority with exactly 1 factor: `0`.
- Unified score 10.00 rows: `332`:
  - with 1 factor: `220`
  - with 2 factors: `109`
  - with 3 factors: `3`

### Guardrail implementation evidence
- Code patch applied in `scripts/scoring/build_unified_scorecard.py`:
  - `Priority` now requires `score_percentile >= 0.97 AND factors_available >= 3`.
- Operational note:
  - `--refresh` only refreshes existing MV definition and does not apply SQL-definition changes.
  - Full rebuild (`python scripts/scoring/build_unified_scorecard.py`) is required after logic edits.
- Before/after impact:
  - Priority count: `4,190 -> 2,047`.
  - Priority with 1-2 factors: `2,143 -> 0`.

### Similarity factor utility
- `score_similarity` present on only `186` rows (`0.13%`).
- Distinct similarity values observed: only `3`.

### Half-life behavior
- OSHA: recent inspections produce materially higher decay-adjusted score than old inspections (behavior consistent).
- WHD: case-count buckets increase monotonically; recent cases score much higher (expected with decay).
- NLRB ULP buckets: score increases with ULP volume (monotonic).

### Finding 4.1
- **Severity:** MEDIUM (improved from CRITICAL after patch)
- **Confidence:** Verified
- **Issue:** Priority sparse-signal inflation was corrected by factor-coverage guardrail.
- **Practical impact:** Top-tier rankings now exclude thin-signal 1-2 factor records.

### Finding 4.2
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** `score_similarity` currently provides negligible differentiation at platform scale.
- **Practical impact:** One of 8 weighted factors is effectively non-participating.

## Section 5 - API & Endpoint Testing (Checkpoint)
### Functional checks
- Verified 200 responses on core endpoints:
  - `/api/health`
  - `/api/employers/search?q=walmart`
  - `/api/scorecard/`
  - `/api/scorecard/unified`
  - `/api/master/stats`
  - `/api/master/non-union-targets`
  - `/api/profile/employers/{id}`
  - `/api/corporate/family/{id}`
  - `/api/unions/search?q=teamsters`

### Repeated timing (3 runs each)
- Slow endpoints:
  - `/api/master/stats`: avg `4444ms`, max `7015ms`
  - `/api/admin/match-quality`: avg `4958ms`, max `5059ms`
  - `/api/master/non-union-targets`: avg `2049ms`
  - `/api/admin/match-review?limit=5`: avg `1254ms`, max `2205ms`

### Auth + admin access
- `.env` has `DISABLE_AUTH=true`.
- Admin hardening patch applied:
  - all `/api/admin/*` endpoints now enforce `Depends(require_admin)`.
  - fail-closed behavior is default when auth is disabled unless `ALLOW_INSECURE_ADMIN=true`.
- Anonymous admin requests now fail:
  - `/api/admin/match-quality` -> `503`
  - `/api/admin/data-freshness` -> `503`
  - `/api/admin/refresh-freshness` -> `503`
  - `/api/admin/employer-groups` -> `503`

### Deprecated/stale endpoint behavior
- `/api/scorecard/` wrapper still serves legacy organizing scorecard path (`mv_organizing_scorecard`) in `api/routers/scorecard.py`.
- Unified tier names are available in unified endpoints, not legacy wrapper.

### SQL injection review
- Injection probe query (`walmart' OR 1=1 --`) did not break endpoint behavior.
- Dynamic SQL exists in multiple routers via f-strings; major paths often use param binding for values.
- Some dynamic object-name queries depend on allowlists (example sectors views via `SECTOR_VIEWS`).

### CORS
- Not wildcard in code defaults; local origins list from config.

### Finding 5.1
- **Severity:** RESOLVED (was CRITICAL pre-patch)
- **Confidence:** Verified
- **Issue:** Admin mutation endpoints were reachable anonymously before hardening.
- **Practical impact:** Risk is mitigated by route-level `require_admin` + fail-closed dependency behavior.

### Finding 5.2
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** Several API endpoints exceed the 3-second target.
- **Practical impact:** Frontend admin/analysis workflows degrade and can time out.

## Section 6 - Frontend & React App (Checkpoint)
### Structure + phase presence
- Feature directories present: `auth`, `search`, `employer-profile`, `scorecard`, `union-explorer`, `admin`.
- `frontend/src/features` file count: `54`.
- Test files detected: `21` in `frontend/__tests__/`.

### Build/test execution status
- Inside sandbox: Node child-process spawning is blocked (`spawn EPERM`), so Vite/esbuild fails.
- Outside sandbox (escalated execution): both commands pass:
  - `npm.cmd run build` -> success (`1877` modules transformed)
  - `npx.cmd vitest run` -> `21` files, `134` tests passed
- Added script for consistency:
  - `frontend/package.json`: `"test": "vitest run"`

### API wiring checks
- API hooks use relative paths via `apiClient` (`fetch(url, ...)`) and no hardcoded localhost endpoint in app API code.
- Employer profile page shows 8-factor section (`ScorecardSection`) and explanatory help copy.

### Legacy frontend coexistence
- Legacy file `files/organizer_v5.html` still served:
  - `GET /` -> `200`
  - `GET /files/organizer_v5.html` -> `200`

### Accessibility spot-check
- Inputs/filters generally include labels or `aria-label` in inspected components.

### Finding 6.1
- **Severity:** LOW
- **Confidence:** Verified
- **Issue:** Frontend build/test cannot run in sandboxed Node due child-process restrictions, but passes outside sandbox.
- **Practical impact:** CI/runtime policy must allow Node child processes for Vite/esbuild.

## Section 7 - Master Employer Table & Dedup (Checkpoint)
### Core counts
- `master_employers`: `2,736,890` (matches expected).
- `master_employer_merge_log`: `289,400` merges (matches expected).
- `is_labor_org=true` in master: `6,686` (matches expected).

### Source-origin split
- `bmf 1,754,142`, `sam 781,778`, `f7 146,863`, `mergent 54,107`.

### Source link integrity
- Master records with zero source IDs: `0`.
- Random sample linkbacks validated to source tables (including SAM by `uei`) with successful lookups.

### Remaining duplicate pressure
- Duplicate groups by normalized name/state/zip: `32,475` (many low-quality blank-name clusters).

### Master API consistency
- `/api/master/stats` counts matched DB exactly.
- `/api/master/non-union-targets` is intentionally filtered (not full non-union population), and sample results had no `is_union=true` leaks.

### Finding 7.1
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** Significant duplicate residue remains in master table cohorts.
- **Practical impact:** Non-union discovery can over-fragment targets.

## Section 8 - Scripts, Pipeline & Code Quality (Checkpoint)
### Pipeline manifest vs disk
- Disk counts:
  - total scripts under `scripts/`: `144`
  - non-analysis pipeline scripts: `89`
- Manifest text says `134` active and `80` pipeline.

### Script spot verification
- 10 random manifest-listed scripts exist and run with `--help`/import entry behavior.

### Security/path scans
- Hardcoded credential token `Juniordog33`: no hits in `scripts/`.
- Broken pattern `password='os.environ.get(...)`: no hits.
- Hardcoded local absolute paths still present in multiple scripts (not all parameterized/config-driven).

### Tests
- `python -m pytest tests/ -v`:
  - `492 passed, 1 skipped` (total `493` collected).

### Coverage gaps
- Router name references absent in tests for: `cba`, `museums`, `public_sector` (string-reference proxy check).

### Archive cleanup
- `archive/old_scripts` contains `602` `.py` files (cleanup appears executed).

### Finding 8.1
- **Severity:** MEDIUM
- **Confidence:** Verified
- **Issue:** Pipeline manifest script counts are stale against disk reality.
- **Practical impact:** Operators can miss active scripts or misestimate maintenance surface.

### Finding 8.2
- **Severity:** MEDIUM
- **Confidence:** Verified
- **Issue:** Hardcoded absolute file paths remain in active scripts.
- **Practical impact:** Portability and automation are brittle.

## Section 9 - Documentation Accuracy (Checkpoint)
### Key drift examples
- `Start each AI/CLAUDE.md` includes stale metrics and stale caveats (examples):
  - `mv_employer_search` listed as `118,015` (actual `107,025`).
  - old warnings like “IRS BMF has 25 rows” despite actual ~2.04M.
  - mixed legacy and modern score systems in same doc.
- `Start each AI/PROJECT_STATE.md` contains mixed fresh + stale counts:
  - `master_employer_source_ids 3,080,492` (actual `3,072,689`)
  - `whd_cases 362,634` in one section vs actual `363,365`
  - `osha_establishments 1,007,275` in one section vs actual `1,007,217`
  - table list says `178` tables, while deep inventory found `182` tables/partitioned tables.

### Core references
- `UNIFIED_ROADMAP_2026_02_19.md` filename usage is mostly consistent now.
- Most core docs reference `UNIFIED_PLATFORM_REDESIGN_SPEC.md`; `PIPELINE_MANIFEST.md` does not.

### Finding 9.1
- **Severity:** HIGH
- **Confidence:** Verified
- **Issue:** Primary AI handoff docs contain significant stale metrics and mixed-generation guidance.
- **Practical impact:** AI and human contributors will continue making inconsistent decisions.

## Section 10 - Summary & Recommendations
### Health score
- **Needs Work**

### Top 10 issues by organizer impact
1. HIGH-confidence match false positives still exist.
2. Membership dedup claim is not reconciled to live totals.
3. Slow core/admin endpoints (>3s target).
4. Match lifecycle drift (`superseded` without active replacement).
5. Similarity factor has near-zero coverage.
6. Master dedup residue remains high.
7. Legacy/unified table count mismatch by source (990, SAM).
8. Documentation drift across core handoff files.
9. Priority ghost-signal concentration remains high despite guardrail.
10. Pipeline manifest/script-count drift.

### Quick wins (<1 hour)
1. Completed: block admin endpoints when auth is disabled unless explicitly overridden.
2. Completed: startup warning now distinguishes blocked-admin vs insecure-admin mode.
3. Completed: Priority tier guardrail (`factors_available >= 3`) with measured reduction.
4. Publish one auto-generated metrics snapshot and link docs to it.
5. Added: `npm test` script alias to `vitest run` in `frontend/package.json`.

## Remediation Patch Plan (Actionable)
### Patch A - Auth hardening (recommended immediate)
Status: **Implemented**
1. Route protection normalized to `Depends(require_admin)` for all `/api/admin/*` endpoints.
2. `require_admin` now fails closed when `JWT_SECRET` is absent unless `ALLOW_INSECURE_ADMIN=true`.
3. Verification complete: anonymous admin calls return `503` under current `DISABLE_AUTH=true`.

### Patch B - Priority inflation guardrail
Status: **Implemented**
1. Applied in `scripts/scoring/build_unified_scorecard.py`:
   - `score_tier='Priority'` requires `score_percentile >= 0.97 AND factors_available >= 3`.
2. Rebuilt MV and confirmed:
   - Priority count `4,190 -> 2,047`.
   - Priority with `factors_available<=2`: `51.1% -> 0.0%`.

### Patch C - Match quality tightening
1. Enforce documented name floor for probabilistic links (`>=0.70`) consistently in all pathways.
2. Re-run matching for affected sources (OSHA/990/WHD/SAM/SEC).
3. Recheck high-confidence sample error rate.

### Patch D - Frontend build/test enablement
Root cause: Node cannot spawn child processes in sandbox (`spawnSync ... EPERM`), which Vite/esbuild needs.

What works:
1. Run build/test outside sandbox or in CI with unrestricted process spawning:
   - `npm.cmd run build`
   - `npx.cmd vitest run` (or `npm.cmd test` after patch)

Environment changes that fix this:
1. Allow `node.exe` child-process spawning via endpoint policy/AppLocker/EDR rules.
2. Ensure execution policy does not block script wrappers (`npm.ps1`/`npx.ps1`) or use `.cmd` variants.
3. If controlled folder access is enabled, allow Node and `frontend/node_modules/*` execution.

### Data quality priorities
1. Reconcile membership dedup source-of-truth and expose auditable method.
2. Improve match QA on HIGH/MEDIUM sets with stricter name floor and sampled review.
3. Reduce low-quality master duplicate clusters.

### Scoring assessment
- 8-factor weighted framework is structurally implemented and formula checks out.
- Current outputs are not yet decision-grade because sparse-factor inflation distorts top tiers.

### Master employer assessment
- Solid base with full source-link coverage and expected size.
- Needs additional dedup cleanup before “single source of truth” confidence.

### Frontend assessment
- Feature-complete structure and hooks are present.
- Build/test reproducibility in this runtime is currently blocked; treat production readiness as conditional.

### Matching assessment
- Pipeline architecture is strong and best-match constraints are mostly working.
- Precision still insufficient in a subset of high-confidence results.

### Security assessment
- Primary anonymous-admin blocker is mitigated by code-level fail-closed admin enforcement.
- CORS wildcard is not present by default code path.

### Documentation gaps
- Need one authoritative auto-generated metrics doc consumed by all handoff docs.
- Need explicit “legacy vs active endpoint/table” matrix.

## Section 11 - What No One Asked (Blind Spots)
### 11.1 Ghost priorities
- Priority employers with no OSHA/NLRB/WHD/federal activity in last 5 years: `1,895 / 2,047`.
- Guardrail removed thin-signal rows, but a large share of top tier still lacks recent enforcement/contract signals.

### 11.2 Hidden-target risk from matching errors
- Very high many-to-one OSHA mappings and confirmed false positives suggest systematic over-linking can hide/warp target lists.

### 11.3 Industry blind spots
- Amazon-like names: only `4` rows detected; none Priority.
- Starbucks-like names: `235` rows; none Priority, `46` Strong.
- Cannabis proxy NAICS patterns returned `0` rows in tested prefixes (coverage gap signal).

### 11.4 No-data vs clean-data ambiguity
- OSHA split:
  - no OSHA data: `115,404`
  - OSHA data + zero violations: `7,911`
  - OSHA data + violations: `23,548`
- Product currently does not clearly separate “no inspection coverage” from “clean history” in top-level ranking semantics.

### 11.5 False-negative proxy
- Recent 2-year election-win matched employers: `957`.
- In Priority/Strong: `239` (`25.0%`).
- In Low: `235` (`24.6%`).
- Signal: model misses many real organizing wins in high-priority buckets.

## Queries/Commands Used (Representative)
```sql
SELECT SUM(COALESCE(members,0)) FROM unions_master;

SELECT source_system, status, COUNT(*)
FROM unified_match_log
GROUP BY source_system, status;

SELECT factors_available, COUNT(*)
FROM mv_unified_scorecard
GROUP BY factors_available;

SELECT COUNT(*)
FROM mv_unified_scorecard
WHERE score_tier='Priority'
  AND (osha_latest_inspection IS NULL OR osha_latest_inspection < CURRENT_DATE-INTERVAL '5 years')
  AND (nlrb_latest_election IS NULL OR nlrb_latest_election < CURRENT_DATE-INTERVAL '5 years')
  AND (whd_latest_finding IS NULL OR whd_latest_finding < CURRENT_DATE-INTERVAL '5 years')
  AND COALESCE(federal_contract_count,0)=0;
```

```bash
python -m pytest tests/ -v
```

```powershell
Invoke-WebRequest http://127.0.0.1:8001/api/master/stats
Invoke-WebRequest http://127.0.0.1:8001/api/admin/score-versions
Invoke-WebRequest -Method POST http://127.0.0.1:8001/api/admin/refresh-freshness
```

