# Honest Assessment & Comprehensive Roadmap: From Now to Deployable

**Date:** February 9, 2026
**Version:** 3.0 (supersedes v2.0, incorporates SCORECARD_IMPROVEMENT_ROADMAP.md and "Every Method for Classifying Businesses")
**Perspective:** Written as if advising a union president
**Scope:** Current state audit + complete technical roadmap to publication-ready deployment

---

## Table of Contents

1. [Honest Assessment](#honest-assessment-if-i-were-a-union-president)
2. [Architecture Overview (As-Is)](#architecture-overview-as-is)
3. [Phase 0: Stabilize What Exists](#phase-0-stabilize-what-exists) -- COMPLETE
4. [Phase 1: Clean the Foundation](#phase-1-clean-the-foundation) -- COMPLETE
5. [Phase 2: Upgrade the Scorecard](#phase-2-upgrade-the-scorecard-quick-wins)
6. [Phase 3: Employer Similarity Engine](#phase-3-employer-similarity-engine-gower-distance)
7. [Phase 4: Improve Match Rates](#phase-4-improve-match-rates)
8. [Phase 5: Architecture for Deployment](#phase-5-architecture-for-deployment)
9. [Phase 6: Build the Decision Interface](#phase-6-build-the-decision-interface)
10. [Phase 7: Publication Readiness](#phase-7-publication-readiness)
11. [Phase 8: Post-Launch Growth](#phase-8-post-launch-growth-ongoing)
12. [Summary Timeline](#summary-timeline)
13. [Current Data Inventory](#current-data-inventory-february-2026)
14. [Complete Database Schema Reference](#complete-database-schema-reference)
15. [Script Inventory & Pipeline Map](#script-inventory--pipeline-map)
16. [Technical Debt Registry](#technical-debt-registry)
17. [Decision Log & Architectural Choices](#decision-log--architectural-choices)
18. [Risk Register](#risk-register)
19. [New Data to Collect](#new-data-to-collect)
20. [Appendix A: What I'd Cut / What I'd Never Cut](#appendix-a-what-id-cut--what-id-never-cut)
21. [Appendix B: Cost Projections](#appendix-b-cost-projections)
22. [Appendix C: Glossary](#appendix-c-glossary)

---

## Honest Assessment: If I Were a Union President

### What I'd Say to My Executive Board

**"We have something genuinely remarkable here -- and it's getting better fast."**

### The Good (and it's legitimately good)

**The data is real and validated.** 14.5 million members counted, validated against the BLS within 1.4%. Fifty out of 51 states reconciled against EPI benchmarks within 15%. If someone challenged our numbers, we could defend them.

**The coverage is extraordinary.** 60,953 deduplicated employers. 2.2 million OSHA violations worth $3.52 billion in penalties. 363,000 wage theft cases totaling $4.7 billion in backwages. 33,000 NLRB elections. GLEIF corporate ownership chains with 498,963 parent-child links. USASpending federal contractor data. IRS 990 nonprofit financials. This is 90+ database tables with genuine cross-referencing, backed by a 33GB PostgreSQL database.

**The data quality is strong.** As of February 9, 2026:
- NAICS coverage: 99.2% (up from 92.3%)
- Geocoding: 99.8% (up from 86%)
- Union hierarchy: 100% coverage, zero orphans (up from 68%)
- Sector classification: 100% clean, zero cross-contamination
- Duplicates: 1,210 merges completed with zero errors
- Validation suite: 9/9 checks passing with drift detection
- 32/32 automated tests passing (20 API + 12 data integrity)
- BLS alignment: 98.6% (within 1.4%)

**The matching is sophisticated.** Splink probabilistic linking, RapidFuzz composite scoring (0.35xJaroWinkler + 0.35xtoken_set_ratio + 0.30xfuzz.ratio), cleanco name normalization, pg_trgm candidate retrieval. Corporate identifier crosswalk: 14,561 multi-source employer identities (up from 3,010 baseline -- 383% growth).

### What Still Needs Work

**1. Nobody can use this but the person who built it.** It runs on one Windows laptop, `localhost:8001`. No login, no deployment, no URL anyone else can visit.

**2. The scorecard needs upgrading.** The 8-factor, 0-62 point system works but treats each factor independently with hand-picked weights. It doesn't ask the most useful question: "Which non-union employers look the most like employers that already have unions?" The weights haven't been validated against real outcomes.

**3. OSHA/WHD/990 match rates are low.** Most employers have blank violation sections:

| Data Source | Records | Matched to F7 | Rate |
|---|---|---|---|
| OSHA | 1,007,217 | 79,981 | 7.9% |
| WHD Wage Theft | 363,365 | ~17,000 | ~4.8% |
| IRS 990 (National) | 586,767 | 0 | 0.0% |
| Mergent | 56,431 | ~3,400 | ~6.0% |

**4. The frontend is a prototype.** `organizer_v5.html` is a single 476KB file with 8,841 lines of inline JavaScript. It works but can't scale.

**5. No data pipeline.** Every data source was loaded manually. No orchestration, no scheduling.

### The Bottom Line

**What we have:** The most comprehensive labor relations dataset I've seen, with validated methodology, sophisticated entity resolution, and strong data quality foundations.

**What we still need:** A smarter scorecard, better match rates, deployment infrastructure, and a real interface.

**Remaining work to deployable:** ~200-250 hours. Phases 0 and 1 are done (saved ~60 hours from original estimate).

---

## Architecture Overview (As-Is)

### System Diagram

```
+---------------------------+       +----------------------------+
|  organizer_v5.html        |       |  Developer's Laptop        |
|  (476KB monolith)         |       |  (Windows 11)              |
|  Tailwind CSS (CDN)       |       |  Python 3.14               |
|  Leaflet.js (CDN)         |  HTTP |  PostgreSQL 17             |
|  Chart.js (CDN)           | <---> |  33GB database             |
|  MarkerCluster (CDN)      |       |  440 Python scripts        |
|  8,841 lines inline JS    |       |  102 SQL files             |
+---------------------------+       +----------------------------+
                                           |
                                    +------+------+
                                    |             |
                              labor_api_v6.py   start-claude.bat
                              (6,642+ lines)    (batch launcher)
                              142 endpoints
                              FastAPI + psycopg2
                              Port 8001
                              Connection pooling (ThreadedConnectionPool)
                              No auth, no TLS
```

---

## Phase 0: Stabilize What Exists -- COMPLETE

**Status: DONE (February 9, 2026)**

All items completed:
- [x] Credentials extracted to `.env` + `db_config.py`
- [x] Hardcoded passwords removed from all files
- [x] Password scrubbed from git history
- [x] `.gitignore` audit complete
- [x] Pushed to GitHub (private repo: `JacobWebsite/TheOrganizer-Labor-Research-Platform`)
- [x] `pyproject.toml` with 12 runtime + 4 dev dependencies
- [x] `scripts/setup/init_database.py` for DB verification
- [x] Connection pooling via `ThreadedConnectionPool` with `@contextmanager` wrapper
- [x] 20 API integration tests + 12 data integrity tests (32/32 passing)
- [x] Union search: `include_historical` filter, `q` parameter alias

**Commit:** `f8aaaf6` (Phase 0), `0374ddb` (union search fix)

---

## Phase 1: Clean the Foundation -- COMPLETE

**Status: DONE (February 9, 2026)**

All items completed:
- [x] **1.1 Duplicate Resolution:** Zero exact dupes, 102 near-dupe groups reviewed (all legitimate -- generic trade names). Previous Splink sprint: 1,210 merges with zero errors.
- [x] **1.2 NAICS Backfill:** 4,208 employers filled via 4-tier strategy (Mergent crosswalk, OSHA pg_trgm, union peer inference, keyword patterns). Coverage: 92.3% -> 99.2%. Script: `scripts/etl/backfill_naics.py`
- [x] **1.3 Geocoding:** 8,444 employers filled via city centroid + state centroid fallback. Coverage: 86% -> 99.8%. Script: `scripts/etl/geocode_backfill.py`
- [x] **1.4 Union Hierarchy:** 8,598 orphans resolved (5,605 locals linked to parents, all count_members=FALSE). Coverage: 68% -> 100%. Script: `scripts/etl/fix_union_hierarchy.py`
- [x] **1.5 Sector Audit:** Zero RLA in PRIVATE, zero NULL/UNKNOWN. 20 PUBLIC_SECTOR with OPEIU/UE verified legitimate. Clean.
- [x] **1.6 Validation Suite:** 9 checks + drift detection. Baselines for 17 tables. Script: `scripts/validation/run_all_checks.py`

**Commit:** `11f8a95` (Phase 1 complete)

---

## Phase 2: Upgrade the Scorecard (Quick Wins)

*Adapted from SCORECARD_IMPROVEMENT_ROADMAP.md "Option A." These are SQL-level changes to the existing scoring logic -- no new libraries needed, immediate impact. This comes BEFORE the similarity engine because it improves the individual score components that the similarity engine will later use.*

**Estimated: 15-25 hours**

### 2.1 Hierarchical NAICS Scoring (4 hrs)

**Problem:** The current scorecard treats NAICS as binary -- either two employers share the same code or they don't. A hospital and a nursing home are "different industries" even though they employ similar workers.

**Fix:** Replace binary NAICS matching with graduated scoring based on shared prefix length:

| Match Level | Score | Example |
|---|---|---|
| Same 6-digit NAICS | 10/10 | General freight (484121) vs general freight (484121) |
| Same 5-digit | 8.5/10 | General freight (484121) vs specialized freight (484122) |
| Same 4-digit | 6.5/10 | General freight (4841) vs used goods transport (4842) |
| Same 3-digit | 4/10 | Truck transport (484) vs school bus (485) |
| Same 2-digit | 2/10 | Trucking (48) vs warehousing (49) -- same supersector |
| Different sector | 0/10 | Trucking (48) vs software (51) |

**Implementation:** Modify the scoring SQL in `labor_api_v6.py` (lines ~4571, ~4682). The `score_industry_density` calculation currently just checks if industry density exceeds thresholds. Add a sub-score for NAICS proximity to industry peers.

**Data needed:** The existing `naics` column on `f7_employers_deduped` (99.2% populated) is sufficient. Current data is all 2-digit, which limits the hierarchical granularity. See [New Data to Collect](#new-data-to-collect) for upgrading to 6-digit NAICS via OSHA/Mergent inheritance.

### 2.2 OSHA Violation Normalization (4 hrs)

**Problem:** The current `score_osha_violations` (0-4 points) uses raw violation counts. This penalizes large employers unfairly and lets small ones off easy. A hospital with 10 violations might be perfectly average for hospitals, while a small office with 2 violations might be terrible.

**Fix:** Divide violations by industry average. An employer with 2x their industry's average violation rate scores higher than one with 0.5x, regardless of raw counts.

**Implementation:**
1. Download BLS Survey of Occupational Injuries and Illnesses (SOII) data -- free, published by NAICS at 2-6 digit levels
2. Create `bls_injury_rates` reference table (NAICS code -> average DART rate)
3. For each employer: `excess_violation_rate = employer_violations / industry_average`
4. Score: >3x average = 10/10, >2x = 8/10, >1.5x = 6/10, >1x = 4/10, <=1x = 2/10

**Data needed:** BLS SOII data (free download from bls.gov/iif). See [New Data to Collect](#new-data-to-collect).

### 2.3 Size Score Refinement (2 hrs)

**Problem:** Current `score_size` is simplistic: 10 if 100-500 employees, 5 if >25, else 2. Research (Farber 2001, Bronfenbrenner 2009) consistently shows smaller units have higher win probability, but the current scoring doesn't capture this well.

**Fix:** Use SBA size standards to normalize -- an employer at 2x its SBA threshold is "large for its industry" regardless of absolute employee count. Also incorporate the inverse relationship between unit size and win rate from academic research.

**Implementation:** Modify scoring SQL. New formula: score based on both absolute size (organizable threshold) and relative size (vs industry SBA standard).

### 2.4 Geographic Favorability Score (3 hrs)

**Problem:** Current `score_geographic` doesn't account for state labor law environment. Right-to-work states have measurably lower win rates (Bronfenbrenner 2009).

**Fix:** Add state-level favorability factors:
- Right-to-work status (binary, from NRTW.org -- 27 states)
- State NLRB election win rate (from our 33K elections data)
- State union density (from BLS CPS)
- Local organizing infrastructure (number of union locals in the metro area, from our `unions_master` data)

**Implementation:** Create `state_labor_favorability` reference table. Combine into weighted geographic sub-score.

### 2.5 Sibling Employer Display (4 hrs)

**Problem:** The scorecard shows a number but no context. An organizer seeing "Score: 38" can't evaluate whether that's meaningful.

**Fix:** For each scored employer, show the 3-5 most similar *unionized* employers already in the database. This doesn't change the score -- it makes the existing score meaningful by showing *who* the comparable employers are.

**Implementation:** New SQL query joining the target's characteristics (NAICS, state, size bucket, violation profile) against unionized employers, ranked by how many characteristics match. New API endpoint: `GET /api/employers/{id}/siblings`. A day of work.

### 2.6 Re-Score All Employers (4 hrs)

After implementing 2.1-2.5:
- Re-run scoring across all 60,953 employers with improved factors
- Store in `employer_scores_v2` (keep v1 for comparison)
- Regenerate tier assignments (TOP/HIGH/MEDIUM/LOW)
- Refresh materialized views

**Phase 2 Deliverable:** A smarter scorecard with graduated industry matching, normalized violations, refined size scoring, geographic favorability, and sibling employer context. All built on existing SQL -- no new libraries.

---

## Phase 3: Employer Similarity Engine (Gower Distance)

*Adapted from SCORECARD_IMPROVEMENT_ROADMAP.md "Option B" and "Every Method for Classifying Businesses." This adds the "how similar is this employer to unionized ones" capability -- the single most impactful analytical upgrade.*

**Estimated: 30-40 hours**

### 3.1 Build the Unified Comparison Table (8 hrs)

Create a single table/materialized view where every employer (union and non-union) has the same set of columns:

| Column | Source | Type |
|---|---|---|
| NAICS 2-digit sector | F7, OSHA, Mergent | Category |
| Employee count (binned) | F7, Mergent, OSHA | Numeric |
| State | All sources | Category |
| Metro area (CBSA) | zip_geography | Category |
| Industry union density | BLS/density tables | Numeric (%) |
| OSHA excess violation rate | OSHA + BLS SOII | Numeric |
| Has government contracts | USASpending crosswalk | Binary |
| Has wage theft violations | WHD matches | Binary |
| Corporate hierarchy depth | GLEIF/crosswalk | Numeric |
| Revenue bucket | Mergent/990 | Numeric |
| Union status | F7, NLRB wins | Binary (the comparison target) |

**Why this step matters:** Gower distance needs all employers described in the same format. Right now data is spread across many tables. This is mostly SQL -- creating a materialized view that pulls everything together.

### 3.2 Gower Distance Computation (10 hrs)

**What it does:** For each non-union employer, find the 5 nearest unionized employers.

```python
import gower
# weight: industry 3x, size 2x, violations 2x, geography 1x, contracts 1x
distance_matrix = gower.gower_matrix(employer_df, weight=[3, 2, 2, 1, 1, 1, 1])
```

**Store results:**
```sql
CREATE TABLE employer_comparables (
    employer_id INTEGER REFERENCES f7_employers_deduped(employer_id),
    comparable_employer_id INTEGER,
    similarity_score FLOAT,
    rank INTEGER,
    shared_features TEXT[],  -- e.g., ['same_naics', 'same_state', 'similar_size']
    PRIMARY KEY (employer_id, rank)
);
```

Pre-compute for all 60,953 employers (batch process). The `gower` library handles missing data gracefully -- it skips missing features and compares on what's available.

**Key advantage:** This handles the messy government data reality where you're *always* missing something for some employers.

### 3.3 Similarity Score Integration (4 hrs)

For each non-union target, average the similarity to its 5 nearest unionized neighbors. That average becomes the similarity score (0-100). Options:
- **Option A:** Add as a new component alongside the existing 8-factor score
- **Option B:** Display separately as "Comparables Match Score"
- **Recommendation:** Option B for now -- keep the existing scorecard and add Gower similarity as a complementary signal. Merge them in Phase 8 when we have outcome validation data.

### 3.4 API Endpoints (4 hrs)

- `GET /api/employers/{id}/comparables` -- return top 5 similar unionized employers
- `GET /api/employers/{id}/comparables?features=naics,state` -- filter by specific features
- Include explanation: "This employer is similar because: same industry (NAICS 62), same state (NY), similar size (150-200 employees), both have OSHA violations above industry average"

### 3.5 Validation (4 hrs)

- Spot-check 50 employer-comparable pairs
- Verify intuitive sense: a non-union hospital should find similar unionized hospitals, not auto dealerships
- Measure diversity: are all comparables from the same state? (bad -- should be geographically diverse)
- If possible: show 20 results to an organizer and ask "do these make sense?"

**Phase 3 Deliverable:** For every employer, the platform can show: "This non-union employer is 87% similar to these 5 unionized employers, and here's why." This transforms the scorecard from a number into a story.

**What organizers see:**

> **ABC Healthcare Corp** -- Organizing Opportunity: 78%
> **Most similar unionized employers:** 1199SEIU at XYZ Hospital (91% match), AFSCME at DEF Nursing Home (87% match), SEIU at GHI Home Care (84% match)
> **Why:** Same industry, same state, similar size, similar violation profile
> **Key leverage:** 3 OSHA violations (2x industry average), $45K in backwages, $12M in NYC contracts

---

## Phase 4: Improve Match Rates

*The biggest data coverage gap. Better match rates mean more employers have complete profiles (violations, contracts, corporate structure), which makes both the scorecard and the similarity engine more accurate.*

**Estimated: 20-30 hours**

### 4.1 OSHA Matching Improvement (8 hrs)

Current: 7.9% (79,981 / 1,007,217). Target: > 20%.

**Problem:** OSHA establishment names are often abbreviated, use DBA names, or are site-specific ("WALMART STORE #4532" vs F7's "WAL-MART STORES INC").

**Strategy:**
1. **Corporate parent matching**: If OSHA establishment matches a Mergent/GLEIF subsidiary, inherit the F7 link from the crosswalk
2. **Address-first matching**: Match on street address + city + state (OSHA has physical workplace addresses)
3. **Aggressive name normalization**: Strip store numbers (`#\d+`), DBA prefixes, legal suffixes
4. **NAICS-constrained fuzzy**: Only fuzzy-match within same 2-digit NAICS to reduce false positives

Expected yield:
| Method | Additional | Running Total |
|---|---|---|
| Current | 79,981 | 79,981 (7.9%) |
| Corporate parent | ~15,000 | ~95,000 (9.4%) |
| Address matching | ~40,000 | ~135,000 (13.4%) |
| Name normalization | ~30,000 | ~165,000 (16.4%) |
| NAICS fuzzy | ~40,000 | ~205,000 (20.3%) |

### 4.2 WHD Matching Improvement (6 hrs)

Current: 4.8% (~17,000 / 363,365). Target: > 12%.

**Strategy:**
1. **Trade name matching**: Currently only matching on `legal_name`; add `trade_name` as fallback
2. **Mergent bridge**: Match WHD -> Mergent (by EIN or name+city), then Mergent -> F7 via crosswalk
3. **Address matching**: WHD has street addresses; match on address+city+state
4. **Lower threshold**: Reduce pg_trgm from 0.55 to 0.45 for WHD only (WHD names are noisier)

### 4.3 IRS 990 Matching (6 hrs)

Current: 0% (586,767 records, zero matched to F7). Largest untapped data source.

**Strategy:**
1. **EIN-based matching**: 990 filers have EIN; crosswalk has EIN for ~1,127 employers. Direct join.
2. **Name+state matching**: `organization_name` from 990 against `employer_name_aggressive` from F7
3. **Expected yield**: 990 filers are nonprofits (hospitals, universities, social services); F7 has significant nonprofit coverage. Estimate: 5,000-15,000 matches.
4. **Value add**: Revenue, total employees, executive compensation -- fields not available from any other source

### 4.4 Refresh Crosswalk and Views (4 hrs)

After match improvements:
- Update `corporate_identifier_crosswalk` with new links
- Refresh all materialized views
- Re-run validation suite to confirm no regressions
- Save new baselines

**Phase 4 Deliverable:** Match rates: OSHA > 20%, WHD > 12%, 990 > 1%. More employers have complete profiles, making the scorecard and similarity engine more accurate.

---

## Phase 5: Architecture for Deployment

*The hardest phase. This is where the laptop project becomes a deployable application.*

**Estimated: 50-60 hours**

### 5.1 API Restructure and Hardening (16 hrs)

**5.1.1 Split into modules (6 hrs)**
```
api/
  __init__.py
  main.py              # FastAPI app creation, middleware
  config.py            # Settings from environment
  database.py          # Connection pool, get_db dependency
  middleware/
    auth.py, rate_limit.py, logging.py
  routers/
    employers.py, unions.py, nlrb.py, osha.py,
    density.py, trends.py, lookups.py, organizing.py,
    corporate.py, sectors.py, admin.py
  models/
    schemas.py         # Pydantic response models
```

**5.1.2 Pagination** (4 hrs) -- All list endpoints: default 50, max 500

**5.1.3 Input validation** (3 hrs) -- Pydantic models, state/NAICS whitelists

**5.1.4 Error handling** (2 hrs) -- Consistent error responses, structured logging

**5.1.5 CORS lockdown** (1 hr) -- Whitelist specific origins

### 5.2 Authentication and Authorization (15 hrs)

- JWT (self-issued) for v1, OAuth in v2
- Roles: admin, organizer, viewer, api
- User management endpoints (register, login, refresh, API keys)

### 5.3 Deployment Infrastructure (16 hrs)

- Docker + docker-compose (API + Postgres + nginx)
- Railway or Render for v1 hosting (~$31-76/month)
- CI/CD: GitHub Actions (test on push, deploy on merge to main)
- Domain + HTTPS (Let's Encrypt)

### 5.4 Data Freshness Pipeline (8 hrs)

- ETL orchestrator (`scripts/etl/orchestrate.py`) with DAG runner
- Parameterize file paths (replace hardcoded Windows paths)
- Quarterly update schedule documented in `docs/DATA_UPDATE_GUIDE.md`

**Phase 5 Deliverable:** Platform accessible at a URL with HTTPS. Multiple users, role-based permissions. Modular, hardened API. Data pipeline documented and partially automated.

---

## Phase 6: Build the Decision Interface

*Now that the engine is deployed, build the dashboard organizers will actually use.*

**Estimated: 45-50 hours**

### 6.1 Frontend Architecture: HTMX + Jinja2 (4 hrs)

Recommended for: zero new languages (Python-only), no build step, server-rendered (fast, SEO-friendly), FastAPI has native Jinja2 support.

### 6.2 Territory Dashboard (14 hrs)

Primary landing page after login:
- Union-first entry point ("Who are you?" selector)
- Territory overview: organized vs non-organized, trend arrows, active NLRB elections
- Top targets list with scores, comparables count, violation highlights
- Territory map with clustered markers (Leaflet.js, already built)

### 6.3 Employer Deep-Dive Profile (12 hrs)

Single page per employer:
- **Header:** Name, address, NAICS, employee count, score badge, corporate parent
- **Score breakdown:** 8-bar chart with explanations for each factor
- **Comparables sidebar:** Top 5 similar unionized employers with similarity % and explanation
- **Violations tab:** OSHA timeline, WHD cases, local violations
- **NLRB history tab:** Elections, ULPs, voluntary recognition
- **Corporate structure tab:** Parent company, subsidiaries, federal contracts, 990 data

### 6.4 Search, Filtering, Export (10 hrs)

- Unified search (employers, unions, NLRB cases)
- Advanced filters (state, industry, tier, violations, contractor, size)
- CSV export, PDF employer profile, territory summary report

### 6.5 Mobile Responsiveness (4 hrs)

Responsive grid, collapsible navigation, touch-friendly map.

**Phase 6 Deliverable:** An organizing director can log in, see their territory, find top targets with evidence-backed scores and comparables, drill into employer profiles, and export reports for board meetings -- in under 5 minutes.

---

## Phase 7: Publication Readiness

**Estimated: 35-40 hours**

### 7.1 Documentation (8 hrs)
- User guide, data methodology page, FAQ

### 7.2 Developer Documentation (6 hrs)
- API docs (Swagger), ERD diagram, contribution guide

### 7.3 Data Methodology Audit (10 hrs)
- External review by 2-3 labor economists/researchers
- Data source provenance documentation

### 7.4 Performance and Stress Testing (8 hrs)
- `EXPLAIN ANALYZE` on 20 slowest queries, add missing indexes
- Load testing (locust/k6) -- target 50 concurrent users
- Uptime monitoring (UptimeRobot), error alerting (Sentry free tier)

### 7.5 Soft Launch and Feedback (6 hrs)
- 3-5 beta testers (union organizers/researchers)
- Structured feedback collection
- Issue triage and critical fixes

**Phase 7 Deliverable:** Platform is live, documented, performance-tested, validated by real users.

---

## Phase 8: Post-Launch Growth (Ongoing)

*These add value after the platform is live. Ordered by impact.*

### 8.1 Historical Outcome Validation and Predictive Model (20 hrs) -- HIGH PRIORITY

**Why this is Phase 8 and not Phase 2:** The SCORECARD_IMPROVEMENT_ROADMAP.md explicitly recommends deferring the predictive model until (a) the scoring components are improved (Phases 2-3), (b) more non-union employer data exists for contrast, and (c) match rates are higher so the model has richer features to work with. Without these prerequisites, a logistic regression would mostly learn "employers in New York with 100-500 employees in healthcare tend to be union" -- true but not actionable.

**When ready (after Phases 2-4 are complete):**
1. Build features-plus-outcome dataset from 33,096 NLRB elections
2. Temporal split: pre-2022 training (~25K), 2022-2024 test (~8K)
3. Evaluate current scorecard: AUC-ROC, precision@k
4. Factor importance: logistic regression + random forest
5. If AUC > 0.65: publish. If < 0.55: rebuild with data-derived weights.
6. Propensity score model: P(unionized | employer features) becomes the organizing opportunity score itself

**The ultimate goal** (from "Every Method for Classifying Businesses"):

```
Opportunity Score = 0.35 x Similarity + 0.35 x Vulnerability + 0.30 x Feasibility
```

Where Similarity = Gower distance to unionized peers, Vulnerability = violations + density + contracts, Feasibility = size + geography + prior elections. The 0.35/0.35/0.30 weights get replaced by empirically optimal weights from outcome validation.

### 8.2 Contract Expiration Tracking (15 hrs) -- HIGH
- FMCS database of CBA expiration dates
- #1 timing signal for organizing

### 8.3 Real-Time NLRB Monitoring (12 hrs) -- HIGH
- Daily scraper for new case filings
- Alert: "New election petition filed at [employer] in [city]"

### 8.4 CPS Microdata for Granular Density (10 hrs) -- MEDIUM
- IPUMS CPS microdata for custom union density at industry x geography x occupation intersections
- Solves the granularity gap (BLS only publishes at ~50 industry categories)
- Source: unionstats.com (Hirsch & Macpherson) -- most useful free resource

### 8.5 Occupation Mix Comparison (15 hrs) -- MEDIUM
- BLS OEWS staffing patterns: what SOC codes exist at each NAICS
- Two employers in different NAICS but with similar occupation mixes are comparable for organizing
- Uses cosine similarity on occupation vectors

### 8.6 State PERB Data Integration (20 hrs) -- MEDIUM
- Public Employment Relations Board data (state/local bargaining)
- Start with NY PERB, expand to CA, IL, NJ, OH

### 8.7 Political Contribution Integration (15 hrs) -- MEDIUM
- FEC PAC contributions, lobbying disclosures
- "This employer spent $500K lobbying against the PRO Act"

### 8.8 Text-Based Employer Embedding (20 hrs) -- FUTURE
- Sentence-BERT embeddings of company descriptions/job postings
- Cosine similarity between employer vectors for nuanced matching
- From "Every Method" research: outperforms NAICS for identifying comparable businesses
- Requires: company description data (LinkedIn profiles, websites, job postings)

### 8.9 Data-Driven Weight Optimization (10 hrs) -- FUTURE
- Once outcome data accumulates from real organizing campaigns
- Cross-validated logistic regression on win/loss outcomes
- Replaces hand-picked weights with empirically optimal ones

---

## Summary Timeline

| Phase | Hours | What You Get | Status |
|---|---|---|---|
| **0: Stabilize** | 32 | Secure, reproducible, testable, pooled | COMPLETE |
| **1: Clean Data** | 28 | 99%+ NAICS/geocode/hierarchy, validation suite | COMPLETE |
| **2: Scorecard Quick Wins** | 15-25 | Hierarchical NAICS, normalized OSHA, geographic favorability, siblings | **NEXT** |
| **3: Similarity Engine** | 30-40 | Gower comparables for every employer | |
| **4: Match Rates** | 20-30 | OSHA >20%, WHD >12%, 990 >1% | |
| **5: Architecture** | 50-60 | Deployed, authenticated, modular API | |
| **6: Interface** | 45-50 | Territory dashboard, employer profiles, export | |
| **7: Publication** | 35-40 | Documented, tested, user-validated | |
| **Total remaining** | **~200-250** | **Deployable for publication** | |

At 15 hrs/week: ~15 weeks (3.7 months)
At 10 hrs/week: ~22 weeks (5.5 months)
At 20 hrs/week: ~12 weeks (3 months)

Phases 2-4 are sequential (each builds on the prior). Phase 5 can overlap with 3-4. Phases 6-7 overlap naturally.

### Critical Path

```
Phase 2 (Scorecard) -> Phase 3 (Similarity) -> Phase 5.3 (Deploy)
    -> Phase 6 (Interface) -> Phase 7.5 (Soft Launch)
```

Phase 4 (Match Rates) can run in parallel with Phase 3 since they're independent data pipelines.

---

## Current Data Inventory (February 2026)

### Core Data Tables

| Source | Table | Records | Matched to F7 | Match Rate | Status |
|---|---|---|---|---|---|
| OLMS Unions | `unions_master` | 26,665 | -- | -- | Complete |
| F7 Employers | `f7_employers_deduped` | 60,953 | -- | -- | Deduplicated, 99.2% NAICS, 99.8% geocoded |
| F7 Relations | `f7_union_employer_relations` | 119,844 | -- | -- | Complete |
| NLRB Elections | `nlrb_elections` | 33,096 | 31,649 | 95.7% | Complete |
| NLRB Participants | `nlrb_participants` | 1,906,542 | 1,824,558 | 95.7% | Complete |
| OSHA Establishments | `osha_establishments` | 1,007,217 | 79,981 | 7.9% | **Needs improvement** |
| OSHA Violations | `osha_violations_detail` | 2,245,020 | via estab. | -- | Complete |
| WHD Wage Theft | `whd_cases` | 363,365 | ~17,000 | ~4.8% | **Needs improvement** |
| Mergent Intellect | `mergent_employers` | 56,431 | ~3,400 | ~6.0% | NY-biased |
| GLEIF Entities | `gleif_us_entities` | 379,192 | ~3,300 | ~0.9% | Complete |
| GLEIF Ownership | `gleif_ownership_links` | 498,963 | via entities | -- | Complete |
| SEC Companies | `sec_companies` | 517,403 | ~2,000 | ~0.4% | Complete |
| USASpending | `federal_contract_recipients` | 47,193 | 9,305 | 19.7% | Complete |
| IRS 990 (National) | `national_990_filers` | 586,767 | 0 | 0.0% | **NOT MATCHED** |
| QCEW | `qcew_annual` | 1,943,426 | 97.5% (ind.) | -- | Complete |
| Corporate Crosswalk | `corporate_identifier_crosswalk` | 14,561 | -- | -- | 383% growth from baseline |
| Corporate Hierarchy | `corporate_hierarchy` | 125,120 | -- | -- | Complete |
| Union Hierarchy | `union_hierarchy` | 26,665 | -- | -- | 100% coverage |

### Validation Status (February 9, 2026)

| Check | Status | Value |
|---|---|---|
| BLS Alignment | PASS | 98.6% (1.4% variance) |
| NAICS Coverage | PASS | 99.2% |
| Geocode Coverage | PASS | 99.8% |
| Hierarchy Coverage | PASS | 100% |
| Sector Completeness | PASS | 100% |
| Crosswalk Orphans | PASS | <40% orphan rate |
| No Exact Duplicates | PASS | 0 exact dupes |
| Materialized Views | PASS | All populated |
| Table Drift | PASS | All stable vs baseline |

---

## Complete Database Schema Reference

### Entity Relationship Overview

```
unions_master (26,665)
    |-- f_num (PK)
    |-- aff_abbr, union_name, members, sector
    |-- 1:M --> f7_union_employer_relations
    |-- 1:M --> lm_data (2.6M historical filings)
    |-- 1:1 --> union_hierarchy (level classification)

f7_employers_deduped (60,953)
    |-- employer_id (PK)
    |-- employer_name, city, state, naics, latest_unit_size
    |-- latitude, longitude (99.8% geocoded)
    |-- M:M --> unions via f7_union_employer_relations
    |-- 1:M --> osha_f7_matches --> osha_establishments
    |-- 1:1 --> corporate_identifier_crosswalk (14,561)
    |-- 1:M --> employer_comparables (Phase 3)
    |-- 1:M --> employer_review_flags

corporate_identifier_crosswalk (14,561)
    |-- f7_employer_id (FK)
    |-- gleif_lei, mergent_duns, sec_cik, ein
    |-- is_federal_contractor, federal_obligations, federal_contract_count
    |-- Links to: gleif_us_entities, mergent_employers, sec_companies

nlrb_elections (33,096)
    |-- case_number (PK)
    |-- employer_name, city, state
    |-- eligible_voters, votes_for, votes_against
    |-- union_won (BOOLEAN)
    |-- 1:M --> nlrb_participants, nlrb_tallies, nlrb_allegations

osha_establishments (1,007,217)
    |-- establishment_id (PK)
    |-- estab_name, city, state, naics
    |-- 1:M --> osha_violations_detail (2.2M)
    |-- M:1 --> f7_employers via osha_f7_matches

whd_cases (363,365)
    |-- case_id (PK)
    |-- trade_name, legal_name, name_normalized
    |-- city, state, naics_code
    |-- total_violations, civil_penalties, backwages_amount
```

### Matching Tier Breakdown (corporate_identifier_crosswalk)

| Tier | Method | Matches | Confidence |
|---|---|---|---|
| 1 | EIN exact (SEC<->Mergent) | 1,127 | HIGH |
| 2 | LEI exact (SEC<->GLEIF) | 84 | HIGH |
| 3 | Name+State (cleanco normalized) | 3,009 | MEDIUM |
| 4 | Splink probabilistic (JW>=0.88) | 1,552 | MEDIUM |
| 5 | USASpending exact name+state | 1,994 | HIGH |
| 6 | USASpending fuzzy (pg_trgm>=0.55) | 6,795 | MEDIUM |
| **Total** | | **14,561** | |

---

## Script Inventory & Pipeline Map

### Active Scripts by Category

| Category | Count | Key Scripts |
|---|---|---|
| **etl** | 52+ | `load_whd_national.py`, `load_gleif_bods.py`, `fetch_qcew.py`, `fetch_usaspending.py`, `backfill_naics.py`, `geocode_backfill.py`, `fix_union_hierarchy.py` |
| **matching** | 30 | `splink_pipeline.py`, `splink_config.py`, `splink_integrate.py` |
| **scoring** | 9 | `update_whd_scores.py`, `match_whd_to_employers.py`, `match_whd_tier2.py` |
| **cleanup** | 34 | `merge_f7_enhanced.py`, `link_multi_location.py` |
| **validation** | 2 | `run_all_checks.py`, `baselines.json` |
| **maintenance** | 95 | `refresh_materialized_views.py` |
| **tests** | 3 | `conftest.py`, `test_api.py` (20 tests), `test_data_integrity.py` (12 tests) |

### Critical Execution Order (Full Refresh)

```
1. ETL Stage (parallelizable)
   fetch_olms.py, extract_osha.py, load_whd_national.py,
   fetch_nlrb.py, fetch_qcew.py, fetch_usaspending.py

2. Matching Stage (sequential)
   splink_pipeline.py --scenario mergent_f7
   splink_pipeline.py --scenario gleif_f7
   splink_pipeline.py --scenario f7_self_dedup
   splink_integrate.py, match_whd_to_employers.py, match_whd_tier2.py

3. Consolidation Stage
   merge_f7_enhanced.py --source combined
   link_multi_location.py, build_crosswalk.py (refresh)

4. Quality Stage
   backfill_naics.py --apply
   geocode_backfill.py --apply
   fix_union_hierarchy.py --apply

5. Validation Stage
   run_all_checks.py --save-baseline
   refresh_materialized_views.py
```

---

## Technical Debt Registry

| ID | Severity | Description | Phase | Status |
|---|---|---|---|---|
| TD-01 | ~~CRITICAL~~ | ~~SQL injection via f-string WHERE clauses~~ | 0.1 | Pattern is safe-but-fragile (verified) |
| TD-02 | ~~CRITICAL~~ | ~~Hardcoded DB password~~ | 0.1 | FIXED -- `.env` + `db_config.py` |
| TD-03 | CRITICAL | Zero authentication on 142 endpoints | 5.2 | |
| TD-04 | HIGH | Permissive CORS (`allow_origins=["*"]`) | 5.1 | |
| TD-05 | HIGH | 6,642-line monolith API file | 5.1 | |
| TD-06 | HIGH | 476KB monolith frontend | 6.x | |
| TD-07 | ~~HIGH~~ | ~~No connection pooling~~ | 0.4 | FIXED -- ThreadedConnectionPool |
| TD-08 | HIGH | 11+ endpoints return unbounded results | 5.1 | |
| TD-09 | ~~HIGH~~ | ~~No dependency management~~ | 0.3 | FIXED -- pyproject.toml |
| TD-10 | HIGH | Project in Downloads folder | 5.3 | |
| TD-11 | ~~HIGH~~ | ~~No database backup strategy~~ | 0.2 | FIXED -- GitHub push |
| TD-12 | MEDIUM | IRS 990 national (586K) unmatched | 4.3 | |
| TD-13 | MEDIUM | OSHA match rate 7.9% | 4.1 | |
| TD-14 | MEDIUM | WHD match rate 4.8% | 4.2 | |
| TD-15 | ~~MEDIUM~~ | ~~43% employers missing geocodes~~ | 1.3 | FIXED -- 99.8% |
| TD-16 | ~~MEDIUM~~ | ~~8,000 employers missing NAICS~~ | 1.2 | FIXED -- 99.2% |
| TD-17 | MEDIUM | Scorecard weights unvalidated | 8.1 | Deferred (needs better data first) |
| TD-18 | MEDIUM | ETL hardcoded to Windows paths | 5.4 | |
| TD-19 | MEDIUM | 440 scripts with no orchestration | 5.4 | |
| TD-20 | MEDIUM | Silent exception swallowing | 5.1 | |
| TD-21 | MEDIUM | No request logging | 5.1 | |
| TD-22 | ~~LOW~~ | ~~No pytest tests~~ | 0.5 | FIXED -- 32/32 passing |
| TD-23 | LOW | No CI/CD pipeline | 5.3 | |
| TD-24 | LOW | Python 3.14-specific | 5.3 | Target 3.12 for Docker |
| TD-25 | LOW | No rate limiting | 5.1 | |

---

## Decision Log & Architectural Choices

### Decision 1: Scorecard Upgrade Sequencing

**Context:** Two documents (ROADMAP_TO_DEPLOYMENT v2.0 and SCORECARD_IMPROVEMENT_ROADMAP.md) had conflicting sequencing. v2.0 put predictive validation first (Phase 2.1); the scorecard roadmap recommended quick wins first.

**Decision (v3.0):** Follow the scorecard roadmap's sequence:
1. **Quick wins first** (Phase 2): Hierarchical NAICS, OSHA normalization, geographic favorability -- all SQL changes, no new libraries
2. **Gower similarity second** (Phase 3): The highest-leverage analytical upgrade
3. **Predictive model deferred** (Phase 8): Needs better data (improved match rates) and more non-union employer contrast

**Rationale:** Quick wins improve the scoring components that the similarity engine uses. The similarity engine needs match rates improved to have rich features. The predictive model needs both of these plus outcome data. Each layer builds on the prior.

### Decision 2: Frontend Technology
**Decision:** HTMX + Jinja2
**Rationale:** Python-only, no build step, FastAPI native support

### Decision 3: Authentication
**Decision:** JWT for v1, OAuth in v2

### Decision 4: Hosting
**Decision:** Railway or Render for v1 (~$31-76/month)

### Decision 5: Python Version
**Decision:** 3.12 for production deployment (not 3.14)

### Decision 6: Scorecard Scale
**Decision:** Keep 0-62 for now. If Phase 8.1 validates and rebuilds, normalize to 0-100.

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Scorecard validation fails (AUC < 0.55) | Medium | HIGH | Phase 8.1 includes rebuild path. Quick wins (Phase 2) add value regardless. |
| R-02 | Database too large for affordable hosting | Low | HIGH | Consider read replicas, partitioning, archiving pre-2015 data |
| R-03 | ~~Laptop failure before backup~~ | ~~Medium~~ | ~~CRITICAL~~ | MITIGATED -- pushed to GitHub |
| R-04 | Python 3.14 incompatibilities in production | Medium | MEDIUM | Target 3.12 for Docker |
| R-05 | Mergent data license restricts redistribution | Medium | MEDIUM | Check license terms before deploying Mergent fields |
| R-06 | IRS 990 matching yields < 1,000 results | Low | LOW | Still adds nonprofit revenue for matched employers |
| R-07 | No organizers want to test it | Low | HIGH | Pre-recruit beta testers before Phase 7 |
| R-08 | OSHA/WHD data freshness lapses | Medium | MEDIUM | Phase 5.4 pipeline with quarterly reminders |
| R-09 | Single-developer bus factor | HIGH | CRITICAL | Documentation (Phase 7.2), contribution guide |
| R-10 | Scope creep from Phase 8 features | Medium | MEDIUM | Phase 8 is explicitly post-launch |
| R-11 | F7 NAICS only 2-digit limits similarity precision | Medium | MEDIUM | Inherit 6-digit from OSHA/Mergent matches (Phase 4) |

---

## New Data to Collect

These are data sources referenced in the scorecard roadmap and "Every Method" document that are **not yet loaded:**

| Data Source | Purpose | Availability | Priority | Phase |
|---|---|---|---|---|
| **BLS SOII injury/illness rates** | OSHA violation normalization (violations / industry average) | Free: bls.gov/iif | HIGH | 2.2 |
| **Right-to-work state list** | Geographic favorability scoring | Free: nrtw.org (27 states) | HIGH | 2.4 |
| **SBA size standards by NAICS** | Normalize employer size by industry | Free: sba.gov/document/support-table-size-standards | MEDIUM | 2.3 |
| **CBSA/metro area mappings** | Geographic grouping for similarity engine | Free: Census Bureau | MEDIUM | 3.1 |
| **6-digit NAICS for F7 employers** | Better hierarchical scoring precision | Inherit from OSHA/Mergent matches | MEDIUM | 4.1 |
| **Unionstats.com granular density** | More detailed density than published BLS | Free: unionstats.com (Hirsch/Macpherson) | MEDIUM | 8.4 |
| **FMCS CBA expirations** | Contract expiration timing for organizing | Free: fmcs.gov | MEDIUM | 8.2 |
| **BLS OEWS staffing patterns** | Occupation mix comparison | Free: bls.gov/oes | LOW | 8.5 |
| **CPS microdata (IPUMS)** | Granular union density estimates | Free: ipums.org | LOW | 8.4 |
| **Company descriptions** | Text-based employer embedding | LinkedIn/websites (scraping) | LOW | 8.8 |

**Immediate action items for Phase 2:**
1. Download BLS SOII data -> `data/reference/bls_soii_rates.csv`
2. Create right-to-work state mapping -> `data/reference/rtw_states.csv`
3. Download SBA size standards -> `data/reference/sba_size_standards.csv`

---

## Appendix A: What I'd Cut / What I'd Never Cut

### Minimum Viable Deployment (~150 hours from current state)

1. **Do Phase 2** (scorecard quick wins) -- 20 hrs
2. **Skip Phase 3** (Gower similarity) -- implement post-launch
3. **Skip Phase 4** (match rate improvements) -- keep current rates
4. **Do Phase 5** (deployment) -- 55 hrs
5. **Do Phase 6 reduced** (basic dashboard, no PDF export) -- 35 hrs
6. **Do Phase 7 reduced** (README, no external audit) -- 15 hrs

That gives: deployed, authenticated, improved scorecard, basic dashboard at a URL.

### What I'd Never Cut

- **Phase 2** (scorecard quick wins) -- immediate value, low effort
- **Phase 5.1-5.3** (API hardening, auth, deployment) -- no auth = no deployment
- **Phase 7.5** (user feedback) -- building without talking to organizers = tools that die unused

---

## Appendix B: Cost Projections

### Monthly Hosting Costs

| Component | Cost/month |
|---|---|
| API server (2 vCPU, 4GB RAM) | $15-25 |
| PostgreSQL (33GB, 4GB RAM) | $15-50 |
| Domain + HTTPS | $1 + free |
| Monitoring (UptimeRobot + Sentry) | Free |
| **Total** | **$31-76/month** |

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **F7** | OLMS Form LM-7 -- union filing listing employers they have contracts with |
| **OLMS** | Office of Labor-Management Standards (DOL) |
| **LM** | Form LM-2/3/4 -- annual union financial disclosure |
| **BLS CPS** | Bureau of Labor Statistics Current Population Survey |
| **EPI** | Economic Policy Institute |
| **NLRB** | National Labor Relations Board |
| **WHD** | Wage and Hour Division (DOL) |
| **OSHA** | Occupational Safety and Health Administration |
| **GLEIF** | Global Legal Entity Identifier Foundation |
| **QCEW** | Quarterly Census of Employment and Wages (BLS) |
| **Splink** | Probabilistic record linkage library (DuckDB backend) |
| **pg_trgm** | PostgreSQL trigram extension for fuzzy matching |
| **cleanco** | Python library for normalizing company names |
| **RapidFuzz** | Fast fuzzy string matching library |
| **Gower Distance** | Similarity metric for mixed data types (categorical + numeric) |
| **AUC-ROC** | Area Under ROC curve -- model quality (0.5 = random, 1.0 = perfect) |
| **NAICS** | North American Industry Classification System (2-6 digit) |
| **SOC** | Standard Occupational Classification (6-digit occupation codes) |
| **SOII** | Survey of Occupational Injuries and Illnesses (BLS) |
| **DART** | Days Away, Restricted, or Transferred (OSHA injury metric) |
| **SBA** | Small Business Administration (102 size standard levels by NAICS) |
| **CBSA** | Core Based Statistical Area (387 metro areas) |
| **UEI** | Unique Entity Identifier (replaced DUNS in 2022) |
| **DUNS** | Dun & Bradstreet Universal Numbering System |
| **LEI** | Legal Entity Identifier (20-char global company ID) |
| **CIK** | Central Index Key (SEC company identifier) |
| **EIN** | Employer Identification Number (IRS tax ID) |
| **FMCS** | Federal Mediation and Conciliation Service |
| **RLA** | Railway Labor Act |
| **ULP** | Unfair Labor Practice |
| **VR** | Voluntary Recognition |
| **BU** | Bargaining Unit |

---

*This document supersedes ROADMAP_TO_DEPLOYMENT.md v2.0 and incorporates SCORECARD_IMPROVEMENT_ROADMAP.md (Option A/B sequencing) and "Every Method for Classifying Businesses" (Gower Distance, propensity scoring, occupation mix, text embedding recommendations).*

*The SCORECARD_IMPROVEMENT_ROADMAP.md remains the detailed reference for scoring methodology. "Every Method for Classifying Businesses" remains the research reference for classification approaches.*

*Last updated: February 9, 2026*
