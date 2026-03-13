# Audit Findings (Feb 25-26, 2026)
Synthesized from 7 reports: Claude Code Audit, Claude Code Deep Investigation, Codex Audit, Codex Deep Investigation, Gemini Audit, Gemini Deep Research, Three-Audit Synthesis.

## 1. Score IS Predictive (Overturns Prior Conclusion)

The "125 vs 392" statistic that alarmed all three initial auditors compared raw election win *counts* (Priority has fewer employers) rather than *win rates*. Corrected to rates, the gradient is monotonic:

| Tier | Elections | Win Rate | Avg Score |
|------|-----------|----------|-----------|
| Priority | 319 | 90.9% | 9.01 |
| Strong | 4,094 | 84.7% | 6.95 |
| Promising | 2,227 | 81.6% | 5.39 |
| Moderate | 3,264 | 76.7% | 3.96 |
| Low | 1,205 | 74.1% | 2.04 |

By score bucket: 0-2=73.4%, 2-4=75.2%, 4-6=80.0%, 6-8=84.5%, 8-10=88.9%. All monotonic.

**Selection bias caveat:** F7-matched employers already have union contracts, so baseline win rate is 80.8% vs 68.0% for all elections. Only 34% of NLRB elections (11,109 of 32,793) link to scored employers; 66% are invisible.

## 2. Factor-Level Predictive Power

| Factor | Weight | Predictive Power | Verdict |
|--------|--------|-----------------|---------|
| NLRB Activity | 3x | +10.2 pp | Strongest, justified |
| Industry Growth | 2x | +9.6 pp | Underweighted, could be 3x |
| Contracts | 2x | +5.7 pp | Reasonable |
| WHD | 1x | +4.1 pp | Reasonable |
| Financial | 2x | +4.1 pp | Reasonable |
| Size | 0x (was 3x) | +0.2 pp | Zero power, now zeroed |
| Union Proximity | 3x | +0.0 pp | Zero power, still weighted |
| OSHA | 1x | -0.6 pp | Slightly predicts LOSSES |

**The score succeeds DESPITE its weights, not because of them.** The two former 3x factors (Size, Proximity) contributed nothing.

**"Data richness paradox":** Employers with FEWER factors win at HIGHER rates (2-factor=88.2%, 8-factor=73.4%). More government data may mark "hardened" targets.

**OSHA inversion:** Small but counterintuitive. May indicate "hardened" employers or high-turnover environments preventing committee-building.

## 3. The Targeting Paradox

The platform scores ~147K employers that already have union contracts. The 2.5M+ non-union employers in master_employers are invisible to scoring. For a platform meant to find NEW organizing targets, this is a fundamental limitation.

**Two-layer strategy proposed:**
- **Layer 1 (Core):** 147K employers with contracts. Deep profiles, full scoring. "Research briefing."
- **Layer 2 (Broader Universe):** 2.5M+ non-union. Structural flags only (OSHA, WHD, contracts, size, industry, financial). Filter-and-flag, not score-and-rank.

**Factors that transfer to non-union:** OSHA, WHD, contracts, size, industry growth, financial (partial).
**Factors that DON'T transfer:** NLRB activity (non-union have none by definition), union proximity (conceptually different).

**Gemini's organizer quote:** "I don't need a computer to tell me Amazon is a big target -- I need it to tell me which 200-person warehouse in New Jersey is angry enough to sign cards tomorrow."

## 4. Priority Tier Quality Problem

Current Priority: 2,278 employers, **86% with zero enforcement data.** They rank high purely on structural factors (proximity, size, industry growth).

Four enforcement-gate scenarios tested:
- A (current): 2,278
- B (>=1 enforcement): 316 — **recommended**
- C (>=2 enforcement): 47 — too restrictive
- D (>=1 enf + >=4 factors): 252 — good but complex

Scenario B top entries: Kaiser Foundation Hospitals, Walt Disney Parks, Allied Universal, Stanford Health Care.

## 5. Fuzzy Match False Positive Rates

| Band | Active Matches | Est. FP Rate |
|------|---------------|-------------|
| 0.80-0.85 | 9,694 (61%) | ~40-50% |
| 0.85-0.90 | 3,897 (25%) | ~50-70% |
| 0.90-0.95 | 1,600 (10%) | ~30-40% |
| 0.95-1.00 | 679 (4%) | Likely best |

**No clean threshold exists.** Even 0.90-0.95 has ~1 in 3 wrong. Token-based similarity can't distinguish "San Francisco State University" from "University of San Francisco."

Blast radius of 0.85 cleanup: 9,694 matches. By source: OSHA 69%, SAM 12%, WHD 11%, 990 6%. Only 35 Priority affected. NLRB unaffected (direct ID matching).

## 6. Frontend Text Mismatches (4 Specific)

| Location | Says | Actually Does |
|----------|------|---------------|
| EmployerProfilePage.jsx:170 | NLRB includes nearby 25-mile momentum | NOT implemented; own-history + ULP only |
| EmployerProfilePage.jsx:171 | Contracts: federal+state+city | Federal-only |
| ScorecardSection.jsx:13 | Financial weight 1x | Actually 2x |
| ScorecardSection.jsx:10,30 | Similarity "under development" | Weight=0, disabled |

**Union Profile API bug:** Frontend expects `financial_trends` and `sister_locals`. API doesn't return these. Two sections render blank.

## 7. Propensity Model is Fake

`score = 0.3 + 0.35 * violations + 0.35 * density` — hardcoded formula, not ML. Model B accuracy = 0.53 (coin flip). Labeling as "ML" or "propensity" creates false expectations.

Options: kill it, relabel as "heuristic risk indicator," or train actual model on NLRB election data.

## 8. Size Factor is Broken by Design

- `group_max_workers` column is **100% NULL** — never populated
- F7 records = bargaining units (median 28 workers), not whole companies
- Consolidated workers from `employer_canonical_groups` has median 76 (2.7x higher)
- No high-end taper above 25,000 as spec requires
- 69.7% of employers score 0-1 on size despite it having had 3x weight
- **NOW ZEROED** (2026-02-26) — size is a filter dimension, not a signal

## 9. Junk Records in Scorecard

Present in Promising/Moderate/Low (gated from Priority/Strong by 3-factor rule):
- "Employer Name" (NY, score=10.00, Promising)
- "Company Lists" (null state, 10.00)
- "M1" (AL, 10.00), "PBGC" (DC, 10.00)
- Federal agencies, school districts, municipal bargaining units
- 525 employers with names <= 3 characters

## 10. Scoring Model Alternatives (Gemini)

**"Strategic Scorecard"** — Anger/Stability/Leverage dimensions instead of single composite. Organizers use checklist approach (combinations of factors), not a single number. A "Readiness Index" showing "High NLRB Activity, Low OSHA, Strong Industry Growth" would be more actionable than "Score: 7.4."

**Academic evidence (Bronfenbrenner meta-analysis):**
- Comprehensive organizing strategy is a better predictor than any data point
- Majority women/POC units have higher win rates
- Smaller units (<50) have higher win rates; larger (>500) provide more strategic power
- High turnover = dissatisfaction but "Exit-Voice Paradox" (Freeman & Medoff 1984) — workers leave instead of organizing

**Union workflow context:**
- UAW: 30-50-70 momentum-based
- Teamsters: 65% support threshold
- SEIU: regional market density
- Bottleneck is not FINDING targets but PRIORITIZING them based on "organizability"

## 11. Pipeline Run Order (Definitive)

```
ETL source loaders (parallel by source)
  -> run_deterministic.py (all or source-specific)
  -> build_employer_groups.py  [DESTRUCTIVE rebuild]
  -> build_employer_data_sources.py --refresh
  -> build_unified_scorecard.py --refresh
  -> compute_nlrb_patterns.py
  -> create_scorecard_mv.py --refresh
  -> compute_gower_similarity.py --refresh-view
  -> train_propensity_model.py --score-only
  -> create_data_freshness.py --refresh
```

**Race-condition pairs:** groups+readers, gower+scorecard, data_sources(DROP)+scores, deterministic+scores.

**Minimum after single-source rematch:** deterministic -> groups -> data_sources --refresh -> unified_scorecard --refresh -> scorecard_mv --refresh -> data_freshness --refresh.

## 12. New Data Source Opportunities

| Source | Value | Difficulty |
|--------|-------|-----------|
| FMCS F-7 contract expirations | "Competitive intelligence" trigger | Medium |
| State PERB (MN, WA pilot) | 7M public workers invisible | Medium-Hard |
| WARN Act notices | Best mass-turnover signal | Medium |
| BLS QCEW wages | "Structural Anger" indicator | Medium |
| 2022 Economic Census RPE | Estimate workforce for 2.5M employers | Medium |
| Job posting data (Indeed/FRED) | Turnover proxy (but Exit-Voice paradox) | Easy (aggregated) |
| Census tract demographics | Strongest demographic predictor | Easy data, hard ethics |

## 13. Security Summary

- 193 API routes: 9 admin-auth, 3 basic-auth, 47 dynamic SQL without auth
- 49 f-string SQL routes classified: 0 Critical, ~5 Tier 1 (dynamic table/ORDER BY), rest lower
- Docker serves legacy HTML, not React frontend
- No .dockerignore
- Hardcoded local paths reduce portability

## 14. Previous Audit Findings Tracker

| Finding | Status |
|---------|--------|
| score_financial = copy of growth | FIXED |
| Contracts flat 4.00 | FIXED |
| Thin-data Priority | PARTIALLY (0 with <3 factors, but 86% lack enforcement) |
| Similarity dead | ACKNOWLEDGED (weight=0) |
| Ghost employers in Priority | PARTIALLY (down to 86%) |
| Fuzzy match FP rate | PARTIALLY (floor 0.80, below-0.85 deactivated 2026-02-26) |
| Orphan match records | FIXED |
| NLRB participants junk | FIXED |
| NLRB confidence >1.0 | FIXED |
| No backup strategy | FIXED (2026-02-26, daily pg_dump) |
| Documentation stale | PARTIALLY |
| Orphaned superseded matches | FIXED |
| Data freshness NULLs | FIXED |
| 12 GB GLEIF dump | FIXED |
| Source re-runs incomplete | FIXED |

## 15. Open Decisions

| ID | Decision | Recommended |
|----|----------|-------------|
| D1 | Priority requires enforcement? | **DECIDED: No.** User rejected enforcement gate — OSHA correlates with size not opportunity, would devalue structurally good targets without govt contact. Percentile + 3-factor stays. |
| D2 | Fuzzy 0.85-0.95 band handling? | Flag in UI with confidence indicator |
| D3 | Size weight? | DONE — zeroed |
| D4 | Build NLRB 25-mile or descope? | Descope + update docs (unless backtest justifies 8-12 hr build) |
| D5 | Industry Growth weight increase? | Maybe 3x (strongest non-NLRB predictor) |
| D6 | Kill propensity model? | Yes or relabel |
| D7 | Strong tier enforcement gate? | **DECIDED: No.** Same reasoning as D1 — no enforcement gate for any tier. |
| D8 | Launch approach? | Beta with friendly union research departments |
| D9 | Non-union scoring timing? | After Layer 1 stabilized |
| D10 | Demographics handling? | Filter-only, with ethical guidelines |
| D11 | Scoring framework overhaul? | Investigating Anger/Stability/Leverage |
| D12 | Union Proximity weight? | Should reduce from 3x (zero predictive power) |
