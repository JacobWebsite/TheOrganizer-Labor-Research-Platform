# Labor Relations Research Platform â€” Unified Roadmap

**Date:** February 17, 2026 (audit corrections applied February 19, 2026)
**Replaces:** All prior roadmaps â€” UNIFIED_ROADMAP_2026_02_16, TRUE Roadmap, ROADMAP_TO_DEPLOYMENT, v10 through v13, and all others. Those documents should be moved to archive.
**Built from:** Three independent AI reviews (Claude, Codex with live database verification, Gemini synthesis), 22 feedback items reviewed and decided in planning session (Feb 16-17, 2026), plus all strategy and research documents in the project. Updated Feb 19, 2026 with findings from second independent three-AI audit (Claude Code, Codex, Gemini) â€” see PROJECT_STATE.md Section 7 for full audit details.
**Status update (2026-02-19, Codex):** Problem 16 (NLRB confidence scale), Problem 17 (legacy scorecard string-ID detail 404), and Problem 19 (planner stats stale) are fixed. Problem 6 Splink hardening is complete in both main and disambiguation paths with default `token_sort_ratio >= 0.70` (override with `MATCH_MIN_NAME_SIM`).
**Status update (2026-02-19, Codex tasks 1-5):** Problem 21 code fix is complete (`build_unified_scorecard.py`), Problem 20 code alignment is complete (`build_employer_data_sources.py`) and pending MV refresh to take effect, Problem 18 rebuild script is added (`scripts/maintenance/rebuild_legacy_tables.py`), Problem 22 investigation doc is added (`docs/SCORECARD_SHRINKAGE_INVESTIGATION.md`), and Problem 14 leftovers were reduced (syntax fix in `extract_ex21.py` plus 7 analysis scripts migrated to `db_config.get_connection`).
**Status update (2026-02-19, Codex batch2):** Problem 11 is now implemented in code (`scripts/scoring/build_unified_scorecard.py`) with a true NLRB 7-year half-life decay and latest-election dominance (pending next unified MV rebuild/refresh to materialize). Phase F1 now has first-draft Docker artifacts (`Dockerfile`, `docker-compose.yml`, `nginx.conf`). New ETL script added for O*NET bulk loads (`scripts/etl/load_onet_data.py`). Database inventory auto-generation was refreshed (`scripts/maintenance/generate_db_inventory.py` -> `docs/db_inventory_latest.md`).
**Status alert (2026-02-19):** Orphan-view cleanup execution dropped legacy scorecard dependencies (`mv_organizing_scorecard` / `v_organizing_scorecard`) via cascade; legacy scorecard objects need controlled rebuild.

**IMPORTANT (2026-02-21):** The **`UNIFIED_PLATFORM_REDESIGN_SPEC.md`** was created after this roadmap and supersedes the scoring system described in Part 3 Phase E and the frontend plans in Wave 4. The Redesign Spec defines: 8-factor weighted scoring (vs 7 factors here), percentile-based tiers (Priority/Strong/Promising/Moderate/Low vs fixed-threshold TOP/HIGH/MEDIUM/LOW), React + Vite frontend migration (vs vanilla JS), and a complete page-by-page UX design. For scoring details, see the Redesign Spec Section 2. For frontend plans, see Redesign Spec Section 5. For the implementation task list, see Redesign Spec Section 16.

---

## How to Read This Document

This is the single source of truth for where the platform stands, what's wrong, and what to do next. Everything is written in plain language. When a technical concept comes up, it's explained right there.

The document has four parts:

1. **Where Things Stand** â€” an honest inventory of what exists and what works
2. **What's Wrong** â€” every known problem, ranked by severity
3. **What to Do Next** â€” a phased plan with clear checkpoints
4. **What Comes Later** â€” the bigger vision, organized by timeframe

---

## PART 1: WHERE THINGS STAND

### The Big Picture

The platform pulls together data from 18+ government and public databases â€” which employers have union contracts, which ones have safety violations, which ones have had union elections, who owns whom â€” and combines all of that into a system that helps organizers figure out where to focus their limited time and resources.

Instead of an organizer separately searching OSHA's website, the NLRB's website, the Department of Labor's website, and the SEC's website to learn about one employer, this platform has already gathered all of that information and linked it together. It then scores employers on how promising they look as organizing targets.

As of today, the core data is loaded, the matching engine works, the scoring system exists, and there are 359 automated checks that verify things are working. But the platform is **not yet ready for other people to use**. There are important accuracy problems, the security isn't production-ready, and the whole thing only runs on one laptop.

### What's in the Database

| What | Count | What This Means |
|------|-------|-----------------|
| Tables | 174 | Each table holds one specific type of information â€” employers, unions, OSHA violations, etc. |
| Views | 123 | Saved lookups that combine information from multiple tables. They don't store new data â€” they just show existing data in useful ways. (Was 186; 63 orphan views dropped 2026-02-19.) |
| Materialized views | 6 | Like views, but the computer saves the results so it doesn't have to recalculate every time. The organizing scorecard is one of these. The tradeoff: saved results can go stale if underlying data changes. |
| Employer records | 146,863 | The core list. Roughly 67,552 "current" (active union relationships) and 79,311 "historical" (past relationships that ended). |
| Total records | ~24 million | Plus ~53 million raw corporate ownership records not yet cleaned. |
| Database size | ~20 GB | About 12 GB is raw corporate ownership data that could be archived. |

### Every Connected Data Source

| Source | What It Contains | Records | Match Rate to Employers |
|--------|-----------------|---------|------------------------|
| **OLMS F-7** | Which unions bargain with which employers | 146,863 employers | This IS the core list |
| **OLMS LM** | Union financial reports | 331,238 filings | Connected through union IDs |
| **OSHA** | Workplace safety inspections and violations | 1M workplaces, 2.2M violations | 47.3% of current employers |
| **NLRB** | Union election results and unfair labor practice complaints | 33,096 elections, 1.9M participants | 28.7% of current employers |
| **WHD (Wage & Hour)** | Wage theft enforcement cases | 363,365 cases | 16.0% of current employers |
| **IRS Form 990** | Nonprofit financial filings | 586,767 filers | 11.9% of current employers |
| **SAM.gov** | Federal government contractor registry | 826,042 entities | 7.5% of current employers |
| **SEC EDGAR** | Public company filings | 517,403 companies | 1,743 direct matches |
| **GLEIF** | Global corporate ownership chains | 379,192 US entities | 3,264 linked |
| **Mergent Intellect** | Commercial business intelligence | 56,426 employers | 947 matched |
| **BLS QCEW** | Employment and wage data by industry | 1.9M rows | Via industry codes |
| **BLS Union Density** | Unionization rates by industry and state | 459+ estimates | Via industry/state |
| **BLS OEWS** | Which occupations exist in which industries | 67,699+ linkages | Via industry codes |
| **USASpending** | Federal contract awards | 47,193 recipients | 9,305 matched |
| **NYC Comptroller** | NYC labor violation records | ~9,000 records | Via name matching |
| **NY Open Book / NYC Open Data** | State and city government contracts | ~101,000 contracts | Via vendor name matching |
| **AFSCME Web Scraper** | Data from AFSCME union websites | 295 profiles, 160 employers | 73 matched (46%) |
| **EPI** | Union membership microdata | 1.4M records | Reference/validation only |

**OLMS data not yet being used:** Four annual report tables sitting in the database with valuable information that hasn't been connected to anything yet:
- `ar_disbursements_total` (216,372 records) â€” union spending by category, including how much they spend on **organizing**
- `ar_membership` (216,508 records) â€” year-over-year membership counts showing growth/decline
- `ar_assets_investments` (304,816 records) â€” union financial health (cash, investments, property)
- `ar_disbursements_emp_off` (2,813,248 records) â€” payments to union officers and employees

### How the Matching System Works

The hardest problem this platform solves is figuring out that "WALMART INC" in OSHA is the same company as "Wal-Mart Stores, Inc." in NLRB and "WAL MART STORES INC" in DOL filings. The platform uses a multi-tier approach â€” easiest and most reliable methods first, fuzzier methods as fallback:

1. **Exact EIN match** â€” same tax ID number = definitely the same entity. Gold standard.
2. **Normalized name match** â€” clean up names (remove "Inc.", "LLC", standardize abbreviations) and check for exact matches.
3. **Address-enhanced match** â€” same cleaned name AND same city/state? Very likely the same.
4. **Aggressive normalization** â€” strip even more noise from names and compare.
5. **Fuzzy matching** â€” algorithms that measure how "similar" two names look, catching typos and abbreviation differences.
6. **Probabilistic matching (Splink)** â€” a statistical model that weighs multiple pieces of evidence together to estimate the probability two records are the same entity.

Every match goes into a central log (1,738,115 entries â€” post-B4 re-runs complete) with a record of which method was used and how confident the system is.

### What's Working Well

- **The BLS benchmark validates the data.** Platform's total membership count (14.5 million workers) matches the Bureau of Labor Statistics' official number within 1.4%.
- **The matching pipeline is auditable.** Every connection between databases has a paper trail.
- **Security went from zero to reasonable.** Login protection, encrypted passwords, rate limiting, zero SQL injection vulnerabilities.
- **The test suite grew 10x.** From 37 to 457 automated checks (456 passing, 1 known failure: hospital abbreviation).
- **The frontend was modularized.** Original 10,500-line monolith split into 21 separate files.

### Key Numbers

| Metric | Value |
|--------|-------|
| NAICS industry code coverage | 84.9% of all employers |
| OSHA match rate (current employers) | 47.3% |
| NLRB match rate (current employers) | 28.7% |
| WHD match rate (current employers) | 16.0% |
| 990 match rate (current employers) | 11.9% |
| Employers with at least one external match | ~61.7% |
| Unified scorecard rows | 146,863 (all employers covered) |
| Old scorecard rows | 212,441 (post-B4 refresh) |
| Automated tests | 457 (456 passing, 1 known failure) |
| API endpoints | 160+ across 20 routers |

---

## PART 2: WHAT'S WRONG

### CRITICAL â€” Fix Before Anything Else

~~**Problem 1: The scorecard is using 10-year-old data.**~~ **FIXED (Phase A2).** OSHA `union_status` filter corrected (changed from `= 'N'` to `!= 'Y'`). Scorecard now uses all available OSHA data through 2025. MV expanded from 22,389 to 212,441 rows (after Phase A2 + B4 re-runs).

~~**Problem 2: Security is turned off by default.**~~ **FIXED (Phase D1).** Auth logic is correctly implemented. API refuses to start without `LABOR_JWT_SECRET`. `require_admin` and `require_auth` dependencies guard all write/admin endpoints. 22 auth tests pass. Local `.env` uses `DISABLE_AUTH=true` â€” this is intentional for development but must be removed before any deployment. âš ï¸ **Deployment risk:** If the local `.env` file reaches a production server unchanged, the system will run with no authentication.

~~**Problem 3: Half of all union-employer relationships are invisible.**~~ **FIXED (confirmed 2026-02-19 by all three independent audits).** Zero orphaned employer relationships. Fix was applied during deduplication (3,531 records repointed, 52,760 historical employers added to deduped table) but was never documented as resolved. The CRITICAL label here was a phantom â€” this problem does not exist in the current database.

### HIGH â€” Fix Before Letting Others Use It

~~**Problem 4: The scorecard only covers ~15% of employers.**~~ **FIXED (Phase E3).** Unified scorecard (`mv_unified_scorecard`) now covers all 146,863 F-7 employers using signal-strength scoring.

~~**Problem 5: Two separate scorecards with different logic.**~~ **FIXED (Phase E3).** One unified scorecard pipeline. Old scorecard (`mv_organizing_scorecard`) kept for backward compatibility but is no longer the primary output.

~~**Problem 6: The matching pipeline has two bugs.**~~ **FIXED (Phase B1-B3, hardening updated 2026-02-19).** Tier ordering corrected (strict-to-broad: EIN > name+city+state > name+state > aggressive > Splink > trigram). Best-match-wins replaces first-hit-wins. Splink name-similarity floor is now enforced in both main fuzzy matching and collision disambiguation (`token_sort_ratio >= 0.70` default, configurable via `MATCH_MIN_NAME_SIM`).

~~**Problem 7: 166 missing unions covering 61,743 workers.**~~ **RESOLVED (2026-02-21).** All active orphans resolved. 29 crosswalk remaps + CWA District 7 devolution + 27 manual adds to unions_master. 138 historical (pre-2021) remain as expected. Active orphans: 0.

~~**Problem 8: Corporate hierarchy endpoints are broken.**~~ **FIXED (Phase A3).** 7 RealDictCursor indexing bugs fixed, route shadowing resolved.

**Problem 9: The platform only runs on one laptop.** *(Partially addressed)*
First-draft Docker setup now exists (`Dockerfile`, `docker-compose.yml`, `nginx.conf`), but CI/CD and automated maintenance are still not in place.

### MEDIUM â€” Important but Not Blocking

~~**Problem 10: Match quality dashboard inflates numbers.**~~ **FIXED (Phase A4).** API now shows both `total_match_rows` and `unique_employers_matched`.

~~**Problem 11: NLRB time-decay is a dead switch.**~~ **FIXED IN CODE (2026-02-19; pending MV refresh).** The unified scorecard builder now applies 7-year half-life decay on NLRB elections (`0.5^(years/7)` via exponential form) and uses latest-election dominance.

**Problem 12: Model B propensity score is basically random.** Accuracy of 0.53 â€” barely better than a coin flip â€” but it's scoring 145,000+ employers. Model A (0.72) is decent.

~~**Problem 13: Documentation keeps falling behind.**~~ **PARTIALLY ADDRESSED.** Three-AI audit (2026-02-19) applied corrections to PROJECT_STATE.md, CLAUDE.md, and this document. However, PIPELINE_MANIFEST.md script counts still drift from filesystem reality. Auto-generation of key metrics (tests, routes, row counts) is needed to prevent recurrence.

~~**Problem 14: 778 Python files with no manifest.**~~ **PARTIALLY ADDRESSED.** 129 active scripts remain (down from 530+), manifest created. `extract_ex21.py` syntax error is fixed. The 7 analysis scripts previously bypassing `db_config.py` were migrated to shared `get_connection`. Remaining cleanup is broader script consolidation/archival.

**Problem 15: Database larger than needed.** Raw GLEIF schema is 12.1 GB (64% of total DB). Only `gleif_us_entities` and `gleif_ownership_links` in the public schema are actually used. The full GLEIF BODS dataset in its own schema is unused by any scoring or matching script. `osha_f7_matches` has 14.9% dead tuple bloat needing VACUUM.

---

### NEW PROBLEMS FOUND IN 2026-02-19 AUDIT

~~**Problem 16 [CRITICAL]: NLRB confidence scores use a different scale than everything else.**~~ **FIXED (2026-02-19).**
Applied SQL normalization in `unified_match_log` (`17,516` rows updated; max now `0.980`), and added matcher write-path normalization so NLRB confidence is written as 0.0-1.0 going forward.

~~**Problem 17 [CRITICAL]: Legacy scorecard detail endpoint returns 404 for all current employer IDs.**~~ **FIXED (2026-02-19).**
Removed numeric regex guard from `api/routers/scorecard.py` so string IDs pass through to detail lookup. Added API test coverage for non-numeric IDs.

**Problem 18 [HIGH]: Legacy match tables are out of sync with unified_match_log.**
Three different numbers for OSHA coverage: 42,976 (legacy table), 32,774 (mv_employer_data_sources), 31,459 (unified_match_log active). The failing test `test_osha_count_matches_legacy_table` is a symptom of this. Legacy tables need to be rebuilt from UML active matches after all re-runs complete.

~~**Problem 19 [HIGH]: PostgreSQL query statistics are completely stale.**~~ **FIXED (2026-02-19).**
Full-database `ANALYZE` completed across all public tables. Verification: `public_tables=174`, `tables_with_last_analyze=174`, elapsed `45.44s`. Next hardening step is autovacuum tuning to keep planner stats current.

**Problem 20 [HIGH]: NLRB flag/score mismatch â€” 3,996 employers flagged has_nlrb but cannot be scored.**
`mv_employer_data_sources` has `has_nlrb=true` for 3,996 employers, but no NLRB score can be computed for them because they have no rows in `nlrb_participants.matched_employer_id`. The flag and the scoring pipeline use different linkage sources. **Code alignment completed on 2026-02-19** in `scripts/scoring/build_employer_data_sources.py` (canonical employer-participant + election linkage); **pending MV refresh** before counts in production views will reflect the fix.

~~**Problem 21 [MEDIUM]: BLS financial factor scores "no data" higher than "confirmed stagnant industry."**~~ **FIXED IN CODE (2026-02-19; pending MV refresh).**
`score_financial` logic in `scripts/scoring/build_unified_scorecard.py` was updated so no-data does not score higher than known stagnation.

**Problem 22 [LOW]: Old scorecard row count is declining across refreshes without explanation.**
Version history: 200,890 â†’ 199,414 â†’ 195,164. Investigation completed on 2026-02-19 (`docs/SCORECARD_SHRINKAGE_INVESTIGATION.md`): primary driver is legacy `osha_f7_matches` exclusion logic in old MV (`WHERE fm.establishment_id IS NULL`) combined with legacy/UML drift and superseded-without-active churn.

**Problem 23 [LOW]: IRS Business Master File table has 25 rows.**
`irs_bmf` contains a test load. The full BMF has ~1.8M tax-exempt organizations. Referenced in pipeline documentation but provides near-zero matching coverage. Load full dataset or remove from docs.

---

## PART 3: WHAT TO DO NEXT

### How This Plan Is Organized

The key insight from the three-AI review: **fix data correctness before deployment.** It doesn't matter if the platform runs beautifully in a container if the scores it produces are misleading.

The phases below are ordered by dependency â€” each one builds on what came before. Some can run in parallel where noted.

---

### Phase A: Fix the Foundation (Estimated: 1-2 weeks)

**The goal:** Fix the problems that make the platform's core output untrustworthy.

**Task A1: Fix the F-7 relations orphan problem.**

This is the single most impactful fix. Half of all union-employer relationships are invisible because the relations table points to employer IDs that were retired during deduplication. A merge log exists (21,608 entries) recording which old IDs merged into which new ones â€” this is the key to reconnecting them.

*How this works:* Think of it like a phone book where half the entries have the wrong phone number. The merge log is a list that says "old number 555-1234 is now 555-5678." We go through every entry with an old number and update it to the new one.

**Checkpoints:**
1. Snapshot "before" numbers â€” total relationships, connected vs orphaned, workers covered, spot-check 5-10 specific employers
2. Map the merge log â€” how many orphans can be fixed via the log? Any without log entries? Any cases where one old ID merged into multiple new ones?
3. Dry run on 100 sample relationships â€” verify the mappings are correct, manually spot-check a few
4. Run the full update inside a database transaction (so it can be rolled back if anything goes wrong)
5. Verify "after" numbers â€” should see ~100% connected vs the current ~50%
6. Handle leftovers â€” orphans not in the merge log get matched by name/location, added to the deduped table, or flagged for manual review
7. Apply the same fix to the NLRB cross-reference table (14,150 orphaned links)

*Why this matters:* Until this is fixed, any query about union-employer relationships is silently missing half the data. Every downstream feature â€” the scorecard, the corporate family view, the search results â€” is working with an incomplete picture.

**Task A2: Fix the scorecard to use fresh data.**
Update the scoring materialized view to pull from all available OSHA/NLRB data (through 2025), not just the 2012-2016 subset. After rebuilding, the scorecard should clearly show when each piece of data was last updated.

*Why this matters:* This is the platform's primary output. If it's based on decade-old data, it could actively mislead organizers.

**Task A3: Fix the broken corporate hierarchy endpoints.**
Correct the column name reference in the 5 corporate API endpoints. The data exists, the endpoints exist â€” they just need to point at the right column.

*Why this matters:* Quick win. The corporate family view is one of the most valuable features for organizers, and it's broken by a simple naming error.

**Task A4: Fix the match quality dashboard.**
Change the API to count distinct employers matched, not total match rows. This gives an honest picture of data coverage.

**Task A5: Investigate the F-7 time boundaries.**
The database has 146,863 employer records â€” 67,552 labeled "current" and 79,311 "historical." But there's no documented definition of what year marks the boundary between current and historical. Figure out: What years does the data actually cover? When does "current" begin? Are there filing gaps (years where an employer appears, disappears, then reappears)?

*Why this matters:* Without understanding the time dimension, we can't tell users whether a relationship is active right now or ended 10 years ago.

**You're done when:**
- Zero orphaned relationships in f7_union_employer_relations
- Zero orphaned links in the NLRB cross-reference
- The scorecard uses the latest available data
- All corporate hierarchy endpoints return valid responses
- The match quality dashboard reports accurate, distinct-employer rates
- The time boundary between "current" and "historical" is documented

---

### Phase B: Fix the Matching Pipeline (Estimated: 1-2 weeks)

**The goal:** Make the connections between databases more accurate, so everything built on top of them is more reliable.

**Task B1: Reorder matching tiers strict-to-broad.**
Right now, some looser matching rules run before stricter ones. This means the system sometimes accepts a weak match when a strong one was available. Reorder so: EIN exact â†’ normalized name+state â†’ address-enhanced â†’ aggressive normalization â†’ fuzzy.

*Why this matters:* Every wrong match cascades â€” OSHA violations get attributed to the wrong employer, scores become unreliable, and an organizer might get bad information about a target.

**Task B2: Fix the first-hit-wins / name collision bug.**
When two different companies normalize to the same name (like "ABC Services" in New York and "ABC Services" in New Jersey), the system currently keeps whichever it saw first and drops the other. Fix this to use additional information (city, address, industry) to distinguish them, or flag ambiguous cases for review instead of silently picking one.

**Task B3: Bring Splink back into the fuzzy matching tier.**
The current fuzzy tier uses trigram matching â€” a simple method that only looks at how similar two names are as strings of characters. Splink is a more sophisticated tool already in the project that weighs multiple pieces of evidence (name similarity, state, city, ZIP, industry, address) and calculates an actual probability that two records are the same entity.

*How this is different:* Trigram matching sees "Springfield Hospital" and "Springfield Health Center" and just measures letter-by-letter similarity. Splink sees the names are somewhat similar AND they're in the same city AND the same state AND the same industry, and concludes there's a 94% chance they're the same place. It's smarter because it uses more clues, not just the name.

*Why bring it back now:* Since we're re-running matches anyway after fixing the tier ordering, upgrading the fuzzy tier at the same time means we only do one round of re-matching instead of two. Splink is already installed and configured â€” it was used for earlier deduplication work.

**Task B4: Re-run affected match tables.**
After the fixes above, re-run the matching pipeline for OSHA (the most affected source â€” 37% of its matches use a low-confidence fuzzy method) and any other sources with quality issues.

**Task B5: Add confidence flags to the UI.**
Tag every match with a confidence level. Matches above 0.9 confidence get no flag (they're reliable). Matches below 0.7 get flagged as "probable match â€” verify if critical." This lets organizers know when to trust a connection and when to double-check.

**You're done when:**
- Matching tiers run in strict-to-broad order
- Name collisions are handled (distinguished or flagged, not silently dropped)
- Splink is active as the fuzzy matching tier
- OSHA and other affected match tables have been re-run
- The UI shows confidence indicators on matches

---

### Phase C: Investigate and Clean Up Missing Data (Estimated: 1 week)

**The goal:** Track down the 195 missing unions and understand what's happening with the OLMS data we're not using yet.

*Can run in parallel with Phase B.*

~~**Task C1: Check the file number crosswalk for the 195 missing unions.**~~ **DONE (2026-02-18).** 29 remapped via crosswalk. 166 remaining. CWA District 7 deferred.

~~**Task C2: Manual OLMS lookup for the top 10-20 missing unions by worker count.**~~ **DONE (2026-02-21).** Investigation found all 166 orphan fnums are ghost file numbers with zero lm_data filing history. No names, no filings, no crosswalk matches. Only CWA District 7 (12590) had crosswalk entries to 5 successor locals.

~~**Task C3: Categorize and resolve.**~~ **DONE (2026-02-21).** Resolution script (`scripts/maintenance/resolve_missing_unions.py`) applied:
- **CWA_GEO:** 12590 resolved -- 38 relations remapped to 5 state-matched successors (CO, MN, TX, CA, OR), 42 relations in unmapped states kept under 12590 (added to unions_master). 38,192 workers restored.
- **HISTORICAL:** 138 ghost fnums (pre-2021) classified as historical defunct unions. Relations preserved for record.
- **MANUAL_ADD:** 27 active (post-2021) ghost fnums manually identified as locals of known national affiliates (AFSCME, SEIU, ATU, IBT/GCC, IATSE, UAW, USW, IBB, IAM, IUOE, SPFPA, NABET-CWA, Workers United) and added to `unions_master`.
- **Audit trail:** 166 entries in `union_fnum_resolution_log` table (CWA_GEO:1, HISTORICAL:138, MANUAL_ADD:27).
- **Result:** Active orphans: **0**. Historical orphans: 138 fnums, 344 rows, 19,155 workers. 7 new tests (464 total, 463 pass).

**Task C4: Catalog the unused OLMS annual report tables.**
Document what's in the four annual report tables that aren't being used yet. Determine which fields are most valuable for the platform. Priority ranking based on our planning session:
- **Tier 1 (high value, integrate soon):** Organizing spend percentage from disbursements, membership growth/decline trends
- **Tier 2 (useful context, later):** Union financial health from assets/investments
- **Future project:** Officer/leadership data combined with compensation analysis

*Why this matters:* These tables enrich the union side of the platform â€” helping answer "which union is best positioned to run this campaign?" rather than just "which employer should be targeted?" The platform is currently strong on employer targeting and weaker on union capacity assessment.

**You're done when:**
- The crosswalk has been checked against all 195 missing file numbers
- The top 20 missing unions by worker count have been manually researched
- Each missing union is categorized (merged, dissolved, reorganized, error, or unknown)
- Resolved unions have been remapped in the relations table
- A written catalog exists documenting what's in the unused OLMS tables and what's most valuable

---

### Phase D: Security, Cleanup, and Project Organization (Estimated: 1-2 weeks)

**The goal:** Make the platform secure, shrink the database, and organize the project so that all AI tools (Claude Code, Codex, Gemini) can work with it effectively.

*Can start during Phase B.*

**Task D1: Harden authentication.**
Remove `DISABLE_AUTH=true` from the default configuration. Make the system refuse to start without proper security credentials. Keep a development override, but make it something you actively opt into.

**Task D2: Archive the raw GLEIF data (~12 GB recovery).**
Back up the 53+ million rows of raw global corporate ownership data to a compressed file, then drop those tables. Only 379,192 US entities were extracted, and only 605 actual matches resulted. The raw data can be restored from backup if ever needed.

**Task D3: Drop unused database indexes (~1.67 GB recovery).**
299 confirmed unused indexes. Dropping them reclaims space and speeds up data inserts.

**Task D4: Create a script manifest.**
A single document listing every active script, what it does, and in what order it should run. Organized by pipeline stage: ETL loading â†’ matching â†’ scoring â†’ API. If it's not in the manifest, it's not part of the active system. This is the guide that any AI tool or human developer reads to understand "what runs, and in what order."

**Task D5: Move dead and one-time scripts to archive.**
The 3 dead API monoliths, scripts referencing nonexistent tables, one-time analysis scripts that already ran, and the 259 scripts with broken credential patterns â€” move all of these out of the active directories into a clearly labeled archive. Not deleted, just out of the way.

**Task D6: Delete redundant data files (~9.3 GB recovery).**
NLRB SQLite databases (4 copies, 3.79 GB), SQL dumps that have been loaded, PostgreSQL installers â€” all already imported into PostgreSQL and just taking up disk space.

**Task D7: Fix the credential pattern.**
The 259 scripts with the broken `password='os.environ.get(...)'` string literal â€” either fix them to use the correct `db_config` import (mechanical find-and-replace) or accept they're archive-only and move them.

**Task D8: Create a shared PROJECT_STATE.md for multi-AI workflow.**
A single document that Claude Code, Codex, and Gemini all read at the start of any session. Contains:
- Section 1: Database connection and startup (must be right)
- Section 2: Table inventory (auto-generated from a script that queries the live database)
- Section 3: Active pipeline (pulled from the script manifest)
- Section 4: Current status and known issues (manually updated after each work session)
- Section 5: Recent decisions (last 5-10 sessions worth â€” the handoff notes between AI sessions)
- Section 6: Design rationale (the "why" behind key choices)

Sections 2 and 3 should be auto-generated so they never go stale. A quick script run before each session regenerates them from the live database and file system.

**Task D9: Full documentation refresh.**
Update CLAUDE.md and README.md to reflect the actual current state. Fix all 19 known inaccuracies in CLAUDE.md, including the wrong startup command. Archive all old roadmap versions (v10, v11, v12, v13, TRUE, previous unified) with clear "superseded by this document" notes.

**Task D10: Fix freshness metadata.**
Correct the entry that says contracts run through "3023" and review all other freshness entries for similar issues.

**You're done when:**
- The platform refuses to start without security credentials
- The database is under 8 GB
- There's a script manifest showing which scripts are active
- Dead/one-time scripts are archived out of active directories
- PROJECT_STATE.md exists with auto-generated sections
- CLAUDE.md, README.md are accurate
- Only one current roadmap exists (this document)

---

### Phase E: Rebuild the Scorecard (Estimated: 2-3 weeks)

> **NOTE:** The scoring system described below has been superseded by `UNIFIED_PLATFORM_REDESIGN_SPEC.md` Section 2, which defines 8 weighted factors (3x/2x/1x tiers), percentile-based tier labels, and a weighted-average final score. See the Redesign Spec for the authoritative scoring design.

**The goal:** Replace the current fragmented scoring system with a single unified pipeline that scores every employer based on whatever data is available for them.

This is the most important design change in the roadmap. Right now there are two separate scorecards (OSHA-based and Mergent-based) covering only ~15% of employers. The new system scores all ~147K employers through one pipeline.

**The core design principle: signal-strength scoring.**

Instead of scoring every employer on all factors (which penalizes employers with missing data), the new system only scores each employer on factors where data actually exists. Missing factors are excluded from the calculation, not treated as zero.

*Example:* If an employer has OSHA violations, NLRB activity, and government contracts â€” but no wage theft data and no 990 filing â€” it gets scored on 3 factors out of the possible total. The score reflects "how strong are the available signals?" not "how many boxes did they check?" The platform displays both the score and a coverage percentage (like "scored on 3 of 8 factors, 38% data coverage") so the organizer knows how much information is behind the number.

**The scoring factors:**

| Factor | What It Measures | Source |
|--------|-----------------|--------|
| OSHA Safety Violations | Workplace danger â€” normalized by industry average, more recent violations weighted more | OSHA |
| NLRB Election Activity Nearby | Real organizing momentum in the area | NLRB |
| Wage Theft Violations | Employers who steal wages create conditions ripe for organizing | WHD + NYC Comptroller |
| Government Contracts | Creates leverage â€” organizers can pressure the government to enforce labor standards | USASpending + NY/NYC contract data (combined into one factor, not separate tiers) |
| Union Proximity | Are there already unions at this employer or its corporate siblings? Sibling unions (same parent, different location) weighted more heavily than distant corporate hierarchy connections | F-7 + corporate hierarchy |
| Financial Indicators & Industry Viability | Revenue, profitability, BLS 10-year growth projections for the industry | SEC, Mergent, 990, BLS projections |
| Employer Size | Sweet spot of 50-500 employees â€” large enough for meaningful bargaining unit, small enough to be reachable | All sources with employee counts |

**Factors dropped as standalone score components (with reasoning):**

- **Industry Union Density** â€” Every employer in the same industry gets the identical score. If you're comparing two hospitals, density tells you nothing about which one is the better target. It's useful context for an organizer to see on the profile page, but it doesn't help distinguish between employers. Kept as informational display, removed from score calculation.
- **Geographic Favorability** â€” Same problem. State-level data is too broad (every employer in New York gets the same boost). County-level has the same issue within a county. Dropped from the score. Geographic context is still displayed.

**Gower distance for comparables (separate from the score):**
Gower distance is a mathematical method for finding employers that are "similar" to each other across multiple dimensions. It's used to answer: "Show me employers that look like this one â€” same size, same industry, same region â€” so I can see how they compare." This is a separate feature from the score â€” it powers the "comparable employers" display, not the score itself.

**How to build it:**

1. **Create a master employer table** with a platform-assigned ID for each employer, mapped to all source IDs (F-7 employer ID, OSHA establishment ID, NLRB ID, etc.)
2. **Build a "what do we know?" lookup** â€” for each employer, which sources have data?
3. **Implement the universal scoring formula** â€” calculate each available factor, exclude missing ones, compute coverage percentage
4. **Add temporal decay** â€” recent violations and events weighted more than old ones (OSHA, WHD, NLRB all get decay)
5. **Wire up the Gower comparables engine** to the new master table

**Task E1: Design and create the master employer table.**
Each unique real-world employer gets one platform ID. The mapping layer records "platform employer #5678 = F-7 employer #12345 = OSHA establishment #67890." This is the foundation everything else connects through.

**Task E2: Build the "what do we know?" lookup for every employer.**
For each employer, query all matched sources and build the data availability map.

**Task E3: Implement the unified scoring formula.**
One pipeline, all employers, signal-strength approach. Missing factors excluded.

**Task E4: Add temporal decay to OSHA, WHD, and NLRB factors.**
More recent events weighted more heavily. Fix the broken NLRB decay (currently stuck at 1.0).

**Task E5: Rewire the Gower comparables engine.**
Connect it to the new master table instead of the old OSHA-only scorecard.

**Task E6: Add coverage percentage to all score displays.**
Every score shows "scored on X of Y factors" so organizers know how much data is behind the number.

**Task E7: Update the API and frontend to use the new scorecard.**
Replace the old scorecard endpoints with the new unified ones. Display the confidence/coverage information in the UI.

**You're done when:**
- One scorecard pipeline exists (the two old ones are retired)
- Every employer in the database has either a score or a clear "not enough data" indicator
- Every score displays its data coverage percentage
- Temporal decay is working on all applicable factors
- The Gower comparables engine runs on the new master table

---

### Phase F: Deployment and Testing (Estimated: 2-3 weeks)

**The goal:** Make the platform accessible to people beyond just you, and start getting real feedback.

**Task F1: Create a Docker setup.**
Docker packages the entire platform â€” code, database, web server, settings â€” into a container that runs identically on any computer. One command (`docker-compose up`) starts everything.

**Task F2: Set up automatic testing (CI/CD).**
Every time code is pushed to GitHub, all 359+ tests run automatically. If anything breaks, you know immediately.

**Task F3: Set up automated maintenance scheduling.**
Materialized view refreshes, database health checks, backups, data freshness checks â€” all on a weekly schedule instead of manual.

**Task F4: Deploy to a hosted environment.**
Using the Docker setup, deploy to a hosting service (Render, Railway, or similar). Set up HTTPS, monitoring, and alerts.

**Task F5: Recruit 3-5 beta testers.**
Invite organizers from different unions. Give them specific tasks and collect structured feedback.

**You're done when:**
- `docker-compose up` starts the platform from scratch
- Tests run automatically on every code push
- Weekly maintenance runs automatically
- The platform is accessible at a URL
- At least 3 organizers have used it and provided feedback

---

### Phase G: Master Employer Deduplication (Estimated: 3-4 weeks)

**The goal:** Build one authoritative row per real-world employer by improving the deduplication systems nationwide. The NY employer export (Feb 2026) proved the methodology — canonical grouping, multi-employer agreement detection, corporate hierarchy collapsing — but exposed significant gaps: only ~25% of employers are in canonical groups, multi-employer agreements inflate worker counts, and corporate subsidiaries remain fragmented. This phase hardens the identity layer that every downstream feature (scoring, exports, deep dives) depends on.

**Why now:** The matching pipeline is solid (Phase B done), the scoring depends on accurate employer identity, and the NY pilot showed exactly what's missing. The master employer key was deferred from Wave 4 because "building it too early bakes in matching errors" — but matching quality is now high enough to proceed. Phase C (166 missing unions) should be completed first or in parallel, since missing unions affect grouping completeness.

**Task G1: Improve canonical grouping algorithm.**
The current `build_employer_groups.py` uses name similarity + geographic proximity to group employers. It catches ~25% of employers (16,209 groups covering 40,304 of 146,863 employers). Add new grouping signals:
- **EIN-based linking:** Employers sharing the same EIN are definitively the same legal entity. EIN data comes from cross-matching with 990/SEC/SAM (~38% coverage).
- **Shared-union signal:** Two employers reported by the same union local in the same city are more likely to be related (e.g., different bargaining units at the same company).
- **NAICS confirmation:** Same industry code adds confidence to fuzzy name matches.
- **Address proximity:** Employers at the same street address are likely the same entity or closely related.

**Task G2: Multi-employer agreement detection nationwide.**
The NY export identified 78 multi-employer agreements using regex patterns (year+code, "Joint Policy," "Multiple Companies," RAB agreements, AMPTP, "and its members"). These patterns work nationally. Run detection against all 146,863 employers to flag agreements that inflate worker counts. Flagged rows get an `is_multi_employer_agreement` marker so they can be handled separately in scoring and display.

**Task G3: Corporate hierarchy collapsing.**
Use SEC EDGAR parent-subsidiary data (Exhibit 21), GLEIF ownership links (498,963 records), and Mergent corporate family data to identify employer records that are subsidiaries of the same parent. Example: Verizon has 11 separate rows in NY alone. Build a hierarchy table mapping subsidiaries to parent entities. Collapsing should be optional (a subsidiary may have a very different labor relations profile from its parent), but the linkage should always be visible.

**Task G4: Geographic normalization.**
City names from F7 data contain inconsistencies: "NYC" vs "New York," "Mt Vernon" vs "Mount Vernon," "Bklyn" vs "Brooklyn." Standardize city names to canonical forms using USPS conventions. This improves both canonical grouping accuracy (two employers at "NYC" and "New York" would currently be treated as different cities) and export quality.

**Task G5: Public sector research expansion.**
F7 only covers private-sector employers. The NY export added 20 manual public-sector entries (NYSUT 467K, CSEA 250K, DC37 150K, etc.) based on hand research. Expand to other large states — CA, IL, OH, PA, MI, WA at minimum. State PERB data (researched by Gemini, see `docs/STATE_PERB_RESEARCH.md`) can inform which states have structured data vs. which require manual research.

**Task G6: Quality audit.**
Spot-check grouping accuracy across 5-10 states. Measure false positive rate (different employers incorrectly grouped) and false negative rate (same employer not grouped). The NY work established verification patterns: check Starbucks (should be 1 group), Verizon (should be 1-2 groups), hospitals with similar names (should remain separate). Define acceptable error rates before building the master key.

**Task G7: Master employer key table.**
Create the definitive `master_employers` table: one row per real-world entity, all source IDs mapped (F7 employer_id, EIN, SEC CIK, GLEIF LEI, SAM UEI, DUNS). Every merge is recorded in a merge audit log and is reversible. Auto-merge for high-confidence cases (EIN match, canonical group), review queue for medium-confidence cases (fuzzy name + same city). Clear distinction between "same entity" merges and "related but different" hierarchy links.

**You're done when:**
- Canonical grouping covers 50%+ of employers (up from ~25%)
- Multi-employer agreements are flagged nationwide
- Corporate hierarchy links are visible for SEC/GLEIF-matched employers
- `master_employers` table exists with merge audit trail
- False positive rate on grouping is < 2% (spot-checked across 5+ states)
- Every downstream system (scoring, API, exports) can use the master key

---

## PART 4: WHAT COMES LATER

These are organized by priority and readiness, not rigid timelines. User feedback from Phase F should heavily influence which of these come first.

### Wave 1: Enrich What's Already There

**Integrate OLMS organizing spend and membership trends (Tier 1 OLMS data).**
Connect the annual report tables to the platform. Show how much each union spends on organizing (as a percentage of total budget) and whether their membership is growing or shrinking. This enriches the union side â€” helping answer "which union is best positioned to run this campaign?"

**Expose the BLS occupation matrix on employer profiles.**
The `bls_industry_occupation_matrix` table (113,473 rows) is already loaded. Build a simple lookup: given an employer's NAICS code, show the typical workforce composition. "78% security guards, 4% supervisors, 6% admin." This is Phase 1 of the workforce demographics feature â€” just making existing data visible.

**Improve corporate crosswalk coverage.**
Run the upgraded matching pipeline (from Phase B) against SEC, GLEIF, and Mergent to push crosswalk coverage beyond the current 37%. Add confidence fields to crosswalk links. This makes the corporate family view useful for more employers.

**Complete the IRS Business Master File integration.**
The table, loader script, and matching adapter already exist but aren't connected end-to-end. The IRS BMF has ~1.8 million tax-exempt organizations, which could significantly improve matching for nonprofit employers (currently only 11.9%).

**O*NET working conditions enrichment.**
O*NET publishes their entire database as clean CSV bulk downloads â€” completely free, no scraping or parsing needed. Load the Work Context and Job Zones tables. Joined to the BLS occupation matrix through standard occupation codes, this tells organizers what daily work life feels like for the people at a target employer: "typically involves standing for 8+ hours, working outdoors, low autonomy." Estimated effort: 2-3 hours.

### Wave 2: Expand Coverage and Intelligence

**ACS PUMS demographic overlay.**
Pre-compute occupation Ã— metro area demographic distributions for the ~50 largest metros using Census data. When showing a workforce profile, combine the industry staffing pattern (from the BLS matrix) with local demographics to estimate the racial, gender, age, and education makeup of a typical workforce at that employer. This is Phase 2 of workforce demographics.

**Revenue-to-headcount estimation.**
When the platform has revenue data for an employer (from SEC, Mergent, or 990), use industry-specific revenue-per-employee ratios to estimate headcount. All three research reports converge on similar formulas. This is Phase 3 of workforce demographics.

**OLMS union financial health (Tier 2 OLMS data).**
Load the assets/investments data to create a financial health indicator for unions. How much cash does the union have? What are their assets? This helps assess which unions have the resources to support a new organizing campaign.

**State PERB data expansion.**
Build scrapers for state Public Employee Relations Board data â€” starting with NY PERB, CA PERB, and IL ILRB. No open-source tools exist for this. This fills the gap where federal data doesn't cover public-sector employers and would be one of the platform's biggest differentiators.

**Parse SEC Exhibit 21 filings.**
Exhibit 21 is a list of subsidiaries that public companies file with the SEC. ~7,000 new filings per year, 100,000+ historical. The challenge is format variability â€” some are HTML tables, some are plain text, some are PDFs. Parsing requires either the CorpWatch parser (~90% accuracy) or an LLM approach. This significantly expands the corporate hierarchy data.

**Web scraper pipeline expansion.**
The AFSCME scraper proved the concept. Expand to Teamsters, SEIU, UFCW, UNITE HERE. On-demand deep-dive tool, not an always-running crawler.

**Prevailing wage intelligence.**
Cross-reference government subsidy databases (Davis-Bacon, state prevailing wage laws) with employer records. Employers receiving public money while paying below prevailing wages are prime organizing targets.

### Wave 3: Advanced Analytics and Research

**Union contract database.**
25,000+ downloadable collective bargaining agreements. Use AI-powered extraction to pull structured data: wage rates, benefit levels, contract duration, key provisions. Enables "here's what workers at similar employers negotiated."

**Propensity model refinement.**
With better match rates and real user feedback about which targets were actually promising, rebuild the propensity model. Needs more non-union training data to improve beyond current Model A (0.72 accuracy).

**Union-lost analysis.**
The 52,760 historical employers represent workplaces that once had union contracts but no longer do. Match them against OSHA/WHD/NLRB to research: what happened after the union left? This produces publishable research.

**OLMS officer/leadership combined project.**
The `ar_disbursements_emp_off` table (2.8M records) has every payment to union officers and employees. Combined with leadership succession analysis and compensation benchmarking, this is a substantial research project.

**Occupation-based similarity.**
Use BLS staffing patterns to find employers that employ similar types of workers, even if they're in different industries. A hospital and a university both employ janitorial staff, cafeteria workers, and maintenance crews.

### Wave 4: Platform Maturity

**Major frontend redesign.** *Fully specified in `UNIFIED_PLATFORM_REDESIGN_SPEC.md` — React + Vite migration with shadcn/ui, Zustand, TanStack Query. See Redesign Spec Section 5 for build order and Section 7 for page designs.*
Expand from current layout to: Search, Employer Profile, Targets, Union Explorer, and Admin/Settings. Happens after the data foundation is solid.

**Master employer key (full implementation).** *Core implementation pulled forward to Phase G (Master Employer Deduplication). Phase G builds the master_employers table, merge audit log, canonical grouping improvements, and corporate hierarchy links. Wave 4 adds the remaining features:* un-merge UI for manual corrections, auto-merge vs review queue tuning based on beta tester feedback, and cross-platform entity resolution (linking to external databases like OpenCorporates or Wikidata).

**Multi-tenant union workspaces.**
Each union gets its own view with territory assignments, saved searches, and campaign tracking.

**Campaign tracking.**
Organizers mark employers as "active campaign" and track progress from research to petition to election to contract. Over time builds a proprietary dataset of organizing outcomes.

**Board report generation.**
One-click PDF/CSV exports for union board presentations: territory overview, top targets with evidence, trend charts, data freshness statement.

**News and media monitoring.**
Automatically scan news for labor-related stories and link them to employers in the database.

---

## APPENDIX A: Timeline Estimates

| Phase | What | Estimated Time | Can Run In Parallel? |
|-------|------|----------------|---------------------|
| A: Fix Foundation | Orphans, scorecard freshness, broken endpoints | 1-2 weeks | Must come first |
| B: Fix Matching | Tier reorder, Splink, re-run matches | 1-2 weeks | After A starts |
| C: Missing Data | 195 unions, OLMS catalog | 1 week | Parallel with B |
| D: Security & Cleanup | Auth, GLEIF archive, manifest, docs, PROJECT_STATE | 1-2 weeks | Parallel with B/C |
| E: Rebuild Scorecard | Unified pipeline, master table, signal-strength scoring | 2-3 weeks | After A and B |
| F: Deploy & Test | Docker, CI/CD, hosting, beta testers | 2-3 weeks | After E |
| G: Master Employer Dedup | Canonical grouping, corporate hierarchy, master key | 3-4 weeks | After B; parallel with F |
| **Total to first real users** | | **8-13 weeks** | |

At 10 hours/week: ~22 weeks (5.5 months)
At 15 hours/week: ~15 weeks (3.8 months)
At 20 hours/week: ~12 weeks (3 months)
Full-time: ~9 weeks (2.2 months)

### Dependency Map

```
Phase A (Fix Foundation) â€”â€”â€” MUST COME FIRST
  |
  |â€”â€”> Phase B (Fix Matching) â€”â€”â€” needs A's orphan fix done
  |       |
  |       |â€”â€”> Phase E (Rebuild Scorecard) â€”â€”â€” needs good matching
  |               |
  |               |â€”â€”> Phase F (Deploy & Test) â€”â€”â€” needs working scorecard
  |
  |â€”â€”> Phase C (Missing Data) â€”â€”â€” can start during B
  |       |
  |       |â€”â€”> Phase G (Master Employer Dedup) â€”â€”â€” needs good matching + missing unions
  |
  |â€”â€”> Phase D (Security & Cleanup) â€”â€”â€” can start during B/C
```

**Critical path:** A â†’ B â†’ E â†’ F
**Parallel work:** C and D alongside B; G can run parallel with F (both need B done, G also benefits from C)
**Minimum viable path:** A + B + E (skip C/D for now) gets to a working scorecard faster, but skips important cleanup
**Master employer path:** A â†’ B â†’ C + G â†’ improves everything downstream (scoring, exports, all Waves)

---

## APPENDIX B: Decisions Made in Planning Session (Feb 16-17, 2026)

These are the key design decisions made during the roadmap review session. They're documented here so future AI sessions don't re-litigate settled questions.

| # | Topic | Decision |
|---|-------|----------|
| 1 | Stale materialized views | Fine for now, proof of concept first |
| 2 | F-7 orphan problem | Fix first (highest priority), detailed checkpoint procedure defined |
| 3 | OLMS unused data | Tier 1: organizing spend + membership trends. Tier 2: financial health. Future: officer/leadership |
| 4 | Matching bugs | Reorder strict-to-broad, fix first-hit-wins, bring Splink back, re-run matches, add confidence flags |
| 5 | Scorecard design | Unified pipeline, signal-strength scoring (missing=excluded not zero), all employers covered |
| 6 | Gower distance | Comparables display only, separate from score |
| 7 | Industry density | Drop as standalone score factor (not actionable), keep as informational display |
| 8 | Geographic favorability | Drop as standalone score factor (too broad), keep as informational display |
| 9 | Government contracts | Combine federal + state + municipal into one factor |
| 10 | Union proximity | Merge sibling unions + corporate hierarchy into one factor, weight siblings more heavily |
| 11 | BLS projections | Add industry growth/decline as component of financial indicators factor |
| 12 | Propensity model | Needs more non-union training data before improvement |
| 13 | Membership display | Distinguish "covered workers" vs "dues-paying members" in UI |
| 14 | 195 missing unions | **RESOLVED (2026-02-21).** 29 crosswalk remaps, CWA District 7 geographic devolution, 138 historical classified, 27 active manually added to unions_master. Active orphans: **0**. Historical: 138 (19,155 workers, pre-2021 defunct). |
| 15 | Corporate hierarchy | Fix broken API, improve crosswalk coverage. Master key deferred to long-term/when confident |
| 16 | FMCS data | Removed from roadmap |
| 17 | Web scraper | On-demand deep-dive tool, not always-running crawler |
| 18 | Workforce demographics | Phase 1: expose existing BLS matrix. Phase 2: ACS PUMS. Phase 3: revenue-to-headcount. Phase 4: O*NET |
| 19 | F-7 time boundaries | Investigate after orphan fix â€” define current vs historical, analyze filing gaps |
| 20 | Frontend redesign | Major redesign after data foundation is solid |
| 21 | Checkpoints | Built into every work session |
| 22 | Contract database | Lower priority, Wave 3 |
| 23 | Project organization | Script manifest, archive dead files, PROJECT_STATE.md for multi-AI workflow |
| 24 | Multi-AI context | Shared PROJECT_STATE.md with auto-generated sections, session handoff notes |
| 25 | Simpler communication | Explain all technical concepts in plain language, assume limited coding/database familiarity |
| 26 | Master employer dedup | Pulled forward from Wave 4 to new Phase G. NY export pilot (Feb 2026) proved the methodology; now harden nationwide. Improves canonical grouping (EIN, shared-union, address signals), adds multi-employer agreement detection, corporate hierarchy collapsing, geographic normalization, public sector expansion, and master employer key table with merge audit trail. |

---

## APPENDIX C: Key Principle

Every project described in this document is technically feasible and intellectually interesting. But the platform succeeds only if it becomes something organizers reach for when making real decisions about where to invest their limited time and resources.

The most important filter for deciding what to build next: **talk to people who would actually use it, and build the thing they ask for.**

