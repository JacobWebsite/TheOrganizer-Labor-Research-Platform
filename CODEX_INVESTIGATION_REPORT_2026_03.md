# Executive Summary
The repository contains a real, working platform, but its documentation is badly out of sync with current code and database reality. The scoring pipeline is substantially more advanced than older docs claim: it now has 10 factors, dynamic denominator logic, temporal decay, and a two-pillar final score path in `build_unified_scorecard.py`. Several previously flagged scoring issues are fixed (financial factor is no longer a copy, contracts are no longer flat, and one-factor Priority records are gone). The biggest active technical risk is security posture, not scoring math: local config currently disables auth, sensitive secrets are in `.env`, and there are many dynamically assembled SQL statements across routers. Match confidence normalization is fixed (0.0-1.0 only), and active orphan matches are currently zero, but medium-confidence fuzzy matches in the 0.85-0.95 band are still heavily used. Similarity remains effectively dead in production scorecards (0 non-NULL scores), so one advertised factor is still non-functional. Pipeline orchestration exists (`refresh_all.py`), but rebuilds still use drop/create patterns that can leave temporary no-view gaps on failure. Backup scripts exist, but I found no evidence in this environment that the scheduled backup task is active. Overall health: functional and improving, but still high-risk for launch due to security/configuration drift and documentation reliability.

# Part 1: Codebase Summary
## 1A: Project Structure
- `api/`: FastAPI backend with 25 router files plus middleware/config/database modules.
- `frontend/`: Active React/Vite app (React 19), with `src/` and `__tests__/`.
- `files/`: Legacy HTML/JS frontend assets still present (`files/js/*.js`, 19 JS files), plus small utility HTML pages.
- `scripts/`: ETL/matching/scoring/maintenance/research and large ad-hoc analysis script inventory.
- `tests/`: Large pytest suite; `pytest --collect-only` reports 1,051 tests.
- `docs/`: Extensive audits/roadmaps, many stale or contradictory.
- `archive/`: Very large historical area.

Python file counts (actual filesystem):
- Active (outside `archive/`): 371 `.py` files.
- Archived (`archive/`): 1,088 `.py` files.
- Total: 1,459 `.py` files.

Organization quality:
- Strength: clear major domains (`etl`, `matching`, `scoring`, `maintenance`).
- Weakness: top-level root is cluttered, many legacy docs coexist with newer docs, and stale references to old paths/frontends remain.

## 1B: Data Pipeline (`scripts/`)
### Stage 1 ETL (`scripts/etl/`)
- Count: 57 Python files.
- Pattern consistency: mixed. Many use `get_connection`, but style is inconsistent; 10 still contain hardcoded local user paths.
- Error handling: inconsistent. 36/57 include `except`; others are fail-fast scripts with minimal operator guidance.
- Reliability notes: at least some outbound data loaders use network calls without explicit timeout handling.

### Stage 2 Matching (`scripts/matching/`)
- Methods in active engine (`scripts/matching/deterministic_matcher.py`):
  - Tiered exact matching (EIN, name+city+state, name+state, aggressive name+state)
  - RapidFuzz blocked fuzzy
  - Trigram fallback
- Pipeline order: clear through `run_deterministic.py` and adapter-based execution.
- Legacy/leftover mix: yes. Splink files remain (`splink_*`) while primary runtime path now uses RapidFuzz but still labels method `FUZZY_SPLINK_ADAPTIVE` for compatibility.

### Stage 3 Scoring (`scripts/scoring/`)
- Main script: `scripts/scoring/build_unified_scorecard.py`.
- Actual factors in MV output: OSHA, NLRB, WHD, Contracts, Union Proximity, Industry Growth, Size, Similarity, Financial, plus research enhancement flag/coverage (`factors_total = 10` at line 692).
- Documentation mismatch: manifest still describes older 7-factor average model; code is now pillar-based weighted scoring.

### Stage 4 Maintenance (`scripts/maintenance/`)
- Count: 17 Python scripts.
- Includes rebuild/dedupe/reject scripts and backup scripts (`backup_labor_data.py` + scheduler setup PowerShell).
- "Refresh everything" script exists at `scripts/scoring/refresh_all.py` with ordered dependency chain.

## 1C: API (`api/`)
- Router files: 25 (excluding `__init__.py`), app exposes 212 `/api` routes at runtime.
- Auth mode in this workspace: effectively off for non-admin endpoints (`DISABLE_AUTH=true` in `.env`).
- Security concerns:
  - Credentials/API keys in plaintext `.env`.
  - Many dynamic SQL executions (92 `cur.execute(f"...")` occurrences across 20 router files), though many are allowlisted/parameterized.
  - Write endpoints guarded by `require_auth` become effectively public when auth is disabled.
- Broken endpoint patterns:
  - Some sector/museum routes rely on views not present in DB and return 404 by design.

## 1D: Frontend (`files/` + `frontend/`)
- Both versions exist:
  - Active React frontend under `frontend/`.
  - Legacy HTML/JS frontend under `files/` still present.
- Current backend comment says legacy `organizer_v5.html` archived, but it is still referenced by README and legacy files still exist.
- Frontend/API alignment:
  - Local static audit script (`check_frontend_api_alignment.py`) still reports differences and many risky `innerHTML` writes in legacy JS (not React).

## 1E: Tests (`tests/`)
- Backend tests: 1,051 collected (`python -m pytest tests --collect-only -q`).
- Backend execution check: partial run started and passed initial tests but full run timed out in this session.
- Frontend tests: could not run in this sandbox due Vite/esbuild spawn `EPERM` startup error.
- Coverage gaps likely remain around operational security and scheduler/backups (unit tests focus heavily on API/data correctness).

# Part 2: Investigation Findings
## Investigation 1: Scoring Pipeline
### OSHA Safety implementation is present and non-trivial
**Where:** `scripts/scoring/build_unified_scorecard.py:273`
**Severity:** MEDIUM
**Status:** FIXED since last audit

**What I found:**
OSHA scoring now compares to industry averages, weights violation severity (willful/repeat/serious), applies 5-year temporal decay, and adds a serious-violation bonus.

**Why it matters:**
This is materially better than flat violation counting and is less likely to over-rank stale or minor records.

**Suggested fix:**
No immediate fix required. Keep this implementation and document it in manifest/README.

**Effort:** 1-2 hours (docs only)
**Verify by:** Query `mv_unified_scorecard` and confirm non-uniform OSHA scores + decay columns exist.

### NLRB factor does not use 25-mile nearby elections
**Where:** `scripts/scoring/build_unified_scorecard.py:298` and `scripts/scoring/build_unified_scorecard.py:321`
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:**
NLRB score uses own election/ULP history plus industry momentum and state momentum. There is no geospatial 25-mile calculation.

**Why it matters:**
Documentation and user expectations can be misleading if they believe local geographic momentum is active.

**Suggested fix:**
1. Either implement a true geospatial nearby election component (lat/lon + distance) or
2. Update all docs/UI text to state clearly that momentum is industry/state-based, not radius-based.

**Effort:** 0.5 day (docs) or 1-2 days (feature)
**Verify by:** Search code for geospatial operators (`ST_DWithin` etc.) and confirm behavior/tests.

### Missing-data handling is mostly correct (NULL exclusion, not punitive zero)
**Where:** `scripts/scoring/build_unified_scorecard.py:614`, `scripts/scoring/build_unified_scorecard.py:654`, `scripts/scoring/build_unified_scorecard.py:697`
**Severity:** LOW
**Status:** FIXED since last audit

**What I found:**
The final scoring uses dynamic denominators and excludes absent factors/pillars by using conditional weights and `NULLIF(..., 0)`.

**Why it matters:**
Employers are no longer heavily penalized for missing government records alone.

**Suggested fix:**
No fix needed; preserve this pattern and add regression tests for denominator behavior.

**Effort:** 2-4 hours (tests/docs)
**Verify by:** Existing tests around `greatest null` and pillar null behavior.

### Similarity factor is still dead in output
**Where:** `scripts/scoring/build_unified_scorecard.py:493`, DB check on `mv_unified_scorecard`
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:**
Code includes `score_similarity`, but current DB state has `0` non-NULL similarity rows in both unified and target scorecards.

**Why it matters:**
One advertised factor has no operational effect, which can mislead users and distort tier interpretation.

**Suggested fix:**
1. Trace and repair the `employer_comparables -> similarity_agg -> score_similarity` chain.
2. Add a pre-build guard failing when comparables exist but similarity coverage is zero.
3. Expose similarity coverage in admin health metrics.

**Effort:** 1-2 days
**Verify by:** `COUNT(*) WHERE score_similarity IS NOT NULL` should be > 0 and stable after refresh.

### Contracts scoring is federal-only (no state/municipal integration)
**Where:** `scripts/scoring/build_unified_scorecard.py:360` and `scripts/scoring/build_unified_scorecard.py:361`
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:**
Contracts factor only reads `is_federal_contractor`/`federal_obligations`. No state/municipal contract fields are used.

**Why it matters:**
If users believe this is multi-level government contracting, they will over-trust coverage.

**Suggested fix:**
1. Keep current behavior but relabel as federal-only everywhere.
2. If needed, ingest and normalize state/municipal sources into a unified contract signal.

**Effort:** 2-4 hours (labeling) or multi-week (data expansion)
**Verify by:** DB schema inspection and UI/API text consistency checks.

## Investigation 2: Matching Quality
### Match storage schema supports confidence and quality bands
**Where:** `scripts/matching/create_unified_match_log.py:20`
**Severity:** LOW
**Status:** FIXED since last audit

**What I found:**
`unified_match_log` stores `match_method`, `match_tier`, `confidence_band`, `confidence_score`, `status`, `evidence`.

**Why it matters:**
This is sufficient for manual review workflows and confidence-based filtering.

**Suggested fix:**
No fix needed.

**Effort:** 0
**Verify by:** `\d unified_match_log` / schema query.

### Confidence normalization fixed to 0.0-1.0
**Where:** `scripts/matching/deterministic_matcher.py:995`, DB checks on `unified_match_log` and `nlrb_employer_xref`
**Severity:** LOW
**Status:** FIXED since last audit

**What I found:**
Confidence ranges are normalized; DB check shows no scores > 1.0 and NLRB xref now 0.90-0.98.

**Why it matters:**
Cross-source confidence semantics are now consistent.

**Suggested fix:**
No fix needed; keep regression assertion in test suite.

**Effort:** 0
**Verify by:** `MAX(confidence_score) <= 1.0` assertions.

### Low-band fuzzy matches are no longer active, but 0.85-0.95 band remains large
**Where:** `scripts/matching/run_deterministic.py:248`, DB check on active fuzzy rows
**Severity:** MEDIUM
**Status:** PARTIALLY FIXED

**What I found:**
Active fuzzy below 0.85 is now zero. However, 3,947 active fuzzy matches remain in 0.85-0.95 range.

**Why it matters:**
This band was previously flagged as high false-positive risk and still affects downstream scoring.

**Suggested fix:**
1. Add secondary constraints (state/NAICS/address) for 0.85-0.95 fuzzy rows.
2. Route medium-confidence fuzzy matches through manual review queue before legacy table promotion.

**Effort:** 1-2 days
**Verify by:** Reduced medium fuzzy volume and improved sampled precision.

## Investigation 3: Security
### Authentication is disabled in current runtime config
**Where:** `.env:13`, `api/config.py:19`, `api/middleware/auth.py:45`
**Severity:** CRITICAL
**Status:** KNOWN-UNFIXED

**What I found:**
`DISABLE_AUTH=true` is set in local config, which bypasses JWT checks for non-public API routes.

**Why it matters:**
Any caller can access data endpoints without login; this breaks basic access control assumptions.

**Suggested fix:**
1. Set `DISABLE_AUTH=false` in deployed environments.
2. Fail startup if `DISABLE_AUTH=true` outside explicit dev profile.
3. Add CI/deploy guard that rejects insecure auth configuration.

**Effort:** 2-6 hours
**Verify by:** Anonymous request to protected endpoint returns 401.

### Write endpoints remain writable when auth is disabled
**Where:** `api/dependencies.py:21`, `api/routers/employers.py:555`, `api/routers/research.py:74`
**Severity:** CRITICAL
**Status:** NEW

**What I found:**
`require_auth` returns a synthetic admin user when JWT is disabled, so mutation routes using `Depends(require_auth)` become effectively unauthenticated writes.

**Why it matters:**
Attackers can create/delete flags, trigger refreshes, and submit research-related writes without credentials.

**Suggested fix:**
1. Change `require_auth` fail-open behavior to fail-closed when JWT is disabled.
2. Allow explicit dev bypass only behind separate secret/IP allowlist.
3. Add tests ensuring write routes reject anonymous requests in all production profiles.

**Effort:** 0.5-1 day
**Verify by:** Anonymous `POST /api/employers/flags` should fail with 401/503.

### Secrets exposed in plaintext project `.env`
**Where:** `.env:5`, `.env:9`, `.env:17`
**Severity:** CRITICAL
**Status:** KNOWN-UNFIXED

**What I found:**
Database password, JWT secret, and Google API key are directly present in repo workspace.

**Why it matters:**
Credential leakage enables database access, token forging, and third-party API abuse.

**Suggested fix:**
1. Rotate all exposed secrets immediately.
2. Remove real secrets from tracked/shared files.
3. Use secret manager/environment injection for runtime.

**Effort:** 2-6 hours
**Verify by:** Old credentials no longer authenticate; new secrets only in secure store.

### Dynamic SQL is still widespread
**Where:** 92 `cur.execute(f"...")` sites across 20 router files (example: `api/routers/sectors.py:192`)
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:**
Most dynamic SQL now uses allowlists and parameter binding, but f-string query assembly still appears extensively.

**Why it matters:**
Large dynamic-SQL surface increases regression risk; a single missing allowlist can reopen injection class bugs.

**Suggested fix:**
1. Prioritize converting identifier interpolation to vetted helper functions.
2. Add static checks in CI for unsafe SQL string assembly patterns.
3. Add focused tests for key sort/filter routes.

**Effort:** 2-5 days
**Verify by:** Static scan count decreases and injection regression tests pass.

## Investigation 4: Pipeline Reliability
### Rebuild path has drop/create gap (not crash-safe for availability)
**Where:** `scripts/scoring/build_unified_scorecard.py:848`, `scripts/scoring/build_unified_scorecard.py:849`, `scripts/scoring/build_unified_scorecard.py:853`
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:**
Default create path drops MV and commits before recreate. If script fails after drop, MV is absent.

**Why it matters:**
Mid-run failure can leave the app without scorecard views until manual intervention.

**Suggested fix:**
1. Prefer `REFRESH CONCURRENTLY` for routine runs.
2. For definition changes, build new MV name then atomic swap/rename.
3. Add failure rollback and post-step existence assertions.

**Effort:** 1-2 days
**Verify by:** Simulated failure after drop no longer leaves missing production MV.

### Locking is per-step, not global chain lock
**Where:** `scripts/scoring/_pipeline_lock.py:18`, `scripts/scoring/refresh_all.py:59`
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:**
Each script uses its own advisory lock key; `refresh_all.py` runs scripts as separate subprocesses without a chain-level lock.

**Why it matters:**
Concurrent manual runs can still interleave different steps and create inconsistent intermediate states.

**Suggested fix:**
1. Add single global chain lock in `refresh_all.py`.
2. Keep per-step locks as secondary safety.
3. Log lock ownership and reject overlapping chain starts.

**Effort:** 0.5-1 day
**Verify by:** Starting two full refreshes concurrently should reject one immediately.

### "Run everything in order" script exists
**Where:** `scripts/scoring/refresh_all.py:21`
**Severity:** LOW
**Status:** FIXED since last audit

**What I found:**
There is an explicit ordered orchestrator (`STEPS`) that runs full chain in dependency order.

**Why it matters:**
This reduces operator error vs manual script ordering.

**Suggested fix:**
No core fix needed; improve lock semantics and failure mode handling.

**Effort:** 0
**Verify by:** End-to-end run logs each step in declared order.

## Investigation 5: Dead Code and Confusion
### Manifest and docs claim removed `scripts/ml/` still active
**Where:** `PIPELINE_MANIFEST.md:127`, filesystem check (`scripts/ml` absent)
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:**
Manifest still contains an ML pipeline section and stale script counts even though `scripts/ml/` is removed.

**Why it matters:**
Operators will run wrong commands and trust wrong architecture descriptions.

**Suggested fix:**
1. Remove obsolete sections from manifest.
2. Regenerate script counts automatically from filesystem in CI.

**Effort:** 2-4 hours
**Verify by:** Manifest script inventory matches actual files and directory counts.

### README startup instructions point to old frontend path
**Where:** `README.md:19`, `README.md:117`, `README.md:199`
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:**
README still tells users to open legacy `files/organizer_v5.html` and reports stale router/test counts.

**Why it matters:**
New contributors will start the wrong UI and misread platform status.

**Suggested fix:**
1. Rewrite Quick Start to React path (`frontend` + Vite build/dev).
2. Replace static counts with generated metrics.

**Effort:** 2-6 hours
**Verify by:** Fresh setup from README launches correct frontend + API successfully.

### Manifest spot-check (5 sampled entries)
Checked entries:
- `scripts/etl/load_osha_violations.py`: exists, does OSHA load work (match).
- `scripts/etl/load_sec_edgar.py`: exists, SEC ingest logic present (match).
- `scripts/matching/run_deterministic.py`: exists, main matching CLI (match).
- `scripts/scoring/compute_gower_similarity.py`: exists, Gower pipeline (match).
- `scripts/maintenance/create_data_freshness.py`: exists, freshness table/refresh (match).

Overall sampled entry correctness: 5/5 match, but global manifest metadata is stale.

## Investigation 6: Documentation vs Reality
- Scoring factor count in code: 10 (`factors_total = 10` in unified scorecard SQL path).
- Backend tests collected now: 1,051 (`pytest --collect-only`).
- API router files now: 25 routers (not 17).
- README startup instructions are outdated for current React-first workflow.

# Part 3: Prioritized Fix List
## Tier 1: Fix Immediately (Dangerous or Actively Misleading)
### Disable-auth + write access fail-open
**Where:** `api/dependencies.py:21`, `api/routers/employers.py:555`
**Severity:** CRITICAL
**Status:** NEW

**What I found:** auth-disabled mode allows write routes with synthetic admin.

**Why it matters:** unauthenticated mutation of production data/workflows.

**Suggested fix:**
1. Make `require_auth` fail closed when JWT disabled.
2. Reserve bypass for explicit local dev-only switch plus network boundary.
3. Add regression tests for all write routes.

**Effort:** 0.5-1 day
**Verify by:** Anonymous write attempts return 401/503.

### Rotate and remove exposed secrets
**Where:** `.env:5`, `.env:9`, `.env:17`
**Severity:** CRITICAL
**Status:** KNOWN-UNFIXED

**What I found:** live DB/JWT/API secrets are exposed in plaintext.

**Why it matters:** immediate compromise risk.

**Suggested fix:** rotate secrets, move to secret manager, scrub history/shares.

**Effort:** 2-6 hours
**Verify by:** old secrets invalid; app works with new injected secrets only.

### Remove insecure Docker JWT fallback
**Where:** `docker-compose.yml:36`
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:** fallback secret `dev-only-change-me` still exists.

**Why it matters:** weak JWT secret can enable token forgery in misconfigured deployments.

**Suggested fix:** remove fallback; require explicit non-default secret on startup.

**Effort:** 1-2 hours
**Verify by:** API container fails startup when secret unset/default.

## Tier 2: Fix Before Launch (Broken but Not Dangerous)
### Fix similarity factor pipeline (currently 0 coverage)
**Where:** `scripts/scoring/build_unified_scorecard.py:493`
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:** similarity score always NULL in live scorecards.

**Why it matters:** score interpretation missing intended signal.

**Suggested fix:** repair comparables bridge + add pre-build guard.

**Effort:** 1-2 days
**Verify by:** non-zero similarity coverage after rebuild.

### Eliminate MV drop/create availability gap
**Where:** `scripts/scoring/build_unified_scorecard.py:848`
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:** failure after drop can remove score view temporarily.

**Why it matters:** partial outages and stale data windows.

**Suggested fix:** concurrent refresh or shadow-build + swap strategy.

**Effort:** 1-2 days
**Verify by:** fault injection does not remove current view.

### Convert high-risk dynamic SQL routes to hardened query builders
**Where:** dynamic SQL across 20 router files (example `api/routers/sectors.py:192`)
**Severity:** HIGH
**Status:** KNOWN-UNFIXED

**What I found:** broad dynamic SQL footprint remains.

**Why it matters:** future regressions can reintroduce SQL injection.

**Suggested fix:** migrate to strict allowlist helpers and CI static rules.

**Effort:** 2-5 days
**Verify by:** reduced dynamic SQL count + passing injection regression tests.

## Tier 3: Fix When Possible (Messy but Functional)
### Reconcile docs/manifest/README with real system
**Where:** `README.md:117`, `PIPELINE_MANIFEST.md:4`, `PIPELINE_MANIFEST.md:127`
**Severity:** MEDIUM
**Status:** KNOWN-UNFIXED

**What I found:** counts and startup docs are stale/inconsistent.

**Why it matters:** slows onboarding and causes operator mistakes.

**Suggested fix:** auto-generate metrics and canonical quickstart from current repo state.

**Effort:** 0.5-1 day
**Verify by:** consistency check script passes across docs.

### Confirm backup scheduler is actually running in deployment
**Where:** `scripts/maintenance/setup_backup_task.ps1:1`
**Severity:** MEDIUM
**Status:** NEEDS INVESTIGATION

**What I found:** backup scripts exist, but scheduled task was not found in this environment.

**Why it matters:** scripts alone do not guarantee recoverability.

**Suggested fix:** configure and monitor scheduled backup task, add restore test playbook.

**Effort:** 0.5 day
**Verify by:** scheduled task present + successful test restore.

# Previous Audit Status (15 items)
| # | Previous Finding | Current Status |
|---|---|---|
| 1 | `score_financial` copied industry growth | FIXED (separate financial logic; low corr ~0.1069) |
| 2 | Government contracts scoring was flat | FIXED (6 distinct contract score buckets) |
| 3 | 231 Priority employers had only 1 factor | FIXED (current count: 0) |
| 4 | Similarity dead / weight issues | KNOWN-UNFIXED (coverage still 0) |
| 5 | 86% Priority had no enforcement | PARTIAL (now ~61.2%, still high) |
| 6 | 0.70-0.80 fuzzy band high FP | PARTIAL (active fuzzy <0.85 now 0; 0.85-0.95 still large) |
| 7 | 46,627 orphan match records | PARTIAL/FIXED for active (active orphans 0; historical non-active still exist) |
| 8 | NLRB participants table 83.6% junk | NEEDS INVESTIGATION (did not reproduce exact metric definition) |
| 9 | NLRB confidence stored as 90/98 | FIXED (0.90-0.98 in xref; no >1.0 in match log) |
| 10 | No automated DB backups | PARTIAL (scripts exist; scheduler not confirmed active here) |
| 11 | 49 API routes with f-string SQL | KNOWN-UNFIXED (still broad dynamic SQL footprint: 92 statements) |
| 12 | `DISABLE_AUTH=true` default | KNOWN-UNFIXED in current workspace (`.env` sets true) |
| 13 | Docs contradict each other | KNOWN-UNFIXED |
| 14 | Pipeline race conditions | PARTIAL (per-step locks exist, no global chain lock) |
| 15 | Size+Proximity overweight/low predictive | NEEDS INVESTIGATION (weights changed to pillar model; effect still questionable) |

# Surprises
- `README.md` is significantly behind reality and still routes users to legacy frontend despite active React app.
- Dynamic SQL is still very widespread even after prior injection-focused audit rounds.
- The backup story is split across scripts/docs/scheduler setup, but operational proof of scheduled execution is not obvious from this environment.
- Legacy and modern systems co-exist (React + legacy JS + deprecated API endpoints), which increases maintenance and security surface area.

# What I did not fully check
- I did not execute the full 1,051-test backend suite to completion in this run (partial run timed out).
- I could not run frontend Vitest in this sandbox due `esbuild` spawn `EPERM`.
- I did not manually validate every API route against live DB schema; I sampled high-risk routes and ran targeted DB checks.
