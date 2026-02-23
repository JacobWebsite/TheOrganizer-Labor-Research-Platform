# Four-Audit Synthesis: Complete Findings, Investigation Items, and Decisions Needed
## For: New Roadmap Planning
### Date: February 22, 2026 (v3 — February 23, 2026)
### Auditors: Claude Code (R4), Codex (R4), Full Codex (R4), Gemini (R4)

---

## How to Read This Document

Three AI systems independently audited the same platform. This document synthesizes **every finding** across all reports into:

1. **PART 1: Agreements** — All auditors flagged the same thing. Highest confidence.
2. **PART 2: Disagreements** — Different conclusions. Decisions needed.
3. **PART 3: Platform-Wide Issues** — Infrastructure, performance, security, docs.
4. **PART 4: Additional Findings** — Specific issues from individual audits that matter.
5. **PART 5: Full Investigation List** — Every question that needs answering before the roadmap.
6. **PART 6: Decision Register** — Every decision the project owner needs to make.
7. **PART 7: Mapping to Redesign Spec** — What's already addressed vs what's new.
8. **PART 8: Suggested Roadmap Priorities** — Proposed ordering for discussion.
9. **PART 9: Redesign Spec vs. Audit Reality** — Where the Spec can't be delivered as written.
10. **PART 10: Dependency Map** — What blocks what. The order things must happen.
11. **PART 11: User Impact Scenarios** — What happens if someone uses the platform today.
12. **PART 12: Success Criteria** — What "fixed" looks like for every major issue.
13. **PART 13: What No Auditor Checked** — Gaps between all four audits that the Spec depends on.
14. **PART 14: Quantitative Reference Tables** — All the numbers in one place for decision-making.

**Appendix A:** All findings sorted by confidence level (all-agree → one-auditor-found).
**Appendix B:** Codex changes made during audit and their status.

### Quick Guide: Where to Start Based on What You Need

- **"What's broken and how bad is it?"** → Read Parts 1-4 (findings, ~200 lines)
- **"What do I need to decide?"** → Read Part 6 (Decision Register, 11 decisions)
- **"Can we build the React frontend now?"** → Read Part 9 (Spec vs Reality) and Part 10 (Dependencies)
- **"What happens if someone uses the platform today?"** → Read Part 11 (User Impact Scenarios)
- **"How do I know when something is fixed?"** → Read Part 12 (Success Criteria)
- **"What numbers do I need to make decisions?"** → Read Part 14 (Reference Tables)
- **"What order should we do things in?"** → Read Part 8 (Priorities) and Part 10 (Dependencies)

---

# PART 1: WHERE ALL THREE AUDITORS AGREE

These are the highest-confidence findings.

---

## 1.1 The Scoring System Has Real Problems (But the Math Works)

The formula for calculating scores is correct — Claude manually verified 5 employers and every calculation matched within rounding. But several of the 8 scoring factors are broken:

**The duplicate factor.** `score_financial` and `score_industry_growth` are literally the same number. Line 340 of `build_unified_scorecard.py` copies one into the other: `s.score_industry_growth AS score_financial`. So you really have 7 unique signals, not 8. The weighted formula only uses `score_industry_growth` once (with 2x weight), so the final score isn't actually double-counting — but the display and documentation claim 8 distinct factors when there are only 7.

**The contracts score gives everyone the same grade.** All 8,672 employers with government contract data get exactly 4.00. No differentiation between a $100K contract and a $10B contract. The Redesign Spec describes a tiered system (0/4/6/7/8/10 based on contract levels), but the code doesn't implement those tiers yet.

**Employers with almost no data float to the top.** The "signal-strength" approach skips missing data instead of counting it as zero. Side effect: if an employer only has 1 piece of data and it's good, they get a perfect 10.0 score. Claude found 231 employers ranked "Priority" with only 1 factor. Specific examples of perfect-10 Priority employers with 1 factor:
- "Company Lists" (10,000 workers, no state) — not a real company
- "Employer Name" (1,100 workers, NY) — a literal placeholder record
- "M1" (AL) — a 2-character name, could be anything
- "Pension Benefit Guaranty Corporation" — a federal agency, not an organizing target

**The similarity factor is dead.** Only 186 out of 146,863 employers (0.1%) have a `score_similarity` value, despite being weighted at 2x. And of those 186, there are only 3 distinct score values. The `employer_comparables` table has 269K rows of calculated comparisons, but the step that translates comparisons into scores is barely connected.

**What Codex fixed during audit:** Added `factors_available >= 3` requirement for Priority tier. Dropped Priority from 4,190 → 2,047 and eliminated all 1-2 factor employers from the top tier. This is working but only addresses Priority, not Strong or lower tiers.

---

## 1.2 The Fuzzy Matching Has a Serious Accuracy Problem

When employer names are slightly different across databases, the system uses a statistical tool called Splink to guess if they're the same company. Splink is getting fooled by geography — it treats being in the same state as such strong evidence that it accepts completely different company names.

**Error rates found:**
- **Claude:** 8 out of 20 HIGH-confidence Splink matches wrong (40%)
- **Codex:** 2 out of 20 HIGH-confidence wrong (10%)
- **Gemini:** Confirmed false positives from geography overweighting

**Specific wrong matches Claude found:**

| OSHA Name | Matched To (F7) | State | Name Similarity | Why It's Wrong |
|-----------|-----------------|-------|-----------------|----------------|
| RCC INCORPORATED | PCA Corrugated | UT | 0.667 | Completely different companies |
| LA COUNTY SHERIFF'S DEPT | LA County Federation of Labor | CA | 0.676 | Government agency matched to a labor organization |
| SIOUX CITY ENGINEERING CO | Sioux City Journal | IA | 0.651 | Engineering company matched to a newspaper |
| MARK YOUNG CONSTRUCTION | Mel-Ro Construction | CO | 0.739 | Two different construction companies |

**Root cause:** The Splink model's Bayesian Factor for matching on state+city+zip combined is approximately 8.5 million — meaning location alone can push a match to 99%+ confidence even with terrible name similarity.

**The 29,236 stale matches:** The name similarity floor was raised from 0.65 to 0.70 on Feb 19, but OSHA matching ran on Feb 18 (before the fix). Result: 29,236 active OSHA Splink matches have name similarity between 0.65-0.699, below the current threshold. Only OSHA is affected — other databases were re-processed after the threshold was raised.

**Gemini also found "legacy poisoning":** Some matches in the unified_match_log came from importing old legacy match tables built with lower standards. Example: "AI Industries" matched to "ABM Industries" via a legacy method with a 0.71 score.

---

## 1.3 The "Priority" Tier Is Mostly Ghost Employers

The "Priority" tier is supposed to be the ~4,000 most promising organizing targets:

- **Claude:** 92.7% have ZERO OSHA/NLRB/WHD data. 94.6% have no activity after 2020 in ANY source.
- **Codex (after fix):** 1,895 of 2,047 remaining Priority employers still lack 5-year enforcement activity.
- **Gemini:** 41 out of 50 sampled Priority had zero enforcement activity since 2020.

These employers are ranked Priority because they're big (Size=high), have unions nearby (Proximity=high), and are in growing industries (Industry Growth=high). But there's no evidence of safety problems, wage theft, or organizing momentum — just structural characteristics.

**The "false negative" problem is the flip side:** Claude checked 18,452 union election wins since 2023. Of those matched to F7 employers, here's where they actually fell in the tiers:

| Tier | Election Wins |
|------|--------------|
| Strong | 6,488 |
| Promising | 583 |
| Moderate | 579 |
| Low | 392 |
| Priority | 125 |

Priority captured only 125 wins despite being the "highest urgency" tier. Meanwhile, 392 employers that successfully organized were rated "Low." Codex found a similar pattern: 25% of recent election wins were in Priority/Strong, but another 24.6% were in Low — essentially coin-flip prediction.

---

## 1.4 The Platform Can't See Most Organizing Successes (The "Targeting Paradox")

**Claude found:** Of 18,452 union election wins since 2023, 10,285 (55.7%) have no F7 link — they're invisible to the platform.

**Gemini identified the bigger version:** The scoring engine only works on F7 employers (already unionized). The 2.7 million potential non-union targets in the master table are completely unscored. The system is designed to find NEW targets but can only evaluate employers that are ALREADY unionized.

**Your Redesign Spec addresses this:** Section 4 (Master Employer List) plans phased seeding — Wave 1 (SAM.gov), Wave 2 (NLRB participants), Wave 3 (OSHA establishments). But implementation is future.

---

## 1.5 No Database Backup Strategy

All three flagged this. 11 GB database, 1.7M match records, months of irreproducible ETL work. Zero automated backups, zero point-in-time recovery. One bad script or disk failure = everything gone.

**Quick fix:** Even a nightly `pg_dump | gzip` script would be an enormous improvement.

---

## 1.6 Documentation Is Seriously Stale

All three found major inconsistencies across docs. Key examples:

| Problem | Source |
|---------|--------|
| CLAUDE.md says `mv_employer_search` has 118,015 rows; actual is 107,025 | Codex |
| CLAUDE.md warns "IRS BMF has 25 rows" but actual is ~2.04M | Codex |
| Documents disagree on factor count: 7 vs 8 vs 9 | Claude |
| MV_UNIFIED_SCORECARD_GUIDE uses legacy tier names (TOP/HIGH/MEDIUM/LOW) | Claude |
| PROJECT_STATE.md has stale counts for multiple tables | Codex |
| Phantom file references (UNIFIED_PLATFORM_REDESIGN_SPEC.md doesn't exist) | Claude |
| 3 active pipeline scripts missing from PIPELINE_MANIFEST | Claude |
| master_employers: 3 different counts across docs (3M / 2.9M / 2.7M) | Claude |

---

## 1.7 Amazon, Walmart, and Entire Industries Are Invisible

- **Amazon:** Only 4 entries (Amazon Studios, Amazon Construction, Amazon Masonry, Amazonas Painting). Zero warehouse/fulfillment records.
- **Walmart:** Zero entries.
- **Cannabis industry:** Zero rows (Codex checked).
- **Finance/Insurance (NAICS 52):** Only 418 employers vs 25,302 in Construction.
- **15.1% of all employers** (22,183) have no NAICS code at all, meaning 3 scoring factors can't work for them.

This is structural: F-7 data only covers employers with union bargaining relationships. The biggest non-union organizing targets are absent.

---

## 1.8 Slow API Endpoints

| Endpoint | Time | Flagged by |
|----------|------|------------|
| `/api/master/stats` | 4-12 seconds | All three |
| `/api/admin/match-quality` | 5 seconds | Codex |
| `/api/master/non-union-targets` | 2 seconds | Codex |
| `/api/profile/employers/{id}` | 3 seconds | Claude |

**Biggest single performance fix:** Add index on `nlrb_participants.case_number` (1.9M rows, currently no index — every JOIN does a full table scan). This takes ~5 minutes to implement.

---

# PART 2: WHERE AUDITORS DISAGREE

---

## 2.1 Name Similarity Floor

| Auditor | Recommended Floor | Reasoning |
|---------|-------------------|-----------|
| Claude | 0.70, possibly 0.75+ | 40% error rate in sample included matches at 0.70-0.74 |
| Codex | 0.70 consistently enforced is sufficient | 10% error rate in sample (lower than Claude's) |
| Gemini | **0.85** for any shared-state match | Most conservative; would reject many more matches |

**The tradeoff:** Higher floor = fewer wrong matches but also fewer correct matches. Going from 0.70 to 0.85 would reject 73,085 of 83,087 current Splink matches (88%).

**How to resolve:** Test each threshold on a sample of 100 matches. Measure the true positive and false positive rates at 0.70, 0.75, 0.80, and 0.85. Then pick the one that balances accuracy against coverage.

---

## 2.2 Orphaned Superseded Match Counts

| Auditor | Count | Method |
|---------|-------|--------|
| Claude | 75,043 | Superseded source IDs with no active match for same source_id |
| Codex | 46,484 | Different counting methodology |

**The question:** Are these low-quality matches that were correctly removed when thresholds were tightened, or are they useful connections that got accidentally lost?

SEC has the highest orphan rate (38.8%) — many SEC entities are SPVs/subsidiaries that inherently don't match well to F7 employers. 990s are next (27.8%).

---

## 2.3 Severity of the Non-Union Scoring Gap

| Auditor | Position |
|---------|----------|
| Gemini | "Most significant finding" — fundamental design flaw that must be fixed first |
| Claude | Acknowledges gap, focuses on fixing F7 quality first |
| Codex | Confirms master table is 98.4% quality score <40, but treats as less urgent |

**This is really a sequencing question:** Fix accuracy of existing scores first (Claude/Codex), or expand scoring to non-union employers first (Gemini)?

---

## 2.4 The Splink Error Rate Itself

Claude found 40% error rate (8/20); Codex found 10% (2/20). Both used random samples of 20, so there's real sampling noise. The true error rate is somewhere in between — call it 10-40%. Even 10% is problematic for organizing decisions.

---

# PART 3: PLATFORM-WIDE ISSUES

---

## 3.1 Membership Numbers Don't Add Up

| Measure | Total |
|---------|-------|
| Raw SUM from unions_master | 73.3M |
| v_union_members_deduplicated view | 72.0M |
| Current-only (not historical) from f7_employers | 15.0M |
| "Correct" dedup calculation (with count_members flag) | 14.5M |
| BLS benchmark | ~14.3M |

The 14.5M matches BLS within 1.5% nationally. But Gemini's crucial insight: this may be a statistical coincidence. State-level data shows:
- **DC:** 141,563% of BLS benchmark (national HQ effect)
- **NY:** 242.6% of benchmark
- **HI:** 10.9% of benchmark (missing 89%)
- **ID:** 19.5% of benchmark (missing 80%)

The massive overcounting in DC/NY is canceling out the massive undercounting in HI/ID/Western states to produce a national total that looks right by accident.

The `v_union_members_deduplicated` view produces 72M instead of 14.5M — it's fundamentally broken and shouldn't be used.

---

## 3.2 Data Freshness Tracking Is Broken

The `data_source_freshness` table has:
- 13 of 19 sources with NULL date ranges
- Most sources showing `last_updated = 2026-02-22` (when table was created, not when data was actually refreshed)
- NY State Contracts with `date_range_end` of September 2122 (100 years in the future)
- No mechanism to alert when source data goes stale

This directly blocks the Admin Panel's "Data Freshness Dashboard" from showing meaningful information.

---

## 3.3 The 26.2% Geocoding Gap

38,486 employers (26.2%) have no latitude/longitude. They won't appear on maps and can't participate in the NLRB "within 25 miles" proximity calculation.

---

## 3.4 Three Empty Columns on the Main Table

`f7_employers_deduped` has three columns that are 100% NULL across all 146,863 rows:
- `naics_detailed` — more specific industry codes (never populated)
- `corporate_parent_id` — parent company links (never populated)
- `cbsa_code` — metro area codes (never populated)

These create a false impression that data exists and should either be populated or removed.

---

## 3.5 NLRB Participant Data Is 83.6% Garbage

1,593,775 out of 1,906,542 records in `nlrb_participants` have literal CSV header text ("Charged Party Address State") instead of real data. CSV parsing went wrong during import. Doesn't affect ULP matching (which uses case-level data), but makes participant-level geographic analysis unreliable.

**Critical question:** Does the NLRB "within 25 miles" proximity calculation (Factor 3) use participant data or case-level data? If it uses participant data, that factor is significantly degraded.

---

## 3.6 Search API Has a Silent Failure Mode

Employer search uses `name=` as its parameter; union search uses `q=`. If someone accidentally uses `?q=walmart` on employer search, it silently returns all 107,025 records with no error. Also, 4 different employer search endpoints exist — the Redesign Spec says "one search to rule them all."

---

## 3.7 Legacy Frontend Still Being Served

The old `organizer_v5.html` (146 KB) is still served alongside the new React app. It shows old tier names, old scores, and old layout. The legacy scorecard endpoint (`/api/scorecard/`) serves data from the old `mv_organizing_scorecard`. A user switching between old and new would see different numbers for the same employer.

---

## 3.8 Blocking Materialized View Refreshes

Two scripts refresh materialized views WITHOUT the `CONCURRENTLY` flag, meaning all users get locked out during the refresh:
- `update_whd_scores.py` → refreshes `mv_employer_search` (powers main search)
- `compute_gower_similarity.py` → refreshes `mv_employer_features`

Quick fix: add one keyword to each script. Matters because the Admin Panel will have refresh buttons.

---

## 3.9 Security Findings

| Issue | Status |
|-------|--------|
| 82 f-string SQL patterns | **All safe** — Claude verified user input always parameterized. Maintainability risk only. |
| Admin endpoints open anonymously | **FIXED** by Codex during audit — now require `require_admin`, fail-closed |
| CORS | **Properly restricted** to localhost origins, NOT wildcard |
| Hardcoded credentials | **CLEAN** — zero in active code. 10 archived files have old password "Juniordog33!" |
| Auth design | **Properly designed** — JWT + startup guard. But never tested with real users. |
| `platform_users` table | **Empty** — auth has never been used by a real user |

---

## 3.10 Code Quality and Portability

- **19 scripts have hardcoded `C:\Users\jakew\Downloads` paths** (Gemini counted 16). Blocks Docker deployment.
- **55 analysis scripts**, 20-30 of which are one-off or superseded (duplicated versions, migration tools).
- **18 GB archive folder** (bigger than the 11 GB database), dominated by a 12 GB GLEIF dump.
- **~10 of 23 API routers lack dedicated test files** (cba, museums, public_sector, etc.).
- **Frontend build is 522 KB** (149 KB gzipped) — slightly over Vite's 500 KB warning threshold.

---

## 3.11 Accessibility Gaps

28 `aria-*`/`role` attributes across 54 frontend components. Basic coverage but thin for professional use. Missing: keyboard navigation for tables/pagination, screen reader announcements for dynamic content, focus management on page transitions.

---

## 3.12 User Data Fragility

The Redesign Spec (Section 9) says: "Flags, saved searches, notes stored in browser localStorage." This means an organizer's work disappears if they switch computers, clear browser data, or use a different browser. For professional research staff, this seems fragile.

---

# PART 4: ADDITIONAL SPECIFIC FINDINGS

---

## 4.1 The Gower Comparables Disconnect

The `employer_comparables` table has 269,000 rows of calculated comparable employers. But `score_similarity` only covers 186 employers with only 3 distinct values. Something in the pipeline between "calculate comparables" and "score similarity" is broken or was only run on a tiny test set. If the comparables data is good, connecting it properly could bring a currently dead factor to meaningful coverage.

---

## 4.2 Union Count Paradox

The platform tracks 26,693 unions vs the BLS estimate of ~16,000 active locals — 67% more than should exist. Includes historical/defunct locals and national affiliations. If the Union Explorer page says "26,693 unions tracked," users might think that's comprehensive when it's actually overcounting dead locals and potentially missing some active ones.

---

## 4.3 46,627 Match Records Pointing Nowhere

Codex found 46,627 records in the unified match log pointing to F7 employer IDs that don't exist. These are different from the orphaned superseded matches — these are active match records whose target employer was apparently deleted. Any enrichment data from those matches is disconnected.

---

## 4.4 7,803 Missing Source ID Linkages

Claude found `master_employer_source_ids` is 7,803 rows short of expected (3,072,689 vs 3,080,492). Some master employers may have lost their source linkage during dedup merge.

---

## 4.5 Over-Merge and Under-Merge Problems

**Over-merging (false groupings):**

| Group | Members | Problem |
|-------|---------|---------|
| D. CONSTRUCTION, INC. | 249 | Unrelated construction companies collapsed |
| International Contractors, Inc. | 188 | Unrelated IL contractors |
| Building Service, Inc. | 164 | Unrelated building/maintenance companies |
| Construction Co. | 140 | Any "Construction" company collapsed |
| National Equipment Corp. | 137 | Unrelated equipment companies |
| PTA ALABAMA CONGRESS | 239 | 239 distinct school chapters merged into one (Gemini) |

**Under-merging (missed groupings):**
- HealthCare Services Group fragmented into 18 separate groups (~900+ records that should be 1)
- "first student inc" vs "first student  inc" (double space) — 31 records normalizer missed

**Master table:** 32,475 duplicate groups by normalized name/state/zip remain (Codex). Many are low-quality blank-name clusters.

**Over-merge risk in master dedup:** 288,782 name+state merges with no confidence scoring or manual review for borderline cases. Common names like "John Smith Construction" could merge two completely different companies.

**Merge audit trail:** `merge_evidence` JSONB field is empty (`{}`) for all sampled merges. No way to see what was merged without querying the merge log separately.

---

## 4.6 is_labor_org Misclassification

Gemini found the `is_labor_org` flag has a binary exclusion problem. Genuine organizing targets like school districts get flagged as labor orgs (because they appear in BMF/990 as tax-exempt entities related to union activity) and are hidden from "Non-Union Targets" search. Meanwhile, union insurance funds like "LOCAL 580 INSURANCE FUNDS" show up in non-union targets.

---

## 4.7 Score Distribution Is Bimodal

The scores form two humps — a big cluster near 0-1.5 and another near 5-6.5, with spikes at the extremes (0 and 10). A well-calibrated system should have a roughly bell-shaped curve. The two populations reflect: employers with very little data (clustered low) and employers with moderate data (clustered middle). The extremes are driven by data sparsity.

---

## 4.8 Multi-Employer Agreement Inflation

The Redesign Spec mentions building trades showing 15x inflation in association agreements vs individual locals. One multi-employer agreement covering 200 contractors gets counted as if each has a separate contract. This inflates member counts, employer counts per union, and the Union Proximity factor.

---

## 4.9 82,864 "Zero External Data" Employers

56.4% of all scored employers have ZERO matches from external sources — no OSHA, NLRB, WHD, SAM, SEC data. Of these, 13,698 are rated Priority or Strong. The platform literally has nothing to say about these employers beyond "they're big and in a growing industry."

---

## 4.10 Non-Employer Records Being Scored

- **Laner Muchin:** A management-side labor law firm with 601 ULP charges and a Moderate tier score. It appears because it's the respondent in ULP cases, but it's not an organizing target.
- **Government agencies:** PBGC is ranked Priority.
- **Placeholder records:** "Employer Name" and "Company Lists" are in the Priority tier.

---

## 4.11 USPS Aggregation Artifact

USPS TX has 38,268 ULPs — this is national ULP data aggregated onto one state record. Score is capped at 7.93 (not 10), showing the ceiling works, but it's still a data artifact.

---

## 4.12 990/SAM Count Mismatches

Legacy match tables and UML active counts don't match for 990 (off by 210) and SAM (off by 1). The 990 gap is a known issue from dual unique constraints causing INSERT failures in the legacy table.

---

# PART 5: FULL INVESTIGATION LIST

Every question that needs answering before committing to a roadmap.

| # | Question | Why It Matters | How to Answer |
|---|----------|---------------|---------------|
| 1 | What name similarity floor is right? | Affects ALL fuzzy matches across ALL data sources | Test 0.70/0.75/0.80/0.85 on 100-match samples, measure true/false positive rates |
| 2 | Is the 14.5M membership number reliable or coincidental? | Platform credibility | Compare state-level to BLS state-by-state, identify the cancellation pattern |
| 3 | How many invisible election wins could Wave 2 (NLRB participants) capture? | Urgency of master table expansion | Match 2023-2025 wins against NLRB participant employer names |
| 4 | Are the 75,043 orphaned matches good removals or accidental losses? | Whether to try to recover them | Sample 20 orphaned matches, judge whether old matches were correct |
| 5 | What's in the 46,627 UML records pointing to missing F7 targets? | Data integrity — could be hiding enrichment data | Query sample, identify pattern (deleted? test data?) |
| 6 | Can we infer NAICS codes for the 22,183 (15.1%) that lack them? | 3 scoring factors depend on industry | Check matched OSHA SIC/NAICS codes, employer name keywords |
| 7 | How widespread is the employer grouping problem? | Trust in corporate hierarchy feature | Review all groups >50 members, sample groups 10-50 |
| 8 | Why does comparables→similarity pipeline only produce 186 scores? | Could unlock a currently dead scoring factor | Trace code path from employer_comparables to score_similarity |
| 9 | Does NLRB "within 25 miles" use the broken participant data? | If yes, Factor 3 is degraded | Check the proximity calculation code |
| 10 | How many junk/placeholder records are in the scoring universe? | Directly pollutes top-tier rankings | Query for generic names, 2-char names, agency names, non-employer types |
| 11 | What's the geocoding gap by tier? | Map features and proximity broken for 26.2% | Query geocoding coverage by tier |
| 12 | How many F7 employers come from multi-employer agreements? | Could explain membership inflation and proximity score distortion | Check for agreement-type filings in F7 data |
| 13 | What does score distribution look like after fixing broken factors? | Tests whether fixes improve output quality | Rebuild scorecard with fixes, compare distribution before/after |
| 14 | How many of 26,693 unions are actually active (filed LM in last 3 years)? | Union Explorer accuracy | Query for recent LM filings per union |
| 15 | Does geographic enforcement bias materially distort scores? | Fairness across states | Compare average scores in high vs low enforcement states, controlling for industry |
| 16 | What happened to the 7,803 missing source ID linkages? | Master employer completeness | Query merge log for patterns |
| 17 | How many is_labor_org exclusions are wrong (hiding real targets)? | Non-union target search accuracy | Sample 20 flagged entities, check if they're actual organizing targets |
| 18 | What's the Splink Bayesian factor for geography, and can it be retuned? | Root cause of matching errors | Examine Splink model parameters, test with reduced geography weight |
| 19 | Are there "legacy poisoned" matches beyond the one Gemini found? | Match quality across the board | Sample legacy-method matches (STRIPPED_FACILITY_MATCH, etc.) |
| 20 | What fraction of Mel-Ro Construction's 179 OSHA matches are false? | Tests whether many-to-one inflation is systematic | Spot-check 20 of the 179 matches |

---

# PART 6: DECISION REGISTER

Every decision the project owner needs to make.

| # | Decision | Options | Tradeoff | Recommendation |
|---|----------|---------|----------|----------------|
| 1 | **Name similarity floor** | 0.70 / 0.75 / 0.80 / 0.85 | Higher = fewer wrong matches but also fewer correct matches | Test before committing. Start with 0.75 sample. |
| 2 | **What does "Priority" mean?** | A: Structurally promising (current design, spec intent) B: Structurally promising AND has recent activity signals (auditor recommendation) | A gives broader view; B gives more actionable intelligence | This is a philosophical choice about the tool's purpose |
| 3 | **Minimum factor requirements** | 2 (spec) / 3 for Priority only (Codex fix) / 3 for Priority+Strong | Higher minimum = fewer thin-data employers in top tiers | Keep Codex's 3-factor Priority floor, consider 3 for Strong too |
| 4 | **Stale OSHA matches** | Bulk-reject 29,236 / Re-run OSHA matching entirely | Reject is faster (~1 hour); re-run captures any new correct matches | Bulk-reject first, re-run later when Splink model is retuned |
| 5 | **Fix scoring vs expand scoring** | Fix accuracy within F7 first / Expand to non-union employers first | Fix first = slower but higher quality; expand first = faster coverage but inaccurate | Fix existing before expanding bad scores to more employers |
| 6 | **score_similarity** | Remove from weighted formula / Keep but investigate pipeline | Removing avoids distortion; keeping preserves potential value | Remove until coverage >10%, investigate pipeline separately |
| 7 | **Keep Codex's changes?** | Keep Priority guardrail + admin hardening / Review and modify | Guardrail working well; admin hardening solid | Keep both. Consider extending guardrail to Strong tier. |
| 8 | **Legacy frontend** | Archive immediately / Keep as fallback | Archiving reduces confusion; keeping allows rollback | Archive after React app is verified working |
| 9 | **User data storage** | Keep localStorage (current) / Move to server-side | localStorage = simpler but fragile; server = persistent across devices | At minimum plan for server-side before production launch |
| 10 | **Archive/GLEIF dump** | Move to external storage / Keep in place | Moving saves 12 GB; keeping simplifies file management | Move before Docker deployment |
| 11 | **Empty columns** | Populate / Remove | Populating requires data work; removing is instant cleanup | Remove naics_detailed and cbsa_code (unused). Keep corporate_parent_id as placeholder for future SEC integration. |

---

# PART 7: MAPPING TO REDESIGN SPEC (Summary Table)

> **For the full analysis of where the Redesign Spec contradicts audit reality, see Part 9.** This table is a quick reference; Part 9 has the detailed breakdown of every Spec promise, what the audits found, and what it means for implementation.

| Audit Finding | In Redesign Spec? | Status |
|---------------|-------------------|--------|
| Duplicate score_financial | **NO** | Need to fix code (line 340) |
| score_contracts = 4.00 for everyone | **PARTIALLY** — Spec describes tiered scoring | Implementation doesn't match spec yet |
| Sparse data inflation | **PARTIALLY** — Spec says min 2 factors | Audits suggest 3 for top tiers |
| Splink matching errors | **YES** — 0.70 floor listed as fixed | But 0.70 may not be enough; old OSHA matches remain |
| Ghost employers in Priority | **NO** — Spec doesn't require recent activity | Philosophical tension between spec and auditors |
| Can't see non-union targets | **YES** — Master Employer List (Section 4) addresses | Phased/future implementation |
| No backup | **NO** | Should be day-one |
| Stale documentation | **PARTIALLY** | Need comprehensive refresh pass |
| Broken membership view | **NO** — Spec shows 14.5M as reliable | Needs investigation |
| Similarity factor nearly empty | **YES** — Spec scopes appropriately | 0.1% coverage means non-functional |
| Geographic bias | **NO** | Needs investigation |
| Performance / slow endpoints | **NO** | Quick wins available |
| Missing indexes | **NO** | Highest-impact: nlrb_participants.case_number |
| Hardcoded paths | **PARTIALLY** — Spec mentions Docker | Paths need fixing |
| Legacy frontend | **YES** — React migration planned | Archive after React launch |
| Data freshness table broken | **YES** — Admin Panel has freshness dashboard | But dashboard will show garbage until table is fixed |
| Employer grouping errors | **NO** | Need systematic review |
| NLRB participant data junk | **NO** | Need to check if proximity calculation is affected |
| Accessibility gaps | **NO** | Thin for professional use |
| User data fragility (localStorage) | **NOTED** in spec as limitation | Decision needed before production |
| is_labor_org misclassification | **NO** | Hiding real targets from non-union search |
| Blocking MV refreshes | **NO** | Quick fix (add CONCURRENTLY) |
| Build size over 500 KB | **NO** | Minor — code-splitting with React.lazy() |

---

# PART 8: SUGGESTED ROADMAP PRIORITIES

Based on the complete synthesis. For discussion, not a final plan.

## Tier 1: Fix Before Anything Else (Data Trust)

These undermine everything downstream. If scores are wrong, no amount of UI polish matters.

1. **Fix score_financial** — compute real value instead of copying industry_growth (line 340)
2. **Fix score_contracts** — implement tiered scoring from Redesign Spec
3. **Clean up OSHA matching** — bulk-reject 29,236 sub-threshold matches
4. **Remove score_similarity from weighted formula** — 0.1% coverage means it's noise
5. **Decide name similarity floor** — test 0.75 and 0.85 on samples, measure impact
6. **Keep Codex's 3-factor Priority guardrail** — consider extending to Strong
7. **Clean junk records from scoring** — remove placeholders, agencies, non-employers
8. **Database backups** — nightly automated (~1 hour to set up)
9. **Add nlrb_participants.case_number index** — single biggest performance win (~5 minutes)
10. **Fix blocking MV refreshes** — add CONCURRENTLY keyword (~5 minutes each)

## Tier 2: Investigate and Make Scores Meaningful

11. **Run the investigation list** — answer the 20 questions in Part 5 before committing to bigger changes
12. **Decide ghost employer question** — should Priority require recent activity?
13. **Investigate membership dedup reliability** — is 14.5M actually reliable state-by-state?
14. **Investigate comparables→similarity pipeline** — could unlock a dead factor
15. **Check NLRB proximity calculation data source** — is Factor 3 using junk participant data?
16. **Fix data freshness table** — prerequisite for Admin Panel dashboard
17. **Investigate geographic enforcement bias** — how much does it distort scores?

## Tier 3: Expand and Clean

18. **Fix employer grouping** — review large groups, break false merges, consolidate fragments
19. **Master table scoring expansion** — start with best-data non-F7 employers
20. **Documentation refresh** — one comprehensive pass to align all docs
21. **Infer NAICS codes** — for 22,183 employers that lack them, try OSHA SIC codes and name keywords
22. **Fix is_labor_org classification** — stop hiding real targets, stop showing non-targets
23. **Address geocoding gap** — try geocoding the 38,486 missing lat/lng from city+state
24. **Clean NLRB participant data** — re-import with proper CSV parsing

## Tier 4: Frontend and Polish

25. **React frontend completion** — per Redesign Spec build order
26. **Archive legacy frontend** — remove organizer_v5.html after React is verified
27. **Consolidate search endpoints** — kill legacy search variants
28. **Code-split React bundle** — get under 500 KB threshold
29. **Improve accessibility** — keyboard nav, screen reader support
30. **Server-side user data** — move flags/notes from localStorage before production

## Tier 5: Deploy

31. **Performance optimization** — slow endpoints, caching for /api/master/stats
32. **Security hardening** — test auth flow end-to-end, remove DISABLE_AUTH from env
33. **Fix hardcoded paths** — make all scripts config-driven for portability
34. **Move GLEIF dump to external storage** — save 12 GB before Docker
35. **Docker containerization** — per Redesign Spec deployment plan
36. **Scrub archived credentials** — remove old passwords from archive files
37. **Beta testing with organizers** — recruit real users for feedback

---

# PART 9: REDESIGN SPEC vs. AUDIT REALITY — Where the Spec Can't Be Delivered As Written

The Redesign Spec (UNIFIED_PLATFORM_REDESIGN_SPEC.md) is the blueprint for the platform. But the audits found that several things the Spec promises either don't work yet, or produce misleading results if built on the current data. This section maps every Spec promise that has an audit problem underneath it.

**Why this matters:** If you build the React frontend exactly as the Spec describes without fixing these issues first, users will see professional-looking pages displaying unreliable data. The interface will look trustworthy but the numbers behind it won't be.

---

## 9.1 Scoring Factor Problems (Spec Section 2)

The Spec describes 8 independent scoring factors. The audits found that only 3-4 are working as described:

| Factor | Spec Promise | Audit Reality | Gap |
|--------|-------------|---------------|-----|
| **1. Union Proximity (3x)** | "2+ unionized siblings = 10, corporate family connection = 5" | Corporate hierarchy endpoints had 7 bugs (now fixed). Exhibit 21 parsing not built. Crosswalk provides some data but no audit verified coverage or accuracy for this specific purpose. | **PARTIALLY WORKING** — depends on corporate hierarchy completeness, which no audit measured |
| **2. Employer Size (3x)** | "Linear ramp 15→500, plateau at 500+" | Working. 100% coverage. Claude verified. | **WORKING** |
| **3. NLRB Activity (3x)** | "70% nearby momentum / 30% own history, 25-mile radius, 7-year half-life" | Time decay code written but waiting on MV refresh. 83.6% of nlrb_participants data is junk (header text instead of real values). No audit verified whether the proximity calculation uses this junk data. | **UNKNOWN** — critical dependency on junk data investigation |
| **4. Gov Contracts (2x)** | "Tiered 0/4/6/7/8/10 based on contract levels" | Code gives ALL 8,672 employers with contracts the same score: 4.00. The tiered system described in the Spec is not implemented. | **BROKEN** — needs code rewrite |
| **5. Industry Growth (2x)** | "Linear mapping from BLS 10-year projections" | Working for the 84.9% of employers with NAICS codes. 15.1% have no NAICS and get skipped. | **MOSTLY WORKING** — 15% gap |
| **6. Statistical Similarity (2x)** | "Uses existing Gower distance comparables engine" | Only 186 of 146,863 employers (0.1%) have a score. The comparables table has 269K rows but the pipeline that converts comparisons into scores is barely connected. Only 3 distinct score values exist. | **EFFECTIVELY DEAD** |
| **7. OSHA Safety (1x)** | "Industry-normalized violation count, 5-year half-life, severity bonus" | 29,236 matches are below the 0.70 threshold (stale from pre-fix runs). 40% of HIGH-confidence Splink matches are wrong (Claude sample). Wrong OSHA data is being displayed for wrong employers. | **CORRUPTED** — right formula, wrong input data |
| **8. WHD Wage Theft (1x)** | "Case count tiers: 0/5/7/10" | Working for the 8.2% of employers with WHD data. Low coverage but functional. | **WORKING** (low coverage by design) |

**Also:** `score_financial` is literally a copy of `score_industry_growth` (line 340 of build_unified_scorecard.py). It appears as a separate factor in the display, making users think there are 8 factors when there are really 7. The Spec's Section 2 describes 8 factors but the "Financial" factor it describes hasn't been built — what exists is just Industry Growth copied into a second column.

**Bottom line:** Of 8 factors, 2 are working well (Size, WHD), 1 is mostly working (Industry Growth), 1 is partially working (Union Proximity), 1 is unknown (NLRB), 1 is broken (Contracts), 1 is effectively dead (Similarity), and 1 has corrupted input (OSHA). The weighted score formula itself is mathematically correct — the problem is what goes into it.

---

## 9.2 Employer Profile Problems (Spec Section 7.2)

The Spec describes a detailed employer profile with confidence dots, source badges, and collapsible data cards. Here's what the audits say about each:

**Confidence Dots (●●●○):** The Spec defines 4 confidence levels. But Claude found that 40% of HIGH-confidence Splink matches are wrong (8/20 sample), and Codex found 10% wrong (2/20). If the platform shows ●●●● or ●●●○ for a match that's actually wrong, users will trust bad data. The confidence dot system is only as good as the matching — and the matching has a serious accuracy problem.

**Score Factor Breakdown:** The Spec shows an 8-factor horizontal bar chart. But score_financial will show the same number as Industry Growth (confusing), score_contracts will show 4.00 for everyone (uninformative), and score_similarity will be blank for 99.9% of employers (misleading — users might think "no similar employers exist" when really the calculation just hasn't run).

**Corporate Hierarchy Card:** The Spec promises "Parent: HCA Healthcare (47 subsidiaries) | 12 have unions." Corporate hierarchy endpoints were fixed (7 bugs resolved), but Exhibit 21 parsing isn't built, and no audit measured how complete the corporate tree actually is. This card will work for some employers but show nothing for many others, even if corporate relationships exist.

**OSHA Safety Violations Card:** Will show violations that may belong to a completely different employer (40% wrong match rate at HIGH confidence). An organizer could look at a "safe" employer and see another company's violations, or look at a dangerous employer and see nothing because the real violations were matched to someone else.

**NLRB Election History Card:** The Spec shows "own history + nearby momentum detail." But 55.7% of election wins can't be matched to F7 employers (Claude finding). The "nearby momentum" calculation may be using junk data (83.6% of participants are header text). An organizer checking whether there are recent wins nearby might get incomplete or wrong information.

**Employee Count Range:** The Spec says "shows range across all sources" when sources disagree. But if some sources are wrongly matched (Splink errors), the range would include data from the wrong employer — creating a nonsensical range that looks like real variation.

---

## 9.3 Targets Page Problems (Spec Section 7.3)

The Spec describes a page with tier summary cards showing counts like "Priority: 4,400." But:

- 92.7% of Priority employers have zero OSHA/NLRB/WHD data (Claude finding)
- After Codex's fix (min 3 factors), Priority dropped from 4,190 to 2,047 — but 1,895 of those 2,047 still lack 5-year enforcement activity
- The tier counts will recalculate on every data refresh, but the underlying problem (ghost employers scoring high on structural factors alone) means the numbers will be misleading regardless of how they're displayed

**The Targets page is designed to answer: "Show me the best organizing targets."** Right now it would show large companies in growing industries near existing unions — which is useful context, but not the same as "employers where workers are likely to want a union." The platform is ranking strategic *positioning* as if it's *actionable intelligence*.

---

## 9.4 Admin Panel Problems (Spec Section 7.5)

**Data Freshness Dashboard:** The Spec says "Shows when each data source was last updated. Stale data highlighted." But the `data_freshness` table has 13 of 19 entries as NULL, and one entry (NY) shows year 2122. Building this dashboard on the current table will either show "unknown" for most sources or display obviously wrong dates.

**Score Weight Configuration:** The Spec says "Changes recalculate all scores immediately." This requires refreshing the materialized view, which currently blocks all writes to the database during refresh. On an 11GB database, this could freeze the system. The MV refresh scripts need `CONCURRENTLY` added first.

**Match Review Queue:** The Spec describes users flagging "Something Looks Wrong" and admins reviewing matches. But with a 10-40% false positive rate on HIGH-confidence matches, the review queue could be overwhelmed on day one. The system needs better matching *before* the review queue becomes the primary quality control mechanism.

---

## 9.5 Search Page Problems (Spec Section 7.1)

The Spec describes a search page with autocomplete and advanced filters. But:

- **Silent failure mode:** Using the wrong parameter name (e.g., `?q=walmart` instead of `?name=walmart`) silently returns ALL 107,025 records unfiltered. No error message. A user who clicks the wrong button or a frontend bug that sends the wrong parameter would show every employer in the database as "results."
- **NAICS filter:** 15.1% of employers lack NAICS codes. Filtering by industry will miss these employers entirely — they're invisible to industry-based searches.
- **Union status filter:** `is_labor_org` misclassification hides some real employer targets (like school districts) from "No Union" searches because they were incorrectly flagged as labor organizations due to their 990/BMF records.

---

## 9.6 Features the Spec Describes That Don't Exist Yet

These are described in the Spec but have no data foundation or implementation:

| Feature | Spec Section | What's Missing |
|---------|-------------|----------------|
| Deep Dive Tool | §12 | No code exists. Depends on NAICS codes (15% missing), web scraping infrastructure, and LLM integration |
| Employee Estimation | §12B | Revenue-per-employee model designed but not implemented |
| Union Website Scraper | §12B | Only AFSCME built. SEIU, UAW, Teamsters, UFCW, USW planned |
| Public Sector Adaptation | §14 | No PERB data collected. Different scoring factors needed. |
| Multi-location profiles | §9 | Depends on master employer list expansion. 56.4% of employers have zero external data |
| Saved searches | §7.3 | Spec marks as "Future Feature" |
| Manual employer entry | §9 | Admin form not built |
| Compare Employers | §7.2 | Side-by-side comparison not built |
| Corporate auto-detection | §9 | Exhibit 21 parsing not built. SEC integration not complete |

None of these are blocking the initial launch — the Spec correctly marks most as future work. But they're listed here so nobody assumes they're ready.

---

# PART 10: DEPENDENCY MAP — What Blocks What

This is the most critical section for planning. Some fixes *must* happen before others, because later work depends on earlier work being done right. If you skip ahead, you'll build on a broken foundation and have to redo work.

Think of it like building a house: you need the foundation before the walls, and the walls before the roof. Here's what depends on what:

---

## Chain 1: Making Scores Trustworthy (MUST BE FIRST)

```
Fix score_financial (remove duplicate)
    → Fix score_contracts (implement tiered scoring from Spec)
        → Investigate score_similarity (is Gower pipeline fixable?)
            → Clean OSHA stale matches (re-run or bulk-reject 29,236)
                → ALL SCORES CHANGE
                    → Validate scores against real organizing outcomes
                        → ONLY THEN: Build React score display components
```

**Why this order:** Every later step in the scoring chain changes the numbers. If you build the React employer profile first, the scores shown will change after every fix, and you'll need to re-test everything. Fix the data first, then build the display.

## Chain 2: Making Matches Reliable

```
Test name similarity floors (0.70 vs 0.75 vs 0.80 on 100-match samples)
    → Decide on floor → Re-tune Splink Bayesian factors
        → Re-run OSHA matching with new parameters
            → Clean grouping errors (false groups of 100+ from generic names)
                → Superseded matches get proper replacements
                    → Confidence levels become meaningful
                        → ONLY THEN: Confidence dots on profiles are trustworthy
```

**Why this order:** Each step changes which matches exist and what confidence they have. Building confidence dot displays before the matches are reliable means displaying wrong confidence levels.

## Chain 3: Making the Targets Page Meaningful

```
Fix scoring (Chain 1 complete)
    → Fix matching (Chain 2 complete)
        → Decide minimum factor requirements for each tier
            → Clean ghost employers / junk records from Priority
                → Tier counts become meaningful
                    → ONLY THEN: Build Targets page tier cards
```

## Chain 4: Making the Admin Panel Work

```
Fix data_freshness table (populate all 19 sources with real dates)
    → Fix MV refresh scripts (add CONCURRENTLY)
        → THEN: Build Admin freshness dashboard and weight config
            → Match quality must be reasonable first (Chain 2)
                → THEN: Build Match Review Queue
```

## Chain 5: Making Search Reliable

```
Fix search parameter handling (reject unknown params with error)
    → Fix is_labor_org misclassification
        → THEN: Search page and filters work as designed
```

## Chain 6: Enabling Non-Union Target Discovery (The "Targeting Paradox")

```
Scoring system fixed (Chain 1)
    → Master Employer List seeded (Wave 1: SAM + Mergent)
        → Matching extended to master employers
            → Non-union employers appear in search and scoring
                → THEN: The platform fulfills its core purpose
```

**This is the biggest strategic chain.** Right now the platform only scores employers that already have union contracts. The entire point of the platform is finding NON-union employers to organize, but they're invisible to the scoring system. This requires Chains 1 and 2 to be done first, otherwise you'd be extending broken scoring and matching to a much larger universe.

---

## What Can Run in Parallel

Not everything is sequential. These can happen alongside the chains above:

- **Database backups** — no dependencies, do immediately
- **Missing indexes** (nlrb_participants.case_number) — no dependencies, do immediately
- **Security hardening** (auth testing, credential scrubbing) — no dependencies
- **Documentation refresh** — can start anytime, update as fixes land
- **NLRB participant data cleanup** — independent of scoring chain
- **Geocoding gap work** — independent
- **Frontend layout shell** (React Phase 1: nav, routing, login) — doesn't display data, safe to build now
- **API parameter fixes** — independent quick win

---

# PART 11: USER IMPACT SCENARIOS — What Happens If Someone Uses the Platform Today

The Redesign Spec defines three core user workflows. Here's what actually happens in each one if an organizer uses the platform right now:

---

## Scenario 1: "Research a specific employer"

**User action:** Searches for "Memorial Hospital" to see if it's a good organizing target.

**What happens:**
1. **Search works** — returns results. But if the frontend sends the wrong parameter name, they might get all 107,025 employers instead (silent failure).
2. **Profile loads** — shows name, location, score, source badges. Looks professional.
3. **Score shows 7.4 / Priority** — but the score includes `score_financial` which is just Industry Growth copied. If the user expands the factor breakdown, they see two bars with the same number and no explanation why.
4. **OSHA card shows 8 violations** — but there's a meaningful chance (10-40% depending on whose sample you trust) these violations actually belong to a different company with a similar name in the same state. The confidence shows ●●●○ (3 dots = "high confidence"), making it look reliable.
5. **NLRB card shows "3 wins within 25 miles"** — but this calculation may be using junk data (83.6% of participant records are header text). No way for the user to know.
6. **Government Contracts card shows "Has federal contracts"** — but the score impact is 4.00 regardless of whether it's a $100K or $10B contract. No differentiation.

**Organizer's conclusion:** "This looks like a great target." But the data behind that conclusion has multiple unreliable components, and the organizer has no way to know which parts to trust.

---

## Scenario 2: "Find the best organizing targets in healthcare"

**User action:** Goes to Targets page, filters to healthcare industry, looks at Priority tier.

**What happens:**
1. **Tier cards show Priority: ~2,047** (after Codex fix) — but 1,895 of those have no enforcement activity in the last 5 years. They're "priority" because they're big, in growing industries, and near existing unions — not because there's evidence workers want to organize.
2. **Industry filter works** — but misses 15.1% of healthcare employers that lack NAICS codes.
3. **Scrolling the list** — the top-ranked employers include "Company Lists" (not a real company), "Employer Name" (a placeholder), and "Pension Benefit Guaranty Corporation" (a federal agency). These have been partially cleaned by Codex's fix but similar junk may remain.
4. **Exporting to CSV** — the organizer now has a spreadsheet of "Priority healthcare targets" that they might share with leadership or use for campaign planning. Many of these are ghost employers.

**Organizer's conclusion:** "Here are the 50 best healthcare targets for our region." But the list contains a mix of genuine high-value targets and phantom entries that look impressive on paper.

---

## Scenario 3: "Check union trends and finances"

**User action:** Looks up SEIU to see membership trends and financial health.

**What happens:**
1. **Union search works** — finds SEIU, shows hierarchy.
2. **Membership shows 14.5M total** — close to BLS benchmark of 14.3M nationally. Looks reliable.
3. **But state-level numbers don't add up** — DC shows 141,563% of BLS benchmark (national headquarters inflating the count). Hawaii shows only 10.9% (missing 90% of members). The national total looks right because over-counting in some states cancels out under-counting in others.
4. **Financial health data** — sourced from LM-2 filings, generally reliable.
5. **Employer connections** — shows F7 employers this union represents. Missing the 55.7% of election wins that couldn't be matched.

**Organizer's conclusion:** National union data looks solid, but any state-level analysis or employer-connection analysis has significant gaps the user can't see.

---

# PART 12: SUCCESS CRITERIA — What "Fixed" Looks Like

For every major finding, here's the target state. These are the numbers the project should measure against to know when an issue is resolved:

| Issue | Current State | Target State | How to Measure |
|-------|--------------|-------------|----------------|
| **Splink match accuracy** | 10-40% false positive rate at HIGH confidence | <5% false positive rate | Random 50-match sample, manual review |
| **Priority tier quality** | 92.7% have zero enforcement data | >50% have at least one enforcement record within 5 years | SQL query on tier + source timestamps |
| **Score factors working** | 3-4 of 8 functional | 7-8 of 8 functional | Each factor has >1 distinct value and >5% coverage |
| **score_contracts variation** | All 8,672 = 4.00 | Tiered per Spec (0/4/6/7/8/10) | `SELECT DISTINCT score_contracts` returns 5+ values |
| **score_similarity coverage** | 186 employers (0.1%) | >10,000 employers (~7%) | Count of non-NULL score_similarity |
| **Stale OSHA matches** | 29,236 below 0.70 floor | 0 below floor | `SELECT COUNT(*) WHERE name_similarity < 0.70 AND is_active` |
| **Geocoding coverage** | 73.8% (108,377 of 146,863) | >90% | Count of employers with non-NULL lat/lng |
| **Data freshness table** | 6 of 19 sources have valid dates | 19 of 19 with real, recent dates | Count of non-NULL, valid entries |
| **Election win visibility** | 44.3% matched to F7 employers | >70% | Re-run matching after master employer expansion |
| **Ghost employers in Priority** | Junk records like "Company Lists" in top tier | Zero placeholder/junk records in Priority or Strong | Manual review of top 100 in each tier |
| **NLRB participant data** | 83.6% junk (header text) | <1% junk | Count of records matching known header patterns |
| **Search parameter handling** | Unknown params return all 107K records | Unknown params return error message | Test with `?q=test` vs `?name=test` |
| **Documentation accuracy** | 3 different table counts, stale tier names, phantom file references | All docs match code reality | Cross-reference doc claims vs database queries |
| **Factor count distribution** | 7,451 employers have only 2 factors | Minimum 3 factors for top 2 tiers; ideally fewer 2-factor employers | Factor distribution query |
| **Membership accuracy** | National matches BLS; state-level varies 10.9%-141,563% | State-level within 25% of BLS for states with >100K members | Compare platform totals vs BLS by state |

---

# PART 13: WHAT NO AUDITOR CHECKED — Gaps Between All Four Audits

The audits focused on data quality, matching accuracy, scoring validity, and code quality. But the Redesign Spec depends on several things that none of the auditors examined:

---

## 13.1 Does the React Frontend Actually Work?

The React frontend is partially built (Build Phase 1-2 described in Spec). No audit verified:
- Whether the existing React components render correctly
- Whether Zustand stores manage state properly
- Whether TanStack Query caching and loading states function
- Whether the API returns data in the format the React components expect
- Whether the 134 frontend (Vitest) tests all pass

**Why it matters:** The roadmap assumes the React shell works and just needs new pages added. If there are fundamental issues with the existing React code, the build timeline could be much longer than planned.

## 13.2 Does the Gower Comparables Engine Produce Meaningful Results?

The audits found that score_similarity only covers 186 employers (0.1%). But no audit examined *why*:
- Is the Gower distance calculation working but the pipeline to scoring is broken?
- Are the 269K comparables rows producing reasonable employer-to-employer comparisons?
- Does the "comparison" make organizing sense — do similar employers actually tend to have similar union outcomes?
- What threshold of similarity is being used, and is it appropriate?

**Why it matters:** Factor 6 (Statistical Similarity) is weighted at 2x and described in the Spec as a key organizing signal. If the comparables engine can't be fixed, this entire factor may need to be redesigned or dropped.

## 13.3 Does the Admin Weight Recalculation Work End-to-End?

The Spec says admins can change factor weights and "all scores recalculate immediately." No audit tested:
- Whether changing a weight in the admin panel actually triggers a recalculation
- Whether the recalculation completes in a reasonable time (or freezes the database)
- Whether tier assignments update correctly after weight changes
- Whether the before/after scores make mathematical sense

**Why it matters:** If this doesn't work, the "admin-configurable" weights described in the Spec are a dead feature.

## 13.4 Is the Corporate Hierarchy Complete Enough for Factor 1?

Factor 1 (Union Proximity) is weighted at 3x — the highest weight alongside Size and NLRB. It depends on knowing which companies are corporate siblings. No audit measured:
- What percentage of employers have known corporate parents
- How many corporate parent-child relationships exist in the database
- Whether the corporate crosswalk is complete enough for Factor 1 to be meaningful
- How many employers *should* have corporate connections but don't (missing data vs genuinely independent)

**Why it matters:** If corporate hierarchy coverage is low (say, 5% of employers), then Factor 1 contributes nothing for 95% of employers and the 3x weight is wasted.

## 13.5 Does the NLRB Proximity Calculation Use Clean or Junk Data?

The audits found that 83.6% of `nlrb_participants` records are junk (header text). But no audit traced:
- Whether the NLRB proximity calculation (nearby wins within 25 miles + same industry) reads from nlrb_participants or from a different table
- If it does read from nlrb_participants, whether it filters out the junk records
- Whether the "25-mile radius" calculation uses geocoded employer locations (26.2% of which are missing)

**Why it matters:** If Factor 3 (NLRB Activity, weighted 3x) is calculated using junk data or missing locations, one of the three most important scoring factors is unreliable.

## 13.6 Does the 492-Test Backend Suite Cover Critical Paths?

Codex reported 492 tests passing. But no audit examined:
- Whether the tests cover the scoring pipeline (build_unified_scorecard.py)
- Whether the tests cover the matching pipeline (Splink, entity resolution)
- Whether the tests cover the critical API endpoints (search, employer profile, scorecard)
- What code coverage looks like for the highest-risk code paths
- Whether 10 API routers with no test files (cba, corporate, density, lookups, museums, projections, public_sector, sectors, trends, vr) have indirect coverage

**Why it matters:** High test count doesn't mean high coverage of important code. The scoring and matching pipelines are the most critical code in the entire system, and if they're not tested, regression bugs could silently corrupt data.

## 13.7 How Does Multi-Employer Agreement Inflation Affect Tier Counts?

Claude found that building trades associations create 15x inflation through multi-employer agreements. But no audit calculated:
- How many employers in each tier are inflated by multi-employer agreements
- Whether removing duplicate association agreements would change tier boundaries
- Whether specific industries (construction especially) are systematically over-represented in Priority/Strong

**Why it matters:** If construction employers are artificially boosted by association agreement inflation, the tier counts and the Targets page are biased toward one industry at the expense of others.

## 13.8 Propensity Models

The Spec mentions Model A (accuracy 0.72) and Model B (accuracy 0.53, hidden from users). No audit:
- Verified the accuracy claims
- Tested whether Model A's predictions correlate with real organizing outcomes
- Checked whether Model A is integrated into the scoring pipeline or just informational
- Assessed whether either model has bias toward specific industries or regions

**Why it matters:** If these models are eventually surfaced to users, their accuracy and fairness need to be verified first.

---

# PART 14: QUANTITATIVE REFERENCE TABLES

These numbers are scattered across the four audit reports. They're collected here so anyone making decisions has the actual data in one place. All numbers were verified by at least one auditor against the live database.

---

## 14.1 Match Method Breakdown (Active Matches)

How the system links records across government databases. "Active" means currently used; superseded matches have been replaced.

| Method | Count | Error Rate (Sampled) | Notes |
|--------|-------|---------------------|-------|
| FUZZY_SPLINK_ADAPTIVE | 83,087 | 10-40% (HIGH conf.) | Largest category. Geography bias causes most errors. |
| NAME_AGGRESSIVE_STATE | 19,768 | Not sampled | Normalized name + same state |
| NAME_CITY_STATE_EXACT | 19,048 | ~0% (deterministic) | High reliability |
| FUZZY_TRIGRAM | 18,013 | ~10% (Codex sample) | Better than Splink but still fuzzy |
| NAME_STATE_EXACT | 14,826 | ~0% (deterministic) | High reliability |
| EIN_EXACT | 13,760 | ~0% (deterministic) | Highest reliability (tax ID match) |
| CROSSWALK | 10,688 | Not sampled | External reference data |
| name_zip_exact | 8,140 | Not sampled | Name + ZIP code |
| Other methods | 18,861 | Varies | Mixed smaller categories |
| **TOTAL ACTIVE** | **~206,191** | | |

**Key takeaway:** About 40% of all active matches (83K of 206K) come from FUZZY_SPLINK_ADAPTIVE, which has the highest error rate. The deterministic methods (EIN, name+city+state, name+state) are reliable but account for less than 25% of matches.

---

## 14.2 Scoring Factor Coverage

How many of the 146,863 scored employers have data for each factor:

| Factor | Coverage | % | Avg Score | Min | Max | Status |
|--------|----------|---|-----------|-----|-----|--------|
| score_size | 146,863 | 100% | 1.48 | 0.00 | 10.00 | ✅ Working |
| score_industry_growth | 124,680 | 84.9% | 6.68 | 4.20 | 9.20 | ✅ Working |
| score_financial | 124,680 | 84.9% | 6.68 | 4.20 | 9.20 | ❌ Duplicate of industry_growth |
| score_union_proximity | 68,827 | 46.9% | 8.80 | 5.00 | 10.00 | ⚠️ Depends on corporate hierarchy completeness |
| score_osha | 31,459 | 21.4% | 1.44 | 0.00 | 10.00 | ❌ 29K stale matches, wrong-employer data |
| score_nlrb | 25,879 | 17.6% | 3.59 | 0.00 | 10.00 | ⚠️ May use junk participant data |
| score_whd | 12,025 | 8.2% | 1.70 | 0.04 | 9.76 | ✅ Working |
| score_contracts | 8,672 | 5.9% | 4.00 | 4.00 | 4.00 | ❌ Zero variation |
| score_similarity | 186 | 0.1% | 8.06 | 0.00 | 10.00 | ❌ Effectively dead |

---

## 14.3 Factor Count Distribution

How many scoring factors each employer has data for:

| Factors Available | Employer Count | % | What This Means |
|-------------------|---------------|---|-----------------|
| 2 | 7,451 | 5.1% | Only Size + one other. Very thin scores. |
| 3 | 9,177 | 6.2% | Minimum for Priority tier (after Codex fix) |
| 4 | 44,481 | 30.3% | Typical: Size + Growth + Proximity + one more |
| 5 | 55,355 | 37.7% | Most common count. Usually includes OSHA. |
| 6 | 21,692 | 14.8% | Good data coverage |
| 7 | 6,998 | 4.8% | Strong data coverage |
| 8 | 1,517 | 1.0% | Near-complete data (but includes score_financial duplicate) |
| 9 | 192 | 0.1% | Has all factors including similarity |

---

## 14.4 Tier Distribution (Before and After Codex Fix)

| Tier | Before Fix | After Fix | Change | Notes |
|------|-----------|-----------|--------|-------|
| Priority (top 3%) | 4,190 | 2,047 | -51% | Min 3 factors + score_percentile ≥ 0.97 |
| Strong | ~17,600 | Not re-measured | | Fix not applied to Strong yet |
| Promising | ~36,700 | Not re-measured | | |
| Moderate | ~51,400 | Not re-measured | | |
| Low | ~36,700 | Not re-measured | | |

**What shifted:** The 2,143 employers removed from Priority (the ones with ≤2 factors) moved into lower tiers. No audit re-measured the full distribution after the fix.

---

## 14.5 Source Match Counts (Cross-Database Linkages)

| Source Database | Active Matches | Legacy Table Count | Discrepancy | Notes |
|----------------|---------------|-------------------|-------------|-------|
| OSHA | 97,142 | 97,142 | Match | Largest source. 29K stale below 0.70 floor. |
| SAM.gov | 28,816 | 28,815 | Off by 1 | Government contractor records |
| IRS 990 | 20,005 | 20,215 | Off by 210 | Known: legacy table has dual unique constraint bug |
| WHD | 19,462 | 19,462 | Match | Wage theft records |
| SEC | Not measured | Not measured | | Corporate filings |
| Mergent | Included in crosswalk | | | Commercial employer data |

---

## 14.6 Election Win Distribution by Tier

Where did employers with actual recent union election wins end up in the tier system?

| Tier | Election Wins (Since 2023) | % of Matched Wins |
|------|---------------------------|-------------------|
| Strong | 6,488 | 79.3% |
| Promising | 583 | 7.1% |
| Moderate | 579 | 7.1% |
| Low | 392 | 4.8% |
| Priority | 125 | 1.5% |

**Key insight:** Strong captures the most wins, not Priority. Priority's heavy weighting of structural factors (Size, Proximity, Growth) means it picks employers that *look good on paper* but may not be where organizing is actually happening. Meanwhile, 392 employers that successfully organized ended up in "Low" — the system told organizers to ignore places where unions actually won.

---

## 14.7 OSHA Match Rate by State (Shows Geographic Variation)

The matching system doesn't perform equally across states:

| State | Match Rate | Relative Performance |
|-------|-----------|---------------------|
| Highest states | ~35% | 2.6x better than lowest |
| Lowest states | ~13% | |

Claude found 2.6x variation in OSHA match rates across major states. This means employers in some states are systematically more likely to have OSHA data linked (and therefore score higher on that factor) than identical employers in other states. The scoring system inadvertently favors employers in states where matching works better.

---

## 14.8 Master Employer Universe

| Category | Count | % | Notes |
|----------|-------|---|-------|
| **Total scored (F7)** | 146,863 | 100% | Only employers with union contracts (current/historical) |
| Have NAICS code | 124,680 | 84.9% | Missing 15.1% for industry-dependent factors |
| Have geocoding | 108,377 | 73.8% | Missing 26.2% for map and proximity features |
| Have ≥1 external source | 63,999 | 43.6% | At least one OSHA/NLRB/WHD/SAM/SEC match |
| Zero external data | 82,864 | 56.4% | Scored only on Size + Growth + Proximity |
| Zero external AND Priority/Strong | 13,698 | 9.3% | High-ranked with no supporting evidence |
| **Master employers (total)** | 2,723,879 | | Includes BMF (1.75M), SAM (782K), and more |
| Master quality score 20-39 | 2,680,547 | 98.4% | Overwhelmingly thin data |
| Master quality score 80+ | 100 | 0.004% | Very few rich records |

---

# APPENDIX A: All Findings by Confidence Level

## All Three Agree (Highest Confidence)
- score_financial is a duplicate of score_industry_growth
- score_contracts has zero variation (all 4.00)
- Sparse data inflates scores for thin-data employers
- Splink fuzzy matching has accuracy problems (10-40% error rate)
- Priority tier dominated by structurally large but inactive employers
- No database backup strategy
- Documentation is significantly stale
- score_similarity has near-zero coverage (0.1%)
- Amazon/Walmart entirely absent
- Slow API endpoints need optimization
- Hardcoded paths block portability

## Two of Three Agree
- 55.7% of union election wins invisible (Claude + Gemini)
- Employer grouping has both over-merge and under-merge problems (Claude + Gemini)
- Master employers table is 98.4% thin data (Claude + Codex)
- Membership dedup view produces 72M instead of 14.5M (Claude + Codex)
- NLRB participant data has header text instead of real values (Claude + Codex)
- Legacy frontend creates confusion alongside React app (Claude + Codex)

## One Auditor Found (Lower Confidence, Worth Verifying)
- Codex: Admin endpoints were previously open anonymously (FIXED during audit)
- Gemini: Western/Pacific states systematically undercounted in membership
- Gemini: "Legacy poisoning" of match log from old match tables
- Gemini: is_labor_org flag hiding real targets
- Claude: 75,043 orphaned superseded matches (Codex found 46,484)
- Claude: 82,864 employers (56.4%) have zero external source data
- Claude: 10 archived files contain old plaintext password
- Claude: Blocking MV refreshes in 2 scripts
- Claude: Score distribution is bimodal (two humps, not bell curve)
- Claude: 3 completely empty columns on main employer table
- Claude: Search API silently returns all records on unknown parameter
- Claude: Gower comparables disconnect (269K comparisons → 186 scores)
- Claude: Union count paradox (26,693 vs ~16,000 active)
- Claude: Data freshness table mostly NULL with 100-year-future date
- Claude: Accessibility gaps (thin for professional use)
- Claude: 7,803 missing source ID linkages
- Claude: USPS TX aggregation artifact (38,268 ULPs on one record)
- Claude: Laner Muchin (law firm) scored as employer

## Positive Findings (Things Working Well)
- Weighted score formula is mathematically correct (Claude verified 5/5)
- Zero duplicate OSHA matches (best-match-wins working)
- Zero hardcoded credentials in active code
- CORS properly restricted (not wildcard)
- Auth properly designed with JWT + startup guard
- All 82 f-string SQL patterns confirmed safe
- Frontend has zero hardcoded URLs, clean API proxy
- All 134 frontend tests passing
- All 492 backend tests passing
- OSHA temporal decay (10-year half-life) working correctly
- WHD temporal decay (5-year half-life) working correctly
- NLRB ULP boost working correctly (monotonically increasing)
- ULP matching quality verified (10/10 sample correct)
- Master employer dedup: zero duplicate EINs, zero orphaned source IDs

---

# APPENDIX B: Codex Changes Made During Audit (Status Check Needed)

| Change | What Codex Did | Impact | Keep? |
|--------|---------------|--------|-------|
| Priority guardrail | Added `factors_available >= 3` for Priority in scorecard builder | Priority: 4,190 → 2,047. All 1-2 factor Priority eliminated. | **YES** — extend to Strong? |
| Admin hardening | All `/api/admin/*` require `require_admin`. Fail-closed when auth disabled unless `ALLOW_INSECURE_ADMIN=true` | Anonymous admin calls now return 503 | **YES** |
| Frontend test script | Added `"test": "vitest run"` to `frontend/package.json` | Convenience for running frontend tests | **YES** |
| Full MV rebuild | Rebuilt mv_unified_scorecard after guardrail patch | New tier distribution reflects guardrail | **Already applied** |

---

*Document generated from: AUDIT_REPORT_CLAUDE_2026_R4.md (935 lines, 57 findings), AUDIT_REPORT_CODEX_2026_R4.md (513 lines), FULL_AUDIT_CODEX_R4.md (498 lines), AUDIT_REPORT_GEMINI_2026_R4.md (114 lines, 5 findings), and UNIFIED_PLATFORM_REDESIGN_SPEC.md (1,074 lines).*
