# Master Roadmap: The Organizer Platform
## Complete Implementation Plan | February 23, 2026

**Synthesized from:** Four-Audit Synthesis v3, Unified Platform Redesign Spec, Research Agent Implementation Plan, Workforce Estimation Model Plan, CBA Extraction Tool, and all session documentation.

**Budget target:** <$500 additional spend (primarily Claude API for research agent)

**Critical constraint:** Fuzzy matching and Splink re-runs are the most time-consuming operations (hours per source). The roadmap sequences these carefully to avoid redundant re-runs.

---

## How to Read This Document

- **USER DECISION** markers indicate places where you must make a choice before work can proceed
- **TIME BOTTLENECK** markers indicate Splink/fuzzy matching operations that take hours
- **BUDGET IMPACT** markers indicate tasks with API or infrastructure costs
- Each phase has clear entry criteria, exit criteria, and estimated effort
- Phases are ordered by dependency — later phases build on earlier ones
- Parallel tracks are marked when tasks can run simultaneously

---

## What Already Exists (Don't Rebuild)

Before planning what to build, here's what's already working:

| Component | Status | Details |
|-----------|--------|---------|
| React Frontend (Phases 1-6) | COMPLETE | Auth, Search, Profile, Targets, Union Explorer, Admin. 134 tests pass. |
| Backend API | COMPLETE | 144 endpoints, 20 routers, FastAPI on port 8001 |
| Matching Pipeline | COMPLETE | 6-tier deterministic + Splink + trigram. 1,738,115 match log entries. |
| Scoring System | WORKING (with issues) | 8 factors, percentile tiers. Math correct but 3-4 factors broken (see Phase 1). |
| Master Employer Table | SEEDED | 2,736,890 records (after dedup). Source IDs: 3,080,492. |
| CBA Extraction Tool | SCAFFOLDED | Schema live, processor working, 208 provisions extracted from test doc. API endpoints exist. |
| Backend Tests | 492 total | 491 pass, 1 skip |
| Frontend Tests | 134 total | All pass |
| Database | 9.5 GB | PostgreSQL `olms_multiyear`, 207+ tables |

---

## Decision Register (All Decisions in One Place)

Every decision you need to make, when you need to make it, and what it affects.

### Decisions Needed Before Phase 1 (Data Trust)

| # | Decision | Options | Recommendation | Blocks |
|---|----------|---------|----------------|--------|
| D1 | **Name similarity floor** | 0.70 / 0.75 / 0.80 / 0.85 | Test on 100-match sample first. Start with 0.75 as hypothesis. | Phase 1.4, Phase 2 (all re-runs) |
| D2 | **What does "Priority" mean?** | A: Structural only (current) / B: Structural + recent activity | B (require recent activity signals) — see note below | Phase 1.6 tier logic |

> **D2 Critical Context:** 92.7% of Priority employers have zero enforcement data. More importantly, among employers with actual union election wins since 2023, Priority captured only **125 wins** (1.5%) while "Low" had 392 wins (4.8%). The current tier system is ranking *strategic positioning* (big employer + growing industry + union nearby) rather than *actionable intelligence* (recent activity signals). Option B would require at least one recent enforcement or election data point to qualify for Priority, which would dramatically shrink the Priority tier but make it far more useful.
| D3 | **Minimum factors for top tiers** | 2 (spec) / 3 for Priority (Codex fix) / 3 for Priority+Strong | Keep Codex's 3 for Priority, extend 3 to Strong | Phase 1.6 |
| D4 | **Handle 29,236 stale OSHA matches** | Bulk-reject now / Re-run OSHA matching entirely | Bulk-reject now (1 hour), re-run after Splink retune (Phase 2) | Phase 1.4 |
| D5 | **score_similarity** | Remove from weighted formula / Keep and fix pipeline | Remove until coverage >10%. Investigate pipeline separately in Phase 1B. | Phase 1.2 |
| D6 | **Keep Codex's audit changes?** | Keep both / Review and modify | Keep both (Priority guardrail + admin hardening) | Already applied |
| D7 | **Empty columns on f7_employers_deduped** | Populate / Remove | Remove `naics_detailed` and `cbsa_code`. Keep `corporate_parent_id` as placeholder. | Phase 1.7 |

### Decisions Needed Before Phase 3 (Frontend Fixes)

| # | Decision | Options | Recommendation | Blocks |
|---|----------|---------|----------------|--------|
| D8 | **Legacy frontend** | Archive immediately / Keep as fallback | Archive after Phase 3 verifies React works correctly | Phase 3.6 |
| D9 | **User data storage** | Keep localStorage / Move to server-side | Plan server-side before production. Keep localStorage for now. | Phase 7 (deployment) |

### Decisions Needed Before Phase 5 (Research Agent)

| # | Decision | Options | Recommendation | Blocks |
|---|----------|---------|----------------|--------|
| D10 | **Web search API for research agent** | Claude built-in / Tavily ($0.001/search) / Exa.ai / SerpAPI ($50/mo) | Claude built-in (zero additional cost). Upgrade later if quality insufficient. | Phase 5.1 |
| D11 | **Dossier detail level** | Full (all 7 sections) / Tiered (quick scan + full on request) | Tiered — matches existing Deep Dive spec (Step 1 fast, Step 2 background) | Phase 5.1 |
| D12 | **Where does research agent run?** | CLI first / FastAPI background task / Celery worker | CLI first, then FastAPI background task. You're the only user now. | Phase 5.1 |
| D13 | **Claude autonomy level** | High / Guided / Scripted with escape hatch | Guided autonomy — recommended order, can deviate with explanation | Phase 5.1 |

### Decisions Needed Before Phase 6 (Workforce Estimation)

| # | Decision | Options | Recommendation | Blocks |
|---|----------|---------|----------------|--------|
| D14 | **Estimation precision target** | Store as point estimate / Store as distribution (range) | Store as median + range. Display median prominently, range as confidence indicator. | Phase 6 schema |

### Decisions Needed Before Phase 4 (CBA Tool)

| # | Decision | Options | Recommendation | Blocks |
|---|----------|---------|----------------|--------|
| D15 | **OCR approach for scanned PDFs** | Docling (open source, free) / Mistral OCR (API, ~$0.01/page) | Start with Docling (free). Fall back to Mistral if quality is poor. | Phase 4.1 |

### Decisions That Can Wait

| # | Decision | When Needed | Options |
|---|----------|-------------|---------|
| D16 | Research agent scoring weights | Before Phase 5.3 | Coverage-first / Quality-first / Balanced |
| D17 | Human grading of research runs | Before Phase 5.3 | Fully auto / Auto + 10% human audit / Human only |
| D18 | Gold standard set size | Before Phase 5.3 | 10 / 15 / 25-30 companies |
| D19 | Query refinement depth | Before Phase 5.4 | Template selection only / Templates + mutation |
| D20 | Fix scoring vs expand scoring first | Before Phase 2B | Fix first (recommended) / Expand first |
| D21 | Archive/GLEIF dump | Before Phase 7 (deployment) | Move to external storage / Keep in place |
| D22 | Public sector adaptation timing | After Phase 3 | Build during Phase 6 / Defer to post-launch |

---

## Budget Breakdown

| Category | Estimated Cost | When |
|----------|---------------|------|
| Claude API for research agent R&D (100 runs) | $50-150 | Phases 5.1-5.3 |
| Claude API for research agent ongoing (200 runs) | $100-200/month | Phase 5+ |
| Geocoding API (38,486 addresses) | $0 (Census geocoder is free) | Phase 2A |
| OCR for CBA tool | $0 (Docling) or ~$20 (Mistral for 2000 pages) | Phase 4 |
| Search API upgrade (if needed) | $0-50 | Phase 5+ |
| **Total R&D** | **$50-220** | |
| **Total ongoing (per month)** | **$100-200** | |

Well under the $500 cap. The ongoing cost is the research agent API usage.

---

# THE PHASES

---

## Phase 0: Quick Wins & Infrastructure (Week 1)

**No decisions needed. No dependencies. Do all of these immediately.**

These are high-impact, low-effort fixes that every auditor flagged. Each takes minutes to hours.

### 0.1 Database Backup Strategy
- Set up nightly `pg_dump | gzip` script
- Store to a second drive or cloud storage
- **Why first:** 11 GB database, months of irreproducible work, zero backup currently
- **Effort:** 1-2 hours
- **Exit criteria:** Automated nightly backup running, verified restore tested once

### 0.2 Add Missing Database Index
- `CREATE INDEX idx_nlrb_participants_case_number ON nlrb_participants(case_number);`
- 1.9M rows, currently no index — every JOIN does a full table scan
- Single biggest performance win across the platform
- **Effort:** 5 minutes (the index build itself takes ~30 seconds)

### 0.3 Fix Blocking MV Refreshes
- Add `CONCURRENTLY` keyword to 2 scripts:
  - `update_whd_scores.py` (refreshes `mv_employer_search`)
  - `compute_gower_similarity.py` (refreshes `mv_employer_features`)
- **Why:** Without this, the Admin Panel refresh buttons will freeze the entire database
- **Effort:** 5 minutes each

### 0.4 Fix Search API Silent Failure
- Add parameter validation to employer search endpoint
- Unknown parameters (e.g., `?q=walmart` instead of `?name=walmart`) should return error, not all 107K records
- **Effort:** 30 minutes

### 0.5 Fix Data Freshness Table
- Populate all 19 sources with real `last_updated` dates and `date_range_start/end`
- Fix NY State Contracts entry showing year 2122
- Clear the 13 NULL entries
- **Why:** Admin Panel's Data Freshness Dashboard shows garbage until this is fixed
- **Effort:** 2-3 hours (requires checking each source's actual last load date)

### 0.6 Run ANALYZE on All Tables
- `ANALYZE;` — fixes stale PostgreSQL planner statistics (168 of 174 tables show 0 rows)
- **Effort:** 2 minutes to run, immediate query plan improvements

### 0.7 Optimize Slow API Endpoints
- Beyond the index fix (0.2), four endpoints are unacceptably slow:
  - `/api/master/stats` — 4-12 seconds. **Add caching** (simple TTL cache, data changes rarely)
  - `/api/admin/match-quality` — 5 seconds. Add summary materialized view or cache
  - `/api/master/non-union-targets` — 2 seconds. Add pagination if not present
  - `/api/profile/employers/{id}` — 3 seconds. Profile query optimization
- **Effort:** 3-4 hours total

### 0.8 Rotate Exposed API Keys
- `GOOGLE_API_KEY` was entered during CBA tool session (2026-02-22) — must be rotated
- Verify no other API keys are exposed in session logs, `.env`, or code
- **Effort:** 15 minutes

### 0.9 Verify IRS BMF Full Load
- `irs_bmf` table reportedly has only 25 test rows, but BMF data (2,027,342 records) went into `master_employers` during Phase G seeding
- Verify: is `irs_bmf` still needed as a standalone table, or was it superseded by the master seeding?
- If superseded: document this clearly. If still needed: load full 1.8M rows.
- **Effort:** 30 minutes to verify, 2-3 hours if load is needed

### Phase 0 Total: ~1.5 days of work

---

## Phase 1: Data Trust — Fix the Scoring System (Weeks 1-3)

**Required decisions: D1-D7**

This is the audit's "Chain 1" — the foundation everything else builds on. If scores are wrong, no amount of UI polish matters.

### 1.1 Fix score_financial Duplicate
- Line 340 of `build_unified_scorecard.py` copies `score_industry_growth` into `score_financial`
- **Fix:** Implement real `score_financial` — the Redesign Spec intended this to be a separate signal (employer-specific financial health vs. industry-wide growth). Options:
  - Use BLS growth + public/nonprofit boost (current implementation already does this for `score_industry_growth`, so this needs to be differentiated)
  - **USER DECISION (minor):** What should `score_financial` actually measure that's different from `score_industry_growth`? Options: (a) Revenue trend for public companies (SEC data), (b) 990 financial health for nonprofits, (c) Combined financial signals. Recommendation: (c) — use SEC revenue trend + 990 health where available, skip for others.
- **Effort:** 2-4 hours
- **Impact:** Changes display for all 146,863 employers but doesn't change weighted score much (was already only counted once in the formula)

### 1.2 Fix score_contracts (Zero Variation)
- All 8,672 employers with contracts get exactly 4.00
- **Fix:** Implement tiered scoring from Redesign Spec:

| Contract Levels | Score |
|----------------|-------|
| No contracts | 0 |
| Federal only | 4 |
| State only | 6 |
| City/local only | 7 |
| Any two levels | 8 |
| All three levels | 10 |

- Need to check data: does the platform have state/city contract data linked? (NY State Contracts + NYC Contracts exist but may not be matched to F7 employers)
- **Effort:** 3-5 hours (depends on whether contract level data is already linked)

### 1.3 Remove/Disable score_similarity
- **Requires decision D5**
- Only 186/146,863 employers (0.1%) have a value. Only 3 distinct scores.
- **Action:** Remove from weighted formula. Keep the column but set weight to 0.
- **Investigation (parallel):** Trace code path from `employer_comparables` (269K rows) to `score_similarity` to understand why the pipeline only produced 186 scores. The comparables data may be good — just disconnected.
- **Effort:** 1 hour to disable, 2-4 hours to investigate pipeline

### 1.4 Clean Stale OSHA Matches
- **Requires decision D1 (name similarity floor) and D4 (bulk-reject vs re-run)**
- 29,236 active OSHA Splink matches have name similarity between 0.65-0.699
- **Recommended action:** Bulk-reject now (mark as superseded in `unified_match_log`)
- **Script:** Single UPDATE statement — ~1 hour including verification
- **Note:** Full re-run deferred to Phase 2 after Splink model is retuned

### 1.5 Clean Junk Records from Scoring Universe
- Remove placeholders: "Company Lists", "Employer Name", "M1", 2-character names
- Remove non-employers: "Pension Benefit Guaranty Corporation" (federal agency), "Laner Muchin" (law firm)
- Remove aggregation artifacts: USPS TX record with 38,268 ULPs (national data on one state record)
- Flag and investigate: Records with `is_labor_org=TRUE` that might be hiding real targets
- **Approach:** Build a SQL-based cleaning script that identifies and flags (not deletes) junk records
- Query patterns: generic names, 2-char names, agency names, known non-employer types
- **Effort:** 3-4 hours

### 1.5B Add "Data Coverage" Indicator to Scoring
- **Critical finding:** 82,864 employers (56.4%) have ZERO external source data (no OSHA, NLRB, WHD, SAM, SEC). Of these, 13,698 are rated Priority or Strong.
- These employers' scores are based entirely on Size + Growth + Proximity — no enforcement evidence
- **Action:** Add `external_source_count` to scoring output. Display on profiles: "Score based on X of 8 factors (Y external sources)"
- This gives users a way to see how thin the underlying data is
- **Effort:** 2-3 hours

### 1.5C Fix/Drop Broken Membership View
- `v_union_members_deduplicated` produces 72M instead of 14.5M — fundamentally broken
- State-level numbers wildly unreliable: DC at 141,563% of BLS, HI at 10.9%
- The national 14.5M total matches BLS by coincidence (overcounting in DC/NY cancels undercounting in HI/ID)
- **Action:** Either fix the view logic or drop it and document the correct query for deduped membership
- **Effort:** 2-4 hours

### 1.5D Remediate 46,627 Dangling Match Records
- 46,627 ACTIVE records in `unified_match_log` point to F7 employer IDs that don't exist
- These are NOT superseded — they're active matches whose target was apparently deleted
- **Action:** After Investigation I3 identifies the pattern, either:
  - Re-point matches to correct employer IDs, or
  - Mark as `status = 'orphaned'` so they don't pollute match counts
- **Effort:** 2-3 hours (after investigation)

### 1.6 Tier Logic Improvements
- **Requires decisions D2, D3**
- Keep Codex's `factors_available >= 3` for Priority
- If D3 = extend to Strong: add same floor
- If D2 = require recent activity: add `has_recent_enforcement_activity` flag (any OSHA/NLRB/WHD record within 5 years)
- **Effort:** 2-3 hours

### 1.7 Clean Empty Columns
- **Requires decision D7**
- Drop `naics_detailed` and `cbsa_code` from `f7_employers_deduped` (100% NULL)
- Keep `corporate_parent_id` as placeholder for SEC integration
- **Effort:** 30 minutes

### 1.8 Rebuild Scoring MV
- After all fixes above: `DROP` and `CREATE` the `mv_unified_scorecard`
- `REFRESH CONCURRENTLY` won't work because the SQL definition changed (new score_financial, new score_contracts, removed score_similarity weight)
- Also refresh `mv_employer_data_sources` and `mv_employer_search`
- **Effort:** 30 minutes (script runs ~11 seconds)

### 1.9 Score Validation Test Set
- Generate 10-15 employers spanning all tiers, 5+ industries, varied sizes
- For each: manually assess whether the score "feels right" given the data
- Compare platform tier assignment to real organizing outcomes where known
- **Critical context for Decision D2:** The audit found that among employers with actual union election wins since 2023:

| Tier | Election Wins | % of Wins |
|------|--------------|-----------|
| Strong | 6,488 | 79.3% |
| Promising | 583 | 7.1% |
| Moderate | 579 | 7.1% |
| Low | 392 | 4.8% |
| Priority | 125 | 1.5% |

- Priority captured only 125 wins. 392 employers that successfully organized were rated "Low." The system is ranking *strategic positioning* as if it's *actionable intelligence*.
- **Effort:** 4-6 hours

### Phase 1 Exit Criteria
- `score_financial` and `score_industry_growth` produce different values
- `SELECT DISTINCT score_contracts` returns 5+ values (not just 4.00)
- `score_similarity` weight = 0 in the formula
- Zero active OSHA matches below the chosen similarity floor
- Zero placeholder/junk records in Priority tier
- Top tiers require minimum 3 factors
- Data coverage indicator visible on profiles
- Broken membership view fixed or dropped
- Score distribution checked (should be less bimodal after fixes)
- Validation test set confirms scores make organizing sense
- All MVs refreshed with new logic
- **Effort total: ~3-4 weeks at 10-15 hrs/week**

---

## Phase 1B: Investigation Sprint (Weeks 2-4, overlaps with Phase 1)

**No decisions needed — this is gathering information to inform later decisions.**

These are the 20 investigation questions from the audit synthesis. Not all need answering before proceeding, but the critical ones do.

### Critical Investigations (block later phases)

| # | Question | How to Answer | Time | Blocks |
|---|----------|---------------|------|--------|
| I1 | Does NLRB "within 25 miles" proximity use junk participant data? | Trace code in scoring scripts | 1 hr | Phase 1.8 (if Factor 3 is degraded) |
| I2 | Why does comparables->similarity pipeline only produce 186 scores? | Trace `employer_comparables` -> `score_similarity` code path | 2-3 hrs | Phase 1.3 (whether to invest in fixing) |
| I3 | What's in the 46,627 UML records pointing to missing F7 targets? | Sample 20, identify pattern | 1-2 hrs | Data integrity decisions |
| I4 | How many junk/placeholder records are in the scoring universe? | SQL queries for generic names, agencies, non-employers | 1-2 hrs | Phase 1.5 cleanup scope |
| I5 | Name similarity floor: test 0.70/0.75/0.80/0.85 on 100-match sample | Random sample 100 Splink matches, manually evaluate at each threshold | 3-4 hrs | **Decision D1** |

### Important but Non-Blocking Investigations

| # | Question | How to Answer | Time |
|---|----------|---------------|------|
| I6 | Is the 14.5M membership number reliable state-by-state? | Compare platform vs BLS by state | 2-3 hrs |
| I7 | Are the 75,043 orphaned superseded matches good removals? | Sample 20, check if old matches were correct | 2 hrs |
| I8 | How widespread is the employer grouping problem? | Review all groups >50 members, sample groups 10-50 | 3-4 hrs |
| I9 | Can we infer NAICS codes for 22,183 employers that lack them? | Check matched OSHA SIC/NAICS codes, name keywords | 2-3 hrs |
| I10 | How many F7 employers come from multi-employer agreements? | Check for agreement-type filings in F7. Building trades show 15x inflation in association agreements. | 2 hrs |
| I11 | What's the geocoding gap by tier? | SQL query on tier + lat/lng coverage | 30 min |
| I12 | Geographic enforcement bias — how much does it distort scores? | Compare avg scores in high vs low enforcement states, controlling for industry. Audits found 2.6x variation in OSHA match rates across states. | 3-4 hrs |
| I13 | How many is_labor_org exclusions are wrong? | Sample 20 flagged entities | 1-2 hrs |
| I14 | Are there "legacy poisoned" matches beyond the one Gemini found? | Sample legacy-method matches | 2 hrs |
| I15 | What happened to the 7,803 missing source ID linkages? | Query merge log for patterns | 1-2 hrs |
| I16 | **What's the Splink Bayesian Factor for geography, and can it be retuned?** | Examine `adaptive_fuzzy_model.json` parameters. Current BFs: state~25, city~400, zip~840. Product ~8.5M overwhelms name similarity. | 2-3 hrs |
| I17 | **What does score distribution look like after fixing broken factors?** | Rebuild scorecard with fixes, histogram before/after. Currently bimodal (two humps at 0-1.5 and 5-6.5). | 1-2 hrs |
| I18 | **How many of 26,693 unions are actually active (filed LM in last 3 years)?** | Query for recent LM filings per union. BLS estimates ~16,000 active locals — platform has 67% more. | 1-2 hrs |
| I19 | **What fraction of Mel-Ro Construction's 179 OSHA matches are false?** | Spot-check 20 of the 179 matches. Tests whether many-to-one inflation is systematic. | 1-2 hrs |
| I20 | **How complete is corporate hierarchy for Factor 1 (Union Proximity, weight 3x)?** | Count employers with known corporate parents. Measure what % of the 146,863 employers have any parent-child relationship. If coverage is low (e.g., 5%), Factor 1's 3x weight is wasted for 95% of employers. Currently: 125,120 links from 13,929 parents, but no one measured how many F7 employers these cover. | 2-3 hrs |

### Investigation Sprint Total: ~35-50 hours

---

## Phase 2: Matching Quality Overhaul (Weeks 4-7)

**Required decisions: D1 (from investigation I5)**

**TIME BOTTLENECK: This phase contains the Splink/fuzzy matching re-runs, which are the most expensive operations in the entire project. Budget 2-4 hours per source.**

### 2.1 Splink Model Retuning
- Root cause: Bayesian Factor for geography (state+city+zip) is ~8.5 million — overwhelms name similarity
- **Action:** Reduce geography weight in Splink model parameters
- Test new parameters against the 100-match gold standard from investigation I5
- **Effort:** 4-6 hours (model parameter adjustment + validation)

### 2.2 OSHA Full Re-Run
- **TIME BOTTLENECK** — OSHA is the largest source (1M+ establishments)
- Re-run with new Splink parameters and new similarity floor
- Uses `scripts/matching/run_deterministic.py osha`
- **Effort:** 4-6 hours (mostly compute time, ~30 min of human time)
- Must batch: never run OSHA in parallel with WHD or SAM (OOM risk)

### 2.3 Evaluate Other Source Re-Runs
- After OSHA re-run, check if other sources need re-running with new parameters
- SAM, 990, WHD, SEC, BMF were all run after the 0.70 floor was set — may be fine
- **USER DECISION (runtime):** Re-run all sources or only OSHA?
- If re-running all: budget ~15 hours total compute time (same as B4 re-runs)
- **Effort decision:** Compare match counts before/after OSHA. If improvement is significant, re-run others.

### 2.4 Fix Employer Grouping
- Break false over-merges (groups >100 with generic names like "D. CONSTRUCTION, INC." with 249 members)
- Fix under-merges (HealthCare Services Group fragmented into 18 groups, "first student" double-space variant)
- **Approach:**
  1. Auto-flag all groups >50 members for review
  2. Apply stricter grouping criteria for generic names (require city match, not just state)
  3. Fix normalizer for double-space and known under-merge patterns
  4. Re-run `scripts/matching/build_employer_groups.py`
- **Effort:** 6-8 hours

### 2.5 Master Employer Dedup Quality
- 288,782 master employer merges were done on name+state with NO confidence scoring
- `merge_evidence` JSONB field is empty (`{}`) for all sampled merges — no audit trail
- 32,475 duplicate groups by normalized name/state/zip remain (many are blank-name clusters)
- **Action:**
  1. Add confidence scoring to merge records retroactively
  2. Flag and review blank-name clusters
  3. Populate `merge_evidence` for future merges
  4. Break obvious false merges (common names like "John Smith Construction" in same state)
- **Effort:** 6-8 hours

### 2.6 Rebuild All MVs
- After matching changes: refresh all 4 MVs
- `mv_unified_scorecard`, `mv_employer_data_sources`, `mv_employer_search`, `mv_employer_features`
- **Effort:** 30 minutes

### Phase 2 Exit Criteria
- Splink false positive rate < 5% (tested on 50-match random sample)
- Zero active matches below chosen similarity floor
- Employer grouping: no false groups >50 members
- All MVs refreshed
- **Effort total: ~3-4 weeks at 10-15 hrs/week**

---

## Phase 2A: Data Enrichment (Weeks 4-6, parallel with Phase 2)

**No decisions needed. Independent of matching work.**

### 2A.1 Geocoding Gap
- 38,486 employers (26.2%) have no lat/lng
- Use Census Geocoder (free, batch API) to geocode from city+state
- **Effort:** 3-4 hours (batch submission + processing)
- **Impact:** Map features and proximity calculations work for more employers

### 2A.2 NAICS Inference
- 22,183 employers (15.1%) have no NAICS code
- Strategy: Check matched OSHA SIC/NAICS codes for same employer, use as inference
- For remaining: try `naicskit` ML-based classifier from employer name
- **Effort:** 4-6 hours
- **Impact:** 3 scoring factors depend on industry code

### 2A.3 Fix is_labor_org Misclassification
- Some real targets (school districts) are incorrectly flagged as labor orgs
- Some non-targets (union insurance funds) are not flagged
- Review and correct based on investigation I13 results
- **Effort:** 2-3 hours

### 2A.4 Fix NLRB Participant Data
- 83.6% of `nlrb_participants` records have literal CSV header text instead of real data
- Re-import with correct CSV parsing
- **Effort:** 3-4 hours (identify correct parsing, re-run import)
- **Impact:** If investigation I1 shows proximity calculation uses this data, this is HIGH priority

### 2A.5 NLRB Xref Coverage Expansion
- 161,759 `nlrb_employer_xref` entries have NULL F7 links — not broken, just unmatched
- These represent NLRB election/case employers that couldn't be linked to F7 employers
- After master employer expansion (Phase 2B), many should become matchable
- **Effort:** 4-6 hours (re-run matching after master table grows)

### 2A.6 Multi-Employer Agreement Investigation & Reconciliation
- Building trades show 15x inflation from association agreements vs. individual locals
- One agreement covering 200 contractors gets counted as 200 separate contracts
- This inflates member counts, employer counts per union, and Factor 1 (Union Proximity, weight 3x)
- **Action:** After Investigation I10 quantifies the scope:
  1. Group agreements, mark primary records
  2. Preserve relationship tracking but don't count each member as a separate employer
  3. Display association agreement context on employer profiles
- **Effort:** 4-6 hours (after investigation)

### Phase 2A Total: ~20-29 hours

---

## Phase 2B: Master Employer Scoring Expansion (Weeks 6-9)

**Requires decision D20 (fix vs expand first). Recommendation: fix first (Phases 1-2), then expand.**

### 2B.1 Score Best-Data Non-F7 Employers
- Start with the 100 master employers with quality score 80+ (already identified in audit)
- Extend scoring to SAM.gov employers with 3+ data sources
- **Effort:** 6-8 hours

### 2B.2 Wave 2: NLRB Participants into Master
- Match NLRB election employers to master table
- The 55.7% of election wins currently invisible to the platform could become visible
- **TIME BOTTLENECK** — NLRB participants table is 1.9M rows, but most are junk (Phase 2A.4)
- Fix participant data quality first
- **Effort:** 4-6 hours (after participant data is clean)

### 2B.3 Wave 3: OSHA Establishments (Filtered)
- Add establishments with 2+ violations or serious violations
- Filter to avoid flooding master table with low-signal records
- **TIME BOTTLENECK** — 1M+ OSHA establishments, matching is slow
- **Effort:** 6-8 hours

### Phase 2B Total: ~16-22 hours

---

## Phase 3: Frontend Fixes & Polish (Weeks 5-8, parallel with Phase 2)

**Required decisions: D8**

The React frontend is COMPLETE (all 6 phases), but the audits found that it displays unreliable data in several places. These fixes update the frontend to work with the corrected backend.

### 3.1 Update Score Display
- Factor bars should reflect corrected scoring (new score_financial, tiered score_contracts)
- score_similarity should show "Under Development" or be hidden when weight=0
- Factor breakdown should clarify that 7 (not 8) unique signals exist until score_financial is differentiated
- **Effort:** 2-3 hours

### 3.2 Update Tier Cards on Targets Page
- Tier counts will change after Phase 1 fixes — ensure they pull from refreshed MV
- Add "Factor coverage" indicator: show how many of the 8 factors have data for each employer
- **Effort:** 2 hours

### 3.3 Update Confidence Dots
- After Phase 2 matching fixes, confidence levels are more meaningful
- Ensure dot display maps to actual match tier confidence
- **Effort:** 1-2 hours

### 3.4 Consolidate Search & Implement Full Search UX
- 4 different employer search endpoints currently exist — Redesign Spec says "kill the existing basic/fuzzy/normalized search split"
- Update React to use only `unified-search` endpoint. Deprecate (don't delete) old endpoints.
- **Autocomplete:** Implement categorized suggestions ("Employers (5 results) | Unions (2 results)"), 300ms debounce, 3 character minimum
- **URL state:** Full URL state for searches: `/search?q=hospital&state=NY&tier=priority`. Must be bookmarkable and shareable.
- **Effort:** 5-7 hours (larger scope than originally estimated)

### 3.5 Fix Admin Panel Components
- Data Freshness Dashboard: should now work after Phase 0.5
- Score Weight Configuration: **must test end-to-end** — no auditor verified this works:
  1. Change a weight in admin panel
  2. Verify MV refresh triggers
  3. Verify refresh completes in reasonable time (not freeze the DB — Phase 0.3 must be done first)
  4. Verify tier assignments update correctly
  5. Verify before/after scores make mathematical sense
- Match Review Queue: after Phase 2, match quality is better — queue won't be overwhelmed on day one
- **Effort:** 4-6 hours (expanded for end-to-end verification)

### 3.5B Implement Help System
- The Redesign Spec provides **complete help copy** for all 5 pages (134 lines, fully drafted)
- Collapsible "How to read this page" section at top of each page, collapsed by default
- Pages: Employer Profile, Search, Targets, Union Explorer, Admin Panel
- Copy is ready — just needs to be wired into React components
- **Effort:** 3-4 hours

### 3.5C Add Research Notes Card to Employer Profile
- Spec defines card #9: free text + flag types (Hot Target / Needs Research / Active Campaign / Follow Up / Dead End) + priority (High/Medium/Low)
- Currently flag system exists but Research Notes card may not display all Spec-required fields
- **Future:** Add assigned user + status tracking when multi-user launches
- **Effort:** 2-3 hours

### 3.6 Archive Legacy Frontend
- **Requires decision D8**
- Remove `organizer_v5.html` from active serving (move to `archive/`)
- Ensure React app handles all routes
- **Effort:** 1 hour

### 3.7 Accessibility Improvements
- Add keyboard navigation for tables and pagination
- Add screen reader announcements for dynamic content (search results, loading states)
- Add focus management on page transitions
- **Effort:** 4-6 hours

### 3.8 Code-Split React Bundle
- Current build is 522 KB (over Vite's 500 KB warning)
- Add `React.lazy()` for route-level code splitting
- **Effort:** 2-3 hours

### Phase 3 Exit Criteria
- Score display reflects all Phase 1 corrections
- Single unified search endpoint with autocomplete and URL state
- Admin panel shows real data freshness dates; weight recalculation verified end-to-end
- Help sections on all 5 pages
- Research Notes card with flag types and priorities
- Data coverage indicator on employer profiles
- Legacy frontend archived
- Build under 500 KB
- All frontend tests still pass
- **Effort total: ~3-4 weeks at 10-15 hrs/week**

---

## Phase 4: CBA Extraction Tool Completion (Weeks 6-10)

**Required decision: D15 (OCR approach)**

The CBA tool is scaffolded but needs production hardening. This is a standalone workstream that runs in parallel with other phases.

**Important context:**
- CBA work was done in `C:\Users\jakew\Downloads\labor-data-project` (Codex repo), NOT in the main project directory. Files may need to be reconciled/merged.
- Gemini API model ID is fragile — if `models/gemini-flash-latest` fails, run `python list_models.py` to check for supported aliases
- A heuristic fallback extractor exists for when AI extraction is unavailable/slow
- Test document: `archive\Claude Ai union project\2021-2024_League_CBA_Booklet_PDF_1.pdf`
- **Windows note:** `uvicorn --reload` causes WinError 5 (permission errors) — run without `--reload` for reliability

### 4.1 OCR Pipeline for Scanned PDFs
- **Requires decision D15**
- Current state: pipeline identifies scanned PDFs but doesn't process them
- **Recommended:** Docling (open-source, free) for initial implementation
- **BUDGET IMPACT:** If Docling quality is insufficient, Mistral OCR at ~$0.01/page = ~$20 for 2000 pages
- Route: scanned -> OCR -> text -> extraction pipeline
- **Effort:** 6-8 hours

### 4.2 Expand Provision Extraction
- Currently: limited examples for provision class extraction
- Needed: populate extraction examples for all 14 provision classes in `cba_extraction_classes.json`
- Move hardcoded examples to `config/cba_few_shot_specs.json`
- **BUDGET IMPACT:** Gemini API calls for extraction. Cost is minimal (~$0.01-0.05 per document with Flash model)
- **Effort:** 6-8 hours

### 4.3 API Hardening
- Add typed Pydantic response models for CBA endpoints
- Add endpoint tests (`tests/test_cba_api.py`)
- Add pagination controls
- Add class filter dropdown sourced from `/api/cba/provisions/classes`
- **Effort:** 4-6 hours

### 4.4 React Frontend Integration
- Create CBA search component in React app (currently only exists as standalone HTML)
- Provision row click -> show full excerpt and surrounding context
- Add CSV export
- **Effort:** 6-8 hours

### 4.5 Human Verification Workflow
- Add `is_human_verified` flag and review endpoint
- Dedupe logic for near-identical clause spans
- Per-run diagnostics: model used, duration, extraction mode, error text
- **Effort:** 4-6 hours

### Phase 4 Exit Criteria
- Scanned PDFs are processed through OCR
- All 14 provision classes have extraction examples
- CBA search integrated into React app
- API has typed response models and tests
- **Effort total: ~26-36 hours over 4 weeks**
- **Budget impact: $0-40 (OCR + Gemini API)**

---

## Phase 5: Research Agent (Weeks 10-18)

**Required decisions: D10-D13 (all needed before starting)**

This is the Deep Dive tool from the Redesign Spec, built as a self-improving research agent. This is the largest new feature and the primary API cost driver.

**Prerequisites (must be in place before starting):**
- Anthropic API key (separate from chat usage) — set up a separate API account
- Phase 1 scoring fixes complete (agent needs stable, accurate data to research against)
- Lock down the dossier structure and commit to it for 100+ runs — changing the template mid-stream breaks the learning system
- Pick 5-6 initial test companies across diverse industries (healthcare, manufacturing, hospitality, building services, transportation, retail)

**Conditions for success:**
- Industry diversity in early runs — if you only test on healthcare, the strategy memory only knows healthcare
- Patience: first 20-30 runs will not be impressive. They build the data that makes runs 50-200 dramatically better.
- Minimum run counts before advancing: Phase 2 needs 30+ logged runs, Phase 3 needs 50+, Phase 4 needs 100+

**Maps to Redesign Spec:** "Run Deep Dive" button on employer profiles → Step 1 (government data, fast) → Step 2 (web research, background). Results saved permanently to profile. "Deep Dive Available" badge on search results for researched employers.

**Note on effort estimates:** The Research Agent Implementation Plan estimates 120-176 hours total. The estimates below are the implementation plan's numbers, not the lower original roadmap estimates.

### 5.1 Phase 1: Build the Research Agent (Weeks 10-14)
**BUDGET IMPACT: ~$15-50 for 30 test runs**

#### 5.1.1 Build Internal Tools (Database Wrappers)
Most queries already exist in the API. Wrap them as callable tools:
- `search_osha`, `search_nlrb`, `search_whd`, `search_sec`, `search_sam`
- `search_990`, `search_contracts`, `get_industry_profile`, `get_similar_employers`, `search_mergent`
- **Effort:** 10-15 hours

#### 5.1.2 Build External Tools
- `search_web` (Claude built-in or Tavily per decision D10)
- `search_news` (web search with date filter)
- `scrape_employer_website` (Crawl4AI — already set up)
- `search_job_postings` (Indeed MCP or Adzuna API)
- **Effort:** 8-12 hours

#### 5.1.3 Create Logging Database Tables
- `research_runs` — one row per deep dive
- `research_actions` — one row per tool call within a run
- `research_facts` — one row per piece of information extracted
- Schema already designed in the Research Agent plan
- **Effort:** 3-4 hours

#### 5.1.4 Write the Agent Prompt
- Define the dossier template (7 sections)
- Recommended tool ordering by company type
- Quality standards (cite sources, note confidence, flag contradictions)
- Budget awareness (don't call expensive tools when cheap ones will do)
- **Effort:** 4-6 hours (most important creative work)

#### 5.1.5 Build Agent Orchestration Code
- Claude API tool use loop
- Result parsing and dossier assembly
- Logging integration
- **Effort:** 8-12 hours

#### 5.1.6 Test on 20-30 Companies
- Spread across 5-6 industries: healthcare, manufacturing, hospitality, building services, transportation, retail
- Manual review of each report
- Iterate on prompt and tool definitions
- **BUDGET IMPACT:** ~$15-50 (10K-50K tokens per run)
- **Effort:** 10-15 hours

#### 5.1 Exit Criteria
- Any company name -> structured dossier with at least 4/7 sections filled
- Every fact has a source citation
- Every tool call is logged with timing and outcome
- 20-30 test runs completed across diverse industries

### 5.2 Phase 2: Strategy Memory (Weeks 14-16)
**BUDGET IMPACT: ~$10-30 for 30 test runs**

#### 5.2.1 Build Strategy Summary Table
- Aggregate action logs into success rates by industry/company type/tool
- `research_strategies` table with hit rates, quality scores, latency, cost per tool per industry
- **Effort:** 5-7 hours

#### 5.2.2 Strategy Injection into Agent Prompt
- Before each run: query strategy table, rank tools by hit_rate * avg_quality
- Format as recommendations in Claude's prompt ("HIGHLY RECOMMENDED: search_osha — 87% hit rate")
- **Effort:** 5-7 hours

#### 5.2.3 Automatic Strategy Updates
- Post-run: update strategy table with new results
- Minimum threshold: only show recommendations based on 3+ runs
- **Effort:** 4-6 hours

#### 5.2 Exit Criteria
- Agent's tool selection visibly varies by company type
- Well-studied industries research faster than new industries
- Strategy table shows clear patterns

### 5.3 Phase 3: Auto Scoring (Weeks 16-18)
**BUDGET IMPACT: ~$25-75 for 50 test runs**

#### 5.3.1 Build Auto-Grading Pipeline
- Post-run: separate Claude call (Sonnet, not Opus — cheaper) grades the dossier
- 5 dimensions: coverage, source quality, consistency, freshness, efficiency
- Scores saved to `research_runs.overall_quality_score`
- **Requires decisions D16, D17, D18**
- **Effort:** 10-14 hours

#### 5.3.2 Build Gold Standard Set
- 15 companies where you know the right answer
- Write expected dossier content for each
- Run agent and compare
- **Effort:** 8-12 hours

#### 5.3.3 Connect Scores to Strategy Table
- Tools that contributed to high-scoring runs get quality boost
- Strategy memory now weighted by quality, not just hit rate
- **Effort:** 3-4 hours

#### 5.3 Exit Criteria
- Every research run gets automatic quality score
- Human spot-checks agree with auto-grader (within 1-2 points on 10-point scale)
- Average quality scores trend upward over first 100 runs

### 5.4 Phase 4: Query Refinement (Weeks 18-20+)
**Deferred — only build if Phase 3 shows template-level optimization is needed**

- Build query template library (3-5 templates per tool)
- Template selection logic based on company characteristics
- Template-level hit rate tracking
- **Requires decision D19**
- **Effort if built:** 27-40 hours

### Phase 5 Total Effort: ~120-176 hours over 10-14 weeks (per Research Agent Implementation Plan)
### Phase 5 Total Budget: ~$75-230

---

## Phase 6: Workforce Estimation Model (Weeks 12-20+)

**Required decision: D14**

This builds on the Research Agent (Phase 5) and existing database infrastructure. Can start in parallel with Phase 5.2+ since Phase 6.1 only needs existing data.

### 6.1 Headcount Estimation Engine (Weeks 12-15)
- Implement 5-layer estimation approach:
  - Layer 1: Direct evidence (SEC 10-K employee count, NLRB bargaining unit size, OSHA inspector notes)
  - Layer 2: Government statistical (QCEW county×NAICS totals, CBP establishment size class, SUSB enterprise size)
  - Layer 3: Financial triangulation (revenue÷industry RPE, payroll÷avg wage, CEO pay ratio median comp×headcount range)
  - Layer 4: Digital traces (job posting count÷industry vacancy rate via JOLTS data, LinkedIn with occupation-specific correction factors)
  - Layer 5: Operational capacity (hospital beds×5.0-6.0 FTEs/bed, school enrollment÷7.1-7.3 staff ratio, warehouse sqft÷industry sqft/employee)
- Store every estimate with full metadata: `{method, value, low, high, definition, date, source}`
- **Definition tags** on every estimate (from Gemini's recommendation): Is this headcount or FTE? Employees-only or including contractors? Global or domestic? This prevents apples-to-oranges comparisons.
- Combine with inverse-variance weighting (most reliable sources count more)
- **New data to ingest:**
  - QCEW bulk data (Priority 1 — Medium effort)
  - CBP/SUSB via Census API (Priority 2 — Low effort, `census` Python wrapper)
  - O*NET bulk download (Priority 3 — Very low effort, 2-3 hours, clean CSV files)
  - LEHD/LODES WAC files (Priority 4 — Block-level employment counts for validation)
- **Tools to integrate:** edgartools (SEC filing parsing), census (Census API wrapper), libpostal or usaddress (address normalization)
- **Job posting caveat:** Scraping Indeed/LinkedIn violates TOS and scrapers break constantly. Build production system around employer-owned career pages. Use JobSpy only for initial research.
- **Effort:** 20-30 hours

### 6.2 Composition Model (Weeks 15-18)
- Start with BLS staffing patterns (already in `bls_industry_occupation_matrix` — 67,699 rows)
- Adjust for employer-specific signals: NLRB unit descriptions, job postings, OSHA narratives
- Overlay Census ACS PUMS demographics for local metro area
- **New data to ingest:**
  - ACS PUMS demographic data for top 50 MSAs (Priority 6 — Medium effort)
- **Effort:** 15-20 hours

### 6.3 Calibration Engine (Weeks 18-20+)
- **This is the highest-leverage custom build (all three workforce estimation reports agree)**
- Use ~50,000 NLRB election records as ground truth for actual headcount
- For each: run all estimation methods, measure accuracy by industry/region
- Learn correction factors: "LinkedIn undercounts warehouse workers by 8x in Southeast"
- Auto-apply corrections to new estimates
- Track confidence: wider ranges for industries with few calibration points
- **Domain adaptation warning:** NLRB data skews heavily toward industries with high organizing activity (healthcare, hospitality, logistics). Calibration factors learned from NLRB will be most accurate for these industries and least accurate for tech, finance, and professional services where elections are rare. Document this bias in the model metadata and flag low-calibration industries in output.
- **Effort:** 15-25 hours

### 6.4 Integration into Platform
- Employer Profile: estimated workforce composition card
- Financial Data card: estimated employee count when no official count exists
- Deep Dive Step 1: workforce data section
- **Effort:** 6-10 hours

### Phase 6 Total Effort: ~56-85 hours over 8 weeks
### Phase 6 Budget: $0 (all data sources are free government data)

---

## Phase 7: Deployment Preparation (Weeks 16-20)

### 7.1 Fix Hardcoded Paths
- 19 scripts have hardcoded `C:\Users\jakew\Downloads` paths
- Make all scripts use config-driven paths (environment variable or config file)
- **Effort:** 4-6 hours

### 7.2 Docker Containerization
- `docker-compose.yml` with:
  - nginx (serves React static files, proxies /api/ to FastAPI)
  - FastAPI (port 8001)
  - PostgreSQL 17 (port 5432)
- Per Redesign Spec Section 5 deployment architecture
- **Requires decision D21 (GLEIF dump):** Move 12 GB GLEIF archive to external storage before containerizing
- **Effort:** 8-12 hours

### 7.3 Security Hardening
- **Critical context:** Zero real user accounts have EVER been created. The only tested auth flow is the test suite fixture with a synthetic dev user. This will be the first real auth exercise.
- Remove `DISABLE_AUTH=true` from `.env`
- Set `JWT_SECRET` to a strong random value (currently guarded by startup check — app won't start without it)
- Test auth flow end-to-end with real user accounts:
  1. Register first user (bootstraps as admin)
  2. Register second user (non-admin)
  3. Verify admin-only endpoints reject non-admin
  4. Verify write endpoints require auth
  5. Verify token refresh works before and after expiry
- **Password policy:** Enforce minimum 12 characters, at least 1 number, at least 1 special character (not currently enforced — `auth.py` accepts any password)
- **Invite-only registration:** Add admin approval or invite-code requirement for new users (the Redesign Spec says "Admin-only registration — no public signups")
- **Session timeout:** Implement 1-hour sliding window expiry (current JWT has no configurable expiry beyond the default)
- Scrub 10 archived files with old plaintext password "Juniordog33!"
- **Effort:** 6-10 hours (expanded from 4-6 due to first-time auth exercise)

### 7.4 Documentation Refresh
- Single comprehensive pass to align all docs with current reality
- Fix: CLAUDE.md row counts, factor counts, tier names, table counts
- Fix: PROJECT_STATE.md stale counts
- Fix: PIPELINE_MANIFEST.md missing 3 active scripts
- Add: master_employers count (settled number)
- **Effort:** 4-6 hours

### 7.5 Backend Test Coverage Gap
- 10 API routers have NO dedicated test files: `cba`, `corporate`, `density`, `lookups`, `museums`, `projections`, `public_sector`, `sectors`, `trends`, `vr`
- These routers have endpoints in production but zero regression safety net
- **Action:** Write basic happy-path tests for each (1 test per endpoint minimum)
- Priority: `cba` (new code, most likely to break), `corporate` (used by profile cards), `density` (used by Union Explorer)
- **Effort:** 8-12 hours

### 7.6 Server-Side User Data (if D9 = server-side)
- Move flags, saved searches, notes from localStorage to database
- Add `user_flags`, `user_notes`, `user_saved_searches` tables
- Update React stores to persist to server
- **Effort:** 8-12 hours

### Phase 7 Total: ~34-52 hours

---

## Phase 8: Advanced Features (Weeks 20+, ongoing)

These are future capabilities from the Redesign Spec and supplementary plans. Each is independent and can be prioritized based on user demand.

### 8.1 Union Website Scraper Expansion
- Currently: AFSCME only (295 profiles, 160 employers, 120 contracts)
- Expand to: SEIU, UAW, Teamsters, UFCW, USW
- **Effort per union:** 8-12 hours (each has different website structure)
- **Total for 5 unions:** 40-60 hours

### 8.2 Public Sector Adaptation
- **Requires decision D22**
- Same card framework, adapted content:
  - OSHA -> Bargaining Units
  - Corporate Hierarchy -> Government Structure
  - Government Contracts -> Budget/Funding
- Different scoring factors
- Need PERB data collection (currently zero)
- **Effort:** 30-40 hours

### 8.3 Employee Estimation Standalone Calculator
- Web page where researchers input revenue + industry -> estimated headcount
- Uses workforce estimation engine from Phase 6
- **Effort:** 6-8 hours (after Phase 6 is built)

### 8.4 SEC Human Capital Extractor
- NLP extraction from 10-K "Human Capital" sections
- ~3,700 public companies
- Extracts: total employees, FT/PT split, unionization %, contractor mentions, turnover
- **Effort:** 15-20 hours

### 8.5 Saved Searches & Notifications
- Save filter parameters + result snapshot
- Show what changed when revisited
- Optional notification: "Notify when new employers match" or "when tracked employer score changes"
- **Effort:** 12-18 hours

### 8.6 Compare Employers Feature
- Side-by-side comparison table
- Highlighted differences across scores, factors, sources
- **Effort:** 8-12 hours

### 8.7 Manual Employer Entry Form
- Admin-only form: name, address, EIN, NAICS, employee count, revenue, website
- Gets [MANUAL] source badge
- Can be matched to pipeline data later
- **Effort:** 4-6 hours

### 8.8 Corporate Auto-Detection (Exhibit 21)
- Parse SEC Exhibit 21 subsidiary listings
- Build parent-child relationships automatically
- Currently: corporate hierarchy has 125,120 links but Exhibit 21 parsing not built
- **Effort:** 15-20 hours

### 8.9 EEO-1 Data Integration
- February 2025 legal settlement made EEO-1 workforce composition data publicly available for the first time
- Contains employer-level headcounts by race, sex, and job category for employers with 100+ employees
- **High value:** Direct employee counts (Layer 1 data for workforce estimation) and demographic composition
- Monitor release schedule and format
- **Effort:** 6-10 hours (data download + matching to master employers)

### 8.10 Expansion Targets Validation
- Union Explorer shows "Expansion Targets" section — employers similar to existing organized workplaces
- This depends on Gower comparables (`employer_comparables`, 269K rows), which currently only produces scores for 186 employers (Phase 1.3 investigation)
- **Action:** After Phase 1.3 investigation fixes the pipeline, validate that expansion target suggestions are meaningful
- Cross-reference against actual organizing outcomes: do suggested targets actually get organized?
- **Effort:** 4-6 hours (after Phase 1.3 pipeline fix)

### 8.11 Propensity Model Verification
- Two propensity models exist: Model A (AUC=0.72, trained on OSHA-matched employers) and Model B (AUC=0.53, all employers)
- Model B barely beats random chance — not useful in current form
- Model A's higher AUC may reflect selection bias (OSHA-matched employers are a non-random subset)
- **Action:** Validate against actual NLRB election outcomes. Does the model predict which employers face elections?
- **USER DECISION (deferred):** Keep, retrain, or remove propensity scores from platform
- **Effort:** 6-8 hours

---

## Dependency Map (Visual)

```
Phase 0 (Quick Wins) ─────────────────────────────────────────────────────────►
    │
    ├── Phase 1 (Data Trust) ─────► Phase 1.8 (Rebuild MVs) ──────────────────►
    │       │                              │
    │       ├── Phase 1B (Investigations) ─┤
    │       │                              │
    │       └──────────────────────────────┼── Phase 2 (Matching Quality) ─────►
    │                                      │        │
    │   Phase 2A (Enrichment) ─────────────┘        │
    │   [parallel with Phase 2]                     │
    │                                               │
    │   Phase 3 (Frontend Fixes) ───────────────────┘
    │   [starts after Phase 1.8, continues through Phase 2]
    │
    │   Phase 4 (CBA Tool) ────────────────────────────────────────────────────►
    │   [independent, runs in parallel]
    │
    │                           Phase 2B (Master Scoring) ─────────────────────►
    │                           [after Phase 2]
    │
    │                                   Phase 5 (Research Agent) ──────────────►
    │                                   [after Phase 1, needs stable data]
    │
    │                                       Phase 6 (Workforce Estimation) ────►
    │                                       [after Phase 5.1, some parallel]
    │
    │                                               Phase 7 (Deployment) ──────►
    │                                               [after Phase 3]
    │
    │                                                       Phase 8 (Advanced)►
    │                                                       [ongoing, as needed]
```

---

## Timeline Summary

| Phase | Weeks | Key Activity | Effort (hrs) |
|-------|-------|-------------|-------------|
| **0: Quick Wins** | 1 | Backups, indexes, MV fix, search fix, freshness, ANALYZE | 8-12 |
| **1: Data Trust** | 1-3 | Fix scoring factors, clean junk, tier logic, rebuild MVs | 20-30 |
| **1B: Investigations** | 2-4 | Answer critical questions, test similarity floors | 25-35 |
| **2: Matching Quality** | 4-7 | Splink retune, OSHA re-run, grouping fix | 20-30 |
| **2A: Enrichment** | 4-6 | Geocoding, NAICS inference, NLRB cleanup | 12-17 |
| **2B: Master Scoring** | 6-9 | Score non-union employers, Waves 2-3 | 16-22 |
| **3: Frontend Fixes** | 5-8 | Update displays, consolidate search, accessibility | 18-27 |
| **4: CBA Tool** | 6-10 | OCR, extraction expansion, React integration | 26-36 |
| **5: Research Agent** | 10-18 | Build agent, strategy memory, auto scoring | 120-176 |
| **6: Workforce Estimation** | 12-20 | Headcount engine, composition, calibration | 56-85 |
| **7: Deployment** | 16-20 | Docker, security, paths, docs, test coverage | 34-52 |
| **8: Advanced** | 20+ | Scraper expansion, public sector, saved searches | 40-100+ |
| **TOTAL (Phases 0-7)** | **~20 weeks** | | **~355-510 hrs** |

---

## Budget Summary

| Item | Cost | Phase |
|------|------|-------|
| Phase 0-4: All free | $0 | 0-4 |
| CBA OCR (if using Mistral) | $0-20 | 4 |
| CBA Gemini API | $5-15 | 4 |
| Research Agent R&D (100 runs) | $75-230 | 5 |
| **Total one-time R&D** | **$80-265** | |
| Research Agent ongoing (200 runs/mo) | $100-200/mo | 5+ |
| **Maximum total to launch** | **~$265** | |
| **Monthly ongoing** | **$100-200** | |

All well under $500 budget target for launch. Ongoing costs are the research agent Claude API usage, which scales with actual usage (only charged per run, not per month). The Research Agent Implementation Plan's cost breakdown: Phase 1 ($15-50), Phase 2 ($10-30), Phase 3 ($25-75), Phase 4 ($25-75 if built).

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Splink retune takes longer than expected | Medium | High (blocks Phase 2) | Can bulk-reject stale matches immediately (Phase 1.4) as interim fix |
| OSHA re-run produces worse results | Low | Medium | Keep backup of current match state; can rollback |
| score_financial differentiation is unclear | Medium | Low | Default: same as industry_growth but different weight. Improve later. |
| Research agent early runs are poor quality | High | Low | Expected — first 20-30 runs build training data. Quality improves with strategy memory. |
| CBA OCR quality insufficient | Medium | Medium | Fall back from Docling to Mistral OCR (small cost increase) |
| Budget overrun on Claude API | Low | Low | Cap at 200 runs during R&D. Total API cost ~$150 max. |
| Python 3.14 compatibility issues | Low | Medium | Already documented. Watch for `\s` escape warnings. |
| Windows path issues during Docker prep | Medium | Medium | Phase 7.1 fixes all hardcoded paths before containerization |
| Job posting scraping violates TOS | High | Medium | Indeed/LinkedIn TOS prohibit scraping. Build production system around employer-owned career pages + Adzuna API. Use JobSpy only for initial research, never at scale. |
| Propensity models unverified | Medium | Medium | Model A (AUC=0.72, OSHA-matched) and Model B (AUC=0.53, all employers) — neither has been validated against real organizing outcomes. Model B barely beats random. Verify before using in production scoring. |
| NLRB calibration bias (Phase 6) | Medium | Medium | NLRB elections skew toward healthcare/hospitality/logistics. Workforce estimates will be least reliable for tech/finance/professional services. Document this in model metadata. |
| First real auth deployment (Phase 7) | Medium | High | Zero real users have ever been created. Auth flow only tested via synthetic fixtures. Budget extra time for Phase 7.3. |

---

## What "Done" Looks Like (Success Criteria from Audit)

| Metric | Current | Target | Phase |
|--------|---------|--------|-------|
| Splink false positive rate (HIGH conf.) | 10-40% | <5% | Phase 2 |
| Priority tier with zero enforcement data | 92.7% | <50% | Phase 1 |
| Score factors working | 3-4 of 8 | 7-8 of 8 | Phase 1 |
| score_contracts distinct values | 1 | 5+ | Phase 1 |
| score_similarity coverage | 0.1% | >10% (or removed) | Phase 1 |
| Stale OSHA matches below floor | 29,236 | 0 | Phase 1 |
| Geocoding coverage | 73.8% | >90% | Phase 2A |
| Data freshness table valid entries | 6 of 19 | 19 of 19 | Phase 0 |
| Election win visibility (matched to F7) | 44.3% | >70% | Phase 2B |
| Junk records in Priority/Strong | Multiple | 0 | Phase 1 |
| NLRB participant data quality | 16.4% clean | >99% clean | Phase 2A |
| Search parameter handling | Silent failure | Error message | Phase 0 |
| Documentation accuracy | 3+ disagreements | Consistent | Phase 7 |
| Deep Dive available | Not built | Working for any employer | Phase 5 |
| Workforce estimation | Not built | Headcount + composition | Phase 6 |
| CBA search | Scaffolded only | Full extraction + search | Phase 4 |

---

## Decision Checklist (Quick Reference)

Decisions ordered by when you need them:

**Need NOW (before Phase 1):**
- [ ] D1: Name similarity floor (test first, then pick)
- [ ] D2: Priority tier = structural only or + activity?
- [ ] D3: Minimum factors for Strong tier?
- [ ] D4: Stale OSHA: bulk-reject now or wait for re-run?
- [ ] D5: score_similarity: remove or keep?
- [ ] D6: Keep Codex's changes? (recommend: yes)
- [ ] D7: Empty columns: drop naics_detailed + cbsa_code?

**Need in ~4 weeks (before Phase 3):**
- [ ] D8: Archive legacy frontend?

**Need in ~8 weeks (before Phase 5):**
- [ ] D10: Web search API for research agent
- [ ] D11: Dossier detail level (tiered recommended)
- [ ] D12: Research agent: CLI first or web first?
- [ ] D13: Claude autonomy level

**Need in ~10 weeks (before Phase 6):**
- [ ] D14: Store estimates as point or distribution?
- [ ] D15: CBA OCR approach

**Can wait:**
- [ ] D9: User data: localStorage vs server
- [ ] D16-D19: Research agent Phase 3-4 decisions
- [ ] D20: Fix scoring vs expand scoring
- [ ] D21: GLEIF dump archival
- [ ] D22: Public sector timing

---

*This roadmap was synthesized on February 23, 2026 from 6 source documents totaling ~3,800 lines. It was then expanded after a systematic gap analysis comparing every section against all 6 source documents (20 gaps identified and addressed). It supersedes UNIFIED_ROADMAP_2026_02_19.md for all planning purposes.*
