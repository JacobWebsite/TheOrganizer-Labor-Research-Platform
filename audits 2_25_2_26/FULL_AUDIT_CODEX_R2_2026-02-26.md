# CODEX_ROUND2_DEEP_INVESTIGATION_2026-02-26

## Investigation 1
### The Question
How should the missing NLRB nearby 25-mile scoring component be implemented, using existing data, without changing code yet?

### The Evidence

- TODO location in scoring code:
  - `scripts/scoring/build_unified_scorecard.py:207`
  - ```sql
    -- TODO: nearby 25-mile momentum requires geocoded employer locations. Keep current own-history model.
    CASE
        WHEN eds.has_nlrb AND na.f7_employer_id IS NOT NULL THEN
            LEAST(10, GREATEST(0, ROUND((
                (COALESCE(na.win_count, 0) * 2 + COALESCE(na.election_count, 0) - COALESCE(na.loss_count, 0))
                * na.latest_decay_factor
                + CASE ... END * na.ulp_decay_factor
            )::numeric, 2)))
    END AS score_nlrb,
    ```

- Current NLRB aggregation path:
  - `scripts/scoring/build_unified_scorecard.py:49-95`
  - `nlrb_elections_agg` + `nlrb_ulp_agg` -> `nlrb_agg` are keyed by `p.matched_employer_id` (own history), no geographic radius CTE.

- Current “union proximity” implementation is corporate-family/group based, not geographic:
  - `scripts/scoring/build_unified_scorecard.py:110-119, 264-269`
  - ```sql
    union_prox AS (
      SELECT e.employer_id, e.canonical_group_id, g.member_count ...
      FROM f7_employers_deduped e
      LEFT JOIN employer_canonical_groups g ON g.group_id = e.canonical_group_id
    )
    ...
    CASE
      WHEN up.member_count IS NULL AND eds.corporate_family_id IS NULL THEN NULL
      WHEN GREATEST(COALESCE(up.member_count, 1)-1,0) >= 2 THEN 10
      WHEN ... THEN 5
      ELSE 0
    END AS score_union_proximity
    ```

- Location data availability (artifact):
  - `docs/audit_artifacts_round3/r2_investigation1_location_data.json`
  - `f7_employers_deduped`: `146,863` total, `122,351` with lat+lon (`83.31%`), city/state `97.25%`, zip `97.14%`.
  - `nlrb_elections`: no location columns (13 columns total; election metadata only).
  - `nlrb_participants`: location-like fields available (`address`, `city`, `state`, `zip`), but no lat/lon.
  - Employer-participant completeness (`participant_type='Employer'`): `114,980` rows, city+state present `48,930` (~42.6%), city+state+zip `48,876` (~42.5%).
  - Geocoding is embedded in F7 tables (`latitude`, `longitude`, `geocode_status`), not a dedicated geocode mapping table.
  - Geocode status distribution in `f7_employers_deduped`: `geocoded` 108,377; `CENSUS_MATCH` 8,940; `ZIP_CENTROID` 5,034; `failed` 20,594; `NULL` 3,918.

- Geocoding scripts update F7 directly:
  - `scripts/etl/geocode_batch_prep.py:104-106` selects non-geocoded F7 rows.
  - `scripts/etl/geocode_batch_run.py:165-170,266-272` updates `f7_employers_deduped.latitude/longitude/geocode_status`.

### The Deliverable
Implementation blueprint (no code changes):

1. Add two new CTEs after `nlrb_ulp_agg` and before `nlrb_agg`:
- `f7_geo AS (...)` from `f7_employers_deduped` with `employer_id, latitude, longitude, naics2` where coordinates present.
- `nlrb_event_geo AS (...)` from `nlrb_participants p JOIN nlrb_elections e` (Employer participants only), mapping event location by:
  - primary: matched employer coordinates via `f7_employers_deduped` (`p.matched_employer_id`)
  - fallback: participant city/state/zip matched to nearest/state-local F7 centroid (if available)
  - include `event_date`, `union_won`, `case_number`, and derived `event_naics2` where possible.

2. Add `nlrb_nearby_agg AS (...)` CTE:
- Join each target employer (`f7_geo tgt`) to nearby event employers (`nlrb_event_geo evt`) with distance <= 25 miles.
- Distance: Haversine SQL formula (no existing PostGIS usage found in repo).
- Similar industry filter: `LEFT(tgt.naics,2) = LEFT(evt.event_naics2,2)` when both available.
- Compute nearby election momentum with 7-year half-life:
  - `nearby_raw = SUM((win*2 + 1 - loss) * decay7(event_date))` across distinct nearby events.
  - Normalize/cap to 0-10 (same style as existing factor clamps).

3. Refactor NLRB factor to explicit split:
- Keep existing own-history score as `score_nlrb_own` (current `nlrb_agg` logic).
- New nearby score `score_nlrb_nearby` from `nlrb_nearby_agg`.
- Final: `score_nlrb = clamp(0.70 * score_nlrb_nearby + 0.30 * score_nlrb_own, 0, 10)`.
- This remains a single factor with existing 3x weight in weighted average.

4. Missing geocode fallback policy:
- If target employer lacks lat/lon: use own-history-only (`score_nlrb = score_nlrb_own`) and flag `nlrb_nearby_available=false`.
- If event location missing: exclude from nearby calc.
- Add columns to MV for transparency: `nlrb_nearby_count`, `nlrb_nearby_score`, `nlrb_own_score`, `nlrb_nearby_available`.

5. Relationship to `score_union_proximity`:
- Keep both concepts but rename for clarity:
  - current `score_union_proximity` -> corporate/network proximity concept.
  - new nearby election momentum stays inside `score_nlrb` per spec 70/30 split.
- Do not replace corporate factor with geo factor unless roadmap explicitly changes factor taxonomy.

Pseudocode CTE sketch:
```sql
..., nlrb_ulp_agg AS (...),
f7_geo AS (...),
nlrb_event_geo AS (...),
nlrb_nearby_agg AS (...),
nlrb_agg AS (...),
raw_scores AS (
  SELECT ...,
         score_nlrb_own,
         score_nlrb_nearby,
         LEAST(10, GREATEST(0, 0.70*score_nlrb_nearby + 0.30*score_nlrb_own)) AS score_nlrb,
         ...
)
```

### Caveats
- I did not benchmark query cost for Haversine joins at full scale.
- I did not validate whether PostGIS extension is available in this DB (no usage found in codebase).

---

## Investigation 2
### The Question
Where exactly does the frontend explain scoring, and where does that explanation drift from actual backend behavior?

### The Evidence

- Full extracted string inventory artifacts:
  - `docs/audit_artifacts_round3/r2_frontend_scoring_strings_raw.csv`
  - `docs/audit_artifacts_round3/r2_frontend_scoring_strings_user_visible.csv`

- Core scoring explanation text locations:
  - `frontend/src/features/employer-profile/EmployerProfilePage.jsx:157-174` (long-form organizer help text)
  - `frontend/src/features/employer-profile/ScorecardSection.jsx:5-13,95` (factor labels + weights + coverage)
  - `frontend/src/features/employer-profile/ProfileHeader.jsx:33-34,98` (weighted score display)

- Backend behavior references for drift checks:
  - similarity weight disabled in scoring math: `scripts/scoring/build_unified_scorecard.py:418,442`
  - financial weight is 2x in weighted formula: `scripts/scoring/build_unified_scorecard.py:417,441,453`
  - NLRB nearby 25-mile logic TODO: `scripts/scoring/build_unified_scorecard.py:207`
  - contracts currently federal-obligations logic: `scripts/scoring/build_unified_scorecard.py:252-262`

Drift table (user-visible scoring text):

| File:Line | What frontend says | What code does | Match? |
|---|---|---|---|
| EmployerProfilePage.jsx:170 | NLRB includes nearby 25-mile similar-industry momentum | TODO not implemented; current model is own-history + ULP | No |
| EmployerProfilePage.jsx:171 | Gov contracts: federal+state+city, multiple levels | current score_contracts is federal-contractor/obligations tiers | No |
| EmployerProfilePage.jsx:166 | Factors weighted, 3x vs 1x text (generic) | true generally, but similarity is excluded and financial is 2x | Partial |
| ScorecardSection.jsx:13 | `Financial` shown as `1x` | scoring formula uses financial at 2x | No |
| ScorecardSection.jsx:10,30 | Peer Similarity under development/disabled | similarity score exists but weighted as 0; effectively disabled in final score | Mostly yes |
| EmployerProfilePage.jsx:157 | Up to 8 factors, missing factors skipped | aligns with factors_available/weight denominator logic | Yes |

### The Deliverable
- Complete extracted list: `docs/audit_artifacts_round3/r2_frontend_scoring_strings_user_visible.csv`
- Correction list (organizer-facing replacements):
  - Replace NLRB text with: "NLRB Activity combines this employer's own election history and ULP activity. Nearby-election momentum is planned but not active yet."
  - Replace contracts text with: "Gov Contracts currently uses federal contract data. State and city contract scoring is planned."
  - Replace financial weight display in ScorecardSection from `1x` to `2x`.
  - Replace generic weighting help sentence with: "Most factors are weighted (3x/2x/1x). Peer Similarity is shown for context but currently not counted in the final score."

### Caveats
- I did not manually classify all 128 extracted user-visible lines one-by-one in prose; the full inventory is provided in CSV artifact.

---

## Investigation 3
### The Question
Among 49 dynamic SQL routes, which are truly dangerous vs. merely using constrained dynamic fragments?

### The Evidence

- Full inventories:
  - `docs/audit_artifacts_round3/r2_dynamic_sql_risk_inventory.csv`
  - `docs/audit_artifacts_round3/r2_dynamic_sql_risk_inventory.md`
  - `docs/audit_artifacts_round3/r2_dynamic_sql_fstring_snippets.csv`

- Counts:
  - 49 routes with f-string `cur.execute(...)`.
  - Initial rule-based classification: High 42, Medium 4, Low 3, Critical 0.

- Constrained/whitelisted examples:
  - `api/routers/sectors.py:105` uses regex pattern for `sort_by` and maps `view_name` from `SECTOR_VIEWS` keys.
  - `api/routers/museums.py:19` constrains `sort_by` via query regex.
  - `api/routers/employers.py:333-339` unified search rejects unknown query params.

### The Deliverable
Classified inventory delivered in `r2_dynamic_sql_risk_inventory.csv` with per-route:
- method/path
- auth level
- SQL read/write mode
- input profile
- risk bucket

Prioritized fix list for High/Critical classes:

1. **Tier 1 (highest practical risk): dynamic table/view or ORDER BY identifiers in f-string**
- Routes: `/api/sectors/{sector}/targets*`, `/api/museums/targets`
- Risk: identifier injection if whitelist/regex logic regresses.
- Minimal fix: keep strict allowlists, add defensive map-based ORDER BY (no direct interpolation), add regression tests.
- Effort: S-M per router.

2. **Tier 2: dynamic `WHERE {where_clause}` assembly on public endpoints**
- Many routes use pre-built condition fragments + bound params.
- Risk: currently low-to-moderate because user values are parameterized; future unsafe fragment additions could introduce injection.
- Minimal fix: enforce helper builder that only appends predefined fragments; static test to ban direct user string insertion into fragments.
- Effort: M (shared helper + route touchups).

3. **Tier 3: admin dynamic SQL routes (already auth-gated)**
- `/api/admin/match-quality`, `/api/admin/match-review`
- Risk low due `require_admin` but still worth refactor to parameterized/static SQL style.
- Effort: S.

### Caveats
- I did not execute live penetration payloads against all 49 endpoints in this round.
- Risk classification uses code-path analysis and route signatures, not runtime WAF/network context.

---

## Investigation 4
### The Question
What is the definitive safe pipeline run order, dependencies, race conditions, and minimal downstream work for partial reruns?

### The Evidence

- Script inventory artifact:
  - `docs/audit_artifacts_round3/r2_pipeline_script_inventory.csv` (93 scripts across etl/matching/scoring/maintenance/ml)

- Key destructive/rebuild operations:
  - `scripts/matching/build_employer_groups.py:422-424` updates F7 rows, deletes all groups, resets sequence.
  - `scripts/scoring/compute_gower_similarity.py:540-541` truncates `employer_comparables`.
  - `scripts/scoring/build_employer_data_sources.py:198` drops MV then recreates.
  - `scripts/scoring/build_unified_scorecard.py:585` drops MV then recreates.
  - `scripts/matching/run_deterministic.py:233-236` supersedes active matches by source.

- Documented order in project state (with corrected paths):
  - `Start each AI/PROJECT_STATE.md:527-537`
  - Corrected script paths:
    - `scripts/scoring/compute_nlrb_patterns.py` (not `scripts/analytics/...`)
    - `scripts/ml/train_propensity_model.py` (not `scripts/modeling/...`)

### The Deliverable
Definitive dependency graph (safe order):

```text
ETL source loaders (parallel by source where safe)
  -> run_deterministic.py (all or source-specific)
  -> splink_pipeline.py (optional fuzzy pass)
  -> build_employer_groups.py  [DESTRUCTIVE rebuild]
  -> build_employer_data_sources.py --refresh/create
  -> build_unified_scorecard.py --refresh/create
  -> compute_nlrb_patterns.py
  -> create_scorecard_mv.py --refresh/create
  -> compute_gower_similarity.py --refresh-view (or rebuild)
  -> train_propensity_model.py --score-only (or retrain)
  -> create_data_freshness.py --refresh
```

Race-condition pairs to avoid:
1. `build_employer_groups.py` + any API/read that depends on canonical groups.
2. `compute_gower_similarity.py` + `build_unified_scorecard.py` (truncated comparables during score build).
3. `build_employer_data_sources.py` (DROP+CREATE mode) + `build_unified_scorecard.py`.
4. `run_deterministic.py` + score rebuild scripts (partial-match snapshots).

Minimum downstream after single-source rematch (e.g., OSHA only):
1. `run_deterministic.py osha ...`
2. `build_employer_groups.py`
3. `build_employer_data_sources.py --refresh`
4. `build_unified_scorecard.py --refresh`
5. `create_scorecard_mv.py --refresh`
6. `create_data_freshness.py --refresh`

Optional after OSHA-only rerun:
- `compute_gower_similarity.py` (not required for OSHA factor changes)
- `train_propensity_model.py` (not required unless model/feature refresh desired)

### Caveats
- I did not execute timed end-to-end pipeline runs in this round to produce measured runtime SLAs.

---

## Investigation 5
### The Question
What is required to make the current Docker/deployment setup production-ready, including React serving and env configuration?

### The Evidence

- `Dockerfile` complete content: `Dockerfile:1-18`
- `docker-compose.yml` complete content: `docker-compose.yml:1-60`
- `nginx.conf` complete content: `nginx.conf:1-19`
- `.dockerignore`: missing
- React build command: `frontend/package.json` scripts include `build: vite build`
- Build output present at `frontend/dist` (exists), no `frontend/build`.
- Current nginx serves legacy files mount (`./files`) with `index organizer_v5.html index.html` (`nginx.conf:6`, `docker-compose.yml:50`).

- Env variable inventory artifact:
  - `docs/audit_artifacts_round3/r2_env_var_inventory.json` (21 vars)

- Frontend env usage:
  - `frontend/src/shared/stores/authStore.js:4` uses `import.meta.env.VITE_DISABLE_AUTH`.

### The Deliverable
1. Complete file contents (as requested) captured above.
2. React serving gap:
- Current compose mounts `./files`, not `frontend/dist`.
- To serve React app, nginx should mount built assets directory (or use multi-stage frontend build image) and default `index index.html`.
3. `.env.example` updated with full required variables and safe defaults:
- `./.env.example` now includes DB/auth/CORS/rate-limit/matching/research/SEC vars.
4. Production checklist:

1. [ ] Provision Postgres and secure credentials.
2. [ ] Populate `.env` from `.env.example`; set strong `LABOR_JWT_SECRET`; set `DISABLE_AUTH=false`.
3. [ ] Build frontend (`npm run build` in `frontend/`) and serve `frontend/dist` via nginx.
4. [ ] Update nginx config to use `index.html` and SPA fallback.
5. [ ] Configure CORS (`ALLOWED_ORIGINS`) to deployed domains.
6. [ ] Run ETL + matching + scoring pipeline in canonical order.
7. [ ] Refresh materialized views (`mv_employer_data_sources`, `mv_unified_scorecard`, `mv_organizing_scorecard`).
8. [ ] Run freshness refresh script.
9. [ ] Verify health endpoints (`/api/health`, `/api/stats`, `/api/system/data-freshness`).
10. [ ] Validate auth flow (login, admin route access controls).
11. [ ] Add `.dockerignore` and multi-stage images for deterministic builds.
12. [ ] Add backup/restore plan for database volume and migration/runbook docs.

### Caveats
- I did not build and run the full compose stack in this round.
- I did not write migrations/bootstrap SQL for empty-database full platform reconstruction.

---

## Investigation 6
### The Question
Which DB objects/files are safe to delete now vs. archive/verify first?

### The Evidence

- Prior scan: `docs/audit_artifacts_round3/db_object_reference_scan_2026-02-26.json`
- Dependency + row-count verification:
  - `docs/audit_artifacts_round3/r2_db_zero_ref_dependency_check.json`
  - 151 zero-ref objects validated; 1 zero-ref table with 0 rows; 59 zero-ref tables with data; 91 zero-ref views.

- Frontend unused file scan:
  - `docs/audit_artifacts_round3/r2_frontend_unimported_files.json`
  - Candidate: `frontend/src/components/ui/separator.jsx`

- Route reference scan artifact:
  - `docs/audit_artifacts_round3/r2_frontend_route_reference_scan.json`

### The Deliverable

List A — Safe to delete immediately (no dependencies found):

| Type | Name | Size | Reason |
|---|---|---:|---|
| table | `cba_wage_schedules` | 0 rows | zero code refs, zero API/test refs, no dependent views |
| view | `all_employers_unified` | n/a | zero code refs, no dependent views/MVs |
| view | `bls_industry_union_density` | n/a | zero code refs, no dependent views/MVs |
| view | `flra_olms_crosswalk` | n/a | zero code refs, no dependent views/MVs |
| view | `union_sector_coverage` | n/a | zero code refs, no dependent views/MVs |
| view | `v_990_by_state` | n/a | zero code refs, no dependent views/MVs |
| view | `v_all_organizing_events` | n/a | zero code refs, no dependent views/MVs |
| frontend file | `frontend/src/components/ui/separator.jsx` | 1 file | unimported in current frontend source tree |

List B — Probably safe but verify first:

| Type | Name | Size | What to check |
|---|---|---:|---|
| table | `nlrb_docket` | 2,046,151 rows | external analyst workflows / ad-hoc notebooks |
| table | `epi_union_membership` | 1,420,064 rows | historical reporting pipelines |
| table | `employers_990_deduped` | 1,046,167 rows | offline enrichment scripts not in active API |
| table | `ar_disbursements_emp_off` | 2,813,248 rows | legacy OLMS analytics consumers |
| table | `union_naics_mapping` | 7,624 rows | old sector analyses / notebooks |
| table | `employer_990_matches` | 514 rows | historical matching QA workflows |

List C — Keep but archive (data retained, no active use in API/frontend):

| Type | Name | Size | Reason to keep |
|---|---|---:|---|
| table | `nlrb_election_results` | 33,096 rows | historical reproducibility |
| table | `nlrb_voting_units` | 31,643 rows | election detail lineage |
| table | `labor_orgs_990` | 19,367 rows | audit/backfill reproducibility |
| table | `labor_orgs_990_deduped` | 15,172 rows | lineage of dedup experiments |
| table | `crosswalk_unions_master` | 50,039 rows | bridge lineage for earlier union mapping |
| scripts | `scripts/analysis/analyze_schedule13_cp2.py`, `...cp3.py`, `multi_employer_fix_v2.py`, `sector_analysis_1.py`, `sector_analysis_2.py`, `sector_analysis_3.py`, `analyze_deduplication_v2.py`, `analyze_geocoding2.py` | n/a | versioned analysis artifacts likely superseded by newer scripts/docs |

### Caveats
- I did not run business-owner interviews to confirm no external BI dashboards depend on these zero-ref objects.
- `PIPELINE_MANIFEST.md` was not found in the repository during this round, so I could not cross-check script usage there.

---

## Tier 0-1 Roadmap Impact Summary
These findings reinforce the Tier 0-1 priorities from the synthesis:

1. **Tier 0 scoring trust:** Implement NLRB nearby 25-mile or remove claims; fix frontend scoring text drift immediately.
2. **Tier 0 security posture:** Keep `DISABLE_AUTH=false` for deployable environments; complete dynamic SQL hardening backlog.
3. **Tier 1 pipeline reliability:** enforce serialized run-order for destructive rebuild stages; publish operator runbook from Investigation 4 graph.
4. **Tier 1 deployability:** update Docker/nginx to serve React build output, ship complete `.env.example`, add `.dockerignore` and deployment checklist to docs.
5. **Tier 1 maintainability:** begin staged cleanup/archival of verified zero-ref DB/views/scripts to reduce cognitive and operational debt.
