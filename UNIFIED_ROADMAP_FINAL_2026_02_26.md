# Unified Platform Roadmap
## February 26, 2026 — Synthesized from 6 Audit & Investigation Reports

---

## How to Read This Document

This roadmap pulls together findings from six separate reports produced by three different AI tools over February 25-26, 2026:

1. **Claude Code Audit** — Checked the actual database by running queries
2. **Claude Code Deep Investigation** — Ran 6 targeted investigations into the most important questions
3. **Codex Audit** — Read the actual code line by line
4. **Codex Deep Investigation** — Produced implementation blueprints and cleanup inventories
5. **Gemini Audit** — Assessed the platform from an organizer's strategic perspective
6. **Gemini Deep Research** — Researched outside sources: academic literature, data availability, organizer workflows

Each step in this roadmap is tagged with which report(s) it comes from, so you can trace any recommendation back to its source evidence.

The roadmap is organized into **Phases** (what to do in what order), and within each phase, every item is categorized as one of:

- 🔧 **Action** — A specific thing to build, fix, or change
- 🔴 **Decision Required** — A choice you need to make before work can proceed
- 🔍 **Data Question** — Something we don't know yet that needs investigation
- 📊 **New Data Source** — An external dataset that could be added to the platform
- ✅ **Resolved** — A question from earlier audits that's now been answered

---

## What We Now Know (Key Findings That Changed the Picture)

Before diving into the roadmap, here are the most important discoveries from Round 2 that update or overturn what we thought after the first audits.

### ✅ The Score IS Predictive (Overturns Previous Conclusion)

All three first-round auditors flagged the "125 vs 392" problem — the Priority tier had only 125 election wins while the Low tier had 392. This made it look like the score was broken.

**The Round 2 investigation resolved this.** The issue was that Low tier contains far more employers than Priority, so of course it has more wins in raw numbers. When you look at **win rates** instead of raw counts, the picture flips completely:

- Priority employers win NLRB elections **90.9%** of the time
- Strong: **84.7%**
- Promising: **81.6%**
- Moderate: **76.7%**
- Low: **74.1%**

That's a clean staircase — every step up in tier means a higher win rate. The scoring system works directionally. It's not perfect, but it's meaningfully better than random.

**Source:** Claude Code R2, Investigation 1

### ✅ We Now Know Which Factors Actually Matter

The backtest also revealed which of the 8 scoring factors actually predict election outcomes, and which don't. This is probably the single most important finding across all six reports:

| Factor | Current Weight | Predictive Power | Verdict |
|--------|---------------|-----------------|---------|
| NLRB Activity | 3x | **+10.2 percentage points** | ✅ Strongest predictor — weight is justified |
| Industry Growth | 2x | **+9.6 pp** | ⬆️ Underweighted — could justify 3x |
| Contracts | 2x | +5.7 pp | ✅ Reasonable |
| WHD (wage theft) | 1x | +4.1 pp | ✅ Reasonable |
| Financial Health | 2x | +4.1 pp | ✅ Reasonable |
| Employer Size | **3x** | **+0.2 pp** | 🔴 Essentially zero — massively overweighted |
| Union Proximity | **3x** | **+0.0 pp** | 🔴 Literally zero predictive power |
| OSHA Violations | 1x | **-0.6 pp** | ⚠️ Slightly predicts LOSSES, not wins |

**What this means in plain language:** The two factors the platform treats as most important (Size and Union Proximity, both at 3x weight) have zero ability to predict whether a union election will succeed. The factors that DO predict success (NLRB history and industry growth) are either correctly weighted or underweighted. The scoring system succeeds despite its weights, not because of them.

**The OSHA finding is counterintuitive:** Employers with high OSHA violation scores actually have slightly LOWER win rates. This could mean that employers with lots of safety violations are ones workers have already tried and failed to organize, or that these employers are sophisticated enough to fight back. More investigation is needed, but it suggests OSHA violations indicate worker anger, not organizing opportunity.

**Source:** Claude Code R2, Investigation 1

### ✅ Fuzzy Matching is Unreliable Across ALL Bands

The first-round audit found 75% false positives in the 0.70-0.80 similarity range. Round 2 tested higher bands and found the problem continues:

| Similarity Band | Active Matches | Estimated False Positive Rate |
|----------------|---------------|------------------------------|
| 0.80-0.85 | 9,694 | ~40-50% |
| 0.85-0.90 | 3,897 | ~50-70% |
| 0.90-0.95 | 1,600 | ~30-40% |
| 0.95-1.00 | 679 | Not sampled (likely best) |

**The fundamental problem:** String similarity scores cannot tell the difference between names that share the same words but are different entities. "San Francisco State University" and "University of San Francisco" share almost all the same words (high similarity score) but are completely different institutions. "CSX Transportation" and "CRC Transportation" look similar to a computer but one is a major railroad and the other is a small trucking company.

**There is no clean threshold.** Even the 0.90-0.95 band has roughly 1 in 3 matches wrong.

**Source:** Claude Code R2, Investigation 2

### ✅ The Research Agent is Broken by a Specific Bug

The research agent runs, produces content, and even assigns quality scores — but none of its work shows up in employer profiles. The root cause is a single line in the database view definition:

The view that powers employer profiles says "only show me research enhancements where `is_union_reference = false`." But all 16 existing research enhancements have `is_union_reference = true`. So the filter excludes every single one. Fixing this one line would immediately light up research data for 16 employers.

Additionally, 77% of research runs don't include the employer ID at all — the system doesn't look up whether the company it's researching already exists in the database before creating the run. So even after fixing the view, most past research work can't be connected to the right employer.

**Source:** Claude Code R2, Investigation 5

### ✅ Priority Becomes Dramatically Better With One Rule Change

Current Priority tier: 2,278 employers, but 86% have zero enforcement data (no OSHA violations, no NLRB activity, no wage theft cases). They rank high purely because they're large and in union-dense areas.

If you add one rule — "Priority requires at least one enforcement signal" — the list drops to 316 employers, but every single one has evidence of actual labor-related activity. The top entries become employers like Kaiser Foundation Hospitals (6 data factors), Walt Disney Parks (OSHA + NLRB), and Stanford Health Care (NLRB + wage theft).

**Source:** Claude Code R2, Investigation 3

### ✅ The Size Factor is Broken by Design

69.7% of employers score 0-1 out of 10 on the size factor. The median size score is 0.19. At 3x weight, this drags down the overall score for nearly every employer in the database.

**Why:** The size formula uses "bargaining unit size" — the number of workers in one specific union contract — not "company size." A hospital might have 5,000 employees total, but the nurses' bargaining unit might only have 150 people. The formula sees "150 workers" and gives a low score. The median bargaining unit is only 28 workers, so most employers look tiny even when the actual company is large.

There IS company-level data available (consolidated across all bargaining units per corporate group), with a median of 76 workers — nearly 3x higher. But the column that's supposed to carry this data into the scoring formula (`group_max_workers`) is completely empty. It was never populated.

**Source:** Claude Code R2, Investigation 4

---

## The Platform's Two-Layer Strategy

Before listing specific tasks, here's the big-picture direction that emerged from the strategic discussion:

**Layer 1 — The Core (147,000 employers with union contracts):**
These employers already exist in the labor system. We have deep data on them from NLRB, OLMS, and other government databases. The goal is to make their profiles as rich, accurate, and useful as possible. Think of this as a "research briefing" — when an organizer needs to learn about an employer quickly, this layer should give them everything the government knows, organized in one place.

**Layer 2 — The Broader Universe (2.5+ million non-union employers):**
We know much less about these employers, and that's expected. We shouldn't pretend to score them the same way we score the core. Instead, we offer "structural flags" — signals like OSHA violations, wage theft cases, government contractor status, industry growth, and size that say "this employer has characteristics worth investigating further." An organizer could filter by region, industry, size, and flags to find a shortlist, then do deeper research.

The platform is a **research briefing tool**, not a **target recommendation engine**. It organizes public information so organizers can make better-informed decisions — it doesn't tell them where to organize.

---

## PHASE 0: Trust Foundations
*Things that must be fixed before anyone should use this platform. Wrong data is worse than missing data.*

**Estimated effort: 15-25 hours**

---

### 0.1 — Fix the Scoring Weights

🔧 **Action: Reduce Size weight from 3x to 1x**
The backtest proves Size has +0.2 percentage points of predictive power — effectively zero. At 3x weight, it's the single biggest drag on the scoring system. Reducing it to 1x would raise the average score for 87% of employers and cause massive (but correct) tier reshuffling. Employers that score well on real signals (NLRB activity, industry growth, contracts) would rise; employers that only score well because they're large would fall.
*Source: Claude Code R2 Inv 1 & 4 | Effort: 1 hour*

🔧 **Action: Reduce Union Proximity weight from 3x to 2x**
Zero predictive power for election outcomes (+0.0 pp). However, it may still have strategic value that doesn't show up in win/loss statistics — being near other union shops means institutional support, experienced organizers, and established playbooks. So don't eliminate it, but don't keep it at the highest weight either.
*Source: Claude Code R2 Inv 1 | Effort: 1 hour*

🔴 **Decision: Should Industry Growth increase from 2x to 3x?**
It's the second-strongest predictor at +9.6 pp, nearly as strong as NLRB. Increasing it to 3x would reward employers in growing industries, which aligns with both the academic literature (workers feel more secure organizing when the industry is expanding) and practitioner wisdom. However, this means 3 factors at 3x weight, which concentrates scoring power.

🔍 **Data Question: What's happening with the OSHA inversion?**
OSHA scores slightly predict losses (-0.6 pp), not wins. This is a small effect and could be statistical noise. But it could also indicate that employers with lots of OSHA violations are "hardened" targets — places where workers are angry but where the employer has already fought off organizing attempts, or where conditions are so bad that turnover prevents committee-building. This needs more investigation before changing the OSHA weight.
*Source: Claude Code R2 Inv 1*

🔧 **Action: Populate `group_max_workers` column**
The column exists but is completely empty. Filling it from the existing `employer_canonical_groups` table would shift the median from 28 workers (bargaining unit level) to 76 workers (company level), making the size factor much more accurate. This is a database operation — the data already exists, it just needs to be connected.
*Source: Claude Code R2 Inv 4 | Effort: 2-3 hours*

---

### 0.2 — Clean the Fuzzy Matches

🔧 **Action: Deactivate all fuzzy matches below 0.85 similarity**
This removes 9,694 matches that are roughly 50% wrong. The blast radius is manageable — only 35 of 2,278 Priority employers are affected, and only 11 would lose enough data to drop tier. OSHA matches are the most affected (69% of removals). NLRB linkage is completely unaffected because NLRB uses direct ID matching, not fuzzy name matching.
*Source: Claude Code R2 Inv 2 & 6 | Effort: 2-4 hours*

🔴 **Decision: What to do about the 0.85-0.95 band?**
Even this band has 30-50% false positives, but it's too large (5,497 matches) to just deactivate without review. Options:
- **Option A: Manual review.** Pull the 5,497 matches and check them. Time-intensive but accurate.
- **Option B: Add secondary confirmation.** Require matching state OR matching industry code (NAICS prefix) for fuzzy matches to stay active. This would catch cross-entity false positives like "San Francisco State University" matched to "University of San Francisco" (different entities, same city).
- **Option C: Flag, don't deactivate.** Mark these matches as "lower confidence" in the frontend so users know the data may not be perfectly attributed. Show which employer the data was matched from.
*Source: Claude Code R2 Inv 2 | Codex R1 OQ2*

🔍 **Data Question: Would industry+state confirmation actually work?**
Before implementing Option B above, we'd need to test it: of the known false positives in the spot-check, how many would be caught by requiring matching state or NAICS prefix? If most false positives are cross-state or cross-industry, this is a cheap fix. If they're within the same state and industry, we need a different approach.

---

### 0.3 — Require Enforcement Evidence for Priority

🔧 **Action: Add enforcement gate to Priority tier**
Change the Priority eligibility rule from "3+ factors with score ≥ 8.0" to "3+ factors including at least 1 enforcement factor (OSHA, NLRB, or WHD) with score ≥ 8.0." This drops Priority from 2,278 to 316 employers, but every remaining employer has evidence of actual labor-related activity. The 1,962 employers removed would fall to Strong tier, which is appropriate — they're structurally interesting but lack enforcement evidence.
*Source: Claude Code R2 Inv 3 | Effort: 1-2 hours*

🔴 **Decision: Should Strong tier also require enforcement?**
The same logic applies to Strong. Currently Strong has many employers with zero enforcement data. Adding the same rule would make Strong more useful, but would push more employers down to Promising. The question is whether "structural factors only" employers belong in Strong or Promising.

🔴 **Decision: Which enforcement scenario to use?**
Four scenarios were tested:
- **Scenario B (≥1 enforcement):** 316 employers. Good balance of quality and quantity.
- **Scenario C (≥2 enforcement):** 47 employers. Very high quality but may be too restrictive.
- **Scenario D (≥1 enforcement + ≥4 total factors):** 252 employers. Similar quality to B with slightly more data coverage per employer.

Recommendation is Scenario B, but this is your call based on how organizers would use the Priority list.

---

### 0.4 — Fix the Frontend Explanations

🔧 **Action: Correct 4 specific text mismatches**
The frontend tells users things about how scoring works that don't match reality. These need to be fixed immediately because they mislead anyone reading the platform:

1. **NLRB description** says it includes "nearby 25-mile similar-industry momentum." It doesn't — this was never built. **Replace with:** "NLRB Activity combines this employer's own election history and ULP (unfair labor practice) activity. Nearby-election momentum is planned but not active yet."

2. **Contracts description** says it includes "federal + state + city" government levels. It only includes federal. **Replace with:** "Government Contracts currently covers federal contractor obligations and procurement activity."

3. **Financial weight** is shown as 1x in the frontend. The actual code uses 2x. **Fix the display to show 2x.**

4. **Similarity** is shown as "under development / disabled." This is actually correct. Keep it, but make sure it's not listed as an active scoring factor anywhere.

*Source: Codex R2 Inv 2 | Effort: 2-3 hours*

---

### 0.5 — Fix the Research Agent Connection

🔧 **Action: Fix the MV JOIN condition (30-minute fix)**
Change the database view to include `is_union_reference = true` enhancements, or remove the `is_union_reference` filter entirely. This immediately makes 16 existing research enhancements visible on employer profiles.
*Source: Claude Code R2 Inv 5 | Effort: 30 minutes*

🔧 **Action: Add employer_id auto-lookup to research agent**
Before creating a research run, the agent should check whether the company name already exists in the employer database and attach the ID if found. A simple name lookup would have linked 16 of the 31 currently-unlinked companies.
*Source: Claude Code R2 Inv 5 | Effort: 1-2 hours*

---

### 0.6 — Database Backup

🔧 **Action: Set up automated daily backups**
The database is 15GB with over 6.8 million records. There are currently zero automated backups. This was flagged in the previous audit round and still hasn't been addressed. A simple scheduled backup script running daily is the minimum.
*Source: All audits | Effort: 2-3 hours*

---

## PHASE 1: Complete the Foundation
*Make the core 147,000 employer profiles as accurate and useful as possible before expanding.*

**Estimated effort: 20-35 hours**

---

### 1.1 — NLRB Nearby 25-Mile Factor

✅ **DESCOPED (2026-02-27).** User decided industry + state momentum (implemented in Phase 0) is sufficient. The 25-mile geographic proximity approach was replaced by NAICS-2 industry momentum and state-level momentum CTEs added directly to the unified and target scorecards. NLRB factor already the strongest predictor at +10.2 pp without geographic proximity. Frontend text updated to describe momentum instead of 25-mile radius.

*Original source: Codex R1 & R2 Inv 1*

---

### 1.2 — Improve the Size Factor Data

✅ **DONE (2026-02-27).** Three changes implemented:
1. **`group_max_workers` propagation:** `build_employer_groups.py` now populates ALL employers — grouped ones get `consolidated_workers`, ungrouped ones get their own `latest_unit_size`. Coverage goes from 44% to near-100%.
2. **High-end taper:** `score_size` (unified) and `signal_size` (target) now taper from 10 to 5 for 25,001-100,000 employees. Mega-employers don't max out size scores.
3. **`company_workers` output column:** Added to `mv_unified_scorecard` for display.

Size remains weight=0 (filter dimension, not a scoring signal per D1/D7).

*Source: Claude Code R2 Inv 4, Codex R1 Area 1 | Implemented 2026-02-27*

---

### 1.3 — Contracts Factor Expansion

✅ **Documentation done (2026-02-27).** Frontend text updated to say "Federal government contracts (USASpending/SAM.gov)" and "State/local contracts not yet included." API explanation already had this note.

📊 **New Data Source: State and local government contracts** *(deferred to later phase)*
To fulfill the original specification, the platform would need state and local procurement data. This data exists but varies enormously by state — some states have searchable databases, others have nothing machine-readable. This is a significant research and engineering effort that belongs in a later phase.
*Source: Codex R1 OQ6*

---

### 1.4 — Union Profile API Gaps

✅ **RESOLVED (2026-02-27).** Investigation confirmed `/api/unions/{f_num}` already returns both `financial_trends` and `sister_locals` fields correctly. The bug report was stale — the endpoint was fixed in an earlier session. No action needed.
*Source: Claude Code R1 (original), verified 2026-02-27*

---

### 1.5 — Pipeline Reliability

✅ **DONE (2026-02-27).** `PIPELINE_MANIFEST.md` documents the run order. PostgreSQL advisory locks added to all 9 pipeline scripts via `scripts/scoring/_pipeline_lock.py` — if two scripts try to run the same step concurrently, the second one fails immediately with a clear error message instead of silently corrupting data. Lock IDs: 800001-800009 (stable, never reused).

*Source: Codex R1 & R2 Inv 4 | Implemented 2026-02-27*

---

### 1.6 — Security Basics

✅ **DONE (2026-02-27).** All three items resolved:
- **Auth default:** `DISABLE_AUTH` is commented out in `.env` — auth is enabled by default. First user bootstraps as admin.
- **`.env.example`:** Already exists with 21 variables documented.
- **SQL injection review:** All 18 f-string SQL patterns use parameterized `%s` queries for WHERE clauses; table/column names come from hardcoded dicts (not user input). No injection risk found.

*Source: Codex R1 & R2 Inv 3 & 5 | Verified 2026-02-27*

---

## PHASE 2: Launch Readiness
*Make the platform usable by real organizers, with honest presentation of what the data can and can't tell you.*

**Estimated effort: 20-35 hours**

---

### 2.1 — Honest Scoring Presentation

🔧 **Action: Reframe from "score" to "structural profile"**
The current presentation implies the score predicts organizing success. While the backtest shows it's directionally predictive, it's more accurate to present it as "this employer's structural characteristics organized by category" rather than "a number that tells you how promising this target is."

Gemini's research found that organizers use a **checklist approach** — they look for combinations of factors (anger signals + stability + leverage points), not a single number. A "Readiness Index" showing "High NLRB Activity, Low OSHA, Strong Industry Growth" would be more actionable than "Score: 7.4."
*Source: Gemini R2 Research 1 & 2*

✅ **KILLED (2026-02-26).** Propensity model removed entirely. Code archived to `archive/propensity_model/`, database tables dropped. The unified scorecard provides more useful information.
*Source: Gemini R1 §3.1*

---

### 2.2 — Data Confidence Indicators

🔧 **Action: Add match confidence to employer profiles**
When a user looks at an employer profile, they should be able to see where each piece of data came from and how confident the match is. An OSHA violation linked by exact EIN match is highly reliable; one linked by fuzzy name matching at 0.87 similarity is less so. This transparency builds trust (organizers can judge for themselves) and protects against the "one bad match destroys credibility" problem that Gemini's trust research identified.
*Source: Gemini R2 Research 5 | Claude Code R2 Inv 2 | Effort: 8-12 hours*

🔧 **Action: Show data sources explicitly**
Each section of an employer profile should cite its source. "OSHA data from OSHA Establishment Search, matched by EIN" or "Wage theft data from DOL WHD, matched by name + state at 0.92 similarity." This is the difference between a tool organizers can evaluate and a black box they have to trust blindly.
*Source: Gemini R2 Research 5*

---

### 2.3 — Docker/Deployment

✅ **DONE (2026-02-27).** Docker updated to serve React frontend:
- `frontend/Dockerfile`: Multi-stage build (Node 22 build → nginx serve)
- `frontend/nginx.conf`: SPA routing + API proxy (replaces legacy `organizer_v5.html`)
- `frontend/.dockerignore` + root `.dockerignore`: Added
- `docker-compose.yml`: Frontend builds from `frontend/Dockerfile`, API healthcheck added, `DISABLE_AUTH` defaults to `false`
- `Dockerfile` (API): HEALTHCHECK added
- Root `nginx.conf`: Legacy `organizer_v5.html` removed from index

*Source: Codex R2 Inv 5 | Implemented 2026-02-27*

---

### 2.4 — Database Cleanup

✅ **DONE (2026-02-27).** 7 confirmed-unused objects dropped via `scripts/maintenance/drop_unused_db_objects.py` (idempotent, safe to re-run):
- Tables: `cba_wage_schedules`, `flra_olms_crosswalk`
- Views: `all_employers_unified`, `bls_industry_union_density`, `union_sector_coverage`, `v_990_by_state`, `v_all_organizing_events`
- `separator.jsx` confirmed nonexistent (skipped)
- `scripts/ml/` directory deleted (only contained stale propensity `__init__.py` + `__pycache__`)

6 "probably safe" tables **kept** (strategic reference data): `epi_union_membership`, `employers_990_deduped`, `ar_disbursements_emp_off`, `nlrb_docket`, `union_naics_mapping`, `employer_990_matches`.

*Source: Codex R2 Inv 6 | Implemented 2026-02-27*

🔍 **Data Question: Are the 151 zero-reference database objects actually unused?**
Codex found 151 database objects (tables and views) with zero code references. 91 are views, 60 are tables. Some may be used by ad-hoc analysis scripts, Jupyter notebooks, or external tools that aren't part of the main codebase. A systematic check (search for table names across ALL files, not just the main application code) would confirm which are truly safe to remove.
*Source: Codex R1 & R2 Inv 6*

---

### 2.5 — Fix Membership Overcounting

✅ **Already resolved (Jan 2025).** `v_union_members_counted` view and API endpoints already use deduplication logic. Current figure: ~14.5M (within 1.5% of BLS 14.3M benchmark). No action needed.
*Source: Claude Code R1 | Verified 2026-02-27*

---

### 2.6 — Launch Strategy

🔴 **Decision: What launch approach to use?**

Gemini's trust research identified three options:

1. **Beta with friendly users:** Partner with 2-3 union research departments that understand data limitations and can give feedback. They would know to check questionable data and would help identify the worst problems before wider release.

2. **Read-only research mode:** Launch as "here's what government databases say about this employer" without any scoring or tier labels. Pure information aggregation. Add scoring later after validation with real users.

3. **Full launch with confidence indicators:** Show everything including scores and tiers, but with clear labels showing where data comes from, how confident each match is, and what the score means (structural profile, not prediction).

Gemini's research suggests the "one bad match" problem is the biggest trust risk — if an organizer finds one piece of wrong information, they may never trust the platform again. This argues for Option 1 (beta) or Option 3 (full transparency) rather than Option 2 (which has data but no context for evaluating it).
*Source: Gemini R2 Research 5*

---

## PHASE 3: Strategic Enrichment
*Add new data sources and capabilities that make the core profiles genuinely valuable.*

**Estimated effort: Large — each item is a project**

---

### 3.1 — Contract Expiration Data

📊 **New Data Source: FMCS F-7 filings**
When a union contract is about to expire, the union must notify the Federal Mediation and Conciliation Service (FMCS). FMCS publishes monthly Excel files of these notices. This data tells you exactly when contracts expire, which is valuable for two reasons:

**For the core 147K:** "The contract at Memorial Hospital expires in 8 months — here's everything about their current situation to prepare for bargaining."

**For the broader universe:** "Three hospital contracts in Northern NJ expire this year — non-union hospitals nearby may have workers watching the bargaining and becoming more interested in organizing."

🔍 **Data Question: Are F7 (OLMS) filings and F-7 (FMCS) filings the same thing?**
These are different forms with confusingly similar names. OLMS F7 is the "bargaining relationship" form already in our database. FMCS F-7 is the "notice of contract expiration" form. We need to verify they're truly separate datasets and check what overlap exists.

🔍 **Data Question: Does FMCS data have employer names that match our database?**
The usefulness of contract expiration data depends on being able to connect it to employers we already track. If FMCS uses different employer names than OLMS, we'd need another round of entity matching.
*Source: Gemini R2 Research 6*

---

### 3.2 — Public Sector Data (PERB)

📊 **New Data Source: State Public Employment Relations Board data**
7 million public sector workers are currently invisible on the platform. States have their own labor boards (PERBs) that handle public employee elections, certifications, and bargaining. Gemini R2 surveyed the landscape:

| State | Data Quality | Difficulty |
|-------|-------------|------------|
| **Minnesota** | Structured web tables with unit size | **Easy** |
| **Washington** | Searchable online database | Medium |
| **Ohio** | Clearinghouse with contracts | Medium |
| **New York** | PDF-heavy, certifications only | Hard |
| **California** | PDF-heavy, decisions only | Hard |

🔧 **Action: Start with Minnesota and Washington as pilot**
These two states have the most accessible data. Building the ingestion pipeline for MN and WA would prove the concept and establish the table schema (`public_sector_elections`) before tackling harder states. The pilot would cover a meaningful chunk of public sector workers and demonstrate value to unions like SEIU and AFSCME.
*Source: Gemini R1 §3.3, R2 Research 3 | Effort: 12-20 hours for pilot*

🔍 **Data Question: Has anyone already aggregated multi-state PERB data?**
Before building our own ingestion, check whether academic datasets, the Labor Action Tracker, or other projects have already done this work. Reusing existing aggregation would save significant effort.
*Source: Gemini R2 Research 3*

---

### 3.3 — Turnover/Discontent Signals

📊 **New Data Source: WARN Act notices**
The WARN Act requires employers to file public notices before mass layoffs (50+ workers). These are available from state DOL websites and aggregators like warntracker.com. A WARN notice is a strong "trigger event" — it signals major disruption and worker anxiety. This is the most reliable turnover signal available.
*Source: Gemini R2 Research 7*

📊 **New Data Source: BLS QCEW wage data**
The Quarterly Census of Employment and Wages provides average wages by county and industry code. By comparing an employer's known wage level to the local average for their industry, the platform could flag "low-wage outliers" — employers paying significantly below their local industry peers. Gemini calls this the "Wage/Cost Gap" and suggests it indicates "structural anger."
*Source: Gemini R2 Research 7*

📊 **New Data Source: Job posting frequency (as structural flag)**
High job posting rates relative to employer size may indicate turnover. However, Gemini's research adds an important nuance: high turnover is a sign of worker dissatisfaction but actually makes organizing HARDER because it's difficult to build a stable organizing committee when workers keep leaving (the "Exit-Voice Paradox" from labor economics). So high turnover would be a "yellow flag" — it means workers are unhappy, but it also means organizing may be harder.

Data is available from Indeed Hiring Lab and FRED (Federal Reserve) at the industry/city level for free. Employer-level data from Burning Glass/Lightcast or Revelio Labs requires commercial licensing.
*Source: Gemini R2 Research 4 & 7*

🔴 **Decision: Are these structural flags or scoring factors?**
Under the two-layer strategy, these new data sources would serve as structural flags for the broader universe (Layer 2), not as additional scoring factors for the core. But some of them (WARN notices, wage outlier data) could also enrich core employer profiles. The question is whether to integrate them into the scoring formula or present them separately.

---

### 3.4 — Revenue-Per-Employee as Strategic Signal

📊 **New Data Source: 2022 Economic Census RPE ratios**
Gemini identified Revenue-per-Employee (RPE) ratios from the Census Bureau as a potentially powerful metric. RPE serves two purposes:

1. **Estimating workforce size:** For the millions of employers where we have revenue data (from 990 filings or corporate records) but no employee count, RPE ratios by industry can estimate how many workers they have. This helps solve the "invisible employers" problem.

2. **Identifying leverage:** According to labor economics (Marshall's Third Law), unions succeed more when labor costs are a small fraction of total costs — because employers can afford wage increases without it affecting their bottom line much. High RPE means high revenue per worker, which means labor costs are likely a smaller share, which means more room for gains. Gemini calls this the "Exploitation Index."

🔍 **Data Question: How accurate are RPE-based workforce estimates?**
Before relying on RPE to estimate company size for 2.5 million employers, we need to test accuracy against employers where we DO know the actual headcount. How close do the estimates come? Is it accurate enough for structural flagging, even if not precise enough for scoring?
*Source: Gemini R2 Research 8*

---

### 3.5 — Demographics Integration

📊 **New Data Source: Census tract-level demographics**
Gemini's literature review found that workforce demographics are among the strongest predictors of organizing success — specifically, majority women and workers of color have higher win rates (Bronfenbrenner, 2004). Census tract data for employer locations could proxy for workforce demographics. This is sensitive data that needs careful handling, but the academic evidence for its relevance is strong.

🔴 **Decision: How to handle demographic data ethically?**
Demographic data is powerful but comes with significant ethical considerations. Showing "this employer's workforce is 70% workers of color" could be useful context for organizers, but it could also be misused. The platform would need clear guidance on how this data should and shouldn't be used, and whether it appears in profiles or only as a filter/flag.
*Source: Gemini R2 Research 2*

---

### 3.6 — Similarity Pipeline Fix

🔧 **Action: Review and rebuild the employer similarity system**
The similarity pipeline exists but has problems: 269,000 comparable pairs were computed, but only 164 employers are actually connected through the graph. The similarity factor is currently weighted at 0x (disabled) in the scoring formula. Before re-enabling it, the pipeline needs review to ensure comparables are meaningful.
*Source: Claude Code R1 | Effort: 8-16 hours*

---

## PHASE 4: The Broader Universe
*Extend structural flagging to the 2.5+ million non-union employers.*

**Estimated effort: Very large — this is a strategic expansion**

---

### 4.1 — Define the Structural Flag Framework

🔴 **Decision: What factors make sense for non-union employers?**

Not all scoring factors apply to employers without union contracts. Here's what does and doesn't transfer:

| Factor | Applies to Non-Union? | Why / Why Not |
|--------|----------------------|---------------|
| OSHA violations | ✅ Yes | Safety records exist regardless of union status |
| WHD (wage theft) | ✅ Yes | Wage theft records exist regardless |
| Government contracts | ✅ Yes | Contractor status is independent of union status |
| Employer size | ✅ Yes | Census/RPE data available for all |
| Industry growth | ✅ Yes | BLS data is industry-level |
| Financial health | ✅ Partially | Only for publicly traded or 990-filing entities |
| NLRB activity | ❌ No | Non-union employers have no NLRB history by definition |
| Union proximity | ❌ Conceptually different | Could mean "nearby union employers in same industry" but that's a different concept than corporate family grouping |

The flags for the broader universe should be the universally-available ones: OSHA, WHD, contracts, size, industry growth, and (where available) financial health. The presentation should be "filter and flag," not "score and rank."
*Source: Strategic reframing discussion*

🔧 **Action: Build a non-union employer search/filter interface**
Instead of a score-based ranking, the broader universe needs a filter interface: "Show me non-union employers in [region] in [industry] with [size range] that have [flag types]." Results would show matching employers with their available structural flags, not a single score.
*Source: Gemini R1 §4 | Effort: Large*

---

### 4.2 — Score the 2.5M with RPE-Based Workforce Estimates

📊 **New Data Source: Estimated headcount for all employers**
Using RPE ratios from the 2022 Economic Census, estimate workforce size for the millions of employers that have revenue data but no headcount. This is the key to making the broader universe searchable by size — currently most non-union employers have no size data at all.
*Source: Gemini R2 Research 8 | Effort: Large*

---

### 4.3 — Contract Expiration as Organizing Trigger

🔧 **Action: Build "nearby expirations" alert for non-union employers**
When a union contract expires at Employer A, non-union workers at similar, nearby Employer B can see the bargaining process play out and may become more interested in organizing. An alert feature — "3 hospital contracts in your area expire in the next year; here are non-union hospitals within 25 miles" — bridges the core and broader universe layers.
*Source: Gemini R2 Research 6*

---

## Open Questions & Research Agenda

These are questions that have come up across the six reports that aren't directly actionable yet but would significantly inform future development.

### Strategic Questions

🔍 **Does the "research briefing tool" framing match what organizers actually need?**
Gemini's R2 research describes how organizers work, but it's based on published sources, not direct interviews. The most important validation step is showing the platform to 2-3 real organizing directors and asking: "Is this useful? What's missing? What would you change?"
*Source: Gemini R2 Research 1*

🔍 **Is there a third use case beyond "deep profiles" and "structural flags"?**
The two-layer model covers research on known employers and filtering for new ones. But organizers might also want: monitoring (track changes at employers on my watchlist), industry intelligence (what's happening across all hospitals in NJ?), or campaign tracking (where is organizing activity increasing?). These are different products.
*Source: Gemini R2 Research 1*

🔍 **How do organizers currently do employer research, and how long does it take?**
If the current research process takes 2 weeks of manual Google searching and government database checking, and the platform can do it in 30 seconds, that's a compelling value proposition even with imperfect data. If organizers already have efficient research processes, the platform needs to be better, not just faster.
*Source: Gemini R2 Research 1*

### Data Quality Questions

🔍 **Why does the OSHA factor slightly predict losses?**
The -0.6 pp finding is small but counterintuitive. Possible explanations: employers with OSHA violations are "hardened" (already fought off organizing); high-violation workplaces have such high turnover that organizing committees can't form; OSHA violations proxy for dangerous industries where workers fear retaliation more. Each explanation suggests a different response.
*Source: Claude Code R2 Inv 1*

🔍 **Why do employers with MORE data factors win at LOWER rates?**
Employers with only 2 scoring factors win elections 88.2% of the time, while employers with 8 factors win only 73.4%. This "data richness paradox" suggests that having extensive government records (OSHA violations, NLRB cases, WHD findings, etc.) may mark employers as harder targets, not easier ones. Alternatively, employers with less data may simply have stronger underlying organizing momentum that isn't captured in government databases.
*Source: Claude Code R2 Inv 1*

🔍 **Is the 34%/66% linkage split a problem or expected?**
Only 34% of NLRB elections could be linked to scored employers (the F7-matched core). The other 66% are at employers not in the F7 database. This limits the backtest to the core universe and means the scoring system can only evaluate employers it already knows about.
*Source: Claude Code R2 Inv 1*

### New Data Source Questions

🔍 **Is Indeed MCP connector usable for employer-level job posting data?**
Indeed is available as an MCP connector on this platform. Can it provide employer-level posting counts that would enable turnover flagging? Or is it limited to job search functionality?
*Source: Gemini R2 Research 4*

🔍 **Can Glassdoor/Indeed review data be accessed programmatically?**
Gemini suggests review velocity (spike in 1-star reviews) as a "friction signal." Is this data actually accessible via API, or would it require scraping? What are the terms of service?
*Source: Gemini R2 Research 7*

🔍 **Are H-1B/LCA filings useful as a hiring intent signal?**
DOL Foreign Labor Certification data is machine-readable and includes employer names. A sudden stop in filings combined with a WARN notice could indicate major workforce disruption. But this only applies to employers that use H-1B workers, which skews toward tech and healthcare.
*Source: Gemini R2 Research 7*

---

## Summary: The First 10 Things to Do

If you want to start working through this roadmap, here are the 10 highest-impact actions in order, with effort estimates:

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | Fix Research Agent MV JOIN bug | Lights up 16 existing research runs immediately | 30 min |
| 2 | Reduce Size weight 3x → 1x | Removes biggest drag on scores | 1 hr |
| 3 | Reduce Union Proximity weight 3x → 2x | Removes zero-predictive-power factor from top weight | 1 hr |
| 4 | Require ≥1 enforcement for Priority | Cuts Priority from 2,278 to 316 real targets | 1-2 hrs |
| 5 | Deactivate fuzzy matches below 0.85 | Removes ~4,800 wrong matches | 2-4 hrs |
| 6 | Fix 4 frontend scoring text mismatches | Stops actively misleading users | 2-3 hrs |
| 7 | Populate `group_max_workers` column | Fixes size data from BU-level to company-level | 2-3 hrs |
| 8 | Set up automated daily backups | Protects 15GB database | 2-3 hrs |
| 9 | Add employer_id auto-lookup to research agent | Fixes 77% of research runs going forward | 1-2 hrs |
| 10 | Document pipeline run order | Prevents race conditions in data rebuilds | 3-4 hrs |

**Total for top 10: approximately 16-24 hours of work.**

These 10 actions would fix the scoring weights, clean the worst data quality problems, reconnect the research agent, protect the database, and fix the frontend lies. They don't add any new data sources or build any new features — they make what already exists trustworthy.

---

*This roadmap synthesizes findings from: Claude Code Audit (Feb 25), Claude Code Deep Investigation R2 (Feb 26), Codex Audit (Feb 26), Codex Deep Investigation R2 (Feb 26), Gemini Strategic Audit (Feb 25), and Gemini Deep Research R2 (Feb 26).*
