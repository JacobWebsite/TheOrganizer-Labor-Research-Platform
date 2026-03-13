# Multi-AI Task Plan — Phases 4-7
**Date:** February 15, 2026
**Workflow:** Gemini researches ahead, Claude Code builds, Codex reviews behind — all in parallel

---

## How to Use This Document

1. **Start each batch** by sending Gemini the research prompts for the NEXT batch
2. **While Gemini researches**, Claude Code works on the current batch
3. **When Claude Code finishes** a batch, send to Codex for review
4. **When Gemini returns** research, adjust Claude Code's approach if needed
5. Mark tasks DONE as they complete

---

## Phase 4: New Data Sources (Weeks 8-10)

### 4.1 SEC EDGAR Full Index (HIGH priority)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research `edgartools` bulk access patterns, confirm EIN availability in XBRL filings, CIK-to-company mapping completeness, rate limits, best approach for 300K+ companies | |
| **Claude Code** | Write ETL script, load 300K+ companies, run through deterministic matcher, write to unified_match_log | |
| **Codex** | Review ETL script for SQL injection, error handling, EIN type matching (TEXT vs INT), batch insert performance | |

### 4.2 IRS Business Master File (HIGH priority)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Compare ProPublica Nonprofit Explorer API vs IRS bulk download. Confirm fields (EIN, name, NTEE codes, address, ruling date). Coverage of union-related orgs. Download URL and format. | |
| **Claude Code** | Write loader, deduplicate against existing 990 data, match to F7 employers via deterministic matcher | |
| **Codex** | Review dedup logic, check for false-positive matches on common nonprofit names (e.g., "Community Health Center" appearing in many states) | |

### 4.3 CPS Microdata via IPUMS (MEDIUM priority)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Confirm union membership variables (UNION, CLASSWKR), geographic granularity (state vs metro vs county), IPUMS registration requirements, sample size limits for sub-state estimates, `ipumspy` package capabilities | |
| **Claude Code** | Write IPUMS extract script, compute state/industry/metro density estimates, replace BLS flat rates in scorecard MV | |
| **Codex** | Review statistical methodology — are sample sizes large enough for metro-level estimates? Is weighting handled correctly? | |

### 4.4 OEWS Staffing Patterns (MEDIUM priority)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Confirm occupation-by-industry matrix format, geographic levels available (national/state/metro), download URL, update frequency, file format (CSV/Excel) | |
| **Claude Code** | Build occupation similarity index between employers, integrate as matching/comparables dimension | |
| **Codex** | Review similarity computation for performance (N^2 problem?), check that occupation codes are handled correctly | |

**Phase 4 parallel plan:**
1. Send Gemini all 4 research prompts at once
2. Start Claude Code on 4.1 (SEC EDGAR) immediately — enough existing knowledge to begin
3. When Gemini returns 4.2 research, start 4.2 while Codex reviews 4.1
4. Continue pipeline: build -> review -> build -> review

---

## Phase 5: Scoring Evolution (Weeks 10-12)

### 5.1 Temporal Decay (Core — ships)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A (straightforward exponential decay math) | — |
| **Claude Code** | Add time-based decay to OSHA, WHD, NLRB factors in scorecard MV SQL. Parameterize half-life (e.g., 5 years). Recent violations weigh more. | |
| **Codex** | Review decay formula, check edge cases (NULL dates, future dates, very old records) | |

### 5.2 Hierarchical NAICS Similarity (Core — ships)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research NAICS hierarchy tree structure — confirm 2-to-6 digit nesting is clean, no cross-sector overlaps | |
| **Claude Code** | Replace binary NAICS matching with gradient similarity (shared prefix length). 5/6 digits shared = very similar, 2/6 = barely related. | |
| **Codex** | Review that NAICS codes with leading zeros handled correctly, no off-by-one in prefix matching | |

### 5.3 Score Versioning (Core — ships)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Add `score_version` column to MV, track methodology changes, bump version on factor changes | |
| **Codex** | Review migration safety — does version bump break any cached frontend data or API contracts? | |

### 5.4 Gower Distance Enhancement (Advanced — experimental)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Add weighted dimensions to employer_comparables (industry 3x, OSHA 2x, state 1x, size 1x). Compute "distance from nearest unionized sibling" as new factor. | |
| **Codex** | Review weight choices, check that distance metric is mathematically sound, verify no division-by-zero | |

### 5.5 Propensity Score Model (Advanced — experimental)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research logistic regression for organizing propensity. What AUC is meaningful for this domain? How have similar models been built in political/social organizing? What features matter most (employer size, industry, geography, violation history)? | |
| **Claude Code** | Train logistic regression on 33K NLRB elections, evaluate AUC, publish as experimental score alongside heuristic | |
| **Codex** | Review model for data leakage (using outcome as feature), overfitting (train/test split), feature engineering mistakes | |

---

## Phase 6: Deployment Prep (Weeks 11-14)

### 6.1 Docker Setup

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Write `docker-compose.yml` (API server + PostgreSQL + nginx reverse proxy), test cold start on clean machine | |
| **Codex** | Review Dockerfile for security: no secrets baked into image, non-root user, `.dockerignore` covers `.env` and data files | |

### 6.2 CI/CD Pipeline

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Write GitHub Actions config: run 240 tests on push, lint on PR, fail fast on critical test failures | |
| **Codex** | Review workflow for secret leaks in logs, proper caching of pip dependencies, test timeout settings | |

### 6.3 Automated Scheduling

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Set up scheduler for: weekly MV refresh, daily freshness check, weekly ANALYZE, nightly backup | |
| **Codex** | Review that scheduled jobs handle failures gracefully (alerting, no silent data corruption, idempotent reruns) | |

### 6.4 Script Lifecycle Management

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Create manifest of ~494 scripts: active (pipeline), legacy (reference), experimental (temp). Archive deprecated to `docs/`. | |
| **Codex** | Review manifest for completeness — any active scripts missed? Any "legacy" scripts still called by something? | |

### 6.5 Drop Unused Indexes

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | N/A | — |
| **Claude Code** | Confirm 299 indexes are genuinely unused (pg_stat_user_indexes scan count = 0), drop them, measure storage savings | |
| **Codex** | Review that no index supports a rare-but-important query (e.g., admin-only endpoints, monthly reports) | |

---

## Phase 7: Intelligence Layer (Week 14+)

### 7.1 Web Scraper Expansion

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research Teamsters (338 locals), SEIU, UFCW, UNITE HERE website patterns — are they templated (Wordpress/SquareSpace) or all custom? What employer data is typically on local union sites? | |
| **Claude Code** | Expand Crawl4AI + AI extraction pipeline to new unions. Match extracted employers against F7. | |
| **Codex** | Review scraper for rate limiting, robots.txt compliance, error recovery, data extraction accuracy | |

### 7.2 State PERB Data (Original Contribution)

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | **Major research task:** NY PERB, CA PERB, IL ILRB — what data do they publish? Do they have APIs or bulk downloads? File formats? Legal restrictions on scraping? What fields are available (employer, union, unit size, certification date)? Is anyone else doing this? | |
| **Claude Code** | Build scrapers/loaders based on Gemini's findings. Integrate into unified match pipeline. | |
| **Codex** | Review data quality — are PERB records reliable enough to match against F7? How to handle state-specific quirks? | |

### 7.3 Union-Lost Analysis

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research academic literature on post-decertification working conditions. What metrics matter? What's been published? Any existing datasets? | |
| **Claude Code** | Match 52K historical employers to OSHA/WHD, compute before/after comparisons (violation rates, wage theft, safety incidents) | |
| **Codex** | Review statistical methodology — are before/after comparisons valid? Selection bias? Confounders? | |

### 7.4 Board Report Generation

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Research: what do union board presentations typically contain? What format do organizers expect (PDF, slides, one-pagers)? | |
| **Claude Code** | Build PDF/CSV export: territory overview, top targets with evidence, trend charts, data freshness statement | |
| **Codex** | Review report output for data accuracy, formatting consistency, correct score display | |

### 7.5 Occupation-Based Similarity

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Covered by 4.4 research | — |
| **Claude Code** | Build similarity index from OEWS data loaded in 4.4 | |
| **Codex** | Covered by 4.4 review | — |

### 7.6 5-Area Frontend Expansion

| Tool | Task | Status |
|------|------|--------|
| **Gemini** | Review proposed information architecture for 5-area layout (Dashboard, My Territory, Employer Research, Organizing Targets, Data Explorer) | |
| **Claude Code** | Implement new navigation structure, split existing 4 screens into 5 areas incrementally | |
| **Codex** | Review for UX consistency, broken links, state management across new navigation | |

---

## Quick Reference: Who Does What

| Tool | Role | When | Total Sessions |
|------|------|------|----------------|
| **Gemini** | Research ahead of implementation | Before Claude Code starts each task | ~10-12 sessions |
| **Claude Code** | All implementation (scripts, API, frontend, tests) | Core work | Every task |
| **Codex** | Code review after each batch | After Claude Code finishes each batch | ~10-12 sessions |

## Recommended Batch Schedule

| Batch | Claude Code Builds | Gemini Researches (for next batch) | Codex Reviews (previous batch) |
|-------|-------------------|-----------------------------------|-------------------------------|
| 1 | 4.1 SEC EDGAR | 4.2 IRS BMF, 4.3 CPS, 4.4 OEWS | Phase 3 code (if not yet reviewed) |
| 2 | 4.2 IRS BMF | 5.2 NAICS hierarchy, 5.5 propensity model lit review | 4.1 SEC EDGAR |
| 3 | 4.3 CPS + 4.4 OEWS | 7.1 scraper targets, 7.2 state PERB | 4.2 IRS BMF |
| 4 | 5.1 Decay + 5.2 NAICS + 5.3 Versioning | 7.3 union-lost literature | 4.3 + 4.4 |
| 5 | 5.4 Gower + 5.5 Propensity model | 7.4 board report format | 5.1-5.3 |
| 6 | 6.1 Docker + 6.2 CI/CD | — | 5.4 + 5.5 |
| 7 | 6.3-6.5 Scheduling + scripts + indexes | — | 6.1 + 6.2 |
| 8 | 7.1 Scrapers + 7.2 PERB | — | 6.3-6.5 |
| 9 | 7.3-7.6 Remaining intelligence | — | 7.1 + 7.2 |

---

*Created: February 15, 2026*
*Status: Phases 1-3 COMPLETE. Phase 4 ready to start.*
