# PROJECT_STATE.md — Labor Relations Research Platform

> **Document Purpose:** Shared context for all AI tools (Claude Code, Codex, Gemini). Current status, active decisions, and what to work on next. For technical details, see `CLAUDE.md` in this directory. For the roadmap, see `COMPLETE_PROJECT_ROADMAP_2026_03.md` (63 tasks, 36 open questions — supersedes the Feb 26 roadmap). For redesign decisions, see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.

**Last updated:** 2026-03-01

---

## Conceptual Framework

**Non-union employers are the targets. Union employers are reference data.**

The platform helps organizers identify and evaluate non-union employers as organizing targets. Union employers (F7, NLRB wins, VR) are a reference dataset — "training data" showing what organized workplaces look like. Non-union employers are "candidates."

**Key implications:**
- The scorecard evaluates non-union employers, not union employers
- Size is a filter dimension (weight = 0), not a scoring signal
- Better union data improves targeting quality (the two pools are linked)
- Scoring uses pillar-based formula: `weighted_score = (anger*3 + stability*3 + leverage*4) / 10`
- **Stability pillar under review** — 99.6% default, may be demoted to flags (D13)

---

## Current Status (2026-03-01)

| Component | Status |
|-----------|--------|
| Phase R2: Improved HITL Review UX | **DONE** — run usefulness, flag-only review, A/B comparison, section review, active learning prompts |
| Phase R1: Research Agent Learning Loop | **DONE** — contradiction detection, human fact review, learning propagation |
| Phase 5: Frontend Redesign | **DONE** — all pages with "Aged Broadsheet" theme |
| Phase 4: Target Scorecard | **DONE** — 4.4M non-union targets scored |
| Phase 3: Strategic Enrichment (A+B+C+D) | **DONE** — research quality, similarity, wage outliers, demographics |
| Phase 0-1: Trust Foundations | **DONE** — scoring fixes, NLRB ULP, momentum |
| Backend tests | **960 pass**, 0 failures, 3 skipped |
| Frontend tests | **184 pass**, 0 failures |

### Key Data Counts

| Table/MV | Rows |
|----------|------|
| f7_employers_deduped | 146,863 (67K post-2020 + 79K historical) |
| master_employers | ~4.4M (post-dedup) |
| mv_unified_scorecard | 146,863 |
| mv_target_scorecard | 4,386,205 |
| mv_employer_search | 107,321 |
| unified_match_log | ~2.2M |
| corporate_identifier_crosswalk | 17,111 |

---

## Active Decisions

| ID | Decision | Status |
|----|----------|--------|
| D1/D7 | No enforcement gate for any tier | **CLOSED** |
| D3 | Size weight zeroed | **DONE** |
| D6 | Kill propensity model | **DONE** |
| D4 | NLRB 25-mile: descoped | **CLOSED** |
| D5 | Industry Growth weight increase to 3x? | Open |
| D8 | Launch approach: beta with friendly unions | Open |
| D11 | Scoring framework overhaul (Anger/Stability/Leverage) | Investigating — see D13 |
| D12 | Union Proximity weight (3x despite zero power) | Open |
| D13 | **Stability pillar fate: rebuild / demote to flags / kill?** | **NEW** — leaning Option B (flags). See session notes below. |
| D14 | **Expand wage outlier coverage to 1.7M employers?** | **NEW** — bottleneck is employer-level wage data |
| D15 | **Form 5500 benefits integration approach?** | **NEW** — 259K EINs, ~48K linked to targets |

---

## Deferred Items (Do NOT Prompt About)

- Phase 2.2: Fuzzy match re-runs (SAM/WHD/990/SEC with RapidFuzz)
- Phase 2.4: Grouping quality audit
- Phase 2.5: Master dedup quality audit
- Deferred until most of the roadmap is done (user decision 2026-02-23).

---

## Next Up — New Roadmap Triage (2026-03-01)

Working through `COMPLETE_PROJECT_ROADMAP_2026_03.md` (Round 4 audit synthesis, 63 tasks).

### Confirmed Broken (diagnostics run 2026-03-01)
| Item | Finding |
|------|---------|
| **Task 0-2: Contracts pipeline** | **0% coverage** — crosswalk has 0 federal contractors. `_match_usaspending.py` needs re-run. |
| **Task 1-1: Similarity pipeline** | **0% coverage** on unified scorecard — IDs drifted out of sync. |
| **Task 1-2: Stability pillar** | **99.6% get default 5.0** — only 515 employers have real data (wage outliers). Adds 1.5 free points to every score. |
| **Task 0-6: Matches below 0.75** | **70 active matches** — quick deactivation needed. |
| **Task 1-8: Union desig whitespace** | **5 untrimmed records** — 1-minute SQL fix. |

### Stability Pillar Investigation (2026-03-01 Session)

**Problem:** The stability pillar contributes 30% of weighted_score but has almost no real data. 99.6% of unified scorecard employers get a hardcoded 5.0 default. The pillar is supposed to measure "workforce stability" (workers stay long enough to organize) but we don't have turnover data.

**Data sources feeding stability (priority order):**
1. Research agent stability score (`rse_score_stability`) — **0 employers**
2. Research turnover rate (`turnover_rate_found`) — **0 employers**
3. QCEW wage outlier (`wage_outlier_score`) — **515 F7, 4,756 non-union** (expandable to ~128K F7 / 1.7M master with NAICS+state)
4. Research sentiment (`sentiment_score_found`) — **0 employers** (target scorecard only)

**Key insight: must work for 4.4M non-union targets, not just 147K F7 employers.**

Coverage on target scorecard:
- Form 5500 (benefits/pension): 48,663 targets (1.1%)
- PPP (workforce size, not stability): 141,415 targets (3.2%)
- Wage outliers: 4,756 non-union (0.1%), but 1.7M eligible for expansion
- Combined realistic: ~50-60K targets with real data

**Options under consideration:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A: Rebuild as "Workforce Investment"** | Combine wage outliers + Form 5500 benefits (pension, welfare, years filed) into new pillar | Measures something real and distinct from anger/leverage | Still only ~50-60K targets covered (1.3%) |
| **B: Demote to flags** | Add `has_pension`, `has_welfare`, `is_wage_outlier` as filterable boolean flags on target scorecard. Not a pillar. | Immediately useful for filtering ("show employers with no benefits"). No fake scores. | Loses pillar structure |
| **C: Kill entirely** | Zero the weight, revisit when WARN Act / actual turnover data available | Simplest. Stops the 5.0 damage immediately. | Loses the signal entirely |

**User leaning toward Option B** — make Form 5500 benefits and wage data into filterable flags rather than pretending to score 4.4M employers on workforce investment.

**Regardless of option chosen, stability weight should be zeroed immediately (Option A quick fix from Task 1-2) to stop the 5.0 default damage.**

### Pending Decisions (new from this session)

| ID | Decision | Context |
|----|----------|---------|
| D13 | Stability pillar: rebuild as "Workforce Investment", demote to flags, or kill? | See investigation above. User leaning toward flags (Option B). |
| D14 | Expand wage outlier coverage to all 1.7M NAICS+state employers? | Currently only 5.4K. Requires employer wage data (bottleneck). |
| D15 | Form 5500 benefits integration approach? | Task 3-1 in roadmap. 259K EINs available, ~48K already linked to targets. |

---

## Audit-Validated Findings

**Round 2 (Feb 25-26, 2026):** Full reports in `audits 2_25_2_26/`. Summary:
- **Score IS predictive** — win rates monotonic by tier (Priority 90.9% -> Low 74.1%)
- **NLRB strongest signal** (+10.2pp), Industry Growth underweighted (+9.6pp)
- **Data richness paradox** — fewer factors = higher win rate (2-factor 88.2% vs 8-factor 73.4%)
- **Selection bias** — only 34% of NLRB elections link to scored employers
- **Priority tier: 86% lack enforcement data** — enforcement gate rejected
- **Fuzzy match FP rates** — 0.80-0.85=40-50%, below-0.85 deactivated
- **Propensity model killed** — was hardcoded formula, coin-flip accuracy

**Round 4 (Mar 2026):** Full reports in project root (`ROUND_4_AUDIT_REPORT_*.md`). Key NEW findings:
- Contracts pipeline broken (0% coverage on unified scorecard)
- Similarity pipeline broken (0% coverage on unified scorecard)
- Stability pillar 99.6% default (investigated in detail this session)
- OSHA severity not weighted (willful vs other treated equally)
- Child labor + repeat violator flags unused
- Close election flag missing (5,356 elections lost by <=5 votes)
- NLRB docket data unused (2M rows)
- Union disbursement data unused (216K rows)

---

## Session History

Historical session updates (Feb 2026) archived to `archive/docs/session_history_2026_03.md`. See git log for change-by-change details.

### 2026-03-01: Roadmap merge + stability investigation
- Merged Round 2 roadmap items into `COMPLETE_PROJECT_ROADMAP_2026_03.md` (5 missing items added: launch strategy, RPE estimates, demographics, research quality frontend, PERB state alternatives). Now 63 tasks, 36 open questions.
- Ran diagnostics on Phase 0 emergency items: confirmed contracts (0%), similarity (0%), stability (99.6% default), 70 sub-0.75 matches, whitespace issues.
- Deep investigation of stability pillar: traced all 4 data sources, checked coverage on both scorecards, assessed Form 5500 / PPP / QCEW expansion potential for 4.4M targets.
- Decision pending: stability pillar fate (D13). Leaning toward demoting to filterable flags (Option B).
