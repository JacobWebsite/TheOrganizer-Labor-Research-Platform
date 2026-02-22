# PROJECT DIRECTORY

> **Labor Relations Research Platform — Complete File & System Reference**
> Last updated: 2026-02-21

> **Document Purpose:** File catalog and database inventory — what exists and where. For technical details, see `CLAUDE.md`. For project status, see `PROJECT_STATE.md`. For the plan, see `UNIFIED_ROADMAP_2026_02_19.md`. For redesign decisions (scoring, React, UX), see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.

This document catalogs every file, directory, database object, and pipeline step in the labor-data-project. It is the master reference for understanding what exists, where it lives, and what it does.

---

## Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. Critical Files (Must-Know)](#2-critical-files-must-know)
- [3. Root-Level Files](#3-root-level-files)
- [4. API (api/)](#4-api-api)
- [5. Scripts -- ETL Pipeline (scripts/etl/)](#5-scripts----etl-pipeline-scriptsetl)
- [6. Scripts -- Matching Pipeline (scripts/matching/)](#6-scripts----matching-pipeline-scriptsmatching)
- [7. Scripts -- Scoring (scripts/scoring/)](#7-scripts----scoring-scriptsscoring)
- [8. Scripts -- ML (scripts/ml/)](#8-scripts----ml-scriptsml)
- [9. Scripts -- Web Scraping (scripts/scraper/)](#9-scripts----web-scraping-scriptsscraper)
- [10. Scripts -- Maintenance (scripts/maintenance/)](#10-scripts----maintenance-scriptsmaintenance)
- [11. Scripts -- Analysis (scripts/analysis/)](#11-scripts----analysis-scriptsanalysis)
- [12. Scripts -- Setup & Performance](#12-scripts----setup--performance)
- [13. Shared Libraries (src/)](#13-shared-libraries-src)
- [14. Frontend (files/)](#14-frontend-files)
- [15. Tests (tests/)](#15-tests-tests)
- [16. SQL Files (sql/)](#16-sql-files-sql)
- [17. Documentation (docs/)](#17-documentation-docs)
- [18. Data Directory (data/)](#18-data-directory-data)
- [19. CorpWatch Data (corpwatch_api_tables_csv/)](#19-corpwatch-data-corpwatch_api_tables_csv)
- [20. Checkpoints & Logs](#20-checkpoints--logs)
- [21. Configuration & Deployment](#21-configuration--deployment)
- [22. Archive (archive/)](#22-archive-archive)
- [23. Database Inventory](#23-database-inventory)
- [24. Pipeline Run Order (Quick Reference)](#24-pipeline-run-order-quick-reference)

---

## 1. Project Overview

The Labor Relations Research Platform is a data integration and analysis system that aggregates 15+ federal data sources to build a comprehensive picture of private-sector labor organizing in the United States. It matches employers across OSHA, WHD, NLRB, SEC, SAM.gov, IRS 990, GLEIF, and other sources to OLMS Form LM/F-7 union filings, producing multi-factor organizing scores and actionable employer profiles.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Database** | PostgreSQL 17 (`olms_multiyear`, localhost, user `postgres`) |
| **API** | FastAPI on Python 3.14, served by Uvicorn on port 8001 |
| **Frontend** | Vanilla JS SPA (`organizer_v5.html`) with Tailwind CSS, Chart.js, Leaflet |
| **Matching** | 6-tier deterministic cascade + Splink probabilistic + trigram fallback |
| **ML** | scikit-learn (propensity models), Gower distance (employer similarity) |
| **Deployment** | Docker Compose (postgres + API + nginx) |

### Key Metrics

| Metric | Value |
|--------|-------|
| F7 employers (deduped) | 146,863 |
| Unified match log rows | 1,738,115 |
| Active matches | OSHA 97K, SAM 29K, 990 20K, WHD 19K, NLRB 13K, SEC 5K, GLEIF 2K, Mergent 1K |
| Database size | 20 GB |
| Tables / Views / MVs | 174 / 123 / 6 |
| Active scripts | 120+ |
| API routers | 20 |
| Frontend JS modules | 19 |
| Tests | 456 passing / 1 failing |
| Total project size | ~18 GB (16 GB in archive/) |

### Quick Start

```bash
# Start the API
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.main:app --reload --port 8001

# Run tests
py -m pytest tests/ -x -q

# Open the frontend
# Navigate to http://localhost:8001 in your browser
```

---

## 2. Critical Files (Must-Know)

These are the files you need to understand before working on anything in this project.

### `db_config.py` (root)

Shared database connection module imported by 500+ scripts. Reads credentials from `.env` (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) and exports `get_connection()` for pooled RealDictCursor connections and `get_raw_connection()` for bare psycopg2. **Must remain at project root** -- moving it breaks all imports. All rows returned as dicts (`row['column_name']`), not tuples.

### `.env` (root)

Environment configuration with database credentials and JWT secret (`LABOR_JWT_SECRET`). Never committed to git. Copy `.env.example` to create it. Also supports: `DISABLE_AUTH`, `ALLOWED_ORIGINS`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`, `MATCH_MIN_NAME_SIM`.

### `PROJECT_STATE.md` (root, 39 KB)

Shared context document updated by all AI tools (Claude Code, Codex, Gemini). Contains: current status, database inventory, phase completion markers, known issues ranked by severity, recent decisions with rationale, and session history. Single source of truth for what has been done and what remains.

### `PIPELINE_MANIFEST.md` (root, 15 KB)

Exhaustive inventory of all 120 active scripts organized by execution stage (ETL, Matching, Scoring, ML, Maintenance). Each script has: purpose, dependencies, data sources, run conditions, and usage. If a script is not listed here, it is archived and inactive.

### `UNIFIED_ROADMAP_2026_02_19.md` (root, 44 KB)

Single source of truth for project planning. Four parts: (1) Where Things Stand (inventory), (2) What's Wrong (ranked problems), (3) What to Do Next (6-phase plan A-F), (4) What Comes Later (post-launch features). Replaces all prior roadmap versions.

### `UNIFIED_PLATFORM_REDESIGN_SPEC.md` (root, 44 KB)

Platform redesign specification — the authoritative document for all redesign decisions. Covers: 8-factor weighted scoring system (Union Proximity/Size/NLRB at 3x, Gov Contracts/Growth/Similarity at 2x, OSHA/WHD at 1x), percentile-based tier labels (Priority/Strong/Promising/Moderate/Low), React + Vite frontend migration plan (shadcn/ui, Zustand, TanStack Query), visual design (Bloomberg meets Linear), page designs (Search, Employer Profile, Targets, Union Explorer, Admin), Deep Dive tool spec, master employer list architecture, security/auth decisions, and Claude Code task list. Supersedes scoring and frontend sections in the Roadmap.

### `CLAUDE.md` (root, 40 KB)

Comprehensive AI assistant reference. Quick start, DB schema details (26,665 unions, 146,863 employers), architecture deep-dives (scorecard, auth, matching, scoring), 20+ technical lessons (Python 3.14 warnings, Windows cp1252, Splink overweighting, psycopg2 quirks), phase completion summaries, and NY export methodology.

### `README.md` (root, 14 KB)

Main project documentation. Quick start, API reference (160+ endpoints across 20 routers), test suite overview (456 tests across 27 files), project structure, feature descriptions, 15 data sources with record counts, and key documentation links.

---

## 3. Root-Level Files

**Total: ~61 files** at the project root, organized by category below.

### Configuration (5 files)

| File | Size | Description |
|------|------|-------------|
| `.env` | 652 B | Database credentials and JWT secret. Never commit. |
| `.env.example` | 102 B | Template for required environment variables. |
| `.gitignore` | 765 B | Excludes .env, archive/, data/, large files (pdf, zip, xlsx), IDE configs. |
| `pyproject.toml` | 1.3 KB | Python project metadata. Requires Python >=3.11. Dependencies: FastAPI, psycopg2, pandas, splink, rapidfuzz, scikit-learn. Pytest config with `slow` and `integration` markers. Ruff linting rules. |
| `requirements.txt` | 344 B | Frozen pip dependencies (21 packages). Key: bcrypt 5.0.0, FastAPI 0.128.0, psycopg2-binary 2.9.11, splink 4.0.12. |

### Docker & Deployment (3 files)

| File | Size | Description |
|------|------|-------------|
| `docker-compose.yml` | 1.6 KB | Multi-container orchestration: postgres:17 (with health checks, persistent volume), Python API (port 8001), nginx:alpine frontend (port 8080, proxies /api/ to backend). |
| `Dockerfile` | 494 B | API container: python:3.12-slim, installs requirements, copies api/ and db_config.py, exposes 8001, runs uvicorn. |
| `nginx.conf` | 461 B | Frontend reverse proxy: serves organizer_v5.html at /, routes /api/* to backend:8001, enables SPA routing with try_files. |

### Core Database Module (1 file)

| File | Size | Description |
|------|------|-------------|
| `db_config.py` | 1.2 KB | Shared database connection. See [Critical Files](#2-critical-files-must-know). |

### Core Documentation (6 files)

| File | Size | Description |
|------|------|-------------|
| `README.md` | 14 KB | Main project documentation. See [Critical Files](#2-critical-files-must-know). |
| `PROJECT_STATE.md` | 39 KB | Shared AI context document. See [Critical Files](#2-critical-files-must-know). |
| `PIPELINE_MANIFEST.md` | 15 KB | Active script inventory. See [Critical Files](#2-critical-files-must-know). |
| `UNIFIED_ROADMAP_2026_02_19.md` | 44 KB | Project roadmap. See [Critical Files](#2-critical-files-must-know). |
| `UNIFIED_PLATFORM_REDESIGN_SPEC.md` | 44 KB | Platform redesign specification. See [Critical Files](#2-critical-files-must-know). |
| `CLAUDE.md` | 40 KB | AI assistant reference. See [Critical Files](#2-critical-files-must-know). |

### Diagnostic Scripts (26 check_*.py files)

These are ad-hoc diagnostic scripts used during development. Most are small (300-1,700 bytes) and query the database for validation. Not part of the active pipeline.

| File | Purpose |
|------|---------|
| `check_all_tables.py` | Query all tables for basic integrity check |
| `check_counts.py` | Verify record counts in key tables |
| `check_log_unique.py` | Audit unified_match_log uniqueness constraints |
| `check_master_schema.py` | Query information_schema for table/view inventory |
| `check_matches.py` | Verify match table consistency |
| `check_match_rates.py` | Compute source-to-F7 match coverage percentages |
| `check_missing_unions.py` | Identify unmapped NLRB participants |
| `check_missing_unions_v2.py` | Alternative union matching validation |
| `check_missing_unions_v3.py` | Third iteration of union validation |
| `check_mv_cols.py` | Verify materialized view column structure |
| `check_old_f7.py` | Query legacy F7 table for comparison |
| `check_old_score_schema.py` | Audit old scorecard schema |
| `check_orphans.py` | Find F7 employers with no matches |
| `check_orphans_v2.py` | Alternative orphan detection |
| `check_orphans_v3.py` | Third orphan validation method |
| `check_osha.py` | OSHA match table validation |
| `check_osha_log.py` | OSHA unified_match_log audit |
| `check_relkind.py` | Query pg_class for relation types |
| `check_rel_schema.py` | Relation schema attribute check |
| `check_schema.py` | Basic schema information query |
| `check_schemas.py` | Enumerate all database schemas |
| `check_scores.py` | Score computation validation |
| `check_sizes.py` | Table size analysis |
| `check_starbucks.py` | Single-employer test case (Starbucks) |
| `check_types.py` | Column type verification |
| `check_whd_fix.py` | WHD match validation |
| `check_whd_score.py` | WHD score computation check |
| `compare_scorecards.py` | Compare scorecard versions |
| `compare_scores_detailed.py` | Detailed score comparison |

### Application Scripts (4 files)

| File | Size | Description |
|------|------|-------------|
| `export_ny_deduped.py` | 25 KB | NY employer CSV export v2. Canonical group collapse (3,642 to 1,641 rows), multi-employer regex detection (78 flagged), fuzzy dedup (10K+), public sector at top. Output: `ny_employers_deduped.csv` (15,509 rows). |
| `export_ny_employers.py` | 6.9 KB | Original NY employer CSV export. Queries F7 employers in NY with union data. Output: `ny_employers_unions.csv` (18,482 rows). |
| `run_remaining_reruns.py` | 4.3 KB | Phase B4 re-run orchestrator. Sequential source re-execution with checkpoint tracking. Flags: `--skip-990`, `--skip-to-sam`, `--refresh-only`. Handles OSHA/SEC/990/WHD/SAM one at a time to avoid OOM. |
| `start-claude.bat` | 193 B | Windows batch file to start API: `py -m uvicorn api.main:app --reload --port 8001`. |

### Data Exports (3 CSV files)

| File | Size | Rows | Description |
|------|------|------|-------------|
| `ny_employers_deduped.csv` | 3.0 MB | 15,509 | NY employers deduplicated -- primary export for organizing use |
| `ny_employers_deduped_v2.csv` | 3.0 MB | 15,509 | Alternative version of deduplicated NY export |
| `ny_employers_unions.csv` | 2.8 MB | 18,482 | NY employers with union relationships (before deduplication) |

### Documentation & Research Reports (10 files)

| File | Size | Description |
|------|------|-------------|
| `AUDIT_CLAUDE_CODE_2026-02-18.md` | 41 KB | Code audit: 530 scripts to 120, reorganization, Phase A fixes |
| `AUDIT_REPORT_GEMINI_2026-02-18.md` | 7.2 KB | Independent verification by Gemini |
| `INDEPENDENT_AI_AUDIT_PROMPT_2026-02-18.md` | 15 KB | Detailed audit request prompt for independent AI review |
| `GEMINI_RESEARCH_HANDOFF.md` | 20 KB | Research synthesis and methodology from Gemini |
| `Future_Projects_Post_Launch_Goals.md` | 35 KB | Post-launch feature roadmap and strategic vision |
| `Workforce Size Estimation Research Report.txt` | 32 KB | Research on workforce sizing methodologies |
| `workforce_estimation_model_plan.md` | 32 KB | Plan for implementing workforce estimation models |
| `deep-research-report.md` | 50 KB | Comprehensive research synthesis |
| `claude_code_folder_reorg_prompt.md` | 11 KB | Prompt document for folder reorganization task |
| `compass_artifact_wf-cfb3bf88...md` | 20 KB | Artifact from Compass research |

### Miscellaneous (5 files)

| File | Description |
|------|-------------|
| `gemini-Analytical Frameworks...md` | Gemini research on workforce composition frameworks |
| `labor data roadmap.pdf` | PDF roadmap document from January 2026 planning |
| `union-research.skill` | Skill definition file for Claude Code extended functionality |
| `codex_test_output.txt` | Test output stub (16 bytes) |
| `NUL` | Placeholder from Windows redirection mishap (128 bytes) |

---

## 4. API (api/)

### Architecture

The API is a FastAPI application serving 160+ endpoints across 20 routers, with JWT authentication, rate limiting, structured logging, and CORS middleware. It serves the frontend SPA at `/` and all data endpoints under `/api/`.

**Run command:** `py -m uvicorn api.main:app --reload --port 8001`

### Core Files

| File | Description |
|------|-------------|
| `api/main.py` | App entry point. Includes all 20 routers, configures middleware stack (CORS, Auth, RateLimit, Logging), serves frontend at `/`, handles psycopg2 errors as 503. Auth startup guard: requires `LABOR_JWT_SECRET` (32+ chars) or `DISABLE_AUTH=true`, exits with code 1 otherwise. |
| `api/config.py` | Configuration management. `PROJECT_ROOT`, `FILES_DIR`, JWT settings (HS256, 8hr expiry), CORS origins (configurable via `ALLOWED_ORIGINS`), rate limit defaults (100 req/60s). |
| `api/database.py` | Connection pool. `ThreadedConnectionPool` (min 2, max 20) with `RealDictCursor`. `get_db()` context manager (auto-commit/rollback). `get_raw_connection()` for bare psycopg2 (autocommit ops). |
| `api/dependencies.py` | FastAPI dependency injection. `require_auth(request)` returns `{username, role}` (synthetic dev user when auth disabled). `require_admin(request)` checks role == "admin", returns 403 otherwise. |
| `api/helpers.py` | Shared utilities. `safe_sort_col()` / `safe_order_dir()` for SQL injection prevention. `is_likely_law_firm(name)` regex patterns for NLRB data quality. `SECTOR_VIEWS` dict mapping 21 sector categories. |
| `api/models/schemas.py` | Pydantic models. `FlagCreate` for data quality flags (source_type, source_id, flag_type, notes). |

### Middleware

| File | Description |
|------|-------------|
| `api/middleware/auth.py` | JWT authentication. Public paths: `/`, `/api/health`, `/api/auth/login`, `/api/auth/register`, `/docs`, `/files/*`. Validates `Authorization: Bearer <token>`, sets `request.state.user` / `.state.role`. No-op when JWT_SECRET is empty. Includes `generate_token()` CLI utility. |
| `api/middleware/logging.py` | Structured request logging: `{method} {path} status={code} duration={ms}ms client={ip}`. 5xx = error, 4xx or slow (>3s) = warning, else info. Uses X-Forwarded-For for client IP behind proxy. |
| `api/middleware/rate_limit.py` | IP-based sliding window rate limiting. Default 100 req/60s. Returns 429 with `Retry-After` header when exceeded. Disable by setting `RATE_LIMIT_REQUESTS` to 0 or negative. |

### Routers (20 total)

| # | Router | Prefix | Key Endpoints | Description |
|---|--------|--------|---------------|-------------|
| 1 | `auth.py` | `/api/auth/` | login, register, refresh, /me | JWT authentication. Bcrypt hashing. Advisory lock for first-user bootstrap. 10 login attempts per 5 min rate limit. |
| 2 | `health.py` | `/api/` | /health, /stats, /system/data-freshness | Health checks, platform stats summary, data source freshness with 90-day stale flag. |
| 3 | `system.py` | `/api/` | /summary, /stats/breakdown, /health/details | Overall platform summary, breakdowns by state/NAICS/CBSA/name, detailed diagnostics. |
| 4 | `lookups.py` | `/api/lookups/` | /sectors, /affiliations, /states, /naics-sectors, /metros | Reference data for UI filter dropdowns. Sectors, affiliations (min 3 members), states, NAICS with density, metros. |
| 5 | `density.py` | `/api/density/` | /naics/{code}, /all, /by-state | BLS union density data. NAICS sector density + 15-year trend. State-level private/public/total density. |
| 6 | `projections.py` | `/api/projections/` | /summary, /industry/{naics}, /occupations/{naics} | BLS employment projections 2024-2034. Growth categories, top occupations by industry. |
| 7 | `employers.py` | `/api/employers/` | /cities, /search (DEPRECATED), /fuzzy-search, detail/flags | Employer search and detail. Pagination (50-500). Public sector support. NAICS gradient enrichment. |
| 8 | `scorecard.py` | `/api/scorecard/` | /, /states, /versions, /unified, /unified/stats, /unified/states, /unified/{id} | Legacy scorecard + Phase E3 unified 7-factor signal-strength scoring (0-10 each, avg unified_score). Tiers: TOP >=7, HIGH >=5, MEDIUM >=3.5, LOW <3.5. |
| 9 | `unions.py` | `/api/unions/` | /cities, /search, /{fnum} detail | Union search with filters (name, affiliation, sector, state, city, type, min_members). Membership trend analysis (growing/declining/stable). 10-year history. |
| 10 | `nlrb.py` | `/api/nlrb/` | /summary, /elections/search, /elections/{case}, /ulp/search | NLRB elections summary (wins/losses/win rate). Election search by state/affiliation/employer/outcome/year/voters. Law firm detection for data quality. |
| 11 | `osha.py` | `/api/osha/` | /summary, /establishments/search, /establishments/{id} | OSHA establishments/violations. Union status (Y/N/A/B). Risk levels. Violation severity (willful, repeat, serious). F7 match confidence. |
| 12 | `organizing.py` | `/api/organizing/` | /scorecard, /scorecard/{id}, /match-review (admin) | Organizing targeting scorecard. Multi-factor scoring with temporal decay (OSHA 10yr, NLRB 7yr). RTW adjustments. Score explanations. Admin match review. |
| 13 | `whd.py` | `/api/whd/` | /summary, /search, /cases/{id} | Wage & Hour Division enforcement. Cases, backwages, civil penalties. Repeat violator tracking. |
| 14 | `trends.py` | `/api/trends/` | /national, /affiliations/summary, /sectors/summary | National membership trends 2010-2024 with deduplication ratio (~0.20). Affiliation and sector trend comparisons. |
| 15 | `corporate.py` | `/api/multi-employer/` | /stats, /groups, /employer/{id}/agreement | Multi-employer agreement stats and groups. Deduplication exclusion tracking. Primary employer designation per group. |
| 16 | `vr.py` | `/api/vr/` | /stats/summary, /by-year, /by-state, /by-affiliation, /map | Voluntary recognition tracking. Geospatial support (lat/lng for mapping). Filters: state, affiliation, year. |
| 17 | `public_sector.py` | `/api/public-sector/` | /stats, /parent-unions, /locals, /employers | Public sector union data. Parent-local hierarchy. Bargaining unit tracking. Separate `ps_` prefix tables. |
| 18 | `museums.py` | `/api/museums/` | /targets, /targets/stats | Museum organizing targets. Sector-specific scoring (mergent_employers). Priority tiers. OSHA + contract data. |
| 19 | `sectors.py` | `/api/sectors/` | /list, /{sector}/summary, /{sector}/targets | 21 sector categories from mergent_employers. Unionized vs non-union targets. Density and contract aggregations. |
| 20 | `profile.py` | `/api/profile/` | /employers/{id} | Canonical employer profile. Consolidates data from 15+ tables: F7, unified scorecard, NLRB elections, ULP cases, OSHA, WHD, VR, federal contracts, financial, density/projections. Single comprehensive endpoint for frontend detail view. |

---

## 5. Scripts -- ETL Pipeline (scripts/etl/)

Data extraction, transformation, and loading scripts for all external data sources. **25 files total.**

| File | Data Source | Purpose | When to Run |
|------|-------------|---------|-------------|
| `load_osha_violations.py` | OSHA | Load 2.2M violation details from SQLite (2012+) with establishment hashing | Initial setup, periodic |
| `load_osha_violations_detail.py` | OSHA | Companion for violation detail extraction | Initial setup |
| `load_national_990.py` | IRS 990 | Load 586K nonprofits via CSV. Normalize names, dedup by EIN, match to F7/Mergent | Initial + periodic |
| `load_whd_national.py` | DOL WHD | Load 363K wage theft cases from WHISARD dataset (110 columns) | Initial + periodic |
| `load_sam.py` | SAM.gov | Parse 826K+ federal contractors from pipe-delimited zip | Initial + periodic |
| `load_sec_edgar.py` | SEC EDGAR | Extract 955K JSON files, load company metadata (CIK, name, EIN, LEI, SIC, addresses) | Initial + periodic |
| `load_gleif_bods.py` | GLEIF/Open Ownership | Restore pgdump.sql.gz (52.7M rows), extract US entities and ownership links | Initial setup only |
| `irs_bmf_loader.py` | IRS BMF | Load ~1.8M tax-exempt organizations (ProPublica API or direct download) | Initial setup |
| `download_bls_union_tables.py` | BLS | Download HTML tables from BLS news releases (Table 1, 3, 5) | Periodic (annual) |
| `parse_bls_union_tables.py` | BLS | Parse downloaded HTML, extract industry/state density data, load to DB | Periodic (annual) |
| `load_bls_projections.py` | BLS | Load industry employment growth projections | Initial setup |
| `fetch_qcew.py` | BLS QCEW | Download and load annual QCEW data (establishments by NAICS x geography x ownership) | Periodic (annual) |
| `_integrate_qcew.py` | BLS QCEW | Integration/processing helper for QCEW data | Support script |
| `sec_edgar_full_index.py` | SEC EDGAR | Fetch SEC EDGAR index files for company lookups | Support script |
| `load_onet_data.py` | O*NET | Load bulk files (Work Context, Job Zones) from data/onet/ | Initial setup |
| `calculate_occupation_similarity.py` | O*NET/BLS | Compute cosine similarity over occupation vectors (industry staffing patterns) | Phase 5 scoring |
| `compute_industry_occupation_overlap.py` | O*NET/BLS | Build industry-occupation matrix from BLS data | Phase 5 setup |
| `parse_oews_employment_matrix.py` | OEWS | Parse occupation-employment matrix | Phase 4 data |
| `create_state_industry_estimates.py` | Multiple | Create state-level industry composition estimates | Phase 4 |
| `extract_gleif_us_optimized.py` | GLEIF | Optimized extraction of US entities from GLEIF | Support script |
| `update_normalization.py` | Internal | Update name normalization tables across the database | Maintenance |
| `_fetch_usaspending_api.py` | USASpending | Fetch federal spending data (experimental, not active) | Research |
| `_match_usaspending.py` | USASpending | Match spending data to employers (experimental) | Research |
| `build_crosswalk.py` | SEC/GLEIF/Mergent/F7 | Build corporate_identifier_crosswalk via 4-tier matching (EIN, LEI, name+state, propagation) | Phase 2 |

---

## 6. Scripts -- Matching Pipeline (scripts/matching/)

The core entity matching engine. Matches external data sources to F7 employers through a 6-tier deterministic cascade with probabilistic fallbacks. **30 files total.**

### Core Engine

| File | Description |
|------|-------------|
| `run_deterministic.py` | CLI entry point. Orchestrates batch matching with checkpoint/resume. Supports `--batch N/M` for parallelization, `--rematch-all` for supersede-and-rerun. |
| `deterministic_matcher.py` | Engine core. 6-tier cascade: EIN (100) > name+city+state (90) > name+state (80) > aggressive (60) > Splink (45) > trigram (40). Best-match-wins per source record. |
| `create_unified_match_log.py` | Creates the central `unified_match_log` table (1.7M+ rows) with standardized schema for all match decisions. |
| `build_employer_groups.py` | Builds canonical employer groups (16,209 groups, 40,304 employers) from shared identifiers. |
| `create_nlrb_bridge.py` | Creates NLRB participant-to-employer match bridge. |
| `resolve_historical_employers.py` | Resolves historical employer records to current canonical groups. |

### Adapters (Source-Specific Loaders)

Each adapter loads unmatched records from one external source for the matcher to process. All use ON CONFLICT DO UPDATE to upgrade matches on re-run.

| File | Source | Record Count | Notes |
|------|--------|-------------|-------|
| `adapters/osha_adapter.py` | OSHA establishments | 1,007K | 97,142 active matches (9.6%) |
| `adapters/whd_adapter.py` | WHD cases | 363K | 19,462 active matches (5.4%) |
| `adapters/n990_adapter.py` | National 990 filers | 586K | 20,215 active matches (3.4%) |
| `adapters/sam_adapter.py` | SAM.gov entities | 826K | 28,816 active matches (3.5%). Requires batching due to OOM. |
| `adapters/sec_adapter_module.py` | SEC EDGAR companies | 517K | 5,339 active matches. Supports `--batch N/M`. |
| `adapters/bmf_adapter_module.py` | IRS BMF organizations | ~1.8M | 9 active matches (very low). |
| `adapters/__init__.py` | -- | -- | Adapter registry/imports |

### Matchers (Tier Implementations)

| File | Tier | Description |
|------|------|-------------|
| `matchers/exact.py` | 1-2 | EIN and exact name matching |
| `matchers/address.py` | 2-3 | Address-based matching with geocoding |
| `matchers/fuzzy.py` | 5b | Trigram/edit-distance fallback when Splink misses |
| `matchers/base.py` | -- | Base matcher class (framework) |

### Configuration & Models

| File | Description |
|------|-------------|
| `config.py` | `MatchConfig` dataclass with tier thresholds and scenario definitions |
| `splink_config.py` | Splink probabilistic settings, comparison rules, blocking logic, quality thresholds (AUTO >= 0.85, REVIEW >= 0.70) |
| `splink_integrate.py` | Integrate Splink results into corporate_identifier_crosswalk |
| `splink_pipeline.py` | Legacy Splink pipeline entry point |
| `train_adaptive_fuzzy_model.py` | Train BayesianOptimization fuzzy similarity model. Produces `adaptive_fuzzy_model.json`. |
| `match_quality_report.py` | Generate matching quality metrics and reports |

### Support Files

| File | Description |
|------|-------------|
| `normalizer.py` | Name normalization (standard, aggressive levels) |
| `differ.py` | Diff/comparison utilities |
| `pipeline.py` | Legacy pipeline entry point |
| `__main__.py` | Legacy CLI entry |
| `cli.py` | Command-line utilities |

### Typical Commands

```bash
# Full re-run for one source
py scripts/matching/run_deterministic.py osha --rematch-all --batch 1/4

# Run all sources
py scripts/matching/run_deterministic.py all

# Build employer groups after matching
py scripts/matching/build_employer_groups.py
```

---

## 7. Scripts -- Scoring (scripts/scoring/)

Signal-strength scoring and materialized view builders. **6 files total.**

| # | File | Pipeline Step | Purpose | Output |
|---|------|--------------|---------|--------|
| 1 | `build_employer_data_sources.py` | 4.5 | Build source coverage flags (8 boolean has_* columns + crosswalk) | `mv_employer_data_sources` (146,863 rows) |
| 2 | `build_unified_scorecard.py` | 4.6 | Build 7-factor unified scorecard (0-10 each, avg unified_score) | `mv_unified_scorecard` (146,863 rows, ~11s) |
| 3 | `create_scorecard_mv.py` | 6 | Create legacy organizing scorecard MV (9 factors, 11-56 range) | `mv_organizing_scorecard` (212,441 rows) |
| 4 | `compute_nlrb_patterns.py` | 5 | NLRB historical win-rate scoring by industry and employer size | `ref_nlrb_industry_win_rates`, `ref_nlrb_size_win_rates` |
| 5 | `compute_gower_similarity.py` | 7 | Employer similarity via Gower distance (14 features incl. occupation overlap) | `employer_comparables` (269K rows) |
| 6 | `update_whd_scores.py` | -- | Update WHD violation scores with temporal decay (7yr half-life) | WHD score columns on f7_employers_deduped |

### Run Order

```bash
# After matching re-runs:
py scripts/scoring/build_employer_data_sources.py --refresh   # Step 4.5
py scripts/scoring/build_unified_scorecard.py --refresh       # Step 4.6
py scripts/scoring/compute_nlrb_patterns.py                   # Step 5
py scripts/scoring/create_scorecard_mv.py --refresh           # Step 6
py scripts/scoring/compute_gower_similarity.py --refresh-view # Step 7
```

---

## 8. Scripts -- ML (scripts/ml/)

Machine learning models for propensity scoring. **4 files total** plus model artifacts.

| File | Purpose | Output |
|------|---------|--------|
| `train_propensity_model.py` | Train NLRB election propensity models | Model A (OSHA-matched, AUC=0.72), Model B (all employers, AUC=0.53) |
| `feature_engineering.py` | Engineer features for propensity models (temporal, cyclical, one-hot encoding) | Feature matrices |
| `create_propensity_tables.py` | Batch-score all employers using trained models | `employer_propensity_scores` table |
| `__init__.py` | Package initialization | -- |

**Model Artifacts** (in `scripts/ml/artifacts/`):
- `model_a.pkl` -- Logistic Regression / Gradient Boosting (OSHA-matched employers)
- `model_b.pkl` -- Logistic Regression / Gradient Boosting (all employers)
- `scaler.pkl` -- Feature scaler

---

## 9. Scripts -- Web Scraping (scripts/scraper/)

Web scraping pipeline for union website data. **8 scripts + 4 JSON data files.**

### Sequential Pipeline

| # | File | Purpose |
|---|------|---------|
| 1 | `fetch_union_sites.py` | Fetch raw pages from union websites (Crawl4AI), save markdown text |
| 2 | `extract_union_data.py` | Read/batch-review raw text, accept structured JSON, insert to DB |
| 3 | `fix_extraction.py` | Fix/cleanup extraction issues |
| 4 | `extract_ex21.py` | Extract Schedule 21 data from SEC filings |
| 5 | `match_web_employers.py` | Match website employer mentions to F7 employers |
| 6 | `read_profiles.py` | Read and display scraped profile data |
| 7 | `export_html.py` | Export profiles to HTML |
| 8 | `fetch_summary.py` | Generate summary statistics |

### Data Files

| File | Description |
|------|-------------|
| `manual_employers.json` | Manually curated employer data |
| `manual_employers_2.json` | Additional manual employer data |
| `ai_employers_batch1.json` | AI-extracted employer data, batch 1 |
| `ai_employers_batch2.json` | AI-extracted employer data, batch 2 |

---

## 10. Scripts -- Maintenance (scripts/maintenance/)

Database maintenance and housekeeping. **5 files total.**

| File | Purpose | Notes |
|------|---------|-------|
| `rebuild_legacy_tables.py` | Rebuild legacy match tables from unified_match_log | Transactional, rollback on error, `--dry-run`. Produces: osha_f7_matches (97K), sam_f7_matches (29K), national_990_f7_matches (20K), whd_f7_matches (19K), nlrb_f7_xref (13K). |
| `create_data_freshness.py` | Track record counts and date ranges per data source | Read-only audit. Pipeline step 9. |
| `fix_signatories_and_groups.py` | Fix signatory employer and canonical group data | Maintenance task |
| `drop_orphan_industry_views.py` | Drop unused industry-specific views | Reduced 186 to 121 views |
| `generate_db_inventory.py` | Generate database schema inventory document | Read-only |

---

## 11. Scripts -- Analysis (scripts/analysis/)

Analysis, validation, and research scripts. **52 files total**, grouped by theme. These are mostly one-off or periodic analysis scripts, not part of the core pipeline.

### Coverage Analysis (8 files)

| File | Purpose |
|------|---------|
| `analyze_coverage.py` | Private sector coverage using F7 employers + median unit sizes |
| `complete_coverage.py` | Complete coverage assessment |
| `corrected_coverage.py` | Corrected coverage metrics |
| `create_coverage_tables.py` | Build coverage reference tables |
| `final_coverage.py` | Final coverage report |
| `federal_deep_dive.py` | Federal contractor deep analysis |
| `federal_final_verification.py` | Verify federal coverage |
| `federal_misclass_check.py` | Check federal misclassification |

### Geographic & Hierarchy (5 files)

| File | Purpose |
|------|---------|
| `analyze_geocoding.py` | Validate geocoding results |
| `analyze_geocoding2.py` | Geocoding analysis v2 |
| `analyze_hierarchy_deep.py` | Deep dive into employer hierarchy |
| `analyze_chapters.py` | Union chapter-level analysis |
| `linkage_analysis.py` | Analyze entity linkages |

### Schedule 13 Analysis (4 files)

| File | Purpose |
|------|---------|
| `analyze_schedule13.py` | Schedule 13 basic analysis |
| `analyze_schedule13_cp2.py` | Schedule 13 checkpoint 2 |
| `analyze_schedule13_cp3.py` | Schedule 13 checkpoint 3 |
| `analyze_schedule13_total.py` | Schedule 13 total summary |

### Sector Analysis (5 files)

| File | Purpose |
|------|---------|
| `sector_analysis_1.py` | Public vs private sector split |
| `sector_analysis_2.py` | Sector composition by union |
| `sector_analysis_3.py` | Sector deep dive |
| `sector_final_summary.py` | Sector summary |
| `teacher_sector_check.py` | Teacher sector validation |

### Multi-Employer & Deduplication (9 files)

| File | Purpose |
|------|---------|
| `multi_employer_analysis.py` | Multi-employer agreement detection |
| `multi_employer_fix.py` | Multi-employer fixes v1 |
| `multi_employer_fix_v2.py` | Multi-employer fixes v2 |
| `multi_employer_final.py` | Final multi-employer report |
| `multi_employer_handler.py` | Multi-employer handling utilities |
| `analyze_deduplication.py` | Deduplication analysis |
| `analyze_deduplication_v2.py` | Deduplication analysis v2 |
| `analyze_membership_duplication.py` | Membership duplication detection |
| `analyze_remaining_overcount.py` | Remaining overcount analysis |

### Matching & Quality (5 files)

| File | Purpose |
|------|---------|
| `matching_analysis.py` | Entity matching metrics |
| `match_quality_report.py` | Match quality assessment |
| `check_relation_dupes.py` | Check for duplicate relations |
| `show_crosswalk_detail.py` | Display crosswalk details |
| `compare_lm2_vs_f7.py` | Compare LM2 vs F7 data |

### API Validation (4 files)

| File | Purpose |
|------|---------|
| `check_frontend_api_alignment.py` | Verify frontend-API contract alignment |
| `check_router_docs_drift.py` | Check API documentation consistency |
| `benchmark_endpoints.py` | Performance benchmark utility |
| `check_js_innerhtml_safety.py` | Security check for HTML injection vulnerabilities |

### Database & Migration (8 files)

| File | Purpose |
|------|---------|
| `migrate_to_db_config_connection.py` | Migrate scripts to centralized db_config |
| `rollback_db_config_migration.py` | Rollback db_config migration if needed |
| `migrate_literal_password_bug.py` | Fix literal password security bug |
| `find_literal_password_bug.py` | Find scripts with literal passwords |
| `fix_literal_password_bug.py` | Apply password security fixes |
| `rollback_password_fix.py` | Rollback password fixes |
| `smoke_migrated_scopes.py` | Test migrated database connections |
| `investigate_orphaned_relations.py` | Find orphaned relations |

### QA & Release (4 files)

| File | Purpose |
|------|---------|
| `run_ci_checks.py` | Run CI validation checks |
| `build_release_gate_summary.py` | Build release gate report |
| `prioritize_innerhtml_api_risk.py` | Risk prioritization for innerHTML issues |
| `phase1_merge_validator.py` | Phase 1 merge validation |

---

## 12. Scripts -- Setup & Performance

| File | Location | Purpose |
|------|----------|---------|
| `init_database.py` | `scripts/setup/` | Database initialization. Creates all 33+ schema files in dependency order. Verifies expected table row counts. Use `--create` flag. |
| `profile_matching.py` | `scripts/performance/` | Performance profiling for matching operations |

---

## 13. Shared Libraries (src/)

Reusable modules imported by scripts and the API.

### src/python/matching/

| File | Description |
|------|-------------|
| `name_normalization.py` | **Single source of truth** for name normalization. 3 levels: standard (legal suffixes, common abbreviations), aggressive (stopwords, DBA patterns, noise tokens), fuzzy (token-centric). Phonetic helpers: soundex, metaphone, phonetic_similarity. Used by all matchers and adapters. |
| `integration_stubs.py` | Integration helpers for matching pipeline |
| `__init__.py` | Package initialization |

### src/python/nlrb/

| File | Description |
|------|-------------|
| `load_nlrb_data.py` | NLRB SQLite-to-PostgreSQL loader. Imports cases, participants, votes, outcomes. Batch inserts (10K rows), conflict handling, migration script. |

### src/sql/

| File | Description |
|------|-------------|
| `nlrb_schema.sql` | NLRB table definitions: nlrb_cases, nlrb_participants, nlrb_votes, nlrb_outcomes with relationships and indexes |

---

## 14. Frontend (files/)

The frontend is a single-page application built with vanilla JavaScript, Tailwind CSS, Chart.js for charts, and Leaflet for maps.

### Main Entry Point

| File | Size | Description |
|------|------|-------------|
| `organizer_v5.html` | 145 KB | Complete SPA. Defines header, 5 app modes (territory/search/deepdive/uniondive/admin), 11 modals (scorecard/elections/corporate/public-sector/trends/analytics/comparison/find-similar/unified-employers/glossary). Includes Tailwind config, CDN imports for Chart.js/Leaflet/marker-clusters. Loads all JS modules. |

### JavaScript Modules (files/js/) -- 19 files

| File | Size | Description |
|------|------|-------------|
| `app.js` | 49 KB | App initialization, mode switching, CSV/PDF exports, URL state management, keyboard shortcuts, entity profile navigation |
| `config.js` | 3.5 KB | Global state: API_BASE, SCORE_FACTORS (8 legacy), UNIFIED_SCORE_FACTORS (7 signals), current results/page/map state |
| `search.js` | 49 KB | Search mode tabs (employers/unions), typeahead/autocomplete, results list with pagination (PAGE_SIZE=15), detail panel |
| `detail.js` | 76 KB | Employer and union detail panel rendering, scoring breakdowns, corporate family, matches, related filings, agreements |
| `scorecard.js` | 67 KB | Organizing Scorecard modal, unified/legacy toggle, state/sector/tier/NAICS filters, results pagination (50/page), detail drawer |
| `territory.js` | 31 KB | Territory mode: union/state/metro dropdowns, union map display, territory analytics, quick-start union links |
| `deepdive.js` | 22 KB | Employer profile deep-dive (deprecated, collapsed into search detail), scoring, siblings, elections |
| `uniondive.js` | 9.4 KB | Union full-page profile: membership/disbursement/affiliation history, organizing capacity, elections by employer |
| `modal-unified.js` | 10 KB | Unified employers modal: state filtering, employer list with source/size/location, detail drawer |
| `modal-similar.js` | 22 KB | Find Similar employers: national dashboard/affiliation selector, similar employer search by industry/size/location |
| `modal-corporate.js` | 16 KB | Corporate family tree modal: parent/subsidiary relationships, map with family locations, total workers/states |
| `modal-elections.js` | 9.8 KB | NLRB elections modal: state/year filtering, results list, detail drawer with election metadata/outcomes |
| `modal-trends.js` | 18 KB | Trends modal: overview/elections/density/growth tabs, time-series charts, export buttons |
| `modal-analytics.js` | 13 KB | Analytics dashboard: summary KPIs, national trends chart, election trends, recent elections list |
| `modal-publicsector.js` | 13 KB | Public sector modal: locals vs employers views, state filtering, affiliation selector |
| `modal-comparison.js` | 11 KB | Comparison view: side-by-side employer/union comparison, scoring comparison, saved searches |
| `glossary.js` | 8.9 KB | Metrics glossary modal: factor descriptions, scoring ranges, definitions table |
| `maps.js` | 7.6 KB | Leaflet map initialization (detail view + full results map), marker clusters, tile layer |
| `utils.js` | 7 KB | Shared utilities: formatNumber, formatCompact, truncateText, showLoading, showError, escapeHtml (XSS protection), csvEscape, downloadCSV, badge/tier coloring |

### CSS

| File | Size | Description |
|------|------|-------------|
| `css/organizer.css` | 7.2 KB | Custom Tailwind extensions, modal animations, skeleton loaders, marker clusters, status badges, score tier colors |

### Utility HTML Files

| File | Size | Description |
|------|------|-------------|
| `api_map.html` | 47 KB | API endpoint documentation and test interface. Lists all routes with parameters, request/response examples. |
| `test_api.html` | 2 KB | Simple API test harness for debugging endpoint calls |
| `afscme_scraper_data.html` | 257 KB | AFSCME union data export/visualization (legacy, from scraper testing) |

---

## 15. Tests (tests/)

**456 tests passing / 1 failing** (hospital abbreviation edge case) across **27 test files + conftest.py**.

### Configuration

| File | Description |
|------|-------------|
| `conftest.py` | Pytest shared fixtures. Test client with `DISABLE_AUTH=true`. Session-scoped client fixture. |

### Test Files

| File | Tests | Focus Area |
|------|-------|------------|
| `test_api.py` | 33 | API integration: 20+ endpoints, response structure, non-empty data, <5s response time |
| `test_auth.py` | 22 | JWT auth flow: register, login, refresh, protected access, rate limiting, role checks |
| `test_data_integrity.py` | 25 | Direct PostgreSQL: schema consistency, FK constraints, match log audit trail, source counts |
| `test_matching_pipeline.py` | 8 | Phase B regression: tier cascade, best-match-wins, batch processing |
| `test_matching.py` | 17 | Normalizer unit tests, composite scoring, Gower distance, match rates by source |
| `test_unified_scorecard.py` | 13 | mv_unified_scorecard: row count parity, 7-factor scoring, NULL handling, tier distribution |
| `test_employer_data_sources.py` | 12 | mv_employer_data_sources: 8 source flags, source_count accuracy, crosswalk, API endpoints |
| `test_scoring.py` | 12 | Scoring helpers: _score_size, _score_osha_normalized, _score_geographic, MV validation |
| `test_temporal_decay.py` | 11 | Time-based decay: OSHA 10yr, NLRB 7yr half-life math, score reduction over time |
| `test_name_normalization.py` | 24 | 3 normalization levels, phonetic helpers (soundex, metaphone). No DB required. |
| `test_naics_hierarchy_scoring.py` | 12 | Industry density: weighted blend of national/state density with NAICS digit-match similarity |
| `test_score_versioning.py` | 6 | score_versions table: algorithm metadata on every MV create/refresh |
| `test_propensity_model.py` | 9 | Feature engineering, model output validation, 14-feature Gower comparables, AUC checks |
| `test_occupation_integration.py` | 4 | industry_occupation_overlap table, naics_to_bls_industry mapping |
| `test_similarity_fallback.py` | 8 | Industry-average fallback for missing Gower scores, nearest-unionized context |
| `test_phase3_matching.py` | 10 | unified_match_log, pre-computed name columns, NLRB bridge view, match quality API |
| `test_phase4_integration.py` | 4 | Phase 4 data sources: SEC (500K+), BLS density, OEWS, occupation similarity |
| `test_employer_groups.py` | 6 | employer_canonical_groups: 1:1 canonical rep, member_count, consolidated_workers |
| `test_api_errors.py` | 10 | 404 for bogus IDs, 422 for invalid params, 503 for DB failures, string ID passthrough |
| `test_frontend_xss_regressions.py` | 6 | Static guards: escapeHtml usage, numeric type coercion, safe field rendering |
| `test_system_data_freshness.py` | 3 | `/api/system/data-freshness`: sources list, stale count consistency |
| `test_union_membership_history.py` | 4 | `/api/unions/{fnum}/membership-history`: series output, sorting, computed fields |
| `test_union_organizing_capacity.py` | 4 | `/api/unions/{fnum}/organizing-capacity`: organizing spend %, disbursement breakdown |
| `test_workforce_profile.py` | 4 | `/api/employers/{id}/workforce-profile`: occupation list, employment share sorting |
| `test_db_config_migration_guard.py` | 11 | Ensures db_config.get_connection() migration is complete across all script scopes |
| `test_phase1_regression_guards.py` | 2 | Guards against RealDictRow numeric index access, enforces JWT secret |
| `test_scorecard_contract_field_parity.py` | 2 | federal_contract_count consistency between scorecard list and detail responses |

---

## 16. SQL Files (sql/)

SQL schema definitions, queries, and patches. **34 files** across three directories.

### Core Schema (sql/)

| File | Description |
|------|-------------|
| `f7_schema.sql` | F-7 employer master schema: f7_employers, f7_employers_deduped, union_sector/union_match_status lookups, employer_canonical_groups, indexes, constraints |
| `f7_indexes.sql` | Performance indexes for f7_employers: canonical_id, state/zip, latest_notice_date |
| `deduplication_views.sql` | Views for merging duplicate employer records, geocoding consolidation, union name canonicalization |

### Schema Definitions (sql/schema/)

| File | Description |
|------|-------------|
| `f7_schema.sql` | F7 employer tables (duplicate of above) |
| `f7_crosswalk_schema.sql` | F7-to-employer crosswalk for corporate relationships |
| `bls_phase1_schema.sql` | BLS union density data tables |
| `nlrb_schema_phase1.sql` | NLRB elections and participants schema |
| `vr_schema.sql` | Voluntary recognition tables |
| `unionstats_schema.sql` | Union statistics and membership tables |
| `afscme_ny_schema.sql` | AFSCME New York specific data tables |
| `schema_v4_employer_search.sql` | Employer search unified view schema |

### Queries (sql/queries/)

| File | Description |
|------|-------------|
| `create_search_views.sql` | Search views: v_employer_search (F7+union+affiliation), v_union_search |
| `dedupe_f7_employers.sql` | Deduplication logic for F7 employer records |
| `diagnose_f7_matching.sql` | Diagnostic queries for matching quality |
| `diagnose_local_numbers.sql` | Union local number extraction diagnosis |
| `diagnose_affiliations.sql` | Affiliation diagnosis queries |
| `fix_union_local_view.sql` | Fix union local number canonicalization |
| `fix_union_local_view_v2.sql` | Union local view fix v2 |
| `fix_views.sql` | View repair queries |
| `fix_views_v2.sql` | View repair v2 |
| `fix_employer_view_v3.sql` | Employer view repair v3 |
| `fix_affiliations.sql` | Union affiliation fixes |
| `check_columns.sql` | Schema column inspection |
| `check_db.sql` | General DB inspection queries |
| `check_lm_columns.sql` | LM form column inspection |
| `update_views_deduped.sql` | Update deduped views after regeneration |
| `BLS_INTEGRATION_QUERIES.sql` | BLS density / state-level union density integration |
| `vr_views_5a.sql` | Voluntary recognition views (phase 5a) |
| `vr_views_5b.sql` | Voluntary recognition views (phase 5b) |
| `test_views.sql` | View validation queries |
| `patch_v4_abc.sql` | Version 4 schema patches |
| `patch_v4_fix.sql` | Version 4 fixes |
| `insert_statements_2024.sql` | Historical data insertions for 2024 |

---

## 17. Documentation (docs/)

**129+ files** of project documentation, organized by category.

### Audit & QA

| File | Description |
|------|-------------|
| `AUDIT_REPORT_2026.md` | Comprehensive 2026 audit report |
| `AUDIT_REPORT_CLAUDE_2026_R3.md` | Claude's round 3 audit findings |
| `AUDIT_REPORT_CODEX_2026_R3.md` | Codex's round 3 audit findings |
| `AUDIT_REPORT_CODEX_2026_R4_FINAL.md` | Codex round 4 final audit |
| `AUDIT_REPORT_CODEX_2026_R4_WORKING.md` | Codex round 4 working draft |
| `AUDIT_REPORT_GEMINI_2026_R3.md` | Gemini's round 3 audit findings |
| `AUDIT_REPORT_ROUND2_CLAUDE.md` | Claude's round 2 audit report |
| `AUDIT_REPORT_ROUND2_CODEX.md` | Codex's round 2 audit report |
| `CI_CHECK_REPORT.md` | Continuous integration check report |
| `CREDENTIAL_SCAN_2026.md` | Security credential scanning results |
| `FOCUSED_AUDIT_CLAUDE_DATABASE.md` | Database-focused audit by Claude |
| `TEST_COVERAGE_REVIEW.md` | Test coverage analysis |

### Matching & Data Integration

| File | Description |
|------|-------------|
| `MATCHING_CODE_REVIEW.md` | Code review of matching algorithms |
| `MATCH_QUALITY_REPORT.md` | Overall match quality assessment |
| `MATCH_QUALITY_SAMPLE_2026.md` | Sample-based quality assessment |
| `SCORECARD_SHRINKAGE_INVESTIGATION.md` | Investigation of scorecard data loss (Codex orphan-view cascade) |
| `MISSING_UNIONS_ANALYSIS.md` | Analysis of missing union records |
| `NLRB_ULP_MATCHING_GAP.md` | NLRB ULP matching gap analysis |

### Methodology & Technical

| File | Description |
|------|-------------|
| `METHODOLOGY_SUMMARY_v8.md` | Current methodology overview |
| `NY_EXPORT_METHODOLOGY.md` | NY deduplicated export methodology |
| `NY_DENSITY_MAP_METHODOLOGY.md` | NY density mapping approach |
| `EPI_BENCHMARK_METHODOLOGY.md` | EPI benchmarking methodology |
| `PHASE3_NORMALIZATION_INTEGRATION_CHECKLIST.md` | Name normalization checklist |
| `PHASE4_ARCHITECTURE_REVIEW.md` | Phase 4 architecture documentation |
| `PHASE4_CODE_REVIEW.md` | Phase 4 code review findings |
| `PHASE5_DETAILED_PLAN.md` | Phase 5 detailed execution plan |
| `PHASE5_EXECUTION_PLAN.md` | Phase 5 implementation strategy |
| `SCORING_INTEGRATION_DESIGN.md` | Unified scoring system design |
| `NLRB_Propensity_Model_Design.md` | NLRB propensity model specification |
| `DATA_QUALITY_FRAMEWORK.md` | Data quality standards framework |
| `PUBLIC_SECTOR_SCHEMA_DOCS.md` | Public sector schema documentation |

### Research & Feasibility

| File | Description |
|------|-------------|
| `ACS_PUMS_FEASIBILITY_RESEARCH.md` | ACS PUMS integration feasibility |
| `BLS_CPS_DENSITY_RESEARCH.md` | BLS CPS density data research |
| `BLS_OEWS_DATA_RESEARCH.md` | BLS OEWS occupation data research |
| `CALIBRATION_ENGINE_FEASIBILITY.md` | Score calibration engine feasibility |
| `CORPORATE_HIERARCHY_RESEARCH.md` | Corporate structure research |
| `COSINE_SIMILARITY_RESEARCH.md` | Cosine similarity research |
| `EDGARTOOLS_EVALUATION.md` | SEC EDGAR tools evaluation |
| `EXHIBIT_21_PARSING_RESEARCH.md` | SEC Exhibit 21 parsing research |
| `HISTORICAL_EMPLOYER_ANALYSIS.md` | Historical employer trend analysis |
| `HUMAN_CAPITAL_DISCLOSURE_RESEARCH.md` | HCD reporting research |
| `IRS_BMF_RESEARCH.md` | IRS Business Master File research |
| `ONET_INTEGRATION_RESEARCH.md` | O*NET occupational research |
| `REVENUE_PER_EMPLOYEE_RESEARCH.md` | Revenue efficiency metrics research |
| `SEC_EDGAR_RESEARCH.md` | SEC EDGAR data integration research |
| `STATE_PERB_RESEARCH.md` | State PERB system research |
| `STATE_PERB_RESEARCH_PART1.md` | State PERB system research part 2 |

### Scoring & Features

| File | Description |
|------|-------------|
| `MERGENT_SCORECARD_PIPELINE.md` | Mergent data scoring pipeline |
| `IRS_BMF_ETL_COMPLETION.md` | BMF ETL integration completion |
| `SEC_ETL_COMPLETION.md` | SEC ETL integration completion |
| `FORM_990_FINAL_RESULTS.md` | Form 990 integration final results |
| `BLOCK_C3_COMPLETION.md` | Phase C3 completion status |

### Case Studies

| File | Description |
|------|-------------|
| `AFSCME_NY_CASE_STUDY.md` | AFSCME New York organizing case study |
| `TEAMSTERS_COMPARISON_REPORT.md` | Teamsters union comparison analysis |

### Planning & Coordination

| File | Description |
|------|-------------|
| `LABOR_PLATFORM_ROADMAP_v10.md` | Roadmap version 10 |
| `LABOR_PLATFORM_ROADMAP_v12.md` | Roadmap version 12 |
| `EXTENDED_ROADMAP.md` | Extended roadmap planning |
| `MULTI_AI_TASK_PLAN.md` | Multi-AI coordination plan |
| `HANDOFF_CLAUDE_GEMINI_2026-02-15.md` | Claude to Gemini handoff |
| `WAVE2_CODEX_PROMPT.md` | Codex wave 2 task prompt |
| `WAVE2_GEMINI_PROMPT.md` | Gemini wave 2 task prompt |
| `CODEX_PARALLEL_TASKS_2026_02_18.md` | Codex parallel task coordination |
| `CHECKPOINT_PARALLEL_CODEX_PHASE1_2026-02-15.md` | Codex parallel checkpoint |

### Completions & Reports

| File | Description |
|------|-------------|
| `SESSION_PHASE4_COMPLETION.md` | Phase 4 completion report |
| `ORPHAN_MAP_2026.md` | Orphaned records mapping |
| `PHASE1_MERGE_VALIDATION_REPORT.md` | Phase 1 merge validation |

### Database & Operations

| File | Description |
|------|-------------|
| `db_inventory_latest.md` | Latest database inventory |
| `PARALLEL_DB_CONFIG_MIGRATION_REPORT.md` | DB config migration details |
| `PARALLEL_QUERY_PLAN_BASELINE.md` | Query performance baseline |
| `DEPENDENCY_REVIEW.md` | Dependency analysis |
| `PERFORMANCE_PROFILE.md` | System performance profiling |

### Frontend & API

| File | Description |
|------|-------------|
| `FRONTEND_CODE_REVIEW.md` | Frontend code review |
| `PARALLEL_FRONTEND_API_AUDIT.md` | Frontend-API audit |
| `PARALLEL_INNERHTML_API_RISK_PRIORITY.md` | JavaScript innerHTML security audit |
| `JS_INNERHTML_SAFETY_CHECK.md` | innerHTML safety validation |
| `PARALLEL_ROUTER_DOCS_DRIFT.md` | API documentation drift analysis |
| `RELEASE_GATE_SUMMARY.md` | Release gate criteria summary |

### Security

| File | Description |
|------|-------------|
| `API_SECURITY_FIXES.md` | API security vulnerability fixes |
| `PARALLEL_PASSWORD_AUTOFIX_REPORT.md` | Automated password fix report |
| `PARALLEL_PHASE1_PASSWORD_AUDIT.md` | Phase 1 password audit |

### General & Reference

| File | Description |
|------|-------------|
| `README.md` | Documentation index |
| `CHAT_COMPRESSED_2026-02-15.md` | Compressed chat history |
| `Labor_Relations_Platform_Summary.pdf` | Executive summary PDF |

### Subdirectory: docs/session-summaries/

Session logs documenting work done by each AI tool.

| File | Description |
|------|-------------|
| `SESSION_LOG_2026.md` | Master 2026 session log |
| `SESSION_SUMMARY_2026-01-31_analytics_corporate.md` | Jan 31 analytics session |
| `SESSION_SUMMARY_2026-02-16e_reorg_phaseA.md` | Feb 16 reorg and Phase A |
| `SESSION_SUMMARY_2026-02-17_codex_handoff.md` | Feb 17 Codex handoff |
| `SESSION_SUMMARY_2026-02-18_claude_B4_batch.md` | Feb 18 Claude B4 re-runs |
| `SESSION_SUMMARY_2026-02-18_codex_tasks_1_2_4_5_9.md` | Feb 18 Codex tasks |
| `SESSION_SUMMARY_2026-02-18_gemini_research_3_4_5.md` | Feb 18 Gemini research |
| `SESSION_SUMMARY_2026-02-19_codex_batch2.md` | Feb 19 Codex batch 2 |
| `SESSION_SUMMARY_2026-02-19_codex_batch3.md` | Feb 19 Codex batch 3 |
| `SESSION_SUMMARY_2026-02-19_codex_critical_fixes.md` | Feb 19 critical fixes |
| `SESSION_SUMMARY_2026-02-19_codex_db_analyze.md` | Feb 19 DB analysis |
| `SESSION_SUMMARY_2026-02-19_codex_frontend_unification.md` | Feb 19 frontend unification |
| `SESSION_SUMMARY_2026-02-19_codex_parallel_fixes.md` | Feb 19 parallel fixes |
| `SESSION_SUMMARY_2026-02-19e_claude_codex_execution.md` | Feb 19e execution |
| `SESSION_SUMMARY_2026-02-20_claude_b4_completion.md` | Feb 20 B4 completion |
| `SESSION_SUMMARY_2026-02-20c_claude_ny_export_v2.md` | Feb 20c NY export v2 |
| `CODEX_SESSION_SUMMARY_2026-02-14_auth_and_sprint3_review.md` | Feb 14 auth/sprint3 |

### Subdirectory: docs/audit_artifacts_round2/

Machine-generated audit artifacts (JSON/CSV) from round 2 audits.

| File | Description |
|------|-------------|
| `section1_inventory.json` | Inventory audit |
| `section2_data_quality.json` | Data quality checks |
| `section3_matching.json` | Matching audit |
| `section4_api_inventory.json` | API inventory |
| `section4_api_inventory_refined.json` | Refined API inventory |
| `section4_endpoint_inventory.csv` | Endpoint CSV listing |
| `section4_endpoint_smoketest.json` | Endpoint smoke test results |
| `section5_frontend_api_scan.json` | Frontend API scan |
| `section5_frontend_summary.json` | Frontend summary |
| `section6_db_checks.json` | Database checks |
| `section8_dead_refs_refined.json` | Dead reference analysis |
| `section8_file_counts.json` | File count audit |
| `section8_scripts_scan.json` | Scripts inventory scan |
| `section9_doc_claim_checks.json` | Documentation claims validation |
| `section9_doc_truth_snapshot.json` | Documentation truth snapshot |

### Subdirectory: docs/coverage/

Coverage analysis data files.

| File | Description |
|------|-------------|
| `COVERAGE_REFERENCE_ANNOTATED.csv` | Annotated coverage reference |
| `FINAL_COVERAGE_BY_STATE.csv` | Final state-by-state coverage |
| `platform_vs_epi_by_state.csv` | Platform vs EPI benchmark comparison |
| `platform_vs_epi_RECONCILED.csv` | Reconciled coverage metrics |

### Subdirectory: docs/reviews/

| File | Description |
|------|-------------|
| `DETERMINISTIC_MATCHING_PIPELINE_REVIEW_2026-02-17.md` | Matching pipeline review |
| `PHASE-B-MATCHING-TESTS-SPLINK-REVIEW-2026-02-17.md` | Splink test review |

### Subdirectory: docs/reference-pdfs/

| File | Description |
|------|-------------|
| `files.epi.org_uploads_union-table6b-december-2025.html.pdf` | EPI union data reference |
| `Table 3. Union affiliation... - 2024 A01 Results.pdf` | BLS union affiliation reference |

---

## 18. Data Directory (data/)

Reference data, lookup tables, and geographic files. **247+ files total.**

### Root-Level Data Files (~41 files)

Mixed collection of CSVs, Excel files, and geographic data:

**Geographic:** `cb_2022_36_tract_500k.zip`, `new-york-zip-codes.kml`, `tl_2022_tract.shp.ea.iso.xml`

**State/County Data:** `contracts_NY STATE after 1_01_23.xlsx`, `county_density_analysis.csv`, `epi_state_benchmarks_2025.csv`, `public_sector_coverage_all_states.csv`, `state_coverage_vs_epi_benchmarks.csv`, `state_workforce_public_private_shares.csv`

**NY-Specific:** `ny_county_density.csv`, `ny_county_density_map.csv`, `ny_county_workforce.xlsx`, `ny_public_sector_gaps.csv`, `ny_tract_density.csv`, `ny_tract_density_map.csv`, `ny_tract_workforce.xlsx`, `ny_zip_density.csv`, `ny_zip_density_map.csv`, `ny_zip_workforce.xlsx`, `ny_990_extract.csv`, `nyc_employer_violations.xlsx`

**Union Data:** `seiu_locals.csv`, `seiu_locals_detailed.csv`, `teamsters_comparison_report.csv`, `teamsters_database_locals.csv`, `teamsters_discrepancies.csv`, `teamsters_missing_from_db.csv`, `teamsters_not_on_website.csv`, `teamsters_official_locals.csv`

**F7 Analysis:** `f7_combined_dedup_evidence.csv`, `f7_duplicate_groups.csv`

**Geocoding:** `geocoding_batch_001.csv`, `geocoding_batch_002.csv`, `geocoding_no_address.csv`, `geocoding_po_boxes.csv`

**Other:** `union_linkage_review.csv`, `sector_review.csv`, `organizing_events_catalog.csv`, `crosscheck_report.csv`, `free_company_dataset.csv.7z`, `usaspending_sample.zip`

### data/bls/ (8 files)

BLS lookup tables and raw HTML:
- `lu.fips`, `lu.indy`, `lu.occupation`, `lu.series`, `lu_data_1.AllData` -- BLS lookup/data files
- `union_2024_table1_characteristics.html`, `union_2024_table3_industry.html`, `union_2024_table5_state.html` -- Downloaded BLS tables

### data/naics_crosswalks/ (8 files)

NAICS code crosswalks between revision years:
- `2002_to_sic.xls`, `2007_to_2002.xls`, `2012_to_2007.xls`, `2017_to_2012.xlsx`, `2022_to_2017.xlsx`, `sic_to_naics_2002.xls`
- `naics_2017_structure.xlsx`, `naics_2022_structure.xlsx`

### data/unionstats/ (147 files)

Union membership statistics from unionstats.com. Organized by subdirectory:
- **demographic/** (30 files) -- Member statistics by demographics (gender, race, education, sector)
- **msa/** (46 files) -- Metropolitan statistical area data 1986-2024
- **occupation/** (42 files) -- Union membership by occupation 1983-2024
- **state/** (40 files) -- State-level data 1983-2023

### data/raw/ (6 files)

Raw source files: XML filings, text extracts, web search archives.

### Empty/Minimal Directories

`data/coverage/`, `data/crosswalk/`, `data/f7/`, `data/nlrb/`, `data/olms/` -- empty or minimal directories from earlier development phases.

---

## 19. CorpWatch Data (corpwatch_api_tables_csv/)

**18 CSV files** from CorpWatch API export. Usage status uncertain -- may have been imported for corporate hierarchy research but not actively used in the matching pipeline.

| File | Description |
|------|-------------|
| `companies.csv` | Company master table |
| `company_filings.csv` | Filing records |
| `company_info.csv` | Company details |
| `company_locations.csv` | Location records |
| `company_names.csv` | Alternative company names |
| `company_relations.csv` | Corporate relationships |
| `cik_name_lookup.csv` | SEC CIK to company name mapping |
| `cw_id_lookup.csv` | CorpWatch ID mapping |
| `filers.csv` | SEC filers |
| `filings.csv` | SEC filing details |
| `filings_lookup.csv` | Filing lookup table |
| `meta.csv` | Metadata |
| `relationships.csv` | Entity relationships |
| `sic_codes.csv` | Standard Industrial Classification codes |
| `sic_sectors.csv` | SIC sector mapping |
| `un_countries.csv` | Country lookup |
| `un_country_aliases.csv` | Country name aliases |
| `un_country_subdivisions.csv` | Country subdivision mapping |

---

## 20. Checkpoints & Logs

### Checkpoint Files

Re-run tracking files created by `run_remaining_reruns.py` and `run_deterministic.py`:

| File | Purpose |
|------|---------|
| `checkpoint_osha_batch_*.json` | OSHA re-run batch progress (4 batches) |
| `checkpoint_sec_batch_*.json` | SEC re-run batch progress (5 batches) |
| `checkpoint_990_batch_*.json` | 990 re-run batch progress (5 batches) |
| `checkpoint_sam_batch_*.json` | SAM re-run batch progress (5 batches) |

### Validation Logs

| File | Purpose |
|------|---------|
| `validation_log_*.txt` | Output from CI check / validation runs |

---

## 21. Configuration & Deployment

### Docker Setup

The project includes a complete Docker Compose deployment:

```
docker-compose.yml  -- 3 services: postgres:17, API (python:3.12-slim), nginx:alpine
Dockerfile          -- API container: install deps, copy api/ + db_config.py, run uvicorn
nginx.conf          -- Reverse proxy: / -> frontend, /api/* -> backend:8001
```

**Ports:** postgres 5432, API 8001, nginx 8080

### Python Configuration

```
pyproject.toml      -- Project metadata, dependencies, pytest config, ruff rules
requirements.txt    -- Frozen pip dependencies (21 packages)
```

**Key Dependencies:** FastAPI 0.128.0, psycopg2-binary 2.9.11, pandas 2.3.3, splink 4.0.12, rapidfuzz 3.14.3, scikit-learn 1.8.0, bcrypt 5.0.0

### Environment

```
.env                -- DB credentials, JWT secret, auth toggle (never committed)
.env.example        -- Template with required keys
```

**Required Variables:** `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
**Optional Variables:** `LABOR_JWT_SECRET` (32+ chars), `DISABLE_AUTH`, `ALLOWED_ORIGINS`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW`, `MATCH_MIN_NAME_SIM`

---

## 22. Archive (archive/)

Archived materials from earlier development phases. **~16 GB total.** Not part of the active codebase.

### Claude Ai union project/ (~8.3 GB)

The original monolithic project from January 2026. Contains: JSON datasets (`all_unions_data.json`, `all_employers_data.json` at 90+ MB each), SQLite databases (`f7.db` 207 MB, `f7_integrated.db` 113 MB), CWA analysis dashboards (8 HTML + 2 JSX), 70+ Python analysis/ETL scripts, F7 SQL dumps, union research data (SEIU, Teamsters, Unite Here), PDFs, and Excel files. Archived because the project was restructured into the current modular architecture.

### imported_data/ (~6.7 GB)

Raw data imports organized in 16 subdirectories: 990/, AFSCME case example NY/, afscme scrape/, bls_projections/, crosswalk/, f7/, lm2/, nlrb/, ny_companies/, olms/, quality check files/, splink/, whd/, and others. Original source data that has been loaded into PostgreSQL. Kept for reference but not needed for normal operation.

### old_scripts/ (~5.3 MB, 100+ files)

Deprecated scripts from checkpoint-based development: `checkpoint_a*.py` through `checkpoint_g*.py`, plus analysis, audit, batch, cleanup, coverage, density, etl, fix, import, maintenance, matching, and research scripts. Superseded by the reorganized `scripts/` directory structure.

### NLTB_APIfiles/ (~781 MB)

Legacy NLRB integration files from an earlier approach. Superseded by `src/python/nlrb/load_nlrb_data.py` and the current NLRB schema.

### bls_phases/ (~77 MB, 3 subdirs)

BLS loading phases (phase 1-3) with SQL data dumps. 53 files total. Data has been loaded into PostgreSQL.

### old_docs/ (~13 MB, 84 files)

Markdown documentation from earlier phases, consolidated and superseded by the current `docs/` directory.

### old_roadmaps/ (~505 KB, 19 files)

Earlier versions of project roadmaps, superseded by `UNIFIED_ROADMAP_2026_02_19.md`.

### old_api/ (~416 KB, 11 files)

Dead API monoliths: `labor_api_v4.py`, `v5.py`, `v6.py`, `labor_search_api` variants, and endpoint specifications. Superseded by the modular `api/routers/` architecture.

### db_config_migration_backups/ (~2.6 MB, 289 files)

Versioned backups of script files from the db_config.py migration (when 500+ scripts were updated to use centralized `get_connection()`).

### frontend/ (~480 KB, 7 files)

Archived HTML/CSS frontend files from before `organizer_v5.html`.

### nlrb_integration/ (~369 KB, 45 files)

Old NLRB matching and schema creation scripts, superseded by the current matching pipeline.

### docs_consolidated_2026-02/ (~516 KB, 56 files)

Consolidated documentation from Jan 23 - Feb 9, 2026. Includes earlier roadmap versions (v8-v9), session summaries, project status, and methodologies.

### password_fix_backups/ (~16 KB, 2 subdirs)

Minimal backups from password security remediation (docs/ and scripts/).

---

## 23. Database Inventory

### Summary

| Metric | Value |
|--------|-------|
| **Total size** | 20 GB |
| **Base tables** | 174 |
| **Views** | 123 |
| **Materialized views** | 6 |

### Top 15 Tables by Row Count

| # | Table | Rows |
|---|-------|------|
| 1 | `ar_disbursements_emp_off` | 2,813,011 |
| 2 | `osha_violations_detail` | 2,244,955 |
| 3 | `nlrb_docket` | 2,046,151 |
| 4 | `qcew_annual` | 1,943,426 |
| 5 | `nlrb_participants` | 1,906,537 |
| 6 | `unified_match_log` | 1,738,115 |
| 7 | `epi_union_membership` | 1,420,064 |
| 8 | `employers_990_deduped` | 1,046,167 |
| 9 | `osha_establishments` | 1,007,275 |
| 10 | `osha_violation_summary` | 872,163 |
| 11 | `sam_entities` | 826,042 |
| 12 | `nlrb_allegations` | 715,805 |
| 13 | `national_990_filers` | 586,767 |
| 14 | `sec_companies` | 517,403 |
| 15 | `gleif_ownership_links` | 498,963 |

### Materialized Views

| View | Rows | Purpose |
|------|------|---------|
| `mv_whd_employer_agg` | 330,419 | WHD employer aggregation |
| `mv_organizing_scorecard` | 212,441 | Legacy organizing scorecard (9 factors, 11-56 range) |
| `mv_employer_search` | 170,775 | Employer unified search |
| `mv_employer_data_sources` | 146,863 | Source coverage flags (8 boolean has_* columns) |
| `mv_unified_scorecard` | 146,863 | Unified 7-factor scorecard (0-10 each, avg unified_score) |
| `mv_employer_features` | 54,968 | Employer feature matrix for ML |

### Key Reference Tables

| Table | Rows | Purpose |
|-------|------|---------|
| `f7_employers_deduped` | 146,863 | Canonical employer records |
| `unions_master` | 26,665 | Union master list (all LM filings) |
| `employer_canonical_groups` | 16,209 | Canonical employer groups |
| `score_versions` | ~50 | Algorithm version tracking |
| `platform_users` | ~2 | Auth users |
| `data_freshness` | ~15 | Data source freshness tracking |

---

## 24. Pipeline Run Order (Quick Reference)

The complete 9-step pipeline, reproduced from `PIPELINE_MANIFEST.md`:

```
Step 1:   ETL -- Load/refresh source data
          py scripts/etl/load_osha_violations.py
          py scripts/etl/load_whd_national.py
          py scripts/etl/load_sam.py
          py scripts/etl/load_sec_edgar.py
          py scripts/etl/load_national_990.py
          py scripts/etl/download_bls_union_tables.py && py scripts/etl/parse_bls_union_tables.py
          py scripts/etl/load_gleif_bods.py
          (+ other ETL scripts as needed)

Step 2:   Matching -- Deterministic + fuzzy
          py scripts/matching/run_deterministic.py all

Step 3:   Matching -- Splink probabilistic (optional)
          py scripts/matching/splink_pipeline.py

Step 4:   Matching -- Build employer groups
          py scripts/matching/build_employer_groups.py

Step 4.5: Scoring -- Build data source flags
          py scripts/scoring/build_employer_data_sources.py --refresh

Step 4.6: Scoring -- Build unified scorecard
          py scripts/scoring/build_unified_scorecard.py --refresh

Step 5:   Scoring -- NLRB patterns
          py scripts/scoring/compute_nlrb_patterns.py

Step 6:   Scoring -- Legacy scorecard MV
          py scripts/scoring/create_scorecard_mv.py --refresh

Step 7:   Scoring -- Gower similarity
          py scripts/scoring/compute_gower_similarity.py --refresh-view

Step 8:   ML -- Propensity scoring
          py scripts/ml/train_propensity_model.py --score-only

Step 9:   Maintenance -- Data freshness
          py scripts/maintenance/create_data_freshness.py --refresh
```

After matching re-runs, also run:
```bash
py scripts/maintenance/rebuild_legacy_tables.py  # Rebuild match tables from UML
# Then refresh all MVs (steps 4.5, 4.6, 6, 7)
```
