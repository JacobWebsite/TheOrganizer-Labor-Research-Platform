# Three-Audit Synthesis & Roadmap
## February 26, 2026

---

## How to Read This Document

Three different AI tools independently audited the labor relations research platform on February 25-26, 2026. Each brought a different lens:

- **Claude Code** had direct access to the database. It ran actual SQL queries and checked real data. When it says "75% false positive rate," that's based on pulling 20 actual matches and checking them by hand.
- **Codex** read the actual code files line by line. It checked whether the code matches the specification document, found bugs, and reviewed the architecture. When it says "NLRB nearby 25-mile factor is a TODO," it's reading that directly from the source file.
- **Gemini** looked at the big picture from an organizer's perspective. It asked whether the platform actually helps people make better decisions about where to organize. When it says "Targeting Paradox," it means the platform mostly scores employers that already have unions.

This synthesis compares what all three found, identifies where they agree and disagree, and produces a prioritized roadmap for what to work on next.

---

## Part 1: What All Three Auditors Agree On

These findings came up independently across all three audits. When three different tools looking through three different lenses reach the same conclusion, that's high confidence.

### 1. The Priority Tier Looks Real But Is Mostly Empty Inside

All three found that the top-ranked "Priority" employers are real companies (hospitals, transit, logistics) — the junk placeholder problem from the last audit is fixed for this tier. But 86% of Priority employers have **zero enforcement data** — no OSHA violations, no NLRB elections, no wage theft cases. They score high purely because they're large, in a unionized industry, and near other union shops.

**What this means for organizers:** The Priority list tells you "this is a big employer in a union-heavy area," which is a starting point. But it can't tell you "workers here are unhappy" or "there's momentum nearby" — the things that actually predict whether an organizing campaign will succeed. An organizer looking at Priority might reasonably ask: "Why is this hospital ranked higher than the one down the street that just had 15 OSHA violations?"

**What changed since last audit:** The `factors_available >= 3` gate successfully blocks junk records from reaching Priority/Strong. That fix worked. But the underlying issue — that structural factors dominate over activity signals — remains.

### 2. Fuzzy Matching Still Produces Wrong Connections

All three found that low-confidence fuzzy matches (the ones where the computer tries to match company names that aren't exact) are unreliable. Claude Code's direct testing was the most damning: of 20 fuzzy matches in the 0.70-0.80 similarity range, **15 were wrong** (75% false positive rate). Examples include "San Francisco First Tee" (a golf nonprofit) matched to "Fairmont San Francisco" (a hotel), and "New Horizons" matched to "Horizon Lines" (completely different companies).

**What this means for organizers:** When a fuzzy match is wrong, it means an employer gets credited with another company's violations, contracts, or wage theft cases. An organizer could see OSHA violations on a company profile that actually belong to a completely different business. This is the fastest way to destroy trust.

**What changed since last audit:** The code now uses a stricter 0.80 floor for new matching runs (up from 0.65). But matches created during earlier runs at the lower threshold are still active in the database. The fix applies going forward but doesn't clean up the past.

### 3. The Score Doesn't Predict Real Organizing Success

All three raised the "125 vs 392" problem from the previous audit: the Priority tier captured only 125 real election wins, while the Low tier captured 392 wins — three times more. The scoring system's highest-ranked employers are *less* likely to see real organizing activity than its lowest-ranked ones.

**What this means:** If the score is supposed to answer "how promising is this employer as an organizing target," and the lowest-ranked employers actually have more organizing wins, the score isn't working as a prediction tool. It may still be useful as a descriptive profile, but calling it a "score" implies prediction.

**What changed since last audit:** This specific finding has not been addressed. No backtesting or validation has been done.

### 4. The Scoring Specification, Code, and Frontend Don't Match

All three found drift between what the spec says, what the code does, and what the frontend tells users:

- **NLRB nearby 25-mile factor:** The spec says 70% of the NLRB score should come from nearby elections within 25 miles. Codex confirmed this is a TODO comment in the code — it was never built. What actually exists is a separate "union proximity" factor based on corporate family groupings, which is a different concept entirely.
- **Similarity factor:** The spec says 2x weight. The code sets it to 0x (disabled). The frontend explanation text still says 2x. An organizer reading the explanation would think similarity matters when it doesn't.
- **Contracts factor:** The spec says tier by government level (federal=4, state=6, etc.). The code tiers by dollar amount of federal obligations only. State and local contracts aren't included.
- **Size taper:** The spec says scores should taper above 25,000 employees. The code doesn't implement this taper — it plateaus at 500 and stays flat.

**What this means:** Three different "sources of truth" tell three different stories about how scoring works. When an organizer asks "why does this employer score 8.5?" the explanation they see may not match what actually happened.

### 5. Research Agent Is Built But Disconnected

All three found the Research Agent exists and produces content, but it's not actually connected to anything users see:

- **Claude Code:** Found `has_research = false` for all 146,863 employers in the scorecard. The feedback loop from research to scoring is architecturally complete but functionally empty. 76% of research runs don't even have an employer_id linking them to a real employer.
- **Codex:** Confirmed the research tables exist and have data, but the integration path to the scorecard MV doesn't produce results.
- **Gemini:** Found the agent fails to save web-sourced facts to the `research_facts` table, and the auto-grader gives high scores (8.67/10) to dossiers with completely empty analysis sections.

**What this means:** The Research Agent is the platform's most unique and potentially valuable feature — automated intelligence gathering about specific employers. But right now it's a standalone tool that doesn't feed into anything an organizer would see. The quality scores are misleading because they don't check whether the agent actually produced useful analysis (vs. just collecting raw data).

### 6. No Backup Strategy

All three flagged that 15 GB of data has zero automated backups. Docker compose has a volume but no backup cron. The previous audit flagged this. It's still not fixed.

---

## Part 2: Unique Discoveries by Each Auditor

These are important findings that only one auditor caught, often because of their specific access or perspective.

### Claude Code Only (Database Evidence)

**score_financial and score_contracts are FIXED.** The previous audit's biggest scoring complaints — that `score_financial` was a copy of `score_industry_growth` and that contracts was flat 4.00 — have been resolved. Claude Code confirmed with actual data: 9,545 employers now have different financial vs. growth scores, and contracts shows a real tiered distribution (1/2/4/6/8/10 by obligation amount). This is significant good news that the other auditors didn't verify directly.

**Source re-runs are actually complete.** The audit prompts said 990, WHD, and SAM had never been re-run. Claude Code checked the match log and found all three sources now use Phase 3+ matching methods, with old methods properly marked as superseded. This is another piece of good news — the "split quality" concern from the prompts turned out to be outdated.

**score_size averages only 1.48 out of 10** despite carrying 3x weight. Because most F7 records represent individual bargaining units (often 20-50 workers), not whole companies, the sweet-spot curve (which peaks at 500+ workers) gives most employers a very low size score. At 3x weight, this factor is systematically dragging down scores for the majority of employers and may be masking other signals.

**Union Profile API bug:** The frontend expects `financial_trends` and `sister_locals` from the union endpoint, but the API doesn't return them. Two entire sections of the Union Profile page render blank. (Note: PROJECT_STATE.md says these fields were added on Feb 19 — this may be a deployment/refresh issue worth checking.)

**CorpWatch utilization is 0.18%.** Of 1.4 million CorpWatch companies imported (3 GB of storage), only 2,597 actually matched to F7 employers. The data enriches corporate hierarchy but isn't visible on employer profiles and isn't used in scoring.

**IRS BMF is fully loaded but unused.** 2 million rows, 491 MB — but only 8 active matches. Either the matching adapter needs to run, or this data source isn't useful for F7 matching.

**The membership deduplication view over-counts 5x** (72 million vs BLS's 14.3 million), likely summing across reporting years without temporal deduplication.

### Codex Only (Code Evidence)

**193 API routes exist, 49 use dynamic SQL with f-strings.** Of those 49, 47 have no explicit authentication requirement. This is a security surface area concern — string-interpolated SQL with no auth gate is a potential injection vector, even if the current user base is internal.

**Pipeline race conditions:** Scripts like `build_employer_groups.py` and `compute_gower_similarity.py` use delete-and-rebuild patterns. If two scoring-related scripts run simultaneously, they can create temporary windows where data is inconsistent or missing. There's no locking mechanism.

**151 database objects have zero code references.** Out of 322 public objects scanned, nearly half appear to be unused — leftover from earlier development phases. This makes the database harder to understand and maintain.

**Size factor missing high-end taper.** The spec says employers above 25,000 workers should see scores taper down (because very large employers are harder to organize). The code ramps to 500, plateaus, and never tapers. This means a 500-person employer and a 50,000-person employer get the same size score.

### Gemini Only (Strategic Perspective)

**The "Targeting Paradox."** The platform scores ~147,000 employers that already have union contracts. The 2.5+ million non-union employers in master_employers are essentially invisible to the scoring system. For a platform meant to help find *new* organizing targets, this is a fundamental limitation.

**The propensity model is a hardcoded formula, not machine learning.** The file `train_propensity_model.py` produces what looks like an ML score, but it's actually `score = 0.3 + 0.35 * violations + 0.35 * density`. Gemini found that Model B (covering all employers) has accuracy of 0.53 — essentially random. Labeling this as a "propensity model" creates false expectations.

**The public sector "black hole."** 7 million unionized public sector workers are effectively invisible. Research on state PERB data (NY, CA, WA) has been done but implementation is stalled. This matters because SEIU, AFSCME, and other major public sector unions are core potential users.

**Missing "silent discontent" signals.** Employers with no government violations but high turnover and low wages — visible through job posting frequency — are currently unscored. These might be the most actionable organizing targets because they have worker dissatisfaction without the public record that tips off management.

---

## Part 3: Where the Auditors Disagree

### False Positive Rate Estimate

- **Claude Code:** ~75% in the 0.70-0.80 fuzzy range (based on 20-match hand review)
- **Gemini:** ~18% overall (estimated from documentation)
- **Codex:** "Mixed quality" — high-confidence matches mostly correct, low-confidence fuzzy matches contain clear false positives

**Resolution:** Claude Code's number is the most reliable because it's based on actually checking matches. But it applies specifically to the low-confidence fuzzy boundary (0.70-0.80), not to all matches. The overall false positive rate across all match types is probably in the 10-20% range because most matches (about 80%) are high-confidence exact-style matches that are generally correct. The problem is concentrated in the fuzzy tier.

### Whether Source Re-runs Are Complete

- **Claude Code:** All three sources (990, WHD, SAM) have been re-run. Old methods show as superseded. ✅
- **Gemini:** Claims these use "legacy matching" creating a "Data Quality Cliff." ❌
- **Codex:** Notes batch/checkpoint resume exists but didn't verify completion status directly.

**Resolution:** Claude Code has direct database evidence. The re-runs are complete. Gemini was working from the audit prompt, which contained outdated information.

### GLEIF Data Status

- **Gemini:** "12GB of unused GLEIF data remains."
- **Claude Code:** "The 12 GB GLEIF raw dump has been cleaned up. Only `gleif_us_entities` (182 MB) and `gleif_ownership_links` (75 MB) remain."

**Resolution:** Claude Code is correct. The bulk GLEIF data was already cleaned. Only useful summary tables remain.

### Union Profile API Fields

- **Claude Code:** API does NOT return `financial_trends` and `sister_locals`. Frontend renders blank.
- **Codex:** "financial/membership cards align with endpoint structure."
- **PROJECT_STATE.md:** Says these fields were added on Feb 19.

**Resolution:** Needs direct verification. Claude Code's SQL-level check is the most authoritative, but it's possible the fields exist in the code but the endpoint wasn't restarted or the MV wasn't refreshed. This should be checked.

---

## Part 4: The Current State in Plain Language

Here's where the platform stands today, written for someone who isn't technical:

**The good news:**
- The database is real and substantial: 15 GB, 198 tables, 147,000 scored employers, data from 11 different government sources
- 1,072 tests pass (914 backend + 158 frontend)
- The React frontend is built and functional
- Major scoring bugs from the last audit (flat contracts, duplicate financial factor) are fixed
- All source matching pipelines have been re-run with improved methods
- Junk records are blocked from the top tiers
- The API is healthy and responsive

**The concerning news:**
- The highest-ranked employers mostly don't have the enforcement data (violations, elections, wage theft) that would actually tell an organizer "there's something happening here"
- About 75% of fuzzy name matches in the critical boundary zone are wrong, and old wrong matches are still active
- The scoring system ranks employers *less* effectively than random chance at predicting real organizing wins
- Three different documents (spec, code, and frontend) disagree about how scoring works
- The Research Agent exists but nothing it produces is visible to users
- 2.5 million non-union employers — the actual new targets — can't be scored yet
- There are no backups of the 15 GB database

---

## Part 5: Prioritized Roadmap

### Tier 0: Trust Foundations (Fix Before Showing Anyone)

These must be resolved before any organizer sees the platform, because each one can produce visibly wrong information that destroys credibility.

**T0-1. Clean up old fuzzy matches (4-8 hours)**
Re-run all sources with the current 0.80 name similarity floor to eliminate matches created at the old 0.65-0.70 thresholds. Consider testing at 0.85 as well. The code already defaults to 0.80 — this is about cleaning up legacy data, not changing logic.

*Why first:* Every other improvement is undermined if employer profiles show violations from the wrong company. An organizer who sees one bad match will question everything else.

**T0-2. Require enforcement evidence for Priority/Strong (1-2 hours)**
Add a rule: to reach Priority or Strong tier, an employer must have at least one enforcement factor (OSHA, NLRB, or WHD) with data. This changes the tiers from "large employer in a union area" to "large employer in a union area WITH evidence of labor activity."

*Why:* 86% of current Priority employers have zero enforcement data. The tier label implies "you should look here first" but the data doesn't support that recommendation.

**T0-3. Align scoring explanations with reality (2-3 hours)**
Update the frontend explanation text to match what the code actually does:
- Remove similarity from displayed factors (weight is 0)
- Describe union proximity accurately (corporate family groupings, not 25-mile radius)
- Show contracts as "federal obligation tiers" not "government level tiers"
- Note that the NLRB nearby 25-mile component is not yet implemented

*Why:* If an organizer reads how the score works and then checks the math, it shouldn't contradict itself.

**T0-4. Remove junk records from lower tiers (2-3 hours)**
Add an `is_valid_employer` flag or filter in the scorecard materialized view to exclude:
- Names ≤ 2 characters ("M1", "TBD")
- Placeholder names ("Employer Name", "Company Lists", "N/A")
- Federal agencies, pension funds, school districts (unless explicitly included)

These are currently in Promising/Moderate tiers with perfect 10.0 scores on their single factor.

*Why:* Even if they're not in Priority, an organizer browsing Promising employers shouldn't see "Employer Name" with a score of 10.

### Tier 1: Complete the Foundation (Fix Before Regular Use)

**T1-1. Implement or formally descope NLRB nearby 25-mile factor (4-8 hours)**
The spec says 70% of the NLRB score should come from nearby elections within 25 miles. This is a TODO in the code. Either build it (the geocoding data exists for 83% of employers) or formally remove it from the spec and update all documentation. Don't leave a gap between what's promised and what exists.

*Why:* Nearby momentum is the spec's most heavily-weighted concept (70% of a 3x factor = the single biggest score driver). Its absence means the NLRB factor only uses own-history, which misses the "hot shop effect" that organizers care most about.

**T1-2. Investigate and recalibrate score_size (2-4 hours)**
Average score_size is 1.48/10 despite 3x weight. This is because F7 records represent bargaining units (often 20-50 workers), not whole companies. Consider:
- Using consolidated worker counts (the `consolidated_workers` field from employer groups) instead of individual BU size
- Reducing weight from 3x to 1-2x
- Implementing the high-end taper above 25,000 that the spec requires

*Why:* At 3x weight with avg 1.48, size is the biggest downward drag on scores for most employers. It may be hiding employers that score well on everything else.

**T1-3. Connect Research Agent to employer profiles (3-5 hours)**
Fix the three breaks in the research-to-user pipeline:
1. Ensure all research runs set `employer_id` (currently only 24% do)
2. Fix the MV LEFT JOIN so `has_research` actually becomes true
3. Add assessment completeness to the auto-grader (so empty analysis sections can't score 8.67)
4. Fix the news/web scraping tools (empty across all reviewed dossiers)

*Why:* The Research Agent is the platform's most unique feature and potentially its biggest differentiator. But right now it produces results that go nowhere.

**T1-4. Fix Union Profile API gap (2-4 hours)**
Verify whether `financial_trends` and `sister_locals` are actually missing from the endpoint or if this is a deployment issue. If missing, implement them. Two entire sections of the Union Profile page are blank.

**T1-5. Set up automated backups (1-2 hours)**
Add a pg_dump cron job. 15 GB of irreplaceable data with zero backups is an unacceptable risk. This was flagged in the previous audit and is still not fixed.

### Tier 2: Make It Trustworthy (Fix Before Launch)

**T2-1. Backtest scores against real outcomes (4-8 hours)**
Use NLRB election outcomes to check whether higher-scoring employers actually see more organizing activity. The 125-wins-in-Priority vs 392-wins-in-Low problem needs quantitative investigation. This will either validate the scoring approach or reveal what needs to change.

*Why:* If the score doesn't predict anything, calling it a score is misleading regardless of how clean the underlying data is.

**T2-2. Secure the API for deployment (4-6 hours)**
- Change `DISABLE_AUTH` default to false
- Audit the 47 dynamic-SQL routes without auth gates
- Remove plaintext credentials from `.env` example files
- Add rate limiting to public endpoints

**T2-3. Update Docker for React frontend (2-3 hours)**
Docker/nginx currently serve the legacy vanilla JS app (`organizer_v5.html`). Point them at the React build output. This is a prerequisite for anyone deploying the platform.

**T2-4. Be honest about the propensity model (1-2 hours)**
Either relabel the propensity model as what it is (a simple heuristic formula) or remove it. Calling a hardcoded `0.3 + 0.35*violations + 0.35*density` formula a "propensity model" implies machine learning when there is none. Model accuracy of 0.53 (random) on non-union employers makes it actively misleading.

**T2-5. Clean up database (3-4 hours)**
- Drop 3 empty tables and the ~151 zero-reference objects
- Assess CorpWatch tables: 3 GB for 0.18% utilization — keep the matched data, archive or drop the bulk
- Fix the membership deduplication view (72M vs 14.3M BLS)
- Clean up 90 leaked pg_temp schemas
- Update CLAUDE.md with accurate table counts and statuses

### Tier 3: Strategic Expansion (Build for Impact)

**T3-1. Score non-union employers (the "Targeting Paradox")**
This is the single biggest strategic limitation identified by Gemini. The platform scores 147K employers with existing union contracts but ignores 2.5M+ non-union employers in master_employers. Solving this requires:
- Defining which factors apply to non-union employers (OSHA, WHD, size, contracts, industry growth all work; NLRB and union proximity need adaptation)
- Running scoring for the expanded pool
- Updating the frontend to distinguish between "currently unionized" and "potential target" profiles

This is the largest effort item but also the highest-impact for actual organizer use.

**T3-2. Implement public sector PERB data**
7 million unionized public sector workers are invisible. NY and CA PERB data has been researched but not implemented. This matters for SEIU, AFSCME, and other unions that are likely early adopters.

**T3-3. Fix the similarity pipeline**
The employer_comparables table has 269K rows, but only 164 connect to the scorecard (0.1% coverage). The pipeline breaks at a name+state bridge step. Weight is currently 0. Either fix the bridge or replace the approach with something that achieves broader coverage.

**T3-4. Add data confidence indicators**
Instead of just showing a score, show users how much data is behind it. An employer with 7 factors and a score of 6.5 is much more informative than one with 2 factors and a score of 8.0. The frontend should communicate this — potentially through a "data richness" badge or a visual confidence indicator alongside the score.

---

## Part 6: What the Previous Audit Found vs. Where We Are Now

| # | Previous Finding | Status | Evidence |
|---|-----------------|--------|----------|
| 1 | score_financial = copy of growth | **FIXED** ✅ | 9,545 employers now differ |
| 2 | Contracts flat 4.00 | **FIXED** ✅ | Tiered 1/2/4/6/8/10 confirmed |
| 3 | Thin-data Priority (231 with 1 factor) | **PARTIALLY FIXED** ⚠️ | 0 with <3 factors, but 86% lack enforcement |
| 4 | Similarity dead (0.1%) | **ACKNOWLEDGED** ⚠️ | Weight = 0. Pipeline not fixed |
| 5 | Ghost employers in Priority (92.7%) | **PARTIALLY FIXED** ⚠️ | Down to 86%. Still dominant pattern |
| 6 | Fuzzy match 10-40% false positives | **PARTIALLY FIXED** ⚠️ | Code floor raised to 0.80, but old matches persist. 75% FP in 0.70-0.80 range |
| 7 | 46,627 orphan match records | **FIXED** ✅ | 0 orphans confirmed |
| 8 | NLRB participants 83.6% junk | **FIXED** ✅ | 0 junk rows remaining |
| 9 | NLRB confidence >1.0 | **FIXED** ✅ | All normalized to 0-1 range |
| 10 | No backup strategy | **NOT FIXED** ❌ | Still no automated backups |
| 11 | Documentation stale | **PARTIALLY FIXED** ⚠️ | MEMORY.md updated, CLAUDE.md still has outdated warnings |
| 12 | 75,043 orphaned superseded matches | **FIXED** ✅ | Confirmed resolved |
| 13 | Data freshness 13/19 NULL | **FIXED** ✅ | All 24 entries have valid timestamps |
| 14 | 12 GB GLEIF dump | **FIXED** ✅ | Cleaned to 257 MB useful tables |
| 15 | Source re-runs incomplete | **FIXED** ✅ | All sources re-run with Phase 3+ methods |

**Summary: 8 fully fixed, 5 partially fixed, 1 not fixed, 1 acknowledged/deferred.** Significant progress since the Feb 19 audit, particularly on data quality fundamentals.

---

## Part 7: Key Numbers to Remember

| Metric | Value | Context |
|--------|-------|---------|
| Total scored employers | 146,863 | F7 union contract employers |
| Non-union employers (unscored) | ~2.5 million | The "Targeting Paradox" |
| Priority tier | 2,278 (1.6%) | Top tier |
| Priority with enforcement data | 316 (14%) | The ones with real labor activity signals |
| Active matches | 129,870 | Across 11 source systems |
| Active fuzzy matches | ~22,500 | Splink + trigram — the risky tier |
| Tests passing | 1,072 | 914 backend + 158 frontend |
| Database size | 15 GB | 198 tables |
| Research runs | 104 | 7.89 avg quality, 76% unlinked to employers |
| Automated backups | 0 | Previous audit flagged this too |
| Scoring factors with data (avg) | 3.0 | Out of 8 possible |
| Employers with 7-8 factors | 905 (0.6%) | Very few have comprehensive data |

---

## Part 8: Decisions That Need to Be Made

These are open questions that came out of the audits where the right answer isn't obvious and requires a judgment call:

### D1: What should "Priority" mean?
- **Option A (current):** Top percentile by score, minimum 3 factors. Mostly structural.
- **Option B (enforcement required):** Same, but require at least 1 enforcement factor. More meaningful but fewer employers qualify.
- **Option C (activity-first):** Redefine Priority around recent activity (NLRB elections, OSHA violations within 2 years). Completely different composition.

### D2: What name similarity threshold?
- **0.80 (current code default):** Eliminates most false positives but may miss some legitimate matches where names are slightly different.
- **0.85 (stricter):** Very few false positives but will drop some real matches.
- **Industry + name combo:** Use a lower name threshold (0.75) but require matching industry codes. More complex but potentially the best tradeoff.

### D3: What to do about score_size at 3x?
- **Reduce to 1x:** Lets other signals dominate for small employers.
- **Use consolidated workers instead of BU size:** Better reflects actual company size but requires the grouping layer to be accurate.
- **Both:** Reduce weight AND use better size data.

### D4: Build NLRB nearby 25-mile or descope it?
- **Build it:** The spec calls it the single most important signal. Geocoding exists for 83% of employers. Estimated 4-8 hours.
- **Descope it:** Acknowledge that union proximity (corporate family) is the proxy and update all documentation. Simpler but loses the "hot shop effect."

### D5: When to tackle non-union employer scoring?
- **Now (before launch):** Makes the platform dramatically more useful but is a major effort.
- **After launch with union-only:** Get feedback from real users first, then expand.
- **Parallel track:** Start scoring non-union employers using the factors that already work (OSHA, WHD, size, contracts, industry growth) while continuing to refine union-employer scoring.

---

## Appendix: Effort Estimates Summary

| Tier | Items | Total Effort | Cumulative |
|------|-------|-------------|------------|
| Tier 0 (Trust) | 4 items | 9-16 hours | 9-16 hrs |
| Tier 1 (Foundation) | 5 items | 12-23 hours | 21-39 hrs |
| Tier 2 (Launch-ready) | 5 items | 14-23 hours | 35-62 hrs |
| Tier 3 (Expansion) | 4 items | Large/strategic | Ongoing |

Tier 0 + Tier 1 combined is roughly 2-5 focused work days. These address the most critical trust and functionality issues.
