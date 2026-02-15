# Labor Relations Research Platform — Unified Roadmap v2
**Date:** February 15, 2026
**Supersedes:** ROADMAP.md (Feb 14), LABOR_PLATFORM_ROADMAP_v12.md (Feb 8), EXTENDED_ROADMAP.md, ROADMAP_TO_DEPLOYMENT.md v3.0
**Based on:** Three Round 2 Audits (Claude, Codex, Consolidated), Matching Improvement Plan, Historical Employer Analysis, GitHub Ecosystem Survey, Business Classification Methods Research, AFSCME Case Study, NY Density Map Methodology, Mergent Pipeline Docs, Teamsters Comparison Report

---

## How to Read This Document

This roadmap consolidates **16 source documents** spanning audits, implementation plans, research notes, and aspirational ideas into a single actionable plan. It is organized into:

1. **Current State** — What exists today, honestly assessed
2. **Document Conflicts** — Where sources disagree and what I recommend
3. **Phase 1: Fix What's Broken** — Immediate bugs and integrity issues
4. **Phase 2: Matching & Data Quality** — The matching pipeline overhaul
5. **Phase 3: New Data Sources** — External data that unlocks new capabilities
6. **Phase 4: Frontend Redesign** — From monolith to modern application
7. **Phase 5: Scoring Model** — From heuristic to empirical
8. **Phase 6: Deployment & Operations** — Making it production-ready
9. **Phase 7: Intelligence Layer** — Forward-looking features
10. **Dependency Map** — What blocks what
11. **Source Document Index** — What each source contributed

---

## Current State (February 15, 2026)

### What's Working Well (all three auditors agree)

- **60,000-orphan fix is the biggest win.** Every employer-union relationship now resolves. This was the #1 crisis from Round 1.
- **9-factor SQL scorecard** via materialized view (`mv_organizing_scorecard`). 24,841 establishments scored. No score drift between list and detail. Supports `REFRESH CONCURRENTLY`.
- **Frontend decomposed** from 10,506-line monolith to 12 focused files. All API connections verified working.
- **Match rates dramatically improved:** OSHA 47.3% (current employers), WHD 16.0%, 990 11.9%, NLRB 28.7%, SAM 7.5%.
- **165 automated tests** covering matching, scoring, API, auth, and data integrity.
- **Security posture improved:** Password removed, CORS locked, JWT system built, parameterized queries throughout.
- **ULP integration** surfaces unfair labor practice history in scorecard.
- **Data freshness tracking** across 15 sources with admin endpoints.

### Platform Metrics

| Metric | Value |
|--------|-------|
| Database size | ~20 GB (includes ~12 GB GLEIF raw schema) |
| Tables | 160 (public) + 9 (gleif schema) = 169 total |
| Views | 186 |
| Materialized views | 4 |
| Total rows | ~23.9M (public) / ~76.7M (including GLEIF schema) |
| API endpoints | 152 across 17 routers |
| Tests | 165/165 passing |
| F7 employers (current) | 60,953 |
| F7 employers (total incl. historical) | 113,713 |
| Python scripts | ~494 in scripts/ |
| Frontend files | 12 (2,160 HTML + 10 JS + 1 CSS) |

### What's Broken Right Now

| Issue | Severity | Source |
|-------|----------|--------|
| 3 density endpoints crash (500 errors) | CRITICAL | Codex only (smoke tests) |
| Auth disabled by default (fail-open) | CRITICAL | All three auditors |
| 824 union file number orphans (worsened from 195) | HIGH | All three auditors |
| 29 scripts have literal-string password bug | HIGH | Claude only |
| GLEIF raw schema still ~12 GB | HIGH | Codex only |
| NAICS coverage 37.7% of current employers | MEDIUM | Claude |
| 299 unused indexes consuming 1.67 GB | MEDIUM | Claude |
| README 55% accurate | MEDIUM | Claude + Codex |
| 150+ tables never analyzed | MEDIUM | Claude + Codex |
| modals.js at 2,598 lines (secondary monolith) | MEDIUM | Claude |
| Frontend still has dual-score remnants | LOW | Codex |

### Sprints 1-6 Status: COMPLETE

All original sprints 1-6 from the Feb 14 roadmap are done:
- Sprint 1: Orphan fix (60K->0), password removal
- Sprint 2: JWT auth, CORS lockdown
- Sprint 3: Scorecard MV, admin refresh, FK indexes
- Sprint 4: 97 new tests (matching + scoring + data integrity)
- Sprint 5: ULP integration, data freshness tracking
- Sprint 6: Frontend split, score explanations API, F7 blind spot banner

---

## Document Conflicts and Recommendations

### Conflict 1: Match Rate Denominators

**Claude** reports OSHA match rate as 47.3% (denominator: 60,953 current employers).
**Codex** reports 25.37% (denominator: 113,713 all employers including historical).

**Recommendation:** Both are correct. Report both numbers in different contexts:
- **For organizers:** Use current-employer rates (47.3% OSHA, 16.0% WHD, 11.9% 990). These reflect what an organizer actually sees when researching active targets.
- **For auditing/completeness:** Use all-employer rates (25.37% OSHA). This is honest about the full table coverage.
- **In the API:** Return `match_rate_current` and `match_rate_total` as separate fields.

### Conflict 2: WHD/990 Matching — Fixed or Broken?

**Claude:** WHD "FIXED" (F7->WHD improved from 2% to 16%). 990 "FIXED" (14K matches via dedicated table).
**Codex:** WHD "STILL BROKEN" (Mergent->WHD only 2.47%). 990 "STILL BROKEN" (only 69 Mergent 990 matches).

**Recommendation:** Claude is correct. Codex measured the wrong pathway. The F7-to-WHD matching pipeline (the one organizers use) genuinely improved 8x. Codex checked Mergent-to-WHD, which was never the primary match path. Similarly, 990 matching works through its own `national_990_f7_matches` table, not through `mergent_employers.matched_990_id` (which is vestigial). Mark these as **IMPROVED**, not "fixed" or "broken." The Mergent columns should be deprecated or removed to prevent future confusion.

### Conflict 3: Scoring Systems — Unified or Dual?

**Claude:** "FIXED" — unified 9-factor MV scorecard in SQL.
**Codex:** "STILL BROKEN" — frontend JavaScript still has 0-62 sector score and 0-100 OSHA score references.

**Recommendation:** The backend IS unified. The frontend has dead code remnants from the old scoring system that should be cleaned up but aren't causing user-facing bugs. This is a cleanup task, not a architectural problem. The AFSCME case study doc and Mergent pipeline doc both reference the old "6-factor" scoring — these docs are simply outdated.

### Conflict 4: GLEIF Storage — 396 MB or 12 GB?

**Claude:** GLEIF "PARTIALLY FIXED" — public schema GLEIF tables consolidated to 396 MB.
**Codex:** GLEIF still ~12 GB across 9 tables in a separate `gleif` schema.

**Recommendation:** Both are correct — they looked at different schemas. The `gleif.*` schema (discovered only by Codex) contains raw corporate ownership data that is almost certainly not needed for the organizer-facing platform. The distilled `gleif_us_entities` table (379K rows, 310 MB in public schema) is what the crosswalk actually uses. **Archive or drop the raw gleif schema to reclaim ~12 GB.** This would cut the database nearly in half.

### Conflict 5: NAICS Coverage

**Claude:** Only 37.7% of F7 employers have NAICS codes.
**Codex:** 94.46% NAICS coverage.

**Recommendation:** Different populations. Claude checked current employers specifically relevant to scoring. Codex checked all employers including historical ones that got NAICS backfilled. For scoring purposes, Claude's number is what matters — 62% of scoreable employers can't get industry-density scores. **Backfill NAICS from OSHA matches (71.8% have naics_code) as a quick win.**

### Conflict 6: NLRB Participant Orphans (92.34%)

**Codex + Summary:** Flagged 1.76M orphaned NLRB participants as CRITICAL.
**Claude:** Did not flag this.

**Recommendation:** This is structurally expected, not a bug. The `nlrb_participants` table contains ALL case participants (ULP cases, representation cases, etc.), not just election participants. Most NLRB case numbers reference non-election proceedings that don't appear in `nlrb_elections`. However, this IS a real limitation for organizer research — participant-to-election joins miss most records. **Create a unified NLRB view** that explicitly bridges case types and documents the structural gap.

### Conflict 7: Outdated Source Documents

Several source documents contain claims that are now incorrect:

| Document | Outdated Claim | Current Reality |
|----------|---------------|-----------------|
| MERGENT_SCORECARD_PIPELINE.md | References `labor_api_v6.py`, 6-factor scoring, NY-only scope | API is modular (17 routers), 9-factor scoring, national scope |
| README.md | `labor_search_api:app`, `frontend/` directory, 6-factor scorecard | `api.main:app`, `files/` directory, 9-factor scorecard |
| AFSCME_NY_CASE_STUDY.md | "6-factor scoring system (0-100)", `/api/targets/search` | 9-factor system, endpoint doesn't exist |
| EXTENDED_ROADMAP.md | Lists checkpoints H-O as all pending | H (Mergent), I (990), J (SEC), K (OSHA) largely done |
| LABOR_PLATFORM_ROADMAP_v12.md | "0-62 point scale across six factors" | 9-factor, score range 10-78, avg 32.3 |
| AFSCME scraper prompt | Hardcoded password in connection string | Password removed from all code |

**Recommendation:** These documents should be treated as historical artifacts, not current references. The new roadmap below supersedes all of them. Add `[HISTORICAL]` banners to the old docs.

---

## Phase 1: Fix What's Broken (Week 1)
**Goal:** Zero crashes, zero critical security issues, zero data integrity regressions
**Effort:** 2-3 days

### 1.1 Fix 3 crashing density endpoints
**Source:** Codex smoke tests (CRITICAL)
**The bug:** `density.py` uses tuple-style indexing (`row[0]`) against `RealDictCursor` (which returns dicts). Three endpoints crash with `KeyError: 0`.
**Files:** `api/routers/density.py` lines ~212, ~363, ~593
**Fix:** Change all positional indexing to named key access (`row['column_name']`).
**Time:** 2-4 hours including regression tests.

### 1.2 Run ANALYZE on full database
**Source:** Claude + Codex (MEDIUM — but takes 2 minutes)
**The issue:** 150-170 tables have never been analyzed. PostgreSQL is guessing about query plans.
**Fix:** `ANALYZE;` (single command, whole database)
**Time:** 2 minutes.

### 1.3 Fix the 29 literal-string password bug scripts
**Source:** Claude (HIGH)
**The bug:** `password="os.environ.get('DB_PASSWORD', '')"` sends the literal text as the password.
**Fix:** Replace with `from db_config import get_connection` in each file.
**Time:** 4-8 hours.

### 1.4 Investigate and fix 824 union file number orphans
**Source:** All three auditors (HIGH)
**The issue:** Historical employer import added employers referencing old unions not in `unions_master`.
**Investigation:** Are these defunct locals that should be added, or genuinely broken references?
**Time:** 4-8 hours.

### 1.5 Backfill NAICS from OSHA matches
**Source:** Claude (MEDIUM)
**The issue:** Only 37.7% of current employers have NAICS codes, crippling industry-density scoring.
**Fix:** Single UPDATE joining `f7_employers_deduped` -> `osha_f7_matches` -> `osha_establishments` where `naics_code IS NOT NULL`.
**Time:** 2-4 hours including scorecard refresh.

### 1.6 Clean up frontend dual-score remnants
**Source:** Codex
**Fix:** Remove old 0-62 and 0-100 score references from `scorecard.js`.
**Time:** 1-2 hours.

### 1.7 Documentation refresh
**Source:** All three auditors
- README.md: Fix startup command, correct `frontend/` -> `files/`, update to 9-factor scorecard, list actual endpoint count (152), add deployment checklist
- CLAUDE.md: Update router count (17), MV row counts, add `gleif` schema note
- ROADMAP.md: Mark Sprint 7.2 PK task as DONE, update test counts
- Add `[HISTORICAL - See Roadmap 2_15v2.md]` banners to: MERGENT_SCORECARD_PIPELINE.md, AFSCME_NY_CASE_STUDY.md, EXTENDED_ROADMAP.md, LABOR_PLATFORM_ROADMAP_v12.md
**Time:** 2-4 hours.

### 1.8 Archive or drop GLEIF raw schema
**Source:** Codex
**The issue:** 9 tables totaling ~12 GB in `gleif.*` schema. Only `gleif_us_entities` (public schema, 310 MB) is used by the platform.
**Fix:** `pg_dump` the gleif schema to a compressed file, then `DROP SCHEMA gleif CASCADE`.
**Time:** 4-8 hours (including verification that nothing breaks).

---

## Phase 2: Matching Pipeline Overhaul (Weeks 2-5)
**Goal:** Standardized, auditable, improvable matching across all data sources
**Effort:** 3-4 weeks
**Source:** `improving matching implementation_2_15.md` (primary), audit findings, classification methods research

This phase implements the matching improvement plan with adjustments based on audit findings and the "Every Method for Classifying Businesses" research.

### 2.1 Standardize match output schema (Week 2)
Every match across every source pair should produce a consistent record:

```
source_system, source_id, target_system, target_id,
method, tier, score, confidence, confidence_band (HIGH/MEDIUM/LOW),
run_id, matched_at, evidence_json
```

**Files to create/modify:**
- `scripts/matching/matchers/base.py` — base match result class
- `scripts/matching/config.py` — centralized threshold policy
- `scripts/matching/pipeline.py` — unified pipeline runner

**New tables:** `match_runs`, `match_run_results`

### 2.2 Normalize all name-matching paths (Week 2)
**The problem from the audits:** Normalization is inconsistent across matchers. The `employer_name_aggressive` field uses one normalization, OSHA matching uses another, Mergent uses a third.
**Fix:** One canonical normalizer with three levels: `standard`, `aggressive`, `fuzzy`. All matchers use the same normalizer. Test that normalization is idempotent.

### 2.3 Improve deterministic matching (Week 2-3)
- Add deterministic tie-breakers for one-to-many candidates (state exact > city exact > higher score > newest source row)
- Strengthen address-tier evidence for auditability
- Persist ALL match attempts (accepted, rejected, review-needed), not just accepted

### 2.4 Splink fallback for unresolved cases (Week 3)
**Source:** Matching improvement plan + classification methods research
Route only unresolved and conflict cases to Splink (probabilistic matching). Don't replace the deterministic pipeline — augment it.
- Per-scenario Splink thresholds (not one global threshold)
- Tag all Splink results with `source_method = SPLINK` and persist probability
- Track handoff counts per scenario

### 2.5 Match quality monitoring (Week 3-4)
**New script:** `scripts/maintenance/matching_quality_dashboard.py`
- Match rate by scenario, by tier, by confidence band
- False-positive sample rate for fuzzy tiers
- Unresolved rate trend
- State-level variance alerts

### 2.6 API match explainability (Week 4)
Add `match_method`, `confidence_band`, and top evidence fields to employer detail, OSHA, WHD, and corporate API responses. Organizers should see **why** a match exists, not just that it does.

### 2.7 NLRB linkage bridge (Week 4-5)
**Source:** Codex + Summary (flagged 92.34% orphan rate)
Create a unified NLRB view that:
- Bridges participants to elections through case numbers
- Explicitly documents which case types (ULP, RC, RD, RM) are expected NOT to have election records
- Provides a clean API surface for "this employer's NLRB history"
- Addresses the missing columns issue (employer_name, city, state not in `nlrb_elections`)

### 2.8 Historical employer matching (Week 5)
**Source:** HISTORICAL_EMPLOYER_ANALYSIS.md
The 52,760 historical employers have zero external references. Options:
- **Recommended:** Run matching against OSHA/WHD/990 for historical trend analysis ("which employers lost their unions?"). This adds strategic value.
- Merge the 4,942 aggressive-name+state overlaps after manual review
- Keep `is_historical` flag for filtering

---

## Phase 3: New Data Sources (Weeks 4-8)
**Goal:** Ingest the highest-value external data that the audits and research identified as missing
**Effort:** 3-5 weeks
**Sources:** Extended roadmap, compass artifact (GitHub ecosystem), audit recommendations

### 3.1 SEC EDGAR Full Index (HIGH priority)
**Source:** Audit recommendations, compass artifact
**Tool:** `edgartools` (1,400 GitHub stars, native Python)
**Value:** 300K+ public companies with CIK numbers. Critical finding from compass artifact: some XBRL filings include `EntityTaxIdentificationNumber` (EIN), enabling direct CIK-to-EIN matching.
**Data to extract:** Company names, CIK, EIN (where available), employee counts, SIC codes, human capital disclosures from 10-K Item 1
**Impact:** Would dramatically improve corporate crosswalk coverage (currently only 4,891 SEC CIK matches)
**Time:** 8-12 hours

### 3.2 IRS Business Master File (HIGH priority)
**Source:** Audit recommendations
**Value:** All nonprofit organizations with EIN, name, NTEE code, and ruling date. The current 990 matching covers only filers (586K). The BMF covers all tax-exempt organizations (~1.8M).
**Impact:** Would improve 990 match rates from 11.9% to potentially 25%+
**Tool:** ProPublica Nonprofit Explorer API or IRS bulk data
**Time:** 10-14 hours

### 3.3 CPS Microdata via IPUMS (MEDIUM priority)
**Source:** Classification methods research, roadmap v12
**Value:** Granular union density at industry x geography x occupation level — far more detailed than the published BLS rates currently used in the scorecard
**Tool:** `ipumspy` Python package (free)
**Impact:** Transforms the `industry_density` scoring factor from a crude 2-digit NAICS lookup to precise density estimates. Addresses the "granularity gap" identified in the classification methods doc.
**Time:** 15-20 hours

### 3.4 OEWS Staffing Patterns (MEDIUM priority)
**Source:** Classification methods research
**Value:** Occupation mix by NAICS industry. Enables "cosine similarity of workforce composition" — two employers with different NAICS codes but similar worker types are comparable for organizing purposes.
**Impact:** Enhances employer similarity scoring beyond NAICS codes alone
**Time:** 10-14 hours

### 3.5 State PERB Data — NY, CA, IL (LOW priority, unique contribution)
**Source:** Compass artifact ("zero open-source coverage on GitHub")
**Value:** Public employment relations board data fills the F7 blind spot for public-sector employers (documented in Sprint 6's F7 coverage banner)
**Risk:** No existing scrapers/tools. Original development required. Data format varies by state.
**Time:** 20-30 hours per state

### 3.6 labordata.org Integration (MEDIUM priority)
**Source:** Compass artifact
**Value:** The `labordata` GitHub organization maintains nightly-refreshed pipelines for NLRB, WHD, OSHA, OLMS, and FMCS data. Their `nlrb-data` repo uses PLpgSQL — direct PostgreSQL integration.
**Why this matters:** Instead of maintaining our own ETL for NLRB/WHD/OSHA, we could sync from their pipeline. This would give us daily-refreshed data instead of static snapshots.
**Risk:** Dependency on external maintainer (Forest Gregg / DataMade)
**Time:** 8-12 hours for initial integration, minimal ongoing maintenance

### 3.7 Remaining Mergent Sectors
**Source:** MERGENT_SCORECARD_PIPELINE.md
**Status:** Museums sector done (243 employers). 11 remaining sectors totaling 10,000-15,000 employers.
**Note:** The Mergent pipeline doc is outdated (references old API, 6-factor scoring, NY-only scope). The pipeline architecture is sound but needs updating to use the current 9-factor national scorecard and db_config.py for connections.
**Time:** 15-20 hours (mostly CUNY library access + CSV processing)

### Data Sources NOT Recommended (deprioritized)

| Source | From | Why Deprioritize |
|--------|------|-----------------|
| FMCS contract expirations | Extended roadmap | Already compiled at bargainingforthecommongood.org |
| FEC/OpenSecrets PAC data | Gemini audit, extended roadmap | Interesting but tangential to core organizing use case. Adds complexity without directly improving target identification. |
| News/media monitoring (GDELT) | Gemini audit, compass artifact | Requires ongoing API costs, event extraction is noisy, and organizing intelligence is better served by structured NLRB/FMCS data |
| Company description embeddings | Classification methods research | Powerful in theory, but requires web scraping company descriptions at scale. Gower distance + NAICS hierarchy covers 80% of the value at 10% of the effort. Revisit after Phase 5 (scoring model). |

---

## Phase 4: Frontend Redesign (Weeks 6-12)
**Goal:** From test harness to decision-ready application
**Effort:** 5-8 weeks

This is the biggest architectural decision ahead. The current frontend works but was built incrementally as a testing tool, not designed as a user application.

### Current Frontend Assessment

**What exists (from Sprint 6):**
- 2,160 lines HTML + 10 JS files + 1 CSS file (~10,695 total lines)
- 3 modes: Territory, Search, Deep Dive
- 15+ modals (modals.js alone is 2,598 lines — a secondary monolith)
- 103 inline `onclick` handlers
- All functions global, plain `<script>` tags (not ES modules)
- No framework, no build system, no component model
- Leaflet maps, Chart.js visualizations

**What works well:**
- All 59 `API_BASE` references connect to real endpoints (zero broken wiring)
- `API_BASE` uses `window.location.origin` (deployment-aware)
- Score explanations come from server (not duplicated client-side)
- F7 blind spot banner documents public-sector coverage gap

**What doesn't work well:**
- **Navigation is developer-oriented, not organizer-oriented.** The current modes (Territory/Search/Deep Dive) are technical categories, not organizing workflows.
- **The modals are doing too much.** Analytics, scorecard, corporate family, comparison, elections, public sector, trends — these should be first-class views, not modals.
- **No state management.** Global `let` variables in `config.js`. State is scattered across files. Back/forward navigation doesn't work.
- **No component reuse.** The employer detail panel, score display, match evidence display, and data source badges are all hand-coded HTML strings.
- **Mobile is broken.** No responsive design. Leaflet maps and data tables overflow on small screens.
- **Export is limited.** No "evidence packet" export for campaign use (flagged by Codex in Sprint 9).
- **No user preferences.** Can't save territories, bookmark employers, or track campaign progress.

### Recommended Approach: Incremental Modernization (not full rewrite)

I **disagree** with the ROADMAP.md suggestion of waiting for "React/Vue SPA (when team grows)." The current codebase is maintainable enough to modernize incrementally without a framework migration. A full React rewrite would take 4-6 weeks and produce a less stable result than improving what exists. Here's why:

1. The current architecture **works.** Zero broken API connections. All modes functional.
2. The 10-file split (Sprint 6) already created a modular-enough structure.
3. ES modules can be adopted file-by-file without a build system.
4. The biggest UX problems are **information architecture**, not technology — reorganizing what's a modal vs. a page, improving navigation flow, adding responsive CSS.

However, I **agree** with the LABOR_PLATFORM_ROADMAP_v12.md's Phase 4 vision of "Task 4.4: Union-first navigation" — starting with "Select your union" instead of forcing users to search. That's the right UX direction.

### 4.1 Information Architecture Redesign (Week 6-7)

Replace the current 3-mode structure with an organizer-centric navigation:

**Current:** Territory | Search | Deep Dive
**Proposed:**
```
Dashboard (landing)
  -> My Territory (select union, see coverage map + KPIs)
  -> Employer Research (search, detail, corporate family)
  -> Organizing Targets (scorecard, comparables, evidence)
  -> Data Explorer (density, trends, elections, analytics)
  -> Admin (data freshness, MV refresh, auth)
```

This maps directly to how an organizing director actually works:
1. "What's my territory?" (Dashboard + My Territory)
2. "Tell me about this employer" (Employer Research)
3. "Who should I organize next?" (Organizing Targets)
4. "What's the big picture?" (Data Explorer)

### 4.2 Promote Modals to Pages (Week 7-8)

The current modal architecture puts too much behind too many clicks. Promote these to first-class pages/views:

| Current Modal | Proposed | Why |
|--------------|----------|-----|
| Scorecard modal | Organizing Targets main view | This is the core value proposition — shouldn't be a modal |
| Corporate Family modal | Employer Research sub-view | Too much data for a modal overlay |
| Analytics modal | Data Explorer sub-view | Charts and tables need full screen |
| Comparison modal | Organizing Targets sub-view | Side-by-side comparison needs space |
| Elections modal | Data Explorer sub-view | Time series data needs full width |
| Trends modal | Data Explorer sub-view | Same reason |

**Keep as modals:** Quick employer detail popup, data freshness info, settings, help.

### 4.3 Split modals.js (Week 7)

The 2,598-line modals.js must be broken up regardless of other redesign choices:
- `modal-employer-detail.js` — employer detail popup
- `modal-corporate.js` — corporate family tree
- `modal-analytics.js` — analytics charts
- `modal-comparison.js` — employer comparison
- `modal-elections.js` — NLRB election data
- `modal-shared.js` — shared modal utilities (open, close, overlay)

### 4.4 ES Modules Migration (Week 8-9)

Migrate from plain `<script>` tags + global functions to ES modules:
- Add `type="module"` to script tags
- Convert global functions to named exports
- Replace inline `onclick` handlers with `addEventListener`
- Import dependencies explicitly

This is the single biggest maintainability improvement. It eliminates the global namespace pollution and makes dependencies explicit. Can be done file-by-file.

### 4.5 Responsive CSS (Week 9-10)

**Source:** All three auditors flagged mobile as broken
- Add CSS Grid/Flexbox layout replacing absolute positioning
- Collapse sidebar on small screens
- Touch-friendly map controls
- Data tables scroll horizontally on mobile
- Score cards stack vertically

### 4.6 Evidence Packet Export (Week 10-11)

**Source:** Codex (Sprint 9.6), AFSCME case study
Generate a downloadable bundle per employer:
- Safety record (OSHA violations, penalties, recency)
- Wage theft history (WHD cases, back wages)
- Election history (NLRB cases, win/loss, vote counts)
- Corporate family (parent, subsidiaries, other locations)
- Comparable employers (Gower similarity matches)
- Score breakdown with explanations

Output: PDF for presentations + CSV for data analysis

### 4.7 URL-Based State Management (Week 11-12)

Every view should have a URL. Currently, navigating to an employer detail or switching modes doesn't update the URL, so:
- Back/forward buttons don't work
- You can't share links to specific views
- Bookmarks are useless

Implement hash-based routing (`#/targets?state=NY&tier=TOP`) that encodes current view + filters.

### Frontend: What I Recommend Against

| Suggestion | Source | Why I Disagree |
|-----------|--------|---------------|
| React/Vue SPA rewrite | ROADMAP.md "Future" section | Too expensive, breaks working code, introduces build system complexity. Not justified for a single-developer project. |
| Redux/Zustand state management | ROADMAP.md "Future" section | Overkill. Simple module-scoped state with URL sync is sufficient for this app's complexity level. |
| TypeScript migration | Common suggestion | The JS codebase is <11K lines. TypeScript would add build complexity without proportional benefit at this scale. |

---

## Phase 5: Scoring Model Evolution (Weeks 10-14)
**Goal:** From hand-tuned heuristic to empirically validated model
**Effort:** 3-5 weeks
**Sources:** Classification methods research, roadmap v12 Phase 3, audit recommendations

### 5.1 Temporal Scoring Decay (Week 10)
**Source:** Claude audit (Sprint 9.4)
A 2025 OSHA violation should matter more than a 2015 one. Add exponential decay:
```
weight = exp(-lambda * years_since_violation)
```
Apply to: OSHA violations, WHD cases, NLRB elections. Lambda tuned per factor.

### 5.2 Hierarchical NAICS Similarity (Week 10-11)
**Source:** Classification methods research
Replace binary NAICS matching with prefix-length scoring:
- Same 6-digit: 1.00
- Same 5-digit: 0.85
- Same 4-digit: 0.65
- Same 3-digit: 0.40
- Same 2-digit: 0.20

This alone transforms the `industry_density` factor from "same 2-digit NAICS yes/no" to a gradient.

### 5.3 Gower Distance Enhancement (Week 11-12)
**Source:** Classification methods research (highest-priority recommendation)
The platform already has Gower similarity (Phase 3 of old roadmap — `employer_comparables` table with 270K rows). Enhance it:
- Add weighted dimensions: industry (3x), OSHA violations (2x), state (1x), size (1x)
- Compute "distance from nearest unionized sibling" as a scoring factor
- Return top-5 comparable unionized employers in the API

### 5.4 Propensity Score Model (Week 12-14)
**Source:** Classification methods research (the single most powerful enhancement)
Fit a logistic regression: P(unionized | employer features) using known outcomes from NLRB elections (33,096 elections).

Features: NAICS code, employee count, state, metro area, industry union density, government contractor status, OSHA violation rate.

The predicted probability for non-union employers **IS** the organizing opportunity score. This replaces hand-picked weights with empirically optimal ones.

Prerequisites: Match rates improved (Phase 2), NAICS backfilled (Phase 1.5), temporal split (pre-2022 train, 2022+ test).

Success criteria: AUC > 0.65 → publish. AUC < 0.55 → rebuild features.

### 5.5 Score Model Versioning (Week 14)
**Source:** Codex (Sprint 9.3)
Add `score_version` column to materialized scorecard. Track methodology changes in a `score_versions` table. Display: "Scored using methodology v2.1 (Feb 2026)".

---

## Phase 6: Deployment & Operations (Weeks 8-12)
**Goal:** Make the platform accessible, reliable, and maintainable
**Effort:** 2-3 weeks (overlaps with Phase 4)

### 6.1 Production Auth Enforcement
**Source:** All three auditors (CRITICAL)
- Require `LABOR_JWT_SECRET` in production mode (startup hard-fail if missing)
- Bootstrap admin user creation flow
- Add rate limiting to all endpoints (not just login)

### 6.2 Docker Setup
**Source:** Claude + Gemini audits
```
Dockerfile (Python 3.12, not 3.14)
docker-compose.yml (API + PostgreSQL + nginx)
Volume mount for .env and data directory
Health check endpoint already exists
```

### 6.3 CI/CD Pipeline
**Source:** Claude + Gemini audits
GitHub Actions:
- Run `pytest tests/ -v` on push
- Lint on PR
- Optional: deploy on merge to main (Railway/Render)

### 6.4 Database Migration Tooling
**Source:** Gemini audit
- Evaluate Alembic for schema migrations
- Create initial migration from current schema
- Document "how to add a new table" workflow

### 6.5 Automated Scheduling
**Source:** All three auditors (no scheduling exists)
- Weekly MV refresh (`mv_organizing_scorecard`, `mv_employer_search`)
- Weekly data freshness check
- Weekly `ANALYZE` on hot-path tables
- Database backup schedule

### 6.6 Script Lifecycle Management
**Source:** Codex (494 scripts, inconsistent lifecycle hygiene)
- Create `scripts/PIPELINE_MANIFEST.md` documenting the blessed rebuild order
- Tag scripts as `active`, `legacy`, or `experimental`
- Move deprecated scripts to `archive/scripts/`
- Fix remaining 315 scripts to use `db_config.get_connection()`

### 6.7 Drop Unused Indexes
**Source:** Claude audit
- Query `pg_stat_user_indexes` for `idx_scan = 0`
- Identify 21 confirmed duplicate indexes (176 MB)
- `DROP INDEX CONCURRENTLY` for confirmed unused/duplicate
- Verify query performance doesn't regress
- `VACUUM FULL` on affected tables
- Target: reclaim 1.67 GB

---

## Phase 7: Intelligence Layer (Weeks 14+)
**Goal:** Forward-looking features that transform the platform from retrospective analysis to strategic intelligence
**Effort:** Ongoing

These are ideas drawn from the research documents that are valuable but depend on earlier phases being complete.

### 7.1 Web Scraper Pipeline Expansion
**Source:** AFSCME scraper prompt, Teamsters comparison report
The AFSCME scraper (295 profiles, 103 sites crawled, 160 employers extracted) proved the concept. Expand to:
- Teamsters (338 official locals, 10 US gaps identified)
- SEIU, UFCW, UNITE HERE
- Use the two-step architecture: Crawl4AI fetches, Claude Code extracts
- Match extracted employers against `f7_employers_deduped`

### 7.2 State PERB Data (Original Contribution)
**Source:** Compass artifact
No open-source tools exist for state public employment relations board data. Building scrapers for NY PERB, CA PERB, and IL ILRB would be the first of its kind and directly addresses the F7 blind spot for public-sector employers.

### 7.3 "Union-Lost" Analysis
**Source:** Historical employer analysis
The 52,760 historical employers represent bargaining units that once had union contracts but no longer do. Matching them against OSHA/NLRB/WHD could answer: "Which employers decertified? What happened to working conditions after the union left?"

### 7.4 Board Report Generation
**Source:** LABOR_PLATFORM_ROADMAP_v12.md Task 4.3
One-click PDF/CSV exports for union board presentations:
- Territory overview (organized vs. non-organized)
- Top targets with evidence
- Trend charts (membership, elections, violations)
- Data freshness statement

### 7.5 Occupation-Based Similarity
**Source:** Classification methods research
Use BLS OEWS staffing patterns to compare employers by **workforce composition** rather than just NAICS code. Two employers with different NAICS codes but similar occupation mixes (lots of warehouse workers, lots of truck drivers) are highly comparable for organizing purposes. Compute cosine similarity of occupation vectors.

---

## Dependency Map

```
Phase 1 (Fix Broken)
  |
  |---> Phase 2 (Matching) <--- depends on 1.5 (NAICS backfill)
  |       |
  |       |---> Phase 5 (Scoring) <--- depends on 2.x (improved match quality)
  |       |
  |       |---> Phase 3 (New Data) <--- independent, can overlap with Phase 2
  |               |
  |               |---> Phase 5 (Scoring) <--- uses new data as features
  |
  |---> Phase 4 (Frontend) <--- independent of Phase 2/3
  |       |
  |       |---> Phase 7 (Intelligence) <--- needs frontend views
  |
  |---> Phase 6 (Deployment) <--- independent, can overlap with Phase 4
          |
          |---> Phase 7 (Intelligence) <--- needs stable deployment
```

**Critical path:** Phase 1 -> Phase 2 -> Phase 5
**Parallel track:** Phase 4 (frontend) can proceed independently
**Can start any time:** Phase 6 (deployment)
**Depends on everything:** Phase 7 (intelligence)

---

## Effort Summary

| Phase | Effort | Weeks | Key Deliverable |
|-------|--------|-------|-----------------|
| 1: Fix Broken | 2-3 days | 1 | Zero crashes, zero critical bugs |
| 2: Matching | 3-4 weeks | 2-5 | Standardized, auditable matching pipeline |
| 3: New Data | 3-5 weeks | 4-8 | SEC EDGAR + IRS BMF + CPS microdata |
| 4: Frontend | 5-8 weeks | 6-12 | Organizer-centric UI with responsive design |
| 5: Scoring | 3-5 weeks | 10-14 | Propensity score model replacing heuristics |
| 6: Deployment | 2-3 weeks | 8-12 | Docker + CI/CD + automated scheduling |
| 7: Intelligence | Ongoing | 14+ | Web scrapers, PERB data, board reports |

**If you had one focused week:** Phase 1 resolves every critical issue.
**If you had one month:** Phase 1 + Phase 2 (matching) + start Phase 4 (frontend).
**If you had three months:** All of Phases 1-6, start Phase 7.

---

## Source Document Index

| Document | Key Contribution to This Roadmap |
|----------|--------------------------------|
| `ROADMAP.md` (Feb 14) | Sprint status, priority framework, architecture decisions |
| `AUDIT_REPORT_ROUND2_CLAUDE.md` | Data quality findings, match rates, missing indexes, documentation accuracy |
| `AUDIT_REPORT_ROUND2_CODEX.md` | Density endpoint crashes, GLEIF raw schema discovery, smoke test methodology |
| `three_audit_comparison_r2.md` | Conflict resolution between auditors, unified priority list, one-week action plan |
| `improving matching implementation_2_15.md` | Phase 2 matching pipeline design (6-phase plan) |
| `HISTORICAL_EMPLOYER_ANALYSIS.md` | Historical employer overlap analysis, resolution options |
| `LABOR_PLATFORM_ROADMAP_v12.md` | Plain-language 4-phase vision (Phase 4 frontend ideas) |
| `EXTENDED_ROADMAP.md` | Checkpoint system for data sources (H-O), integration priority matrix |
| `MERGENT_SCORECARD_PIPELINE.md` | Sector pipeline architecture, remaining sectors list |
| `Every Method for Classifying Businesses.txt` | Gower distance, propensity scoring, NAICS hierarchy, occupation-based similarity |
| `compass_artifact...md` | GitHub ecosystem survey (labordata, edgartools, Splink, openFEC) |
| `AFSCME_NY_CASE_STUDY.md` | Demonstrated target identification workflow, scoring methodology |
| `NY_DENSITY_MAP_METHODOLOGY.md` | Density estimation methodology, auto-calibration approach |
| `TEAMSTERS_COMPARISON_REPORT.md` | Web scraper validation methodology, data quality findings |
| `afscme_scraper_claude_code_prompt_v2_maxplan.md` | Two-step scraper architecture (fetch + AI extract) |
| `docs/README.md` | What documentation looks like when it drifts (cautionary example) |

---

*This roadmap is a living document. Update it after each work session. When a phase completes, move its items to a "Completed" section rather than deleting them.*
