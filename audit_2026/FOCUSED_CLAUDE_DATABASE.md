# FOCUSED TASK: Database Integrity Deep Scan — CLAUDE CODE
# Run AFTER the full audit is complete

You already completed a full audit. Now go deeper on the database layer specifically. Connect to olms_multiyear and run these targeted investigations.

## TASK 1: Orphan Chain Analysis
Trace every orphan record across the entire system. Start with the 824 union file number orphans, but then check:
- Do any osha_f7_matches point to deleted employers?
- Do any nlrb_participants reference cases that don't exist?
- Do any corporate_identifier_crosswalk entries point to missing entities?
- Do any scoring records reference employers that have been removed?

Build a complete "orphan map" showing which tables have broken references to which other tables and how many. Save to docs/ORPHAN_MAP_2026.md

## TASK 2: Deduplication Verification
The platform claims 70.1M raw members → 14.5M deduplicated. Verify this by:
1. Query the raw totals from lm_data
2. Query the deduplicated totals from v_union_members_deduplicated
3. Check the multi-employer agreement handling — does the dedup logic correctly handle cases where one contract covers multiple employers?
4. Spot-check 10 unions with the largest membership — do their deduplicated numbers make sense?
5. Compare state-level totals against the epi_state_benchmarks table

## TASK 3: Match Quality Sampling
For each matching scenario (OSHA, NLRB, WHD, 990, Mergent), pull 20 random matches and evaluate:
- Does the match look correct? (Do the names/addresses actually refer to the same entity?)
- What matching tier was used?
- Are there obvious false positives (different companies matched together)?
- Are there obvious false negatives (same company that should have matched but didn't)?

Save results as a match quality report: docs/MATCH_QUALITY_SAMPLE_2026.md

## TASK 4: Scoring Distribution Analysis
For the 24,841 scored employers:
1. What's the actual score distribution? (histogram-style: 0-10, 10-20, ..., 90-100)
2. Which scoring factors contribute most vs least?
3. Are there employers scored 0 that probably shouldn't be? (e.g., large employers with known union activity)
4. Are there employers scored very high that look suspicious?
5. Do the priority tiers (TOP/HIGH/MEDIUM/LOW) produce sensible groupings?

## TASK 5: Geographic Coverage Gaps
1. Which states have the fewest employers in the database?
2. Which states have the worst OSHA match rates?
3. Are there metro areas with many employers but no OSHA/NLRB connections?
4. Does the density estimation produce any obviously wrong results? (Check the extremes)

Save all findings to docs/FOCUSED_AUDIT_CLAUDE_DATABASE.md
